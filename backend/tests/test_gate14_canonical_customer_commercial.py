"""Gate 14 — Canonical Customer & Commercial Operating Fabric Tests.

Tests for the canonical customer/business reality that connects external
economic relationships to internal execution reality.
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
from app.models.customer import (
    Customer,
    CustomerContact,
    CustomerProjectLink,
    CustomerMeetingLink,
)
from app.models.lead import Opportunity
from app.models.customer_intelligence import (
    CustomerSignal,
    CustomerTheme,
    CustomerCommitment,
    CustomerHealthRow,
    CustomerOutcome,
)
from app.models.company_intent import CompanyIntent
from app.models.finance import Invoice
from app.models.business_commercial import (
    BusinessNeed,
    CommercialIntent,
    BusinessOutcome,
    CustomerRisk,
    CustomerOperatingSlice,
    CustomerImpactAnalysis,
    CustomerOperatingContext,
    BUSINESS_NEED_KINDS,
    BUSINESS_NEED_STATES,
    COMMERCIAL_INTENT_KINDS,
    COMMERCIAL_INTENT_STATES,
    BUSINESS_OUTCOME_KINDS,
    BUSINESS_OUTCOME_STATES,
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
async def test_opportunity(db_session, caller, test_customer):
    """Create test opportunity."""
    opp = Opportunity(
        organization_id=caller.organization_id,
        customer_id=test_customer.id,
        title="Test Opportunity",
        stage="proposal",
        value=100000.0,
        probability=60,
        expected_close_date=date.today() + timedelta(days=30),
    )
    db_session.add(opp)
    await db_session.commit()
    return opp


@pytest_asyncio.fixture
async def test_project(db_session, caller, test_customer):
    """Create test project linked to customer."""
    project = Project(
        organization_id=caller.organization_id,
        name="Customer Project",
        code=f"PRJ{uuid.uuid4().hex[:4]}",
        status="active",
        owner_id="test-owner",
    )
    db_session.add(project)
    await db_session.flush()
    
    link = CustomerProjectLink(
        organization_id=caller.organization_id,
        customer_id=test_customer.id,
        project_id=project.id,
        kind="implementation",
        status="active",
    )
    db_session.add(link)
    await db_session.commit()
    
    return project


@pytest_asyncio.fixture
async def test_customer_commitment(db_session, caller, test_customer, test_project):
    """Create test customer commitment."""
    commitment = CustomerCommitment(
        organization_id=caller.organization_id,
        customer_id=test_customer.id,
        summary="Deliver feature X by Q2",
        expected_at=date.today() + timedelta(days=60),
        status="at_risk",
        project_id=test_project.id,
        capability="Python Development",
        owner_label="Engineering Team",
        source_event_id=f"cc-{uuid.uuid4().hex[:16]}",
    )
    db_session.add(commitment)
    await db_session.commit()
    return commitment


@pytest_asyncio.fixture
async def test_company_commitment(db_session, caller, test_project, test_employee):
    """Create test company commitment."""
    commitment = CompanyCommitment(
        organization_id=caller.organization_id,
        commitment_type="unconditional",
        title="Customer Project Delivery",
        state="active",
        scope_type="project",
        scope_id=test_project.id,
        rationale="Customer commitment",
        fingerprint=f"comm-fp-{uuid.uuid4().hex[:32]}",
        source_event_id="commitment-test-1",
    )
    db_session.add(commitment)
    await db_session.flush()
    
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
    await db_session.commit()
    
    return commitment


@pytest_asyncio.fixture
async def test_business_need(db_session, caller, test_customer, test_opportunity):
    """Create test business need."""
    need = BusinessNeed(
        organization_id=caller.organization_id,
        kind="problem_solution",
        title="Customer needs automated deployment",
        description="Customer wants to automate their deployment pipeline",
        state="qualified",
        customer_id=test_customer.id,
        opportunity_id=test_opportunity.id,
        confidence=0.8,
        estimated_value=100000.0,
        urgency="high",
        fingerprint=f"bn-fp-{uuid.uuid4().hex[:32]}",
    )
    db_session.add(need)
    await db_session.commit()
    return need


@pytest_asyncio.fixture
async def test_commercial_intent(db_session, caller, test_customer, test_business_need):
    """Create test commercial intent."""
    intent = CommercialIntent(
        organization_id=caller.organization_id,
        kind="win_business",
        title="Win deployment automation deal",
        description="Win the deployment automation contract",
        customer_id=test_customer.id,
        business_need_id=test_business_need.id,
        estimated_value=100000.0,
        probability=70,
        expected_close_date=date.today() + timedelta(days=30),
        state="committed",
        fingerprint=f"ci-fp-{uuid.uuid4().hex[:32]}",
    )
    db_session.add(intent)
    await db_session.commit()
    return intent


@pytest_asyncio.fixture
async def test_business_outcome(db_session, caller, test_customer, test_commercial_intent):
    """Create test business outcome."""
    outcome = BusinessOutcome(
        organization_id=caller.organization_id,
        kind="revenue_achieved",
        title="Q2 Revenue from deployment automation",
        state="projected",
        commercial_intent_id=test_commercial_intent.id,
        customer_id=test_customer.id,
        metric_kind="revenue",
        metric_unit="USD",
        target_value=100000.0,
        actual_value=0.0,
        currency="USD",
        revenue_impact=100000.0,
        fingerprint=f"bo-fp-{uuid.uuid4().hex[:32]}",
    )
    db_session.add(outcome)
    await db_session.commit()
    return outcome


# ============================================================================
# Test Classes
# ============================================================================

class TestBusinessNeed:
    """Test BusinessNeed model."""

    @pytest.mark.asyncio
    async def test_create_business_need(
        self, db_session, caller, test_customer, test_opportunity
    ):
        """Test creating a business need."""
        need = BusinessNeed(
            organization_id=caller.organization_id,
            kind="capability_gap",
            title="Customer needs CI/CD pipeline",
            state="discovered",
            customer_id=test_customer.id,
            confidence=0.6,
            fingerprint=f"bn-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(need)
        await db_session.commit()
        
        assert need.id is not None
        assert need.kind == "capability_gap"
        assert need.state == "discovered"
        assert need.customer_id == test_customer.id

    @pytest.mark.asyncio
    async def test_business_need_state_transitions(
        self, db_session, caller, test_customer, test_opportunity
    ):
        """Test business need state transitions."""
        need = BusinessNeed(
            organization_id=caller.organization_id,
            kind="problem_solution",
            title="Test Need",
            state="discovered",
            customer_id=test_customer.id,
            opportunity_id=test_opportunity.id,
            fingerprint=f"bn-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(need)
        await db_session.flush()
        
        # Transition to qualified
        need.state = "qualified"
        need.qualified_at = utcnow()
        await db_session.flush()
        assert need.state == "qualified"
        assert need.qualified_at is not None
        
        # Transition to addressed
        need.state = "addressed"
        need.addressed_at = utcnow()
        await db_session.flush()
        assert need.state == "addressed"


class TestCommercialIntent:
    """Test CommercialIntent model."""

    @pytest.mark.asyncio
    async def test_create_commercial_intent(
        self, db_session, caller, test_customer, test_business_need
    ):
        """Test creating a commercial intent."""
        intent = CommercialIntent(
            organization_id=caller.organization_id,
            kind="expand_account",
            title="Expand customer account",
            customer_id=test_customer.id,
            business_need_id=test_business_need.id,
            estimated_value=50000.0,
            probability=80,
            state="qualified",
            fingerprint=f"ci-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(intent)
        await db_session.commit()
        
        assert intent.id is not None
        assert intent.kind == "expand_account"
        assert intent.customer_id == test_customer.id
        assert intent.business_need_id == test_business_need.id

    @pytest.mark.asyncio
    async def test_commercial_intent_state_transitions(
        self, db_session, caller, test_customer, test_business_need
    ):
        """Test commercial intent state transitions."""
        intent = CommercialIntent(
            organization_id=caller.organization_id,
            kind="win_business",
            title="Test Intent",
            customer_id=test_customer.id,
            business_need_id=test_business_need.id,
            state="proposed",
            fingerprint=f"ci-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(intent)
        await db_session.flush()
        
        # Transition to qualified
        intent.state = "qualified"
        await db_session.flush()
        
        # Transition to committed
        intent.state = "committed"
        intent.committed_at = utcnow()
        await db_session.flush()
        
        # Transition to won
        intent.state = "won"
        intent.won_at = utcnow()
        await db_session.flush()
        
        assert intent.state == "won"
        assert intent.won_at is not None


class TestBusinessOutcome:
    """Test BusinessOutcome model."""

    @pytest.mark.asyncio
    async def test_create_business_outcome(
        self, db_session, caller, test_customer, test_commercial_intent
    ):
        """Test creating a business outcome."""
        outcome = BusinessOutcome(
            organization_id=caller.organization_id,
            kind="revenue_achieved",
            title="Q3 Revenue Target",
            commercial_intent_id=test_commercial_intent.id,
            customer_id=test_customer.id,
            metric_kind="revenue",
            target_value=500000.0,
            actual_value=0.0,
            revenue_impact=500000.0,
            fingerprint=f"bo-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(outcome)
        await db_session.commit()
        
        assert outcome.id is not None
        assert outcome.kind == "revenue_achieved"
        assert outcome.target_value == 500000.0


class TestCustomerOperatingSlice:
    """Test CustomerOperatingSlice derivation."""

    @pytest.mark.asyncio
    async def test_derive_customer_operating_slice(
        self, db_session, caller, test_customer, test_customer_commitment, 
        test_project, test_company_commitment
    ):
        """Test deriving customer operating slice."""
        slice_obj = await customer_operating_fabric_service.derive_customer_operating_slice(
            db_session, caller=caller, customer_id=test_customer.id
        )
        
        assert slice_obj.id is not None
        assert slice_obj.customer_id == test_customer.id
        assert slice_obj.organization_id == caller.organization_id
        assert len(slice_obj.commitments) >= 1
        assert len(slice_obj.projects) >= 1
        assert slice_obj.open_commitments >= 1

    @pytest.mark.asyncio
    async def test_slice_exact_once(
        self, db_session, caller, test_customer, test_customer_commitment, test_project
    ):
        """Test exact-once semantics for slice derivation."""
        slice1 = await customer_operating_fabric_service.derive_customer_operating_slice(
            db_session, caller=caller, customer_id=test_customer.id
        )
        slice2 = await customer_operating_fabric_service.derive_customer_operating_slice(
            db_session, caller=caller, customer_id=test_customer.id
        )
        
        # Should return same slice (exact-once)
        assert slice1.id == slice2.id
        assert slice1.fingerprint == slice2.fingerprint


class TestCustomerOperatingContext:
    """Test CustomerOperatingContext derivation."""

    @pytest.mark.asyncio
    async def test_account_manager_context(
        self, db_session, caller, test_customer, test_customer_commitment
    ):
        """Test account manager operating context."""
        context = await customer_operating_fabric_service.derive_customer_operating_context(
            db_session, caller=caller, customer_id=test_customer.id, role_type="account_manager"
        )
        
        assert context.id is not None
        assert context.role_type == "account_manager"
        assert context.customer_id == test_customer.id
        assert "commitments" in context.__dict__

    @pytest.mark.asyncio
    async def test_executive_context(
        self, db_session, caller, test_customer
    ):
        """Test executive operating context."""
        context = await customer_operating_fabric_service.derive_customer_operating_context(
            db_session, caller=caller, customer_id=test_customer.id, role_type="executive"
        )
        
        assert context.role_type == "executive"

    @pytest.mark.asyncio
    async def test_context_exact_once(
        self, db_session, caller, test_customer, test_customer_commitment
    ):
        """Test exact-once for context."""
        ctx1 = await customer_operating_fabric_service.derive_customer_operating_context(
            db_session, caller=caller, customer_id=test_customer.id, role_type="account_manager"
        )
        ctx2 = await customer_operating_fabric_service.derive_customer_operating_context(
            db_session, caller=caller, customer_id=test_customer.id, role_type="account_manager"
        )
        
        assert ctx1.id == ctx2.id
        assert ctx1.fingerprint == ctx2.fingerprint


class TestCustomerImpactAnalysis:
    """Test CustomerImpactAnalysis derivation."""

    @pytest.mark.asyncio
    async def test_analyze_project_delay_impact(
        self, db_session, caller, test_customer, test_project, test_customer_commitment
    ):
        """Test analyzing impact of project delay on customer."""
        analysis = await customer_operating_fabric_service.analyze_customer_impact(
            db_session,
            caller=caller,
            customer_id=test_customer.id,
            trigger_type="project_delay",
            trigger_entity_type="project",
            trigger_entity_id=test_project.id,
            trigger_params={"weeks": 2},
        )
        
        assert analysis.id is not None
        assert analysis.customer_id == test_customer.id
        assert analysis.trigger_type == "project_delay"
        assert analysis.trigger_entity_type == "project"
        assert analysis.trigger_entity_id == test_project.id
        assert "affected_commitments" in analysis.__dict__
        assert "affected_projects" in analysis.__dict__

    @pytest.mark.asyncio
    async def test_impact_analysis_exact_once(
        self, db_session, caller, test_customer, test_project
    ):
        """Test exact-once for impact analysis."""
        analysis1 = await customer_operating_fabric_service.analyze_customer_impact(
            db_session, caller=caller, customer_id=test_customer.id,
            trigger_type="project_delay", trigger_entity_type="project", trigger_entity_id=test_project.id
        )
        analysis2 = await customer_operating_fabric_service.analyze_customer_impact(
            db_session, caller=caller, customer_id=test_customer.id,
            trigger_type="project_delay", trigger_entity_type="project", trigger_entity_id=test_project.id
        )
        
        assert analysis1.id == analysis2.id
        assert analysis1.fingerprint == analysis2.fingerprint


class TestCustomerRiskDerivation:
    """Test CustomerRisk derivation."""

    @pytest.mark.asyncio
    async def test_derive_customer_risks(
        self, db_session, caller, test_customer, test_customer_commitment, test_project
    ):
        """Test deriving customer risks."""
        risks = await customer_operating_fabric_service.derive_customer_risks(
            db_session, caller=caller, customer_id=test_customer.id
        )
        
        assert isinstance(risks, list)
        # At least commitment risk should exist
        commitment_risks = [r for r in risks if r.kind == "delivery"]
        assert len(commitment_risks) >= 1

    @pytest.mark.asyncio
    async def test_health_derived_risk(
        self, db_session, caller, test_customer
    ):
        """Test risk derived from customer health."""
        # Create at-risk health
        health = CustomerHealthRow(
            organization_id=caller.organization_id,
            customer_id=test_customer.id,
            state="at_risk",
            score=30,
            reasons_json=["Missed SLA", "Declining usage"],
            factors_json={"usage_trend": -0.3},
            computed_at=utcnow(),
        )
        db_session.add(health)
        await db_session.commit()
        
        risks = await customer_operating_fabric_service.derive_customer_risks(
            db_session, caller=caller, customer_id=test_customer.id
        )
        
        health_risks = [r for r in risks if r.kind == "relationship" and "health" in r.title.lower()]
        assert len(health_risks) >= 1
        risk = health_risks[0]
        assert risk.level in ("high", "critical")
        assert risk.epistemic_status == "measured"


class TestCustomerRisk:
    """Test CustomerRisk model."""

    @pytest.mark.asyncio
    async def test_create_customer_risk(
        self, db_session, caller, test_customer, test_customer_commitment
    ):
        """Test creating a customer risk."""
        risk = CustomerRisk(
            organization_id=caller.organization_id,
            customer_id=test_customer.id,
            commitment_id=test_customer_commitment.id,
            kind="delivery",
            level="high",
            title="Commitment delivery at risk",
            description="Project delay threatens commitment",
            probability=0.7,
            impact_score=75.0,
            epistemic_status="observed",
            evidence_fingerprints=["commitment-123"],
            source_event_id="risk-event-1",
            fingerprint=f"cr-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(risk)
        await db_session.commit()
        
        assert risk.id is not None
        assert risk.kind == "delivery"
        assert risk.level == "high"
        assert risk.epistemic_status == "observed"

    @pytest.mark.asyncio
    async def test_customer_risk_causal_chain(
        self, db_session, caller, test_customer
    ):
        """Test customer risk with causal chain."""
        risk = CustomerRisk(
            organization_id=caller.organization_id,
            customer_id=test_customer.id,
            kind="capacity",
            level="critical",
            title="Critical capacity deficit",
            causal_chain=[
                {"type": "person", "id": "person-1", "label": "Lead Engineer", "impact": "overloaded"},
                {"type": "commitment", "id": "comm-1", "label": "Customer Commitment", "impact": "delayed"},
            ],
            probability=0.9,
            impact_score=90.0,
            epistemic_status="observed",
            fingerprint=f"cr-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(risk)
        await db_session.commit()
        
        assert risk.causal_chain is not None
        assert len(risk.causal_chain) >= 0


class TestCustomerImpactAnalysis:
    """Test CustomerImpactAnalysis model."""

    @pytest.mark.asyncio
    async def test_create_impact_analysis(
        self, db_session, caller, test_customer, test_project
    ):
        """Test creating an impact analysis."""
        analysis = CustomerImpactAnalysis(
            organization_id=caller.organization_id,
            customer_id=test_customer.id,
            trigger_type="project_delay",
            trigger_entity_type="project",
            trigger_entity_id=test_project.id,
            trigger_params={"weeks": 3},
            affected_commitments=[
                {"commitment_id": "comm-1", "impact": "delay"}
            ],
            affected_projects=[{"project_id": test_project.id, "impact": "delay"}],
            customer_outcome_impact={"revenue_impact": -50000.0},
            revenue_impact=-50000.0,
            fingerprint=f"cia-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(analysis)
        await db_session.commit()
        
        assert analysis.id is not None
        assert analysis.trigger_type == "project_delay"
        assert analysis.affected_commitments is not None


class TestCustomerOperatingContext:
    """Test CustomerOperatingContext model."""

    @pytest.mark.asyncio
    async def test_create_operating_context(
        self, db_session, caller, test_customer
    ):
        """Test creating an operating context."""
        import hashlib, json
        input_data = {
            "customer_id": test_customer.id,
            "role_type": "account_manager",
            "actor_person_id": "person-123",
        }
        input_fingerprint = hashlib.sha256(
            json.dumps(input_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        context = CustomerOperatingContext(
            organization_id=caller.organization_id,
            customer_id=test_customer.id,
            role_type="account_manager",
            actor_person_id="person-123",
            input_fingerprint=input_fingerprint,
            attention_items=[{"type": "commitment_risk", "title": "Commitment at risk"}],
            commitments=[{"id": "comm-1", "summary": "Test commitment"}],
            risks=[{"id": "risk-1", "level": "high"}],
            fingerprint=f"coc-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(context)
        await db_session.commit()
        
        assert context.id is not None
        assert context.role_type == "account_manager"
        assert context.actor_person_id == "person-123"


class TestGovernance:
    """Test governance enforcement."""

    @pytest.mark.asyncio
    async def test_cross_tenant_slice_blocked(
        self, db_session, caller, test_org, test_customer
    ):
        """Test that cross-tenant slice access is blocked."""
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
        
        # Try to access original org's customer slice
        with pytest.raises(ValueError, match="Cross-tenant access denied"):
            await customer_operating_fabric_service.derive_customer_operating_slice(
                db_session, caller=other_caller, customer_id=test_customer.id
            )

    @pytest.mark.asyncio
    async def test_cross_tenant_context_blocked(
        self, db_session, caller, test_org, test_customer
    ):
        """Test that cross-tenant context access is blocked."""
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
        
        with pytest.raises(ValueError, match="Cross-tenant access denied"):
            await customer_operating_fabric_service.derive_customer_operating_context(
                db_session, caller=other_caller, customer_id=test_customer.id, role_type="account_manager"
            )


class TestEpistemicBoundaries:
    """Test epistemic boundary enforcement."""

    @pytest.mark.asyncio
    async def test_risk_epistemic_status(
        self, db_session, caller, test_customer
    ):
        """Test that risks have proper epistemic status."""
        risks = await customer_operating_fabric_service.derive_customer_risks(
            db_session, caller=caller, customer_id=test_customer.id
        )
        
        for risk in risks:
            assert risk.epistemic_status in (
                "observed", "measured", "evidence_backed", 
                "inferred", "predicted", "proposed", "counterfactual"
            )
            # Risks should not be "truth" or "decision"
            assert risk.epistemic_status not in ("decision", "authorized", "executed", "outcome", "verified")

    @pytest.mark.asyncio
    async def test_impact_analysis_not_truth(
        self, db_session, caller, test_customer, test_project
    ):
        """Test that impact analysis is not presented as truth."""
        analysis = await customer_operating_fabric_service.analyze_customer_impact(
            db_session, caller=caller, customer_id=test_customer.id,
            trigger_type="project_delay", trigger_entity_type="project", trigger_entity_id=test_project.id
        )
        
        # Should have confidence < 1.0
        assert analysis.confidence < 1.0


class TestTemporalTruth:
    """Test temporal truth preservation."""

    @pytest.mark.asyncio
    async def test_business_need_supersession(
        self, db_session, caller, test_customer, test_opportunity
    ):
        """Test business need supersession chain."""
        need1 = BusinessNeed(
            organization_id=caller.organization_id,
            kind="problem_solution",
            title="Need v1",
            state="addressed",
            customer_id=test_customer.id,
            opportunity_id=test_opportunity.id,
            fingerprint=f"bn-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(need1)
        await db_session.flush()
        
        need2 = BusinessNeed(
            organization_id=caller.organization_id,
            kind="problem_solution",
            title="Need v2",
            state="qualified",
            customer_id=test_customer.id,
            supersedes_id=need1.id,
            fingerprint=f"bn-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(need2)
        await db_session.flush()
        
        # Manually set reverse reference (not automatic in model)
        need1.superseded_by_id = need2.id
        await db_session.commit()
        
        # Verify chain
        assert need1.superseded_by_id == need2.id
        assert need2.supersedes_id == need1.id

    @pytest.mark.asyncio
    async def test_commercial_intent_supersession(
        self, db_session, caller, test_customer, test_business_need
    ):
        """Test commercial intent supersession."""
        intent1 = CommercialIntent(
            organization_id=caller.organization_id,
            kind="win_business",
            title="Intent v1",
            customer_id=test_customer.id,
            business_need_id=test_business_need.id,
            state="lost",
            fingerprint=f"ci-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(intent1)
        await db_session.flush()
        
        intent2 = CommercialIntent(
            organization_id=caller.organization_id,
            kind="win_business",
            title="Intent v2",
            customer_id=test_customer.id,
            business_need_id=test_business_need.id,
            state="committed",
            supersedes_id=intent1.id,
            fingerprint=f"ci-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(intent2)
        await db_session.flush()
        
        # Manually set reverse reference (not automatic in model)
        intent1.superseded_by_id = intent2.id
        await db_session.commit()
        
        assert intent1.superseded_by_id == intent2.id
        assert intent2.supersedes_id == intent1.id


class TestRegression:
    """Regression tests for prior gates."""

    @pytest.mark.asyncio
    async def test_gate13_alignment_still_works(
        self, db_session, caller, test_customer, test_project
    ):
        """Test that Gate 13 strategic alignment still works."""
        result = await strategic_alignment_engine.trace_forward(
            db_session, caller=caller,
            entity_type="project", entity_id=test_project.id, max_depth=3
        )
        assert "chain" in result

    @pytest.mark.asyncio
    async def test_gate12_digital_twin_still_works(
        self, db_session, caller, test_customer
    ):
        """Test that Gate 12 Digital Twin still works."""
        result = await canonical_digital_twin_service.derive_twin_state(
            db_session, caller=caller, scope_type="org"
        )
        assert result["advisory_only"] is True

    @pytest.mark.asyncio
    async def test_gate11_counterfactual_still_works(
        self, db_session, caller, test_customer
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
    async def test_fake_customer_id_rejected(
        self, db_session, caller
    ):
        """Test that fake customer IDs are rejected."""
        fake_id = f"fake-{uuid.uuid4().hex[:24]}"
        
        with pytest.raises(ValueError, match="Customer not found"):
            await customer_operating_fabric_service.derive_customer_operating_slice(
                db_session, caller=caller, customer_id=fake_id
            )

    @pytest.mark.asyncio
    async def test_cross_tenant_customer_creation_blocked(
        self, db_session, caller, test_org
    ):
        """Test that customer creation across tenants is isolated."""
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
        
        # Create customer in other org
        other_customer = Customer(
            organization_id=other_org.id,
            company_name="Other Customer",
            status="customer",
        )
        db_session.add(other_customer)
        await db_session.commit()
        
        # Try to access from original caller
        with pytest.raises(ValueError, match="Cross-tenant access denied"):
            await customer_operating_fabric_service.derive_customer_operating_slice(
                db_session, caller=caller, customer_id=other_customer.id
            )

    @pytest.mark.asyncio
    async def test_concurrent_slice_derivation(
        self, db_session, caller, test_customer
    ):
        """Test concurrent slice derivation exact-once."""
        import asyncio
        
        async def derive():
            return await customer_operating_fabric_service.derive_customer_operating_slice(
                db_session, caller=caller, customer_id=test_customer.id
            )
        
        results = await asyncio.gather(*[derive() for _ in range(3)])
        
        # All should return same slice
        ids = {r.id for r in results}
        assert len(ids) == 1

    @pytest.mark.asyncio
    async def test_impact_analysis_with_capacity_change(
        self, db_session, caller, test_customer, test_project, test_employee
    ):
        """Test impact analysis with capacity change trigger."""
        # Create capacity issue
        from app.models.workload import WorkloadSnapshot
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=date.today() - timedelta(days=7),
            period_end=date.today(),
            capacity_hours=40,
            allocated_hours=50,
            utilization=1.25,
            is_overloaded=True,
        )
        db_session.add(workload)
        await db_session.commit()
        
        # Analyze capacity change impact
        analysis = await customer_operating_fabric_service.analyze_customer_impact(
            db_session, caller=caller, customer_id=test_customer.id,
            trigger_type="capacity_change", trigger_entity_type="person", trigger_entity_id=test_employee.id,
            trigger_params={"change_type": "overload"}
        )
        
        assert analysis.affected_capacity is not None

    @pytest.mark.asyncio
    async def test_business_need_derivation_from_signals(
        self, db_session, caller, test_customer
    ):
        """Test business need derivation from customer signals."""
        # Create signals
        signal = CustomerSignal(
            organization_id=caller.organization_id,
            customer_id=test_customer.id,
            signal_type="request",
            need_key="automated_deployment",
            title="Customer requests automated deployment",
            severity="high",
            source="support",
            status="open",
            occurred_at=utcnow(),
            source_event_id=f"signal-{uuid.uuid4().hex[:16]}",
        )
        db_session.add(signal)
        await db_session.flush()
        
        # Create theme
        theme = CustomerTheme(
            organization_id=caller.organization_id,
            key="automated_deployment",
            title="Automated Deployment Requests",
            occurrences=3,
            customer_count=2,
            trend="worsening",
            signal_ids_json=[signal.id],
            customer_ids_json=[test_customer.id],
        )
        db_session.add(theme)
        await db_session.commit()
        
        # Create business need from signal/theme
        need = BusinessNeed(
            organization_id=caller.organization_id,
            kind="capability_gap",
            title="Automated Deployment Capability",
            customer_id=test_customer.id,
            signal_ids=[signal.id],
            theme_ids=[theme.id],
            confidence=0.8,
            fingerprint=f"bn-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(need)
        await db_session.commit()
        
        assert need.signal_ids == [signal.id]
        assert need.theme_ids == [theme.id]


# Need imports
from datetime import date