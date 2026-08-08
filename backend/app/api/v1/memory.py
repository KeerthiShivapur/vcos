"""Phase 19 — Company Memory, Organization Timeline & Universal Context API.

Three surfaces:
  /memory     — permanent organizational memory (decisions, lessons, milestones)
  /timeline   — the organization-wide company history timeline
  /context    — universal context bundles linking entities across modules
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.memory.context_service import context_service
from app.memory.memory_service import memory_service
from app.memory.timeline_service import timeline_service
from app.models.organization import Organization
from app.models.user import User

memory_router = APIRouter(prefix="/memory", tags=["company-memory"])
timeline_router = APIRouter(prefix="/timeline", tags=["organization-timeline"])
context_router = APIRouter(prefix="/context", tags=["universal-context"])


# --------------------------------------------------------------------- memory

class MemoryIn(BaseModel):
    memory_type: str = "institutional"
    title: str
    content: Optional[str] = None
    tags: Optional[list[str]] = None
    importance: str = "medium"
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    source_event: Optional[str] = None
    occurred_at: Optional[datetime] = None


@memory_router.get("")
async def list_memories(
    memory_type: Optional[str] = None,
    importance: Optional[str] = None,
    pinned: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("memory:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await memory_service.list(
        db, org.id,
        memory_type=memory_type, importance=importance, pinned=pinned,
        search=search, limit=limit,
    )
    return {"total": len(rows), "memories": rows}


@memory_router.post("")
async def record_memory(
    body: MemoryIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("memory:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await memory_service.record(
            db,
            organization_id=org.id,
            memory_type=body.memory_type,
            title=body.title,
            content=body.content,
            tags=body.tags,
            importance=body.importance,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            source_event=body.source_event,
            recorded_by=user.id,
            occurred_at=body.occurred_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


@memory_router.get("/recall")
async def recall_memories(
    topic: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("memory:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await memory_service.recall(db, org.id, topic=topic, limit=limit)
    await db.commit()
    return result


@memory_router.get("/{memory_id}")
async def get_memory(
    memory_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("memory:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await memory_service.get(db, org.id, memory_id)
    if row is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return row


@memory_router.patch("/{memory_id}/pin")
async def pin_memory(
    memory_id: str,
    pinned: bool = True,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("memory:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await memory_service.set_pinned(db, org.id, memory_id, pinned=pinned)
    if row is None:
        raise HTTPException(status_code=404, detail="memory not found")
    await db.commit()
    return row


@memory_router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("memory:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    deleted = await memory_service.delete(db, org.id, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="memory not found")
    await db.commit()
    return {"status": "deleted", "memory_id": memory_id}


# -------------------------------------------------------------------- timeline

class TimelineIn(BaseModel):
    event_type: str
    title: str
    category: Optional[str] = None
    detail: Optional[str] = None
    occurred_at: Optional[datetime] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@timeline_router.get("")
async def list_timeline(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=300),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("timeline:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await timeline_service.list(db, org.id, category=category, search=search, limit=limit)
    return {"total": len(rows), "entries": rows}


@timeline_router.post("")
async def record_timeline_entry(
    body: TimelineIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("timeline:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await timeline_service.record(
            db,
            organization_id=org.id,
            event_type=body.event_type,
            title=body.title,
            category=body.category,
            detail=body.detail,
            occurred_at=body.occurred_at,
            actor_id=user.id,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            metadata=body.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


@timeline_router.get("/summary")
async def timeline_summary(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("timeline:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await timeline_service.summary(db, org.id)


@timeline_router.get("/{entry_id}")
async def get_timeline_entry(
    entry_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("timeline:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await timeline_service.get(db, org.id, entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="timeline entry not found")
    return row


# ---------------------------------------------------------------------- context

class ContextAttachIn(BaseModel):
    entity_type: str
    entity_id: str
    related: dict[str, Any]


@context_router.get("/{entity_type}/{entity_id}")
async def get_context(
    entity_type: str,
    entity_id: str,
    rebuild: bool = False,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("context:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    bundle = await context_service.flow(db, org.id, entity_type, entity_id)
    return bundle


@context_router.post("/{entity_type}/{entity_id}/build")
async def build_context(
    entity_type: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("context:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    bundle = await context_service.get(db, org.id, entity_type, entity_id, rebuild=True)
    if bundle is None:
        raise HTTPException(status_code=404, detail="entity not found")
    await db.commit()
    return bundle


@context_router.post("/attach")
async def attach_context(
    body: ContextAttachIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("context:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    bundle = await context_service.get(db, org.id, body.entity_type, body.entity_id, rebuild=True)
    if bundle is None:
        raise HTTPException(status_code=404, detail="entity not found")
    from app.memory.context_service import context_service as _ctx

    await _ctx.attach(db, org.id, body.entity_type, body.entity_id, body.related)
    bundle = await context_service.get(db, org.id, body.entity_type, body.entity_id)
    await db.commit()
    return bundle
