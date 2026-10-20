"""Gradebook tables. AMG-008 / T2-012.

Own file, same reason as the others.

Two tables rather than one. Assignment is the thing being graded and it
holds the points it's out of, once. Grade is one student's result on one
assignment. Doing it the other way, with the total repeated on every row,
means changing a quiz from 20 points to 25 is an update to thirty rows and
any one of them can be missed.

Not mine to build on top of:
  T2-011 grade entry UI             Aaron
  T2-013 teacher only entry rights  Sean
  T2-014 validation rules           Shanna

Scores are deliberately not encrypted. Report cards and averages need the
database to add them up, and an encrypted column can't be summed without
pulling every row out and decrypting it first. Grades are covered by the
access rules and the audit trail instead. The teacher comment is encrypted
since that's free text.

student_id points at users.id, matching Enrollment and Attendance.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database.database import Base
from database.types import EncryptedString


def utcnow():
    return datetime.now(timezone.utc)


class Assignment(Base):
    """Something a section gets graded on. A quiz, an essay, a final."""

    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint("section_id", "title", name="uq_assignment_title"),
        CheckConstraint("points_possible > 0", name="ck_points_possible_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False, index=True)

    title = Column(String, nullable=False)
    category = Column(String, nullable=True)  # "homework", "exam", whatever they use
    points_possible = Column(Float, nullable=False)
    due_date = Column(Date, nullable=True)

    section = relationship("Section")
    grades = relationship("Grade", back_populates="assignment")

    def __repr__(self):
        return f"<Assignment {self.title!r} out of {self.points_possible}>"


class Grade(Base):
    """One student's score on one assignment."""

    __tablename__ = "grades"
    __table_args__ = (
        # One score per student per assignment. Changing a mark is an
        # update, and the audit trail records that it changed.
        UniqueConstraint("assignment_id", "student_id", name="uq_grade_student"),
        # Extra credit is allowed, so no upper bound. Negative is not.
        CheckConstraint("points_earned >= 0", name="ck_points_earned_not_negative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    points_earned = Column(Float, nullable=False)

    # Nullable like Attendance.recorded_by, so a row can be imported. T2-013
    # is what requires a real teacher on anything entered through the app.
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    comment = Column(EncryptedString(context="grades.comment"), nullable=True)

    assignment = relationship("Assignment", back_populates="grades")
    student = relationship("User", foreign_keys=[student_id])
    recorder = relationship("User", foreign_keys=[recorded_by])

    @property
    def percent(self):
        """Score as a percentage, or None if the assignment is worth nothing.

        Guarding the divide even though the constraint should make it
        impossible, because a detached object won't have the assignment
        loaded and a template is a bad place to find that out.
        """
        if self.assignment is None or not self.assignment.points_possible:
            return None
        return 100.0 * self.points_earned / self.assignment.points_possible

    def __repr__(self):
        return f"<Grade student={self.student_id} assignment={self.assignment_id} {self.points_earned}>"
