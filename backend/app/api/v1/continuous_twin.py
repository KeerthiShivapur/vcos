"""Continuous Digital Twin, Optimization & Self-Learning API — Gate 29.

This module provides the REST API for the continuous digital twin,
optimization, and self-learning fabric (Gate 29).
"""

from datetime import datetime
from typing import Any, Optional, List, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.autonomy import AutonomyEvent, AutonomyExecution, AutonomyProposal
from app.models.continuous_twin import (
    CompanyStateSnapshot,
    CompanyStateDimension,
    TwinStateSnapshot,
    TwinSynchronizationLog,
    PredictionCalibration,
    OptimizationContext,
    OptimizationAlternative,
    LearningSignal,
    ContinuousLearningSession,
    InstitutionalMemoryEntry,
    CompanyAttention,
    ModelTwinDrift,
    TwinScope,
    TwinContext,
    ContinuousStateProjection,
    CompanyStateSnapshot,
    CompanyStateDimension,
    TwinStateSnapshot,
    TwinSynchronizationLog,
    PredictionCalibration,
    OptimizationContext,
    OptimizationAlternative,
    LearningSignal,
    ContinuousLearningSession,
    InstitutionalMemoryEntry,
    CompanyAttention,
    ModelTwinDrift,
    TwinScope,
    TwinContext,
    ContinuousStateProjection,
    COMPANY_STATE_DIMENSIONS,
    TWIN_SYNC_STATES,
    CALIBRATION_STATES,
    OPTIMIZATION_STATES,
    DRIFT_SEVERITY,
    LEARNING_SIGNAL_TYPES,
    ATTENTION_PRIORITY,
    TWIN_SCOPE_TYPES,
    DRIFT_TYPES,
)
from app.services.continuous_twin_service import continuous_twin_service

router = APIRouter(prefix="/continuous-twin", tags=["Continuous Digital Twin"])


# =============================================================================
# Request/Response Models
# =============================================================================

class CompanyStateSnapshotResponse(BaseModel):
    id: str
    organization_id: str
    dimension: str
    captured_at: datetime
    valid_from: datetime
    valid_to: Optional[datetime] = None
    state_json: Optional[str] = None
    source_events_json: Optional[str] = None
    computation_duration_ms: int
    version: int
    fingerprint: str


class CompanyStateDimensionResponse(BaseModel):
    id: str
    organization_id: str
    dimension: str
    current_state_json: Optional[str] = None
    last_updated_at: datetime
    composition_rules_json: Optional[str] = None
    source_tables_json: Optional[str] = None
    update_trigger: str
    update_frequency_seconds: int
    last_computed_at: Optional[datetime] = None
    is_healthy: bool
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    version: int


class CompanyStateResponse(BaseModel):
    organization_id: str
    captured_at: str
    state: Dict[str, Any]


class TwinStateSnapshotResponse(BaseModel):
    id: str
    organization_id: str
    scope_type: str
    scope_id: Optional[str] = None
    captured_at: datetime
    twin_state: str
    current_state_json: Optional[str] = None
    predicted_state_json: Optional[str] = None
    counterfactual_states_json: Optional[str] = None
    twin_state: str
    last_synced_at: Optional[datetime] = None
    sync_source: str
    sync_duration_ms: int
    sync_errors_json: Optional[str] = None
    drift_detected: bool
    drift_severity: str
    drift_details_json: Optional[str] = None
    drift_detected_at: Optional[datetime] = None
    computed_at: datetime
    computation_duration_ms: int
    fingerprint: str
    version: int


class TwinSynchronizationLogResponse(BaseModel):
    id: str
    organization_id: str
    scope_type: str
    scope_id: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: int
    status: str
    entities_synced: int
    entities_failed: int
    drift_detected: bool
    drift_severity: str
    drift_details_json: Optional[str] = None
    sync_source: str
    entities_synced_json: Optional[str] = None
    errors_json: Optional[str] = None
    version: int


class SynchronizeTwinRequest(BaseModel):
    scope_type: str = Field("org", pattern="^(org|department|team|project|person)$")
    scope_id: Optional[str] = None
    triggered_by: Optional[str] = None


class TwinSynchronizationLogResponse(BaseModel):
    id: str
    organization_id: str
    scope_type: str
    scope_id: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: int
    status: str
    entities_synced: int
    entities_failed: int
    drift_detected: bool
    drift_severity: str
    drift_details_json: Optional[str] = None
    sync_source: str
    entities_synced_json: Optional[str] = None
    errors_json: Optional[str] = None
    version: int


class PredictionCalibrationResponse(BaseModel):
    id: str
    organization_id: str
    prediction_kind: str
    model_version: str
    status: str
    total_predictions: int
    correct_predictions: int
    accuracy: float
    brier_score: Optional[float] = None
    log_loss: Optional[float] = None
    calibration_curve_json: Optional[str] = None
    expected_confidence: float
    observed_accuracy: float
    calibration_error: float
    bucket_calibration_json: Optional[str] = None
    evaluation_window_days: int
    evaluated_predictions_count: int
    last_evaluated_at: Optional[datetime] = None
    next_evaluation_at: Optional[datetime] = None
    status_details_json: Optional[str] = None
    last_calibrated_at: Optional[datetime] = None
    version: int


class CalibratePredictionsRequest(BaseModel):
    prediction_kind: Optional[str] = None
    evaluation_window_days: int = Field(30, ge=1, le=365)


class CalibratePredictionsResponse(BaseModel):
    calibrations: List[PredictionCalibrationResponse]


class OptimizationContextResponse(BaseModel):
    id: str
    organization_id: str
    objective: str
    objective_type: str
    objective_json: Optional[Dict] = None
    constraints_json: Optional[Dict] = None
    hard_constraints_json: Optional[Dict] = None
    soft_constraints_json: Optional[Dict] = None
    variables_json: Optional[Dict] = None
    scope_type: str
    scope_id: Optional[str] = None
    status: str
    best_solution_json: Optional[Dict] = None
    best_objective_value: Optional[float] = None
    created_by: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    version: int


class OptimizationContextCreate(BaseModel):
    objective: str
    objective_type: str = Field("maximize", pattern="^(maximize|minimize|target)$")
    objective_json: Optional[Dict] = None
    constraints: Optional[List[Dict]] = None
    hard_constraints: Optional[List[Dict]] = None
    soft_constraints: Optional[List[Dict]] = None
    variables: Optional[Dict] = None
    scope_type: str = Field("org", pattern="^(org|department|team|project)$")
    scope_id: Optional[str] = None
    created_by: Optional[str] = None


class OptimizationAlternativeResponse(BaseModel):
    id: str
    context_id: str
    rank: int
    solution_json: Dict
    objective_value: float
    hard_constraints_satisfied: bool
    violated_constraints_json: Optional[Dict] = None
    tradeoffs_json: Optional[Dict] = None
    objective_values_json: Optional[Dict] = None
    is_feasible: bool
    feasibility_score: float
    generated_at: datetime
    version: int


class RunOptimizationRequest(BaseModel):
    objective: str
    objective_type: str = Field("maximize", pattern="^(maximize|minimize|target)$")
    objective_json: Optional[Dict] = None
    constraints: Optional[List[Dict]] = None
    hard_constraints: Optional[List[Dict]] = None
    soft_constraints: Optional[List[Dict]] = None
    variables: Optional[Dict] = None
    scope_type: str = Field("org", pattern="^(org|department|team|project)$")
    scope_id: Optional[str] = None


class CalibratePredictionsRequest(BaseModel):
    prediction_kind: Optional[str] = None
    evaluation_window_days: int = Field(30, ge=1, le=365)


class CalibratePredictionsResponse(BaseModel):
    calibrations: List[Dict]


class LearningSignalResponse(BaseModel):
    id: str
    organization_id: str
    signal_type: str
    priority: str
    source_type: str
    source_id: Optional[str] = None
    source_event_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    details_json: Optional[Dict] = None
    evidence_json: Optional[Dict] = None
    confidence: float
    expected_lesson_type: Optional[str] = None
    applicable_contexts_json: Optional[Dict] = None
    status: str
    lesson_id: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    version: int


class ProcessLearningSignalsResponse(BaseModel):
    processed: List[LearningSignalResponse]


class LearningSignalAcknowledgeRequest(BaseModel):
    acknowledged_by: str


class ContinuousLearningSessionResponse(BaseModel):
    id: str
    organization_id: str
    session_type: str
    scope_type: str
    scope_id: Optional[str] = None
    status: str
    signals_processed: int
    lessons_generated: int
    lessons_validated: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: int
    error: Optional[str] = None


class RunLearningSessionRequest(BaseModel):
    session_type: str = Field("incremental", pattern="^(batch|incremental|triggered|continuous)$")
    scope_type: str = Field("org", pattern="^(org|department|team|project)$")
    scope_id: Optional[str] = None


class RunLearningSessionResponse(BaseModel):
    session: ContinuousLearningSessionResponse


class InstitutionalMemoryEntryResponse(BaseModel):
    id: str
    organization_id: str
    kind: str
    fingerprint: str
    title: str
    summary: Optional[str] = None
    content_json: Dict
    source_type: str
    source_id: Optional[str] = None
    source_event_id: Optional[str] = None
    confidence: float
    evidence_fingerprints: List[str]
    supporting_events_json: Optional[str] = None
    status: str
    supersedes_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    applicable_contexts_json: Optional[Dict] = None
    conditions_json: Optional[Dict] = None
    confidence: float
    evidence_fingerprints: List[str]
    validated: bool
    validated_by: Optional[str] = None
    validated_at: Optional[datetime] = None
    access_count: int
    last_accessed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    version: int


class InstitutionalMemoryEntryCreate(BaseModel):
    kind: str = Field(..., pattern="^(pattern|lesson|decision_precedent|prediction_calibration|optimization_result|risk_precedent)$")
    fingerprint: str
    title: str
    summary: Optional[str] = None
    content_json: Dict
    source_type: str
    source_id: Optional[str] = None
    source_event_id: Optional[str] = None
    confidence: float = Field(0.5, ge=0, le=1)
    evidence_fingerprints: Optional[List[str]] = None
    applicable_contexts: Optional[List[Dict]] = None
    conditions: Optional[List[str]] = None


class InstitutionalMemoryEntryUpdate(BaseModel):
    content_json: Optional[Dict] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)
    evidence_fingerprints: Optional[List[str]] = None
    applicable_contexts: Optional[List[Dict]] = None
    conditions: Optional[List[str]] = None
    status: Optional[str] = None
    supersedes_id: Optional[str] = None
    superseded_by_id: Optional[str] = None


class CompanyAttentionResponse(BaseModel):
    id: str
    organization_id: str
    attention_type: str
    priority: str
    title: str
    description: Optional[str] = None
    details_json: Optional[Dict] = None
    source_type: str
    source_id: Optional[str] = None
    source_event_id: Optional[str] = None
    priority_score: float
    urgency: str
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    assigned_by: Optional[str] = None
    status: str
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None
    escalated: bool
    escalated_at: Optional[datetime] = None
    escalated_to: Optional[str] = None
    escalation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    version: int


class CompanyAttentionCreate(BaseModel):
    attention_type: str = Field(..., pattern="^(prediction_divergence|twin_divergence|capacity_bottleneck|risk_emergence|optimization_opportunity|capacity_bottleneck|risk_emergence)$")
    priority: str = Field("info", pattern="^(info|watch|alert|critical)$")
    title: str
    description: Optional[str] = None
    details_json: Optional[Dict] = None
    source_type: str = "system"
    source_id: Optional[str] = None
    source_event_id: Optional[str] = None
    assigned_to: Optional[str] = None
    urgency: str = "normal"


class CompanyAttentionResolve(BaseModel):
    resolution_note: Optional[str] = None


class ModelTwinDriftResponse(BaseModel):
    id: str
    organization_id: str
    proposal_id: Optional[str] = None
    drift_type: str
    severity: str
    subject_type: str
    subject_id: str
    title: str
    description: Optional[str] = None
    root_cause: Optional[str] = None
    causal_chain: List[Dict]
    probability: float
    impact_score: float
    financial_exposure_cents: Optional[int] = None
    currency: str
    epistemic_status: str
    evidence_fingerprints: List[str]
    signal_ids: List[str]
    prediction_ids: List[str]
    counterfactual_ids: List[str]
    mitigation_actions: List[str]
    owner_person_id: Optional[str] = None
    target_resolution_date: Optional[datetime] = None
    state: str
    supersedes_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    fingerprint: str
    version: int


class DriftDetectRequest(BaseModel):
    drift_type: str = Field(..., pattern="^(prediction_divergence|twin_reality_gap|state_staleness|policy_violation|constraint_violation|capacity_exceeded|external_divergence)$")
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    subject_type: str
    subject_id: str
    expected: Optional[Dict] = None
    observed: Optional[Dict] = None
    deviation_score: float = Field(0.0, ge=0, le=1)
    severity_score: float = Field(0.0, ge=0, le=1)
    evidence: Optional[Dict] = None


class DriftResolveRequest(BaseModel):
    resolved_by: str
    resolution_note: Optional[str] = None


class TwinScopeResponse(BaseModel):
    id: str
    organization_id: str
    scope_type: str
    scope_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    is_default: bool
    access_level: str
    allowed_departments: List[str]
    allowed_teams: List[str]
    created_at: datetime
    updated_at: datetime
    version: int


class TwinScopeCreate(BaseModel):
    scope_type: str = Field(..., pattern="^(org|department|team|project|person)$")
    scope_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    layout_json: Optional[Dict] = None
    background_url: Optional[str] = None
    is_default: bool = False
    capacity: int = Field(50, ge=1, le=10000)
    access_level: str = Field("all", pattern="^(all|department|team|invite_only)$")
    allowed_departments: List[str] = []
    allowed_teams: List[str] = []


class TwinScopeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    layout_json: Optional[Dict] = None
    background_url: Optional[str] = None
    is_default: Optional[bool] = None
    capacity: Optional[int] = None
    access_level: Optional[str] = None
    allowed_departments: Optional[List[str]] = None
    allowed_teams: Optional[List[str]] = None


class TwinContextResponse(BaseModel):
    id: str
    floor_id: str
    name: str
    description: Optional[str] = None
    room_type: str
    capacity: int
    icon: str
    color: str
    requires_booking: bool
    auto_release_minutes: int
    has_screen: bool
    has_whiteboard: bool
    has_video_conf: bool


class TwinContextCreate(BaseModel):
    floor_id: str
    name: str
    description: Optional[str] = None
    room_type: str = "meeting"
    capacity: int = 4
    icon: str = "meeting_room"
    color: str = "#3B82F6"
    requires_booking: bool = True
    auto_release_minutes: int = 15
    has_screen: bool = True
    has_whiteboard: bool = True
    has_video_conf: bool = True


class ContinuousStateProjectionResponse(BaseModel):
    id: str
    organization_id: str
    dimension: str
    current_state_json: Optional[Dict] = None
    current_state_hash: str
    last_event_id: Optional[str] = None
    last_event_at: Optional[datetime] = None
    events_processed: int
    last_refreshed_at: Optional[datetime] = None
    refresh_interval_seconds: int
    is_refreshing: bool
    is_healthy: bool
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    version: int


class UpdateStateProjectionRequest(BaseModel):
    dimension: str
    state_json: Dict
    event_id: Optional[str] = None


class CompanyStateResponse(BaseModel):
    organization_id: str
    captured_at: str
    state: Dict[str, Any]


class SynchronizeTwinRequest(BaseModel):
    scope_type: str = Field("org", pattern="^(org|department|team|project|person)$")
    scope_id: Optional[str] = None
    triggered_by: Optional[str] = None


class SynchronizeTwinResponse(BaseModel):
    log: TwinSynchronizationLogResponse


class CalibratePredictionsRequest(BaseModel):
    prediction_kind: Optional[str] = None
    evaluation_window_days: int = Field(30, ge=1, le=365)


class CalibratePredictionsResponse(BaseModel):
    calibrations: List[Dict]


class RunOptimizationRequest(BaseModel):
    objective: str
    objective_type: str = Field("maximize", pattern="^(maximize|minimize|target)$")
    objective_json: Optional[Dict] = None
    constraints: Optional[List[Dict]] = None
    hard_constraints: Optional[List[Dict]] = None
    soft_constraints: Optional[List[Dict]] = None
    variables: Optional[Dict] = None
    scope_type: str = Field("org", pattern="^(org|department|team|project)$")
    scope_id: Optional[str] = None
    created_by: Optional[str] = None


class RunOptimizationResponse(BaseModel):
    context: OptimizationContextResponse


class ProcessLearningSignalsRequest(BaseModel):
    limit: int = Field(100, ge=1, le=500)


class ProcessLearningSignalsResponse(BaseModel):
    processed: List[LearningSignalResponse]


class RunLearningSessionRequest(BaseModel):
    session_type: str = Field("incremental", pattern="^(batch|incremental|triggered|continuous)$")
    scope_type: str = Field("org", pattern="^(org|department|team|project)$")
    scope_id: Optional[str] = None


class RunLearningSessionResponse(BaseModel):
    session: ContinuousLearningSessionResponse


class RecordInstitutionalMemoryRequest(BaseModel):
    kind: str = Field(..., pattern="^(pattern|lesson|decision_precedent|prediction_calibration|optimization_result|risk_precedent)$")
    fingerprint: str
    title: str
    summary: Optional[str] = None
    content_json: Dict
    source_type: str
    source_id: Optional[str] = None
    source_event_id: Optional[str] = None
    confidence: float = Field(0.5, ge=0, le=1)
    evidence_fingerprints: Optional[List[str]] = None
    applicable_contexts: Optional[List[Dict]] = None
    conditions: Optional[List[str]] = None


class RecordInstitutionalMemoryResponse(BaseModel):
    entry: InstitutionalMemoryEntryResponse


class CreateAttentionRequest(BaseModel):
    attention_type: str = Field(..., pattern="^(prediction_divergence|twin_divergence|capacity_bottleneck|risk_emergence|optimization_opportunity|policy_violation|external_divergence)$")
    priority: str = Field("info", pattern="^(info|watch|alert|critical)$")
    title: str
    description: Optional[str] = None
    details_json: Optional[Dict] = None
    source_type: str = "system"
    source_id: Optional[str] = None
    source_event_id: Optional[str] = None
    assigned_to: Optional[str] = None
    urgency: str = "normal"


class MarkAttentionReadRequest(BaseModel):
    notification_id: str


class DriftDetectRequest(BaseModel):
    drift_type: str = Field(..., pattern="^(prediction_divergence|twin_reality_gap|state_staleness|policy_violation|constraint_violation|capacity_exceeded|external_divergence)$")
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    subject_type: str
    subject_id: str
    expected: Optional[Dict] = None
    observed: Optional[Dict] = None
    deviation_score: float = Field(0.0, ge=0, le=1)
    severity_score: float = Field(0.0, ge=0, le=1)
    evidence: Optional[Dict] = None


class DriftResolveRequest(BaseModel):
    resolved_by: str
    resolution_note: Optional[str] = None


class TwinScopeCreateRequest(BaseModel):
    scope_type: str = Field(..., pattern="^(org|department|team|project|person)$")
    scope_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    included_dimensions: Optional[List[str]] = None
    auto_refresh: bool = True
    refresh_interval_seconds: int = Field(300, ge=60, le=86400)


class TwinContextRequest(BaseModel):
    scope_id: str
    context_type: str = Field(..., pattern="^(company_state|project_state|team_state|capacity_state|financial_state|risk_state|policy_state)$")
    context_json: Dict
    input_fingerprint: str


class StateProjectionUpdateRequest(BaseModel):
    dimension: str
    state_json: Dict
    event_id: Optional[str] = None


class PredictionCalibrateRequest(BaseModel):
    prediction_kind: Optional[str] = None
    evaluation_window_days: int = Field(30, ge=1, le=365)


class OptimizeRequest(BaseModel):
    objective: str
    objective_type: str = Field("maximize", pattern="^(maximize|minimize|target)$")
    objective_json: Optional[Dict] = None
    constraints: Optional[List[Dict]] = None
    hard_constraints: Optional[List[Dict]] = None
    soft_constraints: Optional[List[Dict]] = None
    variables: Optional[Dict] = None
    scope_type: str = Field("org", pattern="^(org|department|team|project)$")
    scope_id: Optional[str] = None
    created_by: Optional[str] = None


class RecordLearningRequest(BaseModel):
    lesson_type: str = Field(..., pattern="^(success_pattern|failure_pattern|policy_gap|optimization)$")
    lesson_title: str
    lesson_summary: Optional[str] = None
    lesson_details: Optional[Dict] = None
    confidence: float = Field(0.5, ge=0, le=1)
    evidence_fingerprints: Optional[List[str]] = None
    applicable_proposal_types: Optional[List[str]] = None
    applicable_contexts: Optional[List[Dict]] = None


class RecordInstitutionalMemoryRequest(BaseModel):
    kind: str = Field(..., pattern="^(pattern|lesson|decision_precedent|prediction_calibration|optimization_result|risk_precedent)$")
    fingerprint: str
    title: str
    summary: Optional[str] = None
    content_json: Dict
    source_type: str
    source_id: Optional[str] = None
    source_event_id: Optional[str] = None
    confidence: float = Field(0.5, ge=0, le=1)
    evidence_fingerprints: Optional[List[str]] = None
    applicable_contexts: Optional[List[Dict]] = None
    conditions: Optional[List[str]] = None


class RecordAttentionRequest(BaseModel):
    attention_type: str = Field(..., pattern="^(prediction_divergence|twin_divergence|capacity_bottleneck|risk_emergence|optimization_opportunity|policy_violation|external_divergence)$")
    priority: str = Field("info", pattern="^(info|watch|alert|critical)$")
    title: str
    description: Optional[str] = None
    details_json: Optional[Dict] = None
    source_type: str = "system"
    source_id: Optional[str] = None
    source_event_id: Optional[str] = None
    assigned_to: Optional[str] = None
    urgency: str = "normal"


class MarkAttentionReadRequest(BaseModel):
    notification_id: str


class DriftDetectRequest(BaseModel):
    drift_type: str = Field(..., pattern="^(prediction_divergence|twin_reality_gap|state_staleness|policy_violation|constraint_violation|capacity_exceeded|external_divergence)$")
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    subject_type: str
    subject_id: str
    expected: Optional[Dict] = None
    observed: Optional[Dict] = None
    deviation_score: float = Field(0.0, ge=0, le=1)
    severity_score: float = Field(0.0, ge=0, le=1)
    evidence: Optional[Dict] = None


class DriftResolveRequest(BaseModel):
    resolved_by: str
    resolution_note: Optional[str] = None


class TwinScopeCreateRequest(BaseModel):
    scope_type: str = Field(..., pattern="^(org|department|team|project|person)$")
    scope_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    included_dimensions: Optional[List[str]] = None
    auto_refresh: bool = True
    refresh_interval_seconds: int = Field(300, ge=60, le=86400)


class TwinContextRequest(BaseModel):
    scope_id: str
    context_type: str = Field(..., pattern="^(company_state|project_state|team_state|capacity_state|financial_state|risk_state|policy_state)$")
    context_json: Dict
    input_fingerprint: str


class StateProjectionUpdateRequest(BaseModel):
    dimension: str
    state_json: Dict
    event_id: Optional[str] = None


class PredictionCalibrateRequest(BaseModel):
    prediction_kind: Optional[str] = None
    evaluation_window_days: int = Field(30, ge=1, le=365)


class OptimizeRequest(BaseModel):
    objective: str
    objective_type: str = Field("maximize", pattern="^(maximize|minimize|target)$")
    objective_json: Optional[Dict] = None
    constraints: Optional[List[Dict]] = None
    hard_constraints: Optional[List[Dict]] = None
    soft_constraints: Optional[List[Dict]] = None
    variables: Optional[Dict] = None
    scope_type: str = Field("org", pattern="^(org|department|team|project)$")
    scope_id: Optional[str] = None
    created_by: Optional[str] = None


class AutonomyEventResponse(BaseModel):
    id: str
    organization_id: str
    proposal_id: Optional[str] = None
    event_type: str
    title: str
    description: Optional[str] = None
    details_json: Optional[str] = None
    occurred_at: datetime
    actor_id: Optional[str] = None


class AutonomyExecutionResponse(BaseModel):
    id: str
    organization_id: str
    proposal_id: str
    state: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    result_json: Optional[str] = None
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
# Company State Endpoints
# =============================================================================

@router.get("/state", response_model=CompanyStateResponse)
async def get_company_state(
    dimensions: Optional[List[str]] = Query(None),
    as_of: Optional[datetime] = Query(None),
    user: User = Depends(require_permission("continuous_twin:state:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get the current continuous company state."""
    state = await continuous_twin_service.derive_company_state(
        db,
        organization_id=org.id,
        dimensions=dimensions,
        as_of=datetime.fromisoformat(as_of.isoformat()) if as_of else None,
    )
    return CompanyStateResponse(
        organization_id=org.id,
        captured_at=utcnow().isoformat(),
        state=state,
    )


@router.get("/state/snapshots", response_model=List[CompanyStateSnapshotResponse])
async def list_state_snapshots(
    dimension: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:state:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List company state snapshots."""
    query = select(CompanyStateSnapshot).where(CompanyStateSnapshot.organization_id == org.id)
    if dimension:
        query = query.where(CompanyStateSnapshot.dimension == dimension)
    query = query.order_by(CompanyStateSnapshot.captured_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    snapshots = result.scalars().all()
    return [CompanyStateSnapshotResponse.from_orm(s) for s in snapshots]


@router.get("/state/dimensions", response_model=List[CompanyStateDimensionResponse])
async def list_state_dimensions(
    user: User = Depends(require_permission("continuous_twin:state:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List all state dimensions."""
    result = await db.execute(
        select(CompanyStateDimension).where(CompanyStateDimension.organization_id == org.id)
    )
    dimensions = result.scalars().all()
    return [CompanyStateDimensionResponse.from_orm(d) for d in dimensions]


# =============================================================================
# Digital Twin Synchronization
# =============================================================================

@router.post("/twin/synchronize", response_model=SynchronizeTwinResponse)
async def synchronize_twin(
    request: SynchronizeTwinRequest,
    user: User = Depends(require_permission("continuous_twin:twin:synchronize")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Synchronize the digital twin with canonical reality."""
    log = await continuous_twin_service.synchronize_twin(
        db,
        organization_id=org.id,
        scope_type=request.scope_type,
        scope_id=request.scope_id,
        triggered_by=request.triggered_by or user.id,
    )
    await db.commit()
    return SynchronizeTwinResponse(log=log)


@router.get("/twin/sync/logs", response_model=List[TwinSynchronizationLogResponse])
async def list_sync_logs(
    scope_type: Optional[str] = Query(None),
    scope_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:twin:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List twin synchronization logs."""
    query = select(TwinSynchronizationLog).where(TwinSynchronizationLog.organization_id == org.id)
    if scope_type:
        query = query.where(TwinSynchronizationLog.scope_type == scope_type)
    if scope_id:
        query = query.where(TwinSynchronizationLog.scope_id == scope_id)
    if status:
        query = query.where(TwinSynchronizationLog.status == status)
    query = query.order_by(TwinSynchronizationLog.started_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    logs = result.scalars().all()
    return [TwinSynchronizationLogResponse.from_orm(l) for l in logs]


@router.get("/twin/state", response_model=TwinStateSnapshotResponse)
async def get_twin_state(
    scope_type: Optional[str] = Query("org"),
    scope_id: Optional[str] = None,
    user: User = Depends(require_permission("continuous_twin:twin:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get the current digital twin state snapshot."""
    query = select(TwinStateSnapshot).where(TwinStateSnapshot.organization_id == org.id)
    if scope_id:
        query = query.where(TwinStateSnapshot.scope_id == scope_id)
    query = query.order_by(TwinStateSnapshot.captured_at.desc()).limit(1)
    result = await db.execute(query)
    snapshot = result.scalars().first()
    if not snapshot:
        raise HTTPException(404, "No twin state snapshot found")
    return TwinStateSnapshotResponse.from_orm(snapshot)


@router.get("/twin/sync/logs", response_model=List[TwinSynchronizationLogResponse])
async def list_twin_sync_logs(
    scope_type: Optional[str] = Query(None),
    scope_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:twin:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List twin synchronization logs."""
    query = select(TwinSynchronizationLog).where(TwinSynchronizationLog.organization_id == org.id)
    if scope_type:
        query = query.where(TwinSynchronizationLog.scope_type == scope_type)
    if scope_id:
        query = query.where(TwinSynchronizationLog.scope_id == scope_id)
    if status:
        query = query.where(TwinSynchronizationLog.status == status)
    query = query.order_by(TwinSynchronizationLog.started_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    logs = result.scalars().all()
    return [TwinSynchronizationLogResponse.from_orm(l) for l in logs]


# =============================================================================
# Prediction Calibration
# =============================================================================

@router.post("/predictions/calibrate", response_model=CalibratePredictionsResponse)
async def calibrate_predictions(
    request: CalibratePredictionsRequest,
    user: User = Depends(require_permission("continuous_twin:predictions:calibrate")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Calibrate prediction models against actual outcomes."""
    calibrations = await continuous_twin_service.calibrate_predictions(
        db,
        organization_id=org.id,
        prediction_kind=request.prediction_kind,
        evaluation_window_days=request.evaluation_window_days,
    )
    await db.commit()
    return CalibratePredictionsResponse(calibrations=calibrations)


@router.get("/predictions/calibration", response_model=List[PredictionCalibrationResponse])
async def list_prediction_calibrations(
    prediction_kind: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:predictions:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List prediction calibrations."""
    query = select(PredictionCalibration).where(PredictionCalibration.organization_id == org.id)
    if prediction_kind:
        query = query.where(PredictionCalibration.prediction_kind == prediction_kind)
    if status:
        query = query.where(PredictionCalibration.status == status)
    query = query.order_by(PredictionCalibration.last_evaluated_at.desc().nullslast()).limit(limit).offset(offset)
    result = await db.execute(query)
    calibrations = result.scalars().all()
    return [PredictionCalibrationResponse.from_orm(c) for c in calibrations]


# =============================================================================
# Optimization
# =============================================================================

@router.post("/optimization/run", response_model=RunOptimizationResponse)
async def run_optimization(
    request: OptimizeRequest,
    user: User = Depends(require_permission("continuous_twin:optimization:run")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Run a constrained optimization over canonical reality."""
    context = await continuous_twin_service.run_optimization(
        db,
        organization_id=org.id,
        objective=request.objective,
        objective_type=request.objective_type,
        objective_json=request.objective_json,
        constraints=request.constraints,
        hard_constraints=request.hard_constraints,
        soft_constraints=request.soft_constraints,
        variables=request.variables,
        scope_type=request.scope_type,
        scope_id=request.scope_id,
        created_by=user.id,
    )
    await db.commit()
    return RunOptimizationResponse(context=context)


@router.get("/optimization/contexts", response_model=List[OptimizationContextResponse])
async def list_optimization_contexts(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:optimization:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List optimization contexts."""
    query = select(OptimizationContext).where(OptimizationContext.organization_id == org.id)
    if status:
        query = query.where(OptimizationContext.status == status)
    query = query.order_by(OptimizationContext.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    contexts = result.scalars().all()
    return [OptimizationContextResponse.from_orm(c) for c in contexts]


@router.get("/optimization/contexts/{context_id}", response_model=OptimizationContextResponse)
async def get_optimization_context(
    context_id: str,
    user: User = Depends(require_permission("continuous_twin:optimization:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get an optimization context by ID."""
    context = await db.get(OptimizationContext, context_id)
    if not context or context.organization_id != org.id:
        raise HTTPException(404, "Optimization context not found")
    return OptimizationContextResponse.from_orm(context)


@router.get("/optimization/contexts/{context_id}/alternatives", response_model=List[OptimizationAlternativeResponse])
async def list_optimization_alternatives(
    context_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:optimization:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List alternatives for an optimization context."""
    query = select(OptimizationAlternative).where(OptimizationAlternative.context_id == context_id)
    query = query.order_by(OptimizationAlternative.rank.asc()).limit(limit).offset(offset)
    result = await db.execute(query)
    alternatives = result.scalars().all()
    return [OptimizationAlternativeResponse.from_orm(a) for a in alternatives]


# =============================================================================
# Prediction Calibration
# =============================================================================

@router.post("/predictions/calibrate", response_model=CalibratePredictionsResponse)
async def calibrate_predictions(
    request: CalibratePredictionsRequest,
    user: User = Depends(require_permission("continuous_twin:predictions:calibrate")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Calibrate prediction models against actual outcomes."""
    calibrations = await continuous_twin_service.calibrate_predictions(
        db,
        organization_id=org.id,
        prediction_kind=request.prediction_kind,
        evaluation_window_days=request.evaluation_window_days,
    )
    await db.commit()
    return CalibratePredictionsResponse(calibrations=calibrations)


@router.get("/predictions/calibration", response_model=List[PredictionCalibrationResponse])
async def list_prediction_calibrations(
    prediction_kind: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:predictions:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List prediction calibrations."""
    query = select(PredictionCalibration).where(PredictionCalibration.organization_id == org.id)
    if prediction_kind:
        query = query.where(PredictionCalibration.prediction_kind == prediction_kind)
    if status:
        query = query.where(PredictionCalibration.status == status)
    query = query.order_by(PredictionCalibration.last_evaluated_at.desc().nullslast()).limit(limit).offset(offset)
    result = await db.execute(query)
    calibrations = result.scalars().all()
    return [PredictionCalibrationResponse.from_orm(c) for c in calibrations]


# =============================================================================
# Continuous Learning
# =============================================================================

@router.post("/learning/signals/process", response_model=ProcessLearningSignalsResponse)
async def process_learning_signals(
    request: ProcessLearningSignalsRequest,
    user: User = Depends(require_permission("continuous_twin:learning:process")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Process open learning signals and generate lessons."""
    processed = await continuous_twin_service.process_learning_signals(
        db, organization_id=org.id, limit=request.limit
    )
    await db.commit()
    return ProcessLearningSignalsResponse(processed=processed)


@router.post("/learning/session", response_model=RunLearningSessionResponse)
async def run_learning_session(
    request: RunLearningSessionRequest,
    user: User = Depends(require_permission("continuous_twin:learning:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Run a continuous learning session."""
    session = await continuous_twin_service.run_learning_session(
        db, organization_id=org.id, session_type=request.session_type,
        scope_type=request.scope_type, scope_id=request.scope_id, triggered_by=user.id
    )
    await db.commit()
    return RunLearningSessionResponse(session=session)


@router.post("/learning/record", response_model=RecordInstitutionalMemoryResponse)
async def record_learning(
    request: RecordLearningRequest,
    user: User = Depends(require_permission("continuous_twin:learning:record")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Record learning from autonomous operation."""
    learning = await continuous_twin_service.record_institutional_memory(
        db, org.id, request.lesson_type, request.lesson_title,
        request.lesson_summary, request.lesson_details, request.confidence,
        request.evidence_fingerprints, request.applicable_proposal_types,
        request.applicable_contexts
    )
    await db.commit()
    return RecordInstitutionalMemoryResponse(entry=learning)


@router.get("/learning", response_model=List[InstitutionalMemoryEntryResponse])
async def list_learning(
    proposal_id: Optional[str] = Query(None),
    lesson_type: Optional[str] = Query(None),
    validated: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:learning:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List institutional memory entries."""
    query = select(InstitutionalMemoryEntry).where(InstitutionalMemoryEntry.organization_id == org.id)
    if lesson_type:
        query = query.where(InstitutionalMemoryEntry.kind == lesson_type)
    if validated is not None:
        query = query.where(InstitutionalMemoryEntry.validated == validated)
    query = query.order_by(InstitutionalMemoryEntry.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    learnings = result.scalars().all()
    return [InstitutionalMemoryEntryResponse.from_orm(l) for l in learnings]


@router.post("/learning/{learning_id}/validate", response_model=InstitutionalMemoryEntryResponse)
async def validate_learning(
    learning_id: str,
    user: User = Depends(require_permission("continuous_twin:learning:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Validate a learning entry."""
    learning = await db.get(InstitutionalMemoryEntry, learning_id)
    if not learning or learning.organization_id != org.id:
        raise HTTPException(404, "Learning entry not found")
    
    learning.validated = True
    learning.validated_by = user.id
    learning.validated_at = utcnow()
    await db.commit()
    
    return InstitutionalMemoryEntryResponse.from_orm(learning)


# =============================================================================
# Institutional Memory
# =============================================================================

@router.post("/memory", response_model=RecordInstitutionalMemoryResponse)
async def record_institutional_memory(
    request: RecordInstitutionalMemoryRequest,
    user: User = Depends(require_permission("continuous_twin:memory:record")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Record a new institutional memory entry."""
    entry = await continuous_twin_service.record_institutional_memory(
        db, org.id, request.kind, request.fingerprint, request.title,
        request.summary, request.content_json, request.source_type,
        request.source_id, request.source_event_id, request.confidence,
        request.evidence_fingerprints, request.applicable_contexts, request.conditions
    )
    await db.commit()
    return RecordInstitutionalMemoryResponse(entry=entry)


@router.get("/memory", response_model=List[InstitutionalMemoryEntryResponse])
async def list_institutional_memory(
    kind: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:memory:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List institutional memory entries."""
    query = select(InstitutionalMemoryEntry).where(InstitutionalMemoryEntry.organization_id == org.id)
    if kind:
        query = query.where(InstitutionalMemoryEntry.kind == kind)
    if status:
        query = query.where(InstitutionalMemoryEntry.status == status)
    query = query.order_by(InstitutionalMemoryEntry.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    entries = result.scalars().all()
    return [InstitutionalMemoryEntryResponse.from_orm(e) for e in entries]


@router.patch("/memory/{entry_id}", response_model=InstitutionalMemoryEntryResponse)
async def update_institutional_memory(
    entry_id: str,
    update: InstitutionalMemoryEntryUpdate,
    user: User = Depends(require_permission("continuous_twin:memory:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update an institutional memory entry."""
    entry = await db.get(InstitutionalMemoryEntry, entry_id)
    if not entry or entry.organization_id != org.id:
        raise HTTPException(404, "Memory entry not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(entry, key, value)
    
    entry.updated_at = utcnow()
    await db.commit()
    
    return InstitutionalMemoryEntryResponse.from_orm(entry)


# =============================================================================
# Attention & Drift
# =============================================================================

@router.post("/attention", response_model=CompanyAttentionResponse)
async def create_attention(
    request: RecordAttentionRequest,
    user: User = Depends(require_permission("continuous_twin:attention:create")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create an attention signal."""
    attention = await continuous_twin_service.create_attention(
        db, org.id, request.attention_type, request.priority, request.title,
        request.description, request.details_json, request.source_type,
        request.source_id, request.source_event_id, request.assigned_to, request.urgency
    )
    await db.commit()
    return CompanyAttentionResponse.from_orm(attention)


@router.post("/attention/{notification_id}/read", response_model=dict)
async def mark_attention_read(
    notification_id: str,
    user: User = Depends(require_permission("continuous_twin:attention:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Mark an attention signal as read."""
    success = await continuous_twin_service.resolve_attention(db, notification_id, user.id)
    await db.commit()
    return {"success": success}


@router.post("/attention/{attention_id}/resolve", response_model=CompanyAttentionResponse)
async def resolve_attention(
    attention_id: str,
    request: MarkAttentionReadRequest,
    user: User = Depends(require_permission("continuous_twin:attention:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Resolve an attention signal."""
    attention = await continuous_twin_service.resolve_attention(db, attention_id, user.id, request.resolution_note)
    await db.commit()
    return CompanyAttentionResponse.from_orm(attention)


@router.get("/attention", response_model=List[CompanyAttentionResponse])
async def list_attention(
    status: Optional[str] = Query(None),
    attention_type: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:attention:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List attention signals."""
    query = select(CompanyAttention).where(CompanyAttention.organization_id == org.id)
    if status:
        query = query.where(CompanyAttention.status == status)
    if attention_type:
        query = query.where(CompanyAttention.attention_type == attention_type)
    if priority:
        query = query.where(CompanyAttention.priority == priority)
    query = query.order_by(CompanyAttention.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    attention = result.scalars().all()
    return [CompanyAttentionResponse.from_orm(a) for a in attention]


@router.post("/drift/detect", response_model=ModelTwinDriftResponse)
async def detect_drift(
    request: DriftDetectRequest,
    user: User = Depends(require_permission("continuous_twin:drift:detect")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Record a model/twin drift."""
    drift = await continuous_twin_service.detect_and_record_drift(
        db, org.id, request.drift_type, request.severity,
        request.subject_type, request.subject_id,
        request.expected, request.observed, request.deviation_score,
        request.severity_score, request.evidence
    )
    await db.commit()
    return ModelTwinDriftResponse.from_orm(drift)


@router.post("/drift/{drift_id}/resolve", response_model=ModelTwinDriftResponse)
async def resolve_drift(
    drift_id: str,
    request: DriftResolveRequest,
    user: User = Depends(require_permission("continuous_twin:drift:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a drift."""
    drift = await db.get(ModelTwinDrift, drift_id)
    if not drift or drift.organization_id != org.id:
        raise HTTPException(404, "Drift not found")
    
    drift.state = "resolved"
    drift.resolved_at = utcnow()
    drift.resolved_by = request.resolved_by
    drift.resolution_note = request.resolution_note
    await db.commit()
    
    return ModelTwinDriftResponse.from_orm(drift)


@router.get("/drift", response_model=List[ModelTwinDriftResponse])
async def list_drifts(
    drift_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, pattern="^(low|medium|high|critical)$"),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:drift:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List model/twin drifts."""
    query = select(ModelTwinDrift).where(ModelTwinDrift.organization_id == org.id)
    if drift_type:
        query = query.where(ModelTwinDrift.drift_type == drift_type)
    if severity:
        query = query.where(ModelTwinDrift.severity == severity)
    if status:
        query = query.where(ModelTwinDrift.state == status)
    query = query.order_by(ModelTwinDrift.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    drifts = result.scalars().all()
    return [ModelTwinDriftResponse.from_orm(d) for d in drifts]


# =============================================================================
# Twin Scopes & Contexts
# =============================================================================

@router.post("/twin/scopes", response_model=TwinScopeResponse, status_code=201)
async def create_twin_scope(
    request: TwinScopeCreateRequest,
    user: User = Depends(require_permission("continuous_twin:twin:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a new twin scope."""
    scope = await continuous_twin_service.create_twin_scope(
        db, org.id, request.scope_type, request.scope_id, request.name,
        request.description, request.included_dimensions, request.auto_refresh,
        request.refresh_interval_seconds
    )
    await db.commit()
    return TwinScopeResponse.from_orm(scope)


@router.get("/twin/scopes", response_model=List[TwinScopeResponse])
async def list_twin_scopes(
    user: User = Depends(require_permission("continuous_twin:twin:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List all twin scopes for the organization."""
    result = await db.execute(
        select(TwinScope).where(TwinScope.organization_id == org.id)
    )
    scopes = result.scalars().all()
    return [TwinScopeResponse.from_orm(s) for s in scopes]


@router.get("/twin/scopes/{scope_id}", response_model=TwinScopeResponse)
async def get_twin_scope(
    scope_id: str,
    user: User = Depends(require_permission("continuous_twin:twin:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get a twin scope by ID."""
    scope = await db.get(TwinScope, scope_id)
    if not scope or scope.organization_id != org.id:
        raise HTTPException(404, "Twin scope not found")
    return TwinScopeResponse.from_orm(scope)


@router.patch("/twin/scopes/{scope_id}", response_model=TwinScopeResponse)
async def update_twin_scope(
    scope_id: str,
    update: TwinScopeUpdate,
    user: User = Depends(require_permission("continuous_twin:twin:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update a twin scope."""
    scope = await db.get(TwinScope, scope_id)
    if not scope or scope.organization_id != org.id:
        raise HTTPException(404, "Twin scope not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(scope, key, value)
    
    await db.commit()
    scope = await db.get(TwinScope, scope_id)
    return TwinScopeResponse.from_orm(scope)


@router.post("/twin/context", response_model=TwinContextResponse)
async def get_twin_context(
    request: TwinContextRequest,
    user: User = Depends(require_permission("continuous_twin:context:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get the operating context for a twin scope."""
    context = await continuous_twin_service.get_twin_context(
        db, org.id, request.scope_id, request.context_type, request.context_json,
        request.input_fingerprint
    )
    await db.commit()
    return TwinContextResponse(
        id=context.id,
        organization_id=context.organization_id,
        proposal_id=context.proposal_id,
        context_type=context.context_type,
        context_json=context.context_json or {},
        computed_at=context.computed_at,
    )


# =============================================================================
# State Projection
# =============================================================================

@router.post("/state/projection/update", response_model=ContinuousStateProjectionResponse)
async def update_state_projection(
    request: StateProjectionUpdateRequest,
    user: User = Depends(require_permission("continuous_twin:state:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update a continuous state projection."""
    projection = await continuous_twin_service.update_state_projection(
        db, org.id, request.dimension, request.state_json, request.event_id
    )
    await db.commit()
    return ContinuousStateProjectionResponse.from_orm(projection)


@router.get("/state/projections", response_model=List[ContinuousStateProjectionResponse])
async def list_state_projections(
    dimension: Optional[str] = Query(None),
    user: User = Depends(require_permission("continuous_twin:state:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List continuous state projections."""
    query = select(ContinuousStateProjection).where(
        ContinuousStateProjection.organization_id == org.id
    )
    if dimension:
        query = query.where(ContinuousStateProjection.dimension == dimension)
    query = query.order_by(ContinuousStateProjection.last_refreshed_at.desc().nullslast())
    result = await db.execute(query)
    projections = result.scalars().all()
    return [ContinuousStateProjectionResponse.from_orm(p) for p in projections]


@router.post("/state/projection/update", response_model=ContinuousStateProjectionResponse)
async def update_state_projection_endpoint(
    request: StateProjectionUpdateRequest,
    user: User = Depends(require_permission("continuous_twin:state:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update a continuous state projection."""
    projection = await continuous_twin_service.update_state_projection(
        db, org.id, request.dimension, request.state_json, request.event_id
    )
    await db.commit()
    return ContinuousStateProjectionResponse.from_orm(projection)


# =============================================================================
# Eligibility Cache
# =============================================================================

@router.post("/eligibility/cache/invalidate", response_model=dict)
async def invalidate_eligibility_cache(
    actor_id: Optional[str] = Body(None),
    proposal_type: Optional[str] = Body(None),
    user: User = Depends(require_permission("continuous_twin:eligibility:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Invalidate eligibility cache."""
    count = await continuous_twin_service.invalidate_eligibility_cache(
        db, org.id, actor_id, proposal_type
    )
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
    user: User = Depends(require_permission("continuous_twin:events:read")),
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
    return [AutonomyEventResponse.from_orm(e) for e in events]


# =============================================================================
# Executions
# =============================================================================

@router.get("/executions", response_model=List[AutonomyExecutionResponse])
async def list_executions(
    proposal_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("continuous_twin:execution:read")),
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
    user: User = Depends(require_permission("continuous_twin:learning:read")),
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
    return [AutonomyLearningResponse.from_orm(l) for l in learnings]


@router.post("/learning/{learning_id}/validate", response_model=AutonomyLearningResponse)
async def validate_learning(
    learning_id: str,
    user: User = Depends(require_permission("continuous_twin:learning:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Validate a learning entry."""
    learning = await db.get(AutonomyLearning, learning_id)
    if not learning or learning.organization_id != org.id:
        raise HTTPException(404, "Learning entry not found")
    
    learning.validated = True
    learning.validated_by = user.id
    learning.validated_at = utcnow()
    await db.commit()
    
    return AutonomyLearningResponse.from_orm(learning)


# =============================================================================
# Risk
# =============================================================================

@router.post("/risk", response_model=AutonomyRiskResponse)
async def create_risk(
    request: DriftDetectRequest,
    user: User = Depends(require_permission("continuous_twin:risk:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create risk assessment for proposal."""
    risk = await autonomy_service.create_risk_assessment(
        db, proposal_id="", kind=request.drift_type, level=request.severity,
        title=request.subject_type, description="",
        probability=request.probability, impact_score=request.impact_score,
        financial_exposure_cents=request.financial_exposure_cents
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


# =============================================================================
# Exports
# =============================================================================

__all__ = ["router"]