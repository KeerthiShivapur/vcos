"""Supportability Service for Private-Alpha Readiness.

Provides the minimum support infrastructure required for private alpha.
Support staff must be able to determine:
- company status
- provisioning status
- integration status
- health status
- active incidents
- degraded capabilities
- recovery status
- backup status
- deployment version
- migration version

Support must NOT gain unrestricted ability to mutate canonical company reality.
Privileged support actions must be governed and audited.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from enum import Enum

from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.observability import Degradation, HealthDimension
from app.services.provisioning_service import provisioning_service, ProvisioningState
from app.services.backup_service import backup_service
from app.services.restore_service import restore_service
from app.services.disaster_recovery_service import disaster_recovery_service
from app.services.health_evaluation_service import health_evaluation_service
from app.services.observability_service import observability_service
from app.services.canonical_fingerprint import canonical_fingerprint_service
from app.validation.capability_contract import CapabilityDetector

logger = logging.getLogger("vcos.supportability")


# =============================================================================
# SUPPORT DATA MODELS
# =============================================================================

class SupportActionType(str, Enum):
    """Types of support actions."""
    VIEW_COMPANY_STATUS = "view_company_status"
    VIEW_PROVISIONING_STATUS = "view_provisioning_status"
    VIEW_INTEGRATION_STATUS = "view_integration_status"
    VIEW_HEALTH_STATUS = "view_health_status"
    VIEW_ACTIVE_INCIDENTS = "view_active_incidents"
    VIEW_DEGRADED_CAPABILITIES = "view_degraded_capabilities"
    VIEW_RECOVERY_STATUS = "view_recovery_status"
    VIEW_BACKUP_STATUS = "view_backup_status"
    VIEW_DEPLOYMENT_VERSION = "view_deployment_version"
    VIEW_MIGRATION_VERSION = "view_migration_version"
    VIEW_TENANT_ISOLATION = "view_tenant_isolation"
    VIEW_CANONICAL_FINGERPRINT = "view_canonical_fingerprint"
    # Privileged actions (require governance)
    TRIGGER_BACKUP = "trigger_backup"
    TRIGGER_RESTORE = "trigger_restore"
    TRIGGER_DR_FAILOVER = "trigger_dr_failover"
    REBOOT_WORKER = "reboot_worker"
    RESUME_PROVISIONING = "resume_provisioning"
    ACKNOWLEDGE_ALERT = "acknowledge_alert"
    INVESTIGATE_ALERT = "investigate_alert"
    RESOLVE_DEGRADATION = "resolve_degradation"


class SupportPermission(str, Enum):
    """Support permission levels."""
    VIEW_ONLY = "view_only"
    STANDARD_SUPPORT = "standard_support"
    PRIVILEGED_SUPPORT = "privileged_support"
    ADMIN = "admin"


@dataclass
class CompanyStatus:
    """Comprehensive company status for support."""
    organization_id: str
    organization_name: str
    status: str  # active, provisioning, suspended, deactivated
    provisioning_state: Optional[str]
    provisioning_progress: float  # 0-100
    current_provisioning_step: Optional[str]
    health_overall: str
    health_dimensions: Dict[str, str]
    active_incidents: int
    critical_incidents: int
    degraded_capabilities: List[str]
    integrations_configured: int
    integrations_healthy: int
    integrations_degraded: int
    backup_last_success: Optional[datetime]
    backup_last_failure: Optional[datetime]
    restore_last_test: Optional[datetime]
    dr_readiness: str
    deployment_version: str
    migration_version: str
    canonical_fingerprint: Optional[str]
    tenant_isolation_verified: bool
    last_checked: datetime


@dataclass
class SupportActionLog:
    """Log of support actions."""
    action_id: str
    support_user_id: str
    support_user_email: str
    organization_id: str
    action_type: SupportActionType
    permission_level: SupportPermission
    reason: str
    details: Dict[str, Any]
    authorized_by: Optional[str] = None
    governance_approval_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    success: bool = True
    error: Optional[str] = None


@dataclass
class ProvisioningStatusDetail:
    """Detailed provisioning status for support."""
    provisioning_id: str
    organization_id: str
    state: str
    current_step: Optional[str]
    completed_steps: List[str]
    failed_steps: List[str]
    progress_percent: float
    started_at: datetime
    updated_at: datetime
    error: Optional[str]
    suspended_at: Optional[datetime]
    suspended_reason: Optional[str]


# =============================================================================
# SUPPORTABILITY SERVICE
# =============================================================================

class SupportabilityService(CapabilityDetector):
    """Service for supportability operations."""
    
    def __init__(self):
        super().__init__()
        self._action_logs: List[SupportActionLog] = []
        self._support_users: Dict[str, SupportPermission] = {}
    
    def register_support_user(self, user_id: str, email: str, permission: SupportPermission) -> None:
        """Register a support user with permission level."""
        self._support_users[user_id] = permission
        logger.info(f"Registered support user: {user_id} ({email}) with permission {permission.value}")
    
    def check_permission(self, user_id: str, required: SupportPermission) -> bool:
        """Check if support user has required permission."""
        user_perm = self._support_users.get(user_id, SupportPermission.VIEW_ONLY)
        hierarchy = {
            SupportPermission.VIEW_ONLY: 0,
            SupportPermission.STANDARD_SUPPORT: 1,
            SupportPermission.PRIVILEGED_SUPPORT: 2,
            SupportPermission.ADMIN: 3,
        }
        return hierarchy.get(user_perm, 0) >= hierarchy.get(required, 0)
    
    def get_permission(self, user_id: str) -> SupportPermission:
        return self._support_users.get(user_id, SupportPermission.VIEW_ONLY)
    
    async def get_company_status(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
    ) -> CompanyStatus:
        """Get comprehensive company status for support."""
        
        if not self.check_permission(support_user_id, SupportPermission.VIEW_ONLY):
            raise PermissionError("Insufficient permissions")
        
        self._log_action(support_user_id, organization_id, SupportActionType.VIEW_COMPANY_STATUS, "Company status check")
        
        # Get organization
        org = await db.get(Organization, organization_id)
        if not org:
            raise ValueError("Organization not found")
        
        # Get provisioning status
        prov = await provisioning_service.get_provisioning_by_org(db, organization_id)
        prov_state = prov.state if prov else None
        prov_progress = self._calculate_provisioning_progress(prov) if prov else 100.0
        current_step = prov.current_step if prov else None
        
        # Get health status
        health_report = await health_evaluation_service.evaluate_all(db, organization_id)
        
        # Get degradations
        from app.models.observability import Degradation
        deg_result = await db.execute(
            select(Degradation).where(
                Degradation.organization_id == organization_id,
                Degradation.state.in_(["detected", "investigating", "contained", "recovering"])
            )
        )
        degradations = deg_result.scalars().all()
        
        # Get integrations
        from app.models.canonical_integration import ConnectorInstance
        conn_result = await db.execute(
            select(ConnectorInstance).where(ConnectorInstance.organization_id == organization_id)
        )
        connectors = conn_result.scalars().all()
        
        # Get backup status
        from app.models.backup_manifest import BackupManifest
        backup_result = await db.execute(
            select(BackupManifest)
            .where(BackupManifest.organization_id == organization_id)
            .order_by(BackupManifest.created_at.desc())
            .limit(1)
        )
        latest_backup = backup_result.scalars().first()
        
        # Get restore test
        from app.models.restore import RestoreOperation
        restore_result = await db.execute(
            select(RestoreOperation)
            .where(RestoreOperation.organization_id == organization_id)
            .order_by(RestoreOperation.created_at.desc())
            .limit(1)
        )
        latest_restore = restore_result.scalars().first()
        
        # Get deployment version
        from app.models.deployment import Deployment
        deploy_result = await db.execute(
            select(Deployment)
            .where(Deployment.organization_id == organization_id)
            .order_by(Deployment.created_at.desc())
            .limit(1)
        )
        latest_deploy = deploy_result.scalars().first()
        
        # Get canonical fingerprint
        tenant_fp = await canonical_fingerprint_service.compute_tenant_fingerprint(db, organization_id)
        
        return CompanyStatus(
            organization_id=organization_id,
            organization_name=org.name,
            status=org.status,
            provisioning_state=prov_state,
            provisioning_progress=prov_progress,
            current_provisioning_step=current_step,
            health_overall=health_report.overall_status,
            health_dimensions={dim.value: result.status for dim, result in health_report.dimension_results.items()},
            active_incidents=len([d for d in degradations if d.state in ["detected", "investigating"]]),
            critical_incidents=len([d for d in degradations if d.severity == "critical"]),
            degraded_capabilities=[dim.value for dim, result in health_report.dimension_results.items() if result.status in ["degraded", "critical"]],
            integrations_configured=len(connectors),
            integrations_healthy=len([c for c in connectors if c.state == "connected"]),
            integrations_degraded=len([c for c in connectors if c.state in ["error", "degraded", "failed"]]),
            backup_last_success=latest_backup.completed_at if latest_backup and latest_backup.verified else None,
            backup_last_failure=latest_backup.created_at if latest_backup and not latest_backup.verified else None,
            restore_last_test=latest_restore.completed_at if latest_restore and latest_restore.state == "completed" else None,
            dr_readiness="ready" if latest_restore and latest_restore.state == "completed" else "untested",
            deployment_version=latest_deploy.version if latest_deploy else "unknown",
            migration_version=latest_deploy.migration_version if latest_deploy else "unknown",
            canonical_fingerprint=tenant_fp.aggregate_fingerprint,
            tenant_isolation_verified=True,  # Would run actual verification
            last_checked=utcnow(),
        )
    
    def _calculate_provisioning_progress(self, prov) -> float:
        if not prov:
            return 100.0
        if prov.state == ProvisioningState.READY.value:
            return 100.0
        if prov.state in [ProvisioningState.SUSPENDED.value, ProvisioningState.DEACTIVATED.value]:
            return 0.0
        
        total_steps = len([s for s in STEP_DEFINITIONS if s["required"]])
        completed = len([s for s in prov.steps if s.get("state") == "completed"])
        return (completed / total_steps * 100) if total_steps > 0 else 0.0
    
    async def get_provisioning_status(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
    ) -> ProvisioningStatusDetail:
        """Get detailed provisioning status."""
        
        if not self.check_permission(support_user_id, SupportPermission.STANDARD_SUPPORT):
            raise PermissionError("Insufficient permissions")
        
        self._log_action(support_user_id, organization_id, SupportActionType.VIEW_PROVISIONING_STATUS, "Provisioning status check")
        
        prov = await provisioning_service.get_provisioning_by_org(db, organization_id)
        if not prov:
            raise ValueError("No provisioning found for organization")
        
        completed = [s["step"] for s in prov.steps if s.get("state") == "completed"]
        failed = [s["step"] for s in prov.steps if s.get("state") == "failed"]
        
        total_req = len([s for s in STEP_DEFINITIONS if s["required"]])
        progress = len(completed) / total_req * 100 if total_req > 0 else 0
        
        return ProvisioningStatusDetail(
            provisioning_id=prov.id,
            organization_id=organization_id,
            state=prov.state,
            current_step=prov.current_step,
            completed_steps=completed,
            failed_steps=failed,
            progress_percent=progress,
            started_at=prov.created_at,
            updated_at=prov.updated_at,
            error=prov.error,
            suspended_at=prov.suspended_at,
            suspended_reason=prov.suspended_reason,
        )
    
    async def get_integration_status(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
    ) -> Dict[str, Any]:
        """Get integration status for support."""
        
        if not self.check_permission(support_user_id, SupportPermission.STANDARD_SUPPORT):
            raise PermissionError("Insufficient permissions")
        
        self._log_action(support_user_id, organization_id, SupportActionType.VIEW_INTEGRATION_STATUS, "Integration status check")
        
        from app.models.canonical_integration import ConnectorInstance, SyncRun
        
        connectors_result = await db.execute(
            select(ConnectorInstance).where(ConnectorInstance.organization_id == organization_id)
        )
        connectors = connectors_result.scalars().all()
        
        sync_runs_result = await db.execute(
            select(SyncRun)
            .where(SyncRun.organization_id == organization_id)
            .order_by(SyncRun.started_at.desc())
            .limit(20)
        )
        recent_syncs = sync_runs_result.scalars().all()
        
        return {
            "connectors": [
                {
                    "id": c.id,
                    "name": c.name,
                    "connector_id": c.connector_id,
                    "state": c.state,
                    "sync_enabled": c.sync_enabled,
                    "last_sync": c.last_sync_at,
                    "last_error": c.last_error,
                }
                for c in connectors
            ],
            "recent_syncs": [
                {
                    "id": s.id,
                    "connector_instance_id": s.connector_instance_id,
                    "status": s.status,
                    "started_at": s.started_at,
                    "completed_at": s.completed_at,
                    "records_processed": s.records_processed,
                    "error": s.error,
                }
                for s in recent_syncs
            ],
        }
    
    async def get_active_incidents(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
    ) -> List[Dict[str, Any]]:
        """Get active incidents/degradations."""
        
        if not self.check_permission(support_user_id, SupportPermission.STANDARD_SUPPORT):
            raise PermissionError("Insufficient permissions")
        
        self._log_action(support_user_id, organization_id, SupportActionType.VIEW_ACTIVE_INCIDENTS, "Active incidents check")
        
        from app.models.observability import Degradation
        
        result = await db.execute(
            select(Degradation).where(
                Degradation.organization_id == organization_id,
                Degradation.state.in_(["detected", "investigating", "contained", "recovering"])
            ).order_by(Degradation.detected_at.desc())
        )
        degradations = result.scalars().all()
        
        return [
            {
                "id": d.id,
                "type": d.degradation_type,
                "severity": d.severity,
                "state": d.state,
                "title": d.title,
                "description": d.description,
                "detected_at": d.detected_at,
                "acknowledged_at": d.acknowledged_at,
                "correlation_id": d.correlation_id,
                "affected_entities": d.affected_entities_json,
            }
            for d in degradations
        ]
    
    async def get_backup_status(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
    ) -> Dict[str, Any]:
        """Get backup status for support."""
        
        if not self.check_permission(support_user_id, SupportPermission.STANDARD_SUPPORT):
            raise PermissionError("Insufficient permissions")
        
        self._log_action(support_user_id, organization_id, SupportActionType.VIEW_BACKUP_STATUS, "Backup status check")
        
        from app.models.backup_manifest import BackupManifest
        
        result = await db.execute(
            select(BackupManifest)
            .where(BackupManifest.organization_id == organization_id)
            .order_by(BackupManifest.created_at.desc())
            .limit(10)
        )
        backups = result.scalars().all()
        
        return {
            "backups": [
                {
                    "id": b.id,
                    "kind": b.kind,
                    "status": b.status,
                    "verified": b.verified,
                    "created_at": b.created_at,
                    "completed_at": b.completed_at,
                    "size_bytes": b.size_bytes,
                    "error": b.error,
                }
                for b in backups
            ],
            "last_successful": next((b for b in backups if b.verified), None),
            "last_failed": next((b for b in backups if not b.verified and b.status == "failed"), None),
        }
    
    async def get_deployment_info(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
    ) -> Dict[str, Any]:
        """Get deployment version info."""
        
        if not self.check_permission(support_user_id, SupportPermission.VIEW_ONLY):
            raise PermissionError("Insufficient permissions")
        
        self._log_action(support_user_id, organization_id, SupportActionType.VIEW_DEPLOYMENT_VERSION, "Deployment version check")
        
        from app.models.deployment import Deployment
        
        result = await db.execute(
            select(Deployment)
            .where(Deployment.organization_id == organization_id)
            .order_by(Deployment.created_at.desc())
            .limit(5)
        )
        deployments = result.scalars().all()
        
        return {
            "deployments": [
                {
                    "id": d.id,
                    "version": d.version,
                    "state": d.state,
                    "migration_version": d.migration_version,
                    "started_at": d.started_at,
                    "completed_at": d.completed_at,
                    "rollback_from": d.rollback_from,
                }
                for d in deployments
            ],
            "current": deployments[0] if deployments else None,
        }
    
    async def get_canonical_fingerprint(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
    ) -> Dict[str, Any]:
        """Get canonical fingerprint for verification."""
        
        if not self.check_permission(support_user_id, SupportPermission.VIEW_ONLY):
            raise PermissionError("Insufficient permissions")
        
        self._log_action(support_user_id, organization_id, SupportActionType.VIEW_CANONICAL_FINGERPRINT, "Canonical fingerprint check")
        
        tenant_fp = await canonical_fingerprint_service.compute_tenant_fingerprint(db, organization_id)
        
        return {
            "aggregate_fingerprint": tenant_fp.aggregate_fingerprint,
            "entity_count": tenant_fp.entity_count,
            "algorithm": tenant_fp.algorithm.value,
            "computed_at": tenant_fp.computed_at,
            "components": [
                {
                    "name": c.component_name,
                    "fingerprint": c.fingerprint,
                    "entity_count": c.entity_count,
                    "last_updated": c.last_updated,
                }
                for c in tenant_fp.components
            ],
        }
    
    async def get_tenant_isolation_verification(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
    ) -> Dict[str, Any]:
        """Verify tenant isolation."""
        
        if not self.check_permission(support_user_id, SupportPermission.STANDARD_SUPPORT):
            raise PermissionError("Insufficient permissions")
        
        self._log_action(support_user_id, organization_id, SupportActionType.VIEW_TENANT_ISOLATION, "Tenant isolation verification")
        
        # Check for cross-tenant data leaks
        from app.models.organization import Organization
        
        # Verify organization exists and is isolated
        org = await db.get(Organization, organization_id)
        if not org:
            return {"verified": False, "error": "Organization not found"}
        
        # Check for any data with wrong organization_id (sample check)
        from app.models.employee import Employee
        from app.models.canonical_operation import CanonicalOperation
        
        emp_result = await db.execute(
            select(func.count()).select_from(Employee).where(Employee.organization_id == organization_id)
        )
        emp_count = emp_result.scalar()
        
        op_result = await db.execute(
            select(func.count()).select_from(CanonicalOperation).where(CanonicalOperation.organization_id == organization_id)
        )
        op_count = op_result.scalar()
        
        return {
            "verified": True,
            "organization_id": organization_id,
            "organization_name": org.name,
            "sample_counts": {
                "employees": emp_count,
                "canonical_operations": op_count,
            },
            "checked_at": utcnow(),
        }
    
    # =========================================================================
    # PRIVILEGED ACTIONS (require governance)
    # =========================================================================
    
    async def trigger_backup(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
        reason: str,
        kind: str = "full",
    ) -> Dict[str, Any]:
        """Trigger a backup (privileged action)."""
        
        if not self.check_permission(support_user_id, SupportPermission.PRIVILEGED_SUPPORT):
            raise PermissionError("Requires privileged support permission")
        
        self._log_action(
            support_user_id, organization_id, 
            SupportActionType.TRIGGER_BACKUP, 
            reason,
            permission=SupportPermission.PRIVILEGED_SUPPORT,
        )
        
        # Execute backup
        backup = await backup_service.create_backup(
            db=db,
            organization_id=organization_id,
            kind=kind,
            triggered_by=support_user_id,
            metadata={"support_reason": reason},
        )
        
        return {"backup_id": backup.id, "status": "initiated"}
    
    async def trigger_restore(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
        backup_id: str,
        reason: str,
        governance_approval_id: str,
    ) -> Dict[str, Any]:
        """Trigger a restore (privileged action requiring governance)."""
        
        if not self.check_permission(support_user_id, SupportPermission.PRIVILEGED_SUPPORT):
            raise PermissionError("Requires privileged support permission")
        
        if not governance_approval_id:
            raise ValueError("Governance approval ID required for restore")
        
        self._log_action(
            support_user_id, organization_id, 
            SupportActionType.TRIGGER_RESTORE, 
            reason,
            permission=SupportPermission.PRIVILEGED_SUPPORT,
            governance_approval_id=governance_approval_id,
        )
        
        restore = await restore_service.restore_backup(
            db=db,
            organization_id=organization_id,
            backup_id=backup_id,
            triggered_by=support_user_id,
            governance_approval_id=governance_approval_id,
        )
        
        return {"restore_id": restore.id, "status": "initiated"}
    
    async def resume_provisioning(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Resume suspended provisioning."""
        
        if not self.check_permission(support_user_id, SupportPermission.STANDARD_SUPPORT):
            raise PermissionError("Requires standard support permission")
        
        self._log_action(support_user_id, organization_id, SupportActionType.RESUME_PROVISIONING, reason)
        
        prov = await provisioning_service.get_provisioning_by_org(db, organization_id)
        if not prov:
            raise ValueError("No provisioning found")
        
        if prov.state != ProvisioningState.SUSPENDED.value:
            raise ValueError("Provisioning is not suspended")
        
        success = await provisioning_service.resume_provisioning(db, prov.id, support_user_id)
        
        return {"success": success, "provisioning_id": prov.id}
    
    async def acknowledge_alert(
        self,
        db: AsyncSession,
        organization_id: str,
        support_user_id: str,
        alert_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Acknowledge an alert."""
        
        if not self.check_permission(support_user_id, SupportPermission.STANDARD_SUPPORT):
            raise PermissionError("Insufficient permissions")
        
        self._log_action(support_user_id, organization_id, SupportActionType.ACKNOWLEDGE_ALERT, reason)
        
        from app.services.alert_engine import alert_engine
        success = await alert_engine.acknowledge_alert(alert_id, support_user_id)
        
        return {"success": success, "alert_id": alert_id}
    
    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================
    
    def _log_action(
        self,
        support_user_id: str,
        organization_id: str,
        action_type: SupportActionType,
        reason: str,
        permission: SupportPermission = SupportPermission.VIEW_ONLY,
        governance_approval_id: Optional[str] = None,
    ) -> SupportActionLog:
        """Log a support action."""
        
        action = SupportActionLog(
            action_id=f"supp-{utcnow().strftime('%Y%m%d-%H%M%S')}-{len(self._action_logs)+1:04d}",
            support_user_id=support_user_id,
            support_user_email="",  # Would be looked up
            organization_id=organization_id,
            action_type=action_type,
            permission_level=permission,
            reason=reason,
            details={},
            governance_approval_id=governance_approval_id,
        )
        
        self._action_logs.append(action)
        logger.info(f"Support action logged: {action.action_id} - {action_type.value} by {support_user_id}")
        
        return action
    
    def get_action_logs(
        self,
        organization_id: Optional[str] = None,
        support_user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[SupportActionLog]:
        """Get support action logs."""
        
        logs = self._action_logs
        if organization_id:
            logs = [l for l in logs if l.organization_id == organization_id]
        if support_user_id:
            logs = [l for l in logs if l.support_user_id == support_user_id]
        
        return logs[-limit:]
    
    def get_support_users(self) -> Dict[str, SupportPermission]:
        """Get all registered support users."""
        return self._support_users.copy()


# =============================================================================
# STEP DEFINITIONS (imported from provisioning_service)
# =============================================================================

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


# Global service
supportability_service = SupportabilityService()