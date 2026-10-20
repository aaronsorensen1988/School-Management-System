"""Tests for the attendance table. SIEM-005 / T2-002.

Covers what the table itself guarantees. Who's allowed to write to it is
T2-003 and the validation rules are T2-004.
"""

from datetime import date, time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.attendance import ABSENT, EXCUSED, PRESENT, TARDY, Attendance
from database.database import Base
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
        course = Course(code="MATH101", name="Algebra I")
        s.add_all([teacher, jane, course])
        s.flush()

        first = Section(course_id=course.id, teacher_id=teacher.id, room="A101",
                        day_of_week="Mon", start_time=time(9, 0), end_time=time(9, 50))
        second = Section(course_id=course.id, teacher_id=teacher.id, room="A102",
                         day_of_week="Mon", start_time=time(10, 0), end_time=time(10, 50))
        s.add_all([first, second])
        s.commit()
        yield s
    keys_module._cached = None


def _ids(db):
    teacher = db.query(User).filter(User.username == "mrsanderson").one()
    jane = db.query(User).filter(User.username == "jsmith").one()
    sections = db.query(Section).order_by(Section.room).all()
    return teacher, jane, sections


MONDAY = date(2026, 10, 26)


# -- the basics ----------------------------------------------------------

def test_a_day_can_be_recorded(db):
    teacher, jane, sections = _ids(db)
    db.add(Attendance(section_id=sections[0].id, student_id=jane.id,
                      on_date=MONDAY, status=ABSENT, recorded_by=teacher.id))
    db.commit()

    row = db.query(Attendance).one()
    assert row.status == ABSENT
    assert row.recorded_at is not None


def test_status_defaults_to_present(db):
    _, jane, sections = _ids(db)
    db.add(Attendance(section_id=sections[0].id, student_id=jane.id, on_date=MONDAY))
    db.commit()
    assert db.query(Attendance).one().status == PRESENT


@pytest.mark.parametrize("status,missed", [
    (PRESENT, False), (ABSENT, True), (TARDY, True), (EXCUSED, True),
])
def test_is_missed_covers_everything_but_present(db, status, missed):
    _, jane, sections = _ids(db)
    row = Attendance(section_id=sections[0].id, student_id=jane.id,
                     on_date=MONDAY, status=status)
    assert row.is_missed() is missed


# -- what the table refuses ----------------------------------------------

def test_the_same_period_cannot_be_taken_twice(db):
    """Correcting a mark is an update. A second row double counts."""
    _, jane, sections = _ids(db)
    db.add(Attendance(section_id=sections[0].id, student_id=jane.id,
                      on_date=MONDAY, status=PRESENT))
    db.commit()

    db.add(Attendance(section_id=sections[0].id, student_id=jane.id,
                      on_date=MONDAY, status=ABSENT))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_made_up_status_is_rejected(db):
    _, jane, sections = _ids(db)
    db.add(Attendance(section_id=sections[0].id, student_id=jane.id,
                      on_date=MONDAY, status="maybe"))
    with pytest.raises(IntegrityError):
        db.commit()


# -- what it has to allow ------------------------------------------------

def test_one_student_has_a_row_per_period(db):
    """Attendance is by period, so four classes is four rows for one day."""
    _, jane, sections = _ids(db)
    db.add_all([
        Attendance(section_id=sections[0].id, student_id=jane.id,
                   on_date=MONDAY, status=PRESENT),
        Attendance(section_id=sections[1].id, student_id=jane.id,
                   on_date=MONDAY, status=ABSENT),
    ])
    db.commit()
    assert db.query(Attendance).count() == 2


def test_the_same_class_on_a_different_day_is_a_new_row(db):
    _, jane, sections = _ids(db)
    db.add_all([
        Attendance(section_id=sections[0].id, student_id=jane.id, on_date=MONDAY),
        Attendance(section_id=sections[0].id, student_id=jane.id,
                   on_date=date(2026, 10, 27)),
    ])
    db.commit()
    assert db.query(Attendance).count() == 2


# -- the part that matters for FERPA -------------------------------------

def test_the_note_is_ciphertext_on_disk(db):
    """Reasons for an absence get typed in here."""
    teacher, jane, sections = _ids(db)
    db.add(Attendance(section_id=sections[0].id, student_id=jane.id,
                      on_date=MONDAY, status=EXCUSED, recorded_by=teacher.id,
                      note="left at 10, mom picking up for an appointment"))
    db.commit()

    stored = db.execute(text("SELECT note FROM attendance")).scalar_one()
    assert is_encrypted(stored)
    assert "appointment" not in stored


def test_the_note_reads_back_as_itself(db):
    _, jane, sections = _ids(db)
    db.add(Attendance(section_id=sections[0].id, student_id=jane.id,
                      on_date=MONDAY, status=EXCUSED, note="family emergency"))
    db.commit()
    db.expire_all()
    assert db.query(Attendance).one().note == "family emergency"


def test_status_stays_plain_so_it_can_be_counted(db):
    """The reason status isn't encrypted. If this fails, absence
    reporting stops working."""
    _, jane, sections = _ids(db)
    db.add_all([
        Attendance(section_id=sections[0].id, student_id=jane.id,
                   on_date=MONDAY, status=ABSENT),
        Attendance(section_id=sections[1].id, student_id=jane.id,
                   on_date=MONDAY, status=ABSENT),
    ])
    db.commit()

    counted = (
        db.query(Attendance)
        .filter(Attendance.student_id == jane.id, Attendance.status == ABSENT)
        .count()
    )
    assert counted == 2
