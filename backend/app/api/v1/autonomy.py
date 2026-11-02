"""Autonomy API — Governed Autonomous Company Operations (Gate 28)."""

from datetime import datetime
from typing import Any, Optional, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.autonomy import (
    AutonomyProposal,
    AutonomyPolicy,
    AutonomyPolicyEvaluation,
    AutonomyEligibility,
    AutonomyEligibilityCache,
    AutonomyEvent,
    AutonomyExecution,
    AutonomyLearning,
    AutonomyRisk,
    AutonomyContext,
    AUTONOMY_STATES,
    AUTONOMY_RISK_CLASSES,
    AUTONOMY_PROPOSAL_TYPES,
    POLICY_DECISIONS,
    AUTONOMY_EVENT_TYPES,
)
from app.services.autonomy_service import autonomy_service

router = APIRouter(prefix="/autonomy", tags=["Governed Autonomy"])


# =============================================================================
# Request/Response Models
# =============================================================================

class AutonomyProposalResponse(BaseModel):
    id: str
    organization_id: str
    proposal_type: str
    title: str
    description: Optional[str] = None
    state: str
    risk_class: str
    priority_score: float
    actor_id: Optional[str] = None
    actor_type: str
    scope_type: str
    scope_id: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    target_label: Optional[str] = None
    context_type: Optional[str] = None
    context_id: Optional[str] = None
    context_label: Optional[str] = None
    why: Optional[str] = None
    evidence_items: List[dict] = []
    evidence_confidence: float
    eligibility_result: Optional[str] = None
    policy_decision: Optional[str] = None
    approval_required: bool
    approval_state: Optional[str] = None
    commitment_id: Optional[str] = None
    execution_id: Optional[str] = None
    execution_state: Optional[str] = None
    outcome_id: Optional[str] = None
    outcome_state: Optional[str] = None
    verified: bool
    assessed: bool
    learned: bool
    created_at: datetime
    proposed_at: Optional[datetime] = None
    authorized_at: Optional[datetime] = None
    committed_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    assessed_at: Optional[datetime] = None
    learned_at: Optional[datetime] = None
    created_by: Optional[str] = None


class AutonomyProposalCreate(BaseModel):
    proposal_type: str = Field(..., pattern="^(execute_action|create_commitment|create_decision|create_task|create_project|allocate_resource|assign_responsibility|modify_policy|trigger_external_operation|recommend_decision|adjust_plan|rebalance_capacity|trigger_workflow)$")
    title: str = Field(..., min_length=1, max_length=240)
    description: Optional[str] = None
    actor_type: str = Field("human", pattern="^(human|system|autonomous|connector|agent)$")
    scope_type: str = Field("org", pattern="^(org|business_unit|region|department|team|project)$")
    scope_id: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    target_label: Optional[str] = None
    context_type: Optional[str] = None
    context_id: Optional[str] = None
    context_label: Optional[str] = None
    why: Optional[str] = None
    evidence_items: Optional[List[dict]] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    source_label: Optional[str] = None
    risk_class: Optional[str] = None
    evidence_items: Optional[List[dict]] = None


class AutonomyProposalAction(BaseModel):
    approval_note: Optional[str] = None


class AutonomyProposalOutcome(BaseModel):
    outcome_type: str
    outcome_state: str
    outcome_summary: str
    outcome_details: Optional[dict] = None
    epistemic_status: str = "observed"


class AutonomyVerification(BaseModel):
    verification_note: Optional[str] = None


class AutonomyAssessment(BaseModel):
    assessment: str
    success_score: Optional[float] = Field(None, ge=0, le=1)
    assessment_details: Optional[dict] = None


class AutonomyLearningRequest(BaseModel):
    lesson_type: str = Field(..., pattern="^(success_pattern|failure_pattern|policy_gap|optimization)$")
    lesson_title: str
    lesson_summary: Optional[str] = None
    lesson_details: Optional[dict] = None
    confidence: float = Field(0.5, ge=0, le=1)
    evidence_fingerprints: Optional[List[str]] = None
    applicable_proposal_types: Optional[List[str]] = None
    applicable_contexts: Optional[List[dict]] = None


class AutonomyRiskRequest(BaseModel):
    kind: str = Field(..., pattern="^(governance|financial|operational|security|compliance|reputational|external)$")
    level: str = Field(..., pattern="^(low|medium|high|critical)$")
    title: str
    description: Optional[str] = None
    probability: float = Field(0.5, ge=0, le=1)
    impact_score: float = Field(0.0, ge=0, le=100)
    financial_exposure_cents: Optional[int] = None


class AutonomyContextRequest(BaseModel):
    context_type: str = Field(..., pattern="^(company_state|project_state|team_state|capacity_state|financial_state|risk_state|policy_state)$")
    context_json: dict
    input_fingerprint: str


class AutonomyPolicyResponse(BaseModel):
    id: str
    organization_id: str
    policy_key: str
    name: str
    description: Optional[str] = None
    applies_to_types: List[str]
    risk_class: str
    required_approval_policy_id: Optional[str] = None
    required_entitlements: dict
    preconditions: List[dict]
    required_evidence_types: List[str]
    min_evidence_confidence: float
    max_financial_amount_cents: Optional[int] = None
    max_resource_allocation_pct: Optional[float] = None
    allowed_connectors: List[str]
    allowed_time_windows: List[dict]
    max_execution_duration_ms: Optional[int] = None
    require_human_approval: bool
    requires_privileged_approval: bool
    is_active: bool
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    version: int


class AutonomyPolicyCreate(BaseModel):
    policy_key: str = Field(..., pattern="^[a-z0-9_-]+$")
    name: str
    risk_class: str = Field(..., pattern="^(observe_only|propose_only|auto_execute_reversible|auto_execute_within_policy|human_approval_required|privileged_human_approval|prohibited)$")
    description: Optional[str] = None
    applies_to_types: Optional[List[str]] = None
    required_approval_policy_id: Optional[str] = None
    required_entitlements: Optional[dict] = None
    preconditions: Optional[List[dict]] = None
    required_evidence_types: Optional[List[str]] = None
    min_evidence_confidence: float = Field(0.7, ge=0, le=1)
    max_financial_amount_cents: Optional[int] = None
    max_resource_allocation_pct: Optional[float] = None
    allowed_connectors: Optional[List[str]] = None
    allowed_time_windows: Optional[List[dict]] = None
    max_execution_duration_ms: Optional[int] = None
    require_human_approval: bool = True
    requires_privileged_approval: bool = False
    is_active: bool = True


class AutonomyPolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    applies_to_types: Optional[List[str]] = None
    required_approval_policy_id: Optional[str] = None
    required_entitlements: Optional[dict] = None
    preconditions: Optional[List[dict]] = None
    required_evidence_types: Optional[List[str]] = None
    min_evidence_confidence: Optional[float] = Field(None, ge=0, le=1)
    max_financial_amount_cents: Optional[int] = None
    max_resource_allocation_pct: Optional[float] = None
    allowed_connectors: Optional[List[str]] = None
    allowed_time_windows: Optional[List[dict]] = None
    max_execution_duration_ms: Optional[int] = None
    require_human_approval: Optional[bool] = None
    requires_privileged_approval: Optional[bool] = None
    is_active: Optional[bool] = None


class AutonomyEligibilityResponse(BaseModel):
    id: str
    organization_id: str
    actor_id: str
    actor_type: str
    proposal_type: str
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None
    eligible: bool
    risk_class: str
    policy_decision: str
    reason: Optional[str] = None
    failed_checks: List[str]
    passed_checks: List[str]
    conditions: List[dict]
    evaluated_at: datetime
    valid_until: Optional[datetime] = None


class AutonomyEventResponse(BaseModel):
    id: str
    organization_id: str
    proposal_id: Optional[str] = None
    event_type: str
    actor_id: Optional[str] = None
    actor_type: str
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    outcome: str
    risk_score: int
    risk_factors: List[str]
    occurred_at: datetime


class AutonomyExecutionResponse(BaseModel):
    id: str
    organization_id: str
    proposal_id: str
    action_id: Optional[str] = None
    state: str
    attempt: int
    max_attempts: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    result: dict
    error: Optional[str] = None


class AutonomyLearningResponse(BaseModel):
    id: str
    organization_id: str
    proposal_id: str
    lesson_type: str
    lesson_title: str
    lesson_summary: Optional[str] = None
    confidence: float
    validated: bool


class AutonomyRiskResponse(BaseModel):
    id: str
    organization_id: str
    proposal_id: Optional[str] = None
    kind: str
    level: str
    title: str
    description: Optional[str] = None
    probability: float
    impact_score: float
    state: str


class AutonomyContextResponse(BaseModel):
    id: str
    organization_id: str
    proposal_id: str
    context_type: str
    context_json: dict
    computed_at: datetime


# =============================================================================
# Policies
# =============================================================================

@router.get("/policies", response_model=List[AutonomyPolicyResponse])
async def list_policies(
    risk_class: Optional[str] = Query(None, pattern="^(observe_only|propose_only|auto_execute_reversible|auto_execute_within_policy|human_approval_required|privileged_human_approval|prohibited)$"),
    is_active: Optional[bool] = None,
    user: User = Depends(require_permission("autonomy:policy:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List autonomy policies for the organization."""
    policies = await autonomy_service.list_policies(db, org.id, is_active=is_active, risk_class=risk_class)
    
    return [
        AutonomyPolicyResponse(
            id=p.id,
            organization_id=p.organization_id,
            policy_key=p.policy_key,
            name=p.name,
            description=p.description,
            applies_to_types=p.applies_to_types or [],
            risk_class=p.risk_class,
            required_approval_policy_id=p.required_approval_policy_id,
            required_entitlements=p.required_entitlements or {},
            preconditions=p.preconditions or [],
            required_evidence_types=p.required_evidence_types or [],
            min_evidence_confidence=p.min_evidence_confidence,
            max_financial_amount_cents=p.max_financial_amount_cents,
            max_resource_allocation_pct=p.max_resource_allocation_pct,
            allowed_connectors=p.allowed_connectors or [],
            allowed_time_windows=p.allowed_time_windows or [],
            max_execution_duration_ms=p.max_execution_duration_ms,
            require_human_approval=p.requires_human_approval,
            requires_privileged_approval=p.requires_privileged_approval,
            is_active=p.is_active,
            approved_by=p.approved_by,
            approved_at=p.approved_at,
            version=p.version,
        )
        for p in policies
    ]


@router.post("/policies", response_model=AutonomyPolicyResponse, status_code=201)
async def create_policy(
    request: AutonomyPolicyCreate,
    user: User = Depends(require_permission("autonomy:policy:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a new autonomy policy."""
    policy = await autonomy_service.create_policy(
        db,
        organization_id=org.id,
        policy_key=request.policy_key,
        name=request.name,
        tier=request.risk_class,
        description=request.description,
        entitlements=request.required_entitlements,
        features={},
        limits={},
        intervals=["monthly", "annual"],
        trial_days=14,
        is_public=True,
        sort_order=0,
        created_by=user.id,
    )
    await db.commit()
    
    # Convert to response format
    policy = await autonomy_service.get_policy(db, policy.id)
    return AutonomyPolicyResponse(
        id=policy.id,
        organization_id=policy.organization_id,
        policy_key=policy.policy_key,
        name=policy.name,
        description=policy.description,
        applies_to_types=policy.applies_to_types or [],
        risk_class=policy.risk_class,
        required_approval_policy_id=policy.required_approval_policy_id,
        required_entitlements=policy.required_entitlements or {},
        preconditions=policy.preconditions or [],
        required_evidence_types=policy.required_evidence_types or [],
        min_evidence_confidence=policy.min_evidence_confidence,
        max_financial_amount_cents=policy.max_financial_amount_cents,
        max_resource_allocation_pct=policy.max_resource_allocation_pct,
        allowed_connectors=policy.allowed_connectors or [],
        allowed_time_windows=policy.allowed_time_windows or [],
        max_execution_duration_ms=policy.max_execution_duration_ms,
        require_human_approval=policy.requires_human_approval,
        requires_privileged_approval=policy.requires_privileged_approval,
        is_active=policy.is_active,
        approved_by=policy.approved_by,
        approved_at=policy.approved_at,
        version=policy.version,
    )


@router.get("/policies/{policy_id}", response_model=AutonomyPolicyResponse)
async def get_policy(
    policy_id: str,
    user: User = Depends(require_permission("autonomy:policy:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get a policy by ID."""
    policy = await autonomy_service.get_policy(db, policy_id)
    if not policy or policy.organization_id != org.id:
        raise HTTPException(404, "Policy not found")
    
    return AutonomyPolicyResponse(
        id=policy.id,
        organization_id=policy.organization_id,
        policy_key=policy.policy_key,
        name=policy.name,
        description=policy.description,
        applies_to_types=policy.applies_to_types or [],
        risk_class=policy.risk_class,
        required_approval_policy_id=policy.required_approval_policy_id,
        required_entitlements=policy.required_entitlements or {},
        preconditions=policy.preconditions or [],
        required_evidence_types=policy.required_evidence_types or [],
        min_evidence_confidence=policy.min_evidence_confidence,
        max_financial_amount_cents=policy.max_financial_amount_cents,
        max_resource_allocation_pct=policy.max_resource_allocation_pct,
        allowed_connectors=policy.allowed_connectors or [],
        allowed_time_windows=policy.allowed_time_windows or [],
        max_execution_duration_ms=policy.max_execution_duration_ms,
        require_human_approval=policy.requires_human_approval,
        requires_privileged_approval=policy.requires_privileged_approval,
        is_active=policy.is_active,
        approved_by=policy.approved_by,
        approved_at=policy.approved_at,
        version=policy.version,
    )


@router.patch("/policies/{policy_id}", response_model=AutonomyPolicyResponse)
async def update_policy(
    policy_id: str,
    request: AutonomyPolicyUpdate,
    user: User = Depends(require_permission("autonomy:policy:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update an autonomy policy."""
    update_data = request.model_dump(exclude_unset=True)
    policy = await autonomy_service.update_policy(db, policy_id, **update_data)
    await db.commit()
    
    if not policy:
        raise HTTPException(404, "Policy not found")
    
    return AutonomyPolicyResponse(
        id=policy.id,
        organization_id=policy.organization_id,
        policy_key=policy.policy_key,
        name=policy.name,
        description=policy.description,
        applies_to_types=policy.applies_to_types or [],
        risk_class=policy.risk_class,
        required_approval_policy_id=policy.required_approval_policy_id,
        required_entitlements=policy.required_entitlements or {},
        preconditions=policy.preconditions or [],
        required_evidence_types=policy.required_evidence_types or [],
        min_evidence_confidence=policy.min_evidence_confidence,
        max_financial_amount_cents=policy.max_financial_amount_cents,
        max_resource_allocation_pct=policy.max_resource_allocation_pct,
        allowed_connectors=policy.allowed_connectors or [],
        allowed_time_windows=policy.allowed_time_windows or [],
        max_execution_duration_ms=policy.max_execution_duration_ms,
        require_human_approval=policy.requires_human_approval,
        requires_privileged_approval=policy.requires_privileged_approval,
        is_active=policy.is_active,
        approved_by=policy.approved_by,
        approved_at=policy.approved_at,
        version=policy.version,
    )


# =============================================================================
# Proposals
# =============================================================================

@router.post("/proposals", response_model=AutonomyProposalResponse, status_code=201)
async def create_proposal(
    request: AutonomyProposalCreate,
    user: User = Depends(require_permission("autonomy:propose")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a new autonomous operation proposal."""
    proposal = await autonomy_service.create_proposal(
        db,
        organization_id=org.id,
        proposal_type=request.proposal_type,
        title=request.title,
        description=request.description,
        actor_id=user.id,
        actor_type=request.actor_type,
        scope_type=request.scope_type,
        scope_id=request.scope_id,
        target_type=request.target_type,
        target_id=request.target_id,
        target_label=request.target_label,
        context_type=request.context_type,
        context_id=request.context_id,
        context_label=request.context_label,
        why=request.why,
        evidence_items=request.evidence_items,
        source_type=request.source_type,
        source_id=request.source_id,
        source_label=request.source_label,
        risk_class=request.risk_class,
        created_by=user.id,
    )
    await db.commit()
    
    proposal = await autonomy_service.get_proposal(db, proposal.id)
    return AutonomyProposalResponse(
        id=proposal.id,
        organization_id=proposal.organization_id,
        proposal_type=proposal.proposal_type,
        title=proposal.title,
        description=proposal.description,
        state=proposal.state,
        risk_class=proposal.risk_class,
        priority_score=proposal.priority_score,
        actor_id=proposal.actor_id,
        actor_type=proposal.actor_type,
        scope_type=proposal.scope_type,
        scope_id=proposal.scope_id,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        target_label=proposal.target_label,
        context_type=proposal.context_type,
        context_id=proposal.context_id,
        context_label=proposal.context_label,
        why=proposal.why,
        evidence_items=proposal.evidence_items or [],
        evidence_confidence=proposal.evidence_confidence,
        eligibility_result=proposal.eligibility_result,
        policy_decision=proposal.policy_decision,
        approval_required=proposal.approval_required,
        approval_state=proposal.approval_state,
        commitment_id=proposal.commitment_id,
        execution_id=proposal.execution_id,
        execution_state=proposal.execution_state,
        outcome_id=proposal.outcome_id,
        outcome_state=proposal.outcome_state,
        verified=proposal.verified,
        assessed=proposal.assessed,
        learned=proposal.learned,
        created_at=proposal.created_at,
        proposed_at=proposal.proposed_at,
        authorized_at=proposal.authorized_at,
        committed_at=proposal.committed_at,
        executed_at=proposal.executed_at,
        verified_at=proposal.verified_at,
        assessed_at=proposal.assessed_at,
        learned_at=proposal.learned_at,
        created_by=proposal.created_by,
    )


@router.get("/proposals", response_model=List[AutonomyProposalResponse])
async def list_proposals(
    state: Optional[str] = Query(None, pattern="^(discovered|eligibility_evaluated|proposed|evidence_validated|governance_evaluated|authorization_required|authorized|committed|executing|executed|outcome_observed|verified|assessed|learned|rejected|cancelled|failed|blocked|superseded)$"),
    proposal_type: Optional[str] = Query(None),
    actor_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("autonomy:proposal:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List autonomy proposals."""
    proposals = await autonomy_service.list_proposals(db, org.id, state=state, proposal_type=proposal_type, actor_id=actor_id, limit=limit, offset=offset)
    
    return [
        AutonomyProposalResponse(
            id=p.id,
            organization_id=p.organization_id,
            proposal_type=p.proposal_type,
            title=p.title,
            description=p.description,
            state=p.state,
            risk_class=p.risk_class,
            priority_score=p.priority_score,
            actor_id=p.actor_id,
            actor_type=p.actor_type,
            scope_type=p.scope_type,
            scope_id=p.scope_id,
            target_type=p.target_type,
            target_id=p.target_id,
            target_label=p.target_label,
            context_type=p.context_type,
            context_id=p.context_id,
            context_label=p.context_label,
            why=p.why,
            evidence_items=p.evidence_items or [],
            evidence_confidence=p.evidence_confidence,
            eligibility_result=p.eligibility_result,
            policy_decision=p.policy_decision,
            approval_required=p.approval_required,
            approval_state=p.approval_state,
            commitment_id=p.commitment_id,
            execution_id=p.execution_id,
            execution_state=p.execution_state,
            outcome_id=p.outcome_id,
            outcome_state=p.outcome_state,
            verified=p.verified,
            assessed=p.assessed,
            learned=p.learned,
            created_at=p.created_at,
            proposed_at=p.proposed_at,
            authorized_at=p.authorized_at,
            committed_at=p.committed_at,
            executed_at=p.executed_at,
            verified_at=p.verified_at,
            assessed_at=p.assessed_at,
            learned_at=p.learned_at,
            created_by=p.created_by,
        )
        for p in proposals
    ]


@router.get("/proposals/{proposal_id}", response_model=AutonomyProposalResponse)
async def get_proposal(
    proposal_id: str,
    user: User = Depends(require_permission("autonomy:proposal:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get a proposal by ID."""
    proposal = await autonomy_service.get_proposal(db, proposal_id)
    if not proposal or proposal.organization_id != org.id:
        raise HTTPException(404, "Proposal not found")
    
    return AutonomyProposalResponse(
        id=proposal.id,
        organization_id=proposal.organization_id,
        proposal_type=proposal.proposal_type,
        title=proposal.title,
        description=proposal.description,
        state=proposal.state,
        risk_class=proposal.risk_class,
        priority_score=proposal.priority_score,
        actor_id=proposal.actor_id,
        actor_type=proposal.actor_type,
        scope_type=proposal.scope_type,
        scope_id=proposal.scope_id,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        target_label=proposal.target_label,
        context_type=proposal.context_type,
        context_id=proposal.context_id,
        context_label=proposal.context_label,
        why=proposal.why,
        evidence_items=proposal.evidence_items or [],
        evidence_confidence=proposal.evidence_confidence,
        eligibility_result=proposal.eligibility_result,
        policy_decision=proposal.policy_decision,
        approval_required=proposal.approval_required,
        approval_state=proposal.approval_state,
        commitment_id=proposal.commitment_id,
        execution_id=proposal.execution_id,
        execution_state=proposal.execution_state,
        outcome_id=proposal.outcome_id,
        outcome_state=proposal.outcome_state,
        verified=proposal.verified,
        assessed=proposal.assessed,
        learned=proposal.learned,
        created_at=proposal.created_at,
        proposed_at=proposal.proposed_at,
        authorized_at=proposal.authorized_at,
        committed_at=proposal.committed_at,
        executed_at=proposal.executed_at,
        verified_at=proposal.verified_at,
        assessed_at=proposal.assessed_at,
        learned_at=proposal.learned_at,
        created_by=proposal.created_by,
    )


@router.post("/proposals/{proposal_id}/evidence", response_model=dict)
async def add_evidence(
    proposal_id: str,
    evidence: dict = Body(...),
    user: User = Depends(require_permission("autonomy:proposal:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Add evidence to a proposal."""
    proposal = await autonomy_service.get_proposal(db, proposal_id)
    if not proposal or proposal.organization_id != org.id:
        raise HTTPException(404, "Proposal not found")
    
    # Add evidence item
    evidence_item = {
        "type": evidence.get("type", "document"),
        "source": evidence.get("source", "user"),
        "content": evidence.get("content", ""),
        "confidence": evidence.get("confidence", 0.5),
        "metadata": evidence.get("metadata", {}),
        "added_by": user.id,
        "added_at": utcnow().isoformat(),
    }
    
    if not proposal.evidence_items:
        proposal.evidence_items = []
    proposal.evidence_items.append(evidence_item)
    
    # Re-validate evidence
    total_confidence = sum(e.get("confidence", 0.5) for e in proposal.evidence_items)
    avg_confidence = total_confidence / len(proposal.evidence_items)
    proposal.evidence_confidence = avg_confidence
    
    if avg_confidence >= 0.7 and proposal.state == "proposed":
        proposal.evidence_validated = True
        proposal.evidence_validated_at = utcnow()
        proposal.evidence_validated_by = "system"
        proposal.state = "evidence_validated"
    
    await db.commit()
    return {"success": True, "evidence_confidence": proposal.evidence_confidence, "state": proposal.state}


@router.post("/proposals/{proposal_id}/evaluate-governance", response_model=dict)
async def evaluate_governance(
    proposal_id: str,
    user: User = Depends(require_permission("autonomy:proposal:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate governance policies for a proposal."""
    proposal = await autonomy_service.get_proposal(db, proposal_id)
    if not proposal or proposal.organization_id != org.id:
        raise HTTPException(404, "Proposal not found")
    
    await autonomy_service.evaluate_governance(db, proposal)
    await db.commit()
    
    return {"success": True, "state": proposal.state, "policy_decision": proposal.policy_decision}


@router.post("/proposals/{proposal_id}/authorize", response_model=AutonomyProposalResponse)
async def authorize_proposal(
    proposal_id: str,
    request: AutonomyProposalAction,
    user: User = Depends(require_permission("autonomy:approve")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Authorize a proposal (human approval)."""
    proposal = await autonomy_service.authorize_proposal(db, proposal_id, user.id, request.approval_note)
    await db.commit()
    
    proposal = await autonomy_service.get_proposal(db, proposal_id)
    return AutonomyProposalResponse(
        id=proposal.id,
        organization_id=proposal.organization_id,
        proposal_type=proposal.proposal_type,
        title=proposal.title,
        description=proposal.description,
        state=proposal.state,
        risk_class=proposal.risk_class,
        priority_score=proposal.priority_score,
        actor_id=proposal.actor_id,
        actor_type=proposal.actor_type,
        scope_type=proposal.scope_type,
        scope_id=proposal.scope_id,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        target_label=proposal.target_label,
        context_type=proposal.context_type,
        context_id=proposal.context_id,
        context_label=proposal.context_label,
        why=proposal.why,
        evidence_items=proposal.evidence_items or [],
        evidence_confidence=proposal.evidence_confidence,
        eligibility_result=proposal.eligibility_result,
        policy_decision=proposal.policy_decision,
        approval_required=proposal.approval_required,
        approval_state=proposal.approval_state,
        commitment_id=proposal.commitment_id,
        execution_id=proposal.execution_id,
        execution_state=proposal.execution_state,
        outcome_id=proposal.outcome_id,
        outcome_state=proposal.outcome_state,
        verified=proposal.verified,
        assessed=proposal.assessed,
        learned=proposal.learned,
        created_at=proposal.created_at,
        proposed_at=proposal.proposed_at,
        authorized_at=proposal.authorized_at,
        committed_at=proposal.committed_at,
        executed_at=proposal.executed_at,
        verified_at=proposal.verified_at,
        assessed_at=proposal.assessed_at,
        learned_at=proposal.learned_at,
        created_by=proposal.created_by,
    )


@router.post("/proposals/{proposal_id}/commit", response_model=AutonomyProposalResponse)
async def commit_proposal(
    proposal_id: str,
    user: User = Depends(require_permission("autonomy:proposal:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Commit an authorized proposal (create commitment)."""
    proposal = await autonomy_service.commit_proposal(db, proposal_id, user.id)
    await db.commit()
    
    proposal = await autonomy_service.get_proposal(db, proposal_id)
    return AutonomyProposalResponse(
        id=proposal.id,
        organization_id=proposal.organization_id,
        proposal_type=proposal.proposal_type,
        title=proposal.title,
        description=proposal.description,
        state=proposal.state,
        risk_class=proposal.risk_class,
        priority_score=proposal.priority_score,
        actor_id=proposal.actor_id,
        actor_type=proposal.actor_type,
        scope_type=proposal.scope_type,
        scope_id=proposal.scope_id,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        target_label=proposal.target_label,
        context_type=proposal.context_type,
        context_id=proposal.context_id,
        context_label=proposal.context_label,
        why=proposal.why,
        evidence_items=proposal.evidence_items or [],
        evidence_confidence=proposal.evidence_confidence,
        eligibility_result=proposal.eligibility_result,
        policy_decision=proposal.policy_decision,
        approval_required=proposal.approval_required,
        approval_state=proposal.approval_state,
        commitment_id=proposal.commitment_id,
        execution_id=proposal.execution_id,
        execution_state=proposal.execution_state,
        outcome_id=proposal.outcome_id,
        outcome_state=proposal.outcome_state,
        verified=proposal.verified,
        assessed=proposal.assessed,
        learned=proposal.learned,
        created_at=proposal.created_at,
        proposed_at=proposal.proposed_at,
        authorized_at=proposal.authorized_at,
        committed_at=proposal.committed_at,
        executed_at=proposal.executed_at,
        verified_at=proposal.verified_at,
        assessed_at=proposal.assessed_at,
        learned_at=proposal.learned_at,
        created_by=proposal.created_by,
    )


@router.post("/proposals/{proposal_id}/execute", response_model=AutonomyProposalResponse)
async def execute_proposal(
    proposal_id: str,
    user: User = Depends(require_permission("autonomy:execute")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Execute an autonomous proposal."""
    proposal = await autonomy_service.execute_proposal(db, proposal_id, user.id)
    await db.commit()
    
    proposal = await autonomy_service.get_proposal(db, proposal_id)
    return AutonomyProposalResponse(
        id=proposal.id,
        organization_id=proposal.organization_id,
        proposal_type=proposal.proposal_type,
        title=proposal.title,
        description=proposal.description,
        state=proposal.state,
        risk_class=proposal.risk_class,
        priority_score=proposal.priority_score,
        actor_id=proposal.actor_id,
        actor_type=proposal.actor_type,
        scope_type=proposal.scope_type,
        scope_id=proposal.scope_id,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        target_label=proposal.target_label,
        context_type=proposal.context_type,
        context_id=proposal.context_id,
        context_label=proposal.context_label,
        why=proposal.why,
        evidence_items=proposal.evidence_items or [],
        evidence_confidence=proposal.evidence_confidence,
        eligibility_result=proposal.eligibility_result,
        policy_decision=proposal.policy_decision,
        approval_required=proposal.approval_required,
        approval_state=proposal.approval_state,
        commitment_id=proposal.commitment_id,
        execution_id=proposal.execution_id,
        execution_state=proposal.execution_state,
        outcome_id=proposal.outcome_id,
        outcome_state=proposal.outcome_state,
        verified=proposal.verified,
        assessed=proposal.assessed,
        learned=proposal.learned,
        created_at=proposal.created_at,
        proposed_at=proposal.proposed_at,
        authorized_at=proposal.authorized_at,
        committed_at=proposal.committed_at,
        executed_at=proposal.executed_at,
        verified_at=proposal.verified_at,
        assessed_at=proposal.assessed_at,
        learned_at=proposal.learned_at,
        created_by=proposal.created_by,
    )


@router.post("/proposals/{proposal_id}/outcome", response_model=AutonomyProposalResponse)
async def record_outcome(
    proposal_id: str,
    request: AutonomyProposalOutcome,
    user: User = Depends(require_permission("autonomy:outcome:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Record outcome of autonomous operation."""
    proposal = await autonomy_service.record_outcome(
        db, proposal_id, request.outcome_type, request.outcome_state,
        request.outcome_summary, request.outcome_details, user.id, request.epistemic_status
    )
    await db.commit()
    
    proposal = await autonomy_service.get_proposal(db, proposal_id)
    return AutonomyProposalResponse(
        id=proposal.id,
        organization_id=proposal.organization_id,
        proposal_type=proposal.proposal_type,
        title=proposal.title,
        description=proposal.description,
        state=proposal.state,
        risk_class=proposal.risk_class,
        priority_score=proposal.priority_score,
        actor_id=proposal.actor_id,
        actor_type=proposal.actor_type,
        scope_type=proposal.scope_type,
        scope_id=proposal.scope_id,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        target_label=proposal.target_label,
        context_type=proposal.context_type,
        context_id=proposal.context_id,
        context_label=proposal.context_label,
        why=proposal.why,
        evidence_items=proposal.evidence_items or [],
        evidence_confidence=proposal.evidence_confidence,
        eligibility_result=proposal.eligibility_result,
        policy_decision=proposal.policy_decision,
        approval_required=proposal.approval_required,
        approval_state=proposal.approval_state,
        commitment_id=proposal.commitment_id,
        execution_id=proposal.execution_id,
        execution_state=proposal.execution_state,
        outcome_id=proposal.outcome_id,
        outcome_state=proposal.outcome_state,
        verified=proposal.verified,
        assessed=proposal.assessed,
        learned=proposal.learned,
        created_at=proposal.created_at,
        proposed_at=proposal.proposed_at,
        authorized_at=proposal.authorized_at,
        committed_at=proposal.committed_at,
        executed_at=proposal.executed_at,
        verified_at=proposal.verified_at,
        assessed_at=proposal.assessed_at,
        learned_at=proposal.learned_at,
        created_by=proposal.created_by,
    )


@router.post("/proposals/{proposal_id}/verify", response_model=AutonomyProposalResponse)
async def verify_outcome(
    proposal_id: str,
    request: AutonomyVerification,
    user: User = Depends(require_permission("autonomy:outcome:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Verify outcome of autonomous operation."""
    proposal = await autonomy_service.verify_outcome(db, proposal_id, user.id, request.verification_note)
    await db.commit()
    
    proposal = await autonomy_service.get_proposal(db, proposal_id)
    return AutonomyProposalResponse(
        id=proposal.id,
        organization_id=proposal.organization_id,
        proposal_type=proposal.proposal_type,
        title=proposal.title,
        description=proposal.description,
        state=proposal.state,
        risk_class=proposal.risk_class,
        priority_score=proposal.priority_score,
        actor_id=proposal.actor_id,
        actor_type=proposal.actor_type,
        scope_type=proposal.scope_type,
        scope_id=proposal.scope_id,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        target_label=proposal.target_label,
        context_type=proposal.context_type,
        context_id=proposal.context_id,
        context_label=proposal.context_label,
        why=proposal.why,
        evidence_items=proposal.evidence_items or [],
        evidence_confidence=proposal.evidence_confidence,
        eligibility_result=proposal.eligibility_result,
        policy_decision=proposal.policy_decision,
        approval_required=proposal.approval_required,
        approval_state=proposal.approval_state,
        commitment_id=proposal.commitment_id,
        execution_id=proposal.execution_id,
        execution_state=proposal.execution_state,
        outcome_id=proposal.outcome_id,
        outcome_state=proposal.outcome_state,
        verified=proposal.verified,
        assessed=proposal.assessed,
        learned=proposal.learned,
        created_at=proposal.created_at,
        proposed_at=proposal.proposed_at,
        authorized_at=proposal.authorized_at,
        committed_at=proposal.committed_at,
        executed_at=proposal.executed_at,
        verified_at=proposal.verified_at,
        assessed_at=proposal.assessed_at,
        learned_at=proposal.learned_at,
        created_by=proposal.created_by,
    )


@router.post("/proposals/{proposal_id}/assess", response_model=AutonomyProposalResponse)
async def assess_outcome(
    proposal_id: str,
    request: AutonomyAssessment,
    user: User = Depends(require_permission("autonomy:outcome:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Assess autonomous operation outcome."""
    proposal = await autonomy_service.assess_outcome(
        db, proposal_id, user.id, request.assessment, request.success_score, request.assessment_details
    )
    await db.commit()
    
    proposal = await autonomy_service.get_proposal(db, proposal_id)
    return AutonomyProposalResponse(
        id=proposal.id,
        organization_id=proposal.organization_id,
        proposal_type=proposal.proposal_type,
        title=proposal.title,
        description=proposal.description,
        state=proposal.state,
        risk_class=proposal.risk_class,
        priority_score=proposal.priority_score,
        actor_id=proposal.actor_id,
        actor_type=proposal.actor_type,
        scope_type=proposal.scope_type,
        scope_id=proposal.scope_id,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        target_label=proposal.target_label,
        context_type=proposal.context_type,
        context_id=proposal.context_id,
        context_label=proposal.context_label,
        why=proposal.why,
        evidence_items=proposal.evidence_items or [],
        evidence_confidence=proposal.evidence_confidence,
        eligibility_result=proposal.eligibility_result,
        policy_decision=proposal.policy_decision,
        approval_required=proposal.approval_required,
        approval_state=proposal.approval_state,
        commitment_id=proposal.commitment_id,
        execution_id=proposal.execution_id,
        execution_state=proposal.execution_state,
        outcome_id=proposal.outcome_id,
        outcome_state=proposal.outcome_state,
        verified=proposal.verified,
        assessed=proposal.assessed,
        learned=proposal.learned,
        created_at=proposal.created_at,
        proposed_at=proposal.proposed_at,
        authorized_at=proposal.authorized_at,
        committed_at=proposal.committed_at,
        executed_at=proposal.executed_at,
        verified_at=proposal.verified_at,
        assessed_at=proposal.assessed_at,
        learned_at=proposal.learned_at,
        created_by=proposal.created_by,
    )


@router.post("/proposals/{proposal_id}/learn", response_model=AutonomyLearningResponse)
async def record_learning(
    proposal_id: str,
    request: AutonomyLearningRequest,
    user: User = Depends(require_permission("autonomy:learning:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Record learning from autonomous operation."""
    learning = await autonomy_service.record_learning(
        db, proposal_id, request.lesson_type, request.lesson_title,
        request.lesson_summary, request.lesson_details, request.confidence,
        request.evidence_fingerprints, request.applicable_proposal_types,
        request.applicable_contexts
    )
    await db.commit()
    
    return AutonomyLearningResponse(
        id=learning.id,
        organization_id=learning.organization_id,
        proposal_id=learning.proposal_id,
        lesson_type=learning.lesson_type,
        lesson_title=learning.lesson_title,
        lesson_summary=learning.lesson_summary,
        confidence=learning.confidence,
        validated=learning.validated,
    )


# =============================================================================
# Risk Assessment
# =============================================================================

@router.post("/proposals/{proposal_id}/risk", response_model=AutonomyRiskResponse)
async def create_risk(
    proposal_id: str,
    request: AutonomyRiskRequest,
    user: User = Depends(require_permission("autonomy:risk:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create risk assessment for proposal."""
    risk = await autonomy_service.create_risk_assessment(
        db, proposal_id, request.kind, request.level, request.title,
        request.description, request.probability, request.impact_score,
        request.financial_exposure_cents
    )
    await db.commit()
    
    return AutonomyRiskResponse(
        id=risk.id,
        organization_id=risk.organization_id,
        proposal_id=risk.proposal_id,
        kind=risk.kind,
        level=risk.level,
        title=risk.title,
        description=risk.description,
        probability=risk.probability,
        impact_score=risk.impact_score,
        state=risk.state,
    )


@router.post("/proposals/{proposal_id}/context", response_model=AutonomyContextResponse)
async def create_context(
    proposal_id: str,
    request: AutonomyContextRequest,
    user: User = Depends(require_permission("autonomy:context:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create governed context for proposal."""
    context = await autonomy_service.create_context(db, proposal_id, request.context_type, request.context_json, request.input_fingerprint)
    await db.commit()
    
    return AutonomyContextResponse(
        id=context.id,
        organization_id=context.organization_id,
        proposal_id=context.proposal_id,
        context_type=context.context_type,
        context_json=context.context_json,
        computed_at=context.computed_at,
    )


# =============================================================================
# Eligibility
# =============================================================================

@router.get("/eligibility", response_model=AutonomyEligibilityResponse)
async def check_eligibility(
    proposal_type: str = Query(..., pattern="^(execute_action|create_commitment|create_decision|create_task|create_project|allocate_resource|assign_responsibility|modify_policy|trigger_external_operation|recommend_decision|adjust_plan|rebalance_capacity|trigger_workflow)$"),
    scope_type: Optional[str] = Query(None, pattern="^(org|business_unit|region|department|team|project)$"),
    scope_id: Optional[str] = None,
    user: User = Depends(require_permission("autonomy:eligibility:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Check autonomy eligibility for current user."""
    eligibility = await autonomy_service.evaluate_eligibility(
        db, organization_id=org.id, actor_id=user.id, actor_type="human",
        proposal_type=proposal_type, scope_type=scope_type, scope_id=scope_id
    )
    
    return AutonomyEligibilityResponse(
        id=eligibility.id,
        organization_id=eligibility.organization_id,
        actor_id=eligibility.actor_id,
        actor_type=eligibility.actor_type,
        proposal_type=eligibility.proposal_type,
        scope_type=eligibility.scope_type,
        scope_id=eligibility.scope_id,
        eligible=eligibility.eligible,
        risk_class=eligibility.risk_class,
        policy_decision=eligibility.policy_decision,
        reason=eligibility.reason,
        failed_checks=eligibility.failed_checks,
        passed_checks=eligibility.passed_checks,
        conditions=eligibility.conditions,
        evaluated_at=eligibility.evaluated_at,
        valid_until=eligibility.valid_until,
    )


@router.post("/eligibility/cache/invalidate", response_model=dict)
async def invalidate_eligibility_cache(
    actor_id: Optional[str] = Body(None),
    proposal_type: Optional[str] = Body(None),
    user: User = Depends(require_permission("autonomy:eligibility:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Invalidate eligibility cache."""
    count = await autonomy_service.invalidate_eligibility_cache(db, org.id, actor_id, proposal_type)
    await db.commit()
    return {"invalidated": count}


# =============================================================================
# Events
# =============================================================================

@router.get("/events", response_model=List[AutonomyEventResponse])
async def list_events(
    proposal_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("autonomy:events:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List autonomy events."""
    query = select(AutonomyEvent).where(AutonomyEvent.organization_id == org.id)
    if proposal_id:
        query = query.where(AutonomyEvent.proposal_id == proposal_id)
    if event_type:
        query = query.where(AutonomyEvent.event_type == event_type)
    query = query.order_by(AutonomyEvent.occurred_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    events = result.scalars().all()
    
    return [
        AutonomyEventResponse(
            id=e.id,
            organization_id=e.organization_id,
            proposal_id=e.proposal_id,
            event_type=e.event_type,
            actor_id=e.actor_id,
            actor_type=e.actor_type,
            from_state=e.from_state,
            to_state=e.to_state,
            outcome=e.outcome,
            risk_score=e.risk_score,
            risk_factors=e.risk_factors,
            occurred_at=e.occurred_at,
        )
        for e in events
    ]


# =============================================================================
# Executions
# =============================================================================

@router.get("/executions", response_model=List[AutonomyExecutionResponse])
async def list_executions(
    proposal_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("autonomy:execution:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List autonomy executions."""
    query = select(AutonomyExecution).where(AutonomyExecution.organization_id == org.id)
    if proposal_id:
        query = query.where(AutonomyExecution.proposal_id == proposal_id)
    if state:
        query = query.where(AutonomyExecution.state == state)
    query = query.order_by(AutonomyExecution.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    executions = result.scalars().all()
    
    return [
        AutonomyExecutionResponse(
            id=e.id,
            organization_id=e.organization_id,
            proposal_id=e.proposal_id,
            action_id=e.action_id,
            state=e.state,
            attempt=e.attempt,
            max_attempts=e.max_attempts,
            started_at=e.started_at,
            completed_at=e.completed_at,
            duration_ms=e.duration_ms,
            result=e.result_json or {},
            error=e.error,
        )
        for e in executions
    ]


# =============================================================================
# Learning
# =============================================================================

@router.get("/learning", response_model=List[AutonomyLearningResponse])
async def list_learning(
    proposal_id: Optional[str] = Query(None),
    lesson_type: Optional[str] = Query(None),
    validated: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("autonomy:learning:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List autonomy learning records."""
    query = select(AutonomyLearning).where(AutonomyLearning.organization_id == org.id)
    if proposal_id:
        query = query.where(AutonomyLearning.proposal_id == proposal_id)
    if lesson_type:
        query = query.where(AutonomyLearning.lesson_type == lesson_type)
    if validated is not None:
        query = query.where(AutonomyLearning.validated == validated)
    query = query.order_by(AutonomyLearning.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    learnings = result.scalars().all()
    
    return [
        AutonomyLearningResponse(
            id=l.id,
            organization_id=l.organization_id,
            proposal_id=l.proposal_id,
            lesson_type=l.lesson_type,
            lesson_title=l.lesson_title,
            lesson_summary=l.lesson_summary,
            confidence=l.confidence,
            validated=l.validated,
        )
        for l in learnings
    ]


# =============================================================================
# Risk
# =============================================================================

@router.get("/risks", response_model=List[AutonomyRiskResponse])
async def list_risks(
    proposal_id: Optional[str] = Query(None),
    level: Optional[str] = Query(None, pattern="^(low|medium|high|critical)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("autonomy:risk:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List autonomy risks."""
    query = select(AutonomyRisk).where(AutonomyRisk.organization_id == org.id)
    if proposal_id:
        query = query.where(AutonomyRisk.proposal_id == proposal_id)
    if level:
        query = query.where(AutonomyRisk.level == level)
    query = query.order_by(AutonomyRisk.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    risks = result.scalars().all()
    
    return [
        AutonomyRiskResponse(
            id=r.id,
            organization_id=r.organization_id,
            proposal_id=r.proposal_id,
            kind=r.kind,
            level=r.level,
            title=r.title,
            description=r.description,
            probability=r.probability,
            impact_score=r.impact_score,
            state=r.state,
        )
        for r in risks
    ]


# =============================================================================
# Contexts
# =============================================================================

@router.get("/contexts", response_model=List[AutonomyContextResponse])
async def list_contexts(
    proposal_id: Optional[str] = Query(None),
    context_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("autonomy:context:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List autonomy contexts."""
    query = select(AutonomyContext).where(AutonomyContext.organization_id == org.id)
    if proposal_id:
        query = query.where(AutonomyContext.proposal_id == proposal_id)
    if context_type:
        query = query.where(AutonomyContext.context_type == context_type)
    query = query.order_by(AutonomyContext.computed_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    contexts = result.scalars().all()
    
    return [
        AutonomyContextResponse(
            id=c.id,
            organization_id=c.organization_id,
            proposal_id=c.proposal_id,
            context_type=c.context_type,
            context_json=c.context_json or {},
            computed_at=c.computed_at,
        )
        for c in contexts
    ]


# =============================================================================
# Exports
# =============================================================================

# Router aliases for backward compatibility with main.py
autonomy_router = router
briefing_router = router
decision_router = router

__all__ = ["router", "autonomy_router", "briefing_router", "decision_router"]