"""Student profile table. SIEM-004 / T1-017. Shanna.

Kept in its own file like Nick's scheduling.py, so we're not all editing
models.py at the same time.

FERPA-sensitive fields (date of birth, home address, and guardian contact
details) are encrypted at rest with Nick's EncryptedString column type
(UMA-003). Student ID, names, and grade stay plain so they can be searched
and sorted.
"""

from sqlalchemy import Column, ForeignKey, Integer, String

from database.database import Base
from database.types import EncryptedString


class Student(Base):
    """A student's enrollment profile."""

    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)

    # Optional link to the student's login account (a User with the Student
    # role). Enrollments in scheduling.py point at users.id, so this is how a
    # profile connects to class schedules. Nullable because a student can be
    # enrolled before an account is created for them.
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True)

    student_number = Column(String, unique=True, nullable=False, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)

    # 0 = Kindergarten, 1-12 = grades 1 through 12.
    grade_level = Column(Integer, nullable=False)

    # Encrypted at rest. Stored as ciphertext and decrypted automatically on read.
    date_of_birth = Column(EncryptedString(context="students.date_of_birth"), nullable=False)
    home_address = Column(EncryptedString(context="students.home_address"), nullable=False)
    guardian_name = Column(EncryptedString(context="students.guardian_name"), nullable=False)
    guardian_email = Column(EncryptedString(context="students.guardian_email"), nullable=False)
