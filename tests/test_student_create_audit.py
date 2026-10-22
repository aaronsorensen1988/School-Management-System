"""Enrolling a student through the web form gets audited. T2-036.

Before this the form called a service that opened its own database session
and wrote the row itself, so the create never touched the repository and
nothing appeared in the access log. Every other way of reading or writing a
student was logged. The one that actually adds a child to the system wasn't.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.audit import ALLOWED, CREATE, DENIED, AccessLog
from database.database import Base, get_db
from database.models import Role, User
from database.students import Student
from security.keys import generate_key
from utils.security import hash_password

KEY = generate_key()

GOOD_FORM = {
    "student_number": "S-500",
    "first_name": "Maya",
    "last_name": "Lopez",
    "date_of_birth": "2012-02-08",
    "grade_level": "8",
    "home_address": "123 Main St",
    "guardian_name": "Ana Lopez",
    "guardian_email": "ana@example.com",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    monkeypatch.setenv("SMS_SESSION_SECRET", "test-secret-not-a-real-one")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    # StaticPool so the app thread and the test share one in-memory database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session(engine) as s:
        admin_role = Role(name="Admin")
        student_role = Role(name="Student")
        s.add_all([admin_role, student_role])
        s.flush()
        s.add_all([
            User(username="admin", password_hash=hash_password("admin-pw"),
                 first_name="System", last_name="Admin", email="admin@school.edu",
                 role_id=admin_role.id),
            User(username="jane", password_hash=hash_password("jane-pw"),
                 first_name="Jane", last_name="Smith", email="jane@school.edu",
                 role_id=student_role.id),
        ])
        s.commit()

    import api

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    api.app.dependency_overrides[get_db] = override_get_db
    c = TestClient(api.app, follow_redirects=False)
    c.session_factory = TestSession
    yield c
    api.app.dependency_overrides.clear()
    keys_module._cached = None


def _login(client, who):
    client.post("/login", data={"username": who, "password": f"{who}-pw"})


def _rows(client, **where):
    with client.session_factory() as db:
        q = db.query(AccessLog)
        for k, v in where.items():
            q = q.filter(getattr(AccessLog, k) == v)
        return q.all()


def _students(client):
    with client.session_factory() as db:
        return db.query(Student).all()


# -- the hole this closes -----------------------------------------------

def test_enrolling_through_the_form_is_logged(client):
    _login(client, "admin")
    r = client.post("/students/new", data=GOOD_FORM)
    assert r.status_code == 303

    rows = _rows(client, action=CREATE, outcome=ALLOWED)
    assert len(rows) == 1
    assert rows[0].actor_role == "Admin"
    assert rows[0].resource_id == _students(client)[0].id


def test_the_student_actually_gets_saved(client):
    """The logging is the new part. Don't break the part that worked."""
    _login(client, "admin")
    client.post("/students/new", data=GOOD_FORM)

    saved = _students(client)
    assert len(saved) == 1
    assert saved[0].student_number == "S-500"
    assert saved[0].home_address == "123 Main St"


def test_a_refused_enrolment_is_logged_too(client):
    """This never used to reach the repository at all. The route turned it
    away itself and nothing recorded the attempt."""
    _login(client, "jane")
    r = client.post("/students/new", data=GOOD_FORM)
    assert r.status_code == 403

    rows = _rows(client, action=CREATE, outcome=DENIED)
    assert len(rows) == 1
    assert rows[0].actor_role == "Student"
    assert _students(client) == []


def test_a_refused_user_is_not_told_what_the_form_wants(client):
    """Permission is checked before validation. Wiring this up the obvious
    way got that backwards and a student submitting an empty form got the
    list of required fields back instead of a refusal."""
    _login(client, "jane")
    r = client.post("/students/new", data={"student_number": "S-999"})

    assert r.status_code == 403
    assert "required" not in r.text.lower()
    assert len(_rows(client, action=CREATE, outcome=DENIED)) == 1


# -- what has to keep working -------------------------------------------

def test_a_bad_form_is_still_rejected_and_logs_nothing(client):
    _login(client, "admin")
    bad = dict(GOOD_FORM, student_number="", first_name="")
    r = client.post("/students/new", data=bad)

    assert r.status_code == 400
    assert "required" in r.text.lower()
    assert _students(client) == []
    assert _rows(client, action=CREATE) == []


def test_a_duplicate_student_number_is_still_rejected(client):
    _login(client, "admin")
    client.post("/students/new", data=GOOD_FORM)
    r = client.post("/students/new", data=dict(GOOD_FORM, first_name="Someone"))

    assert r.status_code == 400
    assert "already exists" in r.text
    assert len(_students(client)) == 1
    # the first one logged, the duplicate never got as far as the repository
    assert len(_rows(client, action=CREATE)) == 1


def test_an_anonymous_post_goes_to_login(client):
    r = client.post("/students/new", data=GOOD_FORM)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"
    assert _students(client) == []


# -- the student and its audit row travel together ----------------------

def test_the_audit_row_and_the_student_are_one_transaction(client):
    """create() flushes the audit row into the caller's transaction rather
    than committing it separately, so a failed save can't leave a log entry
    claiming a student was added when none was."""
    _login(client, "admin")
    client.post("/students/new", data=GOOD_FORM)

    students = _students(client)
    logged = _rows(client, action=CREATE, outcome=ALLOWED)
    assert len(students) == len(logged) == 1
    assert logged[0].resource_id == students[0].id
