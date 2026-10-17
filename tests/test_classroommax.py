"""Tests for T1-024 classroom capacity limit.

Verifies:
1. Seats count decreases as students enroll.
2. The section reports full at 20 students.
3. The scheduling service rejects the 21st enrollment attempt.
"""
from datetime import time
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.database import Base
from database.models import Role, User
from database.scheduling import DEFAULT_CAPACITY, Course, Section
from business_logic.amg.scheduling_service import scheduling_service, CapacityLimitError

@pytest.fixture
def db():
    """Creates an in-memory SQLite DB for isolated testing."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as s:
        # Create roles
        teacher_role = Role(name="Teacher")
        student_role = Role(name="Student")
        s.add_all([teacher_role, student_role])
        s.flush()

        # Create teacher & course
        teacher = User(
            username="mrsanderson",
            password_hash="x",
            first_name="Ann",
            last_name="Anderson",
            email="ann@school.edu",
            role_id=teacher_role.id
        )
        course = Course(code="MATH101", name="Algebra I")
        s.add_all([teacher, course])
        s.flush()

        # Create Section with default capacity of 20
        section = Section(
            course_id=course.id,
            teacher_id=teacher.id,
            room="A101",
            day_of_week="Mon",
            start_time=time(9, 0),
            end_time=time(9, 50),
            capacity=DEFAULT_CAPACITY
        )
        s.add(section)
        s.commit()
        yield s

def test_classroom_capacity_limit(db):
    """Enroll 20 students successfully, then verify the 21st is rejected."""
    section = db.query(Section).one()
    student_role = db.query(Role).filter(Role.name == "Student").one()

    # 1. Enroll 20 students through the service
    for i in range(20):
        student = User(
            username=f"student{i}",
            password_hash="x",
            first_name="Test",
            last_name=f"User{i}",
            email=f"student{i}@school.edu",
            role_id=student_role.id
        )
        db.add(student)
        db.commit()
        db.refresh(student)

        scheduling_service.enroll_student(db, section.id, student.id)

    db.refresh(section)

    # 2. Section must be full
    assert section.is_full()
    assert section.seats_taken == 20
    assert section.seats_left == 0

    # 3. Create the 21st student
    extra_student = User(
        username="student_extra",
        password_hash="x",
        first_name="Extra",
        last_name="Student",
        email="extra@student.edu",
        role_id=student_role.id
    )
    db.add(extra_student)
    db.commit()
    db.refresh(extra_student)

    # 4. Attempting to enroll the 21st student must raise CapacityLimitError
    with pytest.raises(CapacityLimitError, match="Classroom capacity limit reached"):
        scheduling_service.enroll_student(db, section.id, extra_student.id)

    # Verify seat count remains locked at 20
    db.refresh(section)
    assert section.seats_taken == 20