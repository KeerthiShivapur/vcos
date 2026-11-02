"""Gate 24 — Base Connector Interface.

Abstract base class for all external system connectors.
Each provider implements this interface.
"""

from __future__ import annotations

import abc
from datetime import datetime, timezone
from typing import Any, Optional, AsyncIterator, Literal
from enum import Enum

from app.models.canonical_integration import ConnectorInstance
from app.models.canonical_integration import (
    CONNECTOR_STATES,
    CONNECTOR_CAPABILITIES,
    ENTITY_TYPES,
    SYNC_MODES,
    CONNECTOR_KINDS,
    MAPPING_STATES,
    SYNC_STATES,
    SYNC_MODES,
    EXTERNAL_EVENT_STATES,
    CONNECTOR_STATES,
    CONNECTOR_CAPABILITIES,
    ENTITY_TYPES,
)


class BaseConnector(abc.ABC):
    """Abstract base class for all external system connectors."""
    
    @property
    @abc.abstractmethod
    def provider(self) -> str:
        """Provider identifier (e.g., 'google', 'slack', 'github')."""
        pass
    
    @property
    @abc.abstractmethod
    def kind(self) -> str:
        """Connector kind (e.g., 'productivity', 'communication', 'code')."""
        pass
    
    @abc.abstractmethod
    async def authenticate(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        """
        Authenticate with the external system.
        
        Returns: (success, error_message)
        """
        pass
    
    @abc.abstractmethod
    async def test_connection(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        """
        Test the connection to the external system.
        
        Returns: (success, error_message)
        """
        pass
    
    @abc.abstractmethod
    async def full_sync(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Perform a full synchronization.
        
        Yields entity dicts with:
        - entity_type: ENTITY_TYPES value
        - external_id: str
        - data: dict
        - operation: 'create'|'update'|'delete'
        """
        pass
    
    @abc.abstractmethod
    async def incremental_sync(
        self,
        instance: ConnectorInstance,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Perform an incremental synchronization.
        
        Yields entity dicts (same as full_sync).
        """
        pass
    
    @abc.abstractmethod
    async def poll_events(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Poll for external events.
        
        Yields event dicts with:
        - external_event_id: str
        - event_type: str
        - source_id: str
        - source_type: str
        - payload: dict
        - external_timestamp: datetime
        """
        pass
    
    @abc.abstractmethod
    async def execute_operation(
        self,
        instance: ConnectorInstance,
        operation_type: str,
        target_entity_type: str,
        target_external_id: Optional[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute an outbound operation on the external system.
        
        Returns result dict with:
        - external_operation_id: str
        - success: bool
        - data: dict
        """
        pass
    
    @abc.abstractmethod
    async def get_webhook_events(
        self,
        instance: ConnectorInstance,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Parse webhook payload into standardized events.
        
        Returns list of event dicts (same as poll_events).
        """
        pass
    
    @abc.abstractmethod
    async def refresh_credentials(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str], Optional[dict]]:
        """
        Refresh OAuth credentials.
        
        Returns: (success, error_message, new_credentials)
        """
        pass
    
    @abc.abstractmethod
    async def get_rate_limit_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Get current rate limit status."""
        pass
    
    @abc.abstractmethod
    async def resolve_identity(
        self,
        instance: ConnectorInstance,
        external_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Resolve an external identity to VCOS entity attributes.
        
        Returns dict with:
        - external_id
        - external_email
        - external_display_name
        - external_avatar_url
        - external_metadata
        """
        pass
    
    @abc.abstractmethod
    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        """
        Discover and return the connector's capabilities.
        
        Returns dict with:
        - inbound_capabilities: list[str]
        - outbound_capabilities: list[str]
        - supported_entities: list[str]
        - supported_events: list[str]
        - sync_modes: list[str]
        - auth_types: list[str]
        - oauth_scopes: list[str]
        - required_config_fields: list[str]
        - optional_config_fields: list[str]
        - rate_limits: dict
        """
        pass
    
    @abc.abstractmethod
    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        """
        Validate the connector instance configuration.
        
        Returns: (is_valid, error_message)
        """
        pass
    
    @abc.abstractmethod
    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        """
        Get the health status of the connector instance.
        
        Returns dict with:
        - status: 'healthy'|'degraded'|'unhealthy'|'unknown'
        - last_check: datetime
        - details: dict
        - latency_ms: int
"""
        pass
    
    @abc.abstractmethod
    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        """
        Validate webhook signature for security.
        
        Returns True if signature is valid.
        """
        pass
    
    @abc.abstractmethod
    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        """
        Get the connector's declared capabilities.
        
        Returns the connector's capability matrix.
        """
        pass


class ConnectorRegistry:
    
    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}
    
    def register(self, connector: BaseConnector) -> None:
        """Register a connector implementation."""
        key = f"{connector.kind}:{connector.provider}"
        self._connectors[key] = connector
    
    def get(self, kind: str, provider: str) -> Optional[BaseConnector]:
        """Get a connector by kind and provider."""
        return self._connectors.get(f"{kind}:{provider}")
    
    def get_by_instance(self, instance: ConnectorInstance) -> Optional[BaseConnector]:
        """Get connector for an instance."""
        return self.get(instance.connector.kind, instance.connector.provider) if instance.connector else None


# Global registry
connector_registry = ConnectorRegistry()