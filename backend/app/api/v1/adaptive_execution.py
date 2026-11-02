"""Phase 4I.8 â€” Adaptive Execution & Outcome Observation API.

Governance-first API for the canonical commitmentâ†’actionâ†’workâ†’observation loop.
"""

from typing import Optional, List
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.intelligence.adaptive_execution_engine import adaptive_execution_engine
from app.intelligence.governed_commitment_engine import governed_commitment_engine
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/adaptive-execution", tags=["Adaptive Execution"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class ActionFromCommitmentIn(BaseModel):
    action_type: str = Field("task", description="Action type: task|decision|communication|knowledge|meeting|project")
    title: str = Field("", max_length=300, description="Action title")
    description: Optional[str] = Field(None, description="Action description")
    source_problem: Optional[str] = Field(None, description="Source problem")
    target: Optional[str] = Field(None, description="Action target")
    scope_type: Optional[str] = Field(None, description="Scope type override")
    scope_id: Optional[str] = Field(None, description="Scope ID override")
    risk: str = Field("low", description="Risk level: low|medium|high")
    due_at: Optional[date] = Field(None, description="Due date")
    assignee_id: Optional[str] = Field(None, description="Assignee employee ID")
    depends_on: Optional[List[str]] = Field(None, description="Action dependency IDs")


class ActionPlanIn(BaseModel):
    actions: List[ActionFromCommitmentIn] = Field(..., description="Action plan specification")


class ExecutionObservationIn(BaseModel):
    outcome_type: str = Field("success", description="Outcome type: success|partial|failed|not_applicable")
    effectiveness: float = Field(0.5, ge=0.0, le=1.0, description="Effectiveness score 0-1")
    verdict: Optional[str] = Field(None, description="Human verdict")
    evidence: Optional[List[str]] = Field(None, description="Evidence fingerprints")
    notes: Optional[str] = Field(None, description="Observation notes")


class OutcomeAssessmentIn(BaseModel):
    expected_outcome: dict = Field(..., description="Expected outcome with target_value")
    actual_observation: dict = Field(..., description="Actual observation with actual_value")
    measurement_quality: str = Field("medium", description="Measurement quality: high|medium|low|unknown")
    measurement_source: Optional[str] = Field(None, description="Measurement source")
    evidence_fingerprints: Optional[List[str]] = Field(None, description="Evidence fingerprints")


class CommitmentExecutionStatusOut(BaseModel):
    commitment_id: str
    commitment_title: str
    commitment_state: str
    health: str
    actions: dict
    avg_effectiveness: float
    outcomes: List[dict]
    action_details: List[dict]
    objective_linked: bool
    initiative_linked: bool
    project_linked: bool


class ActionProposalOut(BaseModel):
    id: str
    organization_id: str
    action_type: str
    title: str
    description: Optional[str]
    state: str
    risk: str
    scope_type: str
    scope_id: Optional[str]
    target_type: Optional[str]
    target_id: Optional[str]
    source_commitment_id: Optional[str]
    source_company_decision_id: Optional[str]
    source_recommendation_id: Optional[str]
    source_insight_id: Optional[str]
    due_at: Optional[datetime]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    deduplicated: Optional[bool] = None


class OutcomeObservationOut(BaseModel):
    outcome: dict
    action: dict


class OutcomeAssessmentOut(BaseModel):
    commitment_id: str
    assessment: str
    variance_pct: float
    expected: float
    actual: float
    measurement_quality: str
    evidence_fingerprints: List[str]
    contradictions: List[dict]
    assessed_at: str


class CompanyStateUpdateOut(BaseModel):
    company_state: dict
    commitment_outcomes_included: bool
    synthesized_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/commitments/{commitment_id}/propose-actions", response_model=List[ActionProposalOut], status_code=201)
async def propose_actions_from_commitment(
    commitment_id: str,
    payload: ActionPlanIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:manage")),
):
    """
    Propose a batch of governed actions from an authorized commitment.
    
    The commitment must be in an executable state (authorized, active).
    Actions are proposed through the canonical action_ops_engine with the
    commitment as provenance.
    """
    results = await adaptive_execution_engine.propose_actions_from_commitment(
        db, org.id,
        user_id=user.id,
        commitment_id=commitment_id,
        action_plan=[a.model_dump() for a in payload.actions],
    )
    return [ActionProposalOut(**r) for r in results if r]


@router.post("/commitments/{commitment_id}/propose-single-action", response_model=ActionProposalOut, status_code=201)
async def propose_single_action_from_commitment(
    commitment_id: str,
    payload: ActionFromCommitmentIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:manage")),
):
    """
    Propose a single governed action from an authorized commitment.
    """
    result = await governed_commitment_engine.propose_actions_from_commitment(
        db, org.id,
        user_id=user.id,
        commitment_id=commitment_id,
        **payload.model_dump(),
    )
    if not result:
        raise HTTPException(400, "Action not created (may be deduplicated)")
    return ActionProposalOut(**result)


@router.post("/commitments/{commitment_id}/sync-actions", response_model=List[str])
async def sync_commitment_actions(
    commitment_id: str,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:read")),
):
    """
    Sync commitment.action_ids with all CompanyActions that reference
    this commitment as source_commitment_id.
    """
    action_ids = await governed_commitment_engine.sync_commitment_actions(
        db, org.id, commitment_id
    )
    return action_ids


@router.get("/commitments/{commitment_id}/execution-status", response_model=CommitmentExecutionStatusOut)
async def get_commitment_execution_status(
    commitment_id: str,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:read")),
):
    """
    Get comprehensive execution status for a commitment.
    
    Includes action states, outcomes, effectiveness, and health assessment.
    """
    status = await adaptive_execution_engine.get_commitment_execution_status(
        db, org.id, commitment_id
    )
    if not status:
        raise HTTPException(404, "Commitment not found")
    return CommitmentExecutionStatusOut(**status)


@router.post("/actions/{action_id}/route-to-work", response_model=dict)
async def route_action_to_work(
    action_id: str,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:manage")),
):
    """
    Route an approved action through the existing work infrastructure.
    
    Creates the actual Task/Project/Meeting/etc. in the operating systems.
    """
    result = await adaptive_execution_engine.route_action_to_work(
        db, org.id, action_id, user_id=user.id
    )
    if not result:
        raise HTTPException(404, "Action not found or not approved")
    return result


@router.post("/actions/{action_id}/observe", response_model=OutcomeObservationOut)
async def record_execution_observation(
    action_id: str,
    payload: ExecutionObservationIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:manage")),
):
    """
    Record an execution observation with outcome assessment.
    
    This distinguishes action completion from outcome achievement.
    """
    result = await adaptive_execution_engine.record_execution_observation(
        db, org.id,
        user_id=user.id,
        action_id=action_id,
        observation=payload.model_dump(),
        outcome_type=payload.outcome_type,
        effectiveness=payload.effectiveness,
        evidence=payload.evidence,
        notes=payload.notes,
    )
    if not result:
        raise HTTPException(404, "Action not found or not in recordable state")
    return OutcomeObservationOut(**result)


@router.post("/commitments/{commitment_id}/assess-outcome", response_model=OutcomeAssessmentOut)
async def assess_commitment_outcome(
    commitment_id: str,
    payload: OutcomeAssessmentIn,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:manage")),
):
    """
    Assess a commitment's outcome by comparing expected vs actual.
    
    Creates an ObjectiveOutcomeAssessment if linked to objective.
    """
    result = await adaptive_execution_engine.assess_commitment_outcome(
        db, org.id, commitment_id,
        user_id=user.id,
        expected_outcome=payload.expected_outcome,
        actual_observation=payload.actual_observation,
        measurement_quality=payload.measurement_quality,
        measurement_source=payload.measurement_source,
        evidence_fingerprints=payload.evidence_fingerprints,
    )
    return OutcomeAssessmentOut(**result)


@router.post("/commitments/{commitment_id}/update-state", response_model=CompanyStateUpdateOut)
async def update_company_state_from_execution(
    commitment_id: str,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("commitments:read")),
):
    """
    Update CompanyState from execution outcomes.
    
    Feeds back into 4I.4 Planning Context â†’ 4I.5 Adaptive Planning.
    """
    result = await adaptive_execution_engine.update_company_state_from_execution(
        db, org.id, commitment_id
    )
    return CompanyStateUpdateOut(**result)