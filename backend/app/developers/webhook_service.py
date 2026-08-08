from __future__ import annotations

"""Webhook management service (Phase 18.13) â€” endpoints & delivery queue.

Organizations register webhook endpoints subscribed to event names; the
background webhook worker delivers pending WebhookDelivery rows with
HMAC-SHA256 signatures and retries.
"""

import hmac
import hashlib
import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.developer import WebhookDelivery, WebhookEndpoint

ENDPOINT_STATUSES = ("active", "paused", "failing")


class WebhookService:
    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        name: str,
        url: str,
        events: Optional[list[str]] = None,
        secret: Optional[str] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        row = WebhookEndpoint(
            organization_id=organization_id,
            name=name,
            url=url,
            events=events or [],
            secret=secret,
            status="active",
        )
        db.add(row)
        await db.flush()
        if commit:
            await db.commit()
        return self.serialize(row)

    async def list(self, db: AsyncSession, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(WebhookEndpoint)
                .where(WebhookEndpoint.organization_id == organization_id)
                .order_by(WebhookEndpoint.created_at.desc())
            )
        ).scalars().all()
        return [self.serialize(r) for r in rows]

    async def get(self, db: AsyncSession, organization_id: str, endpoint_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.organization_id == organization_id,
                    WebhookEndpoint.id == endpoint_id,
                )
            )
        ).scalars().first()
        return self.serialize(row) if row else None

    async def get_raw(self, db: AsyncSession, organization_id: str, endpoint_id: str) -> Optional[WebhookEndpoint]:
        return (
            await db.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.organization_id == organization_id,
                    WebhookEndpoint.id == endpoint_id,
                )
            )
        ).scalars().first()

    async def set_status(
        self,
        db: AsyncSession,
        organization_id: str,
        endpoint_id: str,
        status: str,
    ) -> Optional[dict[str, Any]]:
        if status not in ENDPOINT_STATUSES:
            raise ValueError(f"status must be one of {ENDPOINT_STATUSES}")
        row = (
            await db.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.organization_id == organization_id,
                    WebhookEndpoint.id == endpoint_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        row.status = status
        if status == "active":
            row.failure_count = 0
        await db.flush()
        return self.serialize(row)

    async def delete(self, db: AsyncSession, organization_id: str, endpoint_id: str) -> bool:
        row = (
            await db.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.organization_id == organization_id,
                    WebhookEndpoint.id == endpoint_id,
                )
            )
        ).scalars().first()
        if row is None:
            return False
        await db.delete(row)
        await db.flush()
        return True

    async def enqueue(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        event_name: str,
        payload: dict[str, Any],
    ) -> int:
        endpoints = (
            await db.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.organization_id == organization_id,
                    WebhookEndpoint.status.in_(("active", "failing")),
                )
            )
        ).scalars().all()
        enqueued = 0
        for endpoint in endpoints:
            if endpoint.events and event_name not in endpoint.events:
                continue
            db.add(
                WebhookDelivery(
                    organization_id=organization_id,
                    endpoint_id=endpoint.id,
                    event_name=event_name,
                    payload_json=json.dumps(payload, default=str),
                    status="pending",
                    attempts=0,
                )
            )
            enqueued += 1
        await db.flush()
        if enqueued:
            await publish_background_event(
                db, name="webhook.queued", organization_id=organization_id,
                payload={"event_name": event_name, "enqueued": enqueued},
            )
        return enqueued

    async def deliveries(
        self,
        db: AsyncSession,
        organization_id: str,
        endpoint_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        stmt = select(WebhookDelivery).where(WebhookDelivery.organization_id == organization_id)
        if endpoint_id:
            stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
        rows = (
            await db.execute(stmt.order_by(WebhookDelivery.created_at.desc()).limit(limit))
        ).scalars().all()
        return [self.serialize_delivery(r) for r in rows]

    async def redeliver(
        self, db: AsyncSession, organization_id: str, delivery_id: str
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(WebhookDelivery).where(
                    WebhookDelivery.organization_id == organization_id,
                    WebhookDelivery.id == delivery_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        row.status = "pending"
        row.attempts = 0
        row.error = None
        row.next_attempt_at = utcnow()
        await db.flush()
        return self.serialize_delivery(row)

    def sign_payload(self, payload: dict[str, Any], secret: Optional[str]) -> Optional[str]:
        if not secret:
            return None
        body = json.dumps(payload, default=str).encode()
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def serialize(self, row: WebhookEndpoint) -> dict[str, Any]:
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "name": row.name,
            "url": row.url,
            "events": row.events or [],
            "status": row.status,
            "success_count": row.success_count,
            "failure_count": row.failure_count,
            "last_delivered_at": row.last_delivered_at.isoformat() if row.last_delivered_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def serialize_delivery(self, row: WebhookDelivery) -> dict[str, Any]:
        return {
            "id": row.id,
            "endpoint_id": row.endpoint_id,
            "event_name": row.event_name,
            "attempts": row.attempts,
            "status": row.status,
            "response_code": row.response_code,
            "response_body": row.response_body,
            "error": row.error,
            "next_attempt_at": row.next_attempt_at.isoformat() if row.next_attempt_at else None,
            "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


webhook_service = WebhookService()
