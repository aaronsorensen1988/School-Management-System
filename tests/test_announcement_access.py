import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import database.scheduling  # noqa: F401

from business_logic.siem.announcement_service import (
    AnnouncementAccessError,
    AnnouncementNotFoundError,
    AnnouncementService,
)
from database.announcements import EVERYONE, PARENTS, Announcement
from database.database import Base
from database.models import Role, User


class Actor:
    def __init__(self, user_id, role):
        self.user_id = user_id
        self.role = role


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        yield db


@pytest.fixture
def announcement_setup(db):
    admin_role = Role(name="Admin")
    teacher_role = Role(name="Teacher")
    student_role = Role(name="Student")
    parent_role = Role(name="Parent")

    db.add_all([
        admin_role,
        teacher_role,
        student_role,
        parent_role,
    ])
    db.flush()

    admin = User(
        username="admin1",
        password_hash="x",
        first_name="System",
        last_name="Admin",
        email="admin1@school.edu",
        role_id=admin_role.id,
    )

    teacher = User(
        username="teacher1",
        password_hash="x",
        first_name="Test",
        last_name="Teacher",
        email="teacher1@school.edu",
        role_id=teacher_role.id,
    )

    student = User(
        username="student1",
        password_hash="x",
        first_name="Test",
        last_name="Student",
        email="student1@school.edu",
        role_id=student_role.id,
    )

    parent = User(
        username="parent1",
        password_hash="x",
        first_name="Test",
        last_name="Parent",
        email="parent1@school.edu",
        role_id=parent_role.id,
    )

    db.add_all([
        admin,
        teacher,
        student,
        parent,
    ])
    db.commit()

    return {
        "admin": admin,
        "teacher": teacher,
        "student": student,
        "parent": parent,
    }


def test_admin_can_create_announcement_draft(db, announcement_setup):
    admin = announcement_setup["admin"]
    actor = Actor(admin.id, "Admin")

    announcement = AnnouncementService.create_draft(
        db,
        actor,
        "Early dismissal",
        "School closes at 1 PM.",
        EVERYONE,
    )

    assert announcement.author_id == admin.id
    assert announcement.audience == EVERYONE
    assert announcement.is_published() is False


def test_teacher_can_create_announcement_draft(db, announcement_setup):
    teacher = announcement_setup["teacher"]
    actor = Actor(teacher.id, "Teacher")

    announcement = AnnouncementService.create_draft(
        db,
        actor,
        "Homework reminder",
        "Assignments are due Friday.",
        PARENTS,
    )

    assert announcement.author_id == teacher.id
    assert announcement.audience == PARENTS


def test_student_cannot_create_announcement(db, announcement_setup):
    student = announcement_setup["student"]
    actor = Actor(student.id, "Student")

    with pytest.raises(AnnouncementAccessError):
        AnnouncementService.create_draft(
            db,
            actor,
            "Fake announcement",
            "Students should not be able to post this.",
        )

    assert db.query(Announcement).count() == 0


def test_parent_cannot_create_announcement(db, announcement_setup):
    parent = announcement_setup["parent"]
    actor = Actor(parent.id, "Parent")

    with pytest.raises(AnnouncementAccessError):
        AnnouncementService.create_draft(
            db,
            actor,
            "Fake announcement",
            "Parents should not be able to post this.",
        )

    assert db.query(Announcement).count() == 0


def test_anonymous_cannot_create_announcement(db):
    actor = Actor(None, None)

    with pytest.raises(AnnouncementAccessError):
        AnnouncementService.create_draft(
            db,
            actor,
            "Fake announcement",
            "Anonymous users cannot post.",
        )

    assert db.query(Announcement).count() == 0


def test_teacher_can_publish_announcement(db, announcement_setup):
    teacher = announcement_setup["teacher"]
    actor = Actor(teacher.id, "Teacher")

    announcement = AnnouncementService.create_draft(
        db,
        actor,
        "Field trip",
        "Permission slips are due Monday.",
    )

    published = AnnouncementService.publish(
        db,
        actor,
        announcement.id,
    )

    assert published.is_published() is True


def test_student_cannot_publish_announcement(db, announcement_setup):
    admin = announcement_setup["admin"]
    student = announcement_setup["student"]

    admin_actor = Actor(admin.id, "Admin")
    student_actor = Actor(student.id, "Student")

    announcement = AnnouncementService.create_draft(
        db,
        admin_actor,
        "Snow day",
        "No school tomorrow.",
    )

    with pytest.raises(AnnouncementAccessError):
        AnnouncementService.publish(
            db,
            student_actor,
            announcement.id,
        )

    db.refresh(announcement)
    assert announcement.is_published() is False


def test_missing_announcement_is_rejected(db, announcement_setup):
    admin = announcement_setup["admin"]
    actor = Actor(admin.id, "Admin")

    with pytest.raises(AnnouncementNotFoundError):
        AnnouncementService.publish(
            db,
            actor,
            9999,
        )