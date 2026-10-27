from sqlalchemy.orm import Session

from business_logic.uma.access_control import AccessControl
from database.announcements import EVERYONE, Announcement


class AnnouncementAccessError(PermissionError):
    """Raised when an actor is not allowed to post announcements."""


class AnnouncementNotFoundError(LookupError):
    """Raised when an announcement cannot be found."""


class AnnouncementService:
    @staticmethod
    def create_draft(
        db: Session,
        actor,
        title: str,
        body: str,
        audience: str = EVERYONE,
    ) -> Announcement:
        if not AccessControl.can_post_announcement(actor.role):
            raise AnnouncementAccessError(
                f"{actor.role or 'anonymous'} users may not post announcements."
            )

        announcement = Announcement(
            title=title,
            body=body,
            audience=audience,
            author_id=actor.user_id,
        )

        db.add(announcement)
        db.commit()
        db.refresh(announcement)

        return announcement

    @staticmethod
    def publish(
        db: Session,
        actor,
        announcement_id: int,
    ) -> Announcement:
        if not AccessControl.can_post_announcement(actor.role):
            raise AnnouncementAccessError(
                f"{actor.role or 'anonymous'} users may not post announcements."
            )

        announcement = (
            db.query(Announcement)
            .filter(Announcement.id == announcement_id)
            .first()
        )

        if announcement is None:
            raise AnnouncementNotFoundError("Announcement not found.")

        announcement.publish()
        db.commit()
        db.refresh(announcement)

        return announcement