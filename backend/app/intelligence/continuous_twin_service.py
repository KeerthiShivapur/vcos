"""Continuous Digital Twin, Optimization & Self-Learning Service — Gate 29.

This service implements the continuous feedback loop connecting:
- Continuous company state derivation
- Digital twin synchronization
- Prediction calibration
- Constrained optimization
- Continuous learning
- Institutional memory
- Attention & drift detection
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Tuple, Set
from enum import Enum
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.core.timeutils import utcnow
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
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task
from app.models.knowledge import Decision
from app.models.company_operating import CompanyDecision
from app.models.execution_strategy import CompanyCommitment, CompanyObjective
from app.models.autonomy import AutonomyProposal
from app.models.canonical_business_intelligence import (
    CanonicalMetric, MetricObservation, CanonicalCompanyHealth
)
from app.models.organizational_learning import (
    OrganizationalLearning,
    LearningEvidence,
)
from app.models.intelligence import PatternDetection
from app.models.company_memory import CompanyMemory
from app.models.canonical_business_intelligence import (
    CanonicalMetric, MetricObservation, CanonicalCompanyHealth,
    VarianceAnalysis, CanonicalDecisionContext, CanonicalExecutiveBriefing
)
from app.intelligence.canonical_business_intelligence_service import canonical_business_intelligence_service
from app.intelligence.company_brain import company_brain
from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
from app.intelligence.organizational_capacity_service import organizational_capacity_service
from app.intelligence.canonical_business_process_service import canonical_business_process_service
from app.intelligence.institutional_intelligence_service import institutional_intelligence_service
from app.intelligence.cross_domain_impact_service import cross_domain_impact_service
from app.intelligence.canonical_mutation import canonical_mutation_boundary
from app.intelligence.company_brain import company_brain
from app.intelligence.canonical_mutation import canonical_mutation_boundary
from app.intelligence.company_brain import company_brain
from app.intelligence.canonical_mutation import CanonicalMutationContext, MutationType
from app.services.autonomy_service import autonomy_service
from app.services.commercial_service import commercial_service
from app.services.audit_service import audit_service
from app.services.event_service import event_service
from app.services.notification_service import notification_service
from app.intelligence.company_context import resolve_caller_access
from app.core.timeutils import utcnow

logger = logging.getLogger("vcos.intelligence.continuous_twin")


class ContinuousTwinService:
    """Service for continuous digital twin, optimization, and self-learning."""
    
    # ------------------------------------------------------------------ Company State
    
    async def derive_company_state(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        dimensions: Optional[List[str]] = None,
        as_of: Optional[datetime] = None,
        caller: Optional["CallerAccess"] = None,
    ) -> Dict[str, Any]:
        """Derive the current continuous company state.
        
        Composes a unified view of the company state from canonical sources.
        """
        dims = dimensions or list(COMPANY_STATE_DIMENSIONS)
        as_of = as_of or utcnow()
        
        state = {}
        
        for dim in dims:
            dim_state = await self._derive_dimension_state(db, organization_id, dim, as_of)
            if dim_state is not None:
                state[dim] = dim_state
        
        # Store snapshot
        await self._store_state_snapshots(db, organization_id, state, as_of)
        
        return {
            "organization_id": organization_id,
            "captured_at": utcnow().isoformat(),
            "state": state,
        }
    
    async def _derive_dimension_state(
        self,
        db: AsyncSession,
        organization_id: str,
        dimension: str,
        as_of: datetime,
    ) -> Optional[Dict[str, Any]]:
        """Derive a single dimension of company state."""
        
        dim_map = {
            "organization": self._derive_org_state,
            "people": self._derive_people_state,
            "roles": self._derive_roles_state,
            "responsibilities": self._derive_responsibilities_state,
            "capacity": self._derive_capacity_state,
            "work": self._derive_work_state,
            "projects": self._derive_projects_state,
            "customers": self._derive_customers_state,
            "commercial": self._derive_commercial_state,
            "financial": self._derive_financial_state,
            "resources": self._derive_resources_state,
            "procurement": self._derive_procurement_state,
            "processes": self._derive_processes_state,
            "knowledge": self._derive_knowledge_state,
            "decisions": self._derive_decisions_state,
            "commitments": self._derive_commitments_state,
            "actions": self._derive_actions_state,
            "outcomes": self._derive_outcomes_state,
            "predictions": self._derive_predictions_state,
            "counterfactuals": self._derive_counterfactuals_state,
            "digital_twin": self._derive_twin_state,
            "institutional_memory": self._derive_memory_state,
            "integrations": self._derive_integrations_state,
            "security": self._derive_security_state,
            "governance": self._derive_governance_state,
        }
        
        derive_func = dim_map.get(dimension)
        if not derive_func:
            return None
        
        return await derive_func(db, organization_id)
    
    async def _derive_org_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        """Derive organization state."""
        from app.models.organization import Organization
        org = await db.get(Organization, organization_id)
        if not org:
            return {}
        return {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "status": org.status,
            "industry": org.industry,
            "country": org.country,
            "timezone": org.timezone,
        }
    
    async def _derive_people_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        """Derive people state."""
        from app.models.employee import Employee
        result = await db.execute(
            select(Employee).where(Employee.organization_id == organization_id, Employee.status == "active")
        )
        employees = result.scalars().all()
        return {
            "total": len(employees),
            "by_role": {},
            "by_department": {},
        }
    
    async def _derive_roles_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.role import Role
        result = await db.execute(
            select(Role).where(Role.organization_id == organization_id)
        )
        roles = result.scalars().all()
        return {"roles": [{"id": r.id, "name": r.name, "code": r.code} for r in roles]}
    
    async def _derive_responsibilities_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.execution_strategy import OrganizationalResponsibility
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == organization_id
            )
        )
        return {"responsibilities": list(result.scalars().all())}
    
    async def _derive_capacity_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.intelligence.organizational_capacity_service import organizational_capacity_service
        return await organizational_capacity_service.get_capacity_summary(db, organization_id)
    
    async def _derive_work_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.task import Task
        result = await db.execute(
            select(Task).where(Task.organization_id == organization_id, Task.status.in_(["pending", "in_progress", "blocked"]))
        )
        tasks = result.scalars().all()
        return {
            "active_tasks": len(tasks),
            "by_status": {},
        }
    
    async def _derive_projects_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.project import Project
        result = await db.execute(
            select(Project).where(Project.organization_id == organization_id, Project.state.in_(["active", "planning"]))
        )
        projects = result.scalars().all()
        return {
            "active_projects": len(projects),
            "projects": [{"id": p.id, "title": p.title, "state": p.state} for p in projects[:20]],
        }
    
    async def _derive_customers_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.customer import Customer
        result = await db.execute(
            select(Customer).where(Customer.organization_id == organization_id)
        )
        return {"total": len(result.scalars().all())}
    
    async def _derive_commercial_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"pipeline": []}
    
    async def _derive_financial_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.canonical_business_intelligence import MetricObservation, CanonicalMetric
        result = await db.execute(
            select(MetricObservation).join(CanonicalMetric).where(
                CanonicalMetric.organization_id == organization_id,
                CanonicalMetric.metric_key.in_(["revenue", "expenses", "cash_position"])
            ).order_by(MetricObservation.period_end.desc()).limit(10)
        )
        return {"metrics": [{"key": m.metric_key, "value": m.value} for m in result.scalars().all()]}
    
    async def _derive_resources_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.intelligence.canonical_resource_asset_service import canonical_resource_asset_service
        return await canonical_resource_asset_service.get_resource_summary(db, organization_id)
    
    async def _derive_procurement_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.intelligence.canonical_procurement_vendor_service import canonical_procurement_vendor_service
        return await canonical_procurement_vendor_service.get_procurement_summary(db, organization_id)
    
    async def _derive_processes_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"processes": []}
    
    async def _derive_knowledge_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.knowledge import KnowledgeDocument
        result = await db.execute(
            select(func.count(KnowledgeDocument.id)).where(
                KnowledgeDocument.organization_id == organization_id,
                KnowledgeDocument.state == "published"
            )
        )
        return {"published_documents": result.scalar() or 0}
    
    async def _derive_decisions_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.company_operating import CompanyDecision
        result = await db.execute(
            select(CompanyDecision).where(
                CompanyDecision.organization_id == organization_id,
                CompanyDecision.state.in_(["proposed", "under_review", "awaiting_approval"])
            )
        )
        return {"pending_decisions": len(result.scalars().all())}
    
    async def _derive_commitments_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.execution_strategy import CompanyCommitment
        result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == organization_id,
                CompanyCommitment.state.in_(["authorized", "active"])
            )
        )
        return {"active_commitments": len(result.scalars().all())}
    
    async def _derive_actions_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.company_actions import CompanyAction
        result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == organization_id,
                CompanyAction.state.in_(["proposed", "ready", "in_progress"])
            )
        )
        return {"pending_actions": len(result.scalars().all())}
    
    async def _derive_outcomes_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"outcomes": []}
    
    async def _derive_predictions_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.prediction import Prediction
        result = await db.execute(
            select(Prediction).where(
                Prediction.organization_id == organization_id,
                Prediction.status == "open"
            ).limit(20)
        )
        return {"open_predictions": len(result.scalars().all())}
    
    async def _derive_counterfactuals_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"counterfactuals": []}
    
    async def _derive_twin_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.digital_twin import DigitalTwin
        result = await db.execute(
            select(DigitalTwin).where(DigitalTwin.organization_id == organization_id)
        )
        twin = result.scalars().first()
        if not twin:
            return {"status": "not_initialized"}
        return {
            "health_score": twin.health_score,
            "health_status": twin.health_status,
            "refresh_count": twin.refresh_count,
            "last_refreshed": twin.last_refreshed_at.isoformat() if twin.last_refreshed_at else None,
        }
    
    async def _derive_memory_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.organizational_learning import OrganizationalLearning
        result = await db.execute(
            select(func.count(OrganizationalLearning.id)).where(
                OrganizationalLearning.organization_id == organization_id,
                OrganizationalLearning.status == "active"
            )
        )
        return {"active_lessons": result.scalar() or 0}
    
    async def _derive_integrations_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        from app.models.canonical_integration import ConnectorInstance
        result = await db.execute(
            select(func.count(ConnectorInstance.id)).where(
                ConnectorInstance.organization_id == organization_id,
                ConnectorInstance.state == "connected"
            )
        )
        return {"connected_systems": result.scalar() or 0}
    
    async def _derive_security_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"security": {}}
    
    async def _derive_governance_state(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        return {"governance": {}}
    
    async def _store_state_snapshots(
        self,
        db: AsyncSession,
        organization_id: str,
        state: Dict[str, Any],
        captured_at: datetime,
    ) -> None:
        """Store state snapshots for each dimension."""
        for dim, dim_state in state.items():
            fingerprint = hashlib.sha256(
                f"{organization_id}:{dim}:{json.dumps(dim_state, sort_keys=True)}".encode()
            ).hexdigest()[:160]
            
            snapshot = CompanyStateSnapshot(
                organization_id=organization_id,
                dimension=dimension,
                captured_at=datetime.now(timezone.utc),
                valid_from=datetime.now(timezone.utc),
                state_json=json.dumps(dim_state, default=str),
                fingerprint=fingerprint,
            )
            db.add(snapshot)
        
        await db.flush()
    
    # ------------------------------------------------------------------ Twin Synchronization
    
    async def synchronize_twin(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope_type: str = "org",
        scope_id: Optional[str] = None,
        triggered_by: Optional[str] = None,
    ) -> TwinSynchronizationLog:
        """Synchronize the digital twin with canonical reality."""
        
        log = TwinSynchronizationLog(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            started_at=utcnow(),
            sync_source="canonical_events",
        )
        db.add(log)
        await db.flush()
        
        start_time = utcnow()
        
        try:
            # Get current twin state
            from app.models.digital_twin import DigitalTwin
            twin_result = await db.execute(
                select(DigitalTwin).where(DigitalTwin.organization_id == organization_id)
            )
            twin = twin_result.scalars().first()
            
            if not twin:
                log.status = "failed"
                log.errors_json = json.dumps({"error": "Digital twin not found"})
                await db.flush()
                return log
            
            # Derive current state
            current_state = await self.derive_company_state(db, twin.organization_id)
            
            # Update twin
            twin.twin_json = json.dumps(current_state)
            twin.last_refreshed_at = utcnow()
            twin.refresh_count += 1
            
            # Detect drift
            drift = await self._detect_drift(db, twin.organization_id)
            if drift:
                # Create drift record
                from app.models.continuous_twin import ModelTwinDrift
                drift_record = ModelTwinDrift(
                    organization_id=twin.organization_id,
                    drift_type="twin_reality_gap",
                    severity="medium",
                    subject_type="digital_twin",
                    subject_id=twin.id,
                    expected_json=json.dumps({"twin": twin.twin_json}),
                    observed_json=json.dumps(current_state),
                    deviation_score=0.1,
                    severity_score=0.5,
                    evidence_json=json.dumps({"detail": "Twin diverged from canonical state"}),
                    detected_by="continuous_twin_service",
                    detected_at=utcnow(),
                )
                db.add(drift_record)
            
            # Update twin state
            twin.twin_json = json.dumps(current_state)
            twin.last_refreshed_at = utcnow()
            
            # Log synchronization
            log.status = "success"
            log.completed_at = utcnow()
            log.duration_ms = int((utcnow() - start_time).total_seconds() * 1000)
            log.entities_synced = 1
            
            await db.flush()
            
        except Exception as e:
            log.status = "failed"
            log.errors_json = json.dumps({"error": str(e)})
            log.completed_at = utcnow()
        
        log.duration_ms = int((utcnow() - start_time).total_seconds() * 1000)
        await db.flush()
        
        return log
    
    async def _detect_drift(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> bool:
        """Detect if twin has drifted from canonical reality."""
        # Simplified drift detection
        return False
    
    # ------------------------------------------------------------------ Prediction Calibration
    
    async def calibrate_predictions(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        prediction_kind: Optional[str] = None,
        evaluation_window_days: int = 30,
    ) -> List[PredictionCalibration]:
        """Calibrate prediction models against actual outcomes."""
        
        from app.models.prediction import Prediction, PredictionHistory
        from app.models.prediction import PredictionModel
        
        # Get predictions to evaluate
        query = select(Prediction).where(
            Prediction.organization_id == organization_id,
            Prediction.status.in_(["validated", "resolved"]),
            Prediction.due_at <= utcnow(),
        )
        
        if prediction_kind:
            query = query.where(Prediction.kind == prediction_kind)
        
        query = query.order_by(Prediction.due_at.desc()).limit(100)
        result = await db.execute(query)
        predictions = result.scalars().all()
        
        calibrations = []
        
        for pred in predictions:
            # Check if already calibrated
            existing = await db.execute(
                select(PredictionHistory).where(
                    PredictionHistory.prediction_id == pred.id
                )
            )
            history = existing.scalar_one_or_none()
            
            if not history:
                # Create calibration record
                outcome = pred.status == "resolved"
                history = PredictionHistory(
                    organization_id=organization_id,
                    prediction_id=pred.id,
                    kind=pred.kind,
                    outcome=outcome,
                    accuracy=1.0 if outcome else 0.0,
                    validated_at=utcnow(),
                )
                db.add(history)
                
                # Update calibration
                calib = await self._update_calibration(db, pred.organization_id, pred.kind, pred.model_version)
                calibrations.append(calib)
        
        return calibrations
    
    async def _update_calibration(
        self,
        db: AsyncSession,
        organization_id: str,
        prediction_kind: str,
        model_version: str,
    ) -> PredictionCalibration:
        """Update calibration metrics for a prediction kind."""
        
        from app.models.prediction import PredictionHistory
        
        # Get recent history
        window_start = utcnow() - timedelta(days=30)
        result = await db.execute(
            select(PredictionHistory).where(
                PredictionHistory.organization_id == organization_id,
                PredictionHistory.kind == prediction_kind,
                PredictionHistory.validated_at >= utcnow() - timedelta(days=30),
            )
        )
        histories = result.scalars().all()
        
        if not histories:
            return None
        
        total = len(histories)
        correct = sum(1 for h in histories if h.outcome)
        accuracy = correct / total if total > 0 else 0.0
        
        # Get or create calibration record
        result = await db.execute(
            select(PredictionCalibration).where(
                PredictionCalibration.organization_id == organization_id,
                PredictionCalibration.prediction_kind == prediction_kind,
                PredictionCalibration.model_version == "twin-v1",
            )
        )
        calib = result.scalars().first()
        
        if not calib:
            calib = PredictionCalibration(
                organization_id=organization_id,
                prediction_kind=prediction_kind,
                model_version="twin-v1",
                status="calibrated",
            )
            db.add(calib)
        
        calib.total_predictions = total
        calib.correct_predictions = sum(1 for h in histories if h.outcome)
        calib.accuracy = calib.correct_predictions / calib.total_predictions if calib.total_predictions > 0 else 0.0
        calib.last_evaluated_at = utcnow()
        calib.next_evaluation_at = utcnow() + timedelta(days=30)
        calib.status = "calibrated"
        calib.evaluated_predictions_count = total
        
        await db.flush()
        return calib
    
    # ------------------------------------------------------------------ Optimization
    
    async def run_optimization(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        objective: str,
        objective_type: str = "maximize",
        objective_json: Optional[Dict] = None,
        constraints: Optional[List[Dict]] = None,
        hard_constraints: Optional[List[Dict]] = None,
        soft_constraints: Optional[List[Dict]] = None,
        variables: Optional[Dict] = None,
        scope_type: str = "org",
        scope_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> OptimizationContext:
        """Run a constrained optimization over canonical reality."""
        
        # Create optimization context
        context = OptimizationContext(
            organization_id=organization_id,
            objective=objective,
            objective_type=objective_type,
            objective_json=json.dumps(objective_json) if objective_json else None,
            constraints_json=json.dumps(constraints) if constraints else None,
            hard_constraints_json=json.dumps(hard_constraints) if hard_constraints else None,
            soft_constraints_json=json.dumps(soft_constraints) if soft_constraints else None,
            variables_json=json.dumps(variables) if variables else None,
            scope_type=scope_type,
            scope_id=scope_id,
            status="analyzing",
            created_by=created_by,
        )
        
        db.add(OptimizationContext)
        await db.flush()
        
        # In a real implementation, this would call an optimization solver
        # For now, create a placeholder alternative
        alternative = OptimizationAlternative(
            context_id=OptimizationContext.id,
            rank=1,
            solution_json=json.dumps({"note": "placeholder"}),
            objective_value=0.0,
            hard_constraints_satisfied=True,
            is_feasible=True,
            feasibility_score=1.0,
        )
        db.add(OptimizationAlternative)
        
        OptimizationContext.status = "ranked"
        OptimizationContext.best_solution_json = json.dumps({})
        OptimizationContext.best_objective_value = 0.0
        
        await db.flush()
        
        return OptimizationContext
    
    # ------------------------------------------------------------------ Continuous Learning
    
    async def process_learning_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        limit: int = 100,
    ) -> List[LearningSignal]:
        """Process open learning signals and generate lessons."""
        
        result = await db.execute(
            select(LearningSignal).where(
                LearningSignal.organization_id == organization_id,
                LearningSignal.status == "open",
            ).order_by(LearningSignal.priority.desc()).limit(limit)
        )
        signals = result.scalars().all()
        
        processed = []
        for signal in signals:
            signal.status = "investigating"
            # In a real implementation, this would analyze the signal
            # and create lessons via organizational_learning_service
            signal.status = "learned"
            signal.resolved_at = utcnow()
            signal.resolved_by = "system"
            signal.resolution_note = "Auto-resolved by continuous learning"
            
            await db.flush()
            processed.append(signal)
        
        return processed
    
    async def run_learning_session(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        session_type: str = "incremental",
        scope_type: str = "org",
        scope_id: Optional[str] = None,
        triggered_by: Optional[str] = None,
    ) -> ContinuousLearningSession:
        """Run a continuous learning session."""
        
        session = ContinuousLearningSession(
            organization_id=organization_id,
            session_type=session_type,
            scope_type=scope_type,
            scope_id=scope_id,
            triggered_by=triggered_by,
            status="running",
            started_at=utcnow(),
        )
        db.add(session)
        await db.flush()
        
        # Process signals
        signals = await self.process_learning_signals(db, organization_id)
        
        session.status = "completed"
        session.completed_at = utcnow()
        session.signals_processed = len(signals)
        session.lessons_generated = 0  # Would be populated by learning service
        
        await db.flush()
        return session
    
    # ------------------------------------------------------------------ Institutional Memory
    
    async def record_institutional_memory(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        kind: str,
        fingerprint: str,
        title: str,
        summary: Optional[str] = None,
        content_json: Dict[str, Any],
        source_type: str,
        source_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
        confidence: float = 0.5,
        evidence_fingerprints: Optional[List[str]] = None,
        applicable_contexts: Optional[List[Dict]] = None,
        conditions: Optional[List[str]] = None,
    ) -> InstitutionalMemoryEntry:
        """Record a new institutional memory entry."""
        
        # Check for existing
        existing = await db.execute(
            select(InstitutionalMemoryEntry).where(
                InstitutionalMemoryEntry.organization_id == organization_id,
                InstitutionalMemoryEntry.kind == kind,
                InstitutionalMemoryEntry.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        
        if existing:
            # Update existing
            existing.content_json = json.dumps(content_json)
            existing.confidence = confidence
            existing.evidence_fingerprints = evidence_fingerprints or []
            existing.updated_at = utcnow()
            await db.flush()
            return existing
        
        entry = InstitutionalMemoryEntry(
            organization_id=organization_id,
            kind=kind,
            fingerprint=fingerprint,
            title=title,
            summary=summary,
            content_json=json.dumps(content_json),
            source_type=source_type,
            source_id=source_id,
            source_event_id=source_event_id,
            confidence=confidence,
            evidence_fingerprints=evidence_fingerprints or [],
        )
        
        db.add(entry)
        await db.flush()
        return entry
    
    # ------------------------------------------------------------------ Attention & Drift
    
    async def create_attention(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        attention_type: str,
        priority: str = "info",
        title: str,
        description: Optional[str] = None,
        details_json: Optional[Dict] = None,
        source_type: str = "system",
        source_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
        assigned_to: Optional[str] = None,
        urgency: str = "normal",
    ) -> CompanyAttention:
        """Create an attention signal."""
        
        priority_map = {"info": 0, "watch": 25, "alert": 50, "critical": 100}
        
        attention = CompanyAttention(
            organization_id=organization_id,
            attention_type=attention_type,
            priority=priority,
            title=title,
            description=description,
            details_json=json.dumps(details_json) if details_json else None,
            source_type=source_type,
            source_id=source_id,
            source_event_id=source_event_id,
            priority_score=priority_map.get(priority, 0),
            urgency=urgency,
            assigned_to=assigned_to,
            assigned_at=utcnow() if assigned_to else None,
            assigned_by="system",
        )
        
        db.add(attention)
        await db.flush()
        return attention
    
    async def resolve_attention(
        self,
        db: AsyncSession,
        attention_id: str,
        resolved_by: str,
        resolution_note: Optional[str] = None,
    ) -> CompanyAttention:
        """Resolve an attention signal."""
        
        attention = await db.get(CompanyAttention, attention_id)
        if not attention:
            raise ValueError("Attention not found")
        
        attention.status = "resolved"
        attention.resolved_at = utcnow()
        attention.resolved_by = resolved_by
        attention.resolution_note = resolution_note
        
        await db.flush()
        return attention
    
    async def detect_and_record_drift(
        self,
        db: AsyncSession,
        organization_id: str,
        drift_type: str,
        severity: str,
        subject_type: str,
        subject_id: str,
        expected: Optional[Dict] = None,
        observed: Optional[Dict] = None,
        deviation_score: float = 0.0,
        severity_score: float = 0.0,
        evidence: Optional[Dict] = None,
    ) -> ModelTwinDrift:
        """Record a model/twin drift."""
        
        drift = ModelTwinDrift(
            organization_id=organization_id,
            drift_type=drift_type,
            level=severity,
            subject_type=subject_type,
            subject_id=subject_id,
            expected_json=json.dumps(expected) if expected else None,
            observed_json=json.dumps(observed) if observed else None,
            deviation_score=deviation_score,
            severity_score=severity_score,
            evidence_json=json.dumps(evidence) if evidence else None,
            detected_by="system",
            detected_at=utcnow(),
        )
        
        db.add(drift)
        await db.flush()
        return drift
    
    # ------------------------------------------------------------------ Twin Context & Scopes
    
    async def create_twin_scope(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope_type: str = "org",
        scope_id: Optional[str] = None,
        name: str,
        description: Optional[str] = None,
        included_dimensions: Optional[List[str]] = None,
        auto_refresh: bool = True,
        refresh_interval_seconds: int = 300,
    ) -> TwinScope:
        """Create a twin scope."""
        
        scope = TwinScope(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            name=name,
            description=description,
            included_dimensions_json=json.dumps(included_dimensions or []),
            auto_refresh=auto_refresh,
            refresh_interval_seconds=refresh_interval_seconds,
        )
        
        db.add(scope)
        await db.flush()
        return scope
    
    async def get_twin_context(
        self,
        db: AsyncSession,
        organization_id: str,
        scope_id: str,
        context_type: str,
        context_json: Dict,
        input_fingerprint: str,
    ) -> TwinContext:
        """Create or update a twin context."""
        
        context = TwinContext(
            organization_id=organization_id,
            scope_id=scope_id,
            context_type=context_type,
            context_json=context_json,
            input_fingerprint=input_fingerprint,
            fingerprint=hashlib.sha256(
                f"{organization_id}:{scope_id}:{context_type}:{input_fingerprint}".encode()
            ).hexdigest()[:160],
        )
        
        db.add(context)
        await db.flush()
        return context
    
    # ------------------------------------------------------------------ State Projection
    
    async def update_state_projection(
        self,
        db: AsyncSession,
        organization_id: str,
        dimension: str,
        state_json: Dict,
        event_id: Optional[str] = None,
    ) -> ContinuousStateProjection:
        """Update a continuous state projection."""
        
        state_hash = hashlib.sha256(
            json.dumps(state_json, sort_keys=True).encode()
        ).hexdigest()[:64]
        
        result = await db.execute(
            select(ContinuousStateProjection).where(
                ContinuousStateProjection.organization_id == organization_id,
                ContinuousStateProjection.dimension == dimension,
            )
        )
        projection = result.scalars().first()
        
        if projection:
            projection.current_state_json = json.dumps(state_json)
            projection.current_state_hash = hashlib.sha256(
                json.dumps(state_json, sort_keys=True).encode()
            ).hexdigest()[:64]
            projection.last_event_id = event_id
            projection.last_event_at = utcnow()
            projection.events_processed += 1
            projection.last_refreshed_at = utcnow()
        else:
            projection = ContinuousStateProjection(
                organization_id=organization_id,
                dimension=dimension,
                current_state_json=json.dumps(state_json),
                current_state_hash=hashlib.sha256(
                    json.dumps(state_json, sort_keys=True).encode()
                ).hexdigest()[:64],
                last_event_id=event_id,
                last_event_at=utcnow(),
                events_processed=1,
                last_refreshed_at=utcnow(),
            )
            db.add(projection)
        
        await db.flush()
        return projection
    
    # ------------------------------------------------------------------ Cache Management
    
    async def invalidate_eligibility_cache(
        self,
        db: AsyncSession,
        organization_id: str,
        actor_id: Optional[str] = None,
        proposal_type: Optional[str] = None,
    ) -> int:
        """Invalidate eligibility cache entries."""
        
        query = select(AutonomyEligibilityCache).where(
            AutonomyEligibilityCache.organization_id == organization_id,
            AutonomyEligibilityCache.invalidated == False,
        )
        if actor_id:
            query = query.where(AutonomyEligibilityCache.cache_key.contains(actor_id))
        if proposal_type:
            query = query.where(AutonomyEligibilityCache.cache_key.contains(proposal_type))
        
        result = await db.execute(query)
        caches = result.scalars().all()
        
        count = 0
        for cache in caches:
            cache.invalidated = True
            cache.invalidated_at = utcnow()
            cache.invalidated_by = "system"
            cache.invalidation_reason = "policy_or_entitlement_change"
            count += 1
        
        await db.flush()
        return count
    
    # ------------------------------------------------------------------ Event Logging
    
    async def _log_audit(
        self,
        db: AsyncSession,
        organization_id: str,
        action: str,
        actor_id: Optional[str],
        resource_type: str,
        resource_id: str,
        details: Optional[Dict] = None,
    ) -> None:
        """Log audit event."""
        await audit_service.log(
            db,
            organization_id=organization_id,
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )

    # ------------------------------------------------------------------ Proposal Queries
    
    async def get_proposal(self, db: AsyncSession, proposal_id: str) -> Optional[AutonomyProposal]:
        return await db.get(AutonomyProposal, proposal_id)

    async def get_proposal_by_fingerprint(
        self, db: AsyncSession, organization_id: str, fingerprint: str
    ) -> Optional[AutonomyProposal]:
        result = await db.execute(
            select(AutonomyProposal).where(
                AutonomyProposal.organization_id == organization_id,
                AutonomyProposal.fingerprint == fingerprint,
            )
        )
        return result.scalar_one_or_none()

    async def list_proposals(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        state: Optional[str] = None,
        proposal_type: Optional[str] = None,
        actor_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AutonomyProposal]:
        query = select(AutonomyProposal).where(AutonomyProposal.organization_id == organization_id)
        if state:
            query = query.where(AutonomyProposal.state == state)
        if proposal_type:
            query = query.where(AutonomyProposal.proposal_type == proposal_type)
        if actor_id:
            query = query.where(AutonomyProposal.actor_id == actor_id)
        query = query.order_by(AutonomyProposal.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())


continuous_twin_service = ContinuousTwinService()