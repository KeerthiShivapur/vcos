"""Event processor (Phase 9.6) — orchestration facade for the event layer.

The event worker's job is one call: ``process_pending(db)``. This module is
the stable seam between workers/engines and the bus so callers never need to
import ``app.events.event_bus`` or the subscriber registry directly. It also
guarantees handler modules are imported (registration side effect) before any
dispatch pass runs.
"""

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("vcos.events.processor")


async def process_pending(db: AsyncSession, *, limit: int = 100,
                          event_names: Optional[list[str]] = None) -> int:
    """Run one dispatch pass: queue events are delivered to their handlers.

    Returns the number of events processed (including events with no handlers,
    which are marked processed so they are never rescanned).
    """
    from app.events.event_bus import event_bus

    return await event_bus.process_pending(db, limit=limit, event_names=event_names)


async def retry_failed(db: AsyncSession, *, limit: int = 50) -> int:
    """Reset permanently failed dispatch jobs so they get another window."""
    from app.events.event_bus import event_bus

    return await event_bus.retry_failed(db, limit=limit)


async def stats(db: AsyncSession, *, organization_id: Optional[str] = None) -> dict[str, Any]:
    from app.events.event_bus import event_bus

    return await event_bus.stats(db, organization_id=organization_id)


async def recent_events(db: AsyncSession, *, organization_id: Optional[str] = None,
                        limit: int = 50, processed: Optional[bool] = None) -> list[dict[str, Any]]:
    from app.events.event_bus import event_bus

    return await event_bus.recent_events(
        db, organization_id=organization_id, limit=limit, processed=processed
    )


async def recent_jobs(db: AsyncSession, *, organization_id: Optional[str] = None,
                      limit: int = 50, status: Optional[str] = None) -> list[dict[str, Any]]:
    from app.events.event_bus import event_bus

    return await event_bus.recent_jobs(
        db, organization_id=organization_id, limit=limit, status=status
    )


def registered_handlers() -> list[str]:
    """Event names that currently have at least one handler registered."""
    from app.events.subscriber import registered_events

    return registered_events()


def ensure_handlers_imported() -> None:
    """Import the handler modules so their @on(...) registrations run."""
    from app.events import handlers  # noqa: F401
