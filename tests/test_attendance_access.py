"""Tests for teacher-only attendance write access. SIEM-005 / T2-003."""

from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from business_logic.siem.attendance_service import (
    AttendanceAccessError,
    AttendanceService,
)
from data_access.repositories.student_repository import Actor
from database.attendance import PRESENT, Attendance
from database.database import Base
from database.models import Role, User
from database.scheduling import Course, Enrollment, Section
from security.keys import generate_key


KEY = generate_key()
MONDAY = date(2026, 10, 26)


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

    with Session(engine) as s:
        teacher_role = Role(name="Teacher")
        student_role = Role(name="Student")
        admin_role = Role(name="Admin")

        s.add_all([teacher_role, student_role, admin_role])
        s.flush()

        teacher = User(
            username="teacher1",
            password_hash="x",
            first_name="Ann",
            last_name="Anderson",
            email="teacher1@school.edu",
            role_id=teacher_role.id,
        )

        other_teacher = User(
            username="teacher2",
            password_hash="x",
            first_name="Bob",
            last_name="Brown",
            email="teacher2@school.edu",
            role_id=teacher_role.id,
        )

        student = User(
            username="student1",
            password_hash="x",
            first_name="Jane",
            last_name="Smith",
            email="student1@school.edu",
            role_id=student_role.id,
        )

        other_student = User(
            username="student2",
            password_hash="x",
            first_name="John",
            last_name="Jones",
            email="student2@school.edu",
            role_id=student_role.id,
        )

        admin = User(
            username="admin2",
            password_hash="x",
            first_name="Admin",
            last_name="User",
            email="admin2@school.edu",
            role_id=admin_role.id,
        )

        course = Course(code="MATH101", name="Algebra I")

        s.add_all([
            teacher,
            other_teacher,
            student,
            other_student,
            admin,
            course,
        ])
        s.flush()

        section = Section(
            course_id=course.id,
            teacher_id=teacher.id,
            room="A101",
            day_of_week="Mon",
            start_time=time(9, 0),
            end_time=time(9, 50),
        )

        s.add(section)
        s.flush()

        s.add(
            Enrollment(
                section_id=section.id,
                student_id=student.id,
            )
        )

        s.commit()
        yield s

    keys_module._cached = None


def _users(db):
    teacher = db.query(User).filter(User.username == "teacher1").one()
    other_teacher = db.query(User).filter(User.username == "teacher2").one()
    student = db.query(User).filter(User.username == "student1").one()
    other_student = db.query(User).filter(User.username == "student2").one()
    admin = db.query(User).filter(User.username == "admin2").one()
    section = db.query(Section).one()

    return teacher, other_teacher, student, other_student, admin, section


def test_assigned_teacher_can_record_attendance(db):
    teacher, _, student, _, _, section = _users(db)

    actor = Actor(user_id=teacher.id, role="Teacher")
    service = AttendanceService()

    row = service.record_attendance(
        db,
        actor,
        section.id,
        student.id,
        MONDAY,
        PRESENT,
    )

    assert row.recorded_by == teacher.id
    assert row.section_id == section.id
    assert row.student_id == student.id
    assert db.query(Attendance).count() == 1


def test_different_teacher_cannot_record_attendance(db):
    _, other_teacher, student, _, _, section = _users(db)

    actor = Actor(user_id=other_teacher.id, role="Teacher")
    service = AttendanceService()

    with pytest.raises(AttendanceAccessError):
        service.record_attendance(
            db,
            actor,
            section.id,
            student.id,
            MONDAY,
            PRESENT,
        )

    assert db.query(Attendance).count() == 0


def test_admin_cannot_record_attendance(db):
    _, _, student, _, admin, section = _users(db)

    actor = Actor(user_id=admin.id, role="Admin")
    service = AttendanceService()

    with pytest.raises(AttendanceAccessError):
        service.record_attendance(
            db,
            actor,
            section.id,
            student.id,
            MONDAY,
            PRESENT,
        )

    assert db.query(Attendance).count() == 0


def test_teacher_cannot_record_unenrolled_student(db):
    teacher, _, _, other_student, _, section = _users(db)

    actor = Actor(user_id=teacher.id, role="Teacher")
    service = AttendanceService()

    with pytest.raises(ValueError, match="not enrolled"):
        service.record_attendance(
            db,
            actor,
            section.id,
            other_student.id,
            MONDAY,
            PRESENT,
        )

    assert db.query(Attendance).count() == 0