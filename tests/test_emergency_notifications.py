"""Emergency notifications. CNS-012 / T2-030 (UI), T2-031 (broadcast).

The broadcast logic on its own, then the page through the real app. Every
table this file needs is imported here so it runs on its own.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from business_logic.siem import emergency_service
from business_logic.siem.emergency_service import EmergencyAccessError
from database import announcements, attendance, audit, grades, parents, scheduling, students  # noqa: F401
from database.database import Base, get_db
from database.emergency import EmergencyNotification, EmergencyReceipt
from database.models import Role, User
from security.keys import generate_key
from utils.security import hash_password

KEY = generate_key()

USERS = [
    ("admin", "admin-pw", "Admin"),
    ("anderson", "ann-pw", "Teacher"),
    ("jane", "jane-pw", "Student"),
    ("john", "john-pw", "Student"),
    ("pat", "pat-pw", "Parent"),
]


class _Actor:
    def __init__(self, user_id, role):
        self.user_id, self.role = user_id, role


def _seed(s):
    roles = {n: Role(name=n) for n in ("Admin", "Teacher", "Student", "Parent")}
    s.add_all(roles.values())
    s.flush()
    for username, pw, role in USERS:
        s.add(User(username=username, password_hash=hash_password(pw), first_name=username.title(),
                   last_name="Test", email=f"{username}@school.edu", role_id=roles[role].id))
    s.commit()


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as s:
        _seed(s)
        yield s
    keys_module._cached = None


def _actor(db, username):
    u = db.query(User).filter_by(username=username).one()
    role = db.query(Role).filter_by(id=u.role_id).one().name
    return _Actor(u.id, role)


GOOD = {"title": "Early dismissal", "message": "School closes at noon today.", "audience": "everyone"}


# -- broadcast logic (T2-031) -------------------------------------------------

def test_admin_sends_to_everyone(db):
    alert, errors = emergency_service.send_emergency(db, _actor(db, "admin"), GOOD)
    assert errors == {}
    assert alert.sent_by == _actor(db, "admin").user_id
    assert db.query(EmergencyReceipt).count() == len(USERS)


@pytest.mark.parametrize("audience,expected", [
    ("staff", {"admin", "anderson"}),
    ("students", {"admin", "jane", "john"}),
    ("parents", {"admin", "pat"}),
])
def test_audience_picks_the_right_people(db, audience, expected):
    alert, _ = emergency_service.send_emergency(db, _actor(db, "admin"), {**GOOD, "audience": audience})
    reached = {r.user.username for r in alert.receipts}
    assert reached == expected


@pytest.mark.parametrize("username", ["anderson", "jane", "pat"])
def test_only_admins_can_send(db, username):
    with pytest.raises(EmergencyAccessError):
        emergency_service.send_emergency(db, _actor(db, username), GOOD)
    assert db.query(EmergencyNotification).count() == 0


def test_bad_alert_saves_nothing(db):
    alert, errors = emergency_service.send_emergency(
        db, _actor(db, "admin"), {"title": " ", "message": "", "audience": "aliens"})
    assert alert is None
    assert set(errors) == {"title", "message", "audience"}
    assert db.query(EmergencyNotification).count() == 0
    assert db.query(EmergencyReceipt).count() == 0


def test_length_limits(db):
    _, errors = emergency_service.send_emergency(db, _actor(db, "admin"), {
        **GOOD, "title": "x" * (emergency_service.TITLE_MAX + 1),
        "message": "y" * (emergency_service.MESSAGE_MAX + 1)})
    assert "at most" in errors["title"] and "at most" in errors["message"]


def test_inbox_unread_and_mark_read(db):
    emergency_service.send_emergency(db, _actor(db, "admin"), GOOD)
    jane = _actor(db, "jane")
    assert emergency_service.unread_count(db, jane.user_id) == 1
    alert, receipt = emergency_service.inbox(db, jane.user_id)[0]
    assert alert.title == "Early dismissal" and receipt.read_at is None

    assert emergency_service.mark_read(db, jane.user_id, alert.id) is True
    assert emergency_service.unread_count(db, jane.user_id) == 0
    first_read = db.query(EmergencyReceipt).filter_by(user_id=jane.user_id).one().read_at
    emergency_service.mark_read(db, jane.user_id, alert.id)          # reading twice keeps the first time
    assert db.query(EmergencyReceipt).filter_by(user_id=jane.user_id).one().read_at == first_read


def test_cannot_mark_someone_elses_alert(db):
    alert, _ = emergency_service.send_emergency(db, _actor(db, "admin"), {**GOOD, "audience": "staff"})
    assert emergency_service.mark_read(db, _actor(db, "jane").user_id, alert.id) is False


def test_sent_history_counts_reads(db):
    alert, _ = emergency_service.send_emergency(db, _actor(db, "admin"), {**GOOD, "audience": "students"})
    emergency_service.mark_read(db, _actor(db, "jane").user_id, alert.id)
    row = emergency_service.sent_history(db)[0]
    assert (row["read"], row["total"]) == (1, 3)


# -- the page (T2-030) ----------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    monkeypatch.setenv("SMS_SESSION_SECRET", "test-secret-not-a-real-one")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session(engine) as s:
        _seed(s)

    import api

    def override_get_db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    api.app.dependency_overrides[get_db] = override_get_db
    c = TestClient(api.app, follow_redirects=False)
    c.session_factory = TestSession
    yield c
    api.app.dependency_overrides.clear()
    keys_module._cached = None


def _login(client, username, password):
    assert client.post("/login", data={"username": username, "password": password}).status_code == 302


def test_page_needs_login(client):
    r = client.get("/emergency")
    assert r.status_code == 302 and r.headers["location"] == "/login"


def test_admin_sends_from_the_page_and_sees_history(client):
    _login(client, "admin", "admin-pw")
    assert "Send an Emergency Alert" in client.get("/emergency").text
    r = client.post("/emergency", data=GOOD)
    assert r.status_code == 303 and r.headers["location"] == "/emergency?notice=sent"
    page = client.get(r.headers["location"]).text
    assert "Emergency alert sent." in page
    assert "Early dismissal" in page
    assert f"0 of {len(USERS)}" in page


def test_page_shows_form_errors(client):
    _login(client, "admin", "admin-pw")
    r = client.post("/emergency", data={"title": "", "message": "Hello", "audience": ""})
    assert r.status_code == 400
    assert "Title is required." in r.text
    assert "Choose who should receive this alert." in r.text
    assert "Hello" in r.text


def test_non_admin_cannot_send_or_see_the_form(client):
    _login(client, "anderson", "ann-pw")
    assert "Send an Emergency Alert" not in client.get("/emergency").text
    r = client.post("/emergency", data=GOOD)
    assert r.status_code == 403
    with client.session_factory() as s:
        assert s.query(EmergencyNotification).count() == 0


def test_student_sees_banner_reads_alert_and_banner_goes_away(client):
    _login(client, "admin", "admin-pw")
    client.post("/emergency", data={**GOOD, "audience": "students"})
    client.get("/logout")

    _login(client, "jane", "jane-pw")
    assert "1 unread emergency alert." in client.get("/dashboard").text
    page = client.get("/emergency").text
    assert "School closes at noon today." in page and "Mark as read" in page

    with client.session_factory() as s:
        alert_id = s.query(EmergencyNotification).one().id
    assert client.post(f"/emergency/{alert_id}/read").status_code == 303
    assert "unread emergency alert" not in client.get("/dashboard").text
    assert "Read" in client.get("/emergency").text


def test_parent_does_not_get_a_students_only_alert(client):
    _login(client, "admin", "admin-pw")
    client.post("/emergency", data={**GOOD, "audience": "students"})
    client.get("/logout")
    _login(client, "pat", "pat-pw")
    assert "No emergency alerts." in client.get("/emergency").text
    assert "unread emergency alert" not in client.get("/dashboard").text
