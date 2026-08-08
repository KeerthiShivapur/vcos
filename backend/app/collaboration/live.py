"""Live collaboration engine — in-memory WebSocket hub (Phase 6.2).

The hub tracks one connection per (session, employee, browser tab) and provides
fan-out for presence, signaling, chat, whiteboard deltas and reactions. It is
process-local: fine for a single API instance; multi-instance deployments would
swap this for Redis pub/sub behind the same interface.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger("vcos.live")


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _dumps(payload: Any) -> str:
    return json.dumps(payload, default=_json_default)


@dataclass
class LiveConnection:
    """One open WebSocket, tagged with who it belongs to."""

    ws: Any
    employee_id: str
    name: str = "Unknown"
    role: str = "participant"
    connected_at: float = field(default_factory=time.time)

    def __hash__(self) -> int:
        return id(self)


class LiveHub:
    """Fan-out registry keyed by session id.

    Thread model: all callers run on the same asyncio event loop (the API
    process), so no locks are required.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, dict[int, LiveConnection]] = {}
        self._keys: dict[tuple[str, str], int] = {}  # (session_id, employee_id) -> conn key

    # ------------------------------------------------------------------ registry

    def register(self, session_id: str, conn: LiveConnection) -> int:
        key = id(conn)
        self._rooms.setdefault(session_id, {})[key] = conn
        self._keys[(session_id, conn.employee_id)] = key
        logger.info("live: %s joined session %s (peers=%s)", conn.employee_id, session_id, self.count(session_id))
        return key

    def unregister(self, session_id: str, key: int) -> Optional[LiveConnection]:
        room = self._rooms.get(session_id)
        if not room:
            return None
        conn = room.pop(key, None)
        if conn is None:
            return None
        current = self._keys.get((session_id, conn.employee_id))
        if current == key:
            del self._keys[(session_id, conn.employee_id)]
        if not room:
            self._rooms.pop(session_id, None)
        logger.info("live: %s left session %s (peers=%s)", conn.employee_id, session_id, self.count(session_id))
        return conn

    # ------------------------------------------------------------------ fan-out

    async def broadcast(
        self,
        session_id: str,
        event: str,
        data: Optional[dict[str, Any]] = None,
        *,
        exclude: Optional[LiveConnection] = None,
        exclude_employee: Optional[str] = None,
    ) -> int:
        """Send an event to everyone in the session; returns delivered count."""
        room = self._rooms.get(session_id)
        if not room:
            return 0
        envelope = _envelope(event, data)
        wire = _dumps(envelope)
        sent = 0
        dead: list[int] = []
        for key, conn in room.items():
            if conn is exclude:
                continue
            if exclude_employee and conn.employee_id == exclude_employee:
                continue
            try:
                sender = getattr(conn.ws, "send_text", None)
                if sender is not None:
                    result = sender(wire)
                else:
                    result = conn.ws.send_json(json.loads(wire))
                if hasattr(result, "__await__"):
                    await result
                sent += 1
            except Exception:  # pragma: no cover - socket raced
                dead.append(key)
        for key in dead:
            self.unregister(session_id, key)
        return sent

    async def send_to_employee(
        self, session_id: str, employee_id: str, event: str, data: Optional[dict[str, Any]] = None
    ) -> bool:
        """Deliver an event to every tab of one employee (used for RTC signaling)."""
        room = self._rooms.get(session_id)
        if not room:
            return False
        envelope = _envelope(event, data)
        wire = _dumps(envelope)
        delivered = False
        for key, conn in room.items():
            if conn.employee_id != employee_id:
                continue
            try:
                sender = getattr(conn.ws, "send_text", None)
                if sender is not None:
                    result = sender(wire)
                else:
                    result = conn.ws.send_json(json.loads(wire))
                if hasattr(result, "__await__"):
                    await result
                delivered = True
            except Exception:  # pragma: no cover - socket raced
                self.unregister(session_id, key)
        return delivered

    def peers(self, session_id: str, exclude_employee: Optional[str] = None) -> list[dict[str, Any]]:
        room = self._rooms.get(session_id, {})
        out: list[dict[str, Any]] = []
        for conn in room.values():
            if exclude_employee and conn.employee_id == exclude_employee:
                continue
            out.append(
                {
                    "employee_id": conn.employee_id,
                    "name": conn.name,
                    "role": conn.role,
                    "online": True,
                }
            )
        return out

    def count(self, session_id: str) -> int:
        return len(self._rooms.get(session_id, {}))


def _envelope(event: str, data: Optional[dict[str, Any]]) -> dict[str, Any]:
    return {"type": event, "ts": time.time(), "data": data or {}}


live_hub = LiveHub()
