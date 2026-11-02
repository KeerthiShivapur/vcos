"""Phase 4I.5 — Adaptive Planning / Replanning Engine.

This engine CONSUMES the 4I.4 CompanyPlanningContext and produces:
- Attention signals (what requires human/decision attention)
- Replanning proposals (governance-reviewed adaptations)
- Decision contexts (prepared decisions for governance)

The adaptive planning layer is the BRIDGE between:
CompanyPlanningContext (what IS) → Attention/Decisions (what SHOULD BE)

Key principles:
- Governance-first: scope resolved before any retrieval
- Learning-first: consumes 4H.7 lessons/patterns/contradictions/provenance
- Deterministic: same planning context → same attention signals
- Provenance: every signal/proposal traces back to canonical sources
- Epistemic separation: fact vs inference vs prediction vs proposal
- Contradiction preservation: both sides visible
- Temporal truth: transitions recorded with triggers
- No autonomous action: signals surfaced, decisions governed
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
    AdaptivePlanningContext,
    AttentionSignal,
    ReplanningProposal,
    DecisionContext,
    AdaptivePlanningTransition,
    ATTENTION_SIGNAL_TYPES,
    ATTENTION_SEVERITY,
    REPLANNING_PROPOSAL_TYPES,
    REPLANNING_PROPOSAL_STATUS,
    DECISION_CONTEXT_TYPES,
    DECISION_CONTEXT_STATUS,
)
from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
from app.models.company_state import CompanyState
from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
from app.models.intelligence import PatternDetection
from app.models.company_actions import CompanyAction
from app.intelligence.company_planning_context_engine import company_planning_context_engine


def _days(n: int) -> timedelta:
    return timedelta(days=n)


class AdaptivePlanningEngine:
    """
    Adaptive Planning Engine — consumes 4I.4 Planning Context to detect 
    attention signals and propose replanning.
    
    Key principles:
    - Governance-first: scope resolved before any retrieval
    - Learning-first: consumes 4H.7 lessons/patterns/contradictions/provenance
    - Deterministic: same planning context -> same attention signals
    - Provenance: every signal/proposal traces back to canonical sources
    - Epistemic separation: fact vs inference vs prediction vs proposal
    - Contradiction preservation: both sides visible
    - Temporal truth: transitions recorded with triggers
    - No autonomous action: signals surfaced, decisions governed
    """

    def __init__(self):
        pass

    # -------------------------------------------------------------------------
    # Main Synthesis Entry Point
    # -------------------------------------------------------------------------

    async def synthesize_adaptive_context(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        planning_context: Optional[CompanyPlanningContext] = None,
        trigger: str = "planning_context_change",
        source_event_id: Optional[str] = None,
        trigger_reason: Optional[str] = None,
    ) -> AdaptivePlanningContext:
        """
        Synthesize the adaptive planning context from a planning context.
        
        This is the primary entry point. It computes attention signals,
        replanning proposals, and decision contexts from the planning context.
        """
        started = time.perf_counter()
        
        # Get planning context if not provided
        if planning_context is None:
            planning_context = await company_planning_context_engine.get_planning_context(
                db, organization_id, scope=scope, scope_id=scope_id
            )
            if not planning_context:
                planning_context = await company_planning_context_engine.synthesize_planning_context(
                    db, organization_id, scope=scope, scope_id=scope_id
                )
        
        # Build input fingerprint for exact-once semantics
        input_data = {
            "organization_id": organization_id,
            "scope": scope,
            "scope_id": scope_id,
            "planning_context_id": planning_context.id,
            "planning_context_version": planning_context.version,
            "planning_context_fingerprint": planning_context.fingerprint,
            "trigger": trigger,
            "source_event_id": source_event_id,
}
        input_fingerprint = _compute_fingerprint(input_data)

        # Determine version FIRST (before detecting signals) so we can include it in fingerprints
        # Get previous adaptive context for transition tracking
        previous_context = await self._get_latest_adaptive_context(
            db, organization_id, scope, scope_id, planning_context.id
        )

        # If no previous context for this planning context, check for any previous adaptive context for the scope
        cross_context_previous = None
        if not previous_context:
            cross_context_previous = await self._get_latest_adaptive_context_for_scope(
                db, organization_id, scope, scope_id
            )

        # Determine version
        version = (previous_context.version + 1) if previous_context else 1
        previous_version_id = previous_context.id if previous_context else None

        # If no previous context for this planning context, use cross-context previous
        if not previous_context and cross_context_previous:
            version = cross_context_previous.version + 1
            previous_version_id = cross_context_previous.id

        # Compute attention signals from planning context (with version for fingerprint uniqueness)
        attention_signals = await self._detect_attention_signals(
            db, organization_id, scope, scope_id, planning_context, version
        )

        # Generate replanning proposals from attention signals
        replanning_proposals = await self._generate_replanning_proposals(
            db, organization_id, scope, scope_id, planning_context, attention_signals, version
        )

        # Generate decision contexts from proposals and signals
        decision_contexts = await self._generate_decision_contexts(
            db, organization_id, scope, scope_id, planning_context,
            attention_signals, replanning_proposals, version
        )

        # Compute overall adaptive health
        overall_adaptive_health = self._compute_adaptive_health(
            attention_signals, replanning_proposals, decision_contexts
        )

        attention_count = len(attention_signals)
        critical_attention_count = sum(1 for s in attention_signals if s.get("severity") in ("critical", "urgent"))
        pending_proposals_count = sum(1 for p in replanning_proposals if p.get("status") in ("proposed", "under_review"))
        pending_decisions_count = sum(1 for d in decision_contexts if d.get("status") in ("draft", "proposed", "evaluated", "recommended"))

        # Track the previous context for transition recording
        transition_from_version_id = previous_version_id
        transition_from_context = previous_context
        
        # Build adaptive context
        adaptive_context = AdaptivePlanningContext(
            organization_id=organization_id,
            scope=scope,
            scope_id=scope_id,
            planning_context_id=planning_context.id,
            planning_context_version=planning_context.version,
            planning_context_fingerprint=planning_context.fingerprint,
            version=version,
            previous_version_id=previous_version_id,
            attention_signals=attention_signals,
            replanning_proposals=replanning_proposals,
            decision_contexts=decision_contexts,
            overall_adaptive_health=overall_adaptive_health,
            attention_count=attention_count,
            critical_attention_count=critical_attention_count,
            pending_proposals_count=pending_proposals_count,
            pending_decisions_count=pending_decisions_count,
            computed_at=utcnow(),
            computation_duration_ms=int((time.perf_counter() - started) * 1000),
            trigger=trigger,
            source_event_id=source_event_id,
            input_fingerprint=input_fingerprint,
            fingerprint=_compute_fingerprint({
                "attention_signals": attention_signals,
                "replanning_proposals": replanning_proposals,
                "decision_contexts": decision_contexts,
            }),
        )
        
        db.add(adaptive_context)
        await db.flush()
        
        # Persist individual attention signals
        await self._persist_attention_signals(
            db, organization_id, scope, scope_id, planning_context, 
            adaptive_context, attention_signals
        )
        
        # Persist replanning proposals
        await self._persist_replanning_proposals(
            db, organization_id, scope, scope_id, planning_context,
            adaptive_context, replanning_proposals
        )
        
        # Persist decision contexts
        await self._persist_decision_contexts(
            db, organization_id, scope, scope_id, planning_context,
            adaptive_context, decision_contexts
        )
        
        # Record state transition if there's a previous version
        if transition_from_context:
            await self._record_adaptive_transition(
                db, organization_id, scope, scope_id,
                transition_from_context, adaptive_context,
                trigger, source_event_id, trigger_reason,
                attention_signals, replanning_proposals, decision_contexts
            )
        elif cross_context_previous:
            # Cross-planning-context transition
            if cross_context_previous.version != adaptive_context.version:
                await self._record_adaptive_transition(
                    db, organization_id, scope, scope_id,
                    cross_context_previous, adaptive_context,
                    trigger, source_event_id, trigger_reason,
                    attention_signals, replanning_proposals, decision_contexts
                )
        
        return adaptive_context

    async def _get_latest_adaptive_context(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
        planning_context_id: str,
    ) -> Optional[AdaptivePlanningContext]:
        """Get the most recent adaptive planning context for the given scope and planning context."""
        stmt = select(AdaptivePlanningContext).where(
            AdaptivePlanningContext.organization_id == organization_id,
            AdaptivePlanningContext.scope == scope,
            AdaptivePlanningContext.scope_id == scope_id,
            AdaptivePlanningContext.planning_context_id == planning_context_id,
        ).order_by(AdaptivePlanningContext.version.desc()).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_latest_adaptive_context_for_scope(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
    ) -> Optional[AdaptivePlanningContext]:
        """Get the most recent adaptive planning context for the given scope (any planning context)."""
        stmt = select(AdaptivePlanningContext).where(
            AdaptivePlanningContext.organization_id == organization_id,
            AdaptivePlanningContext.scope == scope,
            AdaptivePlanningContext.scope_id == scope_id,
        ).order_by(AdaptivePlanningContext.computed_at.desc()).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # Attention Signal Detection
    # -------------------------------------------------------------------------

    async def _detect_attention_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
        planning_context: CompanyPlanningContext,
        adaptive_version: int = 1,
    ) -> list[dict]:
        """Detect attention signals from all sections of the planning context."""
        signals = []

        # 1. Strategic State Signals
        signals.extend(await self._detect_strategic_signals(
            db, organization_id, planning_context, adaptive_version
        ))

        # 2. Execution State Signals
        signals.extend(await self._detect_execution_signals(
            db, organization_id, planning_context, adaptive_version
        ))

        # 3. Outcome State Signals
        signals.extend(await self._detect_outcome_signals(
            db, organization_id, planning_context, adaptive_version
        ))

        # 4. Alignment State Signals
        signals.extend(await self._detect_alignment_signals(
            db, organization_id, planning_context, adaptive_version
        ))

        # 5. Learning State Signals
        signals.extend(await self._detect_learning_signals(
            db, organization_id, planning_context, adaptive_version
        ))

        # 6. Resource State Signals
        signals.extend(await self._detect_resource_signals(
            db, organization_id, planning_context, adaptive_version
        ))

        # 7. Risk State Signals
        signals.extend(await self._detect_risk_signals(
            db, organization_id, planning_context, adaptive_version
        ))

        # 8. Governance State Signals
        signals.extend(await self._detect_governance_signals(
            db, organization_id, planning_context, adaptive_version
        ))

        return signals

    async def _detect_strategic_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: CompanyPlanningContext,
        adaptive_version: int = 1,
    ) -> list[dict]:
        """Detect attention signals from strategic state."""
        signals = []
        strategic = planning_context.strategic_state.get("state", {})

        # At-risk objectives
        at_risk_objectives = strategic.get("at_risk_objectives", [])
        for obj in at_risk_objectives:
            signals.append(self._build_signal(
                signal_type="outcome_deviation",
                severity="warning",
                title=f"Objective at risk: {obj.get('title', 'Unknown')}",
                description=f"Objective {obj.get('id')} is in {obj.get('health', 'at_risk')} state",
                source_context_section="strategic",
                source_conclusion_key="at_risk_objectives",
                source_conclusion_value=obj,
                confidence=0.8,
                epistemic_status="observed",
                affected_entities=[{"type": "objective", "id": obj.get("id"), "role": "primary"}],
                adaptive_version=adaptive_version,
                intent_id=None,  # Would be populated from provenance
            ))

        # Superseded intents
        proposed_intents = strategic.get("proposed_intents_count", 0)
        if proposed_intents > 0:
            signals.append(self._build_signal(
                signal_type="governance_pending",
                severity="info",
                title=f"{proposed_intents} proposed intents awaiting governance",
                description="Proposed intents require governance adoption to become active",
                source_context_section="strategic",
                source_conclusion_key="proposed_intents_count",
                source_conclusion_value=proposed_intents,
                confidence=0.9,
                epistemic_status="observed",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))
        
        return signals

    async def _detect_execution_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: CompanyPlanningContext,
        adaptive_version: int = 1,
    ) -> list[dict]:
        """Detect attention signals from execution state."""
        signals = []
        execution = planning_context.execution_state.get("state", {})
        
# Blocking dependencies
        blocking_deps = execution.get("blocking_dependencies_count", 0)
        if blocking_deps > 0:
            signals.append(self._build_signal(
                signal_type="dependency_blocked",
                severity="critical",
                title=f"{blocking_deps} blocking dependencies detected",
                description="Hard dependencies are blocking initiative/project progress",
                source_context_section="execution",
                source_conclusion_key="blocking_dependencies_count",
                source_conclusion_value=blocking_deps,
                confidence=0.9,
                epistemic_status="observed",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))

        # Low initiative-project coverage - this is an alignment concern, detected in alignment section
        # coverage = execution.get("initiative_project_coverage", 1.0)
        # if coverage < 0.5:
        #     signals.append(self._build_signal(
        #         signal_type="alignment_breakdown",
        #         severity="warning",
        #         title=f"Low initiative-project coverage ({coverage:.0%})",
        #         description="Many initiatives lack linked projects for execution",
        #         source_context_section="alignment",
        #         source_conclusion_key="initiative_project_coverage",
        #         source_conclusion_value=coverage,
        #         confidence=0.8,
        #         epistemic_status="inferred",
        #         affected_entities=[],
        #     ))

        # Actions awaiting approval
        awaiting_approval = execution.get("awaiting_approval_actions_count", 0)
        if awaiting_approval > 0:
            signals.append(self._build_signal(
                signal_type="governance_pending",
                severity="info",
                title=f"{awaiting_approval} actions awaiting approval",
                description="Governance approval needed for actions to proceed",
                source_context_section="execution",
                source_conclusion_key="awaiting_approval_actions_count",
                source_conclusion_value=awaiting_approval,
                confidence=0.9,
                epistemic_status="observed",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))
        
        return signals

    async def _detect_outcome_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: CompanyPlanningContext,
        adaptive_version: int = 1,
    ) -> list[dict]:
        """Detect attention signals from outcome state."""
        signals = []
        outcome = planning_context.outcome_state.get("state", {})
        
# Underperforming outcomes
        underperforming = outcome.get("underperforming_outcomes", 0)
        if underperforming > 0:
            signals.append(self._build_signal(
                signal_type="outcome_deviation",
                severity="critical" if underperforming > 3 else "warning",
                title=f"{underperforming} outcomes underperforming",
                description="Measured outcomes significantly below expected targets",
                source_context_section="outcome",
                source_conclusion_key="underperforming_outcomes",
                source_conclusion_value=underperforming,
                confidence=0.85,
                epistemic_status="measured",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))

        # High variance outcomes
        avg_variance = outcome.get("average_variance_pct", 0)
        if abs(avg_variance) > 20:
            signals.append(self._build_signal(
                signal_type="outcome_deviation",
                severity="warning" if abs(avg_variance) < 50 else "critical",
                title=f"High outcome variance: {avg_variance:.1f}%",
                description="Average outcome variance indicates systemic estimation issues",
                source_context_section="outcome",
                source_conclusion_key="average_variance_pct",
                source_conclusion_value=avg_variance,
                confidence=0.8,
                epistemic_status="measured",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))
        
        return signals

    async def _detect_alignment_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: CompanyPlanningContext,
        adaptive_version: int = 1,
    ) -> list[dict]:
        """Detect attention signals from alignment state."""
        signals = []
        alignment = planning_context.alignment_state.get("state", {})
        
# Critical gaps
        critical_gaps = alignment.get("critical_gaps", 0)
        if critical_gaps > 0:
            signals.append(self._build_signal(
                signal_type="alignment_breakdown",
                severity="critical",
                title=f"{critical_gaps} critical alignment gaps",
                description="Strategic hierarchy has critical gaps requiring immediate attention",
                source_context_section="alignment",
                source_conclusion_key="critical_gaps",
                source_conclusion_value=critical_gaps,
                confidence=0.9,
                epistemic_status="evidence_backed",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))

        # Active conflicts
        active_conflicts = alignment.get("active_conflicts", 0)
        if active_conflicts > 0:
            signals.append(self._build_signal(
                signal_type="alignment_breakdown",
                severity="critical",
                title=f"{active_conflicts} active strategic conflicts",
                description="Conflicting strategic elements require governance resolution",
                source_context_section="alignment",
                source_conclusion_key="active_conflicts",
                source_conclusion_value=active_conflicts,
                confidence=0.9,
                epistemic_status="contested",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))

        # Low alignment score
        avg_score = alignment.get("average_alignment_score", 1.0)
        if avg_score < 0.6:
            signals.append(self._build_signal(
                signal_type="alignment_breakdown",
                severity="warning",
                title=f"Low strategic alignment score: {avg_score:.0%}",
                description="Significant portions of execution not aligned with strategy",
                source_context_section="alignment",
                source_conclusion_key="average_alignment_score",
                source_conclusion_value=avg_score,
                confidence=0.85,
                epistemic_status="evidence_backed",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))
        
        return signals

    async def _detect_learning_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: CompanyPlanningContext,
        adaptive_version: int = 1,
    ) -> list[dict]:
        """Detect attention signals from learning state."""
        signals = []
        learning = planning_context.learning_state.get("state", {})
        
# Open contradictions
        open_contradictions = learning.get("open_contradictions_count", 0)
        if open_contradictions > 0:
            signals.append(self._build_signal(
                signal_type="contradiction_surfaced",
                severity="critical",
                title=f"{open_contradictions} open contradictions",
                description="Contradictions between evidence and expectations require resolution",
                source_context_section="learning",
                source_conclusion_key="open_contradictions_count",
                source_conclusion_value=open_contradictions,
                confidence=0.9,
                epistemic_status="contested",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))

        # High-confidence lessons relevant to current plans
        high_conf_lessons = learning.get("high_confidence_lessons_count", 0)
        if high_conf_lessons > 0:
            # Check if any lessons invalidate current plan assumptions
            signals.append(self._build_signal(
                signal_type="lesson_invalidation",
                severity="info",
                title=f"{high_conf_lessons} high-confidence institutional lessons available",
                description="New institutional learning may inform current planning",
                source_context_section="learning",
                source_conclusion_key="high_confidence_lessons_count",
                source_conclusion_value=high_conf_lessons,
                confidence=0.8,
                epistemic_status="institutional_lesson",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))

        # Emerging patterns
        emerging = learning.get("emerging_patterns_count", 0)
        if emerging > 0:
            signals.append(self._build_signal(
                signal_type="lesson_invalidation",
                severity="info",
                title=f"{emerging} emerging patterns detected",
                description="New organizational patterns may indicate systematic issues or opportunities",
                source_context_section="learning",
                source_conclusion_key="emerging_patterns_count",
                source_conclusion_value=emerging,
                confidence=0.7,
                epistemic_status="inferred",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))
        
        return signals

    async def _detect_resource_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: CompanyPlanningContext,
        adaptive_version: int = 1,
    ) -> list[dict]:
        """Detect attention signals from resource state."""
        signals = []
        resource = planning_context.resource_state.get("state", {})
        
# Overloaded assignees
        overloaded = resource.get("overloaded_assignees", 0)
        if overloaded > 0:
            signals.append(self._build_signal(
                signal_type="resource_contention",
                severity="warning",
                title=f"{overloaded} assignees overloaded",
                description="Resource capacity exceeded for active actions",
                source_context_section="resource",
                source_conclusion_key="overloaded_assignees",
                source_conclusion_value=overloaded,
                confidence=0.75,
                epistemic_status="inferred",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))

        # Low allocation efficiency
        efficiency = resource.get("allocation_efficiency", 1.0)
        if efficiency < 0.7:
            signals.append(self._build_signal(
                signal_type="resource_contention",
                severity="warning",
                title=f"Low resource allocation efficiency: {efficiency:.0%}",
                description="Resource allocation may be suboptimal for current priorities",
                source_context_section="resource",
                source_conclusion_key="allocation_efficiency",
                source_conclusion_value=efficiency,
                confidence=0.7,
                epistemic_status="inferred",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))
        
        return signals

    async def _detect_risk_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: CompanyPlanningContext,
        adaptive_version: int = 1,
    ) -> list[dict]:
        """Detect attention signals from risk state."""
        signals = []
        risk = planning_context.risk_state.get("state", {})
        
# Elevated risks
        elevated = risk.get("total_risks", 0)
        if elevated > 5:
            signals.append(self._build_signal(
                signal_type="risk_elevation",
                severity="critical" if elevated > 10 else "warning",
                title=f"{elevated} elevated risks detected",
                description="Multiple risk signals across strategic, execution, and outcome dimensions",
                source_context_section="risk",
                source_conclusion_key="total_risks",
                source_conclusion_value=elevated,
                confidence=0.8,
                epistemic_status="inferred",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))

        # Newly emerging risks from patterns
        emerging = risk.get("newly_emerging_from_patterns", 0)
        if emerging > 0:
            signals.append(self._build_signal(
                signal_type="risk_elevation",
                severity="warning",
                title=f"{emerging} newly emerging risks from historical patterns",
                description="Institutional patterns indicate new risk vectors",
                source_context_section="risk",
                source_conclusion_key="newly_emerging_from_patterns",
                source_conclusion_value=emerging,
                confidence=0.8,
                epistemic_status="institutional_lesson",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))
        
        return signals

    async def _detect_governance_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        planning_context: CompanyPlanningContext,
        adaptive_version: int = 1,
    ) -> list[dict]:
        """Detect attention signals from governance state."""
        signals = []
        governance = planning_context.governance_state.get("state", {})
        
# Pending decisions
        pending = governance.get("pending_decisions_count", 0)
        if pending > 0:
            signals.append(self._build_signal(
                signal_type="governance_pending",
                severity="info" if pending < 3 else "warning",
                title=f"{pending} decisions pending governance",
                description="Governance decisions required to unblock execution",
                source_context_section="governance",
                source_conclusion_key="pending_decisions_count",
                source_conclusion_value=pending,
                confidence=0.9,
                epistemic_status="observed",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))

        # Decisions awaiting outcome
        awaiting = governance.get("decisions_awaiting_outcome", 0)
        if awaiting > 0:
            signals.append(self._build_signal(
                signal_type="governance_pending",
                severity="info",
                title=f"{awaiting} decisions awaiting outcome recording",
                description="Executed decisions need outcome recording to close the learning loop",
                source_context_section="governance",
                source_conclusion_key="decisions_awaiting_outcome",
                source_conclusion_value=awaiting,
                confidence=0.9,
                epistemic_status="observed",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))

        # Governance contradictions
        gov_contras = governance.get("open_governance_contradictions", 0)
        if gov_contras > 0:
            signals.append(self._build_signal(
                signal_type="contradiction_surfaced",
                severity="critical",
                title=f"{gov_contras} open governance contradictions",
                description="Contradictions in decision evidence require human resolution",
                source_context_section="governance",
                source_conclusion_key="open_governance_contradictions",
                source_conclusion_value=gov_contras,
                confidence=0.9,
                epistemic_status="contested",
                affected_entities=[],
                adaptive_version=adaptive_version,
            ))
        
        return signals

    def _build_signal(
        self,
        signal_type: str,
        severity: str,
        title: str,
        description: str,
        source_context_section: str,
        source_conclusion_key: str,
        source_conclusion_value: Any,
        confidence: float,
        epistemic_status: str,
        affected_entities: list[dict],
        adaptive_version: int = 1,
        intent_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        objective_id: Optional[str] = None,
        initiative_id: Optional[str] = None,
        project_id: Optional[str] = None,
        plan_id: Optional[str] = None,
    ) -> dict:
        """Build a standardized attention signal dict."""
        fingerprint_data = f"{signal_type}:{source_context_section}:{source_conclusion_key}:{title}:v{adaptive_version}"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        return {
            "id": f"att_{fingerprint[:16]}",
            "type": signal_type,
            "severity": severity,
            "title": title,
            "description": description,
            "source_context_section": source_context_section,
            "source_conclusion_key": source_conclusion_key,
            "source_conclusion_value": source_conclusion_value,
            "confidence": confidence,
            "epistemic_status": epistemic_status,
            "affected_entities": affected_entities,
            "intent_id": intent_id,
            "goal_id": goal_id,
            "objective_id": objective_id,
            "initiative_id": initiative_id,
            "project_id": project_id,
            "plan_id": plan_id,
            "fingerprint": fingerprint,
            "status": "active",
        }

    # -------------------------------------------------------------------------
    # Replanning Proposal Generation
    # -------------------------------------------------------------------------

    async def _generate_replanning_proposals(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
        planning_context: CompanyPlanningContext,
        attention_signals: list[dict],
        adaptive_version: int = 1,
    ) -> list[dict]:
        """Generate replanning proposals from attention signals."""
        proposals = []
        
        # Group signals by type to generate targeted proposals
        signals_by_type = {}
        for signal in attention_signals:
            sig_type = signal.get("type")
            if sig_type not in signals_by_type:
                signals_by_type[sig_type] = []
            signals_by_type[sig_type].append(signal)
        
# Generate proposals based on signal patterns
        if "outcome_deviation" in signals_by_type:
            proposals.append(self._build_proposal(
                proposal_type="timeline_adjustment",
                title="Adjust timelines for underperforming outcomes",
                description="Extend timelines or adjust scope for objectives with significant outcome deviations",
                trigger_signal_ids=[s["id"] for s in signals_by_type["outcome_deviation"]],
                adaptive_version=adaptive_version,
                affected_objective_ids=[e["id"] for s in signals_by_type["outcome_deviation"]
                                       for e in s.get("affected_entities", []) if e.get("type") == "objective"],
                proposed_changes={"timeline": {"adjustment": "extend", "reason": "outcome_deviation"}},
                impact_assessment={"timeline_impact_days": 30},
                confidence=0.75,
            ))

        if "alignment_breakdown" in signals_by_type:
            proposals.append(self._build_proposal(
                proposal_type="priority_shift",
                title="Re-prioritize initiatives to restore alignment",
                description="Shift priority to initiatives with strongest strategic alignment",
                trigger_signal_ids=[s["id"] for s in signals_by_type["alignment_breakdown"]],
                adaptive_version=adaptive_version,
                proposed_changes={"priority": {"adjustment": "realign", "reason": "alignment_breakdown"}},
                impact_assessment={"strategic": "improved_alignment"},
                confidence=0.8,
            ))

        if "dependency_blocked" in signals_by_type:
            proposals.append(self._build_proposal(
                proposal_type="dependency_reroute",
                title="Resolve blocking dependencies",
                description="Reroute or resolve hard dependencies blocking critical path",
                trigger_signal_ids=[s["id"] for s in signals_by_type["dependency_blocked"]],
                adaptive_version=adaptive_version,
                proposed_changes={"dependencies": {"adjustment": "reroute", "reason": "dependency_blocked"}},
                impact_assessment={"execution": "unblocked_progress"},
                confidence=0.85,
            ))

        if "resource_contention" in signals_by_type:
            proposals.append(self._build_proposal(
                proposal_type="resource_reallocation",
                title="Reallocate resources to resolve contention",
                description="Move resources from lower-priority to blocked/high-priority work",
                trigger_signal_ids=[s["id"] for s in signals_by_type["resource_contention"]],
                adaptive_version=adaptive_version,
                proposed_changes={"resources": {"adjustment": "reallocate", "reason": "resource_contention"}},
                impact_assessment={"resource": "improved_allocation"},
                confidence=0.8,
            ))

        if "contradiction_surfaced" in signals_by_type:
            proposals.append(self._build_proposal(
                proposal_type="scope_reduction",
                title="Reduce scope to resolve contradictions",
                description="Reduce scope in areas with unresolved contradictions until resolved",
                trigger_signal_ids=[s["id"] for s in signals_by_type["contradiction_surfaced"]],
                adaptive_version=adaptive_version,
                proposed_changes={"scope": {"adjustment": "reduce", "reason": "contradiction_surfaced"}},
                impact_assessment={"risk": "reduced_exposure"},
                confidence=0.7,
            ))

        if "risk_elevation" in signals_by_type:
            proposals.append(self._build_proposal(
                proposal_type="risk_mitigation",
                title="Implement risk mitigation actions",
                description="Execute approved mitigation actions for elevated risks",
                trigger_signal_ids=[s["id"] for s in signals_by_type["risk_elevation"]],
                adaptive_version=adaptive_version,
                proposed_changes={"risk": {"adjustment": "mitigate", "reason": "risk_elevation"}},
                impact_assessment={"risk": "reduced_exposure"},
                confidence=0.8,
            ))

        if "governance_pending" in signals_by_type:
            proposals.append(self._build_proposal(
                proposal_type="scope_authorization",
                title="Governance authorization for pending decisions",
                description="Expedite governance review for pending decisions blocking execution",
                trigger_signal_ids=[s["id"] for s in signals_by_type["governance_pending"]],
                adaptive_version=adaptive_version,
                proposed_changes={},
                impact_assessment={"execution": "unblocked"},
                confidence=0.9,
            ))
        
        return proposals

    def _build_proposal(
        self,
        proposal_type: str,
        title: str,
        description: str,
        trigger_signal_ids: list[str],
        adaptive_version: int = 1,
        affected_intent_ids: Optional[list[str]] = None,
        affected_plan_ids: Optional[list[str]] = None,
        affected_objective_ids: Optional[list[str]] = None,
        affected_initiative_ids: Optional[list[str]] = None,
        proposed_changes: Optional[dict] = None,
        impact_assessment: Optional[dict] = None,
        confidence: float = 0.7,
    ) -> dict:
        """Build a standardized replanning proposal dict."""
        fingerprint_data = f"{proposal_type}:{title}:{':'.join(trigger_signal_ids)}:v{adaptive_version}"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        return {
            "id": f"rpp_{fingerprint[:16]}",
            "type": proposal_type,
            "title": title,
            "description": description,
            "trigger_attention_signal_ids": trigger_signal_ids,
            "affected_intent_ids": affected_intent_ids or [],
            "affected_plan_ids": affected_plan_ids or [],
            "affected_objective_ids": affected_objective_ids or [],
            "affected_initiative_ids": affected_initiative_ids or [],
            "proposed_changes": proposed_changes or {},
            "impact_assessment": impact_assessment or {},
            "confidence": confidence,
            "status": "proposed",
            "fingerprint": fingerprint,
        }

    # -------------------------------------------------------------------------
    # Decision Context Generation
    # -------------------------------------------------------------------------

    async def _generate_decision_contexts(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
        planning_context: CompanyPlanningContext,
        attention_signals: list[dict],
        replanning_proposals: list[dict],
        adaptive_version: int = 1,
    ) -> list[dict]:
        """Generate decision contexts from attention signals and proposals."""
        decisions = []
        
# Decision for each replanning proposal
        for proposal in replanning_proposals:
            decisions.append(self._build_decision_context(
                decision_type="replanning_approval",
                title=f"Approve replanning: {proposal['title']}",
                description=f"Governance approval required for: {proposal['description']}",
                context={"proposal": proposal},
                options=[
                    {"id": "approve", "title": "Approve", "description": "Approve and execute the proposed adaptation", "impact": proposal.get("impact_assessment", {}), "confidence": proposal.get("confidence", 0.7)},
                    {"id": "reject", "title": "Reject", "description": "Reject the proposal; current plan continues", "impact": {}, "confidence": 0.5},
                    {"id": "modify", "title": "Modify", "description": "Request modifications before approval", "impact": {}, "confidence": 0.5},
                ],
                recommendation="approve",
                recommendation_confidence=proposal.get("confidence", 0.7),
                recommendation_reasoning=f"Proposed to address: {', '.join(proposal['trigger_attention_signal_ids'])}",
                replanning_proposal_id=proposal.get("id"),
                attention_signal_ids=proposal.get("trigger_attention_signal_ids", []),
                adaptive_version=adaptive_version,
            ))

        # Decisions for critical attention signals
        critical_signals = [s for s in attention_signals if s.get("severity") in ("critical", "urgent")]
        for signal in critical_signals:
            decisions.append(self._build_decision_context(
                decision_type="attention_response",
                title=f"Respond to: {signal['title']}",
                description=f"Critical attention signal requires governance response: {signal['description']}",
                context={"signal": signal},
                options=[
                    {"id": "acknowledge", "title": "Acknowledge", "description": "Acknowledge signal; no immediate action", "impact": {}, "confidence": 0.5},
                    {"id": "investigate", "title": "Investigate", "description": "Commission investigation before action", "impact": {}, "confidence": 0.7},
                    {"id": "act", "title": "Take Action", "description": "Authorize immediate adaptive action", "impact": {}, "confidence": 0.8},
                ],
                recommendation="investigate",
                recommendation_confidence=0.7,
                recommendation_reasoning=f"Critical signal {signal['type']} requires informed response",
                attention_signal_ids=[signal["id"]],
                adaptive_version=adaptive_version,
            ))
        
        return decisions

    def _build_decision_context(
        self,
        decision_type: str,
        title: str,
        description: str,
        context: dict,
        options: list[dict],
        recommendation: Optional[str],
        recommendation_confidence: float,
        recommendation_reasoning: str,
        adaptive_version: int = 1,
        replanning_proposal_id: Optional[str] = None,
        attention_signal_ids: Optional[list[str]] = None,
    ) -> dict:
        """Build a standardized decision context dict."""
        fingerprint_data = f"{decision_type}:{title}:{recommendation}:v{adaptive_version}"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        return {
            "id": f"dcc_{fingerprint[:16]}",
            "type": decision_type,
            "title": title,
            "description": description,
            "context": context,
            "options": options,
            "recommendation": recommendation,
            "recommendation_confidence": recommendation_confidence,
            "recommendation_reasoning": recommendation_reasoning,
            "replanning_proposal_id": replanning_proposal_id,
            "attention_signal_ids": attention_signal_ids or [],
            "status": "draft",
            "requires_approval": True,
            "fingerprint": fingerprint,
        }

    # -------------------------------------------------------------------------
    # Persistence Methods
    # -------------------------------------------------------------------------

    async def _persist_attention_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
        planning_context: CompanyPlanningContext,
        adaptive_context: AdaptivePlanningContext,
        signals: list[dict],
    ) -> None:
        """Persist individual attention signals with exact-once semantics."""
        for signal in signals:
            # Check if signal already exists (exact-once replay protection)
            existing_stmt = select(AttentionSignal).where(
                AttentionSignal.organization_id == organization_id,
                AttentionSignal.planning_context_id == planning_context.id,
                AttentionSignal.source_context_section == signal["source_context_section"],
                AttentionSignal.source_conclusion_key == signal["source_conclusion_key"],
                AttentionSignal.fingerprint == signal["fingerprint"],
            )
            existing_result = await db.execute(existing_stmt)
            existing = existing_result.scalar_one_or_none()
            
            if existing:
                # Signal already exists, update adaptive_context_id if needed
                if existing.adaptive_context_id != adaptive_context.id:
                    existing.adaptive_context_id = adaptive_context.id
                continue
            
            # Build provenance
            evidence_fps = []
            pattern_ids = []
            lesson_fps = []
            contra_ids = []
            
            # Extract from planning context provenance
            for prov in planning_context.strategic_state.get("provenance", []) + \
                         planning_context.execution_state.get("provenance", []) + \
                         planning_context.outcome_state.get("provenance", []) + \
                         planning_context.alignment_state.get("provenance", []) + \
                         planning_context.learning_state.get("provenance", []) + \
                         planning_context.resource_state.get("provenance", []) + \
                         planning_context.risk_state.get("provenance", []) + \
                         planning_context.governance_state.get("provenance", []):
                if prov.get("type") == "organizational_learning":
                    lesson_fps.extend(prov.get("ids", []))
                elif prov.get("type") == "pattern_detection":
                    pattern_ids.extend(prov.get("ids", []))
                elif "contradiction" in prov.get("type", ""):
                    contra_ids.extend(prov.get("ids", []))
                elif prov.get("type") in ("objective_outcome", "objective_outcome_assessment"):
                    evidence_fps.extend(prov.get("ids", []))
            
            # Serialize source_conclusion_value to string for Text column
            source_conclusion_value = signal["source_conclusion_value"]
            if source_conclusion_value is not None and not isinstance(source_conclusion_value, str):
                source_conclusion_value = json.dumps(source_conclusion_value)
            
            att_signal = AttentionSignal(
                organization_id=organization_id,
                scope=scope,
                scope_id=scope_id,
                planning_context_id=planning_context.id,
                adaptive_context_id=adaptive_context.id,
                signal_type=signal["type"],
                severity=signal["severity"],
                title=signal["title"],
                description=signal["description"],
                source_context_section=signal["source_context_section"],
                source_conclusion_key=signal["source_conclusion_key"],
                source_conclusion_value=source_conclusion_value,
                confidence=signal["confidence"],
                epistemic_status=signal["epistemic_status"],
                affected_entities=signal["affected_entities"],
                evidence_fingerprints=evidence_fps,
                pattern_ids=pattern_ids,
                lesson_fingerprints=lesson_fps,
                contradiction_ids=contra_ids,
                intent_id=signal.get("intent_id"),
                goal_id=signal.get("goal_id"),
                objective_id=signal.get("objective_id"),
                initiative_id=signal.get("initiative_id"),
                project_id=signal.get("project_id"),
                plan_id=signal.get("plan_id"),
                fingerprint=signal["fingerprint"],
            )
            db.add(att_signal)
        
        await db.flush()

    async def _persist_replanning_proposals(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
        planning_context: CompanyPlanningContext,
        adaptive_context: AdaptivePlanningContext,
        proposals: list[dict],
    ) -> None:
        """Persist replanning proposals with exact-once semantics."""
        for proposal in proposals:
            # Check if proposal already exists (exact-once replay protection)
            existing_stmt = select(ReplanningProposal).where(
                ReplanningProposal.organization_id == organization_id,
                ReplanningProposal.planning_context_id == planning_context.id,
                ReplanningProposal.proposal_type == proposal["type"],
                ReplanningProposal.fingerprint == proposal["fingerprint"],
            )
            existing_result = await db.execute(existing_stmt)
            existing = existing_result.scalar_one_or_none()
            
            if existing:
                # Proposal already exists, update adaptive_context_id if needed
                if existing.adaptive_context_id != adaptive_context.id:
                    existing.adaptive_context_id = adaptive_context.id
                continue
            
            rpp = ReplanningProposal(
                organization_id=organization_id,
                scope=scope,
                scope_id=scope_id,
                planning_context_id=planning_context.id,
                adaptive_context_id=adaptive_context.id,
                proposal_type=proposal["type"],
                title=proposal["title"],
                description=proposal["description"],
                trigger_attention_signal_ids=proposal["trigger_attention_signal_ids"],
                affected_intent_ids=proposal.get("affected_intent_ids", []),
                affected_plan_ids=proposal.get("affected_plan_ids", []),
                affected_objective_ids=proposal.get("affected_objective_ids", []),
                affected_initiative_ids=proposal.get("affected_initiative_ids", []),
                proposed_changes=proposal.get("proposed_changes", {}),
                impact_assessment=proposal.get("impact_assessment", {}),
                status=proposal.get("status", "proposed"),
                proposed_by="adaptive_planning_engine",
                proposed_at=utcnow(),
                fingerprint=proposal["fingerprint"],
            )
            db.add(rpp)
        
        await db.flush()

    async def _persist_decision_contexts(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
        planning_context: CompanyPlanningContext,
        adaptive_context: AdaptivePlanningContext,
        decisions: list[dict],
    ) -> None:
        """Persist decision contexts with exact-once semantics."""
        for decision in decisions:
            # Check if decision already exists (exact-once replay protection)
            existing_stmt = select(DecisionContext).where(
                DecisionContext.organization_id == organization_id,
                DecisionContext.planning_context_id == planning_context.id,
                DecisionContext.decision_type == decision["type"],
                DecisionContext.fingerprint == decision["fingerprint"],
            )
            existing_result = await db.execute(existing_stmt)
            existing = existing_result.scalar_one_or_none()
            
            if existing:
                # Decision already exists, update adaptive_context_id if needed
                if existing.adaptive_context_id != adaptive_context.id:
                    existing.adaptive_context_id = adaptive_context.id
                continue
            
            dcc = DecisionContext(
                organization_id=organization_id,
                scope=scope,
                scope_id=scope_id,
                planning_context_id=planning_context.id,
                adaptive_context_id=adaptive_context.id,
                replanning_proposal_id=decision.get("replanning_proposal_id"),
                attention_signal_ids=decision.get("attention_signal_ids", []),
                decision_type=decision["type"],
                title=decision["title"],
                description=decision["description"],
                context=decision["context"],
                options=decision["options"],
                recommendation=decision.get("recommendation"),
                recommendation_confidence=decision.get("recommendation_confidence", 0.5),
                recommendation_reasoning=decision.get("recommendation_reasoning"),
                status=decision.get("status", "draft"),
                requires_approval=decision.get("requires_approval", True),
                fingerprint=decision["fingerprint"],
            )
            db.add(dcc)
        
        await db.flush()
        
        await db.flush()

    # -------------------------------------------------------------------------
    # State Transition Recording
    # -------------------------------------------------------------------------

    async def _record_adaptive_transition(
        self,
        db: AsyncSession,
        organization_id: str,
        scope: str,
        scope_id: Optional[str],
        from_context: AdaptivePlanningContext,
        to_context: AdaptivePlanningContext,
        trigger: str,
        trigger_event_id: Optional[str],
        trigger_reason: Optional[str],
        new_signals: list[dict],
        new_proposals: list[dict],
        new_decisions: list[dict],
    ) -> AdaptivePlanningTransition:
        """Record an adaptive planning context state transition."""
        
        # Compute delta
        delta = self._compute_adaptive_delta(from_context, to_context)
        changed_sections = list(delta.keys())
        
        # Track signal changes
        from_signal_ids = {s["id"] for s in from_context.attention_signals}
        to_signal_ids = {s["id"] for s in to_context.attention_signals}
        new_signal_ids = to_signal_ids - from_signal_ids
        resolved_signal_ids = from_signal_ids - to_signal_ids
        
        # Track proposal changes
        from_proposal_ids = {p["id"] for p in from_context.replanning_proposals}
        to_proposal_ids = {p["id"] for p in to_context.replanning_proposals}
        new_proposal_ids = to_proposal_ids - from_proposal_ids
        updated_proposal_ids = from_proposal_ids & to_proposal_ids
        
        # Track decision changes
        from_decision_ids = {d["id"] for d in from_context.decision_contexts}
        to_decision_ids = {d["id"] for d in to_context.decision_contexts}
        new_decision_ids = to_decision_ids - from_decision_ids
        updated_decision_ids = from_decision_ids & to_decision_ids
        
        transition = AdaptivePlanningTransition(
            organization_id=organization_id,
            scope=scope,
            scope_id=scope_id,
            from_version=from_context.version,
            to_version=to_context.version,
            from_context_id=from_context.id,
            to_context_id=to_context.id,
            trigger=trigger,
            trigger_event_id=trigger_event_id,
            trigger_reason=trigger_reason or f"Adaptive context recomputed via {trigger}",
            delta=delta,
            changed_sections=changed_sections,
            new_attention_signals=list(new_signal_ids),
            resolved_attention_signals=list(resolved_signal_ids),
            escalated_attention_signals=[],
            new_proposals=list(new_proposal_ids),
            updated_proposals=list(updated_proposal_ids),
            new_decisions=list(new_decision_ids),
            updated_decisions=list(updated_decision_ids),
            source_event_id=trigger_event_id,
            computed_by="adaptive_planning_engine",
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

    def _compute_adaptive_delta(
        self,
        from_context: AdaptivePlanningContext,
        to_context: AdaptivePlanningContext,
    ) -> dict:
        """Compute detailed delta between two adaptive context versions."""
        sections = ["attention_signals", "replanning_proposals", "decision_contexts"]
        
        delta = {}
        for section in sections:
            from_items = getattr(from_context, section, []) or []
            to_items = getattr(to_context, section, []) or []
            
            from_ids = {item["id"]: item for item in from_items}
            to_ids = {item["id"]: item for item in to_items}
            
            all_ids = set(from_ids.keys()) | set(to_ids.keys())
            section_delta = {}
            
            for item_id in all_ids:
                from_item = from_ids.get(item_id)
                to_item = to_ids.get(item_id)
                
                if from_item is None:
                    section_delta[item_id] = {"action": "added", "to": to_item}
                elif to_item is None:
                    section_delta[item_id] = {"action": "removed", "from": from_item}
                elif from_item != to_item:
                    section_delta[item_id] = {"action": "modified", "from": from_item, "to": to_item}
            
            if section_delta:
                delta[section] = section_delta
        
        return delta

    def _compute_adaptive_health(
        self,
        attention_signals: list[dict],
        replanning_proposals: list[dict],
        decision_contexts: list[dict],
    ) -> str:
        """Compute overall adaptive health."""
        critical_signals = sum(1 for s in attention_signals if s.get("severity") in ("critical", "urgent"))
        warning_signals = sum(1 for s in attention_signals if s.get("severity") == "warning")
        pending_proposals = sum(1 for p in replanning_proposals if p.get("status") in ("proposed", "under_review"))
        pending_decisions = sum(1 for d in decision_contexts if d.get("status") in ("draft", "proposed", "evaluated", "recommended"))
        
        if critical_signals > 0 or pending_proposals > 5:
            return "critical"
        elif warning_signals > 0 or pending_proposals > 0 or pending_decisions > 3:
            return "attention_needed"
        elif len(attention_signals) > 0:
            return "attention_needed"
        else:
            return "stable"

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    async def get_adaptive_context(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        planning_context_id: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Optional[AdaptivePlanningContext]:
        """Get an adaptive planning context."""
        conditions = [
            AdaptivePlanningContext.organization_id == organization_id,
            AdaptivePlanningContext.scope == scope,
            AdaptivePlanningContext.scope_id == scope_id,
        ]
        if planning_context_id:
            conditions.append(AdaptivePlanningContext.planning_context_id == planning_context_id)
        if version:
            conditions.append(AdaptivePlanningContext.version == version)
        
        stmt = select(AdaptivePlanningContext).where(and_(*conditions))
        if not version and not planning_context_id:
            stmt = stmt.order_by(AdaptivePlanningContext.version.desc()).limit(1)
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_attention_signals(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        signal_type: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[AttentionSignal]:
        """Get attention signals."""
        conditions = [
            AttentionSignal.organization_id == organization_id,
            AttentionSignal.scope == scope,
            AttentionSignal.scope_id == scope_id,
        ]
        if signal_type:
            conditions.append(AttentionSignal.signal_type == signal_type)
        if severity:
            conditions.append(AttentionSignal.severity == severity)
        if status:
            conditions.append(AttentionSignal.status == status)
        
        stmt = select(AttentionSignal).where(and_(*conditions)).order_by(
            AttentionSignal.created_at.desc()
        ).limit(limit)
        
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_replanning_proposals(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        proposal_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[ReplanningProposal]:
        """Get replanning proposals."""
        conditions = [
            ReplanningProposal.organization_id == organization_id,
            ReplanningProposal.scope == scope,
            ReplanningProposal.scope_id == scope_id,
        ]
        if proposal_type:
            conditions.append(ReplanningProposal.proposal_type == proposal_type)
        if status:
            conditions.append(ReplanningProposal.status == status)
        
        stmt = select(ReplanningProposal).where(and_(*conditions)).order_by(
            ReplanningProposal.created_at.desc()
        ).limit(limit)
        
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_decision_contexts(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        decision_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[DecisionContext]:
        """Get decision contexts."""
        conditions = [
            DecisionContext.organization_id == organization_id,
            DecisionContext.scope == scope,
            DecisionContext.scope_id == scope_id,
        ]
        if decision_type:
            conditions.append(DecisionContext.decision_type == decision_type)
        if status:
            conditions.append(DecisionContext.status == status)
        
        stmt = select(DecisionContext).where(and_(*conditions)).order_by(
            DecisionContext.created_at.desc()
        ).limit(limit)
        
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_adaptive_transitions(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        from_version: Optional[int] = None,
        to_version: Optional[int] = None,
        limit: int = 50,
    ) -> list[AdaptivePlanningTransition]:
        """Get adaptive planning transition history."""
        conditions = [
            AdaptivePlanningTransition.organization_id == organization_id,
            AdaptivePlanningTransition.scope == scope,
            AdaptivePlanningTransition.scope_id == scope_id,
        ]
        if from_version:
            conditions.append(AdaptivePlanningTransition.from_version == from_version)
        if to_version:
            conditions.append(AdaptivePlanningTransition.to_version == to_version)
        
        stmt = select(AdaptivePlanningTransition).where(and_(*conditions)).order_by(
            AdaptivePlanningTransition.transitioned_at.desc()
        ).limit(limit)
        
        result = await db.execute(stmt)
        return result.scalars().all()

    # -------------------------------------------------------------------------
    # Integration with CompanyBrain
    # -------------------------------------------------------------------------

    async def answer_adaptive_question(
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
        Answer an adaptive planning question using the synthesized adaptive context.
        
        This integrates with CompanyBrain's governance-first retrieval.
        """
        # Get or synthesize current planning context
        planning_context = await company_planning_context_engine.get_planning_context(
            db, organization_id, scope=scope, scope_id=scope_id
        )
        if not planning_context:
            planning_context = await company_planning_context_engine.synthesize_planning_context(
                db, organization_id, scope=scope, scope_id=scope_id
            )
        
        # Get or synthesize adaptive context
        adaptive_context = await self.get_adaptive_context(
            db, organization_id, scope=scope, scope_id=scope_id,
            planning_context_id=planning_context.id
        )
        if not adaptive_context:
            adaptive_context = await self.synthesize_adaptive_context(
                db, organization_id, scope=scope, scope_id=scope_id,
                planning_context=planning_context
            )
        
        # Build structured answer
        answer = {
            "question": question,
            "planning_context_version": planning_context.version,
            "adaptive_context_version": adaptive_context.version,
            "overall_adaptive_health": adaptive_context.overall_adaptive_health,
            "attention_signals": adaptive_context.attention_signals,
            "replanning_proposals": adaptive_context.replanning_proposals,
            "decision_contexts": adaptive_context.decision_contexts,
            "attention_count": adaptive_context.attention_count,
            "critical_attention_count": adaptive_context.critical_attention_count,
            "pending_proposals_count": adaptive_context.pending_proposals_count,
            "pending_decisions_count": adaptive_context.pending_decisions_count,
            "provenance_available": True,
        }
        
        return answer


adaptive_planning_engine = AdaptivePlanningEngine()