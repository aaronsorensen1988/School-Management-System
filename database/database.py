from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = "sqlite:///./school_management.db"

# SQLite requires this option when the same connection may be used
# across multiple threads, such as during FastAPI requests.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Creates database sessions used by the service and repository layers.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class inherited by all SQLAlchemy models.
Base = declarative_base()