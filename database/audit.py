"""Audit trail for student record access. UMA-003 / T1-014.

Project doc asks for immutable audit logs, so this is append only, no
update or delete anywhere. Denied attempts get logged too, those are the
ones worth having.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from database.database import Base

# What happened
VIEW = "view"
LIST = "list"
CREATE = "create"

# How it went
ALLOWED = "allowed"
DENIED = "denied"


def utcnow():
    return datetime.now(timezone.utc)


class AccessLog(Base):
    """One row per attempt to reach a student record.

    No record contents in here. Copying an address in to prove someone
    read it would just leave a plaintext copy somewhere else.
    """

    __tablename__ = "access_log"

    id = Column(Integer, primary_key=True, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    # Role as it was at the time. Looking it up later would show their
    # current one instead.
    actor_user_id = Column(Integer, nullable=True, index=True)
    actor_role = Column(String, nullable=True)

    action = Column(String, nullable=False)        # view / list / create
    resource_type = Column(String, nullable=False)  # "student"
    resource_id = Column(Integer, nullable=True, index=True)
    outcome = Column(String, nullable=False)       # allowed / denied

    # Short note, e.g. how many rows a list returned. Never record contents.
    detail = Column(String, nullable=True)
