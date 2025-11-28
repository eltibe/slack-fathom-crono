"""
Base CRM Provider Interface

This module defines the abstract base class that all CRM providers must implement.
This abstraction layer enables the application to support multiple CRMs
(Crono, HubSpot, Salesforce, etc.) through a consistent interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class CRMProvider(ABC):
    """Abstract base class for CRM integrations.

    All CRM providers (Crono, HubSpot, Salesforce, etc.) must implement this interface.
    This ensures a consistent API across different CRM systems, making it easy to
    switch between providers or support multiple CRMs in a multi-tenant SaaS environment.
    """

    @abstractmethod
    def __init__(self, credentials: Dict[str, Any]):
        """Initialize provider with credentials.

        Args:
            credentials: Dict containing API keys, OAuth tokens, etc.
                Format varies by provider:
                - Crono: {'public_key': str, 'private_key': str}
                - HubSpot: {'oauth_token': str}
        """
        pass

    @abstractmethod
    def search_accounts(self, query: str, limit: int = 10) -> List[Dict]:
        """Search for accounts/companies by name or domain.

        Args:
            query: Search term (company name or email domain)
            limit: Max results to return

        Returns:
            List of account dicts with standardized fields:
            {
                'id': str,  # CRM-specific account ID
                'name': str,  # Company name
                'website': str,  # Company website
                'crm_type': str  # 'crono', 'hubspot', etc.
            }
        """
        pass

    @abstractmethod
    def get_account_by_id(self, account_id: str) -> Optional[Dict]:
        """Get single account by ID.

        Args:
            account_id: CRM-specific account ID

        Returns:
            Account dict or None if not found
        """
        pass

    @abstractmethod
    def create_note(self, account_id: str, content: str, title: Optional[str] = None) -> Dict:
        """Create a note/activity on an account.

        Args:
            account_id: CRM-specific account ID
            content: Note content (plain text or markdown)
            title: Optional note title

        Returns:
            Created note dict with 'id' and 'created_at'
        """
        pass

    @abstractmethod
    def get_deals(self, account_id: str, limit: int = 100) -> List[Dict]:
        """Get deals/opportunities for an account.

        Args:
            account_id: CRM-specific account ID
            limit: Max deals to return

        Returns:
            List of deal dicts:
            {
                'id': str,
                'name': str,
                'stage': str,  # Standardized stage name
                'amount': float,
                'currency': str,
                'close_date': str  # ISO format
            }
        """
        pass

    @abstractmethod
    def create_task(self, account_id: str, task_data: Dict) -> Dict:
        """Create a task on an account.

        Args:
            account_id: CRM-specific account ID
            task_data: {
                'title': str,
                'description': str,
                'due_date': str,  # ISO format
                'assigned_to': Optional[str]  # User ID or email
            }

        Returns:
            Created task dict with 'id' and 'created_at'
        """
        pass

    @abstractmethod
    def update_deal_stage(self, deal_id: str, stage: str) -> Dict:
        """Update deal/opportunity stage.

        Args:
            deal_id: CRM-specific deal ID
            stage: New stage (standardized name: 'lead', 'qualified', 'proposal',
                   'negotiation', 'closed_won', 'closed_lost')

        Returns:
            Updated deal dict
        """
        pass

    @abstractmethod
    def get_stage_mapping(self) -> Dict[str, str]:
        """Get mapping from standard stages to CRM-specific stage names.

        Returns:
            Dict mapping standard stage names to CRM-specific names:
            {
                'lead': 'Lead',
                'qualified': 'Qualified to Buy',
                'proposal': 'Proposal Sent',
                'negotiation': 'Negotiation',
                'closed_won': 'Closed Won',
                'closed_lost': 'Closed Lost'
            }
        """
        pass
