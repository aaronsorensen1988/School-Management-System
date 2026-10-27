"""Taking attendance for a whole class at once. SIEM-005 / T2-001. Shanna.

The attendance page shows a section's roster for one day. The teacher
picks a status for each student and saves the whole list.

Taking attendance again for the same day changes the rows that are already
there instead of adding new ones. Nick's table comment says the same thing:
a second pass should be an update, not a second row.

Same rules as Sean's T2-003 for who can save: only the teacher assigned to
the section, and only for students enrolled in it. Admins can look but not
change anything. The whole list is checked first and nothing is saved if
any of it is wrong, so a class never ends up half recorded.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from business_logic.siem.attendance_service import AttendanceAccessError
from business_logic.siem.attendance_validation import (
    check_date,
    check_note,
    check_status,
    meets_on,
)
from business_logic.uma.access_control import AccessControl
from database.attendance import Attendance
from database.models import User
from database.scheduling import Enrollment, Section


def can_take(actor, section: Section) -> bool:
    return AccessControl.can_record_attendance(actor.role, actor.user_id, section.teacher_id)


def can_view(actor, section: Section) -> bool:
    return actor.role == "Admin" or can_take(actor, section)


def sections_for(db: Session, actor):
    """Sections this user can open on the attendance page."""
    query = db.query(Section)
    if actor.role == "Teacher":
        query = query.filter(Section.teacher_id == actor.user_id)
    elif actor.role != "Admin":
        return []
    return query.all()


def roster(db: Session, section_id):
    """Students enrolled in the section, sorted by last name."""
    return (
        db.query(User)
        .join(Enrollment, Enrollment.student_id == User.id)
        .filter(Enrollment.section_id == section_id)
        .order_by(User.last_name, User.first_name)
        .all()
    )


def existing_for_day(db: Session, section_id, on_date):
    """{student_id: Attendance} for what's already recorded that day."""
    rows = (
        db.query(Attendance)
        .filter(Attendance.section_id == section_id, Attendance.on_date == on_date)
        .all()
    )
    return {row.student_id: row for row in rows}


def default_date(section: Section, today=None):
    """The most recent day the class met, counting today."""
    day = today or date.today()
    for _ in range(7):
        if meets_on(section, day):
            return day
        day -= timedelta(days=1)
    return today or date.today()


def save_roster(db: Session, actor, section: Section, on_date, entries, today=None):
    """Save one day of attendance for a section.

    entries is {student_id: (status, note)}.
    Returns (number saved, errors). errors is {"date": msg} and/or
    {student_id: msg}. Nothing is saved if there are any errors.
    Raises AttendanceAccessError if this user can't record for the section.
    """
    if not can_take(actor, section):
        raise AttendanceAccessError("Teacher may only record attendance for assigned sections")

    errors = {}
    date_problem = check_date(section, on_date, today)
    if date_problem:
        errors["date"] = date_problem

    students = {s.id: s for s in roster(db, section.id)}

    for student_id in entries:
        if student_id not in students:
            errors["roster"] = "Attendance can only be recorded for students enrolled in this class."

    for student_id, student in students.items():
        status, note = entries.get(student_id, (None, None))
        problem = check_status(status) or check_note(note)
        if problem:
            errors[student_id] = problem

    if errors:
        return 0, errors

    existing = existing_for_day(db, section.id, on_date)
    now = datetime.now(timezone.utc)
    for student_id in students:
        status, note = entries[student_id]
        note = (note or "").strip() or None
        row = existing.get(student_id)
        if row is None:
            db.add(Attendance(
                section_id=section.id,
                student_id=student_id,
                on_date=on_date,
                status=status,
                note=note,
                recorded_by=actor.user_id,
            ))
        else:
            row.status = status
            row.note = note
            row.recorded_by = actor.user_id
            row.recorded_at = now
    db.commit()
    return len(students), {}
