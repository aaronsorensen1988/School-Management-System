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
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    monkeypatch.setenv("SMS_SESSION_SECRET", "test-secret")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session(engine) as s:
        # Create both Admin and Teacher roles
        admin_role = Role(name="Admin")
        teacher_role = Role(name="Teacher")
        s.add_all([admin_role, teacher_role])
        s.flush()

        # Create our Admin tester and a sample Teacher
        admin = User(username="test_admin", password_hash=hash_password("pw"),
                      first_name="Test", last_name="Admin", email="admin@school.edu",
                      role_id=admin_role.id)
        teacher = User(username="mr_feeny", password_hash=hash_password("pw"),
                      first_name="George", last_name="Feeny", email="feeny@school.edu",
                      role_id=teacher_role.id)
        s.add_all([admin, teacher])
        s.commit()

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
    client.post("/login", data={"username": "test_admin", "password": "pw"})
    r = client.get("/teachers")
    assert r.status_code == 200

def test_anonymous_user_cannot_access_teachers_page(client):
    r = client.get("/teachers")
    assert r.status_code == 302
    assert r.headers["location"] == "/login"

def test_teacher_data_renders_on_page(client):
    """Verify that a database-backed teacher actually appears in the HTML."""
    client.post("/login", data={"username": "test_admin", "password": "pw"})
    r = client.get("/teachers")
    
    # Check that the sample teacher's details from the DB are present in the response
    assert "George" in r.text
    assert "Feeny" in r.text