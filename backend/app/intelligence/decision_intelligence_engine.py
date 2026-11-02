"""Phase 4I.6 — Decision Intelligence Engine.

This engine CONSUMES the entire canonical VCOS substrate and produces
a comprehensive decision intelligence context that supports governed decision-making.

Key principles:
- Governance-first: scope resolved before any retrieval
- Learning-first: consumes 4H.7 lessons/patterns/contradictions/provenance
- Deterministic: same canonical inputs -> same decision intelligence context
- Provenance: every conclusion traces back to canonical sources
- Epistemic separation: fact vs inference vs prediction vs proposal vs contested
- Contradiction preservation: both sides visible, never silently resolved
- Temporal truth: state transitions recorded with triggers
- No autonomous action: intelligence synthesized, decisions governed
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, date, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.company_intent import (
    CompanyIntent,
    CompanyPlan,
    PlanItem,
    PlanAdaptation,
    IntentPrediction,
    PlanSimulation,
    IntentPlanState,
    INTENT_KINDS,
    INTENT_EPISTEMIC_STATUS,
    INTENT_SOURCE,
    PLAN_KINDS,
    PLAN_STATES,
    ADAPTATION_TRIGGERS,
    ADAPTATION_ACTIONS,
)
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
    StrategicLink,
    StrategicHistory,
    ObjectiveOutcome,
    ObjectiveOutcomeAssessment,
    ObjectiveContradiction,
    ObjectivePrediction,
    ObjectiveSimulation,
    ObjectivePlanState,
    StrategicAlignment,
    AlignmentGap,
    StrategicConflict,
    StrategicAlignmentState,
    StrategicDependency,
    AlignmentGapDetection,
    StrategicOutcome,
    OBJECTIVE_STATES,
    OUTCOME_STATES,
    ASSESSMENT_STATES,
    MEASUREMENT_QUALITY,
    SUPERSESSION_REASON,
    ASSESSMENT_CONFIDENCE,
    ALIGNMENT_TYPES,
    ALIGNMENT_STATES,
    ALIGNMENT_STRENGTH,
    ALIGNMENT_GAP_TYPES,
    ALIGNMENT_GAP_SEVERITY,
    CONTRIBUTION_LEVELS,
    PLANNING_CONTEXT_SECTIONS,
    PLANNING_CONTEXT_EPISTEMIC_STATUS,
    PLANNING_CONTEXT_CONFIDENCE,
    STATE_TRANSITION_TRIGGERS,
    STATE_TRANSITION_KINDS,
    DECISION_INTELLIGENCE_TYPES,
    DECISION_INTELLIGENCE_STATES,
    DECISION_ALTERNATIVE_STATES,
    CONSEQUENCE_TYPES,
    RISK_ASSESSMENT_LEVELS,
    EVIDENCE_QUALITY_LEVELS,
    PRECEDENT_RELEVANCE_LEVELS,
    _compute_fingerprint,
    CompanyPlanningContext,
    CompanyStateTransition,
    PlanningContextProvenance,
    AdaptivePlanningContext,
    AttentionSignal,
    ReplanningProposal,
    DecisionContext,
    AdaptivePlanningTransition,
    DecisionIntelligenceContext,
    DecisionAlternative,
    DecisionConsequence,
    DecisionPrecedentLink,
    DecisionEvidence,
    DecisionRiskAssessment,
    DecisionIntelligenceTransition,
    DECISION_INTELLIGENCE_TYPES,
    DECISION_INTELLIGENCE_STATES,
    DECISION_ALTERNATIVE_STATES,
    CONSEQUENCE_TYPES,
    RISK_ASSESSMENT_LEVELS,
    EVIDENCE_QUALITY_LEVELS,
    PRECEDENT_RELEVANCE_LEVELS,
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
    StrategicAlignment,
    AlignmentGap,
    StrategicConflict,
    StrategicDependency,
)
from app.models.company_operating import CompanyDecision as OperatingCompanyDecision, CompanyDecisionContradiction as OperatingCompanyDecisionContradiction
from app.models.company_state import CompanyState
from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
from app.models.intelligence import PatternDetection
from app.models.company_actions import CompanyAction
from app.intelligence.company_planning_context_engine import company_planning_context_engine
from app.intelligence.adaptive_planning_engine import adaptive_planning_engine


def _days(n: int) -> timedelta:
    return timedelta(days=n)


class DecisionIntelligenceEngine:
    """
    Decision Intelligence Engine — composes decision intelligence from all canonical sources.
    
    Key principles:
    - Governance-first: scope resolved before any retrieval
    - Learning-first: consumes 4H.7 lessons/patterns/contradictions/provenance
    - Deterministic: same canonical inputs -> same decision intelligence context
    - Provenance: every conclusion traces back to canonical sources
    - Epistemic separation: fact vs inference vs prediction vs proposal vs contested
    - Contradiction preservation: both sides visible, never silently resolved
    - Temporal truth: state transitions recorded with triggers
    - No autonomous action: intelligence synthesized, decisions governed
    """

    def __init__(self):
        pass

    # -------------------------------------------------------------------------
    # Main Synthesis Entry Point
    # -------------------------------------------------------------------------

    async def synthesize_decision_intelligence(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        decision_type: str,
        title: str,
        description: Optional[str] = None,
        scope: str = "company",
        scope_id: Optional[str] = None,
        planning_context: Optional[object] = None,
        adaptive_context: Optional[object] = None,
        trigger: str = "manual_synthesis",
        source_event_id: Optional[str] = None,
        trigger_reason: Optional[str] = None,
    ) -> DecisionIntelligenceContext:
        """
        Synthesize the decision intelligence context from all canonical sources.
        
        This is the primary entry point. It computes all synthesized sections and
        persists a new DecisionIntelligenceContext version with full provenance.
        """
        started = time.perf_counter()
        
        # Get planning context if not provided
        if planning_context is None:
            from app.intelligence.company_planning_context_engine import company_planning_context_engine
            planning_context = await company_planning_context_engine.get_planning_context(
                db, organization_id, scope=scope, scope_id=scope_id
            )
            if not planning_context:
                planning_context = await company_planning_context_engine.synthesize_planning_context(
                    db, organization_id, scope=scope, scope_id=scope_id
                )
        
        # Get adaptive context if not provided
        if adaptive_context is None:
            from app.intelligence.adaptive_planning_engine import adaptive_planning_engine
            adaptive_context = await adaptive_planning_engine.get_adaptive_context(
                db, organization_id, scope=scope, scope_id=scope_id,
                planning_context_id=planning_context.id
            )
        
        # Build input fingerprint for exact-once semantics
        input_data = {
            "organization_id": organization_id,
            "scope": scope,
            "scope_id": scope_id,
            "decision_type": decision_type,
            "title": title,
            "planning_context_id": planning_context.id,
            "planning_context_version": planning_context.version,
            "planning_context_fingerprint": planning_context.fingerprint,
            "adaptive_context_id": adaptive_context.id if adaptive_context else None,
            "trigger": trigger,
            "source_event_id": source_event_id,
        }
        input_fingerprint = _compute_fingerprint(input_data)
        
        # Get previous context for transition tracking
        previous_context = await self._get_latest_context(
            db, organization_id, scope, scope_id, planning_context.id
        )
        
        # Compute all synthesized sections
        strategic_context = await self._synthesize_strategic_context(db, organization_id, planning_context, adaptive_context)
        objective_context = await self._synthesize_objective_context(db, organization_id, planning_context, adaptive_context)
        objective_outcome_context = await self._synthesize_objective_outcome_context(db, organization_id, planning_context, adaptive_context)
        strategic_outcome_context = await self._synthesize_strategic_outcome_context(db, organization_id, planning_context, adaptive_context)
        alignment_context = await self._synthesize_alignment_context(db, organization_id, planning_context, adaptive_context)
        execution_context = await self._synthesize_execution_context(db, organization_id, planning_context, adaptive_context)
        resource_context = await self._synthesize_resource_context(db, organization_id, planning_context, adaptive_context)
        risk_context = await self._synthesize_risk_context(db, organization_id, planning_context, adaptive_context)
        learning_context = await self._synthesize_learning_context(db, organization_id, planning_context, adaptive_context)
        governance_context = await self._synthesize_governance_context(db, organization_id, planning_context, adaptive_context)
        
        # Merge outcome contexts
        objective_outcome_context = await self._synthesize_objective_outcome_context(db, organization_id, planning_context, adaptive_context)
        strategic_outcome_context = await self._synthesize_strategic_outcome_context(db, organization_id, planning_context, adaptive_context)
        outcome_context = {
            "state": {
                **objective_outcome_context.get("state", {}),
                **strategic_outcome_context.get("state", {}),
            },
            "epistemic_status": "measured",
            "confidence": min(
                objective_outcome_context.get("confidence", 0.8),
                strategic_outcome_context.get("confidence", 0.8)
            ),
            "provenance": objective_outcome_context.get("provenance", []) + strategic_outcome_context.get("provenance", []),
            "contradictions": objective_outcome_context.get("contradictions", []) + strategic_outcome_context.get("contradictions", []),
        }
        
        # Compute overall assessment
        overall_confidence = self._compute_overall_confidence(
            strategic_context, objective_context, alignment_context, outcome_context,
            execution_context, resource_context, risk_context, learning_context, governance_context
        )
        
        active_contradictions = self._count_active_contradictions(
            strategic_context, objective_context, alignment_context, outcome_context,
            execution_context, resource_context, risk_context, learning_context, governance_context
        )
        critical_gaps = self._count_critical_gaps(alignment_context)
        elevated_risks = self._count_elevated_risks(risk_context)
        high_confidence_lessons = self._count_high_confidence_lessons(learning_context)
        
# Get previous context for transition tracking
        previous_context = await self._get_latest_context(
            db, organization_id, scope, scope_id, planning_context.id
        )
        
        # Also get cross-context previous for cross-planning-context transitions
        cross_context_previous = None
        if not previous_context:
            cross_context_previous = await self._get_latest_context_for_scope(
                db, organization_id, scope, scope_id
            )
        
        # Determine version
        version = (previous_context.version + 1) if previous_context else 1
        previous_version_id = previous_context.id if previous_context else None
        
        # Track the previous context for transition recording
        transition_from_version_id = previous_version_id
        transition_from_context = previous_context
        
        # If no previous context for this planning context, use cross-context previous
        if not previous_context and cross_context_previous:
            version = cross_context_previous.version + 1
            previous_version_id = cross_context_previous.id
        
        # Build context object
        context = DecisionIntelligenceContext(
            organization_id=organization_id,
            scope=scope,
            scope_id=scope_id,
            planning_context_id=planning_context.id,
            planning_context_version=planning_context.version,
            planning_context_fingerprint=planning_context.fingerprint,
            adaptive_context_id=adaptive_context.id if adaptive_context else None,
            version=version,
            previous_version_id=previous_version_id,
            decision_type=decision_type,
            title=title[:300],
            description=description,
            trigger=trigger,
            trigger_event_id=source_event_id,
            trigger_reason=trigger_reason,
            strategic_context=strategic_context,
            objective_context=objective_context,
            alignment_context=alignment_context,
            outcome_context=outcome_context,
            execution_context=execution_context,
            resource_context=resource_context,
            risk_context=risk_context,
            learning_context=learning_context,
            governance_context=governance_context,
            overall_confidence=overall_confidence,
            active_contradictions=active_contradictions,
            critical_gaps=critical_gaps,
            elevated_risks=elevated_risks,
            high_confidence_lessons=high_confidence_lessons,
            computed_at=utcnow(),
            computation_duration_ms=int((time.perf_counter() - started) * 1000),
            source_event_id=source_event_id,
            input_fingerprint=input_fingerprint,
            fingerprint=_compute_fingerprint({
                "strategic": strategic_context,
                "objective": objective_context,
                "alignment": alignment_context,
                "outcome": outcome_context,
                "execution": execution_context,
                "resource": resource_context,
                "risk": risk_context,
                "learning": learning_context,
                "governance": governance_context,
                "version": version,
            }),
        )
        
        db.add(context)
        await db.flush()
        
        # Record state transition if there's a previous version
        if previous_context:
            await self._record_transition(
                db, organization_id, scope, scope_id,
                previous_context, context,
                trigger, source_event_id, trigger_reason
            )
        elif cross_context_previous:
            # Cross-planning-context transition
            if cross_context_previous.version != context.version:
                await self._record_transition(
                    db, organization_id, scope, scope_id,
                    cross_context_previous, context,
                    trigger, source_event_id, trigger_reason
                )
        
        db.add(context)
        await db.flush()
        
        # Record state transition if there's a previous version
        if previous_context:
            await self._record_transition(
                db, organization_id, scope, scope_id,
                previous_context, context,
                trigger, source_event_id, trigger_reason
            )
        
        # Persist provenance chains
        await self._persist_provenance_chains(
            db, organization_id, context,
            strategic_context, objective_context, alignment_context,
            outcome_context, execution_context, resource_context,
            risk_context, learning_context, governance_context
        )
        
        return context

    async def _get_latest_context(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
        planning_context_id: str,
    ) -> Optional[DecisionIntelligenceContext]:
        """Get the most recent decision intelligence context for the given scope and planning context."""
        stmt = select(DecisionIntelligenceContext).where(
            DecisionIntelligenceContext.organization_id == organization_id,
            DecisionIntelligenceContext.scope == scope,
            DecisionIntelligenceContext.scope_id == scope_id,
            DecisionIntelligenceContext.planning_context_id == planning_context_id,
        ).order_by(DecisionIntelligenceContext.version.desc()).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_latest_context_for_scope(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
    ) -> Optional[DecisionIntelligenceContext]:
        """Get the most recent decision intelligence context for the given scope (any planning context)."""
        stmt = select(DecisionIntelligenceContext).where(
            DecisionIntelligenceContext.organization_id == organization_id,
            DecisionIntelligenceContext.scope == scope,
            DecisionIntelligenceContext.scope_id == scope_id,
        ).order_by(DecisionIntelligenceContext.computed_at.desc()).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # Section Synthesis Methods
    # -------------------------------------------------------------------------

    async def _synthesize_strategic_context(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: object,
        adaptive_context: Optional[object],
    ) -> dict:
        """Synthesize strategic context: intents, goals, strategic priorities."""
        # All intents (filtering done in Python for flexibility)
        intents_stmt = select(CompanyIntent).where(
            CompanyIntent.organization_id == organization_id,
        )
        intents_result = await db.execute(intents_stmt)
        intents = intents_result.scalars().all()
        
        active_intents = [i for i in intents if i.state in ("active", "adopted")]
        proposed_intents = [i for i in intents if i.state in ("proposed", "discovered")]
        
        # Active goals
        goals_stmt = select(CompanyGoal).where(
            CompanyGoal.organization_id == organization_id,
            CompanyGoal.status == "active",
        )
        goals_result = await db.execute(goals_stmt)
        goals = goals_result.scalars().all()
        
        # Strategic priorities (top 5 by priority)
        strategic_priorities = sorted(
            [{"id": i.id, "title": i.title, "kind": i.kind, "priority": i.priority, 
              "epistemic_status": i.epistemic_status, "source": i.source} 
             for i in active_intents],
            key=lambda x: x["priority"]
        )[:5]
        
        return {
            "state": {
                "active_intents_count": len(active_intents),
                "proposed_intents_count": len(proposed_intents),
                "active_goals_count": len(goals),
                "strategic_priorities": strategic_priorities,
                "intent_kinds": list(set(i.kind for i in active_intents)),
                "goal_kinds": list(set(g.kind for g in goals)),
            },
            "epistemic_status": "observed",
            "confidence": 0.9,
            "provenance": [{"type": "intent", "ids": [i.id for i in intents]}, 
                          {"type": "goal", "ids": [g.id for g in goals]}],
            "contradictions": [],
        }

    async def _synthesize_objective_context(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: object,
        adaptive_context: Optional[object],
    ) -> dict:
        """Synthesize objective context: objectives, outcomes, assessments."""
        # Active objectives
        objectives_stmt = select(CompanyObjective).where(
            CompanyObjective.organization_id == organization_id,
            CompanyObjective.status == "active",
        )
        objectives_result = await db.execute(objectives_stmt)
        objectives = objectives_result.scalars().all()
        
        # Objective outcomes
        outcomes_stmt = select(ObjectiveOutcome).where(
            ObjectiveOutcome.organization_id == organization_id,
        )
        outcomes_result = await db.execute(outcomes_stmt)
        outcomes = outcomes_result.scalars().all()
        
        # Outcome assessments
        assessments_stmt = select(ObjectiveOutcomeAssessment).where(
            ObjectiveOutcomeAssessment.organization_id == organization_id,
            ObjectiveOutcomeAssessment.assessment_state == "completed",
        )
        assessments_result = await db.execute(assessments_stmt)
        assessments = assessments_result.scalars().all()
        
        # Objective contradictions
        contradictions_stmt = select(ObjectiveContradiction).where(
            ObjectiveContradiction.organization_id == organization_id,
            ObjectiveContradiction.status == "open",
        )
        contradictions_result = await db.execute(contradictions_stmt)
        contradictions = contradictions_result.scalars().all()
        
        # Categorize outcomes
        achieved = [o for o in outcomes if o.outcome_state == "actual" and o.assessment in ("outperformed", "met")]
        on_track = [o for o in outcomes if o.outcome_state == "projected" and o.variance_pct is not None and o.variance_pct <= 10]
        underperforming = [o for o in outcomes if o.assessment in ("underperformed", "missed")]
        inconclusive = [o for o in outcomes if o.assessment == "inconclusive" or (o.outcome_state == "projected" and o.variance_pct is None)]
        
        # Assessment confidence distribution
        confidence_dist = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
        for a in assessments:
            if a.confidence >= 0.7:
                confidence_dist["high"] += 1
            elif a.confidence >= 0.4:
                confidence_dist["medium"] += 1
            elif a.confidence > 0:
                confidence_dist["low"] += 1
            else:
                confidence_dist["unknown"] += 1
        
        return {
            "state": {
                "active_objectives_count": len(objectives),
                "total_outcomes_tracked": len(outcomes),
                "achieved_outcomes": len(achieved),
                "on_track_outcomes": len(on_track),
                "underperforming_outcomes": len(underperforming),
                "inconclusive_outcomes": len(inconclusive),
                "completed_assessments": len(assessments),
                "assessment_confidence_distribution": confidence_dist,
                "open_contradictions": len(contradictions),
                "average_variance_pct": sum(o.variance_pct for o in outcomes if o.variance_pct is not None) / len([o for o in outcomes if o.variance_pct is not None]) if any(o.variance_pct is not None for o in outcomes) else 0,
            },
            "epistemic_status": "measured",
            "confidence": 0.8,
            "provenance": [
                {"type": "objective", "ids": [o.id for o in objectives]},
                {"type": "objective_outcome", "ids": [o.id for o in outcomes]},
                {"type": "objective_outcome_assessment", "ids": [a.id for a in assessments]},
            ],
            "contradictions": [{"type": "objective_contradiction", "ids": [c.id for c in contradictions]}],
        }

    async def _synthesize_alignment_context(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: object,
        adaptive_context: Optional[object],
    ) -> dict:
        """Synthesize alignment context: alignments, gaps, conflicts, dependencies."""
        # Active alignments
        alignments_stmt = select(StrategicAlignment).where(
            StrategicAlignment.organization_id == organization_id,
            StrategicAlignment.alignment_state == "active",
        )
        alignments_result = await db.execute(alignments_stmt)
        alignments = alignments_result.scalars().all()
        
        # Alignment gaps
        gaps_stmt = select(AlignmentGap).where(
            AlignmentGap.organization_id == organization_id,
            AlignmentGap.state.in_(["open", "acknowledged", "mitigating"]),
        )
        gaps_result = await db.execute(gaps_stmt)
        gaps = gaps_result.scalars().all()
        critical_gaps = [g for g in gaps if g.severity == "critical"]
        
        # Strategic conflicts
        conflicts_stmt = select(StrategicConflict).where(
            StrategicConflict.organization_id == organization_id,
            StrategicConflict.status.in_(["open", "acknowledged", "mitigating"]),
        )
        conflicts_result = await db.execute(conflicts_stmt)
        conflicts = conflicts_result.scalars().all()
        
        # Dependencies
        deps_stmt = select(StrategicDependency).where(
            StrategicDependency.organization_id == organization_id,
            StrategicDependency.state == "active",
        )
        deps_result = await db.execute(deps_stmt)
        dependencies = deps_result.scalars().all()
        blocking_deps = [d for d in dependencies if d.is_blocking]
        
        # Alignment state materializations
        states_stmt = select(StrategicAlignmentState).where(
            StrategicAlignmentState.organization_id == organization_id,
        )
        states_result = await db.execute(states_stmt)
        alignment_states = states_result.scalars().all()
        
        avg_alignment_score = sum(s.overall_alignment_score for s in alignment_states) / len(alignment_states) if alignment_states else 0
        
        return {
            "state": {
                "total_alignments": len(alignments),
                "active_alignments": len([a for a in alignments if a.alignment_state == "active"]),
                "alignment_types_distribution": self._count_by_field(alignments, "alignment_type"),
                "strength_distribution": self._count_by_field(alignments, "strength"),
                "total_gaps": len(gaps),
                "critical_gaps": len(critical_gaps),
                "gaps_by_type": self._count_by_field(gaps, "gap_type"),
                "gaps_by_severity": self._count_by_field(gaps, "severity"),
                "active_conflicts": len(conflicts),
                "conflicts_by_type": self._count_by_field(conflicts, "conflict_type"),
                "conflicts_by_severity": self._count_by_field(conflicts, "severity"),
                "total_dependencies": len(dependencies),
                "blocking_dependencies": len(blocking_deps),
                "average_alignment_score": avg_alignment_score,
                "projects_without_initiatives": sum(s.projects_without_initiatives for s in alignment_states),
                "objectives_without_initiatives": sum(s.objectives_without_initiatives for s in alignment_states),
            },
            "epistemic_status": "evidence_backed",
            "confidence": 0.85,
            "provenance": [
                {"type": "strategic_alignment", "ids": [a.id for a in alignments]},
                {"type": "alignment_gap", "ids": [g.id for g in gaps]},
                {"type": "strategic_conflict", "ids": [c.id for c in conflicts]},
                {"type": "strategic_dependency", "ids": [d.id for d in dependencies]},
            ],
            "contradictions": [
                {"type": "conflict", "ids": [c.id for c in conflicts]},
            ],
        }

    def _count_by_field(self, items: list, field: str) -> dict:
        counts = {}
        for item in items:
            val = getattr(item, field, None)
            if val:
                counts[val] = counts.get(val, 0) + 1
        return counts

    async def _synthesize_objective_outcome_context(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: object,
        adaptive_context: Optional[object],
    ) -> dict:
        """Synthesize objective outcome context: objectives, outcomes, assessments."""
        # Active objectives
        objectives_stmt = select(CompanyObjective).where(
            CompanyObjective.organization_id == organization_id,
            CompanyObjective.status == "active",
        )
        objectives_result = await db.execute(objectives_stmt)
        objectives = objectives_result.scalars().all()
        
        # Objective outcomes
        outcomes_stmt = select(ObjectiveOutcome).where(
            ObjectiveOutcome.organization_id == organization_id,
        )
        outcomes_result = await db.execute(outcomes_stmt)
        outcomes = outcomes_result.scalars().all()
        
        # Outcome assessments
        assessments_stmt = select(ObjectiveOutcomeAssessment).where(
            ObjectiveOutcomeAssessment.organization_id == organization_id,
            ObjectiveOutcomeAssessment.assessment_state == "completed",
        )
        assessments_result = await db.execute(assessments_stmt)
        assessments = assessments_result.scalars().all()
        
        # Objective contradictions
        contradictions_stmt = select(ObjectiveContradiction).where(
            ObjectiveContradiction.organization_id == organization_id,
            ObjectiveContradiction.status == "open",
        )
        contradictions_result = await db.execute(contradictions_stmt)
        contradictions = contradictions_result.scalars().all()
        
        # Categorize outcomes
        achieved = [o for o in outcomes if o.outcome_state == "actual" and o.assessment in ("outperformed", "met")]
        on_track = [o for o in outcomes if o.outcome_state == "projected" and o.variance_pct is not None and o.variance_pct <= 10]
        underperforming = [o for o in outcomes if o.assessment in ("underperformed", "missed")]
        inconclusive = [o for o in outcomes if o.assessment == "inconclusive" or (o.outcome_state == "projected" and o.variance_pct is None)]
        
        # Assessment confidence distribution
        confidence_dist = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
        for a in assessments:
            if a.confidence >= 0.7:
                confidence_dist["high"] += 1
            elif a.confidence >= 0.4:
                confidence_dist["medium"] += 1
            elif a.confidence > 0:
                confidence_dist["low"] += 1
            else:
                confidence_dist["unknown"] += 1
        
        return {
            "state": {
                "active_objectives_count": len(objectives),
                "total_outcomes_tracked": len(outcomes),
                "achieved_outcomes": len(achieved),
                "on_track_outcomes": len(on_track),
                "underperforming_outcomes": len(underperforming),
                "inconclusive_outcomes": len(inconclusive),
                "completed_assessments": len(assessments),
                "assessment_confidence_distribution": confidence_dist,
                "open_contradictions": len(contradictions),
                "average_variance_pct": sum(o.variance_pct for o in outcomes if o.variance_pct is not None) / len([o for o in outcomes if o.variance_pct is not None]) if any(o.variance_pct is not None for o in outcomes) else 0,
            },
            "epistemic_status": "measured",
            "confidence": 0.8,
            "provenance": [
                {"type": "objective", "ids": [o.id for o in objectives]},
                {"type": "objective_outcome", "ids": [o.id for o in outcomes]},
                {"type": "objective_outcome_assessment", "ids": [a.id for a in assessments]},
            ],
            "contradictions": [{"type": "objective_contradiction", "ids": [c.id for c in contradictions]}],
        }

    async def _synthesize_execution_context(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: object,
        adaptive_context: Optional[object],
    ) -> dict:
        """Synthesize execution context: initiatives, projects, actions."""
        # Active initiatives
        initiatives_stmt = select(CompanyInitiative).where(
            CompanyInitiative.organization_id == organization_id,
            CompanyInitiative.status == "active",
        )
        initiatives_result = await db.execute(initiatives_stmt)
        initiatives = initiatives_result.scalars().all()
        
        # Projects linked to initiatives
        project_ids = []
        initiative_project_map = {}
        for init in initiatives:
            links_stmt = select(StrategicLink).where(
                StrategicLink.organization_id == organization_id,
                StrategicLink.initiative_id == init.id,
            )
            links_result = await db.execute(links_stmt)
            links = links_result.scalars().all()
            pids = [l.project_id for l in links]
            initiative_project_map[init.id] = pids
            project_ids.extend(pids)
        
        # Company actions in progress
        action_conditions = [
            CompanyAction.organization_id == organization_id,
            CompanyAction.state.in_(["in_progress", "ready", "awaiting_approval"]),
        ]
        actions_stmt = select(CompanyAction).where(and_(*action_conditions))
        actions_result = await db.execute(actions_stmt)
        actions = actions_result.scalars().all()
        
        # Dependency bottlenecks (blocking dependencies)
        dep_stmt = select(StrategicDependency).where(
            StrategicDependency.organization_id == organization_id,
            StrategicDependency.is_blocking == True,
            StrategicDependency.state == "active",
        )
        dep_result = await db.execute(dep_stmt)
        blocking_deps = dep_result.scalars().all()
        
        return {
            "state": {
                "active_initiatives_count": len(initiatives),
                "active_projects_count": len(set(project_ids)),
                "in_progress_actions_count": len([a for a in actions if a.state == "in_progress"]),
                "awaiting_approval_actions_count": len([a for a in actions if a.state == "awaiting_approval"]),
                "blocking_dependencies_count": len(blocking_deps),
                "initiative_project_coverage": len([i for i in initiatives if initiative_project_map.get(i.id)]) / len(initiatives) if initiatives else 0,
            },
            "epistemic_status": "observed",
            "confidence": 0.85,
            "provenance": [
                {"type": "initiative", "ids": [i.id for i in initiatives]},
                {"type": "project", "ids": list(set(project_ids))},
                {"type": "company_action", "ids": [a.id for a in actions]},
            ],
            "contradictions": [],
        }

    async def _synthesize_strategic_outcome_context(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: object,
        adaptive_context: Optional[object],
    ) -> dict:
        """Synthesize strategic outcome context: strategic outcomes and decision outcomes."""
        # Strategic outcomes
        strategic_outcomes_stmt = select(StrategicOutcome).where(
            StrategicOutcome.organization_id == organization_id,
        )
        strategic_outcomes_result = await db.execute(strategic_outcomes_stmt)
        strategic_outcomes = strategic_outcomes_result.scalars().all()
        
        # Company decision outcomes
        decision_outcomes_stmt = select(OperatingCompanyDecision).where(
            OperatingCompanyDecision.organization_id == organization_id,
            OperatingCompanyDecision.state == "outcome_recorded",
        )
        decision_outcomes_result = await db.execute(decision_outcomes_stmt)
        decision_outcomes = decision_outcomes_result.scalars().all()
        
        return {
            "state": {
                "strategic_outcomes_count": len(strategic_outcomes),
                "decision_outcomes_recorded": len(decision_outcomes),
                "strategic_outcomes_by_metric": self._count_by_field(strategic_outcomes, "metric_kind"),
            },
            "epistemic_status": "measured",
            "confidence": 0.8,
            "provenance": [
                {"type": "strategic_outcome", "ids": [o.id for o in strategic_outcomes]},
                {"type": "company_decision", "ids": [d.id for d in decision_outcomes]},
            ],
            "contradictions": [],
        }

    async def _synthesize_resource_context(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: object,
        adaptive_context: Optional[object],
    ) -> dict:
        """Synthesize resource context: capacity, constraints, allocation."""
        # Company actions by assignee to understand allocation
        actions_stmt = select(CompanyAction).where(
            CompanyAction.organization_id == organization_id,
            CompanyAction.state.in_(["in_progress", "ready", "awaiting_approval"]),
            CompanyAction.assignee_id.isnot(None),
        )
        actions_result = await db.execute(actions_stmt)
        actions = actions_result.scalars().all()
        
        # Group by assignee
        assignee_load = {}
        for action in actions:
            key = f"{action.assignee_type}:{action.assignee_id}"
            if key not in assignee_load:
                assignee_load[key] = {"count": 0, "actions": []}
            assignee_load[key]["count"] += 1
            assignee_load[key]["actions"].append(action.id)
        
        overloaded = [k for k, v in assignee_load.items() if v["count"] > 5]
        
        return {
            "state": {
                "total_active_actions": len(actions),
                "unique_assignees": len(assignee_load),
                "overloaded_assignees": len(overloaded),
                "assignee_load_distribution": {k: v["count"] for k, v in assignee_load.items()},
                "allocation_efficiency": 1.0 - (len(overloaded) / len(assignee_load)) if assignee_load else 1.0,
            },
            "epistemic_status": "inferred",
            "confidence": 0.6,
            "provenance": [{"type": "company_action", "ids": [a.id for a in actions]}],
            "contradictions": [],
        }

    async def _synthesize_risk_context(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: object,
        adaptive_context: Optional[object],
    ) -> dict:
        """Synthesize risk context: strategic, execution, dependency, outcome risks."""
        # Strategic risks from objectives at risk
        at_risk_obj_stmt = select(CompanyObjective).where(
            CompanyObjective.organization_id == organization_id,
            CompanyObjective.status == "at_risk",
        )
        at_risk_obj_result = await db.execute(at_risk_obj_stmt)
        at_risk_objectives = at_risk_obj_result.scalars().all()
        
        # Execution risks from blocking dependencies
        blocking_deps_stmt = select(StrategicDependency).where(
            StrategicDependency.organization_id == organization_id,
            StrategicDependency.is_blocking == True,
            StrategicDependency.state == "active",
        )
        blocking_deps_result = await db.execute(blocking_deps_stmt)
        blocking_deps = blocking_deps_result.scalars().all()
        
        # Outcome risks from underperforming outcomes
        underperf_stmt = select(ObjectiveOutcome).where(
            ObjectiveOutcome.organization_id == organization_id,
            ObjectiveOutcome.assessment.in_(["underperformed", "missed"]),
        )
        underperf_result = await db.execute(underperf_stmt)
        underperforming = underperf_result.scalars().all()
        
        # Prediction-based risks
        intent_predictions_stmt = select(IntentPrediction).where(
            IntentPrediction.organization_id == organization_id,
        )
        intent_predictions_result = await db.execute(intent_predictions_stmt)
        intent_predictions = intent_predictions_result.scalars().all()
        
        obj_predictions_stmt = select(ObjectivePrediction).where(
            ObjectivePrediction.organization_id == organization_id,
        )
        obj_predictions_result = await db.execute(obj_predictions_stmt)
        obj_predictions = obj_predictions_result.scalars().all()
        
        # New risks from learning (patterns that predict failure)
        risk_patterns_stmt = select(PatternDetection).where(
            PatternDetection.organization_id == organization_id,
            PatternDetection.family.in_(["execution", "decision"]),
            PatternDetection.status.in_(["confirmed", "persistent"]),
        )
        risk_patterns_result = await db.execute(risk_patterns_stmt)
        risk_patterns = risk_patterns_result.scalars().all()
        
        all_risks = []
        for obj in at_risk_objectives:
            all_risks.append({
                "type": "strategic",
                "source_type": "objective",
                "source_id": obj.id,
                "title": f"Objective at risk: {obj.title}",
                "severity": "high",
            })
        for dep in blocking_deps:
            all_risks.append({
                "type": "dependency",
                "source_type": "dependency",
                "source_id": dep.id,
                "title": f"Blocking dependency: {dep.dependent_type}:{dep.dependent_id} -> {dep.dependency_type}:{dep.dependency_id}",
                "severity": "high" if dep.is_hard_dependency else "medium",
            })
        for outcome in underperforming:
            all_risks.append({
                "type": "outcome",
                "source_type": "objective_outcome",
                "source_id": outcome.id,
                "title": f"Underperforming outcome: {outcome.metric_kind}",
                "severity": "high",
            })
        
        # Newly emerging risks from patterns
        newly_emerging = [p for p in risk_patterns if p.trend == "rising"]
        
        return {
            "state": {
                "strategic_risks_count": len(at_risk_objectives),
                "execution_risks_count": len(blocking_deps),
                "outcome_risks_count": len(underperforming),
                "prediction_risks_count": len([p for p in intent_predictions if p.prediction.get("trajectory") == "at_risk"]),
                "total_risks": len(all_risks),
                "newly_emerging_from_patterns": len(newly_emerging),
                "top_risks": sorted(all_risks, key=lambda x: 0 if x["severity"] == "high" else 1)[:10],
                "risk_patterns": [{"id": p.id, "title": p.title, "trend": p.trend} for p in newly_emerging[:5]],
            },
            "epistemic_status": "inferred",
            "confidence": 0.75,
            "provenance": [
                {"type": "objective", "ids": [o.id for o in at_risk_objectives]},
                {"type": "strategic_dependency", "ids": [d.id for d in blocking_deps]},
                {"type": "objective_outcome", "ids": [o.id for o in underperforming]},
                {"type": "intent_prediction", "ids": [p.id for p in intent_predictions]},
                {"type": "objective_prediction", "ids": [p.id for p in obj_predictions]},
                {"type": "pattern_detection", "ids": [p.id for p in risk_patterns]},
            ],
            "contradictions": [],
        }

    async def _synthesize_learning_context(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: object,
        adaptive_context: Optional[object],
    ) -> dict:
        """Synthesize learning context: lessons, patterns, contradictions, materialized knowledge."""
        # Active lessons
        lessons_conditions = [
            OrganizationalLearning.organization_id == organization_id,
            OrganizationalLearning.status == "active",
        ]
        lessons_stmt = select(OrganizationalLearning).where(and_(*lessons_conditions))
        lessons_result = await db.execute(lessons_stmt)
        lessons = lessons_result.scalars().all()
        
        high_confidence_lessons = [l for l in lessons if l.confidence >= 0.7]
        
        # Active patterns
        patterns_conditions = [
            PatternDetection.organization_id == organization_id,
            PatternDetection.status.in_(["candidate", "emerging", "confirmed", "persistent"]),
        ]
        patterns_stmt = select(PatternDetection).where(and_(*patterns_conditions))
        patterns_result = await db.execute(patterns_stmt)
        patterns = patterns_result.scalars().all()
        
        emerging_patterns = [p for p in patterns if p.status in ("candidate", "emerging")]
        
        # Contradictions from organizational learning (via CompanyDecisionContradiction)
        contradictions_stmt = select(OperatingCompanyDecisionContradiction).where(
            OperatingCompanyDecisionContradiction.organization_id == organization_id,
            OperatingCompanyDecisionContradiction.status == "open",
        )
        contradictions_result = await db.execute(contradictions_stmt)
        contradictions = contradictions_result.scalars().all()
        
        # Objective contradictions
        obj_contradictions_stmt = select(ObjectiveContradiction).where(
            ObjectiveContradiction.organization_id == organization_id,
            ObjectiveContradiction.status == "open",
        )
        obj_contradictions_result = await db.execute(obj_contradictions_stmt)
        obj_contradictions = obj_contradictions_result.scalars().all()
        
        # Lessons by lifecycle
        lifecycle_dist = {}
        for l in lessons:
            lifecycle_dist[l.lifecycle] = lifecycle_dist.get(l.lifecycle, 0) + 1
        
        # Patterns by family
        family_dist = {}
        for p in patterns:
            family_dist[p.family] = family_dist.get(p.family, 0) + 1
        
        return {
            "state": {
                "active_lessons_count": len(lessons),
                "high_confidence_lessons_count": len(high_confidence_lessons),
                "lessons_by_lifecycle": lifecycle_dist,
                "active_patterns_count": len(patterns),
                "emerging_patterns_count": len(emerging_patterns),
                "patterns_by_family": family_dist,
                "open_contradictions_count": len(contradictions) + len(obj_contradictions),
                "decision_contradictions": len(contradictions),
                "objective_contradictions": len(obj_contradictions),
                "top_lessons": sorted(
                    [{"id": l.id, "title": l.title, "confidence": l.confidence, "kind": l.kind} 
                     for l in lessons],
                    key=lambda x: x["confidence"],
                    reverse=True
                )[:5],
                "top_patterns": sorted(
                    [{"id": p.id, "title": p.title, "confidence": p.confidence, "family": p.family, "count": p.count} 
                     for p in patterns],
                    key=lambda x: x["confidence"],
                    reverse=True
                )[:5],
            },
            "epistemic_status": "institutional_lesson",
            "confidence": 0.8,
            "provenance": [
                {"type": "organizational_learning", "ids": [l.id for l in lessons]},
                {"type": "pattern_detection", "ids": [p.id for p in patterns]},
                {"type": "company_decision_contradiction", "ids": [c.id for c in contradictions]},
                {"type": "objective_contradiction", "ids": [c.id for c in obj_contradictions]},
            ],
            "contradictions": [
                {"type": "decision_contradiction", "ids": [c.id for c in contradictions]},
                {"type": "objective_contradiction", "ids": [c.id for c in obj_contradictions]},
            ],
        }

    async def _synthesize_governance_context(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: object,
        adaptive_context: Optional[object],
    ) -> dict:
        """Synthesize governance context: scope, permissions, unresolved decisions, constraints."""
        # Pending decisions
        pending_decisions_stmt = select(OperatingCompanyDecision).where(
            OperatingCompanyDecision.organization_id == organization_id,
            OperatingCompanyDecision.state.in_(["proposed", "evaluated", "recommended", "approved"]),
        )
        pending_decisions_result = await db.execute(pending_decisions_stmt)
        pending_decisions = pending_decisions_result.scalars().all()
        
        # Decisions needing outcome recording
        outcome_pending_stmt = select(OperatingCompanyDecision).where(
            OperatingCompanyDecision.organization_id == organization_id,
            OperatingCompanyDecision.state.in_(["executed"]),
        )
        outcome_pending_result = await db.execute(outcome_pending_stmt)
        outcome_pending = outcome_pending_result.scalars().all()
        
        # Active contradictions in governance
        gov_contradictions_stmt = select(OperatingCompanyDecisionContradiction).where(
            OperatingCompanyDecisionContradiction.organization_id == organization_id,
            OperatingCompanyDecisionContradiction.status == "open",
        )
        gov_contradictions_result = await db.execute(gov_contradictions_stmt)
        gov_contradictions = gov_contradictions_result.scalars().all()
        
        # Plan adaptations pending approval
        pending_adaptations_stmt = select(PlanAdaptation).where(
            PlanAdaptation.organization_id == organization_id,
            PlanAdaptation.state == "proposed",
        )
        pending_adaptations_result = await db.execute(pending_adaptations_stmt)
        pending_adaptations = pending_adaptations_result.scalars().all()
        
        return {
            "state": {
                "pending_decisions_count": len(pending_decisions),
                "decisions_awaiting_outcome": len(outcome_pending),
                "open_governance_contradictions": len(gov_contradictions),
                "pending_plan_adaptations": len(pending_adaptations),
                "decision_states_distribution": self._count_by_field(pending_decisions, "state"),
            },
            "epistemic_status": "observed",
            "confidence": 0.9,
            "provenance": [
                {"type": "company_decision", "ids": [d.id for d in pending_decisions]},
                {"type": "company_decision_contradiction", "ids": [c.id for c in gov_contradictions]},
                {"type": "plan_adaptation", "ids": [a.id for a in pending_adaptations]},
            ],
            "contradictions": [{"type": "governance_contradiction", "ids": [c.id for c in gov_contradictions]}],
        }

    # -------------------------------------------------------------------------
    # Health & Confidence Computation
    # -------------------------------------------------------------------------

    def _compute_overall_confidence(self, *sections: dict) -> float:
        """Compute overall confidence as minimum of section confidences."""
        confidences = [s.get("confidence", 0) for s in sections]
        return min(confidences) if confidences else 0.0

    def _count_active_contradictions(self, *sections: dict) -> int:
        """Count total active contradictions across all sections."""
        count = 0
        for section in sections:
            contras = section.get("contradictions", [])
            for c in contras:
                if isinstance(c, dict) and "ids" in c:
                    count += len(c["ids"])
        return count

    def _count_critical_gaps(self, alignment_state: dict) -> int:
        """Count critical gaps from alignment state."""
        return alignment_state.get("state", {}).get("critical_gaps", 0)

    def _count_elevated_risks(self, risk_state: dict) -> int:
        """Count elevated risks from risk state."""
        return risk_state.get("state", {}).get("total_risks", 0)

    def _count_high_confidence_lessons(self, learning_state: dict) -> int:
        """Count high confidence lessons from learning state."""
        return learning_state.get("state", {}).get("high_confidence_lessons_count", 0)

    # -------------------------------------------------------------------------
    # State Transition Recording
    # -------------------------------------------------------------------------

    async def _record_transition(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
        from_context: DecisionIntelligenceContext,
        to_context: DecisionIntelligenceContext,
        trigger: str,
        trigger_event_id: Optional[str],
        trigger_reason: Optional[str],
    ) -> DecisionIntelligenceTransition:
        """Record a decision intelligence state transition with full delta and provenance."""
        
        # Check if transition already exists (exact-once replay protection)
        existing_stmt = select(DecisionIntelligenceTransition).where(
            DecisionIntelligenceTransition.organization_id == organization_id,
            DecisionIntelligenceTransition.from_version == from_context.version,
            DecisionIntelligenceTransition.to_version == to_context.version,
        )
        existing_result = await db.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            return existing
        
        # Compute delta
        delta = self._compute_delta(from_context, to_context)
        changed_sections = list(delta.keys())
        
        # Identify new/resolved contradictions
        new_contradictions = self._diff_contradictions(from_context, to_context, "new")
        resolved_contradictions = self._diff_contradictions(from_context, to_context, "resolved")
        
        # Identify new/resolved gaps
        new_gaps = self._diff_gaps(from_context, to_context, "new")
        resolved_gaps = self._diff_gaps(from_context, to_context, "resolved")
        
        # Influencing lessons/patterns
        influencing_lessons = self._extract_influencing_lessons(to_context)
        influencing_patterns = self._extract_influencing_patterns(to_context)
        
        transition = DecisionIntelligenceTransition(
            organization_id=organization_id,
            scope=scope,
            scope_id=scope_id,
            from_version=from_context.version,
            to_version=to_context.version,
            from_context_id=from_context.id,
            to_context_id=to_context.id,
            trigger=trigger,
            trigger_event_id=trigger_event_id,
            trigger_reason=trigger_reason or f"Decision intelligence recomputed via {trigger}",
            delta=delta,
            changed_sections=changed_sections,
            new_contradictions=new_contradictions,
            resolved_contradictions=resolved_contradictions,
            new_gaps=new_gaps,
            resolved_gaps=resolved_gaps,
            influencing_lessons=influencing_lessons,
            influencing_patterns=influencing_patterns,
            state="committed",
            committed_by="system",
            committed_at=utcnow(),
            source_event_id=trigger_event_id,
            computed_by="decision_intelligence_engine",
            fingerprint=_compute_fingerprint({
                "from_version": from_context.version,
                "to_version": to_context.version,
                "delta": delta,
                "trigger": trigger,
            }),
            transitioned_at=utcnow(),
        )
        
        db.add(transition)
        await db.flush()
        return transition

    def _compute_delta(
        self,
        from_context: DecisionIntelligenceContext,
        to_context: DecisionIntelligenceContext,
    ) -> dict:
        """Compute detailed delta between two context versions."""
        sections = [
            "strategic_context", "objective_context", "alignment_context",
            "outcome_context", "execution_context", "resource_context",
            "risk_context", "learning_context", "governance_context"
        ]
        
        delta = {}
        for section in sections:
            from_state = getattr(from_context, section, {}) or {}
            to_state = getattr(to_context, section, {}) or {}
            
            from_data = from_state.get("state", {})
            to_data = to_state.get("state", {})
            
            section_delta = {}
            all_keys = set(from_data.keys()) | set(to_data.keys())
            for key in all_keys:
                from_val = from_data.get(key)
                to_val = to_data.get(key)
                if from_val != to_val:
                    section_delta[key] = {
                        "from": from_val,
                        "to": to_val,
                        "epistemic_status": to_state.get("epistemic_status"),
                        "provenance": to_state.get("provenance", []),
                    }
            
            if section_delta:
                delta[section] = section_delta
        
        return delta

    def _diff_contradictions(self, from_ctx: DecisionIntelligenceContext, to_ctx: DecisionIntelligenceContext, kind: str) -> list:
        """Diff contradictions between context versions."""
        # Simplified - would need to track contradiction IDs per section
        return []

    def _diff_gaps(self, from_ctx: DecisionIntelligenceContext, to_ctx: DecisionIntelligenceContext, kind: str) -> list:
        """Diff gaps between context versions."""
        return []

    def _extract_influencing_lessons(self, context: DecisionIntelligenceContext) -> list:
        """Extract lesson fingerprints that influenced this state."""
        lessons = []
        for section_name in ["strategic_context", "objective_context", "outcome_context", 
                              "alignment_context", "learning_context", "resource_context",
                              "risk_context", "governance_context"]:
            section = getattr(context, section_name, {}) or {}
            for prov in section.get("provenance", []):
                if prov.get("type") == "organizational_learning":
                    lessons.extend(prov.get("ids", []))
        return list(set(lessons))

    def _extract_influencing_patterns(self, context: DecisionIntelligenceContext) -> list:
        """Extract pattern IDs that influenced this state."""
        patterns = []
        for section_name in ["strategic_context", "objective_context", "outcome_context",
                              "alignment_context", "learning_context", "resource_context",
                              "risk_context", "governance_context"]:
            section = getattr(context, section_name, {}) or {}
            for prov in section.get("provenance", []):
                if prov.get("type") == "pattern_detection":
                    patterns.extend(prov.get("ids", []))
        return list(set(patterns))

    # -------------------------------------------------------------------------
    # Provenance Chain Persistence
    # -------------------------------------------------------------------------

    async def _persist_provenance_chains(
        self,
        db: AsyncSession,
        organization_id: str,
        context: DecisionIntelligenceContext,
        strategic: dict,
        objective: dict,
        alignment: dict,
        outcome: dict,
        execution: dict,
        resource: dict,
        risk: dict,
        learning: dict,
        governance: dict,
    ) -> None:
        """Persist provenance chains for all conclusions in the context."""
        
        # Note: We don't have a dedicated provenance table for 4I.6 yet,
        # but the provenance is embedded in each section.
        # This could be extended with a DecisionIntelligenceProvenance model if needed.
        pass

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    async def get_decision_intelligence(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        planning_context_id: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Optional[DecisionIntelligenceContext]:
        """Get a decision intelligence context by scope and optional version."""
        conditions = [
            DecisionIntelligenceContext.organization_id == organization_id,
            DecisionIntelligenceContext.scope == scope,
            DecisionIntelligenceContext.scope_id == scope_id,
        ]
        if planning_context_id:
            conditions.append(DecisionIntelligenceContext.planning_context_id == planning_context_id)
        if version:
            conditions.append(DecisionIntelligenceContext.version == version)
        
        stmt = select(DecisionIntelligenceContext).where(and_(*conditions))
        if not version and not planning_context_id:
            stmt = stmt.order_by(DecisionIntelligenceContext.version.desc()).limit(1)
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_transitions(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        from_version: Optional[int] = None,
        to_version: Optional[int] = None,
        limit: int = 50,
    ) -> list[DecisionIntelligenceTransition]:
        """Get decision intelligence transition history."""
        conditions = [
            DecisionIntelligenceTransition.organization_id == organization_id,
            DecisionIntelligenceTransition.scope == scope,
            DecisionIntelligenceTransition.scope_id == scope_id,
        ]
        if from_version:
            conditions.append(DecisionIntelligenceTransition.from_version == from_version)
        if to_version:
            conditions.append(DecisionIntelligenceTransition.to_version == to_version)
        
        stmt = select(DecisionIntelligenceTransition).where(and_(*conditions)).order_by(
            DecisionIntelligenceTransition.transitioned_at.desc()
        ).limit(limit)
        
        result = await db.execute(stmt)
        return result.scalars().all()

    # -------------------------------------------------------------------------
    # Triggered Recomputation
    # -------------------------------------------------------------------------

    async def trigger_recompute(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        trigger: str,
        source_event_id: Optional[str] = None,
        trigger_reason: Optional[str] = None,
        scope: str = "company",
        scope_id: Optional[str] = None,
    ) -> DecisionIntelligenceContext:
        """Trigger a recomputation of the decision intelligence context."""
        if trigger not in STATE_TRANSITION_TRIGGERS:
            trigger = "manual_recompute"
        
        return await self.synthesize_decision_intelligence(
            db, organization_id,
            decision_type="manual_synthesis",
            title="Recomputed Decision Intelligence",
            scope=scope,
            scope_id=scope_id,
            trigger=trigger,
            source_event_id=source_event_id,
            trigger_reason=trigger_reason,
        )

    # -------------------------------------------------------------------------
    # Integration with CompanyBrain
    # -------------------------------------------------------------------------

    async def answer_decision_question(
        self,
        db: AsyncSession,
        organization_id: str,
        question: str,
        *,
        user: Any,
        scope: str = "company",
        scope_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Answer a decision intelligence question using the synthesized context.
        
        This integrates with CompanyBrain's governance-first retrieval.
        """
        # Get or synthesize current context
        planning_context = await company_planning_context_engine.get_planning_context(
            db, organization_id, scope=scope, scope_id=scope_id
        )
        if not planning_context:
            planning_context = await company_planning_context_engine.synthesize_planning_context(
                db, organization_id, scope=scope, scope_id=scope_id
            )
        
        context = await self.get_decision_intelligence(
            db, organization_id, scope=scope, scope_id=scope_id,
            planning_context_id=planning_context.id
        )
        if not context:
            context = await self.synthesize_decision_intelligence(
                db, organization_id,
                decision_type="manual_synthesis",
                title="Decision Intelligence for Question",
                scope=scope,
                scope_id=scope_id,
                planning_context=planning_context,
            )
        
        # Build structured answer
        answer = {
            "question": question,
            "context_version": context.version,
            "context_computed_at": context.computed_at.isoformat() if context.computed_at else None,
            "overall_confidence": context.overall_confidence,
            "decision_type": context.decision_type,
            "strategic_context": context.strategic_context.get("state", {}),
            "objective_context": context.objective_context.get("state", {}),
            "alignment_context": context.alignment_context.get("state", {}),
            "outcome_context": context.outcome_context.get("state", {}),
            "execution_context": context.execution_context.get("state", {}),
            "resource_context": context.resource_context.get("state", {}),
            "risk_context": context.risk_context.get("state", {}),
            "learning_context": context.learning_context.get("state", {}),
            "governance_context": context.governance_context.get("state", {}),
            "active_contradictions": context.active_contradictions,
            "critical_gaps": context.critical_gaps,
            "elevated_risks": context.elevated_risks,
            "high_confidence_lessons": context.high_confidence_lessons,
            "provenance_available": True,
        }
        
        return answer


decision_intelligence_engine = DecisionIntelligenceEngine()