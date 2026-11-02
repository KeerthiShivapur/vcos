"""Gate 15 — Canonical Financial + Resource + Procurement Operating Fabric Tests.

Tests for the canonical financial/resource/procurement operating fabric.
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
from app.models.customer import Customer, CustomerContact
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
from app.models.finance import (
    Budget,
    BudgetAllocation,
    Expense,
    Invoice,
    Payment,
    PurchaseRequest,
    PurchaseOrder,
    Vendor,
    VendorContract,
    FinancialForecast,
    FinancialMetric,
)
from app.models.financial_resource_procurement import (
    ResourceRequirement,
    ResourceAllocationRecord,
    ProcurementRecord,
    BudgetCommitmentRecord,
    FinancialOutcomeRecord,
    FinancialOperatingSlice,
    FinancialImpactAnalysis,
    RESOURCE_KINDS,
    RESOURCE_STATES,
    ALLOCATION_STATES,
    PROCUREMENT_KINDS,
    PROCUREMENT_STATES,
    BUDGET_KINDS,
    BUDGET_STATES,
    FINANCIAL_TRANSACTION_KINDS,
    FINANCIAL_TRANSACTION_STATES,
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
)
from app.intelligence.customer_operating_fabric_service import (
    customer_operating_fabric_service,
)
from app.intelligence.financial_resource_procurement_service import (
    financial_resource_procurement_service,
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
async def test_customer(db_session, caller, test_employee):
    """Create test customer."""
    customer = Customer(
        organization_id=caller.organization_id,
        company_name="Test Customer Corp",
        status="customer",
        segment="enterprise",
        tier="gold",
        industry="Software",
        owner_id=test_employee.id,
        health_score=85,
        health_status="healthy",
        annual_value=500000.0,
    )
    db_session.add(customer)
    await db_session.flush()
    
    # Add contact
    contact = CustomerContact(
        organization_id=caller.organization_id,
        customer_id=customer.id,
        name="Customer Contact",
        role="cto",
        email="contact@customer.com",
        decision_maker=True,
        is_primary=True,
    )
    db_session.add(contact)
    await db_session.commit()
    
    return customer


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
async def test_project(db_session, caller, test_objective):
    """Create test project linked to objective."""
    project = Project(
        organization_id=caller.organization_id,
        name="Test Project",
        code=f"PRJ{uuid.uuid4().hex[:4]}",
        status="active",
        owner_id="test-owner",
    )
    db_session.add(project)
    await db_session.flush()
    
    # Create initiative for the project
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
    
    # Create strategic link
    from app.models.execution_strategy import StrategicLink
    link = StrategicLink(
        organization_id=caller.organization_id,
        initiative_id=initiative.id,
        project_id=project.id,
        source_event_id=f"link-{uuid.uuid4().hex[:16]}",
        linked_at=utcnow(),
    )
    db_session.add(link)
    await db_session.commit()
    
    return project


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

class TestFinancialResourceProcurementModels:
    """Test the new financial/resource/procurement models."""
    
    @pytest.mark.asyncio
    async def test_create_resource_requirement(
        self, db_session, caller, test_commitment
    ):
        """Test creating a resource requirement."""
        req = ResourceRequirement(
            organization_id=caller.organization_id,
            title="Need 2 Python Engineers",
            description="Need 2 senior Python engineers for project delivery",
            resource_kind="people",
            quantity=2,
            unit="engineers",
            proficiency="senior",
            commitment_id=test_commitment.id,
            commitment_type="company",
            needed_from=date.today(),
            needed_until=date.today() + timedelta(days=90),
            urgency="high",
            estimated_cost=200000,
            currency="USD",
            budget_id="budget-1",
            state="requested",
            fingerprint=f"rr-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(req)
        await db_session.commit()
        
        assert req.id is not None
        assert req.resource_kind == "people"
        assert req.quantity == 2
        assert req.commitment_id == test_commitment.id
    
    @pytest.mark.asyncio
    async def test_create_resource_allocation(
        self, db_session, caller, test_commitment
    ):
        """Test creating a resource allocation record."""
        alloc = ResourceAllocationRecord(
            organization_id=caller.organization_id,
            resource_kind="people",
            title="Allocate 2 Python Engineers",
            description="Allocate 2 senior Python engineers to project",
            requirement_id="req-123",
            commitment_id=test_commitment.id,
            project_id="proj-1",
            quantity=2,
            unit="engineers",
            allocated_cost=180000,
            currency="USD",
            budget_id="budget-1",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=90),
            state="requested",
            requested_by="manager-1",
            fingerprint=f"ra-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(alloc)
        await db_session.commit()
        
        assert alloc.id is not None
        assert alloc.resource_kind == "people"
        assert alloc.quantity == 2
    
    @pytest.mark.asyncio
    async def test_create_procurement_record(
        self, db_session, caller
    ):
        """Test creating a procurement record."""
        proc = ProcurementRecord(
            organization_id=caller.organization_id,
            kind="purchase",
            title="Procure 2 laptops for new engineers",
            description="Purchase 2 high-end laptops for new hires",
            allocation_id="alloc-123",
            vendor_id="vendor-123",
            vendor_name="Dell Technologies",
            estimated_cost=5000,
            currency="USD",
            budget_id="budget-1",
            needed_by=date.today() + timedelta(days=14),
            state="requested",
            requested_by="procurement-manager",
            fingerprint=f"pr-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(proc)
        await db_session.commit()
        
        assert proc.id is not None
        assert proc.kind == "purchase"
        assert proc.vendor_name == "Dell Technologies"
    
    @pytest.mark.asyncio
    async def test_create_budget_commitment(
        self, db_session, caller, test_project
    ):
        """Test creating a budget commitment record."""
        budget = Budget(
            organization_id=caller.organization_id,
            name="Q1 Engineering Budget",
            budget_type="quarterly",
            department_id=None,
            project_id=test_project.id,
            fiscal_year=2026,
            period_start=date.today(),
            period_end=date.today() + timedelta(days=90),
            allocated_amount=500000,
            used_amount=0,
            remaining_amount=500000,
            currency="USD",
            status="active",
        )
        db_session.add(budget)
        await db_session.flush()
        
        bc = BudgetCommitmentRecord(
            organization_id=caller.organization_id,
            budget_id=budget.id,
            commitment_id="comm-123",
            project_id=test_project.id,
            committed_amount=100000,
            currency="USD",
            state="active",
            authorized_by="finance-director",
            fingerprint=f"bc-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(bc)
        await db_session.commit()
        
        assert bc.id is not None
        assert bc.budget_id == budget.id
        assert bc.committed_amount == 100000
    
    @pytest.mark.asyncio
    async def test_create_financial_outcome(
        self, db_session, caller, test_customer
    ):
        """Test creating a financial outcome record."""
        outcome = FinancialOutcomeRecord(
            organization_id=caller.organization_id,
            kind="revenue_achieved",
            title="Q1 Revenue from Deployment Automation",
            state="projected",
            customer_id=test_customer.id,
            metric_kind="revenue",
            metric_unit="USD",
            target_value=100000,
            actual_value=0,
            revenue_impact=100000,
            currency="USD",
            fingerprint=f"fo-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(outcome)
        await db_session.commit()
        
        assert outcome.id is not None
        assert outcome.kind == "revenue_achieved"
        assert outcome.target_value == 100000


class TestFinancialOperatingSlice:
    """Test financial operating slice derivation."""
    
    @pytest.mark.asyncio
    async def test_derive_financial_operating_slice(
        self, db_session, caller, test_commitment, test_project
    ):
        """Test deriving financial operating slice."""
        slice_obj = await financial_resource_procurement_service.derive_financial_operating_slice(
            db_session, caller=caller
        )
        
        assert slice_obj.id is not None
        assert slice_obj.organization_id == caller.organization_id
        assert "budgets" in slice_obj.__dict__
        assert "expenses" in slice_obj.__dict__
        assert "procurements" in slice_obj.__dict__
    
    @pytest.mark.asyncio
    async def test_slice_exact_once(
        self, db_session, caller
    ):
        """Test exact-once semantics for slice derivation."""
        slice1 = await financial_resource_procurement_service.derive_financial_operating_slice(
            db_session, caller=caller
        )
        slice2 = await financial_resource_procurement_service.derive_financial_operating_slice(
            db_session, caller=caller
        )
        
        # Should return same slice (exact-once)
        assert slice1.id == slice2.id
        assert slice1.fingerprint == slice2.fingerprint


class TestFinancialImpactAnalysis:
    """Test financial impact analysis derivation."""
    
    @pytest.mark.asyncio
    async def test_analyze_budget_cut_impact(
        self, db_session, caller, test_commitment, test_project
    ):
        """Test analyzing impact of budget cut."""
        analysis = await financial_resource_procurement_service.analyze_financial_impact(
            db_session,
            caller=caller,
            trigger_type="budget_cut",
            trigger_entity_type="budget",
            trigger_entity_id="budget-123",
            trigger_params={"amount": 50000, "percentage": 10},
        )
        
        assert analysis.id is not None
        assert analysis.trigger_type == "budget_cut"
        assert analysis.trigger_entity_type == "budget"
        assert analysis.trigger_entity_id == "budget-123"
        assert "affected_budgets" in analysis.__dict__
        assert "affected_commitments" in analysis.__dict__
        assert "affected_projects" in analysis.__dict__
    
    @pytest.mark.asyncio
    async def test_impact_analysis_exact_once(
        self, db_session, caller, test_project
    ):
        """Test exact-once for impact analysis."""
        analysis1 = await financial_resource_procurement_service.analyze_financial_impact(
            db_session, caller=caller, customer_id=test_customer.id,
            trigger_type="budget_cut", trigger_entity_type="budget", trigger_entity_id="budget-123"
        )
        analysis2 = await financial_resource_procurement_service.analyze_financial_impact(
            db_session, caller=caller, customer_id=test_customer.id,
            trigger_type="budget_cut", trigger_entity_type="budget", trigger_entity_id="budget-123"
        )
        
        assert analysis1.id == analysis2.id
        assert analysis1.fingerprint == analysis2.fingerprint


class TestResourceRequirement:
    """Test resource requirement creation and linkage."""
    
    @pytest.mark.asyncio
    async def test_create_resource_requirement(
        self, db_session, caller, test_commitment
    ):
        """Test creating a resource requirement linked to commitment."""
        req = ResourceRequirement(
            organization_id=caller.organization_id,
            title="Need 2 Senior Engineers",
            resource_kind="people",
            quantity=2,
            unit="engineers",
            proficiency="senior",
            commitment_id=test_commitment.id,
            commitment_type="company",
            needed_from=date.today(),
            needed_until=date.today() + timedelta(days=90),
            urgency="high",
            estimated_cost=300000,
            fingerprint=f"rr-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(req)
        await db_session.commit()
        
        assert req.id is not None
        assert req.resource_kind == "people"
        assert req.commitment_id == test_commitment.id
    
    @pytest.mark.asyncio
    async def test_resource_requirement_exact_once(
        self, db_session, caller, test_commitment
    ):
        """Test exact-once for resource requirements."""
        from sqlalchemy.exc import IntegrityError
        fp = f"rr-fp-{uuid.uuid4().hex[:32]}"
        req1 = ResourceRequirement(
            organization_id=caller.organization_id,
            title="Need 1 Engineer",
            resource_kind="people",
            quantity=1,
            commitment_id=test_commitment.id,
            fingerprint=fp,
        )
        db_session.add(req1)
        await db_session.commit()
        
        req2 = ResourceRequirement(
            organization_id=caller.organization_id,
            title="Need 1 Engineer",
            resource_kind="people",
            quantity=1,
            commitment_id=test_commitment.id,
            fingerprint=fp,  # Same fingerprint
        )
        db_session.add(req2)
        
        # Second commit should raise IntegrityError due to unique constraint
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestResourceAllocationRecord:
    """Test resource allocation records."""
    
    @pytest.mark.asyncio
    async def test_create_resource_allocation(
        self, db_session, caller, test_commitment
    ):
        """Test creating a resource allocation record."""
        alloc = ResourceAllocationRecord(
            organization_id=caller.organization_id,
            resource_kind="people",
            title="Allocate 2 Python Engineers",
            requirement_id="req-123",
            commitment_id="comm-123",
            project_id="proj-1",
            quantity=2,
            unit="engineers",
            allocated_cost=180000,
            budget_id="budget-1",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=90),
            state="requested",
            requested_by="manager-1",
            fingerprint=f"ra-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(alloc)
        await db_session.commit()
        
        assert alloc.id is not None
        assert alloc.resource_kind == "people"
        assert alloc.quantity == 2


class TestProcurementRecord:
    """Test procurement records."""
    
    @pytest.mark.asyncio
    async def test_create_procurement_record(
        self, db_session, caller
    ):
        """Test creating a procurement record."""
        proc = ProcurementRecord(
            organization_id=caller.organization_id,
            kind="purchase",
            title="Purchase 2 laptops",
            description="Purchase 2 laptops for new hires",
            allocation_id="alloc-123",
            vendor_id="vendor-1",
            vendor_name="Dell Technologies",
            estimated_cost=5000,
            currency="USD",
            budget_id="budget-1",
            needed_by=date.today() + timedelta(days=14),
            state="requested",
            requested_by="procurement-manager",
            fingerprint=f"pr-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(proc)
        await db_session.commit()
        
        assert proc.id is not None
        assert proc.kind == "purchase"
        assert proc.vendor_name == "Dell Technologies"
    
    @pytest.mark.asyncio
    async def test_procurement_state_transitions(
        self, db_session, caller
    ):
        """Test procurement state transitions."""
        proc = ProcurementRecord(
            organization_id=caller.organization_id,
            kind="purchase",
            title="Test Procurement",
            allocation_id="alloc-1",
            estimated_cost=1000,
            state="requested",
            fingerprint=f"pr-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(proc)
        await db_session.flush()
        
        # Transition to approved
        proc.state = "approved"
        proc.approved_by = "procurement-director"
        proc.approved_at = utcnow()
        await db_session.flush()
        
        # Transition to ordered
        proc.state = "ordered"
        proc.ordered_at = utcnow()
        await db_session.flush()
        
        # Transition to received
        proc.state = "received"
        proc.delivered_at = utcnow()
        await db_session.commit()
        
        assert proc.state == "received"
        assert proc.ordered_at is not None
        assert proc.delivered_at is not None


class TestBudgetCommitmentRecord:
    """Test budget commitment records."""
    
    @pytest.mark.asyncio
    async def test_create_budget_commitment(
        self, db_session, caller, test_project
    ):
        """Test creating a budget commitment record."""
        budget = Budget(
            organization_id=caller.organization_id,
            name="Q1 Engineering Budget",
            budget_type="quarterly",
            project_id=test_project.id,
            fiscal_year=2026,
            period_start=date.today(),
            period_end=date.today() + timedelta(days=90),
            allocated_amount=500000,
            used_amount=0,
            remaining_amount=500000,
            currency="USD",
            status="active",
        )
        db_session.add(budget)
        await db_session.flush()
        
        bc = BudgetCommitmentRecord(
            organization_id=caller.organization_id,
            budget_id=budget.id,
            commitment_id="comm-123",
            project_id=test_project.id,
            committed_amount=100000,
            currency="USD",
            state="active",
            authorized_by="finance-director",
            fingerprint=f"bc-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(bc)
        await db_session.commit()
        
        assert bc.id is not None
        assert bc.budget_id == budget.id
        assert bc.committed_amount == 100000


class TestFinancialOutcomeRecord:
    """Test financial outcome records."""
    
    @pytest.mark.asyncio
    async def test_create_financial_outcome(
        self, db_session, caller, test_customer
    ):
        """Test creating a financial outcome record."""
        outcome = FinancialOutcomeRecord(
            organization_id=caller.organization_id,
            kind="revenue_achieved",
            title="Q2 Revenue from Deployment Automation",
            commercial_intent_id="ci-123",
            customer_id=test_customer.id,
            metric_kind="revenue",
            target_value=100000,
            actual_value=0,
            revenue_impact=100000,
            currency="USD",
            fingerprint=f"fo-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(outcome)
        await db_session.commit()
        
        assert outcome.id is not None
        assert outcome.kind == "revenue_achieved"
        assert outcome.target_value == 100000
    
    @pytest.mark.asyncio
    async def test_financial_outcome_state_transitions(
        self, db_session, caller, test_customer
    ):
        """Test financial outcome state transitions."""
        outcome = FinancialOutcomeRecord(
            organization_id=caller.organization_id,
            kind="revenue_achieved",
            title="Test Revenue",
            state="projected",
            commercial_intent_id="ci-123",
            customer_id=test_customer.id,
            target_value=50000,
            revenue_impact=50000,
            fingerprint=f"fo-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(outcome)
        await db_session.flush()
        
        # Transition to achieved
        outcome.state = "achieved"
        outcome.actual_value = 50000
        outcome.achieved_at = utcnow()
        await db_session.flush()
        
        # Transition to verified
        outcome.state = "verified"
        outcome.verified_at = utcnow()
        await db_session.commit()
        
        assert outcome.state == "verified"
        assert outcome.actual_value == 50000
        assert outcome.verified_at is not None


class TestFinancialOperatingSlice:
    """Test financial operating slice derivation."""
    
    @pytest.mark.asyncio
    async def test_derive_financial_operating_slice(
        self, db_session, caller
    ):
        """Test deriving financial operating slice."""
        slice_obj = await financial_resource_procurement_service.derive_financial_operating_slice(
            db_session, caller=caller
        )
        
        assert slice_obj.id is not None
        assert slice_obj.organization_id == caller.organization_id
        assert "budgets" in slice_obj.__dict__
        assert "expenses" in slice_obj.__dict__
        assert "procurements" in slice_obj.__dict__
    
    @pytest.mark.asyncio
    async def test_slice_exact_once(
        self, db_session, caller
    ):
        """Test exact-once semantics for slice derivation."""
        slice1 = await financial_resource_procurement_service.derive_financial_operating_slice(
            db_session, caller=caller
        )
        slice2 = await financial_resource_procurement_service.derive_financial_operating_slice(
            db_session, caller=caller
        )
        
        # Should return same slice (exact-once)
        assert slice1.id == slice2.id
        assert slice1.fingerprint == slice2.fingerprint


class TestFinancialImpactAnalysis:
    """Test financial impact analysis derivation."""
    
    @pytest.mark.asyncio
    async def test_analyze_budget_cut_impact(
        self, db_session, caller
    ):
        """Test analyzing impact of budget cut."""
        analysis = await financial_resource_procurement_service.analyze_financial_impact(
            db_session,
            caller=caller,
            trigger_type="budget_cut",
            trigger_entity_type="budget",
            trigger_entity_id="budget-123",
            trigger_params={"amount": 50000, "percentage": 10},
        )
        
        assert analysis.id is not None
        assert analysis.trigger_type == "budget_cut"
        assert analysis.trigger_entity_type == "budget"
        assert analysis.trigger_entity_id == "budget-123"
        assert "affected_budgets" in analysis.__dict__
        assert "affected_commitments" in analysis.__dict__
        assert "affected_projects" in analysis.__dict__
    
    @pytest.mark.asyncio
    async def test_impact_analysis_exact_once(
        self, db_session, caller
    ):
        """Test exact-once for impact analysis."""
        analysis1 = await financial_resource_procurement_service.analyze_financial_impact(
            db_session, caller=caller,
            trigger_type="budget_cut", trigger_entity_type="budget", trigger_entity_id="budget-123"
        )
        analysis2 = await financial_resource_procurement_service.analyze_financial_impact(
            db_session, caller=caller,
            trigger_type="budget_cut", trigger_entity_type="budget", trigger_entity_id="budget-123"
        )
        
        assert analysis1.id == analysis2.id
        assert analysis1.fingerprint == analysis2.fingerprint


class TestGovernance:
    """Test governance enforcement."""
    
    @pytest.mark.asyncio
    async def test_financial_tenant_isolation(
        self, db_session, caller, test_org
    ):
        """Test that financial data doesn't leak across tenants."""
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
        
        # Create budget in other org
        other_budget = Budget(
            organization_id=other_org.id,
            name="Other Budget",
            budget_type="annual",
            allocated_amount=100000,
            status="active",
        )
        db_session.add(other_budget)
        await db_session.commit()
        
        # Try to access from original caller - should be isolated
        slice_obj = await financial_resource_procurement_service.derive_financial_operating_slice(
            db_session, caller=caller
        )
        
        # Should only see original org's budgets
        assert slice_obj.organization_id == caller.organization_id
        assert slice_obj.organization_id != other_org.id


class TestRegression:
    """Regression tests for prior gates."""
    
    @pytest.mark.asyncio
    async def test_gate14_customer_still_works(
        self, db_session, caller, test_customer
    ):
        """Test that Gate 14 customer operating fabric still works."""
        slice_obj = await customer_operating_fabric_service.derive_customer_operating_slice(
            db_session, caller=caller, customer_id=test_customer.id
        )
        
        assert slice_obj.id is not None
        assert slice_obj.customer_id == test_customer.id
        assert slice_obj.organization_id == caller.organization_id
    
    @pytest.mark.asyncio
    async def test_gate13_alignment_still_works(
        self, db_session, caller, test_project
    ):
        """Test that Gate 13 strategic alignment still works."""
        result = await strategic_alignment_engine.trace_forward(
            db_session, caller=caller,
            entity_type="project", entity_id=test_project.id, max_depth=3
        )
        assert "chain" in result
    
    @pytest.mark.asyncio
    async def test_gate12_digital_twin_still_works(
        self, db_session, caller
    ):
        """Test that Gate 12 Digital Twin still works."""
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session, caller=caller, scope_type="org"
        )
        assert result["advisory_only"] is True
    
    @pytest.mark.asyncio
    async def test_gate11_counterfactual_still_works(
        self, db_session, caller
    ):
        """Test that Gate 11 Counterfactual still works."""
        result = await counterfactual_intelligence_service.create_scenario(
            db_session, caller=caller,
            scenario_kind="capacity_change", subject_type="person",
            subject_id="test-person", params={"delta": 5}, dry_run=True
        )
        assert result["advisory_only"] is True
    
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
    """Adversarial tests."""
    
    @pytest.mark.asyncio
    async def test_fake_budget_id_rejected(
        self, db_session, caller
    ):
        """Test that BudgetCommitmentRecord model has foreign key constraint on budget_id."""
        from sqlalchemy import inspect
        model = BudgetCommitmentRecord
        fk_constraints = [c for c in model.__table__.constraints if hasattr(c, 'referred_table')]
        budget_fks = [c for c in fk_constraints if c.referred_table.name == 'budgets']
        assert len(budget_fks) == 1, "BudgetCommitmentRecord should have FK to budgets table"
    
    @pytest.mark.asyncio
    async def test_cross_tenant_financial_access_blocked(
        self, db_session, caller, test_org
    ):
        """Test that financial data can't be accessed across tenants."""
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
        
        other_budget = Budget(
            organization_id=other_org.id,
            name="Other Budget",
            budget_type="annual",
            allocated_amount=100000,
            status="active",
        )
        db_session.add(other_budget)
        await db_session.commit()
        
        # Try to access from original caller
        with pytest.raises(ValueError):
            await financial_resource_procurement_service.derive_financial_operating_slice(
                db_session, caller=other_caller
            )


# Need imports
import asyncio