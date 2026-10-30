"""Audit rows for teacher parent messaging. CNS-011 / T2-027.

Messages carry private student information, so who sent what to whom, and
who tried and got turned away, belongs on the record the same way student
record access does.

No message body goes in here. That column is encrypted and copying any of
it into the log would leave a readable copy somewhere with weaker rules,
which is the same reason the student audit rows don't carry addresses.

Two resource types. "message" is one message and resource_id is its id.
"message_thread" is one conversation and resource_id is the student.

The audit row commits separately from the message, because MessagingService
commits on its own, so a crash in the gap leaves a message with no row.
Worth fixing if this outgrows a capstone.
"""

from sqlalchemy.orm import Session

from data_access.repositories.audit_repository import record, record_independent
from database.audit import ALLOWED, CREATE, DENIED, LIST, VIEW

MESSAGE = "message"
THREAD = "message_thread"


def record_sent(db: Session, actor, message) -> None:
    """A message went out."""
    record(
        db,
        actor,
        CREATE,
        MESSAGE,
        resource_id=message.id,
        outcome=ALLOWED,
        detail=f"to user {message.recipient_id} about student {message.student_id}",
    )
    db.commit()


def record_thread_viewed(db: Session, actor, other_user_id, student_id, count) -> None:
    """Somebody opened a conversation. count is how many messages they saw."""
    record(
        db,
        actor,
        VIEW,
        THREAD,
        resource_id=student_id,
        outcome=ALLOWED,
        detail=f"with user {other_user_id}, {count} messages",
    )
    db.commit()


def record_inbox_listed(db: Session, actor, count) -> None:
    """Somebody opened their inbox. Cheap to write and it's what shows a
    reviewer that an account was being used at all."""
    record(
        db,
        actor,
        LIST,
        THREAD,
        outcome=ALLOWED,
        detail=f"{count} conversations",
    )
    db.commit()


def record_refusal(db: Session, actor, student_id, reason) -> None:
    """Somebody asked for a conversation they're not part of.

    Independent session because the caller is on its way to an error
    response and may roll back, and a denial is the row most worth keeping.
    """
    record_independent(
        db,
        actor,
        VIEW,
        THREAD,
        resource_id=student_id,
        outcome=DENIED,
        detail=reason,
    )
