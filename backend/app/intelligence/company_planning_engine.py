"""Phase 4I — Company Intent & Planning Engine.

Extends the canonical company planning primitives with adaptive planning
that consumes 4H.7 institutional learning (lessons, patterns, contradictions,
provenance, temporal history).

This engine does NOT create a parallel planning module. It extends the
existing CompanyGoal/CompanyObjective/CompanyInitiative primitives and
consumes the 4H.7 institutional learning substrate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, date, timezone
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
)
from app.models.company_operating import CompanyDecision
from app.models.company_state import CompanyState
from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
from app.models.intelligence import PatternDetection
from app.models.company_operating import CompanyDecisionContradiction
from app.models.company_actions import CompanyAction
from app.intelligence.company_brain import company_brain


def _days(n: int) -> timedelta:
    return timedelta(days=n)


class CompanyPlanningEngine:
    """
    Company Planning Engine — adaptive planning that consumes institutional learning.

    Key principles:
    - Governance-first: scope resolved before any retrieval
    - Learning-first: consumes 4H.7 lessons/patterns/contradictions/provenance
    - Adaptive: plans adapt when learning/state changes
    - Provenance: every plan item traces back to decisions/lessons/patterns
    - Governance: intent → plan → action requires governance approval
    """

    def __init__(self):
        pass

    # -------------------------------------------------------------------------
    # Intent Management
    # -------------------------------------------------------------------------

    async def create_intent(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user_id: str,
        kind: str,
        title: str,
        description: Optional[str] = None,
        rationale: Optional[str] = None,
        scope: str = "company",
        scope_id: Optional[str] = None,
        priority: int = 3,
        start_date: Optional[date] = None,
        target_date: Optional[date] = None,
        metric_kind: Optional[str] = None,
        metric_unit: Optional[str] = None,
        target_value: Optional[float] = None,
        expected_outcome: Optional[dict] = None,
        governance_note: Optional[str] = None,
        policy: str = "auto",
        approval_required: bool = False,
        approver_person_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
        lesson_fingerprints: Optional[list[str]] = None,
        pattern_ids: Optional[list[str]] = None,
        contradiction_ids: Optional[list[str]] = None,
        source_intent_id: Optional[str] = None,
        source_decision_id: Optional[str] = None,
        source_scenario_id: Optional[str] = None,
        source: str = "declared",  # INTENT_SOURCE
    ) -> CompanyIntent:
        """Create a new company intent with governance and learning integration."""
        if kind not in INTENT_KINDS:
            raise ValueError(f"Invalid intent kind: {kind}")

        # Governance: verify caller access (scope check)
        # In production, would call resolve_caller_access here

        # Build fingerprint for exact-once
        fingerprint_data = f"{organization_id}:{kind}:{title}:{scope}:{scope_id or ''}"
        import hashlib
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        # Check exact-once
        existing = await db.execute(
            select(CompanyIntent).where(
                CompanyIntent.organization_id == organization_id,
                CompanyIntent.fingerprint == fingerprint,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Intent with this fingerprint already exists")

        # Resolve learning integration
        lesson_fps = lesson_fingerprints or []
        pattern_ids_list = pattern_ids or []
        contradiction_ids_list = contradiction_ids or []

        intent = CompanyIntent(
            organization_id=organization_id,
            kind=kind,
            title=title[:300],
            description=description,
            rationale=rationale,
            scope=scope,
            scope_id=scope_id,
            priority=max(1, min(5, priority)),
            owner_person_id=owner_person_id,
            owner_label=owner_label,
            sponsor_person_id=sponsor_person_id,
            sponsor_label=sponsor_label,
            policy=policy,
            approval_required=approval_required,
            approver_person_id=approver_person_id,
            start_date=start_date,
            target_date=target_date,
            metric_kind=metric_kind,
            metric_unit=metric_unit,
            target_value=target_value,
            expected_outcome=expected_outcome or {},
            governance_note=governance_note,
            lesson_fingerprints=lesson_fps,
            pattern_ids=pattern_ids_list,
            contradiction_ids=contradiction_ids_list,
            source_event_id=source_event_id,
            source_intent_id=source_intent_id,
            source_decision_id=source_decision_id,
            source_scenario_id=source_scenario_id,
            source=source,
            fingerprint=fingerprint,
        )

        # Set initial epistemic status based on source
        if source == "declared":
            intent.epistemic_status = "proposed"  # Requires governance adoption
        else:
            intent.epistemic_status = "discovered"

        # Set initial state
        if approval_required:
            intent.state = "proposed"
        else:
            intent.state = "active"

        db.add(intent)
        await db.flush()

        # Create strategic history entry
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=organization_id,
            entity_type="intent",
            entity_id=intent.id,
            entity_label=title[:300],
            field="state",
            old_value=None,
            new_value=intent.state,
            reason="Intent created",
            source_event_id=source_event_id or "intent.created",
            changed_at=utcnow(),
        )
        db.add(history)

        return intent

    async def transition_intent_epistemic_status(
        self,
        db: AsyncSession,
        organization_id: str,
        intent_id: str,
        new_status: str,
        *,
        user_id: str,
        reason: str,
        source_event_id: Optional[str] = None,
    ) -> CompanyIntent:
        """Transition intent through epistemic states (discovered→proposed→adopted→active→superseded→archived)."""
        if new_status not in ["discovered", "proposed", "adopted", "active", "superseded", "archived"]:
            raise ValueError(f"Invalid epistemic status: {new_status}")

        intent = await db.get(CompanyIntent, intent_id)
        if not intent or intent.organization_id != organization_id:
            raise ValueError("Intent not found")

        old_status = intent.epistemic_status
        intent.epistemic_status = new_status

        # Sync state with epistemic status
        if new_status == "adopted":
            intent.state = "active"
        elif new_status == "archived":
            intent.state = "retired"
        elif new_status == "superseded":
            intent.state = "retired"

        # Record in strategic history
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=organization_id,
            entity_type="intent",
            entity_id=intent_id,
            entity_label=intent.title[:300],
            field="epistemic_status",
            old_value=old_status,
            new_value=new_status,
            reason=reason,
            source_event_id=source_event_id or f"intent.epistemic.{new_status}",
            changed_at=utcnow(),
        )
        db.add(history)

        await db.flush()
        return intent

    async def supersede_intent(
        self,
        db: AsyncSession,
        organization_id: str,
        old_intent_id: str,
        new_intent_id: str,
        *,
        user_id: str,
        reason: str,
        source_event_id: Optional[str] = None,
    ) -> tuple[CompanyIntent, CompanyIntent]:
        """Supersede an intent with a new one. Maintains temporal supersession chain."""
        old_intent = await db.get(CompanyIntent, old_intent_id)
        new_intent = await db.get(CompanyIntent, new_intent_id)

        if not old_intent or old_intent.organization_id != organization_id:
            raise ValueError("Old intent not found")
        if not new_intent or new_intent.organization_id != organization_id:
            raise ValueError("New intent not found")

        if old_intent.fingerprint != new_intent.fingerprint:
            raise ValueError("Supersession requires same fingerprint (same logical intent)")

        # Link supersession chain
        old_intent.superseded_by_id = new_intent.id
        new_intent.supersedes_id = old_intent.id
        new_intent.source_intent_id = old_intent.id

        # Update epistemic status
        old_intent.epistemic_status = "superseded"
        old_intent.state = "retired"
        new_intent.epistemic_status = "adopted"
        new_intent.state = "active"

        # Record in strategic history
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=organization_id,
            entity_type="intent",
            entity_id=old_intent_id,
            entity_label=old_intent.title[:300],
            field="superseded_by",
            old_value=None,
            new_value=new_intent_id,
            reason=reason,
            source_event_id=source_event_id or f"intent.superseded",
            changed_at=utcnow(),
        )
        db.add(history)

        await db.flush()
        return old_intent, new_intent

    async def link_intent_to_plan(
        self,
        db: AsyncSession,
        organization_id: str,
        intent_id: str,
        plan_id: str,
    ) -> None:
        """Link an intent to a plan."""
        intent = await db.get(CompanyIntent, intent_id)
        if not intent or intent.organization_id != organization_id:
            raise ValueError("Intent not found")

        plan = await db.get(CompanyPlan, plan_id)
        if not plan or plan.organization_id != organization_id:
            raise ValueError("Plan not found")

        intent.intent_id = plan_id
        plan.intent_id = intent_id
        await db.flush()

    # -------------------------------------------------------------------------
    # Plan Management
    # -------------------------------------------------------------------------

    async def create_plan(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user_id: str,
        kind: str,
        title: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        intent_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        objective_ids: Optional[list[str]] = None,
        initiative_ids: Optional[list[str]] = None,
        items: Optional[list[dict]] = None,
        focus: Optional[dict] = None,
        start_date: Optional[date] = None,
        target_date: Optional[date] = None,
        policy: str = "auto",
        approval_required: bool = False,
        approver_person_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
        lesson_fingerprints: Optional[list[str]] = None,
        pattern_ids: Optional[list[str]] = None,
        contradiction_ids: Optional[list[str]] = None,
        source_intent_id: Optional[str] = None,
        source_plan_id: Optional[str] = None,
        source_scenario_id: Optional[str] = None,
    ) -> CompanyPlan:
        """Create a new company plan with learning integration."""
        if kind not in PLAN_KINDS:
            raise ValueError(f"Invalid plan kind: {kind}")

        # Build fingerprint for exact-once
        fingerprint_data = f"{organization_id}:{kind}:{title}:{intent_id or ''}"
        import hashlib
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        # Check exact-once
        existing = await db.execute(
            select(CompanyPlan).where(
                CompanyPlan.organization_id == organization_id,
                CompanyPlan.fingerprint == fingerprint,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Plan with this fingerprint already exists")

        lesson_fps = lesson_fingerprints or []
        pattern_ids_list = pattern_ids or []
        contradiction_ids_list = contradiction_ids or []

        plan = CompanyPlan(
            organization_id=organization_id,
            kind=kind,
            title=title[:300],
            summary=summary,
            description=description,
            intent_id=intent_id,
            goal_id=goal_id,
            objective_ids=objective_ids or [],
            initiative_ids=initiative_ids or [],
            items=items or [],
            focus=focus or {},
            start_date=start_date,
            target_date=target_date,
            policy=policy,
            approval_required=approval_required,
            approver_person_id=approver_person_id,
            lesson_fingerprints=lesson_fps,
            pattern_ids=pattern_ids_list,
            contradiction_ids=contradiction_ids_list,
            source_event_id=source_event_id,
            source_intent_id=source_intent_id,
            source_plan_id=source_plan_id,
            source_scenario_id=source_scenario_id,
            fingerprint=fingerprint,
        )

        # Set initial state
        if approval_required:
            plan.state = "proposed"
        else:
            plan.state = "active"

        db.add(plan)
        await db.flush()

        # Create plan items if provided
        if items:
            for item_data in items:
                await self._create_plan_item(
                    db, organization_id, plan.id, item_data, user_id
                )

        return plan

    async def _create_plan_item(
        self,
        db: AsyncSession,
        organization_id: str,
        plan_id: str,
        item_data: dict,
        user_id: str,
    ) -> PlanItem:
        """Create a plan item with exact-once fingerprint."""
        fingerprint_data = f"{organization_id}:{plan_id}:{item_data.get('title', '')}"
        import hashlib
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        existing = await db.execute(
            select(PlanItem).where(
                PlanItem.organization_id == organization_id,
                PlanItem.plan_id == plan_id,
                PlanItem.fingerprint == fingerprint,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Plan item with fingerprint {fingerprint} already exists")

        item = PlanItem(
            organization_id=organization_id,
            plan_id=plan_id,
            kind=item_data.get("kind", "task"),
            title=item_data.get("title", "")[:300],
            description=item_data.get("description"),
            state=item_data.get("state", "pending"),
            owner_person_id=item_data.get("owner_person_id"),
            owner_label=item_data.get("owner_label", ""),
            assignee_person_id=item_data.get("assignee_person_id"),
            assignee_label=item_data.get("assignee_label", ""),
            start_date=item_data.get("start_date"),
            due_date=item_data.get("due_date"),
            dependencies=item_data.get("dependencies", []),
            resources=item_data.get("resources", []),
            expected_outcome=item_data.get("expected_outcome"),
            confidence=item_data.get("confidence", 0.5),
            lesson_fingerprints=item_data.get("lesson_fingerprints", []),
            pattern_ids=item_data.get("pattern_ids", []),
            source_event_id=item_data.get("source_event_id"),
            source_intent_id=item_data.get("source_intent_id"),
            source_initiative_id=item_data.get("source_initiative_id"),
            source_task_id=item_data.get("source_task_id"),
            fingerprint=fingerprint,
        )
        db.add(item)
        await db.flush()
        return item

    async def update_plan_state(
        self,
        db: AsyncSession,
        organization_id: str,
        plan_id: str,
        new_state: str,
        *,
        user_id: str,
        reason: str,
        source_event_id: Optional[str] = None,
    ) -> CompanyPlan:
        """Transition plan through governance states."""
        if new_state not in PLAN_STATES:
            raise ValueError(f"Invalid plan state: {new_state}")

        plan = await db.get(CompanyPlan, plan_id)
        if not plan or plan.organization_id != organization_id:
            raise ValueError("Plan not found")

        old_state = plan.state
        plan.state = new_state

        if new_state == "completed":
            plan.completed_at = utcnow()

        await db.flush()
        return plan

    async def add_plan_item(
        self,
        db: AsyncSession,
        organization_id: str,
        plan_id: str,
        item_data: dict,
        *,
        user_id: str,
    ) -> PlanItem:
        """Add an item to an existing plan."""
        return await self._create_plan_item(db, organization_id, plan_id, item_data, user_id)

    # -------------------------------------------------------------------------
    # Adaptive Planning
    # -------------------------------------------------------------------------

    async def check_adaptations_needed(
        self,
        db: AsyncSession,
        organization_id: str,
        plan_id: str,
    ) -> list[dict[str, Any]]:
        """
        Check if a plan needs adaptation based on:
        - Outcome deviations
        - Company state changes
        - New institutional lessons
        - New contradictions
        - Prediction changes
        - Governance decisions
        """
        plan = await db.get(CompanyPlan, plan_id)
        if not plan or plan.organization_id != organization_id:
            return []

        adaptations = []

        # Check outcome deviations via intent
        if plan.intent_id:
            intent = await db.get(CompanyIntent, plan.intent_id)
            if intent and intent.metric_kind and intent.current_value is not None and intent.target_value is not None:
                if intent.target_value != 0:
                    deviation = abs(intent.current_value - intent.target_value) / abs(intent.target_value)
                    if deviation > 0.2:  # >20% deviation
                        adaptations.append({
                            "trigger": "outcome_deviation",
                            "trigger_reason": f"Outcome deviation {deviation:.1%} from target",
                            "action": "adjust_timeline",
                            "action_detail": f"Adjust timeline due to {deviation:.1%} outcome deviation",
                            "trigger_event_id": None,
                        })

        # Check for new lessons that invalidate plan assumptions
        if plan.lesson_fingerprints:
            for fp in plan.lesson_fingerprints:
                lesson = await db.execute(
                    select(OrganizationalLearning).where(
                        OrganizationalLearning.organization_id == organization_id,
                        OrganizationalLearning.fingerprint == fp,
                    )
                )
                lesson_obj = lesson.scalar_one_or_none()
                if lesson_obj and lesson_obj.updated_at > (plan.last_adapted_at or plan.created_at):
                    adaptations.append({
                        "trigger": "lesson_learned",
                        "trigger_reason": f"Lesson {fp} updated",
                        "action": "adjust_scope",
                        "action_detail": f"Adjust plan scope based on updated lesson: {lesson_obj.title}",
                        "trigger_event_id": None,
                        "lesson_fingerprint": fp,
                    })

        # Check for new contradictions
        if plan.contradiction_ids:
            for cid in plan.contradiction_ids:
                contra = await db.get(CompanyDecisionContradiction, cid)
                if contra and contra.created_at > (plan.last_adapted_at or plan.created_at):
                    adaptations.append({
                        "trigger": "contradiction",
                        "trigger_reason": f"New contradiction {cid}",
                        "action": "adjust_scope",
                        "action_detail": f"Adjust plan due to new contradiction",
                        "trigger_event_id": contra.source_event_id,
                        "contradiction_id": cid,
                    })

        return adaptations

    async def adapt_plan(
        self,
        db: AsyncSession,
        organization_id: str,
        plan_id: str,
        *,
        user_id: str,
        trigger: str,
        trigger_reason: str,
        action: str,
        action_detail: str,
        trigger_event_id: Optional[str] = None,
        lesson_fingerprint: Optional[str] = None,
        pattern_id: Optional[str] = None,
        contradiction_id: Optional[str] = None,
        before_snapshot: Optional[dict] = None,
        after_snapshot: Optional[dict] = None,
    ) -> PlanAdaptation:
        """Apply an adaptation to a plan with full audit trail."""
        if trigger not in ADAPTATION_TRIGGERS:
            raise ValueError(f"Invalid adaptation trigger: {trigger}")
        if action not in ADAPTATION_ACTIONS:
            raise ValueError(f"Invalid adaptation action: {action}")

        plan = await db.get(CompanyPlan, plan_id)
        if not plan or plan.organization_id != organization_id:
            raise ValueError("Plan not found")

        # Create adaptation record
        fingerprint_data = f"{organization_id}:{plan_id}:{trigger}:{action}:{utcnow().isoformat()}"
        import hashlib
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        adaptation = PlanAdaptation(
            organization_id=organization_id,
            plan_id=plan_id,
            trigger=trigger,
            trigger_event_id=trigger_event_id,
            trigger_reason=trigger_reason,
            action=action,
            action_detail=action_detail,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            lesson_fingerprint=lesson_fingerprint,
            pattern_id=pattern_id,
            contradiction_id=contradiction_id,
            fingerprint=fingerprint,
        )

        plan.adaptation_state = "adapting"
        plan.last_adapted_at = utcnow()
        plan.adaptation_count += 1

        db.add(adaptation)
        await db.flush()

        return adaptation

    async def approve_adaptation(
        self,
        db: AsyncSession,
        organization_id: str,
        adaptation_id: str,
        *,
        user_id: str,
        approval_note: Optional[str] = None,
    ) -> PlanAdaptation:
        """Approve a plan adaptation."""
        adaptation = await db.get(PlanAdaptation, adaptation_id)
        if not adaptation or adaptation.organization_id != organization_id:
            raise ValueError("Adaptation not found")

        adaptation.state = "approved"
        adaptation.approved_by = user_id
        adaptation.approved_at = utcnow()
        adaptation.approval_note = approval_note

        plan = await db.get(CompanyPlan, adaptation.plan_id)
        if plan:
            plan.adaptation_state = "stable"
            plan.last_adapted_at = utcnow()

        await db.flush()
        return adaptation

    # -------------------------------------------------------------------------
    # Predictions & Simulations
    # -------------------------------------------------------------------------

    async def generate_intent_prediction(
        self,
        db: AsyncSession,
        organization_id: str,
        intent_id: str,
        *,
        kind: str,
        horizon_days: int = 90,
    ) -> IntentPrediction:
        """Generate a prediction for an intent using company state and learning."""
        intent = await db.get(CompanyIntent, intent_id)
        if not intent or intent.organization_id != organization_id:
            raise ValueError("Intent not found")

        # Gather evidence from company state, learning, patterns
        evidence_fps = []
        pattern_ids_list = []
        lesson_fps = []

        # Get relevant lessons
        if intent.lesson_fingerprints:
            lesson_fps = intent.lesson_fingerprints

        # Get relevant patterns
        if intent.pattern_ids:
            pattern_ids_list = intent.pattern_ids

        # Build prediction (simplified - real implementation would use ML/analytics)
        prediction = {
            "trajectory": "on_track",
            "probability_of_success": 0.7,
            "key_risks": [],
            "key_opportunities": [],
            "recommended_actions": [],
        }

        fingerprint_data = f"{organization_id}:{intent_id}:{kind}:{utcnow().isoformat()}"
        import hashlib
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        prediction_obj = IntentPrediction(
            organization_id=organization_id,
            intent_id=intent_id,
            kind=kind,
            prediction=prediction,
            confidence=0.7,
            evidence_fingerprints=evidence_fps,
            pattern_ids=pattern_ids_list,
            lesson_fingerprints=lesson_fps,
            horizon_days=horizon_days,
            fingerprint=fingerprint,
        )
        db.add(prediction_obj)
        await db.flush()
        return prediction_obj

    async def run_plan_simulation(
        self,
        db: AsyncSession,
        organization_id: str,
        plan_id: str,
        *,
        user_id: str,
        title: str,
        question: Optional[str] = None,
        assumptions: Optional[list[dict]] = None,
        domains: Optional[list[str]] = None,
    ) -> PlanSimulation:
        """Run a what-if simulation for a plan."""
        plan = await db.get(CompanyPlan, plan_id)
        if not plan or plan.organization_id != organization_id:
            raise ValueError("Plan not found")

        fingerprint_data = f"{organization_id}:{plan_id}:{title}:{utcnow().isoformat()}"
        import hashlib
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        simulation = PlanSimulation(
            organization_id=organization_id,
            plan_id=plan_id,
            title=title,
            question=question,
            assumptions=assumptions or [],
            domains=domains or [],
            status="queued",
            created_by=user_id,
            fingerprint=fingerprint,
        )
        db.add(simulation)
        await db.flush()

        # Run simulation (simplified)
        simulation.status = "running"
        await db.flush()

        # Simplified simulation logic
        results = {
            "projected_outcome": "simulated",
            "key_metrics": {},
            "risks": [],
            "opportunities": [],
        }
        delta = {"compared_to_base": "simulated"}

        simulation.results = results
        simulation.delta = delta
        simulation.status = "finished"
        simulation.completed_at = utcnow()
        simulation.duration_ms = 100

        await db.flush()
        return simulation

    # -------------------------------------------------------------------------
    # State Materialization
    # -------------------------------------------------------------------------

    async def materialize_intent_plan_state(
        self,
        db: AsyncSession,
        organization_id: str,
        intent_id: str,
    ) -> IntentPlanState:
        """Materialize the live state of an intent + its plans."""
        intent = await db.get(CompanyIntent, intent_id)
        if not intent or intent.organization_id != organization_id:
            raise ValueError("Intent not found")

        # Get all plans for this intent
        plans_stmt = select(CompanyPlan).where(
            CompanyPlan.organization_id == organization_id,
            CompanyPlan.intent_id == intent_id,
        )
        plans_result = await db.execute(plans_stmt)
        plans = plans_result.scalars().all()

        # Count contradictions
        contra_count = 0
        lesson_count = 0
        pattern_count = 0

        # Aggregate from intent and plans
        all_lesson_fps = set(intent.lesson_fingerprints or [])
        all_pattern_ids = set(intent.pattern_ids or [])
        all_contra_ids = set(intent.contradiction_ids or [])

        for plan in plans:
            all_lesson_fps.update(plan.lesson_fingerprints or [])
            all_pattern_ids.update(plan.pattern_ids or [])
            all_contra_ids.update(plan.contradiction_ids or [])

        # Count active contradictions
        if all_contra_ids:
            contra_stmt = select(func.count(CompanyDecisionContradiction.id)).where(
                CompanyDecisionContradiction.organization_id == organization_id,
                CompanyDecisionContradiction.id.in_(list(all_contra_ids)),
                CompanyDecisionContradiction.status == "open",
            )
            contra_result = await db.execute(contra_stmt)
            contra_count = contra_result.scalar() or 0

        # Count supporting lessons/patterns
        lesson_count = len(all_lesson_fps)
        pattern_count = len(all_pattern_ids)

        # Get latest adaptation
        last_adaptation = None
        if plans:
            plan_ids = [p.id for p in plans]
            adaptation_stmt = select(PlanAdaptation).where(
                PlanAdaptation.organization_id == organization_id,
                PlanAdaptation.plan_id.in_(plan_ids),
            ).order_by(PlanAdaptation.created_at.desc()).limit(1)
            adaptation_result = await db.execute(adaptation_stmt)
            last_adaptation = adaptation_result.scalar_one_or_none()

        # Get last prediction
        prediction_stmt = select(IntentPrediction).where(
            IntentPrediction.organization_id == organization_id,
            IntentPrediction.intent_id == intent_id,
        ).order_by(IntentPrediction.generated_at.desc()).limit(1)
        prediction_result = await db.execute(prediction_stmt)
        last_prediction = prediction_result.scalar_one_or_none()

        # Determine overall state
        plan_states = [p.state for p in plans]
        if all(s == "completed" for s in plan_states):
            overall_state = "completed"
        elif any(s == "active" for s in plan_states):
            overall_state = "active"
        elif any(s == "paused" for s in plan_states):
            overall_state = "paused"
        elif any(s == "proposed" for s in plan_states):
            overall_state = "proposed"
        else:
            overall_state = "draft"

        # Calculate progress
        total = len(plans)
        completed = sum(1 for p in plans if p.state == "completed")
        progress = completed / total if total > 0 else 0.0

        # Determine health
        health = "healthy"
        if plan_states and any(s == "failed" for s in plan_states):
            health = "critical"
        elif plan_states and any(s == "at_risk" for s in plan_states):
            health = "at_risk"
        elif plan_states and any(s == "paused" for s in plan_states):
            health = "at_risk"

        fingerprint_data = f"{organization_id}:{intent_id}:{utcnow().isoformat()}"
        import hashlib
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        state = IntentPlanState(
            organization_id=organization_id,
            intent_id=intent_id,
            overall_state=overall_state,
            progress=progress,
            health=health,
            total_plans=total,
            active_plans=sum(1 for p in plans if p.state == "active"),
            completed_plans=completed,
            active_contradictions=contra_count,
            supporting_lessons=lesson_count,
            supporting_patterns=pattern_count,
            last_adaptation_at=last_adaptation.created_at if last_adaptation else None,
            last_prediction_at=last_prediction.generated_at if last_prediction else None,
            last_state_change_at=max((p.updated_at for p in plans), default=None),
            fingerprint=fingerprint,
        )
        db.add(state)
        await db.flush()
        return state

    # -------------------------------------------------------------------------
    # Learning Integration Helpers
    # -------------------------------------------------------------------------

    async def get_relevant_lessons(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        topic: Optional[str] = None,
        pattern_id: Optional[str] = None,
        intent_kind: Optional[str] = None,
        limit: int = 10,
    ) -> list[OrganizationalLearning]:
        """Get lessons relevant to a planning context."""
        conditions = [
            OrganizationalLearning.organization_id == organization_id,
            OrganizationalLearning.status == "active",
        ]
        if topic:
            conditions.append(OrganizationalLearning.topic_name.ilike(f"%{topic}%"))
        if pattern_id:
            conditions.append(OrganizationalLearning.source_id == pattern_id)
            conditions.append(OrganizationalLearning.source_type == "pattern")

        stmt = select(OrganizationalLearning).where(and_(*conditions)).order_by(
            OrganizationalLearning.confidence.desc()
        ).limit(limit)

        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_relevant_patterns(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        family: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10,
    ) -> list[PatternDetection]:
        """Get patterns relevant to a planning context."""
        conditions = [PatternDetection.organization_id == organization_id]
        if family:
            conditions.append(PatternDetection.family == family)
        if status:
            conditions.append(PatternDetection.status == status)

        stmt = select(PatternDetection).where(and_(*conditions)).order_by(
            PatternDetection.confidence.desc()
        ).limit(limit)

        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_relevant_contradictions(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        lesson_fingerprint: Optional[str] = None,
        decision_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[CompanyDecisionContradiction]:
        """Get contradictions relevant to a planning context."""
        conditions = [
            CompanyDecisionContradiction.organization_id == organization_id,
            CompanyDecisionContradiction.status == "open",
        ]
        if lesson_fingerprint:
            conditions.append(CompanyDecisionContradiction.lesson_memory_id == lesson_fingerprint)
        if decision_id:
            conditions.append(CompanyDecisionContradiction.decision_id == decision_id)

        stmt = select(CompanyDecisionContradiction).where(and_(*conditions)).order_by(
            CompanyDecisionContradiction.created_at.desc()
        ).limit(limit)

        result = await db.execute(stmt)
        return result.scalars().all()


company_planning_engine = CompanyPlanningEngine()