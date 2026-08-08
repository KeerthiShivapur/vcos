"""Phase 8.4/8.15/8.16 — Strategy & Executive AI Assistant API."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.executive.strategy_service import strategy_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/executive/strategy", tags=["executive"])


@router.get("/goals")
async def list_goals(
    focus: Optional[str] = Query(default=None, pattern="^(growth|retention|innovation|efficiency|expansion|learning)$"),
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await strategy_service.list_goals(
        db, organization_id=org.id, focus=focus, status=status
    )


class GoalIn(BaseModel):
    name: str
    description: Optional[str] = None
    timeframe: str = "quarter"
    status: str = "planned"
    progress: float = 0.0
    priority: str = "medium"
    focus: str = "growth"
    links: dict[str, Any] = {}


@router.post("/goals", status_code=201)
async def create_goal(
    payload: GoalIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from app.people.employee_service import employee_service

    owner = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    goal = await strategy_service.create_goal(
        db, organization_id=org.id, payload=payload.model_dump(),
        owner_id=owner.id if owner else None,
    )
    await db.commit()
    return goal


class GoalUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    timeframe: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[float] = None
    priority: Optional[str] = None
    focus: Optional[str] = None


@router.patch("/goals/{goal_id}")
async def update_goal(
    goal_id: str,
    payload: GoalUpdateIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = await strategy_service.update_goal(
            db, organization_id=org.id, goal_id=goal_id, payload=payload.model_dump(exclude_none=True)
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    await db.commit()
    return result


@router.post("/plan")
async def strategy_plan(
    horizon: str = Query(default="quarter", pattern="^(quarter|half|year)$"),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await strategy_service.plan(db, organization_id=org.id, horizon=horizon)


class AskIn(BaseModel):
    question: str


@router.post("/ask")
async def strategy_ask(
    payload: AskIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not payload.question.strip():
        raise HTTPException(422, "question is required")
    return await strategy_service.ask(
        db, organization_id=org.id, user_id=user.id, question=payload.question
    )
