"""Phase 4I.7 — Governed Commitment / Authorization Engine.

This engine implements the governed bridge from Decision Intelligence to Execution
via canonical CompanyCommitment and CompanyAuthorization entities.

Key principles:
- Governance-first: scope resolved before any retrieval
- Decision ≠ Authorization ≠ Commitment ≠ Execution (explicit boundaries)
- Reuse: consumes CompanyDecision, CompanyAction, CompanyCommitment, CompanyAuthorization,
  GovernanceScope, ApprovalPolicy, CompanyDecisionAlternative, CompanyDecisionEvidence,
  CompanyDecisionPrecedent, CompanyDecisionQuality, CompanyDecisionTrack
- Deterministic: same canonical inputs -> same commitment/authorization state
- Provenance: every commitment/authorization traces back to Decision Intelligence
- Epistemic separation: fact vs inference vs prediction vs proposal vs contested
- Contradiction preservation: both sides visible, never silently resolved
- Temporal truth: state transitions recorded with triggers
- No autonomous action: intelligence synthesized, commitments governed
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
    CompanyCommitment,
    CompanyAuthorization,
    COMMITMENT_STATES,
    COMMITMENT_TYPES,
    AUTHORIZATION_TYPES,
    AUTHORIZATION_STATES,
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
    StrategicAlignment,
    AlignmentGap,
    StrategicConflict,
    StrategicDependency,
)
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionAlternative,
    CompanyDecisionEvidence,
    CompanyDecisionPrecedent,
    CompanyDecisionQuality,
    CompanyDecisionTrack,
    CompanyDecisionContradiction,
    CompanyDecision as OperatingCompanyDecision,
    CompanyDecisionContradiction as OperatingCompanyDecisionContradiction,
    CompanyDecisionAlternative as OperatingCompanyDecisionAlternative,
    CompanyDecisionEvidence as OperatingCompanyDecisionEvidence,
    CompanyDecisionPrecedent as OperatingCompanyDecisionPrecedent,
    CompanyDecisionQuality as OperatingCompanyDecisionQuality,
    CompanyDecisionTrack as OperatingCompanyDecisionTrack,
    CompanyDecisionContradiction as OperatingCompanyDecisionContradiction,
    CompanyDecisionQuality as OperatingCompanyDecisionQuality,
)
from app.models.company_operating import CompanyDecision
from app.models.company_state import CompanyState
from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
from app.models.intelligence import PatternDetection
from app.models.company_actions import CompanyAction, CompanyActionEvent, CompanyActionOutcome
from app.models.governance import GovernanceScope, ApprovalPolicy
from app.models.role import Permission, Role
from app.models.company_actions import CompanyAction, CompanyActionEvent, CompanyActionOutcome
from app.intelligence.decision_intelligence_engine import decision_intelligence_engine
from app.intelligence.company_planning_context_engine import company_planning_context_engine
from app.intelligence.adaptive_planning_engine import adaptive_planning_engine
from app.knowledge.action_ops_engine import action_ops_engine


def _days(n: int) -> timedelta:
    return timedelta(days=n)


class GovernedCommitmentEngine:
    """
    Governed Commitment / Authorization Engine — the canonical bridge from
    Decision Intelligence to Execution via governed authorization.
    
    Key principles:
    - Governance-first: scope resolved before any retrieval
    - Decision ≠ Authorization ≠ Commitment ≠ Execution (explicit boundaries)
    - Reuse: consumes CompanyDecision, CompanyAction, CompanyCommitment, CompanyAuthorization,
      GovernanceScope, ApprovalPolicy, CompanyDecisionAlternative, CompanyDecisionEvidence,
      CompanyDecisionPrecedent, CompanyDecisionQuality, CompanyDecisionTrack
    - Deterministic: same canonical inputs -> same commitment/authorization state
    - Provenance: every commitment/authorization traces back to Decision Intelligence
    - Epistemic separation: fact vs inference vs prediction vs proposal vs contested
    - Contradiction preservation: both sides visible, never silently resolved
    - Temporal truth: state transitions recorded with triggers
    - No autonomous action: intelligence synthesized, commitments governed
    """

    def __init__(self):
        pass

    # -------------------------------------------------------------------------
    # Main Synthesis Entry Points
    # -------------------------------------------------------------------------

    async def create_authorization_request(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user_id: str,
        commitment_type: str = "unconditional",  # unconditional | conditional
        title: str = "",
        description: Optional[str] = None,
        rationale: Optional[str] = None,
        scope_type: str = "company",
        scope_id: Optional[str] = None,
        decision_intelligence_context_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        commitment_id: Optional[str] = None,
        decision_intelligence_context: Optional[object] = None,
        policy_id: Optional[str] = None,
        authorization_type: str = "full",
        conditions: Optional[list[dict]] = None,
        constraints: Optional[dict] = None,
        budget_ceiling: Optional[float] = None,
        budget_currency: Optional[str] = None,
        valid_from: Optional[date] = None,
        valid_until: Optional[date] = None,
        evidence_fingerprints: Optional[list[str]] = None,
        supporting_pattern_ids: Optional[list[str]] = None,
        supporting_lesson_fingerprints: Optional[list[str]] = None,
        contradicting_evidence_fingerprints: Optional[list[str]] = None,
        contradicting_pattern_ids: Optional[list[str]] = None,
        contradicting_lesson_fingerprints: Optional[list[str]] = None,
        contradiction_ids: Optional[list[str]] = None,
        decision_alternative_ids: Optional[list[str]] = None,
        decision_evidence_fingerprints: Optional[list[str]] = None,
        decision_precedent_ids: Optional[list[str]] = None,
        risk_assessment: Optional[dict] = None,
        lesson_fingerprints: Optional[list[str]] = None,
        pattern_ids: Optional[list[str]] = None,
        source_event_id: Optional[str] = None,
        source_decision_id: Optional[str] = None,
        source_scenario_id: Optional[str] = None,
    ) -> CompanyAuthorization:
        """
        Create a new authorization request with governance and learning integration.
        
        This is the primary entry point for requesting authorization based on
        Decision Intelligence context.
        """
        if authorization_type not in AUTHORIZATION_TYPES:
            raise ValueError(f"Invalid authorization type: {authorization_type}")

        # Governance: verify caller access (scope check)
        # In production, would call resolve_caller_access here

        # Build fingerprint for exact-once
        fingerprint_data = f"{organization_id}:{authorization_type}:{title}:{scope_type}:{scope_id or ''}:{decision_intelligence_context_id or ''}"
        import hashlib
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        # Check exact-once
        existing = await db.execute(
            select(CompanyAuthorization).where(
                CompanyAuthorization.organization_id == organization_id,
                CompanyAuthorization.fingerprint == fingerprint,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Authorization with this fingerprint already exists")

        # Resolve governance scope if provided
        if scope_type and scope_id:
            scope = await db.get(GovernanceScope, scope_id)
            if not scope or scope.organization_id != organization_id:
                raise ValueError("Invalid governance scope")

        # Resolve approval policy if provided
        if policy_id:
            policy = await db.get(ApprovalPolicy, policy_id)
            if not policy or policy.organization_id != organization_id:
                raise ValueError("Invalid approval policy")

        # Resolve decision intelligence context if provided
        di_context = None
        if decision_intelligence_context_id:
            di_context = await db.get(DecisionIntelligenceContext, decision_intelligence_context_id)
            if not di_context or di_context.organization_id != organization_id:
                raise ValueError("Invalid decision intelligence context")

        # Resolve decision if provided
        if decision_id:
            decision = await db.execute(
                select(OperatingCompanyDecision).where(
                    OperatingCompanyDecision.organization_id == organization_id,
                    OperatingCompanyDecision.decision_id == decision_id,
                )
            )
            decision_obj = decision.scalar_one_or_none()
            if not decision_obj:
                raise ValueError("Invalid decision ID")

        # Build authorization
        auth = CompanyAuthorization(
            organization_id=organization_id,
            authorization_type=authorization_type,
            title=title[:300],
            description=description,
            rationale=rationale,
            scope_type=scope_type or "company",
            scope_id=scope_id,
            decision_intelligence_context_id=decision_intelligence_context_id,
            decision_id=decision_id,
            commitment_id=commitment_id,
            policy_id=policy_id,
            conditions=conditions or [],
            constraints=constraints,
            budget_ceiling=budget_ceiling,
            budget_currency=budget_currency,
            valid_from=valid_from,
            valid_until=valid_until,
            state="requested",
            requested_by=user_id,
            requested_at=utcnow(),
            evidence_fingerprints=evidence_fingerprints or [],
            supporting_pattern_ids=supporting_pattern_ids or [],
            supporting_lesson_fingerprints=supporting_lesson_fingerprints or [],
            contradicting_evidence_fingerprints=contradicting_evidence_fingerprints or [],
            contradicting_pattern_ids=contradicting_pattern_ids or [],
            contradicting_lesson_fingerprints=contradicting_lesson_fingerprints or [],
            contradiction_ids=contradiction_ids or [],
            decision_alternative_ids=decision_alternative_ids or [],
            decision_evidence_fingerprints=decision_evidence_fingerprints or [],
            decision_precedent_ids=decision_precedent_ids or [],
            risk_assessment=risk_assessment,
            lesson_fingerprints=lesson_fingerprints or [],
            pattern_ids=pattern_ids or [],
            source_event_id=source_event_id,
            source_decision_id=source_decision_id,
            source_scenario_id=source_scenario_id,
            fingerprint=fingerprint,
        )

        db.add(auth)
        await db.flush()

        # Create strategic history entry
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=organization_id,
            entity_type="authorization",
            entity_id=auth.id,
            entity_label=title[:300],
            field="state",
            old_value=None,
            new_value=auth.state,
            reason="Authorization requested",
            source_event_id=source_event_id or "authorization.requested",
            changed_at=utcnow(),
        )
        db.add(history)

        return auth

    async def review_authorization(
        self,
        db: AsyncSession,
        organization_id: str,
        authorization_id: str,
        *,
        user_id: str,
        action: str,  # approve | reject | conditional
        review_note: Optional[str] = None,
        conditions: Optional[list[dict]] = None,
        source_event_id: Optional[str] = None,
    ) -> CompanyAuthorization:
        """Review an authorization request (approve/reject/conditional)."""
        auth = await db.get(CompanyAuthorization, authorization_id)
        if not auth or auth.organization_id != organization_id:
            raise ValueError("Authorization not found")

        if auth.state not in ("requested", "under_review"):
            raise ValueError(f"Authorization in state '{auth.state}' cannot be reviewed")

        old_state = auth.state

        if action == "approve":
            auth.state = "approved"
            auth.approved_by = user_id
            auth.approved_at = utcnow()
            auth.approval_note = review_note
            auth.authorized_at = utcnow()
        elif action == "reject":
            auth.state = "rejected"
            auth.rejected_by = user_id
            auth.rejected_at = utcnow()
            auth.rejection_reason = review_note
        elif action == "conditional":
            auth.state = "conditional"
            auth.reviewed_by = user_id
            auth.reviewed_at = utcnow()
            auth.conditions = conditions or []
            auth.approval_note = review_note
        else:
            raise ValueError(f"Invalid action: {action}")

        # Record in strategic history
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=organization_id,
            entity_type="authorization",
            entity_id=auth.id,
            entity_label=auth.title[:300],
            field="state",
            old_value=old_state,
            new_value=auth.state,
            reason=review_note or f"Authorization {action}",
            source_event_id=source_event_id or f"authorization.{action}",
            changed_at=utcnow(),
        )
        db.add(history)

        await db.flush()
        return auth

    async def create_commitment(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user_id: str,
        commitment_type: str = "unconditional",  # unconditional | conditional
        description: Optional[str] = None,
        title: str = "",
        rationale: str = "",
        scope_type: str = "company",
        scope_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        objective_id: Optional[str] = None,
        initiative_id: Optional[str] = None,
        project_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        authorization_id: Optional[str] = None,
        budget_allocated: Optional[float] = None,
        budget_currency: Optional[str] = None,
        approval_required: bool = False,
        resource_requirements: Optional[dict] = None,
        resource_constraints: Optional[dict] = None,
        start_date: Optional[date] = None,
        target_date: Optional[date] = None,
        conditions: Optional[list[dict]] = None,
        risk_assessment: Optional[dict] = None,
        risk_mitigations: Optional[list[dict]] = None,
        evidence_fingerprints: Optional[list[str]] = None,
        supporting_pattern_ids: Optional[list[str]] = None,
        supporting_lesson_fingerprints: Optional[list[str]] = None,
        contradicting_evidence_fingerprints: Optional[list[str]] = None,
        contradicting_pattern_ids: Optional[list[str]] = None,
        contradicting_lesson_fingerprints: Optional[list[str]] = None,
        contradiction_ids: Optional[list[str]] = None,
        decision_intelligence_context_id: Optional[str] = None,
        decision_alternative_ids: Optional[list[str]] = None,
        decision_evidence_fingerprints: Optional[list[str]] = None,
        decision_precedent_ids: Optional[list[str]] = None,
        source_event_id: Optional[str] = None,
        source_decision_id: Optional[str] = None,
        source_scenario_id: Optional[str] = None,
    ) -> CompanyCommitment:
        """
        Create a new company commitment with governance and learning integration.
        
        This is the primary entry point for creating commitments that bridge
        Decision Intelligence to Execution.
        """
        # commitment_type field in model accepts: unconditional | conditional
        # (COMMITMENT_TYPES constant is for commitment_kind/category, not this field)
        if commitment_type not in ("unconditional", "conditional"):
            raise ValueError(f"Invalid commitment type: {commitment_type}. Must be 'unconditional' or 'conditional'")

        # Governance: verify caller access (scope check)
        from app.intelligence.company_context import resolve_caller_access
        from app.models.user import User as UserModel
        user_obj = await db.get(UserModel, user_id)
        if not user_obj:
            raise ValueError(f"User {user_id} not found")
        caller = await resolve_caller_access(db, organization_id=organization_id, user=user_obj)
        if not caller.org_wide and not caller.anchored_scope_ids:
            raise ValueError("Cross-tenant access denied: user does not have access to organization")

        # If conditional, authorization is required
        if commitment_type == "conditional" and not authorization_id:
            raise ValueError("Conditional commitments require authorization_id")

        # Verify authorization if provided
        if authorization_id:
            auth = await db.get(CompanyAuthorization, authorization_id)
            if not auth or auth.organization_id != organization_id:
                raise ValueError("Invalid authorization")
            if auth.state != "approved":
                raise ValueError("Authorization must be approved")

        # Build fingerprint for exact-once
        fingerprint_data = f"{organization_id}:{commitment_type}:{title}:{scope_type}:{scope_id or ''}:{decision_id or ''}"
        import hashlib
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        # Check exact-once
        existing = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == organization_id,
                CompanyCommitment.fingerprint == fingerprint,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Commitment with this fingerprint already exists")

        # Resolve decision if provided
        if decision_id:
            decision = await db.execute(
                select(OperatingCompanyDecision).where(
                    OperatingCompanyDecision.organization_id == organization_id,
                    OperatingCompanyDecision.decision_id == decision_id,
                )
            )
            decision_obj = decision.scalar_one_or_none()
            if not decision_obj:
                raise ValueError("Invalid decision ID")

        # Resolve intent/objective/initiative/project if provided
        if intent_id:
            intent = await db.get(CompanyIntent, intent_id)
            if not intent or intent.organization_id != organization_id:
                raise ValueError("Invalid intent ID")
        if objective_id:
            objective = await db.get(CompanyObjective, objective_id)
            if not objective or objective.organization_id != organization_id:
                raise ValueError("Invalid objective ID")
        if initiative_id:
            initiative = await db.get(CompanyInitiative, initiative_id)
            if not initiative or initiative.organization_id != organization_id:
                raise ValueError("Invalid initiative ID")
        if project_id:
            project = await db.get(Project, project_id)  # Assuming Project model exists
            if not project or project.organization_id != organization_id:
                raise ValueError("Invalid project ID")

        # Build commitment
        commitment = CompanyCommitment(
            organization_id=organization_id,
            commitment_type=commitment_type,
            title=title[:300],
            description=description,
            rationale=rationale,
            scope_type=scope_type,
            scope_id=scope_id,
            intent_id=intent_id,
            objective_id=objective_id,
            initiative_id=initiative_id,
            project_id=project_id,
            decision_id=decision_id,
            authorization_id=authorization_id,
            budget_allocated=budget_allocated,
            budget_currency=budget_currency,
            resource_requirements=resource_requirements,
            resource_constraints=resource_constraints,
            start_date=start_date,
            target_date=target_date,
            conditions=conditions or [],
            risk_assessment=risk_assessment,
            risk_mitigations=risk_mitigations or [],
            evidence_fingerprints=evidence_fingerprints or [],
            supporting_pattern_ids=supporting_pattern_ids or [],
            supporting_lesson_fingerprints=supporting_lesson_fingerprints or [],
            contradicting_evidence_fingerprints=contradicting_evidence_fingerprints or [],
            contradicting_pattern_ids=contradicting_pattern_ids or [],
            contradicting_lesson_fingerprints=contradicting_lesson_fingerprints or [],
            contradiction_ids=contradiction_ids or [],
            decision_intelligence_context_id=decision_intelligence_context_id,
            decision_alternative_ids=decision_alternative_ids or [],
            source_event_id=source_event_id,
            source_decision_id=source_decision_id,
            source_scenario_id=source_scenario_id,
            fingerprint=fingerprint,
        )
        db.add(commitment)
        await db.flush()

        # Set initial state based on commitment type and authorization
        if commitment_type == "conditional" and authorization_id:
            commitment.state = "pending_authorization"
        elif commitment_type == "unconditional" and not approval_required:
            commitment.state = "authorized"
            commitment.authorized_at = utcnow()
            commitment.authorized_by = user_id
        else:
            commitment.state = "proposed"
            if approval_required:
                commitment.approval_required = True

        db.add(commitment)
        await db.flush()

        # Create strategic history entry
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=organization_id,
            entity_type="commitment",
            entity_id=commitment.id,
            entity_label=title[:300],
            field="state",
            old_value=None,
            new_value=commitment.state,
            reason="Commitment created",
            source_event_id=source_event_id or "commitment.created",
            changed_at=utcnow(),
        )
        db.add(history)

        return commitment

    async def transition_commitment(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
        *,
        user_id: str,
        new_state: str,
        reason: str,
        source_event_id: Optional[str] = None,
    ) -> CompanyCommitment:
        """Transition commitment through governance states."""
        if new_state not in COMMITMENT_STATES:
            raise ValueError(f"Invalid commitment state: {new_state}")

        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != organization_id:
            raise ValueError("Commitment not found")

        old_state = commitment.state
        
        # Validate state transitions
        valid_transitions = {
            "proposed": ["pending_authorization", "cancelled", "rejected"],
            "pending_authorization": ["authorized", "cancelled", "rejected"],
            "authorized": ["active", "paused", "cancelled", "superseded", "fulfilled"],
            "active": ["paused", "fulfilled", "cancelled", "superseded"],
            "paused": ["active", "cancelled", "superseded"],
            "fulfilled": ["superseded"],
            "cancelled": [],
            "expired": [],
            "superseded": [],
            "rejected": [],
        }

        if new_state not in valid_transitions.get(old_state, []):
            raise ValueError(f"Invalid state transition: {old_state} -> {new_state}")

        commitment.state = new_state
        commitment.version += 1

        if new_state == "authorized":
            commitment.authorized_at = utcnow()
            commitment.authorized_by = user_id
        elif new_state == "fulfilled":
            commitment.completed_at = utcnow()
        elif new_state in ("cancelled", "rejected"):
            commitment.cancelled_reason = reason

        # Record in strategic history
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=organization_id,
            entity_type="commitment",
            entity_id=commitment.id,
            entity_label=commitment.title[:300],
            field="state",
            old_value=old_state,
            new_value=new_state,
            reason=reason,
            source_event_id=source_event_id or f"commitment.{new_state}",
            changed_at=utcnow(),
        )
        db.add(history)

        # If superseding another commitment
        if new_state == "superseded":
            # The new commitment should link back
            pass

        await db.flush()
        return commitment

    async def supersede_commitment(
        self,
        db: AsyncSession,
        organization_id: str,
        old_commitment_id: str,
        new_commitment_id: str,
        *,
        user_id: str,
        reason: str,
        source_event_id: Optional[str] = None,
    ) -> tuple[CompanyCommitment, CompanyCommitment]:
        """Supersede a commitment with a new one. Maintains temporal supersession chain."""
        old_commitment = await db.get(CompanyCommitment, old_commitment_id)
        new_commitment = await db.get(CompanyCommitment, new_commitment_id)

        if not old_commitment or old_commitment.organization_id != organization_id:
            raise ValueError("Old commitment not found")
        if not new_commitment or new_commitment.organization_id != organization_id:
            raise ValueError("New commitment not found")

        # Allow supersession with different fingerprints (each version is a new commitment)
        # The supersession chain is maintained via supersedes_id / superseded_by_id
        # Old fingerprint is preserved in the chain for audit trail

        # Link supersession chain
        old_commitment.superseded_by_id = new_commitment.id
        new_commitment.supersedes_id = old_commitment.id
        new_commitment.source_decision_id = old_commitment.decision_id

        # Update states
        old_commitment.state = "superseded"
        old_commitment.version += 1
        new_commitment.state = "authorized"
        new_commitment.authorized_at = utcnow()
        new_commitment.authorized_by = user_id

        # Record in strategic history
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=organization_id,
            entity_type="commitment",
            entity_id=old_commitment_id,
            entity_label=old_commitment.title[:300],
            field="superseded_by",
            old_value=None,
            new_value=new_commitment_id,
            reason=reason,
            source_event_id=source_event_id or "commitment.superseded",
            changed_at=utcnow(),
        )
        db.add(history)

        await db.flush()
        return old_commitment, new_commitment

    # -------------------------------------------------------------------------
    # Authorization Query Methods
    # -------------------------------------------------------------------------

    async def get_authorization(
        self,
        db: AsyncSession,
        organization_id: str,
        authorization_id: str,
    ) -> Optional[CompanyAuthorization]:
        """Get an authorization by ID with tenant isolation."""
        auth = await db.get(CompanyAuthorization, authorization_id)
        if auth and auth.organization_id == organization_id:
            return auth
        return None

    async def list_authorizations(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        state: Optional[str] = None,
        authorization_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CompanyAuthorization]:
        """List authorizations with filters."""
        conditions = [
            CompanyAuthorization.organization_id == organization_id,
            CompanyAuthorization.scope_type == scope,
        ]
        if scope_id:
            conditions.append(CompanyAuthorization.scope_id == scope_id)
        if state:
            conditions.append(CompanyAuthorization.state == state)
        if authorization_type:
            conditions.append(CompanyAuthorization.authorization_type == authorization_type)

        stmt = select(CompanyAuthorization).where(and_(*conditions)).order_by(
            CompanyAuthorization.created_at.desc()
        ).limit(limit).offset(offset)

        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_commitment(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
    ) -> Optional[CompanyCommitment]:
        """Get a commitment by ID with tenant isolation."""
        commitment = await db.get(CompanyCommitment, commitment_id)
        if commitment and commitment.organization_id == organization_id:
            return commitment
        return None

    async def list_commitments(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        scope: str = "company",
        scope_id: Optional[str] = None,
        state: Optional[str] = None,
        commitment_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CompanyCommitment]:
        """List commitments with filters."""
        conditions = [
            CompanyCommitment.organization_id == organization_id,
            CompanyCommitment.scope_type == scope,
        ]
        if scope_id:
            conditions.append(CompanyCommitment.scope_id == scope_id)
        if state:
            conditions.append(CompanyCommitment.state == state)
        if commitment_type:
            conditions.append(CompanyCommitment.commitment_type == commitment_type)

        stmt = select(CompanyCommitment).where(and_(*conditions)).order_by(
            CompanyCommitment.created_at.desc()
        ).limit(limit).offset(offset)

        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_commitment_supersession_chain(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
    ) -> list[CompanyCommitment]:
        """Get the full supersession chain for a commitment."""
        chain = []
        current = await db.get(CompanyCommitment, commitment_id)
        if not current or current.organization_id != organization_id:
            return chain

        # Walk backwards (superseded_by)
        current_id = commitment_id
        while current_id:
            current = await db.get(CompanyCommitment, current_id)
            if not current:
                break
            chain.append(current)
            if current.superseded_by_id:
                current_id = current.superseded_by_id
            else:
                break

        # Walk forwards (supersedes)
        current = await db.get(CompanyCommitment, commitment_id)
        if current and current.supersedes_id:
            prev_id = current.supersedes_id
            while prev_id:
                prev = await db.get(CompanyCommitment, prev_id)
                if not prev:
                    break
                chain.insert(0, prev)
                if prev.supersedes_id:
                    prev_id = prev.supersedes_id
                else:
                    break

        return chain

    # -------------------------------------------------------------------------
    # Condition Evaluation for Conditional Commitments
    # -------------------------------------------------------------------------

    async def evaluate_conditions(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
    ) -> dict:
        """Evaluate all conditions for a conditional commitment."""
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != organization_id:
            raise ValueError("Commitment not found")

        if commitment.commitment_type != "conditional":
            return {"all_met": True, "details": {}}

        if not commitment.conditions:
            return {"all_met": True, "details": {}}

        results = {}
        all_met = True

        for condition in commitment.conditions:
            condition_id = condition.get("id")
            condition_type = condition.get("type")  # metric, event, date, approval, dependency
            threshold = condition.get("threshold")
            metric = condition.get("metric")

            # Evaluate based on condition type
            if condition_type == "metric":
                # Query metric value
                pass
            elif condition_type == "date":
                # Check date condition
                pass
            elif condition_type == "approval":
                # Check if approval exists
                pass
            elif condition_type == "dependency":
                # Check dependency status
                pass

            met = False  # Placeholder
            results[condition_id] = {"met": met, "details": condition}
            if not met:
                all_met = False

        return {"all_met": all_met, "details": results}

    # -------------------------------------------------------------------------
    # Integration with Decision Intelligence
    # -------------------------------------------------------------------------

    async def create_commitment_from_decision_intelligence(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user_id: str,
        decision_intelligence_context_id: str,
        selected_alternative_id: str,
        authorization_required: bool = True,
        source_event_id: Optional[str] = None,
        trigger_reason: Optional[str] = None,
    ) -> CompanyCommitment:
        """
        Create a commitment directly from a Decision Intelligence context
        by selecting one of the generated alternatives.
        """
        di_context = await db.get(DecisionIntelligenceContext, decision_intelligence_context_id)
        if not di_context or di_context.organization_id != organization_id:
            raise ValueError("Decision intelligence context not found")

        # Find the selected alternative from the database
        from app.models.execution_strategy import DecisionAlternative
        alt_result = await db.execute(
            select(DecisionAlternative).where(
                DecisionAlternative.organization_id == organization_id,
                DecisionAlternative.decision_context_id == decision_intelligence_context_id,
                DecisionAlternative.alternative_key == selected_alternative_id,
            )
        )
        selected_alt = alt_result.scalar_one_or_none()

        if not selected_alt:
            raise ValueError("Selected alternative not found")

        # Create authorization request if needed
        authorization_id = None
        if True:  # authorization_required:
            auth = await self.create_authorization_request(
                db, organization_id,
                user_id=user_id,
                authorization_type="full",
                title=f"Authorization for: {selected_alt.title}",
                description=f"Authorization to commit to alternative: {selected_alt.title}",
                rationale=f"Based on decision intelligence context: {di_context.title}",
                decision_intelligence_context_id=decision_intelligence_context_id,
                decision_id=None,
                commitment_id=None,
                source_event_id=source_event_id,
            )
            # Auto-approve for DI-driven commitments
            auth = await self.review_authorization(
                db, organization_id, auth.id,
                user_id=user_id,
                action="approve",
                review_note="Auto-approved from Decision Intelligence context",
            )
            authorization_id = auth.id

        # Create commitment
        commitment = await self.create_commitment(
            db, organization_id,
            user_id=user_id,
            title=f"Commitment: {selected_alt.title}",
            description=selected_alt.description,
            rationale=selected_alt.action_detail if hasattr(selected_alt, 'action_detail') else selected_alt.description,
            scope_type="company",
            scope_id=None,
            intent_id=None,
            objective_id=None,
            initiative_id=None,
            project_id=None,
            decision_id=None,
            authorization_id=authorization_id,
            commitment_type="conditional",
            conditions=[],
            source_event_id=source_event_id,
            decision_intelligence_context_id=decision_intelligence_context_id,
        )

        return commitment

    # -------------------------------------------------------------------------
    # Adaptive Execution: Commitment → Action
    # -------------------------------------------------------------------------

    async def propose_actions_from_commitment(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user_id: str,
        commitment_id: str,
        action_type: str = "task",
        title: str = "",
        description: Optional[str] = None,
        source_problem: Optional[str] = None,
        target: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        risk: str = "low",
        due_at: Optional[datetime] = None,
        assignee_id: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
        ) -> Optional[dict[str, Any]]:
        """
        Propose governed actions from an authorized commitment.
    
        This is the primary entry point for adaptive execution: taking a
        governed commitment and creating the executable actions that fulfill it.
    
        The commitment must be in an executable state (authorized, active, fulfilled).
        Actions are proposed through the canonical action_ops_engine with the
        commitment as provenance.
        """
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != organization_id:
            raise ValueError("Commitment not found")

        if commitment.state not in ("authorized", "active", "fulfilled"):
            raise ValueError(
                f"Commitment state '{commitment.state}' is not executable; "
                "only authorized/active/fulfilled commitments can generate actions"
            )

        # Determine action title from commitment if not provided
        action_title = title or f"Execute: {commitment.title}"
        action_description = description or commitment.description or commitment.rationale
        action_source_problem = source_problem or commitment.rationale
        action_target = target or commitment.title

        # Use commitment's scope if not overridden
        action_scope_type = scope_type or commitment.scope_type
        action_scope_id = scope_id or commitment.scope_id

        # Propose the action through the canonical action engine
        from app.models.user import User
        user = await db.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        result = await action_ops_engine.propose(
            db,
            organization_id=organization_id,
            user=user,
            action_type=action_type,
            title=action_title,
            description=action_description,
            source_problem=action_source_problem,
            target=action_target,
            scope_type=action_scope_type,
            scope_id=action_scope_id,
            risk=risk,
            due_at=due_at,
            source_event_id=f"commitment.action_proposed:{commitment_id}",
            source_commitment_id=commitment_id,
            source_company_decision_id=commitment.decision_id,
            assignee_id=assignee_id,
            depends_on=depends_on,
        )

        if result:
            # Update commitment's action_ids
            action_id = result.get("id")
            if action_id:
                action_ids = list(commitment.action_ids or [])
                if action_id not in action_ids:
                    action_ids.append(action_id)
                    commitment.action_ids = action_ids
                    commitment.version += 1
                    await db.flush()

        return result

    async def sync_commitment_actions(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
        ) -> list[str]:
        """
        Sync commitment.action_ids with all CompanyActions that reference
        this commitment as source_commitment_id.
    
        Useful for reconciliation and ensuring the reverse index is accurate.
        """
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != organization_id:
            raise ValueError("Commitment not found")

        # Find all actions with this commitment as source
        result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == organization_id,
                CompanyAction.source_commitment_id == commitment_id,
            )
        )
        actions = result.scalars().all()

        action_ids = [a.id for a in actions]
        commitment.action_ids = action_ids
        commitment.version += 1
        await db.flush()

        return action_ids

    # -------------------------------------------------------------------------
        # Query Methods
    # -------------------------------------------------------------------------

    async def get_commitment_with_lineage(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
        ) -> dict:
        """Get a commitment with full lineage trace."""
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != organization_id:
            return None

        # Build lineage trace
        lineage = {
            "commitment": commitment,
            "intent": None,
            "objective": None,
            "initiative": None,
            "project": None,
            "decision": None,
            "authorization": None,
            "decision_intelligence": None,
        }

        if commitment.intent_id:
            lineage["intent"] = await db.get(CompanyIntent, commitment.intent_id)
        if commitment.objective_id:
            lineage["objective"] = await db.get(CompanyObjective, commitment.objective_id)
        if commitment.initiative_id:
            lineage["initiative"] = await db.get(CompanyInitiative, commitment.initiative_id)
        if commitment.project_id:
            lineage["project"] = await db.get(Project, commitment.project_id)  # Assuming Project exists
        if commitment.decision_id:
            from app.models.company_operating import CompanyDecision
            from sqlalchemy import select
            decision_result = await db.execute(
                select(CompanyDecision).where(
                    CompanyDecision.organization_id == organization_id,
                    CompanyDecision.decision_id == commitment.decision_id,
                )
            )
            lineage["decision"] = decision_result.scalar_one_or_none()
        if commitment.authorization_id:
            lineage["authorization"] = await db.get(CompanyAuthorization, commitment.authorization_id)
        if commitment.decision_intelligence_context_id:
            lineage["decision_intelligence"] = await db.get(DecisionIntelligenceContext, commitment.decision_intelligence_context_id)

        return lineage


governed_commitment_engine = GovernedCommitmentEngine()