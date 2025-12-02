"""
ORM model for storing user-specific settings and API keys.

This model allows each user within a tenant to store their own
credentials for various integrations and personal preferences.
"""

from sqlalchemy import Column, String, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.schema import ForeignKey
from sqlalchemy.orm import relationship

from src.models.base import Base, BaseModel


class UserSettings(Base, BaseModel):
    __tablename__ = 'user_settings'

    # Foreign keys for multi-tenancy and user-specificity
    tenant_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='CASCADE'),
        nullable=False,
        comment="ID of the tenant (Slack workspace) this setting belongs to"
    )
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,  # Each user can only have one settings entry
        comment="ID of the user this setting belongs to"
    )

    # Integration API Keys (encrypted in production)
    crono_api_key = Column(String(255), nullable=True, comment="DEPRECATED: Legacy combined Crono key (public/private)")
    crono_public_key = Column(String(255), nullable=True, comment="Crono public API key")
    crono_private_key = Column(String(255), nullable=True, comment="Crono private API key")
    fathom_api_key = Column(String(255), nullable=True, comment="API Key for Fathom integration")
    piper_api_key = Column(String(255), nullable=True, comment="API Key for Piper.ai integration")
    gmail_token = Column(Text, nullable=True, comment="OAuth token for Gmail integration")
    calendar_token = Column(Text, nullable=True, comment="OAuth token for Calendar integration")

    # User preferences
    email_tone = Column(String(50), default="professional", comment="Preferred tone for email drafts")
    # Add other settings as needed

    # Relationships
    tenant = relationship("Tenant", back_populates="user_settings")
    user = relationship("User", back_populates="settings")

    def __repr__(self) -> str:
        return f"<UserSettings(id={self.id}, user_id={self.user_id}, tenant_id={self.tenant_id})>"
