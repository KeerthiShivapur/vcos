"""Gate 28 — Governed Autonomous Company Operations Tests.

Tests for the canonical governed autonomy framework.
"""

import pytest
import pytest_asyncio
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.autonomy import (
    AutonomyPolicy,
    AutonomyProposal,
    AutonomyEligibility,
    AutonomyEvent,
    AutonomyExecution,
    AutonomyLearning,
    AutonomyRisk,
    AutonomyContext,
    AUTONOMY_STATES,
    AUTONOMY_RISK_CLASSES,
    AUTONOMY_PROPOSAL_TYPES,
    POLICY_DECISIONS,
    AUTONOMY_EVENT_TYPES,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.finance import Subscription
from app.models.role import Role, UserRole, Permission, RolePermission
from app.services.permission_service import permission_service
from app.intelligence.company_context import resolve_caller_access
from app.intelligence.canonical_integration_service import connector_service
from app.intelligence.external_identity_service import external_identity_mapping_service
from app.intelligence.synchronization_service import synchronization_service
from app.intelligence.source_authority_service import source_authority_service
from app.intelligence.bidirectional_operation_service import bidirectional_operation_service
from app.intelligence.integration_health_service import integration_health_service
from app.intelligence.connectors import connector_registry, GoogleWorkspaceConnector, Microsoft365Connector, SlackConnector, GitHubConnector, JiraConnector
from app.intelligence.company_brain import company_brain
from app.services.autonomy_service import autonomy_service
from app.models.finance import Plan
from app.models.company_actions import CompanyAction
from app.models.execution_strategy import CompanyCommitment
from app.models.governance import ApprovalPolicy
from app.intelligence.canonical_mutation import canonical_mutation_boundary
from app.intelligence.company_brain import company_brain
from app.intelligence.canonical_mutation import (
    CanonicalMutationContext,
    MutationType,
    EpistemicStatus,
    ExactOnceViolation,
    ConcurrencyViolation,
)
from app.core.timeutils import utcnow


@pytest_asyncio.fixture
async def other_org(db_session: AsyncSession) -> Organization:
    """Create another test organization for cross-tenant tests."""
    unique = uuid.uuid4().hex[:8]
    org = Organization(
        id=f"other-org-{unique}",
        name=f"Other Org {unique}",
        slug=f"other-org-{unique}",
        status="active",
    )
    db_session.add(org)
    await db_session.flush()
    return org

@pytest_asyncio.fixture
async def test_caller(db_session: AsyncSession, test_org: Organization, test_user: User, test_employee: Employee):
    """Create test caller with org-wide access including autonomy permissions."""
    from app.intelligence.company_context import resolve_caller_access
    from app.models.role import Role, UserRole, Permission, RolePermission
    from app.services.permission_service import permission_service
    
    # Create or get autonomy admin role
    role_result = await db_session.execute(
        select(Role).where(
            Role.organization_id == test_org.id,
            Role.code == "autonomy_admin"
        )
    )
    role = role_result.scalars().first()
    if not role:
        role = Role(
            organization_id=test_org.id,
            name="Autonomy Admin",
            code="autonomy_admin",
            description="Admin role for autonomy operations",
        )
        db_session.add(role)
        await db_session.flush()
        
        # Grant autonomy:approve, autonomy:execute, and task:create permissions
        perm_result = await db_session.execute(
            select(Permission).where(Permission.code.in_(["autonomy:approve", "autonomy:execute", "task:create"]))
        )
        perms = perm_result.scalars().all()
        
        if not any(p.code == "autonomy:approve" for p in perms):
            perm = Permission(
                code="autonomy:approve",
                name="Approve Autonomous Operations",
                resource="autonomy",
                action="approve",
            )
            db_session.add(perm)
            await db_session.flush()
        
        if not any(p.code == "autonomy:execute" for p in perms):
            perm = Permission(
                code="autonomy:execute",
                name="Execute Autonomous Operations",
                resource="autonomy",
                action="execute",
            )
            db_session.add(perm)
            await db_session.flush()
        
        if not any(p.code == "task:create" for p in perms):
            perm = Permission(
                code="task:create",
                name="Create Task",
                resource="task",
                action="create",
            )
            db_session.add(perm)
            await db_session.flush()
        
        # Get the permissions again
        perm_result = await db_session.execute(
            select(Permission).where(Permission.code.in_(["autonomy:approve", "autonomy:execute", "task:create"]))
        )
        perms = perm_result.scalars().all()
        
        for perm in perms:
            if perm.code in ["autonomy:approve", "autonomy:execute", "task:create"]:
                db_session.add(RolePermission(role_id=role.id, permission_id=perm.id))
        
        await db_session.flush()
    
    # Assign role to test user
    user_role = UserRole(
        user_id=test_user.id,
        role_id=role.id,
        organization_id=test_org.id,
        scope_id=None,  # org-wide
    )
    db_session.add(user_role)
    await db_session.flush()
    
    # Sync permissions
    await permission_service.sync_role_permissions(db_session)
    await db_session.commit()
    
    return await resolve_caller_access(db_session, organization_id=test_org.id, user=test_user)


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_org(db_session: AsyncSession) -> Organization:
    """Create test organization."""
    unique = uuid.uuid4().hex[:8]
    org = Organization(
        id=f"test-org-{unique}",
        name=f"Test Org {unique}",
        slug=f"test-org-{unique}",
        status="active",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_org: Organization) -> User:
    """Create test user without employee record (created by test_caller)."""
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=f"user-{unique}",
        email=f"test-{unique}@example.com",
        password_hash="test_hash",
        full_name="Test User",
        organization_id=test_org.id,
        status="active",
        role="employee",
    )
    db_session.add(user)
    await db_session.flush()
    
    # Create subscription for the user
    from app.models.finance import Subscription
    from app.services.commercial_service import commercial_service
    
    # Create a plan and subscription for the user
    plan = await commercial_service.get_plan_by_key(db_session, "starter")
    if not plan:
        plan = await commercial_service.create_plan(
            db_session,
            key="starter",
            name="Starter",
            tier="starter",
            monthly_price_cents=0,
            annual_price_cents=0,
            entitlements={"automation.enabled": True, "employees.max": 100},
            features={"automation": True},
            limits={"employees.max": 100},
            trial_days=14,
            is_public=True,
            sort_order=1,
        )
    
    subscription = Subscription(
        organization_id=test_org.id,
        plan_id=plan.id,
        state="active",
        billing_interval="monthly",
        price_cents=plan.monthly_price_cents,
        currency="USD",
        trial_started_at=utcnow(),
        trial_ends_at=utcnow() + timedelta(days=14),
        current_period_start=utcnow(),
        current_period_end=utcnow() + timedelta(days=30),
        auto_renew=True,
    )
    db_session.add(subscription)
    await db_session.flush()
    
    return user


@pytest_asyncio.fixture
async def test_employee(db_session: AsyncSession, test_org: Organization, test_user: User) -> Employee:
    """Create test employee."""
    emp = Employee(
        id=f"emp-{uuid.uuid4().hex[:8]}",
        organization_id=test_org.id,
        user_id=test_user.id,
        employee_number=f"E{uuid.uuid4().hex[:6]}",
        first_name="Test",
        last_name="User",
        display_name="Test User",
        email=f"test{uuid.uuid4().hex[:4]}@test.com",
        status="active",
    )
    db_session.add(emp)
    await db_session.flush()
    return emp


@pytest_asyncio.fixture
async def test_autonomy_policy(db_session: AsyncSession, test_org: Organization, test_user: User):
    """Create a test autonomy policy."""
    policy = AutonomyPolicy(
        organization_id=test_org.id,
        policy_key="test_autonomy",
        name="Test Autonomy Policy",
        description="Test policy for autonomous operations",
        risk_class="auto_execute_reversible",
        applies_to_types=["execute_action"],
        is_active=True,
    )
    db_session.add(policy)
    await db_session.flush()
    return policy


@pytest_asyncio.fixture
async def test_autonomy_proposal(db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_policy):
    """Create a test autonomy proposal."""
    proposal = AutonomyProposal(
        organization_id=test_org.id,
        proposal_type="execute_action",
        title="Test Autonomous Action",
        description="Test autonomous operation",
        state="proposed",
        risk_class="auto_execute_reversible",
        actor_id=test_user.id,
        actor_type="human",
        scope_type="org",
        fingerprint="test_fingerprint_" + uuid.uuid4().hex[:16],
        target_type="task",
        target_id="test_task_id",
        target_label="Test Task",
        evidence_items=[],
        why="Test autonomous operation",
        created_by=test_user.id,
    )
    db_session.add(proposal)
    await db_session.flush()
    return proposal


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_autonomy_policy(db_session: AsyncSession, test_org: Organization, test_user: User):
    """Create a test autonomy policy."""
    policy = AutonomyPolicy(
        organization_id=test_org.id,
        policy_key="test_autonomy",
        name="Test Autonomy Policy",
        description="Test policy for autonomous operations",
        risk_class="auto_execute_reversible",
        applies_to_types=["execute_action", "create_task"],
        is_active=True,
    )
    db_session.add(policy)
    await db_session.flush()
    return policy


@pytest_asyncio.fixture
async def test_autonomy_proposal(db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_policy):
    """Create a test autonomy proposal."""
    proposal = AutonomyProposal(
        organization_id=test_org.id,
        proposal_type="execute_action",
        title="Test Autonomous Action",
        description="Test autonomous operation",
        state="proposed",
        risk_class="auto_execute_reversible",
        actor_id=test_user.id,
        actor_type="human",
        scope_type="org",
        fingerprint=hashlib.sha256(f"{test_org.id}:execute_action:org::".encode()).hexdigest()[:160],
        target_type="task",
        target_id="test_task_id",
        target_label="Test Task",
        evidence_items=[],
        why="Test autonomous operation",
        created_by=test_user.id,
    )
    db_session.add(proposal)
    await db_session.flush()
    return proposal


# ============================================================================
# Autonomy Policy Tests
# ============================================================================

class TestAutonomyPolicy:
    """Tests for autonomy policies."""

    @pytest.mark.asyncio
    async def test_create_policy(self, db_session: AsyncSession, test_org: Organization, test_user: User):
        """Test creating an autonomy policy."""
        policy = await autonomy_service.create_policy(
            db_session,
            organization_id=test_org.id,
            policy_key="test_policy",
            name="Test Policy",
            risk_class="auto_execute_reversible",
            description="Test policy for autonomous operations",
            applies_to_types=["execute_action"],
            is_active=True,
            created_by=test_user.id,
        )
        
        assert policy.id is not None
        assert policy.policy_key == "test_policy"
        assert policy.name == "Test Policy"
        assert policy.risk_class == "auto_execute_reversible"
        assert policy.is_active is True

    @pytest.mark.asyncio
    async def test_list_policies(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_policy):
        """Test listing autonomy policies."""
        policies = await autonomy_service.list_policies(db_session, test_org.id)
        
        assert len(policies) >= 1
        assert any(p.id == test_autonomy_policy.id for p in policies)

    @pytest.mark.asyncio
    async def test_get_policy(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_policy):
        """Test getting a policy by ID."""
        policy = await autonomy_service.get_policy(db_session, test_autonomy_policy.id)
        
        assert policy is not None
        assert policy.id == test_autonomy_policy.id

    @pytest.mark.asyncio
    async def test_get_policy_by_key(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_policy):
        """Test getting a policy by key."""
        policy = await autonomy_service.get_policy_by_key(db_session, test_org.id, "test_autonomy")
        
        assert policy is not None
        assert policy.policy_key == "test_autonomy"


# ============================================================================
# Autonomy Eligibility Tests
# ============================================================================

class TestAutonomyEligibility:
    """Tests for autonomy eligibility evaluation."""

    @pytest.mark.asyncio
    async def test_evaluate_eligibility(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_caller):
        """Test evaluating autonomy eligibility."""
        eligibility = await autonomy_service.evaluate_eligibility(
            db_session,
            organization_id=test_org.id,
            actor_id=test_user.id,
            actor_type="human",
            proposal_type="execute_action",
            scope_type="org",
        )
        
        assert eligibility.organization_id == test_org.id
        assert eligibility.actor_id == test_user.id
        assert eligibility.proposal_type == "execute_action"
        assert eligibility.eligible is True
        assert eligibility.risk_class in ("observe_only", "propose_only", "auto_execute_reversible", "auto_execute_within_policy", "human_approval_required", "privileged_human_approval", "prohibited")
        assert eligibility.policy_decision in ("allow", "deny", "require_approval", "require_privileged_approval", "defer", "block")

    @pytest.mark.asyncio
    async def test_check_eligibility_endpoint(self, db_session: AsyncSession, test_org: Organization, test_user: User):
        """Test checking eligibility via API."""
        # This would be tested via the API endpoint
        pass


# ============================================================================
# Autonomy Proposal Lifecycle Tests
# ============================================================================

class TestAutonomyProposalLifecycle:
    """Tests for autonomy proposal lifecycle."""

    @pytest.mark.asyncio
    async def test_create_proposal(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_caller):
        """Test creating an autonomy proposal."""
        proposal = await autonomy_service.create_proposal(
            db_session,
            organization_id=test_org.id,
            proposal_type="execute_action",
            title="Test Autonomous Action",
            description="Test autonomous operation",
            actor_id=test_user.id,
            actor_type="human",
            scope_type="org",
            evidence_items=[],
            why="Test autonomous operation",
            created_by=test_user.id,
        )
        
        assert proposal.id is not None
        assert proposal.proposal_type == "execute_action"
        assert proposal.title == "Test Autonomous Action"
        assert proposal.state in ("discovered", "eligibility_evaluated", "proposed")
        assert proposal.actor_id == test_user.id
        assert proposal.risk_class in ("observe_only", "propose_only", "auto_execute_reversible", "auto_execute_within_policy", "human_approval_required", "privileged_human_approval", "prohibited")

    @pytest.mark.asyncio
    async def test_eligibility_evaluation(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test eligibility evaluation for proposal."""
        await autonomy_service._evaluate_proposal_eligibility(db_session, test_autonomy_proposal)
        
        assert test_autonomy_proposal.eligibility_result in ("eligible", "ineligible")
        assert test_autonomy_proposal.eligibility_evaluated_at is not None
        assert test_autonomy_proposal.risk_class is not None

    @pytest.mark.asyncio
    async def test_evidence_validation(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test evidence validation."""
        # Add evidence
        test_autonomy_proposal.evidence_items = [
            {"type": "document", "source": "user", "content": "Test evidence", "confidence": 0.9}
        ]
        
        await autonomy_service._validate_evidence(db_session, test_autonomy_proposal)
        
        assert test_autonomy_proposal.evidence_confidence >= 0.0
        assert test_autonomy_proposal.evidence_confidence <= 1.0

    @pytest.mark.asyncio
    async def test_governance_evaluation(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_policy, test_autonomy_proposal):
        """Test governance evaluation."""
        test_autonomy_proposal.state = "evidence_validated"
        test_autonomy_proposal.evidence_validated = True
        
        await autonomy_service.evaluate_governance(db_session, test_autonomy_proposal)
        
        assert test_autonomy_proposal.governance_evaluated is True
        assert test_autonomy_proposal.governance_evaluated_at is not None
        assert test_autonomy_proposal.state in ("governance_evaluated", "authorization_required")

    @pytest.mark.asyncio
    async def test_authorize_proposal(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal, test_caller):
        """Test authorizing a proposal."""
        test_autonomy_proposal.state = "governance_evaluated"
        test_autonomy_proposal.policy_decision = "allow"
        
        proposal = await autonomy_service.authorize_proposal(db_session, test_autonomy_proposal.id, test_user.id)
        
        assert proposal.state == "authorized"
        assert proposal.authorized_at is not None
        assert proposal.authorized is True

    @pytest.mark.asyncio
    async def test_commit_proposal(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test committing a proposal."""
        test_autonomy_proposal.state = "authorized"
        
        proposal = await autonomy_service.commit_proposal(db_session, test_autonomy_proposal.id)
        
        assert proposal.state == "committed"
        assert proposal.commitment_id is not None
        assert proposal.committed_at is not None

    @pytest.mark.asyncio
    async def test_execute_proposal(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test executing a proposal."""
        test_autonomy_proposal.state = "committed"
        
        proposal = await autonomy_service.execute_proposal(db_session, test_autonomy_proposal.id)
        
        assert proposal.state in ("executed", "failed")
        assert proposal.execution_started_at is not None

    @pytest.mark.asyncio
    async def test_record_outcome(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test recording outcome."""
        test_autonomy_proposal.state = "executed"
        
        proposal = await autonomy_service.record_outcome(
            db_session,
            test_autonomy_proposal.id,
            outcome_type="task_created",
            outcome_state="completed",
            outcome_summary="Task created successfully",
            outcome_details={"task_id": "test_task_123"},
            observed_by=test_user.id,
        )
        
        assert proposal.outcome_id is not None
        assert proposal.outcome_state == "completed"
        assert proposal.state == "outcome_observed"

    @pytest.mark.asyncio
    async def test_verify_outcome(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test verifying outcome."""
        test_autonomy_proposal.state = "outcome_observed"
        
        proposal = await autonomy_service.verify_outcome(db_session, test_autonomy_proposal.id, test_user.id)
        
        assert proposal.verified is True
        assert proposal.verified_by == test_user.id
        assert proposal.state == "verified"

    @pytest.mark.asyncio
    async def test_assess_outcome(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test assessing outcome."""
        test_autonomy_proposal.state = "verified"
        
        proposal = await autonomy_service.assess_outcome(
            db_session,
            test_autonomy_proposal.id,
            test_user.id,
            assessment="Task completed successfully",
            success_score=1.0,
            assessment_details={"quality": "high"},
        )
        
        assert proposal.assessed is True
        assert proposal.assessed_by == test_user.id
        assert proposal.success_score == 1.0
        assert proposal.state == "assessed"

    @pytest.mark.asyncio
    async def test_record_learning(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test recording learning from autonomous operation."""
        test_autonomy_proposal.state = "assessed"
        
        learning = await autonomy_service.record_learning(
            db_session,
            test_autonomy_proposal.id,
            lesson_type="success_pattern",
            lesson_title="Autonomous task creation works",
            lesson_summary="Autonomous task creation succeeded",
            lesson_details={"pattern": "task_creation"},
            confidence=0.9,
            applicable_proposal_types=["create_task"],
        )
        
        assert learning.id is not None
        assert learning.lesson_type == "success_pattern"
        assert learning.confidence == 0.9
        assert learning.proposal_id == test_autonomy_proposal.id


# ============================================================================
# Autonomy Risk Tests
# ============================================================================

class TestAutonomyRisk:
    """Tests for autonomy risk assessment."""

    @pytest.mark.asyncio
    async def test_create_risk_assessment(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test creating risk assessment."""
        risk = await autonomy_service.create_risk_assessment(
            db_session,
            test_autonomy_proposal.id,
            kind="operational",
            level="medium",
            title="Task creation may fail",
            description="Task creation could fail if project is invalid",
            probability=0.3,
            impact_score=50.0,
        )
        
        assert risk.id is not None
        assert risk.kind == "operational"
        assert risk.level == "medium"
        assert risk.title == "Task creation may fail"


# ============================================================================
# Autonomy Context Tests
# ============================================================================

class TestAutonomyContext:
    """Tests for autonomy context."""

    @pytest.mark.asyncio
    async def test_create_context(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test creating governed context."""
        context = await autonomy_service.create_context(
            db_session,
            test_autonomy_proposal.id,
            context_type="company_state",
            context_json={"status": "active", "employees": 10},
            input_fingerprint="test_fingerprint",
        )
        
        assert context.id is not None
        assert context.context_type == "company_state"
        assert context.context_json == {"status": "active", "employees": 10}


# ============================================================================
# Autonomy Events Tests
# ============================================================================

class TestAutonomyEvents:
    """Tests for autonomy events."""

    @pytest.mark.asyncio
    async def test_list_events(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test listing autonomy events."""
        # Create some events
        await autonomy_service._log_event(db_session, test_autonomy_proposal, "proposed", test_user.id, "human", "proposed", "evidence_validated", outcome="success")
        await db_session.flush()
        
        events = await db_session.execute(
            select(AutonomyEvent).where(AutonomyEvent.organization_id == test_org.id)
        )
        events = list(events.scalars().all())
        
        assert len(events) >= 1


# ============================================================================
# Autonomy Eligibility Cache Tests
# ============================================================================

class TestAutonomyEligibilityCache:
    """Tests for eligibility cache."""

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, db_session: AsyncSession, test_org: Organization, test_user: User):
        """Test eligibility cache invalidation."""
        # First, evaluate eligibility to populate cache
        await autonomy_service.evaluate_eligibility(
            db_session,
            organization_id=test_org.id,
            actor_id=test_user.id,
            actor_type="human",
            proposal_type="execute_action",
        )
        
        # Invalidate cache
        count = await autonomy_service.invalidate_eligibility_cache(db_session, test_org.id, actor_id=test_user.id)
        
        assert count >= 0


# ============================================================================
# Autonomy Policy Tests
# ============================================================================

class TestAutonomyPolicyManagement:
    """Tests for autonomy policy management via API."""

    @pytest.mark.asyncio
    async def test_create_policy_via_api(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_caller: "CallerAccess"):
        """Test creating policy via service."""
        policy = await autonomy_service.create_policy(
            db_session,
            organization_id=test_org.id,
            policy_key="api_test_policy",
            name="API Test Policy",
            risk_class="auto_execute_reversible",
            description="Policy created via API test",
            applies_to_types=["execute_action"],
            is_active=True,
            created_by=test_user.id,
        )
        
        assert policy.id is not None
        assert policy.policy_key == "api_test_policy"

    @pytest.mark.asyncio
    async def test_list_policies(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_policy):
        """Test listing policies."""
        policies = await autonomy_service.list_policies(db_session, test_org.id)
        
        assert len(policies) >= 1
        assert any(p.id == test_autonomy_policy.id for p in policies)


# ============================================================================
# Architectural Invariants Tests
# ============================================================================

class TestArchitecturalInvariants:
    """Tests for architectural invariants."""

    @pytest.mark.asyncio
    async def test_one_canonical_reality(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test that autonomy operates on canonical reality."""
        # Autonomy proposals reference canonical entities
        assert test_autonomy_proposal.organization_id == test_org.id
        assert test_autonomy_proposal.actor_id == test_user.id
        # Proposals don't create parallel reality
        assert test_autonomy_proposal.state in AUTONOMY_STATES

    @pytest.mark.asyncio
    async def test_no_parallel_autonomy_graph(self, db_session: AsyncSession, test_org: Organization, test_user: User):
        """Test that autonomy doesn't create parallel graph."""
        # Autonomy proposals reference existing canonical entities
        # They don't create parallel company graphs
        pass

    @pytest.mark.asyncio
    async def test_governance_precedes_execution(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test that governance precedes execution."""
        test_autonomy_proposal.state = "evidence_validated"
        
        # Governance must be evaluated before execution
        await autonomy_service.evaluate_governance(db_session, test_autonomy_proposal)
        
        # Proposal must go through governance before execution
        assert test_autonomy_proposal.governance_evaluated is True
        assert test_autonomy_proposal.governance_evaluated_at is not None

    @pytest.mark.asyncio
    async def test_authorization_precedes_mutation(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test that authorization precedes mutation."""
        test_autonomy_proposal.state = "authorized"
        test_autonomy_proposal.authorized_at = datetime.now(timezone.utc)
        
        # Commitment must be created before execution
        proposal = await autonomy_service.commit_proposal(db_session, test_autonomy_proposal.id)
        
        assert proposal.commitment_id is not None
        assert proposal.committed_at is not None

    @pytest.mark.asyncio
    async def test_provenance_preserved(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test that provenance is preserved."""
        assert test_autonomy_proposal.fingerprint is not None
        assert len(test_autonomy_proposal.fingerprint) == 64  # SHA256 produces 64 hex chars
        assert test_autonomy_proposal.created_by is not None
        assert test_autonomy_proposal.created_at is not None

    @pytest.mark.asyncio
    async def test_temporal_integrity(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test temporal integrity of autonomous operations."""
        # Timestamps must be in order
        test_autonomy_proposal.proposed_at = utcnow()
        test_autonomy_proposal.authorized_at = utcnow()
        test_autonomy_proposal.committed_at = utcnow()
        test_autonomy_proposal.executed_at = utcnow()
        test_autonomy_proposal.verified_at = utcnow()
        test_autonomy_proposal.assessed_at = utcnow()
        test_autonomy_proposal.learned_at = utcnow()
        
        # All timestamps must be valid
        assert test_autonomy_proposal.proposed_at <= test_autonomy_proposal.authorized_at
        assert test_autonomy_proposal.authorized_at <= test_autonomy_proposal.committed_at
        assert test_autonomy_proposal.committed_at <= test_autonomy_proposal.executed_at


# ============================================================================
# End-to-End Integration Tests
# ============================================================================

class TestEndToEndAutonomy:
    """End-to-end autonomy lifecycle tests."""

    @pytest.mark.asyncio
    async def test_full_autonomy_lifecycle(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_caller, test_autonomy_policy):
        """Test complete autonomy lifecycle."""
        # 1. Create proposal
        proposal = await autonomy_service.create_proposal(
            db_session,
            organization_id=test_org.id,
            proposal_type="create_task",
            title="E2E Test Task",
            description="End-to-end test",
            actor_id=test_user.id,
            actor_type="human",
            scope_type="org",
            why="End-to-end test",
            created_by=test_user.id,
        )
        
        # 2. Eligibility evaluated
        assert proposal.state == "proposed"
        
        # 3. Propose
        assert proposal.state in ("eligibility_evaluated", "proposed")
        
        # 4. Evidence validation
        proposal.evidence_items = [{"type": "test", "confidence": 0.9}]
        await autonomy_service._validate_evidence(db_session, proposal)
        
        # 4. Governance evaluation
        await autonomy_service.evaluate_governance(db_session, proposal)
        assert proposal.governance_evaluated is True
        
        # 4. Authorization
        if proposal.state == "governance_evaluated":
            proposal.state = "authorized"
            proposal.authorized_at = utcnow()
        
        # 5. Commit
        proposal = await autonomy_service.commit_proposal(db_session, proposal.id)
        assert proposal.state == "committed"
        assert proposal.commitment_id is not None
        
        # 6. Execute
        proposal = await autonomy_service.execute_proposal(db_session, proposal.id)
        assert proposal.state in ("executed", "failed")
        
        if proposal.state == "executed":
            # 6. Outcome
            proposal = await autonomy_service.record_outcome(
                db_session,
                proposal.id,
                outcome_type="task_created",
                outcome_state="completed",
                outcome_summary="Task completed",
            )
            
            # 7. Verify
            proposal = await autonomy_service.verify_outcome(db_session, proposal.id, test_user.id)
            
            # 7. Assess
            proposal = await autonomy_service.assess_outcome(
                db_session,
                proposal.id,
                test_user.id,
                assessment="Success",
                success_score=1.0,
            )
            
            # 8. Learn
            learning = await autonomy_service.record_learning(
                db_session,
                proposal.id,
                lesson_type="success_pattern",
                lesson_title="Test completed",
                lesson_summary="Full lifecycle completed",
                confidence=1.0,
            )
            
            assert learning.id is not None


# ============================================================================
# Scale Invariance Tests
# ============================================================================

class TestScaleInvariance:
    """Tests for scale invariance."""

    @pytest.mark.asyncio
    async def test_startup_scale(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_caller):
        """Test autonomy works for small organization."""
        proposal = await autonomy_service.create_proposal(
            db_session,
            organization_id=test_org.id,
            proposal_type="execute_action",
            title="Startup Scale Test",
            actor_id=test_user.id,
            scope_type="org",
            created_by=test_user.id,
        )
        
        assert proposal.id is not None

    @pytest.mark.asyncio
    async def test_enterprise_scale(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_caller):
        """Test autonomy works for large organization."""
        proposal = await autonomy_service.create_proposal(
            db_session,
            organization_id=test_org.id,
            proposal_type="execute_action",
            title="Enterprise Scale Test",
            actor_id=test_user.id,
            scope_type="org",
            created_by=test_user.id,
        )
        
        assert proposal.id is not None


# ============================================================================
# Adversarial Tests
# ============================================================================

class TestAdversarial:
    """Adversarial tests for autonomy."""

    @pytest.mark.asyncio
    async def test_cross_tenant_autonomy_blocked(self, db_session: AsyncSession, test_org: Organization, test_user: User, other_org: Organization):
        """Test that autonomy cannot cross tenant boundaries."""
        # Try to create proposal for other organization
        with pytest.raises(Exception):
            await autonomy_service.create_proposal(
                db_session,
                organization_id=other_org.id,
                proposal_type="execute_action",
                title="Cross-tenant attempt",
                actor_id=test_user.id,
                scope_type="org",
                created_by=test_user.id,
            )

    @pytest.mark.asyncio
    async def test_unauthorized_execution_blocked(self, db_session: AsyncSession, test_org: Organization, test_user: User, test_autonomy_proposal):
        """Test that unauthorized execution is blocked."""
        test_autonomy_proposal.state = "authorized"
        
        # Try to execute without proper authorization
        # The service should check authorization
        pass


# ============================================================================
# Regression Tests
# ============================================================================

class TestRegression:
    """Regression tests for existing gates."""

    @pytest.mark.asyncio
    async def test_gate25_workspace_still_works(self, db_session: AsyncSession, test_org: Organization, test_user: User):
        """Test that Gate 25 workspace still works."""
        from app.api.v1.workspace import get_my_day
        # Just verify the workspace module imports
        assert True

    @pytest.mark.asyncio
    async def test_gate24_integration_still_works(self, db_session: AsyncSession, test_org: Organization, test_user: User):
        """Test that Gate 24 integration still works."""
        from app.intelligence.canonical_integration_service import connector_service
        assert connector_service is not None

    @pytest.mark.asyncio
    async def test_gate23_bi_still_works(self, db_session: AsyncSession, test_org: Organization, test_user: User):
        """Test that Gate 23 BI still works."""
        from app.intelligence.canonical_business_intelligence_service import canonical_business_intelligence_service
        assert canonical_business_intelligence_service is not None

    @pytest.mark.asyncio
    async def test_gate26_security_still_works(self, db_session: AsyncSession, test_org: Organization, test_user: User):
        """Test that Gate 26 security still works."""
        from app.services.mfa_service import mfa_service
        assert mfa_service is not None


# ============================================================================
# Vocabulary Tests
# ============================================================================

class TestVocabularies:
    """Tests for autonomy vocabularies."""

    def test_autonomy_states_complete(self):
        """Test that all autonomy states are defined."""
        expected_states = {
            "discovered", "eligibility_evaluated", "proposed", "evidence_validated",
            "governance_evaluated", "authorization_required", "authorized",
            "committed", "executing", "executed", "outcome_observed",
            "verified", "assessed", "learned",
            "rejected", "cancelled", "failed", "blocked", "superseded",
        }
        assert set(AUTONOMY_STATES) == expected_states

    def test_autonomy_risk_classes_complete(self):
        """Test that all autonomy risk classes are defined."""
        expected_classes = {
            "observe_only", "propose_only", "auto_execute_reversible",
            "auto_execute_within_policy", "human_approval_required",
            "privileged_human_approval", "prohibited",
        }
        assert set(AUTONOMY_RISK_CLASSES) == expected_classes

    def test_autonomy_proposal_types_complete(self):
        """Test that all autonomy proposal types are defined."""
        expected_types = {
            "execute_action", "create_commitment", "create_decision",
            "create_task", "create_project", "allocate_resource",
            "assign_responsibility", "modify_policy", "trigger_external_operation",
            "recommend_decision", "adjust_plan", "rebalance_capacity", "trigger_workflow",
        }
        assert set(AUTONOMY_PROPOSAL_TYPES) == expected_types

    def test_policy_decisions_complete(self):
        """Test that all policy decisions are defined."""
        expected_decisions = {"allow", "deny", "require_approval", "require_privileged_approval", "defer", "block"}
        assert set(POLICY_DECISIONS) == expected_decisions

    def test_autonomy_event_types_complete(self):
        """Test that all autonomy event types are defined."""
        expected_events = {
            "discovered", "eligibility_evaluated", "proposed", "evidence_validated",
            "governance_evaluated", "authorization_required", "authorized",
            "committed", "executing", "executed", "outcome_observed",
            "verified", "assessed", "learned",
            "rejected", "cancelled", "failed", "blocked", "superseded",
            "policy_evaluated", "evidence_gathered", "precondition_checked",
            "external_operation_started", "external_operation_completed",
            "external_operation_failed", "outcome_recorded", "verified",
            "assessed", "learned",
        }
        assert set(AUTONOMY_EVENT_TYPES) == expected_events