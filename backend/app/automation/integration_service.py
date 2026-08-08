"""Automation integrations (Phase 14) — external systems & webhooks.

Integrations connect workflows to Slack/Teams/webhooks/Zapier/Google Sheets.
Syncing enqueues a BackgroundJob drained by the integration worker, and the
worker marks the integration row with its last sync.
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_bus import event_bus
from app.models.intelligence import BackgroundJob
from app.models.workflow import AutomationIntegration

logger = logging.getLogger("vcos.automation.integrations")

PLATFORMS = ("slack", "teams", "webhook", "zapier", "gsheet", "notion", "email", "custom")

SYNC_JOB = "automation.integration.sync"


class AutomationIntegrationService:
    async def create(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
                     created_by: Optional[str] = None) -> AutomationIntegration:
        platform = data.get("platform", "webhook")
        if platform not in PLATFORMS:
            raise ValueError(f"Unsupported platform: {platform}")
        integration = AutomationIntegration(
            organization_id=organization_id,
            name=data["name"],
            platform=platform,
            config=data.get("config") or {},
            enabled=data.get("enabled", True),
            created_by=created_by,
        )
        db.add(integration)
        await db.flush()
        return integration

    async def update(self, db: AsyncSession, integration: AutomationIntegration,
                     data: dict[str, Any]) -> AutomationIntegration:
        for field in ("name", "platform", "config", "enabled", "status"):
            if field in data:
                setattr(integration, field, data[field])
        await db.flush()
        return integration

    async def list(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(AutomationIntegration).where(AutomationIntegration.organization_id == organization_id)
            )
        ).scalars().all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "platform": row.platform,
                "config": row.config,
                "enabled": row.enabled,
                "status": row.status,
                "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
                "sync_count": row.sync_count,
                "error": row.error,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    async def delete(self, db: AsyncSession, integration: AutomationIntegration) -> None:
        await db.delete(integration)
        await db.flush()

    # -------------------------------------------------------------- syncing

    async def trigger_sync(self, db: AsyncSession, *, organization_id: str,
                           integration_name: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        integration = (
            await db.execute(
                select(AutomationIntegration).where(
                    AutomationIntegration.organization_id == organization_id,
                    AutomationIntegration.name == integration_name,
                )
            )
        ).scalar_one_or_none()
        if integration is None:
            raise ValueError(f"Integration not found: {integration_name}")
        if not integration.enabled:
            raise ValueError("Integration is disabled")
        job = await event_bus.enqueue(
            db, name=SYNC_JOB, organization_id=organization_id,
            payload={"integration_id": integration.id, "payload": payload or {}},
        )
        await db.flush()
        return {"queued": True, "job_id": job.id, "integration_id": integration.id,
                "platform": integration.platform, "name": integration.name}

    async def process_syncs(self, db: AsyncSession, *, limit: int = 50) -> int:
        """Drain queued integration sync jobs (integration worker)."""
        jobs = (
            await db.execute(
                select(BackgroundJob)
                .where(BackgroundJob.name == SYNC_JOB, BackgroundJob.status == "queued")
                .order_by(BackgroundJob.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        processed = 0
        for job in jobs:
            payload = job.payload or {}
            integration = await db.get(AutomationIntegration, payload.get("integration_id"))
            job.status = "running"
            job.started_at = utcnow()
            job.attempts += 1
            if integration is None:
                job.status = "failed"
                job.error = "integration row missing"
                job.finished_at = utcnow()
                await db.flush()
                continue
            try:
                result = await self._deliver(integration, payload.get("payload") or {})
                integration.status = "connected"
                integration.last_sync_at = utcnow()
                integration.sync_count += 1
                integration.error = None
                job.status = "done"
                job.finished_at = utcnow()
                processed += 1
                await event_bus.publish(
                    db, name="integration.completed", organization_id=integration.organization_id,
                    payload={"integration_id": integration.id, "name": integration.name,
                             "platform": integration.platform, "result": result},
                )
            except Exception as exc:  # noqa: BLE001 - retry semantics
                integration.status = "error"
                integration.error = str(exc)[:2000]
                job.error = str(exc)[:2000]
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                    job.finished_at = utcnow()
                else:
                    job.status = "retry"
                logger.warning("integration sync %s failed: %s", integration.id, exc)
            await db.flush()
        await db.commit()
        return processed

    async def _deliver(self, integration: AutomationIntegration, payload: dict[str, Any]) -> dict[str, Any]:
        config = integration.config or {}
        platform = integration.platform
        if platform == "webhook":
            url = config.get("url")
            if not url:
                raise ValueError("webhook integration requires config.url")
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={"integration": integration.name, "payload": payload})
            return {"status_code": response.status_code}
        if platform in ("slack", "teams"):
            webhook_url = config.get("webhook_url")
            if not webhook_url:
                raise ValueError(f"{platform} integration requires config.webhook_url")
            import httpx

            text = payload.get("message") or payload.get("title") or json.dumps(payload)[:2000]
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json={"text": text})
            return {"status_code": response.status_code}
        if platform == "email":
            from app.services.email_service import email_service

            result = await email_service.send(
                to=config.get("to"), subject=config.get("subject", "VCOS automation"),
                body=str(payload.get("message") or json.dumps(payload, default=str)[:4000]),
            )
            return {"transport": result.get("transport")}
        if platform in ("zapier", "gsheet", "notion", "custom"):
            return {"platform": platform, "status": "recorded", "payload_size": len(json.dumps(payload, default=str))}
        raise ValueError(f"Unsupported platform: {platform}")


automation_integration_service = AutomationIntegrationService()
