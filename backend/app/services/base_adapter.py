"""Base Connector Adapter — abstract base for provider-specific adapters."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("vcos.integration.adapters")


class SyncMode(Enum):
    INITIAL = "initial"
    INCREMENTAL = "incremental"
    WEBHOOK = "webhook"
    POLLING = "polling"
    REPLAY = "replay"


class SyncState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


@dataclass
class SyncResult:
    """Result of a sync operation."""
    entities_processed: int = 0
    entities_created: int = 0
    entities_updated: int = 0
    entities_deleted: int = 0
    entities_failed: int = 0
    conflicts_detected: int = 0
    events_processed: int = 0
    duration_ms: int = 0
    cursor_before: Optional[str] = None
    cursor_after: Optional[str] = None
    error: Optional[str] = None


class BaseConnectorAdapter:
    """Base class for provider-specific connector adapters.

    Each provider (Google, Microsoft, Slack, GitHub, Jira) implements this interface.
    """

    provider_name: str = "base"

    async def authenticate(self, instance: Any) -> bool:
        """Authenticate with the external provider."""
        logger.warning("authenticate() not implemented, returning False")
        return False

    async def test_connection(self, instance: Any) -> Dict[str, Any]:
        """Test connection to the provider."""
        return {"success": False, "error": "test_connection() not implemented"}

    async def get_initial_cursor(self, instance: Any, entity_type: str) -> str:
        """Get initial cursor for a full sync."""
        return ""

    async def get_incremental_cursor(self, instance: Any, entity_type: str, cursor: str) -> str:
        """Get next cursor for incremental sync."""
        return ""

    async def fetch_page(
        self,
        instance: Any,
        entity_type: str,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """Fetch a page of entities from the provider.

        Returns:
            {
                "entities": [...],
                "next_cursor": str,
                "has_more": bool,
                "total_count": int,
            }
        """
        return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}

    async def fetch_entity(
        self,
        instance: Any,
        entity_type: str,
        external_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single entity by external ID."""
        return None

    async def get_deleted_entities(
        self,
        instance: Any,
        entity_type: str,
        since: datetime,
    ) -> List[str]:
        """Get list of deleted entity external IDs since timestamp."""
        return []

    async def execute_operation(
        self,
        *,
        instance: Any,
        operation_type: str,
        entity_type: str,
        external_id: Optional[str],
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute an outbound operation against the external system.

        Returns: {"external_operation_id": str, "payload": dict}

        Providers that do not support outbound execution leave this
        unimplemented; callers treat NotImplementedError as an explicit
        capability gap (never faked success, never silent failure).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support outbound operation execution"
        )

    async def get_rate_limit_status(self, instance: Any) -> Dict[str, Any]:
        """Get current rate limit status."""
        return {"remaining": 0, "limit": 0, "reset_at": None}

    async def handle_rate_limit(self, instance: Any, reset_at: datetime) -> bool:
        """Handle rate limit - return True if should retry."""
        return False

    def _get_supported_entity_types(self) -> List[str]:
        """Get list of entity types this adapter supports."""
        return []

    def _extract_external_id(self, entity_type: str, entity: Dict) -> Optional[str]:
        """Extract external ID from entity based on type."""
        return entity.get("id") or entity.get("external_id")