"""
Tenant model - Represents Slack workspaces (isolated tenants).

Each Slack workspace is a tenant with its own isolated data, CRM connections,
users, and settings. This is the root of the multi-tenant data hierarchy.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from sqlalchemy import (
    Column, String, DateTime, CheckConstraint, Index
)
from sqlalchemy.orm import relationship, Session

from src.models.base import Base, BaseModel
from src.models.user_settings import UserSettings # NEW


class Tenant(Base, BaseModel):
    """
    Tenant model representing a Slack workspace.

    Each tenant is an isolated customer with their own:
    - Users (Slack workspace members)
    - CRM connections (HubSpot, Salesforce, Crono, etc.)
    - Meeting sessions and data
    - Settings and configuration

    Relationships:
    - users: One-to-many with User model
    - crm_connections: One-to-many with CRMConnection model
    - meeting_sessions: One-to-many with MeetingSession model
    - account_mappings: One-to-many with AccountMapping model
    - api_rate_limits: One-to-many with APIRateLimit model
    - user_settings: One-to-many with UserSettings model (NEW)
    """

    __tablename__ = "tenants"

    # Slack workspace identification
    slack_team_id = Column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="Slack Team ID (e.g., T0123456789)"
    )

    slack_team_name = Column(
        String(255),
        nullable=False,
        comment="Workspace display name"
    )

    slack_team_domain = Column(
        String(255),
        nullable=True,
        comment="Workspace domain (e.g., mycompany.slack.com)"
    )

    # Subscription and billing
    plan_tier = Column(
        String(50),
        nullable=False,
        default='free',
        comment="Subscription plan: free, starter, pro, enterprise"
    )

    subscription_status = Column(
        String(50),
        nullable=True,
        default='active',
        comment="Subscription status: active, trial, suspended, cancelled"
    )

    trial_ends_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When trial period ends (if applicable)"
    )

    # Slack app installation
    slack_bot_token_secret_id = Column(
        String(255),
        nullable=True,
        comment="AWS Secrets Manager ID for bot token"
    )

    slack_app_id = Column(
        String(20),
        nullable=True,
        comment="Slack App ID"
    )

    installed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(),
        comment="When the app was installed"
    )

    installed_by_user_id = Column(
        String(20),
        nullable=True,
        comment="Slack user ID who installed the app"
    )

    # Settings
    default_crm_provider = Column(
        String(50),
        nullable=True,
        comment="Default CRM provider: crono, hubspot, salesforce, pipedrive"
    )

    timezone = Column(
        String(50),
        nullable=False,
        default='UTC',
        comment="Workspace timezone"
    )

    locale = Column(
        String(10),
        nullable=False,
        default='en',
        comment="Workspace locale (language)"
    )

    # Relationships
    users = relationship(
        "User",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="select"
    )

    crm_connections = relationship(
        "CRMConnection",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="select"
    )

    meeting_sessions = relationship(
        "MeetingSession",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="select"
    )

    account_mappings = relationship(
        "AccountMapping",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="select"
    )

    api_rate_limits = relationship(
        "APIRateLimit",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="select"
    )

    audit_logs = relationship(
        "AuditLog",
        back_populates="tenant",
        lazy="select"
    )

    user_settings = relationship(
        "UserSettings",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="select"
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "plan_tier IN ('free', 'starter', 'pro', 'enterprise')",
            name="valid_plan_tier"
        ),
        CheckConstraint(
            "subscription_status IN ('active', 'trial', 'suspended', 'cancelled')",
            name="valid_subscription_status"
        ),
        Index(
            "idx_tenants_subscription_status",
            "subscription_status",
            postgresql_where=(Column("deleted_at").is_(None))
        ),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<Tenant(id={self.id}, slack_team_id={self.slack_team_id}, "
            f"name={self.slack_team_name}, plan={self.plan_tier})>"
        )

    @property
    def is_active(self) -> bool:
        """Check if tenant subscription is active."""
        return self.subscription_status in ('active', 'trial')

    @property
    def is_trial(self) -> bool:
        """Check if tenant is on trial."""
        return self.subscription_status == 'trial'

    @property
    def trial_expired(self) -> bool:
        """Check if trial period has expired."""
        if not self.trial_ends_at:
            return False
        return datetime.now() > self.trial_ends_at

    @classmethod
    def get_by_slack_team_id(
        cls,
        session: Session,
        slack_team_id: str,
        include_deleted: bool = False
    ) -> Optional["Tenant"]:
        """
        Get tenant by Slack team ID.

        Args:
            session: Database session
            slack_team_id: Slack team ID (e.g., T0123456789)
            include_deleted: Include soft-deleted tenants

        Returns:
            Tenant instance or None
        """
        query = session.query(cls).filter(cls.slack_team_id == slack_team_id)

        if not include_deleted:
            query = query.filter(cls.deleted_at.is_(None))

        return query.first()

    @classmethod
    def get_active_tenants(
        cls,
        session: Session,
        limit: Optional[int] = None
    ) -> List["Tenant"]:
        """
        Get all tenants with active subscriptions.

        Args:
            session: Database session
            limit: Maximum number of results

        Returns:
            List of active tenants
        """
        query = (
            session.query(cls)
            .filter(cls.deleted_at.is_(None))
            .filter(cls.subscription_status.in_(['active', 'trial']))
        )

        if limit:
            query = query.limit(limit)

        return query.all()

    def get_default_crm_connection(self, session: Session):
        """
        Get the default CRM connection for this tenant.

        Args:
            session: Database session

        Returns:
            CRMConnection instance or None
        """
        from src.models.crm_connection import CRMConnection

        return (
            session.query(CRMConnection)
            .filter(CRMConnection.tenant_id == self.id)
            .filter(CRMConnection.is_default == True)
            .filter(CRMConnection.deleted_at.is_(None))
            .first()
        )
