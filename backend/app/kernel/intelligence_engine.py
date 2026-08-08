"""Phase 20 — Universal intelligence engine (the company brain).

One AI memory + one company understanding. Generates executive intelligence
snapshots that combine state, health, opportunities, risks, changes,
knowledge growth, learning, customer trends and priorities into a single
connected picture of the company.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomy.awareness_engine import awareness_engine
from app.autonomy.health_engine import health_engine as autonomy_health
from app.core.timeutils import utcnow
from app.kernel.event_engine import event_engine
from app.models.company_memory import CompanyMemory
from app.models.executive_intelligence import ExecutiveIntelligence
from app.models.prediction import Prediction
from app.models.project import Project
from app.models.recommendation import Recommendation


class IntelligenceEngine:
    """Unified executive intelligence across the entire organization."""

    async def generate(
        self, db: AsyncSession, organization_id: str, *, period: str = "on_demand",
        commit: bool = False,
    ) -> dict[str, Any]:
        now = utcnow()
        state = await awareness_engine.latest(db, organization_id)
        current = state.get("state") or {}
        health = await autonomy_health.latest(db, organization_id)

        open_predictions = (
            await db.execute(
                select(Prediction).where(
                    Prediction.organization_id == organization_id,
                    Prediction.status == "open",
                ).limit(50)
            )
        ).scalars().all()
        pending_recommendations = (
            await db.execute(
                select(Recommendation).where(
                    Recommendation.organization_id == organization_id,
                    Recommendation.status == "pending",
                ).limit(50)
            )
        ).scalars().all()
        memories = (
            await db.execute(
                select(func.count(CompanyMemory.id)).where(
                    CompanyMemory.organization_id == organization_id
                )
            )
        ).scalar() or 0
        docs_week = current.get("knowledge", {}).get("added_7d", 0)
        overdue = current.get("tasks", {}).get("overdue", 0)
        at_risk = (
            await db.execute(
                select(func.count(Project.id)).where(
                    Project.organization_id == organization_id,
                    Project.status.in_(["at_risk", "blocked"]),
                )
            )
        ).scalar() or 0

        changes = [
            {"domain": "tasks", "detail": f"{overdue} overdue tasks"} if overdue else None,
            {"domain": "knowledge", "detail": f"{docs_week} documents added this week"} if docs_week else None,
            {"domain": "predictions", "detail": f"{len(open_predictions)} open predictions"} if open_predictions else None,
        ]
        changes = [c for c in changes if c]

        risks: list[dict[str, Any]] = []
        if overdue >= 3:
            risks.append({"title": f"{overdue} overdue tasks threaten delivery", "impact": "medium"})
        if at_risk:
            risks.append({"title": "Projects with failure signals need attention", "impact": "high"})
        for p in open_predictions:
            if p.impact == "high" and p.probability and p.probability >= 0.6:
                risks.append({"title": p.title[:120], "impact": p.impact, "probability": p.probability})

        opportunities: list[dict[str, Any]] = []
        for r in pending_recommendations:
            if r.impact == "high":
                opportunities.append({"title": r.title[:120], "category": r.category, "confidence": r.confidence})

        priorities: list[str] = []
        if overdue:
            priorities.append("Clear the overdue task backlog")
        if risks:
            priorities.append("Address high-impact risks first")
        for r in pending_recommendations[:2]:
            priorities.append(r.title[:120])
        if not priorities:
            priorities.append("Maintain the current trajectory")

        sections = {
            "health": health,
            "state": current,
            "changes": changes,
            "risks": risks,
            "opportunities": opportunities,
            "priorities": priorities,
            "knowledge": {"memories": memories, "documents_7d": docs_week},
            "predictions_open": len(open_predictions),
            "recommendations_pending": len(pending_recommendations),
        }
        summary = (
            f"Company health {health.get('score', 0)} ({health.get('status', 'unknown')}) with "
            f"{len(risks)} risk(s) and {len(opportunities)} opportunity(ies) across "
            f"{current.get('employees', {}).get('total', 0)} employees."
        )

        row = ExecutiveIntelligence(
            organization_id=organization_id,
            period=period,
            title=f"Executive intelligence — {now.strftime('%Y-%m-%d')}",
            summary=summary,
            sections=sections,
            health_score=health.get("score", 0.0),
            intelligence_score=self._score(sections),
            source="kernel.intelligence",
            generated_at=now,
        )
        db.add(row)
        await db.flush()
        await event_engine.publish(
            db, organization_id, "intelligence.updated",
            payload={"intelligence_id": row.id, "health_score": row.health_score,
                     "risks": len(risks), "opportunities": len(opportunities)},
        )
        if commit:
            await db.commit()
        return self.serialize(row)

    def _score(self, sections: dict[str, Any]) -> float:
        health = sections.get("health", {}).get("score", 0.0) or 0.0
        risks = len(sections.get("risks", []))
        opportunities = len(sections.get("opportunities", []))
        return round(max(0.0, health * 0.7 + min(30.0, (opportunities * 5) - (risks * 2))), 1)

    async def latest(
        self, db: AsyncSession, organization_id: str, *, generate: bool = True
    ) -> dict[str, Any]:
        row = (
            await db.execute(
                select(ExecutiveIntelligence)
                .where(ExecutiveIntelligence.organization_id == organization_id)
                .order_by(ExecutiveIntelligence.generated_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if row is None and generate:
            return await self.generate(db, organization_id, commit=True)
        if row is None:
            return None
        return self.serialize(row)

    async def list(
        self, db: AsyncSession, organization_id: str, *, limit: int = 20
    ) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(ExecutiveIntelligence)
                .where(ExecutiveIntelligence.organization_id == organization_id)
                .order_by(ExecutiveIntelligence.generated_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return {"total": len(rows), "intelligence": [self.serialize(r) for r in rows]}

    def serialize(self, row: ExecutiveIntelligence) -> dict[str, Any]:
        return {
            "id": row.id,
            "period": row.period,
            "title": row.title,
            "summary": row.summary,
            "sections": row.sections or {},
            "health_score": row.health_score,
            "intelligence_score": row.intelligence_score,
            "source": row.source,
            "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        }


intelligence_engine = IntelligenceEngine()
