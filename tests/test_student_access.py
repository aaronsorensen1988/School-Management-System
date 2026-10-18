"""Role checks on student records. UMA-003 / T1-013.

Point of these is the negative cases. It's easy to prove an admin can read
everything, the ones that matter are the people who shouldn't.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data_access.repositories.student_repository import (
    ANONYMOUS,
    AccessDenied,
    Actor,
    StudentRepository,
    redact,
)
from database.database import Base
from database.models import Role, User
from database.students import Student
from security.keys import generate_key

KEY = generate_key()


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as s:
        student_role = Role(name="Student")
        s.add(student_role)
        s.flush()

        # two student accounts, so "only your own" means something
        jane_user = User(username="jane", password_hash="x", first_name="Jane",
                         last_name="Smith", email="jane@school.edu", role_id=student_role.id)
        bob_user = User(username="bob", password_hash="x", first_name="Bob",
                        last_name="Jones", email="bob@school.edu", role_id=student_role.id)
        s.add_all([jane_user, bob_user])
        s.flush()

        s.add_all([
            Student(user_id=jane_user.id, student_number="S-001", first_name="Jane",
                    last_name="Smith", grade_level=10, date_of_birth="2010-04-02",
                    home_address="12 Oak St", guardian_name="Mary Smith",
                    guardian_email="mary@example.com"),
            Student(user_id=bob_user.id, student_number="S-002", first_name="Bob",
                    last_name="Jones", grade_level=11, date_of_birth="2009-08-19",
                    home_address="34 Elm St", guardian_name="Paul Jones",
                    guardian_email="paul@example.com"),
        ])
        s.commit()
        yield s
    keys_module._cached = None


@pytest.fixture
def repo(db):
    return StudentRepository(db)


def _id_of(db, number):
    return db.query(Student).filter(Student.student_number == number).one().id


def _user_id_of(db, username):
    return db.query(User).filter(User.username == username).one().id


# -- admin ---------------------------------------------------------------

def test_admin_sees_everyone(repo, db):
    admin = Actor(user_id=99, role="Admin")
    assert len(repo.list_visible(admin)) == 2
    assert repo.get(admin, _id_of(db, "S-001")).first_name == "Jane"


def test_admin_can_create(repo, db):
    admin = Actor(user_id=99, role="Admin")
    repo.create(admin, student_number="S-003", first_name="New", last_name="Kid",
                grade_level=9, date_of_birth="2011-01-01", home_address="56 Pine St",
                guardian_name="A Parent", guardian_email="parent@example.com")
    db.commit()
    assert db.query(Student).count() == 3


# -- student -------------------------------------------------------------

def test_student_sees_only_themselves(repo, db):
    jane = Actor(user_id=_user_id_of(db, "jane"), role="Student")
    visible = repo.list_visible(jane)
    assert [s.student_number for s in visible] == ["S-001"]


def test_student_cant_read_another_student(repo, db):
    jane = Actor(user_id=_user_id_of(db, "jane"), role="Student")
    with pytest.raises(AccessDenied):
        repo.get(jane, _id_of(db, "S-002"))


def test_student_cant_create(repo, db):
    jane = Actor(user_id=_user_id_of(db, "jane"), role="Student")
    with pytest.raises(AccessDenied):
        repo.create(jane, student_number="S-009", first_name="Fake", last_name="Kid",
                    grade_level=9, date_of_birth="2011-01-01", home_address="x",
                    guardian_name="x", guardian_email="x@example.com")


# -- teacher -------------------------------------------------------------

def test_teacher_sees_only_assigned_students(repo, db):
    teacher = Actor(user_id=50, role="Teacher",
                    assigned_student_ids=(_id_of(db, "S-001"),))
    visible = repo.list_visible(teacher)
    assert [s.student_number for s in visible] == ["S-001"]

    with pytest.raises(AccessDenied):
        repo.get(teacher, _id_of(db, "S-002"))


def test_teacher_with_no_roster_sees_nobody(repo):
    teacher = Actor(user_id=50, role="Teacher")
    assert repo.list_visible(teacher) == []


def test_teacher_cant_create(repo):
    teacher = Actor(user_id=50, role="Teacher")
    with pytest.raises(AccessDenied):
        teacher_fields = dict(student_number="S-010", first_name="x", last_name="y",
                              grade_level=9, date_of_birth="2011-01-01", home_address="x",
                              guardian_name="x", guardian_email="x@example.com")
        repo.create(teacher, **teacher_fields)


# -- parent --------------------------------------------------------------

def test_parent_sees_only_their_child(repo, db):
    parent = Actor(user_id=70, role="Parent", child_ids=(_id_of(db, "S-002"),))
    assert [s.student_number for s in repo.list_visible(parent)] == ["S-002"]
    with pytest.raises(AccessDenied):
        repo.get(parent, _id_of(db, "S-001"))


# -- nobody --------------------------------------------------------------

def test_anonymous_gets_nothing(repo, db):
    assert repo.list_visible(ANONYMOUS) == []
    with pytest.raises(AccessDenied):
        repo.get(ANONYMOUS, _id_of(db, "S-001"))


def test_unknown_role_gets_nothing(repo, db):
    # a role we never defined shouldn't fall through to allowed
    stranger = Actor(user_id=1, role="Janitor")
    assert repo.list_visible(stranger) == []
    with pytest.raises(AccessDenied):
        repo.get(stranger, _id_of(db, "S-001"))


def test_missing_student_is_a_lookup_error_not_access_denied(repo):
    admin = Actor(user_id=99, role="Admin")
    with pytest.raises(LookupError):
        repo.get(admin, 9999)


# -- field level ---------------------------------------------------------

SAMPLE = {
    "id": 1, "student_number": "S-001", "name": "Jane Smith", "grade": "10",
    "date_of_birth": "2010-04-02", "home_address": "12 Oak St",
    "guardian_name": "Mary Smith", "guardian_email": "mary@example.com",
}


def test_admin_sees_contact_details():
    assert redact(SAMPLE, Actor(user_id=99, role="Admin"))["home_address"] == "12 Oak St"


def test_teacher_doesnt_get_home_address():
    out = redact(SAMPLE, Actor(user_id=50, role="Teacher"))
    assert out["home_address"] is None
    assert out["guardian_email"] is None
    assert out["name"] == "Jane Smith"  # roster info still works


def test_student_sees_their_own_details():
    out = redact(SAMPLE, Actor(user_id=5, role="Student"), student_user_id=5)
    assert out["home_address"] == "12 Oak St"


def test_student_doesnt_see_someone_elses_details():
    out = redact(SAMPLE, Actor(user_id=6, role="Student"), student_user_id=5)
    assert out["home_address"] is None


def test_redact_doesnt_mutate_the_original():
    redact(SAMPLE, Actor(user_id=50, role="Teacher"))
    assert SAMPLE["home_address"] == "12 Oak St"
