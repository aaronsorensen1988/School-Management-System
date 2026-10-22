"""Announcement table. CNS-010 / T2-023.

Own file, same as the other tables.

Just the table. The rest of the story is other people:
  T2-021 posting UI                  Aaron
  T2-022 role based posting rights   Sean
  T2-024 ethical review              Sean

Nothing here is encrypted and that one is easy. An announcement is a
broadcast. Encrypting a message meant to be read by the whole school
protects nothing and stops anyone searching it.

The one place that isn't obviously true is a draft, which hasn't been
broadcast to anyone yet. We store drafts in the same column as published
text. If somebody later wants drafts private from other staff, that is a
real decision and it needs a column, not a cipher.

audience is here because the system already knows about roles and a
school wide announcement is not the only kind. "Early dismissal Friday"
goes to everyone. "Staff meeting moved" does not need to go to parents.
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
)
from sqlalchemy.orm import relationship

from database.database import Base

# Who an announcement is aimed at. EVERYONE is the common case.
EVERYONE = "everyone"
STAFF = "staff"
STUDENTS = "students"
PARENTS = "parents"

AUDIENCES = (EVERYONE, STAFF, STUDENTS, PARENTS)

# Which roles each audience actually reaches. Admins see everything,
# otherwise there is no way to check what went out.
AUDIENCE_ROLES = {
    EVERYONE: ("Admin", "Teacher", "Student", "Parent"),
    STAFF: ("Admin", "Teacher"),
    STUDENTS: ("Admin", "Student"),
    PARENTS: ("Admin", "Parent"),
}


def utcnow():
    return datetime.now(timezone.utc)


class Announcement(Base):
    """Something posted for people to read."""

    __tablename__ = "announcements"
    __table_args__ = (
        CheckConstraint(
            "audience IN ('everyone', 'staff', 'students', 'parents')",
            name="ck_announcement_audience",
        ),
        CheckConstraint("length(title) > 0", name="ck_announcement_has_title"),
    )

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)

    audience = Column(String, nullable=False, default=EVERYONE, index=True)

    # Who wrote it. Nullable like the other recorded_by columns so a row can
    # be imported, and T2-022 is what makes sure a real person is attached
    # to anything posted through the app.
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Null means a draft. Set it to publish. Keeping the timestamp rather
    # than a boolean because "when did this go out" is the question anyone
    # actually asks afterwards.
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)

    author = relationship("User")

    def is_published(self):
        return self.published_at is not None

    def publish(self, when=None):
        """Idempotent. Publishing twice shouldn't move the date, or the
        record of when it went out is wrong."""
        if self.published_at is None:
            self.published_at = when or utcnow()
        return self.published_at

    def is_visible_to(self, role):
        """Can somebody with this role read it?

        Drafts are visible to nobody through this. Whoever builds the
        posting screen in T2-021 needs their own view of their own drafts.
        """
        if not self.is_published():
            return False
        return role in AUDIENCE_ROLES.get(self.audience, ())

    def __repr__(self):
        state = "published" if self.is_published() else "draft"
        return f"<Announcement {self.title!r} {self.audience} {state}>"
