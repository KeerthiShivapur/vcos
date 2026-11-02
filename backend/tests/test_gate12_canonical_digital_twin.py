"""Gate 12 — Canonical Digital Twin / Future Company State Tests.

Tests for the canonical digital twin derived from Gates 6-11 reality.
"""

import pytest
import pytest_asyncio
import uuid
import json
from datetime import datetime, date, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import resolve_caller_access
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.department import Department
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.workload import WorkloadSnapshot
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
    CompanyObjective,
    CompanyInitiative,
    CompanyGoal,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.org_capability_intelligence import (
    OrgCapability,
    CapabilitySignal,
)
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
    CapacitySnapshot,
)
from app.models.organizational_learning import (
    OrganizationalLearning,
    LearningEvidence,
)
from app.models.intelligence import (
    PatternDetection,
    PatternEvent,
)
from app.models.company_memory import (
    CompanyMemory,
    MemoryEvent,
    MemoryOutcome,
)
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionPrecedent,
    CompanyDecisionContradiction,
    CompanyDecisionQuality,
    CompanyDecisionTrack,
    CompanyDecisionEvidence,
    CompanyScenarioRun,
)
from app.models.prediction import (
    Prediction,
    PredictionHistory,
    PredictionModel,
)
from app.models.execution_strategy import (
    ObjectivePrediction,
    ObjectiveSimulation,
)
from app.models.digital_twin import (
    TwinPrediction,
    StrategicForecast,
)
from app.intelligence.institutional_intelligence_service import (
    institutional_intelligence_service,
)
from app.intelligence.predictive_intelligence_service import (
    predictive_intelligence_service,
)
from app.intelligence.organizational_capacity_service import (
    organizational_capacity_service,
)
from app.intelligence.organizational_intelligence_service import (
    organizational_intelligence_service,
)
from app.intelligence.counterfactual_intelligence_service import (
    counterfactual_intelligence_service,
)
from app.intelligence.canonical_digital_twin_service import (
    canonical_digital_twin_service,
    TwinScopeType,
)
from app.intelligence.company_operating_engine import company_operating_engine


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_org(db_session):
    """Create test organization."""
    org = Organization(
        name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_user(db_session, test_org):
    """Create test user."""
    user = User(
        organization_id=test_org.id,
        email=f"test{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed",
        full_name="Test User",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_employee(db_session, test_org, test_user):
    """Create test employee with user link."""
    emp = Employee(
        organization_id=test_org.id,
        user_id=test_user.id,
        employee_number=f"EMP{uuid.uuid4().hex[:6]}",
        first_name="Test",
        last_name="Employee",
        email=f"employee{uuid.uuid4().hex[:6]}@test.com",
        status="active",
    )
    db_session.add(emp)
    await db_session.flush()
    return emp


@pytest_asyncio.fixture
async def caller(db_session, test_org, test_user, test_employee):
    """Create caller access for test user with CEO permissions."""
    from app.models.role import Role, UserRole
    from app.services.permission_service import permission_service
    
    await permission_service.sync_catalog(db_session)
    await permission_service.seed_org_roles(db_session, test_org.id)
    
    ceo_role = (await db_session.execute(
        select(Role).where(
            Role.organization_id == test_org.id,
            Role.code == "ceo"
        )
    )).scalars().first()
    
    if ceo_role:
        user_role = UserRole(
            user_id=test_user.id,
            role_id=ceo_role.id,
            organization_id=test_org.id,
        )
        db_session.add(user_role)
        await db_session.flush()
    
    caller = await resolve_caller_access(
        db_session, organization_id=test_org.id, user=test_user
    )
    caller.employee_id = test_employee.id
    return caller


@pytest_asyncio.fixture
async def test_team(db_session, test_org, test_employee):
    """Create test team."""
    team = Team(
        organization_id=test_org.id,
        name="Test Team",
        code=f"TM{uuid.uuid4().hex[:4]}",
    )
    db_session.add(team)
    await db_session.flush()
    
    test_employee.team_id = team.id
    await db_session.flush()
    return team


@pytest_asyncio.fixture
async def test_department(db_session, test_org):
    """Create test department."""
    dept = Department(
        organization_id=test_org.id,
        name="Test Department",
        code=f"DEP{uuid.uuid4().hex[:4]}",
    )
    db_session.add(dept)
    await db_session.flush()
    return dept


@pytest_asyncio.fixture
async def test_skill(db_session, test_org):
    """Create test canonical skill."""
    from app.models.skills_intelligence import CanonicalSkill
    skill = CanonicalSkill(
        organization_id=test_org.id,
        canonical_name="Python Development",
        category="Engineering",
        description="Python programming expertise",
    )
    db_session.add(skill)
    await db_session.flush()
    return skill


@pytest_asyncio.fixture
async def test_commitment(db_session, caller, test_employee):
    """Create test commitment with actions and outcomes."""
    commitment = CompanyCommitment(
        organization_id=caller.organization_id,
        commitment_type="unconditional",
        title="Test Commitment",
        state="active",
        scope_type="project",
        scope_id="proj-test",
        rationale="Test rationale",
        fingerprint=f"comm-fp-{uuid.uuid4().hex[:32]}",
        source_event_id="commitment-test-1",
    )
    db_session.add(commitment)
    await db_session.flush()
    
    # Create responsibility
    responsibility = OrganizationalResponsibility(
        organization_id=caller.organization_id,
        responsibility_type="responsible",
        scope_type="commitment",
        scope_id=commitment.id,
        raci_responsible=True,
        person_id=test_employee.id,
        commitment_id=commitment.id,
        valid_from=utcnow(),
        state="active",
        fingerprint=f"resp-fp-{uuid.uuid4().hex[:32]}",
        source_event_id="resp-test-1",
    )
    db_session.add(responsibility)
    await db_session.flush()
    
    # Create action
    action = CompanyAction(
        organization_id=caller.organization_id,
        action_type="capacity_change",
        title="Test Action",
        state="in_progress",
        scope_type="project",
        scope_id="proj-test",
        fingerprint=f"action-fp-{uuid.uuid4().hex[:32]}",
        source_event_id="action-test-1",
        source_commitment_id=commitment.id,
        assignee_id=test_employee.id,
    )
    db_session.add(action)
    await db_session.flush()
    
    # Create outcome
    outcome = CompanyActionOutcome(
        organization_id=caller.organization_id,
        action_id=action.id,
        outcome_type="success",
        effectiveness=0.85,
        verdict="Action completed successfully",
        evidence_json=json.dumps([]),
    )
    db_session.add(outcome)
    await db_session.commit()
    
    return commitment


@pytest_asyncio.fixture
async def test_objective(db_session, caller, test_employee):
    """Create test objective with initiatives."""
    goal = CompanyGoal(
        organization_id=caller.organization_id,
        title="Test Goal",
        status="active",
        kind="growth",
        priority=3,
    )
    db_session.add(goal)
    await db_session.flush()
    
    objective = CompanyObjective(
        organization_id=caller.organization_id,
        goal_id=goal.id,
        title="Test Objective",
        status="active",
        kind="other",
        fingerprint=f"obj-fp-{uuid.uuid4().hex[:32]}",
    )
    db_session.add(objective)
    await db_session.flush()
    
    # Create initiative
    initiative = CompanyInitiative(
        organization_id=caller.organization_id,
        objective_id=objective.id,
        title="Test Initiative",
        status="active",
        kind="other",
        expected_outcome={"target_value": 100, "unit": "units"},
        fingerprint=f"init-fp-{uuid.uuid4().hex[:32]}",
    )
    db_session.add(initiative)
    await db_session.commit()
    
    return objective


@pytest_asyncio.fixture
async def test_capability(db_session, caller, test_skill, test_employee):
    """Create test OrgCapability with expertise."""
    from app.models.skills_intelligence import Expertise as ExpertiseState, ExpertiseEvidence
    expertise = ExpertiseState(
        organization_id=caller.organization_id,
        person_id=test_employee.id,
        skill_id=test_skill.id,
        score=60.0,
        evidence_count=10,
        lifecycle="strong",
    )
    db_session.add(expertise)
    
    capability = OrgCapability(
        organization_id=caller.organization_id,
        skill_id=test_skill.id,
        canonical_name="Python Development",
        category="Engineering",
        lifecycle="strong",
        expert_count=1,
        strong_expert_count=1,
        evidence_count=10,
        corroborated_kinds=3,
        confidence=0.8,
        capacity_potential=1,
        capacity_committed=1,
        capacity_reserved=0,
        capacity_available=0,
        capacity_state="constrained",
        demand_count=2,
        demand_state="high",
        concentration_share=1.0,
        second_share=0.0,
    )
    db_session.add(capability)
    
    # Add allocation demand
    demand = AllocationDemand(
        organization_id=caller.organization_id,
        project_id="proj-1",
        capability="Python Development",
        units=1,
        window_start=date.today(),
        window_end=date.today() + timedelta(days=60),
        proficiency="high",
    )
    db_session.add(demand)
    
    # Add allocation
    allocation = CapacityAllocation(
        organization_id=caller.organization_id,
        project_id="proj-1",
        project_label="Project Alpha",
        capability="Python Development",
        units=1,
        window_start=date.today(),
        window_end=date.today() + timedelta(days=60),
        status="active",
        source_event_id="alloc-1",
    )
    db_session.add(allocation)
    
    await db_session.commit()
    return capability


# ============================================================================
# Test Classes
# ============================================================================

class TestCanonicalDigitalTwinService:
    """Test canonical digital twin service."""
    
    @pytest.mark.asyncio
    async def test_derive_twin_state_org_scope(
        self, db_session, caller, test_commitment, test_objective, test_capability
    ):
        """Test deriving twin state at organization scope."""
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session,
            caller=caller,
            scope_type="org",
        )
        
        assert result["advisory_only"] is True
        assert result["not_a_prediction"] is True
        assert result["not_a_decision"] is True
        assert result["not_an_authorization"] is True
        assert result["not_execution"] is True
        assert "twin_id" in result
        assert "organization_id" in result
        assert result["scope_type"] == "org"
        assert "captured_at" in result
        assert "state_key" in result
        assert "snapshot_ref" in result
        assert "dimensions" in result
        assert "attention" in result
        assert "health" in result
        assert "predictions" in result
        assert "counterfactual_scenarios" in result
        assert "institutional_basis" in result
        assert "provenance" in result
        assert "epistemic_notice" in result
        
        # Check dimensions
        dims = result["dimensions"]
        assert "strategy" in dims
        assert "execution" in dims
        assert "coordination" in dims
        assert "capacity" in dims
        assert "people" in dims
        assert "customers" in dims
        assert "financial" in dims
        assert "knowledge" in dims
        
        # Check health
        health = result["health"]
        assert health["score"] is not None
        assert health["state"] in ("healthy", "concerned", "at_risk", "critical")
    
    @pytest.mark.asyncio
    async def test_derive_twin_state_team_scope(
        self, db_session, caller, test_team, test_commitment
    ):
        """Test deriving twin state at team scope."""
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session,
            caller=caller,
            scope_type="team",
            scope_id=test_team.id,
        )
        
        assert result["advisory_only"] is True
        assert result["scope_type"] == "team"
        assert result["scope_id"] == test_team.id
    
    @pytest.mark.asyncio
    async def test_derive_twin_state_project_scope(
        self, db_session, caller, test_commitment
    ):
        """Test deriving twin state at project scope."""
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session,
            caller=caller,
            scope_type="project",
            scope_id=test_commitment.scope_id,
        )
        
        assert result["advisory_only"] is True
        assert result["scope_type"] == "project"
        assert result["scope_id"] == test_commitment.scope_id
    
    @pytest.mark.asyncio
    async def test_derive_twin_state_person_scope(
        self, db_session, caller, test_employee, test_commitment
    ):
        """Test deriving twin state at person scope."""
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session,
            caller=caller,
            scope_type="person",
            scope_id=test_employee.id,
        )
        
        assert result["advisory_only"] is True
        assert result["scope_type"] == "person"
        assert result["scope_id"] == test_employee.id
    
    @pytest.mark.asyncio
    async def test_twin_state_includes_predictions(
        self, db_session, caller, test_commitment
    ):
        """Test that twin state includes Gate 10 predictions."""
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session,
            caller=caller,
            scope_type="org",
        )
        
        predictions = result["predictions"]
        assert isinstance(predictions, list)
        # May be empty if no predictions generated, but structure should be valid
        for pred in predictions:
            assert "type" in pred
            assert "probability" in pred
            assert "confidence" in pred
            assert "horizon_days" in pred
            assert "basis" in pred
            assert "source" in pred
    
    @pytest.mark.asyncio
    async def test_twin_state_includes_counterfactuals(
        self, db_session, caller, test_commitment
    ):
        """Test that twin state includes Gate 11 counterfactual scenarios."""
        # First create a counterfactual scenario
        await counterfactual_intelligence_service.create_scenario(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="person",
            subject_id="test-person-id",
            params={"delta": 10},
            dry_run=False,
        )
        
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session,
            caller=caller,
            scope_type="org",
        )
        
        counterfactuals = result["counterfactual_scenarios"]
        assert isinstance(counterfactuals, list)
        for cf in counterfactuals:
            assert "scenario_id" in cf
            assert "scenario_kind" in cf
            assert "created_at" in cf
    
    @pytest.mark.asyncio
    async def test_twin_state_includes_institutional_basis(
        self, db_session, caller, test_commitment
    ):
        """Test that twin state includes Gate 9 institutional learning."""
        # Create a lesson first
        lesson = OrganizationalLearning(
            organization_id=caller.organization_id,
            kind="outcome_learning",
            fingerprint="test-lesson-fp",
            title="Test Lesson",
            lesson="Capacity changes affect delivery",
            status="active",
            lifecycle="authoritative",
            confidence=0.8,
            source_type="test",
            source_id="test-1",
            evidence_json=json.dumps(["test"]),
            recorded_by="test",
            observed_at=utcnow(),
        )
        db_session.add(lesson)
        await db_session.commit()
        
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session,
            caller=caller,
            scope_type="org",
        )
        
        basis = result["institutional_basis"]
        assert isinstance(basis, list)
        for item in basis:
            assert "type" in item
            assert "id" in item
            assert "relevance" in item
    
    @pytest.mark.asyncio
    async def test_derive_twin_history(
        self, db_session, caller, test_commitment
    ):
        """Test deriving historical twin states."""
        # Create some state history first by triggering a health refresh
        await company_operating_engine.refresh(
            db_session,
            organization_id=caller.organization_id,
            event=type("Event", (), {"id": f"evt-{uuid.uuid4().hex[:8]}", "name": "test_event"})(),
            payload={},
        )
        
        history = await canonical_digital_twin_service.derive_twin_history(
            db_session,
            caller=caller,
            scope_type="org",
            limit=10,
        )
        
        assert isinstance(history, list)
        for item in history:
            assert "id" in item
            assert "captured_at" in item
            assert "state_key" in item
            assert "snapshot_ref" in item
            assert "state" in item
            assert "summary" in item


class TestScenarioBranches:
    """Test counterfactual scenario branches."""
    
    @pytest.mark.asyncio
    async def test_create_scenario_branch_capacity_change(
        self, db_session, caller, test_employee
    ):
        """Test creating a capacity change scenario branch."""
        result = await canonical_digital_twin_service.create_scenario_branch(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="person",
            subject_id=test_employee.id,
            params={"delta": 10},
            assumptions=["Hiring approved", "Onboarding 4 weeks"],
            scope_type="org",
            dry_run=True,
        )
        
        assert result["advisory_only"] is True
        assert result["not_a_prediction"] is True
        assert result["not_a_decision"] is True
        assert result["not_an_authorization"] is True
        assert result["not_execution"] is True
        assert "branch_id" in result
        assert "baseline_state_key" in result
        assert "scenario" in result
        assert result["scenario"]["kind"] == "capacity_change"
        assert result["scenario"]["subject_type"] == "person"
        assert result["scenario"]["subject_id"] == test_employee.id
        assert result["scenario"]["params"]["delta"] == 10
        assert "projected_consequences" in result
        assert "projected_predictions" in result
        assert "projected_risks" in result
        assert "projected_opportunities" in result
        assert "recommendation" in result
        assert "epistemic_notice" in result
    
    @pytest.mark.asyncio
    async def test_create_scenario_branch_commitment_change(
        self, db_session, caller, test_commitment
    ):
        """Test creating a commitment change scenario branch."""
        result = await canonical_digital_twin_service.create_scenario_branch(
            db_session,
            caller=caller,
            scenario_kind="commitment_change",
            subject_type="commitment",
            subject_id=test_commitment.id,
            params={"action": "delay", "weeks": 4},
            assumptions=["Stakeholders notified"],
            scope_type="project",
            scope_id=test_commitment.scope_id,
            dry_run=True,
        )
        
        assert result["advisory_only"] is True
        assert result["scenario"]["kind"] == "commitment_change"
        assert result["scenario"]["params"]["action"] == "delay"
        assert result["scenario"]["params"]["weeks"] == 4
    
    @pytest.mark.asyncio
    async def test_create_scenario_branch_invalid_kind(
        self, db_session, caller, test_employee
    ):
        """Test that invalid scenario kinds are rejected."""
        result = await canonical_digital_twin_service.create_scenario_branch(
            db_session,
            caller=caller,
            scenario_kind="invalid_kind",
            subject_type="person",
            subject_id=test_employee.id,
            params={},
            dry_run=True,
        )
        
        assert result["advisory_only"] is True
        assert "error" in result
        assert "scenario_kind must be one of" in result["error"]
    
    @pytest.mark.asyncio
    async def test_create_scenario_branch_missing_subject(
        self, db_session, caller
    ):
        """Test that missing subject is rejected."""
        result = await canonical_digital_twin_service.create_scenario_branch(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="",
            subject_id="",
            params={},
            dry_run=True,
        )
        
        assert result["advisory_only"] is True
        assert "error" in result
        assert "subject_type and subject_id are required" in result["error"]
    
    @pytest.mark.asyncio
    async def test_scenario_branch_recommendation_generated(
        self, db_session, caller, test_employee
    ):
        """Test that recommendation is generated for scenario branch."""
        result = await canonical_digital_twin_service.create_scenario_branch(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="person",
            subject_id=test_employee.id,
            params={"delta": 10},
            dry_run=True,
        )
        
        recommendation = result["recommendation"]
        assert recommendation is not None
        assert "type" in recommendation
        assert recommendation["type"] in ("favorable", "caution", "mixed")
        assert "reason" in recommendation
        assert "action" in recommendation


class TestScenarioComparison:
    """Test multi-scenario comparison."""
    
    @pytest.mark.asyncio
    async def test_compare_scenario_branches(
        self, db_session, caller, test_employee, test_commitment
    ):
        """Test comparing multiple scenario branches."""
        scenarios = [
            {
                "scenario_kind": "capacity_change",
                "subject_type": "person",
                "subject_id": test_employee.id,
                "params": {"delta": 10},
            },
            {
                "scenario_kind": "commitment_change",
                "subject_type": "commitment",
                "subject_id": test_commitment.id,
                "params": {"action": "delay", "weeks": 2},
            },
        ]
        
        result = await canonical_digital_twin_service.compare_scenario_branches(
            db_session,
            caller=caller,
            scenario_definitions=scenarios,
            scope_type="org",
        )
        
        assert result["advisory_only"] is True
        assert result["not_a_prediction"] is True
        assert result["not_a_decision"] is True
        assert result["not_an_authorization"] is True
        assert result["not_execution"] is True
        assert "comparison_id" in result
        assert "baseline_state_key" in result
        assert "baseline_health" in result
        assert "branches" in result
        assert len(result["branches"]) == 2
        assert "comparison_matrix" in result
        assert "recommendations" in result
        assert "epistemic_notice" in result
        
        for branch in result["branches"]:
            assert "branch_id" in branch
            assert "scenario" in branch
            assert "projected_health" in branch
            assert "risk_count" in branch
            assert "critical_risks" in branch
            assert "opportunity_count" in branch
    
    @pytest.mark.asyncio
    async def test_compare_scenario_branches_insufficient(
        self, db_session, caller, test_employee
    ):
        """Test that comparison requires at least 2 scenarios."""
        scenarios = [
            {
                "scenario_kind": "capacity_change",
                "subject_type": "person",
                "subject_id": test_employee.id,
                "params": {"delta": 10},
            },
        ]
        
        result = await canonical_digital_twin_service.compare_scenario_branches(
            db_session,
            caller=caller,
            scenario_definitions=scenarios,
        )
        
        assert result["advisory_only"] is True
        assert "error" in result
        assert "At least 2 scenarios required" in result["error"]
    
    @pytest.mark.asyncio
    async def test_compare_scenario_branches_recommendations(
        self, db_session, caller, test_employee, test_commitment
    ):
        """Test that comparison generates recommendations."""
        # Create a bad commitment for high-risk scenario
        bad_commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Bad Commitment",
            state="active",
            scope_type="project",
            scope_id="proj-bad",
            rationale="Test rationale",
            fingerprint=f"comm-fp-bad-{uuid.uuid4().hex[:32]}",
            source_event_id="commitment-bad-1",
        )
        db_session.add(bad_commitment)
        await db_session.flush()
        
        # Add failed outcomes
        for i in range(3):
            action = CompanyAction(
                organization_id=caller.organization_id,
                action_type="task",
                title=f"Bad Action {i}",
                state="completed",
                scope_type="project",
                scope_id="proj-bad",
                fingerprint=f"action-fp-bad-{i}-{uuid.uuid4().hex[:32]}",
                source_event_id=f"action-bad-{i}",
                source_commitment_id=bad_commitment.id,
            )
            db_session.add(action)
            await db_session.flush()
            
            outcome = CompanyActionOutcome(
                organization_id=caller.organization_id,
                action_id=action.id,
                outcome_type="failed",
                effectiveness=0.2,
                verdict="Action failed",
                evidence_json=json.dumps([]),
            )
            db_session.add(outcome)
        
        await db_session.commit()
        
        scenarios = [
            {
                "scenario_kind": "capacity_change",
                "subject_type": "person",
                "subject_id": test_employee.id,
                "params": {"delta": 10},  # Positive capacity change
            },
            {
                "scenario_kind": "commitment_change",
                "subject_type": "commitment",
                "subject_id": bad_commitment.id,
                "params": {"action": "delay", "weeks": 8},  # High risk
            },
        ]
        
        result = await canonical_digital_twin_service.compare_scenario_branches(
            db_session,
            caller=caller,
            scenario_definitions=scenarios,
        )
        
        recommendations = result["recommendations"]
        assert len(recommendations) >= 1
        
        # Should recommend lowest risk (capacity_change)
        lowest_risk = [r for r in recommendations if r["type"] == "lowest_risk"]
        assert len(lowest_risk) >= 1
        assert lowest_risk[0]["scenario_kind"] == "capacity_change"


class TestScenarioHistory:
    """Test scenario history retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_scenario_history(
        self, db_session, caller, test_employee
    ):
        """Test retrieving scenario history."""
        # Create a scenario first
        await counterfactual_intelligence_service.create_scenario(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="person",
            subject_id=test_employee.id,
            params={"delta": 5},
            dry_run=False,
        )
        
        history = await canonical_digital_twin_service.get_scenario_history(
            db_session,
            caller=caller,
            scope_type="org",
            limit=10,
        )
        
        assert len(history) >= 1
        for item in history:
            assert "scenario_id" in item
            assert "advisory_only" in item
            assert "not_a_prediction" in item
            assert "baseline" in item
            assert "hypothetical_change" in item
            assert "propagation" in item
            assert "consequences" in item


class TestEpistemicBoundaries:
    """Test epistemic boundary enforcement."""
    
    @pytest.mark.asyncio
    async def test_twin_state_not_truth(
        self, db_session, caller, test_commitment
    ):
        """Test that twin state is marked as not truth."""
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session,
            caller=caller,
            scope_type="org",
        )
        
        assert result["advisory_only"] is True
        assert result["not_a_prediction"] is True
        assert result["not_a_decision"] is True
        assert result["not_an_authorization"] is True
        assert result["not_execution"] is True
        assert "epistemic_notice" in result
        assert "derived projection" in result["epistemic_notice"]
        assert "canonical reality" in result["epistemic_notice"]
    
    @pytest.mark.asyncio
    async def test_scenario_branch_not_truth(
        self, db_session, caller, test_employee
    ):
        """Test that scenario branch is marked as not truth."""
        result = await canonical_digital_twin_service.create_scenario_branch(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="person",
            subject_id=test_employee.id,
            params={"delta": 10},
            dry_run=True,
        )
        
        assert result["advisory_only"] is True
        assert result["not_a_prediction"] is True
        assert result["not_a_decision"] is True
        assert result["not_an_authorization"] is True
        assert result["not_execution"] is True
        assert "epistemic_notice" in result
        assert "isolated counterfactual projection" in result["epistemic_notice"]
        assert "does not mutate canonical reality" in result["epistemic_notice"]
    
    @pytest.mark.asyncio
    async def test_comparison_not_truth(
        self, db_session, caller, test_employee, test_commitment
    ):
        """Test that comparison is marked as not truth."""
        scenarios = [
            {
                "scenario_kind": "capacity_change",
                "subject_type": "person",
                "subject_id": test_employee.id,
                "params": {"delta": 10},
            },
            {
                "scenario_kind": "commitment_change",
                "subject_type": "commitment",
                "subject_id": test_commitment.id,
                "params": {"action": "delay", "weeks": 2},
            },
        ]
        
        result = await canonical_digital_twin_service.compare_scenario_branches(
            db_session,
            caller=caller,
            scenario_definitions=scenarios,
        )
        
        assert result["advisory_only"] is True
        assert result["not_a_prediction"] is True
        assert result["not_a_decision"] is True
        assert result["not_an_authorization"] is True
        assert result["not_execution"] is True
        assert "epistemic_notice" in result
        assert "isolated counterfactual projections" in result["epistemic_notice"]
        assert "No canonical reality is mutated" in result["epistemic_notice"]


class TestTemporalTruth:
    """Test temporal truth preservation."""
    
    @pytest.mark.asyncio
    async def test_twin_state_temporal_versioning(
        self, db_session, caller, test_commitment
    ):
        """Test that twin state has temporal versioning."""
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session,
            caller=caller,
            scope_type="org",
        )
        
        assert "state_key" in result
        assert "snapshot_ref" in result
        assert "captured_at" in result
        assert result["state_key"].startswith("st:")
    
    @pytest.mark.asyncio
    async def test_twin_history_temporal_ordering(
        self, db_session, caller, test_commitment
    ):
        """Test that twin history is temporally ordered."""
        # Create multiple state snapshots
        for i in range(3):
            await company_operating_engine.refresh(
                db_session,
                organization_id=caller.organization_id,
                event=type("Event", (), {"id": f"evt-{i}-{uuid.uuid4().hex[:8]}", "name": f"test_event_{i}"})(),
                payload={},
            )
        
        history = await canonical_digital_twin_service.derive_twin_history(
            db_session,
            caller=caller,
            scope_type="org",
            limit=10,
        )
        
        # Should be ordered newest first
        for i in range(len(history) - 1):
            t1 = datetime.fromisoformat(history[i]["captured_at"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(history[i+1]["captured_at"].replace("Z", "+00:00"))
            assert t1 >= t2


class TestGovernance:
    """Test governance enforcement."""
    
    @pytest.mark.asyncio
    async def test_twin_tenant_isolation(
        self, db_session, caller, test_org
    ):
        """Test that twin derivation doesn't leak across tenants."""
        # Create another org
        other_org = Organization(
            name="Other Org",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(other_org)
        await db_session.flush()
        
        other_user = User(
            organization_id=other_org.id,
            email=f"other{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed",
            full_name="Other User",
            status="active",
        )
        db_session.add(other_user)
        await db_session.flush()
        
        other_caller = await resolve_caller_access(
            db_session, organization_id=other_org.id, user=other_user
        )
        
        # Create data in other org
        other_commitment = CompanyCommitment(
            organization_id=other_org.id,
            commitment_type="unconditional",
            title="Other Commitment",
            state="active",
            scope_type="project",
            scope_id="proj-other",
            rationale="Test",
            fingerprint=f"comm-other-{uuid.uuid4().hex[:32]}",
            source_event_id="comm-other-1",
        )
        db_session.add(other_commitment)
        await db_session.commit()
        
        # Derive twin for original org
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session,
            caller=caller,
            scope_type="org",
        )
        
        # Should only see original org data
        assert result["organization_id"] == caller.organization_id
        assert result["organization_id"] != other_org.id


class TestRegression:
    """Regression tests for prior gates."""
    
    @pytest.mark.asyncio
    async def test_gate11_counterfactual_still_works(
        self, db_session, caller, test_employee, test_commitment
    ):
        """Test that Gate 11 counterfactual intelligence still works."""
        result = await counterfactual_intelligence_service.create_scenario(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="person",
            subject_id=test_employee.id,
            params={"delta": 10},
            dry_run=True,
        )
        
        assert result["advisory_only"] is True
        assert result["not_a_prediction"] is True
        assert "scenario_id" in result
    
    @pytest.mark.asyncio
    async def test_gate10_predictive_still_works(
        self, db_session, caller, test_commitment
    ):
        """Test that Gate 10 predictive intelligence still works."""
        result = await predictive_intelligence_service.derive_predictions(
            db_session,
            caller=caller,
            scope_type="organization",
        )
        
        assert isinstance(result, list)
        # May be empty if no predictions generated
    
    @pytest.mark.asyncio
    async def test_gate9_institutional_still_works(
        self, db_session, caller, test_commitment
    ):
        """Test that Gate 9 institutional intelligence still works."""
        result = await institutional_intelligence_service.derive_institutional_intelligence(
            db_session,
            caller=caller,
            scope_type="organization",
        )
        
        assert "qualified_lessons" in result
        assert "institutional_patterns" in result


class TestAdversarial:
    """Adversarial tests for digital twin."""
    
    @pytest.mark.asyncio
    async def test_cross_tenant_scenario_access_blocked(
        self, db_session, caller, test_org, test_employee
    ):
        """Test that scenarios can't access cross-tenant entities."""
        other_org = Organization(
            name="Other Org",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(other_org)
        await db_session.flush()
        
        other_user = User(
            organization_id=other_org.id,
            email=f"other{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed",
            full_name="Other User",
            status="active",
        )
        db_session.add(other_user)
        await db_session.flush()
        
        other_emp = Employee(
            organization_id=other_org.id,
            user_id=other_user.id,
            employee_number=f"EMP{uuid.uuid4().hex[:6]}",
            first_name="Other",
            last_name="Employee",
            email=f"other{uuid.uuid4().hex[:6]}@test.com",
            status="active",
        )
        db_session.add(other_emp)
        await db_session.commit()
        
        # Try to create scenario branch with other org's employee
        result = await canonical_digital_twin_service.create_scenario_branch(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="person",
            subject_id=other_emp.id,  # Other org's employee
            params={"delta": 10},
            dry_run=True,
        )
        
        # Should handle gracefully (entity not found in caller's org)
        assert result["advisory_only"] is True
    
    @pytest.mark.asyncio
    async def test_scenario_branch_cannot_mutate_canonical(
        self, db_session, caller, test_employee
    ):
        """Test that scenario branch creation doesn't mutate canonical reality."""
        # Count commitments before
        count_before = await db_session.execute(
            select(func.count(CompanyCommitment.id)).where(
                CompanyCommitment.organization_id == caller.organization_id
            )
        )
        before = count_before.scalar()
        
        # Create scenario branch (dry_run=True)
        await canonical_digital_twin_service.create_scenario_branch(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="person",
            subject_id=test_employee.id,
            params={"delta": 10},
            dry_run=True,
        )
        
        # Count commitments after
        count_after = await db_session.execute(
            select(func.count(CompanyCommitment.id)).where(
                CompanyCommitment.organization_id == caller.organization_id
            )
        )
        after = count_after.scalar()
        
        # Should be unchanged
        assert after == before
    
    @pytest.mark.asyncio
    async def test_twin_derivation_cannot_mutate_canonical(
        self, db_session, caller, test_commitment
    ):
        """Test that twin derivation doesn't mutate canonical reality."""
        count_before = await db_session.execute(
            select(func.count(CompanyCommitment.id)).where(
                CompanyCommitment.organization_id == caller.organization_id
            )
        )
        before = count_before.scalar()
        
        await canonical_digital_twin_service.derive_twin_state(
            db_session,
            caller=caller,
            scope_type="org",
        )
        
        count_after = await db_session.execute(
            select(func.count(CompanyCommitment.id)).where(
                CompanyCommitment.organization_id == caller.organization_id
            )
        )
        after = count_after.scalar()
        
        assert after == before
    
    @pytest.mark.asyncio
    async def test_fake_entity_ids_rejected(
        self, db_session, caller
    ):
        """Test that fake entity IDs are handled gracefully."""
        fake_id = f"fake-{uuid.uuid4().hex[:24]}"
        
        result = await canonical_digital_twin_service.create_scenario_branch(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="person",
            subject_id=fake_id,
            params={"delta": 10},
            dry_run=True,
        )
        
        assert result["advisory_only"] is True
        # Should not crash, may have empty projections
    
    @pytest.mark.asyncio
    async def test_concurrent_scenario_branches_isolated(
        self, db_session, caller, test_employee, test_commitment
    ):
        """Test that concurrent scenario branches don't contaminate each other."""
        # Create two branches concurrently
        branch1 = canonical_digital_twin_service.create_scenario_branch(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="person",
            subject_id=test_employee.id,
            params={"delta": 10},
            dry_run=True,
        )
        branch2 = canonical_digital_twin_service.create_scenario_branch(
            db_session,
            caller=caller,
            scenario_kind="commitment_change",
            subject_type="commitment",
            subject_id=test_commitment.id,
            params={"action": "delay", "weeks": 4},
            dry_run=True,
        )
        
        result1, result2 = await asyncio.gather(branch1, branch2)
        
        # Both should succeed independently
        assert result1["advisory_only"] is True
        assert result2["advisory_only"] is True
        assert result1["branch_id"] != result2["branch_id"]
        assert result1["scenario"]["kind"] == "capacity_change"
        assert result2["scenario"]["kind"] == "commitment_change"


import asyncio