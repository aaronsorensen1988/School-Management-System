from database.database import Base, engine, SessionLocal
from database.models import Role
from database import models
from database import scheduling  # noqa: F401  needs importing or create_all skips it


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


def init_db():
    # Student profile table (SIEM-004). Imported here so create_all sees it.
    from database import students  # noqa: F401

    Base.metadata.create_all(bind=engine)
    seed_roles()


if __name__ == "__main__":
    init_db()
    print("Database initialized.")