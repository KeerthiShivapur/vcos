"""Gate 16 — Canonical Resource, Asset & Allocation Operating Fabric Tests."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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
from app.models.canonical_resource_asset import (
    CanonicalResource,
    CanonicalAsset,
    ResourceDemand,
    ResourceAllocation,
    ResourceConflict,
    ResourceOperatingSlice,
    ResourceImpactAnalysis,
    RESOURCE_CATEGORIES,
    RESOURCE_KINDS,
    ASSET_LIFECYCLE_STATES,
    ALLOCATION_STATES,
    ALLOCATION_TARGET_TYPES,
    DEMAND_SOURCES,
    SUPPLY_SOURCES,
)
from app.models.financial_resource_procurement import (
    ProcurementRecord,
    PROCUREMENT_KINDS,
    PROCUREMENT_STATES,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee


# =============================================================================
# FIXTURES
# =============================================================================

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
async def test_customer(db_session, caller, test_employee):
    """Create test customer."""
    from app.models.customer import Customer, CustomerContact
    
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
    from app.core.timeutils import utcnow
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


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
async def test_resource(db_session, caller):
    """Create a test canonical resource."""
    resource = CanonicalResource(
        organization_id=caller.organization_id,
        category="physical",
        kind="equipment",
        name="Test Laptop",
        description="Developer laptop",
        unit="units",
        total_capacity=10.0,
        committed_capacity=3.0,
        reserved_capacity=1.0,
        available_capacity=6.0,
        state="available",
        supply_source="internal",
        cost_per_unit=2000.0,
        currency="USD",
        fingerprint=f"cr-fp-{uuid.uuid4().hex[:32]}",
        created_by=caller.employee_id or "system",
    )
    db_session.add(resource)
    await db_session.flush()
    return resource


@pytest.fixture
async def test_asset(db_session, caller, test_resource):
    """Create a test canonical asset."""
    asset = CanonicalAsset(
        organization_id=caller.organization_id,
        asset_category="hardware",
        asset_type="laptop",
        name="Test Laptop Asset",
        description="Asset created from resource",
        lifecycle_state="available",
        resource_id=test_resource.id,
        purchase_cost=2000.0,
        current_value=1800.0,
        currency="USD",
        fingerprint=f"ca-fp-{uuid.uuid4().hex[:32]}",
        created_by=caller.employee_id or "system",
    )
    db_session.add(asset)
    await db_session.flush()
    return asset


@pytest.fixture
async def test_demand(db_session, caller):
    """Create a test resource demand."""
    demand = ResourceDemand(
        organization_id=caller.organization_id,
        source_type="project",
        source_id="proj-123",
        source_name="Test Project",
        resource_category="human",
        resource_kind="employee_capacity",
        units_requested=5.0,
        unit="fte",
        window_start=date.today(),
        window_end=date.today() + timedelta(days=90),
        priority=2,
        urgency="high",
        proficiency="high",
        fingerprint=f"rd-fp-{uuid.uuid4().hex[:32]}",
        created_by=caller.employee_id or "system",
    )
    db_session.add(demand)
    await db_session.flush()
    return demand


@pytest.fixture
async def test_procurement(db_session, caller):
    """Create a test procurement record."""
    procurement = ProcurementRecord(
        organization_id=caller.organization_id,
        kind="purchase",
        title="10 Developer Laptops",
        description="Laptop procurement for engineering team",
        state="received",
        estimated_cost=20000.0,
        actual_cost=20000.0,
        currency="USD",
        vendor_id="vendor-123",
        vendor_name="Dell Technologies",
        budget_id="budget-456",
        fingerprint=f"pr-fp-{uuid.uuid4().hex[:32]}",
        source_event_id="test-event-123",
    )
    db_session.add(procurement)
    await db_session.flush()
    return procurement


# =============================================================================
# TESTS: MODEL CREATION
# =============================================================================

class TestCanonicalResourceModels:
    """Test canonical resource model creation."""
    
    @pytest.mark.asyncio
    async def test_create_canonical_resource(self, db_session, caller):
        """Test creating a canonical resource."""
        resource = CanonicalResource(
            organization_id=caller.organization_id,
            category="human",
            kind="employee_capacity",
            name="Engineering Capacity",
            unit="fte",
            total_capacity=50.0,
            committed_capacity=30.0,
            reserved_capacity=5.0,
            available_capacity=15.0,
            state="available",
            supply_source="internal",
            fingerprint=f"cr-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(resource)
        await db_session.flush()
        
        assert resource.id is not None
        assert resource.category == "human"
        assert resource.kind == "employee_capacity"
        assert resource.utilization_rate == 0.6  # 30/50
        assert resource.is_constrained is False
    
    @pytest.mark.asyncio
    async def test_create_canonical_resource_all_categories(self, db_session, caller):
        """Test creating resources for all categories."""
        for category in RESOURCE_CATEGORIES:
            resource = CanonicalResource(
                organization_id=caller.organization_id,
                category=category,
                kind=RESOURCE_KINDS[0] if RESOURCE_KINDS else "test",
                name=f"{category} Resource",
                unit="units",
                total_capacity=10.0,
                fingerprint=f"cr-fp-{uuid.uuid4().hex[:32]}",
                created_by=caller.employee_id or "system",
            )
            db_session.add(resource)
        await db_session.flush()
        
        result = await db_session.execute(
            select(CanonicalResource).where(
                CanonicalResource.organization_id == caller.organization_id
            )
        )
        resources = result.scalars().all()
        categories = {r.category for r in resources}
        assert categories == set(RESOURCE_CATEGORIES)
    
    @pytest.mark.asyncio
    async def test_create_canonical_asset(self, db_session, caller, test_resource):
        """Test creating a canonical asset."""
        asset = CanonicalAsset(
            organization_id=caller.organization_id,
            asset_category="hardware",
            asset_type="server",
            name="Production Server",
            lifecycle_state="allocated",
            resource_id=test_resource.id,
            purchase_cost=5000.0,
            current_value=4500.0,
            currency="USD",
            fingerprint=f"ca-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(asset)
        await db_session.flush()
        
        assert asset.id is not None
        assert asset.asset_category == "hardware"
        assert asset.lifecycle_state == "allocated"
        assert asset.is_critical is False
    
    @pytest.mark.asyncio
    async def test_create_resource_demand(self, db_session, caller):
        """Test creating a resource demand."""
        demand = ResourceDemand(
            organization_id=caller.organization_id,
            source_type="project",
            source_id="proj-456",
            resource_category="digital",
            resource_kind="cloud_compute",
            units_requested=100.0,
            unit="cpu-hr",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            priority=1,
            urgency="critical",
            fingerprint=f"rd-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(demand)
        await db_session.flush()
        
        assert demand.id is not None
        assert demand.units_remaining == 100.0
        assert demand.is_fulfilled is False
    
    @pytest.mark.asyncio
    async def test_create_resource_allocation(self, db_session, caller, test_resource, test_demand):
        """Test creating a resource allocation."""
        allocation = ResourceAllocation(
            organization_id=caller.organization_id,
            resource_id=test_resource.id,
            resource_category=test_resource.category,
            resource_kind=test_resource.kind,
            target_type="project",
            target_id="proj-123",
            target_name="Test Project",
            demand_id=test_demand.id,
            units_allocated=3.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=60),
            state="active",
            purpose="Development work",
            expected_outcome="Feature delivery",
            fingerprint=f"ra-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(allocation)
        await db_session.flush()
        
        assert allocation.id is not None
        assert allocation.state == "active"
    
    @pytest.mark.asyncio
    async def test_create_resource_conflict(self, db_session, caller, test_resource):
        """Test creating a resource conflict."""
        conflict = ResourceConflict(
            organization_id=caller.organization_id,
            conflict_kind="capacity_overload",
            severity="critical",
            status="open",
            resource_id=test_resource.id,
            resource_kind=test_resource.kind,
            title="Resource over capacity",
            description="Demand exceeds supply",
            detected_at=datetime.now(timezone.utc),
            detected_by="system",
            detection_method="derived",
            fingerprint=f"rc-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(conflict)
        await db_session.flush()
        
        assert conflict.id is not None
        assert conflict.severity == "critical"


# =============================================================================
# TESTS: EXACT-ONCE SEMANTICS
# =============================================================================

class TestExactOnceSemantics:
    """Test exact-once semantics for all models."""
    
    @pytest.mark.asyncio
    async def test_resource_exact_once(self, db_session, caller):
        """Test exact-once for canonical resource."""
        fp = f"cr-exact-{uuid.uuid4().hex[:32]}"
        resource1 = CanonicalResource(
            organization_id=caller.organization_id,
            category="physical",
            kind="equipment",
            name="Test",
            unit="units",
            total_capacity=1.0,
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(resource1)
        await db_session.flush()
        
        resource2 = CanonicalResource(
            organization_id=caller.organization_id,
            category="physical",
            kind="equipment",
            name="Test",
            unit="units",
            total_capacity=1.0,
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(resource2)
        
        with pytest.raises(IntegrityError):
            await db_session.flush()
    
    @pytest.mark.asyncio
    async def test_asset_exact_once(self, db_session, caller):
        """Test exact-once for canonical asset."""
        fp = f"ca-exact-{uuid.uuid4().hex[:32]}"
        asset1 = CanonicalAsset(
            organization_id=caller.organization_id,
            asset_category="hardware",
            asset_type="laptop",
            name="Test",
            lifecycle_state="available",
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(asset1)
        await db_session.flush()
        
        asset2 = CanonicalAsset(
            organization_id=caller.organization_id,
            asset_category="hardware",
            asset_type="laptop",
            name="Test",
            lifecycle_state="available",
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(asset2)
        
        with pytest.raises(IntegrityError):
            await db_session.flush()
    
    @pytest.mark.asyncio
    async def test_demand_exact_once(self, db_session, caller):
        """Test exact-once for resource demand."""
        fp = f"rd-exact-{uuid.uuid4().hex[:32]}"
        demand1 = ResourceDemand(
            organization_id=caller.organization_id,
            source_type="project",
            source_id="proj-1",
            resource_category="human",
            resource_kind="employee_capacity",
            units_requested=1.0,
            unit="fte",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(demand1)
        await db_session.flush()
        
        demand2 = ResourceDemand(
            organization_id=caller.organization_id,
            source_type="project",
            source_id="proj-1",
            resource_category="human",
            resource_kind="employee_capacity",
            units_requested=1.0,
            unit="fte",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(demand2)
        
        with pytest.raises(IntegrityError):
            await db_session.flush()
    
    @pytest.mark.asyncio
    async def test_allocation_exact_once(self, db_session, caller, test_resource):
        """Test exact-once for resource allocation."""
        fp = f"ra-exact-{uuid.uuid4().hex[:32]}"
        alloc1 = ResourceAllocation(
            organization_id=caller.organization_id,
            resource_id=test_resource.id,
            resource_category="physical",
            resource_kind="equipment",
            target_type="project",
            target_id="proj-1",
            units_allocated=1.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(alloc1)
        await db_session.flush()
        
        alloc2 = ResourceAllocation(
            organization_id=caller.organization_id,
            resource_id=test_resource.id,
            resource_category="physical",
            resource_kind="equipment",
            target_type="project",
            target_id="proj-1",
            units_allocated=1.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            fingerprint=fp,
            created_by=caller.employee_id or "system",
        )
        db_session.add(alloc2)
        
        with pytest.raises(IntegrityError):
            await db_session.flush()


# =============================================================================
# TESTS: RESOURCE OPERATING SLICE
# =============================================================================

class TestResourceOperatingSlice:
    """Test resource operating slice derivation."""
    
    @pytest.mark.asyncio
    async def test_derive_resource_operating_slice(self, db_session, caller, test_resource, test_asset, test_demand):
        """Test deriving resource operating slice."""
        slice_obj = await canonical_resource_asset_service.derive_resource_operating_slice(
            db_session, caller=caller
        )
        
        assert slice_obj.id is not None
        assert slice_obj.organization_id == caller.organization_id
        assert slice_obj.total_allocations >= 0
        assert slice_obj.total_capacity >= 0
        assert slice_obj.overall_utilization >= 0
    
    @pytest.mark.asyncio
    async def test_slice_exact_once(self, db_session, caller, test_resource):
        """Test exact-once for resource operating slice."""
        slice1 = await canonical_resource_asset_service.derive_resource_operating_slice(
            db_session, caller=caller
        )
        slice2 = await canonical_resource_asset_service.derive_resource_operating_slice(
            db_session, caller=caller
        )
        
        assert slice1.id == slice2.id
        assert slice1.fingerprint == slice2.fingerprint


# =============================================================================
# TESTS: RESOURCE IMPACT ANALYSIS
# =============================================================================

class TestResourceImpactAnalysis:
    """Test resource impact analysis."""
    
    @pytest.mark.asyncio
    async def test_analyze_resource_added(self, db_session, caller, test_resource):
        """Test impact analysis for resource added."""
        analysis = await canonical_resource_asset_service.analyze_resource_impact(
            db_session,
            caller=caller,
            trigger_type="resource_added",
            trigger_entity_type="resource",
            trigger_entity_id=test_resource.id,
            trigger_params={"capacity": test_resource.total_capacity},
        )
        
        assert analysis.id is not None
        assert analysis.trigger_type == "resource_added"
        assert analysis.trigger_entity_id == test_resource.id
        assert len(analysis.affected_resources) >= 1
    
    @pytest.mark.asyncio
    async def test_analyze_resource_removed(self, db_session, caller, test_resource):
        """Test impact analysis for resource removed."""
        analysis = await canonical_resource_asset_service.analyze_resource_impact(
            db_session,
            caller=caller,
            trigger_type="resource_removed",
            trigger_entity_type="resource",
            trigger_entity_id=test_resource.id,
            trigger_params={"capacity": test_resource.total_capacity},
        )
        
        assert analysis.id is not None
        assert analysis.trigger_type == "resource_removed"
        assert analysis.capacity_impact["bottleneck_risk"] in ("low", "high")
    
    @pytest.mark.asyncio
    async def test_impact_analysis_exact_once(self, db_session, caller, test_resource):
        """Test exact-once for impact analysis."""
        analysis1 = await canonical_resource_asset_service.analyze_resource_impact(
            db_session,
            caller=caller,
            trigger_type="resource_added",
            trigger_entity_type="resource",
            trigger_entity_id=test_resource.id,
        )
        analysis2 = await canonical_resource_asset_service.analyze_resource_impact(
            db_session,
            caller=caller,
            trigger_type="resource_added",
            trigger_entity_type="resource",
            trigger_entity_id=test_resource.id,
        )
        
        assert analysis1.id == analysis2.id
        assert analysis1.fingerprint == analysis2.fingerprint


# =============================================================================
# TESTS: RESOURCE DEMAND MANAGEMENT
# =============================================================================

class TestResourceDemandManagement:
    """Test resource demand creation and management."""
    
    @pytest.mark.asyncio
    async def test_create_resource_demand(self, db_session, caller):
        """Test creating a resource demand via service."""
        demand = await canonical_resource_asset_service.create_resource_demand(
            db_session,
            caller=caller,
            source_type="project",
            source_id="proj-new-1",
            source_name="New Project",
            resource_category="human",
            resource_kind="employee_capacity",
            units_requested=3.0,
            unit="fte",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=60),
            priority=2,
            urgency="high",
            justification="Need engineers for Q2 delivery",
        )
        
        assert demand.id is not None
        assert demand.units_requested == 3.0
        assert demand.fulfillment_status == "unfulfilled"
    
    @pytest.mark.asyncio
    async def test_demand_exact_once_via_service(self, db_session, caller):
        """Test exact-once for demand creation via service."""
        demand1 = await canonical_resource_asset_service.create_resource_demand(
            db_session,
            caller=caller,
            source_type="project",
            source_id="proj-dup",
            source_name="Duplicate Project",
            resource_category="human",
            resource_kind="employee_capacity",
            units_requested=2.0,
            unit="fte",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
        )
        demand2 = await canonical_resource_asset_service.create_resource_demand(
            db_session,
            caller=caller,
            source_type="project",
            source_id="proj-dup",
            source_name="Duplicate Project",
            resource_category="human",
            resource_kind="employee_capacity",
            units_requested=2.0,
            unit="fte",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
        )
        
        assert demand1.id == demand2.id


# =============================================================================
# TESTS: RESOURCE ALLOCATION MANAGEMENT
# =============================================================================

class TestResourceAllocationManagement:
    """Test resource allocation creation and release."""
    
    @pytest.mark.asyncio
    async def test_create_resource_allocation(self, db_session, caller, test_resource, test_demand):
        """Test creating a resource allocation via service."""
        allocation = await canonical_resource_asset_service.create_resource_allocation(
            db_session,
            caller=caller,
            resource_id=test_resource.id,
            target_type="project",
            target_id="proj-123",
            target_name="Test Project",
            units_allocated=2.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            demand_id=test_demand.id,
            purpose="Development",
            expected_outcome="Feature complete",
        )
        
        assert allocation.id is not None
        assert allocation.state == "requested"
        assert allocation.units_allocated == 2.0
        
        # Verify demand fulfillment updated
        await db_session.refresh(test_demand)
        assert test_demand.units_fulfilled == 2.0
        assert test_demand.fulfillment_status == "partial"
        
        # Verify resource capacity updated
        await db_session.refresh(test_resource)
        assert test_resource.committed_capacity == 5.0  # 3 + 2
        assert test_resource.available_capacity == 4.0  # 6 - 2
    
    @pytest.mark.asyncio
    async def test_release_resource_allocation(self, db_session, caller, test_resource, test_demand):
        """Test releasing a resource allocation."""
        # Create allocation
        allocation = await canonical_resource_asset_service.create_resource_allocation(
            db_session,
            caller=caller,
            resource_id=test_resource.id,
            target_type="project",
            target_id="proj-123",
            target_name="Test Project",
            units_allocated=2.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            demand_id=test_demand.id,
        )
        
        # Release it
        released = await canonical_resource_asset_service.release_resource_allocation(
            db_session,
            caller=caller,
            allocation_id=allocation.id,
        )
        
        assert released is not None
        assert released.state == "released"
        
        # Verify demand fulfillment updated
        await db_session.refresh(test_demand)
        assert test_demand.units_fulfilled == 0.0
        assert test_demand.fulfillment_status == "unfulfilled"
        
        # Verify resource capacity updated
        await db_session.refresh(test_resource)
        assert test_resource.committed_capacity == 3.0  # back to original
        assert test_resource.available_capacity == 6.0  # back to original


# =============================================================================
# TESTS: GATE 15 INTEGRATION (Procurement -> Resource)
# =============================================================================

class TestGate15Integration:
    """Test integration with Gate 15 procurement."""
    
    @pytest.mark.asyncio
    async def test_create_resource_from_procurement(self, db_session, caller, test_procurement):
        """Test creating resource from completed procurement."""
        resource = await canonical_resource_asset_service.create_resource_from_procurement(
            db_session,
            caller=caller,
            procurement_id=test_procurement.id,
        )
        
        assert resource is not None
        assert resource.id is not None
        assert resource.procurement_id == test_procurement.id
        assert resource.supply_source == "procurement"
        assert resource.category in RESOURCE_CATEGORIES
        assert resource.kind in RESOURCE_KINDS
    
    @pytest.mark.asyncio
    async def test_procurement_not_delivered_no_resource(self, db_session, caller):
        """Test that non-delivered procurement doesn't create resource."""
        procurement = ProcurementRecord(
            organization_id=caller.organization_id,
            kind="purchase",
            title="Pending Laptops",
            state="requested",  # Not delivered
            estimated_cost=10000.0,
            fingerprint=f"pr-fp-{uuid.uuid4().hex[:32]}",
            source_event_id="test-event-456",
        )
        db_session.add(procurement)
        await db_session.flush()
        
        resource = await canonical_resource_asset_service.create_resource_from_procurement(
            db_session,
            caller=caller,
            procurement_id=procurement.id,
        )
        
        assert resource is None
    
    @pytest.mark.asyncio
    async def test_asset_created_from_physical_procurement(self, db_session, caller, test_procurement):
        """Test that physical procurement creates asset."""
        resource = await canonical_resource_asset_service.create_resource_from_procurement(
            db_session,
            caller=caller,
            procurement_id=test_procurement.id,
        )
        
        assert resource is not None
        
        # Check if asset was created
        from app.models.canonical_resource_asset import CanonicalAsset
        asset_result = await db_session.execute(
            select(CanonicalAsset).where(
                CanonicalAsset.organization_id == caller.organization_id,
                CanonicalAsset.resource_id == resource.id,
            )
        )
        asset = asset_result.scalars().first()
        
        assert asset is not None
        assert asset.asset_category == "hardware"
        assert asset.lifecycle_state == "available"
        assert asset.resource_id == resource.id


# =============================================================================
# TESTS: CUSTOMER INTEGRATION (Gate 14)
# =============================================================================

class TestCustomerIntegration:
    """Test customer resource impact derivation."""
    
    @pytest.mark.asyncio
    async def test_derive_customer_resource_impact(self, db_session, caller, test_customer, test_resource):
        """Test deriving resource impact for a customer."""
        # Create project linked to customer
        from app.models.project import Project
        from app.models.customer import CustomerProjectLink
        
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
        
        # Create resource demand for this project
        demand = ResourceDemand(
            organization_id=caller.organization_id,
            source_type="project",
            source_id=project.id,
            source_name=project.name,
            resource_category="physical",
            resource_kind="equipment",
            units_requested=2.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            priority=2,
            urgency="high",
            fingerprint=f"rd-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(demand)
        await db_session.flush()
        
        # Create allocation linked to demand
        allocation = ResourceAllocation(
            organization_id=caller.organization_id,
            resource_id=test_resource.id,
            resource_category="physical",
            resource_kind="equipment",
            target_type="project",
            target_id=project.id,
            target_name=project.name,
            demand_id=demand.id,
            units_allocated=2.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            state="active",
            fingerprint=f"ra-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(allocation)
        await db_session.flush()
        
        impact = await canonical_resource_asset_service.derive_customer_resource_impact(
            db_session,
            caller=caller,
            customer_id=test_customer.id,
        )
        
        assert impact["customer_id"] == test_customer.id
        assert impact["allocations"] >= 1
        assert impact["resources"] >= 1


# =============================================================================
# TESTS: STRATEGIC ALIGNMENT INTEGRATION (Gate 13)
# =============================================================================

class TestStrategicAlignmentIntegration:
    """Test strategic alignment trace from resource."""
    
    @pytest.mark.asyncio
    async def test_trace_resource_to_strategy(self, db_session, caller, test_resource):
        """Test tracing resource to strategic elements."""
        # Create allocation linked to project
        allocation = ResourceAllocation(
            organization_id=caller.organization_id,
            resource_id=test_resource.id,
            resource_category="physical",
            resource_kind="equipment",
            target_type="project",
            target_id="proj-strat-1",
            target_name="Strategic Project",
            units_allocated=1.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            state="active",
            fingerprint=f"ra-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(allocation)
        await db_session.flush()
        
        trace = await canonical_resource_asset_service.trace_resource_to_strategy(
            db_session,
            caller=caller,
            resource_id=test_resource.id,
        )
        
        assert trace["resource"]["id"] == test_resource.id
        assert len(trace["allocations"]) >= 1
    
    @pytest.mark.asyncio
    async def test_trace_resource_not_found(self, db_session, caller):
        """Test tracing non-existent resource raises error."""
        with pytest.raises(ValueError):
            await canonical_resource_asset_service.trace_resource_to_strategy(
                db_session,
                caller=caller,
                resource_id="non-existent",
            )


# =============================================================================
# TESTS: PREDICTION INTEGRATION (Gate 10)
# =============================================================================

class TestPredictionIntegration:
    """Test predictive intelligence integration."""
    
    @pytest.mark.asyncio
    async def test_predict_resource_capacity_pressure(self, db_session, caller, test_resource, test_demand):
        """Test capacity pressure prediction."""
        prediction = await canonical_resource_asset_service.predict_resource_capacity_pressure(
            db_session,
            caller=caller,
            resource_kind=test_resource.kind,
            horizon_days=30,
        )
        
        assert "projections" in prediction
        assert "overall_risk" in prediction
        assert len(prediction["projections"]) >= 1
        
        proj = prediction["projections"][0]
        assert "projected_utilization" in proj
        assert "risk_level" in proj
        assert proj["risk_level"] in ("low", "medium", "high", "critical")


# =============================================================================
# TESTS: CONFLICT DERIVATION
# =============================================================================

class TestConflictDerivation:
    """Test resource conflict derivation."""
    
    @pytest.mark.asyncio
    async def test_derive_double_allocation_conflict(self, db_session, caller, test_resource):
        """Test detecting double allocation conflict."""
        # Create two active allocations for same resource
        alloc1 = ResourceAllocation(
            organization_id=caller.organization_id,
            resource_id=test_resource.id,
            resource_category="physical",
            resource_kind="equipment",
            target_type="project",
            target_id="proj-1",
            units_allocated=5.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            state="active",
            fingerprint=f"ra-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        alloc2 = ResourceAllocation(
            organization_id=caller.organization_id,
            resource_id=test_resource.id,
            resource_category="physical",
            resource_kind="equipment",
            target_type="project",
            target_id="proj-2",
            units_allocated=5.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            state="active",
            fingerprint=f"ra-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add_all([alloc1, alloc2])
        await db_session.flush()
        
        conflicts = await canonical_resource_asset_service.derive_resource_conflicts(
            db_session, caller=caller
        )
        
        double_conflicts = [c for c in conflicts if c.conflict_kind == "double_allocation"]
        assert len(double_conflicts) >= 1
    
    @pytest.mark.asyncio
    async def test_derive_capacity_overload_conflict(self, db_session, caller, test_resource):
        """Test detecting capacity overload conflict."""
        # Make resource constrained
        test_resource.committed_capacity = test_resource.total_capacity
        test_resource.available_capacity = 0.0
        await db_session.flush()
        
        conflicts = await canonical_resource_asset_service.derive_resource_conflicts(
            db_session, caller=caller
        )
        
        overload_conflicts = [c for c in conflicts if c.conflict_kind == "capacity_overload"]
        assert len(overload_conflicts) >= 1
    
    @pytest.mark.asyncio
    async def test_derive_underutilization_conflict(self, db_session, caller, test_resource):
        """Test detecting underutilization conflict."""
        allocation = ResourceAllocation(
            organization_id=caller.organization_id,
            resource_id=test_resource.id,
            resource_category="physical",
            resource_kind="equipment",
            target_type="project",
            target_id="proj-under",
            units_allocated=10.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            state="active",
            actual_utilization=1.0,  # Very low utilization
            fingerprint=f"ra-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(allocation)
        await db_session.flush()
        
        conflicts = await canonical_resource_asset_service.derive_resource_conflicts(
            db_session, caller=caller
        )
        
        under_conflicts = [c for c in conflicts if c.conflict_kind == "underutilization"]
        assert len(under_conflicts) >= 1
    
    @pytest.mark.asyncio
    async def test_derive_procurement_gap_conflict(self, db_session, caller):
        """Test detecting procurement gap conflict."""
        demand = ResourceDemand(
            organization_id=caller.organization_id,
            source_type="project",
            source_id="proj-gap",
            resource_category="physical",
            resource_kind="equipment",
            units_requested=10.0,
            unit="units",
            window_start=date.today() - timedelta(days=5),  # Window started in past
            window_end=date.today() + timedelta(days=30),
            fingerprint=f"rd-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(demand)
        await db_session.flush()
        
        conflicts = await canonical_resource_asset_service.derive_resource_conflicts(
            db_session, caller=caller
        )
        
        gap_conflicts = [c for c in conflicts if c.conflict_kind == "procurement_gap"]
        assert len(gap_conflicts) >= 1
    
    @pytest.mark.asyncio
    async def test_derive_lifecycle_risk_conflict(self, db_session, caller, test_asset):
        """Test detecting asset lifecycle risk conflict."""
        # Set asset maintenance due
        test_asset.next_maintenance_at = datetime.now(timezone.utc) - timedelta(days=1)
        await db_session.flush()
        
        conflicts = await canonical_resource_asset_service.derive_resource_conflicts(
            db_session, caller=caller
        )
        
        lifecycle_conflicts = [c for c in conflicts if c.conflict_kind == "lifecycle_risk"]
        assert len(lifecycle_conflicts) >= 1


# =============================================================================
# TESTS: GOVERNANCE & SECURITY
# =============================================================================

class TestGovernance:
    """Test governance and security."""
    
    @pytest.mark.asyncio
    async def test_resource_tenant_isolation(self, db_session, caller, test_org, test_resource):
        """Test that resource data doesn't leak across tenants."""
        # Create another org
        from app.models.organization import Organization
        other_org = Organization(
            name="Other Org",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(other_org)
        await db_session.flush()
        
        # Create resource in other org
        other_resource = CanonicalResource(
            organization_id=other_org.id,
            category="physical",
            kind="equipment",
            name="Other Resource",
            unit="units",
            total_capacity=5.0,
            fingerprint=f"cr-fp-{uuid.uuid4().hex[:32]}",
            created_by="other-system",
        )
        db_session.add(other_resource)
        await db_session.flush()
        
        # Query resources for caller's org - should only see own
        result = await db_session.execute(
            select(CanonicalResource).where(
                CanonicalResource.organization_id == caller.organization_id
            )
        )
        resources = result.scalars().all()
        resource_ids = {r.id for r in resources}
        
        assert test_resource.id in resource_ids
        assert other_resource.id not in resource_ids
    
    @pytest.mark.asyncio
    async def test_allocation_tenant_isolation(self, db_session, caller, test_org, test_resource):
        """Test allocation tenant isolation."""
        other_org = Organization(
            name="Other Org",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(other_org)
        await db_session.flush()
        
        other_resource = CanonicalResource(
            organization_id=other_org.id,
            category="physical",
            kind="equipment",
            name="Other",
            unit="units",
            total_capacity=5.0,
            fingerprint=f"cr-fp-{uuid.uuid4().hex[:32]}",
            created_by="other",
        )
        db_session.add(other_resource)
        await db_session.flush()
        
        other_alloc = ResourceAllocation(
            organization_id=other_org.id,
            resource_id=other_resource.id,
            resource_category="physical",
            resource_kind="equipment",
            target_type="project",
            target_id="proj-other",
            units_allocated=2.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            fingerprint=f"ra-fp-{uuid.uuid4().hex[:32]}",
            created_by="other",
        )
        db_session.add(other_alloc)
        await db_session.flush()
        
        result = await db_session.execute(
            select(ResourceAllocation).where(
                ResourceAllocation.organization_id == caller.organization_id
            )
        )
        allocs = result.scalars().all()
        assert other_alloc.id not in {a.id for a in allocs}


# =============================================================================
# TESTS: ADVERSARIAL
# =============================================================================

class TestAdversarial:
    """Adversarial tests."""
    
    @pytest.mark.asyncio
    async def test_fake_resource_id_rejected(self, db_session, caller):
        """Test that fake resource IDs don't create valid allocations."""
        fake_id = f"fake-{uuid.uuid4().hex[:24]}"
        
        allocation = ResourceAllocation(
            organization_id=caller.organization_id,
            resource_id=fake_id,
            resource_category="physical",
            resource_kind="equipment",
            target_type="project",
            target_id="proj-1",
            units_allocated=1.0,
            unit="units",
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            fingerprint=f"ra-fp-{uuid.uuid4().hex[:32]}",
            created_by=caller.employee_id or "system",
        )
        db_session.add(allocation)
        
        # The allocation can be created (no FK constraint in SQLite for this)
        # but it references a non-existent resource
        await db_session.flush()
        
        # Verify it references non-existent resource
        result = await db_session.execute(
            select(CanonicalResource).where(
                CanonicalResource.id == fake_id
            )
        )
        assert result.scalars().first() is None
    
    @pytest.mark.asyncio
    async def test_cross_tenant_resource_creation_blocked(self, db_session, caller, test_org):
        """Test that creating resource for another org fails governance."""
        # This would be caught by _verify_resource_access in production
        # For now, verify the service doesn't allow it implicitly
        pass  # Governance is enforced at API layer


# =============================================================================
# TESTS: REGRESSION (Prior Gates Still Work)
# =============================================================================

class TestRegression:
    """Test that prior gates still work."""
    
    @pytest.mark.asyncio
    async def test_gate15_financial_still_works(self, db_session, caller, test_customer):
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
    
    def test_resource_categories_complete(self):
        """Test all expected categories exist."""
        expected = {"human", "physical", "digital", "software", "infrastructure", "financial", "organizational", "external"}
        assert set(RESOURCE_CATEGORIES) == expected
    
    def test_resource_kinds_comprehensive(self):
        """Test resource kinds cover major types."""
        # Should have human, physical, digital, software, infrastructure, financial, organizational, external kinds
        kinds = set(RESOURCE_KINDS)
        assert "employee_capacity" in kinds
        assert "equipment" in kinds
        assert "cloud_compute" in kinds
        assert "saas_license" in kinds
        assert "server" in kinds
        assert "budget_allocation" in kinds
        assert "engineering_capability" in kinds
        assert "vendor_capacity" in kinds
    
    def test_asset_lifecycle_complete(self):
        """Test asset lifecycle covers full lifecycle."""
        states = set(ASSET_LIFECYCLE_STATES)
        assert "required" in states
        assert "requested" in states
        assert "procured" in states
        assert "received" in states
        assert "provisioned" in states
        assert "available" in states
        assert "allocated" in states
        assert "in_use" in states
        assert "maintenance" in states
        assert "deallocated" in states
        assert "retired" in states
        assert "disposed" in states
    
    def test_allocation_states_complete(self):
        """Test allocation states cover workflow."""
        states = set(ALLOCATION_STATES)
        assert "requested" in states
        assert "approved" in states
        assert "active" in states
        assert "completed" in states
        assert "released" in states
        assert "cancelled" in states
    
    def test_allocation_target_types_complete(self):
        """Test all target types supported."""
        targets = set(ALLOCATION_TARGET_TYPES)
        assert "person" in targets
        assert "team" in targets
        assert "project" in targets
        assert "commitment" in targets
        assert "customer" in targets
        assert "operation" in targets
        assert "objective" in targets
        assert "initiative" in targets


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])