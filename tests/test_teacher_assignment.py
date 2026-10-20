"""Teacher assignment rules. AMG-007 / T1-023.

Only a Teacher can be assigned, and a teacher can't be booked into two
sections that meet at the same time.
"""

from datetime import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from business_logic.amg.teacher_assignment import (
    TeacherAssignmentError,
    assign_teacher,
    list_teachers,
    unassign_teacher,
)
from database.database import Base
from database.models import Role, User
from database.scheduling import Course, Section


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as s:
        teacher_role = Role(name="Teacher")
        student_role = Role(name="Student")
        s.add_all([teacher_role, student_role])
        s.flush()

        s.add_all([
            User(username="anderson", password_hash="x", first_name="Ann",
                 last_name="Anderson", email="ann@school.edu", role_id=teacher_role.id),
            User(username="brown", password_hash="x", first_name="Bob",
                 last_name="Brown", email="bob@school.edu", role_id=teacher_role.id),
            User(username="jsmith", password_hash="x", first_name="Jane",
                 last_name="Smith", email="jane@school.edu", role_id=student_role.id),
        ])
        math = Course(code="MATH101", name="Algebra I")
        eng = Course(code="ENG101", name="English I")
        s.add_all([math, eng])
        s.flush()

        s.add_all([
            # 9:00-9:50 Monday
            Section(course_id=math.id, room="A101", day_of_week="Mon",
                    start_time=time(9, 0), end_time=time(9, 50)),
            # 9:30-10:20 Monday, overlaps the first one
            Section(course_id=eng.id, room="B202", day_of_week="Mon",
                    start_time=time(9, 30), end_time=time(10, 20)),
            # 9:00-9:50 Tuesday, same time but a different day
            Section(course_id=eng.id, room="B202", day_of_week="Tue",
                    start_time=time(9, 0), end_time=time(9, 50)),
        ])
        s.commit()
        yield s


def _user(db, username):
    return db.query(User).filter(User.username == username).one()


def _section(db, code, day):
    return (
        db.query(Section).join(Course)
        .filter(Course.code == code, Section.day_of_week == day).one()
    )


def test_teacher_can_be_assigned(db):
    section = _section(db, "MATH101", "Mon")
    assign_teacher(db, section.id, _user(db, "anderson").id)
    assert db.get(Section, section.id).teacher.username == "anderson"


def test_student_cannot_be_assigned_as_teacher(db):
    section = _section(db, "MATH101", "Mon")
    with pytest.raises(TeacherAssignmentError, match="Teacher role"):
        assign_teacher(db, section.id, _user(db, "jsmith").id)
    assert db.get(Section, section.id).teacher_id is None


def test_teacher_cannot_teach_two_overlapping_sections(db):
    ann = _user(db, "anderson").id
    assign_teacher(db, _section(db, "MATH101", "Mon").id, ann)

    with pytest.raises(TeacherAssignmentError, match="overlaps"):
        assign_teacher(db, _section(db, "ENG101", "Mon").id, ann)
    assert _section(db, "ENG101", "Mon").teacher_id is None


def test_same_time_on_a_different_day_is_fine(db):
    ann = _user(db, "anderson").id
    assign_teacher(db, _section(db, "MATH101", "Mon").id, ann)
    assign_teacher(db, _section(db, "ENG101", "Tue").id, ann)
    assert _section(db, "ENG101", "Tue").teacher_id == ann


def test_different_teachers_can_teach_at_the_same_time(db):
    assign_teacher(db, _section(db, "MATH101", "Mon").id, _user(db, "anderson").id)
    assign_teacher(db, _section(db, "ENG101", "Mon").id, _user(db, "brown").id)
    assert _section(db, "ENG101", "Mon").teacher.username == "brown"


def test_reassigning_the_same_section_is_not_a_conflict(db):
    section = _section(db, "MATH101", "Mon")
    ann = _user(db, "anderson").id
    assign_teacher(db, section.id, ann)
    assign_teacher(db, section.id, ann)  # saving again shouldn't clash with itself
    assert db.get(Section, section.id).teacher_id == ann


def test_unassign_clears_the_teacher(db):
    section = _section(db, "MATH101", "Mon")
    assign_teacher(db, section.id, _user(db, "anderson").id)
    unassign_teacher(db, section.id)
    assert db.get(Section, section.id).teacher_id is None


def test_missing_section_or_teacher_raises_lookup_error(db):
    with pytest.raises(LookupError):
        assign_teacher(db, 9999, _user(db, "anderson").id)
    with pytest.raises(LookupError):
        assign_teacher(db, _section(db, "MATH101", "Mon").id, 9999)


def test_list_teachers_only_returns_teachers(db):
    names = [t.username for t in list_teachers(db)]
    assert names == ["anderson", "brown"]
