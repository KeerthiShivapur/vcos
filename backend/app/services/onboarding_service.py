"""Onboarding Service — orchestrates the complete real-company onboarding journey.

Ties together:
- ProvisioningService (infrastructure setup)
- AuthService (authentication, invitations, MFA)
- OrganizationService (organization + owner)
- EmployeeService (employee records)
- WorkspaceService (workspace provisioning)
- ProvisioningService (infrastructure setup)
- Integration configuration
- Canonical reality initialization
- Company Brain initialization
- Observability/Alerting integration

Every step is observable, recoverable, and tenant-safe.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict
from enum import Enum

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.department import Department
from app.models.team import Team
from app.models.role import Role
from app.models.workspace import Workspace, WorkspaceItem
from app.models.invitation import Invitation
from app.models.finance import (
    Provisioning,
    ProvisioningStep,
    Plan,
    Subscription,
    CommercialAccount,
    Entitlement,
    SubscriptionEvent,
)
from app.services.provisioning_service import ProvisioningState, ProvisioningService
from app.models.canonical_integration import (
    ConnectorInstance,
    Connector,
    SyncRun,
)

from app.people.employee_service import employee_service
from app.services.provisioning_service import provisioning_service
from app.services.auth_service import auth_service
from app.services.migration_safety import MigrationSafetyManager
from app.services.organization_service import organization_service
from app.services.permission_service import permission_service
from app.services.canonical_fingerprint import canonical_fingerprint_service
from app.services.health_evaluation_service import health_evaluation_service
from app.services.workspace_service import workspace_service
from app.services.health_model_service import health_model_service
from app.validation.capability_contract import CapabilityDetector
from app.intelligence.canonical_mutation import (
    canonical_mutation_boundary,
    MutationType,
)
from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service

logger = logging.getLogger("vcos.onboarding")


# =============================================================================
# DATA CLASSES
# =============================================================================

class OnboardingPhase(str, Enum):
    """High-level onboarding phases for UI progress tracking."""
    COMPANY_CREATED = "company_created"
    PROVISIONING_STARTED = "provisioning_started"
    PROVISIONING_COMPLETED = "provisioning_completed"
    ADMIN_SETUP = "admin_setup"
    EMPLOYEE_INVITATIONS = "employee_invitations"
    WORKSPACE_READY = "workspace_ready"
    INTEGRATIONS_CONFIGURED = "integrations_configured"
    CANONICAL_REALITY_READY = "canonical_reality_ready"
    ONBOARDING_COMPLETE = "onboarding_complete"


@dataclass
class OnboardingContext:
    """Complete context for a company onboarding journey."""
    # Company identity
    organization_name: str
    domain: str
    admin_email: str
    admin_name: str
    plan_key: str = "starter"
    billing_interval: str = "monthly"
    custom_domain: bool = False
    
    # Admin details
    admin_password: Optional[str] = None
    admin_phone: Optional[str] = None
    
    # Initial employees to invite
    initial_employees: List[Dict[str, Any]] = field(default_factory=list)
    
    # Integration preferences
    integrations_to_configure: List[str] = field(default_factory=list)
    
    # Internal tracking
    organization_id: Optional[str] = None
    provisioning_id: Optional[str] = None
    admin_user_id: Optional[str] = None
    admin_employee_id: Optional[str] = None
    provisioning_id: Optional[str] = None
    
    # Current phase
    current_phase: OnboardingPhase = OnboardingPhase.COMPANY_CREATED
    
    # Progress tracking
    completed_steps: List[str] = field(default_factory=list)
    failed_steps: List[str] = field(default_factory=list)
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    # Timing
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class OnboardingService(CapabilityDetector):
    """Orchestrates the complete real-company onboarding journey."""
    
    def __init__(self):
        super().__init__()
        self._migration_safety = MigrationSafetyManager()
        self._active_onboardings: Dict[str, OnboardingContext] = {}
    
    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================
    
    async def start_company_onboarding(
        self,
        db: AsyncSession,
        context: OnboardingContext,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> OnboardingContext:
        """Start a new company onboarding journey.
        
        This is the main entry point for real company onboarding.
        Creates the organization and begins provisioning.
        """
        logger.info(f"Starting onboarding for {context.organization_name} ({context.domain})")
        
        # Validate inputs
        await self._validate_onboarding_inputs(db, context)
        
        # Check if organization already exists
        existing_org = await db.execute(
            select(Organization).where(Organization.slug == context.domain)
        )
        existing_org = existing_org.scalar_one_or_none()
        
        if existing_org:
            # Organization exists - check if we can use it (consistent with validation logic)
            if existing_org.status in ["active", "provisioning"]:
                existing_owner = (
                    await db.get(User, existing_org.owner_id)
                    if existing_org.owner_id
                    else None
                )
                if existing_owner is not None and existing_owner.email != context.admin_email:
                    # A different company's registration already occupies this
                    # domain. Re-onboarding the same company with its original
                    # admin email is an idempotent resume; anything else is a
                    # domain conflict.
                    raise ValueError(
                        f"Organization with domain {context.domain} already exists"
                    )
                # Use existing organization
                org = existing_org
                logger.info(f"Using existing organization: {org.id}")
                
                # Get or create admin user
                if existing_owner is not None:
                    owner = existing_owner
                elif existing_org.owner_id:
                    owner = await db.get(User, existing_org.owner_id)
                else:
                    # Create admin user
                    from app.schemas.auth import RegisterRequest
                    register_payload = RegisterRequest(
                        organization_name=context.organization_name,
                        organization_slug=context.domain,
                        email=context.admin_email,
                        username=context.admin_email.split('@')[0],
                        full_name=context.admin_name,
                        password=context.admin_password or 'TempPass123!',
                        industry=None,
                        country='US',
                        timezone='UTC',
                        currency='USD',
                    )
                    created = await organization_service.create_organization_and_owner(
                        db, payload=RegisterRequest(
                            organization_name=context.organization_name,
                            organization_slug=context.domain,
                            email=context.admin_email,
                            username=context.admin_email.split('@')[0],
                            full_name=context.admin_name,
                            password=context.admin_password or 'TempPass123!',
                            industry=None,
                            country='US',
                            timezone='UTC',
                            currency='USD',
                        ), ip_address=ip_address, user_agent=user_agent
                    )
                    org = created["organization"]
                    owner = created["owner"]
            else:
                # Organization exists but in invalid state
                raise ValueError(f"Organization with domain {context.domain} exists but is in invalid state: {existing_org.status}")
        else:
            # Phase 1: Create organization (via organization_service + auth_service)
            from app.schemas.auth import RegisterRequest
            register_payload = RegisterRequest(
                organization_name=context.organization_name,
                organization_slug=context.domain,
                email=context.admin_email,
                username=context.admin_email.split('@')[0],
                full_name=context.admin_name,
                password=context.admin_password or 'TempPass123!',
                industry=None,
                country='US',
                timezone='UTC',
                currency='USD',
            )
            created = await organization_service.create_organization_and_owner(
                db, payload=register_payload, ip_address=ip_address, user_agent=user_agent
            )
            org = created["organization"]
            owner = created["owner"]
        
        context.organization_id = org.id
        context.admin_user_id = owner.id
        context.current_phase = OnboardingPhase.PROVISIONING_STARTED
        context.completed_steps.append("company_creation")
        
        # Phase 2: Start provisioning (infrastructure setup) using existing organization
        provisioning = await provisioning_service.start_provisioning(
            db,
            organization_name=context.organization_name,
            domain=context.domain,
            admin_email=context.admin_email,
            admin_name=context.admin_name,
            plan_key=context.plan_key,
            billing_interval=context.billing_interval,
            custom_domain=context.custom_domain,
            organization_id=context.organization_id,
        )
        
        context.provisioning_id = provisioning.id
        context.current_phase = OnboardingPhase.PROVISIONING_STARTED
        context.completed_steps.append("provisioning_started")
        
        # Store context
        self._active_onboardings[org.id] = context
        
        # Emit event
        await publish_event(
            db,
            name="onboarding.started",
            actor_id="system",
            organization_id=org.id,
            payload={
                "organization_name": context.organization_name,
                "domain": context.domain,
                "plan": context.plan_key,
            },
        )
        
        await db.flush()
        logger.info(f"Onboarding started for organization {org.id}")
        
        return context
    
    async def continue_provisioning(
        self,
        db: AsyncSession,
        organization_id: str,
        caller: Any = None,
    ) -> OnboardingContext:
        """Continue provisioning after company creation.
        
        Executes the full provisioning lifecycle.
        """
        context = self._active_onboardings.get(organization_id)
        if not context:
            # Load from database
            prov = await provisioning_service.get_provisioning_by_org(db, organization_id)
            if not prov:
                raise ValueError("No provisioning found for organization")
            context = OnboardingContext(
                organization_id=organization_id,
                provisioning_id=prov.id,
                current_phase=OnboardingPhase.PROVISIONING_STARTED,
            )
            self._active_onboardings[organization_id] = context
        
        try:
            # Execute full provisioning
            provisioning = await provisioning_service.execute_provisioning(
                db,
                provisioning_id=context.provisioning_id,
                caller=caller,
            )
            
            context.current_phase = OnboardingPhase.PROVISIONING_COMPLETED
            context.completed_steps.append("provisioning_completed")
            
            # Admin is already created during organization creation
            # Get admin user/employee
            org = await db.get(Organization, context.organization_id)
            if org and org.owner_id:
                from app.people.employee_service import employee_service
                emp = await db.execute(
                    select(Employee).where(Employee.user_id == org.owner_id)
                )
                emp = emp.scalar_one_or_none()
                if emp:
                    context.admin_employee_id = emp.id
            
            context.current_phase = OnboardingPhase.ADMIN_SETUP
            context.completed_steps.append("admin_setup")
            
            # Emit completion event
            await publish_event(
                db,
                name="onboarding.completed",
                actor_id="system",
                organization_id=organization_id,
                payload={"provisioning_id": context.provisioning_id},
            )
            
            return context
        except Exception as e:
            logger.error(f"Provisioning failed for {organization_id}: {e}")
            raise

    async def get_onboarding_context(self, organization_id: str) -> Optional[OnboardingContext]:
        return self._active_onboardings.get(organization_id)
    
    # =========================================================================
    # EMPLOYEE INVITATIONS
    # =========================================================================
    
    async def invite_initial_employees(
        self,
        db: AsyncSession,
        organization_id: str,
        employees: List[Dict[str, Any]],
        inviter_user_id: str,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Invite initial employees to the company."""
        context = self._active_onboardings.get(organization_id)
        if not context:
            context = OnboardingContext(organization_id=organization_id)
            self._active_onboardings[organization_id] = context
        
        results = []
        
        for emp_data in employees:
            try:
                from app.services.auth_service import auth_service
                result = await auth_service.invite(
                    db,
                    organization=await db.get(Organization, organization_id),
                    inviter=await db.get(User, inviter_user_id),
                    email=emp_data["email"],
                    full_name=emp_data.get("full_name"),
                    role=emp_data.get("role", "employee"),
                    message=emp_data.get("message"),
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                results.append({
                    "email": emp_data["email"],
                    "success": True,
                    "invitation_id": result["invitation"].id,
                    "url": result["url"],
                })
            except Exception as e:
                logger.error(f"Failed to invite {emp_data['email']}: {e}")
                results.append({
                    "email": emp_data["email"],
                    "success": False,
                    "error": str(e),
                })
        
        context.current_phase = OnboardingPhase.EMPLOYEE_INVITATIONS
        context.completed_steps.append("employee_invitations")
        
        await publish_event(
            db,
            name="onboarding.employees_invited",
            actor_id="system",
            organization_id=organization_id,
            payload={"invited_count": len([r for r in results if r.get("success")])},
        )
        
        return results
    
    # =========================================================================
    # WORKSPACE SETUP
    # =========================================================================
    
    async def setup_initial_workspace(
        self,
        db: AsyncSession,
        organization_id: str,
        admin_user_id: str,
    ) -> Workspace:
        """Set up the initial workspace for the admin."""
        workspace = await workspace_service.get_or_create(
            db,
            user_id=admin_user_id,
            organization_id=organization_id,
        )
        
        # Add default workspace items
        await workspace_service.add_item(db, workspace=workspace, data={
            "kind": "pin",
            "title": "Welcome to VCOS",
            "content": "Your company operating system is ready. Start by exploring your workspace.",
            "pinned": True,
        })
        
        await workspace_service.add_item(db, workspace=workspace, data={
            "kind": "shortcut",
            "title": "Company Home",
            "link": "/home",
            "entity_type": "page",
            "entity_id": "home",
        })
        
        return workspace
    
    # =========================================================================
    # INTEGRATION CONFIGURATION
    # =========================================================================
    
    async def configure_integrations(
        self,
        db: AsyncSession,
        organization_id: str,
        integrations: List[str],
    ) -> List[Dict[str, Any]]:
        """Configure initial integrations for the company."""
        from app.services.provider_adapters import provider_adapters
        
        results = []
        
        for integration_key in integrations:
            try:
                connector = await provider_adapters.get_connector(integration_key)
                if not connector:
                    raise ValueError(f"Unknown integration: {integration_key}")
                
                results.append({
                    "integration": integration_key,
                    "connector_id": connector.id,
                    "status": "configured",
                    "next_steps": "Provide credentials and enable sync",
                })
            except Exception as e:
                logger.error(f"Failed to configure integration {integration_key}: {e}")
                results.append({
                    "integration": integration_key,
                    "success": False,
                    "error": str(e),
                })
        
        return results
    
    # =========================================================================
    # CANONICAL REALITY INITIALIZATION
    # =========================================================================
    
    async def initialize_canonical_reality(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Dict[str, Any]:
        """Initialize canonical company reality."""
        
        # Compute initial canonical fingerprint
        tenant_fp = await canonical_fingerprint_service.compute_tenant_fingerprint(
            db, organization_id
        )
        
        # Run initial health evaluation
        health_report = await health_evaluation_service.evaluate_all(
            db, organization_id
        )
        
        # Build initial health model
        from app.services.health_model_service import health_model_service
        health_model = await health_model_service.generate_report(
            db, organization_id
        )
        
        return {
            "canonical_fingerprint": tenant_fp.aggregate_fingerprint,
            "health_overall": health_report.overall_status,
            "health_dimensions": {
                dim.value: result.status 
                for dim, result in health_report.dimension_results.items()
            },
            "health_model_fingerprint": health_model.fingerprint,
        }
    
    # =========================================================================
    # COMPLETE ONBOARDING
    # =========================================================================
    
    async def complete_onboarding(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> OnboardingContext:
        """Mark onboarding as complete."""
        context = self._active_onboardings.get(organization_id)
        if not context:
            prov = await provisioning_service.get_provisioning_by_org(db, organization_id)
            if not prov:
                raise ValueError("No provisioning found for organization")
            context = OnboardingContext(
                organization_id=organization_id,
                provisioning_id=prov.id,
            )
            self._active_onboardings[organization_id] = context
        
        # Final health check
        health_report = await health_evaluation_service.evaluate_all(db, organization_id)
        
        # Final canonical fingerprint
        tenant_fp = await canonical_fingerprint_service.compute_tenant_fingerprint(db, organization_id)
        
        context.current_phase = OnboardingPhase.ONBOARDING_COMPLETE
        context.completed_steps.append("canonical_reality_ready")
        context.completed_steps.append("onboarding_complete")
        context.completed_at = utcnow()
        
        # Emit completion event
        await publish_event(
            db,
            name="onboarding.completed",
            actor_id="system",
            organization_id=organization_id,
            payload={
                "final_health": health_report.overall_status,
                "canonical_fingerprint": tenant_fp.aggregate_fingerprint,
            },
        )
        
        logger.info(f"Onboarding completed for organization {organization_id}")
        return context
    
    # =========================================================================
    # PROGRESS TRACKING
    # =========================================================================
    
    async def get_onboarding_progress(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Dict[str, Any]:
        """Get detailed onboarding progress."""
        context = self._active_onboardings.get(organization_id)
        prov = None
        if not context:
            prov = await provisioning_service.get_provisioning_by_org(db, organization_id)
            if not prov:
                return {"error": "No provisioning found"}
            
            context = OnboardingContext(
                organization_id=organization_id,
                provisioning_id=prov.id,
                current_phase=self._map_provisioning_state_to_phase(prov.state),
            )
            self._active_onboardings[organization_id] = context
        else:
            # Load provisioning from database if we have a provisioning_id
            if context.provisioning_id:
                prov = await db.get(Provisioning, context.provisioning_id)
        
        provisioning_state = prov.state if prov else None
        provisioning_progress = self._calculate_provisioning_progress(prov) if prov else 0
        current_step = prov.current_step if prov else None
        
        return {
            "organization_id": organization_id,
            "current_phase": context.current_phase.value,
            "provisioning_state": provisioning_state,
            "provisioning_progress": provisioning_progress,
            "current_step": current_step,
            "completed_steps": context.completed_steps,
            "failed_steps": context.failed_steps,
            "errors": context.errors,
            "started_at": context.started_at.isoformat() if context.started_at else None,
            "completed_at": context.completed_at.isoformat() if context.completed_at else None,
        }
    
    def _map_provisioning_state_to_phase(self, state: str) -> OnboardingPhase:
        mapping = {
            "requested": OnboardingPhase.PROVISIONING_STARTED,
            "validating": OnboardingPhase.PROVISIONING_STARTED,
            "migrating": OnboardingPhase.PROVISIONING_STARTED,
            "deploying": OnboardingPhase.PROVISIONING_STARTED,
            "health_check": OnboardingPhase.PROVISIONING_STARTED,
            "ready": OnboardingPhase.PROVISIONING_COMPLETED,
            "failed": OnboardingPhase.PROVISIONING_STARTED,
            "rolled_back": OnboardingPhase.PROVISIONING_STARTED,
        }
        return mapping.get(state, OnboardingPhase.PROVISIONING_STARTED)
    
    def _calculate_provisioning_progress(self, provisioning) -> float:
        """Calculate provisioning progress percentage."""
        # Simplified progress calculation based on state
        state_progress = {
            "requested": 10,
            "validating": 20,
            "migrating": 40,
            "deploying": 60,
            "health_check": 80,
            "ready": 100,
            "failed": 0,
            "rolled_back": 0,
        }
        return state_progress.get(provisioning.state, 0)
    
    async def _validate_onboarding_inputs(
        self,
        db: AsyncSession,
        context: OnboardingContext,
    ) -> None:
        """Validate onboarding inputs."""
        if not context.organization_name:
            raise ValueError("Organization name is required")
        if not context.domain:
            raise ValueError("Domain is required")
        if not context.admin_email:
            raise ValueError("Admin email is required")
        if not context.admin_name:
            raise ValueError("Admin name is required")
        
        # Check domain availability - if organization exists, we'll use it
        existing_org = await db.execute(
            select(Organization).where(Organization.slug == context.domain)
        )
        existing_org = existing_org.scalar_one_or_none()
        if existing_org:
            # Organization exists, check if it's in a state we can work with
            if existing_org.status not in ["active", "provisioning"]:
                raise ValueError(f"Organization with domain {context.domain} exists but is in invalid state: {existing_org.status}")
        else:
            # Check email availability only for new organizations
            existing_user = await db.execute(
                select(User).where(User.email == context.admin_email)
            )
            if existing_user.scalar_one_or_none():
                raise ValueError(f"User with email {context.admin_email} already exists")


# Global instance
onboarding_service = OnboardingService()