"""Audit trail for student access. UMA-003 / T1-014.

The denial tests matter most. An allowed read being logged is easy, a
denied one surviving the exception that follows it is the hard part.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data_access.repositories.student_repository import (
    ANONYMOUS,
    AccessDenied,
    Actor,
    StudentRepository,
)
from database.audit import ALLOWED, CREATE, DENIED, LIST, VIEW, AccessLog
from database.database import Base
from database.models import Role, User
from database.students import Student
from security.keys import generate_key

KEY = generate_key()
ADMIN = Actor(user_id=99, role="Admin")


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as s:
        role = Role(name="Student")
        s.add(role)
        s.flush()
        jane = User(username="jane", password_hash="x", first_name="Jane",
                    last_name="Smith", email="jane@school.edu", role_id=role.id)
        s.add(jane)
        s.flush()
        s.add_all([
            Student(user_id=jane.id, student_number="S-001", first_name="Jane",
                    last_name="Smith", grade_level=10, date_of_birth="2010-04-02",
                    home_address="12 Oak St", guardian_name="Mary Smith",
                    guardian_email="mary@example.com"),
            Student(student_number="S-002", first_name="Bob", last_name="Jones",
                    grade_level=11, date_of_birth="2009-08-19", home_address="34 Elm St",
                    guardian_name="Paul Jones", guardian_email="paul@example.com"),
        ])
        s.commit()
        yield s
    keys_module._cached = None


@pytest.fixture
def repo(db):
    return StudentRepository(db)


def entries(db, **where):
    q = db.query(AccessLog)
    for k, v in where.items():
        q = q.filter(getattr(AccessLog, k) == v)
    return q.all()


def _id(db, number):
    return db.query(Student).filter(Student.student_number == number).one().id


# -- allowed -------------------------------------------------------------

def test_a_read_is_logged(repo, db):
    sid = _id(db, "S-001")
    repo.get(ADMIN, sid)
    row = entries(db, action=VIEW)[0]
    assert row.outcome == ALLOWED
    assert row.actor_user_id == 99
    assert row.actor_role == "Admin"
    assert row.resource_id == sid


def test_listing_is_logged_with_a_count(repo, db):
    repo.list_visible(ADMIN)
    row = entries(db, action=LIST)[0]
    assert row.outcome == ALLOWED
    assert "2 of 2" in row.detail


def test_creating_is_logged(repo, db):
    repo.create(ADMIN, student_number="S-003", first_name="New", last_name="Kid",
                grade_level=9, date_of_birth="2011-01-01", home_address="56 Pine St",
                guardian_name="A Parent", guardian_email="p@example.com")
    db.commit()
    assert entries(db, action=CREATE)[0].outcome == ALLOWED


# -- denied, which is the point ------------------------------------------

def test_a_refused_read_is_logged(repo, db):
    jane = Actor(user_id=1, role="Student")
    with pytest.raises(AccessDenied):
        repo.get(jane, _id(db, "S-002"))

    row = entries(db, outcome=DENIED)[0]
    assert row.action == VIEW
    assert row.actor_role == "Student"
    assert row.resource_id == _id(db, "S-002")


def test_the_denied_row_survives_a_rollback(repo, db):
    """The reason _log commits instead of flushing.

    A denied request ends in an exception and the session gets rolled back,
    which would take a merely flushed row with it.
    """
    jane = Actor(user_id=1, role="Student")
    with pytest.raises(AccessDenied):
        repo.get(jane, _id(db, "S-002"))
    db.rollback()
    assert len(entries(db, outcome=DENIED)) == 1


def test_anonymous_listing_is_logged(repo, db):
    repo.list_visible(ANONYMOUS)
    row = entries(db, outcome=DENIED)[0]
    assert row.action == LIST
    assert row.actor_user_id is None
    assert row.actor_role is None


def test_a_refused_create_is_logged(repo, db):
    with pytest.raises(AccessDenied):
        repo.create(Actor(user_id=1, role="Student"), student_number="S-009",
                    first_name="x", last_name="y", grade_level=9,
                    date_of_birth="2011-01-01", home_address="x",
                    guardian_name="x", guardian_email="x@example.com")
    assert entries(db, action=CREATE, outcome=DENIED)


# -- what must not end up in there ---------------------------------------

def test_the_log_doesnt_copy_the_record_into_itself(repo, db):
    """Storing the address to prove someone read it would just put a
    plaintext copy somewhere else and undo the encryption."""
    repo.get(ADMIN, _id(db, "S-001"))
    row = entries(db, action=VIEW)[0]
    blob = " ".join(str(v) for v in [row.detail, row.action, row.resource_type])
    for leaked in ("12 Oak St", "mary@example.com", "2010-04-02", "Jane"):
        assert leaked not in blob


def test_role_is_stored_as_it_was_not_looked_up_later(repo, db):
    """Someone promoted tomorrow shouldn't look like an admin yesterday."""
    repo.get(Actor(user_id=7, role="Teacher", assigned_student_ids=(_id(db, "S-001"),)),
             _id(db, "S-001"))
    assert entries(db, action=VIEW)[0].actor_role == "Teacher"


def test_every_attempt_lands_in_order(repo, db):
    sid = _id(db, "S-001")
    repo.get(ADMIN, sid)
    with pytest.raises(AccessDenied):
        repo.get(Actor(user_id=1, role="Student"), _id(db, "S-002"))
    repo.list_visible(ADMIN)

    rows = db.query(AccessLog).order_by(AccessLog.id).all()
    assert [r.outcome for r in rows] == [ALLOWED, DENIED, ALLOWED]
    assert [r.action for r in rows] == [VIEW, VIEW, LIST]
