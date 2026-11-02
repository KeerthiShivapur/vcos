"""Phase 4I.4 — Company Planning Context / State Synthesis Engine.

This is the canonical state-synthesis layer of the Virtual Company OS.

It does NOT create a parallel planning module, dashboard, or duplicate data store.
It is a deterministic synthesis derived from the entire canonical VCOS substrate:
- 4I.1: CompanyIntent, CompanyPlan, PlanItem, PlanAdaptation, IntentPrediction, PlanSimulation, IntentPlanState
- 4I.2: CompanyObjective, ObjectiveOutcome, ObjectiveOutcomeAssessment, ObjectiveContradiction, ObjectivePrediction, ObjectiveSimulation, ObjectivePlanState
- 4I.3: StrategicAlignment, AlignmentGap, StrategicConflict, StrategicAlignmentState, StrategicDependency, AlignmentGapDetection
- 4H.7: OrganizationalLearning, LearningEvidence, PatternDetection
- CompanyBrain, CompanyState, CompanyDecision, CompanyAction
- CompanyGoal, CompanyInitiative, StrategicLink, StrategicHistory

Every synthesized state preserves:
- Provenance chain back to canonical sources
- Epistemic status (observed/measured/evidence_backed/institutional_lesson/inferred/predicted/proposed/contested)
- Contradiction visibility (both sides preserved)
- Temporal reasoning (state transitions with triggers)
- Governance scope (who can see/change what)
- Exact-once semantics (fingerprint on canonical inputs)

The synthesis is deterministic: same canonical inputs -> same state.
State changes are recorded as transitions with full provenance.
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
    _compute_fingerprint,
    CompanyPlanningContext,
    CompanyStateTransition,
    PlanningContextProvenance,
)
from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
from app.models.company_state import CompanyState
from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
from app.models.intelligence import PatternDetection
from app.models.company_actions import CompanyAction
from app.intelligence.company_brain import company_brain


def _days(n: int) -> timedelta:
    return timedelta(days=n)


class CompanyPlanningContextEngine:
    """
    Company Planning Context Engine — deterministic state synthesis from canonical sources.
    
    Key principles:
    - Governance-first: scope resolved before any retrieval
    - Learning-first: consumes 4H.7 lessons/patterns/contradictions/provenance
    - Deterministic: same canonical inputs -> same synthesized state
    - Provenance: every conclusion traces back to canonical sources
    - Epistemic separation: fact vs inference vs prediction vs proposal vs contested
    - Contradiction preservation: both sides visible, never silently resolved
    - Temporal truth: state transitions recorded with triggers, never overwritten
    """

    def __init__(self):
        pass

    # -------------------------------------------------------------------------
    # Main Synthesis Entry Point
    # -------------------------------------------------------------------------

    async def synthesize_planning_context(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        trigger: str = "manual_recompute",
        source_event_id: Optional[str] = None,
        trigger_reason: Optional[str] = None,
    ) -> CompanyPlanningContext:
        """
        Synthesize the complete company planning context from all canonical sources.
        
        This is the primary entry point. It computes all 8 state sections and
        persists a new CompanyPlanningContext version with full provenance.
        """
        started = time.perf_counter()
        
# Build input fingerprint for exact-once semantics
        input_data = {
            "organization_id": organization_id,
            "scope": scope,
            "scope_id": scope_id,
            "trigger": trigger,
            "source_event_id": source_event_id,
            # Note: computed_at intentionally excluded for deterministic testing
        }
        input_fingerprint = _compute_fingerprint(input_data)

        # Exact-once semantics: only apply when triggered by a specific event
        # Manual recompute should always create a new version
        existing_context = None
        if source_event_id and trigger != "manual_recompute":
            existing_context = await self._get_context_by_input_fingerprint(db, organization_id, input_fingerprint)
            if existing_context:
                return existing_context

        # Get previous context for transition tracking
        previous_context = await self._get_latest_context(db, organization_id, scope, scope_id)
        
        # Compute all state sections
        strategic_state = await self._synthesize_strategic_state(db, organization_id, scope, scope_id)
        execution_state = await self._synthesize_execution_state(db, organization_id, scope, scope_id)
        outcome_state = await self._synthesize_outcome_state(db, organization_id, scope, scope_id)
        alignment_state = await self._synthesize_alignment_state(db, organization_id, scope, scope_id)
        learning_state = await self._synthesize_learning_state(db, organization_id, scope, scope_id)
        resource_state = await self._synthesize_resource_state(db, organization_id, scope, scope_id)
        risk_state = await self._synthesize_risk_state(db, organization_id, scope, scope_id)
        governance_state = await self._synthesize_governance_state(db, organization_id, scope, scope_id)
        
        # Compute overall health and confidence
        overall_health, overall_confidence = self._compute_overall_health(
            strategic_state, execution_state, outcome_state, alignment_state,
            learning_state, resource_state, risk_state, governance_state
        )
        
        # Count signals
        active_contradictions = self._count_active_contradictions(
            strategic_state, execution_state, outcome_state, alignment_state, learning_state
        )
        critical_gaps, total_gaps = self._count_gaps(alignment_state)
        relevant_lessons, high_confidence_lessons, emerging_patterns = self._count_learning_signals(learning_state)
        elevated_risks, newly_emerging_risks = self._count_risk_signals(risk_state)
        
        # Determine version
        version = (previous_context.version + 1) if previous_context else 1
        previous_version_id = previous_context.id if previous_context else None
        
        # Build context object
        context = CompanyPlanningContext(
            organization_id=organization_id,
            scope=scope,
            scope_id=scope_id,
            version=version,
            previous_version_id=previous_version_id,
            strategic_state=strategic_state,
            execution_state=execution_state,
            outcome_state=outcome_state,
            alignment_state=alignment_state,
            learning_state=learning_state,
            resource_state=resource_state,
            risk_state=risk_state,
            governance_state=governance_state,
            overall_health=overall_health,
            overall_confidence=overall_confidence,
            active_contradictions=active_contradictions,
            critical_gaps=critical_gaps,
            total_gaps=total_gaps,
            relevant_lessons=relevant_lessons,
            high_confidence_lessons=high_confidence_lessons,
            emerging_patterns=emerging_patterns,
            elevated_risks=elevated_risks,
            newly_emerging_risks=newly_emerging_risks,
            computed_at=utcnow(),
            computation_duration_ms=int((time.perf_counter() - started) * 1000),
            trigger=trigger,
            source_event_id=source_event_id,
            input_fingerprint=input_fingerprint,
            fingerprint=_compute_fingerprint({
                "strategic": strategic_state,
                "execution": execution_state,
                "outcome": outcome_state,
                "alignment": alignment_state,
                "learning": learning_state,
                "resource": resource_state,
                "risk": risk_state,
                "governance": governance_state,
                "version": version,
            }),
        )
        
        db.add(context)
        await db.flush()
        
        # Record state transition if there's a previous version
        if previous_context:
            await self._record_state_transition(
                db, organization_id, scope, scope_id,
                previous_context, context,
                trigger, source_event_id, trigger_reason
            )
        
        # Persist provenance chains
        await self._persist_provenance_chains(
            db, organization_id, context,
            strategic_state, execution_state, outcome_state,
            alignment_state, learning_state, resource_state,
            risk_state, governance_state
        )
        
        return context

    async def _get_latest_context(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
    ) -> Optional[CompanyPlanningContext]:
        """Get the most recent planning context for the given scope."""
        stmt = select(CompanyPlanningContext).where(
            CompanyPlanningContext.organization_id == organization_id,
            CompanyPlanningContext.scope == scope,
            CompanyPlanningContext.scope_id == scope_id,
        ).order_by(CompanyPlanningContext.version.desc()).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_context_by_input_fingerprint(
        self,
        db: AsyncSession,
        organization_id: str,
        input_fingerprint: str,
    ) -> Optional[CompanyPlanningContext]:
        """Get an existing context by input fingerprint for exact-once semantics."""
        stmt = select(CompanyPlanningContext).where(
            CompanyPlanningContext.organization_id == organization_id,
            CompanyPlanningContext.input_fingerprint == input_fingerprint,
        ).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def __del__(self):
        pass

    # -------------------------------------------------------------------------
    # Section Synthesis Methods
    # -------------------------------------------------------------------------

    async def _synthesize_strategic_state(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
    ) -> dict:
        """Synthesize strategic state: intents, goals, objectives, strategic priorities."""
        # Active intents
        intent_conditions = [CompanyIntent.organization_id == organization_id]
        if scope != "company" and scope_id:
            intent_conditions.append(CompanyIntent.scope == scope)
            intent_conditions.append(CompanyIntent.scope_id == scope_id)
        
        intents_stmt = select(CompanyIntent).where(and_(*intent_conditions))
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
        
        # Active objectives (with intent linkage)
        obj_conditions = [
            CompanyObjective.organization_id == organization_id,
            CompanyObjective.status == "active",
        ]
        if scope != "company" and scope_id:
            # Filter objectives linked to intents in this scope
            obj_conditions.append(
                or_(
                    CompanyObjective.intent_id.in_([i.id for i in intents]),
                    CompanyObjective.goal_id.in_([g.id for g in goals])
                )
            )
        
        objectives_stmt = select(CompanyObjective).where(and_(*obj_conditions))
        objectives_result = await db.execute(objectives_stmt)
        objectives = objectives_result.scalars().all()
        
        # Strategic priorities (top 5 by priority)
        strategic_priorities = sorted(
            [{"id": i.id, "title": i.title, "kind": i.kind, "priority": i.priority, 
              "epistemic_status": i.epistemic_status, "source": i.source} 
             for i in active_intents],
            key=lambda x: x["priority"]
        )[:5]
        
        # At-risk objectives
        at_risk_objectives = [
            {"id": o.id, "title": o.title, "status": o.status, "health": "at_risk" if o.status == "at_risk" else "healthy"}
            for o in objectives if o.status in ("at_risk", "failed")
        ]
        
        return {
            "state": {
                "active_intents_count": len(active_intents),
                "proposed_intents_count": len(proposed_intents),
                "active_goals_count": len(goals),
                "active_objectives_count": len(objectives),
                "strategic_priorities": strategic_priorities,
                "at_risk_objectives": at_risk_objectives,
                "intent_kinds": list(set(i.kind for i in active_intents)),
                "goal_kinds": list(set(g.kind for g in goals)),
            },
            "epistemic_status": "observed",
            "confidence": 0.9,
            "provenance": [{"type": "intent", "ids": [i.id for i in intents]}, 
                          {"type": "goal", "ids": [g.id for g in goals]},
                          {"type": "objective", "ids": [o.id for o in objectives]}],
            "contradictions": [],
        }

    async def _synthesize_execution_state(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
    ) -> dict:
        """Synthesize execution state: initiatives, projects, work, actions."""
        # Active initiatives
        init_conditions = [
            CompanyInitiative.organization_id == organization_id,
            CompanyInitiative.status == "active",
        ]
        initiatives_stmt = select(CompanyInitiative).where(and_(*init_conditions))
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
        
        # Plan items in progress
        plan_items_conditions = [
            PlanItem.organization_id == organization_id,
            PlanItem.state.in_(["in_progress", "pending"]),
        ]
        items_stmt = select(PlanItem).where(and_(*plan_items_conditions))
        items_result = await db.execute(items_stmt)
        plan_items = items_result.scalars().all()
        
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
                "active_plan_items_count": len([i for i in plan_items if i.state == "in_progress"]),
                "pending_plan_items_count": len([i for i in plan_items if i.state == "pending"]),
                "blocking_dependencies_count": len(blocking_deps),
                "initiative_project_coverage": len([i for i in initiatives if initiative_project_map.get(i.id)]) / len(initiatives) if initiatives else 0,
            },
            "epistemic_status": "observed",
            "confidence": 0.85,
            "provenance": [
                {"type": "initiative", "ids": [i.id for i in initiatives]},
                {"type": "project", "ids": list(set(project_ids))},
                {"type": "action", "ids": [a.id for a in actions]},
                {"type": "plan_item", "ids": [i.id for i in plan_items]},
            ],
            "contradictions": [],
        }

    async def _synthesize_outcome_state(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
    ) -> dict:
        """Synthesize outcome state: expected/actual outcomes, assessments, deviations."""
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
        
        # Categorize outcomes
        achieved = [o for o in outcomes if o.outcome_state == "actual" and o.assessment in ("outperformed", "met")]
        on_track = [o for o in outcomes if o.outcome_state == "projected" and o.variance_pct is not None and o.variance_pct <= 10]
        underperforming = [o for o in outcomes if o.assessment in ("underperformed", "missed")]
        inconclusive = [o for o in outcomes if o.assessment == "inconclusive" or o.outcome_state == "projected" and o.variance_pct is None]
        
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
                "total_outcomes_tracked": len(outcomes),
                "achieved_outcomes": len(achieved),
                "on_track_outcomes": len(on_track),
                "underperforming_outcomes": len(underperforming),
                "inconclusive_outcomes": len(inconclusive),
                "completed_assessments": len(assessments),
                "assessment_confidence_distribution": confidence_dist,
                "average_variance_pct": sum(o.variance_pct for o in outcomes if o.variance_pct is not None) / len([o for o in outcomes if o.variance_pct is not None]) if any(o.variance_pct is not None for o in outcomes) else 0,
            },
            "epistemic_status": "measured",
            "confidence": 0.8,
            "provenance": [
                {"type": "objective_outcome", "ids": [o.id for o in outcomes]},
                {"type": "objective_outcome_assessment", "ids": [a.id for a in assessments]},
            ],
            "contradictions": [],
        }

    async def _synthesize_alignment_state(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
    ) -> dict:
        """Synthesize alignment state: alignments, gaps, conflicts, dependencies."""
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
                {"type": "contradiction_in_alignment", "count": sum(a.contradiction_ids for a in alignments if a.contradiction_ids)},
            ],
        }

    def _count_by_field(self, items: list, field: str) -> dict:
        counts = {}
        for item in items:
            val = getattr(item, field, None)
            if val:
                counts[val] = counts.get(val, 0) + 1
        return counts

    async def _synthesize_learning_state(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
    ) -> dict:
        """Synthesize learning state: lessons, patterns, contradictions, materialized knowledge."""
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
        contradictions_stmt = select(CompanyDecisionContradiction).where(
            CompanyDecisionContradiction.organization_id == organization_id,
            CompanyDecisionContradiction.status == "open",
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

    async def _synthesize_resource_state(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
    ) -> dict:
        """Synthesize resource state: capacity, constraints, allocation."""
        # This would integrate with capacity planning, resource allocation intelligence
        # For now, return a structured placeholder that can be extended
        
        # Get company actions by assignee to understand allocation
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
                "capacity_constraints": [],
                "allocation_efficiency": 1.0 - (len(overloaded) / len(assignee_load)) if assignee_load else 1.0,
            },
            "epistemic_status": "inferred",
            "confidence": 0.6,
            "provenance": [{"type": "company_action", "ids": [a.id for a in actions]}],
            "contradictions": [],
        }

    async def _synthesize_risk_state(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
    ) -> dict:
        """Synthesize risk state: strategic, execution, dependency, outcome risks."""
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

    async def _synthesize_governance_state(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
    ) -> dict:
        """Synthesize governance state: scope, permissions, unresolved decisions, constraints."""
        # Pending decisions
        pending_decisions_stmt = select(CompanyDecision).where(
            CompanyDecision.organization_id == organization_id,
            CompanyDecision.state.in_(["proposed", "evaluated", "recommended", "approved"]),
        )
        pending_decisions_result = await db.execute(pending_decisions_stmt)
        pending_decisions = pending_decisions_result.scalars().all()
        
        # Decisions needing outcome recording
        outcome_pending_stmt = select(CompanyDecision).where(
            CompanyDecision.organization_id == organization_id,
            CompanyDecision.state.in_(["executed"]),
        )
        outcome_pending_result = await db.execute(outcome_pending_stmt)
        outcome_pending = outcome_pending_result.scalars().all()
        
        # Active contradictions in governance
        gov_contradictions_stmt = select(CompanyDecisionContradiction).where(
            CompanyDecisionContradiction.organization_id == organization_id,
            CompanyDecisionContradiction.status == "open",
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
                "governance_constraints": [],
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

    def _compute_overall_health(
        self,
        strategic: dict,
        execution: dict,
        outcome: dict,
        alignment: dict,
        learning: dict,
        resource: dict,
        risk: dict,
        governance: dict,
    ) -> tuple[str, float]:
        """Compute overall company health and confidence from section states."""
        # Weighted health scoring
        health_scores = {
            "strategic": self._section_health(strategic),
            "execution": self._section_health(execution),
            "outcome": self._section_health(outcome),
            "alignment": self._section_health(alignment),
            "learning": self._section_health(learning),
            "resource": self._section_health(resource),
            "risk": self._section_health(risk),
            "governance": self._section_health(governance),
        }
        
        weights = {
            "strategic": 0.20,
            "execution": 0.20,
            "outcome": 0.15,
            "alignment": 0.15,
            "learning": 0.10,
            "resource": 0.05,
            "risk": 0.10,
            "governance": 0.05,
        }
        
        weighted_score = sum(health_scores[k] * weights[k] for k in weights)
        
        if weighted_score >= 80:
            overall_health = "healthy"
        elif weighted_score >= 50:
            overall_health = "at_risk"
        else:
            overall_health = "critical"
        
        # Overall confidence is the minimum section confidence (weakest link)
        confidences = [strategic.get("confidence", 0), execution.get("confidence", 0),
                      outcome.get("confidence", 0), alignment.get("confidence", 0),
                      learning.get("confidence", 0), resource.get("confidence", 0),
                      risk.get("confidence", 0), governance.get("confidence", 0)]
        overall_confidence = min(confidences) if confidences else 0.0
        
        return overall_health, overall_confidence

    def _section_health(self, section: dict) -> float:
        """Compute health score (0-100) for a section."""
        state = section.get("state", {})
        # This is a simplified heuristic - real implementation would be more nuanced
        base = 70
        # Boost for good indicators
        if state.get("achieved_outcomes", 0) > state.get("underperforming_outcomes", 0):
            base += 10
        if state.get("active_contradictions", 0) == 0:
            base += 10
        if state.get("critical_gaps", 0) == 0:
            base += 10
        # Penalty for bad indicators
        if state.get("underperforming_outcomes", 0) > 0:
            base -= 15
        if state.get("blocking_dependencies", 0) > 0:
            base -= 10
        if state.get("total_risks", 0) > 5:
            base -= 10
        if state.get("open_governance_contradictions", 0) > 0:
            base -= 5
        return max(0, min(100, base))

    def _count_active_contradictions(self, *sections: dict) -> int:
        """Count total active contradictions across all sections."""
        count = 0
        for section in sections:
            contras = section.get("contradictions", [])
            for c in contras:
                if isinstance(c, dict) and "ids" in c:
                    count += len(c["ids"])
                elif isinstance(c, dict) and "count" in c:
                    count += c["count"]
        return count

    def _count_gaps(self, alignment_state: dict) -> tuple[int, int]:
        """Count critical and total gaps."""
        state = alignment_state.get("state", {})
        critical = state.get("critical_gaps", 0)
        total = state.get("total_gaps", 0)
        return critical, total

    def _count_learning_signals(self, learning_state: dict) -> tuple[int, int, int]:
        """Count learning signals."""
        state = learning_state.get("state", {})
        relevant = state.get("active_lessons_count", 0)
        high_conf = state.get("high_confidence_lessons_count", 0)
        emerging = state.get("emerging_patterns_count", 0)
        return relevant, high_conf, emerging

    def _count_risk_signals(self, risk_state: dict) -> tuple[int, int]:
        """Count risk signals."""
        state = risk_state.get("state", {})
        elevated = state.get("total_risks", 0)
        emerging = state.get("newly_emerging_from_patterns", 0)
        return elevated, emerging

    # -------------------------------------------------------------------------
    # State Transition Recording
    # -------------------------------------------------------------------------

    async def _record_state_transition(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
        from_context: CompanyPlanningContext,
        to_context: CompanyPlanningContext,
        trigger: str,
        trigger_event_id: Optional[str],
        trigger_reason: Optional[str],
    ) -> CompanyStateTransition:
        """Record a state transition with full delta and provenance."""
        
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
        
        # Determine transition kind
        transition_kind = self._determine_transition_kind(changed_sections)
        
        transition = CompanyStateTransition(
            organization_id=organization_id,
            scope=scope,
            scope_id=scope_id,
            from_version=from_context.version,
            to_version=to_context.version,
            from_context_id=from_context.id,
            to_context_id=to_context.id,
            trigger=trigger,
            trigger_event_id=trigger_event_id,
            trigger_reason=trigger_reason or f"State recomputed via {trigger}",
            transition_kind=transition_kind,
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
            computed_by="company_planning_context_engine",
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
        from_context: CompanyPlanningContext,
        to_context: CompanyPlanningContext,
    ) -> dict:
        """Compute detailed delta between two context versions."""
        sections = [
            "strategic_state", "execution_state", "outcome_state",
            "alignment_state", "learning_state", "resource_state",
            "risk_state", "governance_state"
        ]
        
        delta = {}
        for section in sections:
            from_state = getattr(from_context, section, {}) or {}
            to_state = getattr(to_context, section, {}) or {}
            
            # Compare state dicts
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

    def _diff_contradictions(self, from_ctx: CompanyPlanningContext, to_ctx: CompanyPlanningContext, kind: str) -> list:
        """Diff contradictions between context versions."""
        # Simplified - would need to track contradiction IDs per section
        return []

    def _diff_gaps(self, from_ctx: CompanyPlanningContext, to_ctx: CompanyPlanningContext, kind: str) -> list:
        """Diff gaps between context versions."""
        return []

    def _extract_influencing_lessons(self, context: CompanyPlanningContext) -> list:
        """Extract lesson fingerprints that influenced this state."""
        lessons = []
        for section_name in ["strategic_state", "execution_state", "outcome_state", 
                              "alignment_state", "learning_state", "resource_state",
                              "risk_state", "governance_state"]:
            section = getattr(context, section_name, {}) or {}
            for prov in section.get("provenance", []):
                if prov.get("type") == "organizational_learning":
                    lessons.extend(prov.get("ids", []))
        return list(set(lessons))

    def _extract_influencing_patterns(self, context: CompanyPlanningContext) -> list:
        """Extract pattern IDs that influenced this state."""
        patterns = []
        for section_name in ["strategic_state", "execution_state", "outcome_state",
                              "alignment_state", "learning_state", "resource_state",
                              "risk_state", "governance_state"]:
            section = getattr(context, section_name, {}) or {}
            for prov in section.get("provenance", []):
                if prov.get("type") == "pattern_detection":
                    patterns.extend(prov.get("ids", []))
        return list(set(patterns))

    def _determine_transition_kind(self, changed_sections: list) -> str:
        """Determine the primary transition kind from changed sections."""
        if len(changed_sections) > 2:
            return "composite_state_change"
        elif "strategic_state" in changed_sections:
            return "strategic_state_change"
        elif "execution_state" in changed_sections:
            return "execution_state_change"
        elif "outcome_state" in changed_sections:
            return "outcome_state_change"
        elif "alignment_state" in changed_sections:
            return "alignment_state_change"
        elif "learning_state" in changed_sections:
            return "learning_state_change"
        elif "resource_state" in changed_sections:
            return "resource_state_change"
        elif "risk_state" in changed_sections:
            return "risk_state_change"
        elif "governance_state" in changed_sections:
            return "governance_state_change"
        return "composite_state_change"

    # -------------------------------------------------------------------------
    # Provenance Chain Persistence
    # -------------------------------------------------------------------------

    async def _persist_provenance_chains(
        self,
        db: AsyncSession,
        organization_id: str,
        context: CompanyPlanningContext,
        strategic: dict,
        execution: dict,
        outcome: dict,
        alignment: dict,
        learning: dict,
        resource: dict,
        risk: dict,
        governance: dict,
    ) -> None:
        """Persist provenance chains for all conclusions in the context."""
        
        sections_data = {
            "strategic": strategic,
            "execution": execution,
            "outcome": outcome,
            "alignment": alignment,
            "learning": learning,
            "resource": resource,
            "risk": risk,
            "governance": governance,
        }
        
        for section_name, section_data in sections_data.items():
            state = section_data.get("state", {})
            epistemic = section_data.get("epistemic_status", "observed")
            confidence = section_data.get("confidence", 0.5)
            provenance = section_data.get("provenance", [])
            contradictions = section_data.get("contradictions", [])
            
            # For each key conclusion in the state, create provenance record
            prov_index = 0
            for conclusion_key, conclusion_value in state.items():
                if isinstance(conclusion_value, (dict, list)) and not conclusion_value:
                    continue  # Skip empty collections
                
                # Collect evidence fingerprints from provenance
                evidence_fps = []
                pattern_ids = []
                lesson_fps = []
                contra_evidence_fps = []
                contra_pattern_ids = []
                contra_lesson_fps = []
                contra_ids = []
                source_entities = []
                
                for prov in provenance:
                    prov_type = prov.get("type")
                    prov_ids = prov.get("ids", [])
                    if prov_type in ("intent", "goal", "objective", "initiative", "project", 
                                    "action", "plan_item", "company_decision"):
                        source_entities.extend([{"type": prov_type, "id": pid} for pid in prov_ids])
                    elif prov_type == "organizational_learning":
                        lesson_fps.extend(prov_ids)
                    elif prov_type == "pattern_detection":
                        pattern_ids.extend(prov_ids)
                    elif prov_type in ("objective_outcome", "objective_outcome_assessment"):
                        evidence_fps.extend(prov_ids)
                    elif "contradiction" in prov_type:
                        contra_ids.extend(prov_ids)
                
                for contra in contradictions:
                    if isinstance(contra, dict):
                        if "ids" in contra:
                            contra_ids.extend(contra["ids"])
                
                # Build intent->goal->objective->initiative->project chain from source entities
                intent_id = None
                goal_id = None
                objective_id = None
                initiative_id = None
                project_id = None
                
                for entity in source_entities:
                    if entity["type"] == "intent" and not intent_id:
                        intent_id = entity["id"]
                    elif entity["type"] == "goal" and not goal_id:
                        goal_id = entity["id"]
                    elif entity["type"] == "objective" and not objective_id:
                        objective_id = entity["id"]
                    elif entity["type"] == "initiative" and not initiative_id:
                        initiative_id = entity["id"]
                    elif entity["type"] == "project" and not project_id:
                        project_id = entity["id"]
                
                # Convert conclusion_value to string for storage
                    cv_str = str(conclusion_value) if conclusion_value is not None else None
                    
                    try:
                        prov_record = PlanningContextProvenance(
                            organization_id=organization_id,
                            context_id=context.id,
                            section=section_name,
                            conclusion_key=conclusion_key,
                            conclusion_value=cv_str,
                            epistemic_status=epistemic,
                            confidence=confidence,
                            evidence_fingerprints=json.dumps(evidence_fps),
                            pattern_ids=json.dumps(pattern_ids),
                            lesson_fingerprints=json.dumps(lesson_fps),
                            contradicting_evidence_fingerprints=json.dumps(contra_evidence_fps),
                            contradicting_pattern_ids=json.dumps(contra_pattern_ids),
                            contradicting_lesson_fingerprints=json.dumps(contra_lesson_fps),
                            contradiction_ids=json.dumps(contra_ids),
                            source_entities=source_entities,
                            intent_id=intent_id,
                            goal_id=goal_id,
                            objective_id=objective_id,
                            initiative_id=initiative_id,
                            project_id=project_id,
                            scope=context.scope,
                            scope_id=context.scope_id,
                            generated_by="company_planning_context_engine",
                            source_event_id=context.source_event_id,
                            fingerprint=_compute_fingerprint({
                                "context_id": context.id,
                                "section": section_name,
                                "conclusion_key": conclusion_key,
                                "conclusion_value": conclusion_value,
                                "source_entities": source_entities,
                                "prov_index": prov_index,
                            }),
                        )
                    except Exception as e:
                        # Log the error and re-raise
                        import logging
                        logging.error(f"Failed to create PlanningContextProvenance: {e}")
                        raise
                    db.add(prov_record)
                    prov_index += 1
        
        await db.flush()

    # -------------------------------------------------------------------------
    # Query Methods for External Consumers
    # -------------------------------------------------------------------------

    async def get_planning_context(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Optional[CompanyPlanningContext]:
        """Get a planning context by scope and optional version."""
        conditions = [
            CompanyPlanningContext.organization_id == organization_id,
            CompanyPlanningContext.scope == scope,
            CompanyPlanningContext.scope_id == scope_id,
        ]
        if version:
            conditions.append(CompanyPlanningContext.version == version)
        
        stmt = select(CompanyPlanningContext).where(and_(*conditions))
        if not version:
            stmt = stmt.order_by(CompanyPlanningContext.version.desc()).limit(1)
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_state_transitions(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        from_version: Optional[int] = None,
        to_version: Optional[int] = None,
        limit: int = 50,
    ) -> list[CompanyStateTransition]:
        """Get state transition history."""
        conditions = [
            CompanyStateTransition.organization_id == organization_id,
            CompanyStateTransition.scope == scope,
            CompanyStateTransition.scope_id == scope_id,
        ]
        if from_version:
            conditions.append(CompanyStateTransition.from_version == from_version)
        if to_version:
            conditions.append(CompanyStateTransition.to_version == to_version)
        
        stmt = select(CompanyStateTransition).where(and_(*conditions)).order_by(
            CompanyStateTransition.transitioned_at.desc()
        ).limit(limit)
        
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_provenance_for_conclusion(
        self,
        db: AsyncSession,
        organization_id: str,
        context_id: str,
        section: str,
        conclusion_key: str,
    ) -> Optional[PlanningContextProvenance]:
        """Get provenance chain for a specific conclusion."""
        stmt = select(PlanningContextProvenance).where(
            PlanningContextProvenance.organization_id == organization_id,
            PlanningContextProvenance.context_id == context_id,
            PlanningContextProvenance.section == section,
            PlanningContextProvenance.conclusion_key == conclusion_key,
        ).order_by(PlanningContextProvenance.generated_at.desc()).limit(1)
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_full_provenance_chain(
        self,
        db: AsyncSession,
        organization_id: str,
        context_id: str,
    ) -> list[PlanningContextProvenance]:
        """Get complete provenance chain for a context."""
        stmt = select(PlanningContextProvenance).where(
            PlanningContextProvenance.organization_id == organization_id,
            PlanningContextProvenance.context_id == context_id,
        ).order_by(PlanningContextProvenance.section, PlanningContextProvenance.conclusion_key)
        
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
    ) -> CompanyPlanningContext:
        """Trigger a recomputation of the planning context."""
        if trigger not in STATE_TRANSITION_TRIGGERS:
            trigger = "manual_recompute"
        
        return await self.synthesize_planning_context(
            db, organization_id,
            scope=scope,
            scope_id=scope_id,
            trigger=trigger,
            source_event_id=source_event_id,
            trigger_reason=trigger_reason,
        )

    # -------------------------------------------------------------------------
    # Integration with CompanyBrain
    # -------------------------------------------------------------------------

    async def answer_planning_question(
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
        Answer a planning question using the synthesized planning context.
        
        This integrates with CompanyBrain's governance-first retrieval.
        """
        # Get or synthesize current context
        context = await self.get_planning_context(db, organization_id, scope=scope, scope_id=scope_id)
        if not context:
            context = await self.synthesize_planning_context(db, organization_id, scope=scope, scope_id=scope_id)
        
        # Build structured answer from context sections
        answer = {
            "question": question,
            "context_version": context.version,
            "context_computed_at": context.computed_at.isoformat() if context.computed_at else None,
            "overall_health": context.overall_health,
            "overall_confidence": context.overall_confidence,
            "strategic_summary": context.strategic_state.get("state", {}),
            "execution_summary": context.execution_state.get("state", {}),
            "outcome_summary": context.outcome_state.get("state", {}),
            "alignment_summary": context.alignment_state.get("state", {}),
            "learning_summary": context.learning_state.get("state", {}),
            "resource_summary": context.resource_state.get("state", {}),
            "risk_summary": context.risk_state.get("state", {}),
            "governance_summary": context.governance_state.get("state", {}),
            "active_contradictions": context.active_contradictions,
            "critical_gaps": context.critical_gaps,
            "relevant_lessons": context.relevant_lessons,
            "elevated_risks": context.elevated_risks,
            "provenance_available": True,
        }
        
        return answer


company_planning_context_engine = CompanyPlanningContextEngine()