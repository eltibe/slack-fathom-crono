"""
CRM Provider Factory

This module implements the Factory pattern for creating CRM provider instances.
It provides a centralized way to instantiate different CRM providers based on
the CRM type, enabling easy extensibility and multi-tenant support.
"""

from typing import Dict, Any
from .base_provider import CRMProvider
from .crono_provider import CronoProvider


class CRMProviderFactory:
    """Factory to create CRM provider instances.

    This factory pattern allows the application to dynamically create the appropriate
    CRM provider based on configuration or tenant settings, without tight coupling
    to specific provider implementations.

    Example usage:
        # Create a Crono provider
        credentials = {'public_key': 'xxx', 'private_key': 'yyy'}
        crm = CRMProviderFactory.create('crono', credentials)

        # Use the provider
        accounts = crm.search_accounts('Acme Corp')
        crm.create_note(account_id, 'Meeting notes...')
    """

    # Registry of available CRM providers
    # Maps provider type string to provider class
    _providers = {
        'crono': CronoProvider,
        # Future providers can be added here:
        # 'hubspot': HubSpotProvider,
        # 'salesforce': SalesforceProvider,
        # 'pipedrive': PipedriveProvider,
    }

    @classmethod
    def create(cls, crm_type: str, credentials: Dict[str, Any]) -> CRMProvider:
        """Create a CRM provider instance.

        Args:
            crm_type: Provider type identifier ('crono', 'hubspot', 'salesforce', etc.)
            credentials: Provider-specific credentials dict
                - For Crono: {'public_key': str, 'private_key': str}
                - For HubSpot: {'oauth_token': str}
                - Format varies by provider

        Returns:
            CRMProvider instance

        Raises:
            ValueError: If crm_type is not supported
            Exception: If provider initialization fails (invalid credentials, etc.)

        Example:
            >>> factory = CRMProviderFactory()
            >>> crm = factory.create('crono', {
            ...     'public_key': 'pk_123',
            ...     'private_key': 'sk_456'
            ... })
            >>> accounts = crm.search_accounts('Test Company')
        """
        if crm_type not in cls._providers:
            supported_types = ', '.join(cls._providers.keys())
            raise ValueError(
                f"Unsupported CRM type: '{crm_type}'. "
                f"Supported types: {supported_types}"
            )

        provider_class = cls._providers[crm_type]

        try:
            return provider_class(credentials)
        except Exception as e:
            raise Exception(
                f"Failed to initialize {crm_type} provider: {str(e)}"
            ) from e

    @classmethod
    def register_provider(cls, crm_type: str, provider_class: type):
        """Register a new CRM provider (for extensibility).

        This method allows third-party or custom CRM providers to be registered
        at runtime, making the system highly extensible without modifying core code.

        Args:
            crm_type: Provider type identifier (e.g., 'custom_crm')
            provider_class: Provider class implementing CRMProvider interface

        Raises:
            TypeError: If provider_class doesn't implement CRMProvider

        Example:
            >>> from my_custom_crm import CustomCRMProvider
            >>> CRMProviderFactory.register_provider('custom_crm', CustomCRMProvider)
            >>> crm = CRMProviderFactory.create('custom_crm', {'api_key': 'xxx'})
        """
        # Validate that the provider class implements CRMProvider
        if not issubclass(provider_class, CRMProvider):
            raise TypeError(
                f"Provider class must implement CRMProvider interface. "
                f"Got: {provider_class.__name__}"
            )

        cls._providers[crm_type] = provider_class
        print(f"✅ Registered new CRM provider: {crm_type}")

    @classmethod
    def get_supported_types(cls) -> list:
        """Get list of supported CRM types.

        Returns:
            List of supported CRM type identifiers

        Example:
            >>> CRMProviderFactory.get_supported_types()
            ['crono', 'hubspot', 'salesforce']
        """
        return list(cls._providers.keys())

    @classmethod
    def is_supported(cls, crm_type: str) -> bool:
        """Check if a CRM type is supported.

        Args:
            crm_type: CRM type to check

        Returns:
            True if supported, False otherwise

        Example:
            >>> CRMProviderFactory.is_supported('crono')
            True
            >>> CRMProviderFactory.is_supported('unknown_crm')
            False
        """
        return crm_type in cls._providers
