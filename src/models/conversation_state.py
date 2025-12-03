"""
Conversation State Model
Stores conversation state for multi-worker environments
"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.models.base import Base
import uuid


class ConversationState(Base):
    """Store conversation state across Gunicorn workers"""
    __tablename__ = 'conversation_states'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Key used to look up the state (recording_id, thread_ts, etc.)
    state_key = Column(String, unique=True, nullable=False, index=True)

    # The actual state data (JSON)
    state_data = Column(JSONB, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Auto-cleanup: delete states older than 24 hours
    expires_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<ConversationState(state_key='{self.state_key}')>"
