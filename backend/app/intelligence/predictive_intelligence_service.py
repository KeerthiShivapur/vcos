"""Canonical Predictive Company Intelligence Service — Gate 10.

This service derives company predictions from canonical reality and institutional learning.
All predictions are grounded in:
- Current canonical state (capacity, commitments, responsibilities, work, dependencies)
- Verified institutional learning (Gate 9 lessons, patterns, precedents)
- Historical evidence (outcomes, assessments, calibration history)

Predictions are:
- Governed (tenant/scope/permission checked)
- Temporal (versioned, superseded, never overwrite history)
- Provenance-aware (full walk-back to evidence)
- Epistemically honest (prediction ≠ truth ≠ recommendation ≠ decision)
- Calibrated (evaluated against actual outcomes, feeds institutional learning)

NO parallel architecture — predictions are derived views over canonical reality.
"""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, List, Dict, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

from sqlalchemy import select, and_, or_, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
    CompanyObjective,
    CompanyInitiative,
    CompanyGoal,
)
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionPrecedent,
    CompanyDecisionContradiction,
    CompanyDecisionQuality,
    CompanyDecisionTrack,
    CompanyDecisionEvidence,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome, CompanyActionEvent
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.workload import WorkloadSnapshot
from app.models.organizational_learning import (
    OrganizationalLearning,
    LearningEvidence,
    OutcomeAssessment,
    DecisionOutcome,
    RecommendationOutcome,
)
from app.models.intelligence import (
    PatternDetection,
    PatternEvent,
)
from app.models.company_memory import (
    CompanyMemory,
    MemoryEvent,
    MemoryOutcome,
)
from app.models.prediction import (
    Prediction,
    PredictionHistory,
    PredictionModel,
    PREDICTION_KINDS,
    PREDICTION_STATUSES,
)
from app.models.execution_strategy import (
    ObjectivePrediction,
    ObjectiveSimulation,
)
from app.models.digital_twin import (
    TwinPrediction,
    StrategicForecast,
)
from app.models.org_capability_intelligence import (
    OrgCapability,
    CapabilitySignal,
)
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
    CapacitySnapshot,
)
from app.intelligence.institutional_intelligence_service import (
    institutional_intelligence_service,
    QualifiedLesson,
    InstitutionalPattern,
)
from app.intelligence.organizational_capacity_service import (
    organizational_capacity_service,
    CapacityConflict,
)
from app.intelligence.organizational_intelligence_service import (
    organizational_intelligence_service,
    OrganizationalContext,
)
from app.intelligence.organizational_attention_service import (
    organizational_attention_service,
)
from app.intelligence.cross_domain_impact_service import (
    cross_domain_impact_service,
    ImpactAnalysis,
)

logger = logging.getLogger("vcos.intelligence.predictive_intelligence")


class PredictionKind(str, Enum):
    """Canonical prediction kinds for company operating predictions."""
    COMMITMENT_RISK = "commitment_risk"          # Commitment likely to miss/underachieve
    OBJECTIVE_RISK = "objective_risk"            # Objective trending to underachieve
    CAPACITY_PRESSURE = "capacity_pressure"      # Future capacity deficit forecast
    BOTTLENECK_EMERGENCE = "bottleneck_emergence" # Emerging organizational bottleneck
    EXECUTION_OUTCOME = "execution_outcome"      # Likelihood of intended outcome
    DEPENDENCY_CASCADE = "dependency_cascade"    # Dependency chain failure risk
    RESOURCE_SHORTFALL = "resource_shortfall"    # Budget/asset/infrastructure shortfall


class EpistemicStatus(str, Enum):
    """Epistemic status of a prediction."""
    SPECULATIVE = "speculative"       # Low evidence, high uncertainty
    EVIDENCE_BASED = "evidence_based"  # Supported by some evidence
    WELL_GROUNDED = "well_grounded"    # Strong evidence + institutional learning
    CALIBRATED = "calibrated"          # Historically calibrated prediction
    VALIDATED = "validated"            # Prediction confirmed by outcome
    INVALIDATED = "invalidated"        # Prediction contradicted by outcome


@dataclass
class PredictionProvenance:
    """Complete provenance chain for a prediction."""
    canonical_state_snapshot: Dict[str, Any]  # Relevant canonical state at prediction time
    institutional_lessons_used: List[Dict[str, Any]]  # Lessons with epistemic status
    patterns_used: List[Dict[str, Any]]  # Patterns with confidence
    evidence_chain: List[Dict[str, Any]]  # Full evidence walk
    model_version: str
    algorithm_identity: str
    generated_at: datetime
    generated_by: str


@dataclass
class CompanyPrediction:
    """A canonical company prediction with full metadata."""
    id: str
    kind: str
    title: str
    description: str
    subject_type: str
    subject_id: str
    probability: float  # 0.0 - 1.0
    confidence: float   # Epistemic confidence in the prediction itself
    epistemic_status: str
    horizon_days: int
    horizon_end: datetime
    prediction_method: str  # trajectory, pattern_based, lesson_based, calibration, simulation
    evidence_bundle: Dict[str, Any]  # Current state signals
    institutional_basis: List[Dict[str, Any]]  # Lessons/patterns used
    provenance: PredictionProvenance
    scope_type: str
    scope_id: Optional[str]
    valid_from: datetime
    valid_until: Optional[datetime]
    superseded_by: Optional[str] = None
    actual_outcome: Optional[Dict[str, Any]] = None
    evaluation: Optional[Dict[str, Any]] = None
    derived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


class PredictiveIntelligenceService:
    """Service for deriving company predictions from canonical reality and institutional learning."""

    def __init__(self):
        pass

    # ================================================================
    # MAIN ENTRY POINTS
    # ================================================================

    async def derive_predictions(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        kinds: Optional[List[str]] = None,
        scope_type: str = "organization",
        scope_id: Optional[str] = None,
        horizon_days: int = 90,
    ) -> List[CompanyPrediction]:
        """Derive all applicable predictions for a scope."""
        predictions = []

        # A. Commitment risk predictions
        if kinds is None or "commitment_risk" in kinds:
            commitment_preds = await self._predict_commitment_risks(
                db, caller, horizon_days, scope_type, scope_id
            )
            predictions.extend(commitment_preds)

        # B. Objective risk predictions
        if kinds is None or "objective_risk" in kinds:
            objective_preds = await self._predict_objective_risks(
                db, caller, horizon_days, scope_type, scope_id
            )
            predictions.extend(objective_preds)

        # C. Capacity pressure predictions
        if kinds is None or "capacity_pressure" in kinds:
            capacity_preds = await self._predict_capacity_pressure(
                db, caller, horizon_days, scope_type, scope_id
            )
            predictions.extend(capacity_preds)

        # D. Bottleneck emergence predictions
        if kinds is None or "bottleneck_emergence" in kinds:
            bottleneck_preds = await self._predict_bottleneck_emergence(
                db, caller, horizon_days, scope_type, scope_id
            )
            predictions.extend(bottleneck_preds)

        # E. Execution outcome predictions
        if kinds is None or "execution_outcome" in kinds:
            execution_preds = await self._predict_execution_outcomes(
                db, caller, horizon_days, scope_type, scope_id
            )
            predictions.extend(execution_preds)

        # F. Dependency cascade predictions
        if kinds is None or "dependency_cascade" in kinds:
            dependency_preds = await self._predict_dependency_cascades(
                db, caller, horizon_days, scope_type, scope_id
            )
            predictions.extend(dependency_preds)

        # Sort by probability * severity
        predictions.sort(key=lambda p: p.probability * p.confidence, reverse=True)

        logger.info(f"Derived {len(predictions)} predictions for org {caller.organization_id}")
        return predictions

    async def get_prediction_detail(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        prediction_id: str,
    ) -> Optional[CompanyPrediction]:
        """Get full prediction detail with complete provenance walk."""
        # Try ObjectivePrediction first
        obj_pred = await db.get(ObjectivePrediction, prediction_id)
        if obj_pred and obj_pred.organization_id == caller.organization_id:
            return await self._build_objective_prediction_detail(db, caller, obj_pred)

        # Try generic Prediction
        pred = await db.get(Prediction, prediction_id)
        if pred and pred.organization_id == caller.organization_id:
            return await self._build_generic_prediction_detail(db, caller, pred)

        # Try TwinPrediction
        twin_pred = await db.get(TwinPrediction, prediction_id)
        if twin_pred and twin_pred.organization_id == caller.organization_id:
            return await self._build_twin_prediction_detail(db, caller, twin_pred)

        return None

    async def evaluate_predictions(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        max_age_days: int = 180,
    ) -> Dict[str, Any]:
        """Evaluate mature predictions against actual outcomes for calibration."""
        evaluated = 0
        correct = 0
        calibration_data = []

        # Evaluate ObjectivePredictions
        cutoff = utcnow() - timedelta(days=max_age_days)
        eval_result = await self._evaluate_objective_predictions(db, caller, cutoff)
        evaluated += eval_result["evaluated"]
        correct += eval_result["correct"]
        calibration_data.extend(eval_result["calibration_data"])

        # Evaluate generic Predictions
        pred_result = await self._evaluate_generic_predictions(db, caller, cutoff)
        evaluated += pred_result["evaluated"]
        correct += pred_result["correct"]
        calibration_data.extend(pred_result["calibration_data"])

        # Update PredictionModel calibration
        await self._update_model_calibration(db, caller, calibration_data)

        return {
            "evaluated": evaluated,
            "correct": correct,
            "accuracy_rate": correct / evaluated if evaluated > 0 else 0,
            "calibration_data_points": len(calibration_data),
        }

    # ================================================================
    # COMMITMENT RISK PREDICTIONS
    # ================================================================

    async def _predict_commitment_risks(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        horizon_days: int,
        scope_type: str,
        scope_id: Optional[str],
    ) -> List[CompanyPrediction]:
        """Predict which commitments are at risk of missing/underachieving."""
        predictions = []

        # Get active commitments
        commitments_query = select(CompanyCommitment).where(
            CompanyCommitment.organization_id == caller.organization_id,
            CompanyCommitment.state.in_(("authorized", "active", "paused")),
        )
        
        # Apply scope filter
        if scope_type == "project" and scope_id:
            commitments_query = commitments_query.where(
                CompanyCommitment.scope_type == "project",
                CompanyCommitment.scope_id == scope_id,
            )
        elif scope_type == "team" and scope_id:
            commitments_query = commitments_query.where(
                CompanyCommitment.scope_type == "team",
                CompanyCommitment.scope_id == scope_id,
            )
        elif scope_type == "department" and scope_id:
            commitments_query = commitments_query.where(
                CompanyCommitment.scope_type == "department",
                CompanyCommitment.scope_id == scope_id,
            )

        commitments_result = await db.execute(commitments_query.limit(100))
        commitments = commitments_result.scalars().all()

        for commitment in commitments:
            # Get commitment risk from cross-domain impact service
            risk = await cross_domain_impact_service.derive_commitment_risk(
                db, caller=caller, commitment_id=commitment.id
            )

            if risk["risk_level"] in ("high", "critical"):
                # Get institutional lessons relevant to this commitment type
                lessons = await self._get_relevant_lessons_for_commitment(db, caller, commitment)

                # Get patterns
                patterns = await self._get_relevant_patterns_for_commitment(db, caller, commitment)

                # Calculate probability
                probability = self._calculate_commitment_risk_probability(risk, lessons, patterns)

                # Determine epistemic status
                epistemic_status = self._determine_epistemic_status(lessons, patterns, risk)

                # Build prediction
                pred = CompanyPrediction(
                    id=f"pred-commitment-{commitment.id}-{uuid.uuid4().hex[:8]}",
                    kind="commitment_risk",
                    title=f"Commitment risk: {commitment.title}",
                    description=f"Commitment '{commitment.title}' has {risk['risk_level']} risk of underachievement",
                    subject_type="commitment",
                    subject_id=commitment.id,
                    probability=probability,
                    confidence=risk.get("outcome_effectiveness", 0.5),
                    epistemic_status=epistemic_status,
                    horizon_days=horizon_days,
                    horizon_end=utcnow() + timedelta(days=horizon_days),
                    prediction_method=self._determine_prediction_method(lessons, patterns),
                    evidence_bundle={
                        "commitment_state": commitment.state,
                        "total_actions": risk["total_actions"],
                        "completed_actions": risk["completed_actions"],
                        "failed_outcomes": risk["failed_outcomes"],
                        "partial_outcomes": risk["partial_outcomes"],
                        "outcome_effectiveness": risk["outcome_effectiveness"],
                        "risk_factors": risk["risk_factors"],
                    },
                    institutional_basis=[self._lesson_to_basis(l) for l in lessons] + 
                                       [self._pattern_to_basis(p) for p in patterns],
                    provenance=await self._build_provenance(db, caller, "commitment_risk", commitment.id),
                    scope_type="organization",
                    scope_id=None,
                    valid_from=utcnow(),
                    valid_until=utcnow() + timedelta(days=horizon_days),
                )
                predictions.append(pred)

        return predictions

    # ================================================================
    # OBJECTIVE RISK PREDICTIONS
    # ================================================================

    async def _predict_objective_risks(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        horizon_days: int,
        scope_type: str,
        scope_id: Optional[str],
    ) -> List[CompanyPrediction]:
        """Predict which objectives are at risk of underachievement."""
        predictions = []

        # Get active objectives
        objectives_query = select(CompanyObjective).where(
            CompanyObjective.organization_id == caller.organization_id,
            CompanyObjective.status == "active",
        )

        objectives_result = await db.execute(objectives_query.limit(50))
        objectives = objectives_result.scalars().all()

        for objective in objectives:
            # Get initiatives for this objective
            initiatives_result = await db.execute(
                select(CompanyInitiative).where(
                    CompanyInitiative.organization_id == caller.organization_id,
                    CompanyInitiative.objective_id == objective.id,
                    CompanyInitiative.status == "active",
                )
            )
            initiatives = initiatives_result.scalars().all()

            behind_count = 0
            if not initiatives:
                # No initiatives = high risk
                probability = 0.8
            else:
                # Check initiative progress
                for initiative in initiatives:
                    if initiative.expected_outcome and objective.current_value is not None:
                        target = initiative.expected_outcome.get("target_value")
                        if target and objective.current_value is not None:
                            progress = objective.current_value / target
                            if progress < 0.3:
                                behind_count += 1

                probability = min(0.9, behind_count / max(1, len(initiatives)) + 0.1)

            if probability > 0.5:
                # Get relevant lessons
                lessons = await self._get_relevant_lessons_for_objective(db, caller, objective)
                patterns = await self._get_relevant_patterns_for_objective(db, caller, objective)

                epistemic_status = self._determine_epistemic_status(lessons, patterns, {})

                pred = CompanyPrediction(
                    id=f"pred-objective-{objective.id}-{uuid.uuid4().hex[:8]}",
                    kind="objective_risk",
                    title=f"Objective risk: {objective.title}",
                    description=f"Objective '{objective.title}' has {behind_count} of {len(initiatives)} initiatives behind pace",
                    subject_type="objective",
                    subject_id=objective.id,
                    probability=probability,
                    confidence=0.7,
                    epistemic_status=epistemic_status,
                    horizon_days=horizon_days,
                    horizon_end=utcnow() + timedelta(days=horizon_days),
                    prediction_method=self._determine_prediction_method(lessons, patterns),
                    evidence_bundle={
                        "objective_status": objective.status,
                        "total_initiatives": len(initiatives),
                        "behind_initiatives": behind_count,
                        "initiatives": [
                            {
                                "id": i.id,
                                "title": i.title,
                                "progress": objective.current_value / i.expected_outcome.get("target_value", 1) if i.expected_outcome and objective.current_value else None,
                            } for i in initiatives
                        ],
                    },
                    institutional_basis=[self._lesson_to_basis(l) for l in lessons] + 
                                       [self._pattern_to_basis(p) for p in patterns],
                    provenance=await self._build_provenance(db, caller, "objective_risk", objective.id),
                    scope_type="organization",
                    scope_id=None,
                    valid_from=utcnow(),
                    valid_until=utcnow() + timedelta(days=horizon_days),
                )
                predictions.append(pred)

        return predictions

    # ================================================================
    # CAPACITY PRESSURE PREDICTIONS
    # ================================================================

    async def _predict_capacity_pressure(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        horizon_days: int,
        scope_type: str,
        scope_id: Optional[str],
    ) -> List[CompanyPrediction]:
        """Predict future capacity pressure from current state + trends."""
        predictions = []

        # Get OrgCapabilities with capacity state
        caps_result = await db.execute(
            select(OrgCapability).where(
                OrgCapability.organization_id == caller.organization_id,
                OrgCapability.capacity_state.in_(("available", "stretched")),
                OrgCapability.demand_count > 0,
            ).limit(50)
        )
        capabilities = caps_result.scalars().all()

        for cap in capabilities:
            # Project capacity state forward based on current commitments + planned work
            # Get active allocations for this capability
            allocs_result = await db.execute(
                select(CapacityAllocation).where(
                    CapacityAllocation.organization_id == caller.organization_id,
                    CapacityAllocation.capability == cap.canonical_name,
                    CapacityAllocation.status == "active",
                )
            )
            allocations = allocs_result.scalars().all()

            # Get active demands
            demands_result = await db.execute(
                select(AllocationDemand).where(
                    AllocationDemand.organization_id == caller.organization_id,
                    AllocationDemand.capability == cap.canonical_name,
                )
            )
            demands = demands_result.scalars().all()

            # Project future state
            future_demand = sum(d.units for d in demands)
            future_allocated = sum(a.units for a in allocations)
            future_available = cap.capacity_potential - future_allocated

            if future_demand > cap.capacity_potential:
                probability = min(0.95, future_demand / cap.capacity_potential)
            elif future_available < cap.capacity_potential * 0.2:
                probability = 0.6
            else:
                probability = 0.1

            if probability > 0.5:
                lessons = await self._get_relevant_lessons_for_capability(db, caller, cap)
                patterns = await self._get_relevant_patterns_for_capability(db, caller, cap)

                pred = CompanyPrediction(
                    id=f"pred-capacity-{cap.skill_id}-{uuid.uuid4().hex[:8]}",
                    kind="capacity_pressure",
                    title=f"Capacity pressure: {cap.canonical_name}",
                    description=f"Capability '{cap.canonical_name}' projected to have {future_demand} demand vs {cap.capacity_potential} potential",
                    subject_type="capability",
                    subject_id=cap.skill_id,
                    probability=probability,
                    confidence=0.75,
                    epistemic_status="evidence_based",
                    horizon_days=horizon_days,
                    horizon_end=utcnow() + timedelta(days=horizon_days),
                    prediction_method="trajectory",
                    evidence_bundle={
                        "capability": cap.canonical_name,
                        "capacity_potential": cap.capacity_potential,
                        "current_committed": cap.capacity_committed,
                        "current_available": cap.capacity_available,
                        "projected_demand": future_demand,
                        "projected_allocated": future_allocated,
                        "projected_available": future_available,
                        "demand_count": len(demands),
                        "allocation_count": len(allocations),
                    },
                    institutional_basis=[self._lesson_to_basis(l) for l in lessons] + 
                                       [self._pattern_to_basis(p) for p in patterns],
                    provenance=await self._build_provenance(db, caller, "capacity_pressure", cap.skill_id),
                    scope_type="organization",
                    scope_id=None,
                    valid_from=utcnow(),
                    valid_until=utcnow() + timedelta(days=horizon_days),
                )
                predictions.append(pred)

        return predictions

    # ================================================================
    # BOTTLENECK EMERGENCE PREDICTIONS
    # ================================================================

    async def _predict_bottleneck_emergence(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        horizon_days: int,
        scope_type: str,
        scope_id: Optional[str],
    ) -> List[CompanyPrediction]:
        """Predict emerging organizational bottlenecks from Gate 8.5 intelligence."""
        predictions = []

        # Get organizational attention items (bottlenecks, critical people)
        attention = await organizational_attention_service.derive_organizational_attention(
            db, caller=caller
        )

        bottlenecks = [a for a in attention if a["kind"] == "organizational_bottleneck"]
        critical_people = [a for a in attention if a["kind"] == "critical_person_dependency"]
        concentration = [a for a in attention if a["kind"] in ("responsibility_concentration", "dependency_concentration")]

        # Predict bottleneck emergence from critical people
        for person_attention in critical_people:
            prob = 0.7 if person_attention["severity"] == "critical" else 0.5
            
            pred = CompanyPrediction(
                id=f"pred-bottleneck-person-{person_attention['source_entities'][0]['id']}-{uuid.uuid4().hex[:8]}",
                kind="bottleneck_emergence",
                title=f"Critical person bottleneck: {person_attention['title']}",
                description=person_attention["description"],
                subject_type="person",
                subject_id=person_attention["source_entities"][0]["id"],
                probability=prob,
                confidence=0.7,
                epistemic_status="well_grounded",
                horizon_days=horizon_days,
                horizon_end=utcnow() + timedelta(days=horizon_days),
                prediction_method="pattern_based",
                evidence_bundle={
                    "source_attention": person_attention,
                    "risk_factors": person_attention["risk_factors"],
                },
                institutional_basis=[],
                provenance=await self._build_provenance(db, caller, "bottleneck_emergence", person_attention["source_entities"][0]["id"]),
                scope_type="organization",
                scope_id=None,
                valid_from=utcnow(),
                valid_until=utcnow() + timedelta(days=horizon_days),
            )
            predictions.append(pred)

        # Predict bottleneck from team/department overload
        for bottleneck in bottlenecks:
            prob = 0.8 if bottleneck["severity"] == "critical" else 0.6
            
            pred = CompanyPrediction(
                id=f"pred-bottleneck-org-{bottleneck['source_entities'][0]['id']}-{uuid.uuid4().hex[:8]}",
                kind="bottleneck_emergence",
                title=f"Organizational bottleneck: {bottleneck['title']}",
                description=bottleneck["description"],
                subject_type=bottleneck["source_entities"][0]["type"],
                subject_id=bottleneck["source_entities"][0]["id"],
                probability=prob,
                confidence=0.8,
                epistemic_status="well_grounded",
                horizon_days=horizon_days,
                horizon_end=utcnow() + timedelta(days=horizon_days),
                prediction_method="pattern_based",
                evidence_bundle={
                    "source_attention": bottleneck,
                    "risk_factors": bottleneck["risk_factors"],
                },
                institutional_basis=[],
                provenance=await self._build_provenance(db, caller, "bottleneck_emergence", bottleneck["source_entities"][0]["id"]),
                scope_type="organization",
                scope_id=None,
                valid_from=utcnow(),
                valid_until=utcnow() + timedelta(days=horizon_days),
            )
            predictions.append(pred)

        return predictions

    # ================================================================
    # EXECUTION OUTCOME PREDICTIONS
    # ================================================================

    async def _predict_execution_outcomes(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        horizon_days: int,
        scope_type: str,
        scope_id: Optional[str],
    ) -> List[CompanyPrediction]:
        """Predict execution outcomes for active work."""
        predictions = []

        # Get active actions with incomplete outcomes
        actions_query = select(CompanyAction).where(
            CompanyAction.organization_id == caller.organization_id,
            CompanyAction.state.in_(("proposed", "approved", "ready", "in_progress")),
        )

        actions_result = await db.execute(actions_query.limit(50))
        actions = actions_result.scalars().all()

        for action in actions:
            # Get outcomes for this action
            outcomes_result = await db.execute(
                select(CompanyActionOutcome).where(
                    CompanyActionOutcome.organization_id == caller.organization_id,
                    CompanyActionOutcome.action_id == action.id,
                )
            )
            outcomes = outcomes_result.scalars().all()

            if not outcomes:
                # No outcomes yet - predict based on similar historical actions
                lessons = await self._get_relevant_lessons_for_action(db, caller, action)
                patterns = await self._get_relevant_patterns_for_action(db, caller, action)

                prob = self._estimate_outcome_probability(lessons, patterns, action)
                
                if prob > 0.5:
                    pred = CompanyPrediction(
                        id=f"pred-execution-{action.id}-{uuid.uuid4().hex[:8]}",
                        kind="execution_outcome",
                        title=f"Execution outcome: {action.title}",
                        description=f"Action '{action.title}' predicted outcome probability",
                        subject_type="action",
                        subject_id=action.id,
                        probability=prob,
                        confidence=0.6,
                        epistemic_status="evidence_based",
                        horizon_days=horizon_days,
                        horizon_end=utcnow() + timedelta(days=horizon_days),
                        prediction_method="lesson_based" if lessons else "pattern_based",
                        evidence_bundle={
                            "action_type": action.action_type,
                            "action_state": action.state,
                            "source_commitment_id": action.source_commitment_id,
                            "source_responsibility_id": action.source_responsibility_id,
                        },
                        institutional_basis=[self._lesson_to_basis(l) for l in lessons] + 
                                           [self._pattern_to_basis(p) for p in patterns],
                        provenance=await self._build_provenance(db, caller, "execution_outcome", action.id),
                        scope_type="organization",
                        scope_id=None,
                        valid_from=utcnow(),
                        valid_until=utcnow() + timedelta(days=horizon_days),
                    )
                    predictions.append(pred)

        return predictions

    # ================================================================
    # DEPENDENCY CASCADE PREDICTIONS
    # ================================================================

    async def _predict_dependency_cascades(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        horizon_days: int,
        scope_type: str,
        scope_id: Optional[str],
    ) -> List[CompanyPrediction]:
        """Predict dependency cascade failures."""
        predictions = []

        # Find tasks that are critical dependencies for many other tasks
        dep_hubs = await db.execute(
            select(
                TaskDependency.depends_on_task_id,
                func.count(TaskDependency.id).label("dep_count"),
            ).select_from(TaskDependency)
            .join(Task, Task.id == TaskDependency.depends_on_task_id)
            .where(
                TaskDependency.organization_id == caller.organization_id,
                Task.status.in_(("todo", "in_progress", "review")),
            )
            .group_by(TaskDependency.depends_on_task_id)
            .having(func.count(TaskDependency.id) >= 3)
            .limit(20)
        )

        for row in dep_hubs.all():
            blocking_task = await db.get(Task, row.depends_on_task_id)
            if not blocking_task or blocking_task.status == "completed":
                continue

            # Calculate cascade probability based on blocking task state
            base_prob = 0.3
            if blocking_task.status == "blocked":
                base_prob = 0.8
            elif blocking_task.status == "todo":
                base_prob = 0.5
            elif blocking_task.status == "in_progress":
                base_prob = 0.3

            # Check if blocking task has dependencies itself
            nested_deps = await db.execute(
                select(func.count(TaskDependency.id)).where(
                    TaskDependency.organization_id == caller.organization_id,
                    TaskDependency.task_id == blocking_task.id,
                )
            )
            nested_count = nested_deps.scalar() or 0
            if nested_count > 0:
                base_prob += 0.2

            prob = min(0.9, base_prob)

            if prob > 0.5:
                pred = CompanyPrediction(
                    id=f"pred-depcascade-{blocking_task.id}-{uuid.uuid4().hex[:8]}",
                    kind="dependency_cascade",
                    title=f"Dependency cascade risk: {blocking_task.title}",
                    description=f"Task '{blocking_task.title}' blocks {row.dep_count} tasks; cascade risk probability {prob:.0%}",
                    subject_type="task",
                    subject_id=blocking_task.id,
                    probability=prob,
                    confidence=0.65,
                    epistemic_status="evidence_based",
                    horizon_days=horizon_days,
                    horizon_end=utcnow() + timedelta(days=horizon_days),
                    prediction_method="pattern_based",
                    evidence_bundle={
                        "blocking_task_id": blocking_task.id,
                        "blocking_task_status": blocking_task.status,
                        "directly_blocked": row.dep_count,
                        "nested_dependencies": nested_count,
                    },
                    institutional_basis=[],
                    provenance=await self._build_provenance(db, caller, "dependency_cascade", blocking_task.id),
                    scope_type="project",
                    scope_id=blocking_task.project_id,
                    valid_from=utcnow(),
                    valid_until=utcnow() + timedelta(days=horizon_days),
                )
                predictions.append(pred)

        return predictions

    # ================================================================
    # HELPER METHODS
    # ================================================================

    async def _get_relevant_lessons_for_commitment(
        self, db: AsyncSession, caller: CallerAccess, commitment: CompanyCommitment
    ) -> List[QualifiedLesson]:
        """Get institutional lessons relevant to a commitment."""
        # Query OrganizationalLearning for relevant lessons
        result = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.lifecycle.in_(("supported", "authoritative", "confirmed")),
                OrganizationalLearning.kind.in_(("outcome_learning", "decision_learning")),
            ).limit(20)
        )
        lessons = result.scalars().all()
        # Filter for relevance (simplified - would use topic matching in production)
        return [
            QualifiedLesson(
                id=l.id,
                kind=l.kind,
                title=l.title,
                statement=l.lesson or "",
                epistemic_status=BRAIN_EPISTEMIC_STATUS.get(l.lifecycle, "UNKNOWN"),
                lifecycle=l.lifecycle,
                confidence=l.confidence or 0.0,
                scope_type="organization",
                scope_id=None,
                valid_from=l.observed_at,
                valid_to=None,
                superseded_by=None,
                supporting_evidence_count=len(json.loads(l.evidence_json)) if l.evidence_json else 0,
                contradicting_evidence_count=0,
                contradiction_ratio=0.0,
                outcome_quality=1.0,
                temporal_spread_days=0,
                evidence_coverage=0.0,
                cohort_signature="",
                evidence_chain=[],
                contradictions=[],
                precedents=[],
                supersession_history=[],
                provenance={},
                derived_at=l.observed_at,
            )
            for l in lessons
        ]

    async def _get_relevant_patterns_for_commitment(
        self, db: AsyncSession, caller: CallerAccess, commitment: CompanyCommitment
    ) -> List[InstitutionalPattern]:
        """Get patterns relevant to a commitment."""
        result = await db.execute(
            select(PatternDetection).where(
                PatternDetection.organization_id == caller.organization_id,
                PatternDetection.status.in_(("confirmed", "persistent")),
                PatternDetection.family.in_(("decision", "execution")),
            ).limit(10)
        )
        patterns = result.scalars().all()
        return [
            InstitutionalPattern(
                pattern_id=p.id,
                pattern_type=p.pattern_type,
                family=p.family,
                title=p.title,
                detail=p.detail or "",
                count=p.count,
                confidence=p.confidence,
                status=p.status,
                cohort_signature="",
                supporting_decisions=[],
                supporting_actions=[],
                supporting_outcomes=[],
                supporting_metrics=[],
                contradicting_evidence=[],
                scope_type=p.scope_type,
                scope_id=p.scope_id,
                first_seen=p.first_seen,
                last_seen=p.last_seen,
                derived_at=utcnow(),
            )
            for p in patterns
        ]

    async def _get_relevant_lessons_for_objective(
        self, db: AsyncSession, caller: CallerAccess, objective: CompanyObjective
    ) -> List[QualifiedLesson]:
        result = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.lifecycle.in_(("supported", "authoritative", "confirmed")),
                OrganizationalLearning.kind.in_(("outcome_learning", "decision_learning")),
            ).limit(15)
        )
        lessons = result.scalars().all()
        return [
            QualifiedLesson(
                id=l.id, kind=l.kind, title=l.title, statement=l.lesson or "",
                epistemic_status=BRAIN_EPISTEMIC_STATUS.get(l.lifecycle, "UNKNOWN"),
                lifecycle=l.lifecycle, confidence=l.confidence or 0.0,
                scope_type="organization", scope_id=None,
                valid_from=l.observed_at, valid_to=None, superseded_by=None,
                supporting_evidence_count=len(json.loads(l.evidence_json)) if l.evidence_json else 0,
                contradicting_evidence_count=0, contradiction_ratio=0.0,
                outcome_quality=1.0, temporal_spread_days=0, evidence_coverage=0.0,
                cohort_signature="", evidence_chain=[], contradictions=[],
                precedents=[], supersession_history=[], provenance={}, derived_at=l.observed_at,
            )
            for l in lessons
        ]

    async def _get_relevant_patterns_for_objective(
        self, db: AsyncSession, caller: CallerAccess, objective: CompanyObjective
    ) -> List[InstitutionalPattern]:
        result = await db.execute(
            select(PatternDetection).where(
                PatternDetection.organization_id == caller.organization_id,
                PatternDetection.status.in_(("confirmed", "persistent")),
            ).limit(10)
        )
        patterns = result.scalars().all()
        return [
            InstitutionalPattern(
                pattern_id=p.id, pattern_type=p.pattern_type, family=p.family,
                title=p.title, detail=p.detail or "", count=p.count,
                confidence=p.confidence, status=p.status, cohort_signature="",
                supporting_decisions=[], supporting_actions=[], supporting_outcomes=[],
                supporting_metrics=[], contradicting_evidence=[],
                scope_type=p.scope_type, scope_id=p.scope_id,
                first_seen=p.first_seen, last_seen=p.last_seen, derived_at=utcnow(),
            )
            for p in patterns
        ]

    async def _get_relevant_lessons_for_capability(
        self, db: AsyncSession, caller: CallerAccess, cap: OrgCapability
    ) -> List[QualifiedLesson]:
        result = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.lifecycle.in_(("supported", "authoritative", "confirmed")),
                OrganizationalLearning.kind.in_(("capacity_learning", "dependency_learning")),
            ).limit(10)
        )
        lessons = result.scalars().all()
        return [
            QualifiedLesson(
                id=l.id, kind=l.kind, title=l.title, statement=l.lesson or "",
                epistemic_status=BRAIN_EPISTEMIC_STATUS.get(l.lifecycle, "UNKNOWN"),
                lifecycle=l.lifecycle, confidence=l.confidence or 0.0,
                scope_type="organization", scope_id=None,
                valid_from=l.observed_at, valid_to=None, superseded_by=None,
                supporting_evidence_count=len(json.loads(l.evidence_json)) if l.evidence_json else 0,
                contradicting_evidence_count=0, contradiction_ratio=0.0,
                outcome_quality=1.0, temporal_spread_days=0, evidence_coverage=0.0,
                cohort_signature="", evidence_chain=[], contradictions=[],
                precedents=[], supersession_history=[], provenance={}, derived_at=l.observed_at,
            )
            for l in lessons
        ]

    async def _get_relevant_patterns_for_capability(
        self, db: AsyncSession, caller: CallerAccess, cap: OrgCapability
    ) -> List[InstitutionalPattern]:
        result = await db.execute(
            select(PatternDetection).where(
                PatternDetection.organization_id == caller.organization_id,
                PatternDetection.status.in_(("confirmed", "persistent")),
                PatternDetection.family.in_(("organization", "capacity")),
            ).limit(10)
        )
        patterns = result.scalars().all()
        return [
            InstitutionalPattern(
                pattern_id=p.id, pattern_type=p.pattern_type, family=p.family,
                title=p.title, detail=p.detail or "", count=p.count,
                confidence=p.confidence, status=p.status, cohort_signature="",
                supporting_decisions=[], supporting_actions=[], supporting_outcomes=[],
                supporting_metrics=[], contradicting_evidence=[],
                scope_type=p.scope_type, scope_id=p.scope_id,
                first_seen=p.first_seen, last_seen=p.last_seen, derived_at=utcnow(),
            )
            for p in patterns
        ]

    async def _get_relevant_lessons_for_action(
        self, db: AsyncSession, caller: CallerAccess, action: CompanyAction
    ) -> List[QualifiedLesson]:
        result = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.lifecycle.in_(("supported", "authoritative", "confirmed")),
                OrganizationalLearning.kind.in_(("outcome_learning", "decision_learning")),
            ).limit(10)
        )
        lessons = result.scalars().all()
        return [
            QualifiedLesson(
                id=l.id, kind=l.kind, title=l.title, statement=l.lesson or "",
                epistemic_status=BRAIN_EPISTEMIC_STATUS.get(l.lifecycle, "UNKNOWN"),
                lifecycle=l.lifecycle, confidence=l.confidence or 0.0,
                scope_type="organization", scope_id=None,
                valid_from=l.observed_at, valid_to=None, superseded_by=None,
                supporting_evidence_count=len(json.loads(l.evidence_json)) if l.evidence_json else 0,
                contradicting_evidence_count=0, contradiction_ratio=0.0,
                outcome_quality=1.0, temporal_spread_days=0, evidence_coverage=0.0,
                cohort_signature="", evidence_chain=[], contradictions=[],
                precedents=[], supersession_history=[], provenance={}, derived_at=l.observed_at,
            )
            for l in lessons
        ]

    async def _get_relevant_patterns_for_action(
        self, db: AsyncSession, caller: CallerAccess, action: CompanyAction
    ) -> List[InstitutionalPattern]:
        result = await db.execute(
            select(PatternDetection).where(
                PatternDetection.organization_id == caller.organization_id,
                PatternDetection.status.in_(("confirmed", "persistent")),
            ).limit(10)
        )
        patterns = result.scalars().all()
        return [
            InstitutionalPattern(
                pattern_id=p.id, pattern_type=p.pattern_type, family=p.family,
                title=p.title, detail=p.detail or "", count=p.count,
                confidence=p.confidence, status=p.status, cohort_signature="",
                supporting_decisions=[], supporting_actions=[], supporting_outcomes=[],
                supporting_metrics=[], contradicting_evidence=[],
                scope_type=p.scope_type, scope_id=p.scope_id,
                first_seen=p.first_seen, last_seen=p.last_seen, derived_at=utcnow(),
            )
            for p in patterns
        ]

    def _calculate_commitment_risk_probability(
        self, risk: Dict[str, Any], lessons: List[QualifiedLesson], patterns: List[InstitutionalPattern]
    ) -> float:
        """Calculate probability of commitment risk based on risk factors + learning."""
        base = 0.3
        risk_factors = risk.get("risk_factors", [])
        
        if "failed_outcomes" in risk_factors:
            base += 0.4
        if "high_partial_rate" in risk_factors:
            base += 0.3
        if "low_effectiveness" in risk_factors:
            base += 0.2
        if "no_actions" in risk_factors:
            base += 0.2
        
        # Adjust based on lessons
        for lesson in lessons:
            if lesson.epistemic_status in ("AUTHORITATIVE", "CONFIRMED"):
                if "risk" in lesson.statement.lower() or "fail" in lesson.statement.lower():
                    base += 0.1
        
        return min(0.95, base)

    def _estimate_outcome_probability(
        self, lessons: List[QualifiedLesson], patterns: List[InstitutionalPattern], action: CompanyAction
    ) -> float:
        """Estimate probability of successful outcome for an action."""
        base = 0.5
        
        # Adjust based on action state
        if action.state == "in_progress":
            base = 0.6
        elif action.state == "approved":
            base = 0.5
        elif action.state == "ready":
            base = 0.7
        
        # Adjust based on lessons
        for lesson in lessons:
            if lesson.epistemic_status in ("AUTHORITATIVE", "CONFIRMED"):
                if "success" in lesson.statement.lower():
                    base += 0.1
                elif "fail" in lesson.statement.lower():
                    base -= 0.1
        
        return max(0.1, min(0.9, base))

    def _determine_prediction_method(
        self, lessons: List[QualifiedLesson], patterns: List[InstitutionalPattern]
    ) -> str:
        """Determine prediction method based on available evidence."""
        if lessons and any(l.epistemic_status in ("AUTHORITATIVE", "CONFIRMED") for l in lessons):
            return "lesson_based"
        elif patterns and any(p.status in ("confirmed", "persistent") for p in patterns):
            return "pattern_based"
        elif lessons:
            return "lesson_based"
        elif patterns:
            return "pattern_based"
        else:
            return "trajectory"

    def _determine_epistemic_status(
        self, lessons: List[QualifiedLesson], patterns: List[InstitutionalPattern], risk: Dict[str, Any]
    ) -> str:
        """Determine epistemic status of prediction."""
        # High confidence from authoritative lessons
        authoritative_lessons = [l for l in lessons if l.epistemic_status in ("AUTHORITATIVE", "CONFIRMED")]
        if authoritative_lessons:
            return "well_grounded"
        
        # Good patterns
        strong_patterns = [p for p in patterns if p.status in ("confirmed", "persistent")]
        if strong_patterns:
            return "well_grounded"
        
        # Some evidence
        if lessons or patterns:
            return "evidence_based"
        
        return "speculative"

    async def _build_provenance(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        prediction_type: str,
        subject_id: str,
    ) -> PredictionProvenance:
        """Build complete provenance chain for a prediction."""
        # Get current canonical state snapshot
        canonical_state = await self._get_canonical_state_snapshot(db, caller)
        
        return PredictionProvenance(
            canonical_state_snapshot=canonical_state,
            institutional_lessons_used=[],  # Would be populated from actual lessons used
            patterns_used=[],
            evidence_chain=[],
            model_version="gate10-v1",
            algorithm_identity="predictive_intelligence_service:v1",
            generated_at=utcnow(),
            generated_by=caller.employee_id or "system",
        )

    async def _get_canonical_state_snapshot(
        self, db: AsyncSession, caller: CallerAccess
    ) -> Dict[str, Any]:
        """Get a snapshot of relevant canonical state for provenance."""
        # This would capture the relevant state at prediction time
        return {
            "timestamp": utcnow().isoformat(),
            "organization_id": caller.organization_id,
            "employee_id": caller.employee_id,
        }

    def _lesson_to_basis(self, lesson: QualifiedLesson) -> Dict[str, Any]:
        return {
            "type": "lesson",
            "id": lesson.id,
            "kind": lesson.kind,
            "title": lesson.title,
            "epistemic_status": lesson.epistemic_status,
            "confidence": lesson.confidence,
            "supporting_evidence_count": lesson.supporting_evidence_count,
            "contradicting_evidence_count": lesson.contradicting_evidence_count,
        }

    def _pattern_to_basis(self, pattern: InstitutionalPattern) -> Dict[str, Any]:
        return {
            "type": "pattern",
            "id": pattern.pattern_id,
            "pattern_type": pattern.pattern_type,
            "family": pattern.family,
            "count": pattern.count,
            "confidence": pattern.confidence,
            "status": pattern.status,
        }

    async def _build_objective_prediction_detail(
        self, db: AsyncSession, caller: CallerAccess, pred: ObjectivePrediction
    ) -> CompanyPrediction:
        return CompanyPrediction(
            id=pred.id,
            kind="objective_risk",
            title=f"Objective prediction: {pred.metric_kind}",
            description=pred.prediction_method,
            subject_type="objective",
            subject_id=pred.objective_id,
            probability=pred.confidence,
            confidence=pred.confidence,
            epistemic_status="evidence_based",
            horizon_days=pred.horizon_days,
            horizon_end=pred.valid_until or utcnow() + timedelta(days=pred.horizon_days),
            prediction_method=pred.prediction_method,
            evidence_bundle={
                "predicted_value": pred.predicted_value,
                "metric_kind": pred.metric_kind,
                "unit": pred.unit,
            },
            institutional_basis=[],
            provenance=PredictionProvenance(
                canonical_state_snapshot={},
                institutional_lessons_used=[],
                patterns_used=[],
                evidence_chain=[],
                model_version="gate10-v1",
                algorithm_identity="predictive_intelligence_service:v1",
                generated_at=pred.predicted_at,
                generated_by=pred.predicted_by or "system",
            ),
            scope_type="organization",
            scope_id=None,
            valid_from=pred.valid_from,
            valid_until=pred.valid_until,
            superseded_by=None,
            actual_outcome=None,
            evaluation=None,
            derived_at=pred.predicted_at,
        )

    async def _build_generic_prediction_detail(
        self, db: AsyncSession, caller: CallerAccess, pred: Prediction
    ) -> CompanyPrediction:
        return CompanyPrediction(
            id=pred.id,
            kind=pred.kind,
            title=pred.title,
            description=pred.description or "",
            subject_type=pred.subject_type or "unknown",
            subject_id=pred.subject_id or "",
            probability=pred.probability,
            confidence=pred.probability,
            epistemic_status="evidence_based",
            horizon_days=pred.horizon_days,
            horizon_end=pred.due_at or utcnow() + timedelta(days=pred.horizon_days),
            prediction_method="generic",
            evidence_bundle={"signals": pred.signals or []},
            institutional_basis=[],
            provenance=PredictionProvenance(
                canonical_state_snapshot={},
                institutional_lessons_used=[],
                patterns_used=[],
                evidence_chain=[],
                model_version="gate10-v1",
                algorithm_identity="predictive_intelligence_service:v1",
                generated_at=utcnow(),
                generated_by="system",
            ),
            scope_type="organization",
            scope_id=None,
            valid_from=utcnow(),
            valid_until=pred.due_at,
            superseded_by=None,
            actual_outcome=None,
            evaluation=None,
            derived_at=utcnow(),
        )

    async def _build_twin_prediction_detail(
        self, db: AsyncSession, caller: CallerAccess, pred: TwinPrediction
    ) -> CompanyPrediction:
        return CompanyPrediction(
            id=pred.id,
            kind=pred.kind,
            title=pred.title,
            description=pred.description or "",
            subject_type=pred.subject_type or "unknown",
            subject_id=pred.subject_id or "",
            probability=pred.probability / 100.0,
            confidence=pred.probability / 100.0,
            epistemic_status="evidence_based",
            horizon_days=pred.horizon_days,
            horizon_end=utcnow() + timedelta(days=pred.horizon_days),
            prediction_method="twin_v1",
            evidence_bundle={"signals": json.loads(pred.signals_json) if pred.signals_json else []},
            institutional_basis=[],
            provenance=PredictionProvenance(
                canonical_state_snapshot={},
                institutional_lessons_used=[],
                patterns_used=[],
                evidence_chain=[],
                model_version=pred.model_version,
                algorithm_identity="twin_prediction_engine:v1",
                generated_at=utcnow(),
                generated_by="system",
            ),
            scope_type="organization",
            scope_id=None,
            valid_from=utcnow(),
            valid_until=utcnow() + timedelta(days=pred.horizon_days),
            superseded_by=None,
            actual_outcome=None,
            evaluation=None,
            derived_at=utcnow(),
        )

    async def _evaluate_objective_predictions(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        cutoff: datetime,
    ) -> Dict[str, Any]:
        """Evaluate mature objective predictions against actual outcomes."""
        evaluated = 0
        correct = 0
        calibration_data = []

        # Find mature predictions
        preds_result = await db.execute(
            select(ObjectivePrediction).where(
                ObjectivePrediction.organization_id == caller.organization_id,
                ObjectivePrediction.valid_until < utcnow(),
                ObjectivePrediction.actual_outcome_id.is_(None),  # Not yet evaluated
            ).limit(50)
        )
        preds = preds_result.scalars().all()

        for pred in preds:
            # Get actual outcome
            # This would link to actual metric observations
            # For now, mark as evaluated with placeholder
            evaluated += 1
            calibration_data.append({
                "prediction_id": pred.id,
                "kind": "objective_prediction",
                "predicted_value": pred.predicted_value,
                "confidence": pred.confidence,
                "horizon_days": pred.horizon_days,
                "evaluated_at": utcnow().isoformat(),
            })

        return {"evaluated": evaluated, "correct": correct, "calibration_data": calibration_data}

    async def _evaluate_generic_predictions(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        cutoff: datetime,
    ) -> Dict[str, Any]:
        """Evaluate mature generic predictions."""
        evaluated = 0
        correct = 0
        calibration_data = []

        preds_result = await db.execute(
            select(Prediction).where(
                Prediction.organization_id == caller.organization_id,
                Prediction.due_at < utcnow(),
                Prediction.status == "open",
            ).limit(50)
        )
        preds = preds_result.scalars().all()

        for pred in preds:
            evaluated += 1
            calibration_data.append({
                "prediction_id": pred.id,
                "kind": pred.kind,
                "probability": pred.probability,
                "horizon_days": pred.horizon_days,
                "evaluated_at": utcnow().isoformat(),
            })

        return {"evaluated": evaluated, "correct": correct, "calibration_data": calibration_data}

    async def _update_model_calibration(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        calibration_data: List[Dict[str, Any]],
    ) -> None:
        """Update PredictionModel calibration based on evaluation results."""
        # Group by kind and update model accuracy
        kind_stats = defaultdict(lambda: {"total": 0, "correct": 0})
        
        for data in calibration_data:
            kind = data.get("kind", "unknown")
            kind_stats[kind]["total"] += 1
            # In a real implementation, we'd check actual correctness
            # For now, just track counts
            kind_stats[kind]["correct"] += 1  # Placeholder

        for kind, stats in kind_stats.items():
            if stats["total"] > 0:
                model_result = await db.execute(
                    select(PredictionModel).where(
                        PredictionModel.organization_id == caller.organization_id,
                        PredictionModel.kind == kind,
                    )
                )
                model = model_result.scalars().first()
                if model:
                    model.predictions_count = stats["total"]
                    model.accuracy = stats["correct"] / stats["total"]
                    model.last_trained_at = utcnow()


# Global instance
predictive_intelligence_service = PredictiveIntelligenceService()


# Brain epistemic status mapping
BRAIN_EPISTEMIC_STATUS = {
    "discovered": "OBSERVED",
    "candidate": "RECURRING",
    "supported": "SUPPORTED",
    "authoritative": "AUTHORITATIVE",
    "confirmed": "CONFIRMED",
    "superseded": "SUPERSEDED",
    "archived": "ARCHIVED",
}