"""Grade aggregation for report cards. AMG-009 / T2-019. Shanna.

Turns a student's individual grades into the numbers a report card shows:
a percent and a letter grade for each class, an overall average, and an
attendance summary. T2-016 (report card generator) builds on this.

How the math works, written down so nobody has to guess:

  - A class grade is total points earned / total points possible, across
    the assignments that have a grade. A 20 point quiz counts less than a
    100 point test, the same way a teacher's gradebook works.
  - Assignments with no grade yet are left out, not counted as zero. A
    report card run mid-term shouldn't fail a student for work that isn't
    due or isn't graded yet. "graded" vs "assignments" shows the gap.
  - Extra credit can push a class above 100%. T2-014 caps a single score
    at 120% of the assignment, so it can't run away.
  - Percents are rounded to one decimal, half up (89.95 -> 90.0), so the
    report card never shows 89.9999 and the letter matches the number shown.
  - The overall average is the plain average of the class percents, so
    every class counts the same no matter how many points it has.

Who is allowed to see a report card is T2-018 (parent view access), not
this file. This file only does the math.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from database.attendance import STATUSES, Attendance
from database.grades import Assignment, Grade
from database.scheduling import DAYS, Enrollment, Section

# Standard scale. A policy call, so it lives in one place.
LETTER_SCALE = (
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
)


def round_percent(value):
    """89.95 -> 90.0. None stays None."""
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def letter_for(percent):
    """Letter grade for a percent, or None if there's nothing graded yet."""
    if percent is None:
        return None
    for floor, letter in LETTER_SCALE:
        if percent >= floor:
            return letter
    return "F"


def class_grade(db: Session, section_id, student_id):
    """One student's grade in one class.

    Returns a dict:
      earned, possible  points totals across graded assignments
      percent           rounded to one decimal, or None if nothing graded
      letter            A-F, or None if nothing graded
      graded            how many assignments have a grade
      assignments       how many assignments the class has in total
    """
    assignments = db.query(Assignment).filter(Assignment.section_id == section_id).all()
    ids = [a.id for a in assignments]
    possible_by_id = {a.id: a.points_possible for a in assignments}

    grades = []
    if ids:
        grades = (
            db.query(Grade)
            .filter(Grade.student_id == student_id, Grade.assignment_id.in_(ids))
            .all()
        )

    earned = sum(g.points_earned for g in grades)
    possible = sum(possible_by_id[g.assignment_id] for g in grades)

    percent = round_percent(100.0 * earned / possible) if possible else None
    return {
        "earned": earned,
        "possible": possible,
        "percent": percent,
        "letter": letter_for(percent),
        "graded": len(grades),
        "assignments": len(assignments),
    }


def attendance_summary(db: Session, section_id, student_id):
    """Count of each attendance status for one student in one class."""
    counts = {status: 0 for status in STATUSES}
    rows = (
        db.query(Attendance)
        .filter(Attendance.section_id == section_id, Attendance.student_id == student_id)
        .all()
    )
    for row in rows:
        if row.status in counts:
            counts[row.status] += 1
    counts["total"] = len(rows)
    return counts


def student_report(db: Session, student_id):
    """Everything T2-016 needs for one student's report card.

    Returns a dict:
      classes   one entry per enrolled class, sorted by day and start time,
                each with course info, the class_grade numbers and attendance
      overall   average of the class percents (classes with no grades are
                left out), rounded, plus its letter
      attendance  totals across all classes
    """
    sections = (
        db.query(Section)
        .join(Enrollment, Enrollment.section_id == Section.id)
        .filter(Enrollment.student_id == student_id)
        .all()
    )
    day_order = {d: i for i, d in enumerate(DAYS)}
    sections.sort(key=lambda s: (day_order.get(s.day_of_week, 99), s.start_time, s.id))

    classes = []
    totals = {status: 0 for status in STATUSES}
    totals["total"] = 0

    for section in sections:
        grade = class_grade(db, section.id, student_id)
        attendance = attendance_summary(db, section.id, student_id)
        for key in totals:
            totals[key] += attendance[key]
        teacher = section.teacher
        classes.append({
            "section_id": section.id,
            "course_code": section.course.code,
            "course_name": section.course.name,
            "teacher_name": f"{teacher.first_name} {teacher.last_name}" if teacher else None,
            **grade,
            "attendance": attendance,
        })

    graded = [c["percent"] for c in classes if c["percent"] is not None]
    overall = round_percent(sum(graded) / len(graded)) if graded else None

    return {
        "student_id": student_id,
        "classes": classes,
        "overall_percent": overall,
        "overall_letter": letter_for(overall),
        "attendance": totals,
    }
