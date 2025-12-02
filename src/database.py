"""
Database configuration and session management for SQLAlchemy 2.0.

This refactored module uses a DatabaseManager class to encapsulate all
database connection logic, ensuring a single, managed point of entry.
"""

import os
import sys
from contextlib import contextmanager
from typing import Generator, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, Engine, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError

# Load environment variables from .env file
load_dotenv()


class DatabaseManager:
    """A centralized manager for database connections and sessions."""

    def __init__(self):
        self.engine: Optional[Engine] = None
        self.SessionFactory: Optional[sessionmaker[Session]] = None
        self._load_config()

    def _load_config(self):
        """Load database configuration from environment variables."""
        self.db_url = os.getenv("DATABASE_URL")
        self.pool_size = int(os.getenv("DATABASE_POOL_SIZE", "20"))
        self.max_overflow = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
        self.pool_timeout = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))
        self.pool_recycle = int(os.getenv("DATABASE_POOL_RECYCLE", "3600"))
        self.echo = os.getenv("DATABASE_ECHO", "false").lower() == "true"

    def connect(self):
        """Create the database engine and session factory."""
        # Reload config in case environment vars changed after import
        self._load_config()
        if not self.db_url:
            raise ValueError("DATABASE_URL is not set. Please configure it in your environment.")

        try:
            self.engine = create_engine(
                self.db_url,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,
                pool_recycle=self.pool_recycle,
                pool_pre_ping=True,
                echo=self.echo,
                future=True,
            )

            self.SessionFactory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
                future=True,
            )
            self._register_event_listeners()
            print("✓ Database engine created successfully.")
        except Exception as e:
            print(f"❌ Failed to create database engine: {e}", file=sys.stderr)
            raise

    def check_connection(self) -> bool:
        """
        Verify that a connection can be established to the database.
        Returns True on success, raises an exception on failure.
        """
        if not self.engine:
            print("❌ Database engine not initialized. Call connect() first.", file=sys.stderr)
            return False
        
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✓ Database connection verified successfully.")
            return True
        except OperationalError as e:
            print(f"❌ Database connection failed: An OperationalError occurred.", file=sys.stderr)
            print(f"  Error: {e}", file=sys.stderr)
            print(f"  Is the database running and accessible at the configured URL?", file=sys.stderr)
            print(f"  URL: {str(self.engine.url).replace(self.engine.url.password or '', '***')}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"❌ An unexpected error occurred during database connection check: {e}", file=sys.stderr)
            raise

    def get_session(self) -> Session:
        """Get a new database session."""
        if not self.SessionFactory:
            raise RuntimeError("SessionFactory not initialized. Call connect() first.")
        return self.SessionFactory()
        
    def get_database_info(self) -> dict:
        """Get database connection information (for debugging)."""
        if not self.engine:
            return {"error": "Engine not initialized."}
        return {
            "url": str(self.engine.url).replace(self.engine.url.password or "", "***"),
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "pool_timeout": self.pool_timeout,
            "pool_recycle": self.pool_recycle,
            "echo": self.echo,
        }

    def _register_event_listeners(self):
        """Register SQLAlchemy event listeners."""
        if not self.engine:
            return

        @event.listens_for(self.engine, "connect")
        def set_statement_timeout(dbapi_conn, connection_record):
            """Set statement timeout for new connections to prevent long-running queries."""
            if "postgresql" in self.db_url:
                cursor = dbapi_conn.cursor()
                try:
                    cursor.execute("SET statement_timeout = '30s'")
                finally:
                    cursor.close()

# --- Global Database Manager Instance ---
db_manager = DatabaseManager()
# Attempt connection at import time if DATABASE_URL is set (dev convenience)
try:
    if db_manager.db_url:
        db_manager.connect()
except Exception as e:
    # In dev, log and continue; callers can handle connection separately
    sys.stderr.write(f"Warning: automatic DB connect failed: {e}\n")
    sys.stderr.flush()

# Expose engine for legacy imports
engine = db_manager.engine


# --- SQLAlchemy Base and Session Context ---

class Base(DeclarativeBase):
    """Base class for all database models."""
    pass

@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager for providing a transactional database session.
    """
    session = db_manager.get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --- Database Initialization Utilities (for dev/test) ---

def init_db() -> None:
    """
    Initialize database by creating all tables.
    WARNING: Use Alembic migrations for production.
    """
    if not db_manager.engine:
        raise RuntimeError("Database not connected. Call db_manager.connect() before initializing.")
    from src.models import Base as ModelsBase
    ModelsBase.metadata.create_all(bind=db_manager.engine)
    print("✓ Database tables created successfully")


def drop_all_tables() -> None:
    """
    Drop all database tables.
    WARNING: This is destructive and for testing only.
    """
    if not db_manager.engine:
        raise RuntimeError("Database not connected.")
    from src.models import Base as ModelsBase
    ModelsBase.metadata.drop_all(bind=db_manager.engine)
    print("✓ All database tables dropped")

# Example of direct execution for testing the connection
if __name__ == "__main__":
    print("--- Testing DatabaseManager ---")
    try:
        db_manager.connect()
        db_manager.check_connection()
        print("\nDatabase Info:")
        for key, value in db_manager.get_database_info().items():
            print(f"  {key}: {value}")
    except Exception as e:
        print(f"\n--- Test Failed: {e} ---", file=sys.stderr)
        sys.exit(1)
