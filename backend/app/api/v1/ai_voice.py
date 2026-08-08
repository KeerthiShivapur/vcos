"""AI voice endpoints (Phase 7.13) — text-in/text-out voice companion.

The frontend captures audio with the Web Speech API and sends the transcript
here; answers can be spoken back with the same API. Everything else reuses
the chat companion pipeline with ``source=voice`` conversations.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.companion_service import companion_service
from app.ai.voice import ensure_voice_conversation, normalize_transcript, strip_fill_words
from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.ai import AIConversation
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai/voice", tags=["ai"])


class VoiceIn(BaseModel):
    transcript: str
    conversation_id: Optional[str] = None
    context: Optional[dict[str, Any]] = None


class TranscriptIn(BaseModel):
    transcript: str


@router.post("/normalize")
async def normalize(
    payload: TranscriptIn,
    user: User = Depends(require_permission("ai:use")),
) -> dict[str, Any]:
    return {"transcript": normalize_transcript(payload.transcript)}


@router.post("/clean")
async def clean(
    payload: TranscriptIn,
    user: User = Depends(require_permission("ai:use")),
) -> dict[str, Any]:
    return {"transcript": strip_fill_words(payload.transcript)}


@router.post("/ask")
async def voice_ask(
    payload: VoiceIn,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    text = strip_fill_words(payload.transcript)
    if not text:
        return {"answer": "I didn't catch that — could you say it again?", "source": "rules", "intents": []}
    conversation = None
    if payload.conversation_id:
        conversation = await db.get(AIConversation, payload.conversation_id)
    if conversation is None or conversation.organization_id != org.id or conversation.source != "voice":
        conversation = await ensure_voice_conversation(
            db, organization_id=org.id, user_id=user.id
        )
    result = await companion_service.answer(
        db,
        organization_id=org.id,
        user=user,
        message=text,
        context=payload.context or {},
        conversation_id=conversation.id,
    )
    await db.commit()
    return result
