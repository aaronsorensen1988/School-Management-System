"""Messaging pages and the audit rows they write. CNS-011 / T2-025, T2-027.

MessagingService already has its own tests for who may talk to whom, so
these don't re-check the rules. They check that the pages hand the request
over properly, that a refusal comes back as a 403 instead of an empty page,
and that both outcomes land in the access log.

One file for two tasks because the fixture is most of the work. Pages are in
the first section, audit rows in the second.
"""

import re
from datetime import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.audit import ALLOWED, CREATE, DENIED, LIST, VIEW, AccessLog
from database.database import Base, get_db
from database.messages import Message
from database.models import Role, User
from database.parents import ParentStudent
from database.scheduling import Course, Enrollment, Section
from database.students import Student
from security.keys import generate_key
from utils.security import hash_password

KEY = generate_key()

PASSWORDS = {
    "ann": "ann-pw",
    "bob": "bob-pw",
    "pat": "pat-pw",
    "quinn": "quinn-pw",
    "admin": "admin-pw",
}


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

    ids = {}

    with Session(engine) as s:
        roles = {n: Role(name=n) for n in ("Admin", "Teacher", "Student", "Parent")}
        s.add_all(roles.values())
        s.flush()

        def user(username, first, last, role):
            return User(
                username=username,
                password_hash=hash_password(PASSWORDS[username]),
                first_name=first,
                last_name=last,
                email=f"{username}@school.edu",
                role_id=roles[role].id,
            )

        # Two separate classrooms that never touch. Ann teaches Jane, whose
        # parent is Pat. Bob teaches Theo, whose parent is Quinn. Everything
        # that should be refused is somebody reaching across that line.
        #
        # Both halves have to be fully populated. A parent with no student
        # at all would drop out of the contact lists for the wrong reason
        # and the refusal tests would pass without testing anything.
        ann = user("ann", "Ann", "Anderson", "Teacher")
        bob = user("bob", "Bob", "Brown", "Teacher")
        pat = user("pat", "Pat", "Smith", "Parent")
        quinn = user("quinn", "Quinn", "Quill", "Parent")
        admin = user("admin", "System", "Admin", "Admin")

        def student_login(username, first, last):
            return User(
                username=username, password_hash=hash_password("x"),
                first_name=first, last_name=last, email=f"{username}@school.edu",
                role_id=roles["Student"].id,
            )

        jane_login = student_login("jane", "Jane", "Smith")
        theo_login = student_login("theo", "Theo", "Quill")
        s.add_all([ann, bob, pat, quinn, admin, jane_login, theo_login])
        s.flush()

        def student(login_user, number, first, last, guardian, guardian_email):
            return Student(
                user_id=login_user.id, student_number=number, first_name=first,
                last_name=last, grade_level=5, date_of_birth="2015-01-01",
                home_address="1 Main St", guardian_name=guardian,
                guardian_email=guardian_email,
            )

        jane = student(jane_login, "S-001", "Jane", "Smith", "Pat Smith", "pat@school.edu")
        theo = student(theo_login, "S-002", "Theo", "Quill", "Quinn Quill", "quinn@school.edu")
        s.add_all([jane, theo])
        s.flush()

        s.add_all([
            ParentStudent(parent_user_id=pat.id, student_id=jane.id),
            ParentStudent(parent_user_id=quinn.id, student_id=theo.id),
        ])

        math = Course(code="MATH101", name="Math")
        art = Course(code="ART101", name="Art")
        s.add_all([math, art])
        s.flush()

        ann_section = Section(
            course_id=math.id, teacher_id=ann.id, room="A101",
            day_of_week="Mon", start_time=time(9, 0), end_time=time(9, 50),
        )
        bob_section = Section(
            course_id=art.id, teacher_id=bob.id, room="B202",
            day_of_week="Tue", start_time=time(10, 0), end_time=time(10, 50),
        )
        s.add_all([ann_section, bob_section])
        s.flush()
        s.add_all([
            Enrollment(section_id=ann_section.id, student_id=jane_login.id),
            Enrollment(section_id=bob_section.id, student_id=theo_login.id),
        ])
        s.commit()

        ids.update(
            ann=ann.id, bob=bob.id, pat=pat.id, quinn=quinn.id,
            admin=admin.id, jane=jane.id, theo=theo.id,
        )

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
    c.ids = ids
    yield c
    api.app.dependency_overrides.clear()
    keys_module._cached = None


def login(client, username):
    return client.post(
        "/login", data={"username": username, "password": PASSWORDS[username]}
    )


def logs(client, **where):
    with client.session_factory() as d:
        q = d.query(AccessLog)
        for k, v in where.items():
            q = q.filter(getattr(AccessLog, k) == v)
        return q.order_by(AccessLog.id).all()


def send(client, other_id, student_id, body):
    return client.post(
        f"/messages/{other_id}/{student_id}", data={"body": body}
    )


# -- the pages -----------------------------------------------------------

def test_messages_needs_a_login(client):
    r = client.get("/messages")
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_a_thread_needs_a_login(client):
    r = client.get(f"/messages/{1}/{1}")
    assert r.headers["location"] == "/login"


def test_an_admin_cannot_open_the_inbox(client):
    """CNS-011 is a teacher and parent conversation. An admin reading it
    quietly is the thing the audit log is for."""
    login(client, "admin")
    assert client.get("/messages").status_code == 403


def test_a_teacher_sees_the_parent_they_can_write_to(client):
    login(client, "ann")
    body = client.get("/messages").text
    assert "Pat" in body
    assert "Jane" in body


def test_a_teacher_does_not_see_another_teachers_parent(client):
    """Quinn is a real parent with a real child, just not one Ann teaches.
    She has to be fully set up or this passes for the wrong reason."""
    login(client, "ann")
    body = client.get("/messages").text
    assert "Quinn" not in body
    assert "Theo" not in body


def test_each_teacher_sees_only_their_own_classroom(client):
    login(client, "bob")
    body = client.get("/messages").text
    assert "Quinn" in body
    assert "Pat" not in body


def test_a_parent_is_not_offered_a_conversation_to_start(client):
    """Sean caught this in review. The inbox used to list the child's
    teacher under "start a conversation", but send_message refuses a
    parent's first message, so the link was a 403 with extra steps."""
    login(client, "pat")
    body = client.get("/messages").text

    assert "Start a conversation" not in body
    assert "teachers start these conversations" in body.lower()


def test_a_parent_sees_the_teacher_once_the_teacher_writes(client):
    login(client, "ann")
    send(client, client.ids["pat"], client.ids["jane"], "Jane did well today.")
    client.get("/logout")

    login(client, "pat")
    body = client.get("/messages").text
    assert "Ann" in body
    assert "Bob" not in body


def test_a_parent_does_not_see_another_parents_thread(client):
    login(client, "bob")
    send(client, client.ids["quinn"], client.ids["theo"], "About Theo.")
    client.get("/logout")

    login(client, "pat")
    body = client.get("/messages").text
    assert "Quinn" not in body
    assert "Theo" not in body


def test_nothing_the_inbox_offers_ends_in_a_refusal(client):
    """The general form of Sean's bug. Whatever the page links to has to be
    something the service will actually allow. Walk every link the inbox
    renders, for every role, and make sure none of them come back 403.

    quinn is the case that matters most. She's a parent nobody has written
    to yet, which is exactly the state where the page used to offer a link
    that could only fail.
    """
    login(client, "ann")
    send(client, client.ids["pat"], client.ids["jane"], "Jane did well today.")
    client.get("/logout")

    # Parents first on purpose. The check below posts a message, and a
    # teacher's post would give the parent a reply right to test with,
    # hiding the exact case this is here to catch. Teachers may always
    # send, so going after the parents can't flatter them.
    checked = 0
    for who in ("quinn", "pat", "ann", "bob"):
        login(client, who)
        body = client.get("/messages").text
        for link in set(re.findall(r'href="(/messages/\d+/\d+)"', body)):
            page = client.get(link)
            assert page.status_code == 200, f"{who} was offered {link}"
            checked += 1

            # A send box on the page is a promise the post will work.
            if "<textarea" in page.text:
                posted = client.post(link, data={"body": "checking the form works"})
                assert posted.status_code == 303, f"{who} got a dead form on {link}"
        client.get("/logout")

    # Guards the loop itself. If the page stopped rendering links entirely
    # every assertion above would pass without testing anything.
    assert checked >= 3


def test_both_pages_carry_the_privacy_notice(client):
    """T2-028. Same wording style as the parent portal notice, and it says
    out loud that messages are logged and permanent. A notice that leaves
    out the part people would object to isn't doing its job."""
    login(client, "ann")
    send(client, client.ids["pat"], client.ids["jane"], "Jane did well today.")

    inbox = client.get("/messages").text
    thread = client.get(f"/messages/{client.ids['pat']}/{client.ids['jane']}").text

    for page in (inbox, thread):
        assert "Privacy Notice" in page
        assert "FERPA" in page
        assert "records who sent each one" in page

    assert "cannot be edited or deleted" in thread


def test_a_parent_with_no_messages_gets_no_send_box(client):
    """Reaching the thread by typing the URL is allowed, the service lets
    anyone in the pair open it. Showing a form that can only 403 is not."""
    login(client, "quinn")
    page = client.get(f"/messages/{client.ids['bob']}/{client.ids['theo']}")

    assert page.status_code == 200
    assert "<textarea" not in page.text
    assert "once bob writes to you" in page.text.lower()


def test_a_teacher_can_start_a_conversation(client):
    login(client, "ann")
    r = send(client, client.ids["pat"], client.ids["jane"], "Jane did well today.")

    assert r.status_code == 303
    with client.session_factory() as d:
        assert d.query(Message).count() == 1


def test_a_teacher_cannot_write_about_a_student_they_do_not_teach(client):
    login(client, "bob")
    r = send(client, client.ids["pat"], client.ids["jane"], "hello")

    assert r.status_code == 403
    with client.session_factory() as d:
        assert d.query(Message).count() == 0


def test_a_parent_can_reply_once_the_teacher_has_written(client):
    login(client, "ann")
    send(client, client.ids["pat"], client.ids["jane"], "Jane did well today.")
    client.get("/logout")

    login(client, "pat")
    r = send(client, client.ids["ann"], client.ids["jane"], "Thanks for letting me know.")

    assert r.status_code == 303
    with client.session_factory() as d:
        assert d.query(Message).count() == 2


def test_a_parent_cannot_open_the_conversation_first(client):
    login(client, "pat")
    r = send(client, client.ids["ann"], client.ids["jane"], "hello")

    assert r.status_code == 403
    with client.session_factory() as d:
        assert d.query(Message).count() == 0


def test_an_empty_message_comes_back_to_the_conversation(client):
    """400 with the thread still on the page rather than an error page, so
    a long message that trips the length cap isn't just lost."""
    login(client, "ann")
    r = send(client, client.ids["pat"], client.ids["jane"], "   ")

    assert r.status_code == 400
    assert "required" in r.text.lower()
    with client.session_factory() as d:
        assert d.query(Message).count() == 0


def test_the_thread_shows_what_was_said(client):
    login(client, "ann")
    send(client, client.ids["pat"], client.ids["jane"], "Parent evening is Thursday.")

    r = client.get(f"/messages/{client.ids['pat']}/{client.ids['jane']}")
    assert r.status_code == 200
    assert "Parent evening is Thursday." in r.text


def test_a_stranger_cannot_read_the_thread(client):
    login(client, "ann")
    send(client, client.ids["pat"], client.ids["jane"], "Parent evening is Thursday.")
    client.get("/logout")

    login(client, "quinn")
    r = client.get(f"/messages/{client.ids['ann']}/{client.ids['jane']}")
    assert r.status_code == 403
    assert "Parent evening" not in r.text


# -- the audit rows ------------------------------------------------------

def test_sending_is_logged(client):
    login(client, "ann")
    send(client, client.ids["pat"], client.ids["jane"], "Jane did well today.")

    row = logs(client, action=CREATE, resource_type="message")[0]
    assert row.outcome == ALLOWED
    assert row.actor_role == "Teacher"
    assert row.actor_user_id == client.ids["ann"]
    assert str(client.ids["pat"]) in row.detail


def test_the_log_never_holds_the_message(client):
    """The body column is encrypted. A readable copy sitting in the log
    would undo that."""
    secret = "Jane has been struggling since the move."
    login(client, "ann")
    send(client, client.ids["pat"], client.ids["jane"], secret)
    client.get(f"/messages/{client.ids['pat']}/{client.ids['jane']}")

    for row in logs(client):
        assert secret not in (row.detail or "")
        assert "struggling" not in (row.detail or "")


def test_opening_a_thread_is_logged(client):
    login(client, "ann")
    send(client, client.ids["pat"], client.ids["jane"], "Jane did well today.")
    client.get(f"/messages/{client.ids['pat']}/{client.ids['jane']}")

    rows = logs(client, action=VIEW, resource_type="message_thread", outcome=ALLOWED)
    assert rows
    assert rows[-1].resource_id == client.ids["jane"]


def test_opening_the_inbox_is_logged(client):
    login(client, "ann")
    client.get("/messages")

    row = logs(client, action=LIST, resource_type="message_thread")[0]
    assert row.outcome == ALLOWED
    assert row.actor_user_id == client.ids["ann"]


def test_an_admin_asking_for_the_inbox_is_logged(client):
    login(client, "admin")
    client.get("/messages")

    row = logs(client, outcome=DENIED)[0]
    assert row.actor_role == "Admin"
    assert row.resource_type == "message_thread"


def test_a_refused_send_is_logged(client):
    login(client, "bob")
    send(client, client.ids["pat"], client.ids["jane"], "hello")

    row = logs(client, outcome=DENIED)[0]
    assert row.actor_user_id == client.ids["bob"]
    assert row.resource_id == client.ids["jane"]


def test_a_refused_read_is_logged(client):
    login(client, "quinn")
    client.get(f"/messages/{client.ids['ann']}/{client.ids['jane']}")

    row = logs(client, outcome=DENIED)[0]
    assert row.actor_role == "Parent"
    assert row.actor_user_id == client.ids["quinn"]


def test_anonymous_gets_nothing_logged(client):
    """A redirect to the login page isn't an access attempt worth a row.
    Everything that reaches the service does get one."""
    client.get("/messages")
    client.get(f"/messages/{client.ids['ann']}/{client.ids['jane']}")

    assert logs(client, resource_type="message_thread") == []
