"""Phase 20 — Orchestration engine (continuous organizational evolution).

One evolution cycle: observe the organization, rebuild the graph, refresh
health, generate intelligence, record the company memory and timeline, then
emit the organization.updated / organization.evolved events. The company
becomes smarter with every pass.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomy.organization_engine import organization_engine
from app.core.timeutils import utcnow
from app.kernel.event_engine import event_engine
from app.kernel.graph_engine import graph_engine
from app.kernel.intelligence_engine import intelligence_engine
from app.kernel.memory_engine import memory_engine
from app.models.organization import Organization


class OrchestrationEngine:
    """Runs the universal evolution cycle for one or all organizations."""

    async def run_cycle(
        self, db: AsyncSession, organization_id: str, *, commit: bool = False
    ) -> dict[str, Any]:
        now = utcnow()
        observed = await organization_engine.observe(db, organization_id)
        graph = await graph_engine.rebuild(db, organization_id)
        intelligence = await intelligence_engine.generate(db, organization_id)

        timeline = None
        memory = None
        insights = observed.get("insights") or []
        if insights:
            memory = await memory_engine.record_memory(
                db, organization_id,
                memory_type="institutional",
                title=f"Evolution insight: {insights[0]['title'][:120]}",
                content=insights[0]["detail"],
                tags=["evolution", insights[0].get("domain", "organization")],
                importance="medium",
                source_event="organization.evolved",
            )
        timeline = await memory_engine.record_timeline(
            db, organization_id,
            event_type="organization.evolved",
            title="Company intelligence cycle completed",
            category="system",
            detail=(
                f"Health {observed.get('health_score', 0)}, {len(observed.get('changes') or [])} change(s), "
                f"{observed.get('predictions', 0)} prediction(s), "
                f"{observed.get('recommendations', 0)} recommendation(s), "
                f"{graph['nodes']} graph nodes."
            ),
            occurred_at=now,
            metadata={"cycle": 1},
        )

        await event_engine.publish(
            db, organization_id, "organization.updated",
            payload={"health_score": observed.get("health_score"), "source": "kernel.orchestration"},
        )
        await event_engine.publish(
            db, organization_id, "organization.evolved",
            payload={"timeline_id": timeline.get("id"), "memory_id": memory.get("id") if memory else None,
                     "insights": len(insights)},
        )
        if commit:
            await db.commit()
        return {
            "organization_id": organization_id,
            "evolved_at": now.isoformat(),
            "observed": observed,
            "graph": {"nodes": graph["nodes"], "edges": graph["edges"]},
            "intelligence": intelligence,
            "timeline": timeline,
            "memory": memory,
            "events": ["organization.updated", "organization.evolved"],
        }

    async def run_all(self, db: AsyncSession) -> dict[str, Any]:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        results: list[dict[str, Any]] = []
        for org_id in org_ids:
            results.append(await self.run_cycle(db, org_id))
        return {"organizations": len(results), "cycles": results}


orchestration_engine = OrchestrationEngine()
