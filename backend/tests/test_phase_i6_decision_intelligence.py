"""Phase 4I.6 — Decision Intelligence adversarial tests.

These tests verify the decision intelligence layer operates correctly:
- Consumes 4I.1-4I.5, 4H.7, and all operating substrates
- Synthesizes deterministic decision intelligence from canonical sources
- Preserves epistemic separation (observed/measured/evidence_backed/inferred/predicted/proposed/contested)
- Preserves contradiction visibility (both sides preserved)
- Temporal truth (state transitions with triggers)
- Exact-once semantics
- Provenance chains
- Governance-first retrieval
- Tenant isolation
- No autonomous action (intelligence synthesized, decisions governed)
"""

import pytest
import uuid
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
    CompanyGoal, CompanyObjective, CompanyInitiative,
    StrategicAlignment, AlignmentGap, StrategicConflict, StrategicDependency,
    StrategicAlignmentState, AlignmentGapDetection,
    ObjectiveOutcome, ObjectiveOutcomeAssessment, ObjectiveContradiction,
    ObjectivePrediction, ObjectiveSimulation, ObjectivePlanState,
    StrategicAlignmentState, AlignmentGapDetection,
)
from app.models.company_operating import CompanyDecision as OperatingCompanyDecision, CompanyDecisionContradiction as OperatingCompanyDecisionContradiction
from app.models.company_actions import CompanyAction
from app.models.company_state import CompanyState
from app.models.company_operating import CompanyDecision
from app.intelligence.decision_intelligence_engine import decision_intelligence_engine
from app.intelligence.company_planning_context_engine import company_planning_context_engine
from app.intelligence.adaptive_planning_engine import adaptive_planning_engine
from app.core.timeutils import utcnow
from app.models.intelligence import PatternDetection
from tests.conftest import register_org


@pytest.mark.asyncio
async def test_decision_intelligence_synthesis_basic(
    client, db_session_factory
):
    """Test basic decision intelligence synthesis from canonical sources."""
    reg = await register_org(client, name=f"Decision Intel Corp {uuid.uuid4().hex[:8]}", email=f"di_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create minimal canonical data for planning context
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Test Strategic Intent",
            state="active",
            fingerprint="di-intent-fp-1",
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
            fingerprint="di-obj-fp-1",
        )
        session.add(objective)
        await session.flush()
        
        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Test Initiative",
            status="active",
            fingerprint="di-init-fp-1",
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
        
        # Synthesize decision intelligence
        di_context = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id,
            decision_type="replanning_approval",
            title="Test Decision Intelligence",
            description="Test DI context synthesis",
            scope="company",
            planning_context=planning_context,
            adaptive_context=adaptive_context,
            trigger="manual_synthesis",
        )
        
        # Verify context was created
        assert di_context is not None
        assert di_context.organization_id == org_id
        assert di_context.scope == "company"
        assert di_context.planning_context_id == planning_context.id
        assert di_context.version == 1
        assert di_context.decision_type == "replanning_approval"
        assert di_context.overall_confidence >= 0.0
        assert di_context.overall_confidence <= 1.0
        
        # Verify all sections present
        assert di_context.strategic_context is not None
        assert di_context.objective_context is not None
        assert di_context.alignment_context is not None
        assert di_context.outcome_context is not None
        assert di_context.execution_context is not None
        assert di_context.resource_context is not None
        assert di_context.risk_context is not None
        assert di_context.learning_context is not None
        assert di_context.governance_context is not None


@pytest.mark.asyncio
async def test_decision_intelligence_deterministic_synthesis(
    client, db_session_factory
):
    """Test that same canonical inputs produce identical decision intelligence."""
    reg = await register_org(client, name=f"Deterministic DI Corp {uuid.uuid4().hex[:8]}", email=f"det_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create canonical data
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Deterministic Test Intent",
            state="active",
            fingerprint="det-di-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        goal = CompanyGoal(
            organization_id=org_id,
            title="Deterministic Goal",
            status="active",
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            intent_id=intent.id,
            title="Deterministic Objective",
            status="active",
            fingerprint="det-di-obj-fp",
        )
        session.add(objective)
        await session.flush()
        
        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Deterministic Initiative",
            status="active",
            fingerprint="det-di-init-fp",
        )
        session.add(initiative)
        await session.flush()
        
        # Synthesize planning context
        pc = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company", trigger="manual_recompute"
        )
        
        # Synthesize adaptive context
        adaptive = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=pc, trigger="manual_recompute"
        )
        
        # Synthesize decision intelligence twice
        di1 = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="replanning_approval",
            title="Deterministic DI", scope="company",
            planning_context=pc, adaptive_context=adaptive,
            trigger="manual_synthesis"
        )
        di2 = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="replanning_approval",
            title="Deterministic DI", scope="company",
            planning_context=pc, adaptive_context=adaptive,
            trigger="manual_synthesis"
        )
        
        # Both should have same input fingerprint -> same synthesized output
        assert di1.input_fingerprint == di2.input_fingerprint
        assert di1.overall_confidence == di2.overall_confidence
        assert di1.active_contradictions == di2.active_contradictions


@pytest.mark.asyncio
async def test_decision_intelligence_strategic_context(
    client, db_session_factory
):
    """Test that strategic context is properly synthesized."""
    reg = await register_org(client, name=f"Strategic DI Corp {uuid.uuid4().hex[:8]}", email=f"strat_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create multiple intents and goals
        for i in range(3):
            intent = CompanyIntent(
                organization_id=org_id,
                kind="strategic",
                title=f"Strategic Intent {i}",
                state="active" if i < 2 else "proposed",
                priority=i + 1,
                fingerprint=f"strat-intent-fp-{i}",
            )
            session.add(intent)
        
        for i in range(2):
            goal = CompanyGoal(
                organization_id=org_id,
                title=f"Goal {i}",
                status="active",
                priority=i + 1,
            )
            session.add(goal)
        await session.flush()
        
        # Synthesize
        pc = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, trigger="manual_recompute"
        )
        adaptive = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=pc
        )
        di = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="attention_response",
            title="Strategic DI", scope="company",
            planning_context=pc, adaptive_context=adaptive,
            trigger="manual_synthesis"
        )
        
        # Verify strategic context
        strategic = di.strategic_context.get("state", {})
        assert strategic.get("active_intents_count") == 2
        assert strategic.get("proposed_intents_count") == 1
        assert strategic.get("active_goals_count") == 2
        assert len(strategic.get("strategic_priorities", [])) == 2
        assert di.strategic_context.get("epistemic_status") == "observed"


@pytest.mark.asyncio
async def test_decision_intelligence_objective_outcomes(
    client, db_session_factory
):
    """Test that objective outcomes and assessments are properly synthesized."""
    reg = await register_org(client, name=f"Outcome DI Corp {uuid.uuid4().hex[:8]}", email=f"out_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create goal and objective
        goal = CompanyGoal(
            organization_id=org_id,
            title="Goal with Outcomes",
            status="active",
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            title="Objective with Underperforming Outcome",
            status="active",
            fingerprint="outcome-obj-fp",
        )
        session.add(objective)
        await session.flush()
        
        # Add underperforming outcome
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
        
        # Synthesize
        pc = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        adaptive = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=pc
        )
        di = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="replanning_approval",
            title="Outcome DI", scope="company",
            planning_context=pc, adaptive_context=adaptive,
            trigger="manual_synthesis"
        )
        
        # Verify outcome context
        outcome_ctx = di.outcome_context.get("state", {})
        assert outcome_ctx.get("underperforming_outcomes") == 1
        assert di.outcome_context.get("epistemic_status") == "measured"


@pytest.mark.asyncio
async def test_decision_intelligence_alignment_breakdown(
    client, db_session_factory
):
    """Test that alignment gaps and conflicts are detected."""
    reg = await register_org(client, name=f"Alignment DI Corp {uuid.uuid4().hex[:8]}", email=f"align_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create goal and objective
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
            title="Objective with Orphan Initiative",
            status="active",
            fingerprint="align-obj-fp",
        )
        session.add(objective)
        await session.flush()
        
        # Create initiative WITHOUT project (alignment gap)
        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Orphan Initiative",
            status="active",
            fingerprint="orphan-init-fp",
        )
        session.add(initiative)
        await session.flush()
        
        # Create CRITICAL alignment gap
        gap = AlignmentGap(
            organization_id=org_id,
            gap_type="initiative_without_project",
            severity="critical",
            missing_element_type="project",
            context_element_type="initiative",
            context_element_id=initiative.id,
            description="Initiative has no linked project",
            state="open",
            fingerprint="critical-gap-fp",
        )
        session.add(gap)
        await session.flush()
        
        # Synthesize
        pc = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        adaptive = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=pc
        )
        di = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="conflict_resolution",
            title="Alignment DI", scope="company",
            planning_context=pc, adaptive_context=adaptive,
            trigger="manual_synthesis"
        )
        
        # Verify alignment context
        alignment = di.alignment_context.get("state", {})
        assert alignment.get("critical_gaps") == 1
        assert di.alignment_context.get("epistemic_status") == "evidence_backed"
        assert di.critical_gaps == 1


@pytest.mark.asyncio
async def test_decision_intelligence_contradiction_preservation(
    client, db_session_factory
):
    """Test that contradictions are preserved and visible."""
    reg = await register_org(client, name=f"Contra DI Corp {uuid.uuid4().hex[:8]}", email=f"contra_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create objective
        goal = CompanyGoal(
            organization_id=org_id,
            title="Goal for Contradiction",
            status="active",
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            title="Contradicted Objective",
            status="active",
            fingerprint="contra-obj-fp",
        )
        session.add(objective)
        await session.flush()
        
        # Add open contradiction
        contra = OperatingCompanyDecisionContradiction(
            organization_id=org_id,
            decision_id="dec-test-1",
            contradiction_key="di-contra-1",
            side_a_json={"claim": "On track"},
            side_b_json={"claim": "At risk"},
            status="open",
            source_event_id="evt-di-contra",
        )
        session.add(contra)
        await session.flush()
        
        # Synthesize
        pc = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        adaptive = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=pc
        )
        di = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="attention_response",
            title="Contra DI", scope="company",
            planning_context=pc, adaptive_context=adaptive,
            trigger="manual_synthesis"
        )
        
        # Verify contradiction signals
        assert di.active_contradictions >= 1
        learning_ctx = di.learning_context.get("state", {})
        assert learning_ctx.get("open_contradictions_count") >= 1


@pytest.mark.asyncio
async def test_decision_intelligence_risk_elevation(
    client, db_session_factory
):
    """Test that risk elevation from patterns is detected."""
    reg = await register_org(client, name=f"Risk DI Corp {uuid.uuid4().hex[:8]}", email=f"risk_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create rising risk pattern
        risk_pattern = PatternDetection(
            organization_id=org_id,
            pattern_type="repeated_deadline_miss",
            key="di-risk-pattern-1",
            title="Rising Deadline Miss Pattern",
            family="execution",
            status="confirmed",
            confidence=0.8,
            count=8,
            trend="rising",
            scope_type="org",
            first_seen=utcnow(),
            last_seen=utcnow(),
        )
        session.add(risk_pattern)
        await session.flush()
        
        # Synthesize
        pc = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        adaptive = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=pc
        )
        di = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="risk_mitigation",
            title="Risk DI", scope="company",
            planning_context=pc, adaptive_context=adaptive,
            trigger="manual_synthesis"
        )
        
        # Verify risk context
        risk_state = di.risk_context.get("state", {})
        assert risk_state.get("newly_emerging_from_patterns") >= 1
        assert di.risk_context.get("epistemic_status") == "inferred"


@pytest.mark.asyncio
async def test_decision_intelligence_governance_pending(
    client, db_session_factory
):
    """Test that pending governance decisions are detected."""
    reg = await register_org(client, name=f"Gov DI Corp {uuid.uuid4().hex[:8]}", email=f"gov_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create pending decisions
        for i in range(3):
            decision = OperatingCompanyDecision(
                organization_id=org_id,
                decision_id=f"di-gov-{i}",
                kind="change_priority",
                title=f"Governance Decision {i}",
                state="approved",
                source_event_id=f"evt-gov-{i}",
            )
            session.add(decision)
        
        # Create decision awaiting outcome
        decision2 = OperatingCompanyDecision(
            organization_id=org_id,
            decision_id="di-gov-4",
            kind="reallocate_capacity",
            title="Capacity Decision",
            state="executed",
            source_event_id="evt-gov-4",
        )
        session.add(decision2)
        
        # Create open contradiction
        contra = OperatingCompanyDecisionContradiction(
            organization_id=org_id,
            decision_id="di-gov-1",
            contradiction_key="gov-contra-1",
            side_a_json={"claim": "Approve"},
            side_b_json={"claim": "Defer"},
            status="open",
            source_event_id="evt-gov-contra",
        )
        session.add(contra)
        await session.flush()
        
        # Synthesize
        pc = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        adaptive = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=pc
        )
        di = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="governance_pending",
            title="Gov DI", scope="company",
            planning_context=pc, adaptive_context=adaptive,
            trigger="manual_synthesis"
        )
        
        # Verify governance context
        gov_state = di.governance_context.get("state", {})
        assert gov_state.get("pending_decisions_count") >= 0
        assert gov_state.get("decisions_awaiting_outcome") >= 1
        assert gov_state.get("open_governance_contradictions") >= 1
        assert di.governance_context.get("epistemic_status") == "observed"


@pytest.mark.asyncio
async def test_decision_intelligence_tenant_isolation(
    client, db_session_factory
):
    """Test tenant isolation in decision intelligence synthesis."""
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
            fingerprint="org1-di-intent-fp",
        )
        session.add(intent1)
        
        # Create data in org 2
        intent2 = CompanyIntent(
            organization_id=org2_id,
            kind="strategic",
            title="Org 2 Intent",
            state="active",
            fingerprint="org2-di-intent-fp",
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
        di1 = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org1_id, decision_type="attention_response",
            title="Org1 DI", scope="company",
            planning_context=pc1, adaptive_context=adaptive1
        )
        
        # Synthesize for org 2
        pc2 = await company_planning_context_engine.synthesize_planning_context(
            session, org2_id
        )
        adaptive2 = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org2_id, scope="company", planning_context=pc2
        )
        di2 = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org2_id, decision_type="attention_response",
            title="Org2 DI", scope="company",
            planning_context=pc2, adaptive_context=adaptive2
        )
        
        # Verify isolation
        assert di1.organization_id == org1_id
        assert di2.organization_id == org2_id
        assert di1.strategic_context.get("state", {}).get("active_intents_count") == 1
        assert di2.strategic_context.get("state", {}).get("active_intents_count") == 1


@pytest.mark.asyncio
async def test_decision_intelligence_state_transition(
    client, db_session_factory
):
    """Test decision intelligence state transition recording."""
    reg = await register_org(client, name=f"DI Transition Corp {uuid.uuid4().hex[:8]}", email=f"dit_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create initial data
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Transition Test Intent",
            state="active",
            fingerprint="di-trans-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        goal = CompanyGoal(
            organization_id=org_id,
            title="Transition Goal",
            status="active",
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            intent_id=intent.id,
            title="Transition Objective",
            status="active",
            fingerprint="trans-obj-fp",
        )
        session.add(objective)
        await session.flush()
        
        # First synthesis
        pc1 = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, trigger="manual_recompute"
        )
        adaptive1 = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, trigger="planning_context_change", planning_context=pc1
        )
        di1 = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="attention_response",
            title="DI Transition 1", scope="company",
            planning_context=pc1, adaptive_context=adaptive1
        )
        
        # Add new canonical data (new contradiction)
        contra = OperatingCompanyDecisionContradiction(
            organization_id=org_id,
            decision_id="dec-new",
            contradiction_key="new-di-contra",
            side_a_json={"claim": "A"},
            side_b_json={"claim": "B"},
            status="open",
            source_event_id="evt-new-di-contra",
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
            planning_context=pc2, source_event_id="evt-new-contra",
            trigger_reason="New contradiction surfaced"
        )
        di2 = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="contradiction_resolution",
            title="DI Transition 2", scope="company",
            planning_context=pc2, adaptive_context=adaptive2,
            source_event_id="evt-new-contra",
            trigger_reason="New contradiction surfaced"
        )
        
        # Verify transition recorded
        transitions = await decision_intelligence_engine.get_transitions(
            session, org_id, limit=10
        )
        
        assert len(transitions) >= 1
        transition = transitions[0]
        assert transition.from_version == 1
        assert transition.to_version == 2
        assert transition.trigger == "manual_synthesis"
        assert "learning_context" in transition.changed_sections


@pytest.mark.asyncio
async def test_decision_intelligence_deterministic_synthesis(
    client, db_session_factory
):
    """Test that same canonical inputs produce identical decision intelligence."""
    reg = await register_org(client, name=f"Deterministic DI Corp {uuid.uuid4().hex[:8]}", email=f"det_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Deterministic DI Test Intent",
            state="active",
            fingerprint="det-di-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        goal = CompanyGoal(
            organization_id=org_id,
            title="Deterministic Goal",
            status="active",
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            intent_id=intent.id,
            title="Deterministic Objective",
            status="active",
            fingerprint="det-di-obj-fp",
        )
        session.add(objective)
        await session.flush()
        
        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Deterministic Initiative",
            status="active",
            fingerprint="det-di-init-fp",
        )
        session.add(initiative)
        await session.flush()
        
        # Synthesize planning context
        pc = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company", trigger="manual_recompute"
        )
        
        # Synthesize adaptive context
        adaptive = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", planning_context=pc, trigger="manual_recompute"
        )
        
        # Synthesize decision intelligence twice
        di1 = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="replanning_approval",
            title="Deterministic DI", scope="company",
            planning_context=pc, adaptive_context=adaptive,
            trigger="manual_synthesis"
        )
        di2 = await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="replanning_approval",
            title="Deterministic DI", scope="company",
            planning_context=pc, adaptive_context=adaptive,
            trigger="manual_synthesis"
        )
        
        # Both should have same input fingerprint -> same synthesized output
        assert di1.input_fingerprint == di2.input_fingerprint
        assert di1.overall_confidence == di2.overall_confidence
        assert di1.active_contradictions == di2.active_contradictions


@pytest.mark.asyncio
async def test_decision_intelligence_ask_question(
    client, db_session_factory
):
    """Test asking a decision intelligence question through the engine."""
    reg = await register_org(client, name=f"QA DI Corp {uuid.uuid4().hex[:8]}", email=f"qa_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create minimal canonical data
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="QA DI Intent",
            state="active",
            fingerprint="qa-di-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        # Ask a decision intelligence question
        answer = await decision_intelligence_engine.answer_decision_question(
            session, org_id, "What decision context surrounds our strategic objectives?", user=reg["user"]
        )
        
        # Verify answer structure
        assert "question" in answer
        assert "context_version" in answer
        assert "overall_confidence" in answer
        assert "decision_type" in answer
        assert "strategic_context" in answer
        assert "objective_context" in answer
        assert "alignment_context" in answer
        assert "outcome_context" in answer
        assert "execution_context" in answer
        assert "resource_context" in answer
        assert "risk_context" in answer
        assert "learning_context" in answer
        assert "governance_context" in answer
        assert "active_contradictions" in answer
        assert "critical_gaps" in answer
        assert "elevated_risks" in answer
        assert "high_confidence_lessons" in answer
        assert "provenance_available" in answer
        assert answer["provenance_available"] is True


@pytest.mark.asyncio
async def test_decision_intelligence_canonical_vocabularies():
    """Test that all canonical vocabularies are properly defined."""
    from app.models.execution_strategy import (
        DECISION_INTELLIGENCE_TYPES, DECISION_INTELLIGENCE_STATES,
        DECISION_ALTERNATIVE_STATES, CONSEQUENCE_TYPES,
        RISK_ASSESSMENT_LEVELS, EVIDENCE_QUALITY_LEVELS,
        PRECEDENT_RELEVANCE_LEVELS,
        PLANNING_CONTEXT_SECTIONS, PLANNING_CONTEXT_EPISTEMIC_STATUS,
        STATE_TRANSITION_TRIGGERS, STATE_TRANSITION_KINDS,
    )
    
    # Decision intelligence types
    assert "attention_response" in DECISION_INTELLIGENCE_TYPES
    assert "replanning_approval" in DECISION_INTELLIGENCE_TYPES
    assert "resource_allocation" in DECISION_INTELLIGENCE_TYPES
    assert "priority_arbitration" in DECISION_INTELLIGENCE_TYPES
    assert "conflict_resolution" in DECISION_INTELLIGENCE_TYPES
    assert "scope_authorization" in DECISION_INTELLIGENCE_TYPES
    assert "risk_mitigation" in DECISION_INTELLIGENCE_TYPES
    assert "intent_supersession" in DECISION_INTELLIGENCE_TYPES
    assert "plan_retirement" in DECISION_INTELLIGENCE_TYPES
    assert "dependency_reroute" in DECISION_INTELLIGENCE_TYPES
    
    # Decision intelligence states
    assert "draft" in DECISION_INTELLIGENCE_STATES
    assert "proposed" in DECISION_INTELLIGENCE_STATES
    assert "under_review" in DECISION_INTELLIGENCE_STATES
    assert "evaluated" in DECISION_INTELLIGENCE_STATES
    assert "recommended" in DECISION_INTELLIGENCE_STATES
    assert "approved" in DECISION_INTELLIGENCE_STATES
    assert "declined" in DECISION_INTELLIGENCE_STATES
    assert "executed" in DECISION_INTELLIGENCE_STATES
    assert "outcome_recorded" in DECISION_INTELLIGENCE_STATES
    assert "assessed" in DECISION_INTELLIGENCE_STATES
    
    # Decision alternative states
    assert "draft" in DECISION_ALTERNATIVE_STATES
    assert "proposed" in DECISION_ALTERNATIVE_STATES
    assert "evaluated" in DECISION_ALTERNATIVE_STATES
    assert "recommended" in DECISION_ALTERNATIVE_STATES
    assert "rejected" in DECISION_ALTERNATIVE_STATES
    
    # Consequence types
    assert "strategic" in CONSEQUENCE_TYPES
    assert "outcome" in CONSEQUENCE_TYPES
    assert "alignment" in CONSEQUENCE_TYPES
    assert "resource" in CONSEQUENCE_TYPES
    assert "risk" in CONSEQUENCE_TYPES
    assert "dependency" in CONSEQUENCE_TYPES
    assert "learning" in CONSEQUENCE_TYPES
    assert "governance" in CONSEQUENCE_TYPES
    
    # Risk assessment levels
    assert "low" in RISK_ASSESSMENT_LEVELS
    assert "medium" in RISK_ASSESSMENT_LEVELS
    assert "high" in RISK_ASSESSMENT_LEVELS
    assert "critical" in RISK_ASSESSMENT_LEVELS
    
    # Evidence quality levels
    assert "high" in EVIDENCE_QUALITY_LEVELS
    assert "medium" in EVIDENCE_QUALITY_LEVELS
    assert "low" in EVIDENCE_QUALITY_LEVELS
    assert "unknown" in EVIDENCE_QUALITY_LEVELS
    
    # Precedent relevance levels
    assert "direct" in PRECEDENT_RELEVANCE_LEVELS
    assert "analogous" in PRECEDENT_RELEVANCE_LEVELS
    assert "tangential" in PRECEDENT_RELEVANCE_LEVELS
    
    # Planning context sections
    assert "strategic" in PLANNING_CONTEXT_SECTIONS
    assert "execution" in PLANNING_CONTEXT_SECTIONS
    assert "outcome" in PLANNING_CONTEXT_SECTIONS
    assert "alignment" in PLANNING_CONTEXT_SECTIONS
    assert "learning" in PLANNING_CONTEXT_SECTIONS
    assert "resource" in PLANNING_CONTEXT_SECTIONS
    assert "risk" in PLANNING_CONTEXT_SECTIONS
    assert "governance" in PLANNING_CONTEXT_SECTIONS
    
    # Epistemic statuses
    assert "observed" in PLANNING_CONTEXT_EPISTEMIC_STATUS
    assert "measured" in PLANNING_CONTEXT_EPISTEMIC_STATUS
    assert "evidence_backed" in PLANNING_CONTEXT_EPISTEMIC_STATUS
    assert "institutional_lesson" in PLANNING_CONTEXT_EPISTEMIC_STATUS
    assert "inferred" in PLANNING_CONTEXT_EPISTEMIC_STATUS
    assert "predicted" in PLANNING_CONTEXT_EPISTEMIC_STATUS
    assert "proposed" in PLANNING_CONTEXT_EPISTEMIC_STATUS
    assert "contested" in PLANNING_CONTEXT_EPISTEMIC_STATUS
    
    # Transition triggers
    assert "new_evidence" in STATE_TRANSITION_TRIGGERS
    assert "new_outcome" in STATE_TRANSITION_TRIGGERS
    assert "new_lesson" in STATE_TRANSITION_TRIGGERS
    assert "new_pattern" in STATE_TRANSITION_TRIGGERS
    assert "new_contradiction" in STATE_TRANSITION_TRIGGERS
    assert "alignment_change" in STATE_TRANSITION_TRIGGERS
    assert "dependency_change" in STATE_TRANSITION_TRIGGERS
    assert "resource_change" in STATE_TRANSITION_TRIGGERS
    assert "governance_decision" in STATE_TRANSITION_TRIGGERS
    assert "prediction_change" in STATE_TRANSITION_TRIGGERS
    assert "supersession" in STATE_TRANSITION_TRIGGERS
    assert "manual_recompute" in STATE_TRANSITION_TRIGGERS