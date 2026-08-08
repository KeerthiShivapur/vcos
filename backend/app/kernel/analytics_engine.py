"""Phase 20 — Kernel analytics engine.

One analytics surface for the whole organization: counts, health and trends
across every domain, fed from the same state, graph, memory and event data
the rest of the kernel uses.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomy.awareness_engine import awareness_engine
from app.kernel.graph_engine import graph_engine
from app.models.company_memory import OrganizationTimeline as OrgTimeline
from app.models.company_memory import CompanyMemory
from app.models.knowledge import Document
from app.models.notification import Event as EventRow


class AnalyticsEngine:
    """Unified organizational analytics."""

    async def overview(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        state = await awareness_engine.latest(db, organization_id)
        current = state.get("state") or {}
        graph = await graph_engine.stats(db, organization_id)
        memories = (
            await db.execute(
                select(func.count(CompanyMemory.id)).where(
                    CompanyMemory.organization_id == organization_id
                )
            )
        ).scalar() or 0
        documents = (
            await db.execute(
                select(func.count(Document.id)).where(
                    Document.organization_id == organization_id
                )
            )
        ).scalar() or 0
        events = (
            await db.execute(
                select(func.count(EventRow.id)).where(
                    EventRow.organization_id == organization_id
                )
            )
        ).scalar() or 0
        timeline = (
            await db.execute(
                select(func.count(OrgTimeline.id)).where(
                    OrgTimeline.organization_id == organization_id
                )
            )
        ).scalar() or 0
        return {
            "organization_id": organization_id,
            "state": current,
            "score": state.get("score"),
            "graph": {"total_nodes": graph["total_nodes"], "total_edges": graph["total_edges"]},
            "memory": {"total": memories},
            "knowledge": {"documents": documents},
            "events": {"total": events},
            "timeline": {"total": timeline},
        }


analytics_engine = AnalyticsEngine()
