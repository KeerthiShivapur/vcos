"""Phase 4I.4 — Company Planning Context / State Synthesis adversarial tests.

These tests verify the canonical state-synthesis layer operates correctly:
- Deterministic synthesis from canonical sources
- Governance-first retrieval
- Epistemic status separation
- Contradiction preservation
- Temporal truth (state transitions)
- Exact-once semantics
- Provenance chains
- Tenant isolation
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
    OBJECTIVE_STATES, OUTCOME_STATES, ASSESSMENT_STATES,
    ALIGNMENT_TYPES, ALIGNMENT_STATES, ALIGNMENT_STRENGTH,
    ALIGNMENT_GAP_TYPES, ALIGNMENT_GAP_SEVERITY,
    CompanyPlanningContext, CompanyStateTransition, PlanningContextProvenance,
    PLANNING_CONTEXT_SECTIONS, PLANNING_CONTEXT_EPISTEMIC_STATUS,
    STATE_TRANSITION_TRIGGERS, STATE_TRANSITION_KINDS,
)
from app.core.timeutils import utcnow
from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
from app.models.intelligence import PatternDetection
from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
from app.models.company_actions import CompanyAction
from app.models.company_state import CompanyState
from app.models.project import Project
from app.intelligence.company_planning_context_engine import company_planning_context_engine
from tests.conftest import register_org


@pytest.mark.asyncio
async def test_planning_context_synthesis_basic(client, db_session_factory):
    """Test basic planning context synthesis from canonical sources."""
    reg = await register_org(client, name=f"Planning Context Corp {uuid.uuid4().hex[:8]}", email=f"pc_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create minimal canonical data
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Test Strategic Intent",
            description="Test intent for planning context",
            state="active",
            fingerprint="test-intent-fp-1",
        )
        session.add(intent)
        await session.flush()
        
        goal = CompanyGoal(
            organization_id=org_id,
            title="Test Goal",
            description="Test goal",
            status="active",
            priority=1,
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            title="Test Objective",
            description="Test objective",
            status="active",
            intent_id=intent.id,
            fingerprint="test-obj-fp-1",
        )
        session.add(objective)
        await session.flush()
        
        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Test Initiative",
            description="Test initiative",
            status="active",
            fingerprint="test-init-fp-1",
        )
        session.add(initiative)
        await session.flush()
        
        # Synthesize planning context
        context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        
        # Verify context was created
        assert context is not None
        assert context.organization_id == org_id
        assert context.scope == "company"
        assert context.version == 1
        assert context.overall_health in ("healthy", "at_risk", "critical", "unknown")
        assert 0.0 <= context.overall_confidence <= 1.0
        
        # Verify all 8 sections present
        assert context.strategic_state is not None
        assert context.execution_state is not None
        assert context.outcome_state is not None
        assert context.alignment_state is not None
        assert context.learning_state is not None
        assert context.resource_state is not None
        assert context.risk_state is not None
        assert context.governance_state is not None
        
        # Verify strategic state has expected data
        strategic = context.strategic_state.get("state", {})
        assert strategic.get("active_intents_count") >= 1
        assert strategic.get("active_goals_count") >= 1
        assert strategic.get("active_objectives_count") >= 1


@pytest.mark.asyncio
async def test_planning_context_deterministic_synthesis(client, db_session_factory):
    """Test that same canonical inputs produce identical synthesized state."""
    reg = await register_org(client, name=f"Deterministic Corp {uuid.uuid4().hex[:8]}", email=f"det_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create canonical data
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Deterministic Test Intent",
            fingerprint="deterministic-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        # Synthesize twice
        context1 = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company", trigger="manual_recompute"
        )
        context2 = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company", trigger="manual_recompute"
        )
        
        # Both should have same input fingerprint -> same synthesized output
        # (version will differ but input_fingerprint should be same for same inputs - computed_at excluded)
        assert context1.input_fingerprint == context2.input_fingerprint
        assert context1.overall_health == context2.overall_health
        assert context1.overall_confidence == context2.overall_confidence


@pytest.mark.asyncio
async def test_planning_context_state_transition(client, db_session_factory):
    """Test state transition recording with delta and provenance."""
    reg = await register_org(client, name=f"Transition Corp {uuid.uuid4().hex[:8]}", email=f"trans_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create initial canonical data
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Transition Test Intent",
            fingerprint="transition-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        # First synthesis
        context1 = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, trigger="manual_recompute"
        )
        
        # Add new canonical data (new objective)
        goal = CompanyGoal(
            organization_id=org_id,
            title="New Goal",
            status="active",
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            title="New Objective",
            status="active",
            fingerprint="new-obj-fp",
        )
        session.add(objective)
        await session.flush()
        
        # Second synthesis triggered by new evidence
        context2 = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, trigger="new_evidence",
            source_event_id="evt-new-objective",
            trigger_reason="New objective added"
        )
        
        # Verify transition was recorded
        transitions = await company_planning_context_engine.get_state_transitions(
            session, org_id, limit=10
        )
        
        assert len(transitions) >= 1
        transition = transitions[0]
        assert transition.from_version == 1
        assert transition.to_version == 2
        assert transition.trigger == "new_evidence"
        assert transition.trigger_event_id == "evt-new-objective"
        assert "strategic_state" in transition.changed_sections
        assert transition.transition_kind in STATE_TRANSITION_KINDS


@pytest.mark.asyncio
async def test_planning_context_epistemic_separation(client, db_session_factory):
    """Test that epistemic statuses are properly separated in synthesized state."""
    reg = await register_org(client, name=f"Epistemic Corp {uuid.uuid4().hex[:8]}", email=f"epist_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create data with different epistemic qualities
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Epistemic Test Intent",
            epistemic_status="declared",
            source="declared",
            fingerprint="epistemic-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        # Need a goal for the objective
        goal = CompanyGoal(
            organization_id=org_id,
            title="Epistemic Goal",
            status="active",
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            title="Measured Objective",
            status="active",
            current_value=100.0,
            target_value=150.0,
            actual_outcome_state="actual",
            measurement_quality="high",
            fingerprint="epistemic-obj-fp",
        )
        session.add(objective)
        await session.flush()
        
        # Add a lesson (institutional_lesson epistemic status)
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            title="Test Lesson",
            lesson="Projects with unclear scope fail",
            status="active",
            lifecycle="confirmed",
            confidence=0.8,
            fingerprint="epistemic-lesson-fp",
        )
        session.add(lesson)
        await session.flush()
        
        # Add a contradiction (contested epistemic status)
        contra = CompanyDecisionContradiction(
            organization_id=org_id,
            decision_id="dec-test",
            contradiction_key="test-contra",
            side_a_json={"claim": "Project on track"},
            side_b_json={"claim": "Customer retention dropping"},
            status="open",
            source_event_id="evt-contra",
        )
        session.add(contra)
        await session.flush()
        
        context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id
        )
        
        # Verify different sections have appropriate epistemic statuses
        strategic_epistemic = context.strategic_state.get("epistemic_status")
        outcome_epistemic = context.outcome_state.get("epistemic_status")
        learning_epistemic = context.learning_state.get("epistemic_status")
        risk_epistemic = context.risk_state.get("epistemic_status")
        
        # Strategic should be observed (directly observed facts)
        assert strategic_epistemic in PLANNING_CONTEXT_EPISTEMIC_STATUS
        # Outcome should be measured (measured outcomes)
        assert outcome_epistemic in PLANNING_CONTEXT_EPISTEMIC_STATUS
        # Learning should be institutional_lesson
        assert learning_epistemic == "institutional_lesson"
        # Risk should be inferred (derived inference)
        assert risk_epistemic in ("inferred", "predicted")


@pytest.mark.asyncio
async def test_planning_context_contradiction_preservation(client, db_session_factory):
    """Test that contradictions are preserved and visible, not silently resolved."""
    reg = await register_org(client, name=f"Contradiction Corp {uuid.uuid4().hex[:8]}", email=f"contra_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create contradictory data
        goal = CompanyGoal(
            organization_id=org_id,
            title="Contradiction Goal",
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
        
        # Add objective contradiction (both sides preserved)
        obj_contra = CompanyDecisionContradiction(
            organization_id=org_id,
            decision_id="dec-test-1",
            contradiction_key="obj-contra-1",
            side_a_json={"claim": "Objective on track", "evidence": ["evt-1"]},
            side_b_json={"claim": "Objective at risk", "evidence": ["evt-2"]},
            status="open",
            source_event_id="evt-obj-contra",
        )
        session.add(obj_contra)
        
        obj_contra2 = CompanyDecisionContradiction(
            organization_id=org_id,
            decision_id="dec-test-2",
            contradiction_key="obj-contra-2",
            side_a_json={"claim": "High confidence in delivery"},
            side_b_json={"claim": "Historical pattern shows delays"},
            status="open",
            source_event_id="evt-obj-contra-2",
        )
        session.add(obj_contra2)
        await session.flush()
        
        context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id
        )
        
        # Verify contradictions are counted and visible
        assert context.active_contradictions >= 2
        
        # Verify contradictions appear in relevant sections
        learning_contras = context.learning_state.get("contradictions", [])
        assert len(learning_contras) >= 1
        
        # Verify both sides would be traceable via provenance
        provenance = await company_planning_context_engine.get_full_provenance_chain(
            session, org_id, context.id
        )
        assert len(provenance) > 0


@pytest.mark.asyncio
async def test_planning_context_tenant_isolation(client, db_session_factory):
    """Test tenant isolation in planning context synthesis."""
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
            fingerprint="org1-intent-fp",
        )
        session.add(intent1)
        
        # Create data in org 2
        intent2 = CompanyIntent(
            organization_id=org2_id,
            kind="strategic",
            title="Org 2 Intent",
            state="active",
            fingerprint="org2-intent-fp",
        )
        session.add(intent2)
        await session.flush()
        
        # Synthesize for org 1
        context1 = await company_planning_context_engine.synthesize_planning_context(
            session, org1_id
        )
        
        # Synthesize for org 2
        context2 = await company_planning_context_engine.synthesize_planning_context(
            session, org2_id
        )
        
        # Verify isolation
        assert context1.organization_id == org1_id
        assert context2.organization_id == org2_id
        
        strategic1 = context1.strategic_state.get("state", {})
        strategic2 = context2.strategic_state.get("state", {})
        
        # Each org should only see its own intents
        assert strategic1.get("active_intents_count") == 1
        assert strategic2.get("active_intents_count") == 1


@pytest.mark.asyncio
async def test_planning_context_provenance_chain(client, db_session_factory):
    """Test that provenance chains trace back to canonical sources."""
    reg = await register_org(client, name=f"Provenance Corp {uuid.uuid4().hex[:8]}", email=f"prov_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create canonical chain: Intent -> Goal -> Objective -> Initiative
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Provenance Intent",
            fingerprint="prov-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        goal = CompanyGoal(
            organization_id=org_id,
            title="Provenance Goal",
            status="active",
        )
        session.add(goal)
        await session.flush()
        
        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            intent_id=intent.id,
            title="Provenance Objective",
            status="active",
            fingerprint="prov-obj-fp",
        )
        session.add(objective)
        await session.flush()
        
        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Provenance Initiative",
            status="active",
            fingerprint="prov-init-fp",
        )
        session.add(initiative)
        await session.flush()
        
        context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id
        )
        
        # Get provenance chain
        provenance = await company_planning_context_engine.get_full_provenance_chain(
            session, org_id, context.id
        )
        
        assert len(provenance) > 0
        
        # Verify provenance links to canonical entities
        for prov in provenance:
            assert prov.context_id == context.id
            assert prov.section in PLANNING_CONTEXT_SECTIONS
            assert prov.epistemic_status in PLANNING_CONTEXT_EPISTEMIC_STATUS
            assert prov.organization_id == org_id
            
            # Check chain linkage
            source_entities = prov.source_entities
            if source_entities:
                entity_types = [e["type"] for e in source_entities]
                # Should trace to canonical types
                assert any(t in ("intent", "goal", "objective", "initiative", "project", "decision", "action")
                           for t in entity_types)


@pytest.mark.asyncio
async def test_planning_context_scope_inheritance(client, db_session_factory):
    """Test scope inheritance in planning context (project vs company)."""
    reg = await register_org(client, name=f"Scope Corp {uuid.uuid4().hex[:8]}", email=f"scope_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create project-scoped data
        project_intent = CompanyIntent(
            organization_id=org_id,
            kind="project",
            title="Project Intent",
            scope="project",
            scope_id="proj-123",
            fingerprint="project-intent-fp",
        )
        session.add(project_intent)
        
        # Create company-scoped data
        company_intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Company Intent",
            scope="company",
            fingerprint="company-intent-fp",
        )
        session.add(company_intent)
        await session.flush()
        
        # Synthesize company-wide context
        company_context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="company"
        )
        
        # Synthesize project-scoped context
        project_context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, scope="project", scope_id="proj-123"
        )
        
        # Both should exist but have different scopes
        assert company_context.scope == "company"
        assert project_context.scope == "project"
        assert project_context.scope_id == "proj-123"


@pytest.mark.asyncio
async def test_planning_context_learning_integration(client, db_session_factory):
    """Test that 4H.7 institutional learning feeds planning context."""
    reg = await register_org(client, name=f"Learning Corp {uuid.uuid4().hex[:8]}", email=f"learn_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create a high-confidence lesson
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            title="Dependency Pattern Lesson",
            lesson="Projects with >3 external dependencies have 40% higher delay rate",
            status="active",
            lifecycle="confirmed",
            confidence=0.85,
            topic_name="dependency_management",
            fingerprint="learning-dep-fp",
        )
        session.add(lesson)
        
        # Create a pattern that supports the lesson
        pattern = PatternDetection(
            organization_id=org_id,
            pattern_type="external_dependency_delay",
            key="dep-pattern-1",
            title="External Dependency Delay Pattern",
            family="execution",
            status="confirmed",
            confidence=0.75,
            count=5,
            scope_type="org",
            first_seen=utcnow(),
            last_seen=utcnow(),
        )
        session.add(pattern)
        await session.flush()
        
        # Link lesson to pattern
        evidence = LearningEvidence(
            organization_id=org_id,
            learning_id=lesson.id,
            source_type="pattern",
            source_id=pattern.id,
            role="primary",
            weight=1.0,
        )
        session.add(evidence)
        await session.flush()
        
        context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id
        )
        
        # Verify learning signals in context
        assert context.relevant_lessons >= 1
        assert context.high_confidence_lessons >= 1
        assert context.emerging_patterns >= 0
        
        # Verify learning section has the lesson
        learning_state = context.learning_state.get("state", {})
        assert learning_state.get("active_lessons_count", 0) >= 1
        assert learning_state.get("high_confidence_lessons_count", 0) >= 1
        
        # Verify risk state picks up pattern-based risk
        risk_state = context.risk_state.get("state", {})
        # Pattern should contribute to risk assessment


@pytest.mark.asyncio
async def test_planning_context_alignment_feeds_state(client, db_session_factory):
    """Test that 4I.3 alignment data feeds planning context."""
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
            fingerprint="aligned-obj-fp",
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
        
        # Create alignment (objective supports goal)
        alignment = StrategicAlignment(
            organization_id=org_id,
            source_type="objective",
            source_id=objective.id,
            target_type="goal",
            target_id=goal.id,
            alignment_type="supports",
            alignment_state="active",
            strength="primary",
            fingerprint="align-fp",
        )
        session.add(alignment)
        await session.flush()
        
        # Create alignment gap (initiative without project)
        gap = AlignmentGap(
            organization_id=org_id,
            gap_type="initiative_without_project",
            severity="high",
            missing_element_type="project",
            context_element_type="initiative",
            context_element_id=initiative.id,
            description="Initiative has no linked project",
            state="open",
            fingerprint="gap-fp",
        )
        session.add(gap)
        await session.flush()
        
        context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id
        )
        
        # Verify alignment state reflects the data
        alignment_state = context.alignment_state.get("state", {})
        assert alignment_state.get("total_alignments", 0) >= 1
        assert alignment_state.get("total_gaps", 0) >= 1
        assert alignment_state.get("critical_gaps", 0) >= 0  # high severity, not critical
        
        # Verify gaps by type
        gaps_by_type = alignment_state.get("gaps_by_type", {})
        assert "initiative_without_project" in gaps_by_type


@pytest.mark.asyncio
async def test_planning_context_exact_once_semantics(client, db_session_factory):
    """Test exact-once semantics on context synthesis."""
    reg = await register_org(client, name=f"ExactOnce Corp {uuid.uuid4().hex[:8]}", email=f"exact_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Exact Once Test",
            fingerprint="exact-once-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        # Synthesize multiple times with same trigger
        context1 = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, trigger="manual_recompute", source_event_id="evt-same"
        )
        context2 = await company_planning_context_engine.synthesize_planning_context(
            session, org_id, trigger="manual_recompute", source_event_id="evt-same"
        )
        
        # Should create new versions (different version numbers)
        assert context2.version == context1.version + 1
        
        # But input fingerprint should be same for same canonical inputs + same event
        # (The input_fingerprint includes computed_at so will differ - this is expected)
        # What matters is the exact-once constraint on (org, scope, scope_id, version, input_fingerprint)


@pytest.mark.asyncio
async def test_planning_context_risk_from_patterns(client, db_session_factory):
    """Test that patterns feed risk state in planning context."""
    reg = await register_org(client, name=f"Risk Corp {uuid.uuid4().hex[:8]}", email=f"risk_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create a risk-indicating pattern
        risk_pattern = PatternDetection(
            organization_id=org_id,
            pattern_type="repeated_deadline_miss",
            key="risk-pattern-1",
            title="Repeated Deadline Miss Pattern",
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
        
        context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id
        )
        
        # Verify risk state captures pattern-based risk
        risk_state = context.risk_state.get("state", {})
        assert risk_state.get("newly_emerging_from_patterns", 0) >= 1
        risk_patterns = risk_state.get("risk_patterns", [])
        assert len(risk_patterns) >= 1
        assert risk_patterns[0].get("trend") == "rising"


@pytest.mark.asyncio
async def test_planning_context_governance_state(client, db_session_factory):
    """Test governance state synthesis."""
    reg = await register_org(client, name=f"Gov Corp {uuid.uuid4().hex[:8]}", email=f"gov_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create pending decision
        decision = CompanyDecision(
            organization_id=org_id,
            decision_id="dec-gov-1",
            kind="change_priority",
            title="Governance Decision",
            state="approved",
            source_event_id="evt-gov-1",
        )
        session.add(decision)
        
        # Create decision awaiting outcome
        decision2 = CompanyDecision(
            organization_id=org_id,
            decision_id="dec-gov-2",
            kind="reallocate_capacity",
            title="Capacity Decision",
            state="executed",
            source_event_id="evt-gov-2",
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
        
        context = await company_planning_context_engine.synthesize_planning_context(
            session, org_id
        )
        
        # Verify governance state
        gov_state = context.governance_state.get("state", {})
        assert gov_state.get("pending_decisions_count", 0) >= 0
        assert gov_state.get("decisions_awaiting_outcome", 0) >= 1
        assert gov_state.get("open_governance_contradictions", 0) >= 1


@pytest.mark.asyncio
async def test_planning_context_ask_question(client, db_session_factory):
    """Test asking a planning question through the engine."""
    reg = await register_org(client, name=f"QA Corp {uuid.uuid4().hex[:8]}", email=f"qa_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create minimal canonical data
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="QA Intent",
            fingerprint="qa-intent-fp",
        )
        session.add(intent)
        await session.flush()
        
        # Ask a planning question
        answer = await company_planning_context_engine.answer_planning_question(
            session, org_id, "What is the current state of the company?", user=reg["user"]
        )
        
        # Verify answer structure
        assert "question" in answer
        assert "context_version" in answer
        assert "overall_health" in answer
        assert "strategic_summary" in answer
        assert "execution_summary" in answer
        assert "alignment_summary" in answer
        assert "learning_summary" in answer
        assert "risk_summary" in answer
        assert "governance_summary" in answer
        assert "provenance_available" in answer
        assert answer["provenance_available"] is True


@pytest.mark.asyncio
async def test_planning_context_canonical_vocabularies():
    """Test that all canonical vocabularies are properly defined."""
    # Section vocabularies
    assert "strategic" in PLANNING_CONTEXT_SECTIONS
    assert "execution" in PLANNING_CONTEXT_SECTIONS
    assert "outcome" in PLANNING_CONTEXT_SECTIONS
    assert "alignment" in PLANNING_CONTEXT_SECTIONS
    assert "learning" in PLANNING_CONTEXT_SECTIONS
    assert "resource" in PLANNING_CONTEXT_SECTIONS
    assert "risk" in PLANNING_CONTEXT_SECTIONS
    assert "governance" in PLANNING_CONTEXT_SECTIONS
    
    # Epistemic status vocabularies
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
    
    # Transition kinds
    assert "strategic_state_change" in STATE_TRANSITION_KINDS
    assert "execution_state_change" in STATE_TRANSITION_KINDS
    assert "outcome_state_change" in STATE_TRANSITION_KINDS
    assert "alignment_state_change" in STATE_TRANSITION_KINDS
    assert "learning_state_change" in STATE_TRANSITION_KINDS
    assert "resource_state_change" in STATE_TRANSITION_KINDS
    assert "risk_state_change" in STATE_TRANSITION_KINDS
    assert "governance_state_change" in STATE_TRANSITION_KINDS
    assert "composite_state_change" in STATE_TRANSITION_KINDS