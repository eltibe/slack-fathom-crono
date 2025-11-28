"""
Account Mapping model - Maps email domains to CRM accounts.

Local cache of domain → CRM account mappings for faster lookups and to avoid
repeated CRM API calls. Supports manual, auto-discovered, and imported mappings.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from decimal import Decimal

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, Numeric,
    CheckConstraint, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship, Session

from src.models.base import Base, BaseModel


class AccountMapping(Base, BaseModel):
    """
    Account Mapping model for domain to CRM account mappings.

    Provides a local cache of email domain to CRM account mappings:
    - Speeds up account lookups (avoids repeated CRM API calls)
    - Tracks mapping source (manual, auto-discovered, imported)
    - Tracks usage statistics and confidence scores
    - Can be verified by users for higher confidence

    Relationships:
    - tenant: Many-to-one with Tenant model
    - crm_connection: Many-to-one with CRMConnection model
    - created_by_user: Many-to-one with User model
    """

    __tablename__ = "account_mappings"

    # Foreign keys
    tenant_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to tenant (Slack workspace)"
    )

    crm_connection_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("crm_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="CRM connection this mapping belongs to"
    )

    # Domain mapping
    email_domain = Column(
        String(255),
        nullable=False,
        comment="Email domain (e.g., neuronup.com)"
    )

    company_name = Column(
        String(255),
        nullable=True,
        comment="Company name for display"
    )

    # CRM account details
    crm_account_id = Column(
        String(255),
        nullable=False,
        comment="Account ID in CRM system"
    )

    crm_account_name = Column(
        String(255),
        nullable=False,
        comment="Account name in CRM system"
    )

    # Mapping metadata
    mapping_source = Column(
        String(50),
        nullable=True,
        comment="Source: manual, auto_discovered, imported"
    )

    confidence_score = Column(
        Numeric(3, 2),
        nullable=True,
        comment="Confidence score 0.00-1.00 (for auto-discovered)"
    )

    verified = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether mapping has been verified by user"
    )

    # Usage statistics
    times_used = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of times this mapping has been used"
    )

    last_used_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time this mapping was used"
    )

    # Foreign key to user who created mapping
    created_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created this mapping"
    )

    # Relationships
    tenant = relationship(
        "Tenant",
        back_populates="account_mappings"
    )

    crm_connection = relationship(
        "CRMConnection",
        back_populates="account_mappings"
    )

    created_by_user = relationship(
        "User",
        back_populates="created_account_mappings",
        foreign_keys=[created_by_user_id]
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "crm_connection_id", "email_domain",
            name="uq_account_mapping_tenant_crm_domain"
        ),
        CheckConstraint(
            "mapping_source IN ('manual', 'auto_discovered', 'imported')",
            name="valid_mapping_source"
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0.00 AND confidence_score <= 1.00)",
            name="valid_confidence_score"
        ),
        Index("idx_account_mappings_tenant_crm", "tenant_id", "crm_connection_id"),
        Index("idx_account_mappings_domain", "tenant_id", "email_domain"),
        Index(
            "idx_account_mappings_verified",
            "tenant_id", "crm_connection_id",
            postgresql_where=(Column("verified") == True)
        ),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<AccountMapping(id={self.id}, domain={self.email_domain}, "
            f"crm_account={self.crm_account_name}, verified={self.verified})>"
        )

    def increment_usage(self) -> None:
        """Increment usage counter and update last_used_at."""
        self.times_used += 1
        self.last_used_at = datetime.now()

    def verify(self) -> None:
        """Mark this mapping as verified by user."""
        self.verified = True
        self.confidence_score = Decimal("1.00")

    @classmethod
    def get_by_domain(
        cls,
        session: Session,
        tenant_id: UUID,
        crm_connection_id: UUID,
        email_domain: str,
        verified_only: bool = False
    ) -> Optional["AccountMapping"]:
        """
        Get account mapping by email domain.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            crm_connection_id: CRM connection UUID
            email_domain: Email domain to look up
            verified_only: Only return verified mappings

        Returns:
            AccountMapping instance or None
        """
        query = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.crm_connection_id == crm_connection_id)
            .filter(cls.email_domain == email_domain)
            .filter(cls.deleted_at.is_(None))
        )

        if verified_only:
            query = query.filter(cls.verified == True)

        # Order by verified first, then by times_used
        query = query.order_by(
            cls.verified.desc(),
            cls.times_used.desc()
        )

        return query.first()

    @classmethod
    def get_all_for_crm(
        cls,
        session: Session,
        tenant_id: UUID,
        crm_connection_id: UUID,
        verified_only: bool = False,
        limit: Optional[int] = None
    ) -> List["AccountMapping"]:
        """
        Get all account mappings for a CRM connection.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            crm_connection_id: CRM connection UUID
            verified_only: Only return verified mappings
            limit: Maximum number of results

        Returns:
            List of AccountMapping instances
        """
        query = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.crm_connection_id == crm_connection_id)
            .filter(cls.deleted_at.is_(None))
        )

        if verified_only:
            query = query.filter(cls.verified == True)

        query = query.order_by(
            cls.verified.desc(),
            cls.times_used.desc(),
            cls.email_domain.asc()
        )

        if limit:
            query = query.limit(limit)

        return query.all()

    @classmethod
    def search_by_company(
        cls,
        session: Session,
        tenant_id: UUID,
        crm_connection_id: UUID,
        company_name: str,
        limit: Optional[int] = 10
    ) -> List["AccountMapping"]:
        """
        Search account mappings by company name.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            crm_connection_id: CRM connection UUID
            company_name: Company name to search (partial match)
            limit: Maximum number of results

        Returns:
            List of AccountMapping instances
        """
        search_pattern = f"%{company_name}%"

        query = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.crm_connection_id == crm_connection_id)
            .filter(
                (cls.company_name.ilike(search_pattern)) |
                (cls.crm_account_name.ilike(search_pattern))
            )
            .filter(cls.deleted_at.is_(None))
            .order_by(
                cls.verified.desc(),
                cls.times_used.desc()
            )
        )

        if limit:
            query = query.limit(limit)

        return query.all()

    @classmethod
    def get_frequently_used(
        cls,
        session: Session,
        tenant_id: UUID,
        crm_connection_id: UUID,
        days: int = 30,
        limit: int = 50
    ) -> List["AccountMapping"]:
        """
        Get frequently used account mappings.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            crm_connection_id: CRM connection UUID
            days: Consider usage from last N days
            limit: Maximum number of results

        Returns:
            List of frequently used AccountMapping instances
        """
        cutoff_date = datetime.now() - datetime.timedelta(days=days)

        query = (
            session.query(cls)
            .filter(cls.tenant_id == tenant_id)
            .filter(cls.crm_connection_id == crm_connection_id)
            .filter(cls.last_used_at >= cutoff_date)
            .filter(cls.deleted_at.is_(None))
            .order_by(cls.times_used.desc())
            .limit(limit)
        )

        return query.all()

    @classmethod
    def bulk_import(
        cls,
        session: Session,
        tenant_id: UUID,
        crm_connection_id: UUID,
        mappings: List[dict],
        created_by_user_id: Optional[UUID] = None
    ) -> int:
        """
        Bulk import account mappings from a list.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            crm_connection_id: CRM connection UUID
            mappings: List of dicts with keys: email_domain, crm_account_id, crm_account_name
            created_by_user_id: Optional user who created these mappings

        Returns:
            Number of mappings imported
        """
        imported_count = 0

        for mapping_data in mappings:
            # Check if mapping already exists
            existing = cls.get_by_domain(
                session,
                tenant_id,
                crm_connection_id,
                mapping_data['email_domain']
            )

            if not existing:
                mapping = cls(
                    tenant_id=tenant_id,
                    crm_connection_id=crm_connection_id,
                    email_domain=mapping_data['email_domain'],
                    crm_account_id=mapping_data['crm_account_id'],
                    crm_account_name=mapping_data['crm_account_name'],
                    company_name=mapping_data.get('company_name'),
                    mapping_source='imported',
                    created_by_user_id=created_by_user_id
                )
                session.add(mapping)
                imported_count += 1

        session.flush()
        return imported_count
