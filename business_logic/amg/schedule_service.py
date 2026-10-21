"""Course and section setup for the scheduling page. AMG-007 / T1-021. Shanna.

Validation lives here, not just in the HTML form, so the rules still hold
no matter how a request reaches the server (same pattern as SIEM-004).
Each create function returns (object, errors) like StudentService does.
"""

import re
from datetime import datetime

from sqlalchemy.orm import Session

from database.scheduling import DAYS, DEFAULT_CAPACITY, Course, Enrollment, Section

COURSE_CODE_PATTERN = re.compile(r"^[A-Z0-9-]{2,12}$")
MAX_NAME_LENGTH = 100


def _parse_time(value):
    """'09:30' (what an HTML time input sends) -> time, or None if invalid."""
    try:
        return datetime.strptime(value, "%H:%M").time()
    except (TypeError, ValueError):
        return None


def create_course(db: Session, form):
    """Validate and save a course like MATH101 / Algebra I."""
    code = str(form.get("code") or "").strip().upper()
    name = str(form.get("name") or "").strip()
    description = str(form.get("description") or "").strip() or None
    errors = {}

    if not code:
        errors["code"] = "Course code is required."
    elif not COURSE_CODE_PATTERN.match(code):
        errors["code"] = "Course code can only use letters, numbers, and dashes (2-12 characters)."
    elif db.query(Course).filter(Course.code == code).first():
        errors["code"] = f"Course {code} already exists."

    if not name:
        errors["name"] = "Course name is required."
    elif len(name) > MAX_NAME_LENGTH:
        errors["name"] = f"Course name must be {MAX_NAME_LENGTH} characters or fewer."

    if errors:
        return None, errors

    course = Course(code=code, name=name, description=description)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course, {}


def find_room_conflict(db: Session, section: Section):
    """Another section in the same room at an overlapping time, or None.

    The database only blocks an identical room/day/start time, so a class
    starting 15 minutes into another one has to be caught here.
    """
    from database.scheduling import sections_overlap

    others = db.query(Section).filter(Section.room == section.room).all()
    for other in others:
        if other.id != section.id and sections_overlap(section, other):
            return other
    return None


def create_section(db: Session, form):
    """Validate and save a section (one class meeting time for a course)."""
    errors = {}

    course = None
    try:
        course_id = int(form.get("course_id") or "")
    except ValueError:
        errors["course_id"] = "Choose a course."
    else:
        course = db.query(Course).filter(Course.id == course_id).first()
        if course is None:
            errors["course_id"] = "Choose a course."

    room = str(form.get("room") or "").strip().upper()
    if not room:
        errors["room"] = "Room is required."
    elif len(room) > 20:
        errors["room"] = "Room must be 20 characters or fewer."

    day = str(form.get("day_of_week") or "").strip()
    if day not in DAYS:
        errors["day_of_week"] = "Choose a day (Mon-Fri)."

    start = _parse_time(form.get("start_time"))
    end = _parse_time(form.get("end_time"))
    if start is None:
        errors["start_time"] = "Start time is required."
    if end is None:
        errors["end_time"] = "End time is required."
    elif start is not None and end <= start:
        errors["end_time"] = "End time must be after the start time."

    try:
        capacity = int(form.get("capacity") or DEFAULT_CAPACITY)
    except ValueError:
        errors["capacity"] = "Capacity must be a number."
    else:
        if not 1 <= capacity <= DEFAULT_CAPACITY:
            errors["capacity"] = f"Capacity must be between 1 and {DEFAULT_CAPACITY}."

    if errors:
        return None, errors

    section = Section(
        course_id=course.id, room=room, day_of_week=day,
        start_time=start, end_time=end, capacity=capacity,
    )

    conflict = find_room_conflict(db, section)
    if conflict is not None:
        return None, {
            "room": (
                f"Room {room} is already booked for {conflict.course.code} on "
                f"{conflict.day_of_week} {conflict.start_time:%H:%M}-{conflict.end_time:%H:%M}."
            )
        }

    db.add(section)
    db.commit()
    db.refresh(section)
    return section, {}


def sections_for(db: Session, actor):
    """The sections this person should see on the Classes page.

    Admin: every section. Teacher: the sections they teach.
    Student: the sections they're enrolled in. Parent: none yet, since
    parent-child links are a Sprint 2 table (same as the student pages).
    """
    query = db.query(Section)
    if actor.role == "Admin":
        pass
    elif actor.role == "Teacher":
        query = query.filter(Section.teacher_id == actor.user_id)
    elif actor.role == "Student":
        query = query.join(Enrollment).filter(Enrollment.student_id == actor.user_id)
    else:
        return []

    day_order = {d: i for i, d in enumerate(DAYS)}
    sections = query.all()
    return sorted(sections, key=lambda s: (day_order.get(s.day_of_week, 99), s.start_time, s.room))


def section_row(section: Section):
    """Plain dict for the template, so nothing lazy-loads after the session closes."""
    teacher = section.teacher
    return {
        "id": section.id,
        "course_code": section.course.code,
        "course_name": section.course.name,
        "day": section.day_of_week,
        "time": f"{section.start_time:%I:%M %p} - {section.end_time:%I:%M %p}".replace(" 0", " ").lstrip("0"),
        "room": section.room,
        "teacher_id": section.teacher_id,
        "teacher_name": f"{teacher.first_name} {teacher.last_name}" if teacher else None,
        "seats_taken": section.seats_taken,
        "capacity": section.capacity,
    }
