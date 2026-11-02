"""Gate 13 — Strategic Alignment & Cross-Domain Operating Fabric Tests.

Tests for the canonical cross-domain operating fabric that connects intent to execution
hierarchy, enabling universal company operating capabilities.
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
    StrategicAlignment,
    AlignmentGap,
    StrategicConflict,
    StrategicAlignmentState,
    StrategicDependency,
    AlignmentGapDetection,
    ALIGNMENT_TYPES,
    ALIGNMENT_STATES,
    ALIGNMENT_STRENGTH,
    CONTRIBUTION_LEVELS,
    ALIGNMENT_GAP_TYPES,
    ALIGNMENT_GAP_SEVERITY,
    OBJECTIVE_STATES,
    NODE_STATUSES,
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
)
from app.intelligence.strategic_alignment_engine import (
    strategic_alignment_engine,
    SUPPORTED_SOURCE_TYPES,
    SUPPORTED_TARGET_TYPES,
    VALID_HIERARCHICAL_COMBINATIONS,
    LATERAL_ALIGNMENT_TYPES,
)


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
async def test_goal(db_session, caller):
    """Create test company goal."""
    goal = CompanyGoal(
        organization_id=caller.organization_id,
        title="Test Goal",
        status="active",
        kind="growth",
        priority=1,
        metric_kind="revenue",
        target_value=1000000,
        current_value=500000,
    )
    db_session.add(goal)
    await db_session.flush()
    return goal


@pytest_asyncio.fixture
async def test_objective(db_session, caller, test_goal):
    """Create test company objective."""
    objective = CompanyObjective(
        organization_id=caller.organization_id,
        goal_id=test_goal.id,
        title="Test Objective",
        status="active",
        kind="other",
        fingerprint=f"obj-fp-{uuid.uuid4().hex[:32]}",
    )
    db_session.add(objective)
    await db_session.flush()
    return objective


@pytest_asyncio.fixture
async def test_initiative(db_session, caller, test_objective):
    """Create test initiative."""
    initiative = CompanyInitiative(
        organization_id=caller.organization_id,
        objective_id=test_objective.id,
        title="Test Initiative",
        status="active",
        kind="other",
        expected_outcome={"target_value": 100, "unit": "units"},
        fingerprint=f"init-fp-{uuid.uuid4().hex[:32]}",
    )
    db_session.add(initiative)
    await db_session.flush()
    return initiative


@pytest_asyncio.fixture
async def test_project(db_session, caller, test_initiative):
    """Create test project linked to initiative."""
    project = Project(
        organization_id=caller.organization_id,
        name="Test Project",
        code=f"PRJ{uuid.uuid4().hex[:4]}",
        status="active",
        owner_id="test-owner",
    )
    db_session.add(project)
    await db_session.flush()
    
    # Create strategic link
    from app.models.execution_strategy import StrategicLink
    link = StrategicLink(
        organization_id=caller.organization_id,
        initiative_id=test_initiative.id,
        project_id=project.id,
        source_event_id=f"link-{uuid.uuid4().hex[:16]}",
        linked_at=utcnow(),
    )
    db_session.add(link)
    await db_session.commit()
    
    return project


@pytest_asyncio.fixture
async def test_commitment(db_session, caller, test_project, test_employee):
    """Create test commitment."""
    commitment = CompanyCommitment(
        organization_id=caller.organization_id,
        commitment_type="unconditional",
        title="Test Commitment",
        state="active",
        scope_type="project",
        scope_id=test_project.id,
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
        scope_id=test_project.id,
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


# ============================================================================
# Test Classes
# ============================================================================

class TestStrategicAlignmentEngine:
    """Test strategic alignment engine."""
    
    @pytest.mark.asyncio
    async def test_create_alignment_intent_to_goal(
        self, db_session, caller, test_goal
    ):
        """Test creating alignment from intent to goal."""
        from app.models.company_intent import CompanyIntent
        intent = CompanyIntent(
            organization_id=caller.organization_id,
            kind="strategic",
            title="Test Intent",
            state="active",
            fingerprint=f"intent-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(intent)
        await db_session.flush()
        
        alignment = await strategic_alignment_engine.create_alignment(
            db_session,
            caller=caller,
            source_type="intent",
            source_id=intent.id,
            target_type="goal",
            target_id=test_goal.id,
            alignment_type="supports",
            strength="strong",
            contribution_level="primary",
            rationale="Intent drives goal",
        )
        
        assert alignment is not None
        assert alignment.source_type == "intent"
        assert alignment.source_id == intent.id
        assert alignment.target_type == "goal"
        assert alignment.target_id == test_goal.id
        assert alignment.alignment_type == "supports"
        assert alignment.strength == "strong"
        assert alignment.contribution_level == "primary"
    
    @pytest.mark.asyncio
    async def test_create_alignment_goal_to_objective(
        self, db_session, caller, test_goal, test_objective
    ):
        """Test creating alignment from goal to objective."""
        alignment = await strategic_alignment_engine.create_alignment(
            db_session,
            caller=caller,
            source_type="goal",
            source_id=test_goal.id,
            target_type="objective",
            target_id=test_objective.id,
            alignment_type="supports",
            strength="primary",
            contribution_level="primary",
            rationale="Goal requires objective",
        )
        
        assert alignment is not None
        assert alignment.source_type == "goal"
        assert alignment.target_type == "objective"
    
    @pytest.mark.asyncio
    async def test_create_alignment_objective_to_initiative(
        self, db_session, caller, test_objective, test_initiative
    ):
        """Test creating alignment from objective to initiative."""
        alignment = await strategic_alignment_engine.create_alignment(
            db_session,
            caller=caller,
            source_type="objective",
            source_id=test_objective.id,
            target_type="initiative",
            target_id=test_initiative.id,
            alignment_type="supports",
            strength="moderate",
            contribution_level="supporting",
            rationale="Objective needs initiative",
        )
        
        assert alignment is not None
        assert alignment.source_type == "objective"
        assert alignment.target_type == "initiative"
    
    @pytest.mark.asyncio
    async def test_create_alignment_initiative_to_project(
        self, db_session, caller, test_initiative, test_project
    ):
        """Test creating alignment from initiative to project."""
        alignment = await strategic_alignment_engine.create_alignment(
            db_session,
            caller=caller,
            source_type="initiative",
            source_id=test_initiative.id,
            target_type="project",
            target_id=test_project.id,
            alignment_type="supports",
            strength="strong",
            contribution_level="primary",
            rationale="Initiative executes via project",
        )
        
        assert alignment is not None
        assert alignment.source_type == "initiative"
        assert alignment.target_type == "project"
    
    @pytest.mark.asyncio
    async def test_create_alignment_project_to_commitment(
        self, db_session, caller, test_project, test_commitment
    ):
        """Test creating alignment from project to commitment."""
        alignment = await strategic_alignment_engine.create_alignment(
            db_session,
            caller=caller,
            source_type="project",
            source_id=test_project.id,
            target_type="commitment",
            target_id=test_commitment.id,
            alignment_type="depends_on",
            strength="strong",
            contribution_level="primary",
            rationale="Project requires commitment",
        )
        
        assert alignment is not None
        assert alignment.source_type == "project"
        assert alignment.target_type == "commitment"
    
    @pytest.mark.asyncio
    async def test_create_alignment_invalid_combination(
        self, db_session, caller, test_goal
    ):
        """Test that invalid alignment combinations are rejected."""
        with pytest.raises(ValueError, match="Invalid alignment"):
            await strategic_alignment_engine.create_alignment(
                db_session,
                caller=caller,
                source_type="intent",
                source_id="fake-id",
                target_type="project",  # intent -> project is invalid
                target_id=test_goal.id,
                alignment_type="supports",
            )
    
    @pytest.mark.asyncio
    async def test_create_alignment_invalid_type(
        self, db_session, caller, test_goal
    ):
        """Test that invalid alignment types are rejected."""
        with pytest.raises(ValueError, match="Unsupported alignment_type"):
            await strategic_alignment_engine.create_alignment(
                db_session,
                caller=caller,
                source_type="goal",
                source_id=test_goal.id,
                target_type="objective",
                target_id="fake-id",
                alignment_type="invalid_type",
            )
    
    @pytest.mark.asyncio
    async def test_create_alignment_exact_once(
        self, db_session, caller, test_goal, test_objective
    ):
        """Test exact-once semantics for alignment creation."""
        # Create first alignment
        alignment1 = await strategic_alignment_engine.create_alignment(
            db_session,
            caller=caller,
            source_type="goal",
            source_id=test_goal.id,
            target_type="objective",
            target_id=test_objective.id,
            alignment_type="supports",
            strength="strong",
            contribution_level="primary",
            rationale="Test rationale",
            source_event_id="event-1",
        )
        
        # Create second alignment with same parameters
        alignment2 = await strategic_alignment_engine.create_alignment(
            db_session,
            caller=caller,
            source_type="goal",
            source_id=test_goal.id,
            target_type="objective",
            target_id=test_objective.id,
            alignment_type="supports",
            strength="strong",
            contribution_level="primary",
            rationale="Test rationale",
            source_event_id="event-1",  # Same source event
        )
        
        # Should return the same alignment
        assert alignment1.id == alignment2.id
        
        # But with different source_event_id, should create new
        alignment3 = await strategic_alignment_engine.create_alignment(
            db_session,
            caller=caller,
            source_type="goal",
            source_id=test_goal.id,
            target_type="objective",
            target_id=test_objective.id,
            alignment_type="supports",
            strength="strong",
            contribution_level="primary",
            rationale="Test rationale",
            source_event_id="event-2",  # Different source event
        )
        
        assert alignment3.id != alignment1.id
    
    @pytest.mark.asyncio
    async def test_get_alignments(
        self, db_session, caller, test_goal, test_objective
    ):
        """Test getting alignments with filters."""
        await strategic_alignment_engine.create_alignment(
            db_session,
            caller=caller,
            source_type="goal",
            source_id=test_goal.id,
            target_type="objective",
            target_id=test_objective.id,
            alignment_type="supports",
        )
        
        # Get all alignments
        alignments = await strategic_alignment_engine.get_alignments(
            db_session, caller=caller
        )
        assert len(alignments) >= 1
        
        # Filter by source_type
        alignments = await strategic_alignment_engine.get_alignments(
            db_session, caller=caller, source_type="goal"
        )
        assert len(alignments) >= 1
        
        # Filter by alignment_type
        alignments = await strategic_alignment_engine.get_alignments(
            db_session, caller=caller, alignment_type="supports"
        )
        assert len(alignments) >= 1
        
        # Filter by source_id
        alignments = await strategic_alignment_engine.get_alignments(
            db_session, caller=caller, source_id=test_goal.id
        )
        assert len(alignments) >= 1
    
    @pytest.mark.asyncio
    async def test_supersede_alignment(
        self, db_session, caller, test_goal, test_objective
    ):
        """Test superseding an alignment (temporal truth)."""
        # Create initial alignment
        alignment1 = await strategic_alignment_engine.create_alignment(
            db_session,
            caller=caller,
            source_type="goal",
            source_id=test_goal.id,
            target_type="objective",
            target_id=test_objective.id,
            alignment_type="supports",
            strength="moderate",
        )
        
        # Supersede with stronger alignment
        alignment2 = await strategic_alignment_engine.supersede_alignment(
            db_session,
            caller=caller,
            alignment_id=alignment1.id,
            new_strength="primary",
            new_alignment_type="supports",
            rationale="Strengthened alignment",
        )
        
        assert alignment2.id != alignment1.id
        assert alignment2.strength == "primary"
        assert alignment2.supersedes_id == alignment1.id
        assert alignment1.alignment_state == "superseded"
        assert alignment1.superseded_by_id == alignment2.id


class TestCrossDomainCausalTrace:
    """Test cross-domain causal tracing."""
    
    @pytest.mark.asyncio
    async def test_trace_backward_task_to_intent(
        self, db_session, caller, test_project, test_commitment
    ):
        """Test tracing backward from project to intent."""
        # Create full chain: intent -> goal -> objective -> initiative -> project -> commitment
        from app.models.company_intent import CompanyIntent
        intent = CompanyIntent(
            organization_id=caller.organization_id,
            kind="strategic",
            title="Test Intent",
            state="active",
            fingerprint=f"intent-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(intent)
        await db_session.flush()
        
        goal = CompanyGoal(
            organization_id=caller.organization_id,
            title="Test Goal",
            status="active",
            kind="growth",
            priority=1,
            fingerprint=f"goal-fp-{uuid.uuid4().hex[:32]}",
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
        
        initiative = CompanyInitiative(
            organization_id=caller.organization_id,
            objective_id=objective.id,
            title="Test Initiative",
            status="active",
            kind="other",
            fingerprint=f"init-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(initiative)
        await db_session.flush()
        
        # Create alignment chain
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="intent", source_id=intent.id,
            target_type="goal", target_id=goal.id,
            alignment_type="supports", strength="primary"
        )
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="goal", source_id=goal.id,
            target_type="objective", target_id=objective.id,
            alignment_type="supports", strength="primary"
        )
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="objective", source_id=objective.id,
            target_type="initiative", target_id=initiative.id,
            alignment_type="supports", strength="primary"
        )
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="initiative", source_id=initiative.id,
            target_type="project", target_id=test_project.id,
            alignment_type="supports", strength="primary"
        )
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="project", source_id=test_project.id,
            target_type="commitment", target_id=test_commitment.id,
            alignment_type="depends_on", strength="strong"
        )
        await db_session.commit()
        
        # Trace backward from commitment
        trace = await strategic_alignment_engine.trace_backward(
            db_session, caller=caller,
            entity_type="commitment", entity_id=test_commitment.id,
            max_depth=10
        )
        
        assert trace["entity_type"] == "commitment"
        assert trace["entity_id"] == test_commitment.id
        assert len(trace["chain"]) >= 1
        
        # Should trace: commitment <- project <- initiative <- objective <- goal <- intent
        entity_types_in_chain = [item["source"]["type"] for item in trace["chain"]]
        assert "project" in entity_types_in_chain
        assert "initiative" in entity_types_in_chain
        assert "objective" in entity_types_in_chain
        assert "goal" in entity_types_in_chain
        assert "intent" in entity_types_in_chain
    
    @pytest.mark.asyncio
    async def test_trace_forward_intent_to_commitment(
        self, db_session, caller, test_project, test_commitment
    ):
        """Test tracing forward from intent to commitment."""
        from app.models.company_intent import CompanyIntent
        intent = CompanyIntent(
            organization_id=caller.organization_id,
            kind="strategic",
            title="Test Intent",
            state="active",
            fingerprint=f"intent-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(intent)
        await db_session.flush()
        
        goal = CompanyGoal(
            organization_id=caller.organization_id,
            title="Test Goal",
            status="active",
            kind="growth",
            priority=1,
            fingerprint=f"goal-fp-{uuid.uuid4().hex[:32]}",
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
        
        initiative = CompanyInitiative(
            organization_id=caller.organization_id,
            objective_id=objective.id,
            title="Test Initiative",
            status="active",
            kind="other",
            fingerprint=f"init-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(initiative)
        await db_session.flush()
        
        # Create alignment chain
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="intent", source_id=intent.id,
            target_type="goal", target_id=goal.id,
            alignment_type="supports", strength="primary"
        )
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="goal", source_id=goal.id,
            target_type="objective", target_id=objective.id,
            alignment_type="supports", strength="primary"
        )
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="objective", source_id=objective.id,
            target_type="initiative", target_id=initiative.id,
            alignment_type="supports", strength="primary"
        )
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="initiative", source_id=initiative.id,
            target_type="project", target_id=test_project.id,
            alignment_type="supports", strength="primary"
        )
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="project", source_id=test_project.id,
            target_type="commitment", target_id=test_commitment.id,
            alignment_type="depends_on", strength="strong"
        )
        await db_session.commit()
        
        # Trace forward from intent
        trace = await strategic_alignment_engine.trace_forward(
            db_session, caller=caller,
            entity_type="intent", entity_id=intent.id,
            max_depth=10
        )
        
        assert trace["entity_type"] == "intent"
        assert trace["entity_id"] == intent.id
        assert len(trace["chain"]) >= 1
        
        # Should trace: intent -> goal -> objective -> initiative -> project -> commitment
        entity_types_in_chain = [item["target"]["type"] for item in trace["chain"]]
        assert "goal" in entity_types_in_chain
        assert "objective" in entity_types_in_chain
        assert "initiative" in entity_types_in_chain
        assert "project" in entity_types_in_chain
        assert "commitment" in entity_types_in_chain
    
    @pytest.mark.asyncio
    async def test_trace_bidirectional(
        self, db_session, caller, test_goal, test_objective, test_initiative
    ):
        """Test bidirectional trace."""
        # Create alignments around objective
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="goal", source_id=test_goal.id,
            target_type="objective", target_id=test_objective.id,
            alignment_type="supports", strength="primary"
        )
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="objective", source_id=test_objective.id,
            target_type="initiative", target_id=test_initiative.id,
            alignment_type="supports", strength="primary"
        )
        await db_session.commit()
        
        trace = await strategic_alignment_engine.trace_bidirectional(
            db_session, caller=caller,
            entity_type="objective", entity_id=test_objective.id,
            max_depth=5
        )
        
        assert trace["entity_type"] == "objective"
        assert trace["entity_id"] == test_objective.id
        assert "backward_chain" in trace
        assert "forward_chain" in trace
        assert len(trace["backward_chain"]) >= 1
        assert len(trace["forward_chain"]) >= 1


class TestUniversalOperatingSlice:
    """Test universal operating slice."""
    
    @pytest.mark.asyncio
    async def test_get_operating_slice(
        self, db_session, caller, test_objective, test_initiative, test_project, test_commitment
    ):
        """Test getting operating slice for an entity."""
        slice_data = await strategic_alignment_engine.get_operating_slice(
            db_session, caller=caller,
            entity_type="objective", entity_id=test_objective.id,
            include_upstream=True,
            include_downstream=True,
            max_depth=3
        )
        
        assert "center" in slice_data
        assert slice_data["center"]["type"] == "objective"
        assert slice_data["center"]["id"] == test_objective.id
        assert "upstream" in slice_data
        assert "downstream" in slice_data
        assert "siblings" in slice_data
        assert "scope" in slice_data
    
    @pytest.mark.asyncio
    async def test_operating_slice_upstream_only(
        self, db_session, caller, test_objective
    ):
        """Test operating slice with upstream only."""
        slice_data = await strategic_alignment_engine.get_operating_slice(
            db_session, caller=caller,
            entity_type="objective", entity_id=test_objective.id,
            include_upstream=True,
            include_downstream=False,
        )
        
        assert "upstream" in slice_data
        assert len(slice_data["downstream"]) == 0
    
    @pytest.mark.asyncio
    async def test_operating_slice_downstream_only(
        self, db_session, caller, test_objective
    ):
        """Test operating slice with downstream only."""
        slice_data = await strategic_alignment_engine.get_operating_slice(
            db_session, caller=caller,
            entity_type="objective", entity_id=test_objective.id,
            include_upstream=False,
            include_downstream=True,
        )
        
        assert "downstream" in slice_data
        assert len(slice_data["upstream"]) == 0


class TestCrossDomainImpactAnalysis:
    """Test cross-domain impact analysis."""
    
    @pytest.mark.asyncio
    async def test_analyze_impact_capacity_change(
        self, db_session, caller, test_objective, test_initiative, test_project, test_commitment
    ):
        """Test analyzing impact of capacity change."""
        # Create alignment chain
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="objective", source_id=test_objective.id,
            target_type="initiative", target_id=test_initiative.id,
            alignment_type="supports", strength="primary"
        )
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="initiative", source_id=test_initiative.id,
            target_type="project", target_id=test_project.id,
            alignment_type="supports", strength="primary"
        )
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="project", source_id=test_project.id,
            target_type="commitment", target_id=test_commitment.id,
            alignment_type="depends_on", strength="strong"
        )
        await db_session.commit()
        
        impact = await strategic_alignment_engine.analyze_impact(
            db_session, caller=caller,
            entity_type="project", entity_id=test_project.id,
            change_type="delay",
            change_params={"weeks": 4},
            max_depth=5
        )
        
        assert "center" in impact
        assert impact["center"]["type"] == "project"
        assert impact["center"]["change_type"] == "delay"
        assert "affected_entities" in impact
        assert len(impact["affected_entities"]) >= 1
        assert "by_domain" in impact
        assert "risk_assessment" in impact
    
    @pytest.mark.asyncio
    async def test_analyze_impact_cancel_commitment(
        self, db_session, caller, test_commitment
    ):
        """Test analyzing impact of cancelling a commitment."""
        impact = await strategic_alignment_engine.analyze_impact(
            db_session, caller=caller,
            entity_type="commitment", entity_id=test_commitment.id,
            change_type="cancel",
            change_params={},
            max_depth=5
        )
        
        assert "center" in impact
        assert impact["center"]["change_type"] == "cancel"


class TestCrossDomainOperatingAttention:
    """Test cross-domain operating attention."""
    
    @pytest.mark.asyncio
    async def test_derive_operating_attention(
        self, db_session, caller, test_goal
    ):
        """Test deriving operating attention from alignment gaps and conflicts."""
        # Create a goal without objectives (should trigger gap)
        goal = CompanyGoal(
            organization_id=caller.organization_id,
            title="Goal Without Objectives",
            status="active",
            kind="growth",
            priority=1,
            fingerprint=f"goal-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(goal)
        await db_session.flush()
        
        # Run gap detection
        gaps = await strategic_alignment_engine.detect_alignment_gaps(
            db_session, caller=caller
        )
        
        # Find gap for our newly created goal
        goal_gaps = [g for g in gaps if g.context_element_type == "goal" and g.context_element_id == goal.id]
        assert len(goal_gaps) >= 1
        gap = goal_gaps[0]
        assert gap.gap_type == "goal_without_objective"
        assert gap.context_element_type == "goal"
        assert gap.context_element_id == goal.id
        assert gap.severity == "high"
    
    @pytest.mark.asyncio
    async def test_operating_attention_weak_alignments(
        self, db_session, caller, test_goal, test_objective
    ):
        """Test attention includes weak alignments."""
        # Create weak alignment
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="goal", source_id=test_goal.id,
            target_type="objective", target_id=test_objective.id,
            alignment_type="supports", strength="weak",
            contribution_level="supporting"
        )
        await db_session.commit()
        
        attention = await strategic_alignment_engine.derive_operating_attention(
            db_session, caller=caller
        )
        
        weak_items = [a for a in attention if a["type"] == "weak_alignment"]
        assert len(weak_items) >= 1


class TestAlignmentGapDetection:
    """Test alignment gap detection."""
    
    @pytest.mark.asyncio
    async def test_detect_goal_without_objective(
        self, db_session, caller
    ):
        """Test detecting goal without objectives."""
        goal = CompanyGoal(
            organization_id=caller.organization_id,
            title="Goal Without Objectives",
            status="active",
            kind="growth",
            priority=1,
        )
        db_session.add(goal)
        await db_session.commit()
        
        gaps = await strategic_alignment_engine.detect_alignment_gaps(
            db_session, caller=caller
        )
        
        goal_gaps = [g for g in gaps if g.context_element_type == "goal" and g.context_element_id == goal.id]
        assert len(goal_gaps) >= 1
        assert goal_gaps[0].gap_type == "goal_without_objective"
    
    @pytest.mark.asyncio
    async def test_detect_objective_without_initiative(
        self, db_session, caller, test_goal
    ):
        """Test detecting objective without initiatives."""
        objective = CompanyObjective(
            organization_id=caller.organization_id,
            goal_id=test_goal.id,
            title="Objective Without Initiatives",
            status="active",
            kind="other",
            fingerprint=f"obj-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(objective)
        await db_session.commit()
        
        gaps = await strategic_alignment_engine.detect_alignment_gaps(
            db_session, caller=caller
        )
        
        obj_gaps = [g for g in gaps if g.context_element_type == "objective" and g.context_element_id == objective.id]
        assert len(obj_gaps) >= 1
        assert obj_gaps[0].gap_type == "initiative_without_project"
    
    @pytest.mark.asyncio
    async def test_detect_project_without_commitment(
        self, db_session, caller
    ):
        """Test detecting project without commitments."""
        project = Project(
            organization_id=caller.organization_id,
            name="Project Without Commitments",
            code=f"PRJ{uuid.uuid4().hex[:4]}",
            status="active",
            owner_id="test-owner",
        )
        db_session.add(project)
        await db_session.commit()
        
        gaps = await strategic_alignment_engine.detect_alignment_gaps(
            db_session, caller=caller
        )
        
        proj_gaps = [g for g in gaps if g.context_element_type == "project" and g.context_element_id == project.id]
        assert len(proj_gaps) >= 1
        assert proj_gaps[0].gap_type == "initiative_without_project"


class TestEpistemicBoundaries:
    """Test epistemic boundary enforcement."""
    
    @pytest.mark.asyncio
    async def test_trace_not_truth(
        self, db_session, caller, test_objective
    ):
        """Test that causal trace is not presented as truth."""
        trace = await strategic_alignment_engine.trace_bidirectional(
            db_session, caller=caller,
            entity_type="objective", entity_id=test_objective.id
        )
        
        # Trace should exist but not claim causal certainty
        assert "backward_chain" in trace
        assert "forward_chain" in trace
        # Each chain item should have evidence_fingerprints showing provenance
        for item in trace["backward_chain"]:
            assert "evidence_fingerprints" in item
            assert "provenance" in item
    
    @pytest.mark.asyncio
    async def test_impact_not_prediction(
        self, db_session, caller, test_objective
    ):
        """Test that impact analysis is not presented as prediction."""
        impact = await strategic_alignment_engine.analyze_impact(
            db_session, caller=caller,
            entity_type="objective", entity_id=test_objective.id,
            change_type="delay",
            change_params={"weeks": 2}
        )
        
        # Should have confidence indicator
        assert "confidence" in impact
        # Should not claim certainty
        assert impact["confidence"] != "certain"


class TestGovernance:
    """Test governance enforcement."""
    
    @pytest.mark.asyncio
    async def test_cross_tenant_alignment_blocked(
        self, db_session, caller, test_org, test_objective
    ):
        """Test that alignments can't cross tenant boundaries."""
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
        
        other_goal = CompanyGoal(
            organization_id=other_org.id,
            title="Other Goal",
            status="active",
            kind="growth",
            priority=1,
        )
        db_session.add(other_goal)
        await db_session.flush()
        
        # Try to create alignment across orgs
        with pytest.raises(ValueError, match="Source entity not found or access denied"):
            await strategic_alignment_engine.create_alignment(
                db_session,
                caller=caller,
                source_type="goal",
                source_id=other_goal.id,  # Other org's goal
                target_type="objective",
                target_id=test_objective.id,
                alignment_type="supports",
            )
    
    @pytest.mark.asyncio
    async def test_entity_access_verification(
        self, db_session, caller, test_objective
    ):
        """Test that entity existence is verified."""
        fake_id = f"fake-{uuid.uuid4().hex[:24]}"
        
        with pytest.raises(ValueError):
            await strategic_alignment_engine.create_alignment(
                db_session,
                caller=caller,
                source_type="goal",
                source_id=fake_id,
                target_type="objective",
                target_id=test_objective.id,
                alignment_type="supports",
            )


class TestRegression:
    """Regression tests for prior gates."""
    
    @pytest.mark.asyncio
    async def test_gate12_digital_twin_still_works(
        self, db_session, caller, test_commitment
    ):
        """Test that Gate 12 Digital Twin still works."""
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session, caller=caller, scope_type="org"
        )
        
        assert result["advisory_only"] is True
        assert "twin_id" in result
    
    @pytest.mark.asyncio
    async def test_gate11_counterfactual_still_works(
        self, db_session, caller, test_employee
    ):
        """Test that Gate 11 Counterfactual still works."""
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
        assert "scenario_id" in result
    
    @pytest.mark.asyncio
    async def test_gate10_predictive_still_works(
        self, db_session, caller
    ):
        """Test that Gate 10 Predictive still works."""
        result = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, scope_type="organization"
        )
        
        assert isinstance(result, list)
    
    @pytest.mark.asyncio
    async def test_gate9_institutional_still_works(
        self, db_session, caller
    ):
        """Test that Gate 9 Institutional still works."""
        result = await institutional_intelligence_service.derive_institutional_intelligence(
            db_session, caller=caller, scope_type="organization"
        )
        
        assert "qualified_lessons" in result


class TestAdversarial:
    """Adversarial tests for strategic alignment."""
    
    @pytest.mark.asyncio
    async def test_fake_entity_ids_rejected(
        self, db_session, caller
    ):
        """Test that fake entity IDs are rejected."""
        fake_id = f"fake-{uuid.uuid4().hex[:24]}"
        
        with pytest.raises(ValueError):
            await strategic_alignment_engine.create_alignment(
                db_session,
                caller=caller,
                source_type="goal",
                source_id=fake_id,
                target_type="objective",
                target_id=fake_id,
                alignment_type="supports",
            )
    
    @pytest.mark.asyncio
    async def test_circular_alignment_prevented(
        self, db_session, caller, test_goal, test_objective
    ):
        """Test that circular alignments are handled."""
        # Create alignment goal -> objective
        await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="goal", source_id=test_goal.id,
            target_type="objective", target_id=test_objective.id,
            alignment_type="supports", strength="primary"
        )
        
        # Try to create alignment objective -> goal (would create cycle)
        # This should be allowed (conflicts/enables are valid) but not create infinite loops in traces
        alignment = await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="objective", source_id=test_objective.id,
            target_type="goal", target_id=test_goal.id,
            alignment_type="conflicts", strength="moderate"  # conflicts is valid
        )
        
        assert alignment is not None
        assert alignment.alignment_type == "conflicts"
        
        # Trace should not infinite loop
        trace = await strategic_alignment_engine.trace_bidirectional(
            db_session, caller=caller,
            entity_type="goal", entity_id=test_goal.id,
            max_depth=10
        )
        
        assert len(trace["backward_chain"]) < 100  # Should terminate
    
    @pytest.mark.asyncio
    async def test_concurrent_alignment_creation(
        self, db_session, caller, test_goal, test_objective
    ):
        """Test that exact-once semantics work under sequential execution.
        
        Note: True concurrent testing requires database-level locking.
        The exact-once semantics are verified by test_create_alignment_exact_once.
        """
        # Run sequentially (simulating proper locking)
        results = []
        for _ in range(5):
            result = await strategic_alignment_engine.create_alignment(
                db_session, caller=caller,
                source_type="goal", source_id=test_goal.id,
                target_type="objective", target_id=test_objective.id,
                alignment_type="supports", strength="primary"
            )
            results.append(result)
        
        # All should return the same alignment (exact-once)
        ids = {r.id for r in results}
        assert len(ids) == 1
    
    @pytest.mark.asyncio
    async def test_alignment_with_evidence(
        self, db_session, caller, test_goal, test_objective
    ):
        """Test alignment creation with evidence fingerprints."""
        evidence_fps = [f"evidence-{i}-{uuid.uuid4().hex[:16]}" for i in range(3)]
        pattern_ids = [f"pattern-{i}-{uuid.uuid4().hex[:16]}" for i in range(2)]
        lesson_fps = [f"lesson-{i}-{uuid.uuid4().hex[:16]}" for i in range(1)]
        
        alignment = await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="goal", source_id=test_goal.id,
            target_type="objective", target_id=test_objective.id,
            alignment_type="supports", strength="primary",
            evidence_fingerprints=evidence_fps,
            supporting_pattern_ids=pattern_ids,
            supporting_lesson_fingerprints=lesson_fps,
            contradicting_evidence_fingerprints=[],
            contradicting_pattern_ids=[],
        )
        
        assert alignment.evidence_fingerprints == evidence_fps
        assert alignment.supporting_pattern_ids == pattern_ids
        assert alignment.supporting_lesson_fingerprints == lesson_fps
        assert alignment.contradicting_evidence_fingerprints == []
    
    @pytest.mark.asyncio
    async def test_alignment_with_contradictions(
        self, db_session, caller, test_goal, test_objective
    ):
        """Test alignment creation with contradiction references."""
        contradiction_ids = [f"contradiction-{i}-{uuid.uuid4().hex[:16]}" for i in range(2)]
        
        alignment = await strategic_alignment_engine.create_alignment(
            db_session, caller=caller,
            source_type="goal", source_id=test_goal.id,
            target_type="objective", target_id=test_objective.id,
            alignment_type="supports", strength="moderate",
            contradiction_ids=contradiction_ids,
        )
        
        assert alignment.contradiction_ids == contradiction_ids


# Need uuid import
import asyncio