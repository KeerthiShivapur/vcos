"""Event subscriber registry — decorator-driven handler wiring.

Usage::

    from app.events.subscriber import on

    @on("task.completed")
    async def handle_task_completed(db, event, payload):
        ...
"""

import logging
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("vcos.events.subscriber")

Handler = Callable[[AsyncSession, Any, dict[str, Any]], Awaitable[None]]

_HANDLERS: dict[str, list[Handler]] = {}


def on(event_name: str) -> Callable[[Handler], Handler]:
    """Register a handler for an event name (idempotent)."""

    def _wrap(handler: Handler) -> Handler:
        if event_name not in _HANDLERS:
            _HANDLERS[event_name] = []
        if handler not in _HANDLERS[event_name]:
            _HANDLERS[event_name].append(handler)
        logger.debug("registered handler %s for %s", handler.__name__, event_name)
        return handler

    return _wrap


def get_handlers(event_name: str) -> list[Handler]:
    return list(_HANDLERS.get(event_name, []))


def registered_events() -> list[str]:
    return sorted(_HANDLERS.keys())


async def dispatch(db: AsyncSession, event_name: str, event: Any, payload: dict[str, Any]) -> int:
    """Run every handler for an event; returns number of handlers executed."""
    executed = 0
    for handler in get_handlers(event_name):
        try:
            await handler(db, event, payload)
            executed += 1
        except Exception as exc:  # noqa: BLE001 - per-handler isolation
            logger.exception("handler %s failed for %s: %s", handler.__name__, event_name, exc)
    return executed
