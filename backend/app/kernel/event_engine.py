"""Phase 20 — Event engine (the kernel event bus).

One event stream for the whole organization: every subsystem publishes to
the same store and every consumer reads from the same store, so nothing in
the company runs in isolation.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.publisher import publish_background_event, publish_event
from app.models.notification import Event as EventRow

EVENT_NAMES = (
    "organization.updated",
    "company.health.updated",
    "graph.updated",
    "memory.updated",
    "intelligence.updated",
    "recommendation.generated",
    "strategy.updated",
    "organization.evolved",
)


class EventEngine:
    """Unified event bus over the persisted event stream."""

    async def publish(
        self,
        db: AsyncSession,
        organization_id: str,
        name: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        actor_id: Optional[str] = None,
        dispatch: bool = False,
    ) -> dict[str, Any]:
        """Publish one event; optionally enqueue its dispatch job."""
        if dispatch:
            row = await publish_event(
                db, name=name, organization_id=organization_id, actor_id=actor_id, payload=payload
            )
        else:
            row = await publish_background_event(
                db, name=name, organization_id=organization_id, payload=payload
            )
        return {
            "id": row.id,
            "name": row.name,
            "organization_id": row.organization_id,
            "payload": json.loads(row.payload_json) if row.payload_json else {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def list(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        name: Optional[str] = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        stmt = select(EventRow).where(EventRow.organization_id == organization_id)
        if name:
            stmt = stmt.where(EventRow.name == name)
        rows = (
            await db.execute(stmt.order_by(EventRow.created_at.desc()).limit(limit))
        ).scalars().all()
        return {
            "total": len(rows),
            "events": [
                {
                    "id": r.id,
                    "name": r.name,
                    "actor_id": r.actor_id,
                    "payload": json.loads(r.payload_json) if r.payload_json else {},
                    "processed_at": r.processed_at.isoformat() if r.processed_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }

    async def summary(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(EventRow.name, func.count(EventRow.id))
                .where(EventRow.organization_id == organization_id)
                .group_by(EventRow.name)
                .order_by(func.count(EventRow.id).desc())
            )
        ).all()
        return {"total_events": sum(count for _, count in rows), "by_name": dict(rows)}


event_engine = EventEngine()
