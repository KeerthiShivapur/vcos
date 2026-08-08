"""Forums API — Q&A threads, replies, votes (Phase 5.6)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.communication.forum_service import forum_service
from app.communication.presenters import _names, present_reply, present_thread
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.communication import (
    ForumReplyCreate,
    ForumReplyUpdate,
    ForumThreadCreate,
    ForumThreadUpdate,
    ForumVotePayload,
)

router = APIRouter(prefix="/forums", tags=["Forums"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


async def _require_thread(db: AsyncSession, org: Organization, thread_id: str):
    thread = await forum_service.get_thread(db, organization_id=org.id, thread_id=thread_id)
    if thread is None:
        raise HTTPException(404, "Thread not found")
    return thread


async def _present_thread(db: AsyncSession, org: Organization, user: User, thread):
    actor = await _actor(db, org, user)
    names = await _names(db, [thread.author_id] if thread.author_id else [])
    my_vote = None
    if actor:
        my_vote = await forum_service.my_vote(
            db, organization_id=org.id, target_type="thread", target_id=thread.id, employee_id=actor.id
        )
    return await present_thread(
        thread,
        author_name=names.get(thread.author_id) if thread.author_id else None,
        my_vote=my_vote,
    )


async def _present_reply(db: AsyncSession, org: Organization, user: User, reply):
    actor = await _actor(db, org, user)
    names = await _names(db, [reply.author_id] if reply.author_id else [])
    my_vote = None
    if actor:
        my_vote = await forum_service.my_vote(
            db, organization_id=org.id, target_type="reply", target_id=reply.id, employee_id=actor.id
        )
    return await present_reply(
        reply,
        author_name=names.get(reply.author_id) if reply.author_id else None,
        my_vote=my_vote,
    )


@router.get("/categories", response_model=list[dict])
async def list_categories(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    return await forum_service.categories(db, organization_id=org.id)


@router.get("", response_model=list[dict])
async def list_threads(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    threads = await forum_service.list_threads(
        db,
        organization_id=org.id,
        category=category,
        status=status,
        search=search,
        tag=tag,
        limit=min(limit, 500),
        offset=offset,
    )
    return [await _present_thread(db, org, user, t) for t in threads]


@router.post("", response_model=dict, status_code=201)
async def create_thread(
    payload: ForumThreadCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    thread = await forum_service.create_thread(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True), actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present_thread(db, org, user, thread)


@router.get("/{thread_id}", response_model=dict)
async def get_thread(
    thread_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_thread(db, org, thread_id)
    thread = await forum_service.get_thread(db, organization_id=org.id, thread_id=thread_id)
    return await _present_thread(db, org, user, thread)


@router.patch("/{thread_id}", response_model=dict)
async def update_thread(
    thread_id: str,
    payload: ForumThreadUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    thread = await _require_thread(db, org, thread_id)
    actor = await _actor(db, org, user)
    if actor is None or thread.author_id != actor.id:
        raise HTTPException(403, "Only the author can edit this thread")
    thread = await forum_service.update_thread(
        db, organization_id=org.id, thread_id=thread_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present_thread(db, org, user, thread)


@router.delete("/{thread_id}", response_model=Message)
async def delete_thread(
    thread_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    thread = await _require_thread(db, org, thread_id)
    actor = await _actor(db, org, user)
    if actor is None or thread.author_id != actor.id:
        raise HTTPException(403, "Only the author can delete this thread")
    await forum_service.delete_thread(
        db, organization_id=org.id, thread_id=thread_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Thread deleted")


@router.post("/{thread_id}/view", response_model=dict)
async def register_view(
    thread_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_thread(db, org, thread_id)
    await forum_service.register_view(db, organization_id=org.id, thread_id=thread_id)
    await db.commit()
    return {"viewed": True}


@router.post("/{thread_id}/pin", response_model=dict)
async def pin_thread(
    thread_id: str,
    request: Request,
    pinned: bool = True,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_thread(db, org, thread_id)
    thread = await forum_service.toggle_pin(db, organization_id=org.id, thread_id=thread_id, pinned=pinned)
    await db.commit()
    return {"is_pinned": thread.is_pinned}


@router.post("/{thread_id}/vote", response_model=dict)
async def vote_thread(
    thread_id: str,
    payload: ForumVotePayload,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_thread(db, org, thread_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    try:
        result = await forum_service.vote(
            db, organization_id=org.id, target_type="thread", target_id=thread_id, value=payload.value, actor=actor
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return result


@router.post("/{thread_id}/accept", response_model=dict)
async def accept_answer(
    thread_id: str,
    request: Request,
    reply_id: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    thread = await _require_thread(db, org, thread_id)
    actor = await _actor(db, org, user)
    if actor is None or thread.author_id != actor.id:
        raise HTTPException(403, "Only the thread author can accept an answer")
    thread = await forum_service.accept_answer(
        db, organization_id=org.id, thread_id=thread_id, reply_id=reply_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return {"accepted_reply_id": thread.accepted_reply_id, "is_resolved": thread.is_resolved}


# ------------------------------------------------------------- replies

@router.get("/{thread_id}/replies", response_model=list[dict])
async def list_replies(
    thread_id: str,
    limit: int = 300,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_thread(db, org, thread_id)
    replies = await forum_service.list_replies(
        db, organization_id=org.id, thread_id=thread_id, limit=min(limit, 1000), offset=offset
    )
    return [await _present_reply(db, org, user, r) for r in replies]


@router.post("/{thread_id}/replies", response_model=dict, status_code=201)
async def add_reply(
    thread_id: str,
    payload: ForumReplyCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_thread(db, org, thread_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    reply = await forum_service.add_reply(
        db, organization_id=org.id, thread_id=thread_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present_reply(db, org, user, reply)


@router.patch("/{thread_id}/replies/{reply_id}", response_model=dict)
async def update_reply(
    thread_id: str,
    reply_id: str,
    payload: ForumReplyUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_thread(db, org, thread_id)
    actor = await _actor(db, org, user)
    reply = await forum_service.get_reply(db, organization_id=org.id, reply_id=reply_id)
    if reply is None:
        raise HTTPException(404, "Reply not found")
    if actor is None or reply.author_id != actor.id:
        raise HTTPException(403, "Only the author can edit this reply")
    reply = await forum_service.update_reply(
        db, organization_id=org.id, reply_id=reply_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present_reply(db, org, user, reply)


@router.delete("/{thread_id}/replies/{reply_id}", response_model=Message)
async def delete_reply(
    thread_id: str,
    reply_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_thread(db, org, thread_id)
    actor = await _actor(db, org, user)
    reply = await forum_service.get_reply(db, organization_id=org.id, reply_id=reply_id)
    if reply is None:
        raise HTTPException(404, "Reply not found")
    if actor is None or reply.author_id != actor.id:
        raise HTTPException(403, "Only the author can delete this reply")
    await forum_service.delete_reply(
        db, organization_id=org.id, reply_id=reply_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Reply deleted")


@router.post("/{thread_id}/replies/{reply_id}/vote", response_model=dict)
async def vote_reply(
    thread_id: str,
    reply_id: str,
    payload: ForumVotePayload,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_thread(db, org, thread_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    try:
        result = await forum_service.vote(
            db, organization_id=org.id, target_type="reply", target_id=reply_id, value=payload.value, actor=actor
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return result
