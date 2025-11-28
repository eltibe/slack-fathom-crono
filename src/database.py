"""
Database configuration and session management for SQLAlchemy 2.0.

This module provides:
- Database engine configuration with connection pooling
- Session factory and context manager
- Database initialization utilities
- Support for both sync and async operations (currently sync only)
"""

import os
from contextlib import contextmanager
from typing import Generator, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, Engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from sqlalchemy.pool import QueuePool

# Load environment variables
load_dotenv()


# Database configuration from environment variables
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/slack_fathom_crono"
)
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "20"))
DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
DATABASE_POOL_TIMEOUT = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))
DATABASE_POOL_RECYCLE = int(os.getenv("DATABASE_POOL_RECYCLE", "3600"))
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "false").lower() == "true"


# SQLAlchemy 2.0 declarative base
class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Database engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=DATABASE_POOL_SIZE,
    max_overflow=DATABASE_MAX_OVERFLOW,
    pool_timeout=DATABASE_POOL_TIMEOUT,
    pool_recycle=DATABASE_POOL_RECYCLE,
    pool_pre_ping=True,  # Enable connection health checks
    echo=DATABASE_ECHO,   # Log SQL statements (dev only)
    future=True,          # Use SQLAlchemy 2.0 style
)


# Session factory
SessionFactory = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Usage:
        with get_db() as db:
            user = db.query(User).filter_by(id=user_id).first()
            db.commit()

    Yields:
        Session: SQLAlchemy database session

    Raises:
        Exception: Any database error (rolled back automatically)
    """
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Session:
    """
    Create and return a new database session.

    NOTE: Caller is responsible for closing the session.
    Consider using get_db() context manager instead.

    Returns:
        Session: SQLAlchemy database session
    """
    return SessionFactory()


def init_db() -> None:
    """
    Initialize database by creating all tables.

    WARNING: This should only be used for testing/development.
    Use Alembic migrations for production.
    """
    from src.models import Base as ModelsBase
    ModelsBase.metadata.create_all(bind=engine)
    print("✓ Database tables created successfully")


def drop_all_tables() -> None:
    """
    Drop all database tables.

    WARNING: This is destructive and should only be used in testing.
    """
    from src.models import Base as ModelsBase
    ModelsBase.metadata.drop_all(bind=engine)
    print("✓ All database tables dropped")


def check_connection() -> bool:
    """
    Check if database connection is working.

    Returns:
        bool: True if connection successful, False otherwise
    """
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False


def get_database_info() -> dict:
    """
    Get database connection information (for debugging).

    Returns:
        dict: Database configuration details
    """
    return {
        "url": str(engine.url).replace(engine.url.password or "", "***"),
        "pool_size": DATABASE_POOL_SIZE,
        "max_overflow": DATABASE_MAX_OVERFLOW,
        "pool_timeout": DATABASE_POOL_TIMEOUT,
        "pool_recycle": DATABASE_POOL_RECYCLE,
        "echo": DATABASE_ECHO,
    }


# Enable statement timeout for all connections (30 seconds)
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Set connection-level parameters on new connections."""
    # For PostgreSQL: set statement timeout
    if "postgresql" in DATABASE_URL:
        cursor = dbapi_conn.cursor()
        cursor.execute("SET statement_timeout = '30s'")
        cursor.close()


if __name__ == "__main__":
    """Test database connection."""
    print("Database Configuration:")
    print("-" * 60)
    for key, value in get_database_info().items():
        print(f"  {key}: {value}")
    print("-" * 60)

    if check_connection():
        print("✓ Database connection successful!")
    else:
        print("✗ Database connection failed!")
