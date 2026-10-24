from sqlalchemy.orm import Session

from business_logic.uma.access_control import AccessControl
from database.grades import Assignment, Grade
from database.scheduling import Enrollment


class GradeAccessError(Exception):
    """Raised when a user is not allowed to record a grade."""


class GradeEntryError(Exception):
    """Raised when the requested grade target does not exist."""


class GradeService:
    @staticmethod
    def record_grade(
        db: Session,
        actor,
        student_id: int,
        assignment_id: int,
        points_earned: float,
    ) -> Grade:
        assignment = (
            db.query(Assignment)
            .filter(Assignment.id == assignment_id)
            .first()
        )

        if assignment is None:
            raise GradeEntryError("Assignment not found.")

        section = assignment.section

        if not AccessControl.can_record_grade(
            actor.role,
            actor.user_id,
            section.teacher_id,
        ):
            raise GradeAccessError(
                "Only the teacher assigned to this section may record grades."
            )

        enrolled = (
            db.query(Enrollment)
            .filter(
                Enrollment.section_id == section.id,
                Enrollment.student_id == student_id,
            )
            .first()
        )

        if enrolled is None:
            raise GradeAccessError(
                "Grades may only be recorded for students enrolled in this section."
            )

        grade = (
            db.query(Grade)
            .filter(
                Grade.student_id == student_id,
                Grade.assignment_id == assignment_id,
            )
            .first()
        )

        if grade is None:
            grade = Grade(
                student_id=student_id,
                assignment_id=assignment_id,
                points_earned=points_earned,
                recorded_by=actor.user_id,
            )
            db.add(grade)
        else:
            grade.points_earned = points_earned
            grade.recorded_by = actor.user_id

        db.commit()
        db.refresh(grade)

        return grade