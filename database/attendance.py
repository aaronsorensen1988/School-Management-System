"""Attendance table. SIEM-005 / T2-002.

Own file again, same reason as scheduling.py and students.py, so we're not
all editing the same lines.

Just the table. The rest of the story belongs to other people:
  T2-001 attendance entry UI      Shanna
  T2-003 teacher only write access Sean
  T2-004 validation rules          Shanna

One row per student, per section, per day. Attendance gets taken each
period, so a student in four classes has four rows for one day.

student_id matches Enrollment in scheduling.py and points at users.id. The
student profile table uses its own id and the audit log records that one,
so we identify a student two different ways depending on which table you
start from. Something to watch if anyone joins across them.

Status is a plain string so absences can be counted. The note is encrypted
since people write reasons in it.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database.database import Base
from database.types import EncryptedString

# Short list for now. Adding to it is a policy call we haven't made.
PRESENT = "present"
ABSENT = "absent"
TARDY = "tardy"
EXCUSED = "excused"

STATUSES = (PRESENT, ABSENT, TARDY, EXCUSED)

# Use this in reporting instead of listing the statuses again.
MISSED = (ABSENT, TARDY, EXCUSED)


def utcnow():
    return datetime.now(timezone.utc)


class Attendance(Base):
    """One student's attendance for one section on one day."""

    __tablename__ = "attendance"
    __table_args__ = (
        # Taking attendance twice for the same student in the same period
        # should be an update, not a second row.
        UniqueConstraint("section_id", "student_id", "on_date", name="uq_attendance_day"),
        CheckConstraint(
            "status IN ('present', 'absent', 'tardy', 'excused')",
            name="ck_attendance_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    on_date = Column(Date, nullable=False, index=True)
    status = Column(String, nullable=False, default=PRESENT)

    # The teacher who took it. Nullable the same way Section.teacher_id is,
    # so a row can be backfilled or imported. T2-003 is what makes sure a
    # real person is attached to anything entered through the app.
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Free text, so it gets encrypted.
    note = Column(EncryptedString(context="attendance.note"), nullable=True)

    section = relationship("Section")
    student = relationship("User", foreign_keys=[student_id])
    recorder = relationship("User", foreign_keys=[recorded_by])

    def is_missed(self):
        """Anything other than present. For the absence counts in T2-004."""
        return self.status in MISSED

    def __repr__(self):
        return (
            f"<Attendance student={self.student_id} section={self.section_id} "
            f"{self.on_date} {self.status}>"
        )
