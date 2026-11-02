"""Phase 4I.5 â€” Adaptive Planning / Replanning API.

Governance-first API for the adaptive planning layer that consumes 4I.4
Company Planning Context and produces attention signals, replanning proposals,
and decision contexts.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.intelligence.adaptive_planning_engine import adaptive_planning_engine
from app.intelligence.company_context import resolve_caller_access
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/adaptive-planning", tags=["Adaptive Planning"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class AdaptiveContextSynthesizeIn(BaseModel):
    scope: str = "company"
    scope_id: Optional[str] = None
    trigger: str = "planning_context_change"
    source_event_id: Optional[str] = None
    trigger_reason: Optional[str] = None


class AdaptiveContextRecomputeIn(BaseModel):
    trigger: str
    source_event_id: Optional[str] = None
    trigger_reason: Optional[str] = None
    scope: str = "company"
    scope_id: Optional[str] = None


class AdaptiveQuestionIn(BaseModel):
    question: str
    scope: str = "company"
    scope_id: Optional[str] = None


class AdaptiveContextResponse(BaseModel):
    id: str
    organization_id: str
    scope: str
    scope_id: Optional[str]
    planning_context_id: str
    planning_context_version: int
    planning_context_fingerprint: str
    version: int
    previous_version_id: Optional[str]
    overall_adaptive_health: str
    attention_count: int
    critical_attention_count: int
    pending_proposals_count: int
    pending_decisions_count: int
    computed_at: str
    computation_duration_ms: int
    trigger: str
    source_event_id: Optional[str]
    attention_signals: list[dict]
    replanning_proposals: list[dict]
    decision_contexts: list[dict]


class AttentionSignalResponse(BaseModel):
    id: str
    organization_id: str
    scope: str
    scope_id: Optional[str]
    planning_context_id: str
    adaptive_context_id: Optional[str]
    signal_type: str
    severity: str
    title: str
    description: str
    source_context_section: str
    source_conclusion_key: str
    source_conclusion_value: Any
    confidence: float
    epistemic_status: str
    affected_entities: list[dict]
    evidence_fingerprints: list[str]
    pattern_ids: list[str]
    lesson_fingerprints: list[str]
    contradiction_ids: list[str]
    intent_id: Optional[str]
    goal_id: Optional[str]
    objective_id: Optional[str]
    initiative_id: Optional[str]
    project_id: Optional[str]
    plan_id: Optional[str]
    status: str
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[str]
    resolved_by: Optional[str]
    resolved_at: Optional[str]
    resolution_note: Optional[str]
    source_event_id: Optional[str]
    generated_by: str
    created_at: str
    fingerprint: str


class ReplanningProposalResponse(BaseModel):
    id: str
    organization_id: str
    scope: str
    scope_id: Optional[str]
    planning_context_id: str
    adaptive_context_id: Optional[str]
    proposal_type: str
    title: str
    description: str
    trigger_attention_signal_ids: list[str]
    affected_intent_ids: list[str]
    affected_plan_ids: list[str]
    affected_objective_ids: list[str]
    affected_initiative_ids: list[str]
    proposed_changes: dict
    impact_assessment: dict
    lesson_fingerprints: list[str]
    pattern_ids: list[str]
    contradiction_ids: list[str]
    status: str
    proposed_by: Optional[str]
    proposed_at: str
    reviewed_by: Optional[str]
    reviewed_at: Optional[str]
    approved_by: Optional[str]
    approved_at: Optional[str]
    rejected_by: Optional[str]
    rejected_at: Optional[str]
    rejection_reason: Optional[str]
    executed_by: Optional[str]
    executed_at: Optional[str]
    source_event_id: Optional[str]
    fingerprint: str


class DecisionContextResponse(BaseModel):
    id: str
    organization_id: str
    scope: str
    scope_id: Optional[str]
    planning_context_id: str
    adaptive_context_id: Optional[str]
    replanning_proposal_id: Optional[str]
    attention_signal_ids: list[str]
    decision_type: str
    title: str
    description: str
    context: dict
    options: list[dict]
    recommendation: Optional[str]
    recommendation_confidence: float
    recommendation_reasoning: Optional[str]
    recommendation_provenance: list[dict]
    lesson_fingerprints: list[str]
    pattern_ids: list[str]
    contradiction_ids: list[str]
    precedent_decision_ids: list[str]
    status: str
    requires_approval: bool
    approver_person_id: Optional[str]
    approved_by: Optional[str]
    approved_at: Optional[str]
    approval_note: Optional[str]
    rejected_reason: Optional[str]
    company_decision_id: Optional[str]
    company_action_id: Optional[str]
    source_event_id: Optional[str]
    generated_by: str
    created_at: str
    fingerprint: str


class AdaptiveTransitionResponse(BaseModel):
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
    new_attention_signals: list[str]
    resolved_attention_signals: list[str]
    escalated_attention_signals: list[str]
    new_proposals: list[str]
    updated_proposals: list[str]
    new_decisions: list[str]
    updated_decisions: list[str]
    source_event_id: Optional[str]
    computed_by: str
    transitioned_at: str
    fingerprint: str


class AdaptiveQuestionResponse(BaseModel):
    question: str
    planning_context_version: int
    adaptive_context_version: int
    overall_adaptive_health: str
    attention_signals: list[dict]
    replanning_proposals: list[dict]
    decision_contexts: list[dict]
    attention_count: int
    critical_attention_count: int
    pending_proposals_count: int
    pending_decisions_count: int
    provenance_available: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/synthesize", response_model=AdaptiveContextResponse)
async def synthesize_adaptive_context(
    payload: AdaptiveContextSynthesizeIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
):
    """
    Synthesize the adaptive planning context from a planning context.
    
    This consumes the 4I.4 CompanyPlanningContext and produces:
    - Attention signals (what requires human/decision attention)
    - Replanning proposals (governance-reviewed adaptations)
    - Decision contexts (prepared decisions for governance)
    """
    # Governance: verify caller access to scope
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if payload.scope != "company" and payload.scope_id:
        if not access.org_wide:
            if payload.scope == "project" and payload.scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif payload.scope in ("department", "team") and payload.scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    adaptive_context = await adaptive_planning_engine.synthesize_adaptive_context(
        db,
        org.id,
        scope=payload.scope,
        scope_id=payload.scope_id,
        trigger=payload.trigger,
        source_event_id=payload.source_event_id,
        trigger_reason=payload.trigger_reason,
    )
    
    return AdaptiveContextResponse(
        id=adaptive_context.id,
        organization_id=adaptive_context.organization_id,
        scope=adaptive_context.scope,
        scope_id=adaptive_context.scope_id,
        planning_context_id=adaptive_context.planning_context_id,
        planning_context_version=adaptive_context.planning_context_version,
        planning_context_fingerprint=adaptive_context.planning_context_fingerprint,
        version=adaptive_context.version,
        previous_version_id=adaptive_context.previous_version_id,
        overall_adaptive_health=adaptive_context.overall_adaptive_health,
        attention_count=adaptive_context.attention_count,
        critical_attention_count=adaptive_context.critical_attention_count,
        pending_proposals_count=adaptive_context.pending_proposals_count,
        pending_decisions_count=adaptive_context.pending_decisions_count,
        computed_at=adaptive_context.computed_at.isoformat() if adaptive_context.computed_at else "",
        computation_duration_ms=adaptive_context.computation_duration_ms,
        trigger=adaptive_context.trigger,
        source_event_id=adaptive_context.source_event_id,
        attention_signals=adaptive_context.attention_signals or [],
        replanning_proposals=adaptive_context.replanning_proposals or [],
        decision_contexts=adaptive_context.decision_contexts or [],
    )


@router.post("/recompute", response_model=AdaptiveContextResponse)
async def trigger_recompute(
    payload: AdaptiveContextRecomputeIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
):
    """
    Trigger a recomputation of the adaptive planning context.
    """
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if payload.scope != "company" and payload.scope_id:
        if not access.org_wide:
            if payload.scope == "project" and payload.scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif payload.scope in ("department", "team") and payload.scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    adaptive_context = await adaptive_planning_engine.synthesize_adaptive_context(
        db,
        org.id,
        scope=payload.scope,
        scope_id=payload.scope_id,
        trigger=payload.trigger,
        source_event_id=payload.source_event_id,
        trigger_reason=payload.trigger_reason,
    )
    
    return AdaptiveContextResponse(
        id=adaptive_context.id,
        organization_id=adaptive_context.organization_id,
        scope=adaptive_context.scope,
        scope_id=adaptive_context.scope_id,
        planning_context_id=adaptive_context.planning_context_id,
        planning_context_version=adaptive_context.planning_context_version,
        planning_context_fingerprint=adaptive_context.planning_context_fingerprint,
        version=adaptive_context.version,
        previous_version_id=adaptive_context.previous_version_id,
        overall_adaptive_health=adaptive_context.overall_adaptive_health,
        attention_count=adaptive_context.attention_count,
        critical_attention_count=adaptive_context.critical_attention_count,
        pending_proposals_count=adaptive_context.pending_proposals_count,
        pending_decisions_count=adaptive_context.pending_decisions_count,
        computed_at=adaptive_context.computed_at.isoformat() if adaptive_context.computed_at else "",
        computation_duration_ms=adaptive_context.computation_duration_ms,
        trigger=adaptive_context.trigger,
        source_event_id=adaptive_context.source_event_id,
        attention_signals=adaptive_context.attention_signals or [],
        replanning_proposals=adaptive_context.replanning_proposals or [],
        decision_contexts=adaptive_context.decision_contexts or [],
    )


@router.get("/current", response_model=AdaptiveContextResponse)
async def get_current_adaptive_context(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    planning_context_id: Optional[str] = Query(None),
    version: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
):
    """Get the current (or specific version) adaptive planning context."""
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if scope != "company" and scope_id:
        if not access.org_wide:
            if scope == "project" and scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif scope in ("department", "team") and scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    adaptive_context = await adaptive_planning_engine.get_adaptive_context(
        db, org.id, scope=scope, scope_id=scope_id, 
        planning_context_id=planning_context_id, version=version
    )
    
    if not adaptive_context:
        raise HTTPException(404, "Adaptive planning context not found")
    
    return AdaptiveContextResponse(
        id=adaptive_context.id,
        organization_id=adaptive_context.organization_id,
        scope=adaptive_context.scope,
        scope_id=adaptive_context.scope_id,
        planning_context_id=adaptive_context.planning_context_id,
        planning_context_version=adaptive_context.planning_context_version,
        planning_context_fingerprint=adaptive_context.planning_context_fingerprint,
        version=adaptive_context.version,
        previous_version_id=adaptive_context.previous_version_id,
        overall_adaptive_health=adaptive_context.overall_adaptive_health,
        attention_count=adaptive_context.attention_count,
        critical_attention_count=adaptive_context.critical_attention_count,
        pending_proposals_count=adaptive_context.pending_proposals_count,
        pending_decisions_count=adaptive_context.pending_decisions_count,
        computed_at=adaptive_context.computed_at.isoformat() if adaptive_context.computed_at else "",
        computation_duration_ms=adaptive_context.computation_duration_ms,
        trigger=adaptive_context.trigger,
        source_event_id=adaptive_context.source_event_id,
        attention_signals=adaptive_context.attention_signals or [],
        replanning_proposals=adaptive_context.replanning_proposals or [],
        decision_contexts=adaptive_context.decision_contexts or [],
    )


@router.get("/attention-signals", response_model=list[AttentionSignalResponse])
async def get_attention_signals(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    signal_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
):
    """Get attention signals."""
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if scope != "company" and scope_id:
        if not access.org_wide:
            if scope == "project" and scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif scope in ("department", "team") and scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    signals = await adaptive_planning_engine.get_attention_signals(
        db, org.id, scope=scope, scope_id=scope_id,
        signal_type=signal_type, severity=severity, status=status, limit=limit
    )
    
    return [
        AttentionSignalResponse(
            id=s.id,
            organization_id=s.organization_id,
            scope=s.scope,
            scope_id=s.scope_id,
            planning_context_id=s.planning_context_id,
            adaptive_context_id=s.adaptive_context_id,
            signal_type=s.signal_type,
            severity=s.severity,
            title=s.title,
            description=s.description,
            source_context_section=s.source_context_section,
            source_conclusion_key=s.source_conclusion_key,
            source_conclusion_value=s.source_conclusion_value,
            confidence=s.confidence,
            epistemic_status=s.epistemic_status,
            affected_entities=s.affected_entities,
            evidence_fingerprints=s.evidence_fingerprints,
            pattern_ids=s.pattern_ids,
            lesson_fingerprints=s.lesson_fingerprints,
            contradiction_ids=s.contradiction_ids,
            intent_id=s.intent_id,
            goal_id=s.goal_id,
            objective_id=s.objective_id,
            initiative_id=s.initiative_id,
            project_id=s.project_id,
            plan_id=s.plan_id,
            status=s.status,
            acknowledged_by=s.acknowledged_by,
            acknowledged_at=s.acknowledged_at.isoformat() if s.acknowledged_at else None,
            resolved_by=s.resolved_by,
            resolved_at=s.resolved_at.isoformat() if s.resolved_at else None,
            resolution_note=s.resolution_note,
            source_event_id=s.source_event_id,
            generated_by=s.generated_by,
            created_at=s.created_at.isoformat() if s.created_at else "",
            fingerprint=s.fingerprint,
        )
        for s in signals
    ]


@router.get("/replanning-proposals", response_model=list[ReplanningProposalResponse])
async def get_replanning_proposals(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    proposal_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
):
    """Get replanning proposals."""
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if scope != "company" and scope_id:
        if not access.org_wide:
            if scope == "project" and scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif scope in ("department", "team") and scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    proposals = await adaptive_planning_engine.get_replanning_proposals(
        db, org.id, scope=scope, scope_id=scope_id,
        proposal_type=proposal_type, status=status, limit=limit
    )
    
    return [
        ReplanningProposalResponse(
            id=p.id,
            organization_id=p.organization_id,
            scope=p.scope,
            scope_id=p.scope_id,
            planning_context_id=p.planning_context_id,
            adaptive_context_id=p.adaptive_context_id,
            proposal_type=p.proposal_type,
            title=p.title,
            description=p.description,
            trigger_attention_signal_ids=p.trigger_attention_signal_ids,
            affected_intent_ids=p.affected_intent_ids,
            affected_plan_ids=p.affected_plan_ids,
            affected_objective_ids=p.affected_objective_ids,
            affected_initiative_ids=p.affected_initiative_ids,
            proposed_changes=p.proposed_changes,
            impact_assessment=p.impact_assessment,
            lesson_fingerprints=p.lesson_fingerprints,
            pattern_ids=p.pattern_ids,
            contradiction_ids=p.contradiction_ids,
            status=p.status,
            proposed_by=p.proposed_by,
            proposed_at=p.proposed_at.isoformat() if p.proposed_at else "",
            reviewed_by=p.reviewed_by,
            reviewed_at=p.reviewed_at.isoformat() if p.reviewed_at else None,
            approved_by=p.approved_by,
            approved_at=p.approved_at.isoformat() if p.approved_at else None,
            rejected_by=p.rejected_by,
            rejected_at=p.rejected_at.isoformat() if p.rejected_at else None,
            rejection_reason=p.rejection_reason,
            executed_by=p.executed_by,
            executed_at=p.executed_at.isoformat() if p.executed_at else None,
            source_event_id=p.source_event_id,
            fingerprint=p.fingerprint,
        )
        for p in proposals
    ]


@router.get("/decision-contexts", response_model=list[DecisionContextResponse])
async def get_decision_contexts(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    decision_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
):
    """Get decision contexts."""
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if scope != "company" and scope_id:
        if not access.org_wide:
            if scope == "project" and scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif scope in ("department", "team") and scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    decisions = await adaptive_planning_engine.get_decision_contexts(
        db, org.id, scope=scope, scope_id=scope_id,
        decision_type=decision_type, status=status, limit=limit
    )
    
    return [
        DecisionContextResponse(
            id=d.id,
            organization_id=d.organization_id,
            scope=d.scope,
            scope_id=d.scope_id,
            planning_context_id=d.planning_context_id,
            adaptive_context_id=d.adaptive_context_id,
            replanning_proposal_id=d.replanning_proposal_id,
            attention_signal_ids=d.attention_signal_ids,
            decision_type=d.decision_type,
            title=d.title,
            description=d.description,
            context=d.context,
            options=d.options,
            recommendation=d.recommendation,
            recommendation_confidence=d.recommendation_confidence,
            recommendation_reasoning=d.recommendation_reasoning,
            recommendation_provenance=d.recommendation_provenance,
            lesson_fingerprints=d.lesson_fingerprints,
            pattern_ids=d.pattern_ids,
            contradiction_ids=d.contradiction_ids,
            precedent_decision_ids=d.precedent_decision_ids,
            status=d.status,
            requires_approval=d.requires_approval,
            approver_person_id=d.approver_person_id,
            approved_by=d.approved_by,
            approved_at=d.approved_at.isoformat() if d.approved_at else None,
            approval_note=d.approval_note,
            rejected_reason=d.rejected_reason,
            company_decision_id=d.company_decision_id,
            company_action_id=d.company_action_id,
            source_event_id=d.source_event_id,
            generated_by=d.generated_by,
            created_at=d.created_at.isoformat() if d.created_at else "",
            fingerprint=d.fingerprint,
        )
        for d in decisions
    ]


@router.get("/transitions", response_model=list[AdaptiveTransitionResponse])
async def get_adaptive_transitions(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    from_version: Optional[int] = Query(None),
    to_version: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
):
    """Get adaptive planning transition history."""
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if scope != "company" and scope_id:
        if not access.org_wide:
            if scope == "project" and scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif scope in ("department", "team") and scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    transitions = await adaptive_planning_engine.get_adaptive_transitions(
        db, org.id, scope=scope, scope_id=scope_id,
        from_version=from_version, to_version=to_version, limit=limit
    )
    
    return [
        AdaptiveTransitionResponse(
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
            new_attention_signals=t.new_attention_signals,
            resolved_attention_signals=t.resolved_attention_signals,
            escalated_attention_signals=t.escalated_attention_signals,
            new_proposals=t.new_proposals,
            updated_proposals=t.updated_proposals,
            new_decisions=t.new_decisions,
            updated_decisions=t.updated_decisions,
            source_event_id=t.source_event_id,
            computed_by=t.computed_by,
            transitioned_at=t.transitioned_at.isoformat() if t.transitioned_at else "",
            fingerprint=t.fingerprint,
        )
        for t in transitions
    ]


@router.post("/ask", response_model=AdaptiveQuestionResponse)
async def ask_adaptive_question(
    payload: AdaptiveQuestionIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
):
    """
    Ask an adaptive planning question using the synthesized adaptive context.
    """
    access = await resolve_caller_access(db, organization_id=org.id, user=user)
    if payload.scope != "company" and payload.scope_id:
        if not access.org_wide:
            if payload.scope == "project" and payload.scope_id not in access.project_ids:
                raise HTTPException(403, "Not authorized for this project scope")
            elif payload.scope in ("department", "team") and payload.scope_id not in access.visible_scope_ids:
                raise HTTPException(403, "Not authorized for this scope")
    
    answer = await adaptive_planning_engine.answer_adaptive_question(
        db, org.id, payload.question, user=user, scope=payload.scope, scope_id=payload.scope_id
    )
    
    return AdaptiveQuestionResponse(**answer)


@router.get("/health", response_model=dict)
async def get_adaptive_health(
    scope: str = Query("company"),
    scope_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
):
    """Get a quick adaptive health summary."""
    planning_context = await adaptive_planning_engine.get_adaptive_context(
        db, org.id, scope=scope, scope_id=scope_id
    )
    
    if not planning_context:
        # Try to synthesize
        pc = await adaptive_planning_engine.company_planning_context_engine.get_planning_context(
            db, org.id, scope=scope, scope_id=scope_id
        )
        if not pc:
            pc = await adaptive_planning_engine.company_planning_context_engine.synthesize_planning_context(
                db, org.id, scope=scope, scope_id=scope_id
            )
        
        adaptive_context = await adaptive_planning_engine.synthesize_adaptive_context(
            db, org.id, scope=scope, scope_id=scope_id, planning_context=pc
        )
    else:
        adaptive_context = planning_context
    
    return {
        "overall_adaptive_health": adaptive_context.overall_adaptive_health,
        "version": adaptive_context.version,
        "computed_at": adaptive_context.computed_at.isoformat() if adaptive_context.computed_at else None,
        "attention_count": adaptive_context.attention_count,
        "critical_attention_count": adaptive_context.critical_attention_count,
        "pending_proposals_count": adaptive_context.pending_proposals_count,
        "pending_decisions_count": adaptive_context.pending_decisions_count,
    }