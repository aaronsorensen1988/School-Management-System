"""Classes page: scheduling UI and teacher assignment. AMG-007 / T1-021, T1-023.

Checks the page through the real app: who can see it, who can change it,
and that validation and the overlap rules show up as errors on the page.
"""

from datetime import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import Role, User
from database.scheduling import Course, Enrollment, Section
from security.keys import generate_key
from utils.security import hash_password

KEY = generate_key()


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    monkeypatch.setenv("SMS_SESSION_SECRET", "test-secret-not-a-real-one")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    # StaticPool so the app's thread and the test share one in-memory db.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session(engine) as s:
        admin_role, teacher_role, student_role = Role(name="Admin"), Role(name="Teacher"), Role(name="Student")
        s.add_all([admin_role, teacher_role, student_role])
        s.flush()

        s.add_all([
            User(username="admin", password_hash=hash_password("admin-pw"), first_name="System",
                 last_name="Admin", email="admin@school.edu", role_id=admin_role.id),
            User(username="anderson", password_hash=hash_password("ann-pw"), first_name="Ann",
                 last_name="Anderson", email="ann@school.edu", role_id=teacher_role.id),
            User(username="brown", password_hash=hash_password("bob-pw"), first_name="Bob",
                 last_name="Brown", email="bob@school.edu", role_id=teacher_role.id),
            User(username="jane", password_hash=hash_password("jane-pw"), first_name="Jane",
                 last_name="Smith", email="jane@school.edu", role_id=student_role.id),
        ])
        s.flush()
        ann = s.query(User).filter(User.username == "anderson").one()
        jane = s.query(User).filter(User.username == "jane").one()

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
        s.add(Enrollment(section_id=math_mon.id, student_id=jane.id))
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
    r = client.post("/login", data={"username": username, "password": password})
    assert r.status_code == 302


def _section_id(Session_, code, day):
    with Session_() as s:
        return (
            s.query(Section).join(Course)
            .filter(Course.code == code, Section.day_of_week == day).one().id
        )


# -- who can see it --------------------------------------------------------

def test_must_be_logged_in(setup):
    client, _ = setup
    r = client.get("/classes")
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_admin_sees_every_section_and_the_forms(setup):
    client, _ = setup
    _login(client, "admin", "admin-pw")
    r = client.get("/classes")
    assert r.status_code == 200
    assert "MATH101" in r.text and "ART101" in r.text
    assert "Add Course" in r.text and "Add Section" in r.text


def test_teacher_sees_only_their_sections(setup):
    client, _ = setup
    _login(client, "anderson", "ann-pw")
    r = client.get("/classes")
    assert "MATH101" in r.text
    assert "ART101" not in r.text
    assert "Add Course" not in r.text


def test_student_sees_only_their_enrolled_sections(setup):
    client, _ = setup
    _login(client, "jane", "jane-pw")
    r = client.get("/classes")
    assert "MATH101" in r.text
    assert "ART101" not in r.text


# -- who can change it -----------------------------------------------------

def test_non_admin_cannot_add_a_course(setup):
    client, Session_ = setup
    _login(client, "anderson", "ann-pw")
    r = client.post("/classes/courses", data={"code": "SCI101", "name": "Biology"})
    assert r.status_code == 403
    with Session_() as s:
        assert s.query(Course).filter(Course.code == "SCI101").first() is None


def test_non_admin_cannot_assign_a_teacher(setup):
    client, Session_ = setup
    _login(client, "jane", "jane-pw")
    art = _section_id(Session_, "ART101", "Wed")
    r = client.post(f"/classes/{art}/teacher", data={"teacher_id": "1"})
    assert r.status_code == 403


# -- adding courses and sections (T1-021) -----------------------------------

def test_admin_can_add_a_course_and_section(setup):
    client, Session_ = setup
    _login(client, "admin", "admin-pw")

    r = client.post("/classes/courses", data={"code": "sci101", "name": "Biology"})
    assert r.status_code == 303
    with Session_() as s:
        course = s.query(Course).filter(Course.code == "SCI101").one()  # stored uppercase
        course_id = course.id

    r = client.post("/classes/sections", data={
        "course_id": str(course_id), "room": "d404", "day_of_week": "Thu",
        "start_time": "10:00", "end_time": "10:50", "capacity": "20",
    })
    assert r.status_code == 303
    with Session_() as s:
        section = s.query(Section).filter(Section.course_id == course_id).one()
        assert section.room == "D404"
        assert section.teacher_id is None  # assigned separately (T1-023)

    page = client.get("/classes")
    assert "SCI101" in page.text and "Unassigned" in page.text


def test_course_form_shows_errors(setup):
    client, _ = setup
    _login(client, "admin", "admin-pw")
    r = client.post("/classes/courses", data={"code": "MATH101", "name": ""})
    assert r.status_code == 400
    assert "already exists" in r.text
    assert "Course name is required." in r.text


def test_section_end_time_must_be_after_start(setup):
    client, Session_ = setup
    _login(client, "admin", "admin-pw")
    with Session_() as s:
        math_id = s.query(Course).filter(Course.code == "MATH101").one().id
    r = client.post("/classes/sections", data={
        "course_id": str(math_id), "room": "A102", "day_of_week": "Fri",
        "start_time": "11:00", "end_time": "10:00",
    })
    assert r.status_code == 400
    assert "End time must be after the start time." in r.text


def test_capacity_cannot_exceed_20(setup):
    client, Session_ = setup
    _login(client, "admin", "admin-pw")
    with Session_() as s:
        math_id = s.query(Course).filter(Course.code == "MATH101").one().id
    r = client.post("/classes/sections", data={
        "course_id": str(math_id), "room": "A102", "day_of_week": "Fri",
        "start_time": "10:00", "end_time": "10:50", "capacity": "25",
    })
    assert r.status_code == 400
    assert "Capacity must be between 1 and 20." in r.text


def test_room_cannot_be_double_booked(setup):
    client, Session_ = setup
    _login(client, "admin", "admin-pw")
    with Session_() as s:
        art_id = s.query(Course).filter(Course.code == "ART101").one().id
    # A101 already has MATH101 Mon 9:00-9:50, so 9:30 overlaps it
    r = client.post("/classes/sections", data={
        "course_id": str(art_id), "room": "A101", "day_of_week": "Mon",
        "start_time": "09:30", "end_time": "10:20",
    })
    assert r.status_code == 400
    assert "already booked" in r.text


# -- teacher assignment through the page (T1-023) ---------------------------

def test_admin_can_assign_and_remove_a_teacher(setup):
    client, Session_ = setup
    _login(client, "admin", "admin-pw")
    art = _section_id(Session_, "ART101", "Wed")
    with Session_() as s:
        bob = s.query(User).filter(User.username == "brown").one().id

    r = client.post(f"/classes/{art}/teacher", data={"teacher_id": str(bob)})
    assert r.status_code == 303
    with Session_() as s:
        assert s.get(Section, art).teacher_id == bob

    r = client.post(f"/classes/{art}/teacher", data={"teacher_id": ""})
    assert r.status_code == 303
    with Session_() as s:
        assert s.get(Section, art).teacher_id is None


def test_overlapping_assignment_shows_an_error(setup):
    client, Session_ = setup
    _login(client, "admin", "admin-pw")
    with Session_() as s:
        art_id = s.query(Course).filter(Course.code == "ART101").one().id
        ann = s.query(User).filter(User.username == "anderson").one().id
    client.post("/classes/sections", data={
        "course_id": str(art_id), "room": "C303", "day_of_week": "Mon",
        "start_time": "09:15", "end_time": "10:05",
    })
    art_mon = _section_id(Session_, "ART101", "Mon")

    # Ann already teaches MATH101 Mon 9:00-9:50
    r = client.post(f"/classes/{art_mon}/teacher", data={"teacher_id": str(ann)})
    assert r.status_code == 400
    assert "overlaps" in r.text
    with Session_() as s:
        assert s.get(Section, art_mon).teacher_id is None
