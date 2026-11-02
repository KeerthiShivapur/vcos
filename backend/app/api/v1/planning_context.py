"""Phase 4I.4 — Company Planning Context / State Synthesis API.

Governance-first API for the canonical state-synthesis layer of the Virtual Company OS.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.intelligence.company_planning_context_engine import company_planning_context_engine
from app.intelligence.company_context import resolve_caller_access
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/planning-context", tags=["Company Planning Context"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class PlanningContextSynthesizeIn(BaseModel):
    scope: str = "company"
    scope_id: Optional[str] = None
    trigger: str = "manual_recompute"
    source_event_id: Optional[str] = None
    trigger_reason: Optional[str] = None


class PlanningContextRecomputeIn(BaseModel):
    trigger: str
    source_event_id: Optional[str] = None
    trigger_reason: Optional[str] = None
    scope: str = "company"
    scope_id: Optional[str] = None


class PlanningQuestionIn(BaseModel):
    question: str
    scope: str = "company"
    scope_id: Optional[str] = None


class PlanningContextResponse(BaseModel):
    id: str
    organization_id: str
    scope: str
    scope_id: Optional[str]
    version: int
    previous_version_id: Optional[str]
    overall_health: str
    overall_confidence: float
    active_contradictions: int
    critical_gaps: int
    total_gaps: int
    relevant_lessons: int
    high_confidence_lessons: int
    emerging_patterns: int
    elevated_risks: int
    newly_emerging_risks: int
    computed_at: str
    computation_duration_ms: int
    trigger: str
    source_event_id: Optional[str]
    strategic_state: dict
    execution_state: dict
    outcome_state: dict
    alignment_state: dict
    learning_state: dict
    resource_state: dict
    risk_state: dict
    governance_state: dict


class StateTransitionResponse(BaseModel):
    id: str
    organization_id: str
    scope: str
    scope_id: Optional[str]
    from_version: int
    to_version: int
    from_context_id: str
    to_context_id: str
    trigger: str
    trigger_event_id: Optional[str]
    trigger_reason: str
    transition_kind: str
    delta: dict
    changed_sections: list[str]
    new_contradictions: list[str]
    resolved_contradictions: list[str]
    new_gaps: list[str]
    resolved_gaps: list[str]
    influencing_lessons: list[str]
    influencing_patterns: list[str]
    state: str
    committed_by: Optional[str]
    committed_at: Optional[str]
    transitioned_at: str


class ProvenanceResponse(BaseModel):
    id: str
    organization_id: str
    context_id: str
    section: str
    conclusion_key: str
    conclusion_value: Any
    epistemic_status: str
    confidence: float
    evidence_fingerprints: list[str]
    pattern_ids: list[str]
    lesson_fingerprints: list[str]
    contradicting_evidence_fingerprints: list[str]
    contradicting_pattern_ids: list[str]
    contradicting_lesson_fingerprints: list[str]
    contradiction_ids: list[str]
    source_entities: list[dict]
    intent_id: Optional[str]
    goal_id: Optional[str]
    objective_id: Optional[str]
    initiative_id: Optional[str]
    project_id: Optional[str]
    scope: str
    scope_id: Optional[str]
    generated_at: str
    generated_by: str
    source_event_id: Optional[str]


class PlanningQuestionResponse(BaseModel):
    question: str
    context_version: int
    context_computed_at: Optional[str]
    overall_health: str
    overall_confidence: float
    strategic_summary: dict
    execution_summary: dict
    outcome_summary: dict
    alignment_summary: dict
    learning_summary: dict
    resource_summary: dict
    risk_summary: dict
    governance_summary: dict
    active_contradictions: int
    critical_gaps: int
    relevant_lessons: int
    elevated_risks: int
    provenance_available: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/synthesize", response_model=PlanningContextResponse)
async def synthesize_planning_context(
    payload: PlanningContextSynthesizeIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("planning_context.write")),
):
    """
    Synthesize the company planning context from all canonical sources.
    
    This is the primary endpoint that computes the complete organizational state
    from 4I.1 (Intent), 4I.2 (Objectives/Outcomes), 4I.3 (Alignment),
    4H.7 (Learning), and all operating substrates.
    """
    # Governance: verify caller access to scope
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if payload.scope != "company" and payload.scope_id:
        if not access.org_wide:
            if payload.scope == "project" and payload.scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif payload.scope in ("department", "team") and payload.scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    context = await company_planning_context_engine.synthesize_planning_context(
        db,
        org.id,
        scope=payload.scope,
        scope_id=payload.scope_id,
        trigger=payload.trigger,
        source_event_id=payload.source_event_id,
        trigger_reason=payload.trigger_reason,
    )
    
    return PlanningContextResponse(
        id=context.id,
        organization_id=context.organization_id,
        scope=context.scope,
        scope_id=context.scope_id,
        version=context.version,
        previous_version_id=context.previous_version_id,
        overall_health=context.overall_health,
        overall_confidence=context.overall_confidence,
        active_contradictions=context.active_contradictions,
        critical_gaps=context.critical_gaps,
        total_gaps=context.total_gaps,
        relevant_lessons=context.relevant_lessons,
        high_confidence_lessons=context.high_confidence_lessons,
        emerging_patterns=context.emerging_patterns,
        elevated_risks=context.elevated_risks,
        newly_emerging_risks=context.newly_emerging_risks,
        computed_at=context.computed_at.isoformat() if context.computed_at else "",
        computation_duration_ms=context.computation_duration_ms,
        trigger=context.trigger,
        source_event_id=context.source_event_id,
        strategic_state=context.strategic_state or {},
        execution_state=context.execution_state or {},
        outcome_state=context.outcome_state or {},
        alignment_state=context.alignment_state or {},
        learning_state=context.learning_state or {},
        resource_state=context.resource_state or {},
        risk_state=context.risk_state or {},
        governance_state=context.governance_state or {},
    )


@router.post("/recompute", response_model=PlanningContextResponse)
async def trigger_recompute(
    payload: PlanningContextRecomputeIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("planning_context.write")),
):
    """
    Trigger a recomputation of the planning context due to a state change.
    
    Valid triggers: new_evidence, new_outcome, new_lesson, new_pattern,
    new_contradiction, alignment_change, dependency_change, resource_change,
    governance_decision, prediction_change, supersession, manual_recompute
    """
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if payload.scope != "company" and payload.scope_id:
        if not access.org_wide:
            if payload.scope == "project" and payload.scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif payload.scope in ("department", "team") and payload.scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    context = await company_planning_context_engine.trigger_recompute(
        db,
        org.id,
        trigger=payload.trigger,
        source_event_id=payload.source_event_id,
        trigger_reason=payload.trigger_reason,
        scope=payload.scope,
        scope_id=payload.scope_id,
    )
    
    return PlanningContextResponse(
        id=context.id,
        organization_id=context.organization_id,
        scope=context.scope,
        scope_id=context.scope_id,
        version=context.version,
        previous_version_id=context.previous_version_id,
        overall_health=context.overall_health,
        overall_confidence=context.overall_confidence,
        active_contradictions=context.active_contradictions,
        critical_gaps=context.critical_gaps,
        total_gaps=context.total_gaps,
        relevant_lessons=context.relevant_lessons,
        high_confidence_lessons=context.high_confidence_lessons,
        emerging_patterns=context.emerging_patterns,
        elevated_risks=context.elevated_risks,
        newly_emerging_risks=context.newly_emerging_risks,
        computed_at=context.computed_at.isoformat() if context.computed_at else "",
        computation_duration_ms=context.computation_duration_ms,
        trigger=context.trigger,
        source_event_id=context.source_event_id,
        strategic_state=context.strategic_state or {},
        execution_state=context.execution_state or {},
        outcome_state=context.outcome_state or {},
        alignment_state=context.alignment_state or {},
        learning_state=context.learning_state or {},
        risk_state=context.risk_state or {},
        governance_state=context.governance_state or {},
    )


@router.get("/current", response_model=PlanningContextResponse)
async def get_current_context(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    version: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("planning_context.read")),
):
    """Get the current (or specific version) planning context."""
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if scope != "company" and scope_id:
        if not access.org_wide:
            if scope == "project" and scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif scope in ("department", "team") and scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    context = await company_planning_context_engine.get_planning_context(
        db, org.id, scope=scope, scope_id=scope_id, version=version
    )
    
    if not context:
        raise HTTPException(404, "Planning context not found")
    
    return PlanningContextResponse(
        id=context.id,
        organization_id=context.organization_id,
        scope=context.scope,
        scope_id=context.scope_id,
        version=context.version,
        previous_version_id=context.previous_version_id,
        overall_health=context.overall_health,
        overall_confidence=context.overall_confidence,
        active_contradictions=context.active_contradictions,
        critical_gaps=context.critical_gaps,
        total_gaps=context.total_gaps,
        relevant_lessons=context.relevant_lessons,
        high_confidence_lessons=context.high_confidence_lessons,
        emerging_patterns=context.emerging_patterns,
        elevated_risks=context.elevated_risks,
        newly_emerging_risks=context.newly_emerging_risks,
        computed_at=context.computed_at.isoformat() if context.computed_at else "",
        computation_duration_ms=context.computation_duration_ms,
        trigger=context.trigger,
        source_event_id=context.source_event_id,
        strategic_state=context.strategic_state or {},
        execution_state=context.execution_state or {},
        outcome_state=context.outcome_state or {},
        alignment_state=context.alignment_state or {},
        learning_state=context.learning_state or {},
        resource_state=context.resource_state or {},
        risk_state=context.risk_state or {},
        governance_state=context.governance_state or {},
    )


@router.get("/transitions", response_model=list[StateTransitionResponse])
async def get_state_transitions(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    from_version: Optional[int] = Query(None),
    to_version: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("planning_context.read")),
):
    """Get state transition history for the planning context."""
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if scope != "company" and scope_id:
        if not access.org_wide:
            if scope == "project" and scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif scope in ("department", "team") and scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    transitions = await company_planning_context_engine.get_state_transitions(
        db, org.id, scope=scope, scope_id=scope_id,
        from_version=from_version, to_version=to_version, limit=limit
    )
    
    return [
        StateTransitionResponse(
            id=t.id,
            organization_id=t.organization_id,
            scope=t.scope,
            scope_id=t.scope_id,
            from_version=t.from_version,
            to_version=t.to_version,
            from_context_id=t.from_context_id,
            to_context_id=t.to_context_id,
            trigger=t.trigger,
            trigger_event_id=t.trigger_event_id,
            trigger_reason=t.trigger_reason,
            transition_kind=t.transition_kind,
            delta=t.delta,
            changed_sections=t.changed_sections,
            new_contradictions=t.new_contradictions,
            resolved_contradictions=t.resolved_contradictions,
            new_gaps=t.new_gaps,
            resolved_gaps=t.resolved_gaps,
            influencing_lessons=t.influencing_lessons,
            influencing_patterns=t.influencing_patterns,
            state=t.state,
            committed_by=t.committed_by,
            committed_at=t.committed_at.isoformat() if t.committed_at else None,
            transitioned_at=t.transitioned_at.isoformat() if t.transitioned_at else "",
        )
        for t in transitions
    ]


@router.get("/provenance/{context_id}", response_model=list[ProvenanceResponse])
async def get_full_provenance_chain(
    context_id: str,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("planning_context.read")),
):
    """Get the complete provenance chain for a planning context."""
    provenance = await company_planning_context_engine.get_full_provenance_chain(
        db, org.id, context_id
    )
    
    return [
        ProvenanceResponse(
            id=p.id,
            organization_id=p.organization_id,
            context_id=p.context_id,
            section=p.section,
            conclusion_key=p.conclusion_key,
            conclusion_value=p.conclusion_value,
            epistemic_status=p.epistemic_status,
            confidence=p.confidence,
            evidence_fingerprints=p.evidence_fingerprints,
            pattern_ids=p.pattern_ids,
            lesson_fingerprints=p.lesson_fingerprints,
            contradicting_evidence_fingerprints=p.contradicting_evidence_fingerprints,
            contradicting_pattern_ids=p.contradicting_pattern_ids,
            contradicting_lesson_fingerprints=p.contradicting_lesson_fingerprints,
            contradiction_ids=p.contradiction_ids,
            source_entities=p.source_entities,
            intent_id=p.intent_id,
            goal_id=p.goal_id,
            objective_id=p.objective_id,
            initiative_id=p.initiative_id,
            project_id=p.project_id,
            scope=p.scope,
            scope_id=p.scope_id,
            generated_at=p.generated_at.isoformat() if p.generated_at else "",
            generated_by=p.generated_by,
            source_event_id=p.source_event_id,
        )
        for p in provenance
    ]


@router.get("/provenance/{context_id}/{section}/{conclusion_key}", response_model=ProvenanceResponse)
async def get_provenance_for_conclusion(
    context_id: str,
    section: str,
    conclusion_key: str,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("planning_context.read")),
):
    """Get provenance chain for a specific conclusion."""
    provenance = await company_planning_context_engine.get_provenance_for_conclusion(
        db, org.id, context_id, section, conclusion_key
    )
    
    if not provenance:
        raise HTTPException(404, "Provenance not found")
    
    return ProvenanceResponse(
        id=provenance.id,
        organization_id=provenance.organization_id,
        context_id=provenance.context_id,
        section=provenance.section,
        conclusion_key=provenance.conclusion_key,
        conclusion_value=provenance.conclusion_value,
        epistemic_status=provenance.epistemic_status,
        confidence=provenance.confidence,
        evidence_fingerprints=provenance.evidence_fingerprints,
        pattern_ids=provenance.pattern_ids,
        lesson_fingerprints=provenance.lesson_fingerprints,
        contradicting_evidence_fingerprints=provenance.contradicting_evidence_fingerprints,
        contradicting_pattern_ids=provenance.contradicting_pattern_ids,
        contradicting_lesson_fingerprints=provenance.contradicting_lesson_fingerprints,
        contradiction_ids=provenance.contradiction_ids,
        source_entities=provenance.source_entities,
        intent_id=provenance.intent_id,
        goal_id=provenance.goal_id,
        objective_id=provenance.objective_id,
        initiative_id=provenance.initiative_id,
        project_id=provenance.project_id,
        scope=provenance.scope,
        scope_id=provenance.scope_id,
        generated_at=provenance.generated_at.isoformat() if provenance.generated_at else "",
        generated_by=provenance.generated_by,
        source_event_id=provenance.source_event_id,
    )


@router.post("/ask", response_model=PlanningQuestionResponse)
async def ask_planning_question(
    payload: PlanningQuestionIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("planning_context.read")),
):
    """
    Ask a planning question using the synthesized planning context.
    
    This integrates with the Company Brain's governance-first retrieval.
    Returns a structured answer with full provenance availability.
    """
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if payload.scope != "company" and payload.scope_id:
        if not access.org_wide:
            if payload.scope == "project" and payload.scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif payload.scope in ("department", "team") and payload.scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    answer = await company_planning_context_engine.answer_planning_question(
        db, org.id, payload.question, user=user, scope=payload.scope, scope_id=payload.scope_id
    )
    
    return PlanningQuestionResponse(**answer)


@router.get("/health", response_model=dict)
async def get_planning_context_health(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("planning_context.read")),
):
    """Get a quick health summary without full context synthesis."""
    context = await company_planning_context_engine.get_planning_context(
        db, org.id, scope=scope, scope_id=scope_id
    )
    
    if not context:
        # Try to synthesize
        context = await company_planning_context_engine.synthesize_planning_context(
            db, org.id, scope=scope, scope_id=scope_id
        )
    
    return {
        "overall_health": context.overall_health,
        "overall_confidence": context.overall_confidence,
        "version": context.version,
        "computed_at": context.computed_at.isoformat() if context.computed_at else None,
        "active_contradictions": context.active_contradictions,
        "critical_gaps": context.critical_gaps,
        "total_gaps": context.total_gaps,
        "relevant_lessons": context.relevant_lessons,
        "high_confidence_lessons": context.high_confidence_lessons,
        "emerging_patterns": context.emerging_patterns,
        "elevated_risks": context.elevated_risks,
        "newly_emerging_risks": context.newly_emerging_risks,
    }