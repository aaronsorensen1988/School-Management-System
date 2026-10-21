"""Attendance write access for SIEM-005 / T2-003."""

from sqlalchemy.orm import Session

from business_logic.uma.access_control import AccessControl
from database.attendance import Attendance
from database.scheduling import Enrollment, Section


class AttendanceAccessError(PermissionError):
    """Raised when a user may not record attendance for a section."""
    pass


class AttendanceService:
    def record_attendance(
        self,
        db: Session,
        actor,
        section_id: int,
        student_id: int,
        on_date,
        status: str,
        note=None,
    ) -> Attendance:
        """Record attendance for a student in a teacher's assigned section."""

        section = db.query(Section).filter(Section.id == section_id).first()
        if section is None:
            raise LookupError("Section not found")

        if not AccessControl.can_record_attendance(
            actor.role,
            actor.user_id,
            section.teacher_id,
        ):
            raise AttendanceAccessError(
                "Teacher may only record attendance for assigned sections"
            )

        enrollment = db.query(Enrollment).filter(
            Enrollment.section_id == section_id,
            Enrollment.student_id == student_id,
        ).first()

        if enrollment is None:
            raise ValueError("Student is not enrolled in this section")

        attendance = Attendance(
            section_id=section_id,
            student_id=student_id,
            on_date=on_date,
            status=status,
            note=note,
            recorded_by=actor.user_id,
        )

        db.add(attendance)
        db.commit()
        db.refresh(attendance)
        return attendance


attendance_service = AttendanceService()