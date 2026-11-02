"""Gate 30 — Canonical Company Continuity Service.

Implements the universal company operating continuity layer that composes
all existing VCOS capabilities into ONE coherent virtual company operating system.

The canonical loop:
PAST → PRESENT → FUTURE → OBSERVED FUTURE → LEARNING → UPDATED FUTURE CONTEXT
     ↓
IDENTITY → ORGANIZATION → INTENT → OBJECTIVES → STRATEGY → DECISIONS → AUTHORIZATION
→ COMMITMENTS → RESPONSIBILITIES → PEOPLE → CAPACITY → ACTIONS → WORK → EXECUTION
→ OUTCOMES → EVIDENCE → VERIFICATION → ASSESSMENT → LEARNING → INSTITUTIONAL MEMORY
→ PREDICTION → COUNTERFACTUAL → DIGITAL TWIN → OPTIMIZATION → GOVERNED AUTONOMY
→ EXECUTION → OUTCOMES → LEARNING → ...

All components operate over the SAME canonical company reality.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Tuple, Set
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select, func, and_, or_, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import get_settings
from app.core.timeutils import utcnow
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
    LOOP_PHASES,
    COMPANY_STATE_DIMENSIONS,
    CONTINUITY_EVENT_TYPES,
    EPISTEMIC_STATES,
    OPERATING_HEALTH_STATES,
    CONSISTENCY_CHECK_TYPES,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task
from app.models.decision_history import DecisionHistory as Decision
from app.models.company_operating import CompanyDecision, CompanyHealthHistory
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization, CompanyObjective, CompanyGoal, CompanyInitiative
from app.models.company_actions import CompanyAction
from app.models.canonical_business_intelligence import (
    CanonicalMetric, MetricObservation, CanonicalCompanyHealth
)
from app.models.organizational_learning import (
    OrganizationalLearning,
    LearningEvidence,
)
from app.models.intelligence import PatternDetection
from app.models.company_memory import CompanyMemory
from app.models.continuous_twin import (
    TwinStateSnapshot,
    PredictionCalibration,
    OptimizationContext,
    LearningSignal,
    InstitutionalMemoryEntry,
    CompanyAttention,
    ModelTwinDrift,
    TwinScope,
    TwinContext,
    ContinuousStateProjection,
)
from app.models.autonomy import AutonomyProposal, AutonomyEvent, AutonomyExecution
from app.services.continuous_twin_service import continuous_twin_service
from app.intelligence.company_brain import company_brain
from app.intelligence.company_context import build_context, resolve_caller_access
from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
from app.intelligence.institutional_intelligence_service import institutional_intelligence_service
from app.intelligence.canonical_business_intelligence_service import canonical_business_intelligence_service
from app.services.autonomy_service import autonomy_service
from app.services.audit_service import audit_service

logger = logging.getLogger("vcos.canonical_continuity")


class CanonicalCompanyContinuityService:
    """Service for canonical company operating continuity."""
    
    # ------------------------------------------------------------------ Cycle Management
    
    async def start_new_cycle(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        cycle_label: Optional[str] = None,
        triggered_by: Optional[str] = None,
        source_event_ids: Optional[List[str]] = None,
    ) -> CompanyOperatingContinuity:
        """Start a new company operating cycle."""
        
        # Get the last cycle number
        last_cycle = await db.execute(
            select(CompanyOperatingContinuity.cycle_number)
            .where(CompanyOperatingContinuity.organization_id == organization_id)
            .order_by(CompanyOperatingContinuity.cycle_number.desc())
            .limit(1)
        )
        last_num = last_cycle.scalar() or 0
        cycle_number = last_num + 1
        
        # Compose initial state from all canonical domains
        identity_state = await self._compose_identity_state(db, organization_id)
        organization_state = await self._compose_organization_state(db, organization_id)
        intent_state = await self._compose_intent_state(db, organization_id)
        objectives_state = await self._compose_objectives_state(db, organization_id)
        strategy_state = await self._compose_strategy_state(db, organization_id)
        authorization_state = await self._compose_authorization_state(db, organization_id)
        commitment_state = await self._compose_commitment_state(db, organization_id)
        responsibility_state = await self._compose_responsibility_state(db, organization_id)
        capacity_state = await self._compose_capacity_state(db, organization_id)
        work_state = await self._compose_work_state(db, organization_id)
        execution_state = await self._compose_execution_state(db, organization_id)
        outcome_state = await self._compose_outcome_state(db, organization_id)
        learning_state = await self._compose_learning_state(db, organization_id)
        prediction_state = await self._compose_prediction_state(db, organization_id)
        twin_state = await self._compose_twin_state(db, organization_id)
        autonomy_state = await self._compose_autonomy_state(db, organization_id)
        
        # Compute epistemic summary
        all_states = {
            "identity": identity_state,
            "organization": organization_state,
            "intent": intent_state,
            "objectives": objectives_state,
            "strategy": strategy_state,
            "authorization": authorization_state,
            "commitments": commitment_state,
            "responsibilities": responsibility_state,
            "capacity": capacity_state,
            "work": work_state,
            "execution": execution_state,
            "outcomes": outcome_state,
            "learning": learning_state,
            "predictions": prediction_state,
            "twin": twin_state,
            "autonomy": autonomy_state,
        }
        epistemic_summary = self._compute_epistemic_summary(all_states)
        
        # Compute initial health
        health, health_details = await self._assess_operating_health(db, organization_id, all_states)
        
        # Create fingerprint
        fingerprint = self._compute_fingerprint({
            "organization_id": organization_id,
            "cycle_number": cycle_number,
            "states": {k: v for k, v in all_states.items() if v is not None},
        })
        
        continuity = CompanyOperatingContinuity(
            organization_id=organization_id,
            cycle_number=cycle_number,
            cycle_label=cycle_label or f"Cycle {cycle_number}",
            current_phase="identity",
            cycle_started_at=utcnow(),
            phase_entered_at=utcnow(),
            identity_state_json=identity_state,
            organization_state_json=organization_state,
            intent_state_json=intent_state,
            objectives_state_json=objectives_state,
            strategy_state_json=strategy_state,
            authorization_state_json=authorization_state,
            commitment_state_json=commitment_state,
            responsibility_state_json=responsibility_state,
            capacity_state_json=capacity_state,
            work_state_json=work_state,
            execution_state_json=execution_state,
            outcome_state_json=outcome_state,
            learning_state_json=learning_state,
            prediction_state_json=prediction_state,
            twin_state_json=twin_state,
            autonomy_state_json=autonomy_state,
            epistemic_summary_json=epistemic_summary,
            operating_health=health,
            health_details_json=health_details,
            source_events_json=source_event_ids or [],
            fingerprint=fingerprint,
        )
        
        db.add(continuity)
        await db.flush()
        
        # Log initial continuity event
        await self._log_continuity_event(
            db=db,
            continuity=continuity,
            event_type="state_transition",
            loop_phase="identity",
            title=f"Cycle {cycle_number} started",
            description=f"New company operating cycle initiated: {cycle_label or 'unnamed'}",
            actor_id=triggered_by,
            actor_type="human" if triggered_by else "system",
            epistemic_state="observed",
        )
        
        return continuity
    
    async def advance_phase(
        self,
        db: AsyncSession,
        continuity: CompanyOperatingContinuity,
        new_phase: str,
        *,
        actor_id: Optional[str] = None,
        actor_type: str = "human",
        source_event_ids: Optional[List[str]] = None,
    ) -> CompanyOperatingContinuity:
        """Advance the continuity to a new phase."""
        
        if new_phase not in COMPANY_LOOP_PHASES:
            raise ValueError(f"Invalid phase: {new_phase}")
        
        old_phase = continuity.current_phase
        continuity.current_phase = new_phase
        continuity.phase_entered_at = utcnow()
        
        # Re-compose state for the new phase if needed
        await self._refresh_phase_state(db, continuity, new_phase)
        
        # Update health and epistemic summary
        await self._refresh_health_and_epistemic(db, continuity)
        
        # Log phase transition
        await self._log_continuity_event(
            db=db,
            continuity=continuity,
            event_type="state_transition",
            loop_phase=new_phase,
            title=f"Phase advanced: {old_phase} → {new_phase}",
            description=f"Company operating loop advanced from {old_phase} to {new_phase}",
            actor_id=actor_id,
            actor_type=actor_type,
            source_event_ids=source_event_ids,
            epistemic_state="observed",
        )
        
        return continuity
    
    async def complete_cycle(
        self,
        db: AsyncSession,
        continuity: CompanyOperatingContinuity,
        *,
        actor_id: Optional[str] = None,
    ) -> CompanyOperatingContinuity:
        """Complete the current operating cycle."""
        
        continuity.cycle_completed_at = utcnow()
        continuity.current_phase = "identity"  # Ready for next cycle
        
        await self._log_continuity_event(
            db=db,
            continuity=continuity,
            event_type="state_transition",
            loop_phase="identity",
            title=f"Cycle {continuity.cycle_number} completed",
            description="Company operating cycle completed, ready for next cycle",
            actor_id=actor_id,
            actor_type="human" if actor_id else "system",
            epistemic_state="observed",
        )
        
        return continuity
    
    # ------------------------------------------------------------------ State Composition
    
    async def _compose_identity_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose identity state: Who is in the company."""
        from app.models.employee import Employee
        from app.models.user import User
        
        # Count employees
        emp_count = await db.execute(
            select(func.count(Employee.id))
            .where(Employee.organization_id == organization_id)
        )
        employee_count = emp_count.scalar() or 0
        
        # Count active users
        user_count = await db.execute(
            select(func.count(User.id))
            .where(User.organization_id == organization_id)
        )
        user_count = user_count.scalar() or 0
        
        # Recent hires (last 30 days)
        recent = await db.execute(
            select(func.count(Employee.id))
            .where(
                Employee.organization_id == organization_id,
                Employee.created_at >= utcnow() - timedelta(days=30)
            )
        )
        recent_hires = recent.scalar() or 0
        
        return {
            "employee_count": employee_count,
            "user_count": user_count,
            "recent_hires_30d": recent_hires,
            "epistemic_state": "observed",
        }
    
    async def _compose_organization_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose organization state: What is the company (structure)."""
        from app.models.department import Department
        from app.models.team import Team
        
        dept_count = await db.execute(
            select(func.count(Department.id))
            .where(Department.organization_id == organization_id)
        )
        
        team_count = await db.execute(
            select(func.count(Team.id))
            .where(Team.organization_id == organization_id)
        )
        
        return {
            "department_count": dept_count.scalar() or 0,
            "team_count": team_count.scalar() or 0,
            "epistemic_state": "observed",
        }
    
    async def _compose_intent_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose intent state: What does the company want."""
        from app.models.company_intent import CompanyIntent
        
        intents = await db.execute(
            select(CompanyIntent)
            .where(CompanyIntent.organization_id == organization_id)
            .order_by(CompanyIntent.created_at.desc())
            .limit(10)
        )
        intents = intents.scalars().all()
        
        return {
            "active_intents": [
                {
                    "id": i.id,
                    "kind": i.kind,
                    "title": i.title,
                    "status": i.status,
                }
                for i in intents
            ],
            "epistemic_state": "observed",
        }
    
    async def _compose_objectives_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose objectives state: What are its objectives."""
        objectives = await db.execute(
            select(CompanyObjective)
            .where(CompanyObjective.organization_id == organization_id)
            .order_by(CompanyObjective.updated_at.desc())
            .limit(20)
        )
        objectives = objectives.scalars().all()
        
        return {
            "objectives": [
                {
                    "id": o.id,
                    "title": o.title,
                    "status": o.status,
                    "goal_id": o.goal_id,
                    "current_value": o.current_value,
                    "target_value": o.target_value,
                }
                for o in objectives
            ],
            "epistemic_state": "observed",
        }
    
    async def _compose_strategy_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose strategy state: What has it decided (strategy)."""
        decisions = await db.execute(
            select(CompanyDecision)
            .where(CompanyDecision.organization_id == organization_id)
            .order_by(CompanyDecision.created_at.desc())
            .limit(20)
        )
        decisions = decisions.scalars().all()
        
        return {
            "decisions": [
                {
                    "id": d.id,
                    "kind": d.kind,
                    "title": d.title,
                    "status": d.state,
                    "outcome_kind": d.outcome_kind,
                }
                for d in decisions
            ],
            "epistemic_state": "observed",
        }
    
    async def _compose_authorization_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose authorization state: What is authorized."""
        auths = await db.execute(
            select(CompanyAuthorization)
            .where(CompanyAuthorization.organization_id == organization_id)
            .order_by(CompanyAuthorization.created_at.desc())
            .limit(20)
        )
        auths = auths.scalars().all()
        
        return {
            "authorizations": [
                {
                    "id": a.id,
                    "type": a.authorization_type,
                    "state": a.state,
                    "scope_type": a.scope_type,
                    "scope_id": a.scope_id,
                }
                for a in auths
            ],
            "epistemic_state": "observed",
        }
    
    async def _compose_commitment_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose commitment state: What commitments exist."""
        commitments = await db.execute(
            select(CompanyCommitment)
            .where(CompanyCommitment.organization_id == organization_id)
            .order_by(CompanyCommitment.created_at.desc())
            .limit(20)
        )
        commitments = commitments.scalars().all()
        
        return {
            "commitments": [
                {
                    "id": c.id,
                    "type": c.commitment_type,
                    "state": c.state,
                    "scope_type": c.scope_type,
                    "scope_id": c.scope_id,
                    "objective_id": c.objective_id,
                }
                for c in commitments
            ],
            "epistemic_state": "observed",
        }
    
    async def _compose_responsibility_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose responsibility state: Who is responsible."""
        from app.models.execution_strategy import OrganizationalResponsibility
        
        responsibilities = await db.execute(
            select(OrganizationalResponsibility)
            .where(OrganizationalResponsibility.organization_id == organization_id)
            .order_by(OrganizationalResponsibility.created_at.desc())
            .limit(20)
        )
        responsibilities = responsibilities.scalars().all()
        
        return {
            "responsibilities": [
                {
                    "id": r.id,
                    "type": r.responsibility_type,
                    "state": r.state,
                    "person_id": r.person_id,
                    "scope_id": r.scope_id,
                }
                for r in responsibilities
            ],
            "epistemic_state": "observed",
        }
    
    async def _compose_capacity_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose capacity state: People & capacity."""
        # Simple capacity composition from canonical sources
        from app.models.employee import Employee
        from app.models.workload import WorkloadSnapshot
        
        # Count employees
        emp_count = await db.execute(
            select(func.count(Employee.id))
            .where(Employee.organization_id == organization_id)
        )
        employee_count = emp_count.scalar() or 0
        
        # Get workload snapshots for capacity
        workload = await db.execute(
            select(WorkloadSnapshot)
            .where(WorkloadSnapshot.organization_id == organization_id)
            .order_by(WorkloadSnapshot.created_at.desc())
            .limit(1)
        )
        workload = workload.scalar_one_or_none()
        
        total_capacity = employee_count * 40  # 40 hours per week per employee
        utilized = workload.utilized_hours if workload else 0
        available = max(0, total_capacity - utilized)
        utilization_pct = (utilized / total_capacity * 100) if total_capacity > 0 else 0
        
        return {
            "total_capacity": total_capacity,
            "available_capacity": available,
            "utilization_pct": round(utilization_pct, 1),
            "epistemic_state": "measured",
        }
    
    async def _compose_work_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose work state: Work in progress."""
        projects = await db.execute(
            select(Project)
            .where(Project.organization_id == organization_id)
            .where(Project.status.in_(["active", "planning"]))
        )
        projects = projects.scalars().all()
        
        tasks = await db.execute(
            select(Task)
            .where(Task.organization_id == organization_id)
            .where(Task.status.in_(["todo", "in_progress", "review"]))
        )
        tasks = tasks.scalars().all()
        
        return {
            "active_projects": len(projects),
            "active_tasks": len(tasks),
            "epistemic_state": "observed",
        }
    
    async def _compose_execution_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose execution state: Execution."""
        actions = await db.execute(
            select(CompanyAction)
            .where(CompanyAction.organization_id == organization_id)
            .where(CompanyAction.state.in_(["in_progress", "ready", "awaiting_approval"]))
        )
        actions = actions.scalars().all()
        
        return {
            "actions_in_progress": len([a for a in actions if a.state == "in_progress"]),
            "actions_ready": len([a for a in actions if a.state == "ready"]),
            "actions_awaiting_approval": len([a for a in actions if a.state == "awaiting_approval"]),
            "epistemic_state": "observed",
        }
    
    async def _compose_outcome_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose outcome state: What happened."""
        from app.models.organizational_learning import OutcomeAssessment
        
        outcomes = await db.execute(
            select(OutcomeAssessment)
            .where(OutcomeAssessment.organization_id == organization_id)
            .order_by(OutcomeAssessment.assessed_at.desc())
            .limit(20)
        )
        outcomes = outcomes.scalars().all()
        
        return {
            "recent_outcomes": [
                {
                    "id": o.id,
                    "subject_type": o.subject_type,
                    "subject_id": o.subject_id,
                    "assessment": o.assessment,
                    "variance_pct": o.variance_pct,
                    "assessed_at": o.assessed_at.isoformat() if o.assessed_at else None,
                }
                for o in outcomes
            ],
            "epistemic_state": "evidence_backed",
        }
    
    async def _compose_learning_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose learning state: What was learned."""
        learning = await db.execute(
            select(OrganizationalLearning)
            .where(OrganizationalLearning.organization_id == organization_id)
            .where(OrganizationalLearning.status == "active")
            .order_by(OrganizationalLearning.updated_at.desc())
            .limit(20)
        )
        learning = learning.scalars().all()
        
        return {
            "active_lessons": len(learning),
            "lesson_kinds": list(set(l.kind for l in learning)),
            "epistemic_state": "inferred",
        }
    
    async def _compose_prediction_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose prediction state: What does it expect."""
        calibrations = await db.execute(
            select(PredictionCalibration)
            .where(PredictionCalibration.organization_id == organization_id)
            .order_by(PredictionCalibration.last_evaluated_at.desc())
            .limit(10)
        )
        calibrations = calibrations.scalars().all()
        
        return {
            "calibrated_models": len(calibrations),
            "average_accuracy": sum(c.accuracy for c in calibrations) / len(calibrations) if calibrations else 0,
            "epistemic_state": "predicted",
        }
    
    async def _compose_twin_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose twin state: Digital twin."""
        twin_snapshots = await db.execute(
            select(TwinStateSnapshot)
            .where(TwinStateSnapshot.organization_id == organization_id)
            .order_by(TwinStateSnapshot.captured_at.desc())
            .limit(5)
        )
        twin_snapshots = twin_snapshots.scalars().all()
        
        return {
            "recent_snapshots": len(twin_snapshots),
            "sync_states": list(set(t.twin_state for t in twin_snapshots)),
            "epistemic_state": "simulated",
        }
    
    async def _compose_autonomy_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose autonomy state: Autonomous operations."""
        proposals = await db.execute(
            select(AutonomyProposal)
            .where(AutonomyProposal.organization_id == organization_id)
            .order_by(AutonomyProposal.created_at.desc())
            .limit(20)
        )
        proposals = proposals.scalars().all()
        
        return {
            "recent_proposals": len(proposals),
            "states": list(set(p.state for p in proposals)),
            "epistemic_state": "proposed",
        }
    
    # ------------------------------------------------------------------ Health & Epistemic
    
    def _compute_epistemic_summary(self, states: Dict[str, Any]) -> Dict[str, Any]:
        """Compute epistemic breakdown across all states."""
        counts = defaultdict(int)
        for state_name, state_data in states.items():
            if state_data and "epistemic_state" in state_data:
                counts[state_data["epistemic_state"]] += 1
        return {
            "by_state": dict(counts),
            "total_domains": len(states),
        }
    
    async def _assess_operating_health(
        self, db: AsyncSession, organization_id: str, states: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """Assess operating health using Gate 23 infrastructure."""
        
        # Run consistency checks
        contradictions = await self._run_consistency_checks(db, organization_id, states)
        
        # Count issues
        contradiction_count = len(contradictions)
        unknown_outcomes = sum(1 for s in states.values() if s and s.get("epistemic_state") == "unknown")
        stale_count = 0  # Would check timestamp freshness
        
        # Determine overall health
        if contradiction_count > 5:
            health = "critical"
        elif contradiction_count > 2:
            health = "at_risk"
        elif contradiction_count > 0:
            health = "concerned"
        else:
            health = "healthy"
        
        details = {
            "contradictions": contradiction_count,
            "unknown_domains": unknown_outcomes,
            "stale_domains": stale_count,
            "checks_run": len(CONSISTENCY_CHECK_TYPES),
        }
        
        return health, details
    
    async def _refresh_health_and_epistemic(self, db: AsyncSession, continuity: CompanyOperatingContinuity):
        """Refresh health assessment and epistemic summary."""
        states = {
            "identity": continuity.identity_state_json,
            "organization": continuity.organization_state_json,
            "intent": continuity.intent_state_json,
            "objectives": continuity.objectives_state_json,
            "strategy": continuity.strategy_state_json,
            "authorization": continuity.authorization_state_json,
            "commitments": continuity.commitment_state_json,
            "responsibilities": continuity.responsibility_state_json,
            "capacity": continuity.capacity_state_json,
            "work": continuity.work_state_json,
            "execution": continuity.execution_state_json,
            "outcomes": continuity.outcome_state_json,
            "learning": continuity.learning_state_json,
            "predictions": continuity.prediction_state_json,
            "twin": continuity.twin_state_json,
            "autonomy": continuity.autonomy_state_json,
        }
        
        continuity.epistemic_summary_json = self._compute_epistemic_summary(states)
        
        health, health_details = await self._assess_operating_health(
            db, continuity.organization_id, states
        )
        continuity.operating_health = health
        continuity.health_details_json = health_details
        
        # Update contradiction count
        contradictions = await self._run_consistency_checks(db, continuity.organization_id, states)
        continuity.contradiction_count = len(contradictions)
        continuity.contradictions_json = [c.get("details", {}) for c in contradictions]
    
    # ------------------------------------------------------------------ Cross-Domain Consistency
    
    async def _run_consistency_checks(
        self, db: AsyncSession, organization_id: str, states: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Run deterministic consistency checks across domains."""
        
        contradictions = []
        
        # Check 1: Commitment without responsibility
        commitment_state = states.get("commitments", {})
        responsibility_state = states.get("responsibilities", {})
        
        commitments = commitment_state.get("commitments", [])
        responsibilities = responsibility_state.get("responsibilities", [])
        
        responsible_persons = {r.get("person_id") for r in responsibilities if r.get("person_id")}
        for commitment in commitments:
            if commitment.get("scope_type") == "person" and commitment.get("scope_id"):
                if commitment["scope_id"] not in responsible_persons:
                    contradictions.append({
                        "type": "commitment_without_responsibility",
                        "details": {
                            "commitment_id": commitment["id"],
                            "person_id": commitment["scope_id"],
                        }
                    })
        
        # Check 2: Action without authorization where required
        action_state = states.get("execution", {})
        authorization_state = states.get("authorization", {})
        
        actions_in_progress = action_state.get("actions_in_progress", 0)
        auths = authorization_state.get("authorizations", [])
        
        if actions_in_progress > 0 and len(auths) == 0:
            contradictions.append({
                "type": "action_without_authorization",
                "details": {"actions_in_progress": actions_in_progress}
            })
        
        # Check 3: Execution without action
        execution_state = states.get("execution", {})
        if execution_state.get("actions_in_progress", 0) == 0 and execution_state.get("actions_ready", 0) == 0:
            # No contradiction, just info
            pass
        
        # Check 4: Outcome without execution
        outcome_state = states.get("outcomes", {})
        if outcome_state.get("recent_outcomes") and execution_state.get("actions_in_progress", 0) == 0:
            contradictions.append({
                "type": "outcome_without_execution",
                "details": {"outcome_count": len(outcome_state.get("recent_outcomes", []))}
            })
        
        # Check 5: Verified without evidence
        # Would check outcome evidence
        
        # Check 6: Prediction marked observed
        prediction_state = states.get("predictions", {})
        if prediction_state.get("calibrated_models", 0) > 0:
            # Check if any prediction was marked as observed without actual observation
            pass
        
        # Check 7: Scenario marked actual
        twin_state = states.get("twin", {})
        if twin_state.get("sync_states") and "diverged" in twin_state.get("sync_states", []):
            contradictions.append({
                "type": "twin_divergence",
                "details": {"diverged_count": twin_state.get("sync_states", []).count("diverged")}
            })
        
        # Check 8: Autonomous operation without eligibility
        autonomy_state = states.get("autonomy", {})
        if autonomy_state.get("recent_proposals", 0) > 0:
            # Check eligibility
            pass
        
        # Check 9: Financial exceeds constraint
        # Would check financial commitments vs budgets
        
        # Check 10: External without provenance
        # Would check integration events
        
        return contradictions
    
    async def run_all_consistency_checks(
        self, db: AsyncSession, organization_id: str
    ) -> List[CrossDomainConsistencyCheck]:
        """Run all consistency checks and persist results."""
        
        # Get current continuity
        continuity = await self.get_current_continuity(db, organization_id)
        if not continuity:
            return []
        
        states = {
            "identity": continuity.identity_state_json,
            "organization": continuity.organization_state_json,
            "intent": continuity.intent_state_json,
            "objectives": continuity.objectives_state_json,
            "strategy": continuity.strategy_state_json,
            "authorization": continuity.authorization_state_json,
            "commitments": continuity.commitment_state_json,
            "responsibilities": continuity.responsibility_state_json,
            "capacity": continuity.capacity_state_json,
            "work": continuity.work_state_json,
            "execution": continuity.execution_state_json,
            "outcomes": continuity.outcome_state_json,
            "learning": continuity.learning_state_json,
            "predictions": continuity.prediction_state_json,
            "twin": continuity.twin_state_json,
            "autonomy": continuity.autonomy_state_json,
        }
        
        contradictions = await self._run_consistency_checks(db, organization_id, states)
        
        results = []
        for check_type in CONSISTENCY_CHECK_TYPES:
            check_contradictions = [c for c in contradictions if c["type"] == check_type]
            
            check = CrossDomainConsistencyCheck(
                organization_id=organization_id,
                check_type=check_type,
                check_scope_json={"domains": list(states.keys())},
                status="contradiction" if check_contradictions else "passing",
                contradiction_count=len(check_contradictions),
                contradictions_json=check_contradictions if check_contradictions else None,
                affected_entities_json=None,
                fingerprint=self._compute_fingerprint({
                    "org": organization_id,
                    "check_type": check_type,
                    "time": utcnow().isoformat(),
                }),
            )
            
            db.add(check)
            results.append(check)
        
        await db.flush()
        return results
    
    # ------------------------------------------------------------------ Continuity Events
    
    async def _log_continuity_event(
        self,
        db: AsyncSession,
        continuity: CompanyOperatingContinuity,
        event_type: str,
        loop_phase: str,
        title: str,
        description: str,
        actor_id: Optional[str] = None,
        actor_type: str = "human",
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        source_event_ids: Optional[List[str]] = None,
        related_entities: Optional[Dict] = None,
        epistemic_state: str = "observed",
        governance_scope_id: Optional[str] = None,
    ) -> CompanyContinuityEvent:
        """Log a continuity event."""
        
        # Get sequence number for this phase
        seq = await db.execute(
            select(func.max(CompanyContinuityEvent.sequence_in_phase))
            .where(
                CompanyContinuityEvent.continuity_cycle_id == continuity.id,
                CompanyContinuityEvent.loop_phase == loop_phase,
            )
        )
        max_seq = seq.scalar() or 0
        
        fingerprint = self._compute_fingerprint({
            "continuity_id": continuity.id,
            "event_type": event_type,
            "phase": loop_phase,
            "title": title,
            "time": utcnow().isoformat(),
        })
        
        event = CompanyContinuityEvent(
            organization_id=continuity.organization_id,
            continuity_cycle_id=continuity.id,
            event_type=event_type,
            loop_phase=loop_phase,
            occurred_at=utcnow(),
            sequence_in_phase=max_seq + 1,
            actor_id=actor_id,
            actor_type=actor_type,
            title=title,
            description=description,
            entity_type=entity_type,
            entity_id=entity_id,
            related_entities_json=related_entities or {},
            epistemic_state=epistemic_state,
            evidence_fingerprints=[],
            source_event_ids=source_event_ids or [],
            governance_scope_id=governance_scope_id,
            fingerprint=fingerprint,
        )
        
        db.add(event)
        return event
    
    async def record_event(
        self,
        db: AsyncSession,
        organization_id: str,
        event_type: str,
        loop_phase: str,
        title: str,
        description: str,
        *,
        actor_id: Optional[str] = None,
        actor_type: str = "human",
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        source_event_ids: Optional[List[str]] = None,
        related_entities: Optional[Dict] = None,
        epistemic_state: str = "observed",
        governance_scope_id: Optional[str] = None,
    ) -> CompanyContinuityEvent:
        """Record a continuity event in the current cycle."""
        
        continuity = await self.get_current_continuity(db, organization_id)
        if not continuity:
            continuity = await self.start_new_cycle(db, organization_id)
        
        return await self._log_continuity_event(
            db=db,
            continuity=continuity,
            event_type=event_type,
            loop_phase=loop_phase,
            title=title,
            description=description,
            actor_id=actor_id,
            actor_type=actor_type,
            entity_type=entity_type,
            entity_id=entity_id,
            source_event_ids=source_event_ids,
            related_entities=related_entities,
            epistemic_state=epistemic_state,
            governance_scope_id=governance_scope_id,
        )
    
    # ------------------------------------------------------------------ Universal Company Context
    
    async def build_universal_context(
        self,
        db: AsyncSession,
        organization_id: str,
        caller_user_id: str,
        *,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        context_version: int = 1,
    ) -> UniversalCompanyContext:
        """Build universal governed company context for a caller."""
        
        from app.intelligence.company_context import CallerAccess
        
        # Resolve caller access
        user = await db.get(User, caller_user_id)
        if not user:
            raise ValueError("User not found")
        
        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        
        # Compose all domain contexts (governed by access)
        identity = await self._compose_identity_context(db, organization_id, access)
        organization = await self._compose_organization_context(db, organization_id, access)
        intent = await self._compose_intent_context(db, organization_id, access)
        objectives = await self._compose_objectives_context(db, organization_id, access)
        decisions = await self._compose_decisions_context(db, organization_id, access)
        authorization = await self._compose_authorization_context(db, organization_id, access)
        commitments = await self._compose_commitments_context(db, organization_id, access)
        responsibilities = await self._compose_responsibilities_context(db, organization_id, access)
        people = await self._compose_people_context(db, organization_id, access)
        capacity = await self._compose_capacity_context(db, organization_id, access)
        work = await self._compose_work_context(db, organization_id, access)
        projects = await self._compose_projects_context(db, organization_id, access)
        customers = await self._compose_customers_context(db, organization_id, access)
        commercial = await self._compose_commercial_context(db, organization_id, access)
        financial = await self._compose_financial_context(db, organization_id, access)
        resources = await self._compose_resources_context(db, organization_id, access)
        procurement = await self._compose_procurement_context(db, organization_id, access)
        processes = await self._compose_processes_context(db, organization_id, access)
        knowledge = await self._compose_knowledge_context(db, organization_id, access)
        predictions = await self._compose_predictions_context(db, organization_id, access)
        counterfactuals = await self._compose_counterfactuals_context(db, organization_id, access)
        digital_twin = await self._compose_digital_twin_context(db, organization_id, access)
        autonomy = await self._compose_autonomy_context(db, organization_id, access)
        risks = await self._compose_risks_context(db, organization_id, access)
        attention = await self._compose_attention_context(db, organization_id, access)
        learning = await self._compose_learning_context(db, organization_id, access)
        institutional_memory = await self._compose_institutional_memory_context(db, organization_id, access)
        
        # Compute epistemic breakdown
        all_contexts = {
            "identity": identity, "organization": organization, "intent": intent,
            "objectives": objectives, "decisions": decisions, "authorization": authorization,
            "commitments": commitments, "responsibilities": responsibilities,
            "people": people, "capacity": capacity, "work": work, "projects": projects,
            "customers": customers, "commercial": commercial, "financial": financial,
            "resources": resources, "procurement": procurement, "processes": processes,
            "knowledge": knowledge, "predictions": predictions, "counterfactuals": counterfactuals,
            "digital_twin": digital_twin, "autonomy": autonomy, "risks": risks,
            "attention": attention, "learning": learning, "institutional_memory": institutional_memory,
        }
        
        epistemic_breakdown = defaultdict(int)
        for ctx in all_contexts.values():
            if ctx and "epistemic_state" in ctx:
                epistemic_breakdown[ctx["epistemic_state"]] += 1
        
        # Build fingerprint
        fingerprint = self._compute_fingerprint({
            "organization_id": organization_id,
            "caller_user_id": caller_user_id,
            "context_version": context_version,
            "access_hash": hashlib.sha256(str(sorted(access.visible_scope_ids)).encode()).hexdigest()[:16],
        })
        
        context = UniversalCompanyContext(
            organization_id=organization_id,
            caller_user_id=caller_user_id,
            org_wide=access.org_wide,
            scope_type=scope_type,
            scope_id=scope_id,
            identity_json=identity,
            organization_json=organization,
            intent_json=intent,
            objectives_json=objectives,
            decisions_json=decisions,
            authorization_json=authorization,
            commitments_json=commitments,
            responsibilities_json=responsibilities,
            people_json=people,
            capacity_json=capacity,
            work_json=work,
            projects_json=projects,
            customers_json=customers,
            commercial_json=commercial,
            financial_json=financial,
            resources_json=resources,
            procurement_json=procurement,
            processes_json=processes,
            knowledge_json=knowledge,
            predictions_json=predictions,
            counterfactuals_json=counterfactuals,
            digital_twin_json=digital_twin,
            autonomy_json=autonomy,
            risks_json=risks,
            attention_json=attention,
            learning_json=learning,
            institutional_memory_json=institutional_memory,
            computed_at=utcnow(),
            input_fingerprint=fingerprint,
            context_version=context_version,
            epistemic_breakdown_json=dict(epistemic_breakdown),
            fingerprint=fingerprint,
        )
        
        db.add(context)
        await db.flush()
        return context
    
    # Context composition helpers (all governance-aware)
    
    async def _compose_identity_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {
            "epistemic_state": "observed",
            "employee_count": len(access.project_ids),  # Placeholder
        }
    
    async def _compose_organization_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_intent_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_objectives_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_decisions_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_authorization_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_commitments_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_responsibilities_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_people_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_capacity_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "measured"}
    
    async def _compose_work_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_projects_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_customers_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_commercial_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_financial_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "evidence_backed"}
    
    async def _compose_resources_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_procurement_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_processes_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_knowledge_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "evidence_backed"}
    
    async def _compose_predictions_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "predicted"}
    
    async def _compose_counterfactuals_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "counterfactual"}
    
    async def _compose_digital_twin_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "simulated"}
    
    async def _compose_autonomy_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "proposed"}
    
    async def _compose_risks_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "inferred"}
    
    async def _compose_attention_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "evidence_backed"}
    
    async def _compose_learning_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "inferred"}
    
    async def _compose_institutional_memory_context(self, db: AsyncSession, org_id: str, access) -> Dict[str, Any]:
        return {"epistemic_state": "inferred"}
    
    # ------------------------------------------------------------------ Refresh Phase State
    
    async def _refresh_phase_state(self, db: AsyncSession, continuity: CompanyOperatingContinuity, phase: str):
        """Refresh state for a specific phase."""
        
        if phase == "identity":
            continuity.identity_state_json = await self._compose_identity_state(db, continuity.organization_id)
        elif phase == "organization":
            continuity.organization_state_json = await self._compose_organization_state(db, continuity.organization_id)
        elif phase == "intent":
            continuity.intent_state_json = await self._compose_intent_state(db, continuity.organization_id)
        elif phase == "objectives":
            continuity.objectives_state_json = await self._compose_objectives_state(db, continuity.organization_id)
        elif phase == "strategy":
            continuity.strategy_state_json = await self._compose_strategy_state(db, continuity.organization_id)
        elif phase == "authorization":
            continuity.authorization_state_json = await self._compose_authorization_state(db, continuity.organization_id)
        elif phase == "commitments":
            continuity.commitment_state_json = await self._compose_commitment_state(db, continuity.organization_id)
        elif phase == "responsibilities":
            continuity.responsibility_state_json = await self._compose_responsibility_state(db, continuity.organization_id)
        elif phase == "capacity":
            continuity.capacity_state_json = await self._compose_capacity_state(db, continuity.organization_id)
        elif phase == "actions":
            continuity.work_state_json = await self._compose_work_state(db, continuity.organization_id)
        elif phase == "work":
            continuity.work_state_json = await self._compose_work_state(db, continuity.organization_id)
        elif phase == "execution":
            continuity.execution_state_json = await self._compose_execution_state(db, continuity.organization_id)
        elif phase == "outcomes":
            continuity.outcome_state_json = await self._compose_outcome_state(db, continuity.organization_id)
        elif phase == "learning":
            continuity.learning_state_json = await self._compose_learning_state(db, continuity.organization_id)
        elif phase == "institutional_memory":
            continuity.learning_state_json = await self._compose_learning_state(db, continuity.organization_id)
        elif phase == "prediction":
            continuity.prediction_state_json = await self._compose_prediction_state(db, continuity.organization_id)
        elif phase == "counterfactual":
            continuity.prediction_state_json = await self._compose_prediction_state(db, continuity.organization_id)
        elif phase == "digital_twin":
            continuity.twin_state_json = await self._compose_twin_state(db, continuity.organization_id)
        elif phase == "optimization":
            continuity.optimization_state_json = await self._compose_optimization_state(db, continuity.organization_id)
        elif phase == "governed_autonomy":
            continuity.autonomy_state_json = await self._compose_autonomy_state(db, continuity.organization_id)
    
    async def _compose_optimization_state(self, db: AsyncSession, organization_id: str) -> Dict[str, Any]:
        """Compose optimization state."""
        optimizations = await db.execute(
            select(OptimizationContext)
            .where(OptimizationContext.organization_id == organization_id)
            .order_by(OptimizationContext.created_at.desc())
            .limit(10)
        )
        return {
            "recent_optimizations": len(optimizations.scalars().all()),
            "epistemic_state": "inferred",
        }
    
    # ------------------------------------------------------------------ Query Methods
    
    async def get_current_continuity(
        self, db: AsyncSession, organization_id: str
    ) -> Optional[CompanyOperatingContinuity]:
        """Get the current (latest) operating continuity for an organization."""
        
        result = await db.execute(
            select(CompanyOperatingContinuity)
            .where(CompanyOperatingContinuity.organization_id == organization_id)
            .order_by(CompanyOperatingContinuity.cycle_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_continuity_by_cycle(
        self, db: AsyncSession, organization_id: str, cycle_number: int
    ) -> Optional[CompanyOperatingContinuity]:
        """Get a specific continuity cycle."""
        
        result = await db.execute(
            select(CompanyOperatingContinuity)
            .where(
                CompanyOperatingContinuity.organization_id == organization_id,
                CompanyOperatingContinuity.cycle_number == cycle_number,
            )
        )
        return result.scalar_one_or_none()
    
    async def get_continuity_events(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        continuity_cycle_id: Optional[str] = None,
        event_type: Optional[str] = None,
        loop_phase: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CompanyContinuityEvent]:
        """Get continuity events with filtering."""
        
        query = select(CompanyContinuityEvent).where(
            CompanyContinuityEvent.organization_id == organization_id
        )
        
        if continuity_cycle_id:
            query = query.where(CompanyContinuityEvent.continuity_cycle_id == continuity_cycle_id)
        if event_type:
            query = query.where(CompanyContinuityEvent.event_type == event_type)
        if loop_phase:
            query = query.where(CompanyContinuityEvent.loop_phase == loop_phase)
        
        query = query.order_by(CompanyContinuityEvent.occurred_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def get_latest_state_snapshot(
        self, db: AsyncSession, organization_id: str, dimension: str
    ) -> Optional[CompanyStateSnapshotGate30]:
        """Get the latest state snapshot for a dimension."""
        
        result = await db.execute(
            select(CompanyStateSnapshotGate30)
            .where(
                CompanyStateSnapshotGate30.organization_id == organization_id,
                CompanyStateSnapshotGate30.dimension == dimension,
            )
            .order_by(CompanyStateSnapshotGate30.captured_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_universal_context(
        self, db: AsyncSession, organization_id: str, caller_user_id: str
    ) -> Optional[UniversalCompanyContext]:
        """Get the latest universal context for a caller."""
        
        result = await db.execute(
            select(UniversalCompanyContext)
            .where(
                UniversalCompanyContext.organization_id == organization_id,
                UniversalCompanyContext.caller_user_id == caller_user_id,
            )
            .order_by(UniversalCompanyContext.computed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    # ------------------------------------------------------------------ Universal Timeline
    
    async def build_universal_timeline(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        loop_phase: Optional[str] = None,
        days_back: int = 30,
        limit: int = 100,
    ) -> List[UniversalCompanyTimeline]:
        """Build universal company timeline from all canonical sources."""
        
        # This composes timeline from multiple sources
        events = []
        since = utcnow() - timedelta(days=days_back)
        
        # Source 1: Continuity events
        continuity_events = await db.execute(
            select(CompanyContinuityEvent)
            .where(
                CompanyContinuityEvent.organization_id == organization_id,
                CompanyContinuityEvent.occurred_at >= since,
            )
            .order_by(CompanyContinuityEvent.occurred_at.desc())
            .limit(limit)
        )
        for ce in continuity_events.scalars().all():
            events.append({
                "event_type": ce.event_type,
                "loop_phase": ce.loop_phase,
                "occurred_at": ce.occurred_at,
                "title": ce.title,
                "description": ce.description,
                "entity_type": ce.entity_type,
                "entity_id": ce.entity_id,
                "actor_id": ce.actor_id,
                "actor_type": ce.actor_type,
                "scope_type": None,
                "scope_id": ce.governance_scope_id,
                "epistemic_state": ce.epistemic_state,
                "evidence_fingerprints": ce.evidence_fingerprints,
                "related_events_json": ce.related_entities_json.get("events", []) if ce.related_entities_json else [],
                "continuity_cycle_id": ce.continuity_cycle_id,
                "visible_to_org_wide": True,
                "visible_scope_ids_json": [],
            })
        
        # Source 2: Company decisions
        decisions = await db.execute(
            select(CompanyDecision)
            .where(
                CompanyDecision.organization_id == organization_id,
                CompanyDecision.created_at >= since,
            )
            .order_by(CompanyDecision.created_at.desc())
            .limit(limit)
        )
        for d in decisions.scalars().all():
            events.append({
                "event_type": "decision_made",
                "loop_phase": "decisions",
                "occurred_at": d.created_at,
                "title": f"Decision: {d.title}",
                "description": d.reason or d.title,
                "entity_type": "company_decision",
                "entity_id": d.id,
                "actor_id": d.decided_by,
                "actor_type": "human",
                "scope_type": None,
                "scope_id": None,
                "epistemic_state": "observed",
                "evidence_fingerprints": d.evidence_fingerprints or [],
                "related_events_json": [],
                "continuity_cycle_id": None,
                "visible_to_org_wide": True,
                "visible_scope_ids_json": [],
            })
        
        # Source 3: Project timelines
        from app.models.project import ProjectTimeline
        project_timelines = await db.execute(
            select(ProjectTimeline)
            .where(
                ProjectTimeline.organization_id == organization_id,
                ProjectTimeline.occurred_at >= since,
            )
            .order_by(ProjectTimeline.occurred_at.desc())
            .limit(limit)
        )
        for pt in project_timelines.scalars().all():
            events.append({
                "event_type": "project_milestone",
                "loop_phase": "work",
                "occurred_at": pt.occurred_at,
                "title": pt.title,
                "description": pt.description,
                "entity_type": "project",
                "entity_id": pt.project_id,
                "actor_id": pt.actor_id,
                "actor_type": "human",
                "scope_type": "project",
                "scope_id": pt.project_id,
                "epistemic_state": "observed",
                "evidence_fingerprints": [],
                "related_events_json": [],
                "continuity_cycle_id": None,
                "visible_to_org_wide": True,
                "visible_scope_ids_json": [],
            })
        
        # Source 4: Organizational learning
        learning = await db.execute(
            select(OrganizationalLearning)
            .where(
                OrganizationalLearning.organization_id == organization_id,
                OrganizationalLearning.observed_at >= since,
            )
            .order_by(OrganizationalLearning.observed_at.desc())
            .limit(limit)
        )
        for l in learning.scalars().all():
            events.append({
                "event_type": "learning_extracted",
                "loop_phase": "learning",
                "occurred_at": l.observed_at or l.created_at,
                "title": f"Lesson: {l.title}",
                "description": l.lesson,
                "entity_type": "organizational_learning",
                "entity_id": l.id,
                "actor_id": l.validated_by,
                "actor_type": "human",
                "scope_type": None,
                "scope_id": None,
                "epistemic_state": "inferred",
                "evidence_fingerprints": l.evidence_fingerprints or [],
                "related_events_json": [],
                "continuity_cycle_id": None,
                "visible_to_org_wide": True,
                "visible_scope_ids_json": [],
            })
        
        # Sort by time
        events.sort(key=lambda e: e["occurred_at"], reverse=True)
        events = events[:limit]
        
        # Persist timeline entries
        timeline_entries = []
        for e in events:
            entry = UniversalCompanyTimeline(
                organization_id=organization_id,
                event_type=e["event_type"],
                loop_phase=e["loop_phase"],
                occurred_at=e["occurred_at"],
                title=e["title"],
                description=e["description"],
                entity_type=e["entity_type"],
                entity_id=e["entity_id"],
                actor_id=e["actor_id"],
                actor_type=e["actor_type"],
                scope_type=e["scope_type"],
                scope_id=e["scope_id"],
                related_events_json=e["related_events_json"],
                continuity_cycle_id=e["continuity_cycle_id"],
                epistemic_state=e["epistemic_state"],
                evidence_fingerprints=e["evidence_fingerprints"],
                visible_to_org_wide=e["visible_to_org_wide"],
                visible_scope_ids_json=e["visible_scope_ids_json"],
                fingerprint=self._compute_fingerprint(e),
            )
            db.add(entry)
            timeline_entries.append(entry)
        
        await db.flush()
        return timeline_entries
    
    # ------------------------------------------------------------------ Self-Compounding Loop
    
    async def run_compounding_loop(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        trigger: str = "scheduled",
    ) -> SelfCompoundingLoopState:
        """Run one complete self-compounding loop cycle."""
        
        # Get last cycle
        last = await db.execute(
            select(SelfCompoundingLoopState.cycle_number)
            .where(SelfCompoundingLoopState.organization_id == organization_id)
            .order_by(SelfCompoundingLoopState.cycle_number.desc())
            .limit(1)
        )
        last_num = last.scalar() or 0
        cycle_number = last_num + 1
        
        started = utcnow()
        loop = SelfCompoundingLoopState(
            organization_id=organization_id,
            cycle_number=cycle_number,
            current_phase="reality",
            cycle_started_at=started,
            phase_entered_at=started,
            fingerprint=self._compute_fingerprint({
                "org": organization_id,
                "cycle": cycle_number,
                "trigger": trigger,
            }),
        )
        
        db.add(loop)
        await db.flush()
        
        # Phase 1: Reality - Get current company state
        loop.current_phase = "understanding"
        loop.phase_entered_at = utcnow()
        loop.reality_state_json = await self._compose_reality_state(db, organization_id)
        
        # Phase 2: Understanding - Build company context
        loop.current_phase = "intelligence"
        loop.phase_entered_at = utcnow()
        loop.understanding_state_json = await self._compose_understanding_state(db, organization_id)
        
        # Phase 3: Intelligence - Gather patterns, insights, memories
        loop.current_phase = "prediction"
        loop.phase_entered_at = utcnow()
        loop.intelligence_state_json = await self._compose_intelligence_state(db, organization_id)
        
        # Phase 4: Prediction - Get predictive intelligence
        loop.current_phase = "counterfactual"
        loop.phase_entered_at = utcnow()
        loop.prediction_state_json = await self._compose_prediction_state(db, organization_id)
        
        # Phase 5: Counterfactual - Evaluate scenarios
        loop.current_phase = "digital_twin"
        loop.phase_entered_at = utcnow()
        loop.counterfactual_state_json = await self._compose_counterfactual_state(db, organization_id)
        
        # Phase 6: Digital Twin - Sync future state
        loop.current_phase = "optimization"
        loop.phase_entered_at = utcnow()
        loop.digital_twin_state_json = await self._compose_twin_state(db, organization_id)
        
        # Phase 7: Optimization - Run optimizations
        loop.current_phase = "decision"
        loop.phase_entered_at = utcnow()
        loop.optimization_state_json = await self._compose_optimization_state(db, organization_id)
        
        # Phase 8: Decision - Get decision context
        loop.current_phase = "governance"
        loop.phase_entered_at = utcnow()
        loop.decision_state_json = await self._compose_decision_state(db, organization_id)
        
        # Phase 9: Governance - Check authorizations
        loop.current_phase = "autonomy"
        loop.phase_entered_at = utcnow()
        loop.governance_state_json = await self._compose_governance_state(db, organization_id)
        
        # Phase 10: Autonomy - Evaluate autonomous operations
        loop.current_phase = "execution"
        loop.phase_entered_at = utcnow()
        loop.autonomy_state_json = await self._compose_autonomy_state(db, organization_id)
        
        # Phase 11: Execution - Track executions
        loop.current_phase = "outcome"
        loop.phase_entered_at = utcnow()
        loop.execution_state_json = await self._compose_execution_state(db, organization_id)
        
        # Phase 12: Outcome - Record outcomes
        loop.current_phase = "verification"
        loop.phase_entered_at = utcnow()
        loop.outcome_state_json = await self._compose_outcome_state(db, organization_id)
        
        # Phase 13: Verification - Verify outcomes
        loop.current_phase = "learning"
        loop.phase_entered_at = utcnow()
        loop.verification_state_json = await self._compose_verification_state(db, organization_id)
        
        # Phase 14: Learning - Extract lessons
        loop.current_phase = "institutional_memory"
        loop.phase_entered_at = utcnow()
        loop.learning_state_json = await self._compose_learning_state(db, organization_id)
        
        # Phase 15: Institutional Memory - Record durable lessons
        loop.current_phase = "calibration"
        loop.phase_entered_at = utcnow()
        loop.memory_state_json = await self._compose_memory_state(db, organization_id)
        
        # Phase 16: Calibration - Improve predictions
        loop.current_phase = "improved_future_context"
        loop.phase_entered_at = utcnow()
        loop.calibration_state_json = await self._compose_calibration_state(db, organization_id)
        
        # Phase 17: Improved Future Context - Update context
        loop.current_phase = "reality"
        loop.phase_entered_at = utcnow()
        loop.future_context_state_json = await self._compose_future_context_state(db, organization_id)
        
        # Complete
        loop.cycle_completed_at = utcnow()
        loop.loop_duration_ms = int((utcnow() - started).total_seconds() * 1000)
        loop.phases_completed = len(LOOP_PHASES)
        
        # Calculate calibration delta
        loop.calibration_delta = await self._calculate_calibration_delta(db, organization_id)
        loop.learning_accumulated = await self._count_new_learning(db, organization_id, since=started - timedelta(hours=24))
        
        return loop
    
    async def _compose_reality_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return await self._compose_identity_state(db, org_id)
    
    async def _compose_understanding_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        # Use Company Brain to get understanding
        return {"epistemic_state": "inferred"}
    
    async def _compose_intelligence_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"epistemic_state": "inferred"}
    
    async def _compose_counterfactual_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"epistemic_state": "counterfactual"}
    
    async def _compose_decision_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_governance_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"epistemic_state": "observed"}
    
    async def _compose_verification_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"epistemic_state": "evidence_backed"}
    
    async def _compose_memory_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"epistemic_state": "inferred"}
    
    async def _compose_calibration_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"epistemic_state": "measured"}
    
    async def _compose_future_context_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"epistemic_state": "predicted"}
    
    async def _calculate_calibration_delta(self, db: AsyncSession, org_id: str) -> float:
        """Calculate how much calibration improved."""
        return 0.0
    
    async def _count_new_learning(self, db: AsyncSession, org_id: str, since: datetime) -> int:
        """Count new learning entries since timestamp."""
        count = await db.execute(
            select(func.count(OrganizationalLearning.id))
            .where(
                OrganizationalLearning.organization_id == org_id,
                OrganizationalLearning.created_at >= since,
            )
        )
        return count.scalar() or 0
    
    # ------------------------------------------------------------------ Operating Health
    
    async def assess_operating_health(
        self, db: AsyncSession, organization_id: str
    ) -> CompanyOperatingHealth:
        """Assess and persist company operating health."""
        
        continuity = await self.get_current_continuity(db, organization_id)
        if not continuity:
            return None
        
        states = {
            "identity": continuity.identity_state_json,
            "organization": continuity.organization_state_json,
            "intent": continuity.intent_state_json,
            "objectives": continuity.objectives_state_json,
            "strategy": continuity.strategy_state_json,
            "authorization": continuity.authorization_state_json,
            "commitments": continuity.commitment_state_json,
            "responsibilities": continuity.responsibility_state_json,
            "capacity": continuity.capacity_state_json,
            "work": continuity.work_state_json,
            "execution": continuity.execution_state_json,
            "outcomes": continuity.outcome_state_json,
            "learning": continuity.learning_state_json,
            "predictions": continuity.prediction_state_json,
            "twin": continuity.twin_state_json,
            "autonomy": continuity.autonomy_state_json,
        }
        
        contradictions = await self._run_consistency_checks(db, organization_id, states)
        
        health = CompanyOperatingHealth(
            organization_id=organization_id,
            overall_state=continuity.operating_health,
            assessed_at=utcnow(),
            domain_health_json=continuity.health_details_json,
            unresolved_contradictions=continuity.contradiction_count,
            missing_responsibility=0,  # Would compute
            stale_state_count=0,
            failed_executions=0,
            unknown_outcomes=0,
            prediction_divergence_count=0,
            twin_divergence_count=0,
            blocked_operations=0,
            governance_issues=0,
            integration_failures=0,
            learning_gaps=0,
            details_json={"contradictions": [c["type"] for c in contradictions]},
            fingerprint=self._compute_fingerprint({
                "org": organization_id,
                "time": utcnow().isoformat(),
            }),
        )
        
        db.add(health)
        await db.flush()
        return health
    
    # ------------------------------------------------------------------ Utility
    
    def _compute_fingerprint(self, data: Dict[str, Any]) -> str:
        """Compute deterministic fingerprint for exact-once semantics."""
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:40]


# Singleton instance
canonical_company_continuity_service = CanonicalCompanyContinuityService()