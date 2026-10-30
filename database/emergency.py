"""Emergency notification tables. CNS-012 / T2-030, T2-031. Shanna.

Own file, same as the other tables.

Two tables, the same idea as Assignment and Grade:
  EmergencyNotification   the alert itself, written once
  EmergencyReceipt        one row per person it was sent to, so we know who
                          it reached and who has seen it

A receipt row per person matters for an emergency in a way it doesn't for an
announcement. "Did everyone get the lockdown alert, and who still hasn't
opened it?" is the question someone asks afterwards, and an announcement
that's just visible to a role can't answer it.

Audiences reuse the announcement ones (everyone, staff, students, parents)
so the two features don't drift apart.

Delivery is in-app only for now. CNS-012 also lists email and SMS, which
need an outside service we don't have, so they're left for a later sprint.

Not encrypted, same reasoning as announcements: it's a broadcast meant to be
read by everyone it's sent to.

Other parts of CNS-012:
  T2-032 access logging            open
  T2-033 admin only permissions    Sean
  T2-034 ethical review            open
"""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database.announcements import AUDIENCES  # noqa: F401  same list on purpose
from database.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class EmergencyNotification(Base):
    """One emergency alert sent by an administrator."""

    __tablename__ = "emergency_notifications"
    __table_args__ = (
        CheckConstraint(
            "audience IN ('everyone', 'staff', 'students', 'parents')",
            name="ck_emergency_audience",
        ),
        CheckConstraint("length(title) > 0", name="ck_emergency_has_title"),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    audience = Column(String, nullable=False, index=True)

    sent_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    sender = relationship("User")
    receipts = relationship("EmergencyReceipt", back_populates="notification")

    def __repr__(self):
        return f"<EmergencyNotification {self.title!r} to {self.audience}>"


class EmergencyReceipt(Base):
    """One person an alert was sent to, and when they read it."""

    __tablename__ = "emergency_receipts"
    __table_args__ = (
        UniqueConstraint("notification_id", "user_id", name="uq_emergency_receipt"),
    )

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("emergency_notifications.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    notification = relationship("EmergencyNotification", back_populates="receipts")
    user = relationship("User")

    def is_read(self):
        return self.read_at is not None
