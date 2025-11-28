"""
CRM Connection model - Represents CRM provider integrations for tenants.

Each tenant can have multiple CRM connections (HubSpot, Salesforce, Crono, etc.)
with their own credentials, settings, and sync status.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text,
    CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship, Session

from src.models.base import Base, BaseModel


class CRMConnection(Base, BaseModel):
    """
    CRM Connection model representing integrations with CRM providers.

    Each connection stores:
    - Provider type (Crono, HubSpot, Salesforce, Pipedrive)
    - Credentials (stored in AWS Secrets Manager)
    - OAuth tokens for providers that use OAuth
    - Connection status and error tracking
    - Provider-specific settings

    Relationships:
    - tenant: Many-to-one with Tenant model
    - connected_by_user: Many-to-one with User model
    - account_mappings: One-to-many with AccountMapping model
    - meeting_sessions: One-to-many with MeetingSession model
    """

    __tablename__ = "crm_connections"

    # Foreign key to tenant
    tenant_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to tenant (Slack workspace)"
    )

    # CRM provider details
    provider_type = Column(
        String(50),
        nullable=False,
        comment="CRM provider: crono, hubspot, salesforce, pipedrive"
    )

    connection_name = Column(
        String(255),
        nullable=True,
        comment="User-friendly connection name (e.g., 'Production HubSpot')"
    )

    # Credentials (stored in AWS Secrets Manager)
    credentials_secret_id = Column(
        String(255),
        nullable=False,
        comment="AWS Secrets Manager ARN/ID for credentials"
    )

    # OAuth details (for providers like HubSpot, Salesforce)
    oauth_access_token_secret_id = Column(
        String(255),
        nullable=True,
        comment="AWS Secrets Manager ID for OAuth access token"
    )

    oauth_refresh_token_secret_id = Column(
        String(255),
        nullable=True,
        comment="AWS Secrets Manager ID for OAuth refresh token"
    )

    oauth_expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When OAuth access token expires"
    )

    oauth_scopes = Column(
        ARRAY(Text),
        nullable=True,
        comment="OAuth scopes granted (e.g., ['crm.objects.contacts.read'])"
    )

    # Connection status
    status = Column(
        String(50),
        nullable=False,
        default='active',
        comment="Connection status: active, error, disconnected, refreshing"
    )

    last_sync_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful sync with CRM"
    )

    last_error = Column(
        Text,
        nullable=True,
        comment="Last error message encountered"
    )

    last_error_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When last error occurred"
    )

    # Configuration
    settings = Column(
        JSONB,
        nullable=False,
        default={},
        comment="Provider-specific settings (JSONB)"
    )

    is_default = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether this is the default CRM for the tenant"
    )

    # Foreign key to user who created connection
    connected_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created this connection"
    )

    # Relationships
    tenant = relationship(
        "Tenant",
        back_populates="crm_connections"
    )

    connected_by_user = relationship(
        "User",
        back_populates="created_crm_connections",
        foreign_keys=[connected_by_user_id]
    )

    account_mappings = relationship(
        "AccountMapping",
        back_populates="crm_connection",
        cascade="all, delete-orphan",
        lazy="select"
    )

    meeting_sessions = relationship(
        "MeetingSession",
        back_populates="crm_connection",
        lazy="select"
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "provider_type IN ('crono', 'hubspot', 'salesforce', 'pipedrive')",
            name="valid_provider_type"
        ),
        CheckConstraint(
            "status IN ('active', 'error', 'disconnected', 'refreshing')",
            name="valid_status"
        ),
        Index("idx_crm_connections_tenant_id", "tenant_id"),
        Index("idx_crm_connections_provider_type", "tenant_id", "provider_type"),
        Index(
            "idx_crm_connections_default",
            "tenant_id",
            postgresql_where=(
                (Column("is_default") == True) &
                (Column("deleted_at").is_(None))
            )
        ),
        Index(
            "idx_crm_connections_status",
            "status",
            postgresql_where=(Column("deleted_at").is_(None))
        ),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<CRMConnection(id={self.id}, provider={self.provider_type}, "
            f"name={self.connection_name}, status={self.status})>"
        )

    @property
    def is_active(self) -> bool:
        """Check if connection is active and working."""
        return self.status == 'active'

    @property
    def has_oauth(self) -> bool:
        """Check if connection uses OAuth."""
        return self.oauth_access_token_secret_id is not None

    @property
    def oauth_expired(self) -> bool:
        """Check if OAuth token has expired."""
        if not self.oauth_expires_at:
            return False
        return datetime.now() > self.oauth_expires_at

    def mark_error(self, error_message: str) -> None:
        """
        Mark connection as having an error.

        Args:
            error_message: Description of the error
        """
        self.status = 'error'
        self.last_error = error_message
        self.last_error_at = datetime.now()

    def mark_active(self) -> None:
        """Mark connection as active and clear error state."""
        self.status = 'active'
        self.last_error = None
        self.last_error_at = None
        self.last_sync_at = datetime.now()

    @classmethod
    def get_by_tenant(
        cls,
        session: Session,
        tenant_id: UUID,
        provider_type: Optional[str] = None,
        active_only: bool = True,
        include_deleted: bool = False
    ) -> List["CRMConnection"]:
        """
        Get CRM connections for a tenant.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            provider_type: Filter by provider (e.g., 'hubspot')
            active_only: Only return active connections
            include_deleted: Include soft-deleted connections

        Returns:
            List of CRMConnection instances
        """
        query = session.query(cls).filter(cls.tenant_id == tenant_id)

        if provider_type:
            query = query.filter(cls.provider_type == provider_type)

        if active_only:
            query = query.filter(cls.status == 'active')

        if not include_deleted:
            query = query.filter(cls.deleted_at.is_(None))

        return query.order_by(cls.is_default.desc(), cls.created_at.asc()).all()

    @classmethod
    def get_default(
        cls,
        session: Session,
        tenant_id: UUID,
        include_deleted: bool = False
    ) -> Optional["CRMConnection"]:
        """
        Get the default CRM connection for a tenant.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            include_deleted: Include soft-deleted connections

        Returns:
            CRMConnection instance or None
        """
        query = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.is_default == True)
        )

        if not include_deleted:
            query = query.filter(cls.deleted_at.is_(None))

        return query.first()

    @classmethod
    def get_connections_needing_refresh(
        cls,
        session: Session,
        include_deleted: bool = False
    ) -> List["CRMConnection"]:
        """
        Get connections with expired OAuth tokens that need refreshing.

        Args:
            session: Database session
            include_deleted: Include soft-deleted connections

        Returns:
            List of CRMConnection instances needing refresh
        """
        now = datetime.now()

        query = (
            session.query(cls)
            .filter(cls.oauth_expires_at.isnot(None))
            .filter(cls.oauth_expires_at < now)
            .filter(cls.status.in_(['active', 'refreshing']))
        )

        if not include_deleted:
            query = query.filter(cls.deleted_at.is_(None))

        return query.all()

    def set_as_default(self, session: Session) -> None:
        """
        Set this connection as the default for the tenant.
        Unsets any other default connections.

        Args:
            session: Database session
        """
        # Unset all other defaults for this tenant
        session.query(CRMConnection).filter(
            CRMConnection.tenant_id == self.tenant_id,
            CRMConnection.id != self.id,
            CRMConnection.is_default == True
        ).update({"is_default": False})

        # Set this as default
        self.is_default = True
