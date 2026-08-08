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

VALID_KINDS = ("webhook", "api", "app", "datasource")


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
