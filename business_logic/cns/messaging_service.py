from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from database.messages import MAX_MESSAGE_LENGTH, Message
from database.models import Role, User
from database.parents import ParentStudent
from database.scheduling import Enrollment, Section
from database.students import Student


class MessagingAccessError(PermissionError):
    """Raised when an actor is not allowed to send or view a conversation."""


class MessagingNotFoundError(LookupError):
    """Raised when a required user or student cannot be found."""


class MessagingValidationError(ValueError):
    """Raised when message content is invalid."""


class MessagingService:
    @staticmethod
    def _role_for_user(db: Session, user_id: int):
        return (
            db.query(Role.name)
            .join(User, User.role_id == Role.id)
            .filter(User.id == user_id)
            .scalar()
        )

    @staticmethod
    def _student_relationship_exists(
        db: Session,
        teacher_id: int,
        parent_id: int,
        student_id: int,
    ) -> bool:
        student = (
            db.query(Student)
            .filter(Student.id == student_id)
            .first()
        )

        if student is None:
            raise MessagingNotFoundError("Student not found.")

        # Scheduling uses users.id rather than students.id.
        if student.user_id is None:
            return False

        parent_link_exists = (
            db.query(ParentStudent.id)
            .filter(
                ParentStudent.parent_user_id == parent_id,
                ParentStudent.student_id == student.id,
            )
            .first()
            is not None
        )

        if not parent_link_exists:
            return False

        teacher_link_exists = (
            db.query(Enrollment.id)
            .join(Section, Section.id == Enrollment.section_id)
            .filter(
                Enrollment.student_id == student.user_id,
                Section.teacher_id == teacher_id,
            )
            .first()
            is not None
        )

        return teacher_link_exists

    @staticmethod
    def _authorize_pair(
        db: Session,
        actor,
        other_user_id: int,
        student_id: int,
    ):
        if actor.user_id is None:
            raise MessagingAccessError("Anonymous users may not use messaging.")

        other_role = MessagingService._role_for_user(db, other_user_id)

        if other_role is None:
            raise MessagingNotFoundError("Recipient not found.")

        if actor.role == "Teacher":
            if other_role != "Parent":
                raise MessagingAccessError(
                    "Teachers may only message parents."
                )

            teacher_id = actor.user_id
            parent_id = other_user_id

        elif actor.role == "Parent":
            if other_role != "Teacher":
                raise MessagingAccessError(
                    "Parents may only reply to teachers."
                )

            teacher_id = other_user_id
            parent_id = actor.user_id

        else:
            raise MessagingAccessError(
                f"{actor.role or 'anonymous'} users may not use parent messaging."
            )

        if not MessagingService._student_relationship_exists(
            db,
            teacher_id,
            parent_id,
            student_id,
        ):
            raise MessagingAccessError(
                "Teacher and parent are not connected through this student."
            )

        return teacher_id, parent_id

    @staticmethod
    def send_message(
        db: Session,
        actor,
        recipient_id: int,
        student_id: int,
        body: str,
    ) -> Message:
        teacher_id, parent_id = MessagingService._authorize_pair(
            db,
            actor,
            recipient_id,
            student_id,
        )

        # CNS-011 says parents can reply. The teacher starts the conversation.
        if actor.role == "Parent":
            teacher_started = (
                db.query(Message.id)
                .filter(
                    Message.student_id == student_id,
                    Message.sender_id == teacher_id,
                    Message.recipient_id == parent_id,
                )
                .first()
            )

            if teacher_started is None:
                raise MessagingAccessError(
                    "Parents may reply only after a teacher starts the conversation."
                )

        if body is None or not body.strip():
            raise MessagingValidationError("Message body is required.")

        if len(body) > MAX_MESSAGE_LENGTH:
            raise MessagingValidationError(
                f"Message body may not exceed {MAX_MESSAGE_LENGTH} characters."
            )

        message = Message(
            student_id=student_id,
            sender_id=actor.user_id,
            recipient_id=recipient_id,
            body=body,
        )

        db.add(message)
        db.commit()
        db.refresh(message)

        return message

    @staticmethod
    def conversation(
        db: Session,
        actor,
        other_user_id: int,
        student_id: int,
    ):
        teacher_id, parent_id = MessagingService._authorize_pair(
            db,
            actor,
            other_user_id,
            student_id,
        )

        return (
            db.query(Message)
            .filter(
                Message.student_id == student_id,
                or_(
                    and_(
                        Message.sender_id == teacher_id,
                        Message.recipient_id == parent_id,
                    ),
                    and_(
                        Message.sender_id == parent_id,
                        Message.recipient_id == teacher_id,
                    ),
                ),
            )
            .order_by(Message.sent_at, Message.id)
            .all()
        )