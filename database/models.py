from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from database.grades import Assignment, Grade

from database.database import Base


class Role(Base):
    """Represents one of the application's supported user roles."""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    # Allows role.users to access all users assigned to this role.
    users = relationship("User", back_populates="role")


class User(Base):
    """Stores core account information and the user's assigned role."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)

    # Stores the resulting password hash, not a plaintext password.
    password_hash = Column(String, nullable=False)

    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)

    # Links each user to one role in the roles table.
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)

    role = relationship("Role", back_populates="users")