"""Course scheduling business logic for AMG-007 / T1-024."""
from sqlalchemy.orm import Session
from sqlalchemy import update
from database.scheduling import Section, Enrollment
from database.models import User, Role


class CapacityLimitError(ValueError):
    """Raised when attempting to enroll into a full section."""
    pass


class SchedulingService:
    def enroll_student(self, db: Session, section_id: int, student_id: int) -> Enrollment:
        # Lock enrollment changes before checking capacity so two requests
        # cannot both take the final available seat.
        db.execute(
            update(Section)
            .where(Section.id == section_id)
            .values(capacity=Section.capacity)
        )
        
        # 1. Verify section exists
        section = db.query(Section).filter(Section.id == section_id).first()
        if not section:
            raise LookupError("Section not found")

        # 2. Check capacity (T1-024)
        if section.is_full():
            raise CapacityLimitError("Classroom capacity limit reached")

        # 3. Check student validity (must exist and have Student role)
        student = db.query(User).filter(User.id == student_id).first()
        if not student:
            raise LookupError("Student not found")

        student_role = db.query(Role).filter(Role.name == "Student").first()
        if student.role_id != student_role.id:
            raise ValueError("User does not have a Student role")

        # 4. Check for duplicate enrollment
        existing = db.query(Enrollment).filter(
            Enrollment.section_id == section_id,
            Enrollment.student_id == student_id
        ).first()
        if existing:
            raise ValueError("Student already enrolled in this section")

        # 5. Create and commit enrollment
        enrollment = Enrollment(section_id=section_id, student_id=student_id)
        db.add(enrollment)
        db.commit()
        db.refresh(enrollment)
        return enrollment


scheduling_service = SchedulingService()