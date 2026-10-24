from datetime import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from business_logic.siem.grade_service import (
    GradeAccessError,
    GradeEntryError,
    GradeService,
)
from database.database import Base
from database.grades import Assignment, Grade
from database.models import Role, User
from database.scheduling import Course, Enrollment, Section


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
def grade_setup(db):
    teacher_role = Role(name="Teacher")
    student_role = Role(name="Student")
    admin_role = Role(name="Admin")
    parent_role = Role(name="Parent")

    db.add_all([
        teacher_role,
        student_role,
        admin_role,
        parent_role,
    ])
    db.flush()

    teacher = User(
        username="teacher1",
        password_hash="x",
        first_name="Assigned",
        last_name="Teacher",
        email="teacher1@school.edu",
        role_id=teacher_role.id,
    )

    other_teacher = User(
        username="teacher2",
        password_hash="x",
        first_name="Other",
        last_name="Teacher",
        email="teacher2@school.edu",
        role_id=teacher_role.id,
    )

    student = User(
        username="student1",
        password_hash="x",
        first_name="Enrolled",
        last_name="Student",
        email="student1@school.edu",
        role_id=student_role.id,
    )

    other_student = User(
        username="student2",
        password_hash="x",
        first_name="Other",
        last_name="Student",
        email="student2@school.edu",
        role_id=student_role.id,
    )

    admin = User(
        username="admin1",
        password_hash="x",
        first_name="System",
        last_name="Admin",
        email="admin1@school.edu",
        role_id=admin_role.id,
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
        teacher,
        other_teacher,
        student,
        other_student,
        admin,
        parent,
    ])
    db.flush()

    course = Course(
        code="MATH101",
        name="Algebra I",
    )
    db.add(course)
    db.flush()

    section = Section(
        course_id=course.id,
        teacher_id=teacher.id,
        room="101",
        day_of_week="Mon",
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    db.add(section)
    db.flush()

    assignment = Assignment(
        section_id=section.id,
        title="Quiz 1",
        points_possible=100,
    )
    db.add(assignment)

    enrollment = Enrollment(
        section_id=section.id,
        student_id=student.id,
    )
    db.add(enrollment)

    db.commit()

    return {
        "teacher": teacher,
        "other_teacher": other_teacher,
        "student": student,
        "other_student": other_student,
        "admin": admin,
        "parent": parent,
        "section": section,
        "assignment": assignment,
    }


def test_assigned_teacher_can_record_grade(db, grade_setup):
    teacher = grade_setup["teacher"]
    student = grade_setup["student"]
    assignment = grade_setup["assignment"]

    actor = Actor(teacher.id, "Teacher")

    grade = GradeService.record_grade(
        db,
        actor,
        student.id,
        assignment.id,
        92.5,
    )

    assert grade.points_earned == 92.5
    assert grade.recorded_by == teacher.id


def test_other_teacher_cannot_record_grade(db, grade_setup):
    other_teacher = grade_setup["other_teacher"]
    student = grade_setup["student"]
    assignment = grade_setup["assignment"]

    actor = Actor(other_teacher.id, "Teacher")

    with pytest.raises(GradeAccessError):
        GradeService.record_grade(
            db,
            actor,
            student.id,
            assignment.id,
            92.5,
        )

    assert db.query(Grade).count() == 0


def test_admin_cannot_record_grade(db, grade_setup):
    admin = grade_setup["admin"]
    student = grade_setup["student"]
    assignment = grade_setup["assignment"]

    actor = Actor(admin.id, "Admin")

    with pytest.raises(GradeAccessError):
        GradeService.record_grade(
            db,
            actor,
            student.id,
            assignment.id,
            92.5,
        )

    assert db.query(Grade).count() == 0


def test_student_cannot_record_grade(db, grade_setup):
    student = grade_setup["student"]
    assignment = grade_setup["assignment"]

    actor = Actor(student.id, "Student")

    with pytest.raises(GradeAccessError):
        GradeService.record_grade(
            db,
            actor,
            student.id,
            assignment.id,
            100,
        )

    assert db.query(Grade).count() == 0


def test_parent_cannot_record_grade(db, grade_setup):
    parent = grade_setup["parent"]
    student = grade_setup["student"]
    assignment = grade_setup["assignment"]

    actor = Actor(parent.id, "Parent")

    with pytest.raises(GradeAccessError):
        GradeService.record_grade(
            db,
            actor,
            student.id,
            assignment.id,
            100,
        )

    assert db.query(Grade).count() == 0


def test_teacher_cannot_grade_student_not_in_section(db, grade_setup):
    teacher = grade_setup["teacher"]
    other_student = grade_setup["other_student"]
    assignment = grade_setup["assignment"]

    actor = Actor(teacher.id, "Teacher")

    with pytest.raises(GradeAccessError):
        GradeService.record_grade(
            db,
            actor,
            other_student.id,
            assignment.id,
            88,
        )

    assert db.query(Grade).count() == 0


def test_existing_grade_is_updated_not_duplicated(db, grade_setup):
    teacher = grade_setup["teacher"]
    student = grade_setup["student"]
    assignment = grade_setup["assignment"]

    actor = Actor(teacher.id, "Teacher")

    GradeService.record_grade(
        db,
        actor,
        student.id,
        assignment.id,
        80,
    )

    GradeService.record_grade(
        db,
        actor,
        student.id,
        assignment.id,
        95,
    )

    grades = (
        db.query(Grade)
        .filter(
            Grade.student_id == student.id,
            Grade.assignment_id == assignment.id,
        )
        .all()
    )

    assert len(grades) == 1
    assert grades[0].points_earned == 95
    assert grades[0].recorded_by == teacher.id


def test_missing_assignment_is_rejected(db, grade_setup):
    teacher = grade_setup["teacher"]
    student = grade_setup["student"]

    actor = Actor(teacher.id, "Teacher")

    with pytest.raises(GradeEntryError):
        GradeService.record_grade(
            db,
            actor,
            student.id,
            9999,
            90,
        )

    assert db.query(Grade).count() == 0