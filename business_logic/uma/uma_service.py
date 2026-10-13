from database.database import SessionLocal
from database.models import Role, User


class UmaService:
    """Handles user-managment and role-related business logic."""

    VALID_ROLES = {"Admin", "Teacher", "Student", "Parent"}
    def get_user_profile(self, user_id):
        return {
            "user_id": user_id,
            "name": "Test User",
            "role": "student"
        }

    def assign_role(self, user_id, role_name):
        # Normalize input so values such as "teacher" and " TEACHER "
        # resolve to the same stored role name.
        normalized_role = role_name.strip().title()

        if normalized_role not in self.VALID_ROLES:
            raise ValueError(f"Invalid role: {role_name}")
        
        db = SessionLocal()

        try:
            user = db.query(User).filter(User.id == user_id).first()

            if user is None:
                raise ValueError(f"User {user_id} not found")

            role = db.query(Role).filter(Role.name == normalized_role).first()

            if role is None:
                raise ValueError(f"Role {normalized_role} not found")

            # Assign the selected role through its foreign-key ID.
            user.role_id = role.id

            db.commit()
            db.refresh(user)

            return role.name

        except:
            # Prevent partial database changes if the operation fails.
            db.rollback()
            raise

        finally:
            db.close()
