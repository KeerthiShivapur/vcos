"""Phase 20 — Unified company health engine.

One health score for the whole company across employees, projects, knowledge,
learning, community, finance, customers, infrastructure, innovation and
workflow — measured continuously and synchronized into the event stream.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomy.health_engine import health_engine as autonomy_health


class HealthEngine:
    """Unified organizational health center."""

    async def refresh(
        self, db: AsyncSession, organization_id: str, *, commit: bool = False
    ) -> dict[str, Any]:
        """Recompute the unified company health score."""
        return await autonomy_health.refresh(db, organization_id, commit=commit)

    async def latest(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        return await autonomy_health.latest(db, organization_id)

    async def history(
        self, db: AsyncSession, organization_id: str, *, limit: int = 30
    ) -> dict[str, Any]:
        return await autonomy_health.history(db, organization_id, limit=limit)

    async def dimension(
        self, db: AsyncSession, organization_id: str, name: str
    ) -> dict[str, Any]:
        """Latest score for one health dimension."""
        health = await autonomy_health.latest(db, organization_id)
        dimensions = health.get("dimensions") or {}
        if name not in dimensions:
            return {"dimension": name, "score": None, "available": list(dimensions.keys())}
        return {"dimension": name, "score": dimensions[name], "health": health}


health_engine = HealthEngine()
