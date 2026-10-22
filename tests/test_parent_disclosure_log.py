"""Parent portal views land in the access log. SIEM-006 / T2-008.

The portal already went through the repository, so a LIST row was being
written. That says a parent looked at something and how many rows came
back. It doesn't say which child, and for FERPA that's the only part
anybody cares about. These cover the per child rows and the people who ask
for the portal without being a parent.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from data_access.repositories.student_repository import Actor, StudentRepository
from database.audit import ALLOWED, DENIED, LIST, VIEW, AccessLog
from database.database import Base, get_db
from database.models import Role, User
from database.students import Student
from security.keys import generate_key
from utils.security import hash_password

KEY = generate_key()


def _student(**kw):
    base = dict(student_number="S-1", first_name="A", last_name="B", grade_level=5,
                date_of_birth="2014-01-01", home_address="1 St",
                guardian_name="G", guardian_email="g@e.com")
    base.update(kw)
    return Student(**base)


# -- repository level ----------------------------------------------------

@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as s:
        s.add_all([
            _student(student_number="S-001", first_name="Maya", last_name="Lopez"),
            _student(student_number="S-002", first_name="Theo", last_name="Lopez"),
            _student(student_number="S-003", first_name="Someone", last_name="Else"),
        ])
        s.commit()
        yield s
    keys_module._cached = None


def _ids(db, *numbers):
    return tuple(
        db.query(Student).filter(Student.student_number == n).one().id for n in numbers
    )


def test_each_child_shown_gets_its_own_row(db):
    """"1 of 12 rows" doesn't tell you whose record was handed over."""
    kids = _ids(db, "S-001", "S-002")
    parent = Actor(user_id=70, role="Parent", child_ids=kids)
    repo = StudentRepository(db)

    repo.record_parent_disclosure(parent, repo.list_visible(parent))

    rows = db.query(AccessLog).filter(AccessLog.action == VIEW).all()
    assert sorted(r.resource_id for r in rows) == sorted(kids)
    assert all(r.outcome == ALLOWED for r in rows)
    assert all(r.actor_role == "Parent" for r in rows)


def test_the_rows_say_they_came_from_the_portal(db):
    """So a disclosure review can pick parent accesses out of staff ones."""
    parent = Actor(user_id=70, role="Parent", child_ids=_ids(db, "S-001"))
    repo = StudentRepository(db)
    repo.record_parent_disclosure(parent, repo.list_visible(parent))

    row = db.query(AccessLog).filter(AccessLog.action == VIEW).one()
    assert row.detail == "parent portal"


def test_a_parent_only_logs_their_own_children(db):
    """The access rules already stop them seeing S-003. The log shouldn't
    claim they were shown it either."""
    kids = _ids(db, "S-001")
    parent = Actor(user_id=70, role="Parent", child_ids=kids)
    repo = StudentRepository(db)
    repo.record_parent_disclosure(parent, repo.list_visible(parent))

    rows = db.query(AccessLog).filter(AccessLog.action == VIEW).all()
    assert [r.resource_id for r in rows] == list(kids)


def test_a_parent_with_no_children_logs_no_disclosures(db):
    parent = Actor(user_id=70, role="Parent")
    repo = StudentRepository(db)
    repo.record_parent_disclosure(parent, repo.list_visible(parent))

    assert db.query(AccessLog).filter(AccessLog.action == VIEW).count() == 0


def test_a_refusal_is_recorded(db):
    teacher = Actor(user_id=50, role="Teacher")
    StudentRepository(db).record_portal_refusal(teacher)

    row = db.query(AccessLog).filter(AccessLog.outcome == DENIED).one()
    assert row.action == VIEW
    assert row.actor_role == "Teacher"
    assert row.detail == "parent portal"


# -- through the route ---------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    monkeypatch.setenv("SMS_SESSION_SECRET", "test-secret-not-a-real-one")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session(engine) as s:
        parent_role = Role(name="Parent")
        teacher_role = Role(name="Teacher")
        s.add_all([parent_role, teacher_role])
        s.flush()
        s.add_all([
            User(username="pat", password_hash=hash_password("pat-pw"), first_name="Pat",
                 last_name="Lopez", email="pat@e.com", role_id=parent_role.id),
            User(username="tess", password_hash=hash_password("tess-pw"), first_name="Tess",
                 last_name="Teacher", email="tess@school.edu", role_id=teacher_role.id),
        ])
        s.add(_student(student_number="S-001", first_name="Maya", last_name="Lopez"))
        s.commit()

    import api

    def override_get_db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    api.app.dependency_overrides[get_db] = override_get_db
    c = TestClient(api.app, follow_redirects=False)
    c.session_factory = TestSession
    yield c
    api.app.dependency_overrides.clear()
    keys_module._cached = None


def _logs(client, **where):
    with client.session_factory() as d:
        q = d.query(AccessLog)
        for k, v in where.items():
            q = q.filter(getattr(AccessLog, k) == v)
        return q.all()


def test_a_teacher_asking_for_the_portal_is_logged(client):
    client.post("/login", data={"username": "tess", "password": "tess-pw"})
    r = client.get("/parent/portal")

    assert r.status_code == 302
    assert r.headers["location"] == "/dashboard"
    row = _logs(client, outcome=DENIED, detail="parent portal")[0]
    assert row.actor_role == "Teacher"


def test_an_anonymous_visit_goes_to_login_and_logs_nothing(client):
    r = client.get("/parent/portal")
    assert r.headers["location"] == "/login"
    assert _logs(client, detail="parent portal") == []


def test_a_parent_visit_is_recorded_as_a_list(client):
    """What a parent is actually shown is covered at the repository level
    above, because current_actor doesn't put child ids on the Actor yet.
    See the note in test_a_parent_currently_sees_nothing."""
    client.post("/login", data={"username": "pat", "password": "pat-pw"})
    assert client.get("/parent/portal").status_code == 200
    assert _logs(client, action=LIST, actor_role="Parent")


def test_a_parent_currently_sees_nothing(client):
    """Not what we want, and not something T2-008 can fix.

    current_actor builds the Actor from the session and never fills in
    child_ids, because there's no parent to child table to fill them from.
    So list_visible has nothing to match on and every parent gets an empty
    portal. The T2-010 review flags the missing table as the first thing to
    move into the database.

    This test pins the current behaviour on purpose. When somebody adds the
    link it will fail, which is the point. Replace it then with one that
    asserts a parent sees their own child.
    """
    client.post("/login", data={"username": "pat", "password": "pat-pw"})
    client.get("/parent/portal")
    assert _logs(client, action=VIEW, detail="parent portal") == []
