"""Organizational Optimization Engine (Phase 18.12).

Suggests restructuring, project reassignment, expert allocation, meeting
reduction, workflow simplification and automation opportunities — each with
evidence and an expected gain. Persists through the `OptimizationAction`
table and emits `optimization.suggested`.
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.digital_twin.twin_service import digital_twin_service
from app.events.publisher import publish_background_event
from app.models.digital_twin import OptimizationAction

logger = logging.getLogger("vcos.digital_twin.optimization")

OPTIMIZATION_KINDS = [
    "restructuring",
    "reassignment",
    "expert_allocation",
    "meeting_reduction",
    "workflow_simplification",
    "automation",
]


class OptimizationService:
    """Produces evidence-based optimization suggestions from the twin."""

    async def generate(self, db: AsyncSession, organization_id: str, *, commit: bool = False) -> list[dict[str, Any]]:
        twin = await digital_twin_service.get_twin(db, organization_id)
        if twin is None:
            payload = await digital_twin_service.build_twin(db, organization_id)
            counts = payload["entity_counts"]
        else:
            counts = json.loads(twin.entity_counts_json or "{}")

        employees = counts.get("active_employees", counts.get("employees", 0)) or 0
        open_tasks = counts.get("open_tasks", 0) or 0
        tasks = counts.get("tasks", 0) or 0
        meetings = counts.get("meetings", 0) or 0
        workflows = counts.get("workflows", 0) or 0
        projects = counts.get("projects", 0) or 0
        departments = counts.get("departments", 0) or 0
        knowledge = counts.get("knowledge_indexed", counts.get("documents", 0)) or 0

        suggestions: list[dict[str, Any]] = []

        if employees and departments > 1 and departments > employees:
            suggestions.append(
                {
                    "kind": "restructuring",
                    "title": "Consolidate small departments",
                    "rationale": f"{departments} departments for {employees} employees fragments coordination.",
                    "evidence": [{"metric": "departments", "value": departments}, {"metric": "employees", "value": employees}],
                    "impact": "high",
                    "effort": "medium",
                    "expected_gain": 40.0,
                }
            )

        if employees and open_tasks > employees * 5:
            suggestions.append(
                {
                    "kind": "reassignment",
                    "title": "Reassign overloaded task queues",
                    "rationale": f"{open_tasks} open tasks against {employees} employees exceeds balance thresholds.",
                    "evidence": [{"metric": "open_tasks", "value": open_tasks}, {"metric": "active_employees", "value": employees}],
                    "impact": "high",
                    "effort": "low",
                    "expected_gain": open_tasks * 0.5,
                }
            )

        if employees and knowledge and knowledge / employees < 8:
            suggestions.append(
                {
                    "kind": "expert_allocation",
                    "title": "Nominate knowledge experts for onboarding",
                    "rationale": f"Only {knowledge / employees:.1f} knowledge items per employee; expert-led onboarding accelerates coverage.",
                    "evidence": [{"metric": "knowledge_indexed", "value": knowledge}],
                    "impact": "medium",
                    "effort": "low",
                    "expected_gain": 20.0,
                }
            )

        if meetings > 3:
            suggestions.append(
                {
                    "kind": "meeting_reduction",
                    "title": "Cut recurring meeting overhead",
                    "rationale": f"{meetings} meetings on record; recurring events should be audited for value.",
                    "evidence": [{"metric": "meetings", "value": meetings}],
                    "impact": "medium",
                    "effort": "low",
                    "expected_gain": meetings * 1.5,
                }
            )

        if workflows and workflows < projects:
            suggestions.append(
                {
                    "kind": "workflow_simplification",
                    "title": "Simplify multi-step approvals",
                    "rationale": f"{workflows} workflows for {projects} projects suggest room for leaner paths.",
                    "evidence": [{"metric": "workflows", "value": workflows}, {"metric": "projects", "value": projects}],
                    "impact": "medium",
                    "effort": "medium",
                    "expected_gain": workflows * 2.0,
                }
            )

        if tasks and workflows == 0:
            suggestions.append(
                {
                    "kind": "automation",
                    "title": "Automate repetitive task handoffs",
                    "rationale": "No workflow automation is configured while task volume is non-zero.",
                    "evidence": [{"metric": "tasks", "value": tasks}, {"metric": "workflows", "value": workflows}],
                    "impact": "high",
                    "effort": "medium",
                    "expected_gain": tasks * 0.1,
                }
            )

        if not suggestions:
            suggestions.append(
                {
                    "kind": "workflow_simplification",
                    "title": "Establish baseline operating cadence",
                    "rationale": "No blockers detected; setting baselines for workflows and meetings prevents drift.",
                    "evidence": [{"metric": "employees", "value": employees}, {"metric": "workflows", "value": workflows}],
                    "impact": "low",
                    "effort": "low",
                    "expected_gain": 5.0,
                }
            )

        created_rows = []
        for s in suggestions:
            row = OptimizationAction(
                organization_id=organization_id,
                kind=s["kind"],
                title=s["title"],
                rationale=s.get("rationale"),
                impact=s.get("impact", "medium"),
                effort=s.get("effort", "medium"),
                expected_gain=s.get("expected_gain"),
                evidence_json=json.dumps(s.get("evidence", [])),
                status="suggested",
            )
            db.add(row)
            created_rows.append(row)
        await db.flush()
        created = [{**s, "id": row.id, "status": row.status} for s, row in zip(suggestions, created_rows)]
        if created:
            await publish_background_event(
                db,
                name="optimization.suggested",
                organization_id=organization_id,
                payload={"count": len(created), "kinds": [c["kind"] for c in created]},
            )
        if commit:
            await db.commit()
        return created

    async def list(self, db: AsyncSession, organization_id: str, status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        query = select(OptimizationAction).where(OptimizationAction.organization_id == organization_id)
        if status:
            query = query.where(OptimizationAction.status == status)
        query = query.order_by(OptimizationAction.created_at.desc()).limit(limit)
        rows = (await db.execute(query)).scalars().all()
        return [self.serialize(r) for r in rows]

    async def apply(self, db: AsyncSession, organization_id: str, action_id: str, *, commit: bool = False) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(OptimizationAction).where(
                    OptimizationAction.organization_id == organization_id,
                    OptimizationAction.id == action_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        row.status = "applied"
        row.applied_at = utcnow()
        await db.flush()
        if commit:
            await db.commit()
        return self.serialize(row)

    def serialize(self, row: OptimizationAction) -> dict[str, Any]:
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
            "impact": row.impact,
            "effort": row.effort,
            "expected_gain": row.expected_gain,
            "evidence": evidence,
            "status": row.status,
            "applied_at": row.applied_at.isoformat() if row.applied_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


optimization_service = OptimizationService()
