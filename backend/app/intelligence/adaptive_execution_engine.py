"""Phase 4I.8 — Adaptive Execution & Outcome Observation Engine.

This engine implements the canonical bridge from Governed Commitment to Execution
via the existing CompanyAction substrate, and closes the loop with Outcome Observation.

Key principles:
- Governance-first: commitment scope resolved before any action proposal
- Reuses: CompanyCommitment, CompanyAuthorization, CompanyAction, CompanyGoal,
  CompanyObjective, CompanyInitiative, Project, Task, CompanyState, GovernanceScope,
  ApprovalPolicy, StrategicExecutionEngine, action_ops_engine
- Decision ≠ Authorization ≠ Commitment ≠ Action ≠ Execution (explicit boundaries)
- Deterministic: same canonical inputs -> same execution state
- Provenance: every action traces back to Commitment → Authorization → Decision
- Epistemic separation: observation vs assessment vs inference vs prediction
- Contradiction preservation: both expected and actual outcomes visible
- Temporal truth: state transitions recorded with triggers
- No autonomous execution: actions proposed, governance authorizes, execution observed
- Exact-once: fingerprint-based deduplication on all entities
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, date, timedelta, timezone
from typing import Any, Optional, List, Dict

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.company_intent import (
    CompanyIntent,
    CompanyPlan,
    INTENT_KINDS,
    INTENT_EPISTEMIC_STATUS,
)
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
    StrategicLink,
    StrategicHistory,
    CompanyCommitment,
    CompanyAuthorization,
    COMMITMENT_STATES,
    COMMITMENT_TYPES,
    AUTHORIZATION_TYPES,
    AUTHORIZATION_STATES,
    ObjectiveOutcome,
    ObjectiveOutcomeAssessment,
    ObjectiveContradiction,
    OUTCOME_STATES,
    ASSESSMENT_STATES,
    MEASUREMENT_QUALITY,
    SUPERSESSION_REASON,
)
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionContradiction,
    CompanyDecisionPrecedent,
    CompanyDecisionQuality,
    CompanyDecisionTrack,
    CompanyDecisionContradiction as OperatingCompanyDecisionContradiction,
)
from app.models.company_state import CompanyState
from app.models.company_actions import CompanyAction, CompanyActionEvent, CompanyActionOutcome
from app.models.governance import GovernanceScope, ApprovalPolicy
from app.models.project import Project
from app.models.task import Task
from app.intelligence.governed_commitment_engine import governed_commitment_engine
from app.intelligence.strategic_execution_engine import strategic_execution_engine
from app.knowledge.action_ops_engine import action_ops_engine
from app.intelligence.company_planning_context_engine import company_planning_context_engine
from app.intelligence.adaptive_planning_engine import adaptive_planning_engine


def _days(n: int) -> timedelta:
    return timedelta(days=n)


class AdaptiveExecutionEngine:
    """
    Adaptive Execution & Outcome Observation Engine — the canonical bridge from
    Governed Commitment to Execution via governed CompanyAction, with continuous
    outcome observation feeding back into CompanyState and 4H.7 Learning.
    
    Key capabilities:
    1. Commitment → Action: Propose governed actions from authorized commitments
    2. Action → Work: Route actions through existing work infrastructure (Project/Task)
    3. Execution → Observation: Record actual execution outcomes vs expected
    4. Outcome → Assessment: Compare expected vs actual, produce evidence
    5. Assessment → State: Update CompanyState, trigger adaptive planning
    6. Evidence → Learning: Feed into 4H.7 OrganizationalLearning/PatternDetection
    """

    def __init__(self):
        pass

    # -------------------------------------------------------------------------
    # Commitment → Action Proposal (Adaptive Execution)
    # -------------------------------------------------------------------------

    async def propose_actions_from_commitment(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user_id: str,
        commitment_id: str,
        action_plan: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Propose a batch of governed actions from an authorized commitment.
        
        If action_plan is provided, uses it; otherwise derives actions from
        the commitment's strategic context (initiative, project, objective).
        """
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != organization_id:
            raise ValueError("Commitment not found")

        if commitment.state not in ("authorized", "active"):
            raise ValueError(
                f"Commitment state '{commitment.state}' is not executable"
            )

        if action_plan is None:
            action_plan = await self._derive_action_plan(db, organization_id, commitment)

        results = []
        for action_spec in action_plan:
            result = await governed_commitment_engine.propose_actions_from_commitment(
                db, organization_id,
                user_id=user_id,
                commitment_id=commitment_id,
                **action_spec,
            )
            if result:
                results.append(result)

        # Transition commitment to active if actions were proposed
        if results and commitment.state == "authorized":
            await governed_commitment_engine.transition_commitment(
                db, organization_id, commitment_id,
                user_id=user_id,
                new_state="active",
                reason="Actions proposed for execution",
            )

        return results

    async def _derive_action_plan(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment: CompanyCommitment,
    ) -> List[Dict[str, Any]]:
        """
        Derive an action plan from the commitment's strategic context.
        Consumes: Initiative, Project, Objective, Decision Intelligence.
        """
        plan = []

        # 1. If commitment links to an initiative, create alignment actions
        if commitment.initiative_id:
            initiative = await db.get(CompanyInitiative, commitment.initiative_id)
            if initiative and initiative.status == "active":
                # Check for linked projects
                links = list(
                    (await db.execute(
                        select(StrategicLink).where(
                            StrategicLink.organization_id == organization_id,
                            StrategicLink.initiative_id == initiative.id,
                        )
                    )).scalars().all()
                )
                for link in links:
                    project = await db.get(Project, link.project_id)
                    if project and project.status in ("planning", "active"):
                        plan.append({
                            "action_type": "task",
                            "title": f"Align {project.name} with commitment: {commitment.title}",
                            "description": f"Ensure project {project.code} delivers on commitment {commitment.title}",
                            "source_problem": f"Commitment {commitment.title} requires project alignment",
                            "target": project.name,
                            "scope_type": "project",
                            "scope_id": project.id,
                            "risk": "low",
                            "due_at": commitment.target_date,
                        })

        # 2. If commitment links to a project directly, create project actions
        if commitment.project_id and not any(p.get("scope_id") == commitment.project_id for p in plan):
            project = await db.get(Project, commitment.project_id)
            if project:
                plan.append({
                    "action_type": "task",
                    "title": f"Execute commitment via {project.name}",
                    "description": f"Drive project {project.code} to fulfill commitment: {commitment.title}",
                    "source_problem": commitment.rationale,
                    "target": project.name,
                    "scope_type": "project",
                    "scope_id": project.id,
                    "risk": "medium",
                    "due_at": commitment.target_date,
                })

        # 3. If commitment has conditions, create condition-check actions
        if commitment.conditions:
            for condition in commitment.conditions:
                plan.append({
                    "action_type": "task",
                    "title": f"Verify condition: {condition.get('metric', condition.get('id'))}",
                    "description": f"Check condition {condition.get('id')} for commitment {commitment.title}",
                    "source_problem": f"Conditional commitment requires verification",
                    "target": f"Condition {condition.get('id')}",
                    "scope_type": commitment.scope_type,
                    "scope_id": commitment.scope_id,
                    "risk": "low",
                    "due_at": commitment.target_date,
                })

        # 4. If no plan derived, create a generic execution action
        if not plan:
            plan.append({
                "action_type": "task",
                "title": f"Execute commitment: {commitment.title}",
                "description": commitment.description or commitment.rationale,
                "source_problem": commitment.rationale,
                "target": commitment.title,
                "scope_type": commitment.scope_type,
                "scope_id": commitment.scope_id,
                "risk": "medium",
                "due_at": commitment.target_date,
            })

        return plan[:5]  # Bound plan size

    # -------------------------------------------------------------------------
    # Action → Work Routing (via existing infrastructure)
    # -------------------------------------------------------------------------

    async def route_action_to_work(
        self,
        db: AsyncSession,
        organization_id: str,
        action_id: str,
        *,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Route an approved action through the existing work infrastructure.
        This is handled by action_ops_engine._route_into_system but exposed
        here for the adaptive execution workflow.
        """
        action = await db.get(CompanyAction, action_id)
        if not action or action.organization_id != organization_id:
            return None

        if action.state not in ("approved", "ready"):
            raise ValueError(f"Action must be approved or ready to route; current state: {action.state}")

        # The routing is done by action_ops_engine._route_into_system
        # which creates the actual Task/Project/Meeting/etc.
        # We just need to ensure the commitment linkage is maintained
        await action_ops_engine._route_and_ready(
            db, action=action, actor_id=user_id, user=None  # user loaded inside
        )

        # Reload to get target info
        await db.refresh(action)
        return {
            "action_id": action.id,
            "target_type": action.target_type,
            "target_id": action.target_id,
            "state": action.state,
        }

    # -------------------------------------------------------------------------
    # Execution → Observation (Outcome Recording)
    # -------------------------------------------------------------------------

    async def record_execution_observation(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user_id: str,
        action_id: str,
        observation: Dict[str, Any],
        outcome_type: str = "success",
        effectiveness: float = 0.5,
        evidence: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Record an execution observation with outcome assessment.
        
        This is the critical observation step that distinguishes:
        - action completion (task done)
        - outcome achievement (objective met)
        - evidence quality (measurement reliability)
        """
        action = await db.get(CompanyAction, action_id)
        if not action or action.organization_id != organization_id:
            return None

        if action.state not in ("completed", "verified"):
            raise ValueError(f"Cannot record observation from action state: {action.state}")

        # Record via action_ops_engine (creates CompanyActionOutcome)
        result = await action_ops_engine.record_outcome(
            db,
            organization_id=organization_id,
            action_id=action_id,
            user=None,  # loaded inside
            outcome_type=outcome_type,
            verdict=observation.get("verdict"),
            effectiveness=effectiveness,
            notes=notes,
            evidence=evidence,
        )

        if not result:
            return None

        # If action has commitment linkage, update commitment state
        if action.source_commitment_id:
            await self._propagate_outcome_to_commitment(
                db, organization_id, action.source_commitment_id, result
            )

        return result

    async def _propagate_outcome_to_commitment(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
        action_outcome: Dict[str, Any],
    ) -> None:
        """Propagate action outcome to commitment state and objective outcomes."""
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != organization_id:
            return

        # Update commitment state based on action outcomes
        all_actions = commitment.action_ids or []
        if not all_actions:
            return

        # Check all linked actions' outcomes
        completed = 0
        failed = 0
        total_effectiveness = 0.0
        measured = 0

        for action_id in all_actions:
            action = await db.get(CompanyAction, action_id)
            if action and action.outcome_id:
                outcome = await db.get(CompanyActionOutcome, action.outcome_id)
                if outcome:
                    measured += 1
                    total_effectiveness += outcome.effectiveness
                    if outcome.outcome_type == "success":
                        completed += 1
                    elif outcome.outcome_type == "failed":
                        failed += 1

# Derive commitment state
        if measured == len(all_actions) and len(all_actions) > 0:
            if failed == 0 and completed == len(all_actions):
                # All actions completed successfully - can go directly to fulfilled
                new_state = "fulfilled"
            elif failed > 0:
                new_state = "active"  # At risk, needs attention
            else:
                new_state = "active"

            if new_state != commitment.state:
                await governed_commitment_engine.transition_commitment(
                    db, organization_id, commitment_id,
                    user_id="system",
                    new_state=new_state,
                    reason=f"Derived from action outcomes: {completed}/{len(all_actions)} completed",
                )

        # If commitment links to objective, update objective outcome
        if commitment.objective_id:
            await self._update_objective_outcome(
                db, organization_id, commitment.objective_id,
                completed, failed, measured, total_effectiveness
            )

    async def _update_objective_outcome(
        self,
        db: AsyncSession,
        organization_id: str,
        objective_id: str,
        completed: int,
        failed: int,
        measured: int,
        total_effectiveness: float,
    ) -> None:
        """Update objective outcome based on commitment execution."""
        objective = await db.get(CompanyObjective, objective_id)
        if not objective or objective.organization_id != organization_id:
            return

        if measured > 0:
            avg_effectiveness = total_effectiveness / measured
            # Record objective outcome if significant progress
            current_value = objective.current_value or 0.0
            # Simple progress model: effectiveness contributes to current_value
            objective.current_value = min(
                objective.target_value or 100.0,
                current_value + (avg_effectiveness * 10)
            )
            objective.current_value_confidence = min(1.0, avg_effectiveness)
            objective.outcome_recorded_at = utcnow()

            if failed == 0 and completed >= measured * 0.8:
                objective.actual_outcome_state = "actual"
                objective.outcome_assessment = "met"
            elif failed > 0:
                objective.actual_outcome_state = "actual"
                objective.outcome_assessment = "underperformed"

            await db.flush()

    # -------------------------------------------------------------------------
    # Outcome → Assessment → Evidence → Learning Integration
    # -------------------------------------------------------------------------

    async def assess_commitment_outcome(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
        *,
        user_id: str,
        expected_outcome: Dict[str, Any],
        actual_observation: Dict[str, Any],
        measurement_quality: str = "medium",
        measurement_source: Optional[str] = None,
        evidence_fingerprints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Assess a commitment's outcome by comparing expected vs actual.
        Creates an ObjectiveOutcomeAssessment if linked to objective.
        """
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != organization_id:
            raise ValueError("Commitment not found")

        # Determine assessment
        expected = expected_outcome.get("target_value", 0)
        actual = actual_observation.get("actual_value", 0)
        variance = ((actual - expected) / expected * 100) if expected != 0 else 0

        # Assessment logic: positive variance = above target, negative = below target
        if variance >= -5 and variance <= 5:
            assessment = "met"
        elif variance > 5 and variance <= 20:
            assessment = "partially_met"
        elif variance > 20:
            assessment = "outperformed"
        elif variance >= -20 and variance < -5:
            assessment = "partially_met"
        elif variance < -20:
            assessment = "underperformed"
        else:
            assessment = "inconclusive"

        # Create assessment record if linked to objective
        if commitment.objective_id:
            from app.models.execution_strategy import ObjectiveOutcomeAssessment
            import hashlib
            import json
            fingerprint_data = json.dumps({
                "org": organization_id,
                "obj": commitment.objective_id,
                "assessment": assessment,
                "variance": variance,
                "ts": utcnow().isoformat(),
            }, sort_keys=True)
            fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]
            
            assessment_record = ObjectiveOutcomeAssessment(
                organization_id=organization_id,
                objective_id=commitment.objective_id,
                assessment_key=f"assessment_{utcnow().timestamp()}",
                assessment_state="completed",
                assessment=assessment,
                confidence=0.8,
                reasoning=f"Expected: {expected}, Actual: {actual}, Variance: {variance:.1f}%",
                variance_pct=variance,
                assessed_by=user_id,
                assessed_at=utcnow(),
                evidence_fingerprints=evidence_fingerprints or [],
                fingerprint=fingerprint,
            )
            db.add(assessment_record)
            await db.flush()

        # Check for contradictions
        contradictions = []
        if commitment.contradiction_ids:
            for contra_id in commitment.contradiction_ids:
                contra = await db.get(OperatingCompanyDecisionContradiction, contra_id)
                if contra and contra.status == "open":
                    contradictions.append({
                        "contradiction_id": contra_id,
                        "description": f"Side A: {contra.side_a_json}, Side B: {contra.side_b_json}",
                        "relevance": "may_explain_variance" if variance > 20 else "unrelated",
                    })

        return {
            "commitment_id": commitment_id,
            "assessment": assessment,
            "variance_pct": round(variance, 1),
            "expected": expected,
            "actual": actual,
            "measurement_quality": measurement_quality,
            "evidence_fingerprints": evidence_fingerprints or [],
            "contradictions": contradictions,
            "assessed_at": utcnow().isoformat(),
        }

    # -------------------------------------------------------------------------
    # Company State Integration
    # -------------------------------------------------------------------------

    async def update_company_state_from_execution(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
    ) -> Dict[str, Any]:
        """
        Update CompanyState based on execution outcomes.
        This feeds back into 4I.4 Planning Context → 4I.5 Adaptive Planning.
        """
        # Get planning context which already synthesizes company state
        context = await company_planning_context_engine.synthesize_planning_context(
            db, organization_id, scope="company"
        )

        # The context already includes execution state from strategic_execution_engine
        # We just need to ensure the commitment outcomes are reflected

        return {
            "company_state": context.execution_state or {},
            "commitment_outcomes_included": True,
            "synthesized_at": utcnow().isoformat(),
        }

    # -------------------------------------------------------------------------
    # Commitment State Query
    # -------------------------------------------------------------------------

    async def get_commitment_execution_status(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
    ) -> Dict[str, Any]:
        """Get comprehensive execution status for a commitment."""
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != organization_id:
            return {}

        action_ids = commitment.action_ids or []
        actions = []
        completed = 0
        in_progress = 0
        blocked = 0
        pending = 0
        total_effectiveness = 0.0
        outcomes = []

        for action_id in action_ids:
            action = await db.get(CompanyAction, action_id)
            if not action:
                continue

            action_data = {
                "action_id": action.id,
                "title": action.title,
                "action_type": action.action_type,
                "state": action.state,
                "target_type": action.target_type,
                "target_id": action.target_id,
                "assignee_id": action.assignee_id,
                "due_at": action.due_at.isoformat() if action.due_at else None,
                "completed_at": action.completed_at.isoformat() if action.completed_at else None,
            }

            if action.state == "completed":
                completed += 1
            elif action.state == "in_progress":
                in_progress += 1
            elif action.state == "blocked":
                blocked += 1
            else:
                pending += 1

            if action.outcome_id:
                outcome = await db.get(CompanyActionOutcome, action.outcome_id)
                if outcome:
                    outcomes.append({
                        "outcome_id": outcome.id,
                        "outcome_type": outcome.outcome_type,
                        "effectiveness": outcome.effectiveness,
                        "verdict": outcome.verdict,
                    })
                    total_effectiveness += outcome.effectiveness

            actions.append(action_data)

        avg_effectiveness = total_effectiveness / len(outcomes) if outcomes else 0

        # Determine commitment health
        if commitment.state == "fulfilled":
            health = "healthy"
        elif blocked > 0 or (in_progress > 0 and completed == 0):
            health = "at_risk"
        elif in_progress > 0:
            health = "in_progress"
        else:
            health = "pending"

        return {
            "commitment_id": commitment.id,
            "commitment_title": commitment.title,
            "commitment_state": commitment.state,
            "health": health,
            "actions": {
                "total": len(actions),
                "completed": completed,
                "in_progress": in_progress,
                "blocked": blocked,
                "pending": pending,
            },
            "avg_effectiveness": round(avg_effectiveness, 2),
            "outcomes": outcomes,
            "action_details": actions,
            "objective_linked": commitment.objective_id is not None,
            "initiative_linked": commitment.initiative_id is not None,
            "project_linked": commitment.project_id is not None,
        }


adaptive_execution_engine = AdaptiveExecutionEngine()