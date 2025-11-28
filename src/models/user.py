"""
User model - Represents Slack users within tenant workspaces.

Users are scoped to tenants (Slack workspaces) and can have different
roles and preferences within their workspace.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey,
    CheckConstraint, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship, Session

from src.models.base import Base, BaseModel


class User(Base, BaseModel):
    """
    User model representing Slack users within a workspace.

    Each user belongs to a specific tenant (Slack workspace) and can have
    their own preferences, role, and activity tracking.

    Relationships:
    - tenant: Many-to-one with Tenant model
    - meeting_sessions: One-to-many with MeetingSession model
    - created_crm_connections: One-to-many with CRMConnection (as creator)
    - created_account_mappings: One-to-many with AccountMapping (as creator)
    - audit_logs: One-to-many with AuditLog model
    """

    __tablename__ = "users"

    # Foreign key to tenant
    tenant_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to tenant (Slack workspace)"
    )

    # Slack user identification
    slack_user_id = Column(
        String(20),
        nullable=False,
        comment="Slack User ID (e.g., U0123456789)"
    )

    slack_username = Column(
        String(255),
        nullable=True,
        comment="Slack username (display name)"
    )

    slack_email = Column(
        String(255),
        nullable=True,
        comment="Slack user email address"
    )

    slack_real_name = Column(
        String(255),
        nullable=True,
        comment="Slack user real name"
    )

    # User preferences
    preferred_language = Column(
        String(10),
        nullable=False,
        default='en',
        comment="User's preferred language (e.g., en, it, es)"
    )

    notification_settings = Column(
        JSONB,
        nullable=False,
        default={"email_drafts": True, "calendar_events": True},
        comment="User notification preferences (JSONB)"
    )

    # Role and permissions
    role = Column(
        String(50),
        nullable=False,
        default='member',
        comment="User role: admin, member"
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether user is active in workspace"
    )

    # Activity tracking
    first_seen_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(),
        comment="When user first interacted with the bot"
    )

    last_active_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When user last interacted with the bot"
    )

    # Relationships
    tenant = relationship(
        "Tenant",
        back_populates="users"
    )

    meeting_sessions = relationship(
        "MeetingSession",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select"
    )

    created_crm_connections = relationship(
        "CRMConnection",
        back_populates="connected_by_user",
        foreign_keys="CRMConnection.connected_by_user_id",
        lazy="select"
    )

    created_account_mappings = relationship(
        "AccountMapping",
        back_populates="created_by_user",
        foreign_keys="AccountMapping.created_by_user_id",
        lazy="select"
    )

    audit_logs = relationship(
        "AuditLog",
        back_populates="user",
        lazy="select"
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "slack_user_id",
            name="uq_user_tenant_slack_id"
        ),
        CheckConstraint(
            "role IN ('admin', 'member')",
            name="valid_role"
        ),
        Index("idx_users_tenant_id", "tenant_id"),
        Index("idx_users_slack_user_id", "tenant_id", "slack_user_id"),
        Index("idx_users_last_active", "last_active_at", postgresql_using="btree"),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<User(id={self.id}, slack_user_id={self.slack_user_id}, "
            f"email={self.slack_email}, role={self.role})>"
        )

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.role == 'admin'

    def update_last_active(self) -> None:
        """Update last_active_at timestamp to now."""
        self.last_active_at = datetime.now()

    @classmethod
    def get_by_slack_user_id(
        cls,
        session: Session,
        tenant_id: UUID,
        slack_user_id: str,
        include_deleted: bool = False
    ) -> Optional["User"]:
        """
        Get user by tenant ID and Slack user ID.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            slack_user_id: Slack user ID (e.g., U0123456789)
            include_deleted: Include soft-deleted users

        Returns:
            User instance or None
        """
        query = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.slack_user_id == slack_user_id)
        )

        if not include_deleted:
            query = query.filter(cls.deleted_at.is_(None))

        return query.first()

    @classmethod
    def get_tenant_users(
        cls,
        session: Session,
        tenant_id: UUID,
        active_only: bool = True,
        include_deleted: bool = False
    ) -> List["User"]:
        """
        Get all users for a specific tenant.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            active_only: Only return active users
            include_deleted: Include soft-deleted users

        Returns:
            List of User instances
        """
        query = session.query(cls).filter(cls.tenant_id == tenant_id)

        if active_only:
            query = query.filter(cls.is_active == True)

        if not include_deleted:
            query = query.filter(cls.deleted_at.is_(None))

        return query.all()

    @classmethod
    def get_admins(
        cls,
        session: Session,
        tenant_id: UUID,
        include_deleted: bool = False
    ) -> List["User"]:
        """
        Get all admin users for a tenant.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            include_deleted: Include soft-deleted users

        Returns:
            List of admin User instances
        """
        query = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.role == 'admin')
            .filter(cls.is_active == True)
        )

        if not include_deleted:
            query = query.filter(cls.deleted_at.is_(None))

        return query.all()

    @classmethod
    def get_recently_active(
        cls,
        session: Session,
        tenant_id: UUID,
        days: int = 30,
        limit: Optional[int] = None
    ) -> List["User"]:
        """
        Get recently active users within a tenant.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            days: Number of days to look back
            limit: Maximum number of results

        Returns:
            List of recently active User instances
        """
        cutoff_date = datetime.now() - datetime.timedelta(days=days)

        query = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.last_active_at >= cutoff_date)
            .filter(cls.deleted_at.is_(None))
            .order_by(cls.last_active_at.desc())
        )

        if limit:
            query = query.limit(limit)

        return query.all()
