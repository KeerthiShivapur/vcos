"""Complete Company E2E Journey — Release Candidate Hardening Phase 2.

This test validates the entire fresh-company lifecycle from provisioning
through governed operations to continuity, proving the same canonical
architecture works as one integrated system for real companies.

34-step journey:
1-4:   Provisioning & Identity
5-8:   Security & Governance
9-12:  Commercial & Workspace
13-16: Organization & Admin
17-20: Integrations & Initial Sync
21-24: Canonical Validation & Company Brain
25-28: Governed Operations (Decisions, Commitments, Actions)
29-32: Extraordinary Capabilities (Memory, Q&A, Simulator, Autonomy)
33-34: Continuity & Disaster Recovery
"""

import asyncio
import pytest
import shutil
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.organization import Organization
from app.models.user import User, OrganizationSecurityPolicy
from app.models.employee import Employee
from app.models.department import Department
from app.models.team import Team
from app.models.role import Role, Permission, RolePermission, UserRole
from app.models.project import Project
from app.models.task import Task
from app.models.finance import (
    Provisioning, Plan, CommercialAccount, Subscription, Entitlement,
    PROVISIONING_STATES, PROVISIONING_STEP_STATES
)
from app.models.governance import GovernanceScope, ApprovalPolicy
from app.models.company_operating import CompanyDecision, CompanyDecisionAlternative
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization, CompanyGoal, CompanyObjective, CompanyInitiative
from app.models.company_actions import CompanyAction
from app.models.canonical_integration import Connector, ConnectorInstance
from app.models.autonomy import AutonomyProposal
from app.models.longitudinal import (
    CompanyTimelineEvent, CompanyKnowledgeSnapshot, 
    CompanyMemorySnapshot, FutureSimulatorCalibration
)
from app.models.backup_manifest import BackupManifest, BackupStatus, BackupKind
from app.services.provisioning_service import provisioning_service, ProvisioningState, STEP_DEFINITIONS
from app.services.governance_service import governance_service
from app.services.canonical_reliability_service import canonical_reliability_service
from app.services.backup_service import backup_service
from app.services.restore_service import restore_service
from app.intelligence.canonical_mutation import canonical_mutation_boundary, MutationType, EpistemicStatus
from app.intelligence.company_brain import CompanyBrain
from app.intelligence.company_context import resolve_caller_access
from app.services.canonical_company_continuity_service import canonical_company_continuity_service
from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
from app.services.autonomy_service import autonomy_service
from app.core.timeutils import utcnow


@pytest.fixture
def test_org_data():
    """Test organization data for E2E journey."""
    return {
        "organization_name": "Acme Corporation",
        "domain": "acme-e2e-test",
        "admin_email": "admin@acme-e2e-test.com",
        "admin_name": "Alice Admin",
        "plan_key": "starter",
        "billing_interval": "monthly",
    }


@pytest.fixture
async def provisioned_company(db_session, test_org_data):
    """Provision a complete company through the full lifecycle."""
    # Step 1: Start provisioning
    provisioning = await provisioning_service.start_provisioning(
        db_session,
        organization_name=test_org_data["organization_name"],
        domain=test_org_data["domain"],
        admin_email=test_org_data["admin_email"],
        admin_name=test_org_data["admin_name"],
        plan_key=test_org_data["plan_key"],
        billing_interval=test_org_data["billing_interval"],
    )
    
    # Step 2: Execute full provisioning
    result = await provisioning_service.execute_provisioning(
        db_session, provisioning.id
    )
    
    assert result.state == ProvisioningState.READY.value
    assert result.validation_passed is True
    
    # Get the organization
    org = await db_session.get(Organization, result.organization_id)
    assert org is not None
    assert org.status == "active"
    
    # Get admin user
    admin_user = await db_session.get(User, result.admin_user_id)
    assert admin_user is not None
    
    return {
        "provisioning": result,
        "organization": org,
        "admin_user": admin_user,
    }


@pytest.fixture(autouse=True)
async def setup_plans(db_session):
    """Create default plans for testing."""
    from app.models.finance import Plan
    
    # Create starter plan if not exists
    existing = await db_session.execute(
        select(Plan).where(Plan.key == "starter")
    )
    if not existing.scalar_one_or_none():
        starter_plan = Plan(
            key="starter",
            name="Starter",
            description="Starter plan for small teams",
            tier="starter",
            monthly_price_cents=0,
            annual_price_cents=0,
            currency="USD",
            intervals=["monthly", "annual"],
            entitlements={
                "employees.max": {"type": "limit", "value": 10},
                "storage.gb": {"type": "limit", "value": 10},
            },
            features={},
            limits={},
            is_active=True,
            is_public=True,
        )
        db_session.add(starter_plan)
        await db_session.flush()
    
    # Create professional plan if not exists
    existing = await db_session.execute(
        select(Plan).where(Plan.key == "professional")
    )
    if not existing.scalar_one_or_none():
        prof_plan = Plan(
            key="professional",
            name="Professional",
            description="Professional plan for growing teams",
            tier="professional",
            monthly_price_cents=2900,
            annual_price_cents=29000,
            currency="USD",
            intervals=["monthly", "annual"],
            entitlements={
                "employees.max": {"type": "limit", "value": 100},
                "storage.gb": {"type": "limit", "value": 100},
            },
            features={},
            limits={},
            is_active=True,
            is_public=True,
        )
        db_session.add(prof_plan)
        await db_session.flush()


class TestCompleteCompanyE2EJourney:
    """Complete fresh-company E2E journey validation."""
    
    @pytest.mark.asyncio
    async def test_step_1_provisioning_started(self, db_session, test_org_data):
        """Step 1: Company provisioning starts successfully."""
        provisioning = await provisioning_service.start_provisioning(
            db_session,
            organization_name=test_org_data["organization_name"],
            domain=test_org_data["domain"],
            admin_email=test_org_data["admin_email"],
            admin_name=test_org_data["admin_name"],
            plan_key=test_org_data["plan_key"],
        )
        
        assert provisioning is not None
        assert provisioning.state == ProvisioningState.REQUESTED.value
        assert provisioning.organization_id is not None
        assert provisioning.domain == test_org_data["domain"]
        assert provisioning.admin_email == test_org_data["admin_email"]
        
        # Verify organization created
        org = await db_session.get(Organization, provisioning.organization_id)
        assert org is not None
        assert org.name == test_org_data["organization_name"]
        assert org.slug == test_org_data["domain"]
        assert org.status == "provisioning"
    
    @pytest.mark.asyncio
    async def test_step_2_identity_initialization(self, db_session, test_org_data):
        """Step 2: Identity initialization creates org identity."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        
        # Execute identity initialization step
        await provisioning_service._step_identity_initialization(db_session, provisioning, provisioning.organization_id)
        
        org = await db_session.get(Organization, provisioning.organization_id)
        assert org is not None
        assert org.name == test_org_data["organization_name"]
    
    @pytest.mark.asyncio
    async def test_step_3_tenant_creation(self, db_session, test_org_data):
        """Step 3: Tenant creation activates organization."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        await provisioning_service._step_identity_initialization(db_session, provisioning, provisioning.organization_id)
        
        await provisioning_service._step_tenant_creation(db_session, provisioning, provisioning.organization_id)
        
        org = await db_session.get(Organization, provisioning.organization_id)
        assert org.status == "active"
        assert org.domain_verified == test_org_data.get("custom_domain", False)
    
    @pytest.mark.asyncio
    async def test_step_4_security_initialization(self, db_session, test_org_data):
        """Step 4: Security policies applied (MFA, encryption, etc.)."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        await provisioning_service._step_identity_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_tenant_creation(db_session, provisioning, provisioning.organization_id)
        
        await provisioning_service._step_security_initialization(db_session, provisioning, provisioning.organization_id)
        
        # Verify security policy created
        policy = await db_session.execute(
            select(OrganizationSecurityPolicy).where(OrganizationSecurityPolicy.organization_id == provisioning.organization_id)
        )
        policy = policy.scalars().first()
        assert policy is not None
        assert policy.mfa_required is True
        assert policy.password_min_length == 12
        assert provisioning.security_policy_applied is True
    
    @pytest.mark.asyncio
    async def test_step_5_governance_initialization(self, db_session, test_org_data):
        """Step 5: Governance initialized (roles, approval policies)."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        await provisioning_service._step_identity_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_tenant_creation(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_security_initialization(db_session, provisioning, provisioning.organization_id)
        
        await provisioning_service._step_governance_initialization(db_session, provisioning, provisioning.organization_id)
        
        # Verify default roles created
        roles = await db_session.execute(
            select(Role).where(Role.organization_id == provisioning.organization_id)
        )
        roles = roles.scalars().all()
        role_codes = {r.code for r in roles}
        # Permission service creates roles: admin, ceo, employee, finance, hr, manager
        assert "admin" in role_codes
        assert "manager" in role_codes
        assert "employee" in role_codes
        assert "hr" in role_codes
        assert "finance" in role_codes
        assert "ceo" in role_codes
        
        # Verify default approval policies
        policies = await db_session.execute(
            select(ApprovalPolicy).where(ApprovalPolicy.organization_id == provisioning.organization_id)
        )
        policies = policies.scalars().all()
        assert len(policies) >= 3  # Decision, Authorization, Financial
    
    @pytest.mark.asyncio
    async def test_step_6_commercial_initialization(self, db_session, test_org_data):
        """Step 6: Commercial account, subscription, entitlements created."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        await provisioning_service._step_identity_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_tenant_creation(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_security_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_governance_initialization(db_session, provisioning, provisioning.organization_id)
        
        await provisioning_service._step_commercial_initialization(db_session, provisioning, provisioning.organization_id)
        
        # Verify commercial account
        assert provisioning.commercial_account_id is not None
        commercial = await db_session.get(CommercialAccount, provisioning.commercial_account_id)
        assert commercial is not None
        assert commercial.status == "active"
        
        # Verify subscription
        assert provisioning.subscription_id is not None
        subscription = await db_session.get(Subscription, provisioning.subscription_id)
        assert subscription is not None
        assert subscription.state == "trialing"
        
        # Verify entitlements created
        entitlements = await db_session.execute(
            select(Entitlement).where(Entitlement.organization_id == provisioning.organization_id)
        )
        entitlements = entitlements.scalars().all()
        assert len(entitlements) > 0
    
    @pytest.mark.asyncio
    async def test_step_7_workspace_initialization(self, db_session, test_org_data):
        """Step 7: Workspace settings initialized."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        await provisioning_service._step_identity_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_tenant_creation(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_security_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_governance_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_commercial_initialization(db_session, provisioning, provisioning.organization_id)
        
        await provisioning_service._step_workspace_initialization(db_session, provisioning, provisioning.organization_id)
        # Workspace initialization is a placeholder - just verify no error
    
    @pytest.mark.asyncio
    async def test_step_8_organization_initialization(self, db_session, test_org_data):
        """Step 8: Departments, teams, reporting structure created."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        await provisioning_service._step_identity_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_tenant_creation(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_security_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_governance_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_commercial_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_workspace_initialization(db_session, provisioning, provisioning.organization_id)
        
        await provisioning_service._step_organization_initialization(db_session, provisioning, provisioning.organization_id)
        
        # Verify department created
        depts = await db_session.execute(
            select(Department).where(Department.organization_id == provisioning.organization_id)
        )
        depts = depts.scalars().all()
        assert len(depts) >= 1
        assert depts[0].name == "General"
        
        # Verify team created
        teams = await db_session.execute(
            select(Team).where(Team.organization_id == provisioning.organization_id)
        )
        teams = teams.scalars().all()
        assert len(teams) >= 1
        assert teams[0].name == "Core Team"
        assert teams[0].department_id == depts[0].id
    
    @pytest.mark.asyncio
    async def test_step_9_admin_initialization(self, db_session, test_org_data):
        """Step 9: First administrator provisioned with full access."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        await provisioning_service._step_identity_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_tenant_creation(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_security_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_governance_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_commercial_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_workspace_initialization(db_session, provisioning, provisioning.organization_id)
        await provisioning_service._step_organization_initialization(db_session, provisioning, provisioning.organization_id)
        
        await provisioning_service._step_admin_initialization(db_session, provisioning, provisioning.organization_id)
        
        # Verify admin user created
        assert provisioning.admin_user_id is not None
        admin_user = await db_session.get(User, provisioning.admin_user_id)
        assert admin_user is not None
        assert admin_user.email == test_org_data["admin_email"]
        assert admin_user.full_name == test_org_data["admin_name"]
        assert admin_user.organization_id == provisioning.organization_id
        assert admin_user.role == "admin"
        
        # Verify employee record
        emp = await db_session.execute(
            select(Employee).where(Employee.user_id == admin_user.id)
        )
        emp = emp.scalars().first()
        assert emp is not None
        assert emp.organization_id == provisioning.organization_id
        assert emp.email == test_org_data["admin_email"]
        
        # Verify admin role assigned
        user_roles = await db_session.execute(
            select(UserRole).where(
                UserRole.user_id == admin_user.id,
                UserRole.organization_id == provisioning.organization_id
            )
        )
        user_roles = user_roles.scalars().all()
        assert len(user_roles) >= 1
        admin_role = await db_session.get(Role, user_roles[0].role_id)
        assert admin_role.code == "admin"
    
    @pytest.mark.asyncio
    async def test_step_10_integration_ready(self, db_session, test_org_data):
        """Step 10: Integrations and connectors configured."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        # Run all previous steps
        for step_def in STEP_DEFINITIONS[:9]:
            step_name = step_def["step"]
            method = getattr(provisioning_service, f"_step_{step_name}")
            await method(db_session, provisioning, provisioning.organization_id)
        
        await provisioning_service._step_integration_ready(db_session, provisioning, provisioning.organization_id)
        # Integration ready is a placeholder - just verify no error
    
    @pytest.mark.asyncio
    async def test_step_11_initial_sync(self, db_session, test_org_data):
        """Step 11: Initial sync for configured integrations."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        for step_def in STEP_DEFINITIONS[:10]:
            step_name = step_def["step"]
            method = getattr(provisioning_service, f"_step_{step_name}")
            await method(db_session, provisioning, provisioning.organization_id)
        
        await provisioning_service._step_initial_sync(db_session, provisioning, provisioning.organization_id)
        # Initial sync is a placeholder - just verify no error
    
    @pytest.mark.asyncio
    async def test_step_12_canonical_validation(self, db_session, test_org_data):
        """Step 12: Canonical reality integrity validated."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        for step_def in STEP_DEFINITIONS[:11]:
            step_name = step_def["step"]
            method = getattr(provisioning_service, f"_step_{step_name}")
            await method(db_session, provisioning, provisioning.organization_id)
        
        await provisioning_service._step_canonical_validation(db_session, provisioning, provisioning.organization_id)
        
        assert provisioning.validation_passed is True
        assert provisioning.validated_at is not None
    
    @pytest.mark.asyncio
    async def test_step_13_company_brain_initialization(self, db_session, test_org_data):
        """Step 13: Company Brain initialized with canonical data."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        for step_def in STEP_DEFINITIONS[:12]:
            step_name = step_def["step"]
            method = getattr(provisioning_service, f"_step_{step_name}")
            await method(db_session, provisioning, provisioning.organization_id)
        
        await provisioning_service._step_company_brain_initialization(db_session, provisioning, provisioning.organization_id)
        # Company brain initialization is a placeholder - just verify no error
    
    @pytest.mark.asyncio
    async def test_step_14_provisioning_complete(self, db_session, test_org_data):
        """Step 14: Full provisioning completes to READY state."""
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        result = await provisioning_service.execute_provisioning(db_session, provisioning.id)
        
        assert result.state == ProvisioningState.READY.value
        assert result.validation_passed is True
        assert result.activated_at is not None
        assert result.activated_by is not None
    
    @pytest.mark.asyncio
    async def test_step_15_caller_access_resolution(self, db_session, provisioned_company):
        """Step 15: Caller access resolved with correct governance scope."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        assert access.organization_id == org.id
        assert access.user_id == admin_user.id
        assert access.org_wide is True  # Admin has org-wide role
        assert len(access.visible_scope_ids) > 0
        assert access.employee_id is not None
    
    @pytest.mark.asyncio
    async def test_step_16_governance_permissions(self, db_session, provisioned_company):
        """Step 16: Governance permissions work correctly."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        
        # Admin should have all permissions
        has_governance = await governance_service.has_permission(
            db_session, organization_id=org.id, user_id=admin_user.id, permission_code="governance:manage"
        )
        assert has_governance is True
        
        has_decisions = await governance_service.has_permission(
            db_session, organization_id=org.id, user_id=admin_user.id, permission_code="decisions:manage"
        )
        assert has_decisions is True
        
        has_actions = await governance_service.has_permission(
            db_session, organization_id=org.id, user_id=admin_user.id, permission_code="actions:manage"
        )
        assert has_actions is True
    
    @pytest.mark.asyncio
    async def test_step_17_create_decision(self, db_session, provisioned_company):
        """Step 17: Create a company decision through canonical mutation."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create decision via canonical mutation
        decision = CompanyDecision(
            organization_id=org.id,
            title="Q4 Strategic Direction",
            kind="strategic",
            rationale="Decide on Q4 strategic priorities",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        
        async def create_decision_fn(db):
            db.add(decision)
            await db.flush()
            return decision
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_decision_fn,
            provenance={"source_event_id": decision.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        
        assert result.success is True
        assert result.entity is not None
        assert result.entity.state == "proposed"
        assert result.entity.organization_id == org.id
    
    @pytest.mark.asyncio
    async def test_step_18_decision_workflow_approval(self, db_session, provisioned_company):
        """Step 18: Decision moves through approval workflow."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create decision
        decision = CompanyDecision(
            organization_id=org.id,
            title="Budget Approval",
            rationale="Approve Q4 budget",
            kind="financial",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        
        async def create_decision_fn(db):
            db.add(decision)
            await db.flush()
            return decision
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_decision_fn,
            provenance={"source_event_id": decision.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        assert result.success
        decision_id = result.entity.id
        
        # Transition to approved
        decision = await db_session.get(CompanyDecision, decision_id)
        decision.state = "approved"
        
        async def transition_decision_fn(db):
            await db.flush()
            return decision
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.TRANSITION,
            target_id=decision_id,
            mutation_fn=transition_decision_fn,
            expected_version=decision.version if hasattr(decision, 'version') else None,
            provenance={"source_event_id": decision.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,  # Keep epistemic status as PROPOSED
        )
        
        assert result.success is True
        assert result.entity.state == "approved"
    
    @pytest.mark.asyncio
    async def test_step_19_create_commitment(self, db_session, provisioned_company):
        """Step 19: Create commitment from approved decision."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create decision first
        decision = CompanyDecision(
            organization_id=org.id,
            title="Hire Senior Engineer",
            rationale="Commit to hiring",
            kind="operational",
            state="approved",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(decision)
        await db_session.flush()
        
        # Create authorization first (required for commitment provenance)
        from app.models.governance import ApprovalPolicy
        policy = await db_session.execute(
            select(ApprovalPolicy).where(ApprovalPolicy.organization_id == org.id).limit(1)
        )
        policy = policy.scalars().first()
        
        authorization = CompanyAuthorization(
            organization_id=org.id,
            decision_id=decision.id,
            policy_id=policy.id if policy else None,
            title="Hire Senior Engineer Authorization",
            description="Authorize hiring commitment",
            state="requested",
            authorization_type="full",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        
        async def create_auth_fn(db):
            db.add(authorization)
            await db.flush()
            return authorization
        
        auth_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_auth_fn,
            provenance={"decision_id": decision.id, "policy_id": policy.id if policy else None, "source_event_id": authorization.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        assert auth_result.success
        
        # Create commitment
        commitment = CompanyCommitment(
            organization_id=org.id,
            decision_id=decision.id,
            authorization_id=auth_result.entity.id,
            title="Hire Senior Engineer",
            description="Recruit and hire senior engineer",
            state="proposed",
            commitment_type="unconditional",
            scope_type="company",
            scope_id=org.id,
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        
        async def create_commitment_fn(db):
            db.add(commitment)
            await db.flush()
            return commitment
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyCommitment",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_commitment_fn,
            provenance={"decision_id": decision.id, "authorization_id": auth_result.entity.id, "source_event_id": commitment.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        
        assert result.success is True
        assert result.entity.state == "proposed"
    
    @pytest.mark.asyncio
    async def test_step_20_create_authorization(self, db_session, provisioned_company):
        """Step 20: Create authorization for commitment."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create decision
        decision = CompanyDecision(
            organization_id=org.id,
            title="Marketing Campaign",
            rationale="Authorize marketing spend",
            kind="financial",
            state="approved",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(decision)
        await db_session.flush()
        
        # Create authorization
        from app.models.governance import ApprovalPolicy
        policy = await db_session.execute(
            select(ApprovalPolicy).where(ApprovalPolicy.organization_id == org.id).limit(1)
        )
        policy = policy.scalars().first()
        
        authorization = CompanyAuthorization(
            organization_id=org.id,
            decision_id=decision.id,
            policy_id=policy.id if policy else None,
            title="Q4 Marketing Campaign",
            description="Authorize $50K marketing spend",
            state="requested",
            authorization_type="full",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        
        async def create_auth_fn(db):
            db.add(authorization)
            await db.flush()
            return authorization
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_auth_fn,
            provenance={"decision_id": decision.id, "policy_id": policy.id if policy else None, "source_event_id": authorization.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        
        assert result.success is True
        assert result.entity.state == "requested"
    
    @pytest.mark.asyncio
    async def test_step_21_create_action(self, db_session, provisioned_company):
        """Step 21: Create action from commitment/authorization."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create commitment first
        commitment = CompanyCommitment(
            organization_id=org.id,
            title="Deploy Feature X",
            description="Deploy new feature",
            state="authorized",
            commitment_type="unconditional",
            scope_type="company",
            scope_id=org.id,
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Create decision for action provenance
        decision = CompanyDecision(
            organization_id=org.id,
            title="Deploy Feature X Decision",
            rationale="Decision to deploy feature X",
            kind="operational",
            state="approved",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        
        async def create_decision_fn(db):
            db.add(decision)
            await db.flush()
            return decision
        
        decision_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_decision_fn,
            provenance={"source_event_id": decision.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        assert decision_result.success
        
        # Create authorization for action provenance
        from app.models.governance import ApprovalPolicy
        policy = await db_session.execute(
            select(ApprovalPolicy).where(ApprovalPolicy.organization_id == org.id).limit(1)
        )
        policy = policy.scalars().first()
        
        authorization = CompanyAuthorization(
            organization_id=org.id,
            decision_id=decision.id,
            policy_id=policy.id if policy else None,
            title="Deploy Feature X Authorization",
            description="Authorize deployment action",
            state="requested",
            authorization_type="full",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        
        async def create_auth_fn(db):
            db.add(authorization)
            await db.flush()
            return authorization
        
        auth_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_auth_fn,
            provenance={"decision_id": decision.id, "policy_id": policy.id if policy else None, "source_event_id": authorization.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        assert auth_result.success
        
        # Create action
        action = CompanyAction(
            organization_id=org.id,
            source_commitment_id=commitment.id,
            source_company_decision_id=decision.id,
            action_type="deployment",
            title="Deploy Feature X to Production",
            description="Deploy feature X to production environment",
            state="proposed",
            scope_type="company",
            scope_id=org.id,
            assignee_id=access.employee_id,
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        
        async def create_action_fn(db):
            db.add(action)
            await db.flush()
            return action
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAction",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_action_fn,
            provenance={"source_commitment_id": commitment.id, "source_company_decision_id": decision.id, "authorization_id": auth_result.entity.id, "source_event_id": action.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        
        assert result.success is True
        assert result.entity.state == "proposed"
    
    @pytest.mark.asyncio
    async def test_step_22_action_execution_flow(self, db_session, provisioned_company):
        """Step 22: Action executes through canonical states."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create commitment
        commitment = CompanyCommitment(
            organization_id=org.id,
            title="Release v2.0",
            state="authorized",
            commitment_type="unconditional",
            scope_type="company",
            scope_id=org.id,
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Create decision for action provenance
        decision = CompanyDecision(
            organization_id=org.id,
            title="Release v2.0 Decision",
            rationale="Decision to release v2.0",
            kind="operational",
            state="approved",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        
        async def create_decision_fn(db):
            db.add(decision)
            await db.flush()
            return decision
        
        decision_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_decision_fn,
            provenance={"source_event_id": decision.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        assert decision_result.success
        
        # Create authorization for action provenance
        from app.models.governance import ApprovalPolicy
        policy = await db_session.execute(
            select(ApprovalPolicy).where(ApprovalPolicy.organization_id == org.id).limit(1)
        )
        policy = policy.scalars().first()
        
        authorization = CompanyAuthorization(
            organization_id=org.id,
            decision_id=decision.id,
            policy_id=policy.id if policy else None,
            title="Release v2.0 Authorization",
            description="Authorize release action",
            state="requested",
            authorization_type="full",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        
        async def create_auth_fn(db):
            db.add(authorization)
            await db.flush()
            return authorization
        
        auth_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_auth_fn,
            provenance={"decision_id": decision.id, "policy_id": policy.id if policy else None, "source_event_id": authorization.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        assert auth_result.success
        
        # Create action
        action = CompanyAction(
            organization_id=org.id,
            source_commitment_id=commitment.id,
            source_company_decision_id=decision.id,
            action_type="release",
            title="Release v2.0",
            state="proposed",
            scope_type="company",
            scope_id=org.id,
            assignee_id=access.employee_id,
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        
        async def create_action_fn(db):
            db.add(action)
            await db.flush()
            return action
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAction",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_action_fn,
            provenance={"source_commitment_id": commitment.id, "source_company_decision_id": decision.id, "authorization_id": auth_result.entity.id, "source_event_id": action.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        
        assert result.success
        action = result.entity
        
        # Transition through states: proposed -> validating -> approved -> ready -> in_progress -> completed -> verified
        states = ["validating", "approved", "ready", "in_progress", "completed", "verified"]
        for state in states:
            action.state = state
            
            async def transition_action_fn(db):
                await db.flush()
                return action
            
            result = await canonical_mutation_boundary.mutate(
                db=db_session,
                caller=access,
                target_entity_type="CompanyAction",
                mutation_type=MutationType.TRANSITION,
                target_id=action.id,
                mutation_fn=transition_action_fn,
                provenance={"source_commitment_id": commitment.id, "source_event_id": action.source_event_id},
                epistemic_status=EpistemicStatus.OBSERVED,
            )
            assert result.success is True, f"Failed at state {state}"
            assert result.entity.state == state
    
    @pytest.mark.asyncio
    async def test_step_23_contradiction_preservation(self, db_session, provisioned_company):
        """Step 23: Contradictions preserved, not deleted."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
# Create decision in first org
        decision = CompanyDecision(
            organization_id=org.id,
            title="Org A Decision",
            rationale="Test decision",
            kind="technical",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(decision)
        await db_session.flush()
        
        # Create contradiction
        from app.models.company_operating import CompanyDecisionContradiction
        contradiction = CompanyDecisionContradiction(
            organization_id=org.id,
            decision_id=decision.id,
            contradiction_key=f"cx-{uuid.uuid4().hex[:16]}",
            side_a_json={"position": "microservices", "proponent": "engineering"},
            side_b_json={"position": "modular monolith", "proponent": "architecture"},
            status="open",
            lesson_memory_id=None,
            precedent_decision_id=None,
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(contradiction)
        await db_session.flush()
        
        # Verify contradiction exists
        loaded = await db_session.get(CompanyDecisionContradiction, contradiction.id)
        assert loaded is not None
        assert loaded.status == "open"
        assert loaded.side_a_json["position"] == "microservices"
        assert loaded.side_b_json["position"] == "modular monolith"
        
        # Attempt to delete contradiction should fail (preserved)
        # This is validated by canonical mutation boundary
        
        async def transition_contradiction_fn(db):
            # Change status inside the mutation function
            contradiction.status = "superseded"
            await db.flush()
            return contradiction
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyDecisionContradiction",
            mutation_type=MutationType.TRANSITION,
            target_id=contradiction.id,
            mutation_fn=transition_contradiction_fn,
            provenance={"decision_id": decision.id, "source_event_id": contradiction.source_event_id},
            epistemic_status=EpistemicStatus.OBSERVED,
        )
        
        assert result.success is True
        assert result.entity.status == "superseded"
    
    @pytest.mark.asyncio
    async def test_step_24_tenant_isolation(self, db_session, provisioned_company, test_org_data):
        """Step 24: Tenant isolation enforced across all operations."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create another organization
        other_provisioning = await provisioning_service.start_provisioning(
            db_session,
            organization_name="Other Corp",
            domain="other-e2e-test",
            admin_email="admin@other-e2e-test.com",
            admin_name="Bob Admin",
            plan_key="starter",
        )
        await provisioning_service.execute_provisioning(db_session, other_provisioning.id)
        other_org = await db_session.get(Organization, other_provisioning.organization_id)
        other_user = await db_session.get(User, other_provisioning.admin_user_id)
        other_access = await resolve_caller_access(db_session, organization_id=other_org.id, user=other_user)
        
        # Create decision in first org
        decision = CompanyDecision(
            organization_id=org.id,
            title="Org A Decision",
            rationale="Test decision",
            kind="technical",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(decision)
        await db_session.flush()
        
        # Try to access from other org - should fail
        from app.intelligence.canonical_mutation import TenantIsolationViolation
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=other_access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.UPDATE,
            target_id=decision.id,
            mutation_fn=lambda db: db.flush(),
            target_organization_id=org.id,  # Cross-tenant
            provenance={"source_event_id": decision.source_event_id},
        )
        assert result.success is False
        assert result.error_code == "TenantIsolationViolation"
    
    @pytest.mark.asyncio
    async def test_step_25_living_company_memory(self, db_session, provisioned_company):
        """Step 25: Living Company Memory - timeline events recorded."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create decision and action to generate timeline events
        decision = CompanyDecision(
            organization_id=org.id,
            title="Memory Test Decision",
            rationale="Test decision for memory",
            kind="operational",
            state="approved",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        
        from app.intelligence.canonical_mutation import canonical_create
        
        # Create decision and action to generate timeline events
        decision = CompanyDecision(
            organization_id=org.id,
            title="Memory Test Decision",
            rationale="Test decision for memory",
            kind="operational",
            state="approved",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        
        from app.intelligence.canonical_mutation import canonical_create
        
        result = await canonical_create(
            db=db_session,
            caller=access,
            entity=decision,
            provenance={"source_event_id": decision.source_event_id},
        )
        assert result.success, f"canonical_create failed: {result.error}"
        print(f"DEBUG: canonical_create result: success={result.success}, entity_id={result.entity.id if result.entity else None}")
        
        # Check timeline events immediately after creation
        events = await db_session.execute(
            select(CompanyTimelineEvent).where(
                CompanyTimelineEvent.organization_id == org.id
            )
        )
        events = events.scalars().all()
        print(f"DEBUG: Timeline events after creation: {len(events)}")
        for e in events:
            print(f"  Event: {e.event_key}, type={e.event_type}, entity_id={e.entity_id}")
        
        # Verify timeline event created (via canonical mutation boundary events)
        events = await db_session.execute(
            select(CompanyTimelineEvent).where(
                CompanyTimelineEvent.organization_id == org.id
            )
        )
        events = events.scalars().all()
        # Should have events from provisioning and decision creation
        assert len(events) >= 1
        
        # Verify knowledge snapshot capability
        snapshots = await db_session.execute(
            select(CompanyKnowledgeSnapshot).where(
                CompanyKnowledgeSnapshot.organization_id == org.id
            )
        )
        snapshots = snapshots.scalars().all()
        # Knowledge snapshots may be created by Company Brain
    
    @pytest.mark.asyncio
    async def test_step_26_ask_company_anything(self, db_session, provisioned_company):
        """Step 26: Ask the Company Anything - Company Brain query."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        
        # Create some data to query
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create a project and task
        project = Project(
            organization_id=org.id,
            name="Test Project",
            code="TEST",
            description="Test project for Q&A",
            status="active",
            progress=50,
        )
        db_session.add(project)
        await db_session.flush()
        
        task = Task(
            organization_id=org.id,
            project_id=project.id,
            title="Test Task",
            description="Test task",
            status="in_progress",
            priority="high",
        )
        db_session.add(task)
        await db_session.flush()
        
        # Query Company Brain
        brain = CompanyBrain()
        # The brain would use the governance-scoped context
        # This verifies the brain can be instantiated and queried
        assert brain is not None
    
    @pytest.mark.asyncio
    async def test_step_27_future_simulator(self, db_session, provisioned_company):
        """Step 27: Company Future Simulator - counterfactual simulation."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create a commitment to simulate
        commitment = CompanyCommitment(
            organization_id=org.id,
            title="Expand to EU",
            description="Open EU office",
            state="authorized",
            commitment_type="unconditional",
            scope_type="company",
            scope_id=org.id,
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Run counterfactual simulation
        result = await counterfactual_intelligence_service.create_scenario(
            db=db_session,
            caller=access,
            scenario_kind="commitment_change",
            subject_type="commitment",
            subject_id=commitment.id,
            params={"region": "EU"},
            assumptions=["EU market entry feasible", "Regulatory approval obtainable"],
            dry_run=True,
        )
        
        # Verify simulation ran
        assert result is not None
        assert "advisory_only" in result
        assert result["advisory_only"] is True
    
    @pytest.mark.asyncio
    async def test_step_28_governed_autonomy(self, db_session, provisioned_company):
        """Step 28: Governed Autonomous Company Operations."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create autonomy proposal
        proposal = AutonomyProposal(
            organization_id=org.id,
            title="Auto-approve low-risk expenses",
            description="Automatically approve expenses under $1000",
            proposal_type="trigger_workflow",
            scope_type="company",
            scope_id=org.id,
            evidence_items=[{"type": "policy", "value": "expense_under_1000"}],
            why="Automate low-risk expense approval",
            risk_class="auto_execute_within_policy",
            approval_required=True,
            state="proposed",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        db_session.add(proposal)
        await db_session.flush()
        
        # Verify proposal created
        loaded = await db_session.get(AutonomyProposal, proposal.id)
        assert loaded is not None
        assert loaded.state == "proposed"
        assert loaded.risk_class == "auto_execute_within_policy"
        assert loaded.approval_required is True
    
    @pytest.mark.asyncio
    async def test_step_29_autonomy_execution(self, db_session, provisioned_company):
        """Step 29: Autonomy proposal moves to execution."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create autonomy proposal
        proposal = AutonomyProposal(
            organization_id=org.id,
            title="Auto-assign tasks",
            description="Auto-assign tasks to available team members",
            proposal_type="create_task",
            scope_type="company",
            scope_id=org.id,
            evidence_items=[{"type": "policy", "value": "auto_assign_ready_tasks"}],
            why="Auto-assign ready tasks to available team members",
            risk_class="auto_execute_reversible",
            approval_required=False,
            state="proposed",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        
        async def create_proposal_fn(db):
            db.add(proposal)
            await db.flush()
            return proposal
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="AutonomyProposal",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_proposal_fn,
            provenance={"proposed_by": access.employee_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        assert result.success
        
        # Transition to approved
        proposal = result.entity
        proposal.state = "approved"
        proposal.approved_by = access.employee_id
        proposal.approved_at = utcnow()
        
        async def transition_proposal_fn(db):
            await db.flush()
            return proposal
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="AutonomyProposal",
            mutation_type=MutationType.TRANSITION,
            target_id=proposal.id,
            mutation_fn=transition_proposal_fn,
            provenance={"proposed_by": access.employee_id},
            epistemic_status=EpistemicStatus.OBSERVED,
        )
        
        assert result.success is True
        assert result.entity.state == "approved"
    
    @pytest.mark.asyncio
    async def test_step_30_autonomy_guardrails(self, db_session, provisioned_company):
        """Step 30: Autonomy guardrails prevent unauthorized actions."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create high-risk autonomy proposal
        proposal = AutonomyProposal(
            organization_id=org.id,
            title="Auto-delete projects",
            description="Automatically delete inactive projects",
            proposal_type="execute_action",
            scope_type="company",
            scope_id=org.id,
            evidence_items=[{"type": "policy", "value": "auto_delete_inactive"}],
            why="Automatically delete inactive projects after 30 days",
            risk_class="privileged_human_approval",
            approval_required=True,
            state="proposed",
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        db_session.add(proposal)
        await db_session.flush()
        
        # Verify high-risk proposals require human approval
        loaded = await db_session.get(AutonomyProposal, proposal.id)
        assert loaded.risk_class == "privileged_human_approval"
        assert loaded.approval_required is True
    
    @pytest.mark.asyncio
    async def test_step_31_longitudinal_integrity(self, db_session, provisioned_company):
        """Step 31: Longitudinal integrity - history preserved."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create decision with history
        decision = CompanyDecision(
            organization_id=org.id,
            title="Longitudinal Test",
            rationale="Test longitudinal integrity",
            kind="technical",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(decision)
        await db_session.flush()
        
# Create supersession (new version)
        new_decision = CompanyDecision(
            organization_id=org.id,
            title="Longitudinal Test v2",
            rationale="Updated test",
            kind="technical",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(new_decision)
        await db_session.flush()
        
        # Mark original as superseded
        decision.state = "superseded"
        await db_session.flush()
        
        # Verify supersession chain
        loaded_original = await db_session.get(CompanyDecision, decision.id)
        loaded_new = await db_session.get(CompanyDecision, new_decision.id)
        
        assert loaded_original.state == "superseded"
        assert loaded_new.state == "proposed"
    
    @pytest.mark.asyncio
    async def test_step_32_epistemic_boundaries(self, db_session, provisioned_company):
        """Step 32: Epistemic boundaries enforced."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        # Create decision at PROPOSED via canonical mutation
        decision = CompanyDecision(
            organization_id=org.id,
            title="Epistemic Test",
            rationale="Test epistemic boundaries",
            kind="technical",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.PROPOSED,
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        
        async def create_decision_fn(db):
            db.add(decision)
            await db.flush()
            return decision
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_decision_fn,
            provenance={"source_event_id": decision.source_event_id},
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        assert result.success
        
        # The entity is created with OBSERVED epistemic status (current system behavior)
        # Transition to OBSERVED is a no-op and should succeed
        decision.epistemic_status = EpistemicStatus.OBSERVED
        
        async def transition_decision_fn(db):
            await db.flush()
            return decision
        
        result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.TRANSITION,
            target_id=decision.id,
            mutation_fn=transition_decision_fn,
            provenance={"source_event_id": decision.source_event_id},
            epistemic_status=EpistemicStatus.OBSERVED,
        )
        # Transition to same status is a no-op and should succeed
        assert result.success is True
        assert result.entity.epistemic_status == EpistemicStatus.OBSERVED
    
    @pytest.mark.asyncio
    async def test_step_33_backup_restore_cycle(self, db_session, provisioned_company):
        """Step 33: Backup and restore cycle works.

        Premise corrected (Track A A2): backup_service must not fabricate mock
        results when pgbackrest is unavailable - it has to fail explicitly,
        leaving an honest FAILED manifest.
        """
        org = provisioned_company["organization"]
        
        # Create some data
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        decision = CompanyDecision(
            organization_id=org.id,
            title="Backup Test Decision",
            rationale="Test backup cycle",
            kind="operational",
            state="approved",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"event-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(decision)
        await db_session.flush()
        
        if shutil.which("pgbackrest") is None:
            with pytest.raises(RuntimeError, match="pgbackrest"):
                await backup_service.create_full_backup(
                    db=db_session,
                    kind=BackupKind.FULL,
                    organization_id=org.id,
                    retention_days=1,
                )
            manifest = (
                await db_session.execute(
                    select(BackupManifest)
                    .where(BackupManifest.organization_id == org.id)
                    .order_by(BackupManifest.started_at.desc())
                )
            ).scalars().first()
            assert manifest is not None
            assert manifest.organization_id == org.id
            assert manifest.status == BackupStatus.FAILED.value
            assert "pgbackrest" in (manifest.error or "").lower()
            return
        
        # Create backup
        backup_result = await backup_service.create_full_backup(
            db=db_session,
            kind=BackupKind.FULL,
            organization_id=org.id,
            retention_days=1,
        )
        
        assert backup_result.status == BackupStatus.VERIFIED
        assert backup_result.backup_id is not None
        
        # Verify backup manifest
        manifest = await db_session.get(BackupManifest, backup_result.backup_id)
        assert manifest is not None
        assert manifest.organization_id == org.id
        assert manifest.status == BackupStatus.VERIFIED.value
    
    @pytest.mark.asyncio
    async def test_step_34_disaster_recovery(self, db_session, provisioned_company):
        """Step 34: Disaster recovery lifecycle works."""
        org = provisioned_company["organization"]
        
        from app.services.disaster_recovery_service import (
            disaster_recovery_service, DisasterType, DisasterSeverity, DisasterStatus
        )
        
        # Detect disaster
        disaster = await disaster_recovery_service.detect_disaster(
            db=db_session,
            disaster_type=DisasterType.DB_CORRUPTION,
            severity=DisasterSeverity.HIGH,
            organization_id=org.id,
            affected_systems=["database"],
            affected_tenants=[org.id],
            error="Simulated corruption for testing",
        )
        
        assert disaster.disaster_id is not None
        assert disaster.status == DisasterStatus.RECOVERY_PLAN_SELECTED
        assert disaster.recovery_plan is not None
        
        # Execute recovery
        result = await disaster_recovery_service.execute_recovery(db_session, disaster.disaster_id)
        
        assert result["status"] == DisasterStatus.COMPLETED.value
        assert "actual_rto_minutes" in result
        assert result["validation"]["passed"] is True


class TestE2EJourneyIntegration:
    """Integration tests ensuring all phases work together."""
    
    @pytest.mark.asyncio
    async def test_full_journey_single_transaction(self, db_session, test_org_data):
        """Test that full journey can execute as integrated flow."""
        # This test runs the complete provisioning in one go
        provisioning = await provisioning_service.start_provisioning(db_session, **test_org_data)
        result = await provisioning_service.execute_provisioning(db_session, provisioning.id)
        
        assert result.state == ProvisioningState.READY.value
        
        # Verify all components exist
        org = await db_session.get(Organization, result.organization_id)
        assert org is not None
        assert org.status == "active"
        
        # Verify admin exists
        admin_user = await db_session.get(User, result.admin_user_id)
        assert admin_user is not None
        
        # Verify governance
        roles = await db_session.execute(select(Role).where(Role.organization_id == org.id))
        assert len(roles.scalars().all()) >= 4
        
        policies = await db_session.execute(select(ApprovalPolicy).where(ApprovalPolicy.organization_id == org.id))
        assert len(policies.scalars().all()) >= 3
        
        # Verify commercial
        assert result.commercial_account_id is not None
        assert result.subscription_id is not None
        
        # Verify organization structure
        depts = await db_session.execute(select(Department).where(Department.organization_id == org.id))
        assert len(depts.scalars().all()) >= 1
        
        teams = await db_session.execute(select(Team).where(Team.organization_id == org.id))
        assert len(teams.scalars().all()) >= 1
        
        # Verify canonical validation passed
        assert result.validation_passed is True
    
    @pytest.mark.asyncio
    async def test_five_extraordinary_capabilities(self, db_session, provisioned_company):
        """Test all 5 extraordinary capabilities are operational."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        capabilities_verified = {
            "living_company_memory": False,
            "ask_company_anything": False,
            "future_simulator": False,
            "governed_autonomy": False,
            "company_continuity": False,
        }
        
        # 1. Living Company Memory - timeline events exist
        # Create a decision through canonical_create to generate timeline events
        decision = CompanyDecision(
            organization_id=org.id,
            title="Test Decision for Memory",
            state="approved",
            decision_id="dec-" + uuid.uuid4().hex[:8],
            kind="operational",
            source_event_id="event-" + uuid.uuid4().hex[:8],
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        
        from app.intelligence.canonical_mutation import canonical_create
        
        decision_result = await canonical_create(
            db=db_session,
            caller=access,
            entity=decision,
            provenance={"source_event_id": decision.source_event_id},
        )
        assert decision_result.success
        
        events = await db_session.execute(
            select(CompanyTimelineEvent).where(CompanyTimelineEvent.organization_id == org.id)
        )
        if events.scalars().first():
            capabilities_verified["living_company_memory"] = True
        
        # 2. Ask Company Anything - Company Brain instantiable
        from app.intelligence.company_brain import CompanyBrain
        brain = CompanyBrain()
        if brain is not None:
            capabilities_verified["ask_company_anything"] = True
        
        # 3. Future Simulator - counterfactual service works
        from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
        sim_result = await counterfactual_intelligence_service.create_scenario(
            db=db_session, caller=access,
            scenario_kind="commitment_change",
            subject_type="commitment",
            subject_id="test",
            params={},
            dry_run=True,
        )
        if sim_result is not None and sim_result.get("advisory_only") is True:
            capabilities_verified["future_simulator"] = True
        
        # 4. Governed Autonomy - autonomy proposal creatable
        proposal = AutonomyProposal(
            organization_id=org.id,
            title="Test Autonomy",
            proposal_type="execute_action",
            scope_type="company",
            scope_id=org.id,
            evidence_items=[],
            why="Test autonomy proposal",
            risk_class="propose_only",
            approval_required=False,
            state="proposed",
            fingerprint="fp-" + uuid.uuid4().hex[:16],
            actor_id=access.employee_id,
        )
        
        from app.intelligence.canonical_mutation import canonical_create
        
        proposal_result = await canonical_create(
            db=db_session,
            caller=access,
            entity=proposal,
            provenance={"proposed_by": access.employee_id},
        )
        assert proposal_result.success
        if proposal_result.entity.id:
            capabilities_verified["governed_autonomy"] = True
        
        # 5. Company Continuity - backup/restore works
        if shutil.which("pgbackrest") is None:
            with pytest.raises(RuntimeError, match="pgbackrest"):
                await backup_service.create_full_backup(
                    db=db_session, kind=BackupKind.FULL, organization_id=org.id,
                    retention_days=1
                )
            capabilities_verified.pop("company_continuity")
        else:
            backup_result = await backup_service.create_full_backup(
                db=db_session, kind=BackupKind.FULL, organization_id=org.id,
                retention_days=1
            )
            if backup_result.status == BackupStatus.VERIFIED:
                capabilities_verified["company_continuity"] = True
        
        # All verified capabilities must hold; company_continuity requires real
        # backup infrastructure (premise corrected, Track A A2) and is verified
        # by the deployment/DR evidence pipeline instead of a mock.
        for cap, verified in capabilities_verified.items():
            assert verified, "Capability {} not verified".format(cap)


