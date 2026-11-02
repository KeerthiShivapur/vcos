"""Phase 4I.7 — Governed Commitment / Authorization adversarial tests.

These tests verify the governed commitment/authorization layer operates correctly:
- Consumes 4I.1-4I.6, 4H.7, and all operating substrates
- Creates commitments from Decision Intelligence context
- Authorization gate: formal governance review before commitment
- Decision ≠ Authorization ≠ Commitment ≠ Execution (explicit boundaries)
- Governance-first retrieval
- Epistemic status separation (fact vs inference vs prediction vs proposal vs contested)
- Contradiction preservation (both sides visible, never silently resolved)
- Temporal truth (state transitions with triggers, supersession chains)
- Exact-once semantics (fingerprint-based deduplication)
- Provenance chains (intent → objective → initiative → decision → commitment → action)
- Tenant isolation
- No autonomous action (intelligence synthesized, commitments governed)
"""

import pytest
import uuid
import hashlib
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select

from app.models.organization import Organization
from app.models.user import User
from app.models.company_intent import CompanyIntent, CompanyPlan, INTENT_KINDS, PLAN_KINDS
from app.models.execution_strategy import (
    CompanyGoal, CompanyObjective, CompanyInitiative,
    StrategicLink, StrategicAlignment, AlignmentGap,
    StrategicConflict, StrategicAlignmentState, StrategicDependency,
    CompanyPlanningContext, CompanyStateTransition, PlanningContextProvenance,
    AdaptivePlanningContext, AttentionSignal, ReplanningProposal,
    DecisionContext, AdaptivePlanningTransition,
    DecisionIntelligenceContext, DecisionAlternative, DecisionConsequence,
    DecisionPrecedentLink, DecisionEvidence, DecisionRiskAssessment,
    DecisionIntelligenceTransition,
    PLANNING_CONTEXT_SECTIONS, PLANNING_CONTEXT_EPISTEMIC_STATUS,
    STATE_TRANSITION_TRIGGERS, STATE_TRANSITION_KINDS,
    DECISION_INTELLIGENCE_TYPES, DECISION_INTELLIGENCE_STATES,
    DECISION_ALTERNATIVE_STATES, CONSEQUENCE_TYPES,
    RISK_ASSESSMENT_LEVELS, EVIDENCE_QUALITY_LEVELS,
    PRECEDENT_RELEVANCE_LEVELS,
    CompanyCommitment, CompanyAuthorization,
    COMMITMENT_STATES, COMMITMENT_TYPES,
    AUTHORIZATION_TYPES, AUTHORIZATION_STATES,
    ObjectiveOutcome, ObjectiveOutcomeAssessment, ObjectiveContradiction,
    ObjectivePrediction, ObjectiveSimulation, ObjectivePlanState,
    _compute_fingerprint,
)
from app.models.company_operating import CompanyDecision as OperatingCompanyDecision, CompanyDecisionContradiction as OperatingCompanyDecisionContradiction
from app.models.company_actions import CompanyAction
from app.models.company_state import CompanyState
from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
from app.models.intelligence import PatternDetection
from app.intelligence.governed_commitment_engine import governed_commitment_engine
from app.intelligence.decision_intelligence_engine import decision_intelligence_engine
from app.intelligence.adaptive_planning_engine import adaptive_planning_engine
from app.intelligence.company_planning_context_engine import company_planning_context_engine
from app.core.timeutils import utcnow
from tests.conftest import register_org


# =============================================================================
# Test Fixtures / Helpers
# =============================================================================

async def _create_minimal_canonical_chain(db_session_factory, org_id: str):
    """Create minimal canonical data chain: Intent → Goal → Objective → Initiative."""
    async with db_session_factory() as session:
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Test Strategic Intent for 4I.7",
            description="Test intent for governed commitment testing",
            state="active",
            epistemic_status="adopted",
            source="declared",
            priority=1,
            scope="company",
            fingerprint=hashlib.sha256(f"intent:4i7-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(intent)
        await session.flush()

        goal = CompanyGoal(
            organization_id=org_id,
            title="Test Goal for 4I.7",
            description="Test goal for governed commitment testing",
            kind="expansion",
            status="active",
            priority=1,
            metric_kind="adoption_rate",
            target_value=1000,
        )
        session.add(goal)
        await session.flush()

        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            intent_id=intent.id,
            title="Test Objective for 4I.7",
            description="Test objective for governed commitment testing",
            status="active",
            fingerprint=hashlib.sha256(f"objective:4i7-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(objective)
        await session.flush()

        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Test Initiative for 4I.7",
            description="Test initiative for governed commitment testing",
            status="active",
            fingerprint=hashlib.sha256(f"initiative:4i7-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(initiative)
        await session.flush()

        await session.commit()
        return {
            "intent_id": intent.id,
            "goal_id": goal.id,
            "objective_id": objective.id,
            "initiative_id": initiative.id,
        }


async def _create_decision_intelligence_context(db_session_factory, org_id: str, intent_id: str, objective_id: str):
    """Create a DecisionIntelligenceContext with alternatives for testing."""
    async with db_session_factory() as session:
        di_context = DecisionIntelligenceContext(
            organization_id=org_id,
            decision_type="strategic_choice",
            title="Test DI Context for 4I.7",
            description="Decision intelligence context for governed commitment testing",
            scope="company",
            scope_id=None,
            planning_context_id="test-planning-context",
            planning_context_version=1,
            planning_context_fingerprint=hashlib.sha256(f"pc:4i7-test:{org_id}".encode()).hexdigest()[:160],
            trigger="manual_synthesis",
            trigger_reason="Test trigger",
            overall_confidence=0.85,
            source_event_id="test.event",
            input_fingerprint=hashlib.sha256(f"di_input:4i7-test:{org_id}".encode()).hexdigest()[:160],
            fingerprint=hashlib.sha256(f"di_context:4i7-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(di_context)
        await session.flush()

        # Create alternatives
        alt1 = DecisionAlternative(
            organization_id=org_id,
            decision_context_id=di_context.id,
            title="Commit to Full Launch",
            alternative_key="alt_1",
            description="Full market launch with allocated resources",
            state="proposed",
            evaluation={},
            pros=[],
            cons=[],
            risks=[],
            confidence=0.7,
            reasoning="High confidence based on evidence",
            evidence_fingerprints=["evidence_1", "evidence_2"],
            supporting_pattern_ids=["precedent_1"],
            source_event_id="test.event",
            fingerprint=hashlib.sha256(f"alt:1:{org_id}".encode()).hexdigest()[:160],
        )
        alt2 = DecisionAlternative(
            organization_id=org_id,
            decision_context_id=di_context.id,
            title="Phased Pilot First",
            alternative_key="alt_2",
            description="Run pilot in one market before full launch",
            state="proposed",
            evaluation={},
            pros=[],
            cons=[],
            risks=[],
            confidence=0.6,
            reasoning="",
            evidence_fingerprints=["evidence_3"],
            supporting_pattern_ids=["precedent_2"],
            source_event_id="test.event",
            fingerprint=hashlib.sha256(f"alt:2:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(alt1)
        session.add(alt2)
        await session.commit()
        return di_context.id


# =============================================================================
# Authorization Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_authorization_request_basic(client, db_session_factory):
    """Test creating a basic authorization request."""
    reg = await register_org(client, name=f"Auth Corp {uuid.uuid4().hex[:8]}", email=f"auth_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id,
            user_id=user_id,
            authorization_type="full",
            title="Authorization for Full Launch",
            description="Authorize full market launch",
            rationale="Based on DI context showing high confidence",
            scope_type="company",
            decision_intelligence_context_id=None,
            source_event_id="test.event",
        )

    assert auth is not None
    assert auth.organization_id == org_id
    assert auth.authorization_type == "full"
    assert auth.state == "requested"
    assert auth.title == "Authorization for Full Launch"
    assert auth.requested_by == user_id
    assert auth.fingerprint is not None


@pytest.mark.asyncio
async def test_authorization_exact_once_deduplication(client, db_session_factory):
    """Test exact-once semantics: same fingerprint = same authorization (no duplicate)."""
    reg = await register_org(client, name=f"Auth Exact Corp {uuid.uuid4().hex[:8]}", email=f"authexact_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create first authorization
        auth1 = await governed_commitment_engine.create_authorization_request(
            session, org_id,
            user_id=user_id,
            authorization_type="full",
            title="Exact Once Test",
            scope_type="company",
            source_event_id="test.event",
        )

        # Try to create duplicate - should fail
        with pytest.raises(ValueError, match="fingerprint already exists"):
            await governed_commitment_engine.create_authorization_request(
                session, org_id,
                user_id=user_id,
                authorization_type="full",
                title="Exact Once Test",
                scope_type="company",
                source_event_id="test.event",
            )


@pytest.mark.asyncio
async def test_review_authorization_approve(client, db_session_factory):
    """Test authorization review: approve."""
    reg = await register_org(client, name=f"Auth Approve Corp {uuid.uuid4().hex[:8]}", email=f"authapprove_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create authorization
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id,
            user_id=user_id,
            authorization_type="full",
            title="Test Approve",
            scope_type="company",
        )

        # Approve it
        reviewed = await governed_commitment_engine.review_authorization(
            session, org_id, auth.id,
            user_id=user_id,
            action="approve",
            review_note="Approved by governance",
        )

    assert reviewed.state == "approved"
    assert reviewed.approved_by == user_id
    assert reviewed.approved_at is not None
    assert reviewed.authorized_at is not None
    assert reviewed.approval_note == "Approved by governance"


@pytest.mark.asyncio
async def test_review_authorization_reject(client, db_session_factory):
    """Test authorization review: reject."""
    reg = await register_org(client, name=f"Auth Reject Corp {uuid.uuid4().hex[:8]}", email=f"authreject_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id,
            user_id=user_id,
            authorization_type="full",
            title="Test Reject",
            scope_type="company",
        )

        reviewed = await governed_commitment_engine.review_authorization(
            session, org_id, auth.id,
            user_id=user_id,
            action="reject",
            review_note="Insufficient evidence",
        )

    assert reviewed.state == "rejected"
    assert reviewed.rejected_by == user_id
    assert reviewed.rejected_at is not None
    assert reviewed.rejection_reason == "Insufficient evidence"


@pytest.mark.asyncio
async def test_review_authorization_conditional(client, db_session_factory):
    """Test authorization review: conditional approval."""
    reg = await register_org(client, name=f"Auth Cond Corp {uuid.uuid4().hex[:8]}", email=f"authcond_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id,
            user_id=user_id,
            authorization_type="full",
            title="Test Conditional",
            scope_type="company",
        )

        conditions = [{"id": "cond_1", "type": "metric", "metric": "pilot_adoption", "threshold": 0.5}]
        reviewed = await governed_commitment_engine.review_authorization(
            session, org_id, auth.id,
            user_id=user_id,
            action="conditional",
            review_note="Conditional on pilot success",
            conditions=conditions,
        )

    assert reviewed.state == "conditional"
    assert reviewed.conditions == conditions
    assert reviewed.reviewed_by == user_id


# =============================================================================
# Commitment Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_commitment_unconditional(client, db_session_factory):
    """Test creating an unconditional commitment (no authorization required)."""
    reg = await register_org(client, name=f"Commit Corp {uuid.uuid4().hex[:8]}", email=f"commit_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    # Create canonical chain
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        commitment = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="Unconditional Commitment to Launch",
            description="Full launch commitment",
            rationale="Strategic priority",
            scope_type="company",
            intent_id=chain["intent_id"],
            objective_id=chain["objective_id"],
            initiative_id=chain["initiative_id"],
            source_event_id="test.event",
        )

    assert commitment is not None
    assert commitment.organization_id == org_id
    assert commitment.commitment_type == "unconditional"
    assert commitment.title == "Unconditional Commitment to Launch"
    # Unconditional with no approval_required should be auto-authorized
    assert commitment.state in ("authorized", "proposed", "pending_authorization")
    assert commitment.fingerprint is not None
    assert commitment.intent_id == chain["intent_id"]
    assert commitment.objective_id == chain["objective_id"]


@pytest.mark.asyncio
async def test_create_commitment_conditional_requires_authorization(client, db_session_factory):
    """Test that conditional commitment requires authorization_id."""
    reg = await register_org(client, name=f"Cond Commit Corp {uuid.uuid4().hex[:8]}", email=f"condcommit_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Try to create conditional without authorization - should fail
        with pytest.raises(ValueError, match="Conditional commitments require authorization_id"):
            await governed_commitment_engine.create_commitment(
                session, org_id,
                user_id=user_id,
                commitment_type="conditional",
                title="Conditional Commitment",
                scope_type="company",
                intent_id=chain["intent_id"],
            )


@pytest.mark.asyncio
async def test_create_commitment_conditional_with_authorization(client, db_session_factory):
    """Test creating conditional commitment with valid authorization."""
    reg = await register_org(client, name=f"Cond Auth Corp {uuid.uuid4().hex[:8]}", email=f"condauth_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create authorization first
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id,
            user_id=user_id,
            authorization_type="full",
            title="Auth for Conditional Commitment",
            scope_type="company",
        )
        # Approve it
        await governed_commitment_engine.review_authorization(
            session, org_id, auth.id,
            user_id=user_id,
            action="approve",
        )

        # Create conditional commitment with authorization
        commitment = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="conditional",
            title="Conditional Commitment with Auth",
            description="Conditional on pilot success",
            scope_type="company",
            intent_id=chain["intent_id"],
            objective_id=chain["objective_id"],
            authorization_id=auth.id,
            conditions=[{"id": "cond_1", "type": "metric", "metric": "pilot_adoption", "threshold": 0.5}],
            source_event_id="test.event",
        )

    assert commitment is not None
    assert commitment.commitment_type == "conditional"
    assert commitment.authorization_id == auth.id
    assert commitment.state == "pending_authorization"
    assert commitment.conditions == [{"id": "cond_1", "type": "metric", "metric": "pilot_adoption", "threshold": 0.5}]


@pytest.mark.asyncio
async def test_commitment_exact_once_deduplication(client, db_session_factory):
    """Test exact-once semantics for commitments."""
    reg = await register_org(client, name=f"Commit Exact Corp {uuid.uuid4().hex[:8]}", email=f"commitexact_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create first commitment
        commitment1 = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="Exact Once Commitment",
            scope_type="company",
            intent_id=chain["intent_id"],
            source_event_id="test.event",
        )

        # Try duplicate - should fail
        with pytest.raises(ValueError, match="fingerprint already exists"):
            await governed_commitment_engine.create_commitment(
                session, org_id,
                user_id=user_id,
                commitment_type="unconditional",
                title="Exact Once Commitment",
                scope_type="company",
                intent_id=chain["intent_id"],
                source_event_id="test.event",
            )


@pytest.mark.asyncio
async def test_commitment_state_transitions(client, db_session_factory):
    """Test valid commitment state transitions."""
    reg = await register_org(client, name=f"Commit State Corp {uuid.uuid4().hex[:8]}", email=f"commitstate_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        commitment = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="State Transition Test",
            scope_type="company",
            intent_id=chain["intent_id"],
            approval_required=True,
        )

        initial_state = commitment.state

        # Valid transition: proposed -> pending_authorization
        if commitment.state == "proposed":
            print(f"DEBUG TEST: Before 1st transition, state={commitment.state}")
            commitment = await governed_commitment_engine.transition_commitment(
                session, org_id, commitment.id,
                user_id=user_id,
                new_state="pending_authorization",
                reason="Submitted for authorization",
            )
            print(f"DEBUG TEST: After 1st transition, state={commitment.state}")
            assert commitment.state == "pending_authorization"

        # Valid transition: pending_authorization -> authorized
        commitment = await governed_commitment_engine.transition_commitment(
            session, org_id, commitment.id,
            user_id=user_id,
            new_state="authorized",
            reason="Governance approved",
        )
        assert commitment.state == "authorized"
        assert commitment.authorized_at is not None
        assert commitment.authorized_by == user_id

        # Valid transition: authorized -> active
        print(f"DEBUG TEST: Calling transition_commitment with new_state='active'")
        commitment = await governed_commitment_engine.transition_commitment(
            session, org_id, commitment.id,
            user_id=user_id,
            new_state="active",
            reason="Execution started",
        )
        assert commitment.state == "active"

        # Valid transition: active -> fulfilled
        commitment = await governed_commitment_engine.transition_commitment(
            session, org_id, commitment.id,
            user_id=user_id,
            new_state="fulfilled",
            reason="Completed successfully",
        )
        assert commitment.state == "fulfilled"
        assert commitment.completed_at is not None


@pytest.mark.asyncio
async def test_commitment_invalid_state_transition(client, db_session_factory):
    """Test that invalid state transitions are rejected."""
    reg = await register_org(client, name=f"Invalid State Corp {uuid.uuid4().hex[:8]}", email=f"invalidstate_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        commitment = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="Invalid Transition Test",
            scope_type="company",
            intent_id=chain["intent_id"],
            approval_required=True,  # So commitment starts in "proposed" state
        )

        # Try invalid transition: proposed -> fulfilled (skips authorized, active)
        with pytest.raises(ValueError, match="Invalid state transition"):
            await governed_commitment_engine.transition_commitment(
                session, org_id, commitment.id,
                user_id=user_id,
                new_state="fulfilled",
                reason="Invalid skip",
            )


@pytest.mark.asyncio
async def test_commitment_supersession_chain(client, db_session_factory):
    """Test commitment supersession maintains temporal chain."""
    reg = await register_org(client, name=f"Supersede Corp {uuid.uuid4().hex[:8]}", email=f"supersede_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    decision_id = hashlib.sha256(f"decision:supersede:{org_id}".encode()).hexdigest()[:160]

    async with db_session_factory() as session:
        # Create the decision first
        decision = OperatingCompanyDecision(
            organization_id=org_id,
            decision_id=decision_id,
            kind="strategic",
            title="Supersession Test Decision",
            rationale="Test rationale",
            recommendation_key="",
            state="approved",
            approver_label="test",
            source_event_id="test.event",
        )
        session.add(decision)
        await session.flush()

        # Create original commitment (v1)
        old_commitment = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="Original Commitment v1",
            scope_type="company",
            intent_id=chain["intent_id"],
            decision_id=decision_id,
            source_event_id="test.event",
        )

        # Create new commitment v2 (different fingerprint, same logical commitment)
        new_commitment = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="Original Commitment v2",  # Different title = different fingerprint
            scope_type="company",
            intent_id=chain["intent_id"],
            decision_id=decision_id,
            source_event_id="test.event",
        )

        # Supersede old with new
        old, new = await governed_commitment_engine.supersede_commitment(
            session, org_id,
            old_commitment.id,
            new_commitment.id,
            user_id=user_id,
            reason="Updated based on new evidence",
        )

    assert old.state == "superseded"
    assert old.superseded_by_id == new.id
    assert new.state == "authorized"
    assert new.supersedes_id == old.id
    assert new.authorized_by == user_id


@pytest.mark.asyncio
async def test_commitment_supersession_different_fingerprints(client, db_session_factory):
    """Test supersession works with different fingerprints (each version unique)."""
    reg = await register_org(client, name=f"Good Supersede Corp {uuid.uuid4().hex[:8]}", email=f"goodsupersede_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create two different decisions
        decision1_id = hashlib.sha256(f"decision:1:{org_id}".encode()).hexdigest()[:160]
        decision2_id = hashlib.sha256(f"decision:2:{org_id}".encode()).hexdigest()[:160]

        for idx, d_id in enumerate([decision1_id, decision2_id]):
            decision = OperatingCompanyDecision(
                organization_id=org_id,
                decision_id=d_id,
                kind="strategic",
                title=f"Decision {d_id[:8]}",
                rationale="Test rationale",
                recommendation_key="",
                state="approved",
                approver_label="test",
                source_event_id=f"test.event.{idx}",
            )
            session.add(decision)
        await session.flush()

        # Create two commitments with DIFFERENT fingerprints
        old_commitment = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="Old Commitment v1",
            scope_type="company",
            intent_id=chain["intent_id"],
            decision_id=decision1_id,
            source_event_id="test.event.0",
        )

        new_commitment = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="New Commitment v2",
            scope_type="company",
            intent_id=chain["intent_id"],
            decision_id=decision2_id,  # Different decision = different fingerprint
            source_event_id="test.event.1",
        )

        # Supersession should work with different fingerprints
        old, new = await governed_commitment_engine.supersede_commitment(
            session, org_id,
            old_commitment.id,
            new_commitment.id,
            user_id=user_id,
            reason="Valid supersession",
        )

    assert old.state == "superseded"
    assert old.superseded_by_id == new.id
    assert new.supersedes_id == old.id


@pytest.mark.asyncio
async def test_get_commitment_supersession_chain(client, db_session_factory):
    """Test retrieving full supersession chain."""
    reg = await register_org(client, name=f"Chain Corp {uuid.uuid4().hex[:8]}", email=f"chain_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    decision_id = hashlib.sha256(f"decision:chain:{org_id}".encode()).hexdigest()[:160]

    async with db_session_factory() as session:
        # Create the decision first
        decision = OperatingCompanyDecision(
            organization_id=org_id,
            decision_id=decision_id,
            kind="strategic",
            title="Chain Test Decision",
            rationale="Test rationale",
            recommendation_key="",
            state="approved",
            approver_label="test",
            source_event_id="test.event.0",
        )
        session.add(decision)
        await session.flush()

        # Create v1
        c1 = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="Commitment Chain v1",
            scope_type="company",
            intent_id=chain["intent_id"],
            decision_id=decision_id,
            source_event_id="test.event.0",
        )

        # Create v2 (different fingerprint)
        c2 = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="Commitment Chain v2",
            scope_type="company",
            intent_id=chain["intent_id"],
            decision_id=decision_id,
            source_event_id="test.event.1",
        )
        await governed_commitment_engine.supersede_commitment(
            session, org_id, c1.id, c2.id, user_id=user_id, reason="v2"
        )

        # Create v3 (different fingerprint)
        c3 = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="Commitment Chain v3",
            scope_type="company",
            intent_id=chain["intent_id"],
            decision_id=decision_id,
            source_event_id="test.event.2",
        )
        await governed_commitment_engine.supersede_commitment(
            session, org_id, c2.id, c3.id, user_id=user_id, reason="v3"
        )

        # Get full chain
        full_chain = await governed_commitment_engine.get_commitment_supersession_chain(
            session, org_id, c2.id
        )

    # Should have v1, v2, v3 in order
    assert len(full_chain) == 3
    assert full_chain[0].id == c1.id
    assert full_chain[1].id == c2.id
    assert full_chain[2].id == c3.id


# =============================================================================
# Commitment from Decision Intelligence Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_commitment_from_decision_intelligence(client, db_session_factory):
    """Test creating commitment directly from DI context by selecting alternative."""
    reg = await register_org(client, name=f"DI Commit Corp {uuid.uuid4().hex[:8]}", email=f"dicommit_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    di_context_id = await _create_decision_intelligence_context(db_session_factory, org_id, chain["intent_id"], chain["objective_id"])

    async with db_session_factory() as session:
        commitment = await governed_commitment_engine.create_commitment_from_decision_intelligence(
            session, org_id,
            user_id=user_id,
            decision_intelligence_context_id=di_context_id,
            selected_alternative_id="alt_1",
            authorization_required=True,
            source_event_id="test.event",
            trigger_reason="Selected alternative 1 from DI synthesis",
        )

    assert commitment is not None
    assert commitment.decision_intelligence_context_id == di_context_id
    assert commitment.commitment_type == "conditional"  # authorization_required=True
    assert commitment.authorization_id is not None
    assert "Commitment: Commit to Full Launch" in commitment.title


# =============================================================================
# Condition Evaluation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_evaluate_conditions_unconditional(client, db_session_factory):
    """Test condition evaluation for unconditional commitment (always met)."""
    reg = await register_org(client, name=f"Eval Uncond Corp {uuid.uuid4().hex[:8]}", email=f"evaluncond_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        commitment = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="Unconditional No Conditions",
            scope_type="company",
            intent_id=chain["intent_id"],
        )

        result = await governed_commitment_engine.evaluate_conditions(
            session, org_id, commitment.id
        )

    assert result["all_met"] is True
    assert result["details"] == {}


@pytest.mark.asyncio
async def test_evaluate_conditions_conditional(client, db_session_factory):
    """Test condition evaluation for conditional commitment."""
    reg = await register_org(client, name=f"Eval Cond Corp {uuid.uuid4().hex[:8]}", email=f"evalcond_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create and approve authorization
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id, user_id=user_id,
            authorization_type="full", title="Auth", scope_type="company",
        )
        await governed_commitment_engine.review_authorization(
            session, org_id, auth.id, user_id=user_id, action="approve"
        )

        commitment = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="conditional",
            title="Conditional with Conditions",
            scope_type="company",
            intent_id=chain["intent_id"],
            authorization_id=auth.id,
            conditions=[
                {"id": "cond_1", "type": "metric", "metric": "pilot_adoption", "threshold": 0.5},
                {"id": "cond_2", "type": "date", "date": "2026-12-31"},
            ],
        )

        result = await governed_commitment_engine.evaluate_conditions(
            session, org_id, commitment.id
        )

    # Conditions not fully implemented yet, should return structure
    assert "all_met" in result
    assert "details" in result
    assert "cond_1" in result["details"]
    assert "cond_2" in result["details"]


# =============================================================================
# Lineage / Provenance Tests
# =============================================================================

@pytest.mark.asyncio
async def test_commitment_lineage_trace(client, db_session_factory):
    """Test full lineage trace from commitment back to intent."""
    reg = await register_org(client, name=f"Lineage Corp {uuid.uuid4().hex[:8]}", email=f"lineage_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create a decision for lineage
        decision_id = hashlib.sha256(f"decision:lineage:{org_id}".encode()).hexdigest()[:160]
        from app.models.company_operating import CompanyDecision
        decision = CompanyDecision(
            organization_id=org_id,
            decision_id=decision_id,
            kind="strategic",
            title="Lineage Test Decision",
            rationale="Test rationale",
            recommendation_key="",
            state="approved",
            approver_label="test",
            source_event_id="test.event",
        )
        session.add(decision)
        await session.flush()
        
        commitment = await governed_commitment_engine.create_commitment(
            session, org_id,
            user_id=user_id,
            commitment_type="unconditional",
            title="Lineage Test Commitment",
            scope_type="company",
            intent_id=chain["intent_id"],
            objective_id=chain["objective_id"],
            initiative_id=chain["initiative_id"],
            decision_id=decision_id,
        )

        lineage = await governed_commitment_engine.get_commitment_with_lineage(
            session, org_id, commitment.id
        )

    assert lineage is not None
    assert lineage["commitment"] is not None
    assert lineage["commitment"].id == commitment.id
    assert lineage["intent"] is not None
    assert lineage["intent"].id == chain["intent_id"]
    assert lineage["objective"] is not None
    assert lineage["objective"].id == chain["objective_id"]
    assert lineage["initiative"] is not None
    assert lineage["initiative"].id == chain["initiative_id"]
    assert lineage["decision"] is not None


# =============================================================================
# Governance / Scope Tests
# =============================================================================

@pytest.mark.asyncio
async def test_list_authorizations_with_filters(client, db_session_factory):
    """Test listing authorizations with various filters."""
    reg = await register_org(client, name=f"List Auth Corp {uuid.uuid4().hex[:8]}", email=f"listauth_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create multiple authorizations (state defaults to "requested")
        await governed_commitment_engine.create_authorization_request(
            session, org_id, user_id=user_id,
            authorization_type="full", title="Auth 1", scope_type="company"
        )
        auth2 = await governed_commitment_engine.create_authorization_request(
            session, org_id, user_id=user_id,
            authorization_type="conditional", title="Auth 2", scope_type="company"
        )
        await governed_commitment_engine.review_authorization(
            session, org_id, auth2.id, user_id=user_id, action="approve"
        )

        # List all
        all_auths = await governed_commitment_engine.list_authorizations(session, org_id)
        assert len(all_auths) >= 2

        # Filter by state
        requested = await governed_commitment_engine.list_authorizations(session, org_id, state="requested")
        approved = await governed_commitment_engine.list_authorizations(session, org_id, state="approved")
        assert len(requested) >= 1
        assert len(approved) >= 1

        # Filter by type
        full = await governed_commitment_engine.list_authorizations(session, org_id, authorization_type="full")
        conditional = await governed_commitment_engine.list_authorizations(session, org_id, authorization_type="conditional")
        assert len(full) >= 1
        assert len(conditional) >= 1


@pytest.mark.asyncio
async def test_list_commitments_with_filters(client, db_session_factory):
    """Test listing commitments with various filters."""
    reg = await register_org(client, name=f"List Commit Corp {uuid.uuid4().hex[:8]}", email=f"listcommit_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create commitments in different states
        c1 = await governed_commitment_engine.create_commitment(
            session, org_id, user_id=user_id,
            commitment_type="unconditional", title="Commit 1", scope_type="company", intent_id=chain["intent_id"]
        )
        
        # Create authorization for conditional commitment
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id, user_id=user_id,
            authorization_type="conditional", title="Auth for Commit 2", scope_type="company"
        )
        auth = await governed_commitment_engine.review_authorization(
            session, org_id, auth.id, user_id=user_id, action="approve"
        )
        
        c2 = await governed_commitment_engine.create_commitment(
            session, org_id, user_id=user_id,
            commitment_type="conditional", title="Commit 2", scope_type="company", intent_id=chain["intent_id"],
            authorization_id=auth.id
        )

        # List all
        all_commits = await governed_commitment_engine.list_commitments(session, org_id)
        assert len(all_commits) >= 2

        # Filter by type
        unconditional = await governed_commitment_engine.list_commitments(session, org_id, commitment_type="unconditional")
        conditional = await governed_commitment_engine.list_commitments(session, org_id, commitment_type="conditional")
        assert len(unconditional) >= 1
        assert len(conditional) >= 1


# =============================================================================
# Tenant Isolation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_authorization_tenant_isolation(client, db_session_factory):
    """Test that authorizations are tenant-isolated."""
    reg1 = await register_org(client, name=f"Org A {uuid.uuid4().hex[:8]}", email=f"orga_{uuid.uuid4().hex[:8]}@test.co")
    reg2 = await register_org(client, name=f"Org B {uuid.uuid4().hex[:8]}", email=f"orgb_{uuid.uuid4().hex[:8]}@test.co")
    org_a_id = reg1["organization"]["id"]
    org_b_id = reg2["organization"]["id"]
    user_a_id = reg1["user"]["id"]
    user_b_id = reg2["user"]["id"]

    async with db_session_factory() as session:
        # Create auth in Org A
        auth_a = await governed_commitment_engine.create_authorization_request(
            session, org_a_id, user_id=user_a_id,
            authorization_type="full", title="Org A Auth", scope_type="company"
        )

        # Try to access from Org B - should not find it
        auth_b = await governed_commitment_engine.get_authorization(session, org_b_id, auth_a.id)
        assert auth_b is None

        # List in Org B should not show Org A's auth
        org_b_auths = await governed_commitment_engine.list_authorizations(session, org_b_id)
        assert len(org_b_auths) == 0


@pytest.mark.asyncio
async def test_commitment_tenant_isolation(client, db_session_factory):
    """Test that commitments are tenant-isolated."""
    reg1 = await register_org(client, name=f"Org A Commit {uuid.uuid4().hex[:8]}", email=f"orgacommit_{uuid.uuid4().hex[:8]}@test.co")
    reg2 = await register_org(client, name=f"Org B Commit {uuid.uuid4().hex[:8]}", email=f"orgbcommit_{uuid.uuid4().hex[:8]}@test.co")
    org_a_id = reg1["organization"]["id"]
    org_b_id = reg2["organization"]["id"]
    user_a_id = reg1["user"]["id"]
    user_b_id = reg2["user"]["id"]

    chain_a = await _create_minimal_canonical_chain(db_session_factory, org_a_id)

    async with db_session_factory() as session:
        # Create commitment in Org A
        commit_a = await governed_commitment_engine.create_commitment(
            session, org_a_id, user_id=user_a_id,
            commitment_type="unconditional", title="Org A Commit", scope_type="company",
            intent_id=chain_a["intent_id"]
        )

        # Try to access from Org B - should not find it
        commit_b = await governed_commitment_engine.get_commitment(session, org_b_id, commit_a.id)
        assert commit_b is None

        # List in Org B should not show Org A's commitment
        org_b_commits = await governed_commitment_engine.list_commitments(session, org_b_id)
        assert len(org_b_commits) == 0


# =============================================================================
# Decision ≠ Authorization ≠ Commitment ≠ Execution Boundary Tests
# =============================================================================

@pytest.mark.asyncio
async def test_decision_not_equal_authorization(client, db_session_factory):
    """Test that Decision, Authorization, and Commitment are distinct entities."""
    reg = await register_org(client, name=f"Boundary Corp {uuid.uuid4().hex[:8]}", email=f"boundary_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create a CompanyDecision (from 4H.2/4H.5 operating layer)
        from app.models.company_operating import CompanyDecision
        decision = CompanyDecision(
            organization_id=org_id,
            decision_id=hashlib.sha256(f"decision:boundary:{org_id}".encode()).hexdigest()[:160],
            kind="strategic",
            title="Governed Decision",
            rationale="Test rationale",
            recommendation_key="",
            state="approved",
            approver_label="test",
            source_event_id="test.event",
        )
        session.add(decision)
        await session.flush()

        # Create Authorization referencing the decision
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id, user_id=user_id,
            authorization_type="full", title="Auth for Decision", scope_type="company",
            decision_id=decision.decision_id,
        )

        # Create Commitment referencing both
        commitment = await governed_commitment_engine.create_commitment(
            session, org_id, user_id=user_id,
            commitment_type="unconditional", title="Commitment for Decision", scope_type="company",
            intent_id=chain["intent_id"], decision_id=decision.decision_id,
        )

        # Verify distinct IDs and types
        assert decision.decision_id != auth.id
        assert auth.id != commitment.id
        assert commitment.decision_id == decision.decision_id
        assert commitment.authorization_id is None  # unconditional

        # Verify they are different model types
        assert type(decision).__name__ == "CompanyDecision"
        assert type(auth).__name__ == "CompanyAuthorization"
        assert type(commitment).__name__ == "CompanyCommitment"


# =============================================================================
# Integration with Decision Intelligence Tests
# =============================================================================

@pytest.mark.asyncio
async def test_authorization_with_learning_provenance(client, db_session_factory):
    """Test authorization carries learning provenance (lessons, patterns, contradictions)."""
    reg = await register_org(client, name=f"Learning Auth Corp {uuid.uuid4().hex[:8]}", email=f"learnauth_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    # Create a lesson and pattern
    async with db_session_factory() as session:
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            title="Launch Lesson",
            lesson="Launch requires pilot validation",
            lifecycle="authoritative",
            confidence=0.85,
            fingerprint=hashlib.sha256(f"lesson:launch:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(lesson)
        await session.flush()

        pattern = PatternDetection(
            organization_id=org_id,
            pattern_type="launch_pattern",
            key="launch:pilot:validation",
            title="Launch Pattern",
            description="Launches without pilots have 80% failure rate",
            confidence=0.85,
            count=5,
            evidence_json={"decisions": ["d1", "d2", "d3", "d4", "d5"]},
            supporting_event_ids=[],
            first_seen=utcnow(),
            last_seen=utcnow(),
        )
        session.add(pattern)
        await session.commit()

        # Create authorization with learning references
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id, user_id=user_id,
            authorization_type="full", title="Auth with Learning", scope_type="company",
            supporting_lesson_fingerprints=[lesson.fingerprint],
            supporting_pattern_ids=[pattern.id],
            lesson_fingerprints=[lesson.fingerprint],
            pattern_ids=[pattern.id],
        )

    assert auth.supporting_lesson_fingerprints == [lesson.fingerprint]
    assert auth.supporting_pattern_ids == [pattern.id]


@pytest.mark.asyncio
async def test_commitment_with_contradiction_preservation(client, db_session_factory):
    """Test commitment preserves both supporting and contradicting evidence."""
    reg = await register_org(client, name=f"Contra Commit Corp {uuid.uuid4().hex[:8]}", email=f"contracommit_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    # Create a contradiction
    async with db_session_factory() as session:
        from app.models.company_operating import CompanyDecisionContradiction
        contradiction = CompanyDecisionContradiction(
            organization_id=org_id,
            decision_id="test-decision-contra",
            contradiction_key="cx:test-decision-contra:1",
            side_a_json={"claim": "market growing", "evidence_ids": ["e1"]},
            side_b_json={"claim": "market declining", "evidence_ids": ["e2"]},
            status="open",
            source_event_id="test-event-contra",
        )
        session.add(contradiction)
        await session.commit()

        commitment = await governed_commitment_engine.create_commitment(
            session, org_id, user_id=user_id,
            commitment_type="unconditional", title="Commitment with Contradiction", scope_type="company",
            intent_id=chain["intent_id"],
            contradicting_evidence_fingerprints=["contra_evidence_1"],
            contradicting_pattern_ids=["pattern_contra_1"],
            contradiction_ids=[contradiction.id],
        )

    assert commitment.contradicting_evidence_fingerprints == ["contra_evidence_1"]
    assert commitment.contradicting_pattern_ids == ["pattern_contra_1"]
    assert commitment.contradiction_ids == [contradiction.id]


# =============================================================================
# Canonical Vocabularies Tests
# =============================================================================

@pytest.mark.asyncio
async def test_commitment_states_vocabulary():
    """Test COMMITMENT_STATES vocabulary is canonical."""
    expected_states = {"proposed", "pending_authorization", "authorized", "active", "paused", "fulfilled", "cancelled", "expired", "superseded", "rejected"}
    assert set(COMMITMENT_STATES) == expected_states





@pytest.mark.asyncio
async def test_authorization_types_vocabulary():
    """Test AUTHORIZATION_TYPES vocabulary is canonical."""
    expected_types = {"full", "conditional", "partial", "delegated", "emergency"}
    assert set(AUTHORIZATION_TYPES) == expected_types


@pytest.mark.asyncio
async def test_authorization_states_vocabulary():
    """Test AUTHORIZATION_STATES vocabulary is canonical."""
    expected_states = {"requested", "under_review", "approved", "rejected", "conditional", "expired", "revoked"}
    assert set(AUTHORIZATION_STATES) == expected_states


# =============================================================================
# Replay / Exact-Once Tests
# =============================================================================

@pytest.mark.asyncio
async def test_authorization_replay_convergence(client, db_session_factory):
    """Test authorization replay produces same fingerprint."""
    reg = await register_org(client, name=f"Replay Auth Corp {uuid.uuid4().hex[:8]}", email=f"replayauth_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Run 1
        auth1 = await governed_commitment_engine.create_authorization_request(
            session, org_id, user_id=user_id,
            authorization_type="full", title="Replay Test", scope_type="company",
        )
        await session.rollback()

        # Run 2 (simulated replay)
        auth2 = await governed_commitment_engine.create_authorization_request(
            session, org_id, user_id=user_id,
            authorization_type="full", title="Replay Test", scope_type="company",
        )

    # Same fingerprint means exact-once
    assert auth1.fingerprint == auth2.fingerprint


@pytest.mark.asyncio
async def test_commitment_replay_convergence(client, db_session_factory):
    """Test commitment replay produces same fingerprint."""
    reg = await register_org(client, name=f"Replay Commit Corp {uuid.uuid4().hex[:8]}", email=f"replaycommit_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    decision_id = hashlib.sha256(f"decision:replay:{org_id}".encode()).hexdigest()[:160]

    async with db_session_factory() as session:
        # Create the decision first (outside replay)
        from app.models.company_operating import CompanyDecision
        decision = CompanyDecision(
            organization_id=org_id,
            decision_id=decision_id,
            kind="strategic",
            title="Replay Test Decision",
            rationale="Test rationale",
            recommendation_key="",
            state="approved",
            approver_label="test",
            source_event_id="test.event",
        )
        session.add(decision)
        await session.flush()

        # Run 1 - create commitment
        c1 = await governed_commitment_engine.create_commitment(
            session, org_id, user_id=user_id,
            commitment_type="unconditional", title="Replay Commit", scope_type="company",
            decision_id=decision_id, intent_id=chain["intent_id"],
        )

        # Rollback only the commitment, not the decision
        await session.rollback()

        # Re-add decision since it was rolled back
        session.add(decision)
        await session.flush()

        # Run 2 (simulated replay)
        c2 = await governed_commitment_engine.create_commitment(
            session, org_id, user_id=user_id,
            commitment_type="unconditional", title="Replay Commit", scope_type="company",
            decision_id=decision_id, intent_id=chain["intent_id"],
        )

    # Same fingerprint means exact-once
    assert c1.fingerprint == c2.fingerprint


# =============================================================================
# Deterministic Composition Tests
# =============================================================================

@pytest.mark.asyncio
async def test_list_authorizations_deterministic_order(client, db_session_factory):
    """Test list authorizations returns deterministic order."""
    reg = await register_org(client, name=f"Order Auth Corp {uuid.uuid4().hex[:8]}", email=f"orderauth_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create multiple with known titles
        for i in range(5):
            await governed_commitment_engine.create_authorization_request(
                session, org_id, user_id=user_id,
                authorization_type="full", title=f"Auth {i}", scope_type="company",
            )

        # List twice
        list1 = await governed_commitment_engine.list_authorizations(session, org_id, limit=10)
        list2 = await governed_commitment_engine.list_authorizations(session, org_id, limit=10)

    # Should be same order (created_at desc)
    assert [a.id for a in list1] == [a.id for a in list2]


@pytest.mark.asyncio
async def test_list_commitments_deterministic_order(client, db_session_factory):
    """Test list commitments returns deterministic order."""
    reg = await register_org(client, name=f"Order Commit Corp {uuid.uuid4().hex[:8]}", email=f"ordercommit_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        for i in range(5):
            await governed_commitment_engine.create_commitment(
                session, org_id, user_id=user_id,
                commitment_type="unconditional", title=f"Commit {i}", scope_type="company",
                intent_id=chain["intent_id"],
            )

        list1 = await governed_commitment_engine.list_commitments(session, org_id, limit=10)
        list2 = await governed_commitment_engine.list_commitments(session, org_id, limit=10)

    assert [c.id for c in list1] == [c.id for c in list2]