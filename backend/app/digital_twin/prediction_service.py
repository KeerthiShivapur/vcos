"""Predictive Intelligence (Phase 18.4) — explainable organizational predictions.

The prediction engine evaluates the digital twin's state against ten risk
kinds (attrition, project failure, budget overrun, customer churn, knowledge
loss, security risk, burnout, compliance risk, hiring need, innovation trend)
and produces probability/impact/score with a traceable evidence chain.

Models are deterministic rule engines over twin aggregates — every prediction
carries `signals` explaining *why* so executives can audit the reasoning.
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.digital_twin.twin_service import digital_twin_service
from app.events.publisher import publish_background_event
from app.models.digital_twin import TwinPrediction

logger = logging.getLogger("vcos.digital_twin.prediction")

PREDICTION_KINDS = [
    "attrition",
    "project_failure",
    "budget_overrun",
    "customer_churn",
    "knowledge_loss",
    "security_risk",
    "burnout",
    "compliance_risk",
    "hiring_need",
    "innovation_trend",
]


def _level(score: float) -> str:
    if score >= 70:
        return "critical"
    if score >= 45:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


class PredictionService:
    """Generates explainable predictions from the digital twin state."""

    async def _state(self, db: AsyncSession, organization_id: str) -> tuple[dict, dict, dict]:
        twin = await digital_twin_service.get_twin(db, organization_id)
        if twin is None:
            payload = await digital_twin_service.build_twin(db, organization_id)
            return payload["entity_counts"], payload["dimensions"], payload["state"]
        import json as _json

        counts = _json.loads(twin.entity_counts_json or "{}")
        dims = _json.loads(twin.dimensions_json or "{}")
        state = _json.loads(twin.state_json or "{}")
        return counts, dims, state

    async def generate(self, db: AsyncSession, organization_id: str, *, commit: bool = False) -> list[dict[str, Any]]:
        counts, dims, state = await self._state(db, organization_id)
        predictions = self._evaluate(counts, dims, state)
        rows = []
        for pred in predictions:
            row = TwinPrediction(
                organization_id=organization_id,
                kind=pred["kind"],
                title=pred["title"],
                description=pred.get("description"),
                probability=pred["probability"],
                impact=pred["impact"],
                score=pred["score"],
                level=pred["level"],
                horizon_days=pred["horizon_days"],
                subject_type=pred.get("subject_type"),
                subject_name=pred.get("subject_name"),
                signals_json=json.dumps(pred.get("signals", [])),
                recommended_action=pred.get("recommended_action"),
                status="active",
            )
            db.add(row)
            rows.append(row)
        await db.flush()
        created = [self.serialize(r) for r in rows]
        if created:
            await publish_background_event(
                db,
                name="prediction.generated",
                organization_id=organization_id,
                payload={"count": len(created), "kinds": [c["kind"] for c in created]},
            )
        if commit:
            await db.commit()
        return created

    def _evaluate(self, counts: dict, dims: dict, state: dict) -> list[dict[str, Any]]:
        employees = counts.get("active_employees", counts.get("employees", 0)) or 0
        open_tasks = counts.get("open_tasks", 0) or 0
        projects_total = counts.get("projects", 0) or 0
        active_projects = counts.get("active_projects", 0) or 0
        customers = counts.get("customers", 0) or 0
        knowledge = counts.get("knowledge_indexed", counts.get("documents", 0)) or 0
        meetings = counts.get("meetings", 0) or 0
        workloads = state.get("workload_per_employee", 0) or 0
        out: list[dict[str, Any]] = []

        # attrition — workload + absence of leadership/review coverage
        workload_factor = min(60, workloads * 12)
        attrition_prob = min(85, workload_factor + (8 if employees and not dims.get("hr", {}).get("performance_reviews") else 0))
        out.append(
            {
                "kind": "attrition",
                "title": "Attrition risk from workload pressure",
                "description": "Workload per employee may push talent out without intervention.",
                "probability": round(attrition_prob, 1),
                "impact": 80.0,
                "score": round(attrition_prob * 0.8, 1),
                "level": _level(attrition_prob * 0.8),
                "horizon_days": 90,
                "subject_type": "organization",
                "subject_name": "Workforce",
                "signals": [
                    {"metric": "workload_per_employee", "value": workloads, "note": "Open tasks per employee"},
                    {"metric": "active_employees", "value": employees},
                ],
                "recommended_action": "Re-balance task allocation and schedule review check-ins for overloaded teams.",
            }
        )

        # project failure — active projects without capacity
        if active_projects:
            ratio = open_tasks / (employees * 4) if employees else 1.0
            prob = min(80, ratio * 40 + (5 if projects_total > 3 * (employees or 1) else 0))
            out.append(
                {
                    "kind": "project_failure",
                    "title": "Project delivery risk from open task load",
                    "description": "Open task load relative to headcount may cause delivery slippage.",
                    "probability": round(prob, 1),
                    "impact": 75.0,
                    "score": round(prob * 0.75, 1),
                    "level": _level(prob * 0.75),
                    "horizon_days": 30,
                    "subject_type": "organization",
                    "subject_name": "Portfolio",
                    "signals": [
                        {"metric": "open_tasks", "value": open_tasks},
                        {"metric": "active_projects", "value": active_projects},
                    ],
                    "recommended_action": "Review project scope and re-sequence milestones in the twin simulation studio.",
                }
            )

        # budget overrun
        finance = dims.get("finance", {})
        expenses = finance.get("expenses", counts.get("expenses", 0)) or 0
        budgets = finance.get("budgets", counts.get("budgets", 0)) or 0
        if budgets:
            ratio = expenses / max(1, budgets * 10)
            prob = min(70, ratio * 50)
            out.append(
                {
                    "kind": "budget_overrun",
                    "title": "Budget overrun risk",
                    "description": "Expense velocity relative to budget coverage may exceed allocations.",
                    "probability": round(prob, 1),
                    "impact": 60.0,
                    "score": round(prob * 0.6, 1),
                    "level": _level(prob * 0.6),
                    "horizon_days": 90,
                    "subject_type": "organization",
                    "subject_name": "Finance",
                    "signals": [{"metric": "expenses", "value": expenses}, {"metric": "budgets", "value": budgets}],
                    "recommended_action": "Run a finance scenario simulation to model expense ceilings.",
                }
            )

        # customer churn
        if customers:
            coverage = min(100, knowledge / max(1, customers))
            prob = min(60, 35 + (20 if coverage < 15 else 0))
            out.append(
                {
                    "kind": "customer_churn",
                    "title": "Customer churn risk from low knowledge coverage",
                    "description": "Limited knowledge indexed per customer may weaken account management.",
                    "probability": round(prob, 1),
                    "impact": 70.0,
                    "score": round(prob * 0.7, 1),
                    "level": _level(prob * 0.7),
                    "horizon_days": 90,
                    "subject_type": "organization",
                    "subject_name": "Customers",
                    "signals": [{"metric": "customers", "value": customers}, {"metric": "knowledge_indexed", "value": knowledge}],
                    "recommended_action": "Strengthen customer documentation and renewal tracking.",
                }
            )

        # knowledge loss
        if employees:
            knowledge_per_employee = knowledge / employees
            prob = min(70, 50 - knowledge_per_employee * 3)
            out.append(
                {
                    "kind": "knowledge_loss",
                    "title": "Knowledge loss risk from thin documentation",
                    "description": "Low indexed knowledge per employee risks institutional memory loss.",
                    "probability": round(max(0, prob), 1),
                    "impact": 55.0,
                    "score": round(max(0, prob) * 0.55, 1),
                    "level": _level(max(0, prob) * 0.55),
                    "horizon_days": 120,
                    "subject_type": "organization",
                    "subject_name": "Knowledge",
                    "signals": [{"metric": "knowledge_indexed", "value": knowledge}, {"metric": "employees", "value": employees}],
                    "recommended_action": "Enable knowledge gap detection and duplicate merging in the knowledge hub.",
                }
            )

        # security risk — workflow automation without coverage
        workflows = dims.get("workflows", {})
        automation_share = (workflows.get("workflows", 0) or 0) / max(1, projects_total + 1)
        prob = min(50, 30 - automation_share * 10)
        out.append(
            {
                "kind": "security_risk",
                "title": "Security risk from low process automation",
                "description": "Manual process handling increases exposure to errors and policy drift.",
                "probability": round(max(0, prob), 1),
                "impact": 65.0,
                "score": round(max(0, prob) * 0.65, 1),
                "level": _level(max(0, prob) * 0.65),
                "horizon_days": 90,
                "subject_type": "organization",
                "subject_name": "Operations",
                "signals": [{"metric": "workflows", "value": workflows.get("workflows", 0)}],
                "recommended_action": "Automate repetitive approval and handoff steps with the workflow engine.",
            }
        )

        # burnout — workload + meeting pressure
        meeting_pressure = min(40, meetings * 2)
        burnout_prob = min(80, workload_factor + meeting_pressure)
        out.append(
            {
                "kind": "burnout",
                "title": "Burnout risk from load and meeting pressure",
                "description": "Combined task load and meeting volume may exceed sustainable capacity.",
                "probability": round(burnout_prob, 1),
                "impact": 50.0,
                "score": round(burnout_prob * 0.5, 1),
                "level": _level(burnout_prob * 0.5),
                "horizon_days": 30,
                "subject_type": "organization",
                "subject_name": "People",
                "signals": [{"metric": "meetings", "value": meetings}, {"metric": "workload_per_employee", "value": workloads}],
                "recommended_action": "Use the optimization engine to suggest meeting reduction.",
            }
        )

        # compliance risk — hr/asset tracking coverage
        assets = counts.get("assets", 0) or 0
        hr_dims = dims.get("hr", {})
        prob = min(55, 35 - (assets / max(1, employees) * 10) - (hr_dims.get("payroll_runs", 0) or 0))
        out.append(
            {
                "kind": "compliance_risk",
                "title": "Compliance risk from thin HR records",
                "description": "Limited asset/payroll records may leave compliance gaps.",
                "probability": round(max(0, prob), 1),
                "impact": 60.0,
                "score": round(max(0, prob) * 0.6, 1),
                "level": _level(max(0, prob) * 0.6),
                "horizon_days": 120,
                "subject_type": "organization",
                "subject_name": "HR & Compliance",
                "signals": [{"metric": "assets", "value": assets}, {"metric": "payroll_runs", "value": hr_dims.get("payroll_runs", 0)}],
                "recommended_action": "Complete asset assignments and payroll run records.",
            }
        )

        # hiring need — workload-to-capacity gap
        capacity = employees * 4 if employees else 0
        if open_tasks > capacity:
            shortage = int(open_tasks - capacity)
            out.append(
                {
                    "kind": "hiring_need",
                    "title": f"Hiring need: ~{max(1, shortage // 8)} additional headcount",
                    "description": "Open task load exceeds current capacity, indicating hiring demand.",
                    "probability": 70.0,
                    "impact": 45.0,
                    "score": 31.5,
                    "level": "high",
                    "horizon_days": 60,
                    "subject_type": "organization",
                    "subject_name": "Workforce",
                    "signals": [
                        {"metric": "open_tasks", "value": open_tasks},
                        {"metric": "capacity_estimate", "value": capacity},
                    ],
                    "recommended_action": "Model the hire-engineers scenario in the simulation studio.",
                }
            )

        # innovation trend
        community = dims.get("community", {})
        activity = (community.get("posts", 0) or 0) + (community.get("recognition", 0) or 0)
        trend = min(95, 30 + activity * 3)
        out.append(
            {
                "kind": "innovation_trend",
                "title": "Innovation momentum trend",
                "description": "Community and recognition activity indicates healthy idea flow.",
                "probability": round(trend, 1),
                "impact": 35.0,
                "score": round(trend * 0.35, 1),
                "level": "low",
                "horizon_days": 60,
                "subject_type": "organization",
                "subject_name": "Innovation",
                "signals": [{"metric": "community_posts", "value": community.get("posts", 0)}, {"metric": "recognition", "value": community.get("recognition", 0)}],
                "recommended_action": "Channel momentum into the innovation pipeline and idea reviews.",
            }
        )
        return out

    async def list(self, db: AsyncSession, organization_id: str, kind: Optional[str] = None, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        query = select(TwinPrediction).where(TwinPrediction.organization_id == organization_id)
        if kind:
            query = query.where(TwinPrediction.kind == kind)
        if status:
            query = query.where(TwinPrediction.status == status)
        query = query.order_by(TwinPrediction.score.desc()).limit(limit)
        rows = (await db.execute(query)).scalars().all()
        return [self.serialize(r) for r in rows]

    async def set_status(self, db: AsyncSession, organization_id: str, prediction_id: str, status: str, *, commit: bool = False) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(TwinPrediction).where(
                    TwinPrediction.organization_id == organization_id,
                    TwinPrediction.id == prediction_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        row.status = status
        row.resolved_at = utcnow()
        await db.flush()
        if commit:
            await db.commit()
        return self.serialize(row)

    def serialize(self, row: TwinPrediction) -> dict[str, Any]:
        signals = []
        if row.signals_json:
            try:
                signals = json.loads(row.signals_json)
            except (json.JSONDecodeError, TypeError):
                signals = []
        return {
            "id": row.id,
            "kind": row.kind,
            "title": row.title,
            "description": row.description,
            "probability": row.probability,
            "impact": row.impact,
            "score": row.score,
            "level": row.level,
            "horizon_days": row.horizon_days,
            "subject_type": row.subject_type,
            "subject_name": row.subject_name,
            "signals": signals,
            "recommended_action": row.recommended_action,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


prediction_service = PredictionService()
