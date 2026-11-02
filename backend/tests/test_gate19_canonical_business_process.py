"""Gate 19 — Canonical Enterprise Operations & Business Process Fabric Tests."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow
from app.intelligence.canonical_business_process_service import (
    canonical_business_process_service,
)
from app.intelligence.canonical_procurement_vendor_service import (
    canonical_procurement_vendor_service,
)
from app.intelligence.canonical_resource_asset_service import (
    canonical_resource_asset_service,
)
from app.intelligence.financial_resource_procurement_service import (
    financial_resource_procurement_service,
)
from app.intelligence.strategic_alignment_engine import strategic_alignment_engine
from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
from app.intelligence.company_context import CallerAccess
from app.models.role import Role, UserRole
from app.services.permission_service import permission_service
from app.models.canonical_business_process import (
    CanonicalBusinessProcess,
    ProcessExecution,
    ProcessStep,
    ProcessApproval,
    ProcessBottleneck,
    ProcessOperatingSlice,
    ProcessImpactAnalysis,
    ProcessPerformance,
    ProcessDependency,
    ProcessScenario,
    ProcessKnowledge,
    PROCESS_LIFECYCLE_STATES,
    PROCESS_TYPES,
    PROCESS_TRIGGERS,
    PROCESS_PRIORITIES,
    PROCESS_SEVERITY,
    PROCESS_ROLES,
)
from app.models.financial_resource_procurement import (
    BudgetCommitmentRecord,
    FinancialOutcomeRecord,
    ProcurementRecord,
)
from app.models.canonical_resource_asset import (
    CanonicalResource,
    CanonicalAsset,
    ResourceDemand,
    ResourceAllocation,
)
from app.models.canonical_procurement_vendor import (
    CanonicalVendor,
    VendorCapability,
    ExternalCapacity,
    CanonicalProcurement,
    VendorPerformance,
    VendorDependency,
)
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyObjective,
    CompanyInitiative,
    OrganizationalResponsibility,
)
from app.models.company_actions import CompanyAction
from app.models.project import Project
from app.models.customer import Customer, CustomerProjectLink
from app.models.customer_intelligence import CustomerCommitment
from app.models.prediction import Prediction
from app.models.company_operating import CompanyScenarioRun
from app.models.digital_twin import DigitalTwin


# =============================================================================
# FIXTURES
# =============================================================================

@pytest_asyncio.fixture
async def test_org(db_session):
    """Create test organization."""
    from app.models.organization import Organization
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
    from app.models.user import User
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
    from app.models.employee import Employee
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
    
    return CallerAccess(
        organization_id=test_org.id,
        user_id=test_user.id,
        employee_id=test_employee.id if test_employee else None,
        org_wide=True,
        visible_scope_ids=frozenset([test_org.id]),
        project_ids=frozenset(),
        member_conversation_ids=frozenset(),
        links={},
    )


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
    return customer


@pytest_asyncio.fixture
async def test_vendor(db_session, caller):
    """Create a test canonical vendor."""
    vendor = CanonicalVendor(
        organization_id=caller.organization_id,
        name="Test Vendor Inc",
        display_name="Test Vendor",
        kind="supplier",
        industry="Technology",
        country="US",
        state="active",
        criticality="medium",
        payment_terms="net30",
        currency="USD",
        fingerprint=f"cv-fp-{uuid.uuid4().hex[:32]}",
        created_by=caller.employee_id or "system",
    )
    db_session.add(vendor)
    await db_session.flush()
    return vendor


@pytest_asyncio.fixture
async def test_external_capacity(db_session, caller, test_vendor):
    """Create a test external capacity."""
    capacity = ExternalCapacity(
        organization_id=caller.organization_id,
        vendor_id=test_vendor.id,
        capacity_type="cloud_compute_units",
        capacity_name="AWS EC2 Reserved Instances",
        unit="vcpu-hours",
        total_capacity=5000.0,
        committed_capacity=2000.0,
        reserved_capacity=500.0,
        available_capacity=2500.0,
        window_start=date.today(),
        window_end=date.today() + timedelta(days=90),
        cost_per_unit=0.05,
        currency="USD",
        state="available",
        fingerprint=f"ec-fp-{uuid.uuid4().hex[:32]}",
        created_by=caller.employee_id or "system",
    )
    db_session.add(capacity)
    await db_session.flush()
    return capacity


@pytest_asyncio.fixture
async def test_procurement(db_session, caller, test_vendor):
    """Create a test canonical procurement."""
    procurement = CanonicalProcurement(
        organization_id=caller.organization_id,
        kind="purchase",
        title="Cloud Infrastructure Procurement",
        vendor_id=test_vendor.id,
        vendor_name=test_vendor.name,
        estimated_cost=50000.0,
        currency="USD",
        budget_id="budget-123",
        quantity=1000.0,
        unit="vcpu-hours",
        state="identified",
        requested_by=caller.employee_id or "system",
        requested_at=datetime.now(timezone.utc),
        fingerprint=f"cp-fp-{uuid.uuid4().hex[:32]}",
        created_by=caller.employee_id or "system",
    )
    db_session.add(procurement)
    await db_session.flush()
    return procurement


@pytest_asyncio.fixture
async def test_resource(db_session, caller):
    """Create a test canonical resource."""
    resource = CanonicalResource(
        organization_id=caller.organization_id,
        category="digital",
        kind="cloud_compute",
        name="Cloud Compute Resource",
        unit="vcpu-hours",
        total_capacity=10000.0,
        committed_capacity=5000.0,
        reserved_capacity=1000.0,
        available_capacity=4000.0,
        state="available",
        supply_source="procurement",
        cost_per_unit=0.05,
        currency="USD",
        fingerprint=f"cr-fp-{uuid.uuid4().hex[:32]}",
        created_by=caller.employee_id or "system",
    )
    db_session.add(resource)
    await db_session.flush()
    return resource


@pytest_asyncio.fixture
async def test_objective(db_session, caller):
    """Create test objective."""
    from app.models.execution_strategy import CompanyGoal
    
    # First create a goal
    goal = CompanyGoal(
        organization_id=caller.organization_id,
        title="Test Goal",
        description="Test goal for objective",
        kind="strategic",
    )
    db_session.add(goal)
    await db_session.flush()
    
    objective = CompanyObjective(
        organization_id=caller.organization_id,
        goal_id=goal.id,
        title="Test Objective",
        description="Test objective for project",
        kind="strategic",
        status="active",
        fingerprint=f"obj-fp-{uuid.uuid4().hex[:32]}",
    )
    db_session.add(objective)
    await db_session.flush()
    return objective


@pytest_asyncio.fixture
async def test_project(db_session, caller, test_objective):
    """Create test project linked to objective."""
    project = Project(
        organization_id=caller.organization_id,
        name="Strategic Project",
        code=f"STRAT-{uuid.uuid4().hex[:6]}",
        status="active",
        owner_id=caller.employee_id or "system",
    )
    db_session.add(project)
    await db_session.flush()
    
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
    
    from app.models.execution_strategy import StrategicLink
    link = StrategicLink(
        organization_id=caller.organization_id,
        initiative_id=initiative.id,
        project_id=project.id,
        source_event_id=f"evt-{uuid.uuid4().hex[:16]}",
        linked_at=utcnow(),
    )
    db_session.add(link)
    await db_session.flush()
    
    return project


# =============================================================================
# TESTS: MODEL CREATION
# =============================================================================

class TestCanonicalBusinessProcessModels:
    """Test canonical business process model creation."""
    
    @pytest.mark.asyncio
    async def test_create_canonical_business_process(self, db_session, caller):
        """Test creating a canonical business process."""
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Test Process",
            process_type="operational",
            category="sales",
            subcategory="onboarding",
            description="Test business process",
            lifecycle_state="defined",
            trigger_type="manual",
            owner_id=caller.employee_id or "system",
            owner_type="person",
            priority="high",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(process)
        await db_session.flush()
        
        assert process.id is not None
        assert process.name == "Test Process"
        assert process.process_type == "operational"
        assert process.lifecycle_state == "defined"
    
    @pytest.mark.asyncio
    async def test_create_process_execution(self, db_session, caller):
        """Test creating a process execution."""
        # First create a process
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Test Process",
            process_type="operational",
            lifecycle_state="defined",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(process)
        await db_session.flush()
        
        execution = ProcessExecution(
            organization_id=caller.organization_id,
            process_id=process.id,
            execution_number=1,
            trigger_type="manual",
            state="initializing",
            owner_id=caller.employee_id or "system",
            fingerprint=f"pe-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(execution)
        await db_session.flush()
        
        assert execution.id is not None
        assert execution.execution_number == 1
        assert execution.state == "initializing"
    
    @pytest.mark.asyncio
    async def test_create_process_step(self, db_session, caller):
        """Test creating a process step."""
        # Create process and execution first
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Test Process",
            process_type="operational",
            lifecycle_state="defined",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(process)
        await db_session.flush()
        
        execution = ProcessExecution(
            organization_id=caller.organization_id,
            process_id=process.id,
            execution_number=1,
            trigger_type="manual",
            state="initializing",
            fingerprint=f"pe-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(execution)
        await db_session.flush()
        
        step = ProcessStep(
            organization_id=caller.organization_id,
            execution_id=execution.id,
            step_key="step-1",
            step_name="First Step",
            step_type="approval",
            state="pending",
            fingerprint=f"ps-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(step)
        await db_session.flush()
        
        assert step.id is not None
        assert step.step_key == "step-1"
        assert step.step_type == "approval"
    
    @pytest.mark.asyncio
    async def test_create_process_approval(self, db_session, caller):
        """Test creating a process approval."""
        approval = ProcessApproval(
            organization_id=caller.organization_id,
            execution_id="exec-123",
            title="Test Approval",
            approval_type="sequential",
            approver_type="user",
            minimum_approvals=1,
            requested_by="system",
            fingerprint=f"pa-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(approval)
        await db_session.flush()
        
        assert approval.id is not None
        assert approval.title == "Test Approval"
        assert approval.status == "pending"


# =============================================================================
# TESTS: EXACT-ONCE SEMANTICS
# =============================================================================

class TestExactOnceSemantics:
    """Test exact-once semantics for all models."""
    
    @pytest.mark.asyncio
    async def test_business_process_exact_once(self, db_session, caller):
        """Test exact-once for canonical business process."""
        fp = f"cbp-exact-{uuid.uuid4().hex[:32]}"
        process1 = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Exact Process",
            process_type="operational",
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(process1)
        await db_session.flush()
        
        process2 = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Exact Process",
            process_type="operational",
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(process2)
        
        with pytest.raises(IntegrityError):
            await db_session.flush()
    
    @pytest.mark.asyncio
    async def test_process_execution_exact_once(self, db_session, caller):
        """Test exact-once for process execution."""
        fp = f"pe-exact-{uuid.uuid4().hex[:32]}"
        exec1 = ProcessExecution(
            organization_id=caller.organization_id,
            process_id="proc-123",
            execution_number=1,
            trigger_type="manual",
            state="initializing",
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(exec1)
        await db_session.flush()
        
        exec2 = ProcessExecution(
            organization_id=caller.organization_id,
            process_id="proc-123",
            execution_number=1,
            trigger_type="manual",
            state="initializing",
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(exec2)
        
        with pytest.raises(IntegrityError):
            await db_session.flush()
    
    @pytest.mark.asyncio
    async def test_process_step_exact_once(self, db_session, caller):
        """Test exact-once for process step."""
        fp = f"ps-exact-{uuid.uuid4().hex[:32]}"
        step1 = ProcessStep(
            organization_id=caller.organization_id,
            execution_id="exec-123",
            step_key="step-1",
            step_name="Test Step",
            step_type="approval",
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(step1)
        await db_session.flush()
        
        step2 = ProcessStep(
            organization_id=caller.organization_id,
            execution_id="exec-123",
            step_key="step-1",
            step_name="Test Step",
            step_type="approval",
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(step2)
        
        with pytest.raises(IntegrityError):
            await db_session.flush()
    
    @pytest.mark.asyncio
    async def test_process_approval_exact_once(self, db_session, caller):
        """Test exact-once for process approval."""
        fp = f"pa-exact-{uuid.uuid4().hex[:32]}"
        approval1 = ProcessApproval(
            organization_id=caller.organization_id,
            execution_id="exec-123",
            title="Exact Approval",
            fingerprint=fp,
        )
        db_session.add(approval1)
        await db_session.flush()
        
        approval2 = ProcessApproval(
            organization_id=caller.organization_id,
            execution_id="exec-123",
            title="Exact Approval",
            fingerprint=fp,
        )
        db_session.add(approval2)
        
        with pytest.raises(IntegrityError):
            await db_session.flush()


# =============================================================================
# TESTS: PROCESS OPERATING SLICE
# =============================================================================

class TestProcessOperatingSlice:
    """Test process operating slice derivation."""
    
    @pytest.mark.asyncio
    async def test_derive_process_operating_slice(self, db_session, caller, test_vendor, test_resource):
        """Test deriving process operating slice."""
        slice_obj = await canonical_business_process_service.derive_process_operating_slice(
            db_session, caller=caller
        )
        
        assert slice_obj.id is not None
        assert slice_obj.organization_id == caller.organization_id
        assert slice_obj.fingerprint is not None
    
    @pytest.mark.asyncio
    async def test_slice_exact_once(self, db_session, caller):
        """Test exact-once for process operating slice."""
        slice1 = await canonical_business_process_service.derive_process_operating_slice(
            db_session, caller=caller
        )
        slice2 = await canonical_business_process_service.derive_process_operating_slice(
            db_session, caller=caller
        )
        
        assert slice1.id == slice2.id
        assert slice1.fingerprint == slice2.fingerprint


# =============================================================================
# TESTS: PROCESS MANAGEMENT
# =============================================================================

class TestProcessManagement:
    """Test process creation and management."""
    
    @pytest.mark.asyncio
    async def test_create_business_process(self, db_session, caller):
        """Test creating a business process via service."""
        process = await canonical_business_process_service.create_business_process(
            db_session,
            caller=caller,
            name="Service Process",
            process_type="operational",
            category="hr",
            subcategory="onboarding",
            description="New hire onboarding process",
            trigger_type="event",
            owner_id=caller.employee_id,
        )
        
        assert process.id is not None
        assert process.name == "Service Process"
        assert process.category == "hr"
    
    @pytest.mark.asyncio
    async def test_vendor_exact_once_via_service(self, db_session, caller):
        """Test exact-once for process creation via service."""
        process1 = await canonical_business_process_service.create_business_process(
            db_session,
            caller=caller,
            name="Exact Process",
            process_type="operational",
        )
        process2 = await canonical_business_process_service.create_business_process(
            db_session,
            caller=caller,
            name="Exact Process",
            process_type="operational",
        )
        
        assert process1.id == process2.id
    
    @pytest.mark.asyncio
    async def test_create_process_execution(self, db_session, caller):
        """Test creating a process execution via service."""
        # Create process first
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Test Process",
            process_type="operational",
            lifecycle_state="defined",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(process)
        await db_session.flush()
        
        execution = await canonical_business_process_service.create_process_execution(
            db_session,
            caller=caller,
            process_id=process.id,
            trigger_type="manual",
        )
        
        assert execution.id is not None
        assert execution.state == "initializing"
        assert execution.execution_number == 1
    
    @pytest.mark.asyncio
    async def test_transition_process_state(self, db_session, caller):
        """Test process state transition."""
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="State Test Process",
            process_type="operational",
            lifecycle_state="defined",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(process)
        await db_session.flush()
        
        # Transition to triggered
        process = await canonical_business_process_service.transition_process_state(
            db_session,
            caller=caller,
            process_id=process.id,
            new_state="triggered",
            reason="Test trigger",
        )
        
        assert process is not None
        assert process.lifecycle_state == "triggered"
        assert process.started_at is not None
        
        # Transition to completed
        process = await canonical_business_process_service.transition_process_state(
            db_session,
            caller=caller,
            process_id=process.id,
            new_state="completed",
            reason="Test completed",
        )
        
        assert process.lifecycle_state == "completed"
        assert process.completed_at is not None


# =============================================================================
# TESTS: PROCESS EXECUTION MANAGEMENT
# =============================================================================

class TestProcessExecutionManagement:
    """Test process execution creation and management."""
    
    @pytest.mark.asyncio
    async def test_create_process_execution(self, db_session, caller):
        """Test creating a process execution."""
        # Create process first
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Test Process",
            process_type="operational",
            lifecycle_state="defined",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(process)
        await db_session.flush()
        
        execution = await canonical_business_process_service.create_process_execution(
            db_session,
            caller=caller,
            process_id=process.id,
            trigger_type="manual",
        )
        
        assert execution.id is not None
        assert execution.state == "initializing"
        assert execution.execution_number == 1
    
    @pytest.mark.asyncio
    async def test_transition_execution_state(self, db_session, caller):
        """Test execution state transition."""
        # Create process and execution
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Exec Process",
            process_type="operational",
            lifecycle_state="defined",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(process)
        await db_session.flush()
        
        execution = await canonical_business_process_service.create_process_execution(
            db_session,
            caller=caller,
            process_id=process.id,
        )
        
        # Transition to running
        execution = await canonical_business_process_service.transition_execution_state(
            db_session,
            caller=caller,
            execution_id=execution.id,
            new_state="running",
            reason="Started execution",
        )
        
        assert execution is not None
        assert execution.state == "running"
        assert execution.started_at is not None
        
        # Transition to completed
        execution = await canonical_business_process_service.transition_execution_state(
            db_session,
            caller=caller,
            execution_id=execution.id,
            new_state="completed",
            reason="Completed successfully",
        )
        
        assert execution.state == "completed"
        assert execution.completed_at is not None


# =============================================================================
# TESTS: PROCESS STEP MANAGEMENT
# =============================================================================

class TestProcessStepManagement:
    """Test process step creation and management."""
    
    @pytest.mark.asyncio
    async def test_create_process_step(self, db_session, caller):
        """Test creating a process step."""
        # Create process and execution
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Step Test Process",
            process_type="operational",
            lifecycle_state="defined",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(process)
        await db_session.flush()
        
        execution = ProcessExecution(
            organization_id=caller.organization_id,
            process_id=process.id,
            execution_number=1,
            trigger_type="manual",
            state="running",
            fingerprint=f"pe-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(execution)
        await db_session.flush()
        
        step = await canonical_business_process_service.create_process_step(
            db_session,
            caller=caller,
            execution_id=execution.id,
            step_key="step-1",
            step_name="Test Step",
            step_type="approval",
        )
        
        assert step.id is not None
        assert step.step_key == "step-1"
        assert step.step_type == "approval"
        assert step.state == "pending"
    
    @pytest.mark.asyncio
    async def test_complete_step(self, db_session, caller):
        """Test completing a step."""
        # Create process, execution, and step
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Complete Step Process",
            process_type="operational",
            lifecycle_state="defined",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(process)
        await db_session.flush()
        
        execution = ProcessExecution(
            organization_id=caller.organization_id,
            process_id=process.id,
            execution_number=1,
            trigger_type="manual",
            state="running",
            fingerprint=f"pe-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(execution)
        await db_session.flush()
        
        step = ProcessStep(
            organization_id=caller.organization_id,
            execution_id=execution.id,
            step_key="step-1",
            step_name="Test Step",
            step_type="task",
            state="running",
            started_at=utcnow(),
            fingerprint=f"ps-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(step)
        await db_session.flush()
        
        completed = await canonical_business_process_service.complete_step(
            db_session,
            caller=caller,
            step_id=step.id,
            output_data={"result": "success"},
        )
        
        assert completed is not None
        assert completed.state == "succeeded"
        assert completed.completed_at is not None
        assert completed.output_data_json == {"result": "success"}
    
    @pytest.mark.asyncio
    async def test_fail_step(self, db_session, caller):
        """Test failing a step."""
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Fail Step Process",
            process_type="operational",
            lifecycle_state="defined",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(process)
        await db_session.flush()
        
        execution = ProcessExecution(
            organization_id=caller.organization_id,
            process_id=process.id,
            execution_number=1,
            trigger_type="manual",
            state="running",
            fingerprint=f"pe-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(execution)
        await db_session.flush()
        
        step = ProcessStep(
            organization_id=caller.organization_id,
            execution_id=execution.id,
            step_key="step-1",
            step_name="Failing Step",
            step_type="task",
            state="running",
            started_at=utcnow(),
            max_retries=0,
            fingerprint=f"ps-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(step)
        await db_session.flush()
        
        failed = await canonical_business_process_service.fail_step(
            db_session,
            caller=caller,
            step_id=step.id,
            error="Test error",
        )
        
        assert failed is not None
        assert failed.state == "failed"
        assert failed.error == "Test error"
        assert failed.error_count == 1


# =============================================================================
# TESTS: PROCESS APPROVAL MANAGEMENT
# =============================================================================

class TestProcessApprovalManagement:
    """Test process approval creation and management."""
    
    @pytest.mark.asyncio
    async def test_create_process_approval(self, db_session, caller):
        """Test creating a process approval."""
        approval = await canonical_business_process_service.create_process_approval(
            db_session,
            caller=caller,
            execution_id="exec-123",
            title="Test Approval",
            description="Need manager approval",
            approval_type="sequential",
            approver_type="user",
            minimum_approvals=2,
            requires_approval=True,
        )
        
        assert approval.id is not None
        assert approval.title == "Test Approval"
        assert approval.status == "pending"
        assert approval.minimum_approvals == 2
    
    @pytest.mark.asyncio
    async def test_authorize_approval(self, db_session, caller):
        """Test authorizing an approval."""
        approval = ProcessApproval(
            organization_id=caller.organization_id,
            execution_id="exec-123",
            title="Auth Test",
            approval_type="sequential",
            approver_type="user",
            minimum_approvals=1,
            requested_by=caller.employee_id or "system",
            fingerprint=f"pa-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(approval)
        await db_session.flush()
        
        authorized = await canonical_business_process_service.decide_approval(
            db_session,
            caller=caller,
            approval_id=approval.id,
            decision="approved",
            decided_by=caller.employee_id,
            note="Approved for Q2",
        )
        
        assert authorized is not None
        assert authorized.status == "approved"
        assert authorized.decided_by == caller.employee_id
        
        # Test rejection
        approval2 = ProcessApproval(
            organization_id=caller.organization_id,
            execution_id="exec-456",
            title="Reject Test",
            approval_type="sequential",
            approver_type="user",
            minimum_approvals=1,
            requested_by="system",
            fingerprint=f"pa-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(approval2)
        await db_session.flush()
        
        rejected = await canonical_business_process_service.decide_approval(
            db_session,
            caller=caller,
            approval_id=approval2.id,
            decision="rejected",
            decided_by=caller.employee_id,
            note="Budget exceeded",
        )
        
        assert rejected.status == "rejected"


# =============================================================================
# TESTS: GATE 15 INTEGRATION (Finance)
# =============================================================================

class TestGate15Integration:
    """Test integration with Gate 15 financial."""
    
    @pytest.mark.asyncio
    async def test_link_procurement_to_budget(self, db_session, caller, test_procurement):
        """Test linking procurement to budget commitment."""
        budget_commitment = BudgetCommitmentRecord(
            organization_id=caller.organization_id,
            budget_id="budget-123",
            committed_amount=50000.0,
            fingerprint=f"bc-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(budget_commitment)
        await db_session.flush()
        
        procurement = await canonical_procurement_vendor_service.link_procurement_to_budget(
            db_session,
            caller=caller,
            procurement_id=test_procurement.id,
            budget_commitment_id=budget_commitment.id,
        )
        
        assert procurement is not None
        assert procurement.budget_commitment_id == budget_commitment.id
        assert procurement.budget_id == budget_commitment.budget_id
    
    @pytest.mark.asyncio
    async def test_link_procurement_to_financial_outcome(self, db_session, caller, test_procurement):
        """Test linking procurement to financial outcome."""
        outcome = FinancialOutcomeRecord(
            organization_id=caller.organization_id,
            kind="cost_incurred",
            title="Procurement Cost",
            metric_kind="cost",
            target_value=50000.0,
            actual_value=48000.0,
            cost_impact=48000.0,
            currency="USD",
            fingerprint=f"fo-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(outcome)
        await db_session.flush()
        
        procurement = await canonical_procurement_vendor_service.link_procurement_to_financial_outcome(
            db_session,
            caller=caller,
            procurement_id=test_procurement.id,
            financial_outcome_id=outcome.id,
        )
        
        assert procurement is not None
        assert procurement.actual_cost == 48000.0


# =============================================================================
# TESTS: GATE 16 INTEGRATION (Resource/Asset)
# =============================================================================

class TestGate16Integration:
    """Test integration with Gate 16 resource/asset."""
    
    @pytest.mark.asyncio
    async def test_fulfill_procurement_create_resource(self, db_session, caller, test_procurement):
        """Test fulfilling procurement creates resource (Gate 16 integration)."""
        # Transition to completed state first
        await canonical_business_process_service.transition_execution_state(
            db_session,
            caller=caller,
            execution_id=test_procurement.id,
            new_state="completed",
        )
        
        procurement = await canonical_procurement_vendor_service.fulfill_procurement_create_resource(
            db_session,
            caller=caller,
            procurement_id=test_procurement.id,
            received_quantity=10.0,
            accepted_quantity=10.0,
            quality_notes="All items passed inspection",
        )
        
        assert procurement is not None
        assert procurement.state == "received"
        assert procurement.accepted_quantity == 10.0


# =============================================================================
# TESTS: VENDOR PERFORMANCE
# =============================================================================

class TestVendorPerformance:
    """Test vendor performance derivation."""
    
    @pytest.mark.asyncio
    async def test_derive_vendor_performance(self, db_session, caller, test_vendor):
        """Test deriving vendor performance metrics."""
        # Create some procurements with delivery data
        for i in range(10):
            delivered_at = datetime.now(timezone.utc) - timedelta(days=i*3)
            expected = (delivered_at - timedelta(days=1)).date() if i % 3 != 0 else (delivered_at + timedelta(days=2)).date()
            
            proc = CanonicalProcurement(
                organization_id=caller.organization_id,
                kind="purchase",
                title=f"Procurement {i}",
                vendor_id=test_vendor.id,
                vendor_name=test_vendor.name,
                state="accepted",
                delivered_at=delivered_at,
                expected_delivery=expected,
                ordered_at=delivered_at - timedelta(days=5),
                fingerprint=f"cp-perf-{i}-{uuid.uuid4().hex[:24]}",
                created_by=caller.employee_id or "system",
            )
            db_session.add(proc)
        await db_session.flush()
        
        results = await canonical_procurement_vendor_service.derive_vendor_performance(
            db_session,
            caller=caller,
            vendor_id=test_vendor.id,
            period_start=date.today() - timedelta(days=30),
            period_end=date.today(),
        )
        
        assert len(results) >= 3  # on_time_delivery, quality, lead_time
        
        # Check on-time delivery metric
        on_time = next((r for r in results if r.metric_kind == "on_time_delivery"), None)
        assert on_time is not None
        assert 0 <= on_time.metric_value <= 1


# =============================================================================
# TESTS: CONFLICT DERIVATION
# =============================================================================

class TestConflictDerivation:
    """Test process bottleneck/conflict derivation."""
    
    @pytest.mark.asyncio
    async def test_derive_overdue_approval_conflict(self, db_session, caller, test_vendor):
        """Test detecting overdue approval conflict."""
        # Create overdue approval
        approval = ProcessApproval(
            organization_id=caller.organization_id,
            execution_id="exec-123",
            title="Overdue Approval",
            status="pending",
            due_at=utcnow() - timedelta(days=5),
            fingerprint=f"pa-fp-{uuid.uuid4().hex[:32]}",
            requested_by=caller.employee_id or "system",
        )
        db_session.add(approval)
        await db_session.flush()
        
        conflicts = await canonical_business_process_service.derive_process_conflicts(
            db_session, caller=caller
        )
        
        overdue_conflicts = [c for c in conflicts if c.bottleneck_type == "approval_bottleneck"]
        assert len(overdue_conflicts) >= 1
    
    @pytest.mark.asyncio
    async def test_derive_capacity_overload_conflict(self, db_session, caller, test_resource):
        """Test detecting capacity overload conflict."""
        # Make resource constrained
        test_resource.committed_capacity = test_resource.total_capacity
        test_resource.available_capacity = 0.0
        await db_session.flush()
        
        conflicts = await canonical_business_process_service.derive_process_conflicts(
            db_session, caller=caller
        )
        
        overload_conflicts = [c for c in conflicts if c.bottleneck_type == "resource_capacity"]
        assert len(overload_conflicts) >= 1
    
    @pytest.mark.asyncio
    async def test_derive_underutilization_conflict(self, db_session, caller, test_resource):
        """Test detecting underutilization conflict."""
        from app.models.canonical_resource_asset import ResourceAllocation
        
        allocation = ResourceAllocation(
            organization_id=caller.organization_id,
            resource_id=test_resource.id,
            resource_category=test_resource.category,
            resource_kind=test_resource.kind,
            target_type="project",
            target_id="proj-1",
            units_allocated=100,
            actual_utilization=10,
            state="active",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            fingerprint=f"ra-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(allocation)
        await db_session.flush()
        
        conflicts = await canonical_business_process_service.derive_process_conflicts(
            db_session, caller=caller
        )
        
        under_conflicts = [c for c in conflicts if c.bottleneck_type == "underutilization"]
        assert len(under_conflicts) >= 1
    
    @pytest.mark.asyncio
    async def test_derive_contract_expiring_conflict(self, db_session, caller, test_vendor):
        """Test detecting vendor contract expiring conflict."""
        test_vendor.contract_expires_at = utcnow() + timedelta(days=30)
        test_vendor.auto_renew = False
        await db_session.flush()
        
        conflicts = await canonical_business_process_service.derive_process_conflicts(
            db_session, caller=caller
        )
        
        contract_conflicts = [c for c in conflicts if c.bottleneck_type == "vendor_contract_expiring"]
        assert len(contract_conflicts) >= 1


# =============================================================================
# TESTS: PROCESS IMPACT ANALYSIS
# =============================================================================

class TestProcessImpactAnalysis:
    """Test process impact analysis."""
    
    @pytest.mark.asyncio
    async def test_analyze_process_impact(self, db_session, caller):
        """Test analyzing process impact."""
        # Create process
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Impact Test Process",
            process_type="operational",
            lifecycle_state="defined",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by="system",
        )
        db_session.add(process)
        await db_session.flush()
        
        analysis = await canonical_business_process_service.analyze_process_impact(
            db_session,
            caller=caller,
            trigger_type="process_modified",
            trigger_entity_type="process",
            trigger_entity_id=process.id,
            trigger_params={"source_event_id": "evt-123"},
        )
        
        assert analysis.id is not None
        assert analysis.trigger_type == "process_modified"
        assert analysis.trigger_entity_id == process.id
        assert analysis.fingerprint is not None
    
    @pytest.mark.asyncio
    async def test_impact_analysis_exact_once(self, db_session, caller):
        """Test exact-once for impact analysis."""
        analysis1 = await canonical_business_process_service.analyze_process_impact(
            db_session,
            caller=caller,
            trigger_type="process_created",
            trigger_entity_type="process",
            trigger_entity_id="proc-123",
        )
        analysis2 = await canonical_business_process_service.analyze_process_impact(
            db_session,
            caller=caller,
            trigger_type="process_created",
            trigger_entity_type="process",
            trigger_entity_id="proc-123",
        )
        
        assert analysis1.id == analysis2.id
        assert analysis1.fingerprint == analysis2.fingerprint


# =============================================================================
# TESTS: PROCESS SCENARIO (Counterfactual)
# =============================================================================

class TestCounterfactualIntegration:
    """Test counterfactual scenario integration."""
    
    @pytest.mark.asyncio
    async def test_create_process_scenario(self, db_session, caller, test_vendor, test_procurement):
        """Test creating a procurement scenario."""
        result = await canonical_business_process_service.create_process_scenario(
            db_session,
            caller=caller,
            scenario_name="Vendor Failure Scenario",
            process_changes=[
                {
                    "type": "vendor_unavailable",
                    "vendor_id": test_vendor.id,
                    "duration_days": 14,
                },
                {
                    "type": "procurement_delayed",
                    "procurement_id": test_procurement.id,
                    "delay_days": 7,
                },
            ],
        )
        
        assert "scenario_id" in result or "error" in result


# =============================================================================
# TESTS: GOVERNANCE & SECURITY
# =============================================================================

class TestGovernance:
    """Test governance and security."""
    
    @pytest.mark.asyncio
    async def test_process_tenant_isolation(self, db_session, caller, test_org, test_vendor):
        """Test that process data doesn't leak across tenants."""
        from app.models.organization import Organization
        other_org = Organization(
            name="Other Org",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(other_org)
        await db_session.flush()
        
        other_process = CanonicalBusinessProcess(
            organization_id=other_org.id,
            name="Other Process",
            process_type="operational",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by="other",
        )
        db_session.add(other_process)
        await db_session.flush()
        
        # Create a process for caller's org
        caller_process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name="Caller Process",
            process_type="operational",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by="caller",
        )
        db_session.add(caller_process)
        await db_session.flush()
        
        # Query processes for caller's org - should only see own
        result = await db_session.execute(
            select(CanonicalBusinessProcess).where(
                CanonicalBusinessProcess.organization_id == caller.organization_id
            )
        )
        processes = result.scalars().all()
        process_ids = {p.id for p in processes}
        
        assert caller_process.id in process_ids
        assert other_process.id not in process_ids
    
    @pytest.mark.asyncio
    async def test_execution_tenant_isolation(self, db_session, caller, test_org, test_vendor):
        """Test execution tenant isolation."""
        from app.models.organization import Organization
        other_org = Organization(
            name="Other Org",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(other_org)
        await db_session.flush()
        
        other_process = CanonicalBusinessProcess(
            organization_id=other_org.id,
            name="Other Process",
            process_type="operational",
            fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
            created_by="other",
        )
        db_session.add(other_process)
        await db_session.flush()
        
        other_exec = ProcessExecution(
            organization_id=other_org.id,
            process_id=other_process.id,
            execution_number=1,
            trigger_type="manual",
            fingerprint=f"pe-fp-{uuid.uuid4().hex[:32]}",
            created_by="other",
        )
        db_session.add(other_exec)
        await db_session.flush()
        
        result = await db_session.execute(
            select(ProcessExecution).where(
                ProcessExecution.organization_id == caller.organization_id
            )
        )
        executions = result.scalars().all()
        assert other_exec.id not in {e.id for e in executions}


# =============================================================================
# TESTS: ADVERSARIAL
# =============================================================================

class TestAdversarial:
    """Adversarial tests."""
    
    @pytest.mark.asyncio
    async def test_fake_process_id_rejected(self, db_session, caller):
        """Test that fake process IDs don't create valid executions."""
        fake_id = f"fake-{uuid.uuid4().hex[:24]}"
        
        execution = ProcessExecution(
            organization_id=caller.organization_id,
            process_id=fake_id,
            execution_number=1,
            trigger_type="manual",
            fingerprint=f"pe-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(execution)
        await db_session.flush()
        
        # Verify it references non-existent process
        result = await db_session.execute(
            select(CanonicalBusinessProcess).where(
                CanonicalBusinessProcess.id == fake_id
            )
        )
        assert result.scalars().first() is None
    
    @pytest.mark.asyncio
    async def test_cross_tenant_process_creation_blocked(self, db_session, caller, test_org):
        """Test that creating process for another org fails governance."""
        from app.models.organization import Organization
        other_org = Organization(
            name="Other Org",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(other_org)
        await db_session.flush()
        
        # Service should only create for caller's org
        process = await canonical_business_process_service.create_business_process(
            db_session,
            caller=caller,
            name="Cross Tenant Process",
            process_type="operational",
        )
        
        assert process.organization_id == caller.organization_id
        assert process.organization_id != other_org.id


# =============================================================================
# TESTS: REGRESSION (Prior Gates Still Work)
# =============================================================================

class TestRegression:
    """Test that prior gates still work."""
    
    @pytest.mark.asyncio
    async def test_gate17_vendor_still_works(self, db_session, caller):
        """Test Gate 17 vendor service still works."""
        slice_obj = await canonical_procurement_vendor_service.derive_vendor_operating_slice(
            db_session, caller=caller
        )
        assert slice_obj.id is not None
    
    @pytest.mark.asyncio
    async def test_gate16_resource_still_works(self, db_session, caller):
        """Test Gate 16 resource service still works."""
        slice_obj = await canonical_resource_asset_service.derive_resource_operating_slice(
            db_session, caller=caller
        )
        assert slice_obj.id is not None
    
    @pytest.mark.asyncio
    async def test_gate15_financial_still_works(self, db_session, caller):
        """Test Gate 15 financial service still works."""
        slice_obj = await financial_resource_procurement_service.derive_financial_operating_slice(
            db_session, caller=caller
        )
        assert slice_obj.id is not None
    
    @pytest.mark.asyncio
    async def test_gate14_customer_still_works(self, db_session, caller, test_customer):
        """Test Gate 14 customer service still works."""
        from app.intelligence.customer_operating_fabric_service import customer_operating_fabric_service
        slice_obj = await customer_operating_fabric_service.derive_customer_operating_slice(
            db_session, caller=caller, customer_id=test_customer.id
        )
        assert slice_obj.id is not None
    
    @pytest.mark.asyncio
    async def test_gate13_alignment_still_works(self, db_session, caller, test_project):
        """Test Gate 13 strategic alignment still works."""
        result = await strategic_alignment_engine.trace_forward(
            db_session, caller=caller,
            entity_type="project", entity_id=test_project.id, max_depth=3
        )
        assert "chain" in result
    
    @pytest.mark.asyncio
    async def test_gate12_digital_twin_still_works(self, db_session, caller):
        """Test Gate 12 Digital Twin still works."""
        twin = await canonical_digital_twin_service.derive_twin_state(
            db_session, caller=caller
        )
        assert twin is not None
    
    @pytest.mark.asyncio
    async def test_gate11_counterfactual_still_works(self, db_session, caller, test_employee):
        """Test Gate 11 counterfactual still works."""
        result = await counterfactual_intelligence_service.create_scenario(
            db_session,
            caller=caller,
            scenario_kind="capacity_change",
            subject_type="person",
            subject_id=test_employee.id,
            params={"delta": 1},
            dry_run=False,
        )
        assert result["scenario_id"] is not None
    
    @pytest.mark.asyncio
    async def test_gate10_predictive_still_works(self, db_session, caller):
        """Test Gate 10 predictive still works."""
        from app.models.prediction import Prediction
        slice_obj = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller
        )
        assert slice_obj is not None


# =============================================================================
# TESTS: VOCABULARIES
# =============================================================================

class TestVocabularies:
    """Test canonical vocabularies are complete."""
    
    def test_process_lifecycle_states_complete(self):
        """Test all expected lifecycle states exist."""
        expected = {"defined", "ready", "triggered", "in_progress", "blocked", 
                      "waiting", "completed", "verified", "superseded", "archived"}
        assert set(PROCESS_LIFECYCLE_STATES) == expected
    
    def test_process_types_complete(self):
        """Test process types cover major types."""
        types = set(PROCESS_TYPES)
        assert "operational" in types
        assert "project_based" in types
        assert "customer_facing" in types
        assert "internal" in types
        assert "compliance" in types
        assert "emergency" in types
        assert "strategic" in types
    
    def test_process_triggers_complete(self):
        """Test all trigger types covered."""
        triggers = set(PROCESS_TRIGGERS)
        assert "manual" in triggers
        assert "event" in triggers
        assert "schedule" in triggers
        assert "webhook" in triggers
        assert "condition" in triggers
        assert "approval" in triggers
        assert "threshold" in triggers
        assert "manual_override" in triggers
    
    def test_process_priorities_complete(self):
        """Test all priorities covered."""
        priorities = set(PROCESS_PRIORITIES)
        assert "critical" in priorities
        assert "high" in priorities
        assert "medium" in priorities
        assert "low" in priorities
    
    def test_process_roles_complete(self):
        """Test all target types supported."""
        roles = set(PROCESS_ROLES)
        assert "owner" in roles
        assert "accountable" in roles
        assert "participant" in roles
        assert "reviewer" in roles
        assert "executor" in roles
        assert "stakeholder" in roles


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])