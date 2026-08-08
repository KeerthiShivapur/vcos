"""Teams API — teams, cross-functional members, goals (Phase 2)."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.people.employee_service import employee_service
from app.people.team_service import team_service
from app.schemas.common import Message
from app.schemas.people import TeamCreate, TeamMemberOut, TeamOut, TeamUpdate

router = APIRouter(prefix="/teams", tags=["Teams"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


def _team_payload(team) -> dict[str, Any]:
    return {
        "id": team.id,
        "name": team.name,
        "code": team.code,
        "description": team.description,
        "department_id": team.department_id,
        "department_name": getattr(team, "department_name", None),
        "lead_id": team.lead_id,
        "lead_name": getattr(team, "lead_name", None),
        "members_count": getattr(team, "members_count", 0),
        "members": getattr(team, "_member_rows", []),
    }


@router.get("", response_model=list[TeamOut])
async def list_teams(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("team:read")),
    db: AsyncSession = Depends(get_db),
):
    teams = await team_service.list(db, organization_id=org.id)
    return [TeamOut.model_validate(_team_payload(t)) for t in teams]


@router.post("", response_model=TeamOut, status_code=201)
async def create_team(
    payload: TeamCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("team:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    try:
        team = await team_service.create(
            db, organization_id=org.id, data=payload.model_dump(), actor=actor,
            ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    team = await team_service.get(db, organization_id=org.id, team_id=team.id)
    return TeamOut.model_validate(_team_payload(team))


@router.get("/{team_id}", response_model=TeamOut)
async def get_team(
    team_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("team:read")),
    db: AsyncSession = Depends(get_db),
):
    team = await team_service.get(db, organization_id=org.id, team_id=team_id)
    if team is None:
        raise HTTPException(404, "Team not found")
    return TeamOut.model_validate(_team_payload(team))


@router.patch("/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: str,
    payload: TeamUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("team:manage")),
    db: AsyncSession = Depends(get_db),
):
    team = await team_service.get(db, organization_id=org.id, team_id=team_id)
    if team is None:
        raise HTTPException(404, "Team not found")
    actor = await _actor(db, org, user)
    try:
        team = await team_service.update(
            db, organization_id=org.id, team=team, data=payload.model_dump(exclude_unset=True),
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    team = await team_service.get(db, organization_id=org.id, team_id=team_id)
    return TeamOut.model_validate(_team_payload(team))


@router.post("/{team_id}/members", response_model=TeamMemberOut, status_code=201)
async def add_member(
    team_id: str,
    payload: dict,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("team:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        member = await team_service.add_member(
            db, organization_id=org.id, team_id=team_id,
            employee_id=payload["employee_id"], role=payload.get("role"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    from app.models.employee import Employee

    emp = await db.get(Employee, member.employee_id)
    return TeamMemberOut(
        id=member.id,
        employee_id=member.employee_id,
        employee_name=emp.full_name if emp else "Unknown",
        designation=emp.designation if emp else None,
        avatar_url=emp.avatar_url if emp else None,
        role=member.role,
        joined_at=member.joined_at,
        is_primary=False,
    )


@router.delete("/{team_id}/members/{employee_id}", response_model=Message)
async def remove_member(
    team_id: str,
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("team:manage")),
    db: AsyncSession = Depends(get_db),
):
    await team_service.remove_member(db, organization_id=org.id, team_id=team_id, employee_id=employee_id)
    await db.commit()
    return Message(message="Member removed")


@router.post("/{team_id}/goals", response_model=dict)
async def add_goal(
    team_id: str,
    payload: dict,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("team:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        goal = await team_service.add_goal(
            db, organization_id=org.id, team_id=team_id,
            title=payload["title"], status=payload.get("status", "planned"), meta=payload.get("meta"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return {"id": goal.id, "team_id": goal.team_id, "title": goal.title, "status": goal.status}


@router.get("/{team_id}/goals", response_model=list[dict])
async def list_goals(
    team_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("team:read")),
    db: AsyncSession = Depends(get_db),
):
    goals = await team_service.list_goals(db, organization_id=org.id, team_id=team_id)
    return [
        {"id": g.id, "team_id": g.team_id, "title": g.title, "status": g.status,
         "meta": g.meta, "created_at": g.created_at}
        for g in goals
    ]
