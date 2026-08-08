"""AI planning endpoints (Phase 7.9)."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.planning import planning_engine
from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai/plan", tags=["ai"])


class PlanIn(BaseModel):
    plan_type: str = "daily"


@router.post("")
async def create_plan(
    payload: PlanIn,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if payload.plan_type not in ("daily", "weekly"):
        raise HTTPException(status_code=422, detail="plan_type must be daily or weekly")
    try:
        plan = await planning_engine.plan(
            db, organization_id=org.id, user=user, plan_type=payload.plan_type
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    return plan


@router.get("/latest")
async def latest_plan(
    plan_type: str = "daily",
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    plan = await planning_engine.latest(
        db, organization_id=org.id, user=user, plan_type=plan_type
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="no plan yet")
    return plan
