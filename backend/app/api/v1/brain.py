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
from app.intelligence.company_brain import MAX_TIMELINE
from app.intelligence.graph_engine import graph_engine as company_graph
from app.intelligence.insight_engine import insight_engine
from app.intelligence.pattern_engine import pattern_engine
from app.kernel.organization_kernel import organization_kernel
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/brain", tags=["Company Brain"])


class BrainAskIn(BaseModel):
    question: str


class BrainAnswerIn(BaseModel):
    question: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    conversation_id: Optional[str] = None


class BrainSyncIn(BaseModel):
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


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


class BrainPatternStatusIn(BaseModel):
    status: str


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
    """Slice 4D.6 — unified company brain overview.

    The living company view above stays, and the response is extended
    additively with governed, bounded sections: what needs attention (active
    insights, recurring patterns, recent memories) and recent company
    intelligence per source — only what the caller may actually access.
    """
    from app.intelligence.company_brain import company_brain

    base = await organization_kernel.overview(db, org.id)
    unified = await company_brain.overview(db, org.id, user=user)
    base.update(unified)
    return base


# Slice 4D.6 — cross-source evidence drawer + related view (governed, bounded)


@router.get("/evidence/{source_type}/{source_id}")
async def brain_evidence(
    source_type: str,
    source_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
    link_limit: int = Query(5, ge=1, le=10),
) -> dict[str, Any]:
    """Why are these pieces of intelligence connected?

    Resolves one governed source object and links the existing intelligence
    that references it (patterns, insights, memories, knowledge, graph
    neighbors). Restricted evidence is never retrieved, so it can never leak.
    """
    from app.intelligence.company_brain import company_brain

    result = await company_brain.evidence(
        db, org.id, user=user,
        source_type=source_type, source_id=source_id,
        link_limit=link_limit,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    return result


@router.get("/related/{source_type}/{source_id}")
async def brain_related(
    source_type: str,
    source_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(8, ge=1, le=20),
) -> dict[str, Any]:
    """Concise, governed relationship view of one source object.

    Graph neighbors plus cross-source intelligence anchored to the entity —
    bounded and visibility-filtered before exposure.
    """
    from app.intelligence.company_brain import company_brain

    result = await company_brain.related(
        db, org.id, user=user,
        source_type=source_type, source_id=source_id,
        limit=limit,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="related not found")
    return result


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


@router.post("/answer")
async def brain_answer(
    body: BrainAnswerIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.6 — unified company brain answer.

    The canonical 4D.1 claims (evidence-backed, governance-scoped) are
    composed with governed, bounded sections from every relevant source —
    patterns (4D.4), memories (4D.3), insights (4D.5) and semantic knowledge
    (4D.2) — plus related entities, a deterministic summary, a bounded
    confidence and observability metrics. Additive to the 4D.1 contract.

    Slice 4D.7 — conversation_id enables follow-up continuity: the anchor
    entity of the conversation is inherited when the question does not name
    one, and the turn is persisted for the next utterance. 404 when the
    conversation does not belong to this caller/tenant.
    """
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    from app.intelligence.company_brain import company_brain

    result = await company_brain.answer(
        db, org.id, body.question,
        user=user, entity_type=body.entity_type, entity_id=body.entity_id,
        conversation_id=body.conversation_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    if result.get("conversation"):
        await db.commit()  # persist the answered turn
    return result


# Slice 4D.7 — conversational continuity (observation artifact, owner-scoped)


class BrainConversationCreateIn(BaseModel):
    pass


@router.post("/conversations")
async def brain_conversation_create(
    body: BrainConversationCreateIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a conversation (session record) for the caller."""
    from app.intelligence.brain_conversation import create_conversation

    result = await create_conversation(
        db, organization_id=org.id, user_id=user.id
    )
    await db.commit()
    return result


@router.get("/conversations")
async def brain_conversation_list(
    limit: int = Query(default=20, ge=1, le=50),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The caller's own conversation records (bounded, owner-scoped)."""
    from app.intelligence.brain_conversation import list_conversations

    conversations = await list_conversations(
        db, organization_id=org.id, user_id=user.id, limit=limit
    )
    return {"conversations": conversations, "count": len(conversations)}


@router.get("/conversations/{conversation_id}")
async def brain_conversation_get(
    conversation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One conversation with its turns; 404 when not the caller's own."""
    from app.intelligence.brain_conversation import get_conversation

    result = await get_conversation(
        db, organization_id=org.id, user_id=user.id, conversation_id=conversation_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return result


@router.get("/timeline/unified")
async def brain_timeline_unified(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = Query(default=MAX_TIMELINE, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.7 — unified, evidence-backed company timeline.

    Every entry references a real row (memory/pattern/insight/project
    timeline) the caller may access; bounded and governance-filtered before
    exposure. Mirrors the narrative of the previous events at 4D.3.
    """
    from app.intelligence.company_brain import company_brain

    result = await company_brain.timeline(
        db, org.id, user=user,
        entity_type=entity_type, entity_id=entity_id,
        limit=min(limit, MAX_TIMELINE),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="entity not found")
    return result


@router.get("/what-changed")
async def brain_what_changed(
    days: int = Query(default=7, ge=1, le=30),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.7 — what changed (governed digest, persona-aware).

    Org-wide callers see the canonical kernel digest; scoped callers see
    only their visible scope's activity. Bounded by construction.
    """
    from app.intelligence.company_brain import company_brain

    return await company_brain.what_changed(db, org.id, user=user, days=days)


class BrainKnowledgeSearchIn(BaseModel):
    question: str
    kinds: Optional[list[str]] = None
    limit: int = 10


@router.post("/knowledge/search")
async def brain_knowledge_search(
    body: BrainKnowledgeSearchIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.2 — hybrid semantic knowledge search under governance.

    Retrieves chunk-level semantic evidence from the persisted
    ``KnowledgeVector`` index, filtered to what the caller may access before
    any scoring or exposure. Results carry evidence lineage (source row,
    scores, provider, freshness) and never include raw embeddings.
    """
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    from app.knowledge.semantic_search import search as semantic_knowledge_search

    return await semantic_knowledge_search(
        db,
        organization_id=org.id,
        user=user,
        query=body.question,
        kinds=body.kinds,
        limit=body.limit or 10,
    )


# ------------------------------------------------------- 4E.1 canonical model

class BrainReconcileIn(BaseModel):
    kind: Optional[str] = None
    limit: int = 20


@router.get("/knowledge")
async def brain_knowledge_registry(
    limit: int = Query(12, ge=1, le=25),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.1 — governed canonical knowledge registry map.

    The universal ingestion contract surface: canonical sources with their
    lifecycle, authority and freshness, bounded and filtered to what the
    caller may access before exposure.
    """
    from app.knowledge.canonical_service import canonical_engine

    return await canonical_engine.registry(db, organization_id=org.id, user=user, limit=limit)


@router.get("/knowledge/sources/{source_type}/{source_id}")
async def brain_knowledge_source(
    source_type: str,
    source_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.1 — one canonical source with its claims and evidence.

    Temporal truth is preserved: superseded claims stay visible with
    valid_to + superseded_by (what was true vs what is true now).
    Hidden sources return 404 — governance constrains retrieval itself.
    """
    from app.knowledge.canonical_service import canonical_engine

    result = await canonical_engine.source_detail(
        db, organization_id=org.id,
        source_type=source_type, source_id=source_id, user=user,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="knowledge source not found")
    return result


@router.get("/knowledge/claims")
async def brain_knowledge_claims(
    limit: int = Query(10, ge=1, le=25),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.1 — recent canonical claims across accessible sources."""
    from app.knowledge.canonical_service import canonical_engine

    return await canonical_engine.recent_claims(db, organization_id=org.id, user=user, limit=limit)


@router.get("/knowledge/topics")
async def brain_knowledge_topics(
    limit: int = Query(20, ge=1, le=25),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.1 — canonical topic registry seeding entity resolution."""
    from app.knowledge.canonical_service import canonical_engine

    return await canonical_engine.topics(db, organization_id=org.id, user=user, limit=limit)


@router.post("/knowledge/reconcile")
async def brain_knowledge_reconcile(
    body: BrainReconcileIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.1 — bounded on-demand canonical resync (recovery only).

    Normal flow is event-driven; this exists for schema changes and manual
    corrections and is hard-capped so it can never become a full-org scan.
    """
    from app.knowledge.canonical_service import canonical_engine

    return await canonical_engine.reconcile(
        db, organization_id=org.id,
        kind=body.kind, limit=body.limit or 20,
    )


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


# ------------------------------------------------------------------ 4D.3 memory
#
# Slice 4D.3 canonical surface: evidence-backed organizational memory under
# governance. Static routes are declared before /memory/{memory_id} so path
# matching stays unambiguous.

class BrainMemorySearchIn(BaseModel):
    question: str
    limit: int = 10


class BrainMemoryOutcomeIn(BaseModel):
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    outcome_type: str = "positive"  # positive | negative | partial | unresolved
    outcome: Optional[str] = None


@router.get("/memory/feed")
async def brain_memory_feed(
    memory_category: Optional[str] = None,
    status: str = Query(default="active"),
    limit: int = Query(default=50, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.3 — memory feed: the caller's visible organizational memory."""
    from app.memory.memory_store import feed as memory_feed

    return await memory_feed(
        db,
        organization_id=org.id,
        user=user,
        memory_category=memory_category,
        status=status,
        limit=limit,
    )


@router.post("/memory/search")
async def brain_memory_search(
    body: BrainMemorySearchIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.3 — semantic historical retrieval ("have we seen this before?")."""
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    from app.memory.memory_store import search as memory_search

    return await memory_search(
        db,
        organization_id=org.id,
        user=user,
        query=body.question,
        limit=body.limit or 10,
    )


@router.get("/memory/timeline")
async def brain_memory_timeline(
    limit: int = Query(default=50, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.3 — episode-style company history with forming events."""
    from app.memory.memory_store import timeline as memory_timeline

    return await memory_timeline(
        db,
        organization_id=org.id,
        user=user,
        limit=limit,
    )


@router.get("/memory/{memory_id}")
async def brain_memory_get(
    memory_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.3 — one memory with its evidence lineage and context snapshot."""
    from app.memory.memory_store import get as memory_get

    result = await memory_get(db, organization_id=org.id, user=user, memory_id=memory_id)
    if result is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return result


@router.get("/memory/{memory_id}/evidence")
async def brain_memory_evidence(
    memory_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.3 — why VCOS believes this memory (resolved evidence refs)."""
    from app.memory.memory_store import evidence as memory_evidence

    result = await memory_evidence(db, organization_id=org.id, user=user, memory_id=memory_id)
    if result is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return result


@router.get("/memory/{memory_id}/related")
async def brain_memory_related(
    memory_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.3 — semantically related memories (governance-filtered)."""
    from app.memory.memory_store import related as memory_related

    result = await memory_related(db, organization_id=org.id, user=user, memory_id=memory_id)
    if result is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return result


@router.post("/memory/{memory_id}/outcome")
async def brain_memory_outcome(
    memory_id: str,
    body: BrainMemoryOutcomeIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.3 — record an observed outcome for a memory (feedback loop).

    The memory layer only records the observation; no operating entity changes.
    """
    from app.models.company_memory import OUTCOME_TYPES_VALID

    if body.outcome_type not in OUTCOME_TYPES_VALID:
        raise HTTPException(status_code=422, detail=f"invalid outcome_type: {body.outcome_type}")
    from app.memory.memory_store import record_outcome

    result = await record_outcome(
        db,
        organization_id=org.id,
        user=user,
        memory_id=memory_id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        outcome_type=body.outcome_type,
        outcome=body.outcome,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="memory not found")
    await db.commit()
    return result

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


@router.post("/graph/relationships/sync")
async def brain_graph_relationships_sync(
    body: BrainSyncIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.1 — upsert relationship edges for one entity (bounded)."""
    if body.entity_type and body.entity_id:
        count = await company_graph.sync_entity_edges(
            db, organization_id=org.id, entity_type=body.entity_type, entity_id=body.entity_id
        )
    else:
        count = await company_graph.sync_recent_relationships(db, organization_id=org.id)
    await db.commit()
    return {"synced": count, "mode": "entity" if body.entity_id else "recent"}


@router.get("/graph/relationships/traverse")
async def brain_graph_relationships_traverse(
    node_type: str,
    node_id: str,
    max_depth: int = Query(3, ge=1, le=8),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4D.1 — bounded BFS traversal of company relationship edges."""
    return await company_graph.traverse(
        db, organization_id=org.id, start_type=node_type, start_id=node_id,
        max_depth=max_depth,
    )


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


# ---------------------------------------------------------- patterns (4D.4)

@router.get("/patterns")
async def brain_patterns_list(
    pattern_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Universal organizational patterns — governance-scoped, evidence-backed."""
    return await pattern_engine.list_visible(
        db, organization_id=org.id, user=user,
        limit=limit, pattern_type=pattern_type, status=status,
    )


@router.get("/patterns/{pattern_id}")
async def brain_pattern_get(
    pattern_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await pattern_engine.get_visible(
        db, organization_id=org.id, user=user, pattern_id=pattern_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="pattern not found")
    return result


@router.patch("/patterns/{pattern_id}")
async def brain_pattern_status(
    pattern_id: str,
    body: BrainPatternStatusIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await pattern_engine.set_status(
        db, organization_id=org.id, pattern_id=pattern_id, status=body.status
    )
    if result is None:
        raise HTTPException(status_code=404, detail="pattern not found")
    await db.commit()
    return result


@router.get("/patterns/{pattern_id}/evidence")
async def brain_pattern_evidence(
    pattern_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await pattern_engine.evidence_visible(
        db, organization_id=org.id, user=user, pattern_id=pattern_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="pattern not found")
    return result


@router.get("/patterns/{pattern_id}/history")
async def brain_pattern_history(
    pattern_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await pattern_engine.history_visible(
        db, organization_id=org.id, user=user, pattern_id=pattern_id, limit=limit
    )
    if result is None:
        raise HTTPException(status_code=404, detail="pattern not found")
    return result


@router.get("/patterns/{pattern_id}/related")
async def brain_pattern_related(
    pattern_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await pattern_engine.related_visible(
        db, organization_id=org.id, user=user, pattern_id=pattern_id, limit=limit
    )
    if result is None:
        raise HTTPException(status_code=404, detail="pattern not found")
    return result


# ---------------------------------------------------------------------------
# Slice 4D.5 — universal company insights (governance-scoped, observation only)
# ---------------------------------------------------------------------------


@router.get("/insights")
async def brain_insights_list(
    status: Optional[str] = None,
    insight_type: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Universal company insights — governance-scoped, evidence-backed."""
    return await insight_engine.list_visible(
        db, organization_id=org.id, user=user,
        limit=limit, status=status, insight_type=insight_type, severity=severity,
    )


@router.get("/insights/{insight_id}")
async def brain_insight_get(
    insight_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await insight_engine.get_visible(
        db, organization_id=org.id, user=user, insight_id=insight_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="insight not found")
    return result


@router.get("/insights/{insight_id}/evidence")
async def brain_insight_evidence(
    insight_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await insight_engine.evidence_visible(
        db, organization_id=org.id, user=user, insight_id=insight_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="insight not found")
    return result


@router.get("/insights/{insight_id}/history")
async def brain_insight_history(
    insight_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await insight_engine.history_visible(
        db, organization_id=org.id, user=user, insight_id=insight_id, limit=limit
    )
    if result is None:
        raise HTTPException(status_code=404, detail="insight not found")
    return result


@router.get("/insights/{insight_id}/related")
async def brain_insight_related(
    insight_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await insight_engine.related_visible(
        db, organization_id=org.id, user=user, insight_id=insight_id, limit=limit
    )
    if result is None:
        raise HTTPException(status_code=404, detail="insight not found")
    return result
