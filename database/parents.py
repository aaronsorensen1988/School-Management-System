from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from database.database import Base


class ParentStudent(Base):
    """Links a parent user account to a student profile. T2-007."""

    __tablename__ = "parent_students"
    __table_args__ = (
        UniqueConstraint(
            "parent_user_id",
            "student_id",
            name="uq_parent_student",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    parent_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    student_id = Column(
        Integer,
        ForeignKey("students.id"),
        nullable=False,
        index=True,
    )

    parent = relationship("User")
    student = relationship("Student")