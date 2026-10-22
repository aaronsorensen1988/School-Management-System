from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.session import current_actor
from data_access.repositories.student_repository import AccessDenied, StudentRepository
from database.database import Base
from database.models import Role, User
from database.parents import ParentStudent
from database.students import Student
from security.keys import generate_key


@pytest.fixture
def db(monkeypatch):
    key = generate_key()
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{key}")
    monkeypatch.setenv("SMS_ENCRYPTION_ACTIVE_KEY", "k1")

    from security import keys as keys_module

    keys_module.active_keyring(refresh=True)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        yield db

    keys_module._cached = None


@pytest.fixture
def parent_setup(db):
    parent_role = Role(name="Parent")
    student_role = Role(name="Student")

    db.add_all([parent_role, student_role])
    db.flush()

    parent = User(
        username="parent1",
        password_hash="x",
        first_name="Test",
        last_name="Parent",
        email="parent1@school.edu",
        role_id=parent_role.id,
    )

    other_parent = User(
        username="parent2",
        password_hash="x",
        first_name="Other",
        last_name="Parent",
        email="parent2@school.edu",
        role_id=parent_role.id,
    )

    student_user_a = User(
        username="student1",
        password_hash="x",
        first_name="Alice",
        last_name="Student",
        email="student1@school.edu",
        role_id=student_role.id,
    )

    student_user_b = User(
        username="student2",
        password_hash="x",
        first_name="Bob",
        last_name="Student",
        email="student2@school.edu",
        role_id=student_role.id,
    )

    db.add_all([
        parent,
        other_parent,
        student_user_a,
        student_user_b,
    ])
    db.flush()

    student_a = Student(
        user_id=student_user_a.id,
        student_number="S-100",
        first_name="Alice",
        last_name="Student",
        grade_level=8,
        date_of_birth="2012-01-01",
        home_address="100 Test St",
        guardian_name="Test Parent",
        guardian_email="parent1@school.edu",
    )

    student_b = Student(
        user_id=student_user_b.id,
        student_number="S-200",
        first_name="Bob",
        last_name="Student",
        grade_level=9,
        date_of_birth="2011-01-01",
        home_address="200 Test St",
        guardian_name="Other Parent",
        guardian_email="parent2@school.edu",
    )

    db.add_all([student_a, student_b])
    db.flush()

    link = ParentStudent(
        parent_user_id=parent.id,
        student_id=student_a.id,
    )

    db.add(link)
    db.commit()

    return {
        "parent": parent,
        "other_parent": other_parent,
        "student_a": student_a,
        "student_b": student_b,
    }


def _request_for(user):
    return SimpleNamespace(
        session={
            "user_id": user.id,
            "username": user.username,
        }
    )


def test_current_actor_loads_parent_child_ids(db, parent_setup):
    parent = parent_setup["parent"]
    student_a = parent_setup["student_a"]

    actor = current_actor(_request_for(parent), db)

    assert actor.role == "Parent"
    assert actor.user_id == parent.id
    assert actor.child_ids == (student_a.id,)


def test_parent_sees_only_linked_student(db, parent_setup):
    parent = parent_setup["parent"]
    student_a = parent_setup["student_a"]

    actor = current_actor(_request_for(parent), db)

    visible = StudentRepository(db).list_visible(actor)

    assert [student.id for student in visible] == [student_a.id]


def test_parent_cannot_open_unlinked_student(db, parent_setup):
    parent = parent_setup["parent"]
    student_b = parent_setup["student_b"]

    actor = current_actor(_request_for(parent), db)

    with pytest.raises(AccessDenied):
        StudentRepository(db).get(actor, student_b.id)


def test_parent_with_no_links_sees_no_students(db, parent_setup):
    other_parent = parent_setup["other_parent"]

    actor = current_actor(_request_for(other_parent), db)

    assert actor.role == "Parent"
    assert actor.child_ids == ()
    assert StudentRepository(db).list_visible(actor) == []


def test_duplicate_parent_student_link_is_rejected(db, parent_setup):
    parent = parent_setup["parent"]
    student_a = parent_setup["student_a"]

    duplicate = ParentStudent(
        parent_user_id=parent.id,
        student_id=student_a.id,
    )

    db.add(duplicate)

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()


def test_parent_relationship_does_not_depend_on_guardian_email(db, parent_setup):
    parent = parent_setup["parent"]
    student_a = parent_setup["student_a"]

    # Authorization comes from ParentStudent, not matching profile text.
    student_a.guardian_email = "someone-else@example.com"
    db.commit()

    actor = current_actor(_request_for(parent), db)

    visible = StudentRepository(db).list_visible(actor)

    assert [student.id for student in visible] == [student_a.id]