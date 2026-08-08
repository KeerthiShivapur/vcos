"""Phase 20 — Universal Company Brain API.

One surface for the whole organization: the living overview, universal AI,
universal search, living graph, company health, permanent memory, company
timeline, universal context, event stream, analytics and the continuous
evolution cycle. Employees, managers and executives all ask the same brain.
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.kernel.organization_kernel import organization_kernel
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/brain", tags=["Company Brain"])


class BrainAskIn(BaseModel):
    question: str


class BrainMemoryIn(BaseModel):
    memory_type: str = "institutional"
    title: str
    content: Optional[str] = None
    tags: Optional[list[str]] = None
    importance: str = "medium"
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    source_event: Optional[str] = None
    occurred_at: Optional[datetime] = None


class BrainTimelineIn(BaseModel):
    event_type: str
    title: str
    category: Optional[str] = None
    detail: Optional[str] = None
    occurred_at: Optional[datetime] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class BrainGovernanceIn(BaseModel):
    title: str
    category: str = "knowledge"
    rationale: Optional[str] = None
    evidence: Optional[dict[str, Any]] = None
    confidence: float = 0.6
    affected_systems: Optional[list[str]] = None
    requires_approval: bool = True


# ----------------------------------------------------------------- capabilities

@router.get("/capabilities")
async def brain_capabilities(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
) -> dict[str, Any]:
    return organization_kernel.capabilities()


# ---------------------------------------------------------------------- overview

@router.get("/overview")
async def brain_overview(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.overview(db, org.id)


@router.get("/state")
async def brain_state(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.state(db, org.id)


# ------------------------------------------------------------------ universal ai

@router.post("/ask")
async def brain_ask(
    body: BrainAskIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    return await organization_kernel.ask(db, org.id, body.question)


@router.post("/advise")
async def brain_advise(
    body: BrainAskIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    return await organization_kernel.advise(db, org.id, body.question)


@router.get("/explain")
async def brain_explain(
    topic: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.reasoning.explain(db, org.id, topic)


# ----------------------------------------------------------------------- health

@router.get("/health")
async def brain_health(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.health.latest(db, org.id)


@router.post("/health/refresh")
async def brain_health_refresh(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await organization_kernel.health.refresh(db, org.id)
    await db.commit()
    return result


@router.get("/health/history")
async def brain_health_history(
    limit: int = Query(default=30, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.health.history(db, org.id, limit=limit)


# ---------------------------------------------------------------- intelligence

@router.get("/intelligence")
async def brain_intelligence_latest(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.intelligence.latest(db, org.id)


@router.get("/intelligence/history")
async def brain_intelligence_history(
    limit: int = Query(default=20, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.intelligence.list(db, org.id, limit=limit)


@router.post("/intelligence/generate")
async def brain_intelligence_generate(
    period: str = "on_demand",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await organization_kernel.intelligence.generate(db, org.id, period=period)
    await db.commit()
    return result


# ---------------------------------------------------------------------- briefing

@router.get("/briefing")
async def brain_briefing_latest(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.ai.latest_brief(db, org.id)


@router.post("/briefing")
async def brain_briefing_generate(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await organization_kernel.ai.brief(db, org.id)
    await db.commit()
    return result


# ------------------------------------------------------------------ memory

@router.get("/memory")
async def brain_memory_list(
    memory_type: Optional[str] = None,
    importance: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.memory.list_memories(
        db, org.id, memory_type=memory_type, importance=importance, search=search, limit=limit
    )


@router.post("/memory")
async def brain_memory_record(
    body: BrainMemoryIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await organization_kernel.memory.record_memory(
            db, org.id,
            memory_type=body.memory_type, title=body.title, content=body.content,
            tags=body.tags, importance=body.importance,
            entity_type=body.entity_type, entity_id=body.entity_id,
            source_event=body.source_event, recorded_by=user.id, occurred_at=body.occurred_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


# --------------------------------------------------------------------- timeline

@router.get("/timeline")
async def brain_timeline_list(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=300),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.memory.list_timeline(
        db, org.id, category=category, search=search, limit=limit
    )


@router.post("/timeline")
async def brain_timeline_record(
    body: BrainTimelineIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await organization_kernel.memory.record_timeline(
            db, org.id,
            event_type=body.event_type, title=body.title, category=body.category,
            detail=body.detail, occurred_at=body.occurred_at, actor_id=user.id,
            entity_type=body.entity_type, entity_id=body.entity_id, metadata=body.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


# ------------------------------------------------------------------ universal search

@router.get("/search")
async def brain_search(
    q: str,
    limit: int = Query(default=20, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not q.strip():
        raise HTTPException(status_code=422, detail="query is required")
    return await organization_kernel.search.search(db, org.id, q, limit=limit)


# ------------------------------------------------------------------------- graph

@router.get("/graph")
async def brain_graph_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.graph.stats(db, org.id)


@router.get("/graph/nodes")
async def brain_graph_nodes(
    node_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.graph.nodes(
        db, org.id, node_type=node_type, search=search, limit=limit
    )


@router.get("/graph/search")
async def brain_graph_search(
    q: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.graph.search(db, org.id, q)


@router.post("/graph/rebuild")
async def brain_graph_rebuild(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await organization_kernel.graph.rebuild(db, org.id)
    await db.commit()
    return result


# ----------------------------------------------------------------------- context

@router.get("/context")
async def brain_context(
    entity_type: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.context.flow(db, org.id, entity_type, entity_id)


@router.get("/digest")
async def brain_digest(
    days: int = Query(default=1, ge=1, le=30),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.context.digest(db, org.id, days=days)


# ------------------------------------------------------------------------- events

@router.get("/events")
async def brain_events(
    name: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=300),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.events.list(db, org.id, name=name, limit=limit)


@router.get("/events/summary")
async def brain_events_summary(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.events.summary(db, org.id)


# ---------------------------------------------------------------------- analytics

@router.get("/analytics")
async def brain_analytics(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.analytics.overview(db, org.id)


# ------------------------------------------------------------------------ evolve

@router.post("/evolve")
async def brain_evolve(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await organization_kernel.evolve(db, org.id)
    await db.commit()
    return result


# -------------------------------------------------------- AI governance

@router.get("/governance")
async def brain_governance_list(
    category: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=300),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.governance.list(
        db, org.id, category=category, status=status, limit=limit
    )


@router.post("/governance/recommendation")
async def brain_governance_submit(
    body: BrainGovernanceIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await organization_kernel.governance.submit(
            db, org.id,
            title=body.title, category=body.category, rationale=body.rationale,
            evidence=body.evidence, confidence=body.confidence,
            affected_systems=body.affected_systems,
            requires_approval=body.requires_approval, created_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


@router.post("/governance/{recommendation_id}/{decision}")
async def brain_governance_decide(
    recommendation_id: str,
    decision: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await organization_kernel.governance.decide(
            db, org.id, recommendation_id, decision, decided_by=user.id
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="recommendation not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


# ---------------------------------------------------------- resilience

@router.get("/resilience")
async def brain_resilience_list(
    scenario: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_kernel.resilience.list(
        db, org.id, scenario=scenario, status=status, limit=limit
    )


@router.post("/resilience/assess")
async def brain_resilience_assess(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await organization_kernel.resilience.assess(db, org.id)
    await db.commit()
    return result
