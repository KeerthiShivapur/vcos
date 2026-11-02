"""Adapter Registry — factory for creating provider-specific connector adapters."""

import logging
from typing import Any, Optional, Dict, List, Type

from app.models.canonical_integration import ConnectorInstance
from app.services.base_adapter import BaseConnectorAdapter

logger = logging.getLogger("vcos.integration.adapters")

# Import all adapters
from app.services.google_adapter import GoogleWorkspaceAdapter, GoogleConfig
# from app.services.microsoft_adapter import Microsoft365Adapter, MicrosoftConfig  # Temporarily disabled due to msgraph path length issues
from app.services.slack_adapter import SlackAdapter, SlackConfig
from app.services.github_adapter import GitHubAdapter, GitHubConfig
from app.services.jira_adapter import JiraAdapter, JiraConfig


class AdapterRegistry:
    """Registry for connector adapters."""
    
    def __init__(self):
        self._adapters: Dict[str, Type[BaseConnectorAdapter]] = {}
        self._configs: Dict[str, Any] = {}
        self._initialized = False
    
    def register_adapter(self, provider: str, adapter_class: Type[BaseConnectorAdapter], config_class: Optional[Type] = None):
        """Register a provider adapter."""
        self._adapters[provider] = adapter_class
        if config_class:
            self._configs[provider] = config_class
        logger.info(f"Registered adapter for provider: {provider}")
    
    def get_adapter(self, provider: str, instance: Optional[Any] = None) -> Optional[BaseConnectorAdapter]:
        """Get adapter instance for provider."""
        adapter_class = self._adapters.get(provider)
        if not adapter_class:
            logger.warning(f"No adapter registered for provider: {provider}")
            return None
        
        config_class = self._configs.get(provider)
        config = None
        if config_class and self._initialized:
            # Config would be loaded from settings
            pass
        
        return adapter_class(config=config)
    
    def create_adapter_for_instance(self, instance: ConnectorInstance) -> Optional[BaseConnectorAdapter]:
        """Create adapter based on connector instance."""
        if not instance or not instance.connector_id:
            return None
        
        # Get provider from connector instance
        # This would typically come from the connector relationship
        provider = getattr(instance, 'provider', None)
        if not provider and instance.connector:
            provider = instance.connector.provider
        
        if not provider:
            logger.warning(f"Could not determine provider for instance {instance.id}")
            return None
        
        return self.get_adapter(provider)
    
    def initialize(self, settings: Any):
        """Initialize registry with settings."""
        self._initialized = True
        
        # Register default adapters
        self.register_adapter("google", GoogleWorkspaceAdapter, GoogleConfig)
        # self.register_adapter("microsoft", Microsoft365Adapter, MicrosoftConfig)  # Temporarily disabled
        self.register_adapter("slack", SlackAdapter, SlackConfig)
        self.register_adapter("github", GitHubAdapter, GitHubConfig)
        self.register_adapter("jira", JiraAdapter, JiraConfig)
        
        logger.info("Adapter registry initialized with default providers")
    
    def get_supported_providers(self) -> List[str]:
        """Get list of supported providers."""
        return list(self._adapters.keys())
    
    def get_provider_capabilities(self, provider: str) -> Optional[Dict[str, Any]]:
        """Get capabilities for a provider."""
        adapter = self.get_adapter(provider)
        if adapter:
            return {
                "provider": provider,
                "entity_types": adapter._get_supported_entity_types(),
                "sync_modes": ["initial", "incremental", "webhook", "polling", "replay"],
                "supports_webhooks": getattr(adapter, 'supports_webhooks', False),
            }
        return None


# Global registry instance
adapter_registry = AdapterRegistry()

# Auto-initialize with default adapters
adapter_registry.initialize(None)


def create_adapter_for_instance(instance: ConnectorInstance) -> Optional[BaseConnectorAdapter]:
    """Convenience function to create adapter for instance."""
    return adapter_registry.create_adapter_for_instance(instance)


def get_adapter(provider: str) -> Optional[BaseConnectorAdapter]:
    """Get adapter for provider."""
    return adapter_registry.get_adapter(provider)


def initialize_adapter_registry(settings: Any):
    """Initialize adapter registry with settings."""
    adapter_registry.initialize(settings)