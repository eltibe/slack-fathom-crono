"""
Base model class with common fields and methods for all database models.

Provides:
- UUID primary keys
- Automatic timestamp management (created_at, updated_at)
- Soft delete support (deleted_at)
- Common query methods
- Serialization to dict
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Type, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, event
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import declarative_mixin, declared_attr, Session

from src.database import Base as SQLAlchemyBase


T = TypeVar('T', bound='BaseModel')


@declarative_mixin
class BaseModel:
    """
    Abstract base model with common fields and functionality.

    All models inherit these fields:
    - id: UUID primary key
    - created_at: Timestamp when record was created
    - updated_at: Timestamp when record was last updated
    - deleted_at: Timestamp when record was soft-deleted (NULL if active)

    Usage:
        class MyModel(Base, BaseModel):
            __tablename__ = 'my_table'
            name = Column(String(255))
    """

    @declared_attr
    def __tablename__(cls) -> str:
        """Generate table name from class name (override in subclasses)."""
        return cls.__name__.lower()

    # Primary key - UUID
    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
        comment="Unique identifier (UUID)"
    )

    # Timestamp fields
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Timestamp when record was created"
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Timestamp when record was last updated"
    )

    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Timestamp when record was soft-deleted (NULL if active)"
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<{self.__class__.__name__}(id={self.id})>"

    def to_dict(self, exclude: Optional[set] = None) -> Dict[str, Any]:
        """
        Convert model instance to dictionary.

        Args:
            exclude: Set of field names to exclude from output

        Returns:
            dict: Model data as dictionary

        Example:
            user_dict = user.to_dict(exclude={'password_hash'})
        """
        exclude = exclude or set()
        data = {}

        for column in self.__table__.columns:
            if column.name in exclude:
                continue

            value = getattr(self, column.name)

            # Convert special types to serializable formats
            if isinstance(value, UUID):
                value = str(value)
            elif isinstance(value, datetime):
                value = value.isoformat()

            data[column.name] = value

        return data

    def soft_delete(self) -> None:
        """
        Soft delete this record by setting deleted_at timestamp.

        Does not commit - caller must commit the session.
        """
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """
        Restore a soft-deleted record by clearing deleted_at.

        Does not commit - caller must commit the session.
        """
        self.deleted_at = None

    @property
    def is_deleted(self) -> bool:
        """Check if record is soft-deleted."""
        return self.deleted_at is not None

    @classmethod
    def get_by_id(
        cls: Type[T],
        session: Session,
        record_id: UUID,
        include_deleted: bool = False
    ) -> Optional[T]:
        """
        Get a single record by ID.

        Args:
            session: Database session
            record_id: UUID of the record
            include_deleted: If True, include soft-deleted records

        Returns:
            Model instance or None if not found

        Example:
            user = User.get_by_id(session, user_id)
        """
        query = session.query(cls).filter(cls.id == record_id)

        if not include_deleted:
            query = query.filter(cls.deleted_at.is_(None))

        return query.first()

    @classmethod
    def get_all(
        cls: Type[T],
        session: Session,
        include_deleted: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> list[T]:
        """
        Get all records of this type.

        Args:
            session: Database session
            include_deleted: If True, include soft-deleted records
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of model instances

        Example:
            users = User.get_all(session, limit=100)
        """
        query = session.query(cls)

        if not include_deleted:
            query = query.filter(cls.deleted_at.is_(None))

        if offset:
            query = query.offset(offset)

        if limit:
            query = query.limit(limit)

        return query.all()

    @classmethod
    def count(
        cls: Type[T],
        session: Session,
        include_deleted: bool = False
    ) -> int:
        """
        Count total records of this type.

        Args:
            session: Database session
            include_deleted: If True, include soft-deleted records

        Returns:
            int: Total count of records
        """
        query = session.query(cls)

        if not include_deleted:
            query = query.filter(cls.deleted_at.is_(None))

        return query.count()


# SQLAlchemy event listeners for automatic timestamp updates
@event.listens_for(BaseModel, 'before_insert', propagate=True)
def receive_before_insert(mapper, connection, target):
    """Set created_at and updated_at on insert."""
    now = datetime.now(timezone.utc)
    target.created_at = now
    target.updated_at = now


@event.listens_for(BaseModel, 'before_update', propagate=True)
def receive_before_update(mapper, connection, target):
    """Update updated_at on update."""
    target.updated_at = datetime.now(timezone.utc)


# Export Base class for use in models
Base = SQLAlchemyBase
