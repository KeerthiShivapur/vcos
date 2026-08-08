"""Working memory — the short-lived context of active conversations.

Kept in-process (no DB): a bounded ring buffer per (organization, user) with
the most recent exchanges plus a lightweight goal/plan scratchpad the agent
layers use while answering. Nothing here survives a restart; everything else
does.
"""

from __future__ import annotations

import time
from typing import Any, Optional

RING_CAPACITY = 12


class WorkingMemory:
    def __init__(self, capacity: int = RING_CAPACITY) -> None:
        self._capacity = capacity
        self._rings: dict[str, list[dict[str, Any]]] = {}
        self._scratch: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _key(organization_id: str, user_id: Optional[str]) -> str:
        return f"{organization_id}:{user_id or 'anon'}"

    def push(self, *, organization_id: str, user_id: Optional[str], role: str, content: str) -> None:
        key = self._key(organization_id, user_id)
        ring = self._rings.setdefault(key, [])
        ring.append({"role": role, "content": content, "ts": time.time()})
        if len(ring) > self._capacity:
            del ring[: len(ring) - self._capacity]

    def recent(self, *, organization_id: str, user_id: Optional[str], limit: int = 6) -> list[dict[str, Any]]:
        ring = self._rings.get(self._key(organization_id, user_id), [])
        return ring[-limit:]

    def scratch(self, *, organization_id: str, user_id: Optional[str], **values: Any) -> dict[str, Any]:
        key = self._key(organization_id, user_id)
        bucket = self._scratch.setdefault(key, {})
        bucket.update(values)
        return bucket

    def peek(self, *, organization_id: str, user_id: Optional[str]) -> dict[str, Any]:
        return self._scratch.get(self._key(organization_id, user_id), {})

    def clear(self, *, organization_id: str, user_id: Optional[str]) -> None:
        key = self._key(organization_id, user_id)
        self._rings.pop(key, None)
        self._scratch.pop(key, None)
