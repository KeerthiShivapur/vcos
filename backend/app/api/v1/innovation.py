"""Innovation hub API (Phase 5.9)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.communication.innovation_service import innovation_service
from app.communication.presenters import _names, present_idea
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.communication import IdeaCreate, IdeaStatusPayload, IdeaUpdate, PromotePayload

router = APIRouter(prefix="/innovation", tags=["Innovation"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


async def _require_idea(db: AsyncSession, org: Organization, idea_id: str):
    idea = await innovation_service.get(db, organization_id=org.id, idea_id=idea_id)
    if idea is None:
        raise HTTPException(404, "Idea not found")
    return idea


async def _present(db: AsyncSession, org: Organization, user: User, idea):
    actor = await _actor(db, org, user)
    names = await _names(db, [idea.author_id] if idea.author_id else [])
    voted = False
    if actor:
        voted = await innovation_service.my_vote(db, organization_id=org.id, idea_id=idea.id, employee_id=actor.id)
    return await present_idea(
        idea,
        author_name=names.get(idea.author_id) if idea.author_id else None,
        voted=voted,
    )


@router.get("", response_model=list[dict])
async def list_ideas(
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    ideas = await innovation_service.list_all(
        db,
        organization_id=org.id,
        status=status,
        search=search,
        limit=min(limit, 500),
        offset=offset,
    )
    return [await _present(db, org, user, idea) for idea in ideas]


@router.get("/stats", response_model=dict)
async def idea_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    return await innovation_service.stats(db, organization_id=org.id)


@router.post("", response_model=dict, status_code=201)
async def create_idea(
    payload: IdeaCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    idea = await innovation_service.create(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True), actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present(db, org, user, idea)


@router.get("/{idea_id}", response_model=dict)
async def get_idea(
    idea_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    idea = await _require_idea(db, org, idea_id)
    return await _present(db, org, user, idea)


@router.patch("/{idea_id}", response_model=dict)
async def update_idea(
    idea_id: str,
    payload: IdeaUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    idea = await _require_idea(db, org, idea_id)
    actor = await _actor(db, org, user)
    if actor is None or idea.author_id != actor.id:
        raise HTTPException(403, "Only the author can edit this idea")
    idea = await innovation_service.update(
        db, organization_id=org.id, idea_id=idea_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present(db, org, user, idea)


@router.delete("/{idea_id}", response_model=Message)
async def delete_idea(
    idea_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    idea = await _require_idea(db, org, idea_id)
    actor = await _actor(db, org, user)
    if actor is None or idea.author_id != actor.id:
        raise HTTPException(403, "Only the author can delete this idea")
    await innovation_service.delete(
        db, organization_id=org.id, idea_id=idea_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Idea deleted")


@router.post("/{idea_id}/vote", response_model=dict)
async def vote_idea(
    idea_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_idea(db, org, idea_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    result = await innovation_service.vote(db, organization_id=org.id, idea_id=idea_id, actor=actor)
    await db.commit()
    return result


@router.patch("/{idea_id}/status", response_model=dict)
async def update_idea_status(
    idea_id: str,
    payload: IdeaStatusPayload,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_idea(db, org, idea_id)
    actor = await _actor(db, org, user)
    idea = await innovation_service.update_status(
        db, organization_id=org.id, idea_id=idea_id, status=payload.status, feedback=payload.feedback,
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present(db, org, user, idea)


@router.post("/{idea_id}/promote", response_model=dict)
async def promote_idea(
    idea_id: str,
    payload: Optional[PromotePayload] = None,
    request: Request = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_idea(db, org, idea_id)
    actor = await _actor(db, org, user)
    idea = await innovation_service.promote_to_project(
        db, organization_id=org.id, idea_id=idea_id,
        project_id=payload.project_id if payload else None, actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present(db, org, user, idea)
