"""Phase 20 — Universal Company Brain API.

One surface for the whole organization: the living overview, universal AI,
universal search, living graph, company health, permanent memory, company
timeline, universal context, event stream, analytics and the continuous
evolution cycle. Employees, managers and executives all ask the same brain.
"""

from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.core.timeutils import ensure_aware
from app.db.database import get_db
from app.intelligence.company_brain import MAX_TIMELINE
from app.intelligence.company_context import CallerAccess, resolve_caller_access
from app.intelligence.expertise_engine import expertise_engine
from app.intelligence.graph_engine import graph_engine as company_graph
from app.intelligence.insight_engine import insight_engine
from app.intelligence.ownership_engine import ownership_engine
from app.intelligence.pattern_engine import pattern_engine
from app.kernel.organization_kernel import organization_kernel
from app.knowledge.intelligence_engine import _utcnow_iso
from app.knowledge.synthesis_engine import _json_loads
from app.models.knowledge import KnowledgeTopic
from app.models.organization import Organization
from app.models.user import User
from app.people.capability_engine import capability_engine
from app.people.expertise_search import expertise_search
from app.people.people_engine import PeopleError, people_engine
from app.people.skill_engine import SkillError, skill_engine

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


# -------------------------------------------------------------------- 4F.1 people bodies

class PeopleIdentityLinkIn(BaseModel):
    source: str
    source_key: str
    kind: str = "primary"
    verified: bool = False
    note: Optional[str] = None


class PeopleIdentityResolveIn(BaseModel):
    source: str
    source_key: str


class PeopleMembershipIn(BaseModel):
    employment_status: str
    valid_from: Optional[datetime] = None
    employment_type: Optional[str] = None
    note: Optional[str] = None


class PeopleRoleAssignIn(BaseModel):
    role_title: str
    role_type: str = "functional"
    is_primary: bool = False
    valid_from: Optional[datetime] = None


class PeopleRoleChangeIn(BaseModel):
    role_title: Optional[str] = None
    role_type: Optional[str] = None


class PeopleReportingIn(BaseModel):
    relationship_type: str
    manager_person_id: Optional[str] = None
    valid_from: Optional[datetime] = None


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


class BrainEvidenceIn(BaseModel):
    question: str


# ---------------------------------------------------------------------------
# Slice 4E.3 — universal knowledge understanding & synthesis
# ---------------------------------------------------------------------------


@router.get("/knowledge/topics/{topic_name}/state")
async def brain_knowledge_topic_state(
    topic_name: str,
    as_of: Optional[str] = Query(None, description="ISO date/time — the state valid then (4E.5 temporal knowledge)"),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.3 — the state of a topic: the current understanding, active
    problems, recent decisions, patterns, contradictions and evolution —
    assembled only from evidence the caller may see. Slice 4E.5: with
    ``as_of``, returns the understanding valid at that moment (what was true,
    what replaced it) instead of the current state."""
    if as_of:
        from datetime import datetime

        from app.knowledge.action_engine import action_engine

        try:
            parsed = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="as_of must be an ISO datetime") from exc
        result = await action_engine.state_at(
            db, organization_id=org.id, topic_name=topic_name, as_of=parsed, user=user
        )
        if result is None:
            raise HTTPException(status_code=404, detail="topic not found or no understanding at that time")
        return result
    from app.knowledge.synthesis_engine import synthesis_engine

    result = await synthesis_engine.topic_state(
        db, organization_id=org.id, topic_name=topic_name, user=user
    )
    if result is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return result


@router.get("/knowledge/topics/{topic_name}/current-state")
async def brain_knowledge_topic_current(
    topic_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.3 — knowledge snapshot: what the topic means right now, the
    latest authoritative statement, evidence counts and freshness."""
    from app.knowledge.synthesis_engine import synthesis_engine

    result = await synthesis_engine.current_state(
        db, organization_id=org.id, topic_name=topic_name, user=user
    )
    if result is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return result


@router.get("/knowledge/topics/{topic_name}/timeline")
async def brain_knowledge_topic_timeline(
    topic_name: str,
    limit: int = Query(30, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.3 — how the company's understanding of the topic developed."""
    from app.knowledge.synthesis_engine import synthesis_engine

    result = await synthesis_engine.timeline(
        db, organization_id=org.id, topic_name=topic_name, user=user, limit=limit
    )
    if result is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return result


@router.get("/knowledge/topics/{topic_name}/contradictions")
async def brain_knowledge_topic_contradictions(
    topic_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.3 — facet conflicts among the topic's active evidence and how
    each was resolved (authority, then valid_from)."""
    from app.knowledge.synthesis_engine import synthesis_engine

    result = await synthesis_engine.contradictions(
        db, organization_id=org.id, topic_name=topic_name, user=user
    )
    if result is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return result


@router.get("/knowledge/topics/{topic_name}/evidence")
async def brain_knowledge_topic_evidence(
    topic_name: str,
    question: str = Query(..., min_length=2),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.3 — an evidence-backed answer: a deterministic statement plus
    the exact evidence chain (citations, never opinions)."""
    from app.knowledge.synthesis_engine import synthesis_engine

    result = await synthesis_engine.evidence_answer(
        db, organization_id=org.id, topic_name=topic_name,
        question=question, user=user,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return result


@router.post("/knowledge/topics/{topic_name}/synthesize")
async def brain_knowledge_topic_synthesize(
    topic_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.3 — force one deterministic synthesis pass for a topic
    (idempotent). Normal flow is event-driven; this is for recovery."""
    from app.knowledge.synthesis_engine import synthesis_engine

    topic = (
        await db.execute(
            select(KnowledgeTopic).where(
                KnowledgeTopic.organization_id == org.id,
                KnowledgeTopic.name == topic_name,
            )
        )
    ).scalar_one_or_none()
    if topic is None:
        raise HTTPException(status_code=404, detail="topic not found")
    result = await synthesis_engine.synthesize_topic(
        db, organization_id=org.id, topic_id=topic.id, user=user
    )
    await db.commit()
    return result


@router.get("/knowledge/claims/{claim_id}")
async def brain_knowledge_claim(
    claim_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.3 — one claim with its full relationship graph: supporting and
    contradicting claims, related entities, supersession, evidence citations.
    Hidden claims return 404 — governance constrains retrieval itself."""
    from app.knowledge.synthesis_engine import synthesis_engine

    result = await synthesis_engine.claim_detail(
        db, organization_id=org.id, claim_id=claim_id, user=user
    )
    if result is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return result


# ---------------------------------------------------------------------------
# Slice 4E.4 — knowledge intelligence (discovery, graph, change, impact,
# gaps, confidence, ownership, health, recommendations, universal query)
# ---------------------------------------------------------------------------


@router.get("/knowledge/discover")
async def brain_knowledge_discover(
    query: str = Query(..., min_length=2),
    limit: int = Query(8, ge=1, le=20),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.4 — intelligent discovery: what the company knows about a
    question, with the evidence chain that grounds it (governed)."""
    from app.knowledge.intelligence_engine import intelligence_engine

    return await intelligence_engine.discover(
        db, organization_id=org.id, query=query, user=user, limit=limit
    )


@router.get("/knowledge/entities/{entity_type}/{entity_id}/relations")
async def brain_knowledge_relations(
    entity_type: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.4 — knowledge graph intelligence: every typed edge around one
    entity and each neighbor's canonical claims and topics."""
    from app.knowledge.intelligence_engine import intelligence_engine

    return await intelligence_engine.relationships(
        db, organization_id=org.id, entity_type=entity_type,
        entity_id=entity_id, user=user,
    )


@router.get("/knowledge/changes")
async def brain_knowledge_changes(
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(20, ge=1, le=50),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.4 — change intelligence: what changed in the company's
    understanding recently (new evidence, superseded understandings)."""
    from app.knowledge.intelligence_engine import intelligence_engine

    return await intelligence_engine.changes(
        db, organization_id=org.id, user=user, days=days, limit=limit
    )


@router.get("/knowledge/topics/{topic_name}/impact")
async def brain_knowledge_topic_impact(
    topic_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.4 — impact analysis: if this knowledge changes, what else
    changes (affected entities by family, dependent knowledge claims)."""
    from app.knowledge.intelligence_engine import intelligence_engine

    result = await intelligence_engine.impact(
        db, organization_id=org.id, topic_name=topic_name, user=user
    )
    if result is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return result


@router.get("/knowledge/gaps")
async def brain_knowledge_gaps(
    limit: int = Query(30, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.4 — gap intelligence: stale authoritative knowledge,
    unresolved contradictions, undocumented processes, thin evidence."""
    from app.knowledge.intelligence_engine import intelligence_engine

    return await intelligence_engine.gaps(
        db, organization_id=org.id, user=user, limit=limit
    )


@router.get("/knowledge/claims/{claim_id}/confidence")
async def brain_knowledge_claim_confidence(
    claim_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.4 — explainable confidence: every factor behind a claim's
    confidence with its weight, sign and reason."""
    from app.knowledge.intelligence_engine import intelligence_engine

    result = await intelligence_engine.confidence(
        db, organization_id=org.id, claim_id=claim_id, user=user
    )
    if result is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return result


@router.get("/knowledge/topics/{topic_name}/ownership")
async def brain_knowledge_topic_ownership(
    topic_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.4 — ownership intelligence: who owns this knowledge, with
    what authority, verified when."""
    from app.knowledge.intelligence_engine import intelligence_engine

    result = await intelligence_engine.ownership(
        db, organization_id=org.id, topic_name=topic_name, user=user
    )
    if result is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return result


@router.get("/knowledge/health")
async def brain_knowledge_health(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.4 — organizational knowledge health: seven explainable bars
    plus the reasons anything is weak."""
    from app.knowledge.intelligence_engine import intelligence_engine

    return await intelligence_engine.health(
        db, organization_id=org.id, user=user
    )


@router.get("/knowledge/recommendations")
async def brain_knowledge_recommendations(
    limit: int = Query(25, ge=1, le=50),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.4 — knowledge recommendations (deterministic, evidence-backed,
    persisted exactly-once; conditions that clear are resolved)."""
    from app.knowledge.intelligence_engine import intelligence_engine

    result = await intelligence_engine.recommendations(
        db, organization_id=org.id, user=user, limit=limit
    )
    await db.commit()
    return result


class BrainKnowledgeQueryIn(BaseModel):
    question: str


class BrainInsightActionIn(BaseModel):
    note: Optional[str] = None


class BrainRecommendationLifecycleIn(BaseModel):
    action: str
    note: Optional[str] = None
    target: Optional[str] = None
    project_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Slice 4E.6 — universal company actions (knowledge-to-action, governed)
# ---------------------------------------------------------------------------


class BrainActionProposeIn(BaseModel):
    action_type: str
    title: str
    description: Optional[str] = None
    source_problem: Optional[str] = None
    target: Optional[str] = None
    scope_type: str = "org"
    scope_id: Optional[str] = None
    risk: str = "low"
    due_at: Optional[datetime] = None
    source_recommendation_id: Optional[str] = None
    source_insight_id: Optional[str] = None
    source_event_id: Optional[str] = None
    source_claim_ids: Optional[list[str]] = None
    assignee_id: Optional[str] = None
    approver_id: Optional[str] = None
    depends_on: Optional[list[str]] = None


class BrainActionTransitionIn(BaseModel):
    transition: str
    note: Optional[str] = None
    assignee_id: Optional[str] = None
    due_at: Optional[datetime] = None


class BrainActionOutcomeIn(BaseModel):
    outcome_type: str
    verdict: Optional[str] = None
    effectiveness: float = 0.5
    notes: Optional[str] = None
    evidence: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Slice 4E.7 — universal knowledge operating loop (learn / evolve / measure)
# ---------------------------------------------------------------------------


class BrainLoopOutcomeIn(BaseModel):
    """Expected-vs-actual for a verified governed action: recording it runs
    the full learning chain (assessment -> lesson -> knowledge lifecycle ->
    recommendation feedback). Replays are exact-once."""

    action_id: str
    expected_metric: str = "the intended result"
    expected_value: float = 0.0
    actual_value: float = 0.0
    expected_units: Optional[str] = None
    factors: Optional[list[str]] = None
    summary: Optional[str] = None


class BrainLoopAssessIn(BaseModel):
    subject_type: str
    subject_id: str
    expected_metric: str = "the intended result"
    expected_value: float = 0.0
    actual_value: float = 0.0
    expected_units: Optional[str] = None
    factors: Optional[list[str]] = None
    summary: Optional[str] = None


class BrainLoopDecisionOutcomeIn(BaseModel):
    expected_metric: str = "the intended result"
    expected_value: float = 0.0
    actual_value: float = 0.0
    expected_units: Optional[str] = None
    factors: Optional[list[str]] = None
    summary: Optional[str] = None


class BrainLoopImpactIn(BaseModel):
    subject_type: str
    subject_id: str


class BrainLoopContradictionIn(BaseModel):
    authoritative_claim_id: str
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Slice 4E.5 — knowledge intelligence operating layer (knowledge-to-action)
# ---------------------------------------------------------------------------


@router.get("/knowledge/insights")
async def brain_knowledge_insights(
    kind: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="active | acknowledged | resolved"),
    severity: Optional[str] = Query(None),
    limit: int = Query(40, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.5 — universal knowledge insights (12 kinds, exact-once,
    evidence-lineaged, governed): what the company knows MEANS."""
    from app.knowledge.action_engine import action_engine

    result = await action_engine.insights(
        db, organization_id=org.id, user=user,
        kind=kind, status=status, severity=severity, limit=limit,
    )
    await db.commit()
    return result


@router.get("/knowledge/insights/{insight_id}")
async def brain_knowledge_insight_detail(
    insight_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.5 — one insight with its full evidence lineage and audit."""
    from app.knowledge.action_engine import action_engine

    result = await action_engine.insight_detail(
        db, organization_id=org.id, insight_id=insight_id, user=user
    )
    if result is None:
        raise HTTPException(status_code=404, detail="insight not found")
    return result


@router.post("/knowledge/insights/{insight_id}/acknowledge")
async def brain_knowledge_insight_acknowledge(
    insight_id: str,
    body: BrainInsightActionIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.5 — acknowledge an insight (audited; the row is never
    deleted)."""
    from app.knowledge.action_engine import action_engine

    result = await action_engine.acknowledge(
        db, organization_id=org.id, insight_id=insight_id, user=user, note=body.note
    )
    if result is None:
        raise HTTPException(status_code=404, detail="insight not found")
    await db.commit()
    return result


@router.post("/knowledge/insights/{insight_id}/resolve")
async def brain_knowledge_insight_resolve(
    insight_id: str,
    body: BrainInsightActionIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.5 — resolve an insight (audited; conditions that clear are
    resolved by the materializer, this is the explicit user resolution)."""
    from app.knowledge.action_engine import action_engine

    result = await action_engine.resolve(
        db, organization_id=org.id, insight_id=insight_id, user=user, note=body.note
    )
    if result is None:
        raise HTTPException(status_code=404, detail="insight not found")
    await db.commit()
    return result


@router.get("/knowledge/topics/{topic_name}/evolution")
async def brain_knowledge_topic_evolution(
    topic_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.5 — temporal knowledge: the supersession chain (what was
    true, when it changed, what replaced it — old versions never erased)."""
    from app.knowledge.action_engine import action_engine

    result = await action_engine.evolution_trace(
        db, organization_id=org.id, topic_name=topic_name, user=user
    )
    if result is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return result


@router.get("/knowledge/topics/{topic_name}/propagation")
async def brain_knowledge_topic_propagation(
    topic_name: str,
    depth: int = Query(3, ge=1, le=4),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.5 — impact propagation: multi-hop chains from a knowledge
    change through the graph (vendor -> systems -> projects -> customers)."""
    from app.knowledge.action_engine import action_engine

    result = await action_engine.propagation(
        db, organization_id=org.id, topic_name=topic_name, user=user, depth=depth
    )
    if result is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return result


@router.get("/knowledge/coverage")
async def brain_knowledge_coverage(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.5 — knowledge coverage map: per business area, how much of
    the knowledge is authoritative and fresh, and why weak areas are weak."""
    from app.knowledge.action_engine import action_engine

    return await action_engine.coverage(
        db, organization_id=org.id, user=user
    )


@router.get("/knowledge/health-center")
async def brain_knowledge_health_center(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.5 — knowledge health center: 0-100 score, the seven bars,
    and drill-down counts (contradictions, critical gaps, unverified,
    stale, orphan)."""
    from app.knowledge.action_engine import action_engine

    result = await action_engine.health_center(
        db, organization_id=org.id, user=user
    )
    await db.commit()
    return result


@router.get("/knowledge/brief")
async def brain_knowledge_brief(
    since_hours: int = Query(24, ge=1, le=24 * 30),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.5 — the executive knowledge brief: what changed, what
    emerged, what needs a decision, what is affected — and what needs
    attention first."""
    from app.knowledge.action_engine import action_engine

    result = await action_engine.brief(
        db, organization_id=org.id, user=user, since_hours=since_hours
    )
    await db.commit()
    return result


@router.post("/knowledge/recommendations/{recommendation_id}/lifecycle")
async def brain_knowledge_recommendation_lifecycle(
    recommendation_id: str,
    body: BrainRecommendationLifecycleIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.5 — recommendation lifecycle: review / accept / reject /
    convert (task or decision, through the governed operating layers) /
    execute / verify. The knowledge layer recommends; humans execute."""
    from app.knowledge.action_engine import action_engine

    try:
        result = await action_engine.recommendation_lifecycle(
            db, organization_id=org.id, recommendation_id=recommendation_id,
            user=user, action=body.action, note=body.note,
            target=body.target, project_id=body.project_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    await db.commit()
    return result


@router.get("/knowledge/actions")
async def brain_knowledge_actions(
    state: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    scope_type: Optional[str] = Query(None),
    scope_id: Optional[str] = Query(None),
    risk: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    mine: bool = Query(False),
    attention: bool = Query(False),
    blocked_only: bool = Query(False),
    overdue_only: bool = Query(False),
    escalated_only: bool = Query(False),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.6 — the company action center: every governed action in one
    surface with bounded filters, pagination and state/type stats. Callers
    only ever see the actions their governance grants them."""
    from app.knowledge.action_ops_engine import action_ops_engine

    return await action_ops_engine.center(
        db, organization_id=org.id, user=user,
        state=state, action_type=action_type, scope_type=scope_type,
        scope_id=scope_id, risk=risk, assignee_id=assignee_id,
        mine=mine, attention=attention, blocked_only=blocked_only,
        overdue_only=overdue_only, escalated_only=escalated_only,
        search=search, limit=limit, offset=offset,
    )


@router.get("/knowledge/actions/outcome-intelligence")
async def brain_knowledge_action_outcome_intelligence(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.6 — what the company's actions achieve: effectiveness by
    outcome type, action type and risk, feeding back into intelligence."""
    from app.knowledge.action_ops_engine import action_ops_engine

    return await action_ops_engine.outcome_intelligence(
        db, organization_id=org.id
    )


@router.post("/knowledge/actions/evaluate")
async def brain_knowledge_actions_evaluate(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.6 — one idempotent bounded operational pass: expire stale
    approvals, escalate overdue / long-blocked actions, reflect completion
    from routed operating artifacts. Replay-safe."""
    from app.knowledge.action_ops_engine import action_ops_engine

    result = await action_ops_engine.evaluate(db, organization_id=org.id, user=user)
    await db.commit()
    return result


@router.post("/knowledge/actions", status_code=201)
async def brain_knowledge_action_propose(
    body: BrainActionProposeIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.6 — propose a governed company action from the knowledge
    layer. Exact-once by fingerprint; policy applies immediately (low risk
    auto-approves and routes, medium/high wait for approval)."""
    from app.knowledge.action_ops_engine import action_ops_engine

    try:
        result = await action_ops_engine.propose(
            db, organization_id=org.id, user=user,
            action_type=body.action_type, title=body.title,
            description=body.description, source_problem=body.source_problem,
            target=body.target, scope_type=body.scope_type, scope_id=body.scope_id,
            risk=body.risk, due_at=body.due_at,
            source_recommendation_id=body.source_recommendation_id,
            source_insight_id=body.source_insight_id,
            source_event_id=body.source_event_id,
            source_claim_ids=body.source_claim_ids,
            assignee_id=body.assignee_id, approver_id=body.approver_id,
            depends_on=body.depends_on,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=400, detail="action not created")
    await db.commit()
    return result


@router.get("/knowledge/actions/{action_id}")
async def brain_knowledge_action_detail(
    action_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.6 — one action with its full lineage (recommendation,
    insight, claims), immutable audit trail, dependency status and outcome."""
    from app.knowledge.action_ops_engine import action_ops_engine

    result = await action_ops_engine.detail(
        db, organization_id=org.id, action_id=action_id, user=user
    )
    if result is None:
        raise HTTPException(status_code=404, detail="action not found")
    return result


@router.post("/knowledge/actions/{action_id}/transition")
async def brain_knowledge_action_transition(
    action_id: str,
    body: BrainActionTransitionIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.6 — one governed transition surface: assign / start / block /
    unblock / complete / verify / fail / cancel / supersede. Every call is
    audited immutably; actions are never deleted."""
    from app.knowledge.action_ops_engine import action_ops_engine

    try:
        result = await action_ops_engine.transition(
            db, organization_id=org.id, action_id=action_id, user=user,
            transition=body.transition, note=body.note,
            assignee_id=body.assignee_id, due_at=body.due_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="action not found")
    await db.commit()
    return result


@router.post("/knowledge/actions/{action_id}/outcome")
async def brain_knowledge_action_outcome(
    action_id: str,
    body: BrainActionOutcomeIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.6 — record what the verified action actually achieved, with
    evidence flowing back into company intelligence."""
    from app.knowledge.action_ops_engine import action_ops_engine

    try:
        result = await action_ops_engine.record_outcome(
            db, organization_id=org.id, action_id=action_id, user=user,
            outcome_type=body.outcome_type, verdict=body.verdict,
            effectiveness=body.effectiveness, notes=body.notes,
            evidence=body.evidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="action not found")
    await db.commit()
    return result


# ---------------------------------------------------- 4E.7 knowledge loop


@router.get("/knowledge/loop/learning")
async def brain_knowledge_loop_learning(
    kind: Optional[str] = Query(None),
    limit: int = Query(40, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — the company's learning feed: every lesson the company
    learned, with its evidence, governance-filtered."""
    from app.knowledge.learning_engine import learning_engine

    result = await learning_engine.learning_feed(
        db, organization_id=org.id, user=user, kind=kind, limit=limit,
    )
    await db.commit()
    return result


@router.get("/knowledge/loop/learning/{learning_id}")
async def brain_knowledge_loop_learning_detail(
    learning_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — one lesson with its full evidence trail."""
    from app.knowledge.learning_engine import learning_engine

    feed = await learning_engine.learning_feed(
        db, organization_id=org.id, user=user, limit=100,
    )
    item = next((i for i in feed["items"] if i["id"] == learning_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="learning not found")
    return item


@router.post("/knowledge/loop/outcomes")
async def brain_knowledge_loop_outcome(
    body: BrainLoopOutcomeIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — close the loop for a governed action: record what was
    expected vs what actually happened, then learn from it (assessment ->
    lesson with evidence -> canonical knowledge lifecycle -> recommendation
    feedback). Idempotent: replaying never duplicates."""
    from app.knowledge.learning_engine import learning_engine

    try:
        assessment = await learning_engine.assess_outcome(
            db, organization_id=org.id,
            subject_type="action", subject_id=body.action_id,
            expected_metric=body.expected_metric, expected_value=body.expected_value,
            actual_value=body.actual_value, expected_units=body.expected_units,
            factors=body.factors, summary=body.summary, user=user,
        )
        learning = await learning_engine.learn_from_outcome(
            db, organization_id=org.id, action_id=body.action_id, user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {**learning, "assessment": assessment}


@router.post("/knowledge/loop/assessments")
async def brain_knowledge_loop_assess(
    body: BrainLoopAssessIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — record one expected-vs-actual assessment (no learning):
    idempotent upsert per (subject_type, subject_id)."""
    from app.knowledge.learning_engine import learning_engine

    try:
        result = await learning_engine.assess_outcome(
            db, organization_id=org.id,
            subject_type=body.subject_type, subject_id=body.subject_id,
            expected_metric=body.expected_metric, expected_value=body.expected_value,
            actual_value=body.actual_value, expected_units=body.expected_units,
            factors=body.factors, summary=body.summary, user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return result


@router.get("/knowledge/loop/assessments")
async def brain_knowledge_loop_assessments(
    subject_type: Optional[str] = Query(None),
    subject_id: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — the outcome ledger: every expected-vs-actual assessment."""
    from app.models.organizational_learning import OutcomeAssessment

    statement = (
        select(OutcomeAssessment)
        .where(OutcomeAssessment.organization_id == org.id)
        .order_by(OutcomeAssessment.assessed_at.desc())
        .limit(100)
    )
    if subject_type:
        statement = statement.where(OutcomeAssessment.subject_type == subject_type)
    if subject_id:
        statement = statement.where(OutcomeAssessment.subject_id == subject_id)
    rows = list((await db.execute(statement)).scalars().all())
    return {
        "assessments": [
            {
                "id": r.id,
                "subject_type": r.subject_type,
                "subject_id": r.subject_id,
                "expected_metric": r.expected_metric,
                "expected_value": r.expected_value,
                "expected_units": r.expected_units,
                "actual_value": r.actual_value,
                "variance_pct": r.variance_pct,
                "assessment": r.assessment,
                "factors": _json_loads(r.factors_json, []),
                "summary": r.summary,
                "assessed_by": r.assessed_by,
                "assessed_at": ensure_aware(r.assessed_at).isoformat(),
            }
            for r in rows
        ],
        "total": len(rows),
        "generated_at": _utcnow_iso(),
    }


@router.post("/knowledge/loop/decisions/{decision_id}/outcome")
async def brain_knowledge_loop_decision_outcome(
    decision_id: str,
    body: BrainLoopDecisionOutcomeIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — decision feedback loop: a decision's expected vs actual
    result becomes a measured decision outcome + a lesson."""
    from app.knowledge.learning_engine import learning_engine

    try:
        result = await learning_engine.learn_from_decision(
            db, organization_id=org.id, decision_id=decision_id,
            expected_metric=body.expected_metric, expected_value=body.expected_value,
            actual_value=body.actual_value, expected_units=body.expected_units,
            factors=body.factors, summary=body.summary, user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return result


@router.get("/knowledge/loop/decisions")
async def brain_knowledge_loop_decisions(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — decision performance: every measured decision outcome."""
    from app.models.organizational_learning import DecisionOutcome

    rows = list(
        (
            await db.execute(
                select(DecisionOutcome)
                .where(DecisionOutcome.organization_id == org.id)
                .order_by(DecisionOutcome.measured_at.desc())
                .limit(100)
            )
        ).scalars().all()
    )
    return {
        "decisions": [
            {
                "id": r.id,
                "decision_id": r.decision_id,
                "expected_metric": r.expected_metric,
                "expected_value": r.expected_value,
                "expected_units": r.expected_units,
                "actual_value": r.actual_value,
                "variance_pct": r.variance_pct,
                "assessment": r.assessment,
                "outcome_type": r.outcome_type,
                "factors": _json_loads(r.factors_json, []),
                "summary": r.summary,
                "measured_by": r.measured_by,
                "measured_at": ensure_aware(r.measured_at).isoformat(),
            }
            for r in rows
        ],
        "total": len(rows),
        "generated_at": _utcnow_iso(),
    }


@router.get("/knowledge/loop/recommendation-quality")
async def brain_knowledge_loop_recommendation_quality(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — deterministic per-kind recommendation quality from the
    outcome ledger: explainable, auditable, never a silent rewrite."""
    from app.knowledge.learning_engine import learning_engine

    return await learning_engine.recommendation_quality(db, organization_id=org.id)


@router.post("/knowledge/loop/contradictions/{topic_name}/resolution")
async def brain_knowledge_loop_contradiction_resolution(
    topic_name: str,
    body: BrainLoopContradictionIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — settle a contradiction by authority: the authoritative
    claim is retained and advanced, losing evidence stays as historical
    truth, and the resolution is learned."""
    from app.knowledge.learning_engine import learning_engine

    try:
        result = await learning_engine.record_contradiction_resolution(
            db, organization_id=org.id, topic_name=topic_name,
            authoritative_claim_id=body.authoritative_claim_id,
            user=user, reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return result


@router.get("/knowledge/loop/changes")
async def brain_knowledge_loop_changes(
    since_hours: int = Query(24, ge=1, le=24 * 30),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — company "what changed?" feed: deterministically
    materialized, exact-once, grouped critical / important / normal."""
    from app.knowledge.learning_engine import learning_engine

    result = await learning_engine.company_changes(
        db, organization_id=org.id, since_hours=since_hours, user=user,
    )
    await db.commit()
    return result


@router.get("/knowledge/loop/health")
async def brain_knowledge_loop_health(
    window_hours: int = Query(24, ge=1, le=24 * 30),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — company health: ten explainable dimensions where every
    signal carries metric + evidence + time window + confidence + explanation."""
    from app.knowledge.learning_engine import learning_engine

    result = await learning_engine.company_health(
        db, organization_id=org.id, user=user, window_hours=window_hours,
    )
    await db.commit()
    return result


@router.post("/knowledge/loop/impact")
async def brain_knowledge_loop_impact(
    body: BrainLoopImpactIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — company-wide impact analysis: "if we change X, what does
    it reach?" Direct/indirect reach, risks, owners, customers, deadlines,
    financial assumptions and mitigations — governance-filtered, persisted."""
    from app.knowledge.learning_engine import learning_engine

    try:
        result = await learning_engine.impact_analysis(
            db, organization_id=org.id,
            subject_type=body.subject_type, subject_id=body.subject_id, user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return result


@router.get("/knowledge/loop/insights")
async def brain_knowledge_loop_insights(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — the Universal Action Center: one consolidated governed
    board (critical issues, recommended actions, pending approvals, knowledge
    gaps, contradictions, emerging risks, overdue actions, decisions awaiting
    attention, customer-impacting changes, learning opportunities)."""
    from app.knowledge.learning_engine import learning_engine

    result = await learning_engine.operating_insights(
        db, organization_id=org.id, user=user,
    )
    await db.commit()
    return result


@router.get("/knowledge/loop/insights/{insight_id}")
async def brain_knowledge_loop_insight_detail(
    insight_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — one operating insight with its why/impact/evidence."""
    from app.knowledge.learning_engine import learning_engine

    result = await learning_engine.insight_detail(
        db, organization_id=org.id, insight_id=insight_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="insight not found")
    return result


@router.post("/knowledge/loop/insights/{insight_id}/resolve")
async def brain_knowledge_loop_insight_resolve(
    insight_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — governed human resolution of an operating insight (never
    deleted, always audited with the acting user)."""
    from app.knowledge.learning_engine import learning_engine

    result = await learning_engine.resolve_insight(
        db, organization_id=org.id, insight_id=insight_id, user=user,
    )
    await db.commit()
    return result


@router.get("/knowledge/loop/explain")
async def brain_knowledge_loop_explain(
    subject_type: str = Query(...),
    subject_id: str = Query(...),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — 'why?': a subject's state decomposed into explicit
    reasons, each backed by evidence the caller may see."""
    from app.knowledge.learning_engine import learning_engine

    return await learning_engine.explain(
        db, organization_id=org.id, subject_type=subject_type,
        subject_id=subject_id, user=user,
    )


@router.get("/knowledge/loop/authorization")
async def brain_knowledge_loop_authorization(
    risk: str = Query(...),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.7 — the risk ladder: LOW automatic, MEDIUM approval, HIGH
    explicit human authorization."""
    from app.knowledge.learning_engine import learning_engine

    try:
        return await learning_engine.authorization_for(db, organization_id=org.id, risk=risk)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/knowledge/query")
async def brain_knowledge_query(
    body: BrainKnowledgeQueryIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4E.4 — universal company knowledge query: natural questions route
    to the right intelligence; every answer is grounded and governed."""
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    from app.knowledge.intelligence_engine import intelligence_engine

    return await intelligence_engine.query(
        db, organization_id=org.id, question=body.question, user=user
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


# ---------------------------------------------------------------------------
# Slice 4F.1 — Universal People Intelligence Foundation
# ---------------------------------------------------------------------------
# One governed people surface for the brain: canonical person profiles,
# identity resolution, temporal membership/roles/reporting, the living org
# chart, the People Graph and unit rollups. Access is resolved before data is
# assembled (CallerAccess), writes are temporal-window operations (history is
# never destroyed) and every entry lands in the append-only people timeline.

async def _people_access(db: AsyncSession, org: Organization, user: User) -> CallerAccess:
    return await resolve_caller_access(db, organization_id=org.id, user=user)


@router.get("/people")
async def brain_people_list(
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The governed people directory of the organization."""
    access = await _people_access(db, org, user)
    return await people_engine.list_people(
        db, organization_id=org.id, access=access, query=q, limit=limit
    )


@router.get("/people/search")
async def brain_people_search(
    q: str = Query(..., max_length=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Governed people/team/department search for brain mentions."""
    access = await _people_access(db, org, user)
    return await people_engine.search(db, organization_id=org.id, access=access, q=q)


@router.get("/people/{person_id}")
async def brain_people_get(
    person_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Canonical person profile: current membership, open roles, reporting,
    identity links — everything 4F.2-4F.6 will attach to."""
    access = await _people_access(db, org, user)
    try:
        return await people_engine.get_profile(
            db, organization_id=org.id, access=access, person_id=person_id
        )
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/people/{person_id}/history")
async def brain_people_history(
    person_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Full temporal history: membership windows, role windows, reporting
    windows and the append-only people timeline."""
    access = await _people_access(db, org, user)
    try:
        return await people_engine.get_profile(
            db, organization_id=org.id, access=access, person_id=person_id,
            include_history=True,
        )
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/people/{person_id}/at")
async def brain_people_as_of(
    person_id: str,
    at: Optional[datetime] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Temporal reconstruction: the person's world at one moment in time."""
    access = await _people_access(db, org, user)
    try:
        return await people_engine.as_of(
            db, organization_id=org.id, access=access, person_id=person_id,
            at=at or ensure_aware(datetime.utcnow()),
        )
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/people/{person_id}/reporting-line")
async def brain_people_reporting_line(
    person_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The chain of managers above a person."""
    access = await _people_access(db, org, user)
    try:
        return await people_engine.reporting_line(
            db, organization_id=org.id, access=access, person_id=person_id
        )
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/people/{person_id}/related")
async def brain_people_related(
    person_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Why is this person related to everyone else? Deterministic relations
    with an explicit reason for each pair."""
    access = await _people_access(db, org, user)
    try:
        return await people_engine.related_people(
            db, organization_id=org.id, access=access, person_id=person_id
        )
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post("/people/{person_id}/identities")
async def brain_people_identity_link(
    person_id: str,
    payload: PeopleIdentityLinkIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Link one strong identifier to one canonical person. A key already
    active on another person is refused — ambiguity is never silently merged."""
    try:
        result = await people_engine.register_identity(
            db, organization_id=org.id, person_id=person_id,
            source=payload.source, source_key=payload.source_key,
            kind=payload.kind, verified=payload.verified, note=payload.note,
            actor_id=(await _people_access(db, org, user)).employee_id,
        )
        await db.commit()
        return result
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post("/people/identities/resolve")
async def brain_people_identity_resolve(
    payload: PeopleIdentityResolveIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Resolve one strong identifier to the canonical person — or admit the
    identifier is unknown/retired. Never merges ambiguity."""
    return await people_engine.resolve_identity(
        db, organization_id=org.id, source=payload.source, source_key=payload.source_key
    )


@router.put("/people/{person_id}/membership")
async def brain_people_membership(
    person_id: str,
    payload: PeopleMembershipIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Open a new membership window (previous open window is closed, never
    deleted). Mirrors the mapped employee status when applicable."""
    try:
        result = await people_engine.set_membership(
            db, organization_id=org.id, person_id=person_id,
            employment_status=payload.employment_status,
            valid_from=payload.valid_from,
            employment_type=payload.employment_type,
            note=payload.note,
            source_type="people.membership", source_id=person_id,
            actor_id=(await _people_access(db, org, user)).employee_id,
        )
        await db.commit()
        return result
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post("/people/{person_id}/roles")
async def brain_people_role_assign(
    person_id: str,
    payload: PeopleRoleAssignIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Assign a temporal role window. Many roles per person; at most one open
    primary (assigning a new primary demotes the previous one)."""
    try:
        result = await people_engine.assign_role(
            db, organization_id=org.id, person_id=person_id,
            role_title=payload.role_title, role_type=payload.role_type,
            is_primary=payload.is_primary, valid_from=payload.valid_from,
            source_type="people.role", source_id=person_id,
            actor_id=(await _people_access(db, org, user)).employee_id,
        )
        await db.commit()
        return result
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post("/people/roles/{assignment_id}/change")
async def brain_people_role_change(
    assignment_id: str,
    payload: PeopleRoleChangeIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Change a role: the old window closes, a continuation window opens —
    the role history is preserved."""
    try:
        result = await people_engine.change_role(
            db, organization_id=org.id, assignment_id=assignment_id,
            role_title=payload.role_title, role_type=payload.role_type,
            source_type="people.role", source_id=assignment_id,
            actor_id=(await _people_access(db, org, user)).employee_id,
        )
        await db.commit()
        return result
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post("/people/roles/{assignment_id}/remove")
async def brain_people_role_remove(
    assignment_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Close a role window — the closed window remains in history."""
    try:
        result = await people_engine.remove_role(
            db, organization_id=org.id, assignment_id=assignment_id,
            source_type="people.role", source_id=assignment_id,
            actor_id=(await _people_access(db, org, user)).employee_id,
        )
        await db.commit()
        return result
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post("/people/{person_id}/reporting")
async def brain_people_reporting(
    person_id: str,
    payload: PeopleReportingIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Set (or clear) a temporal reporting relationship. The open reports_to
    window mirrors Employee.manager_id so the live org chart stays coherent."""
    try:
        result = await people_engine.set_reporting(
            db, organization_id=org.id, person_id=person_id,
            relationship_type=payload.relationship_type,
            manager_person_id=payload.manager_person_id,
            valid_from=payload.valid_from,
            source_type="people.reporting", source_id=person_id,
            actor_id=(await _people_access(db, org, user)).employee_id,
        )
        await db.commit()
        return result
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/org/chart")
async def brain_org_chart(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The living org chart from current open reports_to windows. Invisible
    subordinates are never revealed to scoped callers."""
    access = await _people_access(db, org, user)
    return await people_engine.org_chart(db, organization_id=org.id, access=access)


@router.get("/org/graph")
async def brain_org_graph(
    depth: int = Query(default=3, ge=1, le=8),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The People Graph: person + team + department + role nodes with
    reporting / membership edges — fully governed."""
    access = await _people_access(db, org, user)
    return await people_engine.people_graph(
        db, organization_id=org.id, access=access, depth=depth
    )


@router.get("/org/units")
async def brain_org_units(
    unit_kind: str = Query(..., pattern="^(team|department|business_unit|location)$"),
    unit_id: str = Query(...),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Members of a team / department / business_unit / location."""
    access = await _people_access(db, org, user)
    try:
        return await people_engine.unit_members(
            db, organization_id=org.id, access=access, unit_kind=unit_kind, unit_id=unit_id
        )
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/org/units/summary")
async def brain_org_units_summary(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Departments and teams with governed member counts."""
    access = await _people_access(db, org, user)
    return await people_engine.units_summary(db, organization_id=org.id, access=access)


# ---------------------------------------------------------------------------
# Slice 4F.2 — Universal Skills & Expertise Intelligence
#
# One governed expertise surface. Everything is evidence-derived and
# explainable: skills (associations) never grant expertise; expertise never
# exists without canonical evidence; every claim carries lineage; reads are
# governance-scoped before data assembly; aggregates are gated per scope so
# hidden people never leak through counts or rankings.
# ---------------------------------------------------------------------------


class PersonSkillDeclareIn(BaseModel):
    name: Optional[str] = None
    skill_id: Optional[str] = None
    level: int = 2
    source: str = "declared"


async def _require_visible_person(
    db: AsyncSession, org: Organization, access: CallerAccess, person_id: str,
) -> dict[str, Any]:
    try:
        return await people_engine.get_profile(
            db, organization_id=org.id, access=access, person_id=person_id
        )
    except PeopleError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


async def _require_scope_visibility(
    db: AsyncSession, org: Organization, access: CallerAccess,
    scope_type: str, scope_id: str,
) -> None:
    """Aggregates are only served when the caller can see the whole scope —
    a hidden member must never leak through a count or a ranking."""
    from app.models.employee import Employee

    if scope_type == "team":
        from app.models.team import Team

        exists = (
            await db.execute(
                select(Team.id).where(
                    Team.organization_id == org.id, Team.id == scope_id
                )
            )
        ).scalar_one_or_none()
    elif scope_type == "department":
        from app.models.department import Department

        exists = (
            await db.execute(
                select(Department.id).where(
                    Department.organization_id == org.id,
                    Department.id == scope_id,
                )
            )
        ).scalar_one_or_none()
    else:
        exists = None
    if scope_type in ("team", "department") and exists is None:
        raise HTTPException(status_code=404, detail="scope not found")

    if access.org_wide:
        return
    visible = await people_engine.visible_person_ids(
        db, organization_id=org.id, access=access
    )
    if scope_type == "team":
        from app.models.team import TeamMember

        member_ids = set(
            (
                await db.execute(
                    select(TeamMember.employee_id).where(
                        TeamMember.organization_id == org.id, TeamMember.team_id == scope_id
                    )
                )
            ).scalars().all()
        )
        employee_ids = set(
            (
                await db.execute(
                    select(Employee.id).where(
                        Employee.organization_id == org.id, Employee.team_id == scope_id
                    )
                )
            ).scalars().all()
        )
        member_ids |= employee_ids
    elif scope_type == "department":
        member_ids = set(
            (
                await db.execute(
                    select(Employee.id).where(
                        Employee.organization_id == org.id,
                        Employee.department_id == scope_id,
                    )
                )
            ).scalars().all()
        )
    else:
        member_ids: set[str] = set()
    if member_ids and (visible is None or member_ids <= set(visible)):
        return
    raise HTTPException(status_code=404, detail="scope not found")


@router.get("/expertise/skills")
async def brain_expertise_skills(
    q: Optional[str] = Query(default=None, max_length=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The canonical skill taxonomy with aliases and parents."""
    await skill_engine.ensure_taxonomy(db, organization_id=org.id)
    entries = await skill_engine.list_taxonomy(
        db, organization_id=org.id
    )
    if q:
        wanted = await expertise_search.resolve_for_query(
            db, organization_id=org.id, query=q
        )
        wanted_ids = {s.id for s in wanted}
        entries = [e for e in entries if e["skill_id"] in wanted_ids]
    return {
        "total": len(entries),
        "skills": entries,
        "generated_at": _utcnow_iso(),
    }


@router.get("/expertise/search")
async def brain_expertise_search(
    q: str = Query(..., max_length=200),
    scope_type: Optional[str] = Query(default=None, pattern="^(team|department|business_unit)$"),
    scope_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    recent_only: bool = Query(default=False),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Governed ranked expert discovery: expertise + confidence + recency +
    evidence count + organizational scope — never keyword matching alone.
    ``recent_only`` narrows to people with demonstrated evidence in the last
    180 days (Slice 4F.3 "who has shown it recently" question)."""
    access = await _people_access(db, org, user)
    return await expertise_search.search(
        db, organization_id=org.id, access=access, query=q,
        scope_type=scope_type, scope_id=scope_id, limit=limit,
        recent_only=recent_only,
    )


@router.get("/expertise/skills/{skill_id}")
async def brain_expertise_skill_detail(
    skill_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One canonical skill: taxonomy view + its strongest visible experts."""
    from app.models.skills_intelligence import CanonicalSkill

    skill = await db.get(CanonicalSkill, skill_id)
    if skill is None or skill.organization_id != org.id:
        raise HTTPException(status_code=404, detail="skill not found")
    access = await _people_access(db, org, user)
    experts = await expertise_search.search(
        db, organization_id=org.id, access=access,
        query=skill.canonical_name, limit=10,
    )
    return {
        "skill_id": skill.id,
        "canonical_name": skill.canonical_name,
        "description": skill.description,
        "category": skill.category,
        "status": skill.status,
        "provenance": skill.provenance,
        "level": skill.level,
        "experts": experts["experts"],
        "expert_total": experts["total"],
        "generated_at": _utcnow_iso(),
    }


@router.get("/expertise/teams/{team_id}")
async def brain_expertise_team(
    team_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Team capability map from bounded indexed aggregates (gated by scope)."""
    access = await _people_access(db, org, user)
    await _require_scope_visibility(db, org, access, "team", team_id)
    return await capability_engine.team_map(
        db, organization_id=org.id, team_id=team_id
    )


@router.get("/expertise/departments/{department_id}")
async def brain_expertise_department(
    department_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Department capability map from bounded indexed aggregates (gated)."""
    access = await _people_access(db, org, user)
    await _require_scope_visibility(db, org, access, "department", department_id)
    return await capability_engine.department_map(
        db, organization_id=org.id, department_id=department_id
    )


@router.get("/expertise/organization")
async def brain_expertise_organization(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The organization-level capability map. Org-wide callers only: the
    rollup covers every member, so it must never leak to scoped callers."""
    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    return await capability_engine.org_map(
        db, organization_id=org.id
    )


@router.get("/people/{person_id}/skills")
async def brain_people_skills(
    person_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Skill associations of a person (declared + observed) with the current
    evidence-derived overlay. Associations are never expertise."""
    access = await _people_access(db, org, user)
    await _require_visible_person(db, org, access, person_id)
    return await expertise_search.person_skills(
        db, organization_id=org.id, person_id=person_id
    )


@router.post("/people/{person_id}/skills")
async def brain_people_skills_declare(
    person_id: str,
    payload: PersonSkillDeclareIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Declared association — never expertise. The skill is resolved through
    the canonical taxonomy (name or skill_id) and mirrored into the legacy
    operating layer; no evidence dimension moves."""
    access = await _people_access(db, org, user)
    await _require_visible_person(db, org, access, person_id)
    try:
        if payload.skill_id:
            from app.models.skills_intelligence import CanonicalSkill

            skill = await db.get(CanonicalSkill, payload.skill_id)
            if skill is None or skill.organization_id != org.id:
                raise SkillError("skill not found")
        elif payload.name:
            skill = await skill_engine.get_or_create_for_declared(
                db, organization_id=org.id, name=payload.name,
                created_by=user.id,
            )
        else:
            raise SkillError("name or skill_id is required")
        level = max(1, min(5, payload.level))
        association = await skill_engine.bump_person_skill(
            db, organization_id=org.id, person_id=person_id,
            skill_id=skill.id, source="declared" if payload.source == "declared" else "signaled",
            declared_level=level, created_by=user.id,
        )
        # legacy compatibility mirror (operating layer keeps working)
        from app.models.employee import Employee, EmployeeSkill
        from app.models.skill import Skill as LegacySkill
        from app.people.expertise_service import expertise_service

        legacy = await expertise_service.create_skill(
            db, organization_id=org.id,
            data={"name": skill.canonical_name, "category": skill.category,
                  "description": skill.description},
        )
        existing_emp_skill = (
            await db.execute(
                select(EmployeeSkill).where(
                    EmployeeSkill.organization_id == org.id,
                    EmployeeSkill.employee_id == person_id,
                    EmployeeSkill.skill_id == legacy.id,
                )
            )
        ).scalar_one_or_none()
        if existing_emp_skill is None:
            db.add(EmployeeSkill(
                organization_id=org.id,
                employee_id=person_id,
                skill_id=legacy.id,
                level=level,
                years_experience=0.0,
                verified=False,
            ))
        await db.commit()
    except SkillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "person_id": person_id,
        "skill_id": skill.id,
        "skill_name": skill.canonical_name,
        "category": skill.category,
        "declared_level": level,
        "source": association.source,
        "status": association.status,
        "first_seen": association.first_seen.isoformat(),
        "last_seen": association.last_seen.isoformat(),
    }


async def _resolve_state_skill(
    db: AsyncSession, org: Organization, skill_id: str,
) -> str:
    """Slice 4F.3 — a skill reference may arrive as a canonical skill id (the
    evidence engine) OR a legacy skill id (the profile/phase-2 surfaces); the
    canonical cell is resolved deterministically, never guessed."""
    from app.models.skills_intelligence import CanonicalSkill
    from app.models.skill import Skill

    canonical = (
        await db.execute(
            select(CanonicalSkill).where(
                CanonicalSkill.organization_id == org.id, CanonicalSkill.id == skill_id
            )
        )
    ).scalar_one_or_none()
    if canonical is not None:
        return canonical.id
    legacy: Optional[Skill] = await db.get(Skill, skill_id)
    if legacy is not None and legacy.organization_id == org.id:
        aliased = (
            await db.execute(
                select(CanonicalSkill).where(
                    CanonicalSkill.organization_id == org.id,
                    CanonicalSkill.canonical_name == legacy.name,
                )
            )
        ).scalar_one_or_none()
        if aliased is not None:
            return aliased.id
    return skill_id


@router.get("/people/{person_id}/expertise")
async def brain_people_expertise(
    person_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Evidence-derived expertise of a person, strongest first."""
    access = await _people_access(db, org, user)
    await _require_visible_person(db, org, access, person_id)
    return await expertise_search.person_expertise(
        db, organization_id=org.id, person_id=person_id
    )


@router.get("/people/{person_id}/expertise/{skill_id}")
async def brain_people_expertise_skill(
    person_id: str,
    skill_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The defensible state of one (person x skill) cell: dimensions + score
    + confidence + lifecycle."""
    access = await _people_access(db, org, user)
    await _require_visible_person(db, org, access, person_id)
    skill_id = await _resolve_state_skill(db, org, skill_id)
    state = await expertise_engine.state(
        db, organization_id=org.id, person_id=person_id, skill_id=skill_id
    )
    if state is None:
        raise HTTPException(status_code=404, detail="no expertise state for this skill")
    return state


@router.get("/people/{person_id}/expertise/{skill_id}/evidence")
async def brain_people_expertise_evidence(
    person_id: str,
    skill_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Expertise evidence lineage: every item carries its canonical source
    id (task / document / decision / certificate / event)."""
    access = await _people_access(db, org, user)
    await _require_visible_person(db, org, access, person_id)
    skill_id = await _resolve_state_skill(db, org, skill_id)
    state = await expertise_engine.state(
        db, organization_id=org.id, person_id=person_id, skill_id=skill_id
    )
    if state is None:
        raise HTTPException(status_code=404, detail="no expertise state for this skill")
    items = await expertise_engine.lineage(
        db, organization_id=org.id, person_id=person_id, skill_id=skill_id, limit=limit,
    )
    return {
        "person_id": person_id,
        "skill_id": skill_id,
        "skill_name": state["skill_name"],
        "lifecycle": state["lifecycle"],
        "score": state["score"],
        "confidence": state["confidence"],
        "evidence_total": len(items),
        "evidence": items,
    }


@router.get("/people/{person_id}/expertise/{skill_id}/trust")
async def brain_people_expertise_trust(
    person_id: str,
    skill_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4F.3 — the TRUST profile of one (person x skill) cell.

    WHY VCOS believes it (evidence trail), WHAT supports it (kinds/sources),
    HOW reliable it is (confidence, outcome validation), HOW recent it is
    (freshness), WHAT corroborates it (independent lineages/kinds), and what
    CONTRADICTS it (negative + expired evidence, never hidden)."""
    access = await _people_access(db, org, user)
    await _require_visible_person(db, org, access, person_id)
    skill_id = await _resolve_state_skill(db, org, skill_id)
    profile = await expertise_engine.trust(
        db, organization_id=org.id, person_id=person_id, skill_id=skill_id,
        limit=limit,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="no expertise state for this skill")
    return profile


@router.get("/expertise/evidence/{evidence_id}")
async def brain_expertise_evidence_item(
    evidence_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Slice 4F.3 — one evidence item with full provenance (governed
    drill-down: the item is only served when the subject person is visible
    to the caller)."""
    access = await _people_access(db, org, user)
    item = await expertise_engine.evidence(
        db, organization_id=org.id, evidence_id=evidence_id,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    await _require_visible_person(db, org, access, item["person_id"])
    return item


# ---------------------------------------------------------------------------
# Slice 4F.4 — Ownership & Responsibility Intelligence
# ---------------------------------------------------------------------------
# The governed "who is responsible for what" surface: canonical temporal
# responsibility windows with types, scopes, backups, escalation, full history
# and advisory analysis (mismatch / gap / single-point) that NEVER auto-fixes.


class OwnershipAssignIn(BaseModel):
    object_type: str
    object_id: str
    object_name: Optional[str] = None
    responsibility_type: str = "primary"
    owner_id: str
    scope_id: Optional[str] = None
    backup_owner_id: Optional[str] = None
    declared_start: Optional[datetime] = None
    declared_end: Optional[datetime] = None
    reason: Optional[str] = None


class OwnershipTransferIn(BaseModel):
    object_type: str
    object_id: str
    to_owner_id: str


class OwnershipBackupIn(BaseModel):
    object_type: str
    object_id: str
    backup_owner_id: str


class OwnershipCloseIn(BaseModel):
    object_type: str
    object_id: str
    reason: Optional[str] = None


class OwnershipCoverageIn(BaseModel):
    objects: list[dict[str, Any]]


async def _ownership_access(db: AsyncSession, org: Organization, user: User) -> CallerAccess:
    return await resolve_caller_access(db, organization_id=org.id, user=user)


@router.get("/ownership/objects/{object_type}/{object_id}")
async def brain_ownership_object(
    object_type: str,
    object_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The current responsibility world of one object: primary owner, stacked
    responsibility types, backup and any open advisory signals."""
    from app.intelligence.ownership_engine import OwnershipError, ownership_engine

    access = await _ownership_access(db, org, user)
    current = await ownership_engine.current(
        db, organization_id=org.id, object_type=object_type,
        object_id=object_id, access=access,
    )
    signals = await ownership_engine.signals(
        db, organization_id=org.id, status="open", limit=20,
    )
    object_signals = [
        s for s in signals["signals"]
        if s["object_type"] == object_type and s["object_id"] == object_id
    ]
    return {**current, "signals": object_signals}


@router.get("/ownership/objects/{object_type}/{object_id}/history")
async def brain_ownership_object_history(
    object_type: str,
    object_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Full responsibility history of one object: every assigned/transferred/
    closed window, newest first — "who owned X six months ago"."""
    access = await _ownership_access(db, org, user)
    return await ownership_engine.history(
        db, organization_id=org.id, object_type=object_type,
        object_id=object_id, access=access, limit=limit,
    )


@router.get("/ownership/objects/{object_type}/{object_id}/as-of")
async def brain_ownership_object_as_of(
    object_type: str,
    object_id: str,
    at: Optional[datetime] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Temporal reconstruction: the responsibility world of an object at one
    moment in time (e.g. when an incident happened)."""
    access = await _ownership_access(db, org, user)
    return await ownership_engine.as_of(
        db, organization_id=org.id, object_type=object_type,
        object_id=object_id, at=at or ensure_aware(datetime.utcnow()), access=access,
    )


@router.get("/ownership/objects/{object_type}/{object_id}/continuity")
async def brain_ownership_object_continuity(
    object_type: str,
    object_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Who takes over: primary -> backup -> governed 4C delegation (read-only)
    -> escalation scope. Never invents a successor."""
    access = await _ownership_access(db, org, user)
    return await ownership_engine.continuity(
        db, organization_id=org.id, object_type=object_type,
        object_id=object_id, access=access,
    )


@router.get("/ownership/people/{person_id}/responsibilities")
async def brain_ownership_person_responsibilities(
    person_id: str,
    active_only: bool = True,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Everything one person is responsible for (and has been), plus backup
    roles held."""
    access = await _ownership_access(db, org, user)
    await _require_visible_person(db, org, access, person_id)
    return await ownership_engine.responsibilities_of(
        db, organization_id=org.id, owner_id=person_id,
        access=access, active_only=active_only,
    )


@router.post("/ownership/assign")
async def brain_ownership_assign(
    body: OwnershipAssignIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The governed write: assign (or transfer) a responsibility. History is
    preserved; analysis findings are never auto-applied here."""
    from app.intelligence.ownership_engine import OwnershipError, ownership_engine

    try:
        result = await ownership_engine.record(
            db, organization_id=org.id,
            object_type=body.object_type, object_id=body.object_id,
            object_name=body.object_name, responsibility_type=body.responsibility_type,
            owner_id=body.owner_id, scope_id=body.scope_id,
            backup_owner_id=body.backup_owner_id,
            declared_start=body.declared_start, declared_end=body.declared_end,
            source="declared",
            evidence={"reason": body.reason, "actor": user.id},
            actor_id=user.id,
        )
    except OwnershipError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    await db.commit()
    return result


@router.post("/ownership/transfer")
async def brain_ownership_transfer(
    body: OwnershipTransferIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from app.intelligence.ownership_engine import OwnershipError, ownership_engine

    try:
        result = await ownership_engine.record(
            db, organization_id=org.id,
            object_type=body.object_type, object_id=body.object_id,
            responsibility_type="primary", owner_id=body.to_owner_id,
            source="transfer", evidence={"actor": user.id},
            actor_id=user.id,
        )
    except OwnershipError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    await db.commit()
    return result


@router.post("/ownership/backup")
async def brain_ownership_backup(
    body: OwnershipBackupIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from app.intelligence.ownership_engine import OwnershipError, ownership_engine

    try:
        result = await ownership_engine.set_backup(
            db, organization_id=org.id,
            object_type=body.object_type, object_id=body.object_id,
            backup_owner_id=body.backup_owner_id, actor_id=user.id,
        )
    except OwnershipError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    await db.commit()
    return result


@router.post("/ownership/close")
async def brain_ownership_close(
    body: OwnershipCloseIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from app.intelligence.ownership_engine import ownership_engine

    result = await ownership_engine.close(
        db, organization_id=org.id,
        object_type=body.object_type, object_id=body.object_id,
        responsibility_type="primary", reason=body.reason, actor_id=user.id,
    )
    await db.commit()
    return result


@router.get("/ownership/analyze")
async def brain_ownership_analyze_read(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Advisory analysis (dry run): what the next bounded batch WOULD surface.
    Nothing is persisted."""
    from app.intelligence.ownership_engine import ownership_engine

    candidate_rows = await ownership_engine.active_batch(
        db, organization_id=org.id, offset=offset, limit=limit,
    )
    return {
        "dry_run": True,
        "would_scan": len(candidate_rows),
        "note": "Run POST /ownership/analyze to persist advisory signals.",
    }


@router.post("/ownership/analyze")
async def brain_ownership_analyze_write(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Persist one bounded batch of advisory signals (mismatch / gap /
    single-point). Analysis never changes a responsibility."""
    from app.intelligence.ownership_engine import ownership_engine

    result = await ownership_engine.analyze(
        db, organization_id=org.id, offset=offset, limit=limit,
        commit=True, actor_id=user.id,
    )
    await db.commit()
    return result


@router.get("/ownership/signals")
async def brain_ownership_signals(
    kind: Optional[str] = Query(default=None),
    status: str = Query(default="open"),
    limit: int = Query(default=200, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await ownership_engine.signals(
        db, organization_id=org.id, kind=kind, status=status, limit=limit,
    )


@router.post("/ownership/signals/{signal_id}/resolve")
async def brain_ownership_signal_resolve(
    signal_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from app.intelligence.ownership_engine import OwnershipError, ownership_engine

    try:
        result = await ownership_engine.resolve_signal(
            db, organization_id=org.id, signal_id=signal_id, actor_id=user.id,
        )
    except OwnershipError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    await db.commit()
    return result


@router.get("/ownership/summary")
async def brain_ownership_summary(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One-glance ownership posture: active responsibilities and open signals."""
    return await ownership_engine.summary(db, organization_id=org.id)


@router.post("/ownership/coverage-check")
async def brain_ownership_coverage_check(
    body: OwnershipCoverageIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """For an explicitly named bounded list of objects: which lack a primary
    responsibility? Analysis only — nothing is created."""
    return await ownership_engine.coverage_check(
        db, organization_id=org.id, candidates=body.objects,
    )


# ---------------------------------------------------------------------------
# Slice 4F.5 — Work Collaboration Intelligence
#
# One governed collaboration surface: the canonical Work Collaboration Graph
# (person <-> person, team <-> team, project). Everything is evidence-derived
# and explainable (counters, strength formula, confidence, health, quality,
# monthly evolution); every read is governance-scoped; signals are advisory
# only — nothing here changes people, teams or projects. Bottlenecks are
# "potential concentration risk" findings, never labels; gaps name a missing
# relationship, never a failing team.
# ---------------------------------------------------------------------------


@router.get("/collaboration/overview")
async def brain_collaboration_overview(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One-glance collaboration posture: relationship health distribution,
    strongest pairs, weakening pairs, open advisory signals and org-level
    accumulators."""
    from app.intelligence.work_collaboration_engine import work_collaboration_engine

    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    return await work_collaboration_engine.overview(
        db, organization_id=org.id, access=access,
    )


@router.get("/collaboration/relationships/people/{person_a}/with/{person_b}")
async def brain_collaboration_pair(
    person_a: str,
    person_b: str,
    limit: int = Query(default=10, ge=1, le=50),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One canonical relationship: counters, strength, confidence, health,
    quality, monthly markers, recent evidence and the strength explanation —
    "why does the record say these two collaborate?"."""
    from app.intelligence.work_collaboration_engine import CollaborationError, work_collaboration_engine

    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    for person_id in (person_a, person_b):
        await _require_visible_person(db, org, access, person_id)
    try:
        return await work_collaboration_engine.relationship_detail(
            db, organization_id=org.id, person_a=person_a,
            person_b=person_b, access=access, limit=limit,
        )
    except CollaborationError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/collaboration/people/{person_id}")
async def brain_collaboration_person(
    person_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One person's collaboration world: strongest partners (ranked), their
    relationship record, and the person's share of org collaboration strength
    (concentration context — advisory only)."""
    from app.intelligence.work_collaboration_engine import work_collaboration_engine

    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    await _require_visible_person(db, org, access, person_id)
    return await work_collaboration_engine.person_relationships(
        db, organization_id=org.id, person_id=person_id, access=access, limit=limit,
    )


@router.get("/collaboration/units/{unit_type}/{unit_id}")
async def brain_collaboration_unit(
    unit_type: str,
    unit_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cross-unit collaboration: how strongly a team/department collaborates
    with every other unit, with health and quality per pair."""
    from app.intelligence.work_collaboration_engine import CollaborationError, work_collaboration_engine

    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    try:
        return await work_collaboration_engine.unit_relationships(
            db, organization_id=org.id, unit_type=unit_type,
            unit_id=unit_id, access=access, limit=limit,
        )
    except CollaborationError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/collaboration/projects/{project_id}")
async def brain_collaboration_project(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Project collaboration evidence: top pairs, per-person evidence share,
    and a potential dependency-concentration advisory (never a verdict)."""
    from app.intelligence.work_collaboration_engine import CollaborationError, work_collaboration_engine

    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    try:
        return await work_collaboration_engine.project_view(
            db, organization_id=org.id, project_id=project_id, access=access,
        )
    except CollaborationError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/collaboration/changes")
async def brain_collaboration_changes(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """What changed recently in the collaboration graph: emerging,
    strengthening, weakening and dormant relationships with their evidence —
    "which teams are becoming disconnected" lives here."""
    from app.intelligence.work_collaboration_engine import work_collaboration_engine

    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    return await work_collaboration_engine.changes(
        db, organization_id=org.id, access=access, days=days, limit=limit,
    )


@router.get("/collaboration/signals")
async def brain_collaboration_signals(
    kind: Optional[str] = Query(default=None),
    status: str = Query(default="open"),
    limit: int = Query(default=20, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """All advisory collaboration signals (concentration risk, slowdown,
    negative shift, gap) — findings that never change the organization."""
    from app.intelligence.work_collaboration_engine import work_collaboration_engine

    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    return await work_collaboration_engine.signals(
        db, organization_id=org.id, access=access, kind=kind, status=status, limit=limit,
    )


@router.get("/collaboration/gaps")
async def brain_collaboration_gaps(
    status: str = Query(default="open"),
    limit: int = Query(default=20, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Required-but-low-evidence collaboration between units (e.g. shared
    project work whose pair shows almost no collaboration). A gap names a
    missing relationship — never a failing team."""
    from app.intelligence.work_collaboration_engine import work_collaboration_engine

    return await work_collaboration_engine.signals(
        db, organization_id=org.id, kind="gap", status=status, limit=limit,
    )


@router.get("/collaboration/bottlenecks")
async def brain_collaboration_bottlenecks(
    status: str = Query(default="open"),
    limit: int = Query(default=20, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Potential collaboration concentration risk: people carrying a large
    share of the org's collaboration strength. Advisory — never a label."""
    from app.intelligence.work_collaboration_engine import work_collaboration_engine

    return await work_collaboration_engine.signals(
        db, organization_id=org.id, kind="concentration", status=status, limit=limit,
    )


@router.post("/collaboration/analyze")
async def brain_collaboration_analyze(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One bounded gap-analysis pass (active projects -> shared departments ->
    evidence check). Persists or auto-resolves advisory gap signals only."""
    from app.intelligence.work_collaboration_engine import work_collaboration_engine

    result = await work_collaboration_engine.analyze_gaps(
        db, organization_id=org.id,
    )
    await db.commit()
    return result


@router.post("/collaboration/signals/{signal_id}/resolve")
async def brain_collaboration_signal_resolve(
    signal_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Acknowledge/resolve an advisory signal by id (bounded single lookup).
    Resolving a signal changes nothing in the collaboration graph."""
    from app.intelligence.work_collaboration_engine import work_collaboration_engine

    await work_collaboration_engine.resolve_signal_by_id(
        db, organization_id=org.id, signal_id=signal_id, actor_id=user.id,
    )
    await db.commit()
    return {"resolved": signal_id}


# ---------------------------------------------------------------------------
# Slice 4F.6 — Organizational Capability & Capacity Intelligence
# ---------------------------------------------------------------------------
# One governed surface for the capability record: what the organization can
# do, how much is free right now, where it is concentrated and whether an
# initiative can be taken on. Org-wide views require org-wide governance
# (like the 4F.2 org capability map — a hidden person can never leak through
# a capability rollup). Scoped callers see only the project-anchored
# capability surface, without member counts. Analysis never changes the
# organization: the only write surface acknowledges advisory signals.

MAX_CAPABILITY_INITIATIVE = 50


@router.get("/capabilities/overview")
async def brain_capabilities_overview(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The Organizational Capability Center: lifecycle distribution, strong /
    emerging / constrained capabilities, concentration risks and gaps —
    every row evidence-backed and explainable. Org-wide callers only."""
    from app.intelligence.org_capability_engine import org_capability_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await org_capability_engine.overview(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/capabilities/signals")
async def brain_capabilities_signals(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """All open advisory capability signals (concentration risk, single-person
    dependency, capacity constraint, gaps) — findings that never change the
    organization. Org-wide callers only."""
    from app.intelligence.org_capability_engine import org_capability_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await org_capability_engine.signals(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.patch("/capabilities/signals/{signal_id}/acknowledge")
async def brain_capabilities_signal_acknowledge(
    signal_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Acknowledge an advisory capability signal by id (bounded single
    lookup). Acknowledging changes nothing in the organization."""
    from app.intelligence.org_capability_engine import org_capability_engine

    result = await org_capability_engine.acknowledge_signal(
        db, organization_id=org.id, signal_id=signal_id, noted_by=user.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="signal not found")
    await db.commit()
    return result


@router.get("/capabilities/projects/{project_id}")
async def brain_capabilities_project(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Capabilities evidenced on one project, with lifecycle and free
    capacity — leak-free for scoped callers (no member counts)."""
    from app.intelligence.org_capability_engine import org_capability_engine

    access = await _people_access(db, org, user)
    if not access.org_wide and project_id not in access.project_ids:
        raise HTTPException(status_code=404, detail="scope not found")
    return await org_capability_engine.project_capabilities(
        db, organization_id=org.id, project_id=project_id,
    )


@router.post("/capabilities/initiative")
async def brain_capabilities_initiative(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """"Can we take this on?" — deterministic, evidence-backed capability gap
    analysis for an initiative. Every required capability resolves to the
    canonical taxonomy and answers with its lifecycle, evidence and free
    capacity. Org-wide callers see the full surface; scoped callers only
    the capabilities anchored to their visible projects (no member counts).
    Never a forecast and never a guarantee."""
    from app.intelligence.org_capability_engine import org_capability_engine

    question = str(body.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="question too long")
    access = await _people_access(db, org, user)
    if access.org_wide:
        result = await org_capability_engine.initiative_gap(
            db, organization_id=org.id, question=question, access=access,
        )
    else:
        result = await org_capability_engine.initiative_gap(
            db, organization_id=org.id, question=question, access=access,
        )
        visible: set[str] = set()
        for project_id in list(access.project_ids)[:MAX_CAPABILITY_INITIATIVE]:
            view = await org_capability_engine.project_capabilities(
                db, organization_id=org.id, project_id=project_id,
            )
            visible.update(c["skill_id"] for c in view["capabilities"])
        result["answers"] = [
            a for a in result["answers"] if a["skill_id"] in visible
        ]
        result["total"] = len(result["answers"])
        result["scope"] = "project"
    return {**result, "question": question, "generated_at": _utcnow_iso()}


@router.get("/capabilities/{skill_id}")
async def brain_capabilities_detail(
    skill_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Full evidence-backed detail of one organizational capability: state,
    capacity model, demand, concentration, experts, owners, teams, projects,
    knowledge, history and open signals. Org-wide callers only."""
    from app.intelligence.org_capability_engine import org_capability_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await org_capability_engine.capability_detail(
        db, organization_id=org.id, skill_id=skill_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="capability not found")
    return {**result, "generated_at": _utcnow_iso()}

# ---------------------------------------------------------------------------
# Slice 4F.7 — People Decision Intelligence (the 4F capstone)
#
# "Given all that evidence, what people/organizational decision should we
# consider, and why?" One governed surface that consumes 4F.2 expertise,
# 4F.3 trust, 4F.4 ownership, 4F.5 collaboration and 4F.6 capability &
# capacity to produce an evidence-backed recommendation with alternatives,
# trade-offs, unknowns and confidence — then a HUMAN decides, acts, and the
# outcome becomes evidence for the next decision.
#
# Hard rules (from the 4F.7 directive):
#   * NO employee scores — candidates carry decision-specific evidence only.
#   * Privacy pipeline LOCKED in order: Identity -> Authorization ->
#     Governance scope -> Accessible evidence -> Reasoning -> Answer.
#     Scoped callers only create/view decisions on projects they can see.
#   * HIGH-tier people decisions (hiring, promotion, termination,
#     compensation, disciplinary) are refused: they stay under human
#     governance. Medium-tier writes (lifecycle, outcome) require
#     employees:manage — humans decide, never the system.
# ---------------------------------------------------------------------------

MAX_DECISION_REQUIREMENTS = 12


@router.post("/decisions")
async def brain_decisions_create(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a people decision and reason over it immediately: the request,
    context, requirements -> capabilities, candidate discovery, evidence and
    a recommendation with alternatives, trade-offs and confidence. Project-
    anchored decisions may be created by scoped callers on projects they can
    see; org-wide decisions require org-wide governance."""
    from app.intelligence.people_decision_engine import (
        DECISION_TYPES,
        people_decision_engine,
    )

    decision_type = str(body.get("decision_type", "")).strip()
    if decision_type not in DECISION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"decision_type must be one of: {', '.join(DECISION_TYPES)}",
        )
    requirements = body.get("requirements") or []
    if isinstance(requirements, list) and len(requirements) > MAX_DECISION_REQUIREMENTS:
        raise HTTPException(status_code=400, detail="too many requirements")
    context_type = body.get("context_type") or None
    context_id = body.get("context_id") or None
    access = await _people_access(db, org, user)
    if context_type == "project":
        if not access.org_wide and context_id not in access.project_ids:
            raise HTTPException(status_code=404, detail="scope not found")
    elif context_type in ("org", None):
        if not access.org_wide:
            raise HTTPException(status_code=404, detail="scope not found")
    else:
        if not access.org_wide:
            raise HTTPException(status_code=404, detail="scope not found")
    try:
        view = await people_decision_engine.create_and_evaluate(
            db, organization_id=org.id, actor_id=user.id, body={
                "decision_type": decision_type,
                "objective": str(body.get("objective", "")).strip(),
                "requirements": requirements,
                "context_type": context_type,
                "context_id": context_id,
                "context_label": body.get("context_label"),
                "risk_tier": body.get("risk_tier"),
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {**view, "generated_at": _utcnow_iso()}


@router.get("/decisions")
async def brain_decisions_list(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    lifecycle: Optional[str] = None,
    decision_type: Optional[str] = None,
) -> dict[str, Any]:
    """Recent people decisions. Scoped callers only ever see decisions made
    on projects inside their governance scope (conversation scope leaks
    nothing)."""
    from app.intelligence.people_decision_engine import people_decision_engine

    access = await _people_access(db, org, user)
    result = await people_decision_engine.list(
        db, organization_id=org.id, limit=limit, lifecycle=lifecycle,
        decision_type=decision_type, access=access,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/decisions/{decision_id}")
async def brain_decisions_detail(
    decision_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Full decision record: recommendation, Why, alternatives with
    trade-offs, why-not for others, evidence, bounded what-if runs,
    provenance and the human governance audit trail."""
    from app.intelligence.people_decision_engine import (
        DECISION_TYPES,
        people_decision_engine,
    )

    access = await _people_access(db, org, user)
    view = await _require_visible_decision(db, org, access, decision_id)
    return {**view, "generated_at": _utcnow_iso()}


async def _require_visible_decision(
    db: AsyncSession, org: Organization, access: CallerAccess, decision_id: str,
) -> dict[str, Any]:
    """Governance-scoped decision read: org-wide callers see everything;
    scoped callers only decisions anchored to their visible projects."""
    from app.intelligence.people_decision_engine import people_decision_engine

    if access.org_wide:
        try:
            return await people_decision_engine.view(
                db, organization_id=org.id, decision_id=decision_id
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="decision not found") from exc
    from app.models.people_decision import PeopleDecision

    decision_row = (
        await db.execute(
            select(PeopleDecision).where(
                PeopleDecision.organization_id == org.id,
                PeopleDecision.id == decision_id,
            )
        )
    ).scalar_one_or_none()
    if decision_row is None:
        raise HTTPException(status_code=404, detail="decision not found")
    if (
        decision_row.context_type != "project"
        or decision_row.context_id not in access.project_ids
    ):
        raise HTTPException(status_code=404, detail="scope not found")
    try:
        return await people_decision_engine.view(
            db, organization_id=org.id, decision_id=decision_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="decision not found") from exc


@router.post("/decisions/{decision_id}/lifecycle")
async def brain_decisions_lifecycle(
    decision_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Human-governed lifecycle transition: review -> approve | reject ->
    execute -> verify. Every transition is audit-logged with its actor.
    High-impact people decisions never exist here — they stay in the
    approvals/HR surfaces under people governance."""
    from app.intelligence.people_decision_engine import people_decision_engine

    action = str(body.get("action", "")).strip()
    if not action:
        raise HTTPException(status_code=400, detail="action is required")
    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    try:
        view = await people_decision_engine.transition(
            db, organization_id=org.id, decision_id=decision_id,
            action=action, actor_id=user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="decision not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {**view, "generated_at": _utcnow_iso()}


@router.post("/decisions/{decision_id}/outcome")
async def brain_decisions_outcome(
    decision_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record the REAL outcome a human observed after acting on (or
    rejecting) the recommendation. Success AND failure are kept honestly —
    both become evidence for the next evaluation (Decision -> Outcome ->
    Learning)."""
    from app.intelligence.people_decision_engine import people_decision_engine

    status = str(body.get("status", "")).strip()
    if not status:
        raise HTTPException(status_code=400, detail="status is required")
    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    try:
        view = await people_decision_engine.record_outcome(
            db, organization_id=org.id, decision_id=decision_id,
            status=status, note=body.get("note"), actor_id=user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="decision not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {**view, "generated_at": _utcnow_iso()}


@router.post("/decisions/{decision_id}/what-if")
async def brain_decisions_what_if(
    decision_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bounded decision simulation: what changes in THIS decision's context
    if this person were assigned instead of the primary — capability
    availability, concentration, workload, ownership conflicts. Bounded by
design: it is not the prediction engine, only the decision's own scope."""
    from app.intelligence.people_decision_engine import people_decision_engine

    person_id = body.get("person_id")
    if not person_id:
        raise HTTPException(status_code=400, detail="person_id is required")
    access = await _people_access(db, org, user)
    from app.models.people_decision import PeopleDecision

    decision_row = (
        await db.execute(
            select(PeopleDecision).where(
                PeopleDecision.organization_id == org.id,
                PeopleDecision.id == decision_id,
            )
        )
    ).scalar_one_or_none()
    if decision_row is None:
        raise HTTPException(status_code=404, detail="decision not found")
    if (
        not access.org_wide
        and (
            decision_row.context_type != "project"
            or decision_row.context_id not in access.project_ids
        )
    ):
        raise HTTPException(status_code=404, detail="scope not found")
    try:
        result = await people_decision_engine.what_if(
            db, organization_id=org.id, decision_id=decision_id,
            person_id=person_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="decision or person not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {**result, "decision_id": decision_id, "generated_at": _utcnow_iso()}


# ---------------------------------------------------------------------------
# Slice 4G.1 — Project & Execution Intelligence (the Execution Command
# Center). The canonical per-project execution record: goal -> project ->
# milestone -> task chain, deterministic health (healthy|watch|at_risk|
# critical) with factors and primary cause, blocker root-cause chains with
# systemic grouping, the real CPM critical path, capacity constraints
# (4F.6), pending 4A decisions, the mandatory outcome record, and the
# deterministic "what should happen next" prioritization. Change-driven:
# fed exclusively from the durable event bus, replay-safe and exact-once;
# advisory-only — the engine never writes projects/tasks/people/capacity.
#
# Governance: command/next are ORG-WIDE surfaces — scoped callers get 404
# (same idiom as 4F.6/4F.7). Project detail is visible to scoped callers on
# projects inside their governance scope. Recording an outcome requires
# projects:manage — a human writes the outcome; the system never evaluates
# itself.
# ---------------------------------------------------------------------------


@router.get("/execution/command")
async def brain_execution_command(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The Execution Command Center: every active project's execution state,
    health + explain, primary cause, last change and bounded counts."""
    from app.intelligence.execution_engine import execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await execution_engine.command_center(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/next")
async def brain_execution_next(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """'What should happen next?' — deterministic prioritized bounded list:
    unresolved decisions first, then critical-path pressure, blocked work on
    the path, overdue milestones, then high-priority ready work."""
    from app.intelligence.execution_engine import execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await execution_engine.execution_next(db, organization_id=org.id)
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/projects/{project_id}")
async def brain_execution_project_detail(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One project's full execution record: health + factors + explain +
    primary cause, critical path, blocker chains, systemic blockers,
    capacity constraints, pending decisions, goal chain and outcome."""
    from app.intelligence.execution_engine import execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide and project_id not in access.project_ids:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await execution_engine.project_detail(
        db, organization_id=org.id, project_id=project_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    return {**result, "generated_at": _utcnow_iso()}


@router.post("/execution/projects/{project_id}/outcome")
async def brain_execution_record_outcome(
    project_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The mandatory outcome record: planned vs actual + assessment in
    successful|partial|unsuccessful statuses. Outcomes become evidence and
    are snapshotted — they never rewrite the project."""
    from app.intelligence.execution_engine import execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide and project_id not in access.project_ids:
        raise HTTPException(status_code=404, detail="scope not found")
    status = str(body.get("status", "")).strip()
    if status not in ("successful", "partial", "unsuccessful"):
        raise HTTPException(
            status_code=400,
            detail="status must be one of: successful, partial, unsuccessful",
        )
    result = await execution_engine.record_outcome(
        db, organization_id=org.id, project_id=project_id,
        outcome={
            "status": status,
            "planned_outcome": body.get("planned_outcome"),
            "actual_outcome": body.get("actual_outcome"),
            "assessment": body.get("assessment"),
        },
        recorded_by=user.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    await db.commit()
    return {**result, "generated_at": _utcnow_iso()}


# ---------------------------------------------------------------------------
# Slice 4G.2 — Execution Coordination & Dependency Intelligence (the
# coordination layer of the Execution Command Center). How the WHOLE org
# coordinates: cross-project dependency pressure (shared-capacity contention
# + critical conflicts), the handoff ledger (pending/slow/recurring),
# coordination gaps, blockage propagation, and deterministic evidence-backed
# recommendations with confidence. Change-driven from the durable event bus,
# exact-once, advisory-only — the engine writes only its own tables and never
# reallocates people or reschedules work; human-controlled actions only.
#
# Governance: filters run BEFORE assembly. The coordination center is an
# ORG-WIDE surface (scoped callers 404 — same idiom as 4G.1/4F.6/4F.7).
# Project coordination views are visible to scoped callers for projects in
# their governance scope, but only project-scoped findings (handoff_risk,
# recurring_handoff, coordination_gap, propagation_risk) — pair/org kinds
# (shared_capacity, critical_conflict) reveal other projects' names and
# capacity and stay org-wide. Resolving a finding requires projects:manage;
# the system never resolves its own findings automatically as an outcome.
# ---------------------------------------------------------------------------


@router.get("/execution/coordination/center")
async def brain_coordination_center(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The Execution Coordination Center: open coordination findings with
    evidence + confidence, handoff ledger stats, bounded recommendations,
    and which projects are entangled."""
    from app.intelligence.coordination_engine import coordination_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await coordination_engine.center(
        db, organization_id=org.id, access=access,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/coordination/projects/{project_id}")
async def brain_coordination_project(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One project's coordination view: its findings, handoff ledger,
    propagation history, alternative owners and bounded what-if options."""
    from app.models.execution_coordination import SCOPED_KINDS
    from app.intelligence.coordination_engine import coordination_engine

    access = await _people_access(db, org, user)
    if not access.org_wide and project_id not in access.project_ids:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await coordination_engine.project_detail(
        db, organization_id=org.id, project_id=project_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    if not access.org_wide:
        result["incidents"] = [
            i for i in result["incidents"] if i["kind"] in SCOPED_KINDS
        ]
        result["recommendations"] = [
            r for r in result["recommendations"] if r["kind"] in SCOPED_KINDS
        ]
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/coordination/projects/{project_id}/what-if")
async def brain_coordination_what_if(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bounded coordination options for one project — explicitly NOT a
    prediction. Each option lists its deterministic effects and what it does
    NOT claim; nothing here reallocates or reschedules anything."""
    from app.intelligence.coordination_engine import coordination_engine

    access = await _people_access(db, org, user)
    if not access.org_wide and project_id not in access.project_ids:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await coordination_engine.project_detail(
        db, organization_id=org.id, project_id=project_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    return {"what_if": result["what_if"], "generated_at": _utcnow_iso()}


@router.post("/execution/coordination/incidents/{incident_id}/resolve")
async def brain_coordination_resolve(
    incident_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """A human resolves a coordination finding (advisory record, never a
    mutation of the org). If the underlying condition recurs, the next
    change-driven refresh reopens it with fresh evidence."""
    from app.models.execution_coordination import (
        CoordinationIncident,
        SCOPED_KINDS,
    )
    from app.intelligence.coordination_engine import coordination_engine

    access = await _people_access(db, org, user)
    incident = (
        await db.execute(
            select(CoordinationIncident).where(
                CoordinationIncident.organization_id == org.id,
                CoordinationIncident.id == incident_id,
            )
        )
    ).scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    if not access.org_wide:
        if incident.project_id not in access.project_ids:
            raise HTTPException(status_code=404, detail="scope not found")
        if incident.kind not in SCOPED_KINDS:
            raise HTTPException(status_code=404, detail="scope not found")
    result = await coordination_engine.resolve_incident(
        db, organization_id=org.id, incident_id=incident_id,
        note=body.get("note"), resolved_by=user.id,
    )
    await db.commit()
    return {**result, "generated_at": _utcnow_iso()}


# ---------------------------------------------------------------------------
# Slice 4G.3 — Strategic Portfolio & Goal Execution Intelligence
# ---------------------------------------------------------------------------
# Strategy is an ORG-WIDE surface (scoped callers 404 — same idiom as 4G.1 /
# 4G.2): company goals and portfolio coverage reveal other departments' work
# and capacity. Reads need brain:read; every write is a human-governed action
# (projects:manage), always advisory — the engine never decides, reschedules
# or re-ranks people. Writes publish the canonical strategy.* events; the
# event worker recomputes only the affected goal's neighborhood (incremental,
# exact-once snapshots).


@router.get("/execution/strategy/portfolio")
async def brain_strategy_portfolio(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Portfolio health: goal coverage, alignment rollup, outcome
    confidence and the top company attention list (all evidence-backed)."""
    from app.intelligence.strategic_execution_engine import strategic_execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await strategic_execution_engine.portfolio(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/strategy/goals/{goal_id}")
async def brain_strategy_goal_detail(
    goal_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One company goal's strategic record: coverage factors, missing
    capabilities, contributing projects and people, risks, priority history
    and strategy -> outcome learning."""
    from app.intelligence.strategic_execution_engine import strategic_execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await strategic_execution_engine.goal_detail(
        db, organization_id=org.id, goal_id=goal_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="goal not found")
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/strategy/gaps")
async def brain_strategy_gaps(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Strategic execution gaps: active projects without an explicit link to
    an active objective, and active goals whose coverage is below healthy."""
    from app.intelligence.strategic_execution_engine import strategic_execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await strategic_execution_engine.gaps(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/strategy/focus")
async def brain_strategy_focus(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """TOP COMPANY ATTENTION: deterministic focus ranking with the evidence
    behind every item. Advisory — leadership decides."""
    from app.intelligence.strategic_execution_engine import strategic_execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await strategic_execution_engine.focus(
        db, organization_id=org.id,
    )
    return {"focus": result, "advisory_only": True, "generated_at": _utcnow_iso()}


@router.get("/execution/strategy/conflicts")
async def brain_strategy_conflicts(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Portfolio contention: constrained capabilities claimed by active
    projects under different goals, with the strategic stakes."""
    from app.intelligence.strategic_execution_engine import strategic_execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await strategic_execution_engine.conflicts(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/strategy/impact")
async def brain_strategy_impact(
    project_id: str,
    delay_days: int = Query(default=14, ge=1, le=90),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """What a delay reaches: downstream projects, the strategic chain,
    customers, milestones and decisions. Bounded sensitivity, not a forecast."""
    from app.intelligence.strategic_execution_engine import strategic_execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await strategic_execution_engine.impact(
        db, organization_id=org.id, project_id=project_id, delay_days=delay_days,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/strategy/what-if")
async def brain_strategy_what_if(
    goal_id: Optional[str] = Query(default=None),
    project_id: Optional[str] = Query(default=None),
    delay_days: int = Query(default=14, ge=1, le=90),
    priority: Optional[int] = Query(default=None, ge=1, le=5),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bounded strategic what-if: delay a project (coverage sensitivity) or
    re-prioritize a goal (focus re-ranking). Assumptions are explicit."""
    from app.intelligence.strategic_execution_engine import strategic_execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await strategic_execution_engine.what_if(
        db, organization_id=org.id, goal_id=goal_id, project_id=project_id,
        delay_days=delay_days, priority=priority,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="what-if not resolvable")
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/strategy/alternatives")
async def brain_strategy_alternatives(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Three bounded courses for one project with evidence and a
    recommendation. Humans decide; nothing is executed."""
    from app.intelligence.strategic_execution_engine import strategic_execution_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await strategic_execution_engine.alternatives(
        db, organization_id=org.id, project_id=project_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    return {**result, "generated_at": _utcnow_iso()}


@router.post("/execution/strategy/goals")
async def brain_strategy_create_goal(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a company goal (the top of the strategic execution graph)."""
    from app.models.execution_strategy import CompanyGoal
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    try:
        priority = max(1, min(5, int(body.get("priority", 3))))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="priority must be 1..5")
    goal = CompanyGoal(
        organization_id=org.id,
        title=title[:300],
        description=body.get("description"),
        kind=(body.get("kind") or "other")[:40],
        status=(body.get("status") or "active")[:16],
        priority=priority,
        metric_kind=body.get("metric_kind"),
        metric_unit=body.get("metric_unit"),
        target_value=body.get("target_value"),
        current_value=body.get("current_value"),
        owner_person_id=body.get("owner_person_id"),
        owner_label=(body.get("owner_label") or "")[:255],
        timeline_label=(body.get("timeline_label") or "")[:120],
    )
    db.add(goal)
    await db.flush()
    await publish_event(
        db, name="strategy.goal.created", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id, "goal_id": goal.id, "id": goal.id,
            "title": goal.title, "status": goal.status, "priority": goal.priority,
            "kind": goal.kind,
        },
    )
    await db.commit()
    return {"goal_id": goal.id, "generated_at": _utcnow_iso()}


@router.post("/execution/strategy/goals/{goal_id}/priority")
async def brain_strategy_change_priority(
    goal_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """A human changes a company goal's priority (1 = highest). The change
    event is retained in the strategic history as organizational memory."""
    from app.models.execution_strategy import CompanyGoal
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    goal = (
        await db.execute(
            select(CompanyGoal).where(
                CompanyGoal.organization_id == org.id,
                CompanyGoal.id == goal_id,
            )
        )
    ).scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=404, detail="goal not found")
    try:
        priority = max(1, min(5, int(body.get("priority", goal.priority))))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="priority must be 1..5")
    old_priority = goal.priority
    if priority == old_priority:
        await db.commit()
        return {"goal_id": goal_id, "priority": priority, "changed": False,
                "generated_at": _utcnow_iso()}
    goal.priority = priority
    await publish_event(
        db, name="strategy.goal.priority.changed", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id, "goal_id": goal.id, "id": goal.id,
            "title": goal.title, "priority": priority,
            "old_priority": old_priority,
            "reason": body.get("reason"),
        },
    )
    await db.commit()
    return {"goal_id": goal_id, "priority": priority, "old_priority": old_priority,
            "changed": True, "generated_at": _utcnow_iso()}


@router.post("/execution/strategy/objectives")
async def brain_strategy_create_objective(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create an objective under a company goal."""
    from app.models.execution_strategy import CompanyGoal, CompanyObjective
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    goal_id = body.get("goal_id")
    goal = (
        await db.execute(
            select(CompanyGoal).where(
                CompanyGoal.organization_id == org.id,
                CompanyGoal.id == goal_id,
            )
        )
    ).scalar_one_or_none() if goal_id else None
    if goal is None:
        raise HTTPException(status_code=404, detail="goal not found")
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    objective = CompanyObjective(
        organization_id=org.id,
        goal_id=goal.id,
        title=title[:300],
        description=body.get("description"),
        kind=(body.get("kind") or "other")[:40],
        status=(body.get("status") or "active")[:16],
        required_capabilities=body.get("required_capabilities") or [],
        owner_person_id=body.get("owner_person_id"),
        owner_label=(body.get("owner_label") or "")[:255],
    )
    db.add(objective)
    await db.flush()
    await publish_event(
        db, name="strategy.objective.created", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id, "goal_id": goal.id,
            "objective_id": objective.id, "id": objective.id,
            "title": objective.title, "status": objective.status,
        },
    )
    await db.commit()
    return {"objective_id": objective.id, "generated_at": _utcnow_iso()}


@router.post("/execution/strategy/initiatives")
async def brain_strategy_create_initiative(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create an initiative under an objective (carries the strategic
    assumption: expected outcome + customer commitments where declared)."""
    from app.models.execution_strategy import CompanyInitiative, CompanyObjective
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    objective_id = body.get("objective_id")
    objective = (
        await db.execute(
            select(CompanyObjective).where(
                CompanyObjective.organization_id == org.id,
                CompanyObjective.id == objective_id,
            )
        )
    ).scalar_one_or_none() if objective_id else None
    if objective is None:
        raise HTTPException(status_code=404, detail="objective not found")
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    initiative = CompanyInitiative(
        organization_id=org.id,
        objective_id=objective.id,
        title=title[:300],
        description=body.get("description"),
        kind=(body.get("kind") or "other")[:40],
        status=(body.get("status") or "active")[:16],
        required_capabilities=body.get("required_capabilities") or [],
        customer_commitments=body.get("customer_commitments") or [],
        expected_outcome=body.get("expected_outcome"),
        owner_person_id=body.get("owner_person_id"),
        owner_label=(body.get("owner_label") or "")[:255],
    )
    db.add(initiative)
    await db.flush()
    await publish_event(
        db, name="strategy.initiative.created", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id, "goal_id": objective.goal_id,
            "objective_id": objective.id, "initiative_id": initiative.id,
            "id": initiative.id, "title": initiative.title,
            "status": initiative.status,
        },
    )
    await db.commit()
    return {"initiative_id": initiative.id, "generated_at": _utcnow_iso()}


@router.post("/execution/strategy/initiatives/{initiative_id}/link")
async def brain_strategy_link_project(
    initiative_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Goal -> work traceability: link a project to an initiative."""
    from app.models.execution_strategy import CompanyInitiative, CompanyObjective
    from app.models.project import Project
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    initiative = (
        await db.execute(
            select(CompanyInitiative).where(
                CompanyInitiative.organization_id == org.id,
                CompanyInitiative.id == initiative_id,
            )
        )
    ).scalar_one_or_none()
    if initiative is None:
        raise HTTPException(status_code=404, detail="initiative not found")
    project_id = body.get("project_id")
    project = (
        await db.execute(
            select(Project).where(
                Project.organization_id == org.id,
                Project.id == project_id,
            )
        )
    ).scalar_one_or_none() if project_id else None
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    objective = (
        await db.execute(
            select(CompanyObjective).where(
                CompanyObjective.organization_id == org.id,
                CompanyObjective.id == initiative.objective_id,
            )
        )
    ).scalar_one_or_none()
    await publish_event(
        db, name="strategy.initiative.linked", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "goal_id": objective.goal_id if objective else None,
            "objective_id": initiative.objective_id,
            "initiative_id": initiative.id,
            "initiative_title": initiative.title,
            "project_id": project.id, "project_label": project.name,
        },
    )
    await db.commit()
    return {"linked": True, "generated_at": _utcnow_iso()}


@router.post("/execution/strategy/initiatives/{initiative_id}/unlink")
async def brain_strategy_unlink_project(
    initiative_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove a goal -> work link (history keeps the event trail)."""
    from app.models.execution_strategy import CompanyInitiative, CompanyObjective
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    initiative = (
        await db.execute(
            select(CompanyInitiative).where(
                CompanyInitiative.organization_id == org.id,
                CompanyInitiative.id == initiative_id,
            )
        )
    ).scalar_one_or_none()
    if initiative is None:
        raise HTTPException(status_code=404, detail="initiative not found")
    project_id = body.get("project_id")
    objective = (
        await db.execute(
            select(CompanyObjective).where(
                CompanyObjective.organization_id == org.id,
                CompanyObjective.id == initiative.objective_id,
            )
        )
    ).scalar_one_or_none()
    await publish_event(
        db, name="strategy.initiative.unlinked", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "goal_id": objective.goal_id if objective else None,
            "objective_id": initiative.objective_id,
            "initiative_id": initiative.id,
            "project_id": project_id,
        },
    )
    await db.commit()
    return {"unlinked": True, "generated_at": _utcnow_iso()}


@router.post("/execution/strategy/initiatives/{initiative_id}/outcome")
async def brain_strategy_record_outcome(
    initiative_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record a strategy -> outcome observation (expected vs actual). Feeds
    the organizational learning engine (4E.7) — the strategy loop closes."""
    from app.models.execution_strategy import CompanyInitiative, CompanyObjective
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    initiative = (
        await db.execute(
            select(CompanyInitiative).where(
                CompanyInitiative.organization_id == org.id,
                CompanyInitiative.id == initiative_id,
            )
        )
    ).scalar_one_or_none()
    if initiative is None:
        raise HTTPException(status_code=404, detail="initiative not found")
    if body.get("actual_value") is None:
        raise HTTPException(status_code=400, detail="actual_value is required")
    objective = (
        await db.execute(
            select(CompanyObjective).where(
                CompanyObjective.organization_id == org.id,
                CompanyObjective.id == initiative.objective_id,
            )
        )
    ).scalar_one_or_none()
    await publish_event(
        db, name="strategy.outcome.recorded", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "goal_id": objective.goal_id if objective else None,
            "objective_id": initiative.objective_id,
            "initiative_id": initiative.id,
            "project_id": body.get("project_id"),
            "project_label": (body.get("project_label") or "")[:300],
            "metric_kind": (body.get("metric_kind") or "other")[:80],
            "unit": (body.get("unit") or "")[:40],
            "expected_value": body.get("expected_value"),
            "actual_value": body.get("actual_value"),
        },
    )
    await db.commit()
    return {"recorded": True, "generated_at": _utcnow_iso()}


# ---------------------------------------------------------------------------
# Slice 4G.4 — Universal Resource & Capacity Allocation
#
# One governed surface for the capacity ledger: explicit project demands
# (capability x units x window), human allocation decisions with outcomes,
# and the advisory surfaces (center, gaps, contention, traceability,
# overloads, capability detail, alternatives, what-if). Every payload the
# brain returns is evidence-backed and deterministic; nothing here moves
# people or capacity — a human decides. Reads are org-wide (brain:read);
# writes are governed (projects:manage). Change events feed the engine's
# exact-once snapshots via the capacity.* event handlers.
# ---------------------------------------------------------------------------


def _capacity_date(value: Any) -> Optional[date]:
    """Parse a demand/allocation window date from the request body."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _customer_event_time(value: Any) -> datetime:
    """Parse a customer event timestamp (occurred_at / delivered_at) from
    the request body, defaulting to now in UTC."""
    if isinstance(value, datetime):
        return value
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


async def _capacity_window(
    body: dict[str, Any],
) -> tuple[str, date, date]:
    """Validate and return (capability, window_start, window_end)."""
    capability = (body.get("capability") or "").strip()[:120]
    window_start = _capacity_date(body.get("window_start"))
    window_end = _capacity_date(body.get("window_end"))
    if not capability:
        raise HTTPException(status_code=400, detail="capability is required")
    if not window_start or not window_end:
        raise HTTPException(
            status_code=400, detail="window_start and window_end (YYYY-MM-DD) are required"
        )
    if window_end < window_start:
        raise HTTPException(
            status_code=400, detail="window_end must be on or after window_start"
        )
    return capability, window_start, window_end


@router.get("/execution/capacity/center")
async def brain_capacity_center(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """CAPACITY CENTER: company utilization, critical bottlenecks,
    overloaded capabilities, capability gaps, goals at risk and the top
    constraint with a recommended action. Advisory, deterministic."""
    from app.intelligence.resource_allocation_engine import resource_allocation_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await resource_allocation_engine.center(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/capacity/gaps")
async def brain_capacity_gaps(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Current capacity gaps (windows containing today) and FUTURE gaps
    clearly labeled as projections — never presented as fact."""
    from app.intelligence.resource_allocation_engine import resource_allocation_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await resource_allocation_engine.gaps(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/capacity/contention")
async def brain_capacity_contention(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Projects competing for the same scarce capability, ordered with
    their strategic stakes. Advisory — humans decide the allocation."""
    from app.intelligence.resource_allocation_engine import resource_allocation_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await resource_allocation_engine.contention(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/capacity/traceability")
async def brain_capacity_traceability(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """RESOURCE-TO-GOAL TRACEABILITY: how each capability's demand maps to
    company goals, initiatives and unaligned work (the drill-down)."""
    from app.intelligence.resource_allocation_engine import resource_allocation_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await resource_allocation_engine.traceability(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/capacity/overloads")
async def brain_capacity_overloads(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Overload and under-utilization at capability, team and person level —
    evidence-backed, never a rank for people."""
    from app.intelligence.resource_allocation_engine import resource_allocation_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await resource_allocation_engine.overloads(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/capacity/capabilities/{capability}")
async def brain_capacity_capability_detail(
    capability: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One capability's full capacity record: supply + demand in the latest
    window, the gap with WHY, stakes, commitments and temporal history."""
    from app.intelligence.resource_allocation_engine import resource_allocation_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await resource_allocation_engine.capability_detail(
        db, organization_id=org.id, capability=capability[:120],
    )
    if result is None:
        raise HTTPException(status_code=404, detail="capability not found")
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/capacity/alternatives")
async def brain_capacity_alternatives(
    project_id: str,
    capability: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Three bounded allocation courses for one project's contention with
    benefit/risk/confidence/evidence. Humans decide; nothing executes."""
    from app.intelligence.resource_allocation_engine import resource_allocation_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await resource_allocation_engine.alternatives(
        db, organization_id=org.id, project_id=project_id,
        capability=(capability or None),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/capacity/what-if")
async def brain_capacity_what_if(
    from_project_id: str,
    to_project_id: str,
    capability: str,
    units: int = Query(default=1, ge=1),
    window_days: int = Query(default=30, ge=1, le=365),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bounded reallocation scenario: move N units of a capability from one
    project to another. Simulated gaps + goal directions; NEVER a prediction
    and never executed."""
    from app.intelligence.resource_allocation_engine import resource_allocation_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await resource_allocation_engine.what_if(
        db, organization_id=org.id,
        from_project_id=from_project_id, to_project_id=to_project_id,
        capability=capability[:120], units=units, window_days=window_days,
    )
    if result is None:
        raise HTTPException(
            status_code=404, detail="no shared demand window found for this reallocation"
        )
    return {**result, "generated_at": _utcnow_iso()}


@router.post("/execution/capacity/demands")
async def brain_capacity_create_demand(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Declare (create) or change (update) a project's explicit resource
    demand: capability x units x window. The governed write publishes the
    capacity.demand event; the engine recomputes that window's snapshot."""
    from app.models.project import Project
    from app.models.resource_allocation_intelligence import AllocationDemand
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    project_id = (body.get("project_id") or "").strip()
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    project = (
        await db.execute(
            select(Project).where(
                Project.organization_id == org.id, Project.id == project_id,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    capability, window_start, window_end = await _capacity_window(body)
    try:
        units = max(1, int(body.get("units", 1)))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="units must be a positive integer")
    proficiency = (body.get("proficiency") or "high").strip()[:24]
    if proficiency not in ("high", "expert"):
        raise HTTPException(status_code=400, detail="proficiency must be high or expert")
    note = (body.get("note") or "")[:1000] or None

    demand = (
        await db.execute(
            select(AllocationDemand).where(
                AllocationDemand.organization_id == org.id,
                AllocationDemand.project_id == project_id,
                AllocationDemand.capability == capability,
                AllocationDemand.window_start == window_start,
                AllocationDemand.window_end == window_end,
            )
        )
    ).scalar_one_or_none()
    if demand is None:
        demand = AllocationDemand(
            organization_id=org.id, project_id=project_id,
            capability=capability, units=units,
            window_start=window_start, window_end=window_end,
            proficiency=proficiency, note=note,
        )
        db.add(demand)
        await db.flush()
        await publish_event(
            db, name="capacity.demand.created", organization_id=org.id,
            actor_id=user.id,
            payload={
                "organization_id": org.id, "project_id": project_id,
                "project_label": project.name,
                "capability": capability, "units": units,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "proficiency": proficiency, "note": note,
            },
        )
        await db.commit()
        return {"demand_id": demand.id, "created": True,
                "generated_at": _utcnow_iso()}

    old_units = demand.units
    demand.units = units
    demand.proficiency = proficiency
    if note is not None:
        demand.note = note
    await publish_event(
        db, name="capacity.demand.updated", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id, "project_id": project_id,
            "project_label": project.name,
            "capability": capability, "units": units, "old_units": old_units,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "proficiency": proficiency,
            "reason": (body.get("reason") or "")[:1000] or None,
        },
    )
    await db.commit()
    return {"demand_id": demand.id, "created": False,
            "generated_at": _utcnow_iso()}


@router.post("/execution/capacity/demands/{demand_id}/remove")
async def brain_capacity_remove_demand(
    demand_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove a project's explicit resource demand. The event is retained
    in the capacity history as organizational memory."""
    from app.models.resource_allocation_intelligence import AllocationDemand
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    demand = (
        await db.execute(
            select(AllocationDemand).where(
                AllocationDemand.organization_id == org.id,
                AllocationDemand.id == demand_id,
            )
        )
    ).scalar_one_or_none()
    if demand is None:
        raise HTTPException(status_code=404, detail="demand not found")
    removed = {
        "project_id": demand.project_id, "capability": demand.capability,
        "units": demand.units,
        "window_start": demand.window_start.isoformat(),
        "window_end": demand.window_end.isoformat(),
    }
    await publish_event(
        db, name="capacity.demand.removed", organization_id=org.id,
        actor_id=user.id,
        payload={
            **removed,
            "organization_id": org.id,
            "reason": (body.get("reason") or "")[:1000] or None,
        },
    )
    await db.delete(demand)
    await db.commit()
    return {"demand_id": demand_id, "removed": True, **removed,
            "generated_at": _utcnow_iso()}


@router.post("/execution/capacity/allocations")
async def brain_capacity_create_allocation(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """A human commits a governed capacity allocation: X units of a
    capability to a project inside a window (a claim on supply)."""
    from app.models.project import Project
    from app.models.resource_allocation_intelligence import CapacityAllocation
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    project_id = (body.get("project_id") or "").strip()
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    project = (
        await db.execute(
            select(Project).where(
                Project.organization_id == org.id, Project.id == project_id,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    capability, window_start, window_end = await _capacity_window(body)
    try:
        units = max(1, int(body.get("units", 1)))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="units must be a positive integer")
    allocation = CapacityAllocation(
        organization_id=org.id, project_id=project_id,
        project_label=project.name[:300], capability=capability, units=units,
        window_start=window_start, window_end=window_end,
        status="active", outcome=None,
        note=(body.get("note") or "")[:1000] or None,
        source_event_id="",
    )
    db.add(allocation)
    await db.flush()
    event = await publish_event(
        db, name="capacity.allocation.created", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id, "allocation_id": allocation.id,
            "project_id": project_id, "project_label": project.name[:300],
            "capability": capability, "units": units,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        },
    )
    allocation.source_event_id = getattr(event, "id", "") or allocation.id
    await db.commit()
    return {"allocation_id": allocation.id, "created": True,
            "generated_at": _utcnow_iso()}


@router.post("/execution/capacity/allocations/{allocation_id}/outcome")
async def brain_capacity_allocation_outcome(
    allocation_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record a governed allocation's outcome (achieved/partial/missed).
    The observation pours into 4E.7 organizational learning — VCOS gets
    smarter from its own allocation history."""
    from app.models.resource_allocation_intelligence import CapacityAllocation
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    allocation = (
        await db.execute(
            select(CapacityAllocation).where(
                CapacityAllocation.organization_id == org.id,
                CapacityAllocation.id == allocation_id,
            )
        )
    ).scalar_one_or_none()
    if allocation is None:
        raise HTTPException(status_code=404, detail="allocation not found")
    outcome = (body.get("outcome") or "").strip()
    if outcome not in ("achieved", "partial", "missed"):
        raise HTTPException(
            status_code=400, detail="outcome must be achieved, partial or missed"
        )
    if allocation.status != "active":
        raise HTTPException(status_code=400, detail="allocation is not active")
    allocation.status = "completed"
    allocation.outcome = outcome
    if body.get("note"):
        allocation.note = (body.get("note") or "")[:1000]
    event = await publish_event(
        db, name="capacity.allocation.completed", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id, "allocation_id": allocation.id,
            "project_id": allocation.project_id,
            "project_label": allocation.project_label,
            "capability": allocation.capability, "units": allocation.units,
            "window_start": allocation.window_start.isoformat(),
            "window_end": allocation.window_end.isoformat(),
            "outcome": outcome,
            "note": allocation.note,
        },
    )
    allocation.source_event_id = getattr(event, "id", "") or allocation.id
    await db.commit()
    return {"allocation_id": allocation_id, "outcome": outcome,
            "recorded": True, "generated_at": _utcnow_iso()}


@router.post("/execution/customer/signals")
async def brain_customer_record_signal(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record a voice-of-customer signal: feedback, request, complaint,
    issue, success, churn risk, adoption, outcome or expansion evidence.
    A governed write that publishes the customer.signal event; the 4G.5
    engine recomputes that customer's health and the affected theme."""
    from app.models.customer import Customer
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    customer_id = (body.get("customer_id") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")
    customer = (
        await db.execute(
            select(Customer).where(
                Customer.organization_id == org.id, Customer.id == customer_id,
            )
        )
    ).scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    signal_type = (body.get("signal_type") or "").strip()
    from app.intelligence.customer_intelligence_engine import SIGNAL_TYPES, SIGNAL_SOURCES
    if signal_type not in SIGNAL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"signal_type must be one of {', '.join(SIGNAL_TYPES)}",
        )
    summary = (body.get("summary") or "").strip()
    if not summary:
        raise HTTPException(status_code=400, detail="summary is required")
    severity = (body.get("severity") or "info").strip()[:16]
    from app.intelligence.customer_intelligence_engine import SIGNAL_SEVERITIES
    if severity not in SIGNAL_SEVERITIES:
        raise HTTPException(
            status_code=400,
            detail=f"severity must be one of {', '.join(SIGNAL_SEVERITIES)}",
        )
    source = (body.get("source") or "observation").strip()[:24]
    if source not in SIGNAL_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"source must be one of {', '.join(SIGNAL_SOURCES)}",
        )
    occurred_at = _customer_event_time(body.get("occurred_at"))
    event = await publish_event(
        db, name="customer.signal.recorded", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "customer_id": customer_id,
            "customer_label": customer.company_name,
            "signal_type": signal_type,
            "severity": severity,
            "summary": summary,
            "source": source,
            "need": (body.get("need") or "")[:64],
            "occurred_at": occurred_at.isoformat(),
            "tags": body.get("tags"),
        },
    )
    await db.commit()
    return {
        "signal_recorded": True,
        "source_event_id": getattr(event, "id", ""),
        "customer_id": customer_id,
        "generated_at": _utcnow_iso(),
    }


@router.post("/execution/customer/signals/{signal_id}/resolve")
async def brain_customer_resolve_signal(
    signal_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Mark a customer signal resolved (issue closed / request satisfied).
    The resolution re-feeds health: a resolved issue stops weighing."""
    from app.models.customer_intelligence import CustomerSignal
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    signal = (
        await db.execute(
            select(CustomerSignal).where(
                CustomerSignal.organization_id == org.id,
                CustomerSignal.id == signal_id,
            )
        )
    ).scalar_one_or_none()
    if signal is None:
        raise HTTPException(status_code=404, detail="signal not found")
    if signal.status in ("resolved", "closed"):
        raise HTTPException(status_code=400, detail="signal already resolved")
    event = await publish_event(
        db, name="customer.signal.resolved", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "signal_id": signal.id,
            "customer_id": signal.customer_id,
            "signal_type": signal.signal_type,
            "need": signal.need_key,
            "resolution": (body.get("resolution") or "")[:1000] or None,
        },
    )
    await db.commit()
    return {
        "signal_resolved": True,
        "source_event_id": getattr(event, "id", ""),
        "customer_id": signal.customer_id,
        "generated_at": _utcnow_iso(),
    }


@router.post("/execution/customer/commitments")
async def brain_customer_create_commitment(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record a definite customer commitment: a deliverable with a date
    (now fixed, unconditional). The governed write publishes
    customer.commitment.created — the engine links it to the project and
    to the customer health."""
    from app.models.customer import Customer
    from app.models.customer_intelligence import CustomerCommitment
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    customer_id = (body.get("customer_id") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")
    customer = (
        await db.execute(
            select(Customer).where(
                Customer.organization_id == org.id, Customer.id == customer_id,
            )
        )
    ).scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    summary = (body.get("summary") or "").strip()
    if not summary:
        raise HTTPException(status_code=400, detail="summary is required")
    expected_on = _customer_event_time(body.get("expected_at")).date()
    project_id = (body.get("project_id") or "").strip() or None
    if project_id:
        from app.models.project import Project
        project = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == org.id, Project.id == project_id,
                )
            )
        ).scalar_one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
    existing = (
        await db.execute(
            select(CustomerCommitment).where(
                CustomerCommitment.organization_id == org.id,
                CustomerCommitment.customer_id == customer_id,
                CustomerCommitment.summary == summary,
            )
        )
    ).scalar_one_or_none()
    created = existing is None
    if existing is None:
        existing = CustomerCommitment(
            organization_id=org.id, customer_id=customer_id,
            summary=summary, expected_at=expected_on,
            project_id=project_id, status="pending",
            capability=(body.get("capability") or "")[:80] or None,
            owner_label=(body.get("owner_label") or "")[:120] or None,
            note=(body.get("note") or "")[:2000] or None,
            source_event_id="",
        )
        db.add(existing)
        await db.flush()
    else:
        existing.expected_at = expected_on
        if project_id:
            existing.project_id = project_id
    event = await publish_event(
        db,
        name="customer.commitment.created" if created else "customer.commitment.updated",
        organization_id=org.id, actor_id=user.id,
        payload={
            "organization_id": org.id,
            "commitment_id": existing.id,
            "customer_id": customer_id,
            "customer_label": customer.company_name,
            "summary": summary,
            "expected_at": expected_on.isoformat(),
            "project_id": project_id,
            "project_label": project.name if project_id else None,
            "capability": existing.capability,
            "owner_label": existing.owner_label,
            "created": created,
        },
    )
    existing.source_event_id = getattr(event, "id", "") or existing.id
    await db.commit()
    return {"commitment_id": existing.id, "created": created,
            "generated_at": _utcnow_iso()}


@router.post("/execution/customer/commitments/{commitment_id}/deliver")
async def brain_customer_deliver_commitment(
    commitment_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deliver a commitment (demonstrated, not asserted). The delivery
    event re-feeds the customer's health and their outcome story."""
    from app.models.customer_intelligence import CustomerCommitment
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    commitment = (
        await db.execute(
            select(CustomerCommitment).where(
                CustomerCommitment.organization_id == org.id,
                CustomerCommitment.id == commitment_id,
            )
        )
    ).scalar_one_or_none()
    if commitment is None:
        raise HTTPException(status_code=404, detail="commitment not found")
    if commitment.status == "delivered":
        raise HTTPException(status_code=400, detail="commitment already delivered")
    delivered_on = _customer_event_time(body.get("delivered_at")).date()
    event = await publish_event(
        db, name="customer.commitment.delivered", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "commitment_id": commitment.id,
            "customer_id": commitment.customer_id,
            "summary": commitment.summary,
            "expected_at": commitment.expected_at.isoformat(),
            "delivered_at": delivered_on.isoformat(),
            "project_id": commitment.project_id,
            "capability": commitment.capability,
            "note": (body.get("note") or "")[:1000] or None,
        },
    )
    commitment.source_event_id = getattr(event, "id", "") or commitment.id
    await db.commit()
    return {"commitment_id": commitment_id, "delivered": True,
            "generated_at": _utcnow_iso()}


@router.post("/execution/customer/outcomes")
async def brain_customer_record_outcome(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record a customer outcome observation: baseline -> target -> actual
    for a business metric. It becomes a theme surface and pours into 4E.7
    organizational learning."""
    from app.models.customer import Customer
    from app.models.customer_intelligence import CustomerOutcome
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    customer_id = (body.get("customer_id") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")
    customer = (
        await db.execute(
            select(Customer).where(
                Customer.organization_id == org.id, Customer.id == customer_id,
            )
        )
    ).scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    metric_kind = (body.get("metric_kind") or "").strip()
    if not metric_kind:
        raise HTTPException(status_code=400, detail="metric_kind is required")
    try:
        baseline = float(body.get("baseline")) if body.get("baseline") is not None else None
        target = float(body.get("target")) if body.get("target") is not None else None
        actual = float(body.get("actual")) if body.get("actual") is not None else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="baseline/target/actual must be numbers")
    out = CustomerOutcome(
        organization_id=org.id, customer_id=customer_id,
        metric_kind=metric_kind,
        baseline=baseline, target=target, actual=actual,
        unit=(body.get("unit") or "")[:16] or None,
        period_label=(body.get("period_label") or "")[:32] or None,
        signal_id=None,
        note=(body.get("note") or "")[:1000] or None,
        source_event_id="",
    )
    db.add(out)
    await db.flush()
    event = await publish_event(
        db, name="customer.outcome.recorded", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "outcome_id": out.id,
            "customer_id": customer_id,
            "customer_label": customer.company_name,
            "metric_kind": metric_kind,
            "baseline": baseline,
            "target": target,
            "actual": actual,
            "unit": out.unit,
            "period_label": out.period_label,
            "note": out.note,
        },
    )
    out.source_event_id = getattr(event, "id", "") or out.id
    await db.commit()
    return {"outcome_id": out.id,
            "source_event_id": getattr(event, "id", ""),
            "generated_at": _utcnow_iso()}


@router.get("/execution/customer/signals")
async def brain_customer_signals(
    customer_id: Optional[str] = None,
    need: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The voice-of-customer signal ledger, filterable by customer, need
    and severity — ordered newest first, bounded."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.signals(
        db, organization_id=org.id, customer_id=customer_id or None,
        need=need or None, severity=severity or None, limit=min(max(limit, 1), 500),
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/themes")
async def brain_customer_themes(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The customer theme aggregate: recurring needs across customers with
    evidence counts and the explainable impact scoring."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.themes(db, organization_id=org.id)
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/health")
async def brain_customer_healths(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Every customer's evidence-backed health: state, score and why."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.healths(db, organization_id=org.id)
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/health/{customer_id}")
async def brain_customer_health(
    customer_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One customer's health detail: score, the why, positives and the
    temporal history trail."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.health(
        db, organization_id=org.id, customer_id=customer_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/risk")
async def brain_customer_risk(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Customer risk: at-risk accounts with the propagation from delayed
    projects through commitments up to strategic goals."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.risk(db, organization_id=org.id)
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/commitments")
async def brain_customer_commitments(
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The commitment ledger: what we promised, to whom, when, and the
    project + capability + capacity behind each promise."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.commitments(
        db, organization_id=org.id, status=status or None,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/outcomes")
async def brain_customer_outcomes(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The customer outcome evidence ledger: baseline -> target -> actual."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.outcomes(db, organization_id=org.id)
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/coverage")
async def brain_customer_coverage(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Coverage: is the portfolio actually addressing what customers need —
    per theme, traceable to active initiatives and projects."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.coverage(db, organization_id=org.id)
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/gaps")
async def brain_customer_gaps(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Strategic customer gaps: high-demand themes nothing is addressing.
    Advisory only — decisions stay with people."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.strategic_gaps(db, organization_id=org.id)
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/opportunities")
async def brain_customer_opportunities(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Customer opportunity detection: demand-type needs shared by multiple
    customers with strategic relevance. Advisory only."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.opportunities(db, organization_id=org.id)
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/trends")
async def brain_customer_trends(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Signal volume trends per theme over the last six months.
    Deterministic and evidence-backed — never a forecast."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.trends(db, organization_id=org.id)
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/knowledge")
async def brain_customer_knowledge(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Knowledge linkage: does our own knowledge base cover the customer
    themes we keep collecting — and where are the blind spots?"""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.knowledge_linkage(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/customer/customers/{customer_id}")
async def brain_customer_detail(
    customer_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One customer's command center: health + trail, timeline, themes,
    commitments and outcome evidence."""
    from app.intelligence.customer_intelligence_engine import customer_intelligence_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await customer_intelligence_engine.customer_do(
        db, organization_id=org.id, customer_id=customer_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return {**result, "generated_at": _utcnow_iso()}


# ---------------------------------------------------------------------------
# 4G.6 — Commercial & Business Performance Intelligence
# ---------------------------------------------------------------------------


def _business_float(value: Any, field: str) -> Optional[float]:
    """Strictly parse a numeric business value (metrics, targets, forecasts)."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field} must be a number")


async def _business_metric_or_404(
    db: AsyncSession, org: Organization, metric_key: str,
) -> Any:
    """Resolve a business metric by its canonical key inside the org."""
    from app.models.business_performance import BusinessMetric
    from app.intelligence.business_performance_engine import _metric_key

    key = _metric_key(metric_key)
    metric = (
        await db.execute(
            select(BusinessMetric).where(
                BusinessMetric.organization_id == org.id,
                BusinessMetric.key == key,
            )
        )
    ).scalar_one_or_none()
    if metric is None:
        raise HTTPException(status_code=404, detail=f"metric '{key}' not found")
    return metric


@router.post("/execution/business/metrics")
async def brain_business_create_metric(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Define (or update) a canonical business metric. The governed write
    publishes business.metric.created / business.metric.updated — the 4G.6
    engine keeps one live metric per key and recomputes the scope."""
    from app.models.business_performance import (
        METRIC_DIRECTIONS,
        METRIC_GRANULARITIES,
        METRIC_KINDS,
        METRIC_VISIBILITIES,
        BusinessMetric,
    )
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    key = (body.get("key") or body.get("metric_key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    kind = (body.get("kind") or "other").strip()[:40]
    if kind not in METRIC_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {', '.join(METRIC_KINDS)}",
        )
    direction = (body.get("direction") or "up_is_good").strip()[:16]
    if direction not in METRIC_DIRECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"direction must be one of {', '.join(METRIC_DIRECTIONS)}",
        )
    granularity = (body.get("period_granularity") or "monthly").strip()[:16]
    if granularity not in METRIC_GRANULARITIES:
        raise HTTPException(
            status_code=400,
            detail=f"period_granularity must be one of {', '.join(METRIC_GRANULARITIES)}",
        )
    visibility = (body.get("visibility") or "internal").strip()[:16]
    if visibility not in METRIC_VISIBILITIES:
        raise HTTPException(
            status_code=400,
            detail=f"visibility must be one of {', '.join(METRIC_VISIBILITIES)}",
        )
    existing = (
        await db.execute(
            select(BusinessMetric).where(
                BusinessMetric.organization_id == org.id,
                BusinessMetric.key == key,
            )
        )
    ).scalar_one_or_none()
    created = existing is None
    event = await publish_event(
        db, name="business.metric.created" if created else "business.metric.updated",
        organization_id=org.id, actor_id=user.id,
        payload={
            "organization_id": org.id,
            "key": key,
            "label": (body.get("label") or key)[:200],
            "description": (body.get("description") or "")[:4000] or None,
            "kind": kind,
            "direction": direction,
            "unit": (body.get("unit") or "")[:40],
            "period_granularity": granularity,
            "visibility": visibility,
            "scope": (body.get("scope") or "org_wide").strip()[:16],
            "scope_entity_id": (body.get("scope_entity_id") or "").strip()[:32],
            "status": (body.get("status") or "")[:16],
        },
    )
    await db.commit()
    return {
        "metric_key": key,
        "created": created,
        "source_event_id": getattr(event, "id", ""),
        "generated_at": _utcnow_iso(),
    }


@router.post("/execution/business/outcomes")
async def brain_business_record_outcome(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record a business outcome observation (actual result of a metric).
    Lazily creates the metric when it does not exist yet; always refreshes
    the affected scope's performance assessment."""
    from app.models.business_performance import OBSERVATION_SOURCES
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    metric_key = (body.get("metric_key") or body.get("key") or "").strip()
    if not metric_key:
        raise HTTPException(status_code=400, detail="metric_key is required")
    value = _business_float(body.get("value"), "value")
    if value is None and body.get("actual") is not None:
        value = _business_float(body.get("actual"), "actual")
    if value is None:
        raise HTTPException(status_code=400, detail="value (or actual) is required")
    source = (body.get("source") or "financial").strip()[:24]
    if source not in OBSERVATION_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"source must be one of {', '.join(OBSERVATION_SOURCES)}",
        )
    observed_at = _customer_event_time(body.get("observed_at"))
    event = await publish_event(
        db, name="business.outcome.recorded", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "metric_key": metric_key,
            "metric_label": (body.get("metric_label") or body.get("label") or "")[:200],
            "value": value,
            "observed_at": observed_at.isoformat(),
            "source": source,
            "unit": (body.get("unit") or "")[:40],
            "note": (body.get("note") or "")[:4000] or None,
            "kind": (body.get("kind") or "")[:40],
            "direction": (body.get("direction") or "")[:16],
        },
    )
    await db.commit()
    return {
        "outcome_recorded": True,
        "metric_key": metric_key,
        "source_event_id": getattr(event, "id", ""),
        "generated_at": _utcnow_iso(),
    }


@router.post("/execution/business/targets")
async def brain_business_create_target(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Commit (or revise) a business target with a deadline. The governed
    write publishes business.target.created / business.target.updated; the
    engine derives the deterministic status and the gap to attainment."""
    from app.models.business_performance import TARGET_BELIEFS, BusinessTarget
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    metric_key = (body.get("metric_key") or "").strip()
    metric_id = (body.get("metric_id") or "").strip()
    if metric_id:
        from app.models.business_performance import BusinessMetric

        metric = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == org.id,
                    BusinessMetric.id == metric_id,
                )
            )
        ).scalar_one_or_none()
        if metric is None:
            raise HTTPException(status_code=404, detail="metric not found")
        metric_key = metric.key or metric_key
    elif metric_key:
        metric = await _business_metric_or_404(db, org, metric_key)
        metric_id = metric.id
    else:
        raise HTTPException(status_code=400, detail="metric_key (or metric_id) is required")
    target_value = _business_float(body.get("target_value"), "target_value")
    if target_value is None:
        raise HTTPException(status_code=400, detail="target_value is required")
    end_at = _customer_event_time(body.get("end_at")).date()
    period_label = (body.get("period_label") or "").strip()[:80]
    belief = (body.get("belief") or "plausible").strip()[:16]
    if belief not in TARGET_BELIEFS:
        raise HTTPException(
            status_code=400,
            detail=f"belief must be one of {', '.join(TARGET_BELIEFS)}",
        )
    existing = (
        await db.execute(
            select(BusinessTarget).where(
                BusinessTarget.organization_id == org.id,
                BusinessTarget.metric_id == metric_id,
                BusinessTarget.period_label == period_label,
            )
        )
    ).scalar_one_or_none()
    created = existing is None
    event = await publish_event(
        db, name="business.target.created" if created else "business.target.updated",
        organization_id=org.id, actor_id=user.id,
        payload={
            "organization_id": org.id,
            "metric_id": metric_id,
            "metric_key": metric_key,
            "target_value": target_value,
            "unit": (body.get("unit") or "")[:40],
            "start_at": _customer_event_time(body.get("start_at")).date().isoformat()
            if body.get("start_at") else None,
            "end_at": end_at.isoformat(),
            "period_label": period_label,
            "belief": belief,
            "rationale": (body.get("rationale") or "")[:4000] or None,
            "owner_label": (body.get("owner_label") or "")[:200],
            "initiative_labels": body.get("initiative_labels") or [],
            "dependency_labels": body.get("dependency_labels") or [],
            "open_decisions": body.get("open_decisions") or [],
            "strategy_label": (body.get("strategy_label") or "")[:300],
            "project_labels": body.get("project_labels") or [],
            "periods": body.get("periods") or [],
        },
    )
    await db.commit()
    return {
        "target_id": getattr(event, "id", ""),
        "created": created,
        "metric_key": metric_key,
        "period_label": period_label,
        "source_event_id": getattr(event, "id", ""),
        "generated_at": _utcnow_iso(),
    }


@router.post("/execution/business/forecasts")
async def brain_business_create_forecast(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Commit (or revise) a bounded forecast arc for a business metric.
    Projected knowledge only — always labeled as such, never observed fact."""
    from app.models.business_performance import FORECAST_TYPES, BusinessForecast
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    metric_key = (body.get("metric_key") or "").strip()
    metric_id = (body.get("metric_id") or "").strip()
    if metric_id:
        from app.models.business_performance import BusinessMetric

        metric = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == org.id,
                    BusinessMetric.id == metric_id,
                )
            )
        ).scalar_one_or_none()
        if metric is None:
            raise HTTPException(status_code=404, detail="metric not found")
        metric_key = metric.key or metric_key
    elif metric_key:
        metric = await _business_metric_or_404(db, org, metric_key)
        metric_id = metric.id
    else:
        raise HTTPException(status_code=400, detail="metric_key (or metric_id) is required")
    forecast_type = (body.get("forecast_type") or "base").strip()[:16]
    if forecast_type not in FORECAST_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"forecast_type must be one of {', '.join(FORECAST_TYPES)}",
        )
    horizon_label = (body.get("horizon_label") or "").strip()[:80]
    if not horizon_label:
        raise HTTPException(status_code=400, detail="horizon_label is required")
    confidence = _business_float(body.get("confidence"), "confidence")
    if confidence is not None and not 0 <= confidence <= 1:
        raise HTTPException(status_code=400, detail="confidence must be between 0 and 1")
    existing = (
        await db.execute(
            select(BusinessForecast).where(
                BusinessForecast.organization_id == org.id,
                BusinessForecast.metric_id == metric_id,
                BusinessForecast.horizon_label == horizon_label,
                BusinessForecast.forecast_type == forecast_type,
            )
        )
    ).scalar_one_or_none()
    created = existing is None
    event = await publish_event(
        db, name="business.forecast.created" if created else "business.forecast.updated",
        organization_id=org.id, actor_id=user.id,
        payload={
            "organization_id": org.id,
            "metric_id": metric_id,
            "metric_key": metric_key,
            "horizon_label": horizon_label,
            "forecast_type": forecast_type,
            "basis": (body.get("basis") or "")[:300],
            "path": body.get("path") or [],
            "low": _business_float(body.get("low"), "low"),
            "midpoint": _business_float(body.get("midpoint"), "midpoint"),
            "high": _business_float(body.get("high"), "high"),
            "confidence": confidence if confidence is not None else 0.5,
            "confidence_basis": (body.get("confidence_basis") or "")[:300],
            "required_conditions": body.get("required_conditions") or [],
            "risk_factors": body.get("risk_factors") or [],
            "growth_rate": _business_float(body.get("growth_rate"), "growth_rate"),
        },
    )
    await db.commit()
    return {
        "forecast_id": getattr(event, "id", ""),
        "created": created,
        "metric_key": metric_key,
        "horizon_label": horizon_label,
        "source_event_id": getattr(event, "id", ""),
        "generated_at": _utcnow_iso(),
    }


@router.post("/execution/business/drivers")
async def brain_business_detect_driver(
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record a detected business driver: evidence-backed, with the
    deterministic link language to the affected metrics (linked to /
    strongly associated with / evidence indicates)."""
    from app.models.business_performance import (
        DRIVER_DIRECTIONS,
        DRIVER_STRENGTHS,
        DRIVER_TYPES,
        IMPACT_SHAPES,
    )
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    key = (body.get("key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    title = (body.get("title") or key)[:200]
    driver_type = (body.get("driver_type") or "market").strip()[:24]
    if driver_type not in DRIVER_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"driver_type must be one of {', '.join(DRIVER_TYPES)}",
        )
    strength = (body.get("strength") or "moderate").strip()[:16]
    if strength not in DRIVER_STRENGTHS:
        raise HTTPException(
            status_code=400,
            detail=f"strength must be one of {', '.join(DRIVER_STRENGTHS)}",
        )
    direction = (body.get("direction") or "toward").strip()[:16]
    if direction not in DRIVER_DIRECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"direction must be one of {', '.join(DRIVER_DIRECTIONS)}",
        )
    impact_shape = (body.get("impact_shape") or "aggregation").strip()[:16]
    if impact_shape not in IMPACT_SHAPES:
        raise HTTPException(
            status_code=400,
            detail=f"impact_shape must be one of {', '.join(IMPACT_SHAPES)}",
        )
    event = await publish_event(
        db, name="business.driver.detected", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "key": key,
            "title": title,
            "driver_type": driver_type,
            "strength": strength,
            "direction": direction,
            "impact_shape": impact_shape,
            "metric_keys": body.get("metric_keys") or [],
            "monetized_impact": _business_float(body.get("monetized_impact"), "monetized_impact"),
            "evidence_count": body.get("evidence_count") or 0,
            "note": (body.get("note") or "")[:4000] or None,
        },
    )
    await db.commit()
    return {
        "driver_key": key,
        "source_event_id": getattr(event, "id", ""),
        "generated_at": _utcnow_iso(),
    }


@router.get("/execution/business/metrics")
async def brain_business_metrics(
    scope: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The business metric ledger: every metric with its current/previous
    value, direction-aware trend and linked targets."""
    from app.intelligence.business_performance_engine import business_performance_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await business_performance_engine.metrics(
        db, organization_id=org.id, scope=scope or None,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/business/metrics/{metric_key}")
async def brain_business_metric(
    metric_key: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One metric's full evidence: the observation series, targets,
    forecasts, drivers and recorded links."""
    from app.intelligence.business_performance_engine import (
        _metric_key,
        business_performance_engine,
    )
    from app.models.business_performance import BusinessMetric

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    metric = (
        await db.execute(
            select(BusinessMetric).where(
                BusinessMetric.organization_id == org.id,
                BusinessMetric.key == _metric_key(metric_key),
            )
        )
    ).scalar_one_or_none()
    if metric is None:
        raise HTTPException(status_code=404, detail="metric not found")
    result = await business_performance_engine.metric(
        db, organization_id=org.id, metric_id=metric.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="metric not found")
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/business/targets")
async def brain_business_targets(
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The committed target ledger with deterministic statuses and gaps."""
    from app.intelligence.business_performance_engine import business_performance_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await business_performance_engine.targets(
        db, organization_id=org.id, status=status or None,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/business/targets/{target_id}")
async def brain_business_target(
    target_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One target's command center: metric, observations, gap analysis,
    linked initiatives/projects/dependencies/decisions."""
    from app.intelligence.business_performance_engine import business_performance_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await business_performance_engine.target(
        db, organization_id=org.id, target_id=target_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="target not found")
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/business/forecasts")
async def brain_business_forecasts(
    metric_key: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The forecast ledger: conservative/base/optimistic arcs with their
    basis and confidence — always labeled as projected, never observed."""
    from app.intelligence.business_performance_engine import business_performance_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await business_performance_engine.forecasts(
        db, organization_id=org.id, metric_key=metric_key or None,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/business/drivers")
async def brain_business_drivers(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The detected driver ledger with the deterministic link language to
    the metrics they move."""
    from app.intelligence.business_performance_engine import business_performance_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await business_performance_engine.drivers(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/business/performance")
async def brain_business_performance(
    scope: str = "org_wide",
    scope_entity_id: str = "",
    period_label: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The current evidence-backed performance assessment of a scope:
    multidimensional health, trajectories, drivers, gains/losses and the
    summary narrative."""
    from app.intelligence.business_performance_engine import business_performance_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await business_performance_engine.performance(
        db, organization_id=org.id, scope=scope,
        scope_entity_id=scope_entity_id, period_label=period_label or None,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="no performance evidence yet")
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/business/behind-target")
async def brain_business_behind_target(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The flagship 'why are we behind target' chain: target -> gap ->
    drivers -> customers -> knowledge -> strategy -> projects -> capacity
    -> decisions -> what to do. Advisory only."""
    from app.intelligence.business_performance_engine import business_performance_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await business_performance_engine.behind_target(
        db, organization_id=org.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="no target yet")
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/business/recommendations")
async def brain_business_recommendations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """What leadership should do next, derived deterministically from the
    current snapshot and the target ledger. Advisory only, bounded, every
    item carries its evidence."""
    from app.intelligence.business_performance_engine import business_performance_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await business_performance_engine.recommendations(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


# ---------------------------------------------------------------------------
# Slice 4G.7 — Universal Company Operating Intelligence
#
# The company-level operating layer: one composed company state, eight-domain
# company health with root causes, root-cause chains, impact propagation, the
# universal recommendation queue, bounded what-if scenarios, "What changed?"
# synthesis, and the company memory (decision -> reason -> action -> outcome
# -> learning). Every read composes the canonical 4G.1-4G.6 engines; the only
# writes are governed human approvals (advisory-first — nothing executes
# without a human).
# ---------------------------------------------------------------------------


@router.get("/execution/company/state")
async def brain_company_state(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The universal company state: one composed picture of the company as a
    whole — strategy, execution, coordination, capacity, people, customers,
    financial and knowledge — plus what the company as a whole should pay
    attention to next."""
    from app.intelligence.company_operating_engine import company_operating_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    result = await company_operating_engine.company_state(
        db, organization_id=org.id,
    )
    return {**result, "generated_at": _utcnow_iso()}


@router.get("/execution/company/health")
async def brain_company_health(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Eight-domain company health with the primary constraint, its root
    cause and interventions — the answer to 'how is the company as a whole
    doing'."""
    from app.intelligence.company_operating_engine import company_operating_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    return await company_operating_engine.health(
        db, organization_id=org.id,
    )


@router.get("/execution/company/root-cause")
async def brain_company_root_cause(
    problem: str = Query(..., min_length=1),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Walk a business problem down to people and capability: business
    problem -> metric -> driver -> customer impact -> project ->
    task/dependency -> capacity constraint -> people/capability."""
    from app.intelligence.company_operating_engine import company_operating_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    return await company_operating_engine.root_cause(
        db, organization_id=org.id, problem=problem,
    )


@router.get("/execution/company/impact")
async def brain_company_impact(
    subject_type: str = Query(...),
    subject_id: str = Query(..., min_length=1),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Propagate a change across the company: person | project | capability |
    customer | goal -> execution -> strategy -> customers -> business."""
    from app.intelligence.company_operating_engine import company_operating_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    return await company_operating_engine.impact(
        db, organization_id=org.id,
        subject_type=subject_type, subject_id=subject_id,
    )


@router.get("/execution/company/recommendations")
async def brain_company_recommendations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The universal company recommendation queue: what the company as a whole
    should do next, prioritized, evidence-carrying, advisory-only."""
    from app.intelligence.company_operating_engine import company_operating_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    return await company_operating_engine.recommendations(
        db, organization_id=org.id,
    )


class BrainCompanyWhatIfIn(BaseModel):
    scenario_type: str
    payload: Optional[dict[str, Any]] = None
    project_id: Optional[str] = None
    days: Optional[int] = None
    capability: Optional[str] = None
    from_project_id: Optional[str] = None
    to_project_id: Optional[str] = None
    units: Optional[int] = None
    people: Optional[int] = None
    ramp_days: Optional[int] = None


@router.post("/execution/company/what-if")
async def brain_company_what_if(
    body: BrainCompanyWhatIfIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bounded deterministic consequences of a scenario — reallocate | delay |
    hire. Never a prediction, never executed; humans decide."""
    from app.intelligence.company_operating_engine import company_operating_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    flat = body.model_dump(exclude_none=True)
    scenario_payload = body.payload or {
        k: v for k, v in flat.items()
        if k in ("project_id", "days", "capability", "from_project_id",
                 "to_project_id", "units", "people", "ramp_days")
    }
    return await company_operating_engine.what_if(
        db, organization_id=org.id,
        scenario_type=body.scenario_type,
        payload=scenario_payload,
    )


@router.get("/execution/company/changes")
async def brain_company_changes(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """'What changed?' — the meaningful company-level deltas since the
    previous health assessment, each with why it matters."""
    from app.intelligence.company_operating_engine import company_operating_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    return await company_operating_engine.changes(
        db, organization_id=org.id,
    )


@router.get("/execution/company/memory")
async def brain_company_memory(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("brain:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Company memory: the governed decision history and what the company
    learned (decision -> reason -> action -> outcome -> learning)."""
    from app.intelligence.company_operating_engine import company_operating_engine

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    return await company_operating_engine.memory(
        db, organization_id=org.id,
    )


class BrainCompanyDecisionIn(BaseModel):
    kind: str
    title: str
    recommendation_key: Optional[str] = None
    rationale: Optional[str] = None
    note: Optional[str] = None
    impact_label: Optional[str] = None
    expected_improvement: Optional[str] = None
    confidence: Optional[float] = None
    owner_label: Optional[str] = None
    state: Optional[str] = None


@router.post("/execution/company/decisions")
async def brain_company_record_decision(
    body: BrainCompanyDecisionIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """GOVERNED WRITE — a human approves (or declines) a company
    recommendation. Nothing executes without this human approval; the
    decision becomes part of company memory."""
    import uuid as _uuid

    from app.models.company_operating import DECISION_KINDS, DECISION_STATES
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    kind = (body.kind or "").strip()
    title = (body.title or "").strip()
    if kind not in DECISION_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {', '.join(DECISION_KINDS)}",
        )
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    state = (body.state or "approved").strip()
    if state not in DECISION_STATES or state not in ("approved", "declined"):
        raise HTTPException(status_code=400, detail="state must be approved or declined")
    if body.confidence is not None and not (0.0 <= body.confidence <= 1.0):
        raise HTTPException(status_code=400, detail="confidence must be between 0 and 1")
    decision_id = f"dec:{kind}:{_uuid.uuid4().hex[:12]}"
    event = await publish_event(
        db, name="company.decision.recorded", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "decision_id": decision_id,
            "kind": kind,
            "title": title,
            "recommendation_key": (body.recommendation_key or "").strip(),
            "rationale": (body.rationale or "").strip(),
            "note": (body.note or "").strip(),
            "impact_label": (body.impact_label or "").strip(),
            "expected_improvement": (body.expected_improvement or "").strip(),
            "confidence": body.confidence,
"owner_label": (body.owner_label or "").strip(),
                "state": state,
                "approver_label": (user.full_name or user.email or user.id),
            },
    )
    await db.commit()
    return {
        "decision_recorded": True,
        "decision_id": decision_id,
        "kind": kind,
        "title": title,
        "state": state,
        "source_event_id": getattr(event, "id", ""),
        "generated_at": _utcnow_iso(),
    }


@router.post("/execution/company/decisions/{decision_id}/execute")
async def brain_company_execute_decision(
    decision_id: str,
    body: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """GOVERNED WRITE — mark an approved company decision as executed (the
    human action that closes the recommendation -> action loop)."""
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    event = await publish_event(
        db, name="company.action.executed", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "decision_id": decision_id,
            "executed_by_label": (
                (body.get("executed_by_label") or "").strip()
                or (user.full_name or user.email or user.id)
            ),
        },
    )
    await db.commit()
    return {
        "executed": True,
        "decision_id": decision_id,
        "source_event_id": getattr(event, "id", ""),
        "generated_at": _utcnow_iso(),
    }


class BrainCompanyOutcomeIn(BaseModel):
    outcome_kind: str
    effectiveness: Optional[float] = None
    lesson: Optional[str] = None
    evidence: Optional[list] = None


@router.post("/execution/company/decisions/{decision_id}/outcome")
async def brain_company_record_outcome(
    decision_id: str,
    body: BrainCompanyOutcomeIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("projects:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """GOVERNED WRITE — record the observed outcome + lesson of an executed
    company action. Closes the learning loop: the lesson becomes part of
    company memory that future recommendations cite."""
    from app.models.company_operating import OUTCOME_KINDS
    from app.events.publisher import publish_event

    access = await _people_access(db, org, user)
    if not access.org_wide:
        raise HTTPException(status_code=404, detail="scope not found")
    outcome_kind = (body.outcome_kind or "").strip()
    if outcome_kind not in OUTCOME_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"outcome_kind must be one of {', '.join(OUTCOME_KINDS)}",
        )
    if body.effectiveness is not None and not (0.0 <= body.effectiveness <= 1.0):
        raise HTTPException(status_code=400, detail="effectiveness must be between 0 and 1")
    event = await publish_event(
        db, name="company.outcome.recorded", organization_id=org.id,
        actor_id=user.id,
        payload={
            "organization_id": org.id,
            "decision_id": decision_id,
            "outcome_kind": outcome_kind,
            "effectiveness": body.effectiveness,
            "lesson": (body.lesson or "").strip(),
            "evidence": body.evidence or [],
        },
    )
    await db.commit()
    return {
        "outcome_recorded": True,
        "decision_id": decision_id,
        "outcome_kind": outcome_kind,
        "source_event_id": getattr(event, "id", ""),
        "generated_at": _utcnow_iso(),
    }
