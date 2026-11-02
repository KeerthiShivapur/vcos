import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.notification import Event

logger = logging.getLogger("vcos.events")


class EventService:
    """Event bus: every important action emits an event.

    Events are persisted (reliable, replayable) and, when Redis is enabled,
    published to a pub/sub channel so future workers can react in real time.
    """

    def __init__(self) -> None:
        self._redis = None
        self._redis_error: Optional[str] = None

    async def _get_redis(self):
        settings = get_settings()
        if not settings.REDIS_ENABLED or not settings.REDIS_URL:
            return None
        if self._redis is None and self._redis_error is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                await self._redis.ping()
            except Exception as exc:  # pragma: no cover - depends on infra
                self._redis_error = str(exc)
                logger.warning("Redis unavailable, events are DB-only: %s", exc)
                self._redis = None
        return self._redis

    async def emit(
        self,
        db: AsyncSession,
        *,
        name: str,
        actor_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        flush: bool = True,
    ) -> Event:
        event = Event(
            name=name,
            actor_id=actor_id,
            organization_id=organization_id,
            payload=payload if payload is not None else {},
        )
        db.add(event)
        if flush:
            await db.flush()

        try:
            redis = await self._get_redis()
            if redis is not None:
                await redis.publish(
                    "vcos:events",
                    json.dumps(
                        {"name": name, "actor_id": actor_id, "organization_id": organization_id, "payload": payload},
                        default=str,
                    ),
                )
        except Exception as exc:  # pragma: no cover
            logger.debug("event publish failed: %s", exc)
        return event


event_service = EventService()
