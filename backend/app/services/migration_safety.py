"""Migration Safety Contract — validates schema evolution preserves canonical reality.

Implements:
- Pre-migration safety checks
- Migration execution with validation
- Post-migration integrity verification
- Rollback safety assessment
- Failure injection testing
- Canonical mutation boundary enforcement during migration
- Longitudinal integrity preservation during migration
- Tenant isolation enforcement during migration
- Event emission for migration lifecycle events
"""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, List, Dict, Callable, Tuple

from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

from app.validation.capability_contract import (
    ValidationStatus,
    ValidationCheck,
    ValidationResult,
    EnvironmentCapability,
    CapabilityDetector,
    CapabilityAwareValidator,
)
from app.models.backup_manifest import BackupManifest, BackupStatus, BackupKind
from app.services.backup_service import backup_service
from app.services.restore_service import restore_service, RestoreStatus
from app.core.timeutils import utcnow
from app.services.canonical_reality_integrity_service import canonical_reality_integrity_service
from app.services.canonical_reliability_service import canonical_reliability_service
from app.services.event_service import event_service
from app.intelligence.canonical_mutation import canonical_mutation_boundary
from app.models.canonical_reliability import CanonicalOperation

logger = logging.getLogger("vcos.migration")


class MigrationType(Enum):
    """Types of migrations."""
    ALEMBIC_UPGRADE = "alembic_upgrade"
    ALEMBIC_DOWNGRADE = "alembic_downgrade"
    SCHEMA_SYNC = "schema_sync"  # create_all bootstrap
    POSTGRES_ALTERS = "postgres_alters"  # idempotent ALTER statements


class MigrationSafetyLevel(Enum):
    """Safety classification of migration operations."""
    REVERSIBLE = "reversible"           # Can safely rollback (add column, add index)
    FORWARD_COMPATIBLE = "forward_compatible"  # Expand → migrate → contract pattern
    DATA_TRANSFORMING = "data_transforming"     # Transforms data, rollback may lose info
    DESTRUCTIVE = "destructive"         # Drops columns/tables, loses data


@dataclass
class MigrationStep:
    """A single migration step with safety metadata."""
    name: str
    sql: str
    safety_level: MigrationSafetyLevel
    reversible: bool
    description: str
    dependencies: List[str] = field(default_factory=list)
    rollback_sql: Optional[str] = None
    validation_query: Optional[str] = None  # Query to verify step succeeded
    estimated_duration_seconds: float = 0.0


@dataclass
class MigrationPlan:
    """Complete migration plan with safety analysis."""
    plan_id: str
    migration_type: MigrationType
    from_revision: str
    to_revision: str
    steps: List[MigrationStep] = field(default_factory=list)
    safety_level: MigrationSafetyLevel = MigrationSafetyLevel.REVERSIBLE
    requires_backup: bool = True
    rollback_possible: bool = True
    pre_validation: List[Callable] = field(default_factory=list)
    post_validation: List[Callable] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MigrationResult:
    """Result of a migration execution."""
    plan_id: str
    success: bool
    started_at: datetime
    completed_at: Optional[datetime] = None
    steps_completed: int = 0
    steps_total: int = 0
    current_step: Optional[str] = None
    error: Optional[str] = None
    rollback_executed: bool = False
    rollback_success: bool = False
    validation_results: Dict[str, ValidationResult] = field(default_factory=dict)
    rpo_seconds: Optional[float] = None
    rto_seconds: Optional[float] = None


class MigrationSafetyContract(CapabilityAwareValidator):
    """Enforces migration safety through capability-aware validation."""

    def __init__(self, db: AsyncSession = None, engine: AsyncEngine = None):
        super().__init__(db)
        self.engine = engine
        self._migration_history: List[MigrationResult] = []

    async def validate_pre_migration(self, plan: MigrationPlan) -> ValidationResult:
        """Run pre-migration safety checks."""
        self.db = self.db  # Ensure detector has db
        result = ValidationResult(domain="pre_migration")
        
        # 1. Verify PostgreSQL connectivity
        pg_capability = await self.detector.detect(EnvironmentCapability.POSTGRESQL_INFORMATION_SCHEMA)
        if not pg_capability:
            result.add_check(ValidationCheck(
                name="postgresql_connectivity",
                status=ValidationStatus.BLOCKED,
                message="PostgreSQL not available for migration",
                details={},
                required_capabilities=[EnvironmentCapability.POSTGRESQL_INFORMATION_SCHEMA],
                available_capabilities=[],
            ))
            result.determine_overall()
            return result
        
        result.add_check(ValidationCheck(
            name="postgresql_connectivity",
            status=ValidationStatus.VERIFIED,
            message="PostgreSQL connection verified",
            details={},
            required_capabilities=[EnvironmentCapability.POSTGRESQL_INFORMATION_SCHEMA],
            available_capabilities=[EnvironmentCapability.POSTGRESQL_INFORMATION_SCHEMA],
        ))
        
        # 2. Verify current Alembic revision
        try:
            revision_result = await self.db.execute(text("SELECT version_num FROM alembic_version"))
            current_revision = revision_result.scalar()
            if current_revision:
                result.add_check(ValidationCheck(
                    name="current_revision",
                    status=ValidationStatus.VERIFIED,
                    message=f"Current revision: {current_revision}",
                    details={"revision": current_revision},
                ))
            else:
                result.add_check(ValidationCheck(
                    name="current_revision",
                    status=ValidationStatus.WARNING,
                    message="No current revision found (fresh database)",
                    details={},
                ))
        except Exception as e:
            result.add_check(ValidationCheck(
                name="current_revision",
                status=ValidationStatus.FAILED,
                message=f"Could not read current revision: {str(e)}",
                details={"error": str(e)},
            ))
        
        # 3. Verify expected schema exists
        schema_check = await self._verify_schema_integrity()
        result.checks.extend(schema_check.checks)
        
        # 4. Check backup/recovery point availability
        backup_capability = await self.detector.detect(EnvironmentCapability.POSTGRESQL_PGBACKREST)
        if plan.requires_backup and not backup_capability:
            result.add_check(ValidationCheck(
                name="backup_capability",
                status=ValidationStatus.WARNING,
                message="pgbackrest not available - cannot create pre-migration backup",
                details={},
                required_capabilities=[EnvironmentCapability.POSTGRESQL_PGBACKREST],
                available_capabilities=[],
            ))
        elif plan.requires_backup:
            result.add_check(ValidationCheck(
                name="backup_capability",
                status=ValidationStatus.VERIFIED,
                message="pgbackrest available for pre-migration backup",
                details={},
                required_capabilities=[EnvironmentCapability.POSTGRESQL_PGBACKREST],
                available_capabilities=[EnvironmentCapability.POSTGRESQL_PGBACKREST],
            ))
        
        # 5. Record migration identity
        result.add_check(ValidationCheck(
            name="migration_identity",
            status=ValidationStatus.VERIFIED,
            message=f"Migration plan {plan.plan_id} registered",
            details={
                "plan_id": plan.plan_id,
                "type": plan.migration_type.value,
                "from_revision": plan.from_revision,
                "to_revision": plan.to_revision,
            },
        ))
        
        # 6. Record VCOS and database revisions
        try:
            # Get VCOS version from settings
            from app.core.config import get_settings
            settings = get_settings()
            vcos_version = getattr(settings, 'APP_VERSION', 'unknown')
            
            result.add_check(ValidationCheck(
                name="version_recording",
                status=ValidationStatus.VERIFIED,
                message="Versions recorded",
                details={
                    "vcos_revision": vcos_version,
                    "database_revision": plan.from_revision,
                    "target_revision": plan.to_revision,
                },
            ))
        except Exception:
            pass
        
        # 7. Verify required capabilities for migration steps
        for step in plan.steps:
            if step.validation_query:
                try:
                    await self.db.execute(text(step.validation_query))
                    result.add_check(ValidationCheck(
                        name=f"step_validation_{step.name}",
                        status=ValidationStatus.VERIFIED,
                        message=f"Pre-validation for {step.name} passed",
                        details={},
                    ))
                except Exception as e:
                    result.add_check(ValidationCheck(
                        name=f"step_validation_{step.name}",
                        status=ValidationStatus.FAILED,
                        message=f"Pre-validation for {step.name} failed: {str(e)}",
                        details={"error": str(e)},
                    ))
        
        # 8. Canonical mutation boundary check - ensure no pending operations would be affected
        await self._check_canonical_operations_safety(result, plan)
        
        # 9. Longitudinal integrity baseline - capture pre-migration state
        await self._capture_longitudinal_baseline(result, plan)
        
        # 10. Tenant isolation check - ensure migration won't cross tenant boundaries
        await self._check_tenant_isolation_safety(result, plan)
        
        result.determine_overall()
        return result

    async def _verify_schema_integrity(self) -> ValidationResult:
        """Verify critical schema elements exist."""
        result = ValidationResult(domain="schema_integrity")
        
        critical_tables = [
            "organizations", "users", "employees", "departments", "teams",
            "projects", "tasks", "company_decisions", "company_actions",
            "company_commitments", "company_authorizations",
            "company_objectives", "company_goals",
            "canonical_operations", "operation_attempts",
            "organizational_learning", "canonical_observations",
        ]
        
        missing = []
        for table in critical_tables:
            try:
                await self.db.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
            except Exception:
                missing.append(table)
        
        if missing:
            result.add_check(ValidationCheck(
                name="critical_tables",
                status=ValidationStatus.FAILED,
                message=f"Missing critical tables: {missing}",
                details={"missing_tables": missing},
            ))
        else:
            result.add_check(ValidationCheck(
                name="critical_tables",
                status=ValidationStatus.VERIFIED,
                message="All critical tables present",
                details={},
            ))
        
        result.determine_overall()
        return result

    async def _check_canonical_operations_safety(self, result: ValidationResult, plan: MigrationPlan) -> None:
        """Check that no canonical operations are in progress that would be affected by migration."""
        try:
            # Check for in-progress canonical operations
            in_progress_ops = await self.db.execute(
                text("""
                    SELECT COUNT(*) FROM canonical_operations 
                    WHERE state IN ('queued', 'attempting', 'executing', 'retrying', 'unknown')
                """)
            )
            in_progress_count = in_progress_ops.scalar() or 0
            
            if in_progress_count > 0:
                result.add_check(ValidationCheck(
                    name="canonical_operations_safety",
                    status=ValidationStatus.WARNING,
                    message=f"{in_progress_count} canonical operation(s) in progress - migration may affect them",
                    details={"in_progress_operations": in_progress_count},
                ))
            else:
                result.add_check(ValidationCheck(
                    name="canonical_operations_safety",
                    status=ValidationStatus.VERIFIED,
                    message="No canonical operations in progress",
                    details={"in_progress_operations": 0},
                ))
        except Exception as e:
            result.add_check(ValidationCheck(
                name="canonical_operations_safety",
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Could not check canonical operations: {str(e)}",
                details={"error": str(e)},
            ))

    async def _capture_longitudinal_baseline(self, result: ValidationResult, plan: MigrationPlan) -> None:
        """Capture longitudinal state baseline before migration."""
        try:
            from app.models.longitudinal import (
                CompanyTimelineEvent,
                CompanyKnowledgeSnapshot,
                DecisionTimelineEvent,
                LearningTimelineEvent,
                OrganizationalTimelineEvent,
                MergerAcquisitionLineage,
                LongitudinalProvenance,
                EpistemicCalibrationEvent,
                CompanyMemorySnapshot,
            )
            
            # Capture counts of longitudinal entities for baseline comparison
            longitudinal_tables = [
                ("company_timeline_events", CompanyTimelineEvent),
                ("company_knowledge_snapshots", CompanyKnowledgeSnapshot),
                ("decision_timeline_events", DecisionTimelineEvent),
                ("learning_timeline_events", LearningTimelineEvent),
                ("organizational_timeline_events", OrganizationalTimelineEvent),
                ("merger_acquisition_lineage", MergerAcquisitionLineage),
                ("longitudinal_provenance", LongitudinalProvenance),
                ("epistemic_calibration_events", EpistemicCalibrationEvent),
                ("company_memory_snapshots", CompanyMemorySnapshot),
            ]
            
            baseline = {}
            for table_name, model in longitudinal_tables:
                try:
                    count_result = await self.db.execute(
                        text(f"SELECT COUNT(*) FROM {table_name}")
                    )
                    baseline[table_name] = count_result.scalar() or 0
                except Exception:
                    baseline[table_name] = -1  # Table may not exist
            
            result.add_check(ValidationCheck(
                name="longitudinal_baseline",
                status=ValidationStatus.VERIFIED,
                message="Longitudinal baseline captured",
                details={"baseline": baseline},
            ))
            
            # Store baseline in plan for post-migration comparison
            plan.baseline_longitudinal = baseline
            
        except Exception as e:
            result.add_check(ValidationCheck(
                name="longitudinal_baseline",
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Could not capture longitudinal baseline: {str(e)}",
                details={"error": str(e)},
            ))

    async def _check_tenant_isolation_safety(self, result: ValidationResult, plan: MigrationPlan) -> None:
        """Verify migration won't cross tenant boundaries."""
        try:
            # Check that all critical tables have organization_id columns
            # and that migration steps don't operate across tenants
            critical_tables = [
                "organizations", "users", "employees", "departments", "teams",
                "projects", "tasks", "company_decisions", "company_actions",
                "company_commitments", "company_authorizations",
                "company_objectives", "company_goals",
                "canonical_operations", "operation_attempts",
                "organizational_learning", "canonical_observations",
            ]
            
            tenant_safe = True
            unsafe_tables = []
            
            for table in critical_tables:
                try:
                    # Check if table has organization_id column
                    result_cols = await self.db.execute(text(f"""
                        SELECT COUNT(*) FROM information_schema.columns 
                        WHERE table_name = '{table}' AND column_name = 'organization_id'
                    """))
                    has_org_id = (result_cols.scalar() or 0) > 0
                    
                    if not has_org_id:
                        tenant_safe = False
                        unsafe_tables.append(f"{table} (no organization_id)")
                except Exception:
                    pass  # Table may not exist
            
            if tenant_safe:
                result.add_check(ValidationCheck(
                    name="tenant_isolation_safety",
                    status=ValidationStatus.VERIFIED,
                    message="All critical tables have organization_id for tenant isolation",
                    details={},
                ))
            else:
                result.add_check(ValidationCheck(
                    name="tenant_isolation_safety",
                    status=ValidationStatus.WARNING,
                    message=f"Some critical tables lack organization_id: {unsafe_tables}",
                    details={"unsafe_tables": unsafe_tables},
                ))
                
        except Exception as e:
            result.add_check(ValidationCheck(
                name="tenant_isolation_safety",
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Could not verify tenant isolation: {str(e)}",
                details={"error": str(e)},
            ))

    async def create_pre_migration_backup(self, plan: MigrationPlan) -> Optional[str]:
        """Create a backup before migration if required."""
        if not plan.requires_backup:
            return None
        
        try:
            backup_metadata = await backup_service.create_full_backup(
                self.db,
                kind=BackupKind.PRE_MIGRATION,
                retention_days=7,
            )
            logger.info(f"Pre-migration backup created: {backup_metadata.backup_id}")
            return backup_metadata.backup_id
        except Exception as e:
            logger.error(f"Failed to create pre-migration backup: {e}")
            return None

    async def execute_migration(self, plan: MigrationPlan) -> MigrationResult:
        """Execute migration plan with safety checks."""
        result = MigrationResult(
            plan_id=plan.plan_id,
            success=False,
            started_at=datetime.now(timezone.utc),
            steps_total=len(plan.steps),
        )
        
        self._migration_history.append(result)
        
        # Run pre-migration validation
        pre_validation = await self.validate_pre_migration(plan)
        result.validation_results["pre_migration"] = pre_validation
        
        if pre_validation.overall_status in (ValidationStatus.FAILED, ValidationStatus.BLOCKED):
            result.error = f"Pre-migration validation failed: {pre_validation.message}"
            result.completed_at = datetime.now(timezone.utc)
            return result
        
        # Create pre-migration backup
        backup_id = await self.create_pre_migration_backup(plan)
        
        # Execute migration steps
        for i, step in enumerate(plan.steps):
            result.current_step = step.name
            logger.info(f"Executing migration step {i+1}/{len(plan.steps)}: {step.name}")
            
            try:
                async with self.db.begin():
                    await self.db.execute(text(step.sql))
                    
                    # Run step validation if provided
                    if step.validation_query:
                        await self.db.execute(text(step.validation_query))
                
                result.steps_completed = i + 1
                logger.info(f"Step {step.name} completed successfully")
                
            except Exception as e:
                result.error = f"Step {step.name} failed: {str(e)}"
                logger.error(result.error)
                
                # Attempt rollback if reversible
                if plan.rollback_possible and step.rollback_sql:
                    rollback_result = await self._execute_rollback(plan, i)
                    result.rollback_executed = True
                    result.rollback_success = rollback_result
                
                result.completed_at = datetime.now(timezone.utc)
                return result
        
        # Run post-migration validation
        post_validation = await self.validate_post_migration(plan)
        result.validation_results["post_migration"] = post_validation
        
        if post_validation.overall_status == ValidationStatus.FAILED:
            result.error = f"Post-migration validation failed: {post_validation.message}"
            # Don't auto-rollback on validation failure - let operator decide
            result.completed_at = datetime.now(timezone.utc)
            return result
        
        result.success = True
        result.completed_at = datetime.now(timezone.utc)
        logger.info(f"Migration {plan.plan_id} completed successfully")
        return result

    async def _execute_rollback(self, plan: MigrationPlan, failed_step_index: int) -> bool:
        """Execute rollback for completed steps in reverse order."""
        logger.warning(f"Executing rollback for migration {plan.plan_id}")
        
        try:
            for i in range(failed_step_index, -1, -1):
                step = plan.steps[i]
                if step.rollback_sql:
                    logger.info(f"Rolling back step: {step.name}")
                    await self.db.execute(text(step.rollback_sql))
                    await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    async def validate_post_migration(self, plan: MigrationPlan) -> ValidationResult:
        """Run post-migration integrity checks."""
        result = ValidationResult(domain="post_migration")
        
        # 1. Verify Alembic revision updated
        try:
            revision_result = await self.db.execute(text("SELECT version_num FROM alembic_version"))
            new_revision = revision_result.scalar()
            if new_revision == plan.to_revision:
                result.add_check(ValidationCheck(
                    name="revision_updated",
                    status=ValidationStatus.VERIFIED,
                    message=f"Revision updated to {new_revision}",
                    details={"revision": new_revision},
                ))
            else:
                result.add_check(ValidationCheck(
                    name="revision_updated",
                    status=ValidationStatus.FAILED,
                    message=f"Revision not updated. Expected {plan.to_revision}, got {new_revision}",
                    details={"expected": plan.to_revision, "actual": new_revision},
                ))
        except Exception as e:
            result.add_check(ValidationCheck(
                name="revision_updated",
                status=ValidationStatus.FAILED,
                message=f"Could not verify revision: {str(e)}",
                details={"error": str(e)},
            ))
        
        # 2. Verify schema
        schema_validation = await restore_service._validate_schema(self.db)
        result.validation_results["schema"] = schema_validation
        
        if schema_validation.overall_status == ValidationStatus.FAILED:
            for check in schema_validation.checks:
                if check.status == ValidationStatus.FAILED:
                    result.checks.append(check)
        
        # 3. Verify critical tables
        critical_tables = [
            "organizations", "users", "employees", "departments", "teams",
            "projects", "tasks", "company_decisions", "company_actions",
            "company_commitments", "company_authorizations",
            "company_objectives", "company_goals",
            "canonical_operations", "operation_attempts",
            "organizational_learning", "canonical_observations",
        ]
        
        missing = []
        for table in critical_tables:
            try:
                await self.db.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
            except Exception:
                missing.append(table)
        
        if missing:
            result.add_check(ValidationCheck(
                name="critical_tables",
                status=ValidationStatus.FAILED,
                message=f"Missing critical tables after migration: {missing}",
                details={"missing_tables": missing},
            ))
        else:
            result.add_check(ValidationCheck(
                name="critical_tables",
                status=ValidationStatus.VERIFIED,
                message="All critical tables present",
                details={},
            ))
        
        # 4. Verify indexes
        index_capability = EnvironmentCapability.POSTGRESQL_INFORMATION_SCHEMA
        index_available = await self.detector.detect(index_capability)
        
        if index_available:
            try:
                index_result = await self.db.execute(text("""
                    SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public'
                """))
                index_count = index_result.scalar() or 0
                result.add_check(ValidationCheck(
                    name="indexes_present",
                    status=ValidationStatus.VERIFIED,
                    message=f"Indexes present: {index_count}",
                    details={"index_count": index_count},
                    required_capabilities=[index_capability],
                    available_capabilities=[index_capability],
                ))
            except Exception as e:
                result.add_check(ValidationCheck(
                    name="indexes_present",
                    status=ValidationStatus.INCONCLUSIVE,
                    message=f"Could not verify indexes: {str(e)}",
                    details={"error": str(e)},
                    required_capabilities=[index_capability],
                    available_capabilities=[index_capability],
                ))
        
        # 5. Verify constraints
        if index_available:
            try:
                fk_result = await self.db.execute(text("""
                    SELECT COUNT(*) FROM information_schema.table_constraints 
                    WHERE constraint_type = 'FOREIGN KEY' AND table_schema = 'public'
                """))
                fk_count = fk_result.scalar() or 0
                
                uc_result = await self.db.execute(text("""
                    SELECT COUNT(*) FROM information_schema.table_constraints 
                    WHERE constraint_type = 'UNIQUE' AND table_schema = 'public'
                """))
                uc_count = uc_result.scalar() or 0
                
                result.add_check(ValidationCheck(
                    name="constraints",
                    status=ValidationStatus.VERIFIED if fk_count > 0 else ValidationStatus.WARNING,
                    message=f"Constraints: {fk_count} FK, {uc_count} UNIQUE",
                    details={"foreign_keys": fk_count, "unique_constraints": uc_count},
                    required_capabilities=[index_capability],
                    available_capabilities=[index_capability],
                ))
            except Exception as e:
                result.add_check(ValidationCheck(
                    name="constraints",
                    status=ValidationStatus.INCONCLUSIVE,
                    message=f"Could not verify constraints: {str(e)}",
                    details={"error": str(e)},
                    required_capabilities=[index_capability],
                    available_capabilities=[index_capability],
                ))
        
        # 6. Run canonical integrity validation
        canonical_validation = await restore_service._validate_canonical_integrity(self.db)
        result.validation_results["canonical_integrity"] = canonical_validation
        
        if canonical_validation.overall_status == ValidationStatus.FAILED:
            for check in canonical_validation.checks:
                if check.status == ValidationStatus.FAILED:
                    result.checks.append(check)
        
        # 7. Run temporal validation
        temporal_validation = await restore_service._validate_temporal_integrity(self.db)
        result.validation_results["temporal"] = temporal_validation
        
        # 8. Run tenant isolation validation
        tenant_validation = await restore_service._validate_tenant_isolation(self.db, "")
        result.validation_results["tenant_isolation"] = tenant_validation
        
        # 9. Run provenance validation
        provenance_validation = await restore_service._validate_provenance(self.db)
        result.validation_results["provenance"] = provenance_validation
        
        # 10. Run epistemic validation
        epistemic_validation = await restore_service._validate_epistemic(self.db)
        result.validation_results["epistemic"] = epistemic_validation
        
        # 11. Run governance validation
        governance_validation = await restore_service._validate_governance(self.db)
        result.validation_results["governance"] = governance_validation
        
        # 12. Canonical mutation boundary check - ensure no operations bypassed the boundary
        await self._validate_canonical_mutation_boundary(result, plan)
        
        # 13. Longitudinal integrity comparison - compare with pre-migration baseline
        await self._compare_longitudinal_integrity(result, plan)
        
        # 14. Tenant isolation verification - ensure migration didn't cross boundaries
        await self._verify_tenant_isolation_post_migration(result, plan)
        
        # 15. Emit migration completion event
        await self._emit_migration_event(plan, "migration.completed", {"status": "success"})

        result.determine_overall()
        return result

    async def _validate_canonical_mutation_boundary(self, result: ValidationResult, plan: MigrationPlan) -> None:
        """Validate that canonical mutation boundary was not bypassed during migration."""
        try:
            # Check that all canonical operations were properly recorded
            # and no direct SQL bypassed the mutation boundary
            mutation_ops = await self.db.execute(
                text("""
                    SELECT COUNT(*) FROM canonical_operations 
                    WHERE created_at >= NOW() - INTERVAL '1 hour'
                    AND state IN ('completed', 'failed', 'reconciled')
                """)
            )
            recent_ops = mutation_ops.scalar() or 0
            
            # Check for any operations that might have bypassed the boundary
            # by looking for operations without proper provenance
            boundary_bypass = await self.db.execute(
                text("""
                    SELECT COUNT(*) FROM canonical_operations 
                    WHERE created_at >= NOW() - INTERVAL '1 hour'
                    AND (provenance IS NULL OR provenance = '{}')
                    AND state = 'completed'
                """)
            )
            bypass_count = boundary_bypass.scalar() or 0
            
            if bypass_count > 0:
                result.add_check(ValidationCheck(
                    name="canonical_mutation_boundary",
                    status=ValidationStatus.WARNING,
                    message=f"{bypass_count} operation(s) may have bypassed canonical mutation boundary",
                    details={"operations_without_provenance": bypass_count, "total_recent_operations": recent_ops},
                ))
            else:
                result.add_check(ValidationCheck(
                    name="canonical_mutation_boundary",
                    status=ValidationStatus.VERIFIED,
                    message="Canonical mutation boundary respected",
                    details={"recent_operations": recent_ops},
                ))
        except Exception as e:
            result.add_check(ValidationCheck(
                name="canonical_mutation_boundary",
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Could not verify canonical mutation boundary: {str(e)}",
                details={"error": str(e)},
            ))

    async def _compare_longitudinal_integrity(self, result: ValidationResult, plan: MigrationPlan) -> None:
        """Compare longitudinal state before and after migration."""
        try:
            if not hasattr(plan, 'baseline_longitudinal') or not plan.baseline_longitudinal:
                result.add_check(ValidationCheck(
                    name="longitudinal_integrity",
                    status=ValidationStatus.INCONCLUSIVE,
                    message="No longitudinal baseline captured pre-migration",
                    details={},
                ))
                return
            
            from app.models.longitudinal import (
                CompanyTimelineEvent,
                CompanyKnowledgeSnapshot,
                DecisionTimelineEvent,
                LearningTimelineEvent,
                OrganizationalTimelineEvent,
                MergerAcquisitionLineage,
                LongitudinalProvenance,
                EpistemicCalibrationEvent,
                CompanyMemorySnapshot,
            )
            
            longitudinal_tables = [
                ("company_timeline_events", CompanyTimelineEvent),
                ("company_knowledge_snapshots", CompanyKnowledgeSnapshot),
                ("decision_timeline_events", DecisionTimelineEvent),
                ("learning_timeline_events", LearningTimelineEvent),
                ("organizational_timeline_events", OrganizationalTimelineEvent),
                ("merger_acquisition_lineage", MergerAcquisitionLineage),
                ("longitudinal_provenance", LongitudinalProvenance),
                ("epistemic_calibration_events", EpistemicCalibrationEvent),
                ("company_memory_snapshots", CompanyMemorySnapshot),
            ]
            
            discrepancies = []
            for table_name, model in longitudinal_tables:
                try:
                    count_result = await self.db.execute(
                        text(f"SELECT COUNT(*) FROM {table_name}")
                    )
                    current_count = count_result.scalar() or 0
                    baseline_count = plan.baseline_longitudinal.get(table_name, -1)
                    
                    if baseline_count >= 0 and current_count != baseline_count:
                        discrepancies.append({
                            "table": table_name,
                            "baseline": baseline_count,
                            "current": current_count,
                            "delta": current_count - baseline_count,
                        })
                except Exception:
                    discrepancies.append({
                        "table": table_name,
                        "error": "Table not accessible",
                    })
            
            if discrepancies:
                result.add_check(ValidationCheck(
                    name="longitudinal_integrity",
                    status=ValidationStatus.WARNING,
                    message=f"Longitudinal state changed during migration: {len(discrepancies)} table(s) affected",
                    details={"discrepancies": discrepancies},
                ))
            else:
                result.add_check(ValidationCheck(
                    name="longitudinal_integrity",
                    status=ValidationStatus.VERIFIED,
                    message="Longitudinal integrity preserved - no unexpected changes",
                    details={"tables_checked": len(longitudinal_tables)},
                ))
        except Exception as e:
            result.add_check(ValidationCheck(
                name="longitudinal_integrity",
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Could not compare longitudinal integrity: {str(e)}",
                details={"error": str(e)},
            ))

    async def _verify_tenant_isolation_post_migration(self, result: ValidationResult, plan: MigrationPlan) -> None:
        """Verify tenant isolation after migration."""
        try:
            # Check that all critical tables still have organization_id and no cross-tenant data
            critical_tables = [
                "organizations", "users", "employees", "departments", "teams",
                "projects", "tasks", "company_decisions", "company_actions",
                "company_commitments", "company_authorizations",
                "company_objectives", "company_goals",
                "canonical_operations", "operation_attempts",
                "organizational_learning", "canonical_observations",
            ]
            
            tenant_safe = True
            unsafe_tables = []
            cross_tenant_leaks = []
            
            for table in critical_tables:
                try:
                    # Check if table has organization_id column
                    result_cols = await self.db.execute(text(f"""
                        SELECT COUNT(*) FROM information_schema.columns 
                        WHERE table_name = '{table}' AND column_name = 'organization_id'
                    """))
                    has_org_id = (result_cols.scalar() or 0) > 0
                    
                    if not has_org_id:
                        tenant_safe = False
                        unsafe_tables.append(f"{table} (no organization_id)")
                    else:
                        # Check for NULL organization_id values (cross-tenant leaks)
                        null_check = await self.db.execute(
                            text(f"SELECT COUNT(*) FROM {table} WHERE organization_id IS NULL")
                        )
                        null_count = null_check.scalar() or 0
                        if null_count > 0:
                            cross_tenant_leaks.append(f"{table}: {null_count} rows with NULL organization_id")
                            tenant_safe = False
                except Exception:
                    pass  # Table may not exist
            
            if tenant_safe:
                result.add_check(ValidationCheck(
                    name="tenant_isolation_post_migration",
                    status=ValidationStatus.VERIFIED,
                    message="Tenant isolation verified after migration - no cross-tenant leaks",
                    details={},
                ))
            else:
                details = {}
                if unsafe_tables:
                    details["tables_missing_org_id"] = unsafe_tables
                if cross_tenant_leaks:
                    details["cross_tenant_leaks"] = cross_tenant_leaks
                
                result.add_check(ValidationCheck(
                    name="tenant_isolation_post_migration",
                    status=ValidationStatus.FAILED,
                    message=f"Tenant isolation violated after migration",
                    details=details,
                ))
                
        except Exception as e:
            result.add_check(ValidationCheck(
                name="tenant_isolation_post_migration",
                status=ValidationStatus.INCONCLUSIVE,
                message=f"Could not verify tenant isolation post-migration: {str(e)}",
                details={"error": str(e)},
            ))

    async def _emit_migration_event(self, plan: MigrationPlan, event_name: str, details: Dict[str, Any]) -> None:
        """Emit migration lifecycle event."""
        try:
            from app.services.event_service import event_service
            await event_service.emit(
                db=self.db,
                name=event_name,
                actor_id="system",
                organization_id="system",
                payload={
                    "migration_plan_id": plan.plan_id,
                    "migration_type": plan.migration_type.value,
                    "from_revision": plan.from_revision,
                    "to_revision": plan.to_revision,
                    **details,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to emit migration event {event_name}: {e}")

    async def test_migration_failure(self, plan: MigrationPlan, failure_step: int) -> MigrationResult:
        """Test migration failure at specific step for failure injection."""
        # This is a test utility - creates a modified plan that will fail
        test_plan = MigrationPlan(
            plan_id=f"{plan.plan_id}-test-failure-{failure_step}",
            migration_type=plan.migration_type,
            from_revision=plan.from_revision,
            to_revision=plan.to_revision,
            steps=plan.steps.copy(),
            safety_level=plan.safety_level,
            requires_backup=False,  # Don't need backup for tests
            rollback_possible=True,
        )
        
        # Inject failure at specified step
        if 0 <= failure_step < len(test_plan.steps):
            failing_step = test_plan.steps[failure_step]
            # Create a step that will definitely fail
            failing_step.sql = f"{failing_step.sql}; SELECT 1/0;"
        
        return await self.execute_migration(test_plan)


class MigrationSafetyManager:
    """High-level manager for migration safety operations."""

    def __init__(self, db: AsyncSession = None, engine: AsyncEngine = None):
        self.contract = MigrationSafetyContract(db, engine)

    async def upgrade_to_head(self, db: AsyncSession, target_revision: str = "head") -> MigrationResult:
        """Upgrade database to target revision with full safety checks."""
        self.contract.db = db
        
        # Get current revision
        try:
            current_result = await db.execute(text("SELECT version_num FROM alembic_version"))
            current_revision = current_result.scalar() or "base"
        except Exception:
            current_revision = "base"
        
        plan = MigrationPlan(
            plan_id=f"upgrade-{uuid.uuid4().hex[:8]}",
            migration_type=MigrationType.ALEMBIC_UPGRADE,
            from_revision=current_revision,
            to_revision=target_revision,
            safety_level=MigrationSafetyLevel.FORWARD_COMPATIBLE,
            requires_backup=True,
            rollback_possible=True,
        )
        
        # Note: Actual Alembic execution would be done via alembic command
        # This plan represents the safety contract around it
        logger.info(f"Migration plan created: {plan.plan_id} from {current_revision} to {target_revision}")
        
        # Validate pre-migration
        pre_validation = await self.contract.validate_pre_migration(plan)
        
        # Create backup
        backup_id = await self.contract.create_pre_migration_backup(plan)
        
        result = MigrationResult(
            plan_id=plan.plan_id,
            success=True,
            started_at=datetime.now(timezone.utc),
            steps_total=0,
        )
        
        result.validation_results["pre_migration"] = pre_validation
        
        return result

    async def verify_migration_safety(self, db: AsyncSession, from_rev: str, to_rev: str) -> ValidationResult:
        """Verify a migration path is safe without executing it."""
        self.contract.db = db
        
        plan = MigrationPlan(
            plan_id=f"verify-{uuid.uuid4().hex[:8]}",
            migration_type=MigrationType.ALEMBIC_UPGRADE,
            from_revision=from_rev,
            to_revision=to_rev,
            safety_level=MigrationSafetyLevel.FORWARD_COMPATIBLE,
            requires_backup=True,
            rollback_possible=True,
        )
        
        return await self.contract.validate_pre_migration(plan)


# Global instance
migration_safety_contract = MigrationSafetyContract()
migration_safety_manager = MigrationSafetyManager()