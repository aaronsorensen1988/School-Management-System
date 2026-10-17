"""Student enrollment logic for SIEM-004 (Sprint 1 T1-016, T1-017, T1-018).

The validation rules live here instead of only in the HTML form, so they
still apply no matter how data reaches the server.
"""

import re
from datetime import date

from database.database import SessionLocal
from database.students import Student

# Human-friendly labels for every required field on the enrollment form.
REQUIRED_FIELDS = {
    "student_number": "Student ID",
    "first_name": "First name",
    "last_name": "Last name",
    "date_of_birth": "Date of birth",
    "grade_level": "Grade level",
    "home_address": "Home address",
    "guardian_name": "Parent/guardian name",
    "guardian_email": "Parent/guardian email",
}

MIN_GRADE = 0    # 0 = Kindergarten
MAX_GRADE = 12
MIN_AGE = 3
MAX_AGE = 21
MAX_NAME_LENGTH = 100

STUDENT_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9-]{3,20}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_student(form, today=None):
    """Check required fields and formats for a new student.

    Returns (cleaned, errors):
      cleaned - trimmed values ready to save
      errors  - field name -> message to show next to that field
    """
    today = today or date.today()
    cleaned = {}
    errors = {}

    # 1. Every field is required.
    for field, label in REQUIRED_FIELDS.items():
        value = str(form.get(field) or "").strip()
        if not value:
            errors[field] = f"{label} is required."
        cleaned[field] = value

    # 2. Student ID format.
    if "student_number" not in errors and not STUDENT_NUMBER_PATTERN.match(cleaned["student_number"]):
        errors["student_number"] = (
            "Student ID can only use letters, numbers, and dashes (3-20 characters)."
        )

    # 3. Names can't be unreasonably long.
    for field in ("first_name", "last_name", "guardian_name"):
        if field not in errors and len(cleaned[field]) > MAX_NAME_LENGTH:
            errors[field] = f"{REQUIRED_FIELDS[field]} must be {MAX_NAME_LENGTH} characters or fewer."

    # 4. Date of birth must be a real date in the past, for a school-age student.
    if "date_of_birth" not in errors:
        try:
            dob = date.fromisoformat(cleaned["date_of_birth"])
        except ValueError:
            errors["date_of_birth"] = "Date of birth must be a valid date (YYYY-MM-DD)."
        else:
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if dob >= today:
                errors["date_of_birth"] = "Date of birth must be in the past."
            elif not MIN_AGE <= age <= MAX_AGE:
                errors["date_of_birth"] = (
                    f"Student must be between {MIN_AGE} and {MAX_AGE} years old."
                )

    # 5. Grade level must be K (0) through 12.
    if "grade_level" not in errors:
        try:
            grade = int(cleaned["grade_level"])
        except ValueError:
            errors["grade_level"] = "Grade level must be a number."
        else:
            if not MIN_GRADE <= grade <= MAX_GRADE:
                errors["grade_level"] = "Grade level must be between K (0) and 12."
            else:
                cleaned["grade_level"] = grade

    # 6. Guardian email must look like an email address.
    if "guardian_email" not in errors and not EMAIL_PATTERN.match(cleaned["guardian_email"]):
        errors["guardian_email"] = "Parent/guardian email must be a valid email address."

    return cleaned, errors


class StudentService:
    """Saves and loads student profiles."""

    def create_student(self, form):
        """Validate and save a new student.

        Returns (student_id, errors). student_id is None if anything failed.
        """
        cleaned, errors = validate_student(form)
        if errors:
            return None, errors

        db = SessionLocal()
        try:
            existing = (
                db.query(Student)
                .filter(Student.student_number == cleaned["student_number"])
                .first()
            )
            if existing is not None:
                return None, {"student_number": "A student with this ID already exists."}

            student = Student(**cleaned)
            db.add(student)
            db.commit()
            db.refresh(student)
            return student.id, {}

        except Exception:
            # Prevent partial database changes if the save fails.
            db.rollback()
            raise

        finally:
            db.close()

    def list_students(self):
        """Return every student, sorted by last name, for the Students page."""
        db = SessionLocal()
        try:
            students = db.query(Student).order_by(Student.last_name, Student.first_name).all()
            return [self._to_dict(s) for s in students]
        finally:
            db.close()

    def get_student(self, student_id):
        """Return one student's profile, or None if the ID doesn't exist."""
        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            return None

        db = SessionLocal()
        try:
            student = db.query(Student).filter(Student.id == student_id).first()
            return self._to_dict(student) if student else None
        finally:
            db.close()

    @staticmethod
    def _to_dict(student):
        # Read every column while the session is still open. The encrypted
        # columns come back already decrypted.
        grade = "K" if student.grade_level == 0 else str(student.grade_level)
        return {
            "id": student.id,
            "student_number": student.student_number,
            "name": f"{student.first_name} {student.last_name}",
            "first_name": student.first_name,
            "last_name": student.last_name,
            "grade": grade,
            "date_of_birth": student.date_of_birth,
            "home_address": student.home_address,
            "guardian_name": student.guardian_name,
            "guardian_email": student.guardian_email,
        }
