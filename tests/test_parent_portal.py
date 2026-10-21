import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import Role, User
from database.students import Student
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

    # Insert a fake "Parent" role and user into the temporary database
    with Session(engine) as s:
        parent_role = Role(name="Parent")
        student_role = Role(name="Student")
        s.add_all([parent_role, student_role])
        s.flush()

        parent = User(username="test_parent", password_hash=hash_password("pw"),
                      first_name="Test", last_name="Parent", email="p@school.edu",
                      role_id=parent_role.id)
        
        student = User(username="test_student", password_hash=hash_password("pw"),
                      first_name="Test", last_name="Student", email="s@school.edu",
                      role_id=student_role.id)
        s.add_all([parent, student])
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

def test_parent_can_access_portal(client):
    """Verify that a logged-in parent can see the portal and privacy notice."""
    client.post("/login", data={"username": "test_parent", "password": "pw"})
    r = client.get("/parent/portal")
    assert r.status_code == 200
    assert "Parent Portal: My Children" in r.text
    assert "Privacy Notice" in r.text

def test_student_cannot_access_parent_portal(client):
    """Verify that a student is kicked back to the dashboard if they try to access the portal."""
    client.post("/login", data={"username": "test_student", "password": "pw"})
    r = client.get("/parent/portal")
    assert r.status_code == 302
    assert r.headers["location"] == "/dashboard"

def test_anonymous_user_is_redirected(client):
    """Verify that someone not logged in cannot access the portal."""
    r = client.get("/parent/portal")
    assert r.status_code == 302
    assert r.headers["location"] == "/login"