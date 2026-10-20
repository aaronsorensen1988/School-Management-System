"""Teacher assignment for class sections. AMG-007 / T1-023. Shanna.

Nick's scheduling tables leave Section.teacher_id empty on purpose so it
can be filled in here. The rules from the AMG-007 acceptance criteria:

  - only a user with the Teacher role can be assigned to a section
  - a teacher can't be booked into two sections that meet at the same time
    (uses sections_overlap from database/scheduling.py)

Kept in its own file so it doesn't collide with scheduling_service.py,
which holds Aaron's capacity check (T1-024).
"""

from sqlalchemy.orm import Session

from database.models import Role, User
from database.scheduling import Section, sections_overlap


class TeacherAssignmentError(ValueError):
    """The assignment breaks a scheduling rule (wrong role, time conflict)."""


def list_teachers(db: Session):
    """Every user with the Teacher role, sorted by last name."""
    teacher_role = db.query(Role).filter(Role.name == "Teacher").first()
    if teacher_role is None:
        return []
    return (
        db.query(User)
        .filter(User.role_id == teacher_role.id)
        .order_by(User.last_name, User.first_name)
        .all()
    )


def find_teacher_conflict(db: Session, section: Section, teacher_id: int):
    """Return the teacher's other section that overlaps this one, or None."""
    others = (
        db.query(Section)
        .filter(Section.teacher_id == teacher_id, Section.id != section.id)
        .all()
    )
    for other in others:
        if sections_overlap(section, other):
            return other
    return None


def assign_teacher(db: Session, section_id: int, teacher_id: int) -> Section:
    """Assign a teacher to a section after checking the rules.

    Raises LookupError if the section or user doesn't exist, and
    TeacherAssignmentError if the user isn't a teacher or is already
    teaching another section at the same time.
    """
    section = db.query(Section).filter(Section.id == section_id).first()
    if section is None:
        raise LookupError("Section not found")

    teacher = db.query(User).filter(User.id == teacher_id).first()
    if teacher is None:
        raise LookupError("Teacher not found")

    teacher_role = db.query(Role).filter(Role.name == "Teacher").first()
    if teacher_role is None or teacher.role_id != teacher_role.id:
        raise TeacherAssignmentError(
            f"{teacher.first_name} {teacher.last_name} does not have the Teacher role."
        )

    conflict = find_teacher_conflict(db, section, teacher.id)
    if conflict is not None:
        raise TeacherAssignmentError(
            f"{teacher.first_name} {teacher.last_name} already teaches "
            f"{conflict.course.code} on {conflict.day_of_week} "
            f"{conflict.start_time:%H:%M}-{conflict.end_time:%H:%M}, "
            f"which overlaps this section."
        )

    section.teacher_id = teacher.id
    db.commit()
    db.refresh(section)
    return section


def unassign_teacher(db: Session, section_id: int) -> Section:
    """Remove the teacher from a section (it goes back to Unassigned)."""
    section = db.query(Section).filter(Section.id == section_id).first()
    if section is None:
        raise LookupError("Section not found")

    section.teacher_id = None
    db.commit()
    db.refresh(section)
    return section
