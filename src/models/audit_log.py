"""
Audit Log model - Immutable security and compliance audit trail.

Tracks all critical operations for security monitoring, compliance,
and debugging. Audit logs are never deleted, only archived.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, INET
from sqlalchemy.orm import relationship, Session

from src.models.base import Base, BaseModel


class AuditLog(Base, BaseModel):
    """
    Audit Log model for security and compliance tracking.

    IMPORTANT: Audit logs are IMMUTABLE. Once created, they should never be
    modified or deleted (except for regulatory data retention policies).

    Records all critical events:
    - Authentication (login, logout, token refresh)
    - Data access (CRM reads, account lookups)
    - Configuration changes (settings updates, connections)
    - Integration operations (CRM writes, email sends)
    - Security events (failed auth, permission denied)

    Relationships:
    - tenant: Many-to-one with Tenant model (nullable for system events)
    - user: Many-to-one with User model (nullable for system events)
    """

    __tablename__ = "audit_logs"

    # Foreign keys (nullable for system-level events)
    tenant_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Reference to tenant (NULL for system events)"
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User who performed the action (NULL for system events)"
    )

    # Event details
    event_type = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Event type (e.g., crm.note.created, user.login)"
    )

    event_category = Column(
        String(50),
        nullable=False,
        comment="Event category: authentication, data_access, configuration, integration, security"
    )

    resource_type = Column(
        String(50),
        nullable=True,
        comment="Type of resource affected (e.g., meeting_session, crm_connection)"
    )

    resource_id = Column(
        PG_UUID(as_uuid=True),
        nullable=True,
        comment="ID of the resource affected"
    )

    # Event data
    action_description = Column(
        Text,
        nullable=False,
        comment="Human-readable description of the action"
    )

    ip_address = Column(
        INET,
        nullable=True,
        comment="IP address of the client"
    )

    user_agent = Column(
        Text,
        nullable=True,
        comment="User agent string from client"
    )

    # Request/response data (sanitized - no sensitive data!)
    request_data = Column(
        JSONB,
        nullable=True,
        comment="Sanitized request data (JSONB)"
    )

    response_data = Column(
        JSONB,
        nullable=True,
        comment="Sanitized response data (JSONB)"
    )

    # Outcome
    status = Column(
        String(50),
        nullable=False,
        comment="Outcome: success, failure, partial"
    )

    error_message = Column(
        Text,
        nullable=True,
        comment="Error message if status is failure"
    )

    # Relationships
    tenant = relationship(
        "Tenant",
        back_populates="audit_logs"
    )

    user = relationship(
        "User",
        back_populates="audit_logs"
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "event_category IN ('authentication', 'data_access', 'configuration', 'integration', 'security')",
            name="valid_event_category"
        ),
        CheckConstraint(
            "status IN ('success', 'failure', 'partial')",
            name="valid_status"
        ),
        Index("idx_audit_logs_tenant_created", "tenant_id", "created_at", postgresql_using="btree"),
        Index("idx_audit_logs_user_created", "user_id", "created_at", postgresql_using="btree"),
        Index("idx_audit_logs_event_type", "event_type", "created_at", postgresql_using="btree"),
        Index("idx_audit_logs_created_at", "created_at", postgresql_using="btree"),
        Index(
            "idx_audit_logs_failures",
            "tenant_id", "created_at",
            postgresql_where=(Column("status") == 'failure')
        ),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<AuditLog(id={self.id}, event_type={self.event_type}, "
            f"status={self.status}, user_id={self.user_id})>"
        )

    # Override soft delete - audit logs should not be soft deleted
    def soft_delete(self) -> None:
        """Audit logs cannot be soft deleted (immutable)."""
        raise NotImplementedError("Audit logs are immutable and cannot be deleted")

    @classmethod
    def log_event(
        cls,
        session: Session,
        event_type: str,
        event_category: str,
        action_description: str,
        status: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_data: Optional[dict] = None,
        response_data: Optional[dict] = None,
        error_message: Optional[str] = None
    ) -> "AuditLog":
        """
        Create an audit log entry.

        Args:
            session: Database session
            event_type: Event type (e.g., 'crm.note.created')
            event_category: Category (authentication, data_access, etc.)
            action_description: Human-readable description
            status: Outcome (success, failure, partial)
            tenant_id: Optional tenant ID
            user_id: Optional user ID
            resource_type: Optional resource type
            resource_id: Optional resource ID
            ip_address: Optional client IP
            user_agent: Optional user agent
            request_data: Optional sanitized request data
            response_data: Optional sanitized response data
            error_message: Optional error message

        Returns:
            Created AuditLog instance

        Example:
            AuditLog.log_event(
                session=db,
                event_type='crm.note.created',
                event_category='integration',
                action_description='Created note in CRM for meeting',
                status='success',
                tenant_id=tenant_id,
                user_id=user_id,
                resource_type='meeting_session',
                resource_id=meeting_id
            )
        """
        log = cls(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            event_category=event_category,
            resource_type=resource_type,
            resource_id=resource_id,
            action_description=action_description,
            ip_address=ip_address,
            user_agent=user_agent,
            request_data=request_data,
            response_data=response_data,
            status=status,
            error_message=error_message
        )
        session.add(log)
        session.flush()
        return log

    @classmethod
    def get_tenant_logs(
        cls,
        session: Session,
        tenant_id: UUID,
        event_category: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        days: int = 30,
        limit: int = 100
    ) -> List["AuditLog"]:
        """
        Get audit logs for a tenant.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            event_category: Optional filter by category
            event_type: Optional filter by event type
            status: Optional filter by status
            days: Number of days to look back
            limit: Maximum number of results

        Returns:
            List of AuditLog instances
        """
        cutoff_date = datetime.now() - datetime.timedelta(days=days)

        query = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.created_at >= cutoff_date)
        )

        if event_category:
            query = query.filter(cls.event_category == event_category)

        if event_type:
            query = query.filter(cls.event_type == event_type)

        if status:
            query = query.filter(cls.status == status)

        query = query.order_by(cls.created_at.desc()).limit(limit)

        return query.all()

    @classmethod
    def get_user_logs(
        cls,
        session: Session,
        user_id: UUID,
        event_category: Optional[str] = None,
        days: int = 30,
        limit: int = 100
    ) -> List["AuditLog"]:
        """
        Get audit logs for a user.

        Args:
            session: Database session
            user_id: User UUID
            event_category: Optional filter by category
            days: Number of days to look back
            limit: Maximum number of results

        Returns:
            List of AuditLog instances
        """
        cutoff_date = datetime.now() - datetime.timedelta(days=days)

        query = (
            session.query(cls)
            .filter(cls.user_id == user_id)
            .filter(cls.created_at >= cutoff_date)
        )

        if event_category:
            query = query.filter(cls.event_category == event_category)

        query = query.order_by(cls.created_at.desc()).limit(limit)

        return query.all()

    @classmethod
    def get_recent_failures(
        cls,
        session: Session,
        tenant_id: Optional[UUID] = None,
        hours: int = 24,
        limit: int = 50
    ) -> List["AuditLog"]:
        """
        Get recent failed events (for security monitoring).

        Args:
            session: Database session
            tenant_id: Optional tenant filter
            hours: Number of hours to look back
            limit: Maximum number of results

        Returns:
            List of failed AuditLog instances
        """
        cutoff_date = datetime.now() - datetime.timedelta(hours=hours)

        query = (
            session.query(cls)
            .filter(cls.status == 'failure')
            .filter(cls.created_at >= cutoff_date)
        )

        if tenant_id:
            query = query.filter(cls.tenant_id == tenant_id)

        query = query.order_by(cls.created_at.desc()).limit(limit)

        return query.all()

    @classmethod
    def get_security_events(
        cls,
        session: Session,
        tenant_id: Optional[UUID] = None,
        days: int = 7,
        limit: int = 100
    ) -> List["AuditLog"]:
        """
        Get recent security-related events.

        Args:
            session: Database session
            tenant_id: Optional tenant filter
            days: Number of days to look back
            limit: Maximum number of results

        Returns:
            List of security AuditLog instances
        """
        cutoff_date = datetime.now() - datetime.timedelta(days=days)

        query = (
            session.query(cls)
            .filter(cls.event_category == 'security')
            .filter(cls.created_at >= cutoff_date)
        )

        if tenant_id:
            query = query.filter(cls.tenant_id == tenant_id)

        query = query.order_by(cls.created_at.desc()).limit(limit)

        return query.all()
