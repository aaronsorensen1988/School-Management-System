"""Attendance validation rules. SIEM-005 / T2-004. Shanna.

These run before anything is saved, so the teacher gets a clear message
instead of a database error.

Nick's table (T2-002) already blocks a bad status and a second row for the
same student, section and day. The checks here catch those same problems
earlier with a readable message, plus the ones the database can't know
about:
  - no attendance for a future date
  - no attendance on a day the class doesn't meet
  - notes have a length limit

Who is allowed to record attendance, and whether the student is enrolled,
is Sean's T2-003 (attendance_service.py / AccessControl), not this file.
"""

from datetime import date, datetime

from sqlalchemy.orm import Session

from database.attendance import STATUSES, Attendance
from database.scheduling import DAYS, Section

NOTE_MAX = 200

STATUS_LIST = ", ".join(STATUSES[:-1]) + f", or {STATUSES[-1]}"


def parse_date(raw):
    """'2026-10-26' -> date. Returns (date, None) or (None, error message)."""
    raw = str(raw or "").strip()
    if not raw:
        return None, "Choose a date."
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "Enter the date as YYYY-MM-DD."


def meets_on(section: Section, on_date: date) -> bool:
    """True if the section's day of the week matches the date."""
    weekday = on_date.weekday()  # Mon = 0
    return weekday < len(DAYS) and DAYS[weekday] == section.day_of_week


def check_date(section: Section, on_date, today=None):
    """Error message for the date, or None if it's fine."""
    today = today or date.today()
    if on_date is None:
        return "Choose a date."
    if on_date > today:
        return "Attendance can't be taken for a future date."
    if not meets_on(section, on_date):
        code = section.course.code if section.course else "This class"
        return (
            f"{code} meets on {section.day_of_week}, and "
            f"{on_date.strftime('%b %d, %Y')} is a {on_date.strftime('%a')}."
        )
    return None


def check_status(status):
    """Error message for the status, or None if it's one of the allowed ones."""
    if status not in STATUSES:
        return f"Choose {STATUS_LIST}."
    return None


def check_note(note):
    if note and len(note) > NOTE_MAX:
        return f"Notes can be at most {NOTE_MAX} characters."
    return None


def find_existing(db: Session, section_id, student_id, on_date):
    return (
        db.query(Attendance)
        .filter(
            Attendance.section_id == section_id,
            Attendance.student_id == student_id,
            Attendance.on_date == on_date,
        )
        .first()
    )


def check_new_record(db: Session, section: Section, student_id, on_date, status, note=None, today=None):
    """All the T2-004 checks for adding one new attendance row.

    Returns a list of error messages. Empty list means it's OK to save.
    """
    errors = []
    for problem in (check_date(section, on_date, today), check_status(status), check_note(note)):
        if problem:
            errors.append(problem)

    if on_date is not None and find_existing(db, section.id, student_id, on_date):
        errors.append(
            f"Attendance for this student on {on_date.strftime('%b %d, %Y')} is already "
            "recorded. Change the existing entry instead of adding a second one."
        )
    return errors
