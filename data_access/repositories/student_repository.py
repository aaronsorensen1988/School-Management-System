"""Role checked access to student records. UMA-003 / T1-013.

Encryption protects the db file. Doesn't help if someone logged in reads
records they shouldn't. This is that half.

    repo = StudentRepository(db)
    students = repo.list_visible(actor)
    student  = repo.get(actor, 7)              # raises AccessDenied

Actor is who's asking, no default and no bypass or someone forgets it.
Rules live in business_logic.uma.access_control, this enforces them.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from business_logic.uma.access_control import AccessControl
from data_access.repositories.audit_repository import record
from database.audit import ALLOWED, CREATE, DENIED, LIST, VIEW
from database.students import Student

# Fields that only staff should see. A student looking at their own record
# sees them too, it's their information.
CONTACT_FIELDS = ("home_address", "guardian_name", "guardian_email", "date_of_birth")


class AccessDenied(PermissionError):
    """Actor isn't allowed to do that."""


@dataclass(frozen=True)
class Actor:
    """Who's asking. user_id is a users.id, the other two are students.id,
    passed in by the caller since rosters and parent links aren't tables
    yet (Sprint 2)."""

    user_id: int | None = None
    role: str | None = None
    assigned_student_ids: tuple = field(default_factory=tuple)
    child_ids: tuple = field(default_factory=tuple)


# Not logged in. Gets nothing.
ANONYMOUS = Actor()


class StudentRepository:
    def __init__(self, db: Session):
        self.db = db

    # -- reads ---------------------------------------------------------

    def get(self, actor: Actor, student_id: int) -> Student:
        """One student. Raises AccessDenied if this actor can't see them.

        Raises instead of returning None so the caller can tell "no such
        student" from "not allowed", and so T1-014 has something to log.
        """
        student = self.db.query(Student).filter(Student.id == student_id).first()
        if student is None:
            raise LookupError(f"no student with id {student_id}")

        if not self._may_view(actor, student):
            self._log(actor, VIEW, DENIED, student_id)
            raise AccessDenied(
                f"{actor.role or 'anonymous'} user {actor.user_id} may not view student {student_id}"
            )

        self._log(actor, VIEW, ALLOWED, student_id)
        return student

    def list_visible(self, actor: Actor) -> list[Student]:
        """Every student this actor may see, often none of them.

        Filters in Python because rosters and parent links come in on the
        Actor, not from tables. Fine at school sizes, move it into the
        query in Sprint 2.
        """
        if actor.role is None:
            self._log(actor, LIST, DENIED)
            return []

        students = (
            self.db.query(Student)
            .order_by(Student.last_name, Student.first_name)
            .all()
        )
        visible = [s for s in students if self._may_view(actor, s)]
        self._log(actor, LIST, ALLOWED,
                  detail=f"{len(visible)} of {len(students)} rows")
        return visible

    # -- writes --------------------------------------------------------

    def create(self, actor: Actor, **fields) -> Student:
        """Add a student. Admins only."""
        if not AccessControl.can_manage_students(actor.role):
            self._log(actor, CREATE, DENIED)
            raise AccessDenied(
                f"{actor.role or 'anonymous'} user {actor.user_id} may not create students"
            )
        student = Student(**fields)
        self.db.add(student)
        self.db.flush()
        self._log(actor, CREATE, ALLOWED, student.id, commit=False)
        return student

    # -- helpers -------------------------------------------------------

    def _log(self, actor, action, outcome, resource_id=None, detail=None, commit=True):
        """Record and commit straight away.

        Has to commit, not flush. A denial ends in an exception and a
        rolled back request, and a plain read never commits at all, so a
        flushed row would be thrown away either way.
        """
        record(self.db, actor, action, "student", resource_id, outcome, detail)
        if commit:
            self.db.commit()

    def _may_view(self, actor: Actor, student: Student) -> bool:
        # Sean's policy compares requester_id to student_id. a logged in
        # student is a users.id, so match against the linked account rather
        # than the profile's own id.
        subject_id = student.user_id if actor.role == "Student" else student.id
        return AccessControl.can_view_student_record(
            role=actor.role,
            requester_id=actor.user_id,
            student_id=subject_id,
            assigned_student_ids=list(actor.assigned_student_ids),
            child_ids=list(actor.child_ids),
        )


def redact(student_dict: dict, actor: Actor, student_user_id: int | None = None) -> dict:
    """Blank contact details for anyone who shouldn't have them.

    Access decides which students, this decides how much of each. Admins
    and the student themselves see everything, everyone else gets the
    academic fields and None for the rest.
    """
    if actor.role == "Admin":
        return student_dict
    if actor.role == "Student" and student_user_id is not None and actor.user_id == student_user_id:
        return student_dict

    out = dict(student_dict)
    for key in CONTACT_FIELDS:
        if key in out:
            out[key] = None
    return out
