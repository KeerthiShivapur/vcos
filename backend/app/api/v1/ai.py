"""AI Companion endpoints — Phase 7 (universal companion).

Conversation lifecycle: ask (persists thread + messages), history, feedback,
and an SSE streaming variant for the chat UI.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.companion_service import companion_service
from app.ai.gateway import ai_gateway
from app.ai.learning import learning_service
from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai", tags=["ai"])


class CompanionContext(BaseModel):
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    goal_id: Optional[str] = None
    meeting_id: Optional[str] = None


class CompanionAsk(BaseModel):
    message: str
    context: Optional[CompanionContext] = None
    conversation_id: Optional[str] = None


class FeedbackIn(BaseModel):
    message_id: Optional[str] = None
    content: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    helpful: Optional[bool] = None
    correction: Optional[str] = None


@router.get("/companion/status")
async def companion_status(
    _: User = Depends(require_permission("ai:use")),
) -> dict[str, Any]:
    status = await ai_gateway.status()
    status["grounded"] = True
    status["capabilities"] = [
        "my_day",
        "org_pulse",
        "entity_summary",
        "universal_search",
        "expert_finder",
        "planning",
        "recommendations",
        "predictions",
        "actions",
        "memory",
        "voice",
    ]
    return status


@router.post("/companion/ask")
async def companion_ask(
    payload: CompanionAsk,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    context = payload.context.model_dump() if payload.context else {}
    result = await companion_service.answer(
        db,
        organization_id=org.id,
        user=user,
        message=payload.message,
        context=context,
        conversation_id=payload.conversation_id,
    )
    await db.commit()
    return result


@router.post("/companion/stream")
async def companion_stream(
    payload: CompanionAsk,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    context = payload.context.model_dump() if payload.context else {}
    result = await companion_service.answer(
        db,
        organization_id=org.id,
        user=user,
        message=payload.message,
        context=context,
        conversation_id=payload.conversation_id,
    )

    async def event_stream():
        import json as _json

        full = result["answer"]
        step = max(1, len(full) // 24)
        for i in range(0, len(full), step):
            yield f"data: {_json.dumps({'delta': full[i:i + step]}, default=str)}\n\n"
        yield f"data: {_json.dumps({'done': {'conversation_id': result['conversation_id'], 'message_id': result['message_id'], 'intents': result['intents'], 'source': result['source']}}, default=str)}\n\n"

    await db.commit()
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from sqlalchemy import select

    from app.models.ai import AIConversation

    rows = (
        await db.execute(
            select(AIConversation)
            .where(
                AIConversation.organization_id == org.id,
                AIConversation.user_id == user.id,
            )
            .order_by(AIConversation.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "total": len(rows),
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "source": c.source,
                "created_at": c.created_at,
            }
            for c in rows
        ],
    }


@router.get("/conversations/{conversation_id}")
async def conversation_history(
    conversation_id: str,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    messages = await companion_service.history(db, conversation_id=conversation_id)
    if not messages:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"conversation_id": conversation_id, "messages": messages}


@router.post("/feedback")
async def submit_feedback(
    payload: FeedbackIn,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await learning_service.record_feedback(
        db,
        organization_id=org.id,
        user=user,
        message_id=payload.message_id,
        content=payload.content,
        rating=payload.rating,
        helpful=payload.helpful,
        correction=payload.correction,
    )
    await db.commit()
    return {"id": row.id, "status": "recorded"}
