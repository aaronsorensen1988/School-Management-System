"""Writing to the audit trail. UMA-003 / T1-014.

Only a write path. There's deliberately no update or delete, and reads are
a separate concern for whoever builds the compliance view in Sprint 2.

    record(db, actor, VIEW, "student", student_id, ALLOWED)
"""

from sqlalchemy.orm import Session, sessionmaker

from database.audit import AccessLog, utcnow


def _entry(actor, action, resource_type, resource_id=None,
           outcome="allowed", detail=None):
    return AccessLog(
        occurred_at=utcnow(),
        actor_user_id=getattr(actor, "user_id", None),
        actor_role=getattr(actor, "role", None),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        detail=detail,
    )

def record(db: Session, actor, action, resource_type, resource_id=None,
           outcome="allowed", detail=None) -> AccessLog:
    """Write an audit row as part of the caller's transaction."""
    entry = _entry(
        actor, action, resource_type, resource_id, outcome, detail
    )
    db.add(entry)
    db.flush()
    return entry

def record_independent(db: Session, actor, action, resource_type,
                       resource_id=None, outcome="allowed", detail=None) -> AccessLog:
    """Write and commit an audit row without committing the caller's session."""
    AuditSession = sessionmaker(
        bind=db.get_bind(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    audit_db = AuditSession()
    try:
        entry = _entry(
            actor, action, resource_type, resource_id, outcome, detail
        )
        audit_db.add(entry)
        audit_db.commit()
        return entry
    except Exception:
        audit_db.rollback()
        raise
    finally:
        audit_db.close()
