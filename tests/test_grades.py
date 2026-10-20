"""Tests for the gradebook tables. AMG-008 / T2-012.

What the tables guarantee. Who's allowed to enter a grade is T2-013 and the
validation rules are T2-014.
"""

from datetime import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.database import Base
from database.grades import Assignment, Grade
from database.models import Role, User
from database.scheduling import Course, Section
from security.crypto import is_encrypted
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
        teacher_role = Role(name="Teacher")
        student_role = Role(name="Student")
        s.add_all([teacher_role, student_role])
        s.flush()

        teacher = User(username="mrsanderson", password_hash="x", first_name="Ann",
                       last_name="Anderson", email="ann@school.edu", role_id=teacher_role.id)
        jane = User(username="jsmith", password_hash="x", first_name="Jane",
                    last_name="Smith", email="jane@school.edu", role_id=student_role.id)
        bob = User(username="bjones", password_hash="x", first_name="Bob",
                   last_name="Jones", email="bob@school.edu", role_id=student_role.id)
        course = Course(code="MATH101", name="Algebra I")
        s.add_all([teacher, jane, bob, course])
        s.flush()

        first = Section(course_id=course.id, teacher_id=teacher.id, room="A101",
                        day_of_week="Mon", start_time=time(9, 0), end_time=time(9, 50))
        second = Section(course_id=course.id, teacher_id=teacher.id, room="A102",
                         day_of_week="Mon", start_time=time(10, 0), end_time=time(10, 50))
        s.add_all([first, second])
        s.commit()
        yield s
    keys_module._cached = None


def _fixtures(db):
    teacher = db.query(User).filter(User.username == "mrsanderson").one()
    jane = db.query(User).filter(User.username == "jsmith").one()
    bob = db.query(User).filter(User.username == "bjones").one()
    sections = db.query(Section).order_by(Section.room).all()
    return teacher, jane, bob, sections


def _quiz(db, section, title="Quiz 1", points=20):
    a = Assignment(section_id=section.id, title=title,
                   category="homework", points_possible=points)
    db.add(a)
    db.commit()
    return a


# -- the basics ----------------------------------------------------------

def test_a_grade_can_be_entered(db):
    teacher, jane, _, sections = _fixtures(db)
    quiz = _quiz(db, sections[0])
    db.add(Grade(assignment_id=quiz.id, student_id=jane.id,
                 points_earned=17, recorded_by=teacher.id))
    db.commit()

    row = db.query(Grade).one()
    assert row.points_earned == 17
    assert row.recorded_at is not None


def test_percent_uses_the_assignment_total(db):
    _, jane, _, sections = _fixtures(db)
    quiz = _quiz(db, sections[0], points=20)
    db.add(Grade(assignment_id=quiz.id, student_id=jane.id, points_earned=15))
    db.commit()
    assert db.query(Grade).one().percent == 75.0


def test_percent_is_none_when_the_assignment_isnt_loaded(db):
    """A detached Grade shouldn't take a template down with it."""
    assert Grade(assignment_id=1, student_id=1, points_earned=10).percent is None


# -- what the tables refuse ----------------------------------------------

def test_a_student_gets_one_score_per_assignment(db):
    """Changing a mark is an update. A second row makes the average wrong."""
    _, jane, _, sections = _fixtures(db)
    quiz = _quiz(db, sections[0])
    db.add(Grade(assignment_id=quiz.id, student_id=jane.id, points_earned=17))
    db.commit()

    db.add(Grade(assignment_id=quiz.id, student_id=jane.id, points_earned=19))
    with pytest.raises(IntegrityError):
        db.commit()


def test_an_assignment_cannot_be_worth_zero(db):
    _, _, _, sections = _fixtures(db)
    db.add(Assignment(section_id=sections[0].id, title="Nothing", points_possible=0))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_negative_score_is_rejected(db):
    _, jane, _, sections = _fixtures(db)
    quiz = _quiz(db, sections[0])
    db.add(Grade(assignment_id=quiz.id, student_id=jane.id, points_earned=-5))
    with pytest.raises(IntegrityError):
        db.commit()


def test_two_assignments_in_one_section_cannot_share_a_title(db):
    _, _, _, sections = _fixtures(db)
    _quiz(db, sections[0], title="Quiz 1")
    db.add(Assignment(section_id=sections[0].id, title="Quiz 1", points_possible=10))
    with pytest.raises(IntegrityError):
        db.commit()


# -- what it has to allow ------------------------------------------------

def test_extra_credit_is_allowed(db):
    """Over 100 percent happens, so the table shouldn't block it."""
    _, jane, _, sections = _fixtures(db)
    quiz = _quiz(db, sections[0], points=20)
    db.add(Grade(assignment_id=quiz.id, student_id=jane.id, points_earned=22))
    db.commit()
    assert db.query(Grade).one().percent == 110.0


def test_different_sections_can_both_have_a_quiz_1(db):
    _, _, _, sections = _fixtures(db)
    _quiz(db, sections[0], title="Quiz 1")
    _quiz(db, sections[1], title="Quiz 1")
    assert db.query(Assignment).count() == 2


def test_one_assignment_holds_every_students_score(db):
    _, jane, bob, sections = _fixtures(db)
    quiz = _quiz(db, sections[0])
    db.add_all([
        Grade(assignment_id=quiz.id, student_id=jane.id, points_earned=17),
        Grade(assignment_id=quiz.id, student_id=bob.id, points_earned=12),
    ])
    db.commit()
    db.expire_all()
    assert len(db.query(Assignment).one().grades) == 2


# -- the encryption decision ---------------------------------------------

def test_the_comment_is_ciphertext_on_disk(db):
    """Free text about a student, so it should be unreadable on disk."""
    teacher, jane, _, sections = _fixtures(db)
    quiz = _quiz(db, sections[0])
    db.add(Grade(assignment_id=quiz.id, student_id=jane.id, points_earned=9,
                 recorded_by=teacher.id,
                 comment="struggling since the move, worth a call home"))
    db.commit()

    stored = db.execute(text("SELECT comment FROM grades")).scalar_one()
    assert is_encrypted(stored)
    assert "struggling" not in stored


def test_the_comment_reads_back_as_itself(db):
    _, jane, _, sections = _fixtures(db)
    quiz = _quiz(db, sections[0])
    db.add(Grade(assignment_id=quiz.id, student_id=jane.id,
                 points_earned=9, comment="see me after class"))
    db.commit()
    db.expire_all()
    assert db.query(Grade).one().comment == "see me after class"


def test_scores_stay_plain_so_the_database_can_add_them_up(db):
    """The reason points_earned isn't encrypted. If this ever fails,
    averages have to be done in Python instead."""
    from sqlalchemy import func

    _, jane, bob, sections = _fixtures(db)
    quiz = _quiz(db, sections[0], points=20)
    db.add_all([
        Grade(assignment_id=quiz.id, student_id=jane.id, points_earned=18),
        Grade(assignment_id=quiz.id, student_id=bob.id, points_earned=12),
    ])
    db.commit()

    average = db.query(func.avg(Grade.points_earned)).scalar()
    assert average == 15.0
