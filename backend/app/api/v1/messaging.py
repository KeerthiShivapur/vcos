"""Messaging API — conversations, DMs, messages, reactions, receipts (Phase 5.17)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.communication.message_service import message_service
from app.communication.presenters import _names, present_conversation, present_message
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message as ApiMessage
from app.schemas.communication import (
    ConversationCreate,
    ConversationMemberPayload,
    MessageCreate,
    MessageUpdate,
    ReactionPayload,
)

router = APIRouter(tags=["Messaging"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


async def _require_membership(db: AsyncSession, org: Organization, conversation_id: str, employee_id: str):
    conversation = await message_service.get_conversation(db, organization_id=org.id, conversation_id=conversation_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    members = await message_service.members(db, organization_id=org.id, conversation_id=conversation_id)
    if not any(m.employee_id == employee_id for m in members):
        raise HTTPException(403, "Not a member of this conversation")
    return conversation


async def _present_conversation(db: AsyncSession, org: Organization, employee_id: str, conversation):
    members = await message_service.members(db, organization_id=org.id, conversation_id=conversation.id)
    unread = {row["conversation_id"]: row["unread"] for row in await message_service.unread_counts(db, organization_id=org.id, employee_id=employee_id)}
    return await present_conversation(
        conversation,
        member_count=len(members),
        unread_count=unread.get(conversation.id, 0),
    )


# ------------------------------------------------------------- conversations

@router.get("/conversations", response_model=list[dict])
async def list_conversations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        return []
    conversations = await message_service.list_conversations(db, organization_id=org.id, employee_id=actor.id)
    return [await _present_conversation(db, org, actor.id, c) for c in conversations]


@router.post("/conversations", response_model=dict, status_code=201)
async def create_conversation(
    payload: ConversationCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    conversation = await message_service.create_conversation(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True), actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present_conversation(db, org, actor.id, conversation)


@router.post("/dms/{employee_id}", response_model=dict)
async def open_dm(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    if employee_id == actor.id:
        raise HTTPException(400, "Cannot DM yourself")
    conversation = await message_service.find_or_create_dm(
        db, organization_id=org.id, other_employee_id=employee_id, actor=actor
    )
    await db.commit()
    return await _present_conversation(db, org, actor.id, conversation)


@router.get("/conversations/{conversation_id}", response_model=dict)
async def get_conversation(
    conversation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    conversation = await _require_membership(db, org, conversation_id, actor.id)
    return await _present_conversation(db, org, actor.id, conversation)


@router.patch("/conversations/{conversation_id}", response_model=dict)
async def update_conversation(
    conversation_id: str,
    payload: ConversationCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    await _require_membership(db, org, conversation_id, actor.id)
    conversation = await message_service.update_conversation(
        db, organization_id=org.id, conversation_id=conversation_id,
        payload=payload.model_dump(exclude_unset=True), actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present_conversation(db, org, actor.id, conversation)


@router.post("/conversations/{conversation_id}/archive", response_model=ApiMessage)
async def archive_conversation(
    conversation_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    await _require_membership(db, org, conversation_id, actor.id)
    await message_service.archive_conversation(
        db, organization_id=org.id, conversation_id=conversation_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return ApiMessage(message="Conversation archived")


@router.get("/conversations/{conversation_id}/members", response_model=list[dict])
async def list_conversation_members(
    conversation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    await _require_membership(db, org, conversation_id, actor.id)
    members = await message_service.members(db, organization_id=org.id, conversation_id=conversation_id)
    names = await _names(db, [m.employee_id for m in members])
    return [
        {"employee_id": m.employee_id, "employee_name": names.get(m.employee_id), "role": m.role}
        for m in members
    ]


@router.post("/conversations/{conversation_id}/members", response_model=dict, status_code=201)
async def add_conversation_member(
    conversation_id: str,
    payload: ConversationMemberPayload,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    await _require_membership(db, org, conversation_id, actor.id)
    member = await message_service.add_member(
        db, organization_id=org.id, conversation_id=conversation_id, employee_id=payload.employee_id,
        actor=actor, ip_address=get_client_ip(request),
    )
    if member is None:
        raise HTTPException(404, "Conversation not found")
    await db.commit()
    return {"employee_id": member.employee_id, "role": member.role}


@router.delete("/conversations/{conversation_id}/members/{employee_id}", response_model=ApiMessage)
async def remove_conversation_member(
    conversation_id: str,
    employee_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    await _require_membership(db, org, conversation_id, actor.id)
    if not await message_service.remove_member(
        db, organization_id=org.id, conversation_id=conversation_id, employee_id=employee_id,
        actor=actor, ip_address=get_client_ip(request),
    ):
        raise HTTPException(404, "Member not found")
    await db.commit()
    return ApiMessage(message="Member removed")


@router.post("/conversations/{conversation_id}/read", response_model=dict)
async def mark_conversation_read(
    conversation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    await _require_membership(db, org, conversation_id, actor.id)
    await message_service.mark_conversation_read(db, organization_id=org.id, conversation_id=conversation_id, employee_id=actor.id)
    await db.commit()
    return {"read": True}


# ------------------------------------------------------------- messages

@router.get("/conversations/{conversation_id}/messages", response_model=list[dict])
async def list_messages(
    conversation_id: str,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    await _require_membership(db, org, conversation_id, actor.id)
    messages = await message_service.list_messages(
        db, organization_id=org.id, conversation_id=conversation_id, limit=min(limit, 200), offset=offset
    )
    return [await _present_one_message(db, m) for m in reversed(messages)]


async def _present_one_message(db: AsyncSession, message):
    names = await _names(db, [message.sender_id] if message.sender_id else [])
    reactions = await message_service.reactions(db, organization_id=message.organization_id, message_id=message.id)
    return await present_message(
        message,
        sender_name=names.get(message.sender_id) if message.sender_id else None,
        reactions=reactions,
    )


@router.post("/conversations/{conversation_id}/messages", response_model=dict, status_code=201)
async def send_message(
    conversation_id: str,
    payload: MessageCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    await _require_membership(db, org, conversation_id, actor.id)
    message = await message_service.send(
        db, organization_id=org.id, conversation_id=conversation_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present_one_message(db, message)


@router.get("/conversations/{conversation_id}/pinned", response_model=list[dict])
async def list_pinned_messages(
    conversation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    await _require_membership(db, org, conversation_id, actor.id)
    pinned = await message_service.pinned_messages(db, organization_id=org.id, conversation_id=conversation_id)
    result = []
    for item in pinned:
        message = await message_service.get_message(db, organization_id=org.id, message_id=item.message_id)
        if message is not None:
            result.append(await _present_one_message(db, message))
    return result


@router.get("/mentions", response_model=list[dict])
async def my_mentions(
    limit: int = 50,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        return []
    messages = await message_service.my_mention_threads(db, organization_id=org.id, employee_id=actor.id, limit=min(limit, 200))
    return [await _present_one_message(db, m) for m in messages]


@router.get("/messages/{message_id}", response_model=dict)
async def get_message(
    message_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    message = await message_service.get_message(db, organization_id=org.id, message_id=message_id)
    if message is None:
        raise HTTPException(404, "Message not found")
    await _require_membership(db, org, message.conversation_id, actor.id)
    return await _present_one_message(db, message)


@router.patch("/messages/{message_id}", response_model=dict)
async def update_message(
    message_id: str,
    payload: MessageUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    message = await message_service.get_message(db, organization_id=org.id, message_id=message_id)
    if message is None:
        raise HTTPException(404, "Message not found")
    if message.sender_id != actor.id:
        raise HTTPException(403, "Only the sender can edit this message")
    await _require_membership(db, org, message.conversation_id, actor.id)
    message = await message_service.update_message(
        db, organization_id=org.id, message_id=message_id, content=payload.content, actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present_one_message(db, message)


@router.delete("/messages/{message_id}", response_model=ApiMessage)
async def delete_message(
    message_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    message = await message_service.get_message(db, organization_id=org.id, message_id=message_id)
    if message is None:
        raise HTTPException(404, "Message not found")
    if message.sender_id != actor.id:
        raise HTTPException(403, "Only the sender can delete this message")
    await _require_membership(db, org, message.conversation_id, actor.id)
    await message_service.delete_message(
        db, organization_id=org.id, message_id=message_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return ApiMessage(message="Message deleted")


@router.post("/messages/{message_id}/reactions", response_model=dict)
async def toggle_message_reaction(
    message_id: str,
    payload: ReactionPayload,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    message = await message_service.get_message(db, organization_id=org.id, message_id=message_id)
    if message is None:
        raise HTTPException(404, "Message not found")
    await _require_membership(db, org, message.conversation_id, actor.id)
    result = await message_service.toggle_reaction(
        db, organization_id=org.id, message_id=message_id, emoji=payload.emoji, actor=actor
    )
    await db.commit()
    return result


@router.get("/messages/{message_id}/reactions", response_model=list[dict])
async def list_message_reactions(
    message_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    message = await message_service.get_message(db, organization_id=org.id, message_id=message_id)
    if message is None:
        raise HTTPException(404, "Message not found")
    await _require_membership(db, org, message.conversation_id, actor.id)
    return await message_service.reactions(db, organization_id=org.id, message_id=message_id)


@router.post("/messages/{message_id}/read", response_model=dict)
async def mark_message_read(
    message_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    message = await message_service.get_message(db, organization_id=org.id, message_id=message_id)
    if message is None:
        raise HTTPException(404, "Message not found")
    await _require_membership(db, org, message.conversation_id, actor.id)
    await message_service.mark_read(db, organization_id=org.id, message_id=message_id, employee_id=actor.id)
    await db.commit()
    return {"read": True}


@router.post("/messages/{message_id}/pin", response_model=dict)
async def pin_message(
    message_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    message = await message_service.get_message(db, organization_id=org.id, message_id=message_id)
    if message is None:
        raise HTTPException(404, "Message not found")
    await _require_membership(db, org, message.conversation_id, actor.id)
    pinned = await message_service.pin_message(
        db, organization_id=org.id, conversation_id=message.conversation_id, message_id=message_id, actor=actor
    )
    await db.commit()
    return {"pinned": pinned}
