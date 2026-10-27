from datetime import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from business_logic.cns.messaging_service import (
    MessagingAccessError,
    MessagingService,
    MessagingValidationError,
)
from data_access.repositories.student_repository import Actor
from database.database import Base
from database.messages import Message
from database.models import Role, User
from database.parents import ParentStudent
from database.scheduling import Course, Enrollment, Section
from database.students import Student
from security.keys import generate_key


KEY = generate_key()


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")

    from security import keys as keys_module

    keys_module.active_keyring(refresh=True)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        roles = {
            name: Role(name=name)
            for name in ("Admin", "Teacher", "Student", "Parent")
        }

        db.add_all(roles.values())
        db.flush()

        teacher = User(
            username="teacher1",
            password_hash="x",
            first_name="Ann",
            last_name="Anderson",
            email="teacher1@school.edu",
            role_id=roles["Teacher"].id,
        )

        other_teacher = User(
            username="teacher2",
            password_hash="x",
            first_name="Bob",
            last_name="Brown",
            email="teacher2@school.edu",
            role_id=roles["Teacher"].id,
        )

        student_user = User(
            username="student1",
            password_hash="x",
            first_name="Jane",
            last_name="Smith",
            email="student1@school.edu",
            role_id=roles["Student"].id,
        )

        parent = User(
            username="parent1",
            password_hash="x",
            first_name="Pat",
            last_name="Smith",
            email="parent1@school.edu",
            role_id=roles["Parent"].id,
        )

        other_parent = User(
            username="parent2",
            password_hash="x",
            first_name="Other",
            last_name="Parent",
            email="parent2@school.edu",
            role_id=roles["Parent"].id,
        )

        admin = User(
            username="admin1",
            password_hash="x",
            first_name="System",
            last_name="Admin",
            email="admin1@school.edu",
            role_id=roles["Admin"].id,
        )

        db.add_all([
            teacher,
            other_teacher,
            student_user,
            parent,
            other_parent,
            admin,
        ])
        db.flush()

        student = Student(
            user_id=student_user.id,
            student_number="S-001",
            first_name="Jane",
            last_name="Smith",
            grade_level=5,
            date_of_birth="2015-01-01",
            home_address="1 Main St",
            guardian_name="Pat Smith",
            guardian_email="parent1@school.edu",
        )

        db.add(student)
        db.flush()

        db.add(
            ParentStudent(
                parent_user_id=parent.id,
                student_id=student.id,
            )
        )

        course = Course(
            code="MATH101",
            name="Math",
        )

        db.add(course)
        db.flush()

        section = Section(
            course_id=course.id,
            teacher_id=teacher.id,
            room="A101",
            day_of_week="Mon",
            start_time=time(9, 0),
            end_time=time(9, 50),
        )

        db.add(section)
        db.flush()

        db.add(
            Enrollment(
                section_id=section.id,
                student_id=student_user.id,
            )
        )

        db.commit()

        yield {
            "db": db,
            "teacher": teacher,
            "other_teacher": other_teacher,
            "student_user": student_user,
            "student": student,
            "parent": parent,
            "other_parent": other_parent,
            "admin": admin,
            "engine": engine,
        }

    keys_module._cached = None


def test_teacher_can_message_parent_of_assigned_student(db):
    session = db["db"]

    actor = Actor(
        user_id=db["teacher"].id,
        role="Teacher",
    )

    message = MessagingService.send_message(
        session,
        actor,
        db["parent"].id,
        db["student"].id,
        "Jane is doing well in class.",
    )

    assert message.sender_id == db["teacher"].id
    assert message.recipient_id == db["parent"].id
    assert message.student_id == db["student"].id


def test_message_body_is_encrypted_at_rest(db):
    session = db["db"]

    actor = Actor(
        user_id=db["teacher"].id,
        role="Teacher",
    )

    message = MessagingService.send_message(
        session,
        actor,
        db["parent"].id,
        db["student"].id,
        "Private progress update.",
    )

    raw = session.connection().exec_driver_sql(
        "SELECT body FROM messages WHERE id = ?",
        (message.id,),
    ).scalar_one()

    assert raw != "Private progress update."
    assert "Private progress update." not in raw


def test_teacher_cannot_message_unrelated_parent(db):
    actor = Actor(
        user_id=db["teacher"].id,
        role="Teacher",
    )

    with pytest.raises(MessagingAccessError):
        MessagingService.send_message(
            db["db"],
            actor,
            db["other_parent"].id,
            db["student"].id,
            "This should not send.",
        )


def test_unassigned_teacher_cannot_message_parent(db):
    actor = Actor(
        user_id=db["other_teacher"].id,
        role="Teacher",
    )

    with pytest.raises(MessagingAccessError):
        MessagingService.send_message(
            db["db"],
            actor,
            db["parent"].id,
            db["student"].id,
            "This should not send.",
        )


def test_parent_cannot_start_conversation(db):
    actor = Actor(
        user_id=db["parent"].id,
        role="Parent",
    )

    with pytest.raises(MessagingAccessError):
        MessagingService.send_message(
            db["db"],
            actor,
            db["teacher"].id,
            db["student"].id,
            "Hello?",
        )


def test_parent_can_reply_after_teacher_messages(db):
    session = db["db"]

    teacher_actor = Actor(
        user_id=db["teacher"].id,
        role="Teacher",
    )

    parent_actor = Actor(
        user_id=db["parent"].id,
        role="Parent",
    )

    MessagingService.send_message(
        session,
        teacher_actor,
        db["parent"].id,
        db["student"].id,
        "Jane is doing well.",
    )

    reply = MessagingService.send_message(
        session,
        parent_actor,
        db["teacher"].id,
        db["student"].id,
        "Thanks for the update.",
    )

    assert reply.sender_id == db["parent"].id
    assert reply.recipient_id == db["teacher"].id


def test_conversation_contains_both_directions(db):
    session = db["db"]

    teacher_actor = Actor(
        user_id=db["teacher"].id,
        role="Teacher",
    )

    parent_actor = Actor(
        user_id=db["parent"].id,
        role="Parent",
    )

    MessagingService.send_message(
        session,
        teacher_actor,
        db["parent"].id,
        db["student"].id,
        "First message.",
    )

    MessagingService.send_message(
        session,
        parent_actor,
        db["teacher"].id,
        db["student"].id,
        "Reply.",
    )

    messages = MessagingService.conversation(
        session,
        teacher_actor,
        db["parent"].id,
        db["student"].id,
    )

    assert [message.body for message in messages] == [
        "First message.",
        "Reply.",
    ]


def test_admin_and_student_cannot_use_parent_messaging(db):
    for user, role, recipient in (
        (db["admin"], "Admin", db["parent"]),
        (db["student_user"], "Student", db["parent"]),
    ):
        actor = Actor(user_id=user.id, role=role)

        with pytest.raises(MessagingAccessError):
            MessagingService.send_message(
                db["db"],
                actor,
                recipient.id,
                db["student"].id,
                "Nope.",
            )


def test_blank_message_is_rejected(db):
    actor = Actor(
        user_id=db["teacher"].id,
        role="Teacher",
    )

    with pytest.raises(MessagingValidationError):
        MessagingService.send_message(
            db["db"],
            actor,
            db["parent"].id,
            db["student"].id,
            "   ",
        )

    assert db["db"].query(Message).count() == 0