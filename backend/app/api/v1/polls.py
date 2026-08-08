"""Polls API (Phase 5.10)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.communication.poll_service import poll_service
from app.communication.presenters import _names, _community_names, present_poll
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.communication import PollCreate, PollUpdate, PollVotePayload

router = APIRouter(prefix="/polls", tags=["Polls"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


async def _require_poll(db: AsyncSession, org: Organization, poll_id: str):
    poll = await poll_service.get(db, organization_id=org.id, poll_id=poll_id)
    if poll is None:
        raise HTTPException(404, "Poll not found")
    return poll


async def _present(db: AsyncSession, org: Organization, user: User, poll):
    actor = await _actor(db, org, user)
    options = await poll_service.options(db, organization_id=org.id, poll_id=poll.id)
    creator_names = await _names(db, [poll.created_by] if poll.created_by else [])
    community_names = await _community_names(db, [poll.community_id] if poll.community_id else [])
    my_choices: list[str] = []
    if actor:
        my_choices = await poll_service.my_vote_ids(db, organization_id=org.id, poll_id=poll.id, employee_id=actor.id)
    return await present_poll(
        poll,
        creator_name=creator_names.get(poll.created_by) if poll.created_by else None,
        community_name=community_names.get(poll.community_id) if poll.community_id else None,
        options=[
            {"id": o.id, "poll_id": o.poll_id, "text": o.text, "sort_order": o.sort_order, "vote_count": o.vote_count}
            for o in options
        ],
        voted=len(my_choices) > 0,
        my_choices=my_choices,
    )


@router.get("", response_model=list[dict])
async def list_polls(
    status: Optional[str] = None,
    community_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    polls = await poll_service.list_all(
        db,
        organization_id=org.id,
        status=status,
        community_id=community_id,
        limit=min(limit, 500),
        offset=offset,
    )
    return [await _present(db, org, user, poll) for poll in polls]


@router.post("", response_model=dict, status_code=201)
async def create_poll(
    payload: PollCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    poll = await poll_service.create(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True), actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present(db, org, user, poll)


@router.get("/{poll_id}", response_model=dict)
async def get_poll(
    poll_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    poll = await _require_poll(db, org, poll_id)
    return await _present(db, org, user, poll)


@router.patch("/{poll_id}", response_model=dict)
async def update_poll(
    poll_id: str,
    payload: PollUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    poll = await _require_poll(db, org, poll_id)
    actor = await _actor(db, org, user)
    if actor is None or poll.created_by != actor.id:
        raise HTTPException(403, "Only the creator can edit this poll")
    poll = await poll_service.update(
        db, organization_id=org.id, poll_id=poll_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present(db, org, user, poll)


@router.delete("/{poll_id}", response_model=Message)
async def delete_poll(
    poll_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    poll = await _require_poll(db, org, poll_id)
    actor = await _actor(db, org, user)
    if actor is None or poll.created_by != actor.id:
        raise HTTPException(403, "Only the creator can delete this poll")
    await poll_service.delete(
        db, organization_id=org.id, poll_id=poll_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Poll deleted")


@router.post("/{poll_id}/vote", response_model=dict)
async def vote_poll(
    poll_id: str,
    payload: PollVotePayload,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_poll(db, org, poll_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    try:
        result = await poll_service.vote(
            db, organization_id=org.id, poll_id=poll_id, option_ids=payload.option_ids, actor=actor
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return result


@router.get("/{poll_id}/results", response_model=dict)
async def poll_results(
    poll_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_poll(db, org, poll_id)
    try:
        return await poll_service.results(db, organization_id=org.id, poll_id=poll_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
