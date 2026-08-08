"""Phase 19 — Autonomous Enterprise API: state, observe, insights, plans,
briefings and decision support.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.autonomy.awareness_engine import awareness_engine
from app.autonomy.executive_briefing import executive_briefing_engine
from app.autonomy.organization_engine import organization_engine
from app.autonomy.planning_engine import planning_engine
from app.autonomy.decision_support import decision_support_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

autonomy_router = APIRouter(prefix="/autonomy", tags=["autonomy"])
briefing_router = APIRouter(prefix="/autonomy/briefing", tags=["autonomy"])
decision_router = APIRouter(prefix="/autonomy/decisions", tags=["autonomy"])


# ------------------------------------------------------------------- state

@autonomy_router.get("/state")
async def company_state(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await awareness_engine.latest(db, org.id)


@autonomy_router.post("/observe")
async def observe_organization(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await organization_engine.observe(db, org.id)
    await db.commit()
    return result


@autonomy_router.get("/insights")
async def organization_insights(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from sqlalchemy import select

    from app.models.company_state import CompanyState

    state = (await awareness_engine.latest(db, org.id)).get("state") or {}
    overdue = state.get("tasks", {}).get("overdue", 0)
    usage = state.get("budget", {}).get("usage_percent", 0)
    active = state.get("projects", {}).get("active", 0)
    insights = []
    if overdue:
        insights.append({"domain": "tasks", "title": f"{overdue} overdue tasks", "detail": "Clear the backlog to protect delivery."})
    if usage >= 80:
        insights.append({"domain": "finance", "title": "Budget usage high", "detail": f"{usage}% of budget consumed."})
    if active == 0:
        insights.append({"domain": "projects", "title": "No active projects", "detail": "Consider kickoffs or archiving."})
    return {"insights": insights, "state": state}


@autonomy_router.get("/metrics")
async def organization_metrics(
    name: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await awareness_engine.metrics(db, org.id, name=name, limit=limit)
    return {"total": len(rows), "metrics": rows}


# -------------------------------------------------------------------- plans

class PlanGenerateIn(BaseModel):
    kinds: Optional[list[str]] = None


class PlanStatusIn(BaseModel):
    status: str


@autonomy_router.get("/plans")
async def list_plans(
    kind: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await planning_engine.list(db, org.id, kind=kind)


@autonomy_router.post("/plans/generate")
async def generate_plans(
    body: Optional[PlanGenerateIn] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await planning_engine.generate(
        db, org.id, kinds=body.kinds if body else None, created_by=user.id
    )
    await db.commit()
    return result


@autonomy_router.patch("/plans/{plan_id}")
async def update_plan_status(
    plan_id: str,
    body: PlanStatusIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await planning_engine.set_status(db, org.id, plan_id, body.status, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    await db.commit()
    return row


# ----------------------------------------------------------------- briefing

@briefing_router.get("")
async def latest_briefing(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await executive_briefing_engine.latest(db, org.id)


@briefing_router.post("/generate")
async def generate_briefing(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await executive_briefing_engine.generate(db, org.id)
    await db.commit()
    return result


# ------------------------------------------------------------------ decisions

class DecisionCaseIn(BaseModel):
    title: str
    question: Optional[str] = None
    category: str = "strategy"
    context: Optional[str] = None
    alternatives: Optional[list[dict[str, Any]]] = None


class DecisionDecideIn(BaseModel):
    decision: str  # approved | rejected
    outcome: Optional[str] = None
    lessons: Optional[list[str]] = None


@decision_router.get("")
async def list_decisions(
    category: Optional[str] = None,
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await decision_support_service.list(db, org.id, category=category, status=status)


@decision_router.post("")
async def create_decision_case(
    body: DecisionCaseIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await decision_support_service.create_case(
            db, org.id, title=body.title, question=body.question, category=body.category,
            context=body.context, alternatives=body.alternatives, created_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


@decision_router.get("/{decision_id}")
async def get_decision(
    decision_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await decision_support_service.get(db, org.id, decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return row


@decision_router.post("/{decision_id}/decide")
async def decide_decision(
    decision_id: str,
    body: DecisionDecideIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await decision_support_service.decide(
            db, org.id, decision_id, decision=body.decision, outcome=body.outcome,
            lessons=body.lessons, user_id=user.id,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="decision not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row
