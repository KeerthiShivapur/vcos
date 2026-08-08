"""Autonomous Recommendations (Phase 18.8) — proactive, evidence-grounded advice.

The recommendation engine combines twin state, health dimensions and active
predictions into recommendations for hiring, training, automation, process
changes, knowledge updates, risk mitigation, workflow improvements and
leadership actions. Recommendations persist through the Phase 8
`ExecutiveRecommendation` table (kind, title, rationale, evidence, confidence,
impact, status) and emit `recommendation.generated`.
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.digital_twin.health_service import health_service
from app.digital_twin.prediction_service import prediction_service
from app.digital_twin.twin_service import digital_twin_service
from app.events.publisher import publish_background_event
from app.models.executive import ExecutiveRecommendation

logger = logging.getLogger("vcos.digital_twin.recommendation")


class RecommendationService:
    """Generates autonomous recommendations from real organizational evidence."""

    async def generate(self, db: AsyncSession, organization_id: str, *, commit: bool = False) -> list[dict[str, Any]]:
        twin = await digital_twin_service.get_twin(db, organization_id)
        if twin is None:
            payload = await digital_twin_service.build_twin(db, organization_id)
            counts = payload["entity_counts"]
        else:
            counts = json.loads(twin.entity_counts_json or "{}")
        health = await health_service.latest(db, organization_id)
        predictions = await prediction_service.list(db, organization_id, status="active")

        recommendations: list[dict[str, Any]] = []
        employees = counts.get("active_employees", counts.get("employees", 0)) or 0
        open_tasks = counts.get("open_tasks", 0) or 0
        knowledge = counts.get("knowledge_indexed", counts.get("documents", 0)) or 0
        customers = counts.get("customers", 0) or 0
        budgets = counts.get("budgets", 0) or 0
        workflows = counts.get("workflows", 0) or 0
        meetings = counts.get("meetings", 0) or 0

        # hiring
        if employees and open_tasks > employees * 4:
            recommendations.append(
                {
                    "kind": "hire",
                    "title": "Hire to relieve open task load",
                    "rationale": f"{open_tasks} open tasks exceed the {employees * 4} capacity estimate.",
                    "evidence": [{"metric": "open_tasks", "value": open_tasks}, {"metric": "active_employees", "value": employees}],
                    "expected_outcome": "Reduced workload pressure and faster delivery cycles.",
                    "confidence": 0.75,
                    "impact": "high",
                }
            )

        # training
        health_learning = (health or {}).get("breakdown", {}).get("learning", {}).get("score", 50)
        if health_learning and health_learning < 45:
            recommendations.append(
                {
                    "kind": "training",
                    "title": "Increase learning engagement",
                    "rationale": f"Learning health is {health_learning}/100, below the healthy threshold.",
                    "evidence": [{"metric": "learning_health", "value": health_learning}],
                    "expected_outcome": "Higher skill coverage and retention.",
                    "confidence": 0.7,
                    "impact": "medium",
                }
            )

        # knowledge
        if knowledge == 0 and employees:
            recommendations.append(
                {
                    "kind": "knowledge",
                    "title": "Seed the knowledge base",
                    "rationale": "No indexed knowledge exists for the organization.",
                    "evidence": [{"metric": "knowledge_indexed", "value": knowledge}],
                    "expected_outcome": "Faster onboarding and reduced knowledge loss.",
                    "confidence": 0.8,
                    "impact": "high",
                }
            )

        # automation
        if workflows < max(2, projects := counts.get("projects", 0) or 0):
            recommendations.append(
                {
                    "kind": "automation",
                    "title": "Automate recurring processes",
                    "rationale": f"Only {workflows} workflows defined while {projects or 0} projects are active.",
                    "evidence": [{"metric": "workflows", "value": workflows}, {"metric": "projects", "value": projects or 0}],
                    "expected_outcome": "Reduced manual handoffs and faster approvals.",
                    "confidence": 0.65,
                    "impact": "medium",
                }
            )

        # meeting reduction
        if meetings > 5 and employees:
            recommendations.append(
                {
                    "kind": "reduce_meetings",
                    "title": "Review meeting load",
                    "rationale": f"{meetings} meetings on record may be consuming collaboration time.",
                    "evidence": [{"metric": "meetings", "value": meetings}],
                    "expected_outcome": "Recovered focus time for deep work.",
                    "confidence": 0.6,
                    "impact": "low",
                }
            )

        # budget tracking
        if budgets == 0:
            recommendations.append(
                {
                    "kind": "finance",
                    "title": "Establish budget tracking",
                    "rationale": "No budgets are defined, limiting overrun prediction.",
                    "evidence": [{"metric": "budgets", "value": budgets}],
                    "expected_outcome": "Earlier visibility into financial risk.",
                    "confidence": 0.7,
                    "impact": "medium",
                }
            )

        # risk mitigation from predictions
        for pred in predictions:
            if pred["level"] in ("high", "critical"):
                recommendations.append(
                    {
                        "kind": "risk_mitigation",
                        "title": f"Mitigate {pred['kind'].replace('_', ' ')} risk",
                        "rationale": pred["title"],
                        "evidence": pred.get("signals", []),
                        "expected_outcome": pred.get("recommended_action", "Risk reduced through early intervention."),
                        "confidence": 0.7,
                        "impact": "high",
                    }
                )

        created_rows = []
        for rec in recommendations:
            row = ExecutiveRecommendation(
                organization_id=organization_id,
                kind=rec["kind"],
                title=rec["title"],
                rationale=rec.get("rationale"),
                evidence_json=json.dumps(rec.get("evidence", [])),
                expected_outcome=rec.get("expected_outcome"),
                confidence=rec.get("confidence", 0.7),
                impact=rec.get("impact", "medium"),
                status="active",
            )
            db.add(row)
            created_rows.append(row)
        await db.flush()
        created = [{**r, "id": row.id, "status": row.status} for r, row in zip(recommendations, created_rows)]
        if created:
            await publish_background_event(
                db,
                name="recommendation.generated",
                organization_id=organization_id,
                payload={"count": len(created), "kinds": [c["kind"] for c in created]},
            )
        if commit:
            await db.commit()
        return created

    async def list(self, db: AsyncSession, organization_id: str, status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        query = select(ExecutiveRecommendation).where(ExecutiveRecommendation.organization_id == organization_id)
        if status:
            query = query.where(ExecutiveRecommendation.status == status)
        query = query.order_by(ExecutiveRecommendation.created_at.desc()).limit(limit)
        rows = (await db.execute(query)).scalars().all()
        return [self.serialize(r) for r in rows]

    def serialize(self, row: ExecutiveRecommendation) -> dict[str, Any]:
        evidence = []
        if row.evidence_json:
            try:
                evidence = json.loads(row.evidence_json)
            except (json.JSONDecodeError, TypeError):
                evidence = []
        return {
            "id": row.id,
            "kind": row.kind,
            "title": row.title,
            "rationale": row.rationale,
            "evidence": evidence,
            "expected_outcome": row.expected_outcome,
            "confidence": row.confidence,
            "impact": row.impact,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def set_status(self, db: AsyncSession, organization_id: str, recommendation_id: str, status: str, *, commit: bool = False) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(ExecutiveRecommendation).where(
                    ExecutiveRecommendation.organization_id == organization_id,
                    ExecutiveRecommendation.id == recommendation_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        if status not in ("accepted", "dismissed"):
            raise ValueError("status must be accepted or dismissed")
        row.status = status
        await db.flush()
        if commit:
            await db.commit()
        return self.serialize(row)


recommendation_service = RecommendationService()
