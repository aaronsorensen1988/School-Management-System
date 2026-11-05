"""Student profile page: hidden fields say so instead of printing "None".

The redact rule (student_repository.redact) blanks contact details for
anyone who isn't an admin or the student themselves. That part is right
and isn't changed here. What changed is the page: a parent used to see
"Date of birth: None" on their own child, which reads like missing data.
Now the page says "Hidden for privacy".
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import api  # imported first so every model's table is registered on Base
from database.database import Base, get_db
from database.models import Role, User
from database.parents import ParentStudent
from database.students import Student
from security.keys import generate_key
from utils.security import hash_password

KEY = generate_key()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SMS_ENCRYPTION_KEYS", f"k1:{KEY}")
    monkeypatch.setenv("SMS_SESSION_SECRET", "test-secret-not-a-real-one")
    from security import keys as keys_module
    keys_module.active_keyring(refresh=True)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session(engine) as s:
        admin_role = Role(name="Admin")
        parent_role = Role(name="Parent")
        s.add_all([admin_role, parent_role])
        s.flush()

        s.add(User(username="admin", password_hash=hash_password("admin-pw"),
                   first_name="System", last_name="Admin", email="admin@school.edu",
                   role_id=admin_role.id))
        priya = User(username="priya", password_hash=hash_password("priya-pw"),
                     first_name="Priya", last_name="Patel", email="priya@example.com",
                     role_id=parent_role.id)
        s.add(priya)
        s.flush()

        zoe = Student(student_number="S-100", first_name="Zoe", last_name="Patel",
                      grade_level=10, date_of_birth="2010-01-09",
                      home_address="912 Willow Drive", guardian_name="Priya Patel",
                      guardian_email="priya@example.com")
        s.add(zoe)
        s.flush()
        s.add(ParentStudent(parent_user_id=priya.id, student_id=zoe.id))
        s.commit()
        zoe_id = zoe.id

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    api.app.dependency_overrides[get_db] = override_get_db
    c = TestClient(api.app, follow_redirects=False)
    c.zoe_id = zoe_id
    yield c
    api.app.dependency_overrides.clear()
    keys_module._cached = None


def test_parent_sees_hidden_for_privacy_not_none(client):
    client.post("/login", data={"username": "priya", "password": "priya-pw"})
    r = client.get(f"/ui/student/{client.zoe_id}")

    assert r.status_code == 200
    assert "Zoe Patel" in r.text
    assert r.text.count("Hidden for privacy") == 4
    assert "None" not in r.text


def test_parent_still_does_not_get_the_contact_details(client):
    """The wording changed, the rule didn't."""
    client.post("/login", data={"username": "priya", "password": "priya-pw"})
    body = client.get(f"/ui/student/{client.zoe_id}").text

    assert "912 Willow Drive" not in body
    assert "2010-01-09" not in body
    assert "priya@example.com" not in body


def test_admin_sees_the_real_values(client):
    client.post("/login", data={"username": "admin", "password": "admin-pw"})
    body = client.get(f"/ui/student/{client.zoe_id}").text

    assert "912 Willow Drive" in body
    assert "2010-01-09" in body
    assert "Hidden for privacy" not in body
