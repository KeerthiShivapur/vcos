"""Organization Health Engine (Phase 18.5) — unified health score.

Nine dimensions are scored 0-100 from the digital twin's entity counts:

  organization, leadership, knowledge, learning, customer, community,
  innovation, financial, department

The unified score is the weighted average; the record is persisted so health
trends are visible over time.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.digital_twin.twin_service import digital_twin_service
from app.events.publisher import publish_background_event
from app.models.digital_twin import OrganizationHealthRecord

logger = logging.getLogger("vcos.digital_twin.health")

WEIGHTS = {
    "organization": 0.15,
    "leadership": 0.12,
    "knowledge": 0.12,
    "learning": 0.10,
    "customer": 0.12,
    "community": 0.08,
    "innovation": 0.08,
    "financial": 0.15,
    "department": 0.08,
}


def _score_components(dimensions: dict[str, Any], counts: dict[str, int]) -> dict[str, Any]:
    """Score each dimension from twin aggregates with explainable drivers."""
    people = dimensions.get("people", {})
    employees = people.get("active", counts.get("active_employees", counts.get("employees", 0))) or 0

    components: dict[str, dict[str, Any]] = {}

    # organization — structural coverage (departments/teams present)
    org = dimensions.get("organization", {})
    org_score = min(100, 30 + (org.get("departments", 0) or 0) * 15 + (org.get("teams", 0) or 0) * 10)
    components["organization"] = {
        "score": round(org_score),
        "status": _status(org_score),
        "drivers": [f"{org.get('departments', 0)} departments", f"{org.get('teams', 0)} teams"],
    }

    # leadership — performance reviews + succession readiness proxy
    hr = dimensions.get("hr", {})
    leadership = min(100, 40 + (hr.get("performance_reviews", 0) or 0) * 12)
    components["leadership"] = {
        "score": round(leadership),
        "status": _status(leadership),
        "drivers": [f"{hr.get('performance_reviews', 0)} performance reviews on record"],
    }

    # knowledge — indexed knowledge per employee
    knowledge = dimensions.get("knowledge", {})
    indexed = knowledge.get("indexed", counts.get("knowledge_indexed", 0)) or 0
    per_employee = indexed / employees if employees else 0
    knowledge_score = min(100, 30 + per_employee * 15)
    components["knowledge"] = {
        "score": round(knowledge_score),
        "status": _status(knowledge_score),
        "drivers": [f"{indexed} indexed knowledge items", f"{per_employee:.1f} per employee"],
    }

    # learning — enrollment coverage
    learning = dimensions.get("learning", {})
    enrollments = learning.get("enrollments", counts.get("course_enrollments", 0)) or 0
    learning_score = min(100, 25 + enrollments / employees * 30) if employees else 25.0
    components["learning"] = {
        "score": round(learning_score),
        "status": _status(learning_score),
        "drivers": [f"{enrollments} course enrollments"],
    }

    # customer — relationship density
    customers = dimensions.get("customers", {})
    customer_score = min(100, 35 + (customers.get("customers", 0) or 0) * 8)
    components["customer"] = {
        "score": round(customer_score),
        "status": _status(customer_score),
        "drivers": [f"{customers.get('customers', 0)} customers", f"{customers.get('contracts', 0)} contracts"],
    }

    # community — activity level
    community = dimensions.get("community", {})
    activity = (community.get("posts", 0) or 0) + (community.get("recognition", 0) or 0) * 2
    community_score = min(100, 30 + activity * 4)
    components["community"] = {
        "score": round(community_score),
        "status": _status(community_score),
        "drivers": [f"{community.get('posts', 0)} posts", f"{community.get('recognition', 0)} recognitions"],
    }

    # innovation — initiatives + workflow automation coverage
    workflows = dimensions.get("workflows", {})
    innovation = min(100, 30 + (workflows.get("workflows", 0) or 0) * 10)
    components["innovation"] = {
        "score": round(innovation),
        "status": _status(innovation),
        "drivers": [f"{workflows.get('workflows', 0)} automated workflows"],
    }

    # financial — budget/expense discipline proxy
    finance = dimensions.get("finance", {})
    financial = min(100, 40 + (finance.get("budgets", 0) or 0) * 12 - min(30, (finance.get("expenses", 0) or 0)))
    components["financial"] = {
        "score": round(max(0, financial)),
        "status": _status(financial),
        "drivers": [f"{finance.get('budgets', 0)} budgets", f"{finance.get('expenses', 0)} expenses"],
    }

    # department — workload balance proxy
    projects = dimensions.get("projects", {})
    open_tasks = projects.get("open_tasks", counts.get("open_tasks", 0)) or 0
    department = min(100, 60 + 40 - (open_tasks / employees * 5 if employees else 0))
    components["department"] = {
        "score": round(department),
        "status": _status(department),
        "drivers": [f"{open_tasks} open tasks", f"{employees} employees"],
    }

    return components


def _status(score: float) -> str:
    if score >= 75:
        return "excellent"
    if score >= 60:
        return "good"
    if score >= 40:
        return "watch"
    return "at_risk"


class HealthService:
    """Computes and persists unified organization health records."""

    async def compute(
        self, db: AsyncSession, organization_id: str, *, persist: bool = True
    ) -> dict[str, Any]:
        twin = await digital_twin_service.get_twin(db, organization_id)
        if twin is None:
            twin_payload = await digital_twin_service.build_twin(db, organization_id)
            counts = twin_payload["entity_counts"]
            dimensions = twin_payload["dimensions"]
        else:
            import json as _json

            counts = _json.loads(twin.entity_counts_json or "{}")
            dimensions = _json.loads(twin.dimensions_json or "{}")

        components = _score_components(dimensions, counts)
        total = 0.0
        weight_sum = 0.0
        for key, weight in WEIGHTS.items():
            comp = components.get(key)
            if comp:
                total += comp["score"] * weight
                weight_sum += weight
        score = round(total / weight_sum) if weight_sum else 0
        status = _status(score)

        result = {
            "score": score,
            "status": status,
            "breakdown": components,
            "generated_at": utcnow().isoformat(),
        }

        if persist:
            record = OrganizationHealthRecord(
                organization_id=organization_id,
                score=score,
                status=status,
                breakdown_json=json.dumps(components),
                period=utcnow().strftime("%Y-%m-%d"),
                generated_at=utcnow(),
            )
            db.add(record)
            twin_row = await digital_twin_service.get_twin(db, organization_id)
            if twin_row is not None:
                twin_row.health_score = score
                twin_row.health_status = status
            await db.flush()
            await publish_background_event(
                db,
                name="health.updated",
                organization_id=organization_id,
                payload={"score": score, "status": status},
            )
        return result

    async def latest(self, db: AsyncSession, organization_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(OrganizationHealthRecord)
                .where(OrganizationHealthRecord.organization_id == organization_id)
                .order_by(OrganizationHealthRecord.generated_at.desc())
                .limit(1)
            )
        ).scalars().first()
        return self.serialize(row) if row else None

    async def history(self, db: AsyncSession, organization_id: str, limit: int = 30) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(OrganizationHealthRecord)
                .where(OrganizationHealthRecord.organization_id == organization_id)
                .order_by(OrganizationHealthRecord.generated_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [self.serialize(r) for r in rows]

    def serialize(self, record: OrganizationHealthRecord) -> dict[str, Any]:
        breakdown = {}
        if record.breakdown_json:
            try:
                breakdown = json.loads(record.breakdown_json)
            except (json.JSONDecodeError, TypeError):
                breakdown = {}
        return {
            "id": record.id,
            "score": record.score,
            "status": record.status,
            "breakdown": breakdown,
            "period": record.period,
            "generated_at": record.generated_at.isoformat() if record.generated_at else None,
        }


health_service = HealthService()
