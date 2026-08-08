"""Event publisher (Phase 9.6) — the single entry point for emitting events.

Two flavors are provided:

- ``publish_event`` — business events that need background reactions; a
  dispatch job is enqueued so the event worker picks it up (durable delivery).
- ``publish_background_event`` — audit events emitted by engines/workers
  themselves (e.g. ``expertise.updated``). They are persisted into the event
  stream so the organization can see everything the background layer did, but
  they do not enqueue jobs — nothing subscribes to the background layer's own
  actions, so a job would only add queue noise.
"""

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.event_bus import event_bus
from app.models.notification import Event as EventRow

logger = logging.getLogger("vcos.events.publisher")


async def publish_event(
    db: AsyncSession,
    *,
    name: str,
    organization_id: Optional[str],
    actor_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> EventRow:
    """Persist an event and enqueue its dispatch job (durable delivery)."""
    return await event_bus.publish(
        db,
        name=name,
        organization_id=organization_id,
        actor_id=actor_id,
        payload=payload,
        enqueue=True,
    )


async def publish_background_event(
    db: AsyncSession,
    *,
    name: str,
    organization_id: Optional[str],
    payload: Optional[dict[str, Any]] = None,
) -> EventRow:
    """Persist a background/engine-generated event for the audit stream.

    No dispatch job is enqueued: these events document what the autonomous
    layer did. The event worker's orphan pass marks them processed so they
    never accumulate as unprocessed rows.
    """
    return await event_bus.publish(
        db,
        name=name,
        organization_id=organization_id,
        payload=payload,
        enqueue=False,
    )
