"""
Meeting Session model - Tracks all meetings processed through the bot.

Each meeting session represents a Fathom recording that has been processed
through the AI pipeline, with results stored in the CRM and email drafted.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from sqlalchemy import (
    Column, String, Integer, Text, DateTime, ForeignKey,
    CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship, Session

from src.models.base import Base, BaseModel


class MeetingSession(Base, BaseModel):
    """
    Meeting Session model representing a processed meeting.

    Each session tracks:
    - Fathom meeting details (title, date, participants)
    - AI processing results (summary, email draft, insights)
    - CRM integration results (account, note, deals)
    - Google integration results (Gmail draft, Calendar event)
    - Processing status and errors

    Relationships:
    - tenant: Many-to-one with Tenant model
    - user: Many-to-one with User model
    - crm_connection: Many-to-one with CRMConnection model
    """

    __tablename__ = "meeting_sessions"

    # Foreign keys
    tenant_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to tenant (Slack workspace)"
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who initiated processing"
    )

    # Fathom meeting details
    fathom_recording_id = Column(
        String(255),
        nullable=False,
        comment="Fathom recording ID"
    )

    fathom_meeting_title = Column(
        String(500),
        nullable=True,
        comment="Meeting title from Fathom"
    )

    fathom_meeting_date = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the meeting occurred"
    )

    fathom_duration_minutes = Column(
        Integer,
        nullable=True,
        comment="Meeting duration in minutes"
    )

    fathom_participants = Column(
        ARRAY(Text),
        nullable=True,
        comment="List of meeting participants"
    )

    # AI processing results
    transcript_language = Column(
        String(10),
        nullable=True,
        comment="Detected language of transcript (e.g., en, it, es)"
    )

    ai_summary = Column(
        JSONB,
        nullable=True,
        comment="Structured AI summary output (JSONB)"
    )

    email_draft = Column(
        Text,
        nullable=True,
        comment="Generated follow-up email draft"
    )

    sales_insights = Column(
        JSONB,
        nullable=True,
        comment="Sales insights from AI analysis (JSONB)"
    )

    # CRM integration
    crm_connection_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("crm_connections.id", ondelete="SET NULL"),
        nullable=True,
        comment="CRM connection used for this session"
    )

    crm_account_id = Column(
        String(255),
        nullable=True,
        comment="CRM account ID where data was stored"
    )

    crm_account_name = Column(
        String(255),
        nullable=True,
        comment="CRM account name"
    )

    crm_note_id = Column(
        String(255),
        nullable=True,
        comment="ID of created note in CRM"
    )

    crm_deal_ids = Column(
        ARRAY(Text),
        nullable=True,
        comment="Associated deal IDs in CRM"
    )

    # Google integrations
    gmail_draft_id = Column(
        String(255),
        nullable=True,
        comment="Gmail draft ID"
    )

    calendar_event_id = Column(
        String(255),
        nullable=True,
        comment="Google Calendar event ID"
    )

    calendar_event_link = Column(
        Text,
        nullable=True,
        comment="Link to calendar event"
    )

    # Processing metadata
    processing_status = Column(
        String(50),
        nullable=False,
        default='pending',
        comment="Processing status: pending, processing, completed, failed, cancelled"
    )

    processing_started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When processing started"
    )

    processing_completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When processing completed"
    )

    processing_error = Column(
        Text,
        nullable=True,
        comment="Error message if processing failed"
    )

    # Actions performed
    actions_performed = Column(
        JSONB,
        nullable=False,
        default=[],
        comment="List of actions performed (e.g., ['email_draft', 'crm_note'])"
    )

    # Relationships
    tenant = relationship(
        "Tenant",
        back_populates="meeting_sessions"
    )

    user = relationship(
        "User",
        back_populates="meeting_sessions"
    )

    crm_connection = relationship(
        "CRMConnection",
        back_populates="meeting_sessions"
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')",
            name="valid_processing_status"
        ),
        Index("idx_meeting_sessions_tenant_id", "tenant_id"),
        Index("idx_meeting_sessions_user_id", "user_id"),
        Index("idx_meeting_sessions_fathom_id", "tenant_id", "fathom_recording_id"),
        Index("idx_meeting_sessions_created_at", "created_at", postgresql_using="btree"),
        Index(
            "idx_meeting_sessions_status",
            "processing_status",
            postgresql_where=(Column("processing_status") != 'completed')
        ),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<MeetingSession(id={self.id}, fathom_id={self.fathom_recording_id}, "
            f"status={self.processing_status}, title={self.fathom_meeting_title})>"
        )

    @property
    def is_completed(self) -> bool:
        """Check if processing is completed."""
        return self.processing_status == 'completed'

    @property
    def is_failed(self) -> bool:
        """Check if processing failed."""
        return self.processing_status == 'failed'

    @property
    def is_processing(self) -> bool:
        """Check if currently processing."""
        return self.processing_status == 'processing'

    @property
    def processing_duration_seconds(self) -> Optional[int]:
        """Calculate processing duration in seconds."""
        if not self.processing_started_at or not self.processing_completed_at:
            return None
        delta = self.processing_completed_at - self.processing_started_at
        return int(delta.total_seconds())

    def start_processing(self) -> None:
        """Mark session as started processing."""
        self.processing_status = 'processing'
        self.processing_started_at = datetime.now()

    def complete_processing(self, actions: Optional[list] = None) -> None:
        """
        Mark session as completed.

        Args:
            actions: List of actions performed (e.g., ['email_draft', 'crm_note'])
        """
        self.processing_status = 'completed'
        self.processing_completed_at = datetime.now()
        if actions:
            self.actions_performed = actions

    def fail_processing(self, error_message: str) -> None:
        """
        Mark session as failed.

        Args:
            error_message: Description of the error
        """
        self.processing_status = 'failed'
        self.processing_completed_at = datetime.now()
        self.processing_error = error_message

    @classmethod
    def get_by_fathom_id(
        cls,
        session: Session,
        tenant_id: UUID,
        fathom_recording_id: str,
        include_deleted: bool = False
    ) -> Optional["MeetingSession"]:
        """
        Get meeting session by Fathom recording ID.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            fathom_recording_id: Fathom recording ID
            include_deleted: Include soft-deleted sessions

        Returns:
            MeetingSession instance or None
        """
        query = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.fathom_recording_id == fathom_recording_id)
        )

        if not include_deleted:
            query = query.filter(cls.deleted_at.is_(None))

        return query.first()

    @classmethod
    def get_user_sessions(
        cls,
        session: Session,
        user_id: UUID,
        limit: Optional[int] = None,
        days: Optional[int] = None
    ) -> List["MeetingSession"]:
        """
        Get meeting sessions for a user.

        Args:
            session: Database session
            user_id: User UUID
            limit: Maximum number of results
            days: Only return sessions from last N days

        Returns:
            List of MeetingSession instances
        """
        query = (
            session.query(cls)
            .filter(cls.user_id == user_id)
            .filter(cls.deleted_at.is_(None))
            .order_by(cls.created_at.desc())
        )

        if days:
            cutoff_date = datetime.now() - datetime.timedelta(days=days)
            query = query.filter(cls.created_at >= cutoff_date)

        if limit:
            query = query.limit(limit)

        return query.all()

    @classmethod
    def get_pending_sessions(
        cls,
        session: Session,
        tenant_id: Optional[UUID] = None,
        limit: Optional[int] = None
    ) -> List["MeetingSession"]:
        """
        Get sessions that are pending or processing.

        Args:
            session: Database session
            tenant_id: Optional tenant filter
            limit: Maximum number of results

        Returns:
            List of pending MeetingSession instances
        """
        query = (
            session.query(cls)
            .filter(cls.processing_status.in_(['pending', 'processing']))
            .filter(cls.deleted_at.is_(None))
            .order_by(cls.created_at.asc())
        )

        if tenant_id:
            query = query.filter(cls.tenant_id == tenant_id)

        if limit:
            query = query.limit(limit)

        return query.all()

    @classmethod
    def get_failed_sessions(
        cls,
        session: Session,
        tenant_id: Optional[UUID] = None,
        hours: int = 24,
        limit: Optional[int] = None
    ) -> List["MeetingSession"]:
        """
        Get recently failed sessions.

        Args:
            session: Database session
            tenant_id: Optional tenant filter
            hours: Only return sessions that failed in last N hours
            limit: Maximum number of results

        Returns:
            List of failed MeetingSession instances
        """
        cutoff_date = datetime.now() - datetime.timedelta(hours=hours)

        query = (
            session.query(cls)
            .filter(cls.processing_status == 'failed')
            .filter(cls.processing_completed_at >= cutoff_date)
            .filter(cls.deleted_at.is_(None))
            .order_by(cls.processing_completed_at.desc())
        )

        if tenant_id:
            query = query.filter(cls.tenant_id == tenant_id)

        if limit:
            query = query.limit(limit)

        return query.all()
