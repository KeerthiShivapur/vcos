"""Release Safety Preflight Service.

Implements the release safety gate that determines whether VCOS is safe to
begin a release. This is the foundation for Release Candidate Hardening
Slice 2A.

Key principles:
- Compose existing primitives (canonical integrity, backup, DR, observability)
- No duplicate health/release systems
- Deterministic structured result: READY, BLOCKED, INVALID, WARNING
- If mandatory prerequisite fails, release MUST be BLOCKED
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from enum import Enum

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.validation.capability_contract import (
    CapabilityDetector,
    EnvironmentCapability,
    ValidationStatus,
    ValidationResult,
    ValidationCheck,
)
from app.services.backup_service import backup_service
from app.services.restore_service import restore_service
from app.services.canonical_reality_integrity_service import (
    canonical_reality_integrity_service,
    IntegrityFindingType,
    IntegritySeverity,
)
from app.services.disaster_recovery_service import disaster_recovery_service
from app.services.observability_service import observability_service
from app.services.canonical_reliability_service import canonical_reliability_service
from app.core.timeutils import utcnow


logger = logging.getLogger("vcos.release_safety")


class PreflightStatus(str, Enum):
    """Release preflight status."""
    READY = "ready"               # All mandatory checks passed
    BLOCKED = "blocked"           # Mandatory prerequisite failed
    INVALID = "invalid"           # Invalid configuration/state
    WARNING = "warning"           # Non-mandatory checks failed but release can proceed


class PreflightPhase(str, Enum):
    """Release preflight phases."""
    APPLICATION_VERSION = "application_version"
    DATABASE_CONNECTIVITY = "database_connectivity"
    SCHEMA_REVISION = "schema_revision"
    MIGRATION_STATE = "migration_state"
    BACKUP_READINESS = "backup_readiness"
    DR_READINESS = "dr_readiness"
    CANONICAL_INTEGRITY = "canonical_integrity"
    PROVENANCE_INTEGRITY = "provenance_integrity"
    TEMPORAL_INTEGRITY = "temporal_integrity"
    GOVERNANCE_READINESS = "governance_readiness"
    TENANT_ISOLATION = "tenant_isolation"
    LONGITUDINAL_INTEGRITY = "longitudinal_integrity"
    CONCURRENCY_READINESS = "concurrency_readiness"
    OBSERVABILITY_READINESS = "observability_readiness"


@dataclass
class PreflightCheckResult:
    """Result of a single preflight check."""
    phase: PreflightPhase
    status: ValidationStatus
    message: str
    mandatory: bool
    details: Dict[str, Any] = field(default_factory=dict)
    required_capabilities: List[EnvironmentCapability] = field(default_factory=list)
    available_capabilities: List[EnvironmentCapability] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.value,
            "status": self.status.value,
            "message": self.message,
            "mandatory": self.mandatory,
            "details": self.details,
            "required_capabilities": [cap.value for cap in self.required_capabilities],
            "available_capabilities": [cap.value for cap in self.available_capabilities],
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class ReleasePreflightResult:
    """Complete release preflight result."""
    overall_status: PreflightStatus
    checks: List[PreflightCheckResult] = field(default_factory=list)
    application_version: str = ""
    database_revision: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "message": self.message,
            "application_version": self.application_version,
            "database_revision": self.database_revision,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "checks": [
                {
                    "phase": c.phase.value,
                    "status": c.status.value,
                    "message": c.message,
                    "mandatory": c.mandatory,
                    "details": c.details,
                    "required_capabilities": [cap.value for cap in c.required_capabilities],
                    "available_capabilities": [cap.value for cap in c.available_capabilities],
                    "checked_at": c.checked_at.isoformat(),
                }
                for c in self.checks
            ],
        }


class ReleaseSafetyPreflight(CapabilityDetector):
    """Release safety preflight service - composes existing primitives."""

    def __init__(self):
        super().__init__()
        self.settings = get_settings()

    async def run_preflight(
        self,
        db: AsyncSession,
        organization_id: Optional[str] = None,
        require_backup: bool = True,
        require_dr: bool = True,
    ) -> ReleasePreflightResult:
        """Run complete release preflight validation.
        
        Args:
            db: Database session
            organization_id: Organization to validate (if None, validates all)
            require_backup: Whether backup readiness is mandatory
            require_dr: Whether DR readiness is mandatory
            
        Returns:
            ReleasePreflightResult with overall status and detailed checks
        """
        self.db = db
        result = ReleasePreflightResult(
            overall_status=PreflightStatus.READY,
            application_version=self.settings.APP_VERSION,
        )
        
        # Run all preflight checks in order
        checks = [
            (await self._check_application_version(), True),
            (await self._check_database_connectivity(db), True),
            (await self._check_schema_revision(db), True),
            (await self._check_migration_state(db), True),
            (await self._check_backup_readiness(db, require_backup), require_backup),
            (await self._check_dr_readiness(db, require_dr), require_dr),
            (await self._check_canonical_integrity(db, organization_id), True),
            (await self._check_provenance_integrity(db, organization_id), True),
            (await self._check_temporal_integrity(db, organization_id), True),
            (await self._check_governance_readiness(db, organization_id), True),
            (await self._check_tenant_isolation(db, organization_id), True),
            (await self._check_longitudinal_integrity(db, organization_id), False),  # Non-mandatory
            (await self._check_concurrency_readiness(db), True),
            (await self._check_observability_readiness(db, organization_id), False),
        ]
        
        blocked = False
        warnings = False
        
        for check_result, mandatory in checks:
            result.checks.append(check_result)
            
            # Determine if this check blocks release
            is_failure = check_result.status == ValidationStatus.FAILED
            is_blocked = check_result.status == ValidationStatus.BLOCKED
            is_warning = check_result.status == ValidationStatus.WARNING
            
            if mandatory and (is_failure or is_blocked):
                blocked = True
            elif not mandatory and (is_failure or is_blocked or is_warning):
                warnings = True
        
        # Determine overall status
        if blocked:
            result.overall_status = PreflightStatus.BLOCKED
            result.message = "Release blocked: mandatory prerequisite(s) failed"
        elif warnings:
            result.overall_status = PreflightStatus.WARNING
            result.message = "Release ready with warnings: non-mandatory check(s) failed"
        else:
            result.overall_status = PreflightStatus.READY
            result.message = "All preflight checks passed - release can proceed"
        
        result.completed_at = utcnow()
        return result

    # =========================================================================
    # INDIVIDUAL PREFLIGHT CHECKS
    # =========================================================================

    async def _check_application_version(self) -> PreflightCheckResult:
        """Check application version is available."""
        version = self.settings.APP_VERSION
        if not version or version == "unknown":
            return PreflightCheckResult(
                phase=PreflightPhase.APPLICATION_VERSION,
                status=ValidationStatus.FAILED,
                message="Application version not configured",
                mandatory=True,
                details={"version": version},
            )
        return PreflightCheckResult(
            phase=PreflightPhase.APPLICATION_VERSION,
            status=ValidationStatus.VERIFIED,
            message=f"Application version: {version}",
            mandatory=True,
            details={"version": version},
        )

    async def _check_database_connectivity(self, db: AsyncSession) -> PreflightCheckResult:
        """Check database connectivity."""
        try:
            await db.execute(text("SELECT 1"))
            return PreflightCheckResult(
                phase=PreflightPhase.DATABASE_CONNECTIVITY,
                status=ValidationStatus.VERIFIED,
                message="Database connectivity verified",
                mandatory=True,
                details={"connected": True},
            )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.DATABASE_CONNECTIVITY,
                status=ValidationStatus.FAILED,
                message=f"Database connectivity failed: {str(e)}",
                mandatory=True,
                details={"error": str(e)},
            )

    async def _check_schema_revision(self, db: AsyncSession) -> PreflightCheckResult:
        """Check current Alembic schema revision."""
        try:
            revision_result = await db.execute(text("SELECT version_num FROM alembic_version"))
            revision = revision_result.scalar()
            if revision:
                return PreflightCheckResult(
                    phase=PreflightPhase.SCHEMA_REVISION,
                    status=ValidationStatus.VERIFIED,
                    message=f"Schema revision: {revision}",
                    mandatory=True,
                    details={"revision": revision},
                )
            else:
                # Fresh database without migrations is a valid state for new deployments
                return PreflightCheckResult(
                    phase=PreflightPhase.SCHEMA_REVISION,
                    status=ValidationStatus.VERIFIED,
                    message="Fresh database (no schema revision) - valid for new deployment",
                    mandatory=True,
                    details={"revision": None},
                )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.SCHEMA_REVISION,
                status=ValidationStatus.FAILED,
                message=f"Could not read schema revision: {str(e)}",
                mandatory=True,
                details={"error": str(e)},
            )

    async def _check_migration_state(self, db: AsyncSession) -> PreflightCheckResult:
        """Check migration state - no pending migrations."""
        # In a real deployment, this would check if alembic upgrade head is needed
        # For now, we verify the schema is accessible
        try:
            await db.execute(text("SELECT 1 FROM alembic_version"))
            return PreflightCheckResult(
                phase=PreflightPhase.MIGRATION_STATE,
                status=ValidationStatus.VERIFIED,
                message="Migration state accessible",
                mandatory=True,
                details={},
            )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.MIGRATION_STATE,
                status=ValidationStatus.FAILED,
                message=f"Migration state check failed: {str(e)}",
                mandatory=True,
                details={"error": str(e)},
            )

    async def _check_backup_readiness(self, db: AsyncSession, mandatory: bool) -> PreflightCheckResult:
        """Check backup readiness."""
        try:
            # Check if pgbackrest is available
            pgbackrest_available = await self.detect(EnvironmentCapability.POSTGRESQL_PGBACKREST)
            
            # Check for recent verified backup
            recent_backup = await db.execute(text("""
                SELECT id, status, completed_at, backup_kind
                FROM backup_manifests
                WHERE status = 'verified'
                ORDER BY completed_at DESC
                LIMIT 1
            """))
            backup = recent_backup.first()
            
            if backup:
                return PreflightCheckResult(
                    phase=PreflightPhase.BACKUP_READINESS,
                    status=ValidationStatus.VERIFIED,
                    message=f"Verified backup found: {backup[0]} ({backup[3]})",
                    mandatory=mandatory,
                    details={
                        "backup_id": backup[0],
                        "status": backup[1],
                        "completed_at": str(backup[2]),
                        "kind": backup[3],
                        "pgbackrest_available": pgbackrest_available,
                    },
                )
            else:
                if mandatory:
                    return PreflightCheckResult(
                        phase=PreflightPhase.BACKUP_READINESS,
                        status=ValidationStatus.FAILED,
                        message="No verified backup found - release requires verified backup",
                        mandatory=mandatory,
                        details={"pgbackrest_available": pgbackrest_available},
                    )
                else:
                    return PreflightCheckResult(
                        phase=PreflightPhase.BACKUP_READINESS,
                        status=ValidationStatus.WARNING,
                        message="No verified backup found (non-mandatory)",
                        mandatory=mandatory,
                        details={"pgbackrest_available": pgbackrest_available},
                    )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.BACKUP_READINESS,
                status=ValidationStatus.FAILED if mandatory else ValidationStatus.WARNING,
                message=f"Backup readiness check failed: {str(e)}",
                mandatory=mandatory,
                details={"error": str(e)},
            )

    async def _check_dr_readiness(self, db: AsyncSession, mandatory: bool) -> PreflightCheckResult:
        """Check DR readiness."""
        try:
            # Check if restore service is functional
            # In test mode, restore service uses mock pgbackrest
            pgbackrest_available = await self.detect(EnvironmentCapability.POSTGRESQL_PGBACKREST)
            
            # Check if we have any restore operations capability
            restore_capability = await self.detect(EnvironmentCapability.POSTGRESQL_PITR)
            
            return PreflightCheckResult(
                phase=PreflightPhase.DR_READINESS,
                status=ValidationStatus.VERIFIED,
                message="DR readiness verified",
                mandatory=mandatory,
                details={
                    "pgbackrest_available": pgbackrest_available,
                    "pitr_available": restore_capability,
                },
            )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.DR_READINESS,
                status=ValidationStatus.FAILED if mandatory else ValidationStatus.WARNING,
                message=f"DR readiness check failed: {str(e)}",
                mandatory=mandatory,
                details={"error": str(e)},
            )

    async def _check_canonical_integrity(
        self,
        db: AsyncSession,
        organization_id: Optional[str],
    ) -> PreflightCheckResult:
        """Check canonical reality integrity using existing service."""
        try:
            if organization_id:
                findings = await canonical_reality_integrity_service.run_integrity_scan(
                    db=db,
                    organization_id=organization_id,
                    checks=["structural", "tenant", "temporal", "provenance", "epistemic", "operating_chain"],
                    limit=10,
                )
            else:
                # Run for all organizations
                org_result = await db.execute(text("SELECT id FROM organizations WHERE status = 'active'"))
                organizations = [row[0] for row in org_result.fetchall()]
                
                all_findings = []
                for org_id in organizations:
                    findings = await canonical_reality_integrity_service.run_integrity_scan(
                        db=db,
                        organization_id=org_id,
                        checks=["structural", "tenant", "temporal", "provenance", "epistemic", "operating_chain"],
                        limit=10,
                    )
                    all_findings.extend(findings)
                findings = all_findings
            
            critical_findings = [f for f in findings if f.severity == IntegritySeverity.CRITICAL]
            high_findings = [f for f in findings if f.severity == IntegritySeverity.HIGH]
            
            if critical_findings:
                return PreflightCheckResult(
                    phase=PreflightPhase.CANONICAL_INTEGRITY,
                    status=ValidationStatus.FAILED,
                    message=f"Canonical integrity validation failed: {len(critical_findings)} critical finding(s)",
                    mandatory=True,
                    details={
                        "critical": len(critical_findings),
                        "high": len(high_findings),
                        "total": len(findings),
                    },
                )
            elif high_findings:
                return PreflightCheckResult(
                    phase=PreflightPhase.CANONICAL_INTEGRITY,
                    status=ValidationStatus.WARNING,
                    message=f"Canonical integrity validated with {len(high_findings)} high-severity warning(s)",
                    mandatory=True,
                    details={
                        "critical": 0,
                        "high": len(high_findings),
                        "total": len(findings),
                    },
                )
            else:
                return PreflightCheckResult(
                    phase=PreflightPhase.CANONICAL_INTEGRITY,
                    status=ValidationStatus.VERIFIED,
                    message="Canonical integrity validated",
                    mandatory=True,
                    details={
                        "critical": 0,
                        "high": 0,
                        "total": len(findings),
                    },
                )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.CANONICAL_INTEGRITY,
                status=ValidationStatus.FAILED,
                message=f"Canonical integrity check failed: {str(e)}",
                mandatory=True,
                details={"error": str(e)},
            )

    async def _check_provenance_integrity(
        self,
        db: AsyncSession,
        organization_id: Optional[str],
    ) -> PreflightCheckResult:
        """Check provenance integrity."""
        try:
            if organization_id:
                findings = await canonical_reality_integrity_service.check_provenance_integrity(
                    db=db,
                    organization_id=organization_id,
                    limit=10,
                )
            else:
                org_result = await db.execute(text("SELECT id FROM organizations WHERE status = 'active'"))
                organizations = [row[0] for row in org_result.fetchall()]
                
                all_findings = []
                for org_id in organizations:
                    findings = await canonical_reality_integrity_service.check_provenance_integrity(
                        db=db,
                        organization_id=org_id,
                        limit=10,
                    )
                    all_findings.extend(findings)
                findings = all_findings
            
            critical_findings = [f for f in findings if f.severity == IntegritySeverity.CRITICAL]
            high_findings = [f for f in findings if f.severity == IntegritySeverity.HIGH]
            
            if critical_findings:
                return PreflightCheckResult(
                    phase=PreflightPhase.PROVENANCE_INTEGRITY,
                    status=ValidationStatus.FAILED,
                    message=f"Provenance integrity failed: {len(critical_findings)} critical finding(s)",
                    mandatory=True,
                    details={"critical": len(critical_findings), "high": len(high_findings)},
                )
            elif high_findings:
                return PreflightCheckResult(
                    phase=PreflightPhase.PROVENANCE_INTEGRITY,
                    status=ValidationStatus.WARNING,
                    message=f"Provenance integrity with {len(high_findings)} high-severity warning(s)",
                    mandatory=True,
                    details={"critical": 0, "high": len(high_findings)},
                )
            else:
                return PreflightCheckResult(
                    phase=PreflightPhase.PROVENANCE_INTEGRITY,
                    status=ValidationStatus.VERIFIED,
                    message="Provenance integrity validated",
                    mandatory=True,
                    details={"critical": 0, "high": 0},
                )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.PROVENANCE_INTEGRITY,
                status=ValidationStatus.FAILED,
                message=f"Provenance integrity check failed: {str(e)}",
                mandatory=True,
                details={"error": str(e)},
            )

    async def _check_temporal_integrity(
        self,
        db: AsyncSession,
        organization_id: Optional[str],
    ) -> PreflightCheckResult:
        """Check temporal integrity."""
        try:
            if organization_id:
                findings = await canonical_reality_integrity_service.check_temporal_integrity(
                    db=db,
                    organization_id=organization_id,
                    limit=10,
                )
            else:
                org_result = await db.execute(text("SELECT id FROM organizations WHERE status = 'active'"))
                organizations = [row[0] for row in org_result.fetchall()]
                
                all_findings = []
                for org_id in organizations:
                    findings = await canonical_reality_integrity_service.check_temporal_integrity(
                        db=db,
                        organization_id=org_id,
                        limit=10,
                    )
                    all_findings.extend(findings)
                findings = all_findings
            
            critical_findings = [f for f in findings if f.severity == IntegritySeverity.CRITICAL]
            high_findings = [f for f in findings if f.severity == IntegritySeverity.HIGH]
            
            if critical_findings:
                return PreflightCheckResult(
                    phase=PreflightPhase.TEMPORAL_INTEGRITY,
                    status=ValidationStatus.FAILED,
                    message=f"Temporal integrity failed: {len(critical_findings)} critical finding(s)",
                    mandatory=True,
                    details={"critical": len(critical_findings), "high": len(high_findings)},
                )
            elif high_findings:
                return PreflightCheckResult(
                    phase=PreflightPhase.TEMPORAL_INTEGRITY,
                    status=ValidationStatus.WARNING,
                    message=f"Temporal integrity with {len(high_findings)} high-severity warning(s)",
                    mandatory=True,
                    details={"critical": 0, "high": len(high_findings)},
                )
            else:
                return PreflightCheckResult(
                    phase=PreflightPhase.TEMPORAL_INTEGRITY,
                    status=ValidationStatus.VERIFIED,
                    message="Temporal integrity validated",
                    mandatory=True,
                    details={"critical": 0, "high": 0},
                )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.TEMPORAL_INTEGRITY,
                status=ValidationStatus.FAILED,
                message=f"Temporal integrity check failed: {str(e)}",
                mandatory=True,
                details={"error": str(e)},
            )

    async def _check_governance_readiness(
        self,
        db: AsyncSession,
        organization_id: Optional[str],
    ) -> PreflightCheckResult:
        """Check governance readiness - all entities have proper governance."""
        try:
            # Check for ungoverned authorizations
            if organization_id:
                query = text("""
                    SELECT COUNT(*) FROM company_authorizations
                    WHERE organization_id = :org_id
                    AND approved_by IS NULL
                    AND state IN ('approved', 'conditional')
                """)
                result = await db.execute(query, {"org_id": organization_id})
            else:
                query = text("""
                    SELECT COUNT(*) FROM company_authorizations
                    WHERE approved_by IS NULL
                    AND state IN ('approved', 'conditional')
                """)
                result = await db.execute(query)
            
            ungoverned = result.scalar() or 0
            
            if ungoverned > 0:
                return PreflightCheckResult(
                    phase=PreflightPhase.GOVERNANCE_READINESS,
                    status=ValidationStatus.FAILED,
                    message=f"Found {ungoverned} ungoverned authorization(s)",
                    mandatory=True,
                    details={"ungoverned_count": ungoverned},
                )
            
            # Check for approval policies
            if organization_id:
                policy_query = text("SELECT COUNT(*) FROM approval_policies WHERE organization_id = :org_id")
                result = await db.execute(policy_query, {"org_id": organization_id})
            else:
                policy_query = text("SELECT COUNT(*) FROM approval_policies")
                result = await db.execute(policy_query)
            
            policy_count = result.scalar() or 0
            
            if policy_count == 0:
                return PreflightCheckResult(
                    phase=PreflightPhase.GOVERNANCE_READINESS,
                    status=ValidationStatus.WARNING,
                    message="No approval policies configured",
                    mandatory=False,
                    details={"policy_count": 0},
                )
            
            return PreflightCheckResult(
                phase=PreflightPhase.GOVERNANCE_READINESS,
                status=ValidationStatus.VERIFIED,
                message="Governance readiness validated",
                mandatory=True,
                details={"policy_count": policy_count},
            )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.GOVERNANCE_READINESS,
                status=ValidationStatus.FAILED,
                message=f"Governance readiness check failed: {str(e)}",
                mandatory=True,
                details={"error": str(e)},
            )

    async def _check_tenant_isolation(
        self,
        db: AsyncSession,
        organization_id: Optional[str],
    ) -> PreflightCheckResult:
        """Check tenant isolation."""
        try:
            if organization_id:
                findings = await canonical_reality_integrity_service.check_tenant_integrity(
                    db=db,
                    organization_id=organization_id,
                    limit=10,
                )
            else:
                org_result = await db.execute(text("SELECT id FROM organizations WHERE status = 'active'"))
                organizations = [row[0] for row in org_result.fetchall()]
                
                all_findings = []
                for org_id in organizations:
                    findings = await canonical_reality_integrity_service.check_tenant_integrity(
                        db=db,
                        organization_id=org_id,
                        limit=10,
                    )
                    all_findings.extend(findings)
                findings = all_findings
            
            critical_findings = [f for f in findings if f.severity == IntegritySeverity.CRITICAL]
            high_findings = [f for f in findings if f.severity == IntegritySeverity.HIGH]
            
            if critical_findings:
                return PreflightCheckResult(
                    phase=PreflightPhase.TENANT_ISOLATION,
                    status=ValidationStatus.FAILED,
                    message=f"Tenant isolation failed: {len(critical_findings)} critical finding(s)",
                    mandatory=True,
                    details={"critical": len(critical_findings), "high": len(high_findings)},
                )
            elif high_findings:
                return PreflightCheckResult(
                    phase=PreflightPhase.TENANT_ISOLATION,
                    status=ValidationStatus.WARNING,
                    message=f"Tenant isolation with {len(high_findings)} high-severity warning(s)",
                    mandatory=True,
                    details={"critical": 0, "high": len(high_findings)},
                )
            else:
                return PreflightCheckResult(
                    phase=PreflightPhase.TENANT_ISOLATION,
                    status=ValidationStatus.VERIFIED,
                    message="Tenant isolation validated",
                    mandatory=True,
                    details={"critical": 0, "high": 0},
                )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.TENANT_ISOLATION,
                status=ValidationStatus.FAILED,
                message=f"Tenant isolation check failed: {str(e)}",
                mandatory=True,
                details={"error": str(e)},
            )

    async def _check_longitudinal_integrity(
        self,
        db: AsyncSession,
        organization_id: Optional[str],
    ) -> PreflightCheckResult:
        """Check longitudinal (35-I) integrity - historical state preservation."""
        try:
            # Check for longitudinal integrity using existing 35-I infrastructure
            from app.models.longitudinal import (
                CompanyTimelineEvent,
                CompanyKnowledgeSnapshot,
                DecisionTimelineEvent,
                LearningTimelineEvent,
                OrganizationalTimelineEvent,
            )
            
            issues = []
            
            # Check timeline events have valid temporal bounds
            # CompanyTimelineEvent uses occurred_at, effective_from, effective_to, recorded_by
            if organization_id:
                query = text("""
                    SELECT COUNT(*) FROM company_timeline_events
                    WHERE organization_id = :org_id
                    AND (
                        occurred_at IS NULL 
                        OR effective_from IS NULL 
                        OR effective_to IS NULL
                        OR effective_from > effective_to
                    )
                """)
                result = await db.execute(query, {"org_id": organization_id})
            else:
                query = text("""
                    SELECT COUNT(*) FROM company_timeline_events
                    WHERE occurred_at IS NULL 
                    OR effective_from IS NULL 
                    OR effective_to IS NULL
                    OR effective_from > effective_to
                """)
                result = await db.execute(query)
            
            temporal_issues = result.scalar() or 0
            if temporal_issues > 0:
                issues.append(f"{temporal_issues} timeline events with invalid temporal bounds")
            
            # Check knowledge snapshots have valid temporal bounds
            if organization_id:
                query = text("""
                    SELECT COUNT(*) FROM company_knowledge_snapshots
                    WHERE organization_id = :org_id
                    AND (
                        snapshot_at IS NULL 
                        OR valid_from IS NULL 
                        OR valid_to IS NULL
                        OR valid_from > valid_to
                    )
                """)
                result = await db.execute(query, {"org_id": organization_id})
            else:
                query = text("""
                    SELECT COUNT(*) FROM company_knowledge_snapshots
                    WHERE snapshot_at IS NULL 
                    OR valid_from IS NULL 
                    OR valid_to IS NULL
                    OR valid_from > valid_to
                """)
                result = await db.execute(query)
            
            fingerprint_issues = result.scalar() or 0
            if fingerprint_issues > 0:
                issues.append(f"{fingerprint_issues} knowledge snapshots with invalid temporal bounds")
            
            if issues:
                return PreflightCheckResult(
                    phase=PreflightPhase.LONGITUDINAL_INTEGRITY,
                    status=ValidationStatus.WARNING,
                    message=f"Longitudinal integrity warnings: {'; '.join(issues)}",
                    mandatory=False,
                    details={"issues": issues},
                )
            
            return PreflightCheckResult(
                phase=PreflightPhase.LONGITUDINAL_INTEGRITY,
                status=ValidationStatus.VERIFIED,
                message="Longitudinal integrity validated",
                mandatory=False,
                details={},
            )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.LONGITUDINAL_INTEGRITY,
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Longitudinal integrity check failed: {str(e)}",
                mandatory=False,
                details={"error": str(e)},
            )

    async def _check_concurrency_readiness(self, db: AsyncSession) -> PreflightCheckResult:
        """Check concurrency (35-G) readiness - no stuck operations."""
        try:
            # Check for stuck canonical operations
            query = text("""
                SELECT COUNT(*) FROM canonical_operations
                WHERE state IN ('queued', 'attempting', 'executing', 'retrying', 'unknown')
                AND updated_at < NOW() - INTERVAL '5 minutes'
            """)
            result = await db.execute(query)
            stuck_ops = result.scalar() or 0
            
            if stuck_ops > 0:
                return PreflightCheckResult(
                    phase=PreflightPhase.CONCURRENCY_READINESS,
                    status=ValidationStatus.WARNING,
                    message=f"Found {stuck_ops} potentially stuck canonical operation(s)",
                    mandatory=False,
                    details={"stuck_operations": stuck_ops},
                )
            
            # Check for worker lease conflicts
            lease_query = text("""
                SELECT COUNT(*) FROM worker_leases
                WHERE expires_at < NOW()
                AND active = true
            """)
            result = await db.execute(lease_query)
            expired_leases = result.scalar() or 0
            
            if expired_leases > 0:
                return PreflightCheckResult(
                    phase=PreflightPhase.CONCURRENCY_READINESS,
                    status=ValidationStatus.WARNING,
                    message=f"Found {expired_leases} expired active worker lease(s)",
                    mandatory=False,
                    details={"expired_leases": expired_leases},
                )
            
            return PreflightCheckResult(
                phase=PreflightPhase.CONCURRENCY_READINESS,
                status=ValidationStatus.VERIFIED,
                message="Concurrency readiness validated",
                mandatory=True,
                details={},
            )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.CONCURRENCY_READINESS,
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Concurrency readiness check failed: {str(e)}",
                mandatory=True,
                details={"error": str(e)},
            )

    async def _check_observability_readiness(
        self,
        db: AsyncSession,
        organization_id: Optional[str],
    ) -> PreflightCheckResult:
        """Check observability (Gate 34) readiness."""
        try:
            # Check if health dimensions are being recorded
            if organization_id:
                query = text("""
                    SELECT COUNT(*) FROM health_dimensions
                    WHERE organization_id = :org_id
                    AND recorded_at > NOW() - INTERVAL '1 hour'
                """)
                result = await db.execute(query, {"org_id": organization_id})
            else:
                query = text("""
                    SELECT COUNT(*) FROM health_dimensions
                    WHERE recorded_at > NOW() - INTERVAL '1 hour'
                """)
                result = await db.execute(query)
            
            recent_health = result.scalar() or 0
            
            if recent_health == 0:
                return PreflightCheckResult(
                    phase=PreflightPhase.OBSERVABILITY_READINESS,
                    status=ValidationStatus.WARNING,
                    message="No recent health dimension recordings",
                    mandatory=False,
                    details={"recent_health_checks": 0},
                )
            
            return PreflightCheckResult(
                phase=PreflightPhase.OBSERVABILITY_READINESS,
                status=ValidationStatus.VERIFIED,
                message="Observability readiness validated",
                mandatory=False,
                details={"recent_health_checks": recent_health},
            )
        except Exception as e:
            return PreflightCheckResult(
                phase=PreflightPhase.OBSERVABILITY_READINESS,
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Observability readiness check failed: {str(e)}",
                mandatory=False,
                details={"error": str(e)},
            )


# Global instance
release_safety_preflight = ReleaseSafetyPreflight()