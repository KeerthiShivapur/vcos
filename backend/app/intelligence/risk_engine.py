"""Phase 9.9 — Background risk engine (continuous risk assessment).

While the executive risk engine (Phase 8.4) derives strategic risks from
operational data directly, this engine turns the *background intelligence
layer's own findings* into strategic risks, closing the loop: anything the
autonomous organization detects (knowledge decay, overload signals, approval
bottlenecks, duplicate work, repeated delays, collaboration silos) becomes a
managed strategic risk with a probability/impact score, recommended actions
and an evidence chain.

Design rules:
- Risks persist to ``strategic_risks`` (StrategicRisk) so the executive risk
  register is the single source of truth for risk management.
- Deduplication uses (kind, subject_type, subject_id, title) against open
  risks — a finding that keeps occurring just re-scores the open risk instead
  of flooding the register.
- Each newly created risk emits a ``risk.detected`` background event (audit
  stream only, no dispatch job).
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.executive import StrategicRisk
from app.models.intelligence import (
    ACTIVE_PATTERN_STATUSES,
    BurnoutSignal,
    CollaborationMetric,
    DuplicateDetection,
    KnowledgeInsight,
    PatternDetection,
    WorkflowInsight,
)

logger = logging.getLogger("vcos.intelligence.risk")

_SIGNAL_SOURCES = {
    "knowledge_loss": {
        "title_prefix": "Knowledge risk",
        "probability": 0.5,
        "impact": 0.6,
        "level": "medium",
        "actions": ["Refresh or archive the outdated knowledge", "Assign an owner to close the gap"],
    },
    "overload": {
        "title_prefix": "Overload signal",
        "probability": 0.55,
        "impact": 0.7,
        "level": "high",
        "actions": ["Review the employee's workload distribution", "Reallocate tasks to balance load"],
    },
    "approval_bottleneck": {
        "title_prefix": "Approval bottleneck",
        "probability": 0.6,
        "impact": 0.55,
        "level": "medium",
        "actions": ["Add a secondary approver", "Define SLA-backed approval routing"],
    },
    "duplicate_work": {
        "title_prefix": "Duplicate work",
        "probability": 0.5,
        "impact": 0.4,
        "level": "medium",
        "actions": ["Merge the duplicated items", "Add a naming convention to avoid recurrence"],
    },
    "repeated_delay": {
        "title_prefix": "Repeated delay pattern",
        "probability": 0.6,
        "impact": 0.6,
        "level": "high",
        "actions": ["Investigate the root cause of the recurring delay", "Re-estimate the affected scope"],
    },
    "collaboration_silo": {
        "title_prefix": "Collaboration silo",
        "probability": 0.45,
        "impact": 0.5,
        "level": "medium",
        "actions": ["Create cross-team pairing opportunities", "Share visibility into the isolated area"],
    },
}


class BackgroundRiskEngine:
    async def scan(self, db: AsyncSession, *, organization_id: str) -> int:
        """Detect risks from the intelligence layer; returns new risks created."""
        created = 0
        candidates = [
            *await self._knowledge_risks(db, organization_id=organization_id),
            *await self._overload_risks(db, organization_id=organization_id),
            *await self._approval_risks(db, organization_id=organization_id),
            *await self._duplicate_risks(db, organization_id=organization_id),
            *await self._pattern_risks(db, organization_id=organization_id),
            *await self._silo_risks(db, organization_id=organization_id),
        ]
        for candidate in candidates:
            if await self._persist(db, organization_id=organization_id, candidate=candidate):
                created += 1
        if created:
            await db.flush()
            await publish_background_event(
                db,
                name="risk.detected",
                organization_id=organization_id,
                payload={"new_risks": created},
            )
        return created

    # -------------------------------------------------------------- sources

    async def _knowledge_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(KnowledgeInsight).where(
                    KnowledgeInsight.organization_id == organization_id,
                    KnowledgeInsight.status == "open",
                    KnowledgeInsight.kind.in_(("outdated", "missing", "gap", "conflict")),
                )
            )
        ).scalars().all()
        results = []
        for insight in rows:
            results.append({
                "kind": "knowledge_loss",
                "title": f"{_SIGNAL_SOURCES['knowledge_loss']['title_prefix']}: {insight.title}",
                "description": f"Background knowledge scan flagged: {insight.detail or insight.title}.",
                "subject_type": insight.entity_type or "knowledge",
                "subject_id": insight.entity_id,
                "subject_name": insight.title[:250],
                "evidence": [f"{insight.kind} insight (confidence {insight.confidence:.2f})"],
                "source_ref": insight.id,
            })
        return results

    async def _overload_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        from app.models.employee import Employee

        rows = (
            await db.execute(
                select(BurnoutSignal, Employee.display_name, Employee.first_name, Employee.last_name)
                .join(Employee, Employee.id == BurnoutSignal.employee_id)
                .where(
                    BurnoutSignal.organization_id == organization_id,
                    BurnoutSignal.status == "open",
                    BurnoutSignal.level.in_(("elevated", "high")),
                )
            )
        ).all()
        results = []
        for signal, display_name, first_name, last_name in rows:
            full_name = display_name or f"{first_name} {last_name or ''}".strip()
            # severity-aware scoring: a high signal is a high-probability risk
            probability = 0.75 if signal.level == "high" else 0.55
            results.append({
                "kind": "overload",
                "title": f"{_SIGNAL_SOURCES['overload']['title_prefix']}: {full_name} ({signal.level})",
                "description": (
                    f"Workload patterns for {full_name} match a {signal.level} overload pattern. "
                    "This is a data-driven workload flag, not a diagnosis."
                ),
                "subject_type": "employee",
                "subject_id": signal.employee_id,
                "subject_name": full_name,
                "probability": probability,
                "impact": 0.7,
                "evidence": list((signal.signals or {}).values())[:4],
                "source_ref": signal.id,
            })
        return results

    async def _approval_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(WorkflowInsight).where(
                    WorkflowInsight.organization_id == organization_id,
                    WorkflowInsight.status == "open",
                    WorkflowInsight.insight_type.in_(("approval_bottleneck", "slow_approval")),
                    WorkflowInsight.severity.in_(("warning", "critical")),
                )
            )
        ).scalars().all()
        results = []
        for insight in rows:
            results.append({
                "kind": "approval_bottleneck",
                "title": f"{_SIGNAL_SOURCES['approval_bottleneck']['title_prefix']}: {insight.title}",
                "description": insight.detail or insight.title,
                "subject_type": insight.entity_type,
                "subject_id": insight.entity_id,
                "subject_name": insight.title[:250],
                "evidence": [f"{insight.insight_type} insight ({insight.severity})"],
                "source_ref": insight.id,
            })
        return results

    async def _duplicate_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(DuplicateDetection).where(
                    DuplicateDetection.organization_id == organization_id,
                    DuplicateDetection.status == "open",
                    DuplicateDetection.similarity >= 0.8,
                )
            )
        ).scalars().all()
        results = []
        for dup in rows:
            results.append({
                "kind": "duplicate_work",
                "title": f"{_SIGNAL_SOURCES['duplicate_work']['title_prefix']}: {dup.title_a}",
                "description": (
                    f"'{dup.title_a}' and '{dup.title_b}' appear to be duplicates "
                    f"(similarity {dup.similarity:.0%}). {dup.reason or ''}"
                ),
                "subject_type": dup.entity_type_a,
                "subject_id": dup.entity_id_a,
                "subject_name": (dup.title_a or dup.title_b)[:250],
                "evidence": [f"similarity {dup.similarity:.0%}", dup.reason or ""],
                "source_ref": dup.id,
            })
        return results

    async def _pattern_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(PatternDetection).where(
                    PatternDetection.organization_id == organization_id,
                    PatternDetection.status.in_(ACTIVE_PATTERN_STATUSES),
                    PatternDetection.pattern_type == "repeated_delay",
                    PatternDetection.count >= 2,
                )
            )
        ).scalars().all()
        results = []
        for pattern in rows:
            results.append({
                "kind": "repeated_delay",
                "title": f"{_SIGNAL_SOURCES['repeated_delay']['title_prefix']}: {pattern.title}",
                "description": pattern.detail or pattern.title,
                "subject_type": "pattern",
                "subject_id": pattern.id,
                "subject_name": pattern.title[:250],
                "evidence": [f"seen {pattern.count}x", pattern.evidence or ""],
                "source_ref": pattern.id,
            })
        return results

    async def _silo_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(CollaborationMetric).where(
                    CollaborationMetric.organization_id == organization_id,
                    CollaborationMetric.metric_type == "silo",
                    CollaborationMetric.value >= 0.6,
                )
            )
        ).scalars().all()
        results = []
        for metric in rows:
            detail = metric.detail or {}
            label = detail.get("department") or detail.get("label") or "an area"
            results.append({
                "kind": "collaboration_silo",
                "title": f"{_SIGNAL_SOURCES['collaboration_silo']['title_prefix']}: {label}",
                "description": (
                    f"Collaboration analysis found {label} with a silo score of "
                    f"{metric.value:.0%}, indicating low cross-functional interaction."
                ),
                "subject_type": "department",
                "subject_id": detail.get("department_id"),
                "subject_name": str(label)[:250],
                "evidence": [f"silo score {metric.value:.0%}"],
                "source_ref": metric.id,
            })
        return results

    # -------------------------------------------------------------- persistence

    async def _persist(self, db: AsyncSession, *, organization_id: str, candidate: dict[str, Any]) -> bool:
        """Create a new risk unless an open risk with the same identity exists."""
        kind = candidate["kind"]
        template = _SIGNAL_SOURCES[kind]
        existing = await self._find_open(
            db, organization_id=organization_id,
            kind=kind, subject_id=candidate.get("subject_id"),
            title=candidate["title"],
        )
        if existing is not None:
            # re-score with the latest signal, keep single row per identity
            existing.probability = max(existing.probability, candidate.get("probability", template["probability"]))
            existing.impact = max(existing.impact, candidate.get("impact", template["impact"]))
            existing.score = round(existing.probability * existing.impact, 3)
            existing.level = self._level(existing.score)
            existing.updated_at = utcnow()
            return False
        probability = candidate.get("probability", template["probability"])
        impact = candidate.get("impact", template["impact"])
        score = round(probability * impact, 3)
        db.add(
            StrategicRisk(
                organization_id=organization_id,
                kind=kind,
                title=candidate["title"][:300],
                description=candidate.get("description"),
                probability=probability,
                impact=impact,
                score=score,
                level=self._level(score),
                subject_type=candidate.get("subject_type"),
                subject_id=candidate.get("subject_id"),
                subject_name=candidate.get("subject_name"),
                affected_teams_json=None,
                recommended_actions_json=json.dumps(template["actions"]),
                evidence_json=json.dumps(candidate.get("evidence", []), default=str),
                status="open",
            )
        )
        return True

    async def _find_open(
        self, db: AsyncSession, *, organization_id: str, kind: str,
        subject_id: Optional[str], title: str,
    ) -> Optional[StrategicRisk]:
        stmt = select(StrategicRisk).where(
            StrategicRisk.organization_id == organization_id,
            StrategicRisk.kind == kind,
            StrategicRisk.status == "open",
            StrategicRisk.title == title,
        )
        if subject_id:
            stmt = stmt.where(StrategicRisk.subject_id == subject_id)
        row = await db.execute(stmt)
        return row.scalars().first()

    @staticmethod
    def _level(score: float) -> str:
        if score >= 0.7:
            return "critical"
        if score >= 0.45:
            return "high"
        if score >= 0.25:
            return "medium"
        return "low"

    async def list_open(self, db: AsyncSession, *, organization_id: str,
                        limit: int = 50) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(StrategicRisk)
                .where(StrategicRisk.organization_id == organization_id)
                .order_by(StrategicRisk.score.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "title": r.title,
                "description": r.description,
                "probability": r.probability,
                "impact": r.impact,
                "score": r.score,
                "level": r.level,
                "subject_type": r.subject_type,
                "subject_id": r.subject_id,
                "subject_name": r.subject_name,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


background_risk_engine = BackgroundRiskEngine()
