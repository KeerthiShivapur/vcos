"""AI memory endpoints (Phase 7.2)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory import memory_manager
from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai/memory", tags=["ai"])


class MemoryIn(BaseModel):
    content: str
    memory_type: str = "semantic"
    kind: str = "fact"
    scope: str = "organization"
    subject_type: Optional[str] = None
    subject_id: Optional[str] = None
    importance: int = 5


@router.get("")
async def recall_memories(
    memory_type: Optional[str] = None,
    kind: Optional[str] = None,
    text: Optional[str] = None,
    limit: int = 20,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await memory_manager.recall(
        db,
        organization_id=org.id,
        memory_type=memory_type,
        kind=kind,
        text=text,
        limit=limit,
    )
    return {
        "total": len(rows),
        "memories": [
            {
                "id": m.id,
                "memory_type": m.memory_type,
                "scope": m.scope,
                "kind": m.kind,
                "content": m.content,
                "source": m.source,
                "importance": m.importance,
                "created_at": m.created_at,
            }
            for m in rows
        ],
    }


@router.post("")
async def remember(
    payload: MemoryIn,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    memory = await memory_manager.remember(
        db,
        organization_id=org.id,
        content=payload.content,
        memory_type=payload.memory_type,
        kind=payload.kind,
        scope=payload.scope,
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        user_id=user.id,
        importance=payload.importance,
        source="api",
    )
    await db.commit()
    return {"id": memory.id if memory else None, "status": "remembered"}


@router.post("/consolidate")
async def consolidate(
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await memory_manager.consolidate(db, organization_id=org.id, user_id=user.id)
    await db.commit()
    return result


@router.delete("/{memory_id}")
async def forget_memory(
    memory_id: str,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    deleted = await memory_manager.forget(db, memory_id)
    await db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"status": "forgotten"}
