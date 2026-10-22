"""Who's logged in. UMA-002, wiring for T1-013.

Users and roles existed and login ignored them, so nothing knew who you
were and the role checks had nobody to check. This connects them.

Signed cookie session. Role gets re-read from the db each request so
changing someone's role takes effect right away.
"""

import hashlib
import os

from sqlalchemy.orm import Session

from data_access.repositories.student_repository import ANONYMOUS, Actor
from database.models import Role, User
from database.parents import ParentStudent

SESSION_USER_ID = "user_id"
SESSION_USERNAME = "username"
ENV_SECRET = "SMS_SESSION_SECRET"

# How long a session lasts. Short because this is a school records system
# and a shared classroom computer is the normal case.
SESSION_MAX_AGE = 60 * 60 * 2  # 2 hours


def session_secret() -> str:
    """Key the session cookie is signed with.

    Set SMS_SESSION_SECRET for real. Otherwise it's derived from the
    encryption key so a fresh checkout only needs one variable.
    """
    explicit = (os.environ.get(ENV_SECRET) or "").strip()
    if explicit:
        return explicit

    from security.keys import active_keyring

    _, key = active_keyring().active()
    return hashlib.sha256(b"sms-session\x00" + key).hexdigest()


def login_user(request, user: User) -> None:
    request.session[SESSION_USER_ID] = user.id
    request.session[SESSION_USERNAME] = user.username


def logout_user(request) -> None:
    request.session.clear()


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Check username and password against the users table.

    Same None for "no such user" and "wrong password", otherwise you can
    work out which usernames exist.
    """
    from utils.security import verify_password

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def current_actor(request, db: Session) -> Actor:
    """Actor from the session, or ANONYMOUS if not logged in.

    Role comes from the db, not the cookie, so demoting someone takes
    effect on their next click.

    Rosters and parent links don't exist yet (Sprint 2), so teachers and
    parents currently see nobody. Safe direction to be wrong in.
    """
    user_id = request.session.get(SESSION_USER_ID)
    if not user_id:
        return ANONYMOUS

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        # Account deleted while they were logged in.
        request.session.clear()
        return ANONYMOUS

    role = db.query(Role).filter(Role.id == user.role_id).first()
    role_name = role.name if role else None

    child_ids = ()

    if role_name == "Parent":
        child_ids = tuple(
            row.student_id
            for row in (
                db.query(ParentStudent)
                .filter(ParentStudent.parent_user_id == user.id)
                .all()
            )
        )

    return Actor(
        user_id=user.id,
        role=role_name,
        child_ids=child_ids,
    )
