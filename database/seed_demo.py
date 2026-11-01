from datetime import time

from database.database import SessionLocal
from database.init_db import init_db
from database.models import Role, User
from database.students import Student
from database.parents import ParentStudent
from database.scheduling import Course, Section, Enrollment
from utils.security import hash_password


DEMO_PASSWORD = "Demo123!"


def get_roles(db):
    """Return the application's roles keyed by name."""
    return {
        role.name: role
        for role in db.query(Role).all()
    }


def get_or_create_user(
    db,
    roles,
    username,
    first_name,
    last_name,
    email,
    role_name,
):
    """Create a demo user if the username does not already exist."""
    existing = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )

    if existing:
        return existing

    user = User(
        username=username,
        password_hash=hash_password(DEMO_PASSWORD),
        first_name=first_name,
        last_name=last_name,
        email=email,
        role_id=roles[role_name].id,
    )

    db.add(user)
    db.flush()

    return user


def get_or_create_student(
    db,
    user,
    student_number,
    first_name,
    last_name,
    grade_level,
    date_of_birth,
    home_address,
    guardian_name,
    guardian_email,
):
    """Create a student profile linked to a Student user account."""
    existing = (
        db.query(Student)
        .filter(Student.student_number == student_number)
        .first()
    )

    if existing:
        return existing

    student = Student(
        user_id=user.id,
        student_number=student_number,
        first_name=first_name,
        last_name=last_name,
        grade_level=grade_level,
        date_of_birth=date_of_birth,
        home_address=home_address,
        guardian_name=guardian_name,
        guardian_email=guardian_email,
    )

    db.add(student)
    db.flush()

    return student


def link_parent(db, parent, student):
    """Link a parent account to a student profile if not already linked."""
    existing = (
        db.query(ParentStudent)
        .filter(
            ParentStudent.parent_user_id == parent.id,
            ParentStudent.student_id == student.id,
        )
        .first()
    )

    if existing:
        return existing

    link = ParentStudent(
        parent_user_id=parent.id,
        student_id=student.id,
    )

    db.add(link)
    db.flush()

    return link


def get_or_create_course(db, code, name, description):
    existing = (
        db.query(Course)
        .filter(Course.code == code)
        .first()
    )

    if existing:
        return existing

    course = Course(
        code=code,
        name=name,
        description=description,
    )

    db.add(course)
    db.flush()

    return course


def get_or_create_section(
    db,
    course,
    teacher,
    room,
    day_of_week,
    start_time,
    end_time,
):
    existing = (
        db.query(Section)
        .filter(
            Section.course_id == course.id,
            Section.room == room,
            Section.day_of_week == day_of_week,
            Section.start_time == start_time,
        )
        .first()
    )

    if existing:
        return existing

    section = Section(
        course_id=course.id,
        teacher_id=teacher.id,
        room=room,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        capacity=20,
    )

    db.add(section)
    db.flush()

    return section


def enroll_student(db, section, student_user):
    existing = (
        db.query(Enrollment)
        .filter(
            Enrollment.section_id == section.id,
            Enrollment.student_id == student_user.id,
        )
        .first()
    )

    if existing:
        return existing

    enrollment = Enrollment(
        section_id=section.id,
        student_id=student_user.id,
    )

    db.add(enrollment)
    db.flush()

    return enrollment


def seed_demo():
    # Make sure all application tables and base roles exist first.
    init_db()

    db = SessionLocal()

    try:
        roles = get_roles(db)

        required_roles = {"Admin", "Teacher", "Student", "Parent"}
        missing_roles = required_roles - set(roles)

        if missing_roles:
            raise RuntimeError(
                f"Missing required roles: {', '.join(sorted(missing_roles))}"
            )

        # ---------------------------------------------------------
        # USERS
        # ---------------------------------------------------------

        admin = get_or_create_user(
            db,
            roles,
            username="admin.demo",
            first_name="Morgan",
            last_name="Reed",
            email="morgan.reed@sansacademy.edu",
            role_name="Admin",
        )

        ramirez = get_or_create_user(
            db,
            roles,
            username="ramirez.demo",
            first_name="Elena",
            last_name="Ramirez",
            email="elena.ramirez@sansacademy.edu",
            role_name="Teacher",
        )

        lee = get_or_create_user(
            db,
            roles,
            username="lee.demo",
            first_name="Marcus",
            last_name="Lee",
            email="marcus.lee@sansacademy.edu",
            role_name="Teacher",
        )

        maya_user = get_or_create_user(
            db,
            roles,
            username="maya.demo",
            first_name="Maya",
            last_name="Carter",
            email="maya.carter@sansacademy.edu",
            role_name="Student",
        )

        liam_user = get_or_create_user(
            db,
            roles,
            username="liam.demo",
            first_name="Liam",
            last_name="Brooks",
            email="liam.brooks@sansacademy.edu",
            role_name="Student",
        )

        zoe_user = get_or_create_user(
            db,
            roles,
            username="zoe.demo",
            first_name="Zoe",
            last_name="Patel",
            email="zoe.patel@sansacademy.edu",
            role_name="Student",
        )

        noah_user = get_or_create_user(
            db,
            roles,
            username="noah.demo",
            first_name="Noah",
            last_name="Patel",
            email="noah.patel@sansacademy.edu",
            role_name="Student",
        )

        emma_user = get_or_create_user(
            db,
            roles,
            username="emma.demo",
            first_name="Emma",
            last_name="Chen",
            email="emma.chen@sansacademy.edu",
            role_name="Student",
        )

        caleb_user = get_or_create_user(
            db,
            roles,
            username="caleb.demo",
            first_name="Caleb",
            last_name="Johnson",
            email="caleb.johnson@sansacademy.edu",
            role_name="Student",
        )

        jordan = get_or_create_user(
            db,
            roles,
            username="jordan.demo",
            first_name="Jordan",
            last_name="Carter",
            email="jordan.carter@example.com",
            role_name="Parent",
        )

        dana = get_or_create_user(
            db,
            roles,
            username="dana.demo",
            first_name="Dana",
            last_name="Brooks",
            email="dana.brooks@example.com",
            role_name="Parent",
        )

        priya = get_or_create_user(
            db,
            roles,
            username="priya.demo",
            first_name="Priya",
            last_name="Patel",
            email="priya.patel@example.com",
            role_name="Parent",
        )

        linda = get_or_create_user(
            db,
            roles,
            username="linda.demo",
            first_name="Linda",
            last_name="Chen",
            email="linda.chen@example.com",
            role_name="Parent",
        )

        # ---------------------------------------------------------
        # STUDENT PROFILES
        # ---------------------------------------------------------

        maya = get_or_create_student(
            db,
            maya_user,
            student_number="SANS1001",
            first_name="Maya",
            last_name="Carter",
            grade_level=10,
            date_of_birth="2010-03-14",
            home_address="1425 Maple Street, Omaha, NE",
            guardian_name="Jordan Carter",
            guardian_email="jordan.carter@example.com",
        )

        liam = get_or_create_student(
            db,
            liam_user,
            student_number="SANS1002",
            first_name="Liam",
            last_name="Brooks",
            grade_level=10,
            date_of_birth="2010-07-22",
            home_address="3812 Oak Avenue, Omaha, NE",
            guardian_name="Dana Brooks",
            guardian_email="dana.brooks@example.com",
        )

        zoe = get_or_create_student(
            db,
            zoe_user,
            student_number="SANS1003",
            first_name="Zoe",
            last_name="Patel",
            grade_level=10,
            date_of_birth="2010-01-09",
            home_address="912 Willow Drive, Omaha, NE",
            guardian_name="Priya Patel",
            guardian_email="priya.patel@example.com",
        )

        noah = get_or_create_student(
            db,
            noah_user,
            student_number="SANS1004",
            first_name="Noah",
            last_name="Patel",
            grade_level=11,
            date_of_birth="2009-05-18",
            home_address="912 Willow Drive, Omaha, NE",
            guardian_name="Priya Patel",
            guardian_email="priya.patel@example.com",
        )

        emma = get_or_create_student(
            db,
            emma_user,
            student_number="SANS1005",
            first_name="Emma",
            last_name="Chen",
            grade_level=11,
            date_of_birth="2009-10-02",
            home_address="2741 Pine Street, Omaha, NE",
            guardian_name="Linda Chen",
            guardian_email="linda.chen@example.com",
        )

        caleb = get_or_create_student(
            db,
            caleb_user,
            student_number="SANS1006",
            first_name="Caleb",
            last_name="Johnson",
            grade_level=11,
            date_of_birth="2009-12-11",
            home_address="5608 Cedar Lane, Omaha, NE",
            guardian_name="Robert Johnson",
            guardian_email="robert.johnson@example.com",
        )

        # ---------------------------------------------------------
        # PARENT / STUDENT RELATIONSHIPS
        # ---------------------------------------------------------

        link_parent(db, jordan, maya)
        link_parent(db, dana, liam)

        # Multi-child family for Parent Portal/report-card testing.
        link_parent(db, priya, zoe)
        link_parent(db, priya, noah)

        link_parent(db, linda, emma)

        # Caleb intentionally has no linked parent account.
        # Useful as an edge case during the demo.

        # ---------------------------------------------------------
        # COURSES
        # ---------------------------------------------------------

        algebra = get_or_create_course(
            db,
            code="MATH101",
            name="Algebra I",
            description="Foundations of algebraic reasoning and problem solving.",
        )

        geometry = get_or_create_course(
            db,
            code="MATH201",
            name="Geometry",
            description="Geometry, measurement, proofs, and spatial reasoning.",
        )

        english = get_or_create_course(
            db,
            code="ENG101",
            name="English I",
            description="Reading, writing, grammar, and composition.",
        )

        literature = get_or_create_course(
            db,
            code="ENG201",
            name="Literature",
            description="Analysis of fiction, poetry, drama, and nonfiction.",
        )

        # ---------------------------------------------------------
        # SECTIONS
        # ---------------------------------------------------------

        algebra_section = get_or_create_section(
            db,
            algebra,
            ramirez,
            room="201",
            day_of_week="Mon",
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        geometry_section = get_or_create_section(
            db,
            geometry,
            ramirez,
            room="202",
            day_of_week="Tue",
            start_time=time(10, 0),
            end_time=time(11, 0),
        )

        english_section = get_or_create_section(
            db,
            english,
            lee,
            room="105",
            day_of_week="Wed",
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        literature_section = get_or_create_section(
            db,
            literature,
            lee,
            room="106",
            day_of_week="Thu",
            start_time=time(10, 0),
            end_time=time(11, 0),
        )

        # ---------------------------------------------------------
        # ENROLLMENTS
        # ---------------------------------------------------------

        # Grade 10 students
        for student_user in (
            maya_user,
            liam_user,
            zoe_user,
        ):
            enroll_student(db, algebra_section, student_user)
            enroll_student(db, english_section, student_user)

        # Grade 11 students
        for student_user in (
            noah_user,
            emma_user,
            caleb_user,
        ):
            enroll_student(db, geometry_section, student_user)
            enroll_student(db, literature_section, student_user)

        db.commit()

        # ---------------------------------------------------------
        # SUMMARY
        # ---------------------------------------------------------

        print()
        print("=" * 60)
        print("SANS Academy demo data seeded successfully.")
        print("=" * 60)
        print()
        print(f"Demo password for all accounts: {DEMO_PASSWORD}")
        print()
        print("ADMIN")
        print("  admin.demo")
        print()
        print("TEACHERS")
        print("  ramirez.demo")
        print("  lee.demo")
        print()
        print("STUDENTS")
        print("  maya.demo")
        print("  liam.demo")
        print("  zoe.demo")
        print("  noah.demo")
        print("  emma.demo")
        print("  caleb.demo")
        print()
        print("PARENTS")
        print("  jordan.demo   -> Maya Carter")
        print("  dana.demo     -> Liam Brooks")
        print("  priya.demo    -> Zoe Patel + Noah Patel")
        print("  linda.demo    -> Emma Chen")
        print()
        print("Caleb Johnson intentionally has no linked parent account.")
        print("=" * 60)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_demo()