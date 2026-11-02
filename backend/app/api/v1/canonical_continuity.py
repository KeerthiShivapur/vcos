"""Gate 30 — Canonical Company Continuity API.

Provides REST API for the universal company operating continuity layer.
"""

from datetime import datetime
from typing import Any, Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.canonical_company_continuity import (
    CompanyOperatingContinuity,
    CompanyContinuityEvent,
    CompanyStateSnapshotGate30,
    UniversalCompanyContext,
    CrossDomainConsistencyCheck,
    CompanyOperatingHealth,
    UniversalCompanyTimeline,
    SelfCompoundingLoopState,
    COMPANY_LOOP_PHASES,
    CONTINUITY_EVENT_TYPES,
    EPISTEMIC_STATES,
    OPERATING_HEALTH_STATES,
    CONSISTENCY_CHECK_TYPES,
)
from app.services.canonical_company_continuity_service import canonical_company_continuity_service

router = APIRouter(prefix="/canonical-continuity", tags=["Canonical Company Continuity"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ContinuityCycleResponse(BaseModel):
    id: str
    organization_id: str
    cycle_number: int
    cycle_label: Optional[str] = None
    current_phase: str
    cycle_started_at: datetime
    cycle_completed_at: Optional[datetime] = None
    phase_entered_at: datetime
    operating_health: str
    health_details_json: Optional[Dict] = None
    contradiction_count: int
    contradictions_json: Optional[List[Dict]] = None
    lessons_learned: int
    patterns_updated: int
    calibration_improvements: int
    epistemic_summary_json: Optional[Dict] = None
    fingerprint: str
    version: int


class ContinuityEventResponse(BaseModel):
    id: str
    organization_id: str
    continuity_cycle_id: str
    event_type: str
    loop_phase: str
    occurred_at: datetime
    sequence_in_phase: int
    actor_id: Optional[str] = None
    actor_type: str
    title: str
    description: Optional[str] = None
    details_json: Optional[Dict] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    related_entities_json: Optional[Dict] = None
    epistemic_state: str
    evidence_fingerprints: List[str]
    source_event_ids: List[str]
    governance_scope_id: Optional[str] = None
    fingerprint: str
    version: int


class ContinuityStartRequest(BaseModel):
    cycle_label: Optional[str] = None
    triggered_by: Optional[str] = None
    source_event_ids: Optional[List[str]] = None


class PhaseAdvanceRequest(BaseModel):
    phase: str = Field(..., pattern="^(" + "|".join(COMPANY_LOOP_PHASES) + ")$")
    actor_id: Optional[str] = None
    actor_type: str = "human"
    source_event_ids: Optional[List[str]] = None


class ContinuityEventRecordRequest(BaseModel):
    event_type: str = Field(..., pattern="^(" + "|".join(CONTINUITY_EVENT_TYPES) + ")$")
    loop_phase: str = Field(..., pattern="^(" + "|".join(COMPANY_LOOP_PHASES) + ")$")
    title: str
    description: str
    actor_id: Optional[str] = None
    actor_type: str = "human"
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    source_event_ids: Optional[List[str]] = None
    related_entities: Optional[Dict] = None
    epistemic_state: str = Field("observed", pattern="^(" + "|".join(EPISTEMIC_STATES) + ")$")
    governance_scope_id: Optional[str] = None


class UniversalContextResponse(BaseModel):
    id: str
    organization_id: str
    caller_user_id: str
    org_wide: bool
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None
    computed_at: datetime
    context_version: int
    epistemic_breakdown_json: Optional[Dict] = None
    fingerprint: str
    version: int


class ConsistencyCheckResponse(BaseModel):
    id: str
    organization_id: str
    check_type: str
    checked_at: datetime
    status: str
    contradiction_count: int
    contradictions_json: Optional[List[Dict]] = None
    affected_entities_json: Optional[List[Dict]] = None
    acknowledged: bool
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    fingerprint: str
    version: int


class ConsistencyCheckAcknowledgeRequest(BaseModel):
    acknowledged_by: str
    resolution_note: Optional[str] = None


class OperatingHealthResponse(BaseModel):
    id: str
    organization_id: str
    overall_state: str
    assessed_at: datetime
    domain_health_json: Optional[Dict] = None
    unresolved_contradictions: int
    missing_responsibility: int
    stale_state_count: int
    failed_executions: int
    unknown_outcomes: int
    prediction_divergence_count: int
    twin_divergence_count: int
    blocked_operations: int
    governance_issues: int
    integration_failures: int
    learning_gaps: int
    details_json: Optional[Dict] = None
    fingerprint: str
    version: int


class TimelineEntryResponse(BaseModel):
    id: str
    organization_id: str
    event_type: str
    loop_phase: str
    occurred_at: datetime
    title: str
    description: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    actor_id: Optional[str] = None
    actor_type: str
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None
    related_events_json: Optional[List[str]] = None
    continuity_cycle_id: Optional[str] = None
    epistemic_state: str
    evidence_fingerprints: List[str]
    visible_to_org_wide: bool
    visible_scope_ids_json: List[str]
    fingerprint: str
    version: int


class CompoundingLoopResponse(BaseModel):
    id: str
    organization_id: str
    cycle_number: int
    current_phase: str
    cycle_started_at: datetime
    cycle_completed_at: Optional[datetime] = None
    phase_entered_at: datetime
    loop_duration_ms: int
    phases_completed: int
    calibration_delta: float
    learning_accumulated: int
    fingerprint: str
    version: int


class CompoundingLoopRunRequest(BaseModel):
    trigger: str = "scheduled"


# =============================================================================
# Operating Continuity Endpoints
# =============================================================================

@router.post("/cycles/start", response_model=ContinuityCycleResponse, status_code=201)
async def start_continuity_cycle(
    request: ContinuityStartRequest,
    user: User = Depends(require_permission("canonical_continuity:cycles:write")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Start a new company operating continuity cycle."""
    
    continuity = await canonical_company_continuity_service.start_new_cycle(
        db,
        org.id,
        cycle_label=request.cycle_label,
        triggered_by=request.triggered_by or user.id,
        source_event_ids=request.source_event_ids,
    )
    await db.commit()
    
    return ContinuityCycleResponse(
        id=continuity.id,
        organization_id=continuity.organization_id,
        cycle_number=continuity.cycle_number,
        cycle_label=continuity.cycle_label,
        current_phase=continuity.current_phase,
        cycle_started_at=continuity.cycle_started_at,
        cycle_completed_at=continuity.cycle_completed_at,
        phase_entered_at=continuity.phase_entered_at,
        operating_health=continuity.operating_health,
        health_details_json=continuity.health_details_json,
        contradiction_count=continuity.contradiction_count,
        contradictions_json=continuity.contradictions_json,
        lessons_learned=continuity.lessons_learned,
        patterns_updated=continuity.patterns_updated,
        calibration_improvements=continuity.calibration_improvements,
        epistemic_summary_json=continuity.epistemic_summary_json,
        fingerprint=continuity.fingerprint,
        version=continuity.version,
    )


@router.get("/cycles/current", response_model=ContinuityCycleResponse)
async def get_current_cycle(
    user: User = Depends(require_permission("canonical_continuity:cycles:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get the current operating continuity cycle."""
    
    continuity = await canonical_company_continuity_service.get_current_continuity(db, org.id)
    if not continuity:
        raise HTTPException(status_code=404, detail="No continuity cycle found")
    
    return ContinuityCycleResponse(
        id=continuity.id,
        organization_id=continuity.organization_id,
        cycle_number=continuity.cycle_number,
        cycle_label=continuity.cycle_label,
        current_phase=continuity.current_phase,
        cycle_started_at=continuity.cycle_started_at,
        cycle_completed_at=continuity.cycle_completed_at,
        phase_entered_at=continuity.phase_entered_at,
        operating_health=continuity.operating_health,
        health_details_json=continuity.health_details_json,
        contradiction_count=continuity.contradiction_count,
        contradictions_json=continuity.contradictions_json,
        lessons_learned=continuity.lessons_learned,
        patterns_updated=continuity.patterns_updated,
        calibration_improvements=continuity.calibration_improvements,
        epistemic_summary_json=continuity.epistemic_summary_json,
        fingerprint=continuity.fingerprint,
        version=continuity.version,
    )


@router.get("/cycles/{cycle_number}", response_model=ContinuityCycleResponse)
async def get_cycle_by_number(
    cycle_number: int,
    user: User = Depends(require_permission("canonical_continuity:cycles:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific continuity cycle by number."""
    
    continuity = await canonical_company_continuity_service.get_continuity_by_cycle(
        db, org.id, cycle_number
    )
    if not continuity:
        raise HTTPException(status_code=404, detail="Continuity cycle not found")
    
    return ContinuityCycleResponse(
        id=continuity.id,
        organization_id=continuity.organization_id,
        cycle_number=continuity.cycle_number,
        cycle_label=continuity.cycle_label,
        current_phase=continuity.current_phase,
        cycle_started_at=continuity.cycle_started_at,
        cycle_completed_at=continuity.cycle_completed_at,
        phase_entered_at=continuity.phase_entered_at,
        operating_health=continuity.operating_health,
        health_details_json=continuity.health_details_json,
        contradiction_count=continuity.contradiction_count,
        contradictions_json=continuity.contradictions_json,
        lessons_learned=continuity.lessons_learned,
        patterns_updated=continuity.patterns_updated,
        calibration_improvements=continuity.calibration_improvements,
        epistemic_summary_json=continuity.epistemic_summary_json,
        fingerprint=continuity.fingerprint,
        version=continuity.version,
    )


@router.post("/cycles/{cycle_id}/advance", response_model=ContinuityCycleResponse)
async def advance_cycle_phase(
    cycle_id: str,
    request: PhaseAdvanceRequest,
    user: User = Depends(require_permission("canonical_continuity:cycles:write")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Advance the continuity cycle to a new phase."""
    
    continuity = await db.get(CompanyOperatingContinuity, cycle_id)
    if not continuity or continuity.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Continuity cycle not found")
    
    continuity = await canonical_company_continuity_service.advance_phase(
        db,
        continuity,
        request.phase,
        actor_id=request.actor_id or user.id,
        actor_type=request.actor_type,
        source_event_ids=request.source_event_ids,
    )
    await db.commit()
    
    return ContinuityCycleResponse(
        id=continuity.id,
        organization_id=continuity.organization_id,
        cycle_number=continuity.cycle_number,
        cycle_label=continuity.cycle_label,
        current_phase=continuity.current_phase,
        cycle_started_at=continuity.cycle_started_at,
        cycle_completed_at=continuity.cycle_completed_at,
        phase_entered_at=continuity.phase_entered_at,
        operating_health=continuity.operating_health,
        health_details_json=continuity.health_details_json,
        contradiction_count=continuity.contradiction_count,
        contradictions_json=continuity.contradictions_json,
        lessons_learned=continuity.lessons_learned,
        patterns_updated=continuity.patterns_updated,
        calibration_improvements=continuity.calibration_improvements,
        epistemic_summary_json=continuity.epistemic_summary_json,
        fingerprint=continuity.fingerprint,
        version=continuity.version,
    )


@router.post("/cycles/{cycle_id}/complete", response_model=ContinuityCycleResponse)
async def complete_cycle(
    cycle_id: str,
    user: User = Depends(require_permission("canonical_continuity:cycles:write")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Complete the current operating cycle."""
    
    continuity = await db.get(CompanyOperatingContinuity, cycle_id)
    if not continuity or continuity.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Continuity cycle not found")
    
    continuity = await canonical_company_continuity_service.complete_cycle(
        db, continuity, actor_id=user.id
    )
    await db.commit()
    
    return ContinuityCycleResponse(
        id=continuity.id,
        organization_id=continuity.organization_id,
        cycle_number=continuity.cycle_number,
        cycle_label=continuity.cycle_label,
        current_phase=continuity.current_phase,
        cycle_started_at=continuity.cycle_started_at,
        cycle_completed_at=continuity.cycle_completed_at,
        phase_entered_at=continuity.phase_entered_at,
        operating_health=continuity.operating_health,
        health_details_json=continuity.health_details_json,
        contradiction_count=continuity.contradiction_count,
        contradictions_json=continuity.contradictions_json,
        lessons_learned=continuity.lessons_learned,
        patterns_updated=continuity.patterns_updated,
        calibration_improvements=continuity.calibration_improvements,
        epistemic_summary_json=continuity.epistemic_summary_json,
        fingerprint=continuity.fingerprint,
        version=continuity.version,
    )


# =============================================================================
# Continuity Events
# =============================================================================

@router.post("/events/record", response_model=ContinuityEventResponse, status_code=201)
async def record_continuity_event(
    request: ContinuityEventRecordRequest,
    user: User = Depends(require_permission("canonical_continuity:events:write")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Record a continuity event in the current cycle."""
    
    event = await canonical_company_continuity_service.record_event(
        db=db,
        organization_id=org.id,
        event_type=request.event_type,
        loop_phase=request.loop_phase,
        title=request.title,
        description=request.description,
        actor_id=request.actor_id or user.id,
        actor_type=request.actor_type,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        source_event_ids=request.source_event_ids,
        related_entities=request.related_entities,
        epistemic_state=request.epistemic_state,
        governance_scope_id=request.governance_scope_id,
    )
    await db.commit()
    
    return ContinuityEventResponse(
        id=event.id,
        organization_id=event.organization_id,
        continuity_cycle_id=event.continuity_cycle_id,
        event_type=event.event_type,
        loop_phase=event.loop_phase,
        occurred_at=event.occurred_at,
        sequence_in_phase=event.sequence_in_phase,
        actor_id=event.actor_id,
        actor_type=event.actor_type,
        title=event.title,
        description=event.description,
        details_json=event.details_json,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        related_entities_json=event.related_entities_json,
        epistemic_state=event.epistemic_state,
        evidence_fingerprints=event.evidence_fingerprints,
        source_event_ids=event.source_event_ids,
        governance_scope_id=event.governance_scope_id,
        fingerprint=event.fingerprint,
        version=event.version,
    )


@router.get("/events", response_model=List[ContinuityEventResponse])
async def list_continuity_events(
    cycle_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    loop_phase: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("canonical_continuity:events:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List continuity events with filtering."""
    
    events = await canonical_company_continuity_service.get_continuity_events(
        db=db,
        organization_id=org.id,
        continuity_cycle_id=cycle_id,
        event_type=event_type,
        loop_phase=loop_phase,
        limit=limit,
        offset=offset,
    )
    
    return [
        ContinuityEventResponse(
            id=e.id,
            organization_id=e.organization_id,
            continuity_cycle_id=e.continuity_cycle_id,
            event_type=e.event_type,
            loop_phase=e.loop_phase,
            occurred_at=e.occurred_at,
            sequence_in_phase=e.sequence_in_phase,
            actor_id=e.actor_id,
            actor_type=e.actor_type,
            title=e.title,
            description=e.description,
            details_json=e.details_json,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            related_entities_json=e.related_entities_json,
            epistemic_state=e.epistemic_state,
            evidence_fingerprints=e.evidence_fingerprints,
            source_event_ids=e.source_event_ids,
            governance_scope_id=e.governance_scope_id,
            fingerprint=e.fingerprint,
            version=e.version,
        )
        for e in events
    ]


# =============================================================================
# Universal Company Context
# =============================================================================

@router.get("/context", response_model=UniversalContextResponse)
async def get_universal_context(
    user: User = Depends(require_permission("canonical_continuity:context:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get the universal governed company context for the current user."""
    
    context = await canonical_company_continuity_service.get_universal_context(
        db, org.id, user.id
    )
    if not context:
        # Build it if not exists
        context = await canonical_company_continuity_service.build_universal_context(
            db, org.id, user.id
        )
        await db.commit()
    
    return UniversalContextResponse(
        id=context.id,
        organization_id=context.organization_id,
        caller_user_id=context.caller_user_id,
        org_wide=context.org_wide,
        scope_type=context.scope_type,
        scope_id=context.scope_id,
        computed_at=context.computed_at,
        context_version=context.context_version,
        epistemic_breakdown_json=context.epistemic_breakdown_json,
        fingerprint=context.fingerprint,
        version=context.version,
    )


@router.post("/context/refresh", response_model=UniversalContextResponse)
async def refresh_universal_context(
    user: User = Depends(require_permission("canonical_continuity:context:write")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Refresh the universal company context for the current user."""
    
    context = await canonical_company_continuity_service.build_universal_context(
        db, org.id, user.id
    )
    await db.commit()
    
    return UniversalContextResponse(
        id=context.id,
        organization_id=context.organization_id,
        caller_user_id=context.caller_user_id,
        org_wide=context.org_wide,
        scope_type=context.scope_type,
        scope_id=context.scope_id,
        computed_at=context.computed_at,
        context_version=context.context_version,
        epistemic_breakdown_json=context.epistemic_breakdown_json,
        fingerprint=context.fingerprint,
        version=context.version,
    )


# =============================================================================
# Cross-Domain Consistency Checks
# =============================================================================

@router.post("/consistency/run", response_model=List[ConsistencyCheckResponse])
async def run_consistency_checks(
    user: User = Depends(require_permission("canonical_continuity:consistency:write")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Run all cross-domain consistency checks."""
    
    results = await canonical_company_continuity_service.run_all_consistency_checks(
        db, org.id
    )
    await db.commit()
    
    return [
        ConsistencyCheckResponse(
            id=c.id,
            organization_id=c.organization_id,
            check_type=c.check_type,
            checked_at=c.checked_at,
            status=c.status,
            contradiction_count=c.contradiction_count,
            contradictions_json=c.contradictions_json,
            affected_entities_json=c.affected_entities_json,
            acknowledged=c.acknowledged,
            acknowledged_by=c.acknowledged_by,
            acknowledged_at=c.acknowledged_at,
            resolution_note=c.resolution_note,
            fingerprint=c.fingerprint,
            version=c.version,
        )
        for c in results
    ]


@router.get("/consistency/checks", response_model=List[ConsistencyCheckResponse])
async def list_consistency_checks(
    check_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("canonical_continuity:consistency:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List consistency checks with filtering."""
    
    query = select(CrossDomainConsistencyCheck).where(
        CrossDomainConsistencyCheck.organization_id == org.id
    )
    
    if check_type:
        query = query.where(CrossDomainConsistencyCheck.check_type == check_type)
    if status:
        query = query.where(CrossDomainConsistencyCheck.status == status)
    
    query = query.order_by(CrossDomainConsistencyCheck.checked_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    checks = result.scalars().all()
    
    return [
        ConsistencyCheckResponse(
            id=c.id,
            organization_id=c.organization_id,
            check_type=c.check_type,
            checked_at=c.checked_at,
            status=c.status,
            contradiction_count=c.contradiction_count,
            contradictions_json=c.contradictions_json,
            affected_entities_json=c.affected_entities_json,
            acknowledged=c.acknowledged,
            acknowledged_by=c.acknowledged_by,
            acknowledged_at=c.acknowledged_at,
            resolution_note=c.resolution_note,
            fingerprint=c.fingerprint,
            version=c.version,
        )
        for c in checks
    ]


@router.post("/consistency/checks/{check_id}/acknowledge", response_model=ConsistencyCheckResponse)
async def acknowledge_consistency_check(
    check_id: str,
    request: ConsistencyCheckAcknowledgeRequest,
    user: User = Depends(require_permission("canonical_continuity:consistency:write")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge a consistency check contradiction."""
    
    check = await db.get(CrossDomainConsistencyCheck, check_id)
    if not check or check.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Consistency check not found")
    
    check.acknowledged = True
    check.acknowledged_by = request.acknowledged_by
    check.acknowledged_at = utcnow()
    check.resolution_note = request.resolution_note
    check.version += 1
    
    await db.commit()
    
    return ConsistencyCheckResponse(
        id=check.id,
        organization_id=check.organization_id,
        check_type=check.check_type,
        checked_at=check.checked_at,
        status=check.status,
        contradiction_count=check.contradiction_count,
        contradictions_json=check.contradictions_json,
        affected_entities_json=check.affected_entities_json,
        acknowledged=check.acknowledged,
        acknowledged_by=check.acknowledged_by,
        acknowledged_at=check.acknowledged_at,
        resolution_note=check.resolution_note,
        fingerprint=check.fingerprint,
        version=check.version,
    )


# =============================================================================
# Operating Health
# =============================================================================

@router.get("/health", response_model=OperatingHealthResponse)
async def get_operating_health(
    user: User = Depends(require_permission("canonical_continuity:health:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get the current company operating health assessment."""
    
    health = await canonical_company_continuity_service.assess_operating_health(db, org.id)
    if not health:
        raise HTTPException(status_code=404, detail="No operating health available")
    
    return OperatingHealthResponse(
        id=health.id,
        organization_id=health.organization_id,
        overall_state=health.overall_state,
        assessed_at=health.assessed_at,
        domain_health_json=health.domain_health_json,
        unresolved_contradictions=health.unresolved_contradictions,
        missing_responsibility=health.missing_responsibility,
        stale_state_count=health.stale_state_count,
        failed_executions=health.failed_executions,
        unknown_outcomes=health.unknown_outcomes,
        prediction_divergence_count=health.prediction_divergence_count,
        twin_divergence_count=health.twin_divergence_count,
        blocked_operations=health.blocked_operations,
        governance_issues=health.governance_issues,
        integration_failures=health.integration_failures,
        learning_gaps=health.learning_gaps,
        details_json=health.details_json,
        fingerprint=health.fingerprint,
        version=health.version,
    )


@router.post("/health/refresh", response_model=OperatingHealthResponse)
async def refresh_operating_health(
    user: User = Depends(require_permission("canonical_continuity:health:write")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Refresh the operating health assessment."""
    
    health = await canonical_company_continuity_service.assess_operating_health(db, org.id)
    await db.commit()
    
    return OperatingHealthResponse(
        id=health.id,
        organization_id=health.organization_id,
        overall_state=health.overall_state,
        assessed_at=health.assessed_at,
        domain_health_json=health.domain_health_json,
        unresolved_contradictions=health.unresolved_contradictions,
        missing_responsibility=health.missing_responsibility,
        stale_state_count=health.stale_state_count,
        failed_executions=health.failed_executions,
        unknown_outcomes=health.unknown_outcomes,
        prediction_divergence_count=health.prediction_divergence_count,
        twin_divergence_count=health.twin_divergence_count,
        blocked_operations=health.blocked_operations,
        governance_issues=health.governance_issues,
        integration_failures=health.integration_failures,
        learning_gaps=health.learning_gaps,
        details_json=health.details_json,
        fingerprint=health.fingerprint,
        version=health.version,
    )


# =============================================================================
# Universal Company Timeline
# =============================================================================

@router.get("/timeline", response_model=List[TimelineEntryResponse])
async def get_universal_timeline(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = None,
    loop_phase: Optional[str] = Query(None),
    days_back: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(require_permission("canonical_continuity:timeline:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get the universal company timeline."""
    
    entries = await canonical_company_continuity_service.build_universal_timeline(
        db=db,
        organization_id=org.id,
        entity_type=entity_type,
        entity_id=entity_id,
        loop_phase=loop_phase,
        days_back=days_back,
        limit=limit,
    )
    
    return [
        TimelineEntryResponse(
            id=e.id,
            organization_id=e.organization_id,
            event_type=e.event_type,
            loop_phase=e.loop_phase,
            occurred_at=e.occurred_at,
            title=e.title,
            description=e.description,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            actor_id=e.actor_id,
            actor_type=e.actor_type,
            scope_type=e.scope_type,
            scope_id=e.scope_id,
            related_events_json=e.related_events_json,
            continuity_cycle_id=e.continuity_cycle_id,
            epistemic_state=e.epistemic_state,
            evidence_fingerprints=e.evidence_fingerprints,
            visible_to_org_wide=e.visible_to_org_wide,
            visible_scope_ids_json=e.visible_scope_ids_json,
            fingerprint=e.fingerprint,
            version=e.version,
        )
        for e in entries
    ]


# =============================================================================
# Self-Compounding Loop
# =============================================================================

@router.post("/compounding-loop/run", response_model=CompoundingLoopResponse)
async def run_compounding_loop(
    request: CompoundingLoopRunRequest,
    user: User = Depends(require_permission("canonical_continuity:compounding:write")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Run one complete self-compounding loop cycle."""
    
    loop = await canonical_company_continuity_service.run_compounding_loop(
        db, org.id, trigger=request.trigger
    )
    await db.commit()
    
    return CompoundingLoopResponse(
        id=loop.id,
        organization_id=loop.organization_id,
        cycle_number=loop.cycle_number,
        current_phase=loop.current_phase,
        cycle_started_at=loop.cycle_started_at,
        cycle_completed_at=loop.cycle_completed_at,
        phase_entered_at=loop.phase_entered_at,
        loop_duration_ms=loop.loop_duration_ms,
        phases_completed=loop.phases_completed,
        calibration_delta=loop.calibration_delta,
        learning_accumulated=loop.learning_accumulated,
        fingerprint=loop.fingerprint,
        version=loop.version,
    )


@router.get("/compounding-loop/history", response_model=List[CompoundingLoopResponse])
async def get_compounding_loop_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("canonical_continuity:compounding:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get self-compounding loop history."""
    
    result = await db.execute(
        select(SelfCompoundingLoopState)
        .where(SelfCompoundingLoopState.organization_id == org.id)
        .order_by(SelfCompoundingLoopState.cycle_number.desc())
        .limit(limit)
        .offset(offset)
    )
    loops = result.scalars().all()
    
    return [
        CompoundingLoopResponse(
            id=l.id,
            organization_id=l.organization_id,
            cycle_number=l.cycle_number,
            current_phase=l.current_phase,
            cycle_started_at=l.cycle_started_at,
            cycle_completed_at=l.cycle_completed_at,
            phase_entered_at=l.phase_entered_at,
            loop_duration_ms=l.loop_duration_ms,
            phases_completed=l.phases_completed,
            calibration_delta=l.calibration_delta,
            learning_accumulated=l.learning_accumulated,
            fingerprint=l.fingerprint,
            version=l.version,
        )
        for l in loops
    ]


# =============================================================================
# State Snapshots
# =============================================================================

@router.get("/state/{dimension}", response_model=Dict[str, Any])
async def get_state_snapshot(
    dimension: str,
    user: User = Depends(require_permission("canonical_continuity:state:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest state snapshot for a dimension."""
    
    if dimension not in COMPANY_STATE_DIMENSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid dimension: {dimension}")
    
    snapshot = await canonical_company_continuity_service.get_latest_state_snapshot(
        db, org.id, dimension
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="State snapshot not found")
    
    return {
        "id": snapshot.id,
        "organization_id": snapshot.organization_id,
        "dimension": snapshot.dimension,
        "captured_at": snapshot.captured_at,
        "valid_from": snapshot.valid_from,
        "valid_to": snapshot.valid_to,
        "state_json": snapshot.state_json,
        "source_events_json": snapshot.source_events_json,
        "computation_duration_ms": snapshot.computation_duration_ms,
        "version": snapshot.version,
        "fingerprint": snapshot.fingerprint,
        "epistemic_composition_json": snapshot.epistemic_composition_json,
    }


# =============================================================================
# Vocabularies
# =============================================================================

@router.get("/vocabularies/phases")
async def get_loop_phases():
    """Get all company operating loop phases."""
    return {"phases": list(COMPANY_LOOP_PHASES)}


@router.get("/vocabularies/event-types")
async def get_event_types():
    """Get all continuity event types."""
    return {"event_types": list(CONTINUITY_EVENT_TYPES)}


@router.get("/vocabularies/epistemic-states")
async def get_epistemic_states():
    """Get all epistemic states."""
    return {"epistemic_states": list(EPISTEMIC_STATES)}


@router.get("/vocabularies/health-states")
async def get_health_states():
    """Get all operating health states."""
    return {"health_states": list(OPERATING_HEALTH_STATES)}


@router.get("/vocabularies/consistency-checks")
async def get_consistency_checks():
    """Get all consistency check types."""
    return {"consistency_checks": list(CONSISTENCY_CHECK_TYPES)}


@router.get("/vocabularies/dimensions")
async def get_state_dimensions():
    """Get all company state dimensions."""
    return {"dimensions": list(COMPANY_STATE_DIMENSIONS)}