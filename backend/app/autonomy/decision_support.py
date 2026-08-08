"""AI decision support — AI explains, humans approve.

For sensitive decisions (hiring, termination, large budget, legal approval,
customer contracts, acquisitions) the engine explains advantages, risks,
alternatives, historical evidence and predictions. The decision stays in
``pending_approval`` until a human approves; approved decisions are recorded in
decision history and captured into company memory.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomy.prediction_engine import prediction_engine
from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.company_memory import CompanyMemory
from app.models.decision_history import DecisionHistory, DECISION_CATEGORIES
from app.models.prediction import Prediction


class DecisionSupportService:
    async def create_case(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        title: str,
        question: str | None = None,
        category: str = "strategy",
        context: str | None = None,
        alternatives: list[dict[str, Any]] | None = None,
        created_by: str | None = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        if category not in DECISION_CATEGORIES:
            raise ValueError(f"category must be one of {DECISION_CATEGORIES}")
        analysis = await self._analyze(db, organization_id, title, category, context)
        row = DecisionHistory(
            organization_id=organization_id,
            title=title,
            question=question,
            category=category,
            context=context,
            alternatives=alternatives or [],
            analysis=analysis,
            participants=[created_by] if created_by else [],
            status="pending_approval",
            decided_by=None,
            source_event="decision.proposed",
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db, name="decision.proposed", organization_id=organization_id,
            payload={"decision_id": row.id, "category": category},
        )
        if commit:
            await db.commit()
        return self._serialize(row)

    async def _analyze(
        self, db: AsyncSession, organization_id: str, title: str, category: str,
        context: str | None,
    ) -> dict[str, Any]:
        """Build the explainable analysis: pros/cons, history, predictions."""
        advantages = self._advantages(category)
        risks = self._risks(category, title)

        historical = (
            await db.execute(
                select(DecisionHistory)
                .where(
                    DecisionHistory.organization_id == organization_id,
                    DecisionHistory.category == category,
                )
                .order_by(DecisionHistory.created_at.desc())
                .limit(5)
            )
        ).scalars().all()
        history = [
            {
                "title": h.title, "outcome": h.outcome, "status": h.status,
                "lessons": (h.lessons or [])[:3],
            }
            for h in historical
        ]

        relevant_predictions: list[dict[str, Any]] = []
        if category in ("hiring", "budget", "acquisition", "expansion"):
            preds = (
                await db.execute(
                    select(Prediction)
                    .where(
                        Prediction.organization_id == organization_id,
                        Prediction.kind.in_(["capacity_bottleneck", "budget_overrun", "customer_churn"]),
                        Prediction.status == "open",
                    )
                    .limit(5)
                )
            ).scalars().all()
            relevant_predictions = [
                {"kind": p.kind, "title": p.title, "probability": p.probability}
                for p in preds
            ]

        related_memories = (
            await db.execute(
                select(CompanyMemory)
                .where(
                    CompanyMemory.organization_id == organization_id,
                    CompanyMemory.importance.in_(["high", "critical"]),
                )
                .order_by(CompanyMemory.created_at.desc())
                .limit(5)
            )
        ).scalars().all()
        evidence = [
            {"memory": m.title, "memory_type": m.memory_type}
            for m in related_memories
        ]

        return {
            "advantages": advantages,
            "risks": risks,
            "alternatives_note": "Evaluate alternatives before approving; see alternatives list.",
            "historical_evidence": history,
            "predictions": relevant_predictions,
            "organizational_memory": evidence,
            "generated_at": utcnow().isoformat(),
        }

    def _advantages(self, category: str) -> list[str]:
        return {
            "hiring": ["Adds critical capacity", "Reduces overload risk", "Brings new skills"],
            "termination": ["Removes underperformance", "Restores team balance"],
            "budget": ["Funds strategic initiatives", "Improves capital efficiency"],
            "legal": ["Reduces compliance exposure", "Protects the company"],
            "contract": ["Secures revenue", "Deepens customer relationship"],
            "acquisition": ["Accelerates market entry", "Adds capability fast"],
            "expansion": ["Accesses new markets", "Diversifies revenue"],
            "product": ["Aligns roadmap with demand"],
            "pricing": ["Improves margins"],
            "infrastructure": ["Improves reliability and scale"],
            "strategy": ["Advances long-term positioning"],
        }.get(category, ["Advances organizational goals"])

    def _risks(self, category: str, title: str) -> list[str]:
        return {
            "hiring": ["Onboarding lag before productivity", "Budget burden", "Culture fit risk"],
            "termination": ["Legal exposure", "Knowledge loss", "Team morale impact"],
            "budget": ["Opportunity cost", "Reduced liquidity"],
            "legal": ["Slow execution", "External dependency"],
            "contract": ["Obligation mismatch", "Pricing pressure"],
            "acquisition": ["Integration cost", "Cultural clash", "Execution risk"],
            "expansion": ["Compliance complexity", "Infrastructure cost", "Support load"],
            "product": ["Build misalignment", "Market timing"],
            "pricing": ["Customer pushback", "Competitive pressure"],
            "infrastructure": ["Migration disruption"],
            "strategy": ["Uncertain market response"],
        }.get(category, ["Execution risk"])

    async def decide(
        self, db: AsyncSession, organization_id: str, decision_id: str, *,
        decision: str, outcome: str | None = None,
        lessons: list[str] | None = None,
        user_id: str | None = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        """Human approval/rejection of a decision case."""
        row = (
            await db.execute(
                select(DecisionHistory).where(
                    DecisionHistory.organization_id == organization_id,
                    DecisionHistory.id == decision_id,
                )
            )
        ).scalars().first()
        if row is None:
            raise LookupError("decision not found")
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be approved or rejected")
        row.status = "approved" if decision == "approved" else "rejected"
        row.outcome = outcome or ("Approved" if decision == "approved" else "Rejected")
        row.decided_by = user_id
        row.decided_at = utcnow()
        if lessons:
            row.lessons = lessons
        await db.flush()
        await publish_background_event(
            db, name="decision.made", organization_id=organization_id,
            payload={"decision_id": row.id, "status": row.status},
        )
        if row.status == "approved":
            from app.memory.memory_service import memory_service

            await memory_service.record(
                db,
                organization_id=organization_id,
                memory_type="decision",
                title=f"Decision: {row.title}",
                content=f"Category: {row.category}. {row.outcome}",
                tags=["decision", row.category],
                importance="high",
                entity_type="decision",
                entity_id=row.id,
                source_event="decision.made",
            )
        if commit:
            await db.commit()
        return self._serialize(row)

    async def list(
        self, db: AsyncSession, organization_id: str, *, category: str | None = None,
        status: str | None = None, limit: int = 100,
    ) -> dict[str, Any]:
        stmt = select(DecisionHistory).where(DecisionHistory.organization_id == organization_id)
        if category:
            stmt = stmt.where(DecisionHistory.category == category)
        if status:
            stmt = stmt.where(DecisionHistory.status == status)
        rows = (
            await db.execute(stmt.order_by(DecisionHistory.created_at.desc()).limit(limit))
        ).scalars().all()
        return {"total": len(rows), "decisions": [self._serialize(r) for r in rows]}

    async def get(self, db: AsyncSession, organization_id: str, decision_id: str) -> dict[str, Any] | None:
        row = (
            await db.execute(
                select(DecisionHistory).where(
                    DecisionHistory.organization_id == organization_id,
                    DecisionHistory.id == decision_id,
                )
            )
        ).scalars().first()
        return self._serialize(row) if row else None

    def _serialize(self, row: DecisionHistory) -> dict[str, Any]:
        return {
            "id": row.id, "title": row.title, "question": row.question,
            "category": row.category, "context": row.context,
            "alternatives": row.alternatives or [], "analysis": row.analysis or {},
            "participants": row.participants or [], "outcome": row.outcome,
            "results": row.results or [], "lessons": row.lessons or [],
            "status": row.status, "decided_by": row.decided_by,
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


decision_support_service = DecisionSupportService()
