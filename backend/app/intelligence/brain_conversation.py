"""Slice 4D.7 — Brain conversation store (follow-up continuity, observation-only).

A bounded, tenant- and owner-scoped session record. The answer endpoint
persists one turn per question so follow-up questions ("Has this happened
before?", "Who owns it?") can inherit the anchor entity from the previous
utterance — the user never repeats the entity and the frontend never
re-sends the anchor.

This is an observation artifact, not an intelligence engine: it stores
question/answer turns, never reasons, never retrieves, never mutates an
operating entity.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.brain import BrainConversation, BrainConversationTurn

MAX_CONVERSATIONS_PER_USER = 20
MAX_TURNS_PER_CONVERSATION = 24
ANCHOR_LOOKBACK_TURNS = 3


def _serialize_turn(row: BrainConversationTurn) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "question": row.question,
        "summary": row.summary,
        "anchor_type": row.anchor_type,
        "anchor_id": row.anchor_id,
        "anchor_title": row.anchor_title,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_conversation(row: BrainConversation) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "user_id": row.user_id,
        "turn_count": row.turn_count or 0,
        "last_anchor_type": row.last_anchor_type,
        "last_anchor_id": row.last_anchor_id,
        "last_anchor_title": row.last_anchor_title,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def create_conversation(
    db: AsyncSession, *, organization_id: str, user_id: str
) -> dict[str, Any]:
    """Create a conversation for a caller, trimming the caller to the bound."""
    existing = (
        await db.execute(
            select(BrainConversation.id)
            .where(
                BrainConversation.organization_id == organization_id,
                BrainConversation.user_id == user_id,
            )
            .order_by(BrainConversation.updated_at.desc())
            .limit(MAX_CONVERSATIONS_PER_USER + 1)
        )
    ).scalars().all()
    if len(existing) >= MAX_CONVERSATIONS_PER_USER:
        # Trim the oldest conversation (and its turns via cascade) so the
        # session artifact stays bounded per user.
        oldest_id = existing[-1]
        await db.execute(
            delete(BrainConversation).where(BrainConversation.id == oldest_id)
        )
    row = BrainConversation(
        organization_id=organization_id,
        user_id=user_id,
        turn_count=0,
    )
    db.add(row)
    await db.flush()  # populate the generated id before serialization
    return _serialize_conversation(row)


async def list_conversations(
    db: AsyncSession, *, organization_id: str, user_id: str, limit: int = 20
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(BrainConversation)
            .where(
                BrainConversation.organization_id == organization_id,
                BrainConversation.user_id == user_id,
            )
            .order_by(BrainConversation.updated_at.desc())
            .limit(max(1, min(limit, 50)))
        )
    ).scalars().all()
    return [_serialize_conversation(row) for row in rows]


async def get_conversation(
    db: AsyncSession,
    *,
    organization_id: str,
    user_id: str,
    conversation_id: str,
    include_turns: bool = True,
) -> Optional[dict[str, Any]]:
    """Fetch a conversation, ensuring tenant + owner match. None == 404."""
    row = await db.get(BrainConversation, conversation_id)
    if (
        row is None
        or row.organization_id != organization_id
        or row.user_id != user_id
    ):
        return None
    data = _serialize_conversation(row)
    if include_turns:
        turns = (
            await db.execute(
                select(BrainConversationTurn)
                .where(BrainConversationTurn.conversation_id == conversation_id)
                .order_by(BrainConversationTurn.created_at.asc())
                .limit(100)
            )
        ).scalars().all()
        data["turns"] = [_serialize_turn(turn) for turn in turns]
    return data


async def resolve_anchor(
    db: AsyncSession, *, conversation_id: str
) -> Optional[dict[str, Any]]:
    """The most recent anchor referenced in the conversation (bounded)."""
    rows = (
        await db.execute(
            select(BrainConversationTurn)
            .where(BrainConversationTurn.conversation_id == conversation_id)
            .order_by(BrainConversationTurn.created_at.desc())
            .limit(ANCHOR_LOOKBACK_TURNS)
        )
    ).scalars().all()
    for turn in reversed(rows):
        if turn.anchor_type and turn.anchor_id:
            return {
                "type": turn.anchor_type,
                "id": turn.anchor_id,
                "title": turn.anchor_title,
            }
    return None


async def append_turn(
    db: AsyncSession,
    *,
    conversation_id: str,
    question: str,
    summary: Optional[str] = None,
    anchor_type: Optional[str] = None,
    anchor_id: Optional[str] = None,
    anchor_title: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Persist one answered question; trims turns beyond the per-conversation bound.

    Returns the serialized turn, or None when the conversation does not exist.
    """
    conversation = await db.get(BrainConversation, conversation_id)
    if conversation is None:
        return None
    turn = BrainConversationTurn(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        question=question,
        summary=summary,
        anchor_type=anchor_type,
        anchor_id=anchor_id,
        anchor_title=anchor_title,
    )
    db.add(turn)

    conversation.turn_count = (conversation.turn_count or 0) + 1
    conversation.last_anchor_type = anchor_type
    conversation.last_anchor_id = anchor_id
    conversation.last_anchor_title = anchor_title
    conversation.updated_at = utcnow()

    stale = (
        await db.execute(
            select(BrainConversationTurn.id)
            .where(BrainConversationTurn.conversation_id == conversation.id)
            .order_by(BrainConversationTurn.created_at.desc())
            .offset(MAX_TURNS_PER_CONVERSATION)
        )
    ).scalars().all()
    if stale:
        await db.execute(
            delete(BrainConversationTurn).where(BrainConversationTurn.id.in_(stale))
        )
    return _serialize_turn(turn)