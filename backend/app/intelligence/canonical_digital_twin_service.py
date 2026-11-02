"""Canonical Digital Twin / Future Company State — Gate 12.

The Digital Twin is a DERIVED PROJECTION over canonical company reality.
It is NOT a second source of truth — it composes, projects, and reasons
over the ONE canonical company reality established by Gates 6-11.

Architecture:
  ONE CANONICAL COMPANY REALITY
        |
        +-- Actual state (CompanyDecision, CompanyCommitment, etc.)
        +-- Historical state (CompanyStateHistory, CompanyScenarioRun)
        +-- Counterfactual projection (Gate 11 CompanyScenarioRun)
        +-- Predicted state (Gate 10 Prediction)
        +-- Future-state projection (this service)
        |
        +-- Company Brain (4I.1/4I.2)
        +-- Institutional Learning (Gate 9)
        +-- Prediction (Gate 10)
        +-- Counterfactual (Gate 11)

The twin derives from:
- CompanyDecision / CompanyCommitment / CompanyAction / CompanyActionOutcome
- CompanyObjective / CompanyInitiative / CompanyGoal
- OrganizationalResponsibility / AccountabilityLink
- CompanyAuthorization / CompanyAuthorizationPolicy
- CompanyScenarioRun (Gate 11 counterfactuals)
- Prediction / PredictionHistory (Gate 10)
- OrganizationalLearning / PatternDetection (Gate 9)
- CompanyStateHistory (temporal)
- Cross-domain intelligence services

NEVER creates:
- DigitalTwinGraph
- ScenarioGraph
- SimulationDatabase
- FutureCompanyDatabase
- TwinBrain / TwinMemory / TwinPredictionEngine
"""

import json
import logging
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow, ensure_aware
from app.intelligence.company_context import CallerAccess
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionPrecedent,
    CompanyDecisionContradiction,
    CompanyDecisionQuality,
    CompanyDecisionTrack,
    CompanyDecisionEvidence,
    CompanyScenarioRun,
    CompanyStateHistory,
    CompanyHealthHistory,
)
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
    CompanyObjective,
    CompanyInitiative,
    CompanyGoal,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.organizational_learning import (
    OrganizationalLearning,
    LearningEvidence,
)
from app.models.intelligence import (
    PatternDetection,
    PatternEvent,
)
from app.models.prediction import (
    Prediction,
    PredictionHistory,
    PredictionModel,
)
from app.models.company_memory import (
    CompanyMemory,
    MemoryEvent,
    MemoryOutcome,
)
from app.models.execution_strategy import (
    ObjectivePrediction,
    ObjectiveSimulation,
)
from app.models.digital_twin import (
    TwinPrediction,
    StrategicForecast,
)
from app.intelligence.institutional_intelligence_service import (
    institutional_intelligence_service,
)
from app.intelligence.predictive_intelligence_service import (
    predictive_intelligence_service,
)
from app.intelligence.organizational_capacity_service import (
    organizational_capacity_service,
)
from app.intelligence.organizational_intelligence_service import (
    organizational_intelligence_service,
)
from app.intelligence.counterfactual_intelligence_service import (
    counterfactual_intelligence_service,
    ScenarioKind,
)
from app.intelligence.cross_domain_impact_service import (
    cross_domain_impact_service,
)
from app.intelligence.company_operating_engine import (
    company_operating_engine,
)

logger = logging.getLogger("vcos.intelligence.canonical_digital_twin")


class TwinScopeType(str, Enum):
    """Scope types for digital twin derivation."""
    ORG = "org"
    DEPARTMENT = "department"
    TEAM = "team"
    PROJECT = "project"
    PERSON = "person"


@dataclass
class TwinState:
    """A point-in-time canonical company state projection."""
    organization_id: str
    scope_type: str
    scope_id: Optional[str]
    captured_at: datetime
    state_key: str
    snapshot_ref: str
    
    # Canonical dimensions
    strategy: Dict[str, Any] = field(default_factory=dict)
    execution: Dict[str, Any] = field(default_factory=dict)
    coordination: Dict[str, Any] = field(default_factory=dict)
    capacity: Dict[str, Any] = field(default_factory=dict)
    people: Dict[str, Any] = field(default_factory=dict)
    customers: Dict[str, Any] = field(default_factory=dict)
    financial: Dict[str, Any] = field(default_factory=dict)
    knowledge: Dict[str, Any] = field(default_factory=dict)
    
    # Cross-cutting
    attention: List[Dict[str, Any]] = field(default_factory=list)
    health_score: Optional[float] = None
    health_state: Optional[str] = None
    
    # Projections
    predictions: List[Dict[str, Any]] = field(default_factory=list)
    counterfactual_scenarios: List[Dict[str, Any]] = field(default_factory=list)
    institutional_basis: List[Dict[str, Any]] = field(default_factory=list)
    
    # Provenance
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TwinScenarioBranch:
    """A counterfactual branch from a baseline twin state."""
    branch_id: str
    baseline_state_key: str
    scenario_kind: str
    subject_type: str
    subject_id: str
    params: Dict[str, Any]
    assumptions: List[str]
    created_at: datetime
    
    # Derived projection
    projected_state: Optional[Dict[str, Any]] = None
    projected_predictions: List[Dict[str, Any]] = field(default_factory=list)
    projected_risks: List[Dict[str, Any]] = field(default_factory=list)
    projected_opportunities: List[Dict[str, Any]] = field(default_factory=list)
    comparison: Optional[Dict[str, Any]] = None
    recommendation: Optional[Dict[str, Any]] = None


@dataclass
class TwinComparison:
    """Comparison of multiple scenario branches."""
    comparison_id: str
    baseline_state_key: str
    branches: List[TwinScenarioBranch]
    comparison_matrix: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    derived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CanonicalDigitalTwinService:
    """Service for deriving the canonical digital twin from company reality."""
    
    # Supported scope types
    SCOPE_TYPES = frozenset([
        "org",
        "department", 
        "team",
        "project",
        "person",
    ])
    
    # Maximum scenario branches per comparison
    MAX_BRANCHES = 10
    
    # Projection horizon defaults
    DEFAULT_HORIZON_DAYS = 90
    
    def __init__(self):
        pass
    
    # ================================================================
    # MAIN ENTRY POINTS
    # ================================================================
    
    async def derive_twin_state(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scope_type: str = "org",
        scope_id: Optional[str] = None,
        as_of: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Derive the canonical company state at a point in time.
        
        This is the core twin derivation — it composes the canonical
        engines' outputs into a single governed projection.
        
        Args:
            db: Database session
            caller: Governance-resolved caller access
            scope_type: Scope level (org, department, team, project, person)
            scope_id: Specific scope identifier
            as_of: Optional ISO timestamp for historical point-in-time
            
        Returns:
            Complete twin state projection with provenance
        """
        # Governance check
        if scope_type not in self.SCOPE_TYPES:
            scope_type = "org"
        
        if not caller.org_wide and scope_type == "org":
            # Non-org-wide callers get department/team scope
            pass  # Would add scope resolution here
        
        # 1. Capture canonical baseline using existing 4H.3 infrastructure
        baseline_dict = await company_operating_engine._scenario_baseline(
            db, organization_id=caller.organization_id,
            scope_type=scope_type, scope_id=scope_id, as_of=as_of
        )
        
        snapshot_ref = baseline_dict.get("snapshot_ref")
        state_key = baseline_dict.get("state_key")
        
        # 2. Derive each canonical dimension
        dimensions = await self._derive_dimensions(
            db, caller, scope_type, scope_id, as_of
        )
        
        # 3. Compute cross-cutting attention and health
        attention = await self._derive_attention(db, caller, dimensions)
        health_score, health_state = self._compute_health_score(dimensions)
        
        # 4. Get active predictions (Gate 10)
        predictions = await self._derive_predictions(
            db, caller, scope_type, scope_id, as_of
        )
        
        # 5. Get active counterfactual scenarios (Gate 11)
        counterfactuals = await self._derive_counterfactuals(
            db, caller, scope_type, scope_id, as_of
        )
        
        # 6. Get institutional learning basis (Gate 9)
        institutional_basis = await self._derive_institutional_basis(
            db, caller, scope_type, scope_id
        )
        
        # 7. Build provenance
        provenance = await self._build_provenance(
            db, caller, baseline_dict, dimensions
        )
        
        # 8. Construct twin state
        twin_state = TwinState(
            organization_id=caller.organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            captured_at=utcnow(),
            state_key=state_key or f"st:{caller.organization_id}:{scope_type}:{scope_id or 'org'}",
            snapshot_ref=snapshot_ref or "no-baseline",
            strategy=dimensions.get("strategy", {}),
            execution=dimensions.get("execution", {}),
            coordination=dimensions.get("coordination", {}),
            capacity=dimensions.get("capacity", {}),
            people=dimensions.get("people", {}),
            customers=dimensions.get("customers", {}),
            financial=dimensions.get("financial", {}),
            knowledge=dimensions.get("knowledge", {}),
            attention=attention,
            health_score=health_score,
            health_state=health_state,
            predictions=predictions,
            counterfactual_scenarios=counterfactuals,
            institutional_basis=institutional_basis,
            provenance=provenance,
        )
        
        return self._twin_state_to_surface(twin_state)
    
    async def derive_twin_history(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scope_type: str = "org",
        scope_id: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """Derive historical twin states from CompanyStateHistory.
        
        Returns point-in-time states showing company evolution.
        """
        if scope_type not in self.SCOPE_TYPES:
            scope_type = "org"
        
        query = select(CompanyStateHistory).where(
            CompanyStateHistory.organization_id == caller.organization_id,
            CompanyStateHistory.scope_type == scope_type,
        )
        if scope_id:
            query = query.where(CompanyStateHistory.scope_id == scope_id)
        
        query = query.order_by(desc(CompanyStateHistory.occurred_at)).limit(limit)
        result = await db.execute(query)
        
        history = []
        for row in result.scalars().all():
            # CompanyStateHistory uses dimensions_json as the state representation
            state = {}
            if row.dimensions_json:
                try:
                    state = {"dimensions": row.dimensions_json}
                except (TypeError,):
                    state = {}
            
            history.append({
                "id": row.id,
                "captured_at": ensure_aware(row.occurred_at).isoformat() if row.occurred_at else None,
                "state_key": row.state_key,
                "snapshot_ref": row.source_event_id,
                "scope_type": row.scope_type,
                "scope_id": row.scope_id,
                "state": state,
                "summary": {
                    "delta_count": len(row.delta_json) if row.delta_json else 0,
                    "risk_count": len(row.risks_json) if row.risks_json else 0,
                    "opportunity_count": len(row.opportunities_json) if row.opportunities_json else 0,
                    "attention_count": len(row.attention_json) if row.attention_json else 0,
                },
                "event_name": getattr(row, 'event_name', None),
                "source_event_id": row.source_event_id,
            })
        
        return history
    
    async def create_scenario_branch(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scenario_kind: str,
        subject_type: str,
        subject_id: str,
        params: Optional[Dict[str, Any]] = None,
        assumptions: Optional[List[str]] = None,
        scope_type: str = "org",
        scope_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Create a counterfactual scenario branch from current twin state.
        
        This integrates Gate 11 counterfactual intelligence.
        The branch is an isolated projection — does not mutate canonical reality.
        """
        kind = (scenario_kind or "").strip().lower()
        st = (subject_type or "").strip().lower()
        sid = (subject_id or "").strip()
        
        if kind not in counterfactual_intelligence_service.SCENARIO_KINDS:
            return {
                "advisory_only": True,
                "not_a_prediction": True,
                "error": f"scenario_kind must be one of {', '.join(sorted(counterfactual_intelligence_service.SCENARIO_KINDS))}",
                "generated_at": utcnow().isoformat(),
            }
        
        if not st or not sid:
            return {
                "advisory_only": True,
                "not_a_prediction": True,
                "error": "subject_type and subject_id are required",
                "generated_at": utcnow().isoformat(),
            }
        
        params = params or {}
        assumptions = assumptions or []
        
        # 1. Get current baseline twin state
        baseline_result = await self.derive_twin_state(
            db, caller=caller, scope_type=scope_type, scope_id=scope_id
        )
        baseline_state_key = baseline_result["state_key"]
        baseline_snapshot_ref = baseline_result["snapshot_ref"]
        
        # 2. Run counterfactual scenario via Gate 11
        scenario_result = await counterfactual_intelligence_service.create_scenario(
            db,
            caller=caller,
            scenario_kind=kind,
            subject_type=st,
            subject_id=sid,
            params=params,
            assumptions=assumptions,
            scope_type=scope_type,
            scope_id=scope_id,
            dry_run=dry_run,
        )
        
        # 3. Build scenario branch
        branch_id = f"branch-{kind}-{st}-{sid}-{uuid.uuid4().hex[:8]}"
        branch = TwinScenarioBranch(
            branch_id=branch_id,
            baseline_state_key=baseline_state_key,
            scenario_kind=kind,
            subject_type=st,
            subject_id=sid,
            params=params,
            assumptions=assumptions,
            created_at=utcnow(),
            projected_state=scenario_result.get("consequences", {}),
            projected_predictions=scenario_result.get("predictions", []),
            projected_risks=scenario_result.get("risks", []),
            projected_opportunities=scenario_result.get("opportunities", []),
            comparison=scenario_result.get("comparison"),
            recommendation=None,  # Single branch has no comparison yet
        )
        
        # 4. Generate recommendation for single branch vs baseline
        branch.recommendation = self._generate_branch_recommendation(
            baseline_result, branch
        )
        
        return self._branch_to_surface(branch, baseline_result)
    
    async def compare_scenario_branches(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scenario_definitions: List[Dict[str, Any]],
        scope_type: str = "org",
        scope_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compare multiple scenario branches against the same baseline.
        
        Extends Gate 11 comparison with deeper multi-domain evaluation.
        """
        if len(scenario_definitions) < 2:
            return {
                "advisory_only": True,
                "not_a_prediction": True,
                "error": "At least 2 scenarios required for comparison",
                "generated_at": utcnow().isoformat(),
            }
        
        if len(scenario_definitions) > self.MAX_BRANCHES:
            scenario_definitions = scenario_definitions[:self.MAX_BRANCHES]
        
        # 1. Get single baseline for all scenarios
        baseline_result = await self.derive_twin_state(
            db, caller=caller, scope_type=scope_type, scope_id=scope_id
        )
        baseline_state_key = baseline_result["state_key"]
        
        # 2. Create all branches
        branches = []
        for scenario_def in scenario_definitions:
            kind = scenario_def.get("scenario_kind", "").strip().lower()
            st = scenario_def.get("subject_type", "").strip().lower()
            sid = scenario_def.get("subject_id", "").strip()
            
            if kind not in counterfactual_intelligence_service.SCENARIO_KINDS or not sid:
                continue
            
            # Run counterfactual via Gate 11
            scenario_result = await counterfactual_intelligence_service.create_scenario(
                db,
                caller=caller,
                scenario_kind=kind,
                subject_type=st,
                subject_id=sid,
                params=scenario_def.get("params", {}),
                assumptions=scenario_def.get("assumptions", []),
                scope_type=scope_type,
                scope_id=scope_id,
                dry_run=True,  # Comparison is always exploration
            )
            
            branch_id = f"cmp-{kind}-{st}-{sid}-{uuid.uuid4().hex[:8]}"
            branch = TwinScenarioBranch(
                branch_id=branch_id,
                baseline_state_key=baseline_state_key,
                scenario_kind=kind,
                subject_type=st,
                subject_id=sid,
                params=scenario_def.get("params", {}),
                assumptions=scenario_def.get("assumptions", []),
                created_at=utcnow(),
                projected_state=scenario_result.get("consequences", {}),
                projected_predictions=scenario_result.get("predictions", []),
                projected_risks=scenario_result.get("risks", []),
                projected_opportunities=scenario_result.get("opportunities", []),
            )
            branches.append(branch)
        
        # 3. Build deep comparison
        comparison = self._build_deep_comparison(baseline_result, branches)
        
        twin_comparison = TwinComparison(
            comparison_id=f"twin-cmp-{uuid.uuid4().hex[:8]}",
            baseline_state_key=baseline_state_key,
            branches=branches,
            comparison_matrix=comparison.get("comparison_matrix", {}),
            recommendations=comparison.get("recommendations", []),
        )
        
        return self._comparison_to_surface(twin_comparison, baseline_result)
    
    async def get_scenario_history(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        scenario_kind: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get historical scenario runs (CompanyScenarioRun from Gate 11)."""
        query = select(CompanyScenarioRun).where(
            CompanyScenarioRun.organization_id == caller.organization_id,
        )
        
        if scope_type:
            query = query.where(CompanyScenarioRun.scope_type == scope_type)
        if scope_id:
            query = query.where(CompanyScenarioRun.scope_id == scope_id)
        if scenario_kind:
            query = query.where(CompanyScenarioRun.scenario_kind == scenario_kind)
        
        query = query.order_by(desc(CompanyScenarioRun.occurred_at)).limit(limit)
        result = await db.execute(query)
        
        return [self._scenario_run_to_surface(row) for row in result.scalars().all()]
    
    # ================================================================
    # DIMENSION DERIVATION
    # ================================================================
    
    async def _derive_dimensions(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        scope_type: str,
        scope_id: Optional[str],
        as_of: Optional[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Derive all canonical dimensions by composing existing engines."""
        
        # Use the existing company operating engine to get full state
        company_state = await company_operating_engine.company_state(
            db, organization_id=caller.organization_id
        )
        
        # Also get health assessment
        health = await company_operating_engine.health(
            db, organization_id=caller.organization_id
        )
        
        # Extract dimensions from company_state
        dimensions = company_state.get("dimensions", {})
        
        # Add health domains
        for domain in health.get("domains", []):
            key = domain.get("key")
            if key and key in dimensions:
                dimensions[key]["health_score"] = domain.get("score")
                dimensions[key]["health_state"] = domain.get("state")
                dimensions[key]["health_reasons"] = domain.get("reasons", [])
        
        return dimensions
    
    async def _derive_attention(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        dimensions: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Derive cross-cutting attention items from all dimensions."""
        attention = []
        
        # Collect from each dimension
        for key, dim in dimensions.items():
            if dim.get("health_score", 100) < 75:
                attention.append({
                    "priority": 1 if dim.get("health_score", 100) < 50 else 2,
                    "kind": f"{key}_health",
                    "title": f"{dim.get('label', key)} is {dim.get('health_state', 'concerned')} ({dim.get('health_score', 0)}/100)",
                    "why": dim.get("health_reasons", ["attention needed"])[0] if dim.get("health_reasons") else "attention needed",
                    "domain": key,
                })
        
        # Add organizational attention from Gate 8.5
        try:
            org_attention = await organizational_attention_service.derive_organizational_attention(
                db, caller=caller
            )
            for item in org_attention:
                attention.append({
                    "priority": 1 if item.get("kind") in ("critical_person_dependency", "organizational_bottleneck") else 2,
                    "kind": f"organizational_{item.get('kind')}",
                    "title": item.get("title", item.get("kind")),
                    "why": item.get("summary", ""),
                    "domain": "organizational",
                    "source": "organizational_attention",
                })
        except Exception:
            pass  # Graceful degradation
        
        # Sort by priority and limit
        attention.sort(key=lambda a: a.get("priority", 3))
        return attention[:10]
    
    def _compute_health_score(
        self,
        dimensions: Dict[str, Dict[str, Any]],
    ) -> tuple[Optional[float], Optional[str]]:
        """Compute unified health score from dimensions."""
        from app.models.company_operating import DOMAIN_WEIGHTS
        
        scores = []
        for key, dim in dimensions.items():
            score = dim.get("health_score")
            if score is not None:
                weight = DOMAIN_WEIGHTS.get(key, 0.0)
                scores.append((weight, score))
        
        if not scores:
            return None, None
        
        weighted = sum(w * s for w, s in scores)
        total_weight = sum(w for w, _ in scores)
        score = weighted / total_weight if total_weight > 0 else 0
        
        if score >= 75:
            state = "healthy"
        elif score >= 50:
            state = "concerned"
        elif score >= 30:
            state = "at_risk"
        else:
            state = "critical"
        
        return round(score, 1), state
    
    # ================================================================
    # PREDICTION INTEGRATION (Gate 10)
    # ================================================================
    
    async def _derive_predictions(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        scope_type: str,
        scope_id: Optional[str],
        as_of: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Derive active predictions from Gate 10 predictive intelligence."""
        predictions = []
        
        # Get predictive intelligence predictions
        try:
            pred_result = await predictive_intelligence_service.derive_predictions(
                db, caller=caller, scope_type=scope_type, scope_id=scope_id
            )
            for p in pred_result.get("predictions", []):
                predictions.append({
                    "type": p.get("type"),
                    "subject_type": p.get("subject_type"),
                    "subject_id": p.get("subject_id"),
                    "title": p.get("title"),
                    "probability": p.get("probability"),
                    "confidence": p.get("confidence"),
                    "horizon_days": p.get("horizon_days"),
                    "basis": p.get("basis"),
                    "source": "predictive_intelligence",
                })
        except Exception:
            pass  # Graceful degradation
        
        # Get ObjectivePredictions (4I.2)
        try:
            obj_preds = await db.execute(
                select(ObjectivePrediction).where(
                    ObjectivePrediction.organization_id == caller.organization_id,
                    ObjectivePrediction.status == "active",
                ).limit(20)
            )
            for p in obj_preds.scalars().all():
                predictions.append({
                    "type": "objective_trajectory",
                    "subject_type": "objective",
                    "subject_id": p.objective_id,
                    "title": f"Objective trajectory: {p.prediction_type}",
                    "probability": p.probability,
                    "confidence": p.confidence,
                    "horizon_days": p.horizon_days,
                    "basis": "objective_prediction",
                    "source": "objective_prediction",
                })
        except Exception:
            pass
        
        # Get TwinPredictions (Phase 18)
        try:
            twin_preds = await db.execute(
                select(TwinPrediction).where(
                    TwinPrediction.organization_id == caller.organization_id,
                    TwinPrediction.status == "active",
                ).limit(20)
            )
            for p in twin_preds.scalars().all():
                predictions.append({
                    "type": p.kind,
                    "subject_type": p.subject_type,
                    "subject_id": p.subject_id,
                    "title": p.title,
                    "probability": p.probability / 100.0 if p.probability > 1 else p.probability,
                    "confidence": 0.7,
                    "horizon_days": p.horizon_days,
                    "basis": "twin_prediction",
                    "source": "twin_prediction",
                })
        except Exception:
            pass
        
        return predictions
    
    # ================================================================
    # COUNTERFACTUAL INTEGRATION (Gate 11)
    # ================================================================
    
    async def _derive_counterfactuals(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        scope_type: str,
        scope_id: Optional[str],
        as_of: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Derive active counterfactual scenarios from Gate 11."""
        counterfactuals = []
        
        try:
            history = await counterfactual_intelligence_service.get_scenario_history(
                db, caller=caller, scope_type=scope_type, scope_id=scope_id, limit=20
            )
            for s in history:
                counterfactuals.append({
                    "scenario_id": s.get("scenario_id"),
                    "scenario_kind": s.get("hypothetical_change", {}).get("scenario_kind"),
                    "subject_type": s.get("hypothetical_change", {}).get("subject_type"),
                    "subject_id": s.get("hypothetical_change", {}).get("subject_id"),
                    "params": s.get("hypothetical_change", {}).get("params", {}),
                    "created_at": s.get("occurred_at"),
                    "risk_count": len(s.get("consequences", {}).get("risks_already_present", [])) + len(s.get("direct_effects", [])),
                    "source": "counterfactual_intelligence",
                })
        except Exception:
            pass
        
        return counterfactuals
    
    # ================================================================
    # INSTITUTIONAL LEARNING INTEGRATION (Gate 9)
    # ================================================================
    
    async def _derive_institutional_basis(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        scope_type: str,
        scope_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Derive institutional learning basis from Gate 9."""
        basis = []
        
        try:
            inst_result = await institutional_intelligence_service.derive_institutional_intelligence(
                db, caller=caller, scope_type=scope_type, scope_id=scope_id
            )
            
            for lesson in inst_result.get("lessons", []):
                basis.append({
                    "type": "lesson",
                    "id": lesson.get("id"),
                    "kind": lesson.get("kind"),
                    "title": lesson.get("title"),
                    "lifecycle": lesson.get("lifecycle"),
                    "confidence": lesson.get("confidence"),
                    "relevance": lesson.get("relevance", 0.5),
                })
            
            for pattern in inst_result.get("patterns", []):
                basis.append({
                    "type": "pattern",
                    "id": pattern.get("id"),
                    "pattern_type": pattern.get("pattern_type"),
                    "family": pattern.get("family"),
                    "count": pattern.get("count"),
                    "confidence": pattern.get("confidence"),
                    "relevance": pattern.get("relevance", 0.5),
                })
        except Exception:
            pass
        
        return basis
    
    # ================================================================
    # PROVENANCE
    # ================================================================
    
    async def _build_provenance(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        baseline_dict: Dict[str, Any],
        dimensions: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build complete provenance for twin derivation."""
        
        return {
            "derived_from": "canonical_reality",
            "baseline_snapshot": baseline_dict.get("snapshot_ref"),
            "baseline_state_key": baseline_dict.get("state_key"),
            "baseline_captured_at": baseline_dict.get("occurred_at"),
            "scope": {
                "scope_type": baseline_dict.get("scope_type"),
                "scope_id": baseline_dict.get("scope_id"),
            },
            "dimensions_derived": list(dimensions.keys()),
            "derived_at": utcnow().isoformat(),
            "derived_by": caller.employee_id or "system",
            "model_version": "gate12-v1",
            "algorithm_identity": "canonical_digital_twin_service:v1",
            "epistemic_notice": (
                "This is a derived projection over canonical reality. "
                "It is advisory only — not a prediction, not a decision, not execution."
            ),
        }
    
    # ================================================================
    # COMPARISON & RECOMMENDATION
    # ================================================================
    
    def _build_deep_comparison(
        self,
        baseline_result: Dict[str, Any],
        branches: List[TwinScenarioBranch],
    ) -> Dict[str, Any]:
        """Build deep multi-domain comparison of scenario branches."""
        
        comparison = {
            "baseline": {
                "state_key": baseline_result["state_key"],
                "snapshot_ref": baseline_result["snapshot_ref"],
                "health_score": baseline_result.get("health_score"),
                "health_state": baseline_result.get("health_state"),
                "dimensions": {
                    k: v.get("health_score") for k, v in baseline_result.get("dimensions", {}).items()
                    if v.get("health_score") is not None
                },
            },
            "branches": [],
            "comparison_matrix": {},
            "recommendations": [],
        }
        
        # Build comparison for each branch
        for branch in branches:
            # Compute projected health from branch consequences
            projected_health = self._project_health_from_consequences(
                baseline_result, branch.projected_state
            )
            
            branch_data = {
                "branch_id": branch.branch_id,
                "scenario": {
                    "kind": branch.scenario_kind,
                    "subject_type": branch.subject_type,
                    "subject_id": branch.subject_id,
                    "params": branch.params,
                },
                "projected_health": projected_health,
                "risk_count": len(branch.projected_risks),
                "critical_risks": len([r for r in branch.projected_risks if r.get("severity") in ("critical", "high")]),
                "opportunity_count": len(branch.projected_opportunities),
                "prediction_count": len(branch.projected_predictions),
                "high_confidence_predictions": len([p for p in branch.projected_predictions if p.get("confidence", 0) > 0.7]),
            }
            comparison["branches"].append(branch_data)
        
        # Build comparison matrix
        if len(branches) >= 2:
            comparison["comparison_matrix"] = self._build_comparison_matrix(branches)
            comparison["recommendations"] = self._generate_comparison_recommendations(branches)
        
        return comparison
    
    def _project_health_from_consequences(
        self,
        baseline_result: Dict[str, Any],
        consequences: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Project health impact from scenario consequences."""
        # Simplified projection based on consequences
        baseline_health = baseline_result.get("health_score", 75)
        
        # Adjust based on risks/opportunities
        risk_impact = len(consequences.get("risks_already_present", [])) * -5
        opportunity_impact = len(consequences.get("opportunities_already_present", [])) * 3
        
        projected = max(0, min(100, baseline_health + risk_impact + opportunity_impact))
        
        if projected >= 75:
            state = "healthy"
        elif projected >= 50:
            state = "concerned"
        elif projected >= 30:
            state = "at_risk"
        else:
            state = "critical"
        
        return {
            "score": projected,
            "state": state,
            "delta": round(projected - baseline_health, 1),
        }
    
    def _build_comparison_matrix(
        self,
        branches: List[TwinScenarioBranch],
    ) -> Dict[str, Any]:
        """Build detailed comparison matrix."""
        matrix = {
            "health": {},
            "risks": {},
            "opportunities": {},
            "predictions": {},
            "capacity_impact": {},
            "commitment_impact": {},
            "objective_impact": {},
        }
        
        for branch in branches:
            bid = branch.branch_id
            # Health projection
            matrix["health"][bid] = {
                "projected_score": 75,  # Would compute from consequences
                "delta": 0,
            }
            # Risks
            matrix["risks"][bid] = {
                "total": len(branch.projected_risks),
                "critical": len([r for r in branch.projected_risks if r.get("severity") == "critical"]),
                "high": len([r for r in branch.projected_risks if r.get("severity") == "high"]),
                "medium": len([r for r in branch.projected_risks if r.get("severity") == "medium"]),
            }
            # Opportunities
            matrix["opportunities"][bid] = {
                "total": len(branch.projected_opportunities),
            }
            # Predictions
            matrix["predictions"][bid] = {
                "total": len(branch.projected_predictions),
                "high_confidence": len([p for p in branch.projected_predictions if p.get("confidence", 0) > 0.7]),
            }
        
        return matrix
    
    def _generate_comparison_recommendations(
        self,
        branches: List[TwinScenarioBranch],
    ) -> List[Dict[str, Any]]:
        """Generate recommendations from branch comparison."""
        recommendations = []
        
        if len(branches) < 2:
            return recommendations
        
        # Lowest risk recommendation
        min_risk_branch = min(
            branches,
            key=lambda b: len([r for r in b.projected_risks if r.get("severity") in ("critical", "high")])
        )
        recommendations.append({
            "type": "lowest_risk",
            "branch_id": min_risk_branch.branch_id,
            "scenario_kind": min_risk_branch.scenario_kind,
            "reason": "Lowest high/critical risk count",
        })
        
        # Highest opportunity recommendation
        max_opp_branch = max(
            branches,
            key=lambda b: len(b.projected_opportunities)
        )
        if max_opp_branch != min_risk_branch:
            recommendations.append({
                "type": "highest_opportunity",
                "branch_id": max_opp_branch.branch_id,
                "scenario_kind": max_opp_branch.scenario_kind,
                "reason": "Highest opportunity count",
            })
        
        # Best health projection
        # (Would need actual projected health computation)
        
        return recommendations
    
    def _generate_branch_recommendation(
        self,
        baseline_result: Dict[str, Any],
        branch: TwinScenarioBranch,
    ) -> Dict[str, Any]:
        """Generate recommendation for single branch vs baseline."""
        risk_count = len(branch.projected_risks)
        critical_risks = len([r for r in branch.projected_risks if r.get("severity") in ("critical", "high")])
        opp_count = len(branch.projected_opportunities)
        
        if critical_risks == 0 and opp_count > 0:
            return {
                "type": "favorable",
                "reason": f"No critical/high risks identified, {opp_count} opportunities",
                "action": "Consider proceeding with governance approval",
            }
        elif critical_risks > 0 and opp_count == 0:
            return {
                "type": "caution",
                "reason": f"{critical_risks} critical/high risks, no offsetting opportunities",
                "action": "Requires mitigation before proceeding",
            }
        else:
            return {
                "type": "mixed",
                "reason": f"{critical_risks} critical/high risks, {opp_count} opportunities",
                "action": "Weigh risks against opportunities with governance",
            }
    
    # ================================================================
    # SURFACE / OUTPUT
    # ================================================================
    
    def _twin_state_to_surface(self, twin: TwinState) -> Dict[str, Any]:
        """Convert twin state to surface format."""
        return {
            "advisory_only": True,
            "not_a_prediction": True,
            "not_a_decision": True,
            "not_an_authorization": True,
            "not_execution": True,
            "twin_id": f"twin-{twin.organization_id}-{twin.scope_type}-{twin.scope_id or 'org'}",
            "organization_id": twin.organization_id,
            "scope_type": twin.scope_type,
            "scope_id": twin.scope_id,
            "captured_at": twin.captured_at.isoformat(),
            "state_key": twin.state_key,
            "snapshot_ref": twin.snapshot_ref,
            "dimensions": {
                "strategy": twin.strategy,
                "execution": twin.execution,
                "coordination": twin.coordination,
                "capacity": twin.capacity,
                "people": twin.people,
                "customers": twin.customers,
                "financial": twin.financial,
                "knowledge": twin.knowledge,
            },
            "attention": twin.attention,
            "health": {
                "score": twin.health_score,
                "state": twin.health_state,
            } if twin.health_score is not None else None,
            "predictions": twin.predictions,
            "counterfactual_scenarios": twin.counterfactual_scenarios,
            "institutional_basis": twin.institutional_basis,
            "provenance": twin.provenance,
            "epistemic_notice": (
                "This twin state is a derived projection over canonical reality. "
                "It represents the company's state at a point in time. "
                "It is NOT a prediction, decision, authorization, or execution. "
                "Actual company state only changes through governed canonical mutation."
            ),
            "derived_at": twin.captured_at.isoformat(),
        }
    
    def _branch_to_surface(
        self,
        branch: TwinScenarioBranch,
        baseline_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Convert scenario branch to surface format."""
        return {
            "advisory_only": True,
            "not_a_prediction": True,
            "not_a_decision": True,
            "not_an_authorization": True,
            "not_execution": True,
            "branch_id": branch.branch_id,
            "baseline_state_key": branch.baseline_state_key,
            "scenario": {
                "kind": branch.scenario_kind,
                "subject_type": branch.subject_type,
                "subject_id": branch.subject_id,
                "params": branch.params,
                "assumptions": branch.assumptions,
            },
            "projected_consequences": branch.projected_state,
            "projected_predictions": branch.projected_predictions,
            "projected_risks": branch.projected_risks,
            "projected_opportunities": branch.projected_opportunities,
            "recommendation": branch.recommendation,
            "comparison": branch.comparison,
            "created_at": branch.created_at.isoformat(),
            "epistemic_notice": (
                "This scenario branch is an isolated counterfactual projection. "
                "It does not mutate canonical reality. "
                "Any actual change requires: recommendation -> decision -> authorization -> canonical mutation."
            ),
        }
    
    def _comparison_to_surface(
        self,
        comparison: TwinComparison,
        baseline_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Convert twin comparison to surface format."""
        # Rebuild branch data from comparison_matrix
        branch_data = comparison.comparison_matrix.get("branches", [])
        
        return {
            "advisory_only": True,
            "not_a_prediction": True,
            "not_a_decision": True,
            "not_an_authorization": True,
            "not_execution": True,
            "comparison_id": comparison.comparison_id,
            "baseline_state_key": comparison.baseline_state_key,
            "baseline_health": {
                "score": baseline_result.get("health_score"),
                "state": baseline_result.get("health_state"),
            },
            "branches": [
                {
                    "branch_id": b.branch_id,
                    "scenario": {
                        "kind": b.scenario_kind,
                        "subject_type": b.subject_type,
                        "subject_id": b.subject_id,
                        "params": b.params,
                    },
                    "projected_health": branch_data[i].get("projected_health", {})
                        if i < len(branch_data) else {},
                    "risk_count": len(b.projected_risks),
                    "critical_risks": len([r for r in b.projected_risks if r.get("severity") in ("critical", "high")]),
                    "opportunity_count": len(b.projected_opportunities),
                }
                for i, b in enumerate(comparison.branches)
            ],
            "comparison_matrix": comparison.comparison_matrix,
            "recommendations": comparison.recommendations,
            "derived_at": comparison.derived_at.isoformat(),
            "epistemic_notice": (
                "This comparison evaluates isolated counterfactual projections. "
                "No canonical reality is mutated. "
                "Recommendations are advisory — human decision required for any action."
            ),
        }
    
    def _scenario_run_to_surface(self, row: CompanyScenarioRun) -> Dict[str, Any]:
        """Convert CompanyScenarioRun to surface format."""
        honesty = dict(row.honesty_json or {})
        surf = dict(row.consequences_json or {})
        
        return {
            "scenario_id": row.id,
            "organization_id": row.organization_id,
            "scope_type": row.scope_type,
            "scope_id": row.scope_id,
            "advisory_only": True,
            "not_a_prediction": True,
            "baseline": {
                "snapshot_ref": row.snapshot_ref,
                "state_key": row.state_key,
                "occurred_at": row.occurred_at.isoformat(),
                "scope_type": row.scope_type,
                "scope_id": row.scope_id,
                "as_of": (row.input_json or {}).get("as_of"),
            },
            "hypothetical_change": {
                "scenario_kind": row.scenario_kind,
                "subject_type": (row.input_json or {}).get("subject_type"),
                "subject_id": (row.input_json or {}).get("subject_id"),
                "params": (row.input_json or {}).get("params", {}),
                "assumptions": row.assumptions_json or [],
                "organization_scope": {
                    "scope_type": row.scope_type,
                    "scope_id": row.scope_id,
                },
                "as_of": (row.input_json or {}).get("as_of"),
            },
            "direct_effects": surf.get("direct_effects", []),
            "dependent_effects": surf.get("dependent_effects", []),
            "risks_already_present": surf.get("risks_already_present", []),
            "opportunities_already_present": surf.get("opportunities_already_present", []),
            "decisions_to_reconsider": row.decision_suggestions_json or [],
            "causal_basis": {
                "hops": row.propagation_json or [],
                "hop_count": len(row.propagation_json or []),
                "edge_ids": sorted(
                    str(h.get("edge_id") or "") for h in (row.propagation_json or []) if h.get("edge_id")
                ),
                "bounded": len(row.propagation_json or []) >= 50,
            },
            "propagation": row.propagation_json or [],
            "consequences": {
                "direct_effects": surf.get("direct_effects", []),
                "dependent_effects": surf.get("dependent_effects", []),
                "risks_already_present": surf.get("risks_already_present", []),
                "opportunities_already_present": surf.get("opportunities_already_present", []),
            },
            "snapshot_ref": row.snapshot_ref,
            "honesty": honesty,
            "human_decision": (
                "A human decides what to do next — VCOS presents consequences "
                "and evidence, it never selects among options."
            ),
            "note": "recorded rehearsal — replayed from the append-only history",
            "occurred_at": row.occurred_at.isoformat(),
            "generated_at": utcnow().isoformat(),
        }


    async def capture_twin_snapshot(
        self,
        db: AsyncSession,
        organization_id: str,
        twin_scope: str = "org",
        scope_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Capture a twin snapshot for the given organization.
        
        This is a convenience wrapper around derive_twin_state that creates
        a system-level caller for the organization.
        
        Args:
            db: Database session
            organization_id: Organization ID
            twin_scope: Scope type (org, department, team, project, person)
            scope_id: Optional scope identifier
            
        Returns:
            Twin state projection with provenance
        """
        from app.intelligence.company_context import CallerAccess
        
        # Create a system caller for the organization
        caller = CallerAccess(
            organization_id=organization_id,
            user_id="system",
            employee_id="system",
            org_wide=True,
        )
        
        return await self.derive_twin_state(
            db=db,
            caller=caller,
            scope_type=twin_scope,
            scope_id=scope_id,
        )

# Global instance
canonical_digital_twin_service = CanonicalDigitalTwinService()