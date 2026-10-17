"""Tests for the scheduling tables. AMG-007 / T1-022.

Covers what the tables themselves guarantee. The rules that live in code
(teacher assignment, the capacity check) are T1-023 and T1-024.
"""

from datetime import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.database import Base
from database.models import Role, User
from database.scheduling import (
    DEFAULT_CAPACITY,
    Course,
    Enrollment,
    Section,
    sections_overlap,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as s:
        teacher_role = Role(name="Teacher")
        student_role = Role(name="Student")
        s.add_all([teacher_role, student_role])
        s.flush()

        teacher = User(username="mrsanderson", password_hash="x", first_name="Ann",
                       last_name="Anderson", email="ann@school.edu", role_id=teacher_role.id)
        student = User(username="jsmith", password_hash="x", first_name="Jane",
                       last_name="Smith", email="jane@school.edu", role_id=student_role.id)
        course = Course(code="MATH101", name="Algebra I")
        s.add_all([teacher, student, course])
        s.flush()

        section = Section(course_id=course.id, teacher_id=teacher.id, room="A101",
                          day_of_week="Mon", start_time=time(9, 0), end_time=time(9, 50))
        s.add(section)
        s.commit()
        yield s


def test_capacity_defaults_to_20(db):
    assert db.query(Section).one().capacity == DEFAULT_CAPACITY == 20


def test_course_links_to_its_sections(db):
    course = db.query(Course).one()
    assert len(course.sections) == 1
    assert course.sections[0].room == "A101"


def test_teacher_is_optional_until_assigned(db):
    # T1-023 fills this in later, so a section has to be creatable without it
    course = db.query(Course).one()
    db.add(Section(course_id=course.id, room="B202", day_of_week="Tue",
                   start_time=time(10, 0), end_time=time(10, 50)))
    db.commit()
    assert db.query(Section).filter(Section.teacher_id.is_(None)).count() == 1


def test_student_cant_enroll_twice_in_the_same_section(db):
    section = db.query(Section).one()
    student = db.query(User).filter(User.username == "jsmith").one()
    db.add(Enrollment(section_id=section.id, student_id=student.id))
    db.commit()

    db.add(Enrollment(section_id=section.id, student_id=student.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_same_room_cant_be_double_booked(db):
    course = db.query(Course).one()
    db.add(Section(course_id=course.id, room="A101", day_of_week="Mon",
                   start_time=time(9, 0), end_time=time(9, 50)))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_end_time_has_to_be_after_start(db):
    course = db.query(Course).one()
    db.add(Section(course_id=course.id, room="C303", day_of_week="Wed",
                   start_time=time(11, 0), end_time=time(10, 0)))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_seat_counts(db):
    section = db.query(Section).one()
    student = db.query(User).filter(User.username == "jsmith").one()
    assert section.seats_left == 20
    assert not section.is_full()

    db.add(Enrollment(section_id=section.id, student_id=student.id))
    db.commit()
    db.refresh(section)
    assert section.seats_taken == 1
    assert section.seats_left == 19


# --- overlap helper, T1-023 uses this ---

def _sec(day, start, end):
    return Section(room="X", day_of_week=day, start_time=start, end_time=end)


@pytest.mark.parametrize("a_start,a_end,b_start,b_end,expected", [
    ((9, 0), (9, 50), (9, 30), (10, 20), True),   # b starts during a
    ((9, 0), (9, 50), (8, 30), (9, 15), True),    # b ends during a
    ((9, 0), (9, 50), (9, 10), (9, 20), True),    # b inside a
    ((9, 0), (9, 50), (9, 50), (10, 40), False),  # back to back, fine
    ((9, 0), (9, 50), (10, 0), (10, 50), False),  # no overlap
])
def test_overlap(a_start, a_end, b_start, b_end, expected):
    a = _sec("Mon", time(*a_start), time(*a_end))
    b = _sec("Mon", time(*b_start), time(*b_end))
    assert sections_overlap(a, b) is expected


def test_different_days_never_overlap():
    a = _sec("Mon", time(9, 0), time(9, 50))
    b = _sec("Tue", time(9, 0), time(9, 50))
    assert sections_overlap(a, b) is False
