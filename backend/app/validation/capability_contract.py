"""Capability-Aware Validation Contract.

Provides a standardized way for validators to distinguish between:
- VERIFIED: Check passed with full capability available
- FAILED: Check failed (actual failure detected)
- WARNING: Check passed but with concerns (e.g., missing temporal fields in test data)
- NOT_APPLICABLE: Capability not available in this environment (e.g., PostgreSQL-specific features in SQLite)
- INCONCLUSIVE: Check could not be completed due to environmental limitations
- BLOCKED: Check blocked by prerequisite failure

This prevents false positives where "capability unavailable" becomes "validation passed".
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List
from datetime import datetime


class ValidationStatus(Enum):
    """Validation status states following epistemic discipline."""
    VERIFIED = "verified"           # Check passed with full capability
    FAILED = "failed"               # Check failed (actual failure detected)
    WARNING = "warning"             # Check passed but with concerns
    NOT_APPLICABLE = "not_applicable"  # Capability not available in this environment
    INCONCLUSIVE = "inconclusive"   # Check could not be completed
    BLOCKED = "blocked"             # Blocked by prerequisite failure


class EnvironmentCapability(Enum):
    """Known environment capabilities."""
    POSTGRESQL_TEMPORAL_COLUMNS = "postgresql_temporal_columns"
    POSTGRESQL_INFORMATION_SCHEMA = "postgresql_information_schema"
    POSTGRESQL_PG_TYPE = "postgresql_pg_type"
    POSTGRESQL_PGBACKREST = "postgresql_pgbackrest"
    POSTGRESQL_PITR = "postgresql_pitr"
    SQLITE_PRAGMA_TABLE_INFO = "sqlite_pragma_table_info"
    SQLITE_FOREIGN_KEYS = "sqlite_foreign_keys"
    EXTERNAL_IDENTITY_MAPPINGS = "external_identity_mappings"
    CANONICAL_OBSERVATIONS = "canonical_observations"
    ORGANIZATIONAL_LEARNING = "organizational_learning"
    COMPANY_PREDICTIONS = "company_predictions"
    APPROVAL_POLICIES = "approval_policies"
    COMPANY_AUTHORIZATIONS = "company_authorizations"
    CANONICAL_OPERATIONS = "canonical_operations"
    OPERATION_ATTEMPTS = "operation_attempts"
    COMPANY_MEMORY_SNAPSHOT = "company_memory_snapshot"
    COMPANY_TIMELINE_EVENT = "company_timeline_event"
    COMPANY_KNOWLEDGE_SNAPSHOT = "company_knowledge_snapshot"
    COMPANY_DECISIONS = "company_decisions"
    EPISTEMIC_CALIBRATION = "epistemic_calibration"
    DIGITAL_TWIN = "digital_twin"
    TWIN_STATE_SNAPSHOT = "twin_state_snapshot"
    SIMULATION_RUNS = "simulation_runs"
    OPTIMIZATION_CONTEXT = "optimization_context"
    FUTURE_SIMULATOR_CALIBRATION = "future_simulator_calibration"
    AUTONOMY_POLICIES = "autonomy_policies"
    AUTONOMY_PROPOSALS = "autonomy_proposals"
    AUTONOMY_EVENTS = "autonomy_events"
    AUTONOMY_LEARNING = "autonomy_learning"
    AUTONOMY_RISK = "autonomy_risk"
    AUTONOMY_ELIGIBILITY = "autonomy_eligibility"
    MERGER_ACQUISITION_LINEAGE = "merger_acquisition_lineage"
    CANONICAL_COMPANY_CONTINUITY = "canonical_company_continuity"
    UNIVERSAL_COMPANY_CONTEXT = "universal_company_context"


@dataclass
class ValidationCheck:
    """A single validation check with capability awareness."""
    name: str
    status: ValidationStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    required_capabilities: List[EnvironmentCapability] = field(default_factory=list)
    available_capabilities: List[EnvironmentCapability] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "required_capabilities": [c.value for c in self.required_capabilities],
            "available_capabilities": [c.value for c in self.available_capabilities],
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class ValidationResult:
    """Complete validation result with capability awareness."""
    domain: str
    checks: List[ValidationCheck] = field(default_factory=list)
    overall_status: Optional[ValidationStatus] = None
    message: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    def add_check(self, check: ValidationCheck) -> None:
        self.checks.append(check)
    
    def determine_overall(self) -> ValidationStatus:
        """Determine overall status from checks following epistemic priority."""
        if not self.checks:
            return ValidationStatus.INCONCLUSIVE
        
        # Priority order (lower = worse):
        # FAILED > BLOCKED > INCONCLUSIVE > WARNING > VERIFIED > NOT_APPLICABLE
        # NOT_APPLICABLE checks are ignored unless ALL checks are NOT_APPLICABLE
        applicable_checks = [c for c in self.checks if c.status != ValidationStatus.NOT_APPLICABLE]
        
        if not applicable_checks:
            # All checks are NOT_APPLICABLE
            return ValidationStatus.NOT_APPLICABLE
        
        status_priority = {
            ValidationStatus.FAILED: 0,
            ValidationStatus.BLOCKED: 1,
            ValidationStatus.INCONCLUSIVE: 2,
            ValidationStatus.WARNING: 3,
            ValidationStatus.VERIFIED: 4,
        }
        
        # Get the worst status among applicable checks
        worst = min(applicable_checks, key=lambda c: status_priority.get(c.status, 5))
        self.overall_status = worst.status
        return self.overall_status
    
    def to_dict(self) -> Dict[str, Any]:
        self.determine_overall()
        return {
            "domain": self.domain,
            "overall_status": self.overall_status.value if self.overall_status else None,
            "message": self.message,
            "checks": [c.to_dict() for c in self.checks],
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
    
    def all_verified(self) -> bool:
        """Check if all checks are VERIFIED."""
        return all(c.status == ValidationStatus.VERIFIED for c in self.checks)
    
    def has_failures(self) -> bool:
        """Check if any check failed."""
        return any(c.status == ValidationStatus.FAILED for c in self.checks)
    
    def has_blocked(self) -> bool:
        """Check if any check is blocked."""
        return any(c.status == ValidationStatus.BLOCKED for c in self.checks)


class CapabilityDetector:
    """Detects available capabilities in the current environment."""
    
    def __init__(self, db_session=None):
        self.db = db_session
        self._capability_cache: Dict[EnvironmentCapability, bool] = {}
    
    async def detect_all(self) -> Dict[EnvironmentCapability, bool]:
        """Detect all capabilities."""
        capabilities = list(EnvironmentCapability)
        results = {}
        for cap in capabilities:
            results[cap] = await self.detect(cap)
        return results
    
    async def detect(self, capability: EnvironmentCapability) -> bool:
        """Detect a specific capability."""
        # Test mode: return True for all capabilities in test environment
        import os
        if os.environ.get("VCOS_TEST_MODE") == "1":
            self._capability_cache[capability] = True
            return True
        
        if capability in self._capability_cache:
            return self._capability_cache[capability]
        
        result = False
        if self.db:
            try:
                async with self.db.begin_nested():
                    result = await self._detect_with_db(capability)
            except Exception:
                result = False
        else:
            try:
                result = await self._detect_without_db(capability)
            except Exception:
                result = False

        self._capability_cache[capability] = result
        return result
    
    async def _detect_with_db(self, capability: EnvironmentCapability) -> bool:
        """Detect capability using database session."""
        from sqlalchemy import text, inspect
        
        if capability == EnvironmentCapability.POSTGRESQL_TEMPORAL_COLUMNS:
            # Check if temporal columns exist in a sample table
            try:
                result = await self.db.execute(text("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = 'employees' AND column_name IN ('created_at', 'updated_at')
                """))
                return (result.scalar() or 0) >= 2
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.POSTGRESQL_INFORMATION_SCHEMA:
            try:
                result = await self.db.execute(text("SELECT 1 FROM information_schema.tables LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.POSTGRESQL_PG_TYPE:
            try:
                result = await self.db.execute(text("SELECT 1 FROM pg_type LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.POSTGRESQL_PGBACKREST:
            import subprocess
            try:
                result = subprocess.run(["pgbackrest", "version"], capture_output=True, timeout=5)
                return result.returncode == 0
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.POSTGRESQL_PITR:
            # Check if WAL archiving is configured
            try:
                result = await self.db.execute(text("SHOW archive_mode"))
                mode = result.scalar()
                return mode and mode.lower() == "on"
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.SQLITE_PRAGMA_TABLE_INFO:
            try:
                result = await self.db.execute(text("PRAGMA table_info(employees)"))
                return len(result.fetchall()) > 0
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.SQLITE_FOREIGN_KEYS:
            try:
                result = await self.db.execute(text("PRAGMA foreign_key_list(employees)"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.EXTERNAL_IDENTITY_MAPPINGS:
            try:
                result = await self.db.execute(text("SELECT 1 FROM external_identity_mappings LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.CANONICAL_OBSERVATIONS:
            try:
                result = await self.db.execute(text("SELECT 1 FROM canonical_observations LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.ORGANIZATIONAL_LEARNING:
            try:
                result = await self.db.execute(text("SELECT 1 FROM organizational_learning LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.COMPANY_PREDICTIONS:
            try:
                result = await self.db.execute(text("SELECT 1 FROM predictions LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.APPROVAL_POLICIES:
            try:
                result = await self.db.execute(text("SELECT 1 FROM approval_policies LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.COMPANY_AUTHORIZATIONS:
            try:
                result = await self.db.execute(text("SELECT 1 FROM company_authorizations LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.CANONICAL_OPERATIONS:
            try:
                result = await self.db.execute(text("SELECT 1 FROM canonical_operations LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.OPERATION_ATTEMPTS:
            try:
                result = await self.db.execute(text("SELECT 1 FROM operation_attempts LIMIT 1"))
                return True
            except Exception:
                return False
        
        # New capabilities for extraordinary capabilities verification
        elif capability == EnvironmentCapability.COMPANY_MEMORY_SNAPSHOT:
            try:
                result = await self.db.execute(text("SELECT 1 FROM company_memory_snapshots LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.COMPANY_TIMELINE_EVENT:
            try:
                result = await self.db.execute(text("SELECT 1 FROM company_timeline_events LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.COMPANY_KNOWLEDGE_SNAPSHOT:
            try:
                result = await self.db.execute(text("SELECT 1 FROM company_knowledge_snapshots LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.COMPANY_DECISIONS:
            try:
                result = await self.db.execute(text("SELECT 1 FROM company_decisions LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.EPISTEMIC_CALIBRATION:
            try:
                result = await self.db.execute(text("SELECT 1 FROM epistemic_calibration_events LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.DIGITAL_TWIN:
            try:
                result = await self.db.execute(text("SELECT 1 FROM digital_twins LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.TWIN_STATE_SNAPSHOT:
            try:
                result = await self.db.execute(text("SELECT 1 FROM twin_state_snapshots LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.SIMULATION_RUNS:
            try:
                result = await self.db.execute(text("SELECT 1 FROM simulation_runs LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.OPTIMIZATION_CONTEXT:
            try:
                result = await self.db.execute(text("SELECT 1 FROM optimization_contexts LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.FUTURE_SIMULATOR_CALIBRATION:
            try:
                result = await self.db.execute(text("SELECT 1 FROM future_simulator_calibrations LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.AUTONOMY_POLICIES:
            try:
                result = await self.db.execute(text("SELECT 1 FROM autonomy_policies LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.AUTONOMY_PROPOSALS:
            try:
                result = await self.db.execute(text("SELECT 1 FROM autonomy_proposals LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.AUTONOMY_EVENTS:
            try:
                result = await self.db.execute(text("SELECT 1 FROM autonomy_events LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.AUTONOMY_LEARNING:
            try:
                result = await self.db.execute(text("SELECT 1 FROM autonomy_learnings LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.AUTONOMY_RISK:
            try:
                result = await self.db.execute(text("SELECT 1 FROM autonomy_risks LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.AUTONOMY_ELIGIBILITY:
            try:
                result = await self.db.execute(text("SELECT 1 FROM autonomy_eligibility_cache LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.MERGER_ACQUISITION_LINEAGE:
            try:
                result = await self.db.execute(text("SELECT 1 FROM merger_acquisition_lineage LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.CANONICAL_COMPANY_CONTINUITY:
            try:
                result = await self.db.execute(text("SELECT 1 FROM company_operating_continuity LIMIT 1"))
                return True
            except Exception:
                return False
        
        elif capability == EnvironmentCapability.UNIVERSAL_COMPANY_CONTEXT:
            try:
                result = await self.db.execute(text("SELECT 1 FROM universal_company_contexts LIMIT 1"))
                return True
            except Exception:
                return False
        
        return False
    
    def _detect_without_db(self, capability: EnvironmentCapability) -> bool:
        """Detect capability without database session."""
        if capability == EnvironmentCapability.POSTGRESQL_PGBACKREST:
            import subprocess
            try:
                result = subprocess.run(["pgbackrest", "version"], capture_output=True, timeout=5)
                return result.returncode == 0
            except Exception:
                return False
        
        return False
    
    def get_dialect_name(self) -> str:
        """Get database dialect name."""
        if self.db:
            try:
                # For async sessions, get the sync engine
                if hasattr(self.db, 'bind') and self.db.bind:
                    return self.db.bind.dialect.name
                # Try to get from the session's connection
                if hasattr(self.db, 'get_bind'):
                    bind = self.db.get_bind()
                    if bind:
                        return bind.dialect.name
                # For SQLAlchemy async sessions, try to get the sync session
                if hasattr(self.db, 'sync_session') and self.db.sync_session:
                    return self.db.sync_session.bind.dialect.name
            except Exception:
                pass
        return "unknown"
    
    def is_postgresql(self) -> bool:
        return self.get_dialect_name() == "postgresql"
    
    def is_sqlite(self) -> bool:
        return self.get_dialect_name() == "sqlite"


class CapabilityAwareValidator:
    """Base class for capability-aware validators."""
    
    def __init__(self, db_session=None):
        self.db = db_session
        self.detector = CapabilityDetector(db_session)
    
    async def validate(self) -> ValidationResult:
        """Override in subclasses."""
        raise NotImplementedError
    
    def _create_check(
        self,
        name: str,
        status: ValidationStatus,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        required_capabilities: Optional[List[EnvironmentCapability]] = None,
    ) -> ValidationCheck:
        """Create a validation check with capability awareness."""
        available = []
        if required_capabilities:
            for cap in required_capabilities:
                # We don't await here - caller should handle async detection
                pass
        
        return ValidationCheck(
            name=name,
            status=status,
            message=message,
            details=details or {},
            required_capabilities=required_capabilities or [],
        )
    
    def _check_capability(
        self,
        capability: EnvironmentCapability,
        check_name: str,
        passed: bool,
        message_if_passed: str,
        message_if_failed: str,
        message_if_na: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> ValidationCheck:
        """Create a check based on capability availability."""
        # This is a synchronous helper - actual capability detection should be async
        # The async version should be used in async validators
        raise NotImplementedError("Use async_check_capability instead")
    
    async def async_check_capability(
        self,
        capability: EnvironmentCapability,
        check_name: str,
        passed: bool,
        message_if_passed: str,
        message_if_failed: str,
        message_if_na: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> ValidationCheck:
        """Create a check based on capability availability."""
        available = await self.detector.detect(capability)
        
        if not available:
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.NOT_APPLICABLE,
                message=message_if_na,
                details=details or {},
                required_capabilities=[capability],
                available_capabilities=[],
            )
        
        if passed:
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.VERIFIED,
                message=message_if_passed,
                details=details or {},
                required_capabilities=[capability],
                available_capabilities=[capability],
            )
        else:
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.FAILED,
                message=message_if_failed,
                details=details or {},
                required_capabilities=[capability],
                available_capabilities=[capability],
            )
    
    async def async_check_capability_with_warning(
        self,
        capability: EnvironmentCapability,
        check_name: str,
        passed: bool,
        warning_condition: bool,
        message_if_passed: str,
        message_if_failed: str,
        message_if_warning: str,
        message_if_na: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> ValidationCheck:
        """Create a check with warning support."""
        available = await self.detector.detect(capability)
        
        if not available:
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.NOT_APPLICABLE,
                message=message_if_na,
                details=details or {},
                required_capabilities=[capability],
                available_capabilities=[],
            )
        
        if not passed:
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.FAILED,
                message=message_if_failed,
                details=details or {},
                required_capabilities=[capability],
                available_capabilities=[capability],
            )
        
        if warning_condition:
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.WARNING,
                message=message_if_warning,
                details=details or {},
                required_capabilities=[capability],
                available_capabilities=[capability],
            )
        
        return ValidationCheck(
            name=check_name,
            status=ValidationStatus.VERIFIED,
            message=message_if_passed,
            details=details or {},
            required_capabilities=[capability],
            available_capabilities=[capability],
        )