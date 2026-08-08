"""Decision Intelligence (Phase 18.7) — decisions with reason, evidence, lessons.

Executives record decisions; the engine stores the decision, reason,
alternatives, evidence, outcome and lessons learned. When an outcome is
recorded the engine analyzes the decision (why it succeeded or failed) and
emits `decision.analyzed`.
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.digital_twin import DecisionRecord

logger = logging.getLogger("vcos.digital_twin.decision")


class DecisionService:
    """Stores and analyzes organizational decisions."""

    async def create(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        decision: str,
        decided_by: Optional[str] = None,
        category: str = "strategy",
        reason: Optional[str] = None,
        alternatives: Optional[list[str]] = None,
        evidence: Optional[list[dict]] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        row = DecisionRecord(
            organization_id=organization_id,
            decided_by=decided_by,
            category=category,
            decision=decision,
            reason=reason,
            alternatives_json=json.dumps(alternatives or []),
            evidence_json=json.dumps(evidence or []),
            status="made",
            decided_at=utcnow(),
        )
        db.add(row)
        await db.flush()
        if commit:
            await db.commit()
        return self.serialize(row)

    async def record_outcome(
        self,
        db: AsyncSession,
        organization_id: str,
        decision_id: str,
        *,
        outcome: str,
        outcome_score: float,
        commit: bool = False,
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(DecisionRecord).where(
                    DecisionRecord.organization_id == organization_id,
                    DecisionRecord.id == decision_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        row.outcome = outcome
        row.outcome_score = max(-100.0, min(100.0, outcome_score))
        row.status = "reviewed"
        row.analyzed = True
        lessons = self._lessons(row)
        row.lessons_json = json.dumps(lessons)
        await db.flush()
        await publish_background_event(
            db,
            name="decision.analyzed",
            organization_id=organization_id,
            payload={"decision_id": row.id, "outcome_score": row.outcome_score, "lessons": lessons},
        )
        if commit:
            await db.commit()
        return self.serialize(row)

    def _lessons(self, row: DecisionRecord) -> list[str]:
        lessons = []
        score = row.outcome_score or 0
        if score >= 50:
            lessons.append("The decision met its intended outcome — preserve the reasoning for reuse.")
            lessons.append("Evidence alignment was strong; keep the same evidence discipline.")
        elif score <= -30:
            lessons.append("The decision did not achieve its intended outcome — revisit assumptions.")
            lessons.append("Consider running scenario simulations before similar decisions.")
        else:
            lessons.append("Mixed outcome — review the assumptions behind the decision.")
        if row.alternatives_json:
            try:
                alternatives = json.loads(row.alternatives_json)
            except (json.JSONDecodeError, TypeError):
                alternatives = []
            if len(alternatives) >= 2:
                lessons.append("Multiple alternatives were considered — a good decision practice.")
        if not row.reason:
            lessons.append("Record the reason for future decisions to strengthen analysis.")
        return lessons

    async def analyze(self, db: AsyncSession, organization_id: str, decision_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(DecisionRecord).where(
                    DecisionRecord.organization_id == organization_id,
                    DecisionRecord.id == decision_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        record = self.serialize(row)
        lessons = []
        if row.lessons_json:
            try:
                lessons = json.loads(row.lessons_json)
            except (json.JSONDecodeError, TypeError):
                lessons = []
        verdict = "success" if (row.outcome_score or 0) >= 50 else "failure" if (row.outcome_score or 0) <= -30 else "mixed"
        return {
            **record,
            "verdict": verdict,
            "lessons": lessons,
            "analysis": (
                f"Decision '{row.decision[:120]}' scored {row.outcome_score or 0}/100. "
                f"Verdict: {verdict}. Lessons: {'; '.join(lessons) if lessons else 'none recorded yet.'}"
            ),
        }

    async def list(self, db: AsyncSession, organization_id: str, category: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        query = select(DecisionRecord).where(DecisionRecord.organization_id == organization_id)
        if category:
            query = query.where(DecisionRecord.category == category)
        query = query.order_by(DecisionRecord.decided_at.desc()).limit(limit)
        rows = (await db.execute(query)).scalars().all()
        return [self.serialize(r) for r in rows]

    def serialize(self, row: DecisionRecord) -> dict[str, Any]:
        def _loads(value: Optional[str], fallback: Any):
            if not value:
                return fallback
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return fallback

        return {
            "id": row.id,
            "decided_by": row.decided_by,
            "category": row.category,
            "decision": row.decision,
            "reason": row.reason,
            "alternatives": _loads(row.alternatives_json, []),
            "evidence": _loads(row.evidence_json, []),
            "outcome": row.outcome,
            "outcome_score": row.outcome_score,
            "lessons": _loads(row.lessons_json, []),
            "status": row.status,
            "analyzed": row.analyzed,
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


decision_service = DecisionService()
