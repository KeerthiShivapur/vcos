"""Goals API — OKRs with key results (Phase 3)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.work import GoalCreate, GoalOut, GoalUpdate, KeyResultCreate, KeyResultOut, KeyResultUpdate
from app.work.goal_service import goal_service

router = APIRouter(prefix="/goals", tags=["Goals"])


def _goal_payload(g) -> dict:
    return {
        "id": g.id,
        "parent_goal_id": g.parent_goal_id,
        "parent_name": getattr(g, "parent_name", None),
        "name": g.name,
        "description": g.description,
        "scope": g.scope,
        "owner_id": g.owner_id,
        "owner_name": getattr(g, "owner_name", None),
        "department_id": g.department_id,
        "team_id": g.team_id,
        "project_id": g.project_id,
        "status": g.status,
        "progress": g.progress or 0,
        "priority": g.priority,
        "start_date": g.start_date,
        "end_date": g.end_date,
        "key_results_count": getattr(g, "key_results_count", 0),
        "created_at": g.created_at,
        "updated_at": g.updated_at,
    }


@router.get("", response_model=list[GoalOut])
async def list_goals(
    scope: Optional[str] = None,
    status: Optional[str] = None,
    owner_id: Optional[str] = None,
    team_id: Optional[str] = None,
    search: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("goals:read")),
    db: AsyncSession = Depends(get_db),
):
    goals = await goal_service.list_all(
        db, organization_id=org.id, scope=scope, status=status,
        owner_id=owner_id, team_id=team_id, search=search,
    )
    return [GoalOut.model_validate(_goal_payload(g)) for g in goals]


@router.post("", response_model=GoalOut, status_code=201)
async def create_goal(
    payload: GoalCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("goals:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    data = payload.model_dump(exclude_unset=True)
    if "key_results" in data:
        data["key_results"] = [kr.model_dump() if hasattr(kr, "model_dump") else kr for kr in data["key_results"]]
    try:
        goal = await goal_service.create(
            db, organization_id=org.id, data=data, actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    goal = await goal_service.get(db, organization_id=org.id, goal_id=goal.id)
    return GoalOut.model_validate(_goal_payload(goal))


@router.get("/{goal_id}", response_model=GoalOut)
async def get_goal(
    goal_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("goals:read")),
    db: AsyncSession = Depends(get_db),
):
    goal = await goal_service.get(db, organization_id=org.id, goal_id=goal_id)
    if goal is None:
        raise HTTPException(404, "Goal not found")
    return GoalOut.model_validate(_goal_payload(goal))


@router.patch("/{goal_id}", response_model=GoalOut)
async def update_goal(
    goal_id: str,
    payload: GoalUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("goals:manage")),
    db: AsyncSession = Depends(get_db),
):
    goal = await goal_service.get(db, organization_id=org.id, goal_id=goal_id)
    if goal is None:
        raise HTTPException(404, "Goal not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        goal = await goal_service.update(
            db, organization_id=org.id, goal=goal,
            data=payload.model_dump(exclude_unset=True), actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    goal = await goal_service.get(db, organization_id=org.id, goal_id=goal_id)
    return GoalOut.model_validate(_goal_payload(goal))


@router.delete("/{goal_id}", response_model=Message)
async def delete_goal(
    goal_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("goals:manage")),
    db: AsyncSession = Depends(get_db),
):
    goal = await goal_service.get(db, organization_id=org.id, goal_id=goal_id)
    if goal is None:
        raise HTTPException(404, "Goal not found")
    await goal_service.delete(db, organization_id=org.id, goal=goal)
    await db.commit()
    return Message(message="Goal deleted")


# --------------------------------------------------------------------------- Key results

@router.get("/{goal_id}/key-results", response_model=list[KeyResultOut])
async def list_key_results(
    goal_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("goals:read")),
    db: AsyncSession = Depends(get_db),
):
    goal = await goal_service.get(db, organization_id=org.id, goal_id=goal_id)
    if goal is None:
        raise HTTPException(404, "Goal not found")
    return await goal_service.key_results(db, organization_id=org.id, goal_id=goal_id)


@router.post("/{goal_id}/key-results", response_model=KeyResultOut, status_code=201)
async def add_key_result(
    goal_id: str,
    payload: KeyResultCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("goals:manage")),
    db: AsyncSession = Depends(get_db),
):
    goal = await goal_service.get(db, organization_id=org.id, goal_id=goal_id)
    if goal is None:
        raise HTTPException(404, "Goal not found")
    try:
        kr = await goal_service.add_key_result(
            db, organization_id=org.id, goal_id=goal_id, data=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return await goal_service._fetch_kr(db, kr.id)


@router.patch("/{goal_id}/key-results/{kr_id}", response_model=KeyResultOut)
async def update_key_result(
    goal_id: str,
    kr_id: str,
    payload: KeyResultUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("goals:manage")),
    db: AsyncSession = Depends(get_db),
):
    goal = await goal_service.get(db, organization_id=org.id, goal_id=goal_id)
    if goal is None:
        raise HTTPException(404, "Goal not found")
    kr = await goal_service.get_kr(db, organization_id=org.id, kr_id=kr_id)
    if kr is None:
        raise HTTPException(404, "Key result not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    kr = await goal_service.update_key_result(
        db, organization_id=org.id, goal_id=goal_id, kr=kr,
        data=payload.model_dump(exclude_unset=True), actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await goal_service._fetch_kr(db, kr.id)


@router.delete("/{goal_id}/key-results/{kr_id}", response_model=Message)
async def delete_key_result(
    goal_id: str,
    kr_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("goals:manage")),
    db: AsyncSession = Depends(get_db),
):
    goal = await goal_service.get(db, organization_id=org.id, goal_id=goal_id)
    if goal is None:
        raise HTTPException(404, "Goal not found")
    kr = await goal_service.get_kr(db, organization_id=org.id, kr_id=kr_id)
    if kr is None:
        raise HTTPException(404, "Key result not found")
    await goal_service.delete_key_result(db, organization_id=org.id, kr=kr)
    await db.commit()
    return Message(message="Key result deleted")
