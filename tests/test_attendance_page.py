"""Attendance page through the real app. SIEM-005 / T2-001, T2-004.

Who can open it, who can save, and that validation problems show up on the
page instead of as a database error. Dates are worked out from today so
these keep passing no matter what day they run.
"""

from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.attendance import Attendance
from database.database import Base, get_db
from database.models import Role, User
from database.scheduling import Course, Enrollment, Section
from security.keys import generate_key
from utils.security import hash_password

KEY = generate_key()


def last_monday():
    today = date.today()
    return today - timedelta(days=today.weekday())


def next_monday():
    return last_monday() + timedelta(days=7)


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
        admin_role, teacher_role, student_role = Role(name="Admin"), Role(name="Teacher"), Role(name="Student")
        s.add_all([admin_role, teacher_role, student_role])
        s.flush()

        def user(username, pw, first, last, role):
            return User(username=username, password_hash=hash_password(pw), first_name=first,
                        last_name=last, email=f"{username}@school.edu", role_id=role.id)

        s.add_all([
            user("admin", "admin-pw", "System", "Admin", admin_role),
            user("anderson", "ann-pw", "Ann", "Anderson", teacher_role),
            user("brown", "bob-pw", "Bob", "Brown", teacher_role),
            user("jane", "jane-pw", "Jane", "Smith", student_role),
            user("john", "john-pw", "John", "Jones", student_role),
        ])
        s.flush()
        ann = s.query(User).filter_by(username="anderson").one()

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
        for name in ("jane", "john"):
            s.add(Enrollment(section_id=math_mon.id, student_id=s.query(User).filter_by(username=name).one().id))
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


def _ids(Session_):
    with Session_() as s:
        section = s.query(Section).join(Course).filter(Course.code == "MATH101").one()
        jane = s.query(User).filter_by(username="jane").one()
        john = s.query(User).filter_by(username="john").one()
        return section.id, jane.id, john.id


def _form(on_date, jane, john, jane_status="present", john_status="present"):
    return {"on_date": on_date.isoformat(),
            f"status_{jane}": jane_status, f"note_{jane}": "",
            f"status_{john}": john_status, f"note_{john}": ""}


# -- who can see it --------------------------------------------------------

def test_must_be_logged_in(setup):
    client, _ = setup
    r = client.get("/attendance")
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_students_cannot_use_the_page(setup):
    client, _ = setup
    _login(client, "jane", "jane-pw")
    assert client.get("/attendance").status_code == 403


def test_teacher_sees_only_their_classes(setup):
    client, _ = setup
    _login(client, "anderson", "ann-pw")
    r = client.get("/attendance")
    assert r.status_code == 200
    assert "MATH101" in r.text
    assert "ART101" not in r.text


def test_teacher_sees_the_roster(setup):
    client, Session_ = setup
    section_id, _, _ = _ids(Session_)
    _login(client, "anderson", "ann-pw")
    r = client.get(f"/attendance/{section_id}")
    assert r.status_code == 200
    assert "Jane Smith" in r.text and "John Jones" in r.text
    assert "Save Attendance" in r.text
    assert last_monday().isoformat() in r.text


def test_other_teacher_is_blocked(setup):
    client, Session_ = setup
    section_id, _, _ = _ids(Session_)
    _login(client, "brown", "bob-pw")
    r = client.get(f"/attendance/{section_id}")
    assert r.status_code == 403
    assert "classes you teach" in r.text


def test_admin_can_view_but_not_save(setup):
    client, Session_ = setup
    section_id, jane, john = _ids(Session_)
    _login(client, "admin", "admin-pw")
    r = client.get(f"/attendance/{section_id}")
    assert r.status_code == 200
    assert "View only" in r.text
    assert "Save Attendance" not in r.text

    r = client.post(f"/attendance/{section_id}", data=_form(last_monday(), jane, john))
    assert r.status_code == 403
    with Session_() as s:
        assert s.query(Attendance).count() == 0


# -- saving ------------------------------------------------------------------

def test_teacher_saves_attendance(setup):
    client, Session_ = setup
    section_id, jane, john = _ids(Session_)
    _login(client, "anderson", "ann-pw")
    r = client.post(f"/attendance/{section_id}", data=_form(last_monday(), jane, john, john_status="absent"))
    assert r.status_code == 303
    assert "notice=saved" in r.headers["location"]
    with Session_() as s:
        rows = {a.student_id: a.status for a in s.query(Attendance).all()}
    assert rows == {jane: "present", john: "absent"}

    r = client.get(r.headers["location"])
    assert "Attendance saved." in r.text


def test_saving_twice_updates_instead_of_duplicating(setup):
    client, Session_ = setup
    section_id, jane, john = _ids(Session_)
    _login(client, "anderson", "ann-pw")
    client.post(f"/attendance/{section_id}", data=_form(last_monday(), jane, john))
    r = client.post(f"/attendance/{section_id}", data=_form(last_monday(), jane, john, jane_status="tardy"))
    assert r.status_code == 303
    with Session_() as s:
        rows = s.query(Attendance).all()
        assert len(rows) == 2
        assert {a.student_id: a.status for a in rows}[jane] == "tardy"


# -- validation shows on the page (T2-004) -------------------------------------

def test_future_date_is_refused(setup):
    client, Session_ = setup
    section_id, jane, john = _ids(Session_)
    _login(client, "anderson", "ann-pw")
    r = client.post(f"/attendance/{section_id}", data=_form(next_monday(), jane, john))
    assert r.status_code == 400
    assert "future date" in r.text
    assert "Nothing was saved" in r.text
    with Session_() as s:
        assert s.query(Attendance).count() == 0


def test_wrong_day_of_week_is_refused(setup):
    client, Session_ = setup
    section_id, jane, john = _ids(Session_)
    _login(client, "anderson", "ann-pw")
    a_tuesday = last_monday() - timedelta(days=6)
    r = client.post(f"/attendance/{section_id}", data=_form(a_tuesday, jane, john))
    assert r.status_code == 400
    assert "meets on Mon" in r.text


def test_bad_status_is_refused(setup):
    client, Session_ = setup
    section_id, jane, john = _ids(Session_)
    _login(client, "anderson", "ann-pw")
    r = client.post(f"/attendance/{section_id}", data=_form(last_monday(), jane, john, john_status="sick"))
    assert r.status_code == 400
    assert "Choose present, absent, tardy, or excused." in r.text
    with Session_() as s:
        assert s.query(Attendance).count() == 0


def test_bad_date_text_is_refused(setup):
    client, Session_ = setup
    section_id, jane, john = _ids(Session_)
    _login(client, "anderson", "ann-pw")
    data = _form(last_monday(), jane, john)
    data["on_date"] = "not-a-date"
    r = client.post(f"/attendance/{section_id}", data=data)
    assert r.status_code == 400
    assert "YYYY-MM-DD" in r.text


def test_classes_page_links_to_attendance_for_teachers(setup):
    client, _ = setup
    _login(client, "anderson", "ann-pw")
    r = client.get("/classes")
    assert "/attendance" in r.text
