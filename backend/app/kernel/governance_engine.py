"""Phase 20 — Responsible AI governance engine (the human-in-the-loop layer).

Every AI recommendation is submitted with its rationale, supporting
evidence, confidence and affected systems. Humans review, approve, reject or
override AI suggestions before anything happens — high-impact actions require
approval, and the worker escalates recommendations that sit too long.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.publisher import publish_background_event
from app.models.ai_governance import GovernanceRecommendation

GOVERNANCE_CATEGORIES = (
    "hiring", "knowledge", "workflow", "investment", "risk", "innovation",
    "customer", "learning", "people",
)

_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "proposed": ("approved", "rejected", "overridden"),
    "approved": ("implemented", "overridden", "rejected"),
    "rejected": ("proposed",),
    "overridden": ("implemented", "proposed"),
    "implemented": (),
}


class GovernanceEngine:
    """Review-and-override layer over every AI suggestion."""

    async def submit(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        title: str,
        category: str = "knowledge",
        rationale: Optional[str] = None,
        evidence: Optional[dict[str, Any]] = None,
        confidence: float = 0.6,
        affected_systems: Optional[list[str]] = None,
        requires_approval: bool = True,
        created_by: Optional[str] = None,
        source: str = "kernel.governance",
    ) -> dict[str, Any]:
        if category not in GOVERNANCE_CATEGORIES:
            raise ValueError(f"category must be one of {GOVERNANCE_CATEGORIES}")
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("confidence must be between 0 and 1")
        row = GovernanceRecommendation(
            organization_id=organization_id,
            category=category,
            title=title,
            rationale=rationale,
            evidence=evidence or {},
            confidence=round(confidence, 2),
            affected_systems=affected_systems or [],
            requires_approval=requires_approval,
            status="proposed",
            source=source,
            created_by=created_by,
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db, name="recommendation.generated", organization_id=organization_id,
            payload={"recommendation_id": row.id, "source": source, "category": category,
                     "confidence": row.confidence},
        )
        return self.serialize(row)

    async def decide(
        self,
        db: AsyncSession,
        organization_id: str,
        recommendation_id: str,
        decision: str,
        *,
        decided_by: Optional[str] = None,
    ) -> dict[str, Any]:
        if decision not in ("approved", "rejected", "overridden", "implemented"):
            raise ValueError(f"decision must be one of approved|rejected|overridden|implemented")
        row = (
            await db.execute(
                select(GovernanceRecommendation).where(
                    GovernanceRecommendation.organization_id == organization_id,
                    GovernanceRecommendation.id == recommendation_id,
                )
            )
        ).scalars().first()
        if row is None:
            raise KeyError("recommendation not found")
        if decision not in _TRANSITIONS.get(row.status, ()):
            raise ValueError(f"cannot move recommendation from {row.status} to {decision}")
        row.status = decision
        row.decided_by = decided_by
        row.decided_at = utcnow()
        await db.flush()
        return self.serialize(row)

    async def list(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        category: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        stmt = select(GovernanceRecommendation).where(
            GovernanceRecommendation.organization_id == organization_id
        )
        if category:
            stmt = stmt.where(GovernanceRecommendation.category == category)
        if status:
            stmt = stmt.where(GovernanceRecommendation.status == status)
        rows = (
            await db.execute(
                stmt.order_by(GovernanceRecommendation.created_at.desc()).limit(limit)
            )
        ).scalars().all()
        pending = (
            await db.execute(
                select(func.count(GovernanceRecommendation.id)).where(
                    GovernanceRecommendation.organization_id == organization_id,
                    GovernanceRecommendation.status == "proposed",
                )
            )
        ).scalar() or 0
        return {"total": len(rows), "pending": pending,
                "recommendations": [self.serialize(r) for r in rows]}

    async def escalate_stale(
        self, db: AsyncSession, organization_id: str, *, older_than_days: int = 7
    ) -> int:
        """Flag recommendations awaiting review for too long (worker task)."""
        cutoff = ensure_aware(utcnow() - timedelta(days=older_than_days))
        rows = (
            await db.execute(
                select(GovernanceRecommendation).where(
                    GovernanceRecommendation.organization_id == organization_id,
                    GovernanceRecommendation.status == "proposed",
                    GovernanceRecommendation.created_at < cutoff,
                )
            )
        ).scalars().all()
        for row in rows:
            await publish_background_event(
                db, name="organization.updated", organization_id=organization_id,
                payload={"escalated_recommendation": row.id,
                         "message": "AI recommendation awaiting review"},
            )
        return len(rows)

    def serialize(self, row: GovernanceRecommendation) -> dict[str, Any]:
        return {
            "id": row.id,
            "category": row.category,
            "title": row.title,
            "rationale": row.rationale,
            "evidence": row.evidence or {},
            "confidence": row.confidence,
            "affected_systems": row.affected_systems or [],
            "requires_approval": row.requires_approval,
            "status": row.status,
            "source": row.source,
            "created_by": row.created_by,
            "decided_by": row.decided_by,
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


governance_engine = GovernanceEngine()
