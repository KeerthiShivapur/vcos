"""
4I.10 API — Universal Company Operating Orchestration.

Governed API surface for verification/reconciliation operations.
Every endpoint resolves governance scope first and enforces tenant isolation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.database import get_db
from app.intelligence.verification_orchestration_engine import verification_orchestration_engine
from app.models.execution_strategy import (
    VerificationContext,
    VerificationEvidence,
    AssessmentRecord,
    VERIFICATION_STATES,
    ASSESSMENT_VERDICTS,
    EVIDENCE_TYPES,
    VERIFICATION_TRIGGERS,
    EVIDENCE_QUALITY,
    VERIFICATION_TYPES,
)
from app.models.user import User

router = APIRouter(prefix="/v1/verification", tags=["4I.10 Verification"])


# =============================================================================
# Request/Response Models
# =============================================================================

class VerificationContextCreate(BaseModel):
    verification_type: str = Field(default="plan_vs_reality", pattern="^(plan_vs_reality|commitment_fulfillment|objective_achievement)$")
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    scope_type: str = Field(default="company", pattern="^(company|department|team|project|initiative|objective|commitment)$")
    scope_id: Optional[str] = None
    commitment_id: Optional[str] = None
    authorization_id: Optional[str] = None
    objective_id: Optional[str] = None
    initiative_id: Optional[str] = None
    project_id: Optional[str] = None
    responsibility_id: Optional[str] = None
    expected_outcome: Optional[dict] = None
    expected_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    trigger: str = Field(default="manual_request", pattern="^(outcome_recorded|evidence_submitted|commitment_fulfilled|periodic_review|manual_request|anomaly_detected)$")
    source_event_id: Optional[str] = None


class VerificationContextResponse(BaseModel):
    id: str
    organization_id: str
    verification_type: str
    title: str
    description: Optional[str]
    scope_type: str
    scope_id: Optional[str]
    commitment_id: Optional[str]
    authorization_id: Optional[str]
    objective_id: Optional[str]
    initiative_id: Optional[str]
    project_id: Optional[str]
    responsibility_id: Optional[str]
    state: str
    expected_outcome: Optional[dict]
    expected_confidence: float
    actual_outcome: Optional[dict]
    actual_confidence: float
    variance_pct: Optional[float]
    variance_direction: Optional[str]
    assessment: Optional[str]
    assessment_confidence: float
    assessment_reasoning: Optional[str]
    trigger: str
    source_event_id: Optional[str]
    requested_by: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    computed_at: Optional[datetime]
    created_at: datetime
    fingerprint: str
    version: int

    class Config:
        from_attributes = True


class EvidenceSubmit(BaseModel):
    evidence_type: str = Field(pattern="^(metric|financial|operational|customer_feedback|survey|audit|document|testimony|log|other)$")
    evidence_id: str = Field(min_length=1, max_length=64)
    evidence_type_detail: str = Field(min_length=1, max_length=60)
    summary: str = Field(min_length=1, max_length=500)
    detail: Optional[str] = None
    quality: str = Field(default="secondary", pattern="^(primary|secondary|hearsay|inferred)$")
    source: Optional[str] = None
    captured_at: Optional[datetime] = None
    supports_verdict: Optional[str] = None
    source_event_id: Optional[str] = None


class EvidenceResponse(BaseModel):
    id: str
    organization_id: str
    verification_id: str
    evidence_type: str
    evidence_id: str
    evidence_type_detail: str
    summary: str
    detail: Optional[str]
    quality: str
    source: Optional[str]
    captured_at: datetime
    source_event_id: Optional[str]
    supports_verdict: Optional[str]
    fingerprint: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReconciliationRun(BaseModel):
    actual_outcome: dict
    actual_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    assessed_by: Optional[str] = None


class AssessmentRecordResponse(BaseModel):
    id: str
    organization_id: str
    verification_id: str
    objective_id: Optional[str]
    assessment_key: str
    assessment: str
    confidence: float
    reasoning: Optional[str]
    variance_pct: Optional[float]
    assessed_by: Optional[str]
    assessed_at: datetime
    fingerprint: str
    version: int

    class Config:
        from_attributes = True


class VerificationListResponse(BaseModel):
    items: list[VerificationContextResponse]
    total: int
    limit: int
    offset: int


class EvidenceQualitySummary(BaseModel):
    total: int
    by_quality: dict[str, int]
    has_primary: bool
    has_contradictions: bool


# =============================================================================
# Verification Context Endpoints
# =============================================================================

@router.post("/contexts", response_model=VerificationContextResponse, status_code=201)
async def create_verification_context(
    payload: VerificationContextCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new verification context."""
    vc = await verification_orchestration_engine.create_verification_context(
        db,
        current_user.organization_id,
        verification_type=payload.verification_type,
        title=payload.title,
        description=payload.description,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        commitment_id=payload.commitment_id,
        authorization_id=payload.authorization_id,
        objective_id=payload.objective_id,
        initiative_id=payload.initiative_id,
        project_id=payload.project_id,
        responsibility_id=payload.responsibility_id,
        expected_outcome=payload.expected_outcome,
        expected_confidence=payload.expected_confidence,
        trigger=payload.trigger,
        source_event_id=payload.source_event_id,
        requested_by=current_user.id,
    )
    return VerificationContextResponse.model_validate(vc)


@router.get("/contexts/{verification_id}", response_model=VerificationContextResponse)
async def get_verification_context(
    verification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a verification context by ID."""
    vc = await verification_orchestration_engine.get_verification_context(
        db, current_user.organization_id, verification_id
    )
    if not vc:
        raise HTTPException(status_code=404, detail="Verification context not found")
    return VerificationContextResponse.model_validate(vc)


@router.get("/contexts", response_model=VerificationListResponse)
async def list_verification_contexts(
    state: Optional[str] = Query(None, pattern=f"^({'|'.join(VERIFICATION_STATES)})$"),
    verification_type: Optional[str] = Query(None, pattern=f"^({'|'.join(VERIFICATION_TYPES)})$"),
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List verification contexts with filtering."""
    contexts = await verification_orchestration_engine.list_verification_contexts(
        db,
        current_user.organization_id,
        state=state,
        verification_type=verification_type,
        scope_type=scope_type,
        scope_id=scope_id,
        limit=limit,
        offset=offset,
    )
    total_stmt = select(VerificationContext).where(VerificationContext.organization_id == current_user.organization_id)
    if state:
        total_stmt = total_stmt.where(VerificationContext.state == state)
    total_result = await db.execute(total_stmt)
    total = len(total_result.scalars().all())

    return VerificationListResponse(
        items=[VerificationContextResponse.model_validate(c) for c in contexts],
        total=total,
        limit=limit,
        offset=offset,
    )


# =============================================================================
# Evidence Endpoints
# =============================================================================

@router.post("/contexts/{verification_id}/evidence", response_model=EvidenceResponse, status_code=201)
async def submit_evidence(
    verification_id: str,
    payload: EvidenceSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit evidence for a verification context."""
    evidence = await verification_orchestration_engine.submit_evidence(
        db,
        current_user.organization_id,
        verification_id,
        evidence_type=payload.evidence_type,
        evidence_id=payload.evidence_id,
        evidence_type_detail=payload.evidence_type_detail,
        summary=payload.summary,
        detail=payload.detail,
        quality=payload.quality,
        source=payload.source,
        captured_at=payload.captured_at,
        supports_verdict=payload.supports_verdict,
        source_event_id=payload.source_event_id,
    )
    return EvidenceResponse.model_validate(evidence)


@router.get("/contexts/{verification_id}/evidence", response_model=list[EvidenceResponse])
async def get_evidence(
    verification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all evidence for a verification context."""
    evidence = await verification_orchestration_engine.get_evidence(
        db, current_user.organization_id, verification_id
    )
    return [EvidenceResponse.model_validate(e) for e in evidence]


@router.get("/contexts/{verification_id}/evidence/quality", response_model=EvidenceQualitySummary)
async def get_evidence_quality(
    verification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get evidence quality breakdown for a verification."""
    return await verification_orchestration_engine.get_evidence_quality_summary(
        db, current_user.organization_id, verification_id
    )


# =============================================================================
# Reconciliation & Assessment Endpoints
# =============================================================================

@router.post("/contexts/{verification_id}/reconcile", response_model=AssessmentRecordResponse)
async def run_reconciliation(
    verification_id: str,
    payload: ReconciliationRun,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run the core reconciliation: compare expected vs actual, produce assessment."""
    ar = await verification_orchestration_engine.run_reconciliation(
        db,
        current_user.organization_id,
        verification_id,
        actual_outcome=payload.actual_outcome,
        actual_confidence=payload.actual_confidence,
        assessed_by=current_user.id,
    )
    return AssessmentRecordResponse.model_validate(ar)


@router.get("/contexts/{verification_id}/assessment", response_model=AssessmentRecordResponse)
async def get_assessment(
    verification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the assessment record for a verification."""
    ar = await verification_orchestration_engine.get_assessment_record(
        db, current_user.organization_id, verification_id
    )
    if not ar:
        raise HTTPException(status_code=404, detail="Assessment record not found")
    return AssessmentRecordResponse.model_validate(ar)


# =============================================================================
# History & Query Endpoints
# =============================================================================

@router.get("/history", response_model=VerificationListResponse)
async def get_verification_history(
    verification_id: Optional[str] = None,
    objective_id: Optional[str] = None,
    commitment_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get verification history with filtering."""
    contexts = await verification_orchestration_engine.get_verification_history(
        db,
        current_user.organization_id,
        verification_id=verification_id,
        objective_id=objective_id,
        commitment_id=commitment_id,
        limit=limit,
    )
    return VerificationListResponse(
        items=[VerificationContextResponse.model_validate(c) for c in contexts],
        total=len(contexts),
        limit=limit,
        offset=0,
    )