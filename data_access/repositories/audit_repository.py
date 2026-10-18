"""Writing to the audit trail. UMA-003 / T1-014.

Only a write path. There's deliberately no update or delete, and reads are
a separate concern for whoever builds the compliance view in Sprint 2.

    record(db, actor, VIEW, "student", student_id, ALLOWED)
"""

from sqlalchemy.orm import Session

from database.audit import AccessLog, utcnow


def record(db: Session, actor, action, resource_type, resource_id=None,
           outcome="allowed", detail=None) -> AccessLog:
    """Add one row. Flushes but doesn't commit, so it rides along with
    whatever transaction the caller is in."""
    entry = AccessLog(
        occurred_at=utcnow(),
        actor_user_id=getattr(actor, "user_id", None),
        actor_role=getattr(actor, "role", None),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        detail=detail,
    )
    db.add(entry)
    db.flush()
    return entry
