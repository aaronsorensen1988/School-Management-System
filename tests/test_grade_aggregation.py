"""Grade aggregation for report cards. AMG-009 / T2-019.

Every table this file needs is imported here, so it runs on its own as well
as in the full suite.
"""

from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from business_logic.amg.grade_aggregation import (
    attendance_summary,
    class_grade,
    letter_for,
    round_percent,
    student_report,
)
from database.attendance import Attendance
from database.database import Base
from database.grades import Assignment, Grade
from database.models import Role, User
from database.scheduling import Course, Enrollment, Section
from security.keys import generate_key

KEY = generate_key()


# -- small helpers ----------------------------------------------------------

def test_letter_scale():
    assert letter_for(100) == "A"
    assert letter_for(90) == "A"
    assert letter_for(89.9) == "B"
    assert letter_for(80) == "B"
    assert letter_for(70) == "C"
    assert letter_for(60) == "D"
    assert letter_for(59.9) == "F"
    assert letter_for(0) == "F"
    assert letter_for(105) == "A"
    assert letter_for(None) is None


def test_rounding_is_half_up():
    assert round_percent(89.95) == 90.0
    assert round_percent(89.94) == 89.9
    assert round_percent(66.666666) == 66.7
    assert round_percent(None) is None


# -- with a database -----------------------------------------------------------

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
        ann = User(username="anderson", password_hash="x", first_name="Ann", last_name="Anderson",
                   email="ann@school.edu", role_id=teacher_role.id)
        jane = User(username="jane", password_hash="x", first_name="Jane", last_name="Smith",
                    email="jane@school.edu", role_id=student_role.id)
        john = User(username="john", password_hash="x", first_name="John", last_name="Jones",
                    email="john@school.edu", role_id=student_role.id)
        s.add_all([ann, jane, john])
        s.flush()

        math = Course(code="MATH101", name="Algebra I")
        eng = Course(code="ENG101", name="English I")
        art = Course(code="ART101", name="Art")
        s.add_all([math, eng, art])
        s.flush()

        # Added out of order on purpose; the report sorts by day and time.
        eng_tue = Section(course_id=eng.id, room="B202", day_of_week="Tue",
                          start_time=time(9, 0), end_time=time(9, 50))
        math_mon = Section(course_id=math.id, teacher_id=ann.id, room="A101", day_of_week="Mon",
                           start_time=time(9, 0), end_time=time(9, 50))
        art_wed = Section(course_id=art.id, room="C303", day_of_week="Wed",
                          start_time=time(13, 0), end_time=time(13, 50))
        s.add_all([eng_tue, math_mon, art_wed])
        s.flush()

        for section in (math_mon, eng_tue, art_wed):
            s.add(Enrollment(section_id=section.id, student_id=jane.id))
        s.add(Enrollment(section_id=math_mon.id, student_id=john.id))

        quiz = Assignment(section_id=math_mon.id, title="Quiz 1", points_possible=20)
        test = Assignment(section_id=math_mon.id, title="Test 1", points_possible=100)
        homework = Assignment(section_id=math_mon.id, title="Homework 1", points_possible=10)
        essay = Assignment(section_id=eng_tue.id, title="Essay 1", points_possible=50)
        s.add_all([quiz, test, homework, essay])
        s.flush()

        # Jane, math: 18/20 and 72/100, homework not graded yet -> 90/120 = 75%
        s.add_all([
            Grade(assignment_id=quiz.id, student_id=jane.id, points_earned=18),
            Grade(assignment_id=test.id, student_id=jane.id, points_earned=72),
            # Jane, English: 47/50 = 94%
            Grade(assignment_id=essay.id, student_id=jane.id, points_earned=47),
            # John, math: perfect quiz only, so his grades never mix with Jane's
            Grade(assignment_id=quiz.id, student_id=john.id, points_earned=20),
        ])

        # Jane's math attendance: 2 present, 1 tardy, 1 absent
        for day, status in ((5, "present"), (12, "present"), (19, "tardy"), (26, "absent")):
            s.add(Attendance(section_id=math_mon.id, student_id=jane.id,
                             on_date=date(2026, 10, day), status=status))
        # Jane's English attendance: 1 excused
        s.add(Attendance(section_id=eng_tue.id, student_id=jane.id,
                         on_date=date(2026, 10, 20), status="excused"))
        s.commit()
        yield s

    keys_module._cached = None


def _ids(db):
    jane = db.query(User).filter_by(username="jane").one().id
    john = db.query(User).filter_by(username="john").one().id
    sections = {s.course.code: s.id for s in db.query(Section).all()}
    return jane, john, sections


def test_class_grade_weights_by_points(db):
    jane, _, sections = _ids(db)
    g = class_grade(db, sections["MATH101"], jane)
    # 90 of 120, not the average of 90% and 72% (which would be 81%)
    assert (g["earned"], g["possible"]) == (90, 120)
    assert g["percent"] == 75.0
    assert g["letter"] == "C"


def test_ungraded_work_is_left_out_not_zero(db):
    jane, _, sections = _ids(db)
    g = class_grade(db, sections["MATH101"], jane)
    assert g["graded"] == 2
    assert g["assignments"] == 3


def test_class_with_no_grades_has_no_percent(db):
    jane, _, sections = _ids(db)
    g = class_grade(db, sections["ART101"], jane)
    assert g["percent"] is None
    assert g["letter"] is None
    assert g["assignments"] == 0


def test_students_grades_never_mix(db):
    jane, john, sections = _ids(db)
    g = class_grade(db, sections["MATH101"], john)
    assert (g["earned"], g["possible"], g["percent"]) == (20, 20, 100.0)


def test_extra_credit_can_go_over_100(db):
    jane, _, sections = _ids(db)
    essay = db.query(Assignment).filter_by(title="Essay 1").one()
    db.query(Grade).filter_by(assignment_id=essay.id, student_id=jane).one().points_earned = 55
    db.commit()
    g = class_grade(db, sections["ENG101"], jane)
    assert g["percent"] == 110.0
    assert g["letter"] == "A"


def test_attendance_summary_counts_each_status(db):
    jane, _, sections = _ids(db)
    a = attendance_summary(db, sections["MATH101"], jane)
    assert a == {"present": 2, "absent": 1, "tardy": 1, "excused": 0, "total": 4}


def test_student_report_lists_classes_in_schedule_order(db):
    jane, _, _ = _ids(db)
    report = student_report(db, jane)
    assert [c["course_code"] for c in report["classes"]] == ["MATH101", "ENG101", "ART101"]
    math = report["classes"][0]
    assert math["teacher_name"] == "Ann Anderson"
    assert report["classes"][1]["teacher_name"] is None


def test_overall_is_average_of_graded_classes(db):
    jane, _, _ = _ids(db)
    report = student_report(db, jane)
    # (75.0 + 94.0) / 2 = 84.5; Art has no grades, so it's left out
    assert report["overall_percent"] == 84.5
    assert report["overall_letter"] == "B"


def test_report_attendance_totals(db):
    jane, _, _ = _ids(db)
    report = student_report(db, jane)
    assert report["attendance"] == {"present": 2, "absent": 1, "tardy": 1, "excused": 1, "total": 5}


def test_student_with_no_classes_gets_an_empty_report(db):
    report = student_report(db, 9999)
    assert report["classes"] == []
    assert report["overall_percent"] is None
    assert report["overall_letter"] is None
    assert report["attendance"]["total"] == 0
