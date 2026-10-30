"""Who someone may message, and the threads they already have. CNS-011 / T2-025.

MessagingService works one conversation at a time, so it answers "may these
two talk about this student" but not "who are my conversations with". The
pages need both, so the lookups live here.

Everything walks the same teacher to student to parent chain the service
checks on every send. Building the lists off that chain instead of writing
a second set of rules is what keeps the two agreeing. A name that shows up
here will pass authorization, and one that doesn't won't appear.
"""

from collections import namedtuple

from sqlalchemy.orm import Session

from database.messages import Message
from database.models import User
from database.parents import ParentStudent
from database.scheduling import Enrollment, Section
from database.students import Student

# other_user is the person at the far end, student is who the thread is about.
Contact = namedtuple("Contact", "other_user student")

# The inbox sorts on last_sent_at. count is only there so an empty thread
# can't be mistaken for one that has messages in it.
Thread = namedtuple("Thread", "other_user student last_sent_at count")


def _teacher_contacts(db: Session, teacher_id: int):
    """Parents of the students this teacher actually teaches.

    Enrollment.student_id holds a users.id, not a students.id, which is why
    the join to Student goes through Student.user_id.
    """
    rows = (
        db.query(User, Student)
        .join(ParentStudent, ParentStudent.parent_user_id == User.id)
        .join(Student, Student.id == ParentStudent.student_id)
        .join(Enrollment, Enrollment.student_id == Student.user_id)
        .join(Section, Section.id == Enrollment.section_id)
        .filter(Section.teacher_id == teacher_id)
        .all()
    )
    return rows


def contacts_for(db: Session, actor) -> list[Contact]:
    """Everyone this actor may start a conversation with, one entry per
    student.

    Only teachers get anything back. CNS-011 has the teacher opening the
    conversation and the parent replying, so send_message refuses a parent's
    first message. Offering a parent somebody to write to would be offering
    a button that always returns 403, which is what Sean caught in review.
    A parent's legitimate threads all started with a teacher, so they're
    already in threads_for by definition.

    Anybody who isn't a teacher gets an empty list instead of an error,
    because the page decides what to do about that.
    """
    if actor.user_id is None or actor.role != "Teacher":
        return []

    rows = _teacher_contacts(db, actor.user_id)

    # A student in two of the same teacher's sections comes back twice.
    seen = {}
    for other_user, student in rows:
        seen.setdefault((other_user.id, student.id), Contact(other_user, student))

    return sorted(
        seen.values(),
        key=lambda c: (c.student.last_name, c.student.first_name, c.other_user.last_name),
    )


def may_send(actor, other_user_id: int, messages) -> bool:
    """Whether the page should show this actor a send box.

    Mirrors the rule in MessagingService.send_message: a teacher may open a
    conversation, a parent may only reply to one. Opening the thread itself
    is allowed either way, which is why the GET succeeds and the POST is
    what refuses. Rendering a form that can only 403 is the same mismatch
    Sean found on the inbox, one page further in.
    """
    if actor.role == "Teacher":
        return True
    if actor.role == "Parent":
        return any(m.sender_id == other_user_id for m in messages)
    return False


def threads_for(db: Session, actor) -> list[Thread]:
    """Conversations this actor is already part of, newest first.

    Grouped in Python rather than SQL because the pair is (other person,
    student) and which column holds the other person depends on who sent
    each message.
    """
    if actor.user_id is None:
        return []

    messages = (
        db.query(Message)
        .filter(
            (Message.sender_id == actor.user_id)
            | (Message.recipient_id == actor.user_id)
        )
        .order_by(Message.sent_at, Message.id)
        .all()
    )

    if not messages:
        return []

    people = {u.id: u for u in db.query(User).all()}
    students = {s.id: s for s in db.query(Student).all()}

    grouped = {}
    for message in messages:
        other_id = (
            message.recipient_id
            if message.sender_id == actor.user_id
            else message.sender_id
        )
        key = (other_id, message.student_id)
        last_sent_at, count = grouped.get(key, (None, 0))
        grouped[key] = (message.sent_at, count + 1)

    threads = [
        Thread(people[other_id], students[student_id], last_sent_at, count)
        for (other_id, student_id), (last_sent_at, count) in grouped.items()
        if other_id in people and student_id in students
    ]

    return sorted(threads, key=lambda t: t.last_sent_at, reverse=True)
