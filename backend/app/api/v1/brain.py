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
