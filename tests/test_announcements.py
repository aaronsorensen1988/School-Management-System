"""Tests for the announcement table. CNS-010 / T2-023.

What the table guarantees. Who is allowed to post is T2-022 and the screen
is T2-021.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.announcements import (
    EVERYONE,
    PARENTS,
    STAFF,
    STUDENTS,
    Announcement,
)
from database.database import Base
from database.models import Role, User


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as s:
        admin_role = Role(name="Admin")
        s.add(admin_role)
        s.flush()
        s.add(User(username="admin", password_hash="x", first_name="System",
                   last_name="Admin", email="admin@school.edu", role_id=admin_role.id))
        s.commit()
        yield s


def _admin(db):
    return db.query(User).filter(User.username == "admin").one()


# -- the basics ----------------------------------------------------------

def test_an_announcement_can_be_posted(db):
    db.add(Announcement(title="Early dismissal Friday",
                        body="Buses leave at 1pm.", author_id=_admin(db).id))
    db.commit()

    row = db.query(Announcement).one()
    assert row.audience == EVERYONE
    assert row.created_at is not None


def test_a_new_announcement_is_a_draft(db):
    """published_at is null until somebody publishes it."""
    db.add(Announcement(title="Not ready", body="..."))
    db.commit()

    row = db.query(Announcement).one()
    assert row.published_at is None
    assert row.is_published() is False


def test_publishing_sets_the_date(db):
    a = Announcement(title="Snow day", body="No school tomorrow.")
    db.add(a)
    db.commit()

    a.publish()
    db.commit()
    assert db.query(Announcement).one().is_published() is True


def test_publishing_twice_keeps_the_first_date(db):
    """Otherwise the record of when it went out is wrong, and that's the
    question anyone asks afterwards."""
    a = Announcement(title="Snow day", body="No school tomorrow.")
    db.add(a)
    db.commit()

    first = a.publish()
    again = a.publish()
    assert first == again


# -- what the table refuses ----------------------------------------------

def test_a_made_up_audience_is_rejected(db):
    db.add(Announcement(title="Hello", body="...", audience="parents-only-maybe"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_an_empty_title_is_rejected(db):
    db.add(Announcement(title="", body="..."))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_body_is_required(db):
    db.add(Announcement(title="Has a title"))
    with pytest.raises(IntegrityError):
        db.commit()


# -- who sees what -------------------------------------------------------

def test_a_draft_is_visible_to_nobody(db):
    draft = Announcement(title="Later", body="...", audience=EVERYONE)
    for role in ("Admin", "Teacher", "Student", "Parent"):
        assert draft.is_visible_to(role) is False


@pytest.mark.parametrize("role", ["Admin", "Teacher", "Student", "Parent"])
def test_everyone_means_everyone(db, role):
    a = Announcement(title="Early dismissal", body="...", audience=EVERYONE)
    a.publish()
    assert a.is_visible_to(role) is True


def test_staff_announcements_stay_with_staff(db):
    a = Announcement(title="Staff meeting moved", body="...", audience=STAFF)
    a.publish()
    assert a.is_visible_to("Teacher") is True
    assert a.is_visible_to("Student") is False
    assert a.is_visible_to("Parent") is False


def test_parent_announcements_dont_go_to_students(db):
    a = Announcement(title="Fundraiser", body="...", audience=PARENTS)
    a.publish()
    assert a.is_visible_to("Parent") is True
    assert a.is_visible_to("Student") is False


def test_student_announcements_dont_go_to_parents(db):
    a = Announcement(title="Club signups", body="...", audience=STUDENTS)
    a.publish()
    assert a.is_visible_to("Student") is True
    assert a.is_visible_to("Parent") is False


def test_an_admin_can_always_see_it(db):
    """Otherwise there's no way to check what went out."""
    for audience in (EVERYONE, STAFF, STUDENTS, PARENTS):
        a = Announcement(title="x", body="y", audience=audience)
        a.publish()
        assert a.is_visible_to("Admin") is True


def test_an_unknown_role_sees_nothing(db):
    a = Announcement(title="x", body="y", audience=EVERYONE)
    a.publish()
    assert a.is_visible_to("Janitor") is False
    assert a.is_visible_to(None) is False
