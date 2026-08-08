"""Rate limiting with optional Redis backing.

Falls back to an in-process sliding window when Redis is unavailable so the
platform never depends on infrastructure to be safe.
"""

import time
from collections import defaultdict, deque
from typing import Optional

from app.core.config import get_settings


class RateLimiter:
    def __init__(self) -> None:
        self._memory: dict[str, deque[float]] = defaultdict(deque)
        self._redis = None
        self._redis_error: Optional[str] = None

    async def _redis_client(self):
        settings = get_settings()
        if not settings.REDIS_ENABLED or not settings.REDIS_URL:
            return None
        if self._redis is None and self._redis_error is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                await self._redis.ping()
            except Exception as exc:
                self._redis_error = str(exc)
                self._redis = None
        return self._redis

    async def check(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        settings = get_settings()
        if not settings.RATE_LIMIT_ENABLED:
            return True, 0
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        limit = settings.RATE_LIMIT_REQUESTS

        redis = await self._redis_client()
        if redis is not None:
            try:
                current = int(time.time())
                await redis.zremrangebyscore(f"rl:{key}", 0, current - window)
                await redis.zadd(f"rl:{key}", {str(time.time_ns()): current})
                await redis.expire(f"rl:{key}", window + 10)
                count = await redis.zcard(f"rl:{key}")
                if count > limit:
                    return False, window
                return True, 0
            except Exception:
                pass
        return self._check_memory(key, window, limit)

    def _check_memory(self, key: str, window: int, limit: int) -> tuple[bool, int]:
        now = time.monotonic()
        timestamps = self._memory[key]
        while timestamps and now - timestamps[0] > window:
            timestamps.popleft()
        if len(timestamps) >= limit:
            retry = window - (now - timestamps[0])
            return False, max(1, int(retry))
        timestamps.append(now)
        return True, 0


rate_limiter = RateLimiter()
