"""Phase 4I.8 — Adaptive Execution & Outcome Observation adversarial tests.

These tests verify the adaptive execution layer operates correctly:
- Consumes 4I.1-4I.7, 4H.7, and all execution substrates
- Commitment → Action → Work → Observation → Outcome → Learning → State loop
- Governance-first: commitment scope resolved before action proposal
- Decision ≠ Authorization ≠ Commitment ≠ Action ≠ Execution (explicit boundaries)
- Exact-once semantics (fingerprint-based deduplication)
- Provenance chains: Commitment → Action → Work → Outcome
- Epistemic separation: observation vs assessment vs inference vs prediction
- Contradiction preservation (both expected and actual outcomes visible)
- Temporal truth (state transitions with triggers, supersession chains)
- Tenant isolation
- No autonomous execution: actions proposed, governance authorizes, execution observed
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
    StrategicLink, StrategicHistory,
    CompanyCommitment, CompanyAuthorization,
    COMMITMENT_STATES, COMMITMENT_TYPES,
    AUTHORIZATION_TYPES, AUTHORIZATION_STATES,
    ObjectiveOutcome, ObjectiveOutcomeAssessment, ObjectiveContradiction,
    OUTCOME_STATES, ASSESSMENT_STATES, MEASUREMENT_QUALITY,
    SUPERSESSION_REASON,
)
from app.models.company_operating import CompanyDecision as OperatingCompanyDecision, CompanyDecisionContradiction as OperatingCompanyDecisionContradiction
from app.models.company_actions import CompanyAction, CompanyActionEvent, CompanyActionOutcome
from app.models.company_state import CompanyState
from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
from app.models.intelligence import PatternDetection
from app.intelligence.adaptive_execution_engine import adaptive_execution_engine
from app.intelligence.governed_commitment_engine import governed_commitment_engine
from app.intelligence.decision_intelligence_engine import decision_intelligence_engine
from app.intelligence.company_planning_context_engine import company_planning_context_engine
from app.intelligence.adaptive_planning_engine import adaptive_planning_engine
from app.knowledge.action_ops_engine import action_ops_engine
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
            title="Test Strategic Intent for 4I.8",
            description="Test intent for adaptive execution testing",
            state="active",
            epistemic_status="adopted",
            source="declared",
            priority=1,
            scope="company",
            fingerprint=hashlib.sha256(f"intent:4i8-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(intent)
        await session.flush()

        goal = CompanyGoal(
            organization_id=org_id,
            title="Test Goal for 4I.8",
            description="Test goal for adaptive execution testing",
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
            title="Test Objective for 4I.8",
            description="Test objective for adaptive execution testing",
            status="active",
            fingerprint=hashlib.sha256(f"objective:4i8-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(objective)
        await session.flush()

        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Test Initiative for 4I.8",
            description="Test initiative for adaptive execution testing",
            status="active",
            fingerprint=hashlib.sha256(f"initiative:4i8-test:{org_id}".encode()).hexdigest()[:160],
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


async def _create_authorized_commitment(db_session_factory, org_id: str, user_id: str, chain: dict, title: str = "Test Commitment"):
    """Create an authorized commitment with full governance chain."""
    async with db_session_factory() as session:
        # Create authorization first
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id, user_id=user_id,
            authorization_type="full", title=f"Auth for {title}", scope_type="company",
        )
        await governed_commitment_engine.review_authorization(
            session, org_id, auth.id, user_id=user_id, action="approve",
        )

        # Create commitment
        commitment = await governed_commitment_engine.create_commitment(
            session, org_id, user_id=user_id,
            commitment_type="unconditional", title=title,
            scope_type="company", intent_id=chain["intent_id"],
            objective_id=chain["objective_id"], initiative_id=chain["initiative_id"],
            authorization_id=auth.id,
        )
        await session.commit()
        return commitment


# =============================================================================
# Commitment → Action Proposal Tests
# =============================================================================

@pytest.mark.asyncio
async def test_propose_actions_from_authorized_commitment(client, db_session_factory):
    """Test proposing actions from an authorized commitment."""
    reg = await register_org(client, name=f"Exec Corp {uuid.uuid4().hex[:8]}", email=f"exec_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain, "Test Commitment for Actions")

    async with db_session_factory() as session:
        result = await adaptive_execution_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id
        )

    assert len(result) >= 1
    for action in result:
        assert action["source_commitment_id"] == commitment.id
        assert action["action_type"] in ("task", "decision", "communication", "knowledge", "meeting", "project")
        assert action["state"] in ("proposed", "validating", "awaiting_approval", "approved")


@pytest.mark.asyncio
async def test_propose_actions_from_commitment_with_plan(client, db_session_factory):
    """Test proposing actions with a custom action plan."""
    reg = await register_org(client, name=f"Plan Corp {uuid.uuid4().hex[:8]}", email=f"plan_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain, "Commitment with Plan")

    action_plan = [
        {
            "action_type": "task",
            "title": "Execute work item 1",
            "description": "First work item",
            "action_type": "task",
            "risk": "low",
        },
        {
            "action_type": "project",
            "title": "Create sub-project",
            "description": "Sub-project for commitment",
            "action_type": "project",
            "risk": "medium",
        },
    ]

    async with db_session_factory() as session:
        results = await adaptive_execution_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id,
            action_plan=action_plan
        )

    assert len(results) == 2
    assert results[0]["title"] == "Execute work item 1"
    assert results[1]["title"] == "Create sub-project"
    assert all(r["source_commitment_id"] == commitment.id for r in results)


@pytest.mark.asyncio
async def test_propose_actions_from_unauthorized_commitment_fails(client, db_session_factory):
    """Test that proposing actions from unauthorized commitment fails."""
    reg = await register_org(client, name=f"Unauth Corp {uuid.uuid4().hex[:8]}", email=f"unauth_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create unconditional commitment WITH approval_required (state = proposed)
        commitment = await governed_commitment_engine.create_commitment(
            session, org_id, user_id=user_id,
            commitment_type="unconditional", title="Unauthorized Commitment",
            scope_type="company", intent_id=chain["intent_id"],
            # The engine doesn't expose approval_required parameter directly,
            # but we can test the engine's validation by directly setting state
        )
        # Manually set to proposed state (unauthorized)
        commitment.state = "proposed"
        await session.flush()

        # Try to propose actions - should fail
        with pytest.raises(ValueError, match="not executable"):
            await adaptive_execution_engine.propose_actions_from_commitment(
                session, org_id, user_id=user_id, commitment_id=commitment.id
            )


# =============================================================================
# Action → Work Routing Tests
# =============================================================================

@pytest.mark.asyncio
async def test_route_action_to_work(client, db_session_factory):
    """Test routing an approved action to work infrastructure."""
    reg = await register_org(client, name=f"Route Corp {uuid.uuid4().hex[:8]}", email=f"route_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain)

    async with db_session_factory() as session:
        # Propose and approve an action
        result = await governed_commitment_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id,
            action_type="task", title="Routed Task", risk="medium",
        )
        action_id = result["id"]

        # Approve the action
        # Get user object for approval
        from app.models.user import User
        user_obj = await session.get(User, user_id)
        await action_ops_engine.approve(
            session, organization_id=org_id, action_id=action_id, user=user_obj
        )

        # Route to work
        result = await adaptive_execution_engine.route_action_to_work(
            session, org_id, action_id, user_id=user_id
        )

    assert result is not None
    assert result["target_type"] in ("task", "project", "meeting", "communication", "knowledge", "decision")
    assert result["target_id"] is not None


# =============================================================================
# Execution → Observation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_record_execution_observation(client, db_session_factory):
    """Test recording execution observation with outcome."""
    reg = await register_org(client, name=f"Obs Corp {uuid.uuid4().hex[:8]}", email=f"obs_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain)

    async with db_session_factory() as session:
        # Propose, approve, and route action
        result = await governed_commitment_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id,
            action_type="task", title="Observable Task", risk="medium",
        )
        action_id = result["id"]

        # Approve and route
        # Get user object for approval
        from app.models.user import User
        user_obj = await session.get(User, user_id)
        await action_ops_engine.approve(
            session, organization_id=org_id, action_id=action_id, user=user_obj
        )
        await action_ops_engine._route_and_ready(
            session,
            action=await session.get(CompanyAction, action_id),
            actor_id=user_id, user=None
        )

        # Complete the action (start -> complete)
        await action_ops_engine.transition(
            db=session, organization_id=org_id, action_id=action_id, user=None, transition="start"
        )
        await action_ops_engine.transition(
            db=session, organization_id=org_id, action_id=action_id, user=None, transition="complete"
        )

        # Record observation
        result = await adaptive_execution_engine.record_execution_observation(
            session, org_id, user_id=user_id, action_id=action_id,
            observation={"verdict": "Task completed successfully"},
            outcome_type="success",
            effectiveness=0.9,
            evidence=["evidence_1"],
            notes="Completed on time",
        )

    assert result is not None
    assert result["outcome"]["outcome_type"] == "success"
    assert result["outcome"]["effectiveness"] == 0.9


@pytest.mark.asyncio
async def test_observation_distinguishes_completion_from_outcome(client, db_session_factory):
    """Test that observation distinguishes action completion from outcome achievement."""
    reg = await register_org(client, name=f"Distinct Corp {uuid.uuid4().hex[:8]}", email=f"distinct_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain, "Outcome Test Commitment")
    commitment.objective_id = chain["objective_id"]

    async with db_session_factory() as session:
        # Create action and complete it
        result = await governed_commitment_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id,
            action_type="task", title="Task that completes but outcome missed", risk="medium",
        )
        action_id = result["id"]

        # Get user object for approval
        from app.models.user import User
        user_obj = await session.get(User, user_id)
        await action_ops_engine.approve(
            session, organization_id=org_id, action_id=action_id, user=user_obj
        )
        # Start and complete the action
        await action_ops_engine.transition(
            db=session, organization_id=org_id, action_id=action_id, user=None, transition="start"
        )
        await action_ops_engine.transition(
            db=session, organization_id=org_id, action_id=action_id, user=None, transition="complete"
        )

        # Record observation with FAILED outcome (completion ≠ success)
        result = await adaptive_execution_engine.record_execution_observation(
            session, org_id, user_id=user_id, action_id=action_id,
            observation={"verdict": "Task done but objective missed"},
            outcome_type="failed",
            effectiveness=0.2,
            notes="Task completed but metric not achieved",
        )

    assert result["outcome"]["outcome_type"] == "failed"
    assert result["outcome"]["effectiveness"] == 0.2


# =============================================================================
# Outcome → Assessment → Evidence → Learning Tests
# =============================================================================

@pytest.mark.asyncio
async def test_assess_commitment_outcome(client, db_session_factory):
    """Test assessing commitment outcome by comparing expected vs actual."""
    reg = await register_org(client, name=f"Assess Corp {uuid.uuid4().hex[:8]}", email=f"assess_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain, "Assessment Test")
    commitment.objective_id = chain["objective_id"]

    async with db_session_factory() as session:
        result = await adaptive_execution_engine.assess_commitment_outcome(
            session, org_id, commitment.id, user_id=user_id,
            expected_outcome={"target_value": 100},
            actual_observation={"actual_value": 95},
            measurement_quality="high",
            measurement_source="metrics_dashboard",
            evidence_fingerprints=["evidence_1"],
        )

    assert result["assessment"] == "met"
    assert result["variance_pct"] == -5.0
    assert result["expected"] == 100
    assert result["actual"] == 95


@pytest.mark.asyncio
async def test_assess_commitment_outcome_underperformed(client, db_session_factory):
    """Test assessment when outcome underperforms."""
    reg = await register_org(client, name=f"Under Corp {uuid.uuid4().hex[:8]}", email=f"under_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain)

    async with db_session_factory() as session:
        result = await adaptive_execution_engine.assess_commitment_outcome(
            session, org_id, commitment.id, user_id=user_id,
            expected_outcome={"target_value": 100},
            actual_observation={"actual_value": 70},
            measurement_quality="medium",
        )

    assert result["assessment"] == "underperformed"
    assert result["variance_pct"] == -30.0


@pytest.mark.asyncio
async def test_commitment_state_propagation_from_outcomes(client, db_session_factory):
    """Test commitment state propagates from action outcomes."""
    reg = await register_org(client, name=f"Propagate Corp {uuid.uuid4().hex[:8]}", email=f"propagate_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain)

    async with db_session_factory() as session:
        # Propose multiple actions
        results = []
        for i in range(3):
            result = await governed_commitment_engine.propose_actions_from_commitment(
                session, org_id, user_id=user_id, commitment_id=commitment.id,
                action_type="task", title=f"Action {i+1}", risk="medium",
            )
            results.append(result["id"])

        # Approve and complete all
        for action_id in results:
            # Get user object for approval
            from app.models.user import User
            user_obj = await session.get(User, user_id)
            await action_ops_engine.approve(
                session, organization_id=org_id, action_id=action_id, user=user_obj
            )
            # Start and complete the action
            await action_ops_engine.transition(
                db=session, organization_id=org_id, action_id=action_id, user=None, transition="start"
            )
            await action_ops_engine.transition(
                db=session, organization_id=org_id, action_id=action_id, user=None, transition="complete"
            )
            await adaptive_execution_engine.record_execution_observation(
                session, org_id, user_id=user_id, action_id=action_id,
                observation={"verdict": "Action completed successfully"},
                outcome_type="success", effectiveness=0.9,
            )

        # Refresh commitment (re-fetch in current session)
        commitment = await session.get(CompanyCommitment, commitment.id)
        await session.refresh(commitment)

    # Commitment should be fulfilled
    assert commitment.state == "fulfilled"


# =============================================================================
# Exact-Once / Deduplication Tests
# =============================================================================

@pytest.mark.asyncio
async def test_action_proposal_exact_once(client, db_session_factory):
    """Test that proposing same action from same commitment is deduplicated."""
    reg = await register_org(client, name=f"Dedup Corp {uuid.uuid4().hex[:8]}", email=f"dedup_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain)

    async with db_session_factory() as session:
        # Propose first time
        result1 = await governed_commitment_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id,
            action_type="task", title="Dedup Test Action", risk="low",
        )

        # Propose again with same params
        result2 = await governed_commitment_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id,
            action_type="task", title="Dedup Test Action", risk="low",
        )

    assert result1["id"] == result2["id"]
    assert result2.get("deduplicated") is True


# =============================================================================
# Tenant Isolation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_adaptive_execution_tenant_isolation(client, db_session_factory):
    """Test that adaptive execution is tenant-isolated."""
    reg1 = await register_org(client, name=f"Org A {uuid.uuid4().hex[:8]}", email=f"org_a_{uuid.uuid4().hex[:8]}@test.co")
    reg2 = await register_org(client, name=f"Org B {uuid.uuid4().hex[:8]}", email=f"org_b_{uuid.uuid4().hex[:8]}@test.co")
    org_a_id = reg1["organization"]["id"]
    org_b_id = reg2["organization"]["id"]
    user_a_id = reg1["user"]["id"]
    user_b_id = reg2["user"]["id"]

    chain_a = await _create_minimal_canonical_chain(db_session_factory, org_a_id)
    commitment_a = await _create_authorized_commitment(db_session_factory, org_a_id, user_a_id, chain_a)

    async with db_session_factory() as session:
        # Propose action in Org A
        result = await governed_commitment_engine.propose_actions_from_commitment(
            session, org_a_id, user_id=user_a_id, commitment_id=commitment_a.id,
            action_type="task", title="Org A Action", risk="low",
        )
        action_id = result["id"]

        # Try to access from Org B - should not be visible
        action_b = await session.get(CompanyAction, action_id)
        # The engine's _load method enforces tenant isolation, but session.get() does not
        # So we verify the action belongs to Org A
        assert action_b is not None and action_b.organization_id == org_a_id

        # Verify tenant isolation via engine's load method
        action_b_via_engine = await action_ops_engine._load(
            session, organization_id=org_b_id, action_id=action_id
        )
        assert action_b_via_engine is None, "Action from Org A should not be visible in Org B"

        # Propose from Org B should fail (commitment not found)
        with pytest.raises(ValueError, match="Commitment not found"):
            await adaptive_execution_engine.propose_actions_from_commitment(
                session, org_b_id, user_id=user_b_id, commitment_id=commitment_a.id,
                action_plan=[{"action_type": "task", "title": "Should fail", "risk": "low"}],
            )


# =============================================================================
# Governance Boundary Tests (Decision ≠ Authorization ≠ Commitment ≠ Action ≠ Execution)
# =============================================================================

@pytest.mark.asyncio
async def test_decision_not_equal_action(client, db_session_factory):
    """Test that Decision, Authorization, Commitment, Action are distinct."""
    reg = await register_org(client, name=f"Boundary Corp {uuid.uuid4().hex[:8]}", email=f"boundary_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create Decision
        decision = OperatingCompanyDecision(
            organization_id=org_id,
            decision_id=hashlib.sha256(f"decision:boundary:{org_id}".encode()).hexdigest()[:160],
            kind="strategic", title="Governed Decision",
            rationale="Test rationale", recommendation_key="", state="approved",
            approver_label="test",
            source_event_id="test-event-decision",
        )
        session.add(decision)
        await session.flush()

        # Create Authorization
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id, user_id=user_id,
            authorization_type="full", title="Auth for Decision", scope_type="company",
            decision_id=decision.decision_id,
        )
        await governed_commitment_engine.review_authorization(
            session, org_id, auth.id, user_id=user_id, action="approve",
        )

        # Create Commitment
        commitment = await governed_commitment_engine.create_commitment(
            session, org_id, user_id=user_id,
            commitment_type="unconditional", title="Commitment for Decision", scope_type="company",
            intent_id=chain["intent_id"], decision_id=decision.decision_id, authorization_id=auth.id,
        )

        # Propose Action from Commitment
        result = await governed_commitment_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id,
            action_type="task", title="Action from Commitment", risk="low",
        )

        # Verify distinct IDs
        assert decision.decision_id != auth.id
        assert auth.id != commitment.id
        assert commitment.id != result["id"]
        assert result["source_commitment_id"] == commitment.id
        assert result.get("source_company_decision_id") == decision.decision_id


# =============================================================================
# Company State Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_update_company_state_from_execution(client, db_session_factory):
    """Test updating CompanyState from execution outcomes."""
    reg = await register_org(client, name=f"State Corp {uuid.uuid4().hex[:8]}", email=f"state_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain)

    async with db_session_factory() as session:
        result = await adaptive_execution_engine.update_company_state_from_execution(
            session, org_id, commitment.id
        )

    assert "company_state" in result
    assert result["commitment_outcomes_included"] is True


# =============================================================================
# Commitment Execution Status Query
# =============================================================================

@pytest.mark.asyncio
async def test_get_commitment_execution_status(client, db_session_factory):
    """Test getting comprehensive execution status for a commitment."""
    reg = await register_org(client, name=f"Status Corp {uuid.uuid4().hex[:8]}", email=f"status_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain)

    async with db_session_factory() as session:
        # Add some actions
        result = await governed_commitment_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id,
            action_type="task", title="Status Action", risk="medium",
        )
        action_id = result["id"]

        # Get user object for approval
        from app.models.user import User
        user_obj = await session.get(User, user_id)
        await action_ops_engine.approve(
            session, organization_id=org_id, action_id=action_id, user=user_obj
        )
        # Start and complete the action
        await action_ops_engine.transition(
            db=session, organization_id=org_id, action_id=action_id, user=None, transition="start"
        )
        await action_ops_engine.transition(
            db=session, organization_id=org_id, action_id=action_id, user=None, transition="complete"
        )
        await action_ops_engine.record_outcome(
            db=session, organization_id=org_id, action_id=action_id, user=None,
            outcome_type="success", effectiveness=0.85,
        )

        status = await adaptive_execution_engine.get_commitment_execution_status(
            session, org_id, commitment.id
        )

    assert status["commitment_id"] == commitment.id
    assert status["actions"]["total"] >= 1
    assert status["actions"]["completed"] >= 1
    assert status["avg_effectiveness"] > 0
    assert status["health"] in ("healthy", "in_progress", "at_risk", "pending")


# =============================================================================
# Sync / Reconciliation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_sync_commitment_actions(client, db_session_factory):
    """Test syncing commitment action_ids with actual actions."""
    reg = await register_org(client, name=f"Sync Corp {uuid.uuid4().hex[:8]}", email=f"sync_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain)

    async with db_session_factory() as session:
        # Propose action
        result = await governed_commitment_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id,
            action_type="task", title="Sync Test", risk="low",
        )
        action_id = result["id"]

        # Sync
        action_ids = await governed_commitment_engine.sync_commitment_actions(
            session, org_id, commitment.id
        )

    assert action_id in action_ids
    assert len(action_ids) >= 1


# =============================================================================
# Provenance Chain Tests
# =============================================================================

@pytest.mark.asyncio
async def test_action_provenance_chain(client, db_session_factory):
    """Test full provenance chain: Action → Commitment → Authorization → Decision."""
    reg = await register_org(client, name=f"Prov Corp {uuid.uuid4().hex[:8]}", email=f"prov_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create decision
        decision = OperatingCompanyDecision(
            organization_id=org_id,
            decision_id=hashlib.sha256(f"decision:prov:{org_id}".encode()).hexdigest()[:160],
            kind="strategic", title="Provenance Decision",
            rationale="Test rationale", recommendation_key="", state="approved",
            approver_label="test",
            source_event_id="test-event-prov-decision",
        )
        session.add(decision)
        await session.flush()

        # Auth
        auth = await governed_commitment_engine.create_authorization_request(
            session, org_id, user_id=user_id,
            authorization_type="full", title="Auth for Prov", scope_type="company",
            decision_id=decision.decision_id,
        )
        await governed_commitment_engine.review_authorization(
            session, org_id, auth.id, user_id=user_id, action="approve",
        )

        # Commitment
        commitment = await governed_commitment_engine.create_commitment(
            session, org_id, user_id=user_id,
            commitment_type="unconditional", title="Prov Commitment", scope_type="company",
            intent_id=chain["intent_id"], decision_id=decision.decision_id, authorization_id=auth.id,
        )

        # Action
        result = await governed_commitment_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id,
            action_type="task", title="Prov Action", risk="medium",
        )

    # Verify provenance chain
    assert result["source_commitment_id"] == commitment.id
    assert result.get("source_company_decision_id") == decision.decision_id
    assert result.get("source_commitment_id") == commitment.id


# =============================================================================
# Contradiction Preservation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_contradiction_preserved_in_outcome_assessment(client, db_session_factory):
    """Test that contradictions are preserved in outcome assessment."""
    reg = await register_org(client, name=f"Contra Corp {uuid.uuid4().hex[:8]}", email=f"contra_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain)

    # Add a contradiction to commitment
    async with db_session_factory() as session:
        # Re-fetch commitment in this session (it was created in a different session)
        commitment = await session.get(CompanyCommitment, commitment.id)
        
        # Create a decision for the contradiction to reference
        decision = OperatingCompanyDecision(
            organization_id=org_id,
            decision_id=hashlib.sha256(f"decision:contra:{org_id}".encode()).hexdigest()[:160],
            kind="strategic",
            title="Contradiction Test Decision",
            rationale="Test rationale",
            recommendation_key="",
            state="approved",
            approver_label="test",
            source_event_id="test-event-contra-decision",
        )
        session.add(decision)
        await session.flush()

        contradiction = OperatingCompanyDecisionContradiction(
            organization_id=org_id,
            decision_id=decision.decision_id,
            contradiction_key="cx:test:1",
            side_a_json={"claim": "success likely", "evidence_ids": ["e1"]},
            side_b_json={"claim": "high risk of failure", "evidence_ids": ["e2"]},
            status="open",
            source_event_id="test-event-contra",
        )
        session.add(contradiction)
        await session.flush()

        commitment.contradiction_ids = [contradiction.id]
        await session.commit()

        result = await adaptive_execution_engine.assess_commitment_outcome(
            session, org_id, commitment.id, user_id=user_id,
            expected_outcome={"target_value": 100},
            actual_observation={"actual_value": 70},
        )

    assert "contradictions" in result
    assert len(result["contradictions"]) >= 1
    assert result["contradictions"][0]["contradiction_id"] == contradiction.id


# =============================================================================
# Deterministic Composition Tests
# =============================================================================

@pytest.mark.asyncio
async def test_deterministic_action_proposal(client, db_session_factory):
    """Test that same commitment produces same action proposals."""
    reg = await register_org(client, name=f"Determ Corp {uuid.uuid4().hex[:8]}", email=f"determ_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain)

    async with db_session_factory() as session:
        result1 = await adaptive_execution_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id
        )

        # Second call with same commitment
        result2 = await adaptive_execution_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id
        )

    # Same commitment should produce same action plan structure
    assert len(result1) == len(result2)
    for r1, r2 in zip(result1, result2):
        assert r1["action_type"] == r2["action_type"]
        # Titles should be deterministic based on commitment


# =============================================================================
# Canonical Vocabularies
# =============================================================================

@pytest.mark.asyncio
async def test_commitment_states_vocabulary():
    expected = {"proposed", "pending_authorization", "authorized", "active", "paused", "fulfilled", "cancelled", "expired", "superseded", "rejected"}
    assert set(COMMITMENT_STATES) == expected

@pytest.mark.asyncio
async def test_authorization_states_vocabulary():
    expected = {"requested", "under_review", "approved", "rejected", "conditional", "expired", "revoked"}
    assert set(AUTHORIZATION_STATES) == expected

@pytest.mark.asyncio
async def test_outcome_states_vocabulary():
    expected = {"projected", "actual", "superseded"}
    assert set(OUTCOME_STATES) == expected

@pytest.mark.asyncio
async def test_assessment_states_vocabulary():
    expected = {"outperformed", "met", "partially_met", "underperformed", "missed", "inconclusive", "superseded"}
    assert set(ASSESSMENT_STATES) == expected


# =============================================================================
# Replay / Deterministic Tests
# =============================================================================

@pytest.mark.asyncio
async def test_adaptive_execution_replay_convergence(client, db_session_factory):
    """Test replay produces same state."""
    reg = await register_org(client, name=f"Replay Exec Corp {uuid.uuid4().hex[:8]}", email=f"replayexec_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)
    commitment = await _create_authorized_commitment(db_session_factory, org_id, user_id, chain)

    async with db_session_factory() as session:
        result1 = await adaptive_execution_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id
        )
        await session.rollback()

        result2 = await adaptive_execution_engine.propose_actions_from_commitment(
            session, org_id, user_id=user_id, commitment_id=commitment.id
        )

    assert len(result1) == len(result2)
    for r1, r2 in zip(result1, result2):
        assert r1["action_type"] == r2["action_type"]
        assert r1["title"] == r2["title"]