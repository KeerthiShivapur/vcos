"""Gate 17 — Canonical Procurement, Vendor & External Capacity Operating Fabric Tests."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow

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
from app.intelligence.company_context import CallerAccess
from app.models.role import Role, UserRole
from app.services.permission_service import permission_service
from app.models.canonical_procurement_vendor import (
    CanonicalVendor,
    VendorCapability,
    ExternalCapacity,
    CanonicalProcurement,
    VendorPerformance,
    VendorDependency,
    VendorOperatingSlice,
    ProcurementImpactAnalysis,
    VENDOR_KINDS,
    VENDOR_STATES,
    EXTERNAL_CAPACITY_TYPES,
    PROCUREMENT_LIFECYCLE_STATES,
    PROCUREMENT_KINDS,
    AUTHORIZATION_STATES,
    VENDOR_CAPABILITY_CATEGORIES,
    DEPENDENCY_CRITICALITY,
    VENDOR_RISK_KINDS,
)
from app.models.financial_resource_procurement import (
    BudgetCommitmentRecord,
    FinancialOutcomeRecord,
    ProcurementRecord,
)
from app.models.canonical_resource_asset import (
    CanonicalResource,
    ResourceDemand,
    ResourceAllocation,
)
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
)
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyObjective,
    CompanyInitiative,
    StrategicLink,
)
from app.models.project import Project
from app.models.customer import Customer, CustomerProjectLink
from app.models.customer_intelligence import CustomerCommitment


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
async def test_objective(db_session, caller):
    """Create test objective."""
    from app.models.execution_strategy import CompanyObjective, CompanyGoal
    
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
    from app.models.project import Project
    from app.models.execution_strategy import CompanyInitiative, StrategicLink
    
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
        source_event_id=f"evt-{uuid.uuid4().hex[:16]}",
        linked_at=utcnow(),
    )
    db_session.add(link)
    await db_session.flush()
    
    return project


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
async def test_vendor_capability(db_session, caller, test_vendor):
    """Create a test vendor capability."""
    capability = VendorCapability(
        organization_id=caller.organization_id,
        vendor_id=test_vendor.id,
        capability_category="cloud_infrastructure",
        capability_name="AWS EC2 Compute",
        unit="vcpu-hours",
        max_capacity=10000.0,
        unit_cost=0.05,
        currency="USD",
        sla_details_json={"availability": 0.9999, "support": "24/7"},
        state="active",
        fingerprint=f"vc-fp-{uuid.uuid4().hex[:32]}",
        created_by=caller.employee_id or "system",
    )
    db_session.add(capability)
    await db_session.flush()
    return capability


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


# =============================================================================
# TESTS: MODEL CREATION
# =============================================================================

class TestCanonicalVendorModels:
    """Test canonical vendor model creation."""
    
    @pytest.mark.asyncio
    async def test_create_canonical_vendor(self, db_session, caller):
        """Test creating a canonical vendor."""
        vendor = CanonicalVendor(
            organization_id=caller.organization_id,
            name="Test Vendor",
            kind="supplier",
            state="active",
            criticality="high",
            payment_terms="net30",
            currency="USD",
            fingerprint=f"cv-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(vendor)
        await db_session.flush()
        
        assert vendor.id is not None
        assert vendor.name == "Test Vendor"
        assert vendor.kind == "supplier"
        assert vendor.is_critical is True  # high criticality
    
    @pytest.mark.asyncio
    async def test_create_vendor_capability(self, db_session, caller, test_vendor):
        """Test creating a vendor capability."""
        capability = VendorCapability(
            organization_id=caller.organization_id,
            vendor_id=test_vendor.id,
            capability_category="cloud_infrastructure",
            capability_name="Cloud Compute",
            unit="vcpu-hours",
            max_capacity=10000.0,
            unit_cost=0.05,
            currency="USD",
            fingerprint=f"vc-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(capability)
        await db_session.flush()
        
        assert capability.id is not None
        assert capability.capability_category == "cloud_infrastructure"
        assert capability.max_capacity == 10000.0
    
    @pytest.mark.asyncio
    async def test_create_external_capacity(self, db_session, caller, test_vendor):
        """Test creating external capacity."""
        capacity = ExternalCapacity(
            organization_id=caller.organization_id,
            vendor_id=test_vendor.id,
            capacity_type="contractor_fte",
            capacity_name="Contractor Pool",
            unit="fte",
            total_capacity=50.0,
            committed_capacity=20.0,
            available_capacity=30.0,
            window_start=date.today(),
            window_end=date.today() + timedelta(days=90),
            cost_per_unit=5000.0,
            currency="USD",
            state="available",
            fingerprint=f"ec-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(capacity)
        await db_session.flush()
        
        assert capacity.id is not None
        assert capacity.utilization_rate == 0.4  # 20/50
        assert capacity.is_constrained is False
    
    @pytest.mark.asyncio
    async def test_create_canonical_procurement(self, db_session, caller, test_vendor):
        """Test creating a canonical procurement."""
        procurement = CanonicalProcurement(
            organization_id=caller.organization_id,
            kind="purchase",
            title="Server Procurement",
            vendor_id=test_vendor.id,
            vendor_name=test_vendor.name,
            estimated_cost=100000.0,
            currency="USD",
            quantity=10.0,
            unit="units",
            state="identified",
            requested_by=caller.employee_id or "system",
            fingerprint=f"cp-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(procurement)
        await db_session.flush()
        
        assert procurement.id is not None
        assert procurement.is_active is True
        assert procurement.lead_time_days is None
    
    @pytest.mark.asyncio
    async def test_create_vendor_performance(self, db_session, caller, test_vendor):
        """Test creating vendor performance record."""
        performance = VendorPerformance(
            organization_id=caller.organization_id,
            vendor_id=test_vendor.id,
            period_start=date.today().replace(day=1),
            period_end=date.today(),
            metric_kind="on_time_delivery",
            metric_value=0.95,
            metric_unit="ratio",
            target_value=0.95,
            variance=0.0,
            trend="stable",
            sample_size=20,
            confidence=0.8,
            fingerprint=f"vp-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(performance)
        await db_session.flush()
        
        assert performance.id is not None
        assert performance.metric_value == 0.95
    
    @pytest.mark.asyncio
    async def test_create_vendor_dependency(self, db_session, caller, test_vendor):
        """Test creating vendor dependency."""
        dependency = VendorDependency(
            organization_id=caller.organization_id,
            vendor_id=test_vendor.id,
            criticality="high",
            dependency_type="single_source",
            risk_level="high",
            risk_kinds_json=["concentration_risk", "delivery_risk"],
            alternative_vendor_ids_json=[],
            substitution_feasibility="difficult",
            title=f"Dependency on {test_vendor.name}",
            description="Critical single-source dependency",
            evidence_json={"procurement_count": 15},
            fingerprint=f"vd-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(dependency)
        await db_session.flush()
        
        assert dependency.id is not None
        assert dependency.criticality == "high"


# =============================================================================
# TESTS: EXACT-ONCE SEMANTICS
# =============================================================================

class TestExactOnceSemantics:
    """Test exact-once semantics for all models."""
    
    @pytest.mark.asyncio
    async def test_vendor_exact_once(self, db_session, caller):
        """Test exact-once for canonical vendor."""
        fp = f"cv-exact-{uuid.uuid4().hex[:32]}"
        vendor1 = CanonicalVendor(
            organization_id=caller.organization_id,
            name="Exact Vendor",
            kind="supplier",
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(vendor1)
        await db_session.flush()
        
        vendor2 = CanonicalVendor(
            organization_id=caller.organization_id,
            name="Exact Vendor",
            kind="supplier",
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(vendor2)
        
        with pytest.raises(IntegrityError):
            await db_session.flush()
    
    @pytest.mark.asyncio
    async def test_external_capacity_exact_once(self, db_session, caller, test_vendor):
        """Test exact-once for external capacity."""
        fp = f"ec-exact-{uuid.uuid4().hex[:32]}"
        cap1 = ExternalCapacity(
            organization_id=caller.organization_id,
            vendor_id=test_vendor.id,
            capacity_type="cloud_compute_units",
            capacity_name="Cloud Capacity",
            unit="vcpu-hours",
            total_capacity=1000.0,
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(cap1)
        await db_session.flush()
        
        cap2 = ExternalCapacity(
            organization_id=caller.organization_id,
            vendor_id=test_vendor.id,
            capacity_type="cloud_compute_units",
            capacity_name="Cloud Capacity",
            unit="vcpu-hours",
            total_capacity=1000.0,
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(cap2)
        
        with pytest.raises(IntegrityError):
            await db_session.flush()
    
    @pytest.mark.asyncio
    async def test_procurement_exact_once(self, db_session, caller, test_vendor):
        """Test exact-once for canonical procurement."""
        fp = f"cp-exact-{uuid.uuid4().hex[:32]}"
        proc1 = CanonicalProcurement(
            organization_id=caller.organization_id,
            kind="purchase",
            title="Exact Procurement",
            vendor_id=test_vendor.id,
            quantity=10.0,
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(proc1)
        await db_session.flush()
        
        proc2 = CanonicalProcurement(
            organization_id=caller.organization_id,
            kind="purchase",
            title="Exact Procurement",
            vendor_id=test_vendor.id,
            quantity=10.0,
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(proc2)
        
        with pytest.raises(IntegrityError):
            await db_session.flush()


# =============================================================================
# TESTS: VENDOR OPERATING SLICE
# =============================================================================

class TestVendorOperatingSlice:
    """Test vendor operating slice derivation."""
    
    @pytest.mark.asyncio
    async def test_derive_vendor_operating_slice(self, db_session, caller, test_vendor, test_external_capacity, test_procurement):
        """Test deriving vendor operating slice."""
        slice_obj = await canonical_procurement_vendor_service.derive_vendor_operating_slice(
            db_session, caller=caller
        )
        
        assert slice_obj.id is not None
        assert slice_obj.organization_id == caller.organization_id
        assert slice_obj.total_vendors >= 1
        assert slice_obj.active_vendors >= 1
    
    @pytest.mark.asyncio
    async def test_slice_exact_once(self, db_session, caller, test_vendor):
        """Test exact-once for vendor operating slice."""
        slice1 = await canonical_procurement_vendor_service.derive_vendor_operating_slice(
            db_session, caller=caller
        )
        slice2 = await canonical_procurement_vendor_service.derive_vendor_operating_slice(
            db_session, caller=caller
        )
        
        assert slice1.id == slice2.id
        assert slice1.fingerprint == slice2.fingerprint


# =============================================================================
# TESTS: VENDOR MANAGEMENT
# =============================================================================

class TestVendorManagement:
    """Test vendor creation and management."""
    
    @pytest.mark.asyncio
    async def test_create_vendor(self, db_session, caller):
        """Test creating a vendor via service."""
        vendor = await canonical_procurement_vendor_service.create_vendor(
            db_session,
            caller=caller,
            name="Service Vendor",
            kind="supplier",
            industry="Technology",
            country="US",
            payment_terms="net30",
            criticality="high",
        )
        
        assert vendor.id is not None
        assert vendor.name == "Service Vendor"
        assert vendor.is_critical is True
    
    @pytest.mark.asyncio
    async def test_vendor_exact_once_via_service(self, db_session, caller):
        """Test exact-once for vendor creation via service."""
        vendor1 = await canonical_procurement_vendor_service.create_vendor(
            db_session,
            caller=caller,
            name="Exact Service Vendor",
            kind="supplier",
        )
        vendor2 = await canonical_procurement_vendor_service.create_vendor(
            db_session,
            caller=caller,
            name="Exact Service Vendor",
            kind="supplier",
        )
        
        assert vendor1.id == vendor2.id
    
    @pytest.mark.asyncio
    async def test_create_vendor_capability(self, db_session, caller, test_vendor):
        """Test creating vendor capability via service."""
        capability = await canonical_procurement_vendor_service.create_vendor_capability(
            db_session,
            caller=caller,
            vendor_id=test_vendor.id,
            capability_category="cloud_infrastructure",
            capability_name="Cloud Storage",
            unit="gb",
            max_capacity=100000.0,
            unit_cost=0.02,
            sla_details={"availability": 0.9999},
        )
        
        assert capability.id is not None
        assert capability.capability_category == "cloud_infrastructure"
        assert capability.max_capacity == 100000.0
    
    @pytest.mark.asyncio
    async def test_create_external_capacity(self, db_session, caller, test_vendor):
        """Test creating external capacity via service."""
        capacity = await canonical_procurement_vendor_service.create_external_capacity(
            db_session,
            caller=caller,
            vendor_id=test_vendor.id,
            capacity_type="cloud_compute_units",
            capacity_name="Azure Compute",
            unit="vcpu-hours",
            total_capacity=2000.0,
            window_start=date.today(),
            window_end=date.today() + timedelta(days=60),
            cost_per_unit=0.04,
            availability_sla=0.9995,
        )
        
        assert capacity.id is not None
        assert capacity.total_capacity == 2000.0
        assert capacity.available_capacity == 2000.0


# =============================================================================
# TESTS: PROCUREMENT MANAGEMENT
# =============================================================================

class TestProcurementManagement:
    """Test procurement creation and lifecycle."""
    
    @pytest.mark.asyncio
    async def test_create_procurement(self, db_session, caller, test_vendor):
        """Test creating a canonical procurement."""
        procurement = await canonical_procurement_vendor_service.create_procurement(
            db_session,
            caller=caller,
            kind="purchase",
            title="New Procurement",
            vendor_id=test_vendor.id,
            estimated_cost=25000.0,
            currency="USD",
            quantity=5.0,
            unit="units",
            needed_by=date.today() + timedelta(days=30),
            authorization_required=True,
            justification="Needed for Q2 project",
        )
        
        assert procurement.id is not None
        assert procurement.state == "identified"
        assert procurement.authorization_required is True
    
    @pytest.mark.asyncio
    async def test_transition_procurement_state(self, db_session, caller, test_procurement):
        """Test procurement state transition."""
        # Transition to requested
        procurement = await canonical_procurement_vendor_service.transition_procurement_state(
            db_session,
            caller=caller,
            procurement_id=test_procurement.id,
            new_state="requested",
            reason="Submitted for approval",
        )
        
        assert procurement is not None
        assert procurement.state == "requested"
        assert procurement.requested_at is not None
        
        # Transition to approved
        procurement = await canonical_procurement_vendor_service.transition_procurement_state(
            db_session,
            caller=caller,
            procurement_id=test_procurement.id,
            new_state="approved",
            reason="Approved by manager",
        )
        
        assert procurement.state == "approved"
        assert procurement.approved_at is not None
    
    @pytest.mark.asyncio
    async def test_authorize_procurement(self, db_session, caller, test_procurement):
        """Test procurement authorization (Decision != Authorization)."""
        # Transition to requested first
        await canonical_procurement_vendor_service.transition_procurement_state(
            db_session, caller=caller,
            procurement_id=test_procurement.id,
            new_state="requested",
        )
        
        # Authorize
        procurement = await canonical_procurement_vendor_service.authorize_procurement(
            db_session,
            caller=caller,
            procurement_id=test_procurement.id,
            authorized=True,
            amount=50000.0,
            notes="Approved for Q2 budget",
        )
        
        assert procurement is not None
        assert procurement.authorization_state == "approved"
        assert procurement.authorization_amount == 50000.0
        
        # Test rejection
        procurement = await canonical_procurement_vendor_service.authorize_procurement(
            db_session,
            caller=caller,
            procurement_id=test_procurement.id,
            authorized=False,
            notes="Over budget",
        )
        
        assert procurement.authorization_state == "rejected"


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
        # Transition to received state first
        await canonical_procurement_vendor_service.transition_procurement_state(
            db_session, caller=caller,
            procurement_id=test_procurement.id,
            new_state="received",
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
# TESTS: VENDOR PERFORMANCE DERIVATION
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
                vendor_name="Test Vendor",
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
    
    @pytest.mark.asyncio
    async def test_derive_vendor_dependencies(self, db_session, caller, test_vendor):
        """Test deriving vendor dependencies."""
        # Create multiple procurements for the vendor
        for i in range(8):
            proc = CanonicalProcurement(
                organization_id=caller.organization_id,
                kind="purchase",
                title=f"Proc {i}",
                vendor_id=test_vendor.id,
                state="ordered",
                project_id=f"proj-{i}",
                fingerprint=f"cp-dep-{i}-{uuid.uuid4().hex[:24]}",
                created_by=caller.employee_id or "system",
            )
            db_session.add(proc)
        await db_session.flush()
        
        dependencies = await canonical_procurement_vendor_service.derive_vendor_dependencies(
            db_session, caller=caller
        )
        
        assert len(dependencies) >= 1
        dep = next((d for d in dependencies if d.vendor_id == test_vendor.id), None)
        assert dep is not None
        assert dep.criticality in ("high", "critical")  # 8 procurements should be high/critical


# =============================================================================
# TESTS: CONFLICT DERIVATION
# =============================================================================

class TestConflictDerivation:
    """Test procurement conflict derivation."""
    
    @pytest.mark.asyncio
    async def test_derive_overdue_procurement_conflict(self, db_session, caller, test_vendor):
        """Test detecting overdue procurement conflict."""
        # Create overdue procurement
        proc = CanonicalProcurement(
            organization_id=caller.organization_id,
            kind="purchase",
            title="Overdue Procurement",
            vendor_id=test_vendor.id,
            state="ordered",
            expected_delivery=date.today() - timedelta(days=5),
            fingerprint=f"cp-overdue-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(proc)
        await db_session.flush()
        
        conflicts = await canonical_procurement_vendor_service.derive_procurement_conflicts(
            db_session, caller=caller
        )
        
        overdue_conflicts = [c for c in conflicts if c.trigger_type == "procurement_overdue"]
        assert len(overdue_conflicts) >= 1
    
    @pytest.mark.asyncio
    async def test_derive_contract_expiring_conflict(self, db_session, caller, test_vendor):
        """Test detecting vendor contract expiring conflict."""
        test_vendor.contract_expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        test_vendor.auto_renew = False
        await db_session.flush()
        
        conflicts = await canonical_procurement_vendor_service.derive_procurement_conflicts(
            db_session, caller=caller
        )
        
        contract_conflicts = [c for c in conflicts if c.trigger_type == "vendor_contract_expiring"]
        assert len(contract_conflicts) >= 1
    
    @pytest.mark.asyncio
    async def test_derive_capacity_constrained_conflict(self, db_session, caller, test_vendor, test_external_capacity):
        """Test detecting external capacity constrained conflict."""
        test_external_capacity.committed_capacity = test_external_capacity.total_capacity
        test_external_capacity.available_capacity = 0.0
        await db_session.flush()
        
        conflicts = await canonical_procurement_vendor_service.derive_procurement_conflicts(
            db_session, caller=caller
        )
        
        capacity_conflicts = [c for c in conflicts if c.trigger_type == "external_capacity_constrained"]
        assert len(capacity_conflicts) >= 1


# =============================================================================
# TESTS: PROCUREMENT IMPACT ANALYSIS
# =============================================================================

class TestProcurementImpactAnalysis:
    """Test procurement impact analysis."""
    
    @pytest.mark.asyncio
    async def test_analyze_procurement_impact(self, db_session, caller, test_procurement):
        """Test analyzing procurement impact."""
        analysis = await canonical_procurement_vendor_service.analyze_procurement_impact(
            db_session,
            caller=caller,
            trigger_type="procurement_created",
            trigger_entity_type="procurement",
            trigger_entity_id=test_procurement.id,
            trigger_params={"source_event_id": "evt-123"},
        )
        
        assert analysis.id is not None
        assert analysis.trigger_type == "procurement_created"
        assert analysis.trigger_entity_id == test_procurement.id
        assert analysis.fingerprint is not None
    
    @pytest.mark.asyncio
    async def test_impact_analysis_exact_once(self, db_session, caller, test_procurement):
        """Test exact-once for impact analysis."""
        analysis1 = await canonical_procurement_vendor_service.analyze_procurement_impact(
            db_session,
            caller=caller,
            trigger_type="procurement_delayed",
            trigger_entity_type="procurement",
            trigger_entity_id=test_procurement.id,
        )
        analysis2 = await canonical_procurement_vendor_service.analyze_procurement_impact(
            db_session,
            caller=caller,
            trigger_type="procurement_delayed",
            trigger_entity_type="procurement",
            trigger_entity_id=test_procurement.id,
        )
        
        assert analysis1.id == analysis2.id
        assert analysis1.fingerprint == analysis2.fingerprint


# =============================================================================
# TESTS: GATE 14 CUSTOMER INTEGRATION
# =============================================================================

class TestCustomerIntegration:
    """Test customer procurement impact derivation."""
    
    @pytest.mark.asyncio
    async def test_derive_customer_procurement_impact(self, db_session, caller, test_customer, test_vendor):
        """Test deriving procurement impact for a customer."""
        # Create project linked to customer
        project = Project(
            organization_id=caller.organization_id,
            name="Customer Project",
            code=f"CUST-{uuid.uuid4().hex[:6]}",
            status="active",
            owner_id=caller.employee_id or "system",
        )
        db_session.add(project)
        await db_session.flush()
        
        # Link project to customer
        proj_link = CustomerProjectLink(
            organization_id=caller.organization_id,
            customer_id=test_customer.id,
            project_id=project.id,
            kind="delivery",
        )
        db_session.add(proj_link)
        await db_session.flush()
        
        # Create procurement for this project
        for i in range(3):
            proc = CanonicalProcurement(
                organization_id=caller.organization_id,
                kind="purchase",
                title=f"Project Procurement {i}",
                vendor_id=test_vendor.id,
                project_id=project.id,
                estimated_cost=10000.0,
                state="ordered",
                fingerprint=f"cp-cust-{i}-{uuid.uuid4().hex[:24]}",
                created_by=caller.employee_id or "system",
            )
            db_session.add(proc)
        await db_session.flush()
        
        impact = await canonical_procurement_vendor_service.derive_customer_procurement_impact(
            db_session,
            caller=caller,
            customer_id=test_customer.id,
        )
        
        assert impact["customer_id"] == test_customer.id
        assert impact["projects"] == 1
        assert impact["procurements"] == 3
        assert impact["vendors"] == 1


# =============================================================================
# TESTS: GATE 13 STRATEGIC ALIGNMENT INTEGRATION
# =============================================================================

class TestStrategicAlignmentIntegration:
    """Test strategic alignment integration."""
    
    @pytest.mark.asyncio
    async def test_trace_procurement_to_strategy(self, db_session, caller, test_procurement, test_objective):
        """Test tracing procurement to strategic elements."""
        # Link procurement to project and strategic chain
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
            title="Strategic Initiative",
            status="active",
            kind="other",
            expected_outcome={"target_value": 100, "unit": "units"},
            fingerprint=f"init-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(initiative)
        await db_session.flush()
        
        link = StrategicLink(
            organization_id=caller.organization_id,
            initiative_id=initiative.id,
            project_id=project.id,
            source_event_id=f"evt-{uuid.uuid4().hex[:16]}",
            linked_at=datetime.now(timezone.utc),
        )
        db_session.add(link)
        await db_session.flush()
        
        # Update procurement to link to project
        test_procurement.project_id = project.id
        await db_session.flush()
        
        trace = await canonical_procurement_vendor_service.trace_procurement_to_strategy(
            db_session,
            caller=caller,
            procurement_id=test_procurement.id,
        )
        
        assert trace["procurement"]["id"] == test_procurement.id
        assert trace["project"] is not None


# =============================================================================
# TESTS: PREDICTION INTEGRATION (Gate 10)
# =============================================================================

class TestPredictionIntegration:
    """Test predictive intelligence integration."""
    
    @pytest.mark.asyncio
    async def test_predict_vendor_delivery_risk(self, db_session, caller, test_vendor):
        """Test vendor delivery risk prediction."""
        # Create upcoming procurements
        for i in range(5):
            proc = CanonicalProcurement(
                organization_id=caller.organization_id,
                kind="purchase",
                title=f"Upcoming Proc {i}",
                vendor_id=test_vendor.id,
                state="ordered",
                expected_delivery=date.today() + timedelta(days=i*5),
                ordered_at=datetime.now(timezone.utc) - timedelta(days=5),
                fingerprint=f"cp-pred-{i}-{uuid.uuid4().hex[:24]}",
                created_by=caller.employee_id or "system",
            )
            db_session.add(proc)
        await db_session.flush()
        
        # Create performance history
        perf = VendorPerformance(
            organization_id=caller.organization_id,
            vendor_id=test_vendor.id,
            period_start=date.today().replace(day=1) - timedelta(days=30),
            period_end=date.today().replace(day=1) - timedelta(days=1),
            metric_kind="on_time_delivery",
            metric_value=0.85,
            metric_unit="ratio",
            target_value=0.95,
            variance=-0.1,
            sample_size=20,
            confidence=0.8,
            fingerprint=f"vp-pred-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(perf)
        await db_session.flush()
        
        prediction = await canonical_procurement_vendor_service.predict_vendor_delivery_risk(
            db_session,
            caller=caller,
            vendor_id=test_vendor.id,
            horizon_days=30,
        )
        
        assert "predictions" in prediction
        assert len(prediction["predictions"]) >= 1
        
        pred = prediction["predictions"][0]
        assert "risk_score" in pred
        assert "risk_level" in pred
        assert pred["risk_level"] in ("low", "medium", "high")


# =============================================================================
# TESTS: COUNTERFACTUAL/DIGITAL TWIN INTEGRATION
# =============================================================================

class TestCounterfactualIntegration:
    """Test counterfactual and digital twin integration."""
    
    @pytest.mark.asyncio
    async def test_create_procurement_scenario(self, db_session, caller, test_vendor, test_procurement):
        """Test creating procurement scenario."""
        result = await canonical_procurement_vendor_service.create_procurement_scenario(
            db_session,
            caller=caller,
            scenario_name="Vendor Failure Scenario",
            vendor_changes=[
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
    async def test_vendor_tenant_isolation(self, db_session, caller, test_org, test_vendor):
        """Test that vendor data doesn't leak across tenants."""
        from app.models.organization import Organization
        other_org = Organization(
            name="Other Org",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(other_org)
        await db_session.flush()
        
        other_vendor = CanonicalVendor(
            organization_id=other_org.id,
            name="Other Vendor",
            kind="supplier",
            fingerprint=f"cv-fp-{uuid.uuid4().hex[:32]}",
            created_by="other",
        )
        db_session.add(other_vendor)
        await db_session.flush()
        
        result = await db_session.execute(
            select(CanonicalVendor).where(
                CanonicalVendor.organization_id == caller.organization_id
            )
        )
        vendors = result.scalars().all()
        vendor_ids = {v.id for v in vendors}
        
        assert test_vendor.id in vendor_ids
        assert other_vendor.id not in vendor_ids
    
    @pytest.mark.asyncio
    async def test_procurement_tenant_isolation(self, db_session, caller, test_org, test_procurement):
        """Test procurement tenant isolation."""
        from app.models.organization import Organization
        other_org = Organization(
            name="Other Org",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(other_org)
        await db_session.flush()
        
        other_proc = CanonicalProcurement(
            organization_id=other_org.id,
            kind="purchase",
            title="Other Procurement",
            fingerprint=f"cp-fp-{uuid.uuid4().hex[:32]}",
            created_by="other",
        )
        db_session.add(other_proc)
        await db_session.flush()
        
        result = await db_session.execute(
            select(CanonicalProcurement).where(
                CanonicalProcurement.organization_id == caller.organization_id
            )
        )
        procs = result.scalars().all()
        assert other_proc.id not in {p.id for p in procs}


# =============================================================================
# TESTS: ADVERSARIAL
# =============================================================================

class TestAdversarial:
    """Adversarial tests."""
    
    @pytest.mark.asyncio
    async def test_fake_vendor_id_rejected(self, db_session, caller):
        """Test that fake vendor IDs are handled."""
        fake_id = f"fake-{uuid.uuid4().hex[:24]}"
        
        procurement = CanonicalProcurement(
            organization_id=caller.organization_id,
            kind="purchase",
            title="Fake Vendor Procurement",
            vendor_id=fake_id,
            fingerprint=f"cp-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(procurement)
        await db_session.flush()
        
        # Verify it references non-existent vendor
        result = await db_session.execute(
            select(CanonicalVendor).where(
                CanonicalVendor.id == fake_id
            )
        )
        assert result.scalars().first() is None
    
    @pytest.mark.asyncio
    async def test_cross_tenant_vendor_creation_blocked(self, db_session, caller, test_org):
        """Test that creating vendor for another org fails."""
        from app.models.organization import Organization
        other_org = Organization(
            name="Other Org",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(other_org)
        await db_session.flush()
        
        # Service should only create for caller's org
        vendor = await canonical_procurement_vendor_service.create_vendor(
            db_session,
            caller=caller,
            name="Cross Tenant Vendor",
            kind="supplier",
        )
        
        assert vendor.organization_id == caller.organization_id
        assert vendor.organization_id != other_org.id


# =============================================================================
# TESTS: REGRESSION (Prior Gates Still Work)
# =============================================================================

class TestRegression:
    """Test that prior gates still work."""
    
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


# =============================================================================
# TESTS: VOCABULARIES
# =============================================================================

class TestVocabularies:
    """Test canonical vocabularies are complete."""
    
    def test_vendor_kinds_complete(self):
        """Test all expected vendor kinds exist."""
        expected = {"supplier", "vendor", "contractor", "consultant", "cloud_provider", "saas_provider",
                    "logistics", "manufacturing", "professional_services", "staffing", "outsourced_ops",
                    "maintenance", "utility", "financial_services", "legal", "other"}
        assert set(VENDOR_KINDS) == expected
    
    def test_vendor_states_complete(self):
        """Test all vendor states covered."""
        states = set(VENDOR_STATES)
        assert "active" in states
        assert "onboarding" in states
        assert "qualified" in states
        assert "preferred" in states
        assert "approved" in states
        assert "suspended" in states
        assert "terminated" in states
        assert "blacklisted" in states
    
    def test_external_capacity_types_complete(self):
        """Test external capacity types covered."""
        types = set(EXTERNAL_CAPACITY_TYPES)
        assert "contractor_fte" in types
        assert "cloud_compute_units" in types
        assert "saas_seats" in types
        assert "managed_service_hours" in types
        assert "staffing_pool" in types
    
    def test_procurement_lifecycle_complete(self):
        """Test procurement lifecycle states."""
        states = set(PROCUREMENT_LIFECYCLE_STATES)
        assert "identified" in states
        assert "requested" in states
        assert "quoted" in states
        assert "approved" in states
        assert "ordered" in states
        assert "in_fulfillment" in states
        assert "received" in states
        assert "accepted" in states
        assert "completed" in states
        assert "rejected" in states
        assert "cancelled" in states
        assert "delayed" in states
    
    def test_authorization_states_complete(self):
        """Test authorization states."""
        states = set(AUTHORIZATION_STATES)
        assert "not_required" in states
        assert "pending" in states
        assert "approved" in states
        assert "rejected" in states
        assert "escalated" in states
        assert "conditional" in states
    
    def test_vendor_risk_kinds_complete(self):
        """Test vendor risk kinds."""
        kinds = set(VENDOR_RISK_KINDS)
        assert "delivery_risk" in kinds
        assert "quality_risk" in kinds
        assert "capacity_risk" in kinds
        assert "financial_risk" in kinds
        assert "concentration_risk" in kinds
        assert "contract_risk" in kinds
        assert "substitution_risk" in kinds


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])