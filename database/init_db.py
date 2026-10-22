import os

from database.database import Base, engine, SessionLocal
from database.models import Role, User
from database import models
from database import scheduling  # noqa: F401  needs importing or create_all skips it

# Login now checks the users table instead of a hardcoded account, so a
# fresh database needs one admin or nobody can get in at all.
ADMIN_USERNAME = "admin"
ENV_ADMIN_PASSWORD = "SMS_ADMIN_PASSWORD"
DEV_ADMIN_PASSWORD = "password123"  # same as the old hardcoded one


def seed_roles():
    db = SessionLocal()

    roles = [
        "Admin",
        "Teacher",
        "Student",
        "Parent"
    ]

    try:
        for role_name in roles:
            existing_role = (
                db.query(Role)
                .filter(Role.name == role_name)
                .first()
            )

            if existing_role is None:
                db.add(Role(name=role_name))

        db.commit()

    finally:
        db.close()


def seed_admin():
    """Create the starting admin account if there isn't one.

    Password comes from SMS_ADMIN_PASSWORD. If that isn't set we fall back
    to the same password the old hardcoded login used, so the demo keeps
    working, and print a warning because a known password in a school
    records system is not something to leave sitting there quietly.
    """
    from utils.security import hash_password

    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == ADMIN_USERNAME).first():
            return

        admin_role = db.query(Role).filter(Role.name == "Admin").first()
        if admin_role is None:
            raise RuntimeError("Admin role missing, seed_roles has to run first")

        password = os.environ.get(ENV_ADMIN_PASSWORD) or DEV_ADMIN_PASSWORD
        if password == DEV_ADMIN_PASSWORD:
            print(
                f"  WARNING: created '{ADMIN_USERNAME}' with the default development "
                f"password. Set {ENV_ADMIN_PASSWORD} before this goes anywhere real."
            )

        db.add(User(
            username=ADMIN_USERNAME,
            password_hash=hash_password(password),
            first_name="System",
            last_name="Administrator",
            email="admin@school.edu",
            role_id=admin_role.id,
        ))
        db.commit()
    finally:
        db.close()


def init_db():
    # Imported here so create_all sees them.
    from database import students    # noqa: F401  SIEM-004
    from database import audit       # noqa: F401  T1-014
    from database import attendance  # noqa: F401  T2-002
    from database import grades      # noqa: F401  T2-012
    from database import announcements  # noqa: F401  T2-023

    Base.metadata.create_all(bind=engine)
    seed_roles()
    seed_admin()


if __name__ == "__main__":
    init_db()
    print("Database initialized.")