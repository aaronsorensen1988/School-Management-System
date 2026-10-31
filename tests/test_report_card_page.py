"""Report card page through the real app. AMG-009 / T2-016.

Who can see a report card, and that the numbers from T2-019 show up on the
page. Every table this file needs is imported here so it runs on its own.
"""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.attendance import Attendance
from database.database import Base, get_db
from database.grades import Assignment, Grade
from database.models import Role, User
from database.students import Student
from database.parents import ParentStudent
from database.scheduling import Course, Enrollment, Section
from presentation.report_card_routes import can_view_report_card
from security.keys import generate_key
from utils.security import hash_password

KEY = generate_key()


class _Actor:
    def __init__(self, user_id, role):
        self.user_id, self.role = user_id, role


def test_who_can_view():
    class FakeDB:
        def query(self, *args): return self
        def join(self, *args): return self
        def filter(self, *args): return self
        def first(self): return None
        
    db = FakeDB()
    
    assert can_view_report_card(_Actor(1, "Admin"), 5, db)
    assert can_view_report_card(_Actor(5, "Student"), 5, db)
    assert not can_view_report_card(_Actor(6, "Student"), 5, db)
    assert not can_view_report_card(_Actor(2, "Teacher"), 5, db)
    assert not can_view_report_card(_Actor(3, "Parent"), 5, db)
    assert not can_view_report_card(_Actor(None, None), 5, db)
    
@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    monkeypatch.setenv("SMS_SESSION_SECRET", "test-secret-not-a-real-one")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session(engine) as s:
        roles = {n: Role(name=n) for n in ("Admin", "Teacher", "Student", "Parent")}
        s.add_all(roles.values())
        s.flush()

        def user(username, pw, first, last, role):
            return User(username=username, password_hash=hash_password(pw), first_name=first,
                        last_name=last, email=f"{username}@school.edu", role_id=roles[role].id)

        s.add_all([
            user("admin", "admin-pw", "System", "Admin", "Admin"),
            user("anderson", "ann-pw", "Ann", "Anderson", "Teacher"),
            user("jane", "jane-pw", "Jane", "Smith", "Student"),
            user("john", "john-pw", "John", "Jones", "Student"),
            user("pat", "pat-pw", "Pat", "Parent", "Parent"),
        ])
        s.flush()
        ann = s.query(User).filter_by(username="anderson").one()
        jane = s.query(User).filter_by(username="jane").one()

        math = Course(code="MATH101", name="Algebra I")
        art = Course(code="ART101", name="Art")
        s.add_all([math, art])
        s.flush()
        math_mon = Section(course_id=math.id, teacher_id=ann.id, room="A101", day_of_week="Mon",
                           start_time=time(9, 0), end_time=time(9, 50))
        art_wed = Section(course_id=art.id, room="C303", day_of_week="Wed",
                          start_time=time(13, 0), end_time=time(13, 50))
        s.add_all([math_mon, art_wed])
        s.flush()
        s.add_all([Enrollment(section_id=math_mon.id, student_id=jane.id),
                   Enrollment(section_id=art_wed.id, student_id=jane.id)])

        quiz = Assignment(section_id=math_mon.id, title="Quiz 1", points_possible=20)
        test = Assignment(section_id=math_mon.id, title="Test 1", points_possible=100)
        s.add_all([quiz, test])
        s.flush()
        # 18/20 + 72/100 = 90/120 = 75.0% (C)
        s.add_all([Grade(assignment_id=quiz.id, student_id=jane.id, points_earned=18),
                   Grade(assignment_id=test.id, student_id=jane.id, points_earned=72)])
        s.add_all([Attendance(section_id=math_mon.id, student_id=jane.id, on_date=date(2026, 10, 19), status="present"),
                   Attendance(section_id=math_mon.id, student_id=jane.id, on_date=date(2026, 10, 26), status="absent")])
        s.commit()

    import api

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    api.app.dependency_overrides[get_db] = override_get_db
    yield TestClient(api.app, follow_redirects=False), TestSession
    api.app.dependency_overrides.clear()
    keys_module._cached = None


def _login(client, username, password):
    assert client.post("/login", data={"username": username, "password": password}).status_code == 302


def _id(Session_, username):
    with Session_() as s:
        return s.query(User).filter_by(username=username).one().id


def test_must_be_logged_in(setup):
    client, Session_ = setup
    for url in ("/report-cards", f"/report-cards/{_id(Session_, 'jane')}"):
        r = client.get(url)
        assert r.status_code == 302 and r.headers["location"] == "/login"


def test_student_is_sent_to_their_own_card(setup):
    client, Session_ = setup
    _login(client, "jane", "jane-pw")
    r = client.get("/report-cards")
    assert r.status_code == 302
    assert r.headers["location"] == f"/report-cards/{_id(Session_, 'jane')}"


def test_student_sees_their_grades_and_attendance(setup):
    client, Session_ = setup
    _login(client, "jane", "jane-pw")
    r = client.get(f"/report-cards/{_id(Session_, 'jane')}")
    assert r.status_code == 200
    assert "Jane Smith" in r.text
    assert "MATH101" in r.text and "Ann Anderson" in r.text
    assert "75.0%" in r.text
    assert ">C<" in r.text
    assert "2 of 2" in r.text
    assert "No grades yet" in r.text          # Art has no grades
    assert "Overall average" in r.text


def test_student_cannot_see_someone_else(setup):
    client, Session_ = setup
    _login(client, "john", "john-pw")
    r = client.get(f"/report-cards/{_id(Session_, 'jane')}")
    assert r.status_code == 403
    assert "75.0%" not in r.text


def test_admin_sees_the_student_list_and_any_card(setup):
    client, Session_ = setup
    _login(client, "admin", "admin-pw")
    r = client.get("/report-cards")
    assert r.status_code == 200
    assert "Jane Smith" in r.text and "John Jones" in r.text
    assert "Ann Anderson" not in r.text      # teachers aren't in the student list

    r = client.get(f"/report-cards/{_id(Session_, 'jane')}")
    assert r.status_code == 200
    assert "75.0%" in r.text


def test_admin_gets_404_for_a_non_student(setup):
    client, Session_ = setup
    _login(client, "admin", "admin-pw")
    assert client.get(f"/report-cards/{_id(Session_, 'anderson')}").status_code == 404
    assert client.get("/report-cards/99999").status_code == 404


def test_teachers_are_refused_for_now(setup):
    client, Session_ = setup
    _login(client, "anderson", "ann-pw")
    assert client.get("/report-cards").status_code == 403
    r = client.get(f"/report-cards/{_id(Session_, 'jane')}")
    assert r.status_code == 403
    assert "75.0%" not in r.text


def test_student_with_no_classes(setup):
    client, Session_ = setup
    _login(client, "john", "john-pw")
    r = client.get(f"/report-cards/{_id(Session_, 'john')}")
    assert r.status_code == 200
    assert "Not enrolled in any classes yet." in r.text


def test_classes_page_links_to_report_cards_for_students(setup):
    client, _ = setup
    _login(client, "jane", "jane-pw")
    assert "/report-cards" in client.get("/classes").text

def test_parent_can_only_view_linked_student(setup):
    client, Session_ = setup

    with Session_() as s:
        pat = s.query(User).filter_by(username="pat").one()
        jane = s.query(User).filter_by(username="jane").one()
        john = s.query(User).filter_by(username="john").one()
        
        # 1. Create actual Student profiles with STRING birth dates
        jane_profile = Student(
            user_id=jane.id,
            student_number="STU-JANE",
            first_name="Jane",
            last_name="Smith",
            grade_level="9",
            date_of_birth="2010-01-01",  # Passed as a string!
            home_address="123 Test Ave",
            guardian_name="Pat Parent",
            guardian_email="pat@school.edu"
        )
        john_profile = Student(
            user_id=john.id,
            student_number="STU-JOHN",
            first_name="John",
            last_name="Doe",
            grade_level="9",
            date_of_birth="2010-02-02",  # Passed as a string!
            home_address="456 Other St",
            guardian_name="Other Parent",
            guardian_email="other@school.edu"
        )
        s.add_all([jane_profile, john_profile])
        s.flush() 
        
        # 2. Link Pat to Jane's actual Student profile ID
        s.add(ParentStudent(parent_user_id=pat.id, student_id=jane_profile.id))
        s.commit()
        
        jane_id = jane.id
        john_id = john.id

    # 3. Log in as Pat
    _login(client, "pat", "pat-pw")

    # 4. Check Jane's report card (Linked -> Should be 200 OK)
    r_jane = client.get(f"/report-cards/{jane_id}")
    assert r_jane.status_code == 200

    # 5. Check John's report card (Not linked -> Should be 403 Forbidden)
    r_john = client.get(f"/report-cards/{john_id}")
    assert r_john.status_code == 403