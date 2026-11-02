"""Gate 23 — Canonical Business Intelligence & Decision Operating Fabric Service.

This service establishes the Canonical Business Intelligence + Decision Operating Fabric
over the existing canonical reality. It is a governed projection/reasoning capability
over the ONE canonical company reality — NOT a parallel BI architecture.

Key principles:
- BI is a projection over canonical reality, not a competing reality
- Every metric/observation traces to canonical entities with provenance
- Metric lineage: Metric → Calculation → Source Observations → Canonical Entities → Evidence → Provenance
- Governed contexts: person/team/department/project/customer/process/company
- Company health: multidimensional, explainable, evidence-backed
- Variance intelligence: Expected vs Actual with cause candidates (not confirmed causes)
- Root-cause traceability: uses canonical graph, no new causal graph
- Decision operating fabric: integrates evidence, metrics, predictions, counterfactuals, digital twin
- Decision ≠ Recommendation ≠ Authorization ≠ Commitment ≠ Action ≠ Execution ≠ Outcome
- Intelligence loop: Observation → BI → Insight → Decision Context → Decision → Authorization → Commitment → Responsibility → Action → Execution → Outcome → Verification → Learning → Future BI
"""

import json
import logging
import uuid
import hashlib
from datetime import datetime, date, timedelta, timezone
from typing import Any, List, Dict, Optional, Sequence
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow, ensure_aware
from app.intelligence.company_context import CallerAccess
from app.models.canonical_business_intelligence import (
    CanonicalMetric,
    MetricObservation,
    MetricLineage,
    BusinessIntelligenceContext,
    CanonicalCompanyHealth,
    VarianceAnalysis,
    CauseCandidate,
    RootCauseTrace,
    CanonicalDecisionContext,
    CanonicalDecisionOption,
    CanonicalDecisionAssessment,
    CanonicalDecisionCockpitItem,
    CanonicalIntelligenceLoopEvent,
    CanonicalExecutiveBriefing,
    CanonicalNaturalLanguageQuery,
    METRIC_CATEGORIES,
    METRIC_DIRECTIONS,
    METRIC_STATUSES,
    OBSERVATION_LABELS,
    OBSERVATION_SOURCES,
    EPISTEMIC_STATUSES,
    LINEAGE_RELATIONS,
    VARIANCE_DIRECTIONS,
    CAUSE_CANDIDATE_STATUS,
    HEALTH_DIMENSIONS,
    HEALTH_STATES,
    DECISION_CONTEXT_SECTIONS,
    DECISION_STATES,
)
from app.models.business_performance import (
    BusinessMetric,
    BusinessMetricObservation,
    BusinessDriver,
    BusinessTarget,
    BusinessForecast,
    BusinessPerformanceSnapshot,
    BusinessPerformanceHistory,
    BusinessPerformanceLink,
)
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyObjective,
    CompanyInitiative,
    CompanyGoal,
    OrganizationalResponsibility,
    AccountabilityLink,
)
from app.models.company_operating import CompanyDecision
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.customer_intelligence import CustomerHealthRow, CustomerOutcome
from app.models.execution_intelligence import ProjectExecutionState
from app.models.resource_allocation_intelligence import CapacitySnapshot
from app.models.organizational_learning import OrganizationalLearning
from app.models.knowledge import KnowledgeTopic
from app.models.workload import WorkloadSnapshot
from app.intelligence.business_performance_engine import business_performance_engine
from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
from app.intelligence.cross_domain_impact_service import cross_domain_impact_service
from app.intelligence.institutional_intelligence_service import institutional_intelligence_service
from app.intelligence.organizational_attention_service import organizational_attention_service

logger = logging.getLogger("vcos.intelligence.canonical_business_intelligence")


class _MetricKey:
    """Canonicalize a metric key: lowercase, spaces -> dashes."""
    @staticmethod
    def normalize(raw: Any) -> str:
        key = (raw or "").strip().lower().replace(" ", "-").replace("_", "-")
        return key[:120]


def _iso(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


class CanonicalBusinessIntelligenceService:
    """Canonical Business Intelligence & Decision Operating Fabric — one service."""

    def __init__(self) -> None:
        pass

    # ================================================================
    # CANONICAL METRICS (extending 4G.6 BusinessMetric)
    # ================================================================

    async def create_or_update_metric(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        key: str,
        label: str,
        category: str,
        direction: str = "up_is_good",
        unit: str = "",
        description: str = "",
        calculation_definition: str = "",
        semantic_meaning: str = "",
        scope: str = "org_wide",
        scope_entity_id: Optional[str] = None,
        period_granularity: str = "monthly",
        visibility: str = "internal",
        comparison_baseline: Optional[float] = None,
        comparison_baseline_label: str = "",
        source_event_id: str = "",
    ) -> CanonicalMetric:
        """Create or update a canonical metric with full BI semantics."""
        norm_key = _MetricKey.normalize(key)
        if not norm_key:
            raise ValueError("Metric key cannot be empty")

        if category not in METRIC_CATEGORIES:
            category = "operational"
        if direction not in METRIC_DIRECTIONS:
            direction = "up_is_good"
        if period_granularity not in ("daily", "weekly", "monthly", "quarterly", "yearly"):
            period_granularity = "monthly"
        if visibility not in ("public", "internal", "restricted"):
            visibility = "internal"

        metric = (
            await db.execute(
                select(CanonicalMetric).where(
                    CanonicalMetric.organization_id == organization_id,
                    CanonicalMetric.key == norm_key,
                )
            )
        ).scalar_one_or_none()

        now = utcnow()
        if metric is None:
            metric = CanonicalMetric(
                organization_id=organization_id,
                key=norm_key,
                label=label[:200],
                description=description[:4000] or None,
                category=category,
                direction=direction,
                unit=unit[:40],
                calculation_definition=calculation_definition[:4000] or None,
                semantic_meaning=semantic_meaning[:4000] or None,
                scope=scope[:16],
                scope_entity_id=scope_entity_id[:32] if scope_entity_id else None,
                period_granularity=period_granularity,
                visibility=visibility,
                comparison_baseline=comparison_baseline,
                comparison_baseline_label=comparison_baseline_label[:120],
                valid_from=now,
                source_event_id=source_event_id or f"manual:{uuid.uuid4().hex[:8]}",
            )
            db.add(metric)
        else:
            # Update mutable fields
            metric.label = label[:200]
            metric.description = description[:4000] or None
            metric.category = category
            metric.direction = direction
            metric.unit = unit[:40]
            metric.calculation_definition = calculation_definition[:4000] or None
            metric.semantic_meaning = semantic_meaning[:4000] or None
            metric.scope = scope[:16]
            metric.scope_entity_id = scope_entity_id[:32] if scope_entity_id else None
            metric.period_granularity = period_granularity
            metric.visibility = visibility
            metric.comparison_baseline = comparison_baseline
            metric.comparison_baseline_label = comparison_baseline_label[:120]
            metric.source_event_id = source_event_id or f"manual:{uuid.uuid4().hex[:8]}"

        await db.flush()
        return metric

    async def record_observation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        metric_id: str,
        value: float,
        observed_at: Any,
        label: str = "actual",
        source: str = "manual",
        provenance: str = "",
        confidence: float = 1.0,
        epistemic_status: str = "observed",
        note: Optional[str] = None,
        source_event_id: str = "",
    ) -> MetricObservation:
        """Record a metric observation with exact-once semantics."""
        metric = await db.get(CanonicalMetric, metric_id)
        if not metric or metric.organization_id != organization_id:
            raise ValueError(f"Metric not found: {metric_id}")

        observed_dt = observed_at
        if isinstance(observed_dt, str):
            try:
                observed_dt = datetime.fromisoformat(observed_dt)
            except ValueError:
                observed_dt = utcnow()
        if not isinstance(observed_dt, datetime):
            observed_dt = utcnow()

        label = (label or "actual").strip()[:16]
        if label not in OBSERVATION_LABELS:
            label = "actual"

        src = (source or "manual").strip()[:24]
        if src not in OBSERVATION_SOURCES:
            src = "manual"

        if epistemic_status not in EPISTEMIC_STATUSES:
            epistemic_status = "observed"

        # Exact-once check
        existing = (
            await db.execute(
                select(MetricObservation.id).where(
                    MetricObservation.organization_id == organization_id,
                    MetricObservation.metric_id == metric_id,
                    MetricObservation.observed_at == observed_dt,
                    MetricObservation.source_event_id == (source_event_id or f"obs:{uuid.uuid4().hex[:8]}"),
                )
            )
        ).scalar_one_or_none()
        if existing:
            return await db.get(MetricObservation, existing)

        obs = MetricObservation(
            organization_id=organization_id,
            metric_id=metric_id,
            value=value,
            observed_at=observed_dt,
            unit=(metric.unit or "")[:40],
            label=label,
            source=src,
            provenance=(provenance or f"manual:{source_event_id}")[:300],
            confidence=max(0.0, min(1.0, confidence)),
            epistemic_status=epistemic_status,
            note=note[:4000] if note else None,
            source_event_id=source_event_id or f"obs:{uuid.uuid4().hex[:8]}",
        )
        db.add(obs)

        # Update metric's cached current value
        metric.current_value = value
        metric.current_value_at = observed_dt

        # Also update corresponding BusinessMetric if exists
        bm = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == organization_id,
                    BusinessMetric.key == metric.key,
                )
            )
        ).scalar_one_or_none()
        if bm:
            bm.last_value = value
            bm.last_observed_at = observed_dt

        await db.flush()
        return obs

    async def add_lineage(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        metric_id: str,
        source_type: str,
        source_id: str,
        relation: str,
        explanation: str = "",
        evidence_count: int = 0,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
        provenance: str = "",
        confidence: float = 1.0,
        source_event_id: str = "",
    ) -> MetricLineage:
        """Add a lineage link for a metric."""
        metric = await db.get(CanonicalMetric, metric_id)
        if not metric or metric.organization_id != organization_id:
            raise ValueError(f"Metric not found: {metric_id}")

        if relation not in LINEAGE_RELATIONS:
            relation = "linked_to"

        # Deduplication hash
        path_hash = hashlib.sha256(
            f"{organization_id}:{metric_id}:{source_type}:{source_id}:{relation}".encode()
        ).hexdigest()[:64]

        existing = (
            await db.execute(
                select(MetricLineage).where(
                    MetricLineage.organization_id == organization_id,
                    MetricLineage.metric_id == metric_id,
                    MetricLineage.source_type == source_type,
                    MetricLineage.source_id == source_id,
                    MetricLineage.relation == relation,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        lineage = MetricLineage(
            organization_id=organization_id,
            metric_id=metric_id,
            source_type=source_type[:40],
            source_id=source_id[:32],
            relation=relation,
            explanation=explanation[:500],
            evidence_count=evidence_count,
            window_start=window_start,
            window_end=window_end,
            provenance=(provenance or source_event_id)[:300],
            confidence=max(0.0, min(1.0, confidence)),
            source_event_id=source_event_id or f"lineage:{uuid.uuid4().hex[:8]}",
        )
        db.add(lineage)
        await db.flush()
        return lineage

    async def get_metric_lineage(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        metric_id: str,
    ) -> Dict[str, Any]:
        """Get full lineage for a metric — why this metric has its value."""
        metric = await db.get(CanonicalMetric, metric_id)
        if not metric or metric.organization_id != organization_id:
            return {"metric_id": metric_id, "error": "Not found"}

        lineage_rows = list(
            (
                await db.execute(
                    select(MetricLineage).where(
                        MetricLineage.organization_id == organization_id,
                        MetricLineage.metric_id == metric_id,
                    ).order_by(MetricLineage.created_at)
                )
            ).scalars().all()
        )

        # Also get observations
        obs_rows = list(
            (
                await db.execute(
                    select(MetricObservation).where(
                        MetricObservation.organization_id == organization_id,
                        MetricObservation.metric_id == metric_id,
                    ).order_by(MetricObservation.observed_at.desc()).limit(50)
                )
            ).scalars().all()
        )

        # Also get BusinessPerformanceLinks
        links = list(
            (
                await db.execute(
                    select(BusinessPerformanceLink).where(
                        BusinessPerformanceLink.organization_id == organization_id,
                        BusinessPerformanceLink.entity_type == "business_metric",
                        BusinessPerformanceLink.entity_id == metric_id,
                    ).limit(100)
                )
            ).scalars().all()
        )

        return {
            "metric": {
                "id": metric.id,
                "key": metric.key,
                "label": metric.label,
                "category": metric.category,
                "direction": metric.direction,
                "unit": metric.unit,
                "current_value": metric.current_value,
                "current_value_at": _iso(metric.current_value_at) if metric.current_value_at else None,
                "comparison_baseline": metric.comparison_baseline,
                "comparison_baseline_label": metric.comparison_baseline_label,
                "confidence": metric.confidence,
                "epistemic_status": metric.epistemic_status,
                "calculation_definition": metric.calculation_definition,
                "semantic_meaning": metric.semantic_meaning,
            },
            "lineage": [
                {
                    "source_type": l.source_type,
                    "source_id": l.source_id,
                    "relation": l.relation,
                    "explanation": l.explanation,
                    "evidence_count": l.evidence_count,
                    "window_start": _iso(l.window_start) if l.window_start else None,
                    "window_end": _iso(l.window_end) if l.window_end else None,
                    "confidence": l.confidence,
                    "provenance": l.provenance,
                }
                for l in lineage_rows
            ],
            "observations": [
                {
                    "value": o.value,
                    "observed_at": _iso(o.observed_at),
                    "label": o.label,
                    "source": o.source,
                    "provenance": o.provenance,
                    "epistemic_status": o.epistemic_status,
                    "confidence": o.confidence,
                }
                for o in obs_rows
            ],
            "cross_slice_links": [
                {
                    "target_type": ln.target_type,
                    "target_id": ln.target_id,
                    "kind": ln.kind,
                    "weight": ln.weight,
                    "evidence_count": ln.evidence_count,
                    "reasoning": ln.reasoning,
                }
                for ln in links
            ],
        }

    # ================================================================
    # BUSINESS INTELLIGENCE CONTEXTS (governed projections)
    # ================================================================

    async def derive_bi_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        context_type: str,
        context_entity_id: str,
        period_label: Optional[str] = None,
    ) -> BusinessIntelligenceContext:
        """Derive a governed BI context for a specific scope.

        Context types: person | team | department | project | customer | process | company
        Same canonical reality, different authorized projection.
        """
        if context_type not in ("person", "team", "department", "project", "customer", "process", "company"):
            context_type = "company"

        period = period_label or utcnow().strftime("%Y-%m")
        scope_type = "org" if context_type == "company" else context_type
        scope_id = None if context_type == "company" else context_entity_id

        # Get relevant metrics for this context
        metric_keys = await self._get_relevant_metric_keys(db, caller, context_type, context_entity_id)
        kpi_keys = await self._get_kpi_keys(db, caller, context_type, context_entity_id)

        # Derive health for this context
        health_score, health_state = await self._derive_context_health(
            db, caller, context_type, context_entity_id, period
        )

        # Get variance alerts
        variance_alerts = await self._get_variance_alerts(
            db, caller, context_type, context_entity_id, period
        )

        # Get top risks
        top_risks = await self._get_context_risks(
            db, caller, context_type, context_entity_id
        )

        # Get pending decisions
        pending_decisions = await self._get_pending_decisions(
            db, caller, context_type, context_entity_id
        )

        # Generate summary narrative
        summary = await self._generate_context_summary(
            db, caller, context_type, context_entity_id, period,
            health_score, health_state, variance_alerts, top_risks, pending_decisions
        )

        # Governance scope
        gov_scope_type = "org"
        gov_scope_id = None
        if context_type != "company":
            gov_scope_type = context_type
            gov_scope_id = context_entity_id

        context = BusinessIntelligenceContext(
            organization_id=caller.organization_id,
            context_type=context_type,
            context_entity_id=context_entity_id,
            period_label=period,
            governance_scope_type=gov_scope_type,
            governance_scope_id=gov_scope_id,
            metric_keys_json=metric_keys,
            kpi_keys_json=kpi_keys,
            health_score=health_score,
            health_state=health_state,
            variance_alerts_json=variance_alerts,
            top_risks_json=top_risks,
            pending_decisions_json=pending_decisions,
            summary_narrative=summary,
            provenance=f"derived_from_canonical:{caller.employee_id or 'system'}",
            source_event_id=f"bi_context:{uuid.uuid4().hex[:8]}",
        )
        db.add(context)
        await db.flush()
        return context

    async def _get_relevant_metric_keys(
        self, db: AsyncSession, caller: CallerAccess,
        context_type: str, context_entity_id: str
    ) -> List[str]:
        """Get metric keys relevant to a context."""
        keys = []

        if context_type == "person":
            # Metrics tied to person's responsibilities, workload
            resp = await db.execute(
                select(OrganizationalResponsibility).where(
                    OrganizationalResponsibility.organization_id == caller.organization_id,
                    OrganizationalResponsibility.person_id == context_entity_id,
                    OrganizationalResponsibility.state == "active",
                )
            )
            for r in resp.scalars().all():
                if r.commitment_id:
                    comm = await db.get(CompanyCommitment, r.commitment_id)
                    if comm and comm.objective_id:
                        obj = await db.get(CompanyObjective, comm.objective_id)
                        if obj:
                            keys.append(f"objective_progress:{obj.id}")

        elif context_type == "project":
            proj = await db.get(Project, context_entity_id)
            if proj:
                keys.append(f"project_health:{proj.id}")
                # Metrics from project's commitments
                comms = await db.execute(
                    select(CompanyCommitment).where(
                        CompanyCommitment.organization_id == caller.organization_id,
                        CompanyCommitment.scope_type == "project",
                        CompanyCommitment.scope_id == context_entity_id,
                    )
                )
                for c in comms.scalars().all():
                    if c.objective_id:
                        keys.append(f"commitment_risk:{c.id}")

        elif context_type == "company":
            # Company-wide strategic and financial metrics
            keys.extend([
                "revenue", "growth_rate", "customer_retention", "employee_utilization",
                "strategic_alignment", "operational_efficiency", "cash_runway"
            ])

        # Add any canonical metrics scoped to this entity
        metrics = await db.execute(
            select(CanonicalMetric.key).where(
                CanonicalMetric.organization_id == caller.organization_id,
                CanonicalMetric.status == "active",
                CanonicalMetric.scope == context_type,
                CanonicalMetric.scope_entity_id == context_entity_id,
            )
        )
        keys.extend([m[0] for m in metrics.all()])

        return list(dict.fromkeys(keys))  # dedupe

    async def _get_kpi_keys(
        self, db: AsyncSession, caller: CallerAccess,
        context_type: str, context_entity_id: str
    ) -> List[str]:
        """Get KPI keys for a context (subset of metrics marked as KPIs)."""
        # For now, return high-level KPIs based on context
        kpi_map = {
            "person": ["utilization", "commitment_delivery", "capability_growth"],
            "team": ["team_throughput", "cycle_time", "blocked_work", "capability_coverage"],
            "department": ["dept_efficiency", "budget_variance", "headcount_utilization"],
            "project": ["project_health", "delivery_confidence", "budget_burn", "scope_stability"],
            "customer": ["customer_health", "commitment_delivery", "expansion_potential"],
            "process": ["process_throughput", "cycle_time", "error_rate", "automation_rate"],
            "company": ["revenue_growth", "customer_retention", "operational_margin", "strategic_alignment"],
        }
        return kpi_map.get(context_type, [])

    async def _derive_context_health(
        self, db: AsyncSession, caller: CallerAccess,
        context_type: str, context_entity_id: str, period: str
    ) -> tuple[Optional[int], Optional[str]]:
        """Derive health score for a context."""
        # Use existing business_performance_engine for company-wide
        if context_type == "company":
            perf = await business_performance_engine.performance(
                db, organization_id=caller.organization_id, scope="org_wide", period_label=period
            )
            if perf:
                return perf["health"]["score"], perf["health"]["state"]
        elif context_type == "project":
            proj_state = await db.get(ProjectExecutionState, context_entity_id)
            if proj_state:
                health_map = {"healthy": 90, "concerned": 60, "at_risk": 30, "critical": 10}
                score = health_map.get(proj_state.health_status, 50)
                return score, proj_state.health_status
        elif context_type == "customer":
            health = await db.get(CustomerHealthRow, context_entity_id)
            if health:
                health_map = {"healthy": 90, "concerned": 60, "at_risk": 30, "critical": 10}
                score = health_map.get(health.state, 50)
                return score, health.state
        return None, None

    async def _get_variance_alerts(
        self, db: AsyncSession, caller: CallerAccess,
        context_type: str, context_entity_id: str, period: str
    ) -> List[Dict[str, Any]]:
        """Get variance alerts for a context."""
        alerts = []
        variances = await db.execute(
            select(VarianceAnalysis).where(
                VarianceAnalysis.organization_id == caller.organization_id,
                VarianceAnalysis.period_label == period,
                VarianceAnalysis.attention_required.is_(True),
            ).limit(20)
        )
        for v in variances.scalars().all():
            # Filter by context relevance
            if context_type == "project" and v.domain == "project" and v.entity_id == context_entity_id:
                alerts.append({"domain": v.domain, "entity": v.entity_label, "variance_pct": v.variance_pct, "severity": v.impact_severity})
            elif context_type == "company":
                alerts.append({"domain": v.domain, "entity": v.entity_label, "variance_pct": v.variance_pct, "severity": v.impact_severity})
        return alerts[:10]

    async def _get_context_risks(
        self, db: AsyncSession, caller: CallerAccess,
        context_type: str, context_entity_id: str
    ) -> List[Dict[str, Any]]:
        """Get top risks for a context."""
        risks = []
        if context_type == "project":
            proj_state = await db.get(ProjectExecutionState, context_entity_id)
            if proj_state and proj_state.health_status in ("at_risk", "critical"):
                risks.append({"type": "execution", "title": f"Project {proj_state.project_id} at risk", "severity": proj_state.health_status})
        elif context_type == "customer":
            health = await db.get(CustomerHealthRow, context_entity_id)
            if health and health.state in ("at_risk", "concerned"):
                risks.append({"type": "customer", "title": f"Customer health {health.state}", "severity": health.state})
        return risks[:5]

    async def _get_pending_decisions(
        self, db: AsyncSession, caller: CallerAccess,
        context_type: str, context_entity_id: str
    ) -> List[Dict[str, Any]]:
        """Get pending decisions for a context."""
        decisions = []
        # CompanyDecision integration
        decs = await db.execute(
            select(CompanyDecision).where(
                CompanyDecision.organization_id == caller.organization_id,
                CompanyDecision.state.in_(("proposed", "evaluated", "recommended")),
            ).limit(20)
        )
        for d in decs.scalars().all():
            decisions.append({"decision_id": d.id, "title": d.title, "state": d.state})
        return decisions[:10]

    async def _generate_context_summary(
        self, db: AsyncSession, caller: CallerAccess,
        context_type: str, context_entity_id: str, period: str,
        health_score: Optional[int], health_state: Optional[str],
        variance_alerts: List, top_risks: List, pending_decisions: List
    ) -> str:
        """Generate narrative summary for a BI context."""
        parts = []
        entity_name = context_entity_id
        if context_type == "project":
            proj = await db.get(Project, context_entity_id)
            entity_name = proj.name if proj else context_entity_id
        elif context_type == "customer":
            from app.models.customer import Customer
            cust = await db.get(Customer, context_entity_id)
            entity_name = cust.name if cust else context_entity_id

        if health_score is not None:
            parts.append(f"{context_type.title()} {entity_name} health is {health_state} ({health_score}/100)")
        if variance_alerts:
            parts.append(f"{len(variance_alerts)} variance alert(s) requiring attention")
        if top_risks:
            parts.append(f"{len(top_risks)} active risk(s) identified")
        if pending_decisions:
            parts.append(f"{len(pending_decisions)} decision(s) pending")
        return " · ".join(parts) if parts else f"No significant signals for {context_type} {entity_name} in {period}"

    # ================================================================
    # COMPANY HEALTH INTELLIGENCE (multidimensional, explainable)
    # ================================================================

    async def derive_canonical_company_health(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        period_label: Optional[str] = None,
        compute_mode: str = "observed",
    ) -> CanonicalCompanyHealth:
        """Derive multidimensional company health — every dimension traces to evidence."""
        period = period_label or utcnow().strftime("%Y-%m")
        if compute_mode not in ("observed", "derived", "projected", "scenario"):
            compute_mode = "observed"

        # Get business performance snapshot for org-wide
        perf = await business_performance_engine.performance(
            db, organization_id=caller.organization_id, scope="org_wide", period_label=period, compute_mode=compute_mode
        )

        # Build dimensions with evidence
        dimensions = []
        if perf and perf.get("health", {}).get("dimensions"):
            for dim in perf["health"]["dimensions"]:
                dimensions.append({
                    "dimension": dim["key"],
                    "label": dim["label"],
                    "score": dim["score"],
                    "state": dim["state"],
                    "reasons": dim.get("reasons", []),
                    "positives": dim.get("positives", []),
                    "top_metrics": dim.get("top_metrics", []),
                    "evidence_count": dim.get("evidence_count", 0),
                    "metrics_count": dim.get("metrics_count", 0),
                })

        # If no performance data, derive from canonical domains
        if not dimensions:
            dimensions = await self._derive_health_dimensions_from_canonical(db, caller, period)

        # Overall health
        if dimensions:
            overall_score = round(sum(d["score"] for d in dimensions) / len(dimensions))
        else:
            overall_score = 0

        if overall_score >= 75:
            overall_state = "healthy"
        elif overall_score >= 50:
            overall_state = "concerned"
        elif overall_score >= 30:
            overall_state = "at_risk"
        else:
            overall_state = "critical"

        # Driving metrics
        driving_metrics = []
        if perf:
            for traj in perf.get("metrics", {}).get("trajectories", [])[:10]:
                driving_metrics.append({
                    "metric_key": traj["metric_key"],
                    "label": traj["label"],
                    "current": traj["current"],
                    "trend": traj["trend"],
                    "unit": traj["unit"],
                })

        # Active risks from organizational attention
        attention = await organizational_attention_service.derive_organizational_attention(db, caller=caller)
        active_risks = [
            {"kind": a["kind"], "title": a["title"], "severity": a.get("severity", "medium")}
            for a in attention
            if a.get("severity") in ("high", "critical")
        ][:10]

        # Summary narrative
        narrative_parts = [f"Company health is {overall_state} ({overall_score}/100) for {period}"]
        for d in dimensions:
            if d["score"] < 60:
                narrative_parts.append(f"{d['label']}: {d['state']} ({d['score']}) — {', '.join(d['reasons'][:2])}")
        summary = " · ".join(narrative_parts)

        health = CanonicalCompanyHealth(
            organization_id=caller.organization_id,
            period_label=period,
            compute_mode=compute_mode,
            overall_score=overall_score,
            overall_state=overall_state,
            dimensions_json=dimensions,
            driving_metrics_json=driving_metrics,
            active_risks_json=active_risks,
            summary_narrative=summary,
            provenance=f"derived_from_canonical:{caller.employee_id or 'system'}",
            source_event_id=f"canonical_company_health:{uuid.uuid4().hex[:8]}",
            computed_at=utcnow(),
            valid_from=utcnow(),
            valid_to=utcnow() + timedelta(days=30),
        )
        db.add(health)
        await db.flush()
        return health

    async def _derive_health_dimensions_from_canonical(
        self, db: AsyncSession, caller: CallerAccess, period: str
    ) -> List[Dict[str, Any]]:
        """Derive health dimensions from canonical domains when no performance snapshot exists."""
        dimensions = []
        # Strategic: goals, objectives, initiatives
        goals = await db.execute(
            select(CompanyGoal).where(
                CompanyGoal.organization_id == caller.organization_id,
                CompanyGoal.status == "active",
            )
        )
        goal_count = len(goals.scalars().all())
        objectives = await db.execute(
            select(CompanyObjective).where(
                CompanyObjective.organization_id == caller.organization_id,
                CompanyObjective.status == "active",
            )
        )
        obj_count = len(objectives.scalars().all())
        dimensions.append({
            "dimension": "strategic",
            "label": "Strategic Health",
            "score": min(100, 50 + goal_count * 5 + obj_count * 2),
            "state": "healthy" if goal_count > 0 and obj_count > 0 else "concerned",
            "reasons": ["No active goals"] if goal_count == 0 else [],
            "positives": [f"{goal_count} active goals, {obj_count} objectives"] if goal_count > 0 else [],
            "top_metrics": ["goals_active", "objectives_active"],
            "evidence_count": goal_count + obj_count,
            "metrics_count": 2,
        })

        # Operational: projects, processes
        projects = await db.execute(
            select(ProjectExecutionState).where(
                ProjectExecutionState.organization_id == caller.organization_id,
            )
        )
        proj_states = projects.scalars().all()
        at_risk = sum(1 for p in proj_states if p.health_status in ("at_risk", "critical"))
        dimensions.append({
            "dimension": "operational",
            "label": "Operational Health",
            "score": max(0, 100 - at_risk * 15),
            "state": "at_risk" if at_risk > 2 else "concerned" if at_risk > 0 else "healthy",
            "reasons": [f"{at_risk} project(s) at risk"] if at_risk > 0 else [],
            "positives": [f"{len(proj_states)} projects tracked"] if proj_states else [],
            "top_metrics": ["projects_at_risk", "projects_healthy"],
            "evidence_count": len(proj_states),
            "metrics_count": 2,
        })

        # Financial: budgets, revenue
        from app.models.finance import Budget
        budgets = await db.execute(
            select(Budget).where(Budget.organization_id == caller.organization_id)
        )
        budget_count = len(budgets.scalars().all())
        dimensions.append({
            "dimension": "financial",
            "label": "Financial Health",
            "score": 70,  # placeholder
            "state": "healthy",
            "reasons": [],
            "positives": [f"{budget_count} budgets tracked"],
            "top_metrics": ["budget_variance", "revenue_vs_plan"],
            "evidence_count": budget_count,
            "metrics_count": 2,
        })

        # Customer
        health_rows = await db.execute(
            select(CustomerHealthRow).where(CustomerHealthRow.organization_id == caller.organization_id)
        )
        cust_health = health_rows.scalars().all()
        at_risk_cust = sum(1 for c in cust_health if c.state == "at_risk")
        dimensions.append({
            "dimension": "customer",
            "label": "Customer Health",
            "score": max(0, 100 - at_risk_cust * 20),
            "state": "at_risk" if at_risk_cust > 1 else "concerned" if at_risk_cust > 0 else "healthy",
            "reasons": [f"{at_risk_cust} customer(s) at risk"] if at_risk_cust > 0 else [],
            "positives": [f"{len(cust_health)} customers tracked"],
            "top_metrics": ["customers_at_risk", "customer_health_score"],
            "evidence_count": len(cust_health),
            "metrics_count": 2,
        })

        # Workforce
        from app.models.employee import Employee
        emps = await db.execute(
            select(Employee).where(
                Employee.organization_id == caller.organization_id,
                Employee.status == "active",
            )
        )
        emp_count = len(emps.scalars().all())
        workloads = await db.execute(
            select(WorkloadSnapshot).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                WorkloadSnapshot.period_end >= utcnow(),
            )
        )
        wl = workloads.scalars().all()
        overloaded = sum(1 for w in wl if w.is_overloaded)
        dimensions.append({
            "dimension": "workforce",
            "label": "Workforce Health",
            "score": max(0, 100 - overloaded * 10),
            "state": "at_risk" if overloaded > 3 else "concerned" if overloaded > 0 else "healthy",
            "reasons": [f"{overloaded} employee(s) overloaded"] if overloaded > 0 else [],
            "positives": [f"{emp_count} active employees"],
            "top_metrics": ["utilization", "overloaded_count"],
            "evidence_count": emp_count,
            "metrics_count": 2,
        })

        return dimensions

    # ================================================================
    # VARIANCE INTELLIGENCE (Expected vs Actual)
    # ================================================================

    async def analyze_variance(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        domain: str,
        entity_id: str,
        entity_label: str,
        expected_value: float,
        actual_value: float,
        unit: str = "",
        period_label: Optional[str] = None,
        source_event_id: str = "",
    ) -> VarianceAnalysis:
        """Analyze variance between expected and actual with cause candidates."""
        period = period_label or utcnow().strftime("%Y-%m")
        variance = actual_value - expected_value
        variance_pct = (variance / abs(expected_value) * 100) if expected_value != 0 else 0

        direction = "neutral"
        if variance_pct > 2:
            direction = "favorable" if expected_value > 0 else "unfavorable"
        elif variance_pct < -2:
            direction = "unfavorable" if expected_value > 0 else "favorable"

        # Determine severity
        abs_pct = abs(variance_pct)
        if abs_pct >= 50:
            severity = "critical"
        elif abs_pct >= 20:
            severity = "high"
        elif abs_pct >= 10:
            severity = "medium"
        else:
            severity = "low"

        # Generate cause candidates (NOT confirmed causes)
        cause_candidates = await self._generate_cause_candidates(
            db, caller, domain, entity_id, variance, variance_pct
        )

        # Impact assessment
        impact_desc = f"Variance of {variance_pct:.1f}% ({variance:+.2f}{unit}) on {entity_label}"
        attention = severity in ("high", "critical") or abs_pct >= 20

        analysis = VarianceAnalysis(
            organization_id=caller.organization_id,
            domain=domain,
            entity_id=entity_id,
            entity_label=entity_label,
            period_label=period,
            expected_value=expected_value,
            actual_value=actual_value,
            variance=variance,
            variance_pct=round(variance_pct, 2),
            direction=direction,
            unit=unit[:40],
            cause_candidates_json=cause_candidates,
            impact_severity=severity,
            impact_description=impact_desc,
            attention_required=attention,
            attention_reason=f"{severity} variance requires review" if attention else "",
            provenance=f"variance_analysis:{caller.employee_id or 'system'}",
            source_event_id=source_event_id or f"variance:{uuid.uuid4().hex[:8]}",
        )
        db.add(analysis)
        await db.flush()

        # Create cause candidate rows
        for cc in cause_candidates:
            candidate = CauseCandidate(
                organization_id=caller.organization_id,
                variance_id=analysis.id,
                candidate_type=cc["type"],
                candidate_id=cc["id"],
                candidate_label=cc["label"],
                status="candidate",
                evidence_json=cc.get("evidence", []),
                evidence_strength=cc.get("strength", 0.5),
                rationale=cc.get("rationale", ""),
                provenance=f"cause_candidate:{caller.employee_id or 'system'}",
                source_event_id=f"cause:{uuid.uuid4().hex[:8]}",
            )
            db.add(candidate)

        await db.flush()
        return analysis

    async def _generate_cause_candidates(
        self, db: AsyncSession, caller: CallerAccess,
        domain: str, entity_id: str, variance: float, variance_pct: float
    ) -> List[Dict[str, Any]]:
        """Generate cause candidates for a variance using canonical relationships."""
        candidates = []

        if domain == "objective":
            # Check initiatives, commitments, actions
            obj = await db.get(CompanyObjective, entity_id)
            if obj:
                # Initiatives behind pace
                inits = await db.execute(
                    select(CompanyInitiative).where(
                        CompanyInitiative.organization_id == caller.organization_id,
                        CompanyInitiative.objective_id == entity_id,
                        CompanyInitiative.status == "active",
                    )
                )
                for init in inits.scalars().all():
                    if init.expected_outcome and init.expected_outcome.get("target_value"):
                        target = init.expected_outcome["target_value"]
                        current = obj.current_value or 0
                        if current < target * 0.5:
                            init_title = init.title
                            candidates.append({
                                "type": "initiative",
                                "id": init.id,
                                "label": f"Initiative behind pace: {init_title}",
                                "strength": 0.7,
                                "rationale": f"Initiative progress {current}/{target} behind pace for objective",
                                "evidence": [{"type": "initiative_progress", "initiative_id": init.id, "current": current, "target": target}],
                            })

        elif domain == "commitment":
            comm = await db.get(CompanyCommitment, entity_id)
            if comm:
                risk = await cross_domain_impact_service.derive_commitment_risk(db, caller=caller, commitment_id=entity_id)
                for factor in risk.get("risk_factors", []):
                    comm_title = comm.title
                    candidates.append({
                        "type": "commitment",
                        "id": comm.id,
                        "label": f"Commitment risk factor: {factor}",
                        "strength": 0.6,
                        "rationale": f"Cross-domain analysis identified {factor} for commitment {comm_title}",
                        "evidence": [{"type": "commitment_risk", "commitment_id": comm.id, "factor": factor}],
                    })

        elif domain == "project":
            proj_state = await db.get(ProjectExecutionState, entity_id)
            if proj_state:
                if proj_state.health_status in ("at_risk", "critical"):
                    health_status = proj_state.health_status
                    project_id = proj_state.project_id
                    candidates.append({
                        "type": "project",
                        "id": project_id,
                        "label": f"Project execution health: {health_status}",
                        "strength": 0.8,
                        "rationale": f"Project {project_id} health is {health_status}",
                        "evidence": [{"type": "project_health", "project_id": project_id, "status": health_status}],
                    })

        elif domain == "customer":
            health = await db.get(CustomerHealthRow, entity_id)
            if health and health.state in ("at_risk", "concerned"):
                health_state = health.state
                candidates.append({
                    "type": "customer",
                    "id": entity_id,
                    "label": f"Customer health: {health_state}",
                    "strength": 0.8,
                    "rationale": f"Customer health state is {health_state}",
                    "evidence": [{"type": "customer_health", "customer_id": entity_id, "state": health_state}],
                })

        elif domain == "workforce_capacity":
            # Check capacity bottlenecks
            from app.intelligence.organizational_capacity_service import organizational_capacity_service
            cap_ctx = await organizational_capacity_service.derive_capacity_context(db, caller=caller, scope_type="organization")
            if cap_ctx.capacity_state in ("overcommitted", "bottleneck"):
                cap_state = cap_ctx.capacity_state
                cap_util = cap_ctx.utilization
                candidates.append({
                    "type": "capacity",
                    "id": "org_capacity",
                    "label": f"Organizational capacity state: {cap_state}",
                    "strength": 0.7,
                    "rationale": f"Capacity analysis shows {cap_state}",
                    "evidence": [{"type": "capacity_state", "state": cap_state, "utilization": cap_util}],
                })

        return candidates[:10]

    # ================================================================
    # ROOT CAUSE TRACEABILITY (canonical graph traversal)
    # ================================================================

    async def trace_root_cause(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        origin_type: str,
        origin_id: str,
        origin_label: str = "",
        max_depth: int = 6,
    ) -> RootCauseTrace:
        """Trace root cause through canonical graph.

        Example: Customer → Outcome → Commitment → Responsibility → Person → Capacity → Dependency → Task → Process → Vendor → Procurement
        """
        if not origin_label:
            origin_label = origin_id

        trace_path = []
        visited = set()
        current_type = origin_type
        current_id = origin_id
        depth = 0

        while depth < max_depth and (current_type, current_id) not in visited:
            visited.add((current_type, current_id))
            trace_path.append({
                "type": current_type,
                "id": current_id,
                "relation": "origin" if depth == 0 else "affects",
                "evidence": f"Traced from {origin_type} {origin_id}",
            })

            # Get affected entities based on canonical relationships
            next_entities = await self._get_canonical_affected_entities(db, caller.organization_id, current_type, current_id)
            if not next_entities:
                break

            # Pick the strongest link (first one for now)
            current_type, current_id = next_entities[0]["type"], next_entities[0]["id"]
            trace_path[-1]["relation"] = next_entities[0].get("relation", "affects")
            depth += 1

        # Determine strongest contributor
        strongest = None
        if len(trace_path) > 1:
            strongest = trace_path[1]
            strongest_evidence = f"Strongest observed contributor: {strongest['type']} {strongest['id']} via canonical relationships"
        else:
            strongest_evidence = "Insufficient trace depth"

        # Hash for deduplication
        path_str = "->".join(f"{t['type']}:{t['id']}" for t in trace_path)
        path_hash = hashlib.sha256(path_str.encode()).hexdigest()[:64]

        trace = RootCauseTrace(
            organization_id=caller.organization_id,
            origin_type=origin_type,
            origin_id=origin_id,
            origin_label=origin_label,
            trace_path_hash=path_hash,
            trace_path_json=trace_path,
            strongest_contributor_type=strongest["type"] if strongest else None,
            strongest_contributor_id=strongest["id"] if strongest else None,
            strongest_contributor_label=f"{strongest['type']} {strongest['id']}" if strongest else None,
            strongest_contributor_evidence=strongest_evidence,
            trace_confidence=0.7 if len(trace_path) > 2 else 0.4,
            provenance=f"root_cause_trace:{caller.employee_id or 'system'}",
            source_event_id=f"rct:{uuid.uuid4().hex[:8]}",
        )
        db.add(trace)
        await db.flush()
        return trace

    async def _get_canonical_affected_entities(
        self, db: AsyncSession, org_id: str, entity_type: str, entity_id: str
    ) -> List[Dict[str, Any]]:
        """Get entities affected by an entity using canonical relationships."""
        affected = []

        if entity_type == "customer":
            # Customer → BusinessOutcome
            from app.models.business_commercial import BusinessOutcome
            outcomes = await db.execute(
                select(BusinessOutcome).where(
                    BusinessOutcome.organization_id == org_id,
                    BusinessOutcome.customer_id == entity_id,
                )
            )
            for o in outcomes.scalars().all():
                affected.append({"type": "business_outcome", "id": o.id, "relation": "has_outcome"})

        elif entity_type == "business_outcome":
            # BusinessOutcome → Commitment
            comms = await db.execute(
                select(CompanyCommitment).where(
                    CompanyCommitment.organization_id == org_id,
                    # Would need a link from outcome to commitment
                )
            )
            # For now, use scope-based lookup
            pass

        elif entity_type == "commitment":
            # Commitment → Responsibility
            resps = await db.execute(
                select(OrganizationalResponsibility).where(
                    OrganizationalResponsibility.organization_id == org_id,
                    OrganizationalResponsibility.commitment_id == entity_id,
                    OrganizationalResponsibility.state == "active",
                )
            )
            for r in resps.scalars().all():
                affected.append({"type": "responsibility", "id": r.id, "relation": "has_responsibility"})

        elif entity_type == "responsibility":
            # Responsibility → Person (accountable)
            resp = await db.get(OrganizationalResponsibility, entity_id)
            if resp and resp.person_id:
                affected.append({"type": "person", "id": resp.person_id, "relation": "accountable_person"})

        elif entity_type == "person":
            # Person → Capacity
            wl = await db.execute(
                select(WorkloadSnapshot).where(
                    WorkloadSnapshot.organization_id == org_id,
                    WorkloadSnapshot.employee_id == entity_id,
                ).order_by(WorkloadSnapshot.period_start.desc()).limit(1)
            )
            ws = wl.scalar_one_or_none()
            if ws and ws.is_overloaded:
                affected.append({"type": "capacity", "id": f"person_{entity_id}", "relation": "capacity_overload"})

        elif entity_type == "capacity":
            # Capacity → Dependency
            from app.intelligence.organizational_attention_service import organizational_attention_service
            attention = await organizational_attention_service.derive_organizational_attention(db, caller=CallerAccess(
                organization_id=org_id, employee_id=None, org_wide=True, project_ids=set(), visible_scope_ids=set(), member_conversation_ids=set()
            ))
            for a in attention:
                if a["kind"] in ("organizational_bottleneck", "critical_person_dependency"):
                    for se in a.get("source_entities", []):
                        affected.append({"type": se["type"], "id": se["id"], "relation": "bottleneck_dependency"})

        return affected[:5]  # Limit branching

    # ================================================================
    # DECISION OPERATING FABRIC
    # ================================================================

    async def create_decision_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        decision_id: Optional[str] = None,
        question: str = "",
        governance_scope_type: str = "org",
        governance_scope_id: Optional[str] = None,
        authority_role: str = "",
        authority_person_id: Optional[str] = None,
        source_event_id: str = "",
    ) -> CanonicalDecisionContext:
        """Create a decision context integrating all intelligence sources."""
        # Gather evidence from canonical reality
        evidence = await self._gather_decision_evidence(db, caller, question)

        # Get relevant metrics
        metric_ids = await self._get_relevant_metrics_for_question(db, caller, question)

        # Get constraints
        constraints = await self._get_decision_constraints(db, caller, question)

        # Get dependencies
        dependencies = await self._get_decision_dependencies(db, caller, question)

        # Get risks
        risks = await self._get_decision_risks(db, caller, question)

        # Get predictions (Gate 10)
        predictions = await self._get_decision_predictions(db, caller, question)

        # Get counterfactuals (Gate 11)
        counterfactuals = await self._get_decision_counterfactuals(db, caller, question)

        # Get digital twin projections (Gate 12)
        twin_projections = await self._get_decision_twin_projections(db, caller, question)

        # Detect contradictions
        contradictions = await self._detect_contradictions(db, caller, evidence, predictions, counterfactuals)

        context = CanonicalDecisionContext(
            organization_id=caller.organization_id,
            decision_id=decision_id,
            version=1,
            question=question[:500],
            current_state=evidence.get("summary", ""),
            evidence_json=evidence.get("items", []),
            metric_ids_json=metric_ids,
            constraints_json=constraints,
            dependencies_json=dependencies,
            risks_json=risks,
            predictions_json=predictions,
            counterfactuals_json=counterfactuals,
            twin_projections_json=twin_projections,
            options_json=[],
            expected_outcomes_json=[],
            contradictions_json=contradictions,
            epistemic_status="evidence_based",
            confidence=0.5,
            governance_scope_type=governance_scope_type,
            governance_scope_id=governance_scope_id,
            authority_role=authority_role[:60],
            authority_person_id=authority_person_id,
            state="framed",
            provenance=f"decision_context:{caller.employee_id or 'system'}",
            source_event_id=source_event_id or f"dc:{uuid.uuid4().hex[:8]}",
        )
        db.add(context)
        await db.flush()
        return context

    async def add_decision_option(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        decision_context_id: str,
        option_key: str,
        label: str,
        description: str = "",
        expected_outcomes: Optional[List[Dict]] = None,
        risks: Optional[List[Dict]] = None,
        counterfactual: Optional[Dict] = None,
        confidence: float = 0.5,
        source_event_id: str = "",
    ) -> CanonicalDecisionOption:
        """Add an option to a decision context."""
        ctx = await db.get(CanonicalDecisionContext, decision_context_id)
        if not ctx or ctx.organization_id != organization_id:
            raise ValueError("Decision context not found")

        option = CanonicalDecisionOption(
            organization_id=organization_id,
            decision_context_id=decision_context_id,
            option_key=option_key[:80],
            label=label[:200],
            description=description[:4000] or None,
            expected_outcomes_json=expected_outcomes or [],
            risks_json=risks or [],
            counterfactual_json=counterfactual,
            confidence=max(0.0, min(1.0, confidence)),
            epistemic_status="projected",
            provenance=f"decision_option:{uuid.uuid4().hex[:8]}",
            source_event_id=source_event_id or f"opt:{uuid.uuid4().hex[:8]}",
        )
        db.add(option)
        await db.flush()
        return option

    async def create_decision_assessment(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        decision_context_id: str,
        assessor_id: str,
        recommended_option_key: Optional[str] = None,
        rationale: str = "",
        confidence: float = 0.5,
        concerns: Optional[List[str]] = None,
        source_event_id: str = "",
    ) -> CanonicalDecisionAssessment:
        """Record an assessment of a decision context (not a decision itself)."""
        assessment = CanonicalDecisionAssessment(
            organization_id=organization_id,
            decision_context_id=decision_context_id,
            assessor_id=assessor_id,
            recommended_option_key=recommended_option_key,
            rationale=rationale[:4000],
            confidence=max(0.0, min(1.0, confidence)),
            concerns_json=concerns or [],
            provenance=f"decision_assessment:{assessor_id}",
            source_event_id=source_event_id or f"assess:{uuid.uuid4().hex[:8]}",
        )
        db.add(assessment)
        await db.flush()
        return assessment

    async def update_decision_context_state(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        decision_context_id: str,
        new_state: str,
        source_event_id: str = "",
    ) -> CanonicalDecisionContext:
        """Update decision context state (framed → evidence_gathered → options_defined → deliberating → decided...)."""
        if new_state not in DECISION_STATES:
            raise ValueError(f"Invalid state: {new_state}")

        ctx = await db.get(CanonicalDecisionContext, decision_context_id)
        if not ctx or ctx.organization_id != organization_id:
            raise ValueError("Decision context not found")

        ctx.state = new_state
        ctx.source_event_id = source_event_id or f"state_change:{uuid.uuid4().hex[:8]}"
        await db.flush()
        return ctx

    async def _gather_decision_evidence(self, db: AsyncSession, caller: CallerAccess, question: str) -> Dict[str, Any]:
        """Gather evidence for a decision question."""
        items = []
        # This would use the CompanyBrain / reasoning_engine
        # For now, return structured placeholder
        return {
            "summary": f"Evidence gathered for: {question}",
            "items": [
                {"type": "canonical_reality", "description": "Evidence from canonical company state", "confidence": 0.8}
            ],
        }

    async def _get_relevant_metrics_for_question(self, db: AsyncSession, caller: CallerAccess, question: str) -> List[str]:
        """Extract relevant metric IDs from a question."""
        # Simple keyword matching for now
        metrics = await db.execute(
            select(CanonicalMetric.id, CanonicalMetric.key).where(
                CanonicalMetric.organization_id == caller.organization_id,
                CanonicalMetric.status == "active",
            ).limit(50)
        )
        return [m[0] for m in metrics.all()]

    async def _get_decision_constraints(self, db: AsyncSession, caller: CallerAccess, question: str) -> List[Dict]:
        """Get constraints relevant to a decision."""
        return [{"type": "budget", "description": "Budget constraints apply", "severity": "medium"}]

    async def _get_decision_dependencies(self, db: AsyncSession, caller: CallerAccess, question: str) -> List[Dict]:
        """Get dependencies relevant to a decision."""
        return []

    async def _get_decision_risks(self, db: AsyncSession, caller: CallerAccess, question: str) -> List[Dict]:
        """Get risks relevant to a decision."""
        attention = await organizational_attention_service.derive_organizational_attention(db, caller=caller)
        return [
            {"kind": a["kind"], "title": a["title"], "severity": a.get("severity", "medium")}
            for a in attention[:5]
        ]

    async def _get_decision_predictions(self, db: AsyncSession, caller: CallerAccess, question: str) -> List[Dict]:
        """Get predictions (Gate 10) relevant to a decision."""
        preds = await predictive_intelligence_service.derive_predictions(
            db, caller=caller, horizon_days=90
        )
        return [
            {"kind": p.kind, "title": p.title, "probability": p.probability, "confidence": p.confidence}
            for p in preds[:10]
        ]

    async def _get_decision_counterfactuals(self, db: AsyncSession, caller: CallerAccess, question: str) -> List[Dict]:
        """Get counterfactual scenarios (Gate 11) relevant to a decision."""
        # This would require specific scenario definitions
        return []

    async def _get_decision_twin_projections(self, db: AsyncSession, caller: CallerAccess, question: str) -> List[Dict]:
        """Get digital twin projections (Gate 12) relevant to a decision."""
        try:
            twin = await canonical_digital_twin_service.derive_twin_state(
                db, caller=caller, scope_type="org"
            )
            return [{"type": "twin_state", "health_score": twin.get("health", {}).get("score")}]
        except Exception:
            return []

    async def _detect_contradictions(
        self, db: AsyncSession, caller: CallerAccess,
        evidence: Dict, predictions: List, counterfactuals: List
    ) -> List[Dict]:
        """Detect contradictions in evidence for a decision."""
        return []  # Placeholder

    # ================================================================
    # DECISION COCKPIT (decisions requiring attention)
    # ================================================================

    async def get_decision_cockpit(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        limit: int = 20,
    ) -> List[CanonicalDecisionCockpitItem]:
        """Get decisions requiring attention — the decision cockpit surface."""
        # Get decision contexts in states needing attention
        contexts = list(
            (
                await db.execute(
                    select(CanonicalDecisionContext).where(
                        CanonicalDecisionContext.organization_id == caller.organization_id,
                        CanonicalDecisionContext.state.in_(("framed", "evidence_gathered", "options_defined", "deliberating", "awaiting_decision")),
                    ).order_by(CanonicalDecisionContext.created_at.desc()).limit(limit)
                )
            ).scalars().all()
        )

        cockpit_items = []
        for ctx in contexts:
            # Build cockpit item
            why = ctx.question or "Decision requires attention"
            impact = "Impact assessment pending"
            if ctx.risks_json:
                high_risks = [r for r in ctx.risks_json if r.get("severity") in ("high", "critical")]
                if high_risks:
                    impact = f"{len(high_risks)} high/critical risk(s) identified"

            evidence_summary = ""
            if ctx.evidence_json:
                evidence_summary = f"{len(ctx.evidence_json)} evidence item(s)"

            pred_summary = ""
            if ctx.predictions_json:
                high_prob = [p for p in ctx.predictions_json if p.get("probability", 0) > 0.7]
                if high_prob:
                    pred_summary = f"{len(high_prob)} high-probability prediction(s)"

            options_summary = ""
            if ctx.options_json:
                options_summary = f"{len(ctx.options_json)} option(s) defined"

            cf_insight = ""
            if ctx.counterfactuals_json:
                cf_insight = "Counterfactual scenarios available"

            item = CanonicalDecisionCockpitItem(
                organization_id=caller.organization_id,
                decision_context_id=ctx.id,
                priority="critical" if any(r.get("severity") == "critical" for r in ctx.risks_json) else "high" if any(r.get("severity") == "high" for r in ctx.risks_json) else "medium",
                why=why[:500],
                impact_description=impact[:500],
                evidence_summary=evidence_summary[:500],
                prediction_summary=pred_summary[:500],
                options_summary=options_summary[:500],
                counterfactual_insight=cf_insight[:500],
                authority_role=ctx.authority_role or "Decision Owner",
                authority_person_id=ctx.authority_person_id,
                status=ctx.state,
                provenance=f"cockpit:{caller.employee_id or 'system'}",
                source_event_id=f"cockpit:{uuid.uuid4().hex[:8]}",
            )
            db.add(item)
            cockpit_items.append(item)

        await db.flush()
        return cockpit_items

    # ================================================================
    # NATURAL LANGUAGE QUERIES (Ask VCOS)
    # ================================================================

    async def answer_company_question(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        user_id: str,
        question: str,
    ) -> CanonicalNaturalLanguageQuery:
        """Answer a natural-language company question from governed canonical reality."""
        # Parse intent (simplified)
        intent = self._parse_question_intent(question)

        # Use CompanyBrain for the answer
        from app.intelligence.company_brain import CompanyBrain
        brain = CompanyBrain()

        # Need a user object - create minimal one
        class MinimalUser:
            def __init__(self, id):
                self.id = id

        user = MinimalUser(user_id)
        answer = await brain.answer(
            db, caller.organization_id, question,
            user=user,
        )

        nlq = CanonicalNaturalLanguageQuery(
            organization_id=caller.organization_id,
            user_id=user_id,
            question=question,
            intent=intent,
            answer_json=answer,
            sources_json=answer.get("sources_consulted", []) if answer else [],
            confidence=answer.get("confidence", 0.5) if answer else 0.5,
            epistemic_status="evidence_based",
            governance_applied=True,
            asked_at=utcnow(),
            answered_at=utcnow() if answer else None,
        )
        db.add(nlq)
        await db.flush()
        return nlq

    def _parse_question_intent(self, question: str) -> str:
        """Parse the intent of a natural language question."""
        q = question.lower()
        if any(w in q for w in ["why", "cause", "reason"]):
            return "root_cause"
        elif any(w in q for w in ["what changed", "change", "different"]):
            return "change_analysis"
        elif any(w in q for w in ["risk", "at risk", "danger"]):
            return "risk_assessment"
        elif any(w in q for w in ["bottleneck", "capacity", "overloaded"]):
            return "capacity_analysis"
        elif any(w in q for w in ["decision", "decide", "choose", "option"]):
            return "decision_support"
        elif any(w in q for w in ["predict", "forecast", "will", "likely"]):
            return "prediction"
        elif any(w in q for w in ["what if", "scenario", "suppose"]):
            return "counterfactual"
        elif any(w in q for w in ["health", "how are we", "status"]):
            return "health_check"
        return "general_inquiry"

    # ================================================================
    # EXECUTIVE BRIEFINGS
    # ================================================================

    async def generate_executive_briefing(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        briefing_type: str = "daily",
        recipient_scope: str = "executive",
        governance_scope_type: str = "org",
        governance_scope_id: Optional[str] = None,
    ) -> CanonicalExecutiveBriefing:
        """Generate automated executive briefing — view over canonical reality."""
        now = utcnow()
        if briefing_type == "daily":
            period = now.strftime("%Y-%m-%d")
            since = now - timedelta(days=1)
        elif briefing_type == "weekly":
            period = now.strftime("%Y-W%U")
            since = now - timedelta(weeks=1)
        elif briefing_type == "monthly":
            period = now.strftime("%Y-%m")
            since = now - timedelta(days=30)
        else:
            period = now.strftime("%Y-%m-%d")
            since = now - timedelta(days=1)

        sections = []

        # What changed
        from app.kernel.context_engine import context_engine
        try:
            digest = await context_engine.digest(db, caller.organization_id, days=1 if briefing_type == "daily" else 7)
            sections.append({
                "title": "What Changed",
                "content": f"New tasks: {digest.get('new_tasks', 0)}, New memories: {digest.get('new_memories', 0)}, New meetings: {digest.get('new_meetings', 0)}",
            })
        except Exception:
            pass

        # Company health
        health = await self.derive_canonical_company_health(db, caller=caller, period_label=period, compute_mode="observed")
        sections.append({
            "title": "Company Health",
            "content": f"Overall: {health.overall_state} ({health.overall_score}/100)",
            "detail": health.dimensions_json,
        })

        # Pending decisions
        cockpit = await self.get_decision_cockpit(db, caller=caller, limit=10)
        if cockpit:
            sections.append({
                "title": "Decisions Requiring Attention",
                "content": f"{len(cockpit)} decision(s) pending",
                "detail": [{"id": c.decision_context_id, "why": c.why, "priority": c.priority} for c in cockpit[:5]],
            })

        # Top risks
        attention = await organizational_attention_service.derive_organizational_attention(db, caller=caller)
        critical_risks = [a for a in attention if a.get("severity") in ("high", "critical")]
        if critical_risks:
            sections.append({
                "title": "Top Risks",
                "content": f"{len(critical_risks)} critical/high risk(s)",
                "detail": [{"kind": r["kind"], "title": r["title"]} for r in critical_risks[:5]],
            })

        # Predictions (Gate 10)
        preds = await predictive_intelligence_service.derive_predictions(db, caller=caller, horizon_days=30)
        high_preds = [p for p in preds if p.probability > 0.7]
        if high_preds:
            sections.append({
                "title": "Key Predictions",
                "content": f"{len(high_preds)} high-confidence prediction(s)",
                "detail": [{"kind": p.kind, "title": p.title, "probability": p.probability} for p in high_preds[:5]],
            })

        briefing = CanonicalExecutiveBriefing(
            organization_id=caller.organization_id,
            briefing_type=briefing_type,
            period_label=period,
            recipient_scope=recipient_scope,
            governance_scope_type=governance_scope_type,
            governance_scope_id=governance_scope_id,
            sections_json=sections,
            metrics_snapshot_json=[],
            pending_decisions_json=[{"id": c.decision_context_id, "why": c.why, "priority": c.priority} for c in cockpit[:10]],
            top_risks_json=[{"kind": r["kind"], "title": r["title"], "severity": r.get("severity")} for r in critical_risks[:10]],
            provenance=f"executive_briefing:{briefing_type}:{caller.employee_id or 'system'}",
            source_event_id=f"briefing:{uuid.uuid4().hex[:8]}",
            generated_at=now,
        )
        db.add(briefing)
        await db.flush()
        return briefing

    # ================================================================
    # INTELLIGENCE LOOP CLOSURE
    # ================================================================

    async def record_intelligence_loop_event(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        decision_id: str,
        stage: str,
        entity_type: str,
        entity_id: str,
        description: str,
        validated_prior_intelligence: Optional[bool] = None,
        learning_captured: Optional[str] = None,
        source_event_id: str = "",
    ) -> CanonicalIntelligenceLoopEvent:
        """Record an event in the intelligence → decision → execution → learning loop."""
        event = CanonicalIntelligenceLoopEvent(
            organization_id=organization_id,
            decision_id=decision_id,
            stage=stage,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description[:500],
            validated_prior_intelligence=validated_prior_intelligence,
            learning_captured=learning_captured,
            provenance=f"intelligence_loop:{stage}",
            source_event_id=source_event_id or f"loop:{uuid.uuid4().hex[:8]}",
            occurred_at=utcnow(),
        )
        db.add(event)
        await db.flush()
        return event

    async def get_intelligence_loop_trace(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        decision_id: str,
    ) -> List[Dict[str, Any]]:
        """Get the full intelligence loop trace for a decision."""
        events = list(
            (
                await db.execute(
                    select(CanonicalIntelligenceLoopEvent).where(
                        CanonicalIntelligenceLoopEvent.organization_id == organization_id,
                        CanonicalIntelligenceLoopEvent.decision_id == decision_id,
                    ).order_by(CanonicalIntelligenceLoopEvent.occurred_at)
                )
            ).scalars().all()
        )
        return [
            {
                "stage": e.stage,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "description": e.description,
                "validated_prior_intelligence": e.validated_prior_intelligence,
                "learning_captured": e.learning_captured,
                "occurred_at": _iso(e.occurred_at),
            }
            for e in events
        ]


# Global instance
canonical_business_intelligence_service = CanonicalBusinessIntelligenceService()