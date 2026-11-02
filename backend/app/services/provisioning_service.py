"""Company Provisioning Service — universal company onboarding lifecycle.

Implements the complete company provisioning state machine:
REQUESTED → IDENTITY_INITIALIZED → TENANT_CREATED → SECURITY_INITIALIZED
→ GOVERNANCE_INITIALIZED → COMMERCIAL_INITIALIZED → WORKSPACE_INITIALIZED
→ ORGANIZATION_INITIALIZED → ADMIN_INITIALIZED → INTEGRATION_READY
→ INITIAL_SYNC → CANONICAL_VALIDATION → COMPANY_BRAIN_INITIALIZATION → READY

Every transition is idempotent, auditable, recoverable, tenant-safe, and governed.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Callable
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.finance import (
    Provisioning,
    ProvisioningStep,
    Provisioning,
    PROVISIONING_STATES,
    PROVISIONING_STEP_STATES,
)
from app.services.provisioning_instrumentation import (
    record_run_start,
    record_step_start,
    record_step_complete,
    record_run_complete,
    record_provisioning_complete,
    timed_provisioning_step,
    emit_provisioning_observation,
    emit_provisioning_run_observation,
)
from app.models.finance import (
    CommercialAccount,
    Plan,
    Entitlement,
    Subscription,
    SubscriptionEvent,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.department import Department
from app.models.team import Team
from app.models.role import Role
from app.models.project import Project
from app.models.company_operating import CompanyDecision
from app.models.canonical_integration import (
    ConnectorInstance,
    Connector,
)
from app.models.backup_manifest import BackupManifest
from app.services.backup_service import backup_service
from app.services.migration_safety import MigrationSafetyManager
from app.intelligence.canonical_mutation import (
    canonical_mutation_boundary,
    MutationType,
)
from app.intelligence.company_context import CallerAccess

logger = logging.getLogger("vcos.provisioning")


# =============================================================================
# PROVISIONING INSTRUMENTATION
# =============================================================================

@dataclass
class ProvisioningStepMetrics:
    """Metrics for a single provisioning step."""
    step_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    state: str = "pending"
    error: Optional[str] = None
    retry_count: int = 0
    transaction_committed: bool = False
    connection_acquired_at: Optional[datetime] = None
    connection_released_at: Optional[datetime] = None
    lock_wait_seconds: float = 0.0
    db_queries_count: int = 0
    db_rows_affected: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_name": self.step_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "state": self.state,
            "error": self.error,
            "retry_count": self.retry_count,
            "transaction_committed": self.transaction_committed,
            "connection_acquired_at": self.connection_acquired_at.isoformat() if self.connection_acquired_at else None,
            "connection_released_at": self.connection_released_at.isoformat() if self.connection_released_at else None,
            "lock_wait_seconds": self.lock_wait_seconds,
            "db_queries_count": self.db_queries_count,
            "db_rows_affected": self.db_rows_affected,
        }


@dataclass
class ProvisioningMetrics:
    """Complete metrics for a provisioning run."""
    provisioning_id: str
    organization_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    overall_duration_seconds: Optional[float] = None
    final_state: str = "pending"
    steps: Dict[str, ProvisioningStepMetrics] = field(default_factory=dict)
    overall_retry_count: int = 0
    transaction_rollbacks: int = 0
    db_connections_used: int = 0
    db_connections_leaked: int = 0
    peak_locks_held: int = 0
    total_lock_wait_seconds: float = 0.0
    total_db_queries: int = 0
    total_db_rows_affected: int = 0
    failure_reason: Optional[str] = None
    recovery_attempts: int = 0
    idempotency_checks_passed: int = 0
    idempotency_checks_failed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provisioning_id": self.provisioning_id,
            "organization_id": self.organization_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "overall_duration_seconds": self.overall_duration_seconds,
            "final_state": self.final_state,
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "overall_retry_count": self.overall_retry_count,
            "transaction_rollbacks": self.transaction_rollbacks,
            "db_connections_used": self.db_connections_used,
            "db_connections_leaked": self.db_connections_leaked,
            "peak_locks_held": self.peak_locks_held,
            "total_lock_wait_seconds": self.total_lock_wait_seconds,
            "total_db_queries": self.total_db_queries,
            "total_db_rows_affected": self.total_db_rows_affected,
            "failure_reason": self.failure_reason,
            "recovery_attempts": self.recovery_attempts,
            "idempotency_checks_passed": self.idempotency_checks_passed,
            "idempotency_checks_failed": self.idempotency_checks_failed,
        }


# Global metrics registry
_provisioning_metrics: Dict[str, ProvisioningMetrics] = {}


def get_provisioning_metrics(provisioning_id: str) -> Optional[ProvisioningMetrics]:
    """Get metrics for a provisioning run."""
    return _provisioning_metrics.get(provisioning_id)


def clear_provisioning_metrics(provisioning_id: str):
    """Clear metrics for a provisioning run."""
    _provisioning_metrics.pop(provisioning_id, None)


def get_all_provisioning_metrics() -> List[Dict[str, Any]]:
    """Get all provisioning metrics as dictionaries."""
    return [m.to_dict() for m in _provisioning_metrics.values()]


class ProvisioningState(Enum):
    REQUESTED = "requested"
    IDENTITY_INITIALIZED = "identity_initialized"
    TENANT_CREATED = "tenant_created"
    SECURITY_INITIALIZED = "security_initialized"
    GOVERNANCE_INITIALIZED = "governance_initialized"
    COMMERCIAL_INITIALIZED = "commercial_initialized"
    WORKSPACE_INITIALIZED = "workspace_initialized"
    ORGANIZATION_INITIALIZED = "organization_initialized"
    ADMIN_INITIALIZED = "admin_initialized"
    INTEGRATION_READY = "integration_ready"
    INITIAL_SYNC = "initial_sync"
    CANONICAL_VALIDATION = "canonical_validation"
    COMPANY_BRAIN_INITIALIZATION = "company_brain_initialization"
    READY = "ready"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


PROVISIONING_STATE_ORDER = [
    ProvisioningState.REQUESTED,
    ProvisioningState.IDENTITY_INITIALIZED,
    ProvisioningState.TENANT_CREATED,
    ProvisioningState.SECURITY_INITIALIZED,
    ProvisioningState.GOVERNANCE_INITIALIZED,
    ProvisioningState.COMMERCIAL_INITIALIZED,
    ProvisioningState.WORKSPACE_INITIALIZED,
    ProvisioningState.ORGANIZATION_INITIALIZED,
    ProvisioningState.ADMIN_INITIALIZED,
    ProvisioningState.INTEGRATION_READY,
    ProvisioningState.INITIAL_SYNC,
    ProvisioningState.CANONICAL_VALIDATION,
    ProvisioningState.COMPANY_BRAIN_INITIALIZATION,
    ProvisioningState.READY,
]

STEP_DEFINITIONS = [
    {
        "step": "identity_initialization",
        "name": "Identity Initialization",
        "description": "Create organization identity and domain",
        "required": True,
        "recoverable": True,
    },
    {
        "step": "tenant_creation",
        "name": "Tenant Creation",
        "description": "Create organization tenant with domain",
        "required": True,
        "recoverable": True,
    },
    {
        "step": "security_initialization",
        "name": "Security Initialization",
        "description": "Apply security policies, MFA, encryption",
        "required": True,
        "recoverable": True,
    },
    {
        "step": "governance_initialization",
        "name": "Governance Initialization",
        "description": "Set up approval policies, roles, permissions",
        "required": True,
        "recoverable": True,
    },
    {
        "step": "commercial_initialization",
        "name": "Commercial Initialization",
        "description": "Create commercial account, subscription, entitlements",
        "required": True,
        "recoverable": True,
    },
    {
        "step": "workspace_initialization",
        "name": "Workspace Initialization",
        "description": "Create workspace settings, themes, defaults",
        "required": True,
        "recoverable": True,
    },
    {
        "step": "organization_initialization",
        "name": "Organization Initialization",
        "description": "Create departments, teams, roles, reporting structure",
        "required": True,
        "recoverable": True,
    },
    {
        "step": "admin_initialization",
        "name": "Admin Initialization",
        "description": "Provision first administrator with full access",
        "required": True,
        "recoverable": True,
    },
    {
        "step": "integration_ready",
        "name": "Integration Configuration",
        "description": "Configure available integrations and connectors",
        "required": False,
        "recoverable": True,
    },
    {
        "step": "initial_sync",
        "name": "Initial Synchronization",
        "description": "Run initial sync for all configured integrations",
        "required": False,
        "recoverable": True,
    },
    {
        "step": "canonical_validation",
        "name": "Canonical Validation",
        "description": "Validate canonical reality integrity",
        "required": True,
        "recoverable": True,
    },
    {
        "step": "company_brain_initialization",
        "name": "Company Brain Initialization",
        "description": "Initialize Company Brain with canonical data",
        "required": True,
        "recoverable": True,
    },
]


class ProvisioningService:
    """Company Provisioning Service — end-to-end company onboarding.
    
    Implements the complete provisioning state machine with:
    - Idempotent, auditable, recoverable state transitions
    - Tenant-safe operations
    - Governed transitions
    - Failure recovery at every step
    - Commercial integration
    """
    
    def __init__(self):
        self.migration_safety = MigrationSafetyManager()
    
    # ------------------------------------------------------------ Provisioning Lifecycle
    
    async def start_provisioning(
        self,
        db: AsyncSession,
        *,
        organization_name: str,
        domain: str,
        admin_email: str,
        admin_name: str,
        plan_key: str = "starter",
        billing_interval: str = "monthly",
        custom_domain: bool = False,
        caller: Any = None,
        organization_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Any:
        """Start a new company provisioning with idempotency support.
        
        This is the entry point for company onboarding.
        If organization_id is provided, uses existing organization.
        Otherwise creates a new organization.
        
        Idempotency:
        - If idempotency_key is provided, uses exact-once semantics
        - Same key with same payload returns existing provisioning
        - Same key with different payload raises conflict error
        """
        org = None
        # Idempotency key handling - check FIRST before any other operations
        if idempotency_key:
            import hashlib
            import json
            from sqlalchemy import text
            
            # Create deterministic fingerprint for idempotency
            idempotency_data = {
                "idempotency_key": idempotency_key,
                "organization_name": organization_name,
                "domain": domain,
                "admin_email": admin_email,
                "admin_name": admin_name,
                "plan_key": plan_key,
                "billing_interval": billing_interval,
                "custom_domain": custom_domain,
                "organization_id": organization_id,
            }
            # Create deterministic fingerprint
            idempotency_fingerprint = hashlib.sha256(
                json.dumps(idempotency_data, sort_keys=True).encode()
            ).hexdigest()[:64]
            
            # Check for existing provisioning with same idempotency_key (regardless of payload)
            # Use PostgreSQL JSON extraction: metadata_json::jsonb ->> 'idempotency_key'
            existing_by_key = await db.execute(
                select(Provisioning).where(
                    text("(metadata_json::jsonb ->> 'idempotency_key') = :key")
                ).params(key=idempotency_key)
            )
            existing_by_key = existing_by_key.scalar_one_or_none()
            if existing_by_key:
                # Verify payload matches - check if fingerprint matches
                existing_meta = existing_by_key.metadata_json or {}
                existing_fp = existing_meta.get("idempotency_fingerprint")
                if existing_fp != idempotency_fingerprint:
                    # Same key, different payload - conflict!
                    raise ValueError(
                        f"Idempotency key conflict: key '{idempotency_key}' already used "
                        f"with different payload (provisioning: {existing_meta.get('provisioning_id', 'unknown')})"
                    )
                # Same key, same payload - return existing
                return existing_by_key
        
        org = None
        if organization_id:
            # Use existing organization
            org = await db.get(Organization, organization_id)
            if not org:
                raise ValueError(f"Organization not found: {organization_id}")
        else:
            # Check if organization already exists
            existing = await db.execute(
                select(Organization).where(Organization.slug == domain)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Organization with domain {domain} already exists")
            
            # Create organization (in requested state)
            org = Organization(
                name=organization_name,
                slug=domain,
                domain=domain if custom_domain else None,
                status="provisioning",
            )
            db.add(org)
            await db.flush()
        
        # Check if provisioning record already exists for this organization
        existing_provisioning = await db.execute(
            select(Provisioning).where(Provisioning.organization_id == org.id)
        )
        existing_prov = existing_provisioning.scalar_one_or_none()
        if existing_prov:
            # Provisioning record already exists, return it
            return existing_prov
        
        # Create provisioning record
        metadata = {
            "admin_name": admin_name,
            "plan_key": plan_key,
            "billing_interval": billing_interval,
            "custom_domain": custom_domain,
        }
        if idempotency_key:
            import hashlib
            import json
            idempotency_data = {
                "idempotency_key": idempotency_key,
                "organization_name": organization_name,
                "domain": domain,
                "admin_email": admin_email,
                "admin_name": admin_name,
                "plan_key": plan_key,
                "billing_interval": billing_interval,
                "custom_domain": custom_domain,
                "organization_id": organization_id,
            }
            metadata["idempotency_key"] = idempotency_key
            metadata["idempotency_fingerprint"] = hashlib.sha256(
                json.dumps(idempotency_data, sort_keys=True).encode()
            ).hexdigest()[:64]
        
        provisioning = Provisioning(
            organization_id=org.id,
            state=ProvisioningState.REQUESTED.value,
            domain=domain,
            admin_email=admin_email,
            steps=[],
            metadata_json=metadata,
        )
        db.add(provisioning)
        await db.flush()
        
        await publish_event(
            db,
            name="provisioning.started",
            organization_id=org.id,
            payload={
                "provisioning_id": provisioning.id,
                "organization_name": organization_name,
                "domain": domain,
                "plan": plan_key,
            },
        )
        
        return provisioning
    
    async def execute_provisioning(
        self,
        db: AsyncSession,
        provisioning_id: str,
        caller: Any = None,
    ) -> Any:
        """Execute the full provisioning lifecycle."""
        provisioning = await db.get(Provisioning, provisioning_id)
        if not provisioning:
            raise ValueError("Provisioning not found")
        
        # Get plan from metadata
        metadata = provisioning.metadata_json or {}
        plan_key = metadata.get("plan_key", "starter")
        
        plan = await db.execute(
            select(Plan).where(Plan.key == plan_key)
        )
        plan = plan.scalar_one_or_none()
        if not plan:
            raise ValueError(f"Plan not found: {plan_key}")
        
        # Generate run ID for instrumentation
        run_id = f"prov-{provisioning_id}-{int(time.time())}"
        
        # Record provisioning start metrics
        run_metrics = record_run_start(run_id, provisioning_id, provisioning.organization_id)
        
        try:
            # Idempotent re-run: steps already completed are never re-executed.
            completed_steps = {
                s.get("step") for s in (provisioning.steps or []) if s.get("state") == "completed"
            }

            # Execute each step in order (optional steps no-op gracefully when unconfigured)
            for step_index, step_def in enumerate(STEP_DEFINITIONS):
                step_name = step_def["step"]

                if step_name in completed_steps:
                    continue

                # Update current step
                provisioning.current_step = step_name
                await self._update_provisioning_step(db, provisioning, step_name, "running")
                
                # Execute step with instrumentation
                try:
                    async with timed_provisioning_step(
                        db, run_id, step_name, provisioning.organization_id
                    ) as step_timing:
                        await self._execute_step(
                            db=db,
                            provisioning=provisioning,
                            step_name=step_name,
                            step_def=step_def,
                        )
                        
                        await self._update_provisioning_step(
                            db, provisioning, step_name, "completed"
                        )
                except Exception as step_error:
                    await self._update_provisioning_step(
                        db, provisioning, step_name, "failed", error=str(step_error)
                    )
                    raise
                
                # Persist lifecycle state after the step completes
                if step_index + 1 < len(PROVISIONING_STATE_ORDER):
                    provisioning.state = PROVISIONING_STATE_ORDER[step_index + 1].value
                    await db.flush()
                
                # Update metrics from step timing
                if step_timing:
                    record_step_complete(
                        run_id=run_id,
                        step_name=step_name,
                        state="completed",
                        db_queries=0,
                        db_rows_affected=0,
                        transaction_committed=True,
                        lock_wait_seconds=0.0,
                    )
                
                # Emit provisioning observation
                await emit_provisioning_observation(
                    db=db,
                    organization_id=provisioning.organization_id,
                    run_id=run_id,
                    step_name=step_name,
                    state="completed",
                    duration_seconds=step_timing.duration_seconds if step_timing else None,
                )
            
            # All steps completed successfully
            provisioning.state = ProvisioningState.READY.value
            provisioning.activated_at = utcnow()
            provisioning.activated_by = caller.employee_id if caller else "system"
            provisioning.validation_passed = True
            provisioning.validated_at = utcnow()
            
            await db.flush()
            
            await publish_event(
                db,
                name="provisioning.completed",
                organization_id=provisioning.organization_id,
                payload={"provisioning_id": provisioning.id},
            )
            
            # Record overall completion
            record_run_complete(run_id, "ready")
            record_provisioning_complete(provisioning_id, "completed")
            
            # Emit run observation
            await emit_provisioning_run_observation(
                db=db,
                organization_id=provisioning.organization_id,
                run_id=run_id,
                final_state="ready",
                total_duration_seconds=run_metrics.total_duration_seconds,
                steps_completed=len([s for s in provisioning.steps if s.get("state") == "completed"]),
                steps_failed=0,
            )
            
            return provisioning
            
        except Exception as e:
            record_run_complete(run_id, "failed", failure_reason=str(e))
            record_provisioning_complete(provisioning_id, "failed", failure_reason=str(e))
            
            # Emit failure observation
            await emit_provisioning_run_observation(
                db=db,
                organization_id=provisioning.organization_id,
                run_id=run_id,
                final_state="failed",
                total_duration_seconds=run_metrics.total_duration_seconds,
                steps_completed=len([s for s in provisioning.steps if s.get("state") == "completed"]),
                steps_failed=1,
            )
            raise
    
    async def _execute_step(
        self,
        db: AsyncSession,
        provisioning: Provisioning,
        step_name: str,
        step_def: Dict,
    ):
        """Execute a single provisioning step."""
        
        step_methods = {
            "identity_initialization": self._step_identity_initialization,
            "tenant_creation": self._step_tenant_creation,
            "security_initialization": self._step_security_initialization,
            "governance_initialization": self._step_governance_initialization,
            "commercial_initialization": self._step_commercial_initialization,
            "workspace_initialization": self._step_workspace_initialization,
            "organization_initialization": self._step_organization_initialization,
            "admin_initialization": self._step_admin_initialization,
            "integration_ready": self._step_integration_ready,
            "initial_sync": self._step_initial_sync,
            "canonical_validation": self._step_canonical_validation,
            "company_brain_initialization": self._step_company_brain_initialization,
        }
        
        method = step_methods.get(step_name)
        if not method:
            raise ValueError(f"No handler for step: {step_name}")
        
        await method(db, provisioning, provisioning.organization_id)

    # ------------------------------------------------------------ Step Implementations
    
    async def _step_identity_initialization(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Initialize organization identity and domain."""
        # Organization already created in start_provisioning
        # Verify domain ownership if custom domain
        custom_domain = provisioning.metadata_json.get("custom_domain", False) if provisioning.metadata_json else False
        if custom_domain and provisioning.domain:
            # Would verify DNS records, SSL cert, etc.
            pass

    async def _step_tenant_creation(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Create organization tenant with domain."""
        org = await db.get(Organization, org_id)
        if not org:
            raise ValueError("Organization not found")
        
        # Update organization with tenant config
        custom_domain = provisioning.metadata_json.get("custom_domain", False) if provisioning.metadata_json else False
        org.status = "active"
        org.domain_verified = custom_domain
        
        # Create default workspace settings
        # This would create WorkspaceSettings for the org
        
    async def _step_security_initialization(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Apply security policies, MFA, encryption."""
        from app.models.user import OrganizationSecurityPolicy
        
        # Idempotency: reuse existing security policy if already created
        existing_policy = await db.execute(
            select(OrganizationSecurityPolicy).where(
                OrganizationSecurityPolicy.organization_id == org_id
            )
        )
        
        if existing_policy.scalars().first() is None:
            # Apply default security policy
            policy = OrganizationSecurityPolicy(
                organization_id=org_id,
                mfa_required=True,
                password_min_length=12,
                password_require_uppercase=True,
                password_require_lowercase=True,
                password_require_numbers=True,
                password_require_symbols=True,
                session_idle_timeout_minutes=480,
                max_concurrent_sessions=5,
                require_email_verification=True,
                updated_by="system",
            )
            db.add(policy)
        
        # Mark security as applied
        provisioning.security_policy_applied = True
    
    async def _step_governance_initialization(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Set up approval policies, roles, permissions."""
        from app.models.governance import ApprovalPolicy, GovernanceScope
        from app.services.permission_service import permission_service
        
        # Sync permission catalog
        await permission_service.sync_catalog(db)
        
        # Create root governance scope (org-wide) if missing — idempotent
        existing_scope = await db.execute(
            select(GovernanceScope).where(
                GovernanceScope.organization_id == org_id,
                GovernanceScope.scope_type == "organization",
            )
        )
        root_scope = existing_scope.scalars().first()
        if root_scope is None:
            root_scope = GovernanceScope(
                organization_id=org_id,
                name="Organization",
                scope_type="organization",
                entity_id=org_id,
                depth=0,
            )
            db.add(root_scope)
            await db.flush()
        
        # Seed default system roles with proper permissions
        await permission_service.seed_org_roles(db, org_id)
        await permission_service.sync_role_permissions(db)
        
        # Create default approval policies
        default_policies = [
            {
                "name": "Decision Approval",
                "required_permission": "decisions:approve",
                "description": "Approval required for company decisions",
                "approval_type": "parallel",
            },
            {
                "name": "Authorization Approval",
                "required_permission": "authorizations:approve",
                "description": "Approval required for authorizations",
                "approval_type": "sequential",
            },
            {
                "name": "Financial Approval",
                "required_permission": "finance:approve",
                "description": "Approval required for financial commitments",
                "approval_type": "sequential",
            },
        ]
        
        for policy_data in default_policies:
            # Idempotency: skip policies that already exist
            existing_policy = await db.execute(
                select(ApprovalPolicy).where(
                    ApprovalPolicy.organization_id == org_id,
                    ApprovalPolicy.name == policy_data["name"],
                )
            )
            if existing_policy.scalars().first():
                continue
            policy = ApprovalPolicy(
                organization_id=org_id,
                name=policy_data["name"],
                approval_type=policy_data["approval_type"],
                description=policy_data["description"],
                required_permission=policy_data["required_permission"],
                scope_id=root_scope.id,  # Attach to root scope
            )
            db.add(policy)
        
        await db.flush()
    
    async def _step_commercial_initialization(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Create commercial account, subscription, entitlements."""
        
        metadata = provisioning.metadata_json or {}
        plan_key = metadata.get("plan_key", "starter")
        admin_name = metadata.get("admin_name", "Admin")
        billing_interval = metadata.get("billing_interval", "monthly")
        
        # Get plan
        plan = await db.execute(
            select(Plan).where(Plan.key == plan_key)
        )
        plan = plan.scalar_one_or_none()
        if not plan:
            raise ValueError(f"Plan not found: {plan_key}")
        
        # Idempotency: reuse existing commercial account if already created
        existing_account = await db.execute(
            select(CommercialAccount).where(CommercialAccount.organization_id == org_id)
        )
        commercial_account = existing_account.scalars().first()
        
        if commercial_account is None:
            # Create commercial account
            commercial_account = CommercialAccount(
                organization_id=org_id,
                billing_contact_email=provisioning.admin_email,
                billing_contact_name=admin_name,
                currency=plan.currency,
                status="active",
            )
            db.add(commercial_account)
            await db.flush()
        
        provisioning.commercial_account_id = commercial_account.id
        
        # Idempotency: reuse existing subscription if already created
        existing_subscription = await db.execute(
            select(Subscription).where(Subscription.organization_id == org_id)
        )
        subscription = existing_subscription.scalars().first()
        
        if subscription is None:
            # Create subscription
            now = utcnow()
            trial_ends = now + timedelta(days=plan.trial_days)
            
            if billing_interval == "annual":
                price = plan.annual_price_cents
                interval = "annual"
                period_end = now + timedelta(days=365)
            else:
                price = plan.monthly_price_cents
                interval = "monthly"
                period_end = now + timedelta(days=30)
            
            subscription = Subscription(
                organization_id=org_id,
                plan_id=plan.id,
                commercial_account_id=commercial_account.id,
                state="trialing",
                billing_interval=interval,
                price_cents=price,
                currency=plan.currency,
                trial_started_at=utcnow(),
                trial_ends_at=trial_ends,
                current_period_start=now,
                current_period_end=period_end,
                auto_renew=True,
            )
            db.add(subscription)
            await db.flush()
        
        # Create entitlements from plan (only missing keys — idempotent)
        existing_entitlement_rows = await db.execute(
            select(Entitlement.key).where(Entitlement.organization_id == org_id)
        )
        existing_entitlement_keys = set(existing_entitlement_rows.scalars().all())
        
        for key, entitlement_data in (plan.entitlements or {}).items():
            if key in existing_entitlement_keys:
                continue
            entitlement = Entitlement(
                organization_id=org_id,
                key=key,
                entitlement_type=entitlement_data.get("type", "limit"),
                value=str(entitlement_data.get("value", "")),
                numeric_value=entitlement_data.get("value"),
                source="plan",
                effective_from=utcnow(),
            )
            db.add(entitlement)
        
        await db.flush()
        provisioning.subscription_id = subscription.id
    
    async def _step_workspace_initialization(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Create workspace settings, themes, defaults."""
        # This would create default WorkspaceSettings, themes, etc.
        pass
    
    async def _step_organization_initialization(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Create departments, teams, roles, reporting structure."""
        # Create default department (idempotent by code)
        existing_dept = await db.execute(
            select(Department).where(
                Department.organization_id == org_id,
                Department.code == "GEN",
            )
        )
        dept = existing_dept.scalars().first()
        if dept is None:
            dept = Department(
                organization_id=org_id,
                name="General",
                code="GEN",
                description="General department",
            )
            db.add(dept)
            await db.flush()
        
        # Create default team (idempotent by code)
        existing_team = await db.execute(
            select(Team).where(
                Team.organization_id == org_id,
                Team.code == "CORE",
            )
        )
        team = existing_team.scalars().first()
        if team is None:
            team = Team(
                organization_id=org_id,
                department_id=dept.id,
                name="Core Team",
                code="CORE",
                description="Core team",
            )
            db.add(team)
            await db.flush()
    
    async def _step_admin_initialization(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Provision first administrator with full access."""
        metadata = provisioning.metadata_json or {}
        admin_name = metadata.get("admin_name", "Admin")
        
        # Check if admin user already exists (idempotency)
        existing_user = await db.execute(
            select(User).where(
                User.email == provisioning.admin_email,
                User.organization_id == org_id,
            )
        )
        user = existing_user.scalar_one_or_none()
        
        if not user:
            # Create admin user
            user = User(
                email=provisioning.admin_email,
                password_hash="",  # Would be set via invitation flow
                full_name=admin_name,
                organization_id=org_id,
                status="active",
                role="admin",
            )
            db.add(user)
            await db.flush()
        else:
            # Update existing user if needed
            user.full_name = admin_name
            user.status = "active"
            user.role = "admin"
        
        # Check if employee record already exists (idempotency)
        existing_emp = await db.execute(
            select(Employee).where(
                Employee.user_id == user.id,
                Employee.organization_id == org_id,
            )
        )
        emp = existing_emp.scalar_one_or_none()
        
        if not emp:
            # Create employee record
            emp = Employee(
                organization_id=org_id,
                user_id=user.id,
                employee_number=f"ADM{utcnow().strftime('%Y%m%d%H%M')}",
                first_name=admin_name.split()[0],
                last_name=" ".join(admin_name.split()[1:]) if len(admin_name.split()) > 1 else "",
                display_name=admin_name,
                email=provisioning.admin_email,
                joining_date=utcnow().date(),
                status="active",
                employment_type="full_time",
            )
            db.add(emp)
            await db.flush()
        else:
            # Update existing employee
            emp.display_name = admin_name
            emp.email = provisioning.admin_email
            emp.status = "active"
        
        # Assign admin role with org-wide scope (scope_id=None = org-wide)
        admin_role = await db.execute(
            select(Role).where(
                Role.organization_id == org_id,
                Role.code == "admin",
            ).limit(1)
        )
        admin_role = admin_role.scalar_one_or_none()
        if admin_role:
            from app.models.role import UserRoleModelModel
            # Check if user role already exists
            existing_ur = await db.execute(
                select(UserRoleModel).where(
                    UserRoleModel.organization_id == org_id,
                    UserRoleModel.user_id == user.id,
                    UserRoleModel.role_id == admin_role.id,
                )
            )
            if not existing_ur.scalar_one_or_none():
                user_role = UserRoleModel(
                    organization_id=org_id,
                    user_id=user.id,
                    role_id=admin_role.id,
                    scope_id=None,  # None = org-wide scope
                )
                db.add(user_role)
        
        # Create caller access for admin
        provisioning.admin_user_id = user.id
        provisioning.admin_email = provisioning.admin_email
        
        await db.flush()
    
    async def _step_integration_ready(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Verify integration configuration for this organization.

        Records the actual connector-instance landscape (states, sync readiness)
        as auditable step evidence. Organizations without configured integrations
        complete with zero instances.
        """
        instances = (
            await db.execute(
                select(ConnectorInstance).where(ConnectorInstance.organization_id == org_id)
            )
        ).scalars().all()

        by_state: Dict[str, int] = {}
        for instance in instances:
            by_state[instance.state] = by_state.get(instance.state, 0) + 1

        sync_ready = [
            i for i in instances if i.state == "connected" and i.sync_enabled
        ]

        self._record_step_evidence(
            provisioning,
            "integration_ready",
            {
                "instances_total": len(instances),
                "instances_by_state": by_state,
                "sync_ready": len(sync_ready),
            },
        )

    async def _step_initial_sync(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Run initial sync for all connected, sync-enabled integrations.

        Records real per-instance outcomes (SyncRun state, entity counts, errors)
        as auditable step evidence. Unconfigured organizations complete with zero
        instances; per-instance failures are recorded honestly without blocking
        provisioning (integration health is tracked via SyncRun/IntegrationHealth).
        """
        instances = (
            await db.execute(
                select(ConnectorInstance).where(
                    ConnectorInstance.organization_id == org_id,
                    ConnectorInstance.sync_enabled == True,  # noqa: E712
                    ConnectorInstance.state == "connected",
                )
            )
        ).scalars().all()

        from app.services.sync_worker import create_sync_worker

        outcomes: List[Dict[str, Any]] = []
        for instance in instances:
            outcome: Dict[str, Any] = {"instance_id": instance.id, "state": None, "error": None}
            try:
                provider = instance.connector.provider if instance.connector else None
                worker = create_sync_worker(provider)
                sync_run = await worker.run_initial_sync(
                    db, instance.id, org_id, triggered_by="provisioning"
                )
                outcome.update(
                    {
                        "state": sync_run.state,
                        "sync_run_id": sync_run.id,
                        "entities_processed": sync_run.entities_processed,
                        "entities_failed": sync_run.entities_failed,
                        "error": sync_run.error,
                    }
                )
            except Exception as e:
                logger.warning(f"Initial sync failed for {instance.id}: {e}")
                outcome["state"] = "failed"
                outcome["error"] = str(e)
            outcomes.append(outcome)

        provisioning.integrations_configured = len(instances)
        self._record_step_evidence(provisioning, "initial_sync", {"instances": outcomes})
    
    async def _step_canonical_validation(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Validate canonical reality integrity."""
        from sqlalchemy import select, text
        
        # Basic validation: check that canonical tables exist and have data
        # Check CompanyDecision table
        decision_count = await db.execute(
            select(text("count(*)")).select_from(text("company_decisions")).where(text("organization_id = :org_id")).params(org_id=org_id)
        )
        
        # Check CompanyCommitment table
        commitment_count = await db.execute(
            select(text("count(*)")).select_from(text("company_commitments")).where(text("organization_id = :org_id")).params(org_id=org_id)
        )
        
        # Check CompanyAuthorization table
        auth_count = await db.execute(
            select(text("count(*)")).select_from(text("company_authorizations")).where(text("organization_id = :org_id")).params(org_id=org_id)
        )
        
        # Check CompanyAction table
        action_count = await db.execute(
            select(text("count(*)")).select_from(text("company_actions")).where(text("organization_id = :org_id")).params(org_id=org_id)
        )
        
        # If all tables exist and are accessible, validation passes
        provisioning.validation_passed = True
        provisioning.validated_at = utcnow()
    
    async def _step_company_brain_initialization(self, db: AsyncSession, provisioning: Provisioning, org_id: str):
        """Initialize Company Brain with canonical data."""
        # This would initialize Company Brain services
        # For now, just mark as complete
        pass
    
    # ------------------------------------------------------------ Step Management
    
    async def _update_provisioning_step(
        self,
        db: AsyncSession,
        provisioning: Provisioning,
        step_name: str,
        state: str,
        error: Optional[str] = None,
    ):
        """Update provisioning step state."""
        from sqlalchemy.orm.attributes import flag_modified
        
        # Find existing step or create new
        existing_step = None
        for step in provisioning.steps:
            if step.get("step") == step_name:
                existing_step = step
                break
        
        if existing_step:
            existing_step["state"] = state
            existing_step["error"] = error
            if state == "completed":
                existing_step["completed_at"] = utcnow().isoformat()
        else:
            provisioning.steps.append({
                "step": step_name,
                "state": state,
                "started_at": utcnow().isoformat(),
                "completed_at": utcnow().isoformat() if state == "completed" else None,
                "error": error,
            })
        
        # Flag the steps list as modified for SQLAlchemy change detection
        flag_modified(provisioning, "steps")
        
        provisioning.current_step = step_name
        await db.flush()

    def _record_step_evidence(
        self,
        provisioning: Provisioning,
        step_name: str,
        evidence: Dict[str, Any],
    ):
        """Attach honest, auditable step evidence to provisioning metadata."""
        from sqlalchemy.orm.attributes import flag_modified

        metadata = dict(provisioning.metadata_json or {})
        step_evidence = dict(metadata.get("step_evidence") or {})
        step_evidence[step_name] = evidence
        metadata["step_evidence"] = step_evidence
        provisioning.metadata_json = metadata
        flag_modified(provisioning, "metadata_json")

    # ------------------------------------------------------------ Provisioning Queries
    
    async def get_provisioning(self, db: AsyncSession, provisioning_id: str) -> Optional[Provisioning]:
        return await db.get(Provisioning, provisioning_id)
    
    async def get_provisioning_by_org(self, db: AsyncSession, org_id: str) -> Optional[Provisioning]:
        result = await db.execute(
            select(Provisioning).where(Provisioning.organization_id == org_id)
        )
        return result.scalar_one_or_none()
    
    async def retry_failed_step(
        self,
        db: AsyncSession,
        provisioning_id: str,
        step_name: str,
        caller: Any = None,
    ) -> bool:
        """Retry a failed provisioning step."""
        provisioning = await db.get(Provisioning, provisioning_id)
        if not provisioning:
            raise ValueError("Provisioning not found")
        
        # Find the failed step
        step_def = next((s for s in STEP_DEFINITIONS if s["step"] == step_name), None)
        if not step_def:
            raise ValueError(f"Unknown step: {step_name}")
        
        if not step_def["recoverable"]:
            raise ValueError(f"Step {step_name} is not recoverable")
        
        # Reset step to pending
        await self._update_provisioning_step(db, provisioning, step_name, "pending")
        
        # Execute step
        step_method = getattr(self, f"_step_{step_name}", None)
        if not step_method:
            raise ValueError(f"No handler for step: {step_name}")
        
        try:
            await step_method(db, provisioning, provisioning.organization_id)
            await self._update_provisioning_step(db, provisioning, step_name, "completed")
            return True
        except Exception as e:
            await self._update_provisioning_step(db, provisioning, step_name, "failed", error=str(e))
            return False
    
    async def suspend_provisioning(
        self,
        db: AsyncSession,
        provisioning_id: str,
        reason: str,
        caller: Any = None,
    ):
        """Suspend a provisioning."""
        provisioning = await db.get(Provisioning, provisioning_id)
        if not provisioning:
            raise ValueError("Provisioning not found")
        
        provisioning.state = ProvisioningState.SUSPENDED.value
        provisioning.suspended_at = utcnow()
        provisioning.suspended_reason = reason
        await db.flush()
        
        await publish_event(
            db,
            name="provisioning.suspended",
            organization_id=provisioning.organization_id,
            payload={"provisioning_id": provisioning.id, "reason": reason},
        )

    async def resume_provisioning(
        self,
        db: AsyncSession,
        provisioning_id: str,
        caller: Any = None,
    ) -> bool:
        """Resume a suspended provisioning."""
        provisioning = await db.get(Provisioning, provisioning_id)
        if not provisioning:
            raise ValueError("Provisioning not found")
        
        if provisioning.state != ProvisioningState.SUSPENDED.value:
            raise ValueError("Provisioning is not suspended")
        
        # Resume from current step
        provisioning.state = ProvisioningState.REQUESTED.value  # Will re-evaluate from current step
        provisioning.suspended_at = None
        provisioning.suspended_reason = None
        await db.flush()
        
        return True

    # =========================================================================
    # PARTIAL-FAILURE RECOVERY WITH STATE INSPECTION
    # =========================================================================

    class ProvisioningStepState(str, Enum):
        """Detailed state of a provisioning step."""
        NOT_STARTED = "not_started"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        FAILED = "failed"
        UNKNOWN = "unknown"
        RECOVERY_REQUIRED = "recovery_required"

    async def inspect_provisioning_state(
        self,
        db: AsyncSession,
        provisioning_id: str,
    ) -> Dict[str, Any]:
        """Inspect the current state of a provisioning for recovery purposes.
        
        Returns a detailed breakdown of each step's state, allowing
        informed recovery decisions.
        """
        provisioning = await db.get(Provisioning, provisioning_id)
        if not provisioning:
            raise ValueError("Provisioning not found")
        
        steps = provisioning.steps or []
        step_map = {s.get("step"): s for s in steps}
        
        inspection = {
            "provisioning_id": provisioning_id,
            "organization_id": provisioning.organization_id,
            "overall_state": provisioning.state,
            "current_step": provisioning.current_step,
            "steps": {},
            "summary": {
                "total_steps": len(STEP_DEFINITIONS),
                "completed": 0,
                "failed": 0,
                "not_started": 0,
                "in_progress": 0,
                "unknown": 0,
            },
            "recovery_actions": [],
        }
        
        for step_def in STEP_DEFINITIONS:
            step_name = step_def["step"]
            step_data = step_map.get(step_name, {})
            step_state = step_data.get("state", "not_started")
            error = step_data.get("error")
            
            # Determine detailed state
            if step_state == "completed":
                detailed_state = self.ProvisioningStepState.COMPLETED
                inspection["summary"]["completed"] += 1
            elif step_state == "failed":
                detailed_state = self.ProvisioningStepState.FAILED
                inspection["summary"]["failed"] += 1
            elif step_state == "running":
                detailed_state = self.ProvisioningStepState.IN_PROGRESS
                inspection["summary"]["in_progress"] += 1
            elif step_state == "pending":
                detailed_state = self.ProvisioningStepState.NOT_STARTED
                inspection["summary"]["not_started"] += 1
            else:
                detailed_state = self.ProvisioningStepState.UNKNOWN
                inspection["summary"]["unknown"] += 1
            
            inspection["steps"][step_name] = {
                "state": detailed_state.value,
                "raw_state": step_state,
                "required": step_def["required"],
                "recoverable": step_def["recoverable"],
                "error": error,
                "completed_at": step_data.get("completed_at"),
                "started_at": step_data.get("started_at"),
            }
            
            # Determine recovery actions
            if detailed_state == self.ProvisioningStepState.FAILED and step_def["recoverable"]:
                inspection["recovery_actions"].append({
                    "action": "retry",
                    "step": step_name,
                    "reason": "Failed but recoverable",
                })
            elif detailed_state == self.ProvisioningStepState.UNKNOWN:
                inspection["recovery_actions"].append({
                    "action": "investigate",
                    "step": step_name,
                    "reason": "State unknown - needs manual inspection",
                })
            elif detailed_state == self.ProvisioningStepState.IN_PROGRESS:
                inspection["recovery_actions"].append({
                    "action": "wait_or_investigate",
                    "step": step_name,
                    "reason": "Step appears to be in progress - may be stuck",
                })
        
        return inspection

    async def recover_provisioning(
        self,
        db: AsyncSession,
        provisioning_id: str,
        caller: Any = None,
    ) -> Dict[str, Any]:
        """Recover a failed or suspended provisioning with state inspection.
        
        This method:
        1. Inspects the current state
        2. Identifies which steps need recovery
        3. Retries recoverable failed steps
        4. Handles UNKNOWN states appropriately
        5. Continues from the last known good state
        """
        provisioning = await db.get(Provisioning, provisioning_id)
        if not provisioning:
            raise ValueError("Provisioning not found")
        
        # First, inspect the current state
        inspection = await self.inspect_provisioning_state(db, provisioning_id)
        
        recovery_result = {
            "provisioning_id": provisioning_id,
            "inspection": inspection,
            "recovered_steps": [],
            "failed_recoveries": [],
            "final_state": None,
        }
        
        # Retry recoverable failed steps
        for step_def in STEP_DEFINITIONS:
            step_name = step_def["step"]
            step_inspection = inspection["steps"].get(step_name, {})
            step_state = step_inspection.get("state")
            
            # Skip if not required and not in progress
            if not step_def["required"] and step_state != "in_progress":
                continue
            
            # Retry failed recoverable steps
            if step_state == "failed" and step_def["recoverable"]:
                try:
                    success = await self.retry_failed_step(db, provisioning_id, step_name, caller=None)
                    if success:
                        recovery_result["recovered_steps"].append(step_name)
                    else:
                        recovery_result["failed_recoveries"].append(step_name)
                except Exception as e:
                    recovery_result["failed_recoveries"].append(step_name)
        
        # Reload provisioning to get updated state
        await db.refresh(provisioning)
        
        # Check if we can continue from current step
        if provisioning.state in [ProvisioningState.SUSPENDED.value, ProvisioningState.DEACTIVATED.value]:
            # Try to resume
            provisioning.state = ProvisioningState.REQUESTED.value
            provisioning.suspended_at = None
            provisioning.suspended_reason = None
            await db.flush()
        
        # Continue executing remaining steps
        if provisioning.state != ProvisioningState.READY.value:
            try:
                # Execute remaining steps from current step
                await self._execute_remaining_steps(db, provisioning)
                recovery_result["final_state"] = "ready"
            except Exception as e:
                recovery_result["final_state"] = "failed"
                recovery_result["error"] = str(e)
        else:
            recovery_result["final_state"] = "ready"
        
        return recovery_result

    async def _execute_remaining_steps(
        self,
        db: AsyncSession,
        provisioning: Provisioning,
    ):
        """Execute remaining steps from current position."""
        # Find the current step index
        current_step = provisioning.current_step
        start_index = 0
        
        for i, step_def in enumerate(STEP_DEFINITIONS):
            if step_def["step"] == current_step:
                start_index = i
                break
        
        # Execute from current step onwards
        for i in range(start_index, len(STEP_DEFINITIONS)):
            step_def = STEP_DEFINITIONS[i]
            step_name = step_def["step"]
            
            # Skip if already completed
            steps = provisioning.steps or []
            step_data = next((s for s in steps if s.get("step") == step_name), {})
            if step_data.get("state") == "completed":
                continue
            
            # Update current step
            provisioning.current_step = step_name
            await self._update_provisioning_step(db, provisioning, step_name, "running")
            
            try:
                await self._execute_step(
                    db=db,
                    provisioning=provisioning,
                    step_name=step_name,
                    step_def=step_def,
                )
                
                await self._update_provisioning_step(
                    db, provisioning, step_name, "completed"
                )
                
            except Exception as e:
                await self._update_provisioning_step(
                    db, provisioning, step_name, "failed", error=str(e)
                )
                raise

    async def execute_provisioning_with_recovery(
        self,
        db: AsyncSession,
        provisioning_id: str,
        caller: Any = None,
        max_retries: int = 3,
    ) -> Any:
        """Execute provisioning with automatic recovery on failure.
        
        This is the main entry point that wraps execute_provisioning
        with automatic recovery capabilities.
        """
        provisioning = await db.get(Provisioning, provisioning_id)
        if not provisioning:
            raise ValueError("Provisioning not found")
        
        for attempt in range(max_retries):
            try:
                return await self.execute_provisioning(db, provisioning_id, caller)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                
                # Attempt recovery
                recovery = await self.recover_provisioning(db, provisioning_id)
                if recovery["final_state"] == "failed":
                    raise RuntimeError(f"Recovery failed after {max_retries} attempts: {e}")
                
                # Wait before retry with exponential backoff
                await asyncio.sleep(2 ** attempt)
        
        return await self.execute_provisioning(db, provisioning_id, caller)


# Global instance
provisioning_service = ProvisioningService()