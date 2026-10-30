"""Emergency notification broadcast logic. CNS-012 / T2-031. Shanna.

send_emergency() checks the alert, works out who it goes to, and creates the
alert plus one receipt per person in a single save, so an alert is never
half sent.

Who may send is Sean's T2-033 (AccessControl.can_send_emergency_notification).
Access logging is T2-032; log calls belong where the comments say.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from business_logic.uma.access_control import AccessControl
from database.announcements import AUDIENCE_ROLES, AUDIENCES
from database.emergency import EmergencyNotification, EmergencyReceipt
from database.models import Role, User

TITLE_MAX = 100
MESSAGE_MAX = 1000

AUDIENCE_LABELS = {
    "everyone": "Everyone",
    "staff": "Staff (admins and teachers)",
    "students": "Students",
    "parents": "Parents",
}


class EmergencyAccessError(PermissionError):
    """Raised when someone who isn't an admin tries to send an alert."""


def recipients_for(db: Session, audience):
    """Every user an alert to this audience should reach."""
    roles = AUDIENCE_ROLES.get(audience, ())
    if not roles:
        return []
    return (
        db.query(User)
        .join(Role, Role.id == User.role_id)
        .filter(Role.name.in_(roles))
        .order_by(User.id)
        .all()
    )


def check_alert(form):
    """Returns (cleaned values, errors). errors is {field: message}."""
    title = str(form.get("title") or "").strip()
    message = str(form.get("message") or "").strip()
    audience = str(form.get("audience") or "").strip()

    errors = {}
    if not title:
        errors["title"] = "Title is required."
    elif len(title) > TITLE_MAX:
        errors["title"] = f"Title can be at most {TITLE_MAX} characters."
    if not message:
        errors["message"] = "Message is required."
    elif len(message) > MESSAGE_MAX:
        errors["message"] = f"Message can be at most {MESSAGE_MAX} characters."
    if audience not in AUDIENCES:
        errors["audience"] = "Choose who should receive this alert."

    return {"title": title, "message": message, "audience": audience}, errors


def send_emergency(db: Session, actor, form):
    """Send an alert. Returns (notification, errors).

    Raises EmergencyAccessError if the actor isn't allowed to send.
    Nothing is saved if there are errors.
    """
    if not AccessControl.can_send_emergency_notification(actor.role):
        # T2-032: log the refused attempt here.
        raise EmergencyAccessError("Only administrators can send emergency notifications.")

    values, errors = check_alert(form)
    if errors:
        return None, errors

    people = recipients_for(db, values["audience"])

    alert = EmergencyNotification(
        title=values["title"],
        message=values["message"],
        audience=values["audience"],
        sent_by=actor.user_id,
    )
    db.add(alert)
    db.flush()
    for person in people:
        db.add(EmergencyReceipt(notification_id=alert.id, user_id=person.id))
    db.commit()
    db.refresh(alert)
    # T2-032: log the send (who, audience, how many) here.
    return alert, {}


def inbox(db: Session, user_id):
    """A user's alerts, newest first, as (notification, receipt) pairs."""
    return (
        db.query(EmergencyNotification, EmergencyReceipt)
        .join(EmergencyReceipt, EmergencyReceipt.notification_id == EmergencyNotification.id)
        .filter(EmergencyReceipt.user_id == user_id)
        .order_by(EmergencyNotification.sent_at.desc(), EmergencyNotification.id.desc())
        .all()
    )


def unread_count(db: Session, user_id):
    return (
        db.query(EmergencyReceipt)
        .filter(EmergencyReceipt.user_id == user_id, EmergencyReceipt.read_at.is_(None))
        .count()
    )


def mark_read(db: Session, user_id, notification_id):
    """Mark one alert read for this user. Returns False if it wasn't sent to them."""
    receipt = (
        db.query(EmergencyReceipt)
        .filter(EmergencyReceipt.user_id == user_id,
                EmergencyReceipt.notification_id == notification_id)
        .first()
    )
    if receipt is None:
        return False
    if receipt.read_at is None:
        receipt.read_at = datetime.now(timezone.utc)
        db.commit()
    return True


def sent_history(db: Session):
    """Every alert sent, newest first, with how many people read it. Admin view."""
    rows = []
    alerts = (
        db.query(EmergencyNotification)
        .order_by(EmergencyNotification.sent_at.desc(), EmergencyNotification.id.desc())
        .all()
    )
    for alert in alerts:
        total = len(alert.receipts)
        read = sum(1 for r in alert.receipts if r.is_read())
        rows.append({"alert": alert, "total": total, "read": read})
    return rows
