
"""Additional fictional academic data for the SANS Academy demo."""

from datetime import date, datetime, timedelta, timezone

from database.announcements import Announcement
from database.attendance import Attendance
from database.audit import AccessLog
from database.database import SessionLocal
from database.emergency import EmergencyNotification, EmergencyReceipt
from database.grades import Assignment, Grade
from database.messages import Message
from database.models import User
from database.parents import ParentStudent
from database.scheduling import Course, Enrollment, Section
from database.students import Student


def get_or_create_assignment(db, section, title, points, due_date):
    """Create an assignment only if it does not already exist."""
    assignment = (
        db.query(Assignment)
        .filter_by(section_id=section.id, title=title)
        .first()
    )

    if assignment is None:
        assignment = Assignment(
            section_id=section.id,
            title=title,
            points_possible=points,
            due_date=due_date,
        )
        db.add(assignment)
        db.flush()

    return assignment


def get_or_create_grade(db, assignment, student, teacher, points):
    """Avoid duplicate grades for the same student and assignment."""
    grade = (
        db.query(Grade)
        .filter_by(
            assignment_id=assignment.id,
            student_id=student.id,
        )
        .first()
    )

    if grade is None:
        grade = Grade(
            assignment_id=assignment.id,
            student_id=student.id,
            points_earned=points,
            recorded_by=teacher.id,
        )
        db.add(grade)

    return grade


def seed_algebra(db):
    """Populate Algebra I assignments and sample student grades."""
    section = (
        db.query(Section)
        .join(Course, Section.course_id == Course.id)
        .filter(Course.code == "MATH101", Section.room == "201")
        .one_or_none()
    )

    teacher = db.query(User).filter_by(username="ramirez.demo").one_or_none()

    if section is None or teacher is None or section.teacher_id != teacher.id:
        raise RuntimeError("Run the SANS Academy core seed first.")

    assignment_data = [
        ("Linear Equations Quiz", 20, date(2026, 10, 7)),
        ("Unit 1 Exam", 100, date(2026, 10, 20)),
        ("Graphing Homework", 25, date(2026, 11, 6)),
    ]

    assignments = {
        title: get_or_create_assignment(db, section, title, points, due)
        for title, points, due in assignment_data
    }

    scores = {
        "maya.demo": (18, 92),
        "liam.demo": (12, 66),
        "zoe.demo": (17, 82),
    }

    for username, (quiz_score, exam_score) in scores.items():
        student = db.query(User).filter_by(username=username).one_or_none()

        if student is None or not db.query(Enrollment).filter_by(
            section_id=section.id, student_id=student.id
        ).first():
            raise RuntimeError(f"Missing Algebra I enrollment: {username}")

        get_or_create_grade(
            db, assignments["Linear Equations Quiz"],
            student, teacher, quiz_score
        )
        get_or_create_grade(
            db, assignments["Unit 1 Exam"],
            student, teacher, exam_score
        )



def seed_geometry(db):
    """Populate Geometry assignments and grades for 11th graders."""
    section = (
        db.query(Section)
        .join(Course, Section.course_id == Course.id)
        .filter(Course.code == "MATH201", Section.room == "202")
        .one_or_none()
    )

    teacher = db.query(User).filter_by(
        username="ramirez.demo"
    ).one_or_none()

    if section is None or teacher is None or section.teacher_id != teacher.id:
        raise RuntimeError("Missing SANS Academy Geometry section or teacher.")

    assignment_data = [
        ("Angles and Shapes Quiz", 20, date(2026, 10, 9)),
        ("Geometry Unit Exam", 100, date(2026, 10, 22)),
        ("Triangle Proofs Homework", 30, date(2026, 11, 5)),
    ]

    assignments = {
        title: get_or_create_assignment(db, section, title, points, due)
        for title, points, due in assignment_data
    }

    scores = {
        "noah.demo": (19, 90),
        "emma.demo": (16, 85),
        "caleb.demo": (13, 71),
    }

    for username, (quiz_score, exam_score) in scores.items():
        student = db.query(User).filter_by(
            username=username
        ).one_or_none()

        if student is None or not db.query(Enrollment).filter_by(
            section_id=section.id,
            student_id=student.id,
        ).first():
            raise RuntimeError(f"Missing Geometry enrollment: {username}")

        get_or_create_grade(
            db, assignments["Angles and Shapes Quiz"],
            student, teacher, quiz_score
        )
        get_or_create_grade(
            db, assignments["Geometry Unit Exam"],
            student, teacher, exam_score
        )



def seed_english(db):
    """Populate English I assignments and grades for 10th graders."""
    section = (
        db.query(Section)
        .join(Course, Section.course_id == Course.id)
        .filter(Course.code == "ENG101", Section.room == "105")
        .one_or_none()
    )

    teacher = db.query(User).filter_by(
        username="lee.demo"
    ).one_or_none()

    if section is None or teacher is None or section.teacher_id != teacher.id:
        raise RuntimeError("Missing SANS Academy English I section or teacher.")

    assignment_data = [
        ("Reading Comprehension Quiz", 20, date(2026, 10, 8)),
        ("Persuasive Essay", 50, date(2026, 10, 23)),
        ("Narrative Writing Project", 40, date(2026, 11, 6)),
    ]

    assignments = {
        title: get_or_create_assignment(db, section, title, points, due)
        for title, points, due in assignment_data
    }

    scores = {
        "maya.demo": (18, 44),
        "liam.demo": (19, 46),
        "zoe.demo": (17, 47),
    }

    for username, (quiz_score, essay_score) in scores.items():
        student = db.query(User).filter_by(
            username=username
        ).one_or_none()

        if student is None or not db.query(Enrollment).filter_by(
            section_id=section.id,
            student_id=student.id,
        ).first():
            raise RuntimeError(f"Missing English I enrollment: {username}")

        get_or_create_grade(
            db, assignments["Reading Comprehension Quiz"],
            student, teacher, quiz_score
        )
        get_or_create_grade(
            db, assignments["Persuasive Essay"],
            student, teacher, essay_score
        )



def seed_literature(db):
    """Populate Literature assignments and grades for 11th graders."""
    section = (
        db.query(Section)
        .join(Course, Section.course_id == Course.id)
        .filter(Course.code == "ENG201", Section.room == "106")
        .one_or_none()
    )

    teacher = db.query(User).filter_by(
        username="lee.demo"
    ).one_or_none()

    if section is None or teacher is None or section.teacher_id != teacher.id:
        raise RuntimeError("Missing SANS Academy Literature section or teacher.")

    assignment_data = [
        ("Poetry Analysis Quiz", 25, date(2026, 10, 15)),
        ("Literary Analysis Essay", 75, date(2026, 10, 29)),
        ("Comparative Literature Project", 50, date(2026, 11, 12)),
    ]

    assignments = {
        title: get_or_create_assignment(db, section, title, points, due)
        for title, points, due in assignment_data
    }

    scores = {
        "noah.demo": (17, 55),
        "emma.demo": (24, 72),
        "caleb.demo": (22, 64),
    }

    for username, (quiz_score, essay_score) in scores.items():
        student = db.query(User).filter_by(
            username=username
        ).one_or_none()

        if student is None or not db.query(Enrollment).filter_by(
            section_id=section.id,
            student_id=student.id,
        ).first():
            raise RuntimeError(f"Missing Literature enrollment: {username}")

        get_or_create_grade(
            db, assignments["Poetry Analysis Quiz"],
            student, teacher, quiz_score
        )
        get_or_create_grade(
            db, assignments["Literary Analysis Essay"],
            student, teacher, essay_score
        )



def seed_attendance(db):
    """Seed four weeks of fictional SANS Academy attendance."""

    class_data = {
        "MATH101": ("201", ["maya.demo", "liam.demo", "zoe.demo"], [5, 12, 19, 26]),
        "MATH201": ("202", ["noah.demo", "emma.demo", "caleb.demo"], [6, 13, 20, 27]),
        "ENG101": ("105", ["maya.demo", "liam.demo", "zoe.demo"], [7, 14, 21, 28]),
        "ENG201": ("106", ["noah.demo", "emma.demo", "caleb.demo"], [8, 15, 22, 29]),
    }

    # Only these student/class/date combinations differ from "present".
    exceptions = {
        ("MATH101", "liam.demo", 12): "absent",
        ("MATH101", "zoe.demo", 19): "excused",
        ("MATH101", "liam.demo", 26): "tardy",

        ("MATH201", "noah.demo", 13): "absent",
        ("MATH201", "caleb.demo", 20): "absent",

        ("ENG101", "liam.demo", 21): "excused",
        ("ENG101", "maya.demo", 28): "tardy",

        ("ENG201", "caleb.demo", 22): "tardy",
        ("ENG201", "emma.demo", 29): "tardy",
    }

    for course_code, (room, usernames, days) in class_data.items():
        section = (
            db.query(Section)
            .join(Course, Section.course_id == Course.id)
            .filter(Course.code == course_code, Section.room == room)
            .one_or_none()
        )

        if section is None or section.teacher_id is None:
            raise RuntimeError(f"Missing class or teacher: {course_code}")

        for username in usernames:
            student = db.query(User).filter_by(
                username=username
            ).one_or_none()

            if student is None or not db.query(Enrollment).filter_by(
                section_id=section.id,
                student_id=student.id,
            ).first():
                raise RuntimeError(
                    f"Missing enrollment: {username} in {course_code}"
                )

            for day in days:
                attendance_date = date(2026, 10, day)

                existing = (
                    db.query(Attendance)
                    .filter_by(
                        section_id=section.id,
                        student_id=student.id,
                        on_date=attendance_date,
                    )
                    .first()
                )

                if existing:
                    continue

                status = exceptions.get(
                    (course_code, username, day),
                    "present",
                )

                db.add(
                    Attendance(
                        section_id=section.id,
                        student_id=student.id,
                        on_date=attendance_date,
                        status=status,
                        recorded_by=section.teacher_id,
                    )
                )



def seed_announcements(db):
    """Populate published SANS Academy announcements."""
    admin = db.query(User).filter_by(
        username="admin.demo"
    ).one_or_none()

    if admin is None:
        raise RuntimeError("Missing SANS Academy demo administrator.")

    announcement_data = [
        (
            "SANS Academy Fall Showcase",
            "Families are invited to our Fall Showcase on "
            "November 12 at 6:00 PM in the main hall. "
            "Students will present projects and classroom work.",
            "everyone",
            datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc),
        ),
        (
            "October Progress Reports",
            "October progress reports are now available in Roster9. "
            "Parents are encouraged to review their children's "
            "grades and attendance before conferences.",
            "parents",
            datetime(2026, 10, 28, 14, 0, tzinfo=timezone.utc),
        ),
        (
            "Faculty Planning Meeting",
            "Faculty planning will take place November 4 "
            "at 3:30 PM in Room 105. Please bring your "
            "current student progress summaries.",
            "staff",
            datetime(2026, 10, 29, 14, 0, tzinfo=timezone.utc),
        ),
        (
            "November Reading Challenge",
            "The November Reading Challenge begins November 2! "
            "Students can participate by completing their reading "
            "logs and submitting them to Mr. Lee.",
            "students",
            datetime(2026, 10, 30, 14, 0, tzinfo=timezone.utc),
        ),
    ]

    for title, body, audience, published_at in announcement_data:
        existing = (
            db.query(Announcement)
            .filter_by(title=title, audience=audience)
            .first()
        )

        if existing:
            continue

        announcement = Announcement(
            title=title,
            body=body,
            audience=audience,
            author_id=admin.id,
            created_at=published_at,
        )

        announcement.publish(when=published_at)
        db.add(announcement)



def seed_emergency(db):
    """Seed a fictional safety drill for demo accounts only."""

    demo_usernames = [
        "admin.demo",
        "ramirez.demo",
        "lee.demo",
        "maya.demo",
        "liam.demo",
        "zoe.demo",
        "noah.demo",
        "emma.demo",
        "caleb.demo",
        "jordan.demo",
        "dana.demo",
        "priya.demo",
        "linda.demo",
    ]

    users = (
        db.query(User)
        .filter(User.username.in_(demo_usernames))
        .all()
    )

    if len(users) != len(demo_usernames):
        raise RuntimeError(
            "Missing demo accounts. Run seed_demo.py first."
        )

    admin = next(
        user for user in users
        if user.username == "admin.demo"
    )

    title = "DEMO ONLY: Campus Safety Drill"
    message = (
        "This is a fictional safety-drill notification created "
        "for the Roster9 demonstration. No real emergency is "
        "occurring. Please review the notification system as "
        "part of the training exercise."
    )

    sent_at = datetime(2026, 10, 30, 16, 0, tzinfo=timezone.utc)

    alert = (
        db.query(EmergencyNotification)
        .filter_by(
            title=title,
            audience="everyone",
            sent_by=admin.id,
        )
        .first()
    )

    if alert is None:
        alert = EmergencyNotification(
            title=title,
            message=message,
            audience="everyone",
            sent_by=admin.id,
            sent_at=sent_at,
        )

        db.add(alert)
        db.flush()

        # Record the demo alert in the audit trail.
        db.add(
            AccessLog(
                actor_user_id=admin.id,
                actor_role="Admin",
                action="create",
                resource_type="emergency_notification",
                resource_id=alert.id,
                outcome="allowed",
                detail="DEMO SEED: Fictional drill for 13 demo users.",
            )
        )

    # These users have already read the demonstration alert.
    read_usernames = {
        "admin.demo",
        "ramirez.demo",
        "maya.demo",
        "noah.demo",
        "priya.demo",
    }

    read_at = datetime(2026, 10, 30, 17, 0, tzinfo=timezone.utc)

    existing_receipts = {
        receipt.user_id
        for receipt in db.query(EmergencyReceipt)
        .filter_by(notification_id=alert.id)
        .all()
    }

    for user in users:
        if user.id in existing_receipts:
            continue

        db.add(
            EmergencyReceipt(
                notification_id=alert.id,
                user_id=user.id,
                read_at=(
                    read_at if user.username in read_usernames
                    else None
                ),
            )
        )



def seed_messages(db):
    """Seed fictional teacher-parent conversations for SANS Academy."""

    conversations = [
        (
            "SANS1001", "ramirez.demo", "jordan.demo",
            "Maya has been doing excellent work in Algebra I. "
            "Her recent assessments show a strong understanding "
            "of the material.",
            "Thank you for the update! Maya has been working "
            "hard on her math assignments at home.",
            datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc),
        ),
        (
            "SANS1002", "ramirez.demo", "dana.demo",
            "I wanted to discuss Liam's recent Algebra I results. "
            "He's having difficulty with some of the material, "
            "and I'd like to work with him on a study plan.",
            "Thank you for reaching out. I'll encourage Liam "
            "to attend extra help sessions and review his work.",
            datetime(2026, 10, 28, 16, 0, tzinfo=timezone.utc),
        ),
        (
            "SANS1002", "lee.demo", "dana.demo",
            "Liam has been performing very well in English I. "
            "His persuasive essay was especially strong.",
            "That's wonderful to hear! He really enjoys "
            "writing, so I'm glad it's showing in his work.",
            datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc),
        ),
        (
            "SANS1003", "ramirez.demo", "priya.demo",
            "Zoe is making good progress in Algebra I. "
            "Her recent exam results were encouraging, "
            "and she's participating regularly in class.",
            "Thank you for keeping me informed! "
            "I'll make sure she continues practicing.",
            datetime(2026, 10, 29, 16, 0, tzinfo=timezone.utc),
        ),
        (
            "SANS1004", "lee.demo", "priya.demo",
            "I'd like to help Noah strengthen his literary "
            "analysis skills. He's showing improvement, "
            "but his recent essay suggests he could benefit "
            "from some additional practice.",
            "I appreciate the update. We'll spend some time "
            "reviewing the material together this weekend.",
            datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc),
        ),
        (
            "SANS1005", "lee.demo", "linda.demo",
            "Emma has demonstrated excellent analytical "
            "and writing skills in Literature. Her recent "
            "essay was particularly impressive.",
            "Thank you! Emma has really enjoyed the class "
            "and has been talking about the books at home.",
            datetime(2026, 10, 30, 16, 0, tzinfo=timezone.utc),
        ),
    ]

    def add_message(student, sender, recipient, body, sent_at, role):
        """Create a demo message if this exact message is not present."""
        existing = (
            db.query(Message)
            .filter_by(
                student_id=student.id,
                sender_id=sender.id,
                recipient_id=recipient.id,
            )
            .all()
        )

        # Message bodies are encrypted, so compare decrypted values
        # in Python rather than filtering the encrypted DB column.
        if any(message.body == body for message in existing):
            return

        message = Message(
            student_id=student.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            body=body,
            sent_at=sent_at,
        )

        db.add(message)
        db.flush()

        # Identify seeded messages separately in the audit trail.
        db.add(
            AccessLog(
                actor_user_id=sender.id,
                actor_role=role,
                action="create",
                resource_type="message",
                resource_id=message.id,
                outcome="allowed",
                detail=(
                    f"DEMO SEED: to user {recipient.id} "
                    f"about student {student.id}"
                ),
            )
        )

    for student_number, teacher_name, parent_name, first, reply, sent_at in conversations:
        student = db.query(Student).filter_by(
            student_number=student_number
        ).one_or_none()

        teacher = db.query(User).filter_by(
            username=teacher_name
        ).one_or_none()

        parent = db.query(User).filter_by(
            username=parent_name
        ).one_or_none()

        if not all((student, teacher, parent)):
            raise RuntimeError(
                f"Missing demo conversation participants: {student_number}"
            )

        # Verify the parent is linked to the student.
        parent_link = (
            db.query(ParentStudent)
            .filter_by(
                parent_user_id=parent.id,
                student_id=student.id,
            )
            .first()
        )

        # Verify this teacher actually teaches the student.
        teacher_link = (
            db.query(Enrollment)
            .join(Section, Enrollment.section_id == Section.id)
            .filter(
                Enrollment.student_id == student.user_id,
                Section.teacher_id == teacher.id,
            )
            .first()
        )

        if not parent_link or not teacher_link:
            raise RuntimeError(
                f"Invalid teacher-parent relationship: {student_number}"
            )

        # The teacher starts the conversation.
        add_message(
            student, teacher, parent, first,
            sent_at, "Teacher"
        )

        # The parent replies two hours later.
        add_message(
            student, parent, teacher, reply,
            sent_at + timedelta(hours=2), "Parent"
        )


def seed_scenarios():
    with SessionLocal() as db:
        try:
            seed_algebra(db)
            seed_geometry(db)
            seed_english(db)
            seed_literature(db)
            seed_attendance(db)
            seed_announcements(db)
            seed_emergency(db)
            seed_messages(db)
            db.commit()
        except Exception:
            db.rollback()
            raise

    print("SANS Academy demo scenarios seeded successfully.")


if __name__ == "__main__":
    seed_scenarios()
