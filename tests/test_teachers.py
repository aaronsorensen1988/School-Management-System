import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import Role, User
from database.audit import AccessLog
from security.keys import generate_key
from utils.security import hash_password

KEY = generate_key()

@pytest.fixture
def client(monkeypatch):
    # Set up the secure environment variables for testing
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    monkeypatch.setenv("SMS_SESSION_SECRET", "test-secret")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    # Spin up a temporary, isolated SQLite database just for this test
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    # Insert fake roles and users into the temporary database
    with Session(engine) as s:
        admin_role = Role(name="Admin")
        s.add(admin_role)
        s.flush()

        admin = User(username="test_admin", password_hash=hash_password("pw"),
                      first_name="Test", last_name="Admin", email="admin@school.edu",
                      role_id=admin_role.id)
        s.add(admin)
        s.commit()

    # Tell the FastAPI app to use our temporary database
    import api
    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    api.app.dependency_overrides[get_db] = override_get_db
    yield TestClient(api.app, follow_redirects=False)
    api.app.dependency_overrides.clear()
    keys_module._cached = None


# --- THE ACTUAL TESTS ---

def test_admin_can_access_teachers_page(client):
    """Verify that authorized staff can load the wired-up teachers page."""
    client.post("/login", data={"username": "test_admin", "password": "pw"})
    r = client.get("/teachers")
    assert r.status_code == 200

def test_anonymous_user_cannot_access_teachers_page(client):
    """Verify that someone not logged in gets kicked back to the login screen."""
    r = client.get("/teachers")
    assert r.status_code == 302
    assert r.headers["location"] == "/login"