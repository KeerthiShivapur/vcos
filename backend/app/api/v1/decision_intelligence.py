"""Phase 4I.6 â€” Decision Intelligence API.

Governance-first API for the decision intelligence layer that consumes all
canonical VCOS substrates to produce comprehensive decision intelligence contexts.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.intelligence.decision_intelligence_engine import decision_intelligence_engine
from app.intelligence.company_context import resolve_caller_access
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/decision-intelligence", tags=["Decision Intelligence"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class DecisionIntelligenceSynthesizeIn(BaseModel):
    decision_type: str
    title: str
    description: Optional[str] = None
    scope: str = "company"
    scope_id: Optional[str] = None
    trigger: str = "manual_synthesis"
    source_event_id: Optional[str] = None
    trigger_reason: Optional[str] = None


class DecisionIntelligenceRecomputeIn(BaseModel):
    trigger: str
    source_event_id: Optional[str] = None
    trigger_reason: Optional[str] = None
    scope: str = "company"
    scope_id: Optional[str] = None


class DecisionQuestionIn(BaseModel):
    question: str
    scope: str = "company"
    scope_id: Optional[str] = None


class DecisionIntelligenceResponse(BaseModel):
    id: str
    organization_id: str
    scope: str
    scope_id: Optional[str]
    planning_context_id: str
    planning_context_version: int
    planning_context_fingerprint: str
    adaptive_context_id: Optional[str]
    version: int
    previous_version_id: Optional[str]
    decision_type: str
    title: str
    description: Optional[str]
    trigger: str
    trigger_event_id: Optional[str]
    trigger_reason: Optional[str]
    overall_confidence: float
    active_contradictions: int
    critical_gaps: int
    elevated_risks: int
    high_confidence_lessons: int
    computed_at: str
    computation_duration_ms: int
    trigger: str
    source_event_id: Optional[str]
    strategic_context: dict
    objective_context: dict
    alignment_context: dict
    outcome_context: dict
    execution_context: dict
    resource_context: dict
    risk_context: dict
    learning_context: dict
    governance_context: dict


class DecisionIntelligenceTransitionResponse(BaseModel):
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
    fingerprint: str


class DecisionQuestionResponse(BaseModel):
    question: str
    context_version: int
    context_computed_at: Optional[str]
    overall_confidence: float
    decision_type: str
    strategic_context: dict
    objective_context: dict
    alignment_context: dict
    outcome_context: dict
    execution_context: dict
    resource_context: dict
    risk_context: dict
    learning_context: dict
    governance_context: dict
    active_contradictions: int
    critical_gaps: int
    elevated_risks: int
    high_confidence_lessons: int
    provenance_available: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/synthesize", response_model=DecisionIntelligenceResponse)
async def synthesize_decision_intelligence(
    payload: DecisionIntelligenceSynthesizeIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("decisions:manage")),
):
    """
    Synthesize the decision intelligence context from all canonical sources.
    
    This is the primary endpoint that computes the complete decision intelligence
    from 4I.1 (Intent), 4I.2 (Objectives/Outcomes), 4I.3 (Alignment),
    4I.4 (Planning Context), 4I.5 (Adaptive Planning), 4H.7 (Learning),
    and all operating substrates.
    """
    # Governance: verify caller access to scope
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if payload.scope != "company" and payload.scope_id:
        if not access.org_wide:
            if payload.scope == "project" and payload.scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif payload.scope in ("department", "team") and payload.scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    # Validate decision type
    from app.models.execution_strategy import DECISION_INTELLIGENCE_TYPES
    if payload.decision_type not in DECISION_INTELLIGENCE_TYPES:
        raise HTTPException(400, f"Invalid decision type: {payload.decision_type}. Valid types: {DECISION_INTELLIGENCE_TYPES}")
    
    # Validate trigger
    from app.models.execution_strategy import STATE_TRANSITION_TRIGGERS
    if payload.trigger not in STATE_TRANSITION_TRIGGERS:
        payload.trigger = "manual_synthesis"
    
    context = await decision_intelligence_engine.synthesize_decision_intelligence(
        db,
        org.id,
        decision_type=payload.decision_type,
        title=payload.title,
        description=payload.description,
        scope=payload.scope,
        scope_id=payload.scope_id,
        trigger=payload.trigger,
        source_event_id=payload.source_event_id,
        trigger_reason=payload.trigger_reason,
    )
    
    return DecisionIntelligenceResponse(
        id=context.id,
        organization_id=context.organization_id,
        scope=context.scope,
        scope_id=context.scope_id,
        planning_context_id=context.planning_context_id,
        planning_context_version=context.planning_context_version,
        planning_context_fingerprint=context.planning_context_fingerprint,
        adaptive_context_id=context.adaptive_context_id,
        version=context.version,
        previous_version_id=context.previous_version_id,
        decision_type=context.decision_type,
        title=context.title,
        description=context.description,
        trigger=context.trigger,
        trigger_event_id=context.trigger_event_id,
        trigger_reason=context.trigger_reason,
        overall_confidence=context.overall_confidence,
        active_contradictions=context.active_contradictions,
        critical_gaps=context.critical_gaps,
        elevated_risks=context.elevated_risks,
        high_confidence_lessons=context.high_confidence_lessons,
        computed_at=context.computed_at.isoformat() if context.computed_at else "",
        computation_duration_ms=context.computation_duration_ms,
        source_event_id=context.source_event_id,
        strategic_context=context.strategic_context or {},
        objective_context=context.objective_context or {},
        alignment_context=context.alignment_context or {},
        outcome_context=context.outcome_context or {},
        execution_context=context.execution_context or {},
        resource_context=context.resource_context or {},
        risk_context=context.risk_context or {},
        learning_context=context.learning_context or {},
        governance_context=context.governance_context or {},
    )


@router.post("/recompute", response_model=DecisionIntelligenceResponse)
async def trigger_recompute(
    payload: DecisionIntelligenceRecomputeIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("decisions:manage")),
):
    """
    Trigger a recomputation of the decision intelligence context due to a state change.
    
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
    
    from app.models.execution_strategy import STATE_TRANSITION_TRIGGERS
    if payload.trigger not in STATE_TRANSITION_TRIGGERS:
        payload.trigger = "manual_recompute"
    
    context = await decision_intelligence_engine.trigger_recompute(
        db,
        org.id,
        trigger=payload.trigger,
        source_event_id=payload.source_event_id,
        trigger_reason=payload.trigger_reason,
        scope=payload.scope,
        scope_id=payload.scope_id,
    )
    
    return DecisionIntelligenceResponse(
        id=context.id,
        organization_id=context.organization_id,
        scope=context.scope,
        scope_id=context.scope_id,
        planning_context_id=context.planning_context_id,
        planning_context_version=context.planning_context_version,
        planning_context_fingerprint=context.planning_context_fingerprint,
        adaptive_context_id=context.adaptive_context_id,
        version=context.version,
        previous_version_id=context.previous_version_id,
        decision_type=context.decision_type,
        title=context.title,
        description=context.description,
        trigger=context.trigger,
        trigger_event_id=context.trigger_event_id,
        trigger_reason=context.trigger_reason,
        overall_confidence=context.overall_confidence,
        active_contradictions=context.active_contradictions,
        critical_gaps=context.critical_gaps,
        elevated_risks=context.elevated_risks,
        high_confidence_lessons=context.high_confidence_lessons,
        computed_at=context.computed_at.isoformat() if context.computed_at else "",
        computation_duration_ms=context.computation_duration_ms,
        source_event_id=context.source_event_id,
        strategic_context=context.strategic_context or {},
        objective_context=context.objective_context or {},
        alignment_context=context.alignment_context or {},
        outcome_context=context.outcome_context or {},
        execution_context=context.execution_context or {},
        resource_context=context.resource_context or {},
        risk_context=context.risk_context or {},
        learning_context=context.learning_context or {},
        governance_context=context.governance_context or {},
    )


@router.get("/current", response_model=DecisionIntelligenceResponse)
async def get_current_context(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    planning_context_id: Optional[str] = Query(None),
    version: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("decisions:read")),
):
    """Get the current (or specific version) decision intelligence context."""
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if scope != "company" and scope_id:
        if not access.org_wide:
            if scope == "project" and scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif scope in ("department", "team") and scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    context = await decision_intelligence_engine.get_decision_intelligence(
        db, org.id, scope=scope, scope_id=scope_id, 
        planning_context_id=planning_context_id, version=version
    )
    
    if not context:
        raise HTTPException(404, "Decision intelligence context not found")
    
    return DecisionIntelligenceResponse(
        id=context.id,
        organization_id=context.organization_id,
        scope=context.scope,
        scope_id=context.scope_id,
        planning_context_id=context.planning_context_id,
        planning_context_version=context.planning_context_version,
        planning_context_fingerprint=context.planning_context_fingerprint,
        adaptive_context_id=context.adaptive_context_id,
        version=context.version,
        previous_version_id=context.previous_version_id,
        decision_type=context.decision_type,
        title=context.title,
        description=context.description,
        trigger=context.trigger,
        trigger_event_id=context.trigger_event_id,
        trigger_reason=context.trigger_reason,
        overall_confidence=context.overall_confidence,
        active_contradictions=context.active_contradictions,
        critical_gaps=context.critical_gaps,
        elevated_risks=context.elevated_risks,
        high_confidence_lessons=context.high_confidence_lessons,
        computed_at=context.computed_at.isoformat() if context.computed_at else "",
        computation_duration_ms=context.computation_duration_ms,
        source_event_id=context.source_event_id,
        strategic_context=context.strategic_context or {},
        objective_context=context.objective_context or {},
        alignment_context=context.alignment_context or {},
        outcome_context=context.outcome_context or {},
        execution_context=context.execution_context or {},
        resource_context=context.resource_context or {},
        risk_context=context.risk_context or {},
        learning_context=context.learning_context or {},
        governance_context=context.governance_context or {},
    )


@router.get("/transitions", response_model=list[DecisionIntelligenceTransitionResponse])
async def get_transitions(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    from_version: Optional[int] = Query(None),
    to_version: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("decisions:read")),
):
    """Get decision intelligence transition history."""
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if scope != "company" and scope_id:
        if not access.org_wide:
            if scope == "project" and scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif scope in ("department", "team") and scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    transitions = await decision_intelligence_engine.get_transitions(
        db, org.id, scope=scope, scope_id=scope_id,
        from_version=from_version, to_version=to_version, limit=limit
    )
    
    return [
        DecisionIntelligenceTransitionResponse(
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
            fingerprint=t.fingerprint,
        )
        for t in transitions
    ]


@router.post("/ask", response_model=DecisionQuestionResponse)
async def ask_decision_question(
    payload: DecisionQuestionIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("decisions:read")),
):
    """
    Ask a decision intelligence question using the synthesized context.
    
    This integrates with the Company Brain's governance-first retrieval.
    """
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if payload.scope != "company" and payload.scope_id:
        if not access.org_wide:
            if payload.scope == "project" and payload.scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif payload.scope in ("department", "team") and payload.scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    answer = await decision_intelligence_engine.answer_decision_question(
        db, org.id, payload.question, user=user, scope=payload.scope, scope_id=payload.scope_id
    )
    
    return DecisionQuestionResponse(**answer)


@router.get("/health", response_model=dict)
async def get_decision_intelligence_health(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("decisions:read")),
):
    """Get a quick health summary without full context synthesis."""
    planning_context = await decision_intelligence_engine.company_planning_context_engine.get_planning_context(
        db, org.id, scope=scope, scope_id=scope_id
    )
    
    if not planning_context:
        planning_context = await decision_intelligence_engine.company_planning_context_engine.synthesize_planning_context(
            db, org.id, scope=scope, scope_id=scope_id
        )
    
    context = await decision_intelligence_engine.get_decision_intelligence(
        db, org.id, scope=scope, scope_id=scope_id, planning_context_id=planning_context.id
    )
    
    if not context:
        context = await decision_intelligence_engine.synthesize_decision_intelligence(
            db, org.id, decision_type="manual_synthesis", title="Health Check",
            scope=scope, scope_id=scope_id, planning_context=planning_context
        )
    
    return {
        "overall_confidence": context.overall_confidence,
        "version": context.version,
        "computed_at": context.computed_at.isoformat() if context.computed_at else None,
        "active_contradictions": context.active_contradictions,
        "critical_gaps": context.critical_gaps,
        "elevated_risks": context.elevated_risks,
        "high_confidence_lessons": context.high_confidence_lessons,
    }