""""Signed in as" bar on every page, and the home page redirect.

The bar reads the session, so it shows on pages from every router without
each route passing anything in. "/" sends signed-in users to the dashboard
and everyone else to the login page.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import Role, User
from security.keys import generate_key
from utils.security import hash_password

KEY = generate_key()


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
        roles = {n: Role(name=n) for n in ("Admin", "Teacher", "Student", "Parent")}
        s.add_all(roles.values())
        s.flush()
        s.add_all([
            User(username="admin", password_hash=hash_password("admin-pw"), first_name="System",
                 last_name="Admin", email="admin@school.edu", role_id=roles["Admin"].id),
            User(username="jane", password_hash=hash_password("jane-pw"), first_name="Jane",
                 last_name="Smith", email="jane@school.edu", role_id=roles["Student"].id),
        ])
        s.commit()

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


# -- home page redirect ---------------------------------------------------

def test_home_sends_visitors_to_login(client):
    r = client.get("/")
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_home_sends_signed_in_users_to_dashboard(client):
    _login(client, "jane", "jane-pw")
    r = client.get("/")
    assert r.status_code == 302
    assert r.headers["location"] == "/dashboard"


def test_home_after_logout_goes_to_login(client):
    _login(client, "jane", "jane-pw")
    client.get("/logout")
    assert client.get("/").headers["location"] == "/login"


def test_home_with_a_deleted_account_goes_to_login(client):
    _login(client, "jane", "jane-pw")
    with client.session_factory() as s:
        s.delete(s.query(User).filter_by(username="jane").one())
        s.commit()
    assert client.get("/").headers["location"] == "/login"


# -- signed-in bar ---------------------------------------------------------

def test_bar_shows_name_role_and_logout(client):
    _login(client, "admin", "admin-pw")
    page = client.get("/dashboard").text
    assert "Signed in as <strong>admin</strong> (Admin)" in page
    assert 'href="/logout"' in page


def test_bar_shows_on_pages_from_other_routers(client):
    _login(client, "jane", "jane-pw")
    client.get("/dashboard")
    for url in ("/classes", "/report-cards/1", "/emergency"):
        page = client.get(url).text
        assert "Signed in as <strong>jane</strong> (Student)" in page, url


def test_no_bar_on_login_page(client):
    assert "Signed in as" not in client.get("/login").text


def test_bar_gone_after_logout(client):
    _login(client, "admin", "admin-pw")
    client.get("/dashboard")
    client.get("/logout")
    assert "Signed in as" not in client.get("/login").text


def test_role_label_follows_the_database(client):
    """The label is display only; if a role changes, the next page shows it."""
    _login(client, "jane", "jane-pw")
    assert "(Student)" in client.get("/dashboard").text
    with client.session_factory() as s:
        jane = s.query(User).filter_by(username="jane").one()
        jane.role_id = s.query(Role).filter_by(name="Teacher").one().id
        s.commit()
    page = client.get("/dashboard").text
    assert "(Teacher)" in page and "(Student)" not in page
