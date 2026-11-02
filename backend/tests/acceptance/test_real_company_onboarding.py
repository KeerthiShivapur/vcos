"""Real Company Onboarding Acceptance Tests.

Tests the complete company onboarding journey from creation to ready state.
"""

import sys
print(">>> MODULE LOADED: test_real_company_onboarding.py", file=sys.stderr, flush=True)

import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.services.onboarding_service import (
    onboarding_service,
    OnboardingContext,
    OnboardingPhase,
)
from app.services.provisioning_service import provisioning_service, ProvisioningState
from app.services.auth_service import auth_service
from app.services.organization_service import organization_service
from app.core.timeutils import utcnow


# =============================================================================
# FIXTURES
# =============================================================================

async def _clean_provisionings(pg_db_session: AsyncSession):
    """Clean provisionings and related tables before each test."""
    from sqlalchemy import delete, text
    from app.models.finance import Plan
    from app.models.workspace import WorkspaceItem, Workspace
    from app.models.invitation import Invitation
    from app.models.canonical_integration import ConnectorInstance
    from app.models.finance import Provisioning, Subscription, CommercialAccount, Plan
    from app.models.role import UserRole, Role
    from app.models.employee import Employee
    from app.models.team import Team
    from app.models.department import Department
    from app.models.user import User
    from app.models.organization import Organization
    from app.core.timeutils import utcnow
    
    # Use DELETE statements for reliable cleanup (handles FK constraints better)
    # Delete in order to respect foreign key constraints
    try:
        result = await pg_db_session.execute(delete(WorkspaceItem))
        print(f"DEBUG: Deleted {result.rowcount} WorkspaceItems")
        result = await pg_db_session.execute(delete(Workspace))
        print(f"DEBUG: Deleted {result.rowcount} Workspaces")
        result = await pg_db_session.execute(delete(Invitation))
        print(f"DEBUG: Deleted {result.rowcount} Invitations")
        result = await pg_db_session.execute(delete(ConnectorInstance))
        print(f"DEBUG: Deleted {result.rowcount} ConnectorInstances")
        result = await pg_db_session.execute(delete(Provisioning))
        print(f"DEBUG: Deleted {result.rowcount} Provisionings")
        result = await pg_db_session.execute(delete(Subscription))
        print(f"DEBUG: Deleted {result.rowcount} Subscriptions")
        result = await pg_db_session.execute(delete(CommercialAccount))
        print(f"DEBUG: Deleted {result.rowcount} CommercialAccounts")
        result = await pg_db_session.execute(delete(Plan))
        print(f"DEBUG: Deleted {result.rowcount} Plans")
        result = await pg_db_session.execute(delete(UserRole))
        print(f"DEBUG: Deleted {result.rowcount} UserRoles")
        result = await pg_db_session.execute(delete(Role))
        print(f"DEBUG: Deleted {result.rowcount} Roles")
        result = await pg_db_session.execute(delete(Employee))
        print(f"DEBUG: Deleted {result.rowcount} Employees")
        result = await pg_db_session.execute(delete(Team))
        print(f"DEBUG: Deleted {result.rowcount} Teams")
        result = await pg_db_session.execute(delete(Department))
        print(f"DEBUG: Deleted {result.rowcount} Departments")
        result = await pg_db_session.execute(delete(User))
        print(f"DEBUG: Deleted {result.rowcount} Users")
        result = await pg_db_session.execute(delete(Organization))
        print(f"DEBUG: Deleted {result.rowcount} Organizations")
        await pg_db_session.commit()
        print(f"DEBUG: Cleanup committed successfully")
        
        # Verify cleanup
        result = await pg_db_session.execute(text("SELECT count(*) FROM organizations"))
        print(f"DEBUG: Organizations count after cleanup: {result.scalar()}")
        result = await pg_db_session.execute(text("SELECT count(*) FROM users"))
        print(f"DEBUG: Users count after cleanup: {result.scalar()}")
    except Exception as e:
        print(f"DEBUG: Cleanup failed with error: {e}")
        await pg_db_session.rollback()
        raise
    
    # Re-seed the default plans
    starter_plan = Plan(
        key="starter",
        name="Starter",
        description="Starter plan for small teams",
        tier="starter",
        monthly_price_cents=0,
        annual_price_cents=0,
        currency="USD",
        entitlements={"users": {"type": "limit", "value": 10}, "storage_gb": {"type": "limit", "value": 5}},
        is_active=True,
        is_public=True,
        trial_days=14,
    )
    professional_plan = Plan(
        key="professional",
        name="Professional",
        description="Professional plan for growing teams",
        tier="professional",
        monthly_price_cents=2900,
        annual_price_cents=29000,
        currency="USD",
        entitlements={"users": {"type": "limit", "value": 100}, "storage_gb": {"type": "limit", "value": 50}},
        is_active=True,
        is_public=True,
        trial_days=14,
    )
    enterprise_plan = Plan(
        key="enterprise",
        name="Enterprise",
        description="Enterprise plan for large organizations",
        tier="enterprise",
        monthly_price_cents=9900,
        annual_price_cents=99000,
        currency="USD",
        entitlements={"users": {"type": "limit", "value": 1000}, "storage_gb": {"type": "limit", "value": 500}},
        is_active=True,
        is_public=True,
        trial_days=30,
    )
    pg_db_session.add_all([starter_plan, professional_plan, enterprise_plan])
    await pg_db_session.commit()


@pytest_asyncio.fixture
async def onboarding_context() -> OnboardingContext:
    """Create a test onboarding context."""
    return OnboardingContext(
        organization_name=f"Test Company {uuid.uuid4().hex[:8]}",
        domain=f"test-onboard-{uuid.uuid4().hex[:8]}",
        admin_email=f"admin-{uuid.uuid4().hex[:8]}@test.com",
        admin_name="Test Admin",
        plan_key="starter",
        billing_interval="monthly",
        admin_password="TestPass123!",
    )


# =============================================================================
# ONBOARDING TESTS
# =============================================================================

class TestCompanyOnboarding:
    """Test complete company onboarding journey."""
    
    @pytest.mark.asyncio
    async def test_start_onboarding_creates_organization(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        """Starting onboarding creates organization and begins provisioning."""
        
        # Ensure clean transaction state
        await pg_db_session.rollback()
        await _clean_provisionings(pg_db_session)
        
        # Debug: verify domain uniqueness
        from sqlalchemy import select, text
        from app.models.organization import Organization
        result = await pg_db_session.execute(select(Organization).where(Organization.slug == onboarding_context.domain))
        existing = result.scalar_one_or_none()
        print(f"DEBUG: Existing org with domain {onboarding_context.domain}: {existing}")
        result = await pg_db_session.execute(text("SELECT count(*) FROM organizations"))
        print(f"DEBUG: Org count before start: {result.scalar()}")
        
        context = await onboarding_service.start_company_onboarding(
            pg_db_session,
            onboarding_context,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )
        
        # Verify organization created
        assert context.organization_id is not None
        assert context.provisioning_id is not None
        assert context.admin_user_id is not None
        
        # Verify organization exists
        org = await pg_db_session.get(Organization, context.organization_id)
        assert org is not None
        assert org.name == onboarding_context.organization_name
        assert org.slug == onboarding_context.domain
        assert org.status == "active"
        
        # Verify admin user created
        admin = await pg_db_session.get(User, context.admin_user_id)
        assert admin is not None
        assert admin.email == onboarding_context.admin_email
        assert admin.full_name == onboarding_context.admin_name
        
        # Verify provisioning record created
        from app.models.finance import Provisioning
        prov = await pg_db_session.get(Provisioning, context.provisioning_id)
        assert prov is not None
        assert prov.state == ProvisioningState.REQUESTED.value
        assert prov.organization_id == context.organization_id
        
        context = await onboarding_service.start_company_onboarding(
            pg_db_session,
            onboarding_context,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )
        
        # Verify organization created
        assert context.organization_id is not None
        assert context.provisioning_id is not None
        assert context.admin_user_id is not None
        
        # Verify organization exists
        org = await pg_db_session.get(Organization, context.organization_id)
        assert org is not None
        assert org.name == onboarding_context.organization_name
        assert org.slug == onboarding_context.domain
        assert org.status == "active"
        
        # Verify admin user created
        admin = await pg_db_session.get(User, context.admin_user_id)
        assert admin is not None
        assert admin.email == onboarding_context.admin_email
        assert admin.full_name == onboarding_context.admin_name
        
        # Verify provisioning record created
        from app.models.finance import Provisioning
        prov = await pg_db_session.get(Provisioning, context.provisioning_id)
        assert prov is not None
        assert prov.state == ProvisioningState.REQUESTED.value
        assert prov.organization_id == context.organization_id
    
    @pytest.mark.asyncio
    async def test_onboarding_context_tracks_phases(
        self,
        pg_db_session: AsyncSession,
        pg_db_session_factory,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)
        """Onboarding context correctly tracks phase progression."""
        
        context = await onboarding_service.start_company_onboarding(
            pg_db_session,
            onboarding_context,
        )
        
        # Initial phase
        assert context.current_phase == OnboardingPhase.PROVISIONING_STARTED
        assert "company_creation" in context.completed_steps
        assert "provisioning_started" in context.completed_steps
        
        # Continue provisioning
        context = await onboarding_service.continue_provisioning(
            pg_db_session,
            context.organization_id,
        )
        
        # Provisioning completed
        assert context.current_phase == OnboardingPhase.ADMIN_SETUP
        assert "provisioning_completed" in context.completed_steps
        assert "admin_setup" in context.completed_steps
    
    @pytest.mark.asyncio
    async def test_provisioning_completes_all_steps(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)
        """Full provisioning executes all 13 steps successfully."""
        
        context = await onboarding_service.start_company_onboarding(
            pg_db_session,
            onboarding_context,
        )
        
        context = await onboarding_service.continue_provisioning(
            pg_db_session,
            context.organization_id,
        )
        
        # Verify provisioning reached READY state
        from app.models.finance import Provisioning
        prov = await pg_db_session.get(Provisioning, context.provisioning_id)
        assert prov.state == ProvisioningState.READY.value
        assert prov.activated_at is not None
        assert prov.validation_passed is True
        
# All 13 steps should be completed
        completed_steps = [s for s in prov.steps if s.get("state") == "completed"]
        required_steps = [s for s in step_definitions if s["required"]]
        assert len(completed_steps) >= len(required_steps)

    @pytest.mark.asyncio
    async def test_onboarding_context_tracks_phases(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)
        """Onboarding context correctly tracks phase progression."""
        
        context = await onboarding_service.start_company_onboarding(
            pg_db_session,
            onboarding_context,
        )
        
        # Initial phase
        assert context.current_phase == OnboardingPhase.PROVISIONING_STARTED
        assert "company_creation" in context.completed_steps
        assert "provisioning_started" in context.completed_steps
        
        # Continue provisioning
        context = await onboarding_service.continue_provisioning(
            pg_db_session,
            context.organization_id,
        )
        
        # Provisioning completed
        assert context.current_phase == OnboardingPhase.ADMIN_SETUP
        assert "provisioning_completed" in context.completed_steps
        assert "admin_setup" in context.completed_steps
    
    @pytest.mark.asyncio
    async def test_invite_initial_employees(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)
        # Debug: check users table before onboarding
        from sqlalchemy import text
        result = await pg_db_session.execute(text("SELECT count(*) FROM users"))
        print(f"DEBUG: Users count after cleanup: {result.scalar()}")
        """Can invite initial employees during onboarding."""
        
        context = await onboarding_service.start_company_onboarding(
            pg_db_session,
            onboarding_context,
        )
        
        # Debug: check users after start_company_onboarding
        result = await pg_db_session.execute(text("SELECT count(*) FROM users"))
        print(f"DEBUG: Users count after start_company_onboarding: {result.scalar()}")
        result = await pg_db_session.execute(text("SELECT email, organization_id FROM users"))
        for row in result.fetchall():
            print(f"DEBUG: User: {row.email}, org_id: {row.organization_id}")
        
        context = await onboarding_service.continue_provisioning(
            pg_db_session,
            context.organization_id,
        )
        
        # Debug: check users after continue_provisioning
        result = await pg_db_session.execute(text("SELECT count(*) FROM users"))
        print(f"DEBUG: Users count after continue_provisioning: {result.scalar()}")
        result = await pg_db_session.execute(text("SELECT email, organization_id FROM users"))
        for row in result.fetchall():
            print(f"DEBUG: User: {row.email}, org_id: {row.organization_id}")
        
        # Invite initial employees
        employees = [
            {"email": f"emp1-{uuid.uuid4().hex[:8]}@test.com", "full_name": "Employee One", "role": "employee"},
            {"email": f"emp2-{uuid.uuid4().hex[:8]}@test.com", "full_name": "Employee Two", "role": "manager"},
        ]
        
        # Debug: check roles in org before invite
        from sqlalchemy import select
        from app.models.role import Role
        result = await pg_db_session.execute(select(Role).where(Role.organization_id == context.organization_id))
        roles = result.scalars().all()
        print(f"DEBUG: Roles in org before invite: {len(roles)}")
        for r in roles:
            print(f"DEBUG: Role: {r.code}, id={r.id}")
        
        # Debug: check admin user permissions
        from app.models.user import User
        from app.models.role import UserRole
        from sqlalchemy import select
        admin_user = await pg_db_session.get(User, context.admin_user_id)
        print(f"DEBUG: Admin user: {admin_user.email if admin_user else None}, id={admin_user.id if admin_user else None}")
        
        # Check user roles
        result = await pg_db_session.execute(select(UserRole).where(UserRole.user_id == context.admin_user_id, UserRole.organization_id == context.organization_id))
        user_roles = result.scalars().all()
        print(f"DEBUG: Admin user roles: {len(user_roles)}")
        for ur in user_roles:
            print(f"DEBUG: UserRole: role_id={ur.role_id}")
        
        results = await onboarding_service.invite_initial_employees(
            pg_db_session,
            context.organization_id,
            employees,
            context.admin_user_id,
        )
        
        assert len(results) == 2
        assert all(r["success"] for r in results)
        assert all("invitation_id" in r for r in results)
        
        # Verify invitations in database
        from app.models.invitation import Invitation
        result = await pg_db_session.execute(
            select(Invitation).where(Invitation.organization_id == context.organization_id)
        )
        invitations = result.scalars().all()
        assert len(invitations) == 2
    
    @pytest.mark.asyncio
    async def test_workspace_setup(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)
        """Admin workspace is set up after provisioning."""
        
        context = await onboarding_service.start_company_onboarding(
            pg_db_session,
            onboarding_context,
        )
        
        context = await onboarding_service.continue_provisioning(
            pg_db_session,
            context.organization_id,
        )
        
        # Setup workspace
        workspace = await onboarding_service.setup_initial_workspace(
            pg_db_session,
            context.organization_id,
            context.admin_user_id,
        )
        
        assert workspace is not None
        assert workspace.organization_id == context.organization_id
        assert workspace.user_id == context.admin_user_id
        
        # Verify workspace has default items
        from app.services.workspace_service import workspace_service
        items, total = await workspace_service.list_items(
            pg_db_session,
            user_id=context.admin_user_id,
            organization_id=context.organization_id,
        )
        assert total >= 2  # Welcome pin + Company Home shortcut
    
    @pytest.mark.asyncio
    async def test_canonical_reality_initialization(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)
        """Canonical reality is initialized at onboarding completion."""
        
        context = await onboarding_service.start_company_onboarding(
            pg_db_session,
            onboarding_context,
        )
        
        context = await onboarding_service.continue_provisioning(
            pg_db_session,
            context.organization_id,
        )
        
        # Complete onboarding
        context = await onboarding_service.complete_onboarding(
            pg_db_session,
            context.organization_id,
        )
        
        assert context.current_phase == OnboardingPhase.ONBOARDING_COMPLETE
        assert "canonical_reality_ready" in context.completed_steps
        assert "onboarding_complete" in context.completed_steps
        assert context.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_onboarding_progress_tracking(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)
        """Can track onboarding progress at any point."""
        
        context = await onboarding_service.start_company_onboarding(
            pg_db_session,
            onboarding_context,
        )
        
        progress = await onboarding_service.get_onboarding_progress(
            pg_db_session,
            context.organization_id,
        )
        
        assert "organization_id" in progress
        assert "current_phase" in progress
        assert "provisioning_state" in progress
        assert "provisioning_progress" in progress
        assert progress["current_phase"] == OnboardingPhase.PROVISIONING_STARTED.value
        assert progress["provisioning_state"] == ProvisioningState.REQUESTED.value
        
        # After provisioning
        context = await onboarding_service.continue_provisioning(
            pg_db_session,
            context.organization_id,
        )
        
        progress = await onboarding_service.get_onboarding_progress(
            pg_db_session,
            context.organization_id,
        )
        
        assert progress["provisioning_state"] == ProvisioningState.READY.value
        assert progress["provisioning_progress"] == 100.0
    
    @pytest.mark.asyncio
    async def test_onboarding_handles_domain_conflict(
        self,
        pg_db_session: AsyncSession,
    ):
        await _clean_provisionings(pg_db_session)
        """Onboarding fails gracefully when domain already exists."""
        
        # Create first company
        context1 = OnboardingContext(
            organization_name="Test Company 1",
            domain="conflict-test",
            admin_email=f"admin1-{uuid.uuid4().hex[:8]}@test.com",
            admin_name="Admin One",
            admin_password="TestPass123!",
        )
        
        context1 = await onboarding_service.start_company_onboarding(pg_db_session, context1)
        
        # Try to create second company with same domain
        context2 = OnboardingContext(
            organization_name="Test Company 2",
            domain="conflict-test",
            admin_email=f"admin2-{uuid.uuid4().hex[:8]}@test.com",
            admin_name="Admin Two",
            admin_password="TestPass123!",
        )
        
        with pytest.raises(ValueError, match="already exists"):
            await onboarding_service.start_company_onboarding(pg_db_session, context2)
    
    @pytest.mark.asyncio
    async def test_onboarding_handles_email_conflict(
        self,
        pg_db_session: AsyncSession,
    ):
        await _clean_provisionings(pg_db_session)
        """Onboarding fails gracefully when admin email already exists."""
        
        context1 = OnboardingContext(
            organization_name="Test Company 1",
            domain=f"domain1-{uuid.uuid4().hex[:8]}",
            admin_email=f"shared-{uuid.uuid4().hex[:8]}@test.com",
            admin_name="Admin One",
            admin_password="TestPass123!",
        )
        
        await onboarding_service.start_company_onboarding(pg_db_session, context1)
        
        context2 = OnboardingContext(
            organization_name="Test Company 2",
            domain=f"domain2-{uuid.uuid4().hex[:8]}",
            admin_email=context1.admin_email,  # Same email
            admin_name="Admin Two",
            admin_password="TestPass123!",
        )
        
        with pytest.raises(ValueError, match="already exists"):
            await onboarding_service.start_company_onboarding(pg_db_session, context2)


# Import step_definitions for test
from app.services.provisioning_service import STEP_DEFINITIONS as step_definitions