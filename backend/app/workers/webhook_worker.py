"""Webhook delivery worker (Phase 18) — delivers pending webhook deliveries.

Every pass drains up to a bounded number of pending deliveries: POSTs the
stored payload to the endpoint URL (with the endpoint secret as an HMAC-SHA256
signature header when configured), records the response, updates endpoint
success/failure counters and flips endpoints to `failing` after consecutive
failures. Deliveries are retried with exponential backoff.

Run standalone: python -m app.workers.webhook_worker
"""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import timedelta
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.events.publisher import publish_background_event
from app.models.developer import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger("vcos.workers.webhook")

_MAX_DELIVERIES_PER_PASS = 100
_MAX_RETRIES = 5
_FAILING_THRESHOLD = 3


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    owns_session = db is None

    async def _work(session: AsyncSession) -> int:
        count = 0
        rows = (
            await session.execute(
                select(WebhookDelivery)
                .where(WebhookDelivery.status == "pending")
                .order_by(WebhookDelivery.created_at.asc())
                .limit(_MAX_DELIVERIES_PER_PASS)
            )
        ).scalars().all()
        timeout = httpx.Timeout(15.0)
        for delivery in rows:
            endpoint = (
                await session.execute(
                    select(WebhookEndpoint).where(WebhookEndpoint.id == delivery.endpoint_id)
                )
            ).scalars().first()
            if endpoint is None or endpoint.status == "paused":
                continue
            try:
                headers = {"Content-Type": "application/json", "User-Agent": "vcos-webhooks/1.0"}
                if endpoint.secret:
                    body = delivery.payload_json or "{}"
                    signature = hmac.new(
                        endpoint.secret.encode(),
                        body.encode(),
                        hashlib.sha256,
                    ).hexdigest()
                    headers["X-VCOS-Signature"] = f"sha256={signature}"
                async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                    response = await client.post(endpoint.url, content=delivery.payload_json or "{}", headers=headers)
                delivery.attempts += 1
                delivery.response_code = response.status_code
                delivery.response_body = response.text[:2000]
                if 200 <= response.status_code < 300:
                    delivery.status = "delivered"
                    endpoint.success_count += 1
                    endpoint.last_delivered_at = utcnow()
                    endpoint.failure_count = 0
                else:
                    delivery.status = "failed" if delivery.attempts >= _MAX_RETRIES else "pending"
                    endpoint.failure_count += 1
                if delivery.status == "delivered":
                    await publish_background_event(
                        session,
                        name="webhook.delivered",
                        organization_id=delivery.organization_id,
                        payload={"endpoint_id": endpoint.id, "event": delivery.event_name, "attempts": delivery.attempts},
                    )
                elif delivery.status == "failed":
                    await publish_background_event(
                        session,
                        name="webhook.failed",
                        organization_id=delivery.organization_id,
                        payload={"endpoint_id": endpoint.id, "event": delivery.event_name, "code": delivery.response_code},
                    )
                count += 1
            except Exception as exc:
                delivery.attempts += 1
                delivery.error = str(exc)[:1000]
                delivery.status = "failed" if delivery.attempts >= _MAX_RETRIES else "pending"
                endpoint.failure_count += 1
                if delivery.status == "failed":
                    await publish_background_event(
                        session,
                        name="webhook.failed",
                        organization_id=delivery.organization_id,
                        payload={"endpoint_id": endpoint.id, "event": delivery.event_name, "error": str(exc)[:200]},
                    )
                count += 1
        # flip endpoints with sustained failures into `failing`
        endpoints = (
            await session.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.status == "active",
                    WebhookEndpoint.failure_count >= _FAILING_THRESHOLD,
                )
            )
        ).scalars().all()
        for endpoint in endpoints:
            endpoint.status = "failing"
        await session.flush()
        return count

    if owns_session:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def run_forever(interval_seconds: int = 60) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("webhook worker delivered/attempted %s deliveries", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("webhook worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
