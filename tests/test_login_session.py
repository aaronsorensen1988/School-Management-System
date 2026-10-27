"""Login against the users table, and the session it creates. UMA-002.

Login used to check one hardcoded admin and set nothing, so no page knew
who you were. These check that it reads the real table now and that the
student routes actually refuse people.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import Role, User
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

    # StaticPool so every connection shares one in-memory database. Without
    # it TestClient runs the app on another thread, gets its own connection
    # and therefore its own empty database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session(engine) as s:
        admin_role = Role(name="Admin")
        student_role = Role(name="Student")
        s.add_all([admin_role, student_role])
        s.flush()

        s.add(User(username="admin", password_hash=hash_password("correct-horse"),
                   first_name="System", last_name="Admin", email="admin@school.edu",
                   role_id=admin_role.id))
        jane = User(username="jane", password_hash=hash_password("jane-pw"),
                    first_name="Jane", last_name="Smith", email="jane@school.edu",
                    role_id=student_role.id)
        s.add(jane)
        s.flush()

        s.add_all([
            Student(user_id=jane.id, student_number="S-001", first_name="Jane",
                    last_name="Smith", grade_level=10, date_of_birth="2010-04-02",
                    home_address="12 Oak St", guardian_name="Mary Smith",
                    guardian_email="mary@example.com"),
            Student(student_number="S-002", first_name="Bob", last_name="Jones",
                    grade_level=11, date_of_birth="2009-08-19", home_address="34 Elm St",
                    guardian_name="Paul Jones", guardian_email="paul@example.com"),
        ])
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


# -- login ---------------------------------------------------------------

def test_real_user_can_log_in(client):
    r = client.post("/login", data={"username": "admin", "password": "correct-horse"})
    assert r.status_code == 302
    assert r.headers["location"] == "/dashboard"


def test_old_hardcoded_password_no_longer_works(client):
    # the account used to be baked into api.py with this password
    r = client.post("/login", data={"username": "admin", "password": "password123"})
    assert r.status_code == 401


def test_unknown_user_is_rejected(client):
    assert client.post("/login", data={"username": "nope", "password": "x"}).status_code == 401


def test_wrong_and_unknown_look_the_same(client):
    """Don't leak which usernames exist."""
    wrong = client.post("/login", data={"username": "admin", "password": "bad"})
    unknown = client.post("/login", data={"username": "ghost", "password": "bad"})
    assert wrong.status_code == unknown.status_code == 401
    assert "Invalid username or password" in wrong.text
    assert "Invalid username or password" in unknown.text


def test_logout_clears_the_session(client):
    client.post("/login", data={"username": "admin", "password": "correct-horse"})
    assert client.get("/students").status_code == 200
    client.get("/logout")
    assert client.get("/students").headers["location"] == "/login"


# -- the hole this was opened to close -----------------------------------

def test_students_page_needs_a_login(client):
    r = client.get("/students")
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_student_profile_needs_a_login(client):
    assert client.get("/ui/student/1").headers["location"] == "/login"


def test_anonymous_cant_get_a_home_address(client):
    """The actual leak. Used to return every student's address to anyone."""
    body = client.get("/students").text
    assert "12 Oak St" not in body
    assert "mary@example.com" not in body


# -- role enforcement through the web layer ------------------------------

def test_admin_sees_all_students(client):
    client.post("/login", data={"username": "admin", "password": "correct-horse"})
    body = client.get("/students").text
    assert "Jane" in body and "Bob" in body


def test_student_only_sees_themselves(client):
    client.post("/login", data={"username": "jane", "password": "jane-pw"})
    body = client.get("/students").text
    assert "Jane" in body
    assert "Bob" not in body


def test_student_cant_open_another_students_profile(client):
    client.post("/login", data={"username": "jane", "password": "jane-pw"})
    # S-002 is Bob, id 2
    assert client.get("/ui/student/2").status_code == 403


def test_student_cant_reach_the_add_student_form(client):
    client.post("/login", data={"username": "jane", "password": "jane-pw"})
    assert client.get("/students/new").status_code == 403


def test_student_cant_post_a_new_student(client):
    client.post("/login", data={"username": "jane", "password": "jane-pw"})
    r = client.post("/students/new", data={"student_number": "S-999"})
    assert r.status_code == 403


def test_admin_can_reach_the_add_student_form(client):
    client.post("/login", data={"username": "admin", "password": "correct-horse"})
    assert client.get("/students/new").status_code == 200


def test_missing_student_is_404_not_403(client):
    client.post("/login", data={"username": "admin", "password": "correct-horse"})
    assert client.get("/ui/student/9999").status_code == 404


# -- T2-037, the page actually has to say so -----------------------------

def test_a_refused_profile_says_it_was_refused(client):
    """The status code was already right. The page said "Student not found",
    which told a refused user the record doesn't exist and told us nothing
    when we looked at it."""
    client.post("/login", data={"username": "jane", "password": "jane-pw"})
    r = client.get("/ui/student/2")
    assert r.status_code == 403
    assert "Access denied" in r.text
    assert "do not have access" in r.text
    assert "Student not found" not in r.text


def test_a_missing_student_still_says_not_found(client):
    """The other half. Don't turn every 404 into a denial."""
    client.post("/login", data={"username": "admin", "password": "correct-horse"})
    r = client.get("/ui/student/9999")
    assert r.status_code == 404
    assert "Student not found" in r.text
    assert "Access denied" not in r.text
