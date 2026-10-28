"""Teacher-parent messages. CNS-011 / T2-026.

Messages are tied to the student they concern so the system can verify that
the teacher actually teaches the parent's child.

The message body is encrypted because teacher-parent communication may contain
private student information.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship

from database.database import Base
from database.types import EncryptedString


MAX_MESSAGE_LENGTH = 4000


def utcnow():
    return datetime.now(timezone.utc)


class Message(Base):
    """One message between a teacher and a parent."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(
        Integer,
        ForeignKey("students.id"),
        nullable=False,
        index=True,
    )

    sender_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    recipient_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    body = Column(
        EncryptedString(
            context="messages.body",
            max_plaintext=MAX_MESSAGE_LENGTH,
        ),
        nullable=False,
    )

    sent_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        index=True,
    )

    student = relationship("Student")
    sender = relationship("User", foreign_keys=[sender_id])
    recipient = relationship("User", foreign_keys=[recipient_id])