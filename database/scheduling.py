"""Course scheduling tables. AMG-007 / T1-022.

Separate file from models.py so Sean and I aren't editing the same lines.
Shanna, if you add student profile tables, same idea, make your own.

These are just the tables. The rules that sit on top of them are other
people's tasks:
  T1-021 scheduling UI        Shanna
  T1-023 teacher assignment   Shanna
  T1-024 capacity limit       Aaron

Three tables. Course is the subject, Section is one actual class that
meets at a time with a teacher and a room, Enrollment puts a student in a
section. A course can have several sections, which is how you get two
periods of Algebra I with different teachers.

Nothing here is encrypted. Debated it. Course names and times aren't
sensitive, and the enrollment rows are just two foreign keys, so there's
nothing in them worth protecting that isn't already protected on the users
table. Writing it down in case someone asks why.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database.database import Base

DEFAULT_CAPACITY = 20  # T1-024

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")


class Course(Base):
    """A subject that can be taught, like "Algebra I"."""

    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)  # "MATH101"
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    sections = relationship("Section", back_populates="course")


class Section(Base):
    """One class that actually meets. Teacher, room, day and time.

    day/start/end are here so the overlap check in T1-023 has something to
    compare. Not enforcing it in the database, SQLite can't really do time
    range constraints, so that one lives in code.
    """

    __tablename__ = "sections"
    __table_args__ = (
        # same room can't be double booked at the same time
        UniqueConstraint("room", "day_of_week", "start_time", name="uq_room_slot"),
        CheckConstraint("capacity > 0", name="ck_capacity_positive"),
        CheckConstraint("end_time > start_time", name="ck_end_after_start"),
    )

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)

    # teacher is a user with the Teacher role. nullable because a section
    # can be created before anyone's assigned to it, T1-023 fills it in.
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    room = Column(String, nullable=False)
    day_of_week = Column(String, nullable=False)  # one of DAYS
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    capacity = Column(Integer, nullable=False, default=DEFAULT_CAPACITY)

    course = relationship("Course", back_populates="sections")
    teacher = relationship("User")
    enrollments = relationship("Enrollment", back_populates="section")

    @property
    def seats_taken(self):
        return len(self.enrollments)

    @property
    def seats_left(self):
        return self.capacity - self.seats_taken

    def is_full(self):
        """Helper for T1-024. Still check this inside the transaction that
        does the enrolling, otherwise two people can take the last seat."""
        return self.seats_left <= 0


class Enrollment(Base):
    """Puts a student in a section."""

    __tablename__ = "enrollments"
    __table_args__ = (
        # a student can't be in the same section twice
        UniqueConstraint("section_id", "student_id", name="uq_student_section"),
    )

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    section = relationship("Section", back_populates="enrollments")
    student = relationship("User")


def sections_overlap(a, b):
    """Do two sections collide? Same day and the times cross.

    Used for both halves of the acceptance criteria, a teacher can't be in
    two rooms at once and neither can a student. T1-023 calls this, it's
    here because it's about how the table is laid out.
    """
    if a.day_of_week != b.day_of_week:
        return False
    return a.start_time < b.end_time and b.start_time < a.end_time
