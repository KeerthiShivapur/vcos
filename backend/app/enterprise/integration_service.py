"""Integration connection service (Phase 15).

Create, test, sync and remove external integration connections (webhooks,
apps, external services). Testing performs a deterministic handshake against
the stored config; syncing records the sync timestamp and publishes the
integration.synced event for workflow automation.
"""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.enterprise import IntegrationConnection
from app.services.provider_adapters import (
    GoogleWorkspaceAdapter, SlackAdapter, GitHubAdapter, JiraAdapter,
    Microsoft365Adapter,
)

VALID_KINDS = ("webhook", "api", "app", "datasource")

# Provider adapter map
PROVIDER_ADAPTERS = {
    "google": GoogleWorkspaceAdapter,
    "slack": SlackAdapter,
    "github": GitHubAdapter,
    "jira": JiraAdapter,
    "microsoft": Microsoft365Adapter,
}


class MockAdapterInstance:
    """Mock instance for provider adapters using IntegrationConnection data."""
    def __init__(self, connection: 'IntegrationConnection'):
        self.config = connection.config or {}
        self.credentials = {
            "access_token": connection.access_token,
            "refresh_token": connection.refresh_token,
            "client_id": (connection.config or {}).get("client_id"),
            "client_secret": (connection.config or {}).get("client_secret"),
            "personal_access_token": (connection.config or {}).get("personal_access_token"),
        }
        self.id = connection.id
        self.provider = connection.provider
        self.name = connection.name


class IntegrationService:
    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        name: str,
        provider: str,
        kind: str = "webhook",
        config: Optional[dict[str, Any]] = None,
        auth_type: str = "oauth2",
        actor_id: Optional[str] = None,
    ) -> IntegrationConnection:
        if kind not in VALID_KINDS:
            raise ValueError(f"invalid integration kind: {kind}")
        errors = self.validate_config(kind, config or {})
        if errors:
            raise ValueError(f"invalid integration config: {', '.join(errors)}")
        connection = IntegrationConnection(
            organization_id=organization_id,
            name=name,
            provider=provider,
            kind=kind,
            config=config or {},
            auth_type=auth_type,
            status="active",
            connected_at=utcnow(),
        )
        db.add(connection)
        await db.flush()
        await publish_event(
            db,
            name="integration.connected",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"integration_id": connection.id, "name": name, "provider": provider},
        )
        return connection

    def validate_config(self, kind: str, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if kind == "webhook" and not config.get("url"):
            errors.append("url is required for webhook integrations")
        if kind in ("api", "datasource") and not config.get("base_url"):
            errors.append("base_url is required")
        if auth_type := config.get("auth_type"):
            if auth_type == "oauth2" and not (config.get("client_id") and config.get("client_secret")):
                errors.append("oauth2 requires client_id and client_secret")
        return errors

    async def list_connections(
        self, db: AsyncSession, organization_id: str, status: Optional[str] = None
    ) -> list[IntegrationConnection]:
        query = select(IntegrationConnection).where(
            IntegrationConnection.organization_id == organization_id
        )
        if status:
            query = query.where(IntegrationConnection.status == status)
        result = await db.execute(query.order_by(IntegrationConnection.created_at.desc()))
        return list(result.scalars().all())

    async def get(
        self, db: AsyncSession, organization_id: str, connection_id: str
    ) -> Optional[IntegrationConnection]:
        connection = await db.get(IntegrationConnection, connection_id)
        if connection is None or connection.organization_id != organization_id:
            return None
        return connection

    async def update(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connection_id: str,
        **fields: Any,
    ) -> Optional[IntegrationConnection]:
        connection = await self.get(db, organization_id, connection_id)
        if connection is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(connection, key, value)
        return connection

    async def test(
        self, db: AsyncSession, *, organization_id: str, connection_id: str
    ) -> Optional[dict[str, Any]]:
        connection = await self.get(db, organization_id, connection_id)
        if connection is None:
            return None
        
        provider = connection.provider.lower()
        adapter_class = PROVIDER_ADAPTERS.get(provider)
        
        if adapter_class and connection.access_token:
            # Use provider-specific adapter for testing
            mock_instance = MockAdapterInstance(connection)
            adapter = adapter_class(mock_instance)
            try:
                result = await adapter.test_connection(mock_instance)
                connection.status = "active" if result.get("success") else "error"
                if not result.get("success"):
                    connection.error = result.get("error", "Connection test failed")
                else:
                    connection.error = None
                await publish_event(
                    db,
                    name="integration.tested",
                    organization_id=organization_id,
                    payload={"integration_id": connection.id, "provider": connection.provider, "result": result},
                )
                return {"integration_id": connection.id, "status": connection.status, "detail": result.get("detail", result.get("error", "Test completed"))}
            except Exception as e:
                connection.status = "error"
                connection.error = f"Test failed: {str(e)}"
                return {"integration_id": connection.id, "status": "error", "detail": f"Test failed: {str(e)}"}
        
        # Fallback to basic config validation
        config = connection.config or {}
        ok, reason = True, "handshake ok"
        if connection.kind == "webhook":
            ok, reason = bool(config.get("url")), "webhook endpoint configured"
        elif connection.kind in ("api", "datasource"):
            ok, reason = bool(config.get("base_url")), "base endpoint configured"
        status = "active" if ok else "error"
        connection.status = status
        if not ok:
            connection.error = reason
        return {"integration_id": connection.id, "status": status, "detail": reason}

    async def sync(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connection_id: str,
        actor_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        connection = await self.get(db, organization_id, connection_id)
        if connection is None:
            return None
        if connection.status != "active":
            raise ValueError("integration is not active")
        
        provider = connection.provider.lower()
        adapter_class = PROVIDER_ADAPTERS.get(provider)
        
        if adapter_class and connection.access_token:
            # Use provider-specific adapter for synchronization
            mock_instance = MockAdapterInstance(connection)
            adapter = adapter_class(mock_instance)
            try:
                # Get supported entity types for this provider
                entity_types = adapter._get_supported_entity_types() if hasattr(adapter, '_get_supported_entity_types') else []
                
                sync_results = {}
                total_entities = 0
                
                for entity_type in entity_types:
                    try:
                        result = await adapter.fetch_page(mock_instance, entity_type, page_size=100)
                        entities = result.get("entities", [])
                        sync_results[entity_type] = {
                            "count": len(entities),
                            "next_cursor": result.get("next_cursor"),
                            "has_more": result.get("has_more", False),
                        }
                        total_entities += len(entities)
                    except Exception as e:
                        sync_results[entity_type] = {"error": str(e), "count": 0}
                
                connection.last_sync_at = utcnow()
                connection.error = None
                
                await publish_event(
                    db,
                    name="integration.synced",
                    organization_id=organization_id,
                    actor_id=actor_id,
                    payload={
                        "integration_id": connection.id,
                        "name": connection.name,
                        "provider": connection.provider,
                        "entities_synced": total_entities,
                        "sync_results": sync_results,
                    },
                )
                
                return {
                    "integration_id": connection.id,
                    "status": connection.status,
                    "last_sync_at": connection.last_sync_at,
                    "entities_synced": total_entities,
                    "sync_results": sync_results,
                }
            except Exception as e:
                connection.error = f"Sync failed: {str(e)}"
                await publish_event(
                    db,
                    name="integration.sync_failed",
                    organization_id=organization_id,
                    actor_id=actor_id,
                    payload={"integration_id": connection.id, "provider": connection.provider, "error": str(e)},
                )
                return {
                    "integration_id": connection.id,
                    "status": "error",
                    "last_sync_at": connection.last_sync_at,
                    "error": str(e),
                }
        
        # Fallback: just update timestamp for basic integrations
        connection.last_sync_at = utcnow()
        await publish_event(
            db,
            name="integration.synced",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={
                "integration_id": connection.id,
                "name": connection.name,
                "provider": connection.provider,
            },
        )
        return {
            "integration_id": connection.id,
            "status": connection.status,
            "last_sync_at": connection.last_sync_at,
        }

    async def remove(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connection_id: str,
        actor_id: Optional[str] = None,
    ) -> bool:
        connection = await self.get(db, organization_id, connection_id)
        if connection is None:
            return False
        await db.delete(connection)
        await publish_event(
            db,
            name="integration.disconnected",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"integration_id": connection_id},
        )
        return True


integration_service = IntegrationService()
