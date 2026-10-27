"""Grade validation rules. AMG-008 / T2-014.

The rules on their own, then through GradeService so we know a bad score
never reaches the database, then through the grade entry page so the
teacher sees a readable message instead of an error page.
"""

from datetime import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from business_logic.siem.grade_service import GradeAccessError, GradeService
from business_logic.siem.grade_validation import (
    MAX_PERCENT,
    GradeValidationError,
    check_points,
    parse_points,
)
from database.database import Base
from database.grades import Assignment, Grade
from database.models import Role, User
from database.scheduling import Course, Enrollment, Section
from security.keys import generate_key

KEY = generate_key()


class Actor:
    def __init__(self, user_id, role):
        self.user_id = user_id
        self.role = role


# -- the rules on their own -------------------------------------------------

def test_parse_points_accepts_numbers():
    assert parse_points("92") == (92.0, None)
    assert parse_points(" 92.5 ") == (92.5, None)
    assert parse_points("0") == (0.0, None)


def test_parse_points_blank():
    assert parse_points("") == (None, "Enter the points earned.")
    assert parse_points("   ")[1] == "Enter the points earned."
    assert parse_points(None)[1] == "Enter the points earned."


@pytest.mark.parametrize("raw", ["A", "abc", "ninety", "9 2", "inf", "-inf", "nan"])
def test_parse_points_rejects_text_and_non_numbers(raw):
    points, problem = parse_points(raw)
    assert points is None
    assert problem == "Points must be a number, like 92 or 92.5."


def test_negative_is_refused():
    assert check_points(-1, 100) == "Points can't be negative."


def test_zero_and_full_marks_are_fine():
    assert check_points(0, 100) is None
    assert check_points(100, 100) is None


def test_extra_credit_up_to_the_limit_is_fine():
    assert MAX_PERCENT == 120
    assert check_points(110, 100) is None
    assert check_points(120, 100) is None
    assert check_points(24, 20) is None


def test_over_the_limit_is_caught():
    problem = check_points(950, 100)
    assert "950 is more than this assignment allows" in problem
    assert "out of 100" in problem
    assert "up to 120 (120%)" in problem
    assert check_points(120.5, 100) is not None
    assert check_points(25, 20) is not None


# -- through GradeService ------------------------------------------------------

@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as s:
        teacher_role, student_role = Role(name="Teacher"), Role(name="Student")
        s.add_all([teacher_role, student_role])
        s.flush()
        teacher = User(username="teacher1", password_hash="x", first_name="Ann",
                       last_name="Anderson", email="t1@school.edu", role_id=teacher_role.id)
        other = User(username="teacher2", password_hash="x", first_name="Bob",
                     last_name="Brown", email="t2@school.edu", role_id=teacher_role.id)
        student = User(username="student1", password_hash="x", first_name="Jane",
                       last_name="Smith", email="s1@school.edu", role_id=student_role.id)
        s.add_all([teacher, other, student])
        s.flush()
        course = Course(code="MATH101", name="Algebra I")
        s.add(course)
        s.flush()
        section = Section(course_id=course.id, teacher_id=teacher.id, room="A101",
                          day_of_week="Mon", start_time=time(9, 0), end_time=time(9, 50))
        s.add(section)
        s.flush()
        s.add(Assignment(section_id=section.id, title="Quiz 1", points_possible=100))
        s.add(Enrollment(section_id=section.id, student_id=student.id))
        s.commit()
        yield s
    keys_module._cached = None


def _ids(db):
    teacher = db.query(User).filter_by(username="teacher1").one()
    other = db.query(User).filter_by(username="teacher2").one()
    student = db.query(User).filter_by(username="student1").one()
    assignment = db.query(Assignment).one()
    return Actor(teacher.id, "Teacher"), Actor(other.id, "Teacher"), student.id, assignment.id


def test_valid_score_is_saved(db):
    teacher, _, student_id, assignment_id = _ids(db)
    grade = GradeService.record_grade(db, teacher, student_id, assignment_id, 92.5)
    assert grade.points_earned == 92.5


def test_extra_credit_is_saved(db):
    teacher, _, student_id, assignment_id = _ids(db)
    grade = GradeService.record_grade(db, teacher, student_id, assignment_id, 115)
    assert grade.points_earned == 115


def test_negative_score_saves_nothing(db):
    teacher, _, student_id, assignment_id = _ids(db)
    with pytest.raises(GradeValidationError, match="can't be negative"):
        GradeService.record_grade(db, teacher, student_id, assignment_id, -5)
    assert db.query(Grade).count() == 0


def test_typo_score_saves_nothing(db):
    teacher, _, student_id, assignment_id = _ids(db)
    with pytest.raises(GradeValidationError, match="more than this assignment allows"):
        GradeService.record_grade(db, teacher, student_id, assignment_id, 950)
    assert db.query(Grade).count() == 0


def test_bad_update_keeps_the_old_score(db):
    teacher, _, student_id, assignment_id = _ids(db)
    GradeService.record_grade(db, teacher, student_id, assignment_id, 88)
    with pytest.raises(GradeValidationError):
        GradeService.record_grade(db, teacher, student_id, assignment_id, 880)
    db.rollback()
    assert db.query(Grade).one().points_earned == 88


def test_access_check_still_comes_first(db):
    """A teacher who can't grade this class hears that, not a score message."""
    _, other, student_id, assignment_id = _ids(db)
    with pytest.raises(GradeAccessError):
        GradeService.record_grade(db, other, student_id, assignment_id, 950)


# -- through the grade entry page ---------------------------------------------

class DummyTeacher:
    role = "Teacher"
    user_id = 1


@pytest.fixture
def client():
    import api
    return TestClient(api.app)


@patch("presentation.grades_routes.GradeService.record_grade")
@patch("presentation.grades_routes.current_actor")
def test_page_shows_message_for_text(mock_actor, mock_record, client):
    mock_actor.return_value = DummyTeacher()
    r = client.post("/grades/entry", data={"student_id": 1, "assignment_id": 1,
                                           "points_earned": "abc"}, follow_redirects=False)
    assert r.status_code == 400
    assert "Points must be a number, like 92 or 92.5." in r.text
    assert "Nothing was saved." in r.text
    assert 'value="abc"' in r.text
    mock_record.assert_not_called()


@patch("presentation.grades_routes.GradeService.record_grade")
@patch("presentation.grades_routes.current_actor")
def test_page_shows_message_for_blank(mock_actor, mock_record, client):
    mock_actor.return_value = DummyTeacher()
    r = client.post("/grades/entry", data={"student_id": 1, "assignment_id": 1,
                                           "points_earned": ""}, follow_redirects=False)
    assert r.status_code == 400
    assert "Enter the points earned." in r.text
    mock_record.assert_not_called()


@patch("presentation.grades_routes.GradeService.record_grade")
@patch("presentation.grades_routes.current_actor")
def test_page_shows_rule_message_from_the_service(mock_actor, mock_record, client):
    mock_actor.return_value = DummyTeacher()
    mock_record.side_effect = GradeValidationError("Points can't be negative.")
    r = client.post("/grades/entry", data={"student_id": 1, "assignment_id": 1,
                                           "points_earned": "-5"}, follow_redirects=False)
    assert r.status_code == 400
    assert "be negative." in r.text  # the page escapes the apostrophe in "can't"


@patch("presentation.grades_routes.GradeService.record_grade")
@patch("presentation.grades_routes.current_actor")
def test_good_score_still_redirects(mock_actor, mock_record, client):
    mock_actor.return_value = DummyTeacher()
    r = client.post("/grades/entry", data={"student_id": 1, "assignment_id": 1,
                                           "points_earned": "95"}, follow_redirects=False)
    assert r.status_code == 303
    assert mock_record.call_args.args[4] == 95.0


class DummyStudent:
    role = "Student"
    user_id = 2


@patch("presentation.grades_routes.GradeService.record_grade")
@patch("presentation.grades_routes.current_actor")
def test_student_is_refused_before_the_score_is_checked(mock_actor, mock_record, client):
    """A student sending a bad score gets 403, not a validation message."""
    mock_actor.return_value = DummyStudent()
    r = client.post("/grades/entry", data={"student_id": 1, "assignment_id": 1,
                                           "points_earned": "abc"}, follow_redirects=False)
    assert r.status_code == 403
    assert "Points must be a number" not in r.text
    mock_record.assert_not_called()
