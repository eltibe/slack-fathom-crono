"""
CRM Providers Package

This package provides an abstraction layer for multiple CRM integrations.
It enables the application to work with different CRMs (Crono, HubSpot, Salesforce, etc.)
through a unified interface, supporting multi-tenant SaaS architecture.

Usage:
    from providers import CRMProviderFactory

    # Create a CRM provider instance
    crm = CRMProviderFactory.create('crono', {
        'public_key': 'pk_xxx',
        'private_key': 'sk_yyy'
    })

    # Use the provider
    accounts = crm.search_accounts('Company Name')
    crm.create_note(account_id, 'Note content')

Available Providers:
    - crono: Crono CRM
    - More providers coming soon (HubSpot, Salesforce, etc.)
"""

from .base_provider import CRMProvider
from .crono_provider import CronoProvider
from .factory import CRMProviderFactory

__all__ = [
    'CRMProvider',
    'CronoProvider',
    'CRMProviderFactory'
]

__version__ = '1.0.0'
