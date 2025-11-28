"""
API Rate Limit model - Tracks API usage for rate limiting and quota management.

Implements token bucket / sliding window rate limiting for different resources
(meetings processed, API calls, CRM writes) per tenant.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey,
    CheckConstraint, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship, Session

from src.models.base import Base, BaseModel


class APIRateLimit(Base, BaseModel):
    """
    API Rate Limit model for tracking and enforcing usage limits.

    Tracks usage per tenant for different resources:
    - meetings_processed: Number of meetings processed
    - api_calls: Total API calls made
    - crm_writes: Number of CRM write operations

    Each rate limit has:
    - Resource type (what is being limited)
    - Time period (minute, hourly, daily, monthly)
    - Limit value (max allowed in period)
    - Current count (usage so far)
    - Period boundaries (start/end timestamps)

    Relationships:
    - tenant: Many-to-one with Tenant model
    """

    __tablename__ = "api_rate_limits"

    # Foreign key to tenant
    tenant_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to tenant (Slack workspace)"
    )

    # Rate limit configuration
    resource_type = Column(
        String(50),
        nullable=False,
        comment="Resource being limited: meetings_processed, api_calls, crm_writes"
    )

    limit_period = Column(
        String(20),
        nullable=False,
        comment="Time period: minute, hourly, daily, monthly"
    )

    limit_value = Column(
        Integer,
        nullable=False,
        comment="Maximum allowed in period"
    )

    # Current usage
    current_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Current usage count in this period"
    )

    period_start = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Start of the current period"
    )

    period_end = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="End of the current period"
    )

    # Relationships
    tenant = relationship(
        "Tenant",
        back_populates="api_rate_limits"
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "resource_type", "period_start",
            name="uq_rate_limit_tenant_resource_period"
        ),
        CheckConstraint(
            "limit_period IN ('minute', 'hourly', 'daily', 'monthly')",
            name="valid_limit_period"
        ),
        CheckConstraint(
            "limit_value > 0",
            name="positive_limit_value"
        ),
        CheckConstraint(
            "current_count >= 0",
            name="non_negative_current_count"
        ),
        Index("idx_api_rate_limits_tenant_resource", "tenant_id", "resource_type", "period_start"),
        Index(
            "idx_api_rate_limits_period",
            "period_end",
            postgresql_where=(Column("current_count") >= Column("limit_value"))
        ),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<APIRateLimit(id={self.id}, resource={self.resource_type}, "
            f"period={self.limit_period}, count={self.current_count}/{self.limit_value})>"
        )

    @property
    def is_exceeded(self) -> bool:
        """Check if rate limit has been exceeded."""
        return self.current_count >= self.limit_value

    @property
    def is_expired(self) -> bool:
        """Check if the current period has expired."""
        return datetime.now() >= self.period_end

    @property
    def remaining(self) -> int:
        """Get remaining quota in current period."""
        return max(0, self.limit_value - self.current_count)

    @property
    def usage_percentage(self) -> float:
        """Get usage as percentage (0-100)."""
        if self.limit_value == 0:
            return 100.0
        return (self.current_count / self.limit_value) * 100.0

    def increment(self, amount: int = 1) -> bool:
        """
        Increment the usage counter.

        Args:
            amount: Amount to increment (default 1)

        Returns:
            bool: True if increment successful, False if limit exceeded
        """
        if self.is_exceeded:
            return False

        self.current_count += amount
        return True

    def reset(self) -> None:
        """Reset the counter for a new period."""
        self.current_count = 0
        self.period_start = datetime.now()
        self.period_end = self._calculate_period_end(self.limit_period)

    @staticmethod
    def _calculate_period_end(period: str, start: Optional[datetime] = None) -> datetime:
        """
        Calculate the end of a period based on period type.

        Args:
            period: Period type (minute, hourly, daily, monthly)
            start: Start time (defaults to now)

        Returns:
            datetime: End of the period
        """
        if start is None:
            start = datetime.now()

        if period == 'minute':
            return start + timedelta(minutes=1)
        elif period == 'hourly':
            return start + timedelta(hours=1)
        elif period == 'daily':
            return start + timedelta(days=1)
        elif period == 'monthly':
            # Calculate next month (handle year rollover)
            if start.month == 12:
                return start.replace(year=start.year + 1, month=1)
            else:
                return start.replace(month=start.month + 1)
        else:
            raise ValueError(f"Invalid period: {period}")

    @classmethod
    def get_or_create(
        cls,
        session: Session,
        tenant_id: UUID,
        resource_type: str,
        limit_period: str,
        limit_value: int
    ) -> "APIRateLimit":
        """
        Get existing rate limit or create a new one.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            resource_type: Resource type to limit
            limit_period: Time period (minute, hourly, daily, monthly)
            limit_value: Maximum allowed in period

        Returns:
            APIRateLimit instance
        """
        now = datetime.now()

        # Try to get existing active rate limit
        rate_limit = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.resource_type == resource_type)
            .filter(cls.limit_period == limit_period)
            .filter(cls.period_start <= now)
            .filter(cls.period_end > now)
            .filter(cls.deleted_at.is_(None))
            .first()
        )

        if rate_limit:
            return rate_limit

        # Create new rate limit
        period_start = now
        period_end = cls._calculate_period_end(limit_period, period_start)

        rate_limit = cls(
            tenant_id=tenant_id,
            resource_type=resource_type,
            limit_period=limit_period,
            limit_value=limit_value,
            current_count=0,
            period_start=period_start,
            period_end=period_end
        )
        session.add(rate_limit)
        session.flush()

        return rate_limit

    @classmethod
    def check_limit(
        cls,
        session: Session,
        tenant_id: UUID,
        resource_type: str,
        limit_period: str,
        limit_value: int
    ) -> tuple[bool, Optional["APIRateLimit"]]:
        """
        Check if a rate limit would be exceeded.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            resource_type: Resource type to check
            limit_period: Time period
            limit_value: Maximum allowed in period

        Returns:
            Tuple of (is_allowed, rate_limit_instance)
        """
        rate_limit = cls.get_or_create(
            session, tenant_id, resource_type, limit_period, limit_value
        )

        # If period expired, reset it
        if rate_limit.is_expired:
            rate_limit.reset()
            session.flush()

        return (not rate_limit.is_exceeded, rate_limit)

    @classmethod
    def increment_usage(
        cls,
        session: Session,
        tenant_id: UUID,
        resource_type: str,
        limit_period: str,
        limit_value: int,
        amount: int = 1
    ) -> tuple[bool, "APIRateLimit"]:
        """
        Increment usage counter for a rate limit.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            resource_type: Resource type
            limit_period: Time period
            limit_value: Maximum allowed in period
            amount: Amount to increment (default 1)

        Returns:
            Tuple of (was_incremented, rate_limit_instance)
        """
        rate_limit = cls.get_or_create(
            session, tenant_id, resource_type, limit_period, limit_value
        )

        # If period expired, reset it
        if rate_limit.is_expired:
            rate_limit.reset()

        success = rate_limit.increment(amount)
        session.flush()

        return (success, rate_limit)

    @classmethod
    def get_tenant_limits(
        cls,
        session: Session,
        tenant_id: UUID,
        resource_type: Optional[str] = None,
        active_only: bool = True
    ) -> List["APIRateLimit"]:
        """
        Get all rate limits for a tenant.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            resource_type: Optional filter by resource type
            active_only: Only return active (non-expired) limits

        Returns:
            List of APIRateLimit instances
        """
        query = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.deleted_at.is_(None))
        )

        if resource_type:
            query = query.filter(cls.resource_type == resource_type)

        if active_only:
            now = datetime.now()
            query = query.filter(cls.period_end > now)

        query = query.order_by(
            cls.resource_type.asc(),
            cls.limit_period.asc()
        )

        return query.all()

    @classmethod
    def get_exceeded_limits(
        cls,
        session: Session,
        tenant_id: Optional[UUID] = None
    ) -> List["APIRateLimit"]:
        """
        Get all currently exceeded rate limits.

        Args:
            session: Database session
            tenant_id: Optional tenant filter

        Returns:
            List of exceeded APIRateLimit instances
        """
        now = datetime.now()

        query = (
            session.query(cls)
            .filter(cls.current_count >= cls.limit_value)
            .filter(cls.period_end > now)
            .filter(cls.deleted_at.is_(None))
        )

        if tenant_id:
            query = query.filter(cls.tenant_id == tenant_id)

        return query.all()

    @classmethod
    def cleanup_expired(
        cls,
        session: Session,
        days_old: int = 30
    ) -> int:
        """
        Clean up expired rate limit records.

        Args:
            session: Database session
            days_old: Delete records older than this many days

        Returns:
            Number of records deleted
        """
        cutoff_date = datetime.now() - timedelta(days=days_old)

        deleted_count = (
            session.query(cls)
            .filter(cls.period_end < cutoff_date)
            .delete(synchronize_session=False)
        )

        session.flush()
        return deleted_count
