"""Phase 8.5 — Executive Recommendation Engine.

AI continuously recommends strategic actions (hire engineers, assign people,
create documentation, reduce meetings, schedule reviews, add testing, ...).
Every recommendation explains WHY, shows the EVIDENCE, states CONFIDENCE and
the EXPECTED OUTCOME — grounded in live organizational data and the strategic
risks detected by the risk engine.
"""

import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.approval import Risk
from app.models.employee import Employee
from app.models.executive import ExecutiveRecommendation, StrategicRisk
from app.models.knowledge import Document, WikiPage
from app.models.project import Project
from app.models.task import Task
from app.models.workload import WorkloadSnapshot

logger = logging.getLogger("vcos.executive.recommendation")


class RecommendationEngine:
    async def generate(
        self, db: AsyncSession, *, organization_id: str, persist: bool = True
    ) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        risks = (await db.execute(
            select(StrategicRisk).where(
                StrategicRisk.organization_id == organization_id,
                StrategicRisk.status == "open",
            )
        )).scalars().all()

        recommendations.extend(await self._hire_engineers(db, organization_id=organization_id, risks=risks))
        recommendations.extend(await self._assign_support(db, organization_id=organization_id, risks=risks))
        recommendations.extend(await self._create_documentation(db, organization_id=organization_id, risks=risks))
        recommendations.extend(await self._reduce_meetings(db, organization_id=organization_id, risks=risks))
        recommendations.extend(await self._schedule_review(db, organization_id=organization_id, risks=risks))
        recommendations.extend(await self._add_testing(db, organization_id=organization_id, risks=risks))
        recommendations.extend(await self._close_risks(db, organization_id=organization_id, risks=risks))

        recommendations.sort(key=lambda r: r["confidence"], reverse=True)
        if persist:
            await self.persist(db, organization_id=organization_id, recommendations=recommendations)
        return recommendations

    def _rec(
        self, *, organization_id: str, kind: str, title: str, rationale: str,
        evidence: dict[str, Any], expected_outcome: str, confidence: float, impact: str,
    ) -> dict[str, Any]:
        return {
            "organization_id": organization_id,
            "kind": kind,
            "title": title,
            "rationale": rationale,
            "evidence": evidence,
            "expected_outcome": expected_outcome,
            "confidence": round(confidence, 2),
            "impact": impact,
        }

    async def _hire_engineers(
        self, db: AsyncSession, *, organization_id: str, risks: list[StrategicRisk]
    ) -> list[dict[str, Any]]:
        overloaded_risk = next((r for r in risks if r.kind == "overload"), None)
        dependency_risk = next((r for r in risks if r.kind == "key_dependency"), None)
        delay_risk = next((r for r in risks if r.kind == "project_delay"), None)
        if not (overloaded_risk or dependency_risk or delay_risk):
            return []
        reasons = []
        if overloaded_risk:
            reasons.append(f"{overloaded_risk.subject_name} is overloaded per workload snapshots")
        if dependency_risk:
            reasons.append(f"critical delivery depends on {dependency_risk.subject_name}")
        if delay_risk:
            reasons.append(f"project '{delay_risk.subject_name}' risks missing its deadline")
        return [self._rec(
            organization_id=organization_id,
            kind="hire",
            title="Hire additional engineers to relieve delivery pressure",
            rationale="Evidence of overload and dependency risk: " + "; ".join(reasons) + ".",
            evidence={
                "overloaded_employees": overloaded_risk.subject_name if overloaded_risk else None,
                "key_dependency": dependency_risk.subject_name if dependency_risk else None,
                "project_at_risk": delay_risk.subject_name if delay_risk else None,
            },
            expected_outcome="Reduced workload per engineer, lower project-delay probability and de-risked key dependencies.",
            confidence=0.8 if len(reasons) >= 2 else 0.6,
            impact="high",
        )]

    async def _assign_support(
        self, db: AsyncSession, *, organization_id: str, risks: list[StrategicRisk]
    ) -> list[dict[str, Any]]:
        results = []
        for r in risks:
            if r.kind not in ("key_dependency", "overload", "burnout"):
                continue
            results.append(self._rec(
                organization_id=organization_id,
                kind="assign",
                title=f"Assign a support/backup owner for {r.subject_name}",
                rationale=f"{r.subject_name} is central to delivery: {r.description}",
                evidence={"risk_kind": r.kind, "risk_id": r.id, "evidence": self._load_json(r.evidence_json)},
                expected_outcome="Workload is shared, single-point-of-failure risk is removed and delivery continues if the person is unavailable.",
                confidence=min(0.9, r.score + 0.3),
                impact="high" if r.level in ("high", "critical") else "medium",
            ))
        return results

    async def _create_documentation(
        self, db: AsyncSession, *, organization_id: str, risks: list[StrategicRisk]
    ) -> list[dict[str, Any]]:
        gap = [r for r in risks if r.kind == "knowledge_gap"]
        results = []
        for r in gap:
            results.append(self._rec(
                organization_id=organization_id,
                kind="document",
                title=f"Create documentation for project '{r.subject_name}'",
                rationale=r.description or "The project has no published documents or wiki pages.",
                evidence={"risk_id": r.id, "evidence": self._load_json(r.evidence_json)},
                expected_outcome="Critical project knowledge is recorded and no longer lost when people move on.",
                confidence=0.75,
                impact="medium",
            ))
        return results

    async def _reduce_meetings(
        self, db: AsyncSession, *, organization_id: str, risks: list[StrategicRisk]
    ) -> list[dict[str, Any]]:
        overload = [r for r in risks if r.kind == "meeting_overload"]
        results = []
        for r in overload[:3]:
            results.append(self._rec(
                organization_id=organization_id,
                kind="reduce_meetings",
                title=f"Reduce meetings for {r.subject_name}",
                rationale=r.description or "Too many meetings are consuming focus time.",
                evidence={"risk_id": r.id, "evidence": self._load_json(r.evidence_json)},
                expected_outcome="More focus time, lower meeting overload and better deep-work throughput.",
                confidence=0.7,
                impact="medium",
            ))
        return results

    async def _schedule_review(
        self, db: AsyncSession, *, organization_id: str, risks: list[StrategicRisk]
    ) -> list[dict[str, Any]]:
        delays = [r for r in risks if r.kind == "project_delay"]
        results = []
        for r in delays[:3]:
            results.append(self._rec(
                organization_id=organization_id,
                kind="review",
                title=f"Schedule a project review for '{r.subject_name}'",
                rationale=r.description or "The project carries delay signals that need leadership attention.",
                evidence={"risk_id": r.id, "evidence": self._load_json(r.evidence_json)},
                expected_outcome="Blockers surface early and milestones are re-sequenced before the deadline slips.",
                confidence=0.8,
                impact="high",
            ))
        return results

    async def _add_testing(
        self, db: AsyncSession, *, organization_id: str, risks: list[StrategicRisk]
    ) -> list[dict[str, Any]]:
        blocked = (
            await db.execute(select(func.count(Task.id)).where(
                Task.organization_id == organization_id, Task.status == "blocked"
            ))
        ).scalar() or 0
        if blocked < 3:
            return []
        return [self._rec(
            organization_id=organization_id,
            kind="testing",
            title="Increase testing capacity to clear blocked work",
            rationale=f"{blocked} tasks are currently blocked — likely due to verification and dependency issues.",
            evidence={"blocked_tasks": blocked},
            expected_outcome="Fewer blocked tasks, higher task-completion rate and more predictable releases.",
            confidence=0.6,
            impact="medium",
        )]

    async def _close_risks(
        self, db: AsyncSession, *, organization_id: str, risks: list[StrategicRisk]
    ) -> list[dict[str, Any]]:
        open_risks = (
            await db.execute(select(func.count(Risk.id)).where(
                Risk.organization_id == organization_id, Risk.status != "closed"
            ))
        ).scalar() or 0
        if open_risks == 0:
            return []
        return [self._rec(
            organization_id=organization_id,
            kind="risk_review",
            title="Run a risk-review session for the open project risks",
            rationale=f"{open_risks} open risk(s) remain on the books; each carries probability x impact that is not yet mitigated.",
            evidence={"open_risks": open_risks},
            expected_outcome="Risks get owners and mitigation plans, lowering the organization's risk exposure.",
            confidence=0.7,
            impact="high",
        )]

    @staticmethod
    def _load_json(value: str | None) -> Any:
        if not value:
            return {}
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}

    async def persist(
        self, db: AsyncSession, *, organization_id: str, recommendations: list[dict[str, Any]]
    ) -> int:
        active = (
            await db.execute(select(ExecutiveRecommendation).where(
                ExecutiveRecommendation.organization_id == organization_id,
                ExecutiveRecommendation.status == "active",
            ))
        ).scalars().all()
        active_by_kind = {r.kind: r for r in active}
        new_ids = {r["kind"]: r for r in recommendations}
        created = 0
        for kind, payload in new_ids.items():
            existing = active_by_kind.get(kind)
            if existing is not None:
                existing.title = payload["title"]
                existing.rationale = payload["rationale"]
                existing.evidence_json = json.dumps(payload["evidence"])
                existing.expected_outcome = payload["expected_outcome"]
                existing.confidence = payload["confidence"]
                existing.impact = payload["impact"]
                continue
            db.add(ExecutiveRecommendation(
                organization_id=organization_id,
                kind=kind,
                title=payload["title"],
                rationale=payload["rationale"],
                evidence_json=json.dumps(payload["evidence"]),
                expected_outcome=payload["expected_outcome"],
                confidence=payload["confidence"],
                impact=payload["impact"],
            ))
            created += 1
        return created


recommendation_engine = RecommendationEngine()
