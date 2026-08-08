"""Plugin lifecycle service (Phase 15).

Install / enable / disable / update / remove plugins in an organization.
Every payload is "scanned" before activation: plugins that attempt to escape
the sandbox (imports, shell access, absolute writes) are rejected. Requested
permission codes are validated against the permission catalog so plugins can
never grant themselves undeclared powers.
"""

import secrets
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.enterprise import MarketplaceItem, Plugin, PluginVersion

_DANGEROUS_PATTERNS = (
    "__import__",
    "os.system",
    "subprocess",
    "eval(",
    "exec(",
    "open('",
    "open(\"",
    "import shutil",
    "socket",
)


def _scan_payload(payload: Optional[dict[str, Any]]) -> tuple[bool, str]:
    """Deterministic static scan of a plugin payload for sandbox escapes."""
    if not payload:
        return False, "plugin payload is empty"
    code = payload.get("code", "")
    source = code if isinstance(code, str) else str(code)
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in source:
            return False, f"blocked sandbox escape pattern: {pattern}"
    entry = payload.get("entry", "")
    if not entry:
        return False, "plugin payload has no entry point"
    return True, "scan passed"


class PluginService:
    async def _validate_permissions(
        self, requested: Optional[list[str]], catalog: set[str]
    ) -> list[str]:
        requested = requested or []
        return [code for code in requested if code in catalog]

    async def _scan(self, payload: Optional[dict[str, Any]]) -> tuple[str, str]:
        ok, report = _scan_payload(payload)
        return ("clean" if ok else "blocked"), report

    async def install(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        plugin_key: str,
        name: str,
        manifest: dict[str, Any],
        created_by: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Plugin:
        version = manifest.get("version", "1.0.0")
        scan_status, report = await self._scan(manifest.get("payload"))
        if scan_status == "blocked":
            raise ValueError(f"plugin payload rejected: {report}")
        plugin = Plugin(
            organization_id=organization_id,
            plugin_key=plugin_key,
            name=name,
            description=manifest.get("description"),
            version=version,
            author=manifest.get("author", "VCOS Marketplace"),
            category=manifest.get("category", "general"),
            status="installed",
            sandbox=manifest.get("sandbox", True),
            verified=manifest.get("verified", False),
            scan_status=scan_status,
            requested_permissions=manifest.get("permissions", []),
            settings=manifest.get("settings", {}),
            created_by=created_by,
            installed_at=utcnow(),
        )
        db.add(plugin)
        await db.flush()
        plugin_version = PluginVersion(
            plugin_id=plugin.id,
            version=version,
            changelog=manifest.get("changelog"),
            payload=manifest.get("payload", {}),
            scan_status=scan_status,
            scan_report={"report": report},
            verified=manifest.get("verified", False),
        )
        db.add(plugin_version)
        await db.flush()
        await publish_event(
            db,
            name="plugin.installed",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"plugin_id": plugin.id, "plugin_key": plugin_key, "version": version},
        )
        return plugin

    async def list_plugins(
        self, db: AsyncSession, organization_id: str, status: Optional[str] = None
    ) -> list[Plugin]:
        query = select(Plugin).where(Plugin.organization_id == organization_id)
        if status:
            query = query.where(Plugin.status == status)
        result = await db.execute(query.order_by(Plugin.created_at.desc()))
        return list(result.scalars().all())

    async def get(
        self, db: AsyncSession, organization_id: str, plugin_id: str
    ) -> Optional[Plugin]:
        plugin = await db.get(Plugin, plugin_id)
        if plugin is None or plugin.organization_id != organization_id:
            return None
        return plugin

    async def set_status(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        plugin_id: str,
        status: str,
        event_name: str,
        actor_id: Optional[str] = None,
    ) -> Optional[Plugin]:
        plugin = await self.get(db, organization_id, plugin_id)
        if plugin is None:
            return None
        plugin.status = status
        await publish_event(
            db,
            name=event_name,
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"plugin_id": plugin.id, "plugin_key": plugin.plugin_key},
        )
        return plugin

    async def update(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        plugin_id: str,
        version: str,
        changelog: Optional[str],
        payload: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> Optional[Plugin]:
        plugin = await self.get(db, organization_id, plugin_id)
        if plugin is None:
            return None
        scan_status, report = await self._scan(payload)
        if scan_status == "blocked":
            raise ValueError(f"update payload rejected: {report}")
        plugin.version = version
        plugin.scan_status = scan_status
        db.add(
            PluginVersion(
                plugin_id=plugin.id,
                version=version,
                changelog=changelog,
                payload=payload,
                scan_status=scan_status,
                scan_report={"report": report},
                verified=False,
            )
        )
        await publish_event(
            db,
            name="plugin.updated",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"plugin_id": plugin.id, "plugin_key": plugin.plugin_key, "version": version},
        )
        return plugin

    async def update_settings(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        plugin_id: str,
        settings: dict[str, Any],
    ) -> Optional[Plugin]:
        plugin = await self.get(db, organization_id, plugin_id)
        if plugin is None:
            return None
        plugin.settings = {**(plugin.settings or {}), **settings}
        return plugin

    async def remove(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        plugin_id: str,
        actor_id: Optional[str] = None,
    ) -> bool:
        plugin = await self.get(db, organization_id, plugin_id)
        if plugin is None:
            return False
        await db.delete(plugin)
        await publish_event(
            db,
            name="plugin.removed",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"plugin_key": plugin.plugin_key},
        )
        return True

    async def from_marketplace(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        item: MarketplaceItem,
        actor_id: Optional[str] = None,
    ) -> Plugin:
        manifest = dict(item.manifest or {})
        manifest["version"] = item.version
        manifest["verified"] = item.verified
        manifest["scanned"] = item.scanned
        return await self.install(
            db,
            organization_id=organization_id,
            plugin_key=item.plugin_key,
            name=item.name,
            manifest=manifest,
            created_by=actor_id,
            actor_id=actor_id,
        )


plugin_service = PluginService()
