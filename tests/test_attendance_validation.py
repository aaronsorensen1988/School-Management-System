"""Attendance validation and saving a whole roster. SIEM-005 / T2-004, T2-001.

The business rules on their own, without the web page. Dates are fixed and
"today" is passed in, so these don't depend on what day the tests run.
"""

from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from business_logic.siem import attendance_entry
from business_logic.siem.attendance_service import AttendanceAccessError
from business_logic.siem.attendance_validation import (
    NOTE_MAX,
    check_date,
    check_new_record,
    check_note,
    check_status,
    parse_date,
)
from data_access.repositories.student_repository import Actor
from database.attendance import Attendance
from database.database import Base
from database.models import Role, User
from database.scheduling import Course, Enrollment, Section
from security.keys import generate_key

KEY = generate_key()

TODAY = date(2026, 10, 21)        # a Wednesday
LAST_MONDAY = date(2026, 10, 19)
NEXT_MONDAY = date(2026, 10, 26)
A_TUESDAY = date(2026, 10, 20)


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    with Session(engine) as s:
        admin_role, teacher_role, student_role = Role(name="Admin"), Role(name="Teacher"), Role(name="Student")
        s.add_all([admin_role, teacher_role, student_role])
        s.flush()

        def user(username, first, last, role):
            return User(username=username, password_hash="x", first_name=first, last_name=last,
                        email=f"{username}@school.edu", role_id=role.id)

        s.add_all([
            user("admin", "System", "Admin", admin_role),
            user("anderson", "Ann", "Anderson", teacher_role),
            user("brown", "Bob", "Brown", teacher_role),
            user("jane", "Jane", "Smith", student_role),
            user("john", "John", "Jones", student_role),
            user("kim", "Kim", "Lee", student_role),   # not enrolled
        ])
        s.flush()
        ann = s.query(User).filter_by(username="anderson").one()

        math = Course(code="MATH101", name="Algebra I")
        s.add(math)
        s.flush()
        section = Section(course_id=math.id, teacher_id=ann.id, room="A101", day_of_week="Mon",
                          start_time=time(9, 0), end_time=time(9, 50))
        s.add(section)
        s.flush()
        for name in ("jane", "john"):
            s.add(Enrollment(section_id=section.id, student_id=s.query(User).filter_by(username=name).one().id))
        s.commit()
        yield s

    keys_module._cached = None


def _id(db, username):
    return db.query(User).filter_by(username=username).one().id


def _actor(db, username, role):
    return Actor(user_id=_id(db, username), role=role)


def _section(db):
    return db.query(Section).one()


def _all_present(db):
    return {_id(db, "jane"): ("present", ""), _id(db, "john"): ("present", "")}


# -- single rules (T2-004) --------------------------------------------------

def test_parse_date():
    assert parse_date("2026-10-19") == (LAST_MONDAY, None)
    assert parse_date("")[1] == "Choose a date."
    assert parse_date("10/19/2026")[1] == "Enter the date as YYYY-MM-DD."


def test_future_date_is_blocked(db):
    assert check_date(_section(db), NEXT_MONDAY, today=TODAY) == "Attendance can't be taken for a future date."


def test_date_must_be_a_day_the_class_meets(db):
    problem = check_date(_section(db), A_TUESDAY, today=TODAY)
    assert "MATH101 meets on Mon" in problem


def test_past_class_day_is_fine(db):
    assert check_date(_section(db), LAST_MONDAY, today=TODAY) is None


def test_today_is_fine_when_the_class_meets_today(db):
    assert check_date(_section(db), LAST_MONDAY, today=LAST_MONDAY) is None


def test_only_allowed_statuses():
    for ok in ("present", "absent", "tardy", "excused"):
        assert check_status(ok) is None
    assert check_status("sick") == "Choose present, absent, tardy, or excused."
    assert check_status("") is not None


def test_note_length():
    assert check_note("x" * NOTE_MAX) is None
    assert check_note("x" * (NOTE_MAX + 1)) is not None


def test_duplicate_gets_a_friendly_message(db):
    section = _section(db)
    jane = _id(db, "jane")
    assert check_new_record(db, section, jane, LAST_MONDAY, "present", today=TODAY) == []

    db.add(Attendance(section_id=section.id, student_id=jane, on_date=LAST_MONDAY, status="present"))
    db.commit()

    errors = check_new_record(db, section, jane, LAST_MONDAY, "absent", today=TODAY)
    assert len(errors) == 1
    assert "already recorded" in errors[0]


# -- saving a whole roster (T2-001) -------------------------------------------

def test_default_date_is_most_recent_class_day(db):
    assert attendance_entry.default_date(_section(db), today=TODAY) == LAST_MONDAY
    assert attendance_entry.default_date(_section(db), today=LAST_MONDAY) == LAST_MONDAY


def test_roster_is_enrolled_students_only(db):
    names = [u.username for u in attendance_entry.roster(db, _section(db).id)]
    assert names == ["john", "jane"]  # sorted by last name: Jones, Smith


def test_teacher_saves_the_roster(db):
    saved, errors = attendance_entry.save_roster(
        db, _actor(db, "anderson", "Teacher"), _section(db), LAST_MONDAY, _all_present(db), today=TODAY)
    assert errors == {}
    assert saved == 2
    rows = db.query(Attendance).all()
    assert len(rows) == 2
    assert all(r.recorded_by == _id(db, "anderson") for r in rows)


def test_saving_again_updates_instead_of_adding_rows(db):
    teacher, section = _actor(db, "anderson", "Teacher"), _section(db)
    attendance_entry.save_roster(db, teacher, section, LAST_MONDAY, _all_present(db), today=TODAY)

    entries = _all_present(db)
    entries[_id(db, "jane")] = ("tardy", "Bus was late")
    attendance_entry.save_roster(db, teacher, section, LAST_MONDAY, entries, today=TODAY)

    rows = db.query(Attendance).all()
    assert len(rows) == 2
    jane_row = next(r for r in rows if r.student_id == _id(db, "jane"))
    assert jane_row.status == "tardy"
    assert jane_row.note == "Bus was late"


def test_blank_note_is_stored_as_none(db):
    attendance_entry.save_roster(db, _actor(db, "anderson", "Teacher"), _section(db),
                                 LAST_MONDAY, _all_present(db), today=TODAY)
    assert all(r.note is None for r in db.query(Attendance).all())


def test_other_teacher_cannot_save(db):
    with pytest.raises(AttendanceAccessError):
        attendance_entry.save_roster(db, _actor(db, "brown", "Teacher"), _section(db),
                                     LAST_MONDAY, _all_present(db), today=TODAY)
    assert db.query(Attendance).count() == 0


def test_admin_can_view_but_not_save(db):
    admin, section = _actor(db, "admin", "Admin"), _section(db)
    assert attendance_entry.can_view(admin, section)
    with pytest.raises(AttendanceAccessError):
        attendance_entry.save_roster(db, admin, section, LAST_MONDAY, _all_present(db), today=TODAY)


def test_future_date_saves_nothing(db):
    saved, errors = attendance_entry.save_roster(
        db, _actor(db, "anderson", "Teacher"), _section(db), NEXT_MONDAY, _all_present(db), today=TODAY)
    assert saved == 0
    assert errors["date"] == "Attendance can't be taken for a future date."
    assert db.query(Attendance).count() == 0


def test_one_bad_status_saves_nothing(db):
    entries = _all_present(db)
    entries[_id(db, "john")] = ("sick", "")
    saved, errors = attendance_entry.save_roster(
        db, _actor(db, "anderson", "Teacher"), _section(db), LAST_MONDAY, entries, today=TODAY)
    assert saved == 0
    assert _id(db, "john") in errors
    assert db.query(Attendance).count() == 0


def test_every_student_needs_a_status(db):
    entries = {_id(db, "jane"): ("present", "")}  # john left out
    _, errors = attendance_entry.save_roster(
        db, _actor(db, "anderson", "Teacher"), _section(db), LAST_MONDAY, entries, today=TODAY)
    assert _id(db, "john") in errors


def test_student_not_in_the_class_is_rejected(db):
    entries = _all_present(db)
    entries[_id(db, "kim")] = ("present", "")
    _, errors = attendance_entry.save_roster(
        db, _actor(db, "anderson", "Teacher"), _section(db), LAST_MONDAY, entries, today=TODAY)
    assert "roster" in errors
    assert db.query(Attendance).count() == 0
