"""Projects API — projects, roadmaps, epics, milestones, sprints (Phase 3)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.work import (
    EpicCreate,
    EpicOut,
    MilestoneCreate,
    MilestoneOut,
    ProjectCreate,
    ProjectLifecycleRequest,
    ProjectMemberOut,
    ProjectOut,
    ProjectStatsOut,
    ProjectUpdate,
    RoadmapCreate,
    RoadmapLifecycleRequest,
    RoadmapOut,
    SprintCreate,
    SprintOut,
    TimelineEntryOut,
)
from app.work.epic_service import epic_service
from app.work.intelligence_service import intelligence_service
from app.work.milestone_service import milestone_service
from app.work.project_service import project_service
from app.work.roadmap_service import roadmap_service
from app.work.sprint_service import sprint_service

router = APIRouter(tags=["Projects"])


# --------------------------------------------------------------------------- Projects

def _project_payload(p) -> dict[str, Any]:
    return {
        "id": p.id,
        "code": p.code,
        "name": p.name,
        "description": p.description,
        "status": p.status,
        "priority": p.priority,
        "progress": p.progress,
        "health": p.health,
        "owner_id": p.owner_id,
        "owner_name": getattr(p, "owner_name", None),
        "department_id": p.department_id,
        "department_name": getattr(p, "department_name", None),
        "team_id": p.team_id,
        "team_name": getattr(p, "team_name", None),
        "roadmap_id": p.roadmap_id,
        "start_date": p.start_date,
        "end_date": p.end_date,
        "budget": p.budget,
        "tags": p.tags,
        "ai_summary": p.ai_summary,
        "members_count": getattr(p, "members_count", 0),
        "tasks_count": getattr(p, "tasks_count", 0),
        "completed_count": getattr(p, "completed_count", 0),
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    status: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "updated",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    projects = await project_service.list_all(db, organization_id=org.id, status=status, search=search, sort=sort)
    return [ProjectOut.model_validate(_project_payload(p)) for p in projects]


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    data = payload.model_dump(exclude_unset=True)
    if not data.get("owner_id") and actor:
        data["owner_id"] = actor.id
    try:
        project = await project_service.create(
            db, organization_id=org.id, data=data,
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    project = await project_service.get(db, organization_id=org.id, project_id=project.id)
    return ProjectOut.model_validate(_project_payload(project))


@router.get("/projects/portfolio")
async def project_portfolio(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    """Every project with health, progress and pressure signals."""
    return await project_service.portfolio(db, organization_id=org.id)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, organization_id=org.id, project_id=project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return ProjectOut.model_validate(_project_payload(project))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, organization_id=org.id, project_id=project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        project = await project_service.update(
            db, organization_id=org.id, project=project, data=payload.model_dump(exclude_unset=True),
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    project = await project_service.get(db, organization_id=org.id, project_id=project_id)
    return ProjectOut.model_validate(_project_payload(project))


@router.delete("/projects/{project_id}", response_model=Message)
async def delete_project(
    project_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, organization_id=org.id, project_id=project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        await project_service.delete(
            db, organization_id=org.id, project=project, actor=actor, ip_address=get_client_ip(request)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return Message(message="Project deleted")


@router.post("/projects/{project_id}/lifecycle", response_model=ProjectOut)
async def project_lifecycle(
    project_id: str,
    payload: ProjectLifecycleRequest,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    project = await project_service.get(db, organization_id=org.id, project_id=project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        project = await project_service.lifecycle(
            db, organization_id=org.id, project=project, action=payload.action,
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    project = await project_service.get(db, organization_id=org.id, project_id=project_id)
    return ProjectOut.model_validate(_project_payload(project))


@router.get("/projects/{project_id}/members", response_model=list[ProjectMemberOut])
async def list_members(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, organization_id=org.id, project_id=project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return await project_service.members(db, organization_id=org.id, project_id=project_id)


@router.post("/projects/{project_id}/members", response_model=ProjectMemberOut, status_code=201)
async def add_member(
    project_id: str,
    payload: dict,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, organization_id=org.id, project_id=project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    try:
        member = await project_service.add_member(
            db, organization_id=org.id, project_id=project_id,
            employee_id=payload["employee_id"], role=payload.get("role"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    from app.models.employee import Employee

    emp = await db.get(Employee, member.employee_id)
    return ProjectMemberOut(
        id=member.id, employee_id=member.employee_id,
        name=emp.full_name if emp else "Unknown",
        designation=emp.designation if emp else None,
        avatar_url=emp.avatar_url if emp else None,
        role=member.role, joined_at=member.joined_at,
    )


@router.delete("/projects/{project_id}/members/{employee_id}", response_model=Message)
async def remove_member(
    project_id: str,
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    await project_service.remove_member(db, organization_id=org.id, project_id=project_id, employee_id=employee_id)
    await db.commit()
    return Message(message="Member removed")


@router.get("/projects/{project_id}/stats", response_model=ProjectStatsOut)
async def project_stats(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, organization_id=org.id, project_id=project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return await project_service.stats(db, organization_id=org.id, project_id=project_id)


@router.get("/projects/{project_id}/timeline", response_model=list[TimelineEntryOut])
async def project_timeline(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, organization_id=org.id, project_id=project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return await project_service.timeline(db, organization_id=org.id, project_id=project_id)


@router.get("/projects/{project_id}/health", response_model=dict)
async def project_health(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await intelligence_service.project_health(db, organization_id=org.id, project_id=project_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# --------------------------------------------------------------------------- Roadmaps

def _roadmap_payload(r) -> dict[str, Any]:
    return {
        "id": r.id, "name": r.name, "description": r.description,
        "owner_id": r.owner_id, "owner_name": getattr(r, "owner_name", None),
        "timeframe": r.timeframe, "status": r.status,
        "progress": r.progress,
        "created_at": r.created_at, "updated_at": r.updated_at,
    }


@router.get("/roadmaps", response_model=list[RoadmapOut])
async def list_roadmaps(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    return [RoadmapOut.model_validate(_roadmap_payload(r)) for r in await roadmap_service.list_all(db, organization_id=org.id)]


@router.post("/roadmaps", response_model=RoadmapOut, status_code=201)
async def create_roadmap(
    payload: RoadmapCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    roadmap = await roadmap_service.create(
        db, organization_id=org.id, data=payload.model_dump(),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return RoadmapOut.model_validate(_roadmap_payload(roadmap))


@router.get("/roadmaps/{roadmap_id}", response_model=RoadmapOut)
async def get_roadmap(
    roadmap_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    roadmap = await roadmap_service.get(db, organization_id=org.id, roadmap_id=roadmap_id)
    if roadmap is None:
        raise HTTPException(404, "Roadmap not found")
    return RoadmapOut.model_validate(_roadmap_payload(roadmap))


@router.patch("/roadmaps/{roadmap_id}", response_model=RoadmapOut)
async def update_roadmap(
    roadmap_id: str,
    payload: dict,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    roadmap = await roadmap_service.get(db, organization_id=org.id, roadmap_id=roadmap_id)
    if roadmap is None:
        raise HTTPException(404, "Roadmap not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        roadmap = await roadmap_service.update(
            db, organization_id=org.id, roadmap=roadmap, data=payload,
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return RoadmapOut.model_validate(_roadmap_payload(roadmap))


@router.delete("/roadmaps/{roadmap_id}", response_model=Message)
async def delete_roadmap(
    roadmap_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    roadmap = await roadmap_service.get(db, organization_id=org.id, roadmap_id=roadmap_id)
    if roadmap is None:
        raise HTTPException(404, "Roadmap not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        await roadmap_service.delete(
            db, organization_id=org.id, roadmap=roadmap, actor=actor, ip_address=get_client_ip(request)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return Message(message="Roadmap deleted")


@router.get("/roadmaps/{roadmap_id}/detail")
async def roadmap_detail(
    roadmap_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    detail = await roadmap_service.detail(db, organization_id=org.id, roadmap_id=roadmap_id)
    if detail is None:
        raise HTTPException(404, "Roadmap not found")
    return detail


@router.post("/roadmaps/{roadmap_id}/lifecycle", response_model=RoadmapOut)
async def roadmap_lifecycle(
    roadmap_id: str,
    payload: RoadmapLifecycleRequest,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    roadmap = await roadmap_service.get(db, organization_id=org.id, roadmap_id=roadmap_id)
    if roadmap is None:
        raise HTTPException(404, "Roadmap not found")
    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        roadmap = await roadmap_service.lifecycle(
            db, organization_id=org.id, roadmap=roadmap, action=payload.action,
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    hydrated = next(
        (r for r in await roadmap_service.list_all(db, organization_id=org.id) if r.id == roadmap_id),
        None,
    )
    return RoadmapOut.model_validate(_roadmap_payload(hydrated))


# --------------------------------------------------------------------------- Epics

@router.get("/epics", response_model=list[EpicOut])
async def list_epics(
    project_id: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    epics = await epic_service.list_all(db, organization_id=org.id, project_id=project_id)
    return [EpicOut.model_validate(e) for e in epics]


@router.post("/epics", response_model=EpicOut, status_code=201)
async def create_epic(
    payload: EpicCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    epic = await epic_service.create(
        db, organization_id=org.id, data=payload.model_dump(),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return EpicOut.model_validate(epic)


@router.get("/epics/{epic_id}", response_model=EpicOut)
async def get_epic(
    epic_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    epic = await epic_service.get(db, organization_id=org.id, epic_id=epic_id)
    if epic is None:
        raise HTTPException(404, "Epic not found")
    return EpicOut.model_validate(epic)


@router.patch("/epics/{epic_id}", response_model=EpicOut)
async def update_epic(
    epic_id: str,
    payload: dict,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    epic = await epic_service.get(db, organization_id=org.id, epic_id=epic_id)
    if epic is None:
        raise HTTPException(404, "Epic not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        epic = await epic_service.update(
            db, organization_id=org.id, epic=epic, data=payload,
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return EpicOut.model_validate(epic)


@router.delete("/epics/{epic_id}", response_model=Message)
async def delete_epic(
    epic_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    epic = await epic_service.get(db, organization_id=org.id, epic_id=epic_id)
    if epic is None:
        raise HTTPException(404, "Epic not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        await epic_service.delete(
            db, organization_id=org.id, epic=epic, actor=actor, ip_address=get_client_ip(request)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return Message(message="Epic deleted")


@router.post("/epics/{epic_id}/start", response_model=EpicOut)
async def start_epic(
    epic_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    epic = await epic_service.get(db, organization_id=org.id, epic_id=epic_id)
    if epic is None:
        raise HTTPException(404, "Epic not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        epic = await epic_service.start(
            db, organization_id=org.id, epic=epic, actor=actor, ip_address=get_client_ip(request)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return EpicOut.model_validate(epic)


@router.post("/epics/{epic_id}/complete", response_model=EpicOut)
async def complete_epic(
    epic_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    epic = await epic_service.get(db, organization_id=org.id, epic_id=epic_id)
    if epic is None:
        raise HTTPException(404, "Epic not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        epic = await epic_service.complete(
            db, organization_id=org.id, epic=epic, actor=actor, ip_address=get_client_ip(request)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return EpicOut.model_validate(epic)


# --------------------------------------------------------------------------- Milestones

@router.get("/milestones", response_model=list[MilestoneOut])
async def list_milestones(
    project_id: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    return [MilestoneOut.model_validate(m) for m in await milestone_service.list_all(db, organization_id=org.id, project_id=project_id)]


@router.post("/milestones", response_model=MilestoneOut, status_code=201)
async def create_milestone(
    payload: MilestoneCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    milestone = await milestone_service.create(
        db, organization_id=org.id, data=payload.model_dump(),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return MilestoneOut.model_validate(milestone)


@router.get("/milestones/{milestone_id}", response_model=MilestoneOut)
async def get_milestone(
    milestone_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    milestone = await milestone_service.get(db, organization_id=org.id, milestone_id=milestone_id)
    if milestone is None:
        raise HTTPException(404, "Milestone not found")
    return MilestoneOut.model_validate(milestone)


@router.patch("/milestones/{milestone_id}", response_model=MilestoneOut)
async def update_milestone(
    milestone_id: str,
    payload: dict,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    milestone = await milestone_service.get(db, organization_id=org.id, milestone_id=milestone_id)
    if milestone is None:
        raise HTTPException(404, "Milestone not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        milestone = await milestone_service.update(
            db, organization_id=org.id, milestone=milestone, data=payload,
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return MilestoneOut.model_validate(milestone)


@router.post("/milestones/{milestone_id}/complete", response_model=MilestoneOut)
async def complete_milestone(
    milestone_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    milestone = await milestone_service.get(db, organization_id=org.id, milestone_id=milestone_id)
    if milestone is None:
        raise HTTPException(404, "Milestone not found")
    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        milestone = await milestone_service.complete(db, organization_id=org.id, milestone=milestone, actor=actor)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return MilestoneOut.model_validate(milestone)


@router.delete("/milestones/{milestone_id}", response_model=Message)
async def delete_milestone(
    milestone_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    milestone = await milestone_service.get(db, organization_id=org.id, milestone_id=milestone_id)
    if milestone is None:
        raise HTTPException(404, "Milestone not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        await milestone_service.delete(
            db, organization_id=org.id, milestone=milestone, actor=actor, ip_address=get_client_ip(request)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return Message(message="Milestone deleted")


# --------------------------------------------------------------------------- Sprints

@router.get("/sprints", response_model=list[SprintOut])
async def list_sprints(
    project_id: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    return [SprintOut.model_validate(s) for s in await sprint_service.list_all(db, organization_id=org.id, project_id=project_id)]


@router.post("/sprints", response_model=SprintOut, status_code=201)
async def create_sprint(
    payload: SprintCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    sprint = await sprint_service.create(
        db, organization_id=org.id, data=payload.model_dump(),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return SprintOut.model_validate(sprint)


@router.get("/sprints/{sprint_id}", response_model=SprintOut)
async def get_sprint(
    sprint_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:read")),
    db: AsyncSession = Depends(get_db),
):
    sprint = await sprint_service.get(db, organization_id=org.id, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(404, "Sprint not found")
    return SprintOut.model_validate(sprint)


@router.patch("/sprints/{sprint_id}", response_model=SprintOut)
async def update_sprint(
    sprint_id: str,
    payload: dict,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    sprint = await sprint_service.get(db, organization_id=org.id, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(404, "Sprint not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        sprint = await sprint_service.update(
            db, organization_id=org.id, sprint=sprint, data=payload,
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return SprintOut.model_validate(sprint)


@router.post("/sprints/{sprint_id}/start", response_model=SprintOut)
async def start_sprint(
    sprint_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    sprint = await sprint_service.get(db, organization_id=org.id, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(404, "Sprint not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        sprint = await sprint_service.start(
            db, organization_id=org.id, sprint=sprint, actor=actor, ip_address=get_client_ip(request)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    sprint = await sprint_service.get(db, organization_id=org.id, sprint_id=sprint_id)
    return SprintOut.model_validate(sprint)


@router.post("/sprints/{sprint_id}/complete", response_model=SprintOut)
async def complete_sprint(
    sprint_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    sprint = await sprint_service.get(db, organization_id=org.id, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(404, "Sprint not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        sprint = await sprint_service.complete(
            db, organization_id=org.id, sprint=sprint, actor=actor, ip_address=get_client_ip(request)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    sprint = await sprint_service.get(db, organization_id=org.id, sprint_id=sprint_id)
    return SprintOut.model_validate(sprint)


@router.delete("/sprints/{sprint_id}", response_model=Message)
async def delete_sprint(
    sprint_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
):
    sprint = await sprint_service.get(db, organization_id=org.id, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(404, "Sprint not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        await sprint_service.delete(
            db, organization_id=org.id, sprint=sprint, actor=actor, ip_address=get_client_ip(request)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return Message(message="Sprint deleted")
