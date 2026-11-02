"""Phase 4I.5 — Adaptive Planning / Replanning adversarial tests.

These tests verify the adaptive planning layer operates correctly:
- Consumes 4I.4 Planning Context
- Detects attention signals from all 8 sections
- Generates replanning proposals from signals
- Creates decision contexts from proposals
- Governance-first retrieval
- Epistemic status separation
- Temporal truth (state transitions)
- Exact-once semantics
- Tenant isolation
"""

import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select

from app.core.timeutils import utcnow
from app.models.organization import Organization
from app.models.user import User
from app.models.company_intent import CompanyIntent, CompanyPlan
from app.models.execution_strategy import (
    CompanyGoal, CompanyObjective, CompanyInitiative,
    StrategicLink, StrategicAlignment, AlignmentGap,
    StrategicConflict, StrategicAlignmentState, StrategicDependency,
    CompanyPlanningContext, CompanyStateTransition, PlanningContextProvenance,
    AdaptivePlanningContext, AttentionSignal, ReplanningProposal,
    DecisionContext, AdaptivePlanningTransition,
    PLANNING_CONTEXT_SECTIONS, PLANNING_CONTEXT_EPISTEMIC_STATUS,
    STATE_TRANSITION_TRIGGERS, STATE_TRANSITION_KINDS,
    ATTENTION_SIGNAL_TYPES, ATTENTION_SEVERITY,
    REPLANNING_PROPOSAL_TYPES, REPLANNING_PROPOSAL_STATUS,
    DECISION_CONTEXT_TYPES, DECISION_CONTEXT_STATUS,
    ObjectiveOutcome,
)
from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
from app.models.intelligence import PatternDetection
from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
from app.models.company_actions import CompanyAction
from app.models.company_state import CompanyState
from app.models.project import Project
from app.intelligence.adaptive_planning_engine import adaptive_planning_engine
from app.intelligence.company_planning_context_engine import company_planning_context_engine
from tests.conftest import register_org


@pytest.mark.asyncio
async def test_adaptive_context_synthesis_basic(
    client, db_session_factory
):
    """Test basic adaptive context synthesis from planning context."""
    reg = await register_org(client, name=f"Adaptive Corp {uuid.uuid4().hex[:8]}", email=f"adapt_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create minimal canonical data for planning context
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Test Strategic Intent",
            state="active",
            fingerprint="adapt-intent-fp-1",
        )
        session.add(intent)
        await session.flush()
        
        goal = CompanyGoal(
            organization_id=org_id,
            title="Test Goal",
            status="active",
            priority=1,
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            intent_id=intent.id,
            title="Test Objective",
            status="active",
            fingerprint="adapt-obj-fp-1",
        )
        session.add(objective)
        await session.flush()
        
        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Test Initiative",
            status="active",
            fingerprint="adapt-init-fp-1",
        )
        session.add(initiative)
        await session.flush()
        
        # Synthesize planning context first
        planning_context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        
        # Synthesize adaptive context
        adaptive_context = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=planning_context
        )
        
        # Verify context was created
        assert adaptive_context is not None
        assert adaptive_context.organization_id == org_id
        assert adaptive_context.scope == "company"
        assert adaptive_context.planning_context_id == planning_context.id
        assert adaptive_context.version == 1
        assert adaptive_context.overall_adaptive_health in ("stable", "attention_needed", "critical", "replanning_active")
        
        # Verify sections present
        assert adaptive_context.attention_signals is not None
        assert adaptive_context.replanning_proposals is not None
        assert adaptive_context.decision_contexts is not None
        
        # Verify counters
        assert adaptive_context.attention_count == len(adaptive_context.attention_signals)
        assert adaptive_context.critical_attention_count >= 0
        assert adaptive_context.pending_proposals_count >= 0
        assert adaptive_context.pending_decisions_count >= 0


@pytest.mark.asyncio
async def test_adaptive_context_detects_outcome_deviation(
    client, db_session_factory
):
    """Test that adaptive context detects outcome deviations."""
    reg = await register_org(client, name=f"Outcome Corp {uuid.uuid4().hex[:8]}", email=f"out_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create data with underperforming outcomes
        goal = CompanyGoal(
            organization_id=org_id,
            title="Goal with Underperforming Outcome",
            status="active",
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            title="Underperforming Objective",
            status="active",
            fingerprint="outcome-obj-fp-1",
        )
        session.add(objective)
        await session.flush()
        
        # Add outcome that underperformed
        outcome = ObjectiveOutcome(
            organization_id=org_id,
            objective_id=objective.id,
            metric_kind="revenue",
            unit="USD",
            expected_value=1000000.0,
            actual_value=500000.0,
            variance_pct=-50.0,
            outcome_state="actual",
            assessment="underperformed",
            assessment_confidence=0.9,
            source_event_id="evt-outcome-1",
            recorded_at=utcnow(),
            fingerprint="outcome-fp-1",
        )
        session.add(outcome)
        await session.flush()
        
        # Synthesize planning context
        planning_context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        
        # Synthesize adaptive context
        adaptive_context = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=planning_context
        )
        
        # Verify outcome deviation signal detected
        outcome_signals = [s for s in adaptive_context.attention_signals 
                          if s.get("type") == "outcome_deviation"]
        assert len(outcome_signals) >= 1
        
        signal = outcome_signals[0]
        assert signal.get("severity") in ("warning", "critical")
        assert signal.get("source_context_section") == "outcome"
        
        # Verify replanning proposal generated
        timeline_proposals = [p for p in adaptive_context.replanning_proposals 
                             if p.get("type") == "timeline_adjustment"]
        assert len(timeline_proposals) >= 1
        
        # Verify decision context for proposal
        replanning_decisions = [d for d in adaptive_context.decision_contexts 
                               if d.get("type") == "replanning_approval"]
        assert len(replanning_decisions) >= 1


@pytest.mark.asyncio
async def test_adaptive_context_detects_alignment_breakdown(
    client, db_session_factory
):
    """Test that adaptive context detects alignment gaps and conflicts."""
    reg = await register_org(client, name=f"Alignment Corp {uuid.uuid4().hex[:8]}", email=f"align_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create goals and objectives
        goal = CompanyGoal(
            organization_id=org_id,
            title="Aligned Goal",
            status="active",
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            title="Aligned Objective",
            status="active",
            fingerprint="align-obj-fp-1",
        )
        session.add(objective)
        await session.flush()
        
        # Create initiative WITHOUT project (alignment gap)
        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Orphan Initiative",
            status="active",
            fingerprint="orphan-init-fp-1",
        )
        session.add(initiative)
        await session.flush()
        
        # Create alignment gap - use CRITICAL severity for critical_gaps detection
        gap = AlignmentGap(
            organization_id=org_id,
            gap_type="initiative_without_project",
            severity="critical",
            missing_element_type="project",
            context_element_type="initiative",
            context_element_id=initiative.id,
            description="Initiative has no linked project",
            state="open",
            fingerprint="gap-fp-1",
        )
        session.add(gap)
        await session.flush()
        
        # Synthesize planning context
        planning_context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        
        # Synthesize adaptive context
        adaptive_context = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=planning_context
        )
        
        # Verify alignment breakdown signal detected
        alignment_signals = [s for s in adaptive_context.attention_signals 
                           if s.get("type") == "alignment_breakdown"]
        assert len(alignment_signals) >= 1
        
        signal = alignment_signals[0]
        assert signal.get("severity") in ("warning", "critical")
        assert signal.get("source_context_section") == "alignment"
        
        # Verify replanning proposal for priority shift
        priority_proposals = [p for p in adaptive_context.replanning_proposals 
                             if p.get("type") == "priority_shift"]
        assert len(priority_proposals) >= 1


@pytest.mark.asyncio
async def test_adaptive_context_detects_contradictions(
    client, db_session_factory
):
    """Test that adaptive context detects contradictions."""
    reg = await register_org(client, name=f"Contra Corp {uuid.uuid4().hex[:8]}", email=f"contra_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create goal for the objective
        goal = CompanyGoal(
            organization_id=org_id,
            title="Contra Goal",
            status="active",
        )
        session.add(goal)
        await session.flush()
        
        # Create objective with goal_id
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            title="Contradicted Objective",
            status="active",
            fingerprint="contra-obj-fp-1",
        )
        session.add(objective)
        await session.flush()
        
        # Add open contradiction
        contra = CompanyDecisionContradiction(
            organization_id=org_id,
            decision_id="dec-test-1",
            contradiction_key="contra-1",
            side_a_json={"claim": "On track"},
            side_b_json={"claim": "At risk"},
            status="open",
            source_event_id="evt-contra-1",
        )
        session.add(contra)
        await session.flush()
        
        # Synthesize planning context
        planning_context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        
        # Synthesize adaptive context
        adaptive_context = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=planning_context
        )
        
        # Verify contradiction signal detected
        contra_signals = [s for s in adaptive_context.attention_signals 
                         if s.get("type") == "contradiction_surfaced"]
        assert len(contra_signals) >= 1
        
        signal = contra_signals[0]
        assert signal.get("severity") == "critical"
        assert signal.get("epistemic_status") == "contested"
        
        # Verify replanning proposal for scope reduction
        scope_proposals = [p for p in adaptive_context.replanning_proposals 
                          if p.get("type") == "scope_reduction"]
        assert len(scope_proposals) >= 1


@pytest.mark.asyncio
async def test_adaptive_context_detects_resource_contention(
    client, db_session_factory
):
    """Test that adaptive context detects resource contention."""
    reg = await register_org(client, name=f"Resource Corp {uuid.uuid4().hex[:8]}", email=f"res_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create many actions assigned to same person
        for i in range(6):
            action = CompanyAction(
                organization_id=org_id,
                action_type="task",
                title=f"Task {i}",
                state="in_progress",
                assignee_type="employee",
                assignee_id="emp-overloaded",
                fingerprint=f"action-fp-{i}",
                scope_type="org",
            )
            session.add(action)
        await session.flush()
        
        # Synthesize planning context
        planning_context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        
        # Synthesize adaptive context
        adaptive_context = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=planning_context
        )
        
        # Verify resource contention signal detected
        resource_signals = [s for s in adaptive_context.attention_signals 
                          if s.get("type") == "resource_contention"]
        assert len(resource_signals) >= 1
        
        signal = resource_signals[0]
        assert signal.get("severity") in ("warning", "critical")
        assert signal.get("source_context_section") == "resource"


@pytest.mark.asyncio
async def test_adaptive_context_detects_governance_pending(
    client, db_session_factory
):
    """Test that adaptive context detects pending governance decisions."""
    reg = await register_org(client, name=f"Gov Corp {uuid.uuid4().hex[:8]}", email=f"gov_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create pending decisions
        for i in range(3):
            decision = CompanyDecision(
                organization_id=org_id,
                decision_id=f"dec-gov-{i}",
                kind="change_priority",
                title=f"Governance Decision {i}",
                state="approved",
                source_event_id=f"evt-gov-{i}",
            )
            session.add(decision)
        
        # Create decision awaiting outcome
        decision2 = CompanyDecision(
            organization_id=org_id,
            decision_id="dec-gov-4",
            kind="reallocate_capacity",
            title="Capacity Decision",
            state="executed",
            source_event_id="evt-gov-4",
        )
        session.add(decision2)
        
        # Create open contradiction
        contra = CompanyDecisionContradiction(
            organization_id=org_id,
            decision_id="dec-gov-1",
            contradiction_key="gov-contra-1",
            side_a_json={"claim": "Approve"},
            side_b_json={"claim": "Defer"},
            status="open",
            source_event_id="evt-gov-contra",
        )
        session.add(contra)
        await session.flush()
        
        # Synthesize planning context
        planning_context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        
        # Synthesize adaptive context
        adaptive_context = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=planning_context
        )
        
        # Verify governance signals
        gov_signals = [s for s in adaptive_context.attention_signals 
                      if s.get("type") == "governance_pending"]
        assert len(gov_signals) >= 1
        
        # Verify contra signal
        contra_signals = [s for s in adaptive_context.attention_signals 
                         if s.get("type") == "contradiction_surfaced"]
        assert len(contra_signals) >= 1
        
        # Verify proposal for governance authorization
        gov_proposals = [p for p in adaptive_context.replanning_proposals 
                        if p.get("type") == "scope_authorization"]
        assert len(gov_proposals) >= 1


@pytest.mark.asyncio
async def test_adaptive_context_tenant_isolation(
    client, db_session_factory
):
    """Test tenant isolation in adaptive context synthesis."""
    reg1 = await register_org(client, name=f"Org1 {uuid.uuid4().hex[:8]}", email=f"org1_{uuid.uuid4().hex[:8]}@test.co")
    org1_id = reg1["organization"]["id"]
    
    reg2 = await register_org(client, name=f"Org2 {uuid.uuid4().hex[:8]}", email=f"org2_{uuid.uuid4().hex[:8]}@test.co")
    org2_id = reg2["organization"]["id"]

    async with db_session_factory() as session:
        # Create data in org 1
        intent1 = CompanyIntent(
            organization_id=org1_id,
            kind="strategic",
            title="Org 1 Intent",
            state="active",
            fingerprint="org1-adapt-intent-fp",
        )
        session.add(intent1)
        
        # Create data in org 2
        intent2 = CompanyIntent(
            organization_id=org2_id,
            kind="strategic",
            title="Org 2 Intent",
            state="active",
            fingerprint="org2-adapt-intent-fp",
        )
        session.add(intent2)
        await session.flush()
        
        # Synthesize for org 1
        pc1 = await company_planning_context_engine.synthesize_planning_context(
            session, org1_id
        )
        adaptive1 = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org1_id, scope="company", planning_context=pc1
        )
        
        # Synthesize for org 2
        pc2 = await company_planning_context_engine.synthesize_planning_context(
            session, org2_id
        )
        adaptive2 = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org2_id, scope="company", planning_context=pc2
        )
        
        # Verify isolation
        assert adaptive1.organization_id == org1_id
        assert adaptive2.organization_id == org2_id
        
        # Each org should only see its own attention signals
        assert adaptive1.attention_count >= 1
        assert adaptive2.attention_count >= 1


@pytest.mark.asyncio
async def test_adaptive_context_state_transition(
    client, db_session_factory
):
    """Test adaptive context state transition recording."""
    reg = await register_org(client, name=f"Transition Corp {uuid.uuid4().hex[:8]}", email=f"trans_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create initial data
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Transition Test Intent",
            state="active",
            fingerprint="trans-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        # First synthesis
        pc1 = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, trigger="manual_recompute"
        )
        adaptive1 = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, trigger="planning_context_change", planning_context=pc1
        )
        
        # Add new canonical data (new contradiction)
        contra = CompanyDecisionContradiction(
            organization_id=org_id,
            decision_id="dec-new",
            contradiction_key="new-contra",
            side_a_json={"claim": "A"},
            side_b_json={"claim": "B"},
            status="open",
            source_event_id="evt-new-contra",
        )
        session.add(contra)
        await session.flush()
        
        # Second synthesis triggered by new contradiction
        pc2 = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, trigger="new_contradiction",
            source_event_id="evt-new-contra"
        )
        adaptive2 = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, trigger="planning_context_change",
            planning_context=pc2,
            source_event_id="evt-new-contra",
            trigger_reason="New contradiction surfaced"
        )
        
        # Verify transition recorded
        transitions = await adaptive_planning_engine.get_adaptive_transitions(
            session, org_id, limit=10
        )
        
        assert len(transitions) >= 1
        transition = transitions[0]
        assert transition.from_version == 1
        assert transition.to_version == 2
        assert transition.trigger == "planning_context_change"
        assert "attention_signals" in transition.changed_sections
        assert len(transition.new_attention_signals) >= 1


@pytest.mark.asyncio
async def test_adaptive_context_deterministic_synthesis(
    client, db_session_factory
):
    """Test that same planning context produces identical adaptive context."""
    reg = await register_org(client, name=f"Deterministic Corp {uuid.uuid4().hex[:8]}", email=f"det_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Deterministic Test Intent",
            state="active",
            fingerprint="det-adapt-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        # Synthesize planning context
        pc = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company", trigger="manual_recompute"
        )
        
        # Synthesize adaptive context twice
        adaptive1 = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=pc, trigger="manual_recompute"
        )
        adaptive2 = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=pc, trigger="manual_recompute"
        )
        
        # Both should have same input fingerprint -> same synthesized output
        assert adaptive1.input_fingerprint == adaptive2.input_fingerprint
        assert adaptive1.overall_adaptive_health == adaptive2.overall_adaptive_health
        assert adaptive1.attention_count == adaptive2.attention_count


@pytest.mark.asyncio
async def test_adaptive_context_ask_question(
    client, db_session_factory
):
    """Test asking an adaptive planning question through the engine."""
    reg = await register_org(client, name=f"QA Corp {uuid.uuid4().hex[:8]}", email=f"qa_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create minimal canonical data
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="QA Intent",
            state="active",
            fingerprint="qa-adapt-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        # Ask an adaptive planning question
        answer = await adaptive_planning_engine.answer_adaptive_question(
            session, org_id, "What requires attention in the company?", user=reg["user"]
        )
        
        # Verify answer structure
        assert "question" in answer
        assert "planning_context_version" in answer
        assert "adaptive_context_version" in answer
        assert "overall_adaptive_health" in answer
        assert "attention_signals" in answer
        assert "replanning_proposals" in answer
        assert "decision_contexts" in answer
        assert "attention_count" in answer
        assert "critical_attention_count" in answer
        assert "pending_proposals_count" in answer
        assert "pending_decisions_count" in answer
        assert "provenance_available" in answer
        assert answer["provenance_available"] is True


@pytest.mark.asyncio
async def test_adaptive_context_canonical_vocabularies():
    """Test that all canonical vocabularies are properly defined."""
    # Attention signal types
    assert "outcome_deviation" in ATTENTION_SIGNAL_TYPES
    assert "alignment_breakdown" in ATTENTION_SIGNAL_TYPES
    assert "resource_contention" in ATTENTION_SIGNAL_TYPES
    assert "dependency_blocked" in ATTENTION_SIGNAL_TYPES
    assert "contradiction_surfaced" in ATTENTION_SIGNAL_TYPES
    assert "lesson_invalidation" in ATTENTION_SIGNAL_TYPES
    assert "risk_elevation" in ATTENTION_SIGNAL_TYPES
    assert "governance_pending" in ATTENTION_SIGNAL_TYPES
    assert "prediction_shift" in ATTENTION_SIGNAL_TYPES
    assert "supersession_cascade" in ATTENTION_SIGNAL_TYPES
    
    # Attention severity
    assert "info" in ATTENTION_SEVERITY
    assert "warning" in ATTENTION_SEVERITY
    assert "critical" in ATTENTION_SEVERITY
    assert "urgent" in ATTENTION_SEVERITY
    
    # Replanning proposal types
    assert "timeline_adjustment" in REPLANNING_PROPOSAL_TYPES
    assert "scope_reduction" in REPLANNING_PROPOSAL_TYPES
    assert "scope_expansion" in REPLANNING_PROPOSAL_TYPES
    assert "resource_reallocation" in REPLANNING_PROPOSAL_TYPES
    assert "priority_shift" in REPLANNING_PROPOSAL_TYPES
    assert "initiative_addition" in REPLANNING_PROPOSAL_TYPES
    assert "initiative_removal" in REPLANNING_PROPOSAL_TYPES
    assert "ownership_reassignment" in REPLANNING_PROPOSAL_TYPES
    assert "intent_supersession" in REPLANNING_PROPOSAL_TYPES
    assert "plan_retirement" in REPLANNING_PROPOSAL_TYPES
    assert "dependency_reroute" in REPLANNING_PROPOSAL_TYPES
    
    # Replanning proposal status
    assert "proposed" in REPLANNING_PROPOSAL_STATUS
    assert "under_review" in REPLANNING_PROPOSAL_STATUS
    assert "approved" in REPLANNING_PROPOSAL_STATUS
    assert "rejected" in REPLANNING_PROPOSAL_STATUS
    assert "executed" in REPLANNING_PROPOSAL_STATUS
    assert "superseded" in REPLANNING_PROPOSAL_STATUS
    
    # Decision context types
    assert "attention_response" in DECISION_CONTEXT_TYPES
    assert "replanning_approval" in DECISION_CONTEXT_TYPES
    assert "resource_allocation" in DECISION_CONTEXT_TYPES
    assert "priority_arbitration" in DECISION_CONTEXT_TYPES
    assert "conflict_resolution" in DECISION_CONTEXT_TYPES
    assert "scope_authorization" in DECISION_CONTEXT_TYPES
    assert "risk_mitigation" in DECISION_CONTEXT_TYPES
    
    # Decision context status
    assert "draft" in DECISION_CONTEXT_STATUS
    assert "proposed" in DECISION_CONTEXT_STATUS
    assert "evaluated" in DECISION_CONTEXT_STATUS
    assert "recommended" in DECISION_CONTEXT_STATUS
    assert "approved" in DECISION_CONTEXT_STATUS
    assert "declined" in DECISION_CONTEXT_STATUS
    assert "executed" in DECISION_CONTEXT_STATUS
    assert "outcome_recorded" in DECISION_CONTEXT_STATUS
    assert "assessed" in DECISION_CONTEXT_STATUS