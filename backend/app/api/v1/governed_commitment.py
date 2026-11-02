"""Phase 4I.7 â€” Governed Commitment / Authorization API.

Governance-first API for the canonical commitment/authorization layer.
"""

from typing import Optional
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.intelligence.governed_commitment_engine import governed_commitment_engine
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/governed-commitment", tags=["Governed Commitment"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class CommitmentCreateIn(BaseModel):
    commitment_type: str = Field(..., description="Type of commitment")
    title: str = Field(..., max_length=300, description="Commitment title")
    description: Optional[str] = Field(None, description="Commitment description")
    rationale: Optional[str] = Field(None, description="Rationale for commitment")
    scope_type: str = Field("company", description="Scope type: company|initiative|project|department|team")
    scope_id: Optional[str] = Field(None, description="Scope ID if not company-wide")
    intent_id: Optional[str] = Field(None, description="Linked intent ID")
    objective_id: Optional[str] = Field(None, description="Linked objective ID")
    initiative_id: Optional[str] = Field(None, description="Linked initiative ID")
    project_id: Optional[str] = Field(None, description="Linked project ID")
    decision_id: Optional[str] = Field(None, description="Linked decision ID")
    authorization_id: Optional[str] = Field(None, description="Authorization ID if conditional")
    budget_allocated: Optional[float] = Field(None, description="Allocated budget")
    budget_currency: Optional[str] = Field(None, description="Budget currency")
    resource_requirements: Optional[dict] = Field(None, description="Resource requirements")
    resource_constraints: Optional[dict] = Field(None, description="Resource constraints")
    start_date: Optional[date] = Field(None, description="Start date")
    target_date: Optional[date] = Field(None, description="Target completion date")
    conditions: Optional[list[dict]] = Field(None, description="Conditions for conditional commitments")
    risk_assessment: Optional[dict] = Field(None, description="Risk assessment")
    risk_mitigations: Optional[list[dict]] = Field(None, description="Risk mitigations")
    evidence_fingerprints: Optional[list[str]] = Field(None, description="Evidence fingerprints")
    supporting_pattern_ids: Optional[list[str]] = Field(None, description="Supporting pattern IDs")
    supporting_lesson_fingerprints: Optional[list[str]] = Field(None, description="Supporting lesson fingerprints")
    contradicting_evidence_fingerprints: Optional[list[str]] = Field(None, description="Contradicting evidence fingerprints")
    contradicting_pattern_ids: Optional[list[str]] = Field(None, description="Contradicting pattern IDs")
    contradicting_lesson_fingerprints: Optional[list[str]] = Field(None, description="Contradicting lesson fingerprints")
    contradiction_ids: Optional[list[str]] = Field(None, description="Contradiction IDs")
    decision_intelligence_context_id: Optional[str] = Field(None, description="Decision intelligence context ID")
    decision_alternative_ids: Optional[list[str]] = Field(None, description="Decision alternative IDs")
    decision_evidence_fingerprints: Optional[list[str]] = Field(None, description="Decision evidence fingerprints")
    decision_precedent_ids: Optional[list[str]] = Field(None, description="Decision precedent IDs")
    source_event_id: Optional[str] = Field(None, description="Source event ID")
    source_decision_id: Optional[str] = Field(None, description="Source decision ID")
    source_scenario_id: Optional[str] = Field(None, description="Source scenario ID")


class AuthorizationCreateIn(BaseModel):
    authorization_type: str = Field(..., description="Authorization type")
    title: str = Field(..., max_length=300, description="Authorization title")
    description: Optional[str] = Field(None, description="Authorization description")
    rationale: Optional[str] = Field(None, description="Rationale for authorization")
    scope_type: str = Field("company", description="Scope type: company|initiative|project|department|team")
    scope_id: Optional[str] = Field(None, description="Scope ID if not company-wide")
    decision_intelligence_context_id: Optional[str] = Field(None, description="Decision intelligence context ID")
    decision_id: Optional[str] = Field(None, description="Decision ID being authorized")
    commitment_id: Optional[str] = Field(None, description="Commitment being authorized")
    conditions: Optional[list[dict]] = Field(None, description="Authorization conditions")
    constraints: Optional[dict] = Field(None, description="Constraints")
    budget_ceiling: Optional[float] = Field(None, description="Budget ceiling")
    budget_currency: Optional[str] = Field(None, description="Budget currency")
    valid_from: Optional[date] = Field(None, description="Valid from date")
    valid_until: Optional[date] = Field(None, description="Valid until date")
    policy_id: Optional[str] = Field(None, description="Approval policy ID")
    evidence_fingerprints: Optional[list[str]] = Field(None, description="Evidence fingerprints")
    supporting_pattern_ids: Optional[list[str]] = Field(None, description="Supporting pattern IDs")
    supporting_lesson_fingerprints: Optional[list[str]] = Field(None, description="Supporting lesson fingerprints")
    contradicting_evidence_fingerprints: Optional[list[str]] = Field(None, description="Contradicting evidence fingerprints")
    contradicting_pattern_ids: Optional[list[str]] = Field(None, description="Contradicting pattern IDs")
    contradicting_lesson_fingerprints: Optional[list[str]] = Field(None, description="Contradicting lesson fingerprints")
    contradiction_ids: Optional[list[str]] = Field(None, description="Contradiction IDs")
    decision_alternative_ids: Optional[list[str]] = Field(None, description="Decision alternative IDs")
    decision_evidence_fingerprints: Optional[list[str]] = Field(None, description="Decision evidence fingerprints")
    decision_precedent_ids: Optional[list[str]] = Field(None, description="Decision precedent IDs")
    risk_assessment: Optional[dict] = Field(None, description="Risk assessment")
    lesson_fingerprints: Optional[list[str]] = Field(None, description="Lesson fingerprints")
    pattern_ids: Optional[list[str]] = Field(None, description="Pattern IDs")
    source_event_id: Optional[str] = Field(None, description="Source event ID")
    source_decision_id: Optional[str] = Field(None, description="Source decision ID")
    source_scenario_id: Optional[str] = Field(None, description="Source scenario ID")


class AuthorizationReviewIn(BaseModel):
    action: str = Field(..., description="Action: approve|reject|conditional")
    review_note: Optional[str] = Field(None, description="Review note")
    conditions: Optional[list[dict]] = Field(None, description="Conditions for conditional approval")
    source_event_id: Optional[str] = Field(None, description="Source event ID")


class CommitmentTransitionIn(BaseModel):
    new_state: str = Field(..., description="New commitment state")
    reason: str = Field(..., description="Reason for transition")
    source_event_id: Optional[str] = Field(None, description="Source event ID")


class SupersedeCommitmentIn(BaseModel):
    new_commitment_id: str = Field(..., description="New commitment ID to supersede with")
    reason: str = Field(..., description="Reason for supersession")
    source_event_id: Optional[str] = Field(None, description="Source event ID")


class CommitmentFromDIIn(BaseModel):
    decision_intelligence_context_id: str = Field(..., description="Decision intelligence context ID")
    selected_alternative_id: str = Field(..., description="Selected alternative ID")
    authorization_required: bool = Field(True, description="Whether authorization is required")
    source_event_id: Optional[str] = Field(None, description="Source event ID")
    trigger_reason: Optional[str] = Field(None, description="Trigger reason")


class AuthorizationQueryParams(BaseModel):
    scope: str = Field("company", description="Scope: company|initiative|project|department|team")
    scope_id: Optional[str] = Field(None, description="Scope ID")
    state: Optional[str] = Field(None, description="Authorization state filter")
    authorization_type: Optional[str] = Field(None, description="Authorization type filter")
    limit: int = Field(50, le=200, description="Result limit")
    offset: int = Field(0, ge=0, description="Result offset")


class CommitmentQueryParams(BaseModel):
    scope: str = Field("company", description="Scope: company|initiative|project|department|team")
    scope_id: Optional[str] = Field(None, description="Scope ID")
    state: Optional[str] = Field(None, description="Commitment state filter")
    commitment_type: Optional[str] = Field(None, description="Commitment type filter")
    limit: int = Field(50, le=200, description="Result limit")
    offset: int = Field(0, ge=0, description="Result offset")


class CommitmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    commitment_type: str
    title: str
    description: Optional[str]
    rationale: Optional[str]
    scope_type: str
    scope_id: Optional[str]
    intent_id: Optional[str]
    objective_id: Optional[str]
    initiative_id: Optional[str]
    project_id: Optional[str]
    decision_id: Optional[str]
    authorization_id: Optional[str]
    approval_required: bool
    budget_allocated: Optional[float]
    budget_currency: Optional[str]
    resource_requirements: Optional[dict]
    resource_constraints: Optional[dict]
    start_date: Optional[datetime]
    target_date: Optional[datetime]
    conditions: list[dict]
    risk_assessment: Optional[str]
    risk_mitigations: list[dict]
    evidence_fingerprints: list[str]
    supporting_pattern_ids: list[str]
    supporting_lesson_fingerprints: list[str]
    contradicting_evidence_fingerprints: list[str]
    contradicting_pattern_ids: list[str]
    contradicting_lesson_fingerprints: list[str]
    contradiction_ids: list[str]
    decision_intelligence_context_id: Optional[str]
    decision_alternative_ids: list[str]
    action_ids: list[str]
    state: str
    authorized_at: Optional[datetime]
    authorized_by: Optional[str]
    fulfilled_at: Optional[datetime]
    fulfilled_by: Optional[str]
    supersedes_id: Optional[str]
    superseded_by_id: Optional[str]
    source_event_id: Optional[str]
    source_decision_id: Optional[str]
    source_scenario_id: Optional[str]
    fingerprint: str
    version: int
    created_at: datetime
    updated_at: datetime


class AuthorizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    authorization_type: str
    title: str
    description: Optional[str]
    rationale: Optional[str]
    scope_type: str
    scope_id: Optional[str]
    decision_intelligence_context_id: Optional[str]
    decision_id: Optional[str]
    commitment_id: Optional[str]
    policy_id: Optional[str]
    conditions: list[dict]
    constraints: Optional[dict]
    budget_ceiling: Optional[float]
    budget_currency: Optional[str]
    valid_from: datetime
    valid_until: Optional[datetime]
    state: str
    requested_by: Optional[str]
    requested_at: datetime
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    rejected_by: Optional[str]
    rejected_at: Optional[datetime]
    evidence_fingerprints: list[str]
    supporting_pattern_ids: list[str]
    supporting_lesson_fingerprints: list[str]
    contradicting_evidence_fingerprints: list[str]
    contradicting_pattern_ids: list[str]
    contradicting_lesson_fingerprints: list[str]
    contradiction_ids: list[str]
    decision_alternative_ids: list[str]
    decision_evidence_fingerprints: list[str]
    decision_precedent_ids: list[str]
    risk_assessment: Optional[dict]
    lesson_fingerprints: list[str]
    pattern_ids: list[str]
    source_event_id: Optional[str]
    source_decision_id: Optional[str]
    source_scenario_id: Optional[str]
    fingerprint: str
    version: int
    created_at: datetime
    updated_at: datetime


class CommitmentTransitionResponse(BaseModel):
    id: str
    organization_id: str
    commitment_id: str
    from_state: str
    to_state: str
    reason: str
    source_event_id: Optional[str]
    transitioned_at: datetime


class CommitmentLineageResponse(BaseModel):
    commitment: CommitmentResponse
    intent: Optional[dict]
    objective: Optional[dict]
    initiative: Optional[dict]
    project: Optional[dict]
    decision: Optional[dict]
    authorization: Optional[dict]
    decision_intelligence: Optional[dict]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/commitments", response_model=CommitmentResponse, status_code=201)
async def create_commitment(
    payload: CommitmentCreateIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:manage")),
):
    """Create a new company commitment with governance and learning integration."""
    commitment = await governed_commitment_engine.create_commitment(
        db,
        org.id,
        user_id=user.id,
        commitment_type=payload.commitment_type,
        title=payload.title,
        description=payload.description,
        rationale=payload.rationale,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        intent_id=payload.intent_id,
        objective_id=payload.objective_id,
        initiative_id=payload.initiative_id,
        project_id=payload.project_id,
        decision_id=payload.decision_id,
        authorization_id=payload.authorization_id,
        budget_allocated=payload.budget_allocated,
        budget_currency=payload.budget_currency,
        resource_requirements=payload.resource_requirements,
        resource_constraints=payload.resource_constraints,
        start_date=payload.start_date,
        target_date=payload.target_date,
        conditions=payload.conditions,
        risk_assessment=payload.risk_assessment,
        risk_mitigations=payload.risk_mitigations,
        evidence_fingerprints=payload.evidence_fingerprints,
        supporting_pattern_ids=payload.supporting_pattern_ids,
        supporting_lesson_fingerprints=payload.supporting_lesson_fingerprints,
        contradicting_evidence_fingerprints=payload.contradicting_evidence_fingerprints,
        contradicting_pattern_ids=payload.contradicting_pattern_ids,
        contradicting_lesson_fingerprints=payload.contradicting_lesson_fingerprints,
        contradiction_ids=payload.contradiction_ids,
        decision_intelligence_context_id=payload.decision_intelligence_context_id,
        decision_alternative_ids=payload.decision_alternative_ids,
        decision_evidence_fingerprints=payload.decision_evidence_fingerprints,
        decision_precedent_ids=payload.decision_precedent_ids,
        source_event_id=payload.source_event_id,
        source_decision_id=payload.source_decision_id,
        source_scenario_id=payload.source_scenario_id,
    )
    return CommitmentResponse.model_validate(commitment)


@router.post("/authorizations", response_model=AuthorizationResponse, status_code=201)
async def create_authorization(
    payload: AuthorizationCreateIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("authorizations:manage")),
):
    """Create a new authorization request with governance and learning integration."""
    auth = await governed_commitment_engine.create_authorization_request(
        db,
        org.id,
        user_id=user.id,
        authorization_type=payload.authorization_type,
        title=payload.title,
        description=payload.description,
        rationale=payload.rationale,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        decision_intelligence_context_id=payload.decision_intelligence_context_id,
        decision_id=payload.decision_id,
        commitment_id=payload.commitment_id,
        conditions=payload.conditions,
        constraints=payload.constraints,
        budget_ceiling=payload.budget_ceiling,
        budget_currency=payload.budget_currency,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        policy_id=payload.policy_id,
        evidence_fingerprints=payload.evidence_fingerprints,
        supporting_pattern_ids=payload.supporting_pattern_ids,
        supporting_lesson_fingerprints=payload.supporting_lesson_fingerprints,
        contradicting_evidence_fingerprints=payload.contradicting_evidence_fingerprints,
        contradicting_pattern_ids=payload.contradicting_pattern_ids,
        contradicting_lesson_fingerprints=payload.contradicting_lesson_fingerprints,
        contradiction_ids=payload.contradiction_ids,
        decision_alternative_ids=payload.decision_alternative_ids,
        decision_evidence_fingerprints=payload.decision_evidence_fingerprints,
        decision_precedent_ids=payload.decision_precedent_ids,
        risk_assessment=payload.risk_assessment,
        lesson_fingerprints=payload.lesson_fingerprints,
        pattern_ids=payload.pattern_ids,
        source_event_id=payload.source_event_id,
        source_decision_id=payload.source_decision_id,
        source_scenario_id=payload.source_scenario_id,
    )
    return AuthorizationResponse.model_validate(auth)


@router.post("/authorizations/{authorization_id}/review", response_model=AuthorizationResponse)
async def review_authorization(
    authorization_id: str,
    payload: AuthorizationReviewIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("authorizations:manage")),
):
    """Review an authorization request (approve/reject/conditional)."""
    auth = await governed_commitment_engine.review_authorization(
        db,
        org.id,
        authorization_id,
        user_id=user.id,
        action=payload.action,
        review_note=payload.review_note,
        conditions=payload.conditions,
        source_event_id=payload.source_event_id,
    )
    return AuthorizationResponse.model_validate(auth)


@router.post("/commitments/{commitment_id}/transition", response_model=CommitmentResponse)
async def transition_commitment(
    commitment_id: str,
    payload: CommitmentTransitionIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:manage")),
):
    """Transition commitment through governance states."""
    commitment = await governed_commitment_engine.transition_commitment(
        db,
        org.id,
        commitment_id,
        user_id=user.id,
        new_state=payload.new_state,
        reason=payload.reason,
        source_event_id=payload.source_event_id,
    )
    return CommitmentResponse.model_validate(commitment)


@router.post("/commitments/{commitment_id}/supersede", response_model=CommitmentResponse)
async def supersede_commitment(
    commitment_id: str,
    payload: SupersedeCommitmentIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:manage")),
):
    """Supersede a commitment with a new one. Maintains temporal supersession chain."""
    _, new_commitment = await governed_commitment_engine.supersede_commitment(
        db,
        org.id,
        commitment_id,
        payload.new_commitment_id,
        user_id=user.id,
        reason=payload.reason,
        source_event_id=payload.source_event_id,
    )
    return CommitmentResponse.model_validate(new_commitment)


@router.post("/commitments/from-decision-intelligence", response_model=CommitmentResponse, status_code=201)
async def create_commitment_from_decision_intelligence(
    payload: CommitmentFromDIIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:manage")),
):
    """Create a commitment directly from a Decision Intelligence context by selecting an alternative."""
    commitment = await governed_commitment_engine.create_commitment_from_decision_intelligence(
        db,
        org.id,
        user_id=user.id,
        decision_intelligence_context_id=payload.decision_intelligence_context_id,
        selected_alternative_id=payload.selected_alternative_id,
        authorization_required=payload.authorization_required,
        source_event_id=payload.source_event_id,
        trigger_reason=payload.trigger_reason,
    )
    return CommitmentResponse.model_validate(commitment)


@router.get("/commitments", response_model=list[CommitmentResponse])
async def list_commitments(
    params: CommitmentQueryParams = Depends(),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:read")),
):
    """List commitments with filters."""
    commitments = await governed_commitment_engine.list_commitments(
        db, org.id,
        scope=params.scope,
        scope_id=params.scope_id,
        state=params.state,
        commitment_type=params.commitment_type,
        limit=params.limit,
        offset=params.offset,
    )
    return [CommitmentResponse.model_validate(c) for c in commitments]


@router.get("/commitments/{commitment_id}", response_model=CommitmentResponse)
async def get_commitment(
    commitment_id: str,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:read")),
):
    """Get a commitment by ID."""
    commitment = await governed_commitment_engine.get_commitment(
        db, org.id, commitment_id
    )
    if not commitment:
        raise HTTPException(404, "Commitment not found")
    return CommitmentResponse.model_validate(commitment)


@router.get("/commitments/{commitment_id}/lineage", response_model=CommitmentLineageResponse)
async def get_commitment_lineage(
    commitment_id: str,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:read")),
):
    """Get a commitment with full lineage trace."""
    lineage = await governed_commitment_engine.get_commitment_with_lineage(
        db, org.id, commitment_id
    )
    if not lineage:
        raise HTTPException(404, "Commitment not found")
    return CommitmentLineageResponse(**lineage)


@router.get("/commitments/{commitment_id}/supersession-chain", response_model=list[CommitmentResponse])
async def get_supersession_chain(
    commitment_id: str,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:read")),
):
    """Get the full supersession chain for a commitment."""
    chain = await governed_commitment_engine.get_commitment_supersession_chain(
        db, org.id, commitment_id
    )
    return [CommitmentResponse.model_validate(c) for c in chain]


@router.post("/commitments/{commitment_id}/evaluate-conditions", response_model=dict)
async def evaluate_conditions(
    commitment_id: str,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:read")),
):
    """Evaluate all conditions for a conditional commitment."""
    result = await governed_commitment_engine.evaluate_conditions(
        db, org.id, commitment_id
    )
    return result


@router.get("/authorizations", response_model=list[AuthorizationResponse])
async def list_authorizations(
    params: AuthorizationQueryParams = Depends(),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("authorizations:read")),
):
    """List authorizations with filters."""
    authorizations = await governed_commitment_engine.list_authorizations(
        db, org.id,
        scope=params.scope,
        scope_id=params.scope_id,
        state=params.state,
        authorization_type=params.authorization_type,
        limit=params.limit,
        offset=params.offset,
    )
    return [AuthorizationResponse.model_validate(a) for a in authorizations]


@router.get("/authorizations/{authorization_id}", response_model=AuthorizationResponse)
async def get_authorization(
    authorization_id: str,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("authorizations:read")),
):
    """Get an authorization by ID."""
    auth = await governed_commitment_engine.get_authorization(
        db, org.id, authorization_id
    )
    if not auth:
        raise HTTPException(404, "Authorization not found")
    return AuthorizationResponse.model_validate(auth)