"""Recovery Readiness Gates — explicit state machine for recovery validation.

Implements the recovery readiness lifecycle with explicit gates that must pass
before a restored database can be activated.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.validation.capability_contract import (
    ValidationStatus,
    ValidationResult,
    ValidationCheck,
    CapabilityDetector,
    CapabilityAwareValidator,
    EnvironmentCapability,
)
from app.models.backup_manifest import (
    BackupManifest,
    RestoreOperation,
    BackupStatus,
)
from app.services.post_restore_validator import post_restore_canonical_validator, ValidationVerdict

logger = logging.getLogger("vcos.recovery_gates")


class RecoveryGateState(str, Enum):
    """Recovery gate states."""
    CREATED = "created"
    PREFLIGHTED = "preflighted"
    BACKUP_SELECTED = "backup_selected"
    BACKUP_VERIFIED = "backup_verified"
    RESTORE_INITIALIZED = "restore_initialized"
    DATABASE_RESTORED = "database_restored"
    WAL_REPLAYED = "wal_replayed"
    SCHEMA_VALIDATED = "schema_validated"
    CANONICAL_VALIDATED = "canonical_validated"
    TENANT_VALIDATED = "tenant_validated"
    TEMPORAL_VALIDATED = "temporal_validated"
    PROVENANCE_VALIDATED = "provenance_validated"
    GOVERNANCE_VALIDATED = "governance_validated"
    LONGITUDINAL_VALIDATED = "longitudinal_validated"
    DEPENDENCIES_VALIDATED = "dependencies_validated"
    READY_FOR_APPROVAL = "ready_for_approval"
    ACTIVATED = "activated"
    FAILED = "failed"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    INTERRUPTED = "interrupted"


class GateStatus(str, Enum):
    """Individual gate status."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TransitionAction(str, Enum):
    """Actions that trigger state transitions."""
    PREFLIGHT = "preflight"
    SELECT_BACKUP = "select_backup"
    VERIFY_BACKUP = "verify_backup"
    INITIALIZE_RESTORE = "initialize_restore"
    RESTORE_DATABASE = "restore_database"
    REPLAY_WAL = "replay_wal"
    VALIDATE_SCHEMA = "validate_schema"
    VALIDATE_CANONICAL = "validate_canonical"
    VALIDATE_TENANT = "validate_tenant"
    VALIDATE_TEMPORAL = "validate_temporal"
    VALIDATE_PROVENANCE = "validate_provenance"
    VALIDATE_GOVERNANCE = "validate_governance"
    VALIDATE_LONGITUDINAL = "validate_longitudinal"
    VALIDATE_DEPENDENCIES = "validate_dependencies"
    REQUEST_APPROVAL = "request_approval"
    ACTIVATE = "activate"
    FAIL = "fail"
    BLOCK = "block"
    INTERRUPT = "interrupt"


# Valid state transitions
VALID_TRANSITIONS = {
    RecoveryGateState.CREATED: [RecoveryGateState.PREFLIGHTED, RecoveryGateState.FAILED],
    RecoveryGateState.PREFLIGHTED: [RecoveryGateState.BACKUP_SELECTED, RecoveryGateState.FAILED, RecoveryGateState.BLOCKED],
    RecoveryGateState.BACKUP_SELECTED: [RecoveryGateState.BACKUP_VERIFIED, RecoveryGateState.FAILED],
    RecoveryGateState.BACKUP_VERIFIED: [RecoveryGateState.RESTORE_INITIALIZED, RecoveryGateState.FAILED],
    RecoveryGateState.RESTORE_INITIALIZED: [RecoveryGateState.DATABASE_RESTORED, RecoveryGateState.FAILED],
    RecoveryGateState.DATABASE_RESTORED: [RecoveryGateState.WAL_REPLAYED, RecoveryGateState.FAILED],
    RecoveryGateState.WAL_REPLAYED: [RecoveryGateState.SCHEMA_VALIDATED, RecoveryGateState.FAILED],
    RecoveryGateState.SCHEMA_VALIDATED: [RecoveryGateState.CANONICAL_VALIDATED, RecoveryGateState.FAILED],
    RecoveryGateState.CANONICAL_VALIDATED: [RecoveryGateState.TENANT_VALIDATED, RecoveryGateState.FAILED],
    RecoveryGateState.TENANT_VALIDATED: [RecoveryGateState.TEMPORAL_VALIDATED, RecoveryGateState.FAILED],
    RecoveryGateState.TEMPORAL_VALIDATED: [RecoveryGateState.PROVENANCE_VALIDATED, RecoveryGateState.FAILED],
    RecoveryGateState.PROVENANCE_VALIDATED: [RecoveryGateState.GOVERNANCE_VALIDATED, RecoveryGateState.FAILED],
    RecoveryGateState.GOVERNANCE_VALIDATED: [RecoveryGateState.LONGITUDINAL_VALIDATED, RecoveryGateState.FAILED],
    RecoveryGateState.LONGITUDINAL_VALIDATED: [RecoveryGateState.DEPENDENCIES_VALIDATED, RecoveryGateState.FAILED],
    RecoveryGateState.DEPENDENCIES_VALIDATED: [RecoveryGateState.READY_FOR_APPROVAL, RecoveryGateState.FAILED],
    RecoveryGateState.READY_FOR_APPROVAL: [RecoveryGateState.ACTIVATED, RecoveryGateState.BLOCKED, RecoveryGateState.FAILED],
    RecoveryGateState.ACTIVATED: [],  # Terminal
    RecoveryGateState.FAILED: [RecoveryGateState.CREATED],  # Can retry
    RecoveryGateState.BLOCKED: [RecoveryGateState.CREATED],  # Can retry after unblock
    RecoveryGateState.INCONCLUSIVE: [RecoveryGateState.CREATED],  # Can retry
    RecoveryGateState.INTERRUPTED: [RecoveryGateState.CREATED],  # Can retry
}


@dataclass
class RecoveryGate:
    """A single recovery gate with validation logic."""
    name: str
    target_state: RecoveryGateState
    description: str
    validator: Optional[Callable] = None
    required: bool = True
    depends_on: List[str] = field(default_factory=list)
    skip_if: Optional[Callable] = None
    
    # Runtime state
    status: GateStatus = GateStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[ValidationResult] = None
    error: Optional[str] = None


@dataclass
class RecoveryContext:
    """Context for a recovery operation."""
    recovery_id: str
    backup_id: str
    organization_id: str
    target_time: Optional[datetime] = None
    target_lsn: Optional[str] = None
    initiated_by: str = ""
    current_state: RecoveryGateState = RecoveryGateState.CREATED
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    gates: Dict[str, RecoveryGate] = field(default_factory=dict)
    validation_reports: Dict[str, ValidationResult] = field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RecoveryReadinessGates(CapabilityAwareValidator):
    """Recovery readiness state machine with explicit gates."""
    
    def __init__(self):
        super().__init__()
        self._contexts: Dict[str, RecoveryContext] = {}
        self._gate_definitions = self._define_gates()
    
    def _get_active_restore(self, context: RecoveryContext):
        """Resolve the isolated restore for a recovery context.
        
        The isolated restore registry is keyed by restore_id, while recovery
        contexts are keyed by recovery_id. Bridge the two via
        context.metadata["restore_id"] when present.
        """
        from app.services.isolated_restore import isolated_restore_service
        
        candidates = []
        restore_id = (context.metadata or {}).get("restore_id")
        if restore_id:
            candidates.append(restore_id)
        candidates.append(context.recovery_id)
        
        for key in candidates:
            restore = isolated_restore_service.get_restore(key)
            if restore:
                return restore
        
        return None
    
    def _define_gates(self) -> Dict[str, RecoveryGate]:
        """Define all recovery gates in order."""
        return {
            "preflight": RecoveryGate(
                name="preflight",
                target_state=RecoveryGateState.PREFLIGHTED,
                description="Preflight checks: PITR capability, WAL archive health, recovery window",
                validator=self._validate_preflight,
                required=True,
            ),
            "backup_select": RecoveryGate(
                name="backup_select",
                target_state=RecoveryGateState.BACKUP_SELECTED,
                description="Select appropriate backup for recovery target",
                validator=self._validate_backup_select,
                required=True,
            ),
            "backup_verify": RecoveryGate(
                name="backup_verify",
                target_state=RecoveryGateState.BACKUP_VERIFIED,
                description="Verify backup integrity and completeness",
                validator=self._validate_backup_verify,
                required=True,
            ),
            "restore_init": RecoveryGate(
                name="restore_init",
                target_state=RecoveryGateState.RESTORE_INITIALIZED,
                description="Initialize isolated restore environment",
                validator=self._validate_restore_init,
                required=True,
            ),
            "database_restore": RecoveryGate(
                name="database_restore",
                target_state=RecoveryGateState.DATABASE_RESTORED,
                description="Restore base backup to isolated instance",
                validator=self._validate_database_restore,
                required=True,
            ),
            "wal_replay": RecoveryGate(
                name="wal_replay",
                target_state=RecoveryGateState.WAL_REPLAYED,
                description="Replay WAL to recovery target",
                validator=self._validate_wal_replay,
                required=True,
            ),
            "schema_validate": RecoveryGate(
                name="schema_validate",
                target_state=RecoveryGateState.SCHEMA_VALIDATED,
                description="Validate database schema matches expected",
                validator=self._validate_schema,
                required=True,
            ),
            "canonical_validate": RecoveryGate(
                name="canonical_validate",
                target_state=RecoveryGateState.CANONICAL_VALIDATED,
                description="Validate canonical integrity",
                validator=self._validate_canonical,
                required=True,
            ),
            "tenant_validate": RecoveryGate(
                name="tenant_validate",
                target_state=RecoveryGateState.TENANT_VALIDATED,
                description="Validate tenant isolation",
                validator=self._validate_tenant,
                required=True,
            ),
            "temporal_validate": RecoveryGate(
                name="temporal_validate",
                target_state=RecoveryGateState.TEMPORAL_VALIDATED,
                description="Validate temporal integrity",
                validator=self._validate_temporal,
                required=True,
            ),
            "provenance_validate": RecoveryGate(
                name="provenance_validate",
                target_state=RecoveryGateState.PROVENANCE_VALIDATED,
                description="Validate provenance chains",
                validator=self._validate_provenance,
                required=True,
            ),
            "governance_validate": RecoveryGate(
                name="governance_validate",
                target_state=RecoveryGateState.GOVERNANCE_VALIDATED,
                description="Validate governance rules",
                validator=self._validate_governance,
                required=True,
            ),
            "longitudinal_validate": RecoveryGate(
                name="longitudinal_validate",
                target_state=RecoveryGateState.LONGITUDINAL_VALIDATED,
                description="Validate longitudinal integrity",
                validator=self._validate_longitudinal,
                required=True,
            ),
            "dependencies_validate": RecoveryGate(
                name="dependencies_validate",
                target_state=RecoveryGateState.DEPENDENCIES_VALIDATED,
                description="Validate Company Brain and Digital Twin dependencies",
                validator=self._validate_dependencies,
                required=True,
            ),
            "approval_request": RecoveryGate(
                name="approval_request",
                target_state=RecoveryGateState.READY_FOR_APPROVAL,
                description="Require every prior gate to be verified and record the approval request",
                validator=self._validate_approval_request,
                required=True,
            ),
            "activation": RecoveryGate(
                name="activation",
                target_state=RecoveryGateState.ACTIVATED,
                description="Activate only after a recorded approval with every prior gate verified",
                validator=self._validate_activation,
                required=True,
            ),
        }
    
    def create_recovery_context(
        self,
        backup_id: str,
        organization_id: str,
        target_time: Optional[datetime] = None,
        target_lsn: Optional[str] = None,
        initiated_by: str = "",
    ) -> RecoveryContext:
        """Create a new recovery context."""
        recovery_id = f"rec-{uuid.uuid4().hex[:12]}"
        
        context = RecoveryContext(
            recovery_id=recovery_id,
            backup_id=backup_id,
            organization_id=organization_id,
            target_time=target_time,
            target_lsn=target_lsn,
            initiated_by=initiated_by,
            current_state=RecoveryGateState.CREATED,
        )
        
        # Initialize gates
        for gate_name, gate_def in self._gate_definitions.items():
            context.gates[gate_name] = RecoveryGate(
                name=gate_def.name,
                target_state=gate_def.target_state,
                description=gate_def.description,
                validator=gate_def.validator,
                required=gate_def.required,
                depends_on=gate_def.depends_on,
                skip_if=gate_def.skip_if,
            )
        
        self._contexts[recovery_id] = context
        return context
    
    def get_context(self, recovery_id: str) -> Optional[RecoveryContext]:
        """Get recovery context by ID."""
        return self._contexts.get(recovery_id)
    
    async def transition(
        self,
        db: AsyncSession,
        recovery_id: str,
        action: TransitionAction,
    ) -> RecoveryContext:
        """Execute a state transition."""
        context = self._contexts.get(recovery_id)
        if not context:
            raise ValueError(f"Recovery context {recovery_id} not found")
        
        # Map action to target state
        action_to_state = {
            TransitionAction.PREFLIGHT: RecoveryGateState.PREFLIGHTED,
            TransitionAction.SELECT_BACKUP: RecoveryGateState.BACKUP_SELECTED,
            TransitionAction.VERIFY_BACKUP: RecoveryGateState.BACKUP_VERIFIED,
            TransitionAction.INITIALIZE_RESTORE: RecoveryGateState.RESTORE_INITIALIZED,
            TransitionAction.RESTORE_DATABASE: RecoveryGateState.DATABASE_RESTORED,
            TransitionAction.REPLAY_WAL: RecoveryGateState.WAL_REPLAYED,
            TransitionAction.VALIDATE_SCHEMA: RecoveryGateState.SCHEMA_VALIDATED,
            TransitionAction.VALIDATE_CANONICAL: RecoveryGateState.CANONICAL_VALIDATED,
            TransitionAction.VALIDATE_TENANT: RecoveryGateState.TENANT_VALIDATED,
            TransitionAction.VALIDATE_TEMPORAL: RecoveryGateState.TEMPORAL_VALIDATED,
            TransitionAction.VALIDATE_PROVENANCE: RecoveryGateState.PROVENANCE_VALIDATED,
            TransitionAction.VALIDATE_GOVERNANCE: RecoveryGateState.GOVERNANCE_VALIDATED,
            TransitionAction.VALIDATE_LONGITUDINAL: RecoveryGateState.LONGITUDINAL_VALIDATED,
            TransitionAction.VALIDATE_DEPENDENCIES: RecoveryGateState.DEPENDENCIES_VALIDATED,
            TransitionAction.REQUEST_APPROVAL: RecoveryGateState.READY_FOR_APPROVAL,
            TransitionAction.ACTIVATE: RecoveryGateState.ACTIVATED,
            TransitionAction.FAIL: RecoveryGateState.FAILED,
            TransitionAction.BLOCK: RecoveryGateState.BLOCKED,
            TransitionAction.INTERRUPT: RecoveryGateState.INTERRUPTED,
        }
        
        target_state = action_to_state.get(action)
        if not target_state:
            raise ValueError(f"Unknown transition action: {action}")
        
        # Validate transition
        if target_state not in VALID_TRANSITIONS.get(context.current_state, []):
            raise ValueError(
                f"Invalid transition from {context.current_state.value} to {target_state.value} "
                f"via action {action.value}"
            )
        
        # Execute the gate if moving forward
        if target_state != context.current_state and target_state not in (
            RecoveryGateState.FAILED, RecoveryGateState.BLOCKED, 
            RecoveryGateState.INCONCLUSIVE, RecoveryGateState.INTERRUPTED
        ):
            gate_name = self._state_to_gate(target_state)
            if gate_name and gate_name in context.gates:
                gate = context.gates[gate_name]
                await self._execute_gate(db, context, gate)
                
                if gate.status == GateStatus.FAILED:
                    context.current_state = RecoveryGateState.FAILED
                    context.error = gate.error
                elif gate.status == GateStatus.BLOCKED:
                    context.current_state = RecoveryGateState.BLOCKED
                    context.error = gate.error
                elif gate.status == GateStatus.PASSED:
                    context.current_state = target_state
                elif gate.status == GateStatus.SKIPPED:
                    # Capability not applicable in this environment; explicit and
                    # recorded, but does not block the transition.
                    context.current_state = target_state
                else:
                    context.current_state = RecoveryGateState.INCONCLUSIVE
            else:
                context.current_state = target_state
        else:
            context.current_state = target_state
        
        if target_state in (RecoveryGateState.ACTIVATED, RecoveryGateState.FAILED, 
                           RecoveryGateState.BLOCKED, RecoveryGateState.INCONCLUSIVE,
                           RecoveryGateState.INTERRUPTED):
            context.completed_at = utcnow()
        
        return context
    
    def _state_to_gate(self, state: RecoveryGateState) -> Optional[str]:
        """Map state to gate name."""
        state_to_gate = {
            RecoveryGateState.PREFLIGHTED: "preflight",
            RecoveryGateState.BACKUP_SELECTED: "backup_select",
            RecoveryGateState.BACKUP_VERIFIED: "backup_verify",
            RecoveryGateState.RESTORE_INITIALIZED: "restore_init",
            RecoveryGateState.DATABASE_RESTORED: "database_restore",
            RecoveryGateState.WAL_REPLAYED: "wal_replay",
            RecoveryGateState.SCHEMA_VALIDATED: "schema_validate",
            RecoveryGateState.CANONICAL_VALIDATED: "canonical_validate",
            RecoveryGateState.TENANT_VALIDATED: "tenant_validate",
            RecoveryGateState.TEMPORAL_VALIDATED: "temporal_validate",
            RecoveryGateState.PROVENANCE_VALIDATED: "provenance_validate",
            RecoveryGateState.GOVERNANCE_VALIDATED: "governance_validate",
            RecoveryGateState.LONGITUDINAL_VALIDATED: "longitudinal_validate",
            RecoveryGateState.DEPENDENCIES_VALIDATED: "dependencies_validate",
            RecoveryGateState.READY_FOR_APPROVAL: "approval_request",
            RecoveryGateState.ACTIVATED: "activation",
        }
        return state_to_gate.get(state)
    
    async def _execute_gate(
        self,
        db: AsyncSession,
        context: RecoveryContext,
        gate: RecoveryGate,
    ) -> None:
        """Execute a single gate's validation."""
        gate.status = GateStatus.RUNNING
        gate.started_at = utcnow()
        
        try:
            if gate.validator:
                result = await gate.validator(db, context)
                gate.result = result
                
                if result and result.overall_status == ValidationStatus.VERIFIED:
                    gate.status = GateStatus.PASSED
                elif result and result.overall_status == ValidationStatus.FAILED:
                    gate.status = GateStatus.FAILED
                    gate.error = result.message
                elif result and result.overall_status == ValidationStatus.BLOCKED:
                    gate.status = GateStatus.BLOCKED
                    gate.error = result.message
                elif result and result.overall_status == ValidationStatus.NOT_APPLICABLE:
                    gate.status = GateStatus.SKIPPED
                else:
                    # Fail closed: warning / inconclusive / missing result means the
                    # gate is NOT verified and must never transition as passed.
                    status_value = (
                        result.overall_status.value
                        if result and result.overall_status is not None
                        else "no_result"
                    )
                    gate.status = GateStatus.BLOCKED
                    gate.error = f"Gate not verified (status={status_value})"
            else:
                gate.status = GateStatus.SKIPPED
            
        except Exception as e:
            gate.status = GateStatus.FAILED
            gate.error = str(e)
            logger.error(f"Gate {gate.name} failed: {e}")
        
        gate.completed_at = utcnow()
    
    # =====================================================================
    # GATE VALIDATORS
    # =====================================================================
    
    async def _validate_preflight(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Preflight checks."""
        self.db = db
        self.detector.db = db
        
        result = ValidationResult(domain="preflight")
        
        # Check PITR capability
        pitr_available = await self.detector.detect(EnvironmentCapability.POSTGRESQL_PITR)
        if not pitr_available:
            result.add_check(ValidationCheck(
                name="pitr_capability",
                status=ValidationStatus.FAILED,
                message="PostgreSQL PITR capability not available",
            ))
            result.determine_overall()
            return result
        
        # Check WAL archive health
        from app.services.wal_archive_monitor import wal_archive_monitor
        wal_health = await wal_archive_monitor.check_health(db)
        
        if wal_health.overall_state.value == "unhealthy":
            result.add_check(ValidationCheck(
                name="wal_archive",
                status=ValidationStatus.FAILED,
                message=f"WAL archive unhealthy: {wal_health.alerts}",
            ))
            result.determine_overall()
            return result
        
        # Check continuous chain
        if not wal_health.continuous_chain_from_baseline:
            result.add_check(ValidationCheck(
                name="continuous_chain",
                status=ValidationStatus.BLOCKED,
                message="No continuous WAL chain from baseline",
            ))
            result.determine_overall()
            return result
        
        result.add_check(ValidationCheck(
            name="preflight",
            status=ValidationStatus.VERIFIED,
            message="All preflight checks passed",
        ))
        result.determine_overall()
        return result
    
    async def _validate_backup_select(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate backup selection."""
        result = ValidationResult(domain="backup_select")
        
        backup = await db.get(BackupManifest, context.backup_id)
        if not backup:
            result.add_check(ValidationCheck(
                name="backup_exists",
                status=ValidationStatus.FAILED,
                message=f"Backup {context.backup_id} not found",
            ))
            result.determine_overall()
            return result
        
        if backup.status != BackupStatus.VERIFIED:
            result.add_check(ValidationCheck(
                name="backup_verified",
                status=ValidationStatus.FAILED,
                message=f"Backup {context.backup_id} is not verified (status: {backup.status})",
            ))
            result.determine_overall()
            return result
        
        # Check backup belongs to organization
        if backup.organization_id != context.organization_id:
            result.add_check(ValidationCheck(
                name="backup_tenant",
                status=ValidationStatus.FAILED,
                message=f"Backup belongs to different organization",
            ))
            result.determine_overall()
            return result
        
        result.add_check(ValidationCheck(
            name="backup_select",
            status=ValidationStatus.VERIFIED,
            message=f"Backup {context.backup_id} selected and verified",
        ))
        result.determine_overall()
        return result
    
    async def _validate_backup_verify(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Verify backup artifact."""
        result = ValidationResult(domain="backup_verify")
        
        from app.services.backup_service import backup_service
        verification = await backup_service.verify_backup(db, context.backup_id)
        
        if not verification.verified:
            result.add_check(ValidationCheck(
                name="backup_verification",
                status=ValidationStatus.FAILED,
                message=f"Backup verification failed: {verification.errors}",
            ))
            result.determine_overall()
            return result
        
        result.add_check(ValidationCheck(
            name="backup_verification",
            status=ValidationStatus.VERIFIED,
            message="Backup verified successfully",
        ))
        result.determine_overall()
        return result
    
    async def _validate_restore_init(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate restore initialization."""
        result = ValidationResult(domain="restore_init")
        
        # Check if isolated restore was started
        from app.services.isolated_restore import isolated_restore_service
        restore_result = self._get_active_restore(context)
        
        if not restore_result:
            result.add_check(ValidationCheck(
                name="restore_initialized",
                status=ValidationStatus.FAILED,
                message="Isolated restore not initialized",
            ))
            result.determine_overall()
            return result
        
        result.add_check(ValidationCheck(
            name="restore_init",
            status=ValidationStatus.VERIFIED,
            message="Restore environment initialized",
        ))
        result.determine_overall()
        return result
    
    async def _validate_database_restore(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate database restore completed."""
        result = ValidationResult(domain="database_restore")
        
        from app.services.isolated_restore import isolated_restore_service
        restore_result = self._get_active_restore(context)
        
        if not restore_result or restore_result.state.value != "completed":
            result.add_check(ValidationCheck(
                name="database_restored",
                status=ValidationStatus.FAILED,
                message=f"Database restore not completed: {restore_result.state if restore_result else 'not started'}",
            ))
            result.determine_overall()
            return result
        
        result.add_check(ValidationCheck(
            name="database_restored",
            status=ValidationStatus.VERIFIED,
            message="Database restored successfully",
        ))
        result.determine_overall()
        return result
    
    async def _validate_wal_replay(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate WAL replay completed."""
        result = ValidationResult(domain="wal_replay")
        
        from app.services.isolated_restore import isolated_restore_service
        restore_result = self._get_active_restore(context)
        
        if not restore_result or not restore_result.postgres_pid:
            result.add_check(ValidationCheck(
                name="wal_replay",
                status=ValidationStatus.FAILED,
                message="PostgreSQL not running (WAL replay incomplete)",
            ))
            result.determine_overall()
            return result
        
        result.add_check(ValidationCheck(
            name="wal_replay",
            status=ValidationStatus.VERIFIED,
            message="WAL replay completed, PostgreSQL running",
        ))
        result.determine_overall()
        return result
    
    async def _validate_schema(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate schema on restored database."""
        result = ValidationResult(domain="schema")
        
        from app.services.isolated_restore import isolated_restore_service
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        
        restore_result = self._get_active_restore(context)
        if not restore_result or not restore_result.postgres_pid:
            result.add_check(ValidationCheck(
                name="schema",
                status=ValidationStatus.FAILED,
                message="Cannot validate schema - PostgreSQL not running",
            ))
            result.determine_overall()
            return result
        
        # Connect to isolated instance
        engine = create_async_engine(
            f"postgresql+asyncpg://postgres:postgres@localhost:{restore_result.isolated_port}/{restore_result.validation_database}",
            pool_pre_ping=True,
        )
        session = async_sessionmaker(engine, expire_on_commit=False)()
        
        try:
            from app.services.restore_service import restore_service
            validation = await restore_service._validate_schema(session)
            context.validation_reports["schema"] = validation
            
            if validation.overall_status == ValidationStatus.FAILED:
                result.add_check(ValidationCheck(
                    name="schema",
                    status=ValidationStatus.FAILED,
                    message=f"Schema validation failed: {validation.message}",
                ))
            elif validation.overall_status == ValidationStatus.VERIFIED:
                result.add_check(ValidationCheck(
                    name="schema",
                    status=ValidationStatus.VERIFIED,
                    message="Schema validated",
                ))
            else:
                result.add_check(ValidationCheck(
                    name="schema",
                    status=validation.overall_status,
                    message=(
                        f"Schema not fully verified ({validation.overall_status.value}): "
                        f"{validation.message}"
                    ),
                ))
        finally:
            await session.close()
            await engine.dispose()
        
        result.determine_overall()
        return result
    
    async def _validate_canonical(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate canonical integrity on the RESTORED database."""
        result = ValidationResult(domain="canonical")
        
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        
        restore_result = self._get_active_restore(context)
        if not restore_result or not restore_result.postgres_pid:
            result.add_check(ValidationCheck(
                name="canonical",
                status=ValidationStatus.FAILED,
                message="Cannot validate canonical integrity - isolated PostgreSQL not running",
            ))
            result.determine_overall()
            return result
        
        engine = create_async_engine(
            f"postgresql+asyncpg://postgres:postgres@localhost:{restore_result.isolated_port}/{restore_result.validation_database}",
            pool_pre_ping=True,
        )
        session = async_sessionmaker(engine, expire_on_commit=False)()
        
        try:
            report = await post_restore_canonical_validator.validate_restored_database(
                db=session,
                organization_id=context.organization_id,
                restore_id=restore_result.restore_id,
                recovery_target=context.target_time,
                checks=["structural", "tenant", "temporal", "provenance", "epistemic", "governance", "operating_chain"],
            )
            
            context.validation_reports["canonical"] = report
            
            if report.overall_verdict == ValidationVerdict.FAILED:
                msg = f"Canonical validation failed: {report.summary}"
                result.add_check(ValidationCheck(
                    name="canonical",
                    status=ValidationStatus.FAILED,
                    message=msg,
                ))
                result.message = msg
            elif report.overall_verdict == ValidationVerdict.WARNING:
                msg = f"Canonical validation has warnings: {report.summary}"
                result.add_check(ValidationCheck(
                    name="canonical",
                    status=ValidationStatus.WARNING,
                    message=msg,
                ))
                result.message = msg
            else:
                result.add_check(ValidationCheck(
                    name="canonical",
                    status=ValidationStatus.VERIFIED,
                    message="Canonical integrity validated on restored database",
                ))
        finally:
            await session.close()
            await engine.dispose()
        
        result.determine_overall()
        return result
    
    async def _validate_tenant(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate tenant isolation."""
        result = ValidationResult(domain="tenant")
        
        from app.services.isolated_restore import isolated_restore_service
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        
        restore_result = self._get_active_restore(context)
        if not restore_result:
            result.add_check(ValidationCheck(
                name="tenant",
                status=ValidationStatus.FAILED,
                message="No restore result available",
            ))
            result.determine_overall()
            return result
        
        engine = create_async_engine(
            f"postgresql+asyncpg://postgres:postgres@localhost:{restore_result.isolated_port}/{restore_result.validation_database}",
            pool_pre_ping=True,
        )
        session = async_sessionmaker(engine, expire_on_commit=False)()
        
        try:
            from app.services.restore_service import restore_service
            validation = await restore_service._validate_tenant_isolation(session, context.organization_id)
            context.validation_reports["tenant"] = validation
            
            if validation.overall_status == ValidationStatus.FAILED:
                result.add_check(ValidationCheck(
                    name="tenant",
                    status=ValidationStatus.FAILED,
                    message=f"Tenant isolation failed: {validation.message}",
                ))
            elif validation.overall_status == ValidationStatus.VERIFIED:
                result.add_check(ValidationCheck(
                    name="tenant",
                    status=ValidationStatus.VERIFIED,
                    message="Tenant isolation validated",
                ))
            else:
                result.add_check(ValidationCheck(
                    name="tenant",
                    status=validation.overall_status,
                    message=(
                        f"Tenant isolation not fully verified ({validation.overall_status.value}): "
                        f"{validation.message}"
                    ),
                ))
        finally:
            await session.close()
            await engine.dispose()
        
        result.determine_overall()
        return result
    
    async def _validate_temporal(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate temporal integrity."""
        result = ValidationResult(domain="temporal")
        
        from app.services.isolated_restore import isolated_restore_service
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        
        restore_result = self._get_active_restore(context)
        if not restore_result:
            result.add_check(ValidationCheck(
                name="temporal",
                status=ValidationStatus.FAILED,
                message="No restore result available",
            ))
            result.determine_overall()
            return result
        
        engine = create_async_engine(
            f"postgresql+asyncpg://postgres:postgres@localhost:{restore_result.isolated_port}/{restore_result.validation_database}",
            pool_pre_ping=True,
        )
        session = async_sessionmaker(engine, expire_on_commit=False)()
        
        try:
            from app.services.restore_service import restore_service
            validation = await restore_service._validate_temporal_integrity(session)
            context.validation_reports["temporal"] = validation
            
            if validation.overall_status == ValidationStatus.FAILED:
                result.add_check(ValidationCheck(
                    name="temporal",
                    status=ValidationStatus.FAILED,
                    message=f"Temporal validation failed: {validation.message}",
                ))
            elif validation.overall_status == ValidationStatus.VERIFIED:
                result.add_check(ValidationCheck(
                    name="temporal",
                    status=ValidationStatus.VERIFIED,
                    message="Temporal integrity validated",
                ))
            else:
                result.add_check(ValidationCheck(
                    name="temporal",
                    status=validation.overall_status,
                    message=(
                        f"Temporal integrity not fully verified ({validation.overall_status.value}): "
                        f"{validation.message}"
                    ),
                ))
        finally:
            await session.close()
            await engine.dispose()
        
        result.determine_overall()
        return result
    
    async def _validate_provenance(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate provenance chains."""
        result = ValidationResult(domain="provenance")
        
        from app.services.isolated_restore import isolated_restore_service
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        
        restore_result = self._get_active_restore(context)
        if not restore_result:
            result.add_check(ValidationCheck(
                name="provenance",
                status=ValidationStatus.FAILED,
                message="No restore result available",
            ))
            result.determine_overall()
            return result
        
        engine = create_async_engine(
            f"postgresql+asyncpg://postgres:postgres@localhost:{restore_result.isolated_port}/{restore_result.validation_database}",
            pool_pre_ping=True,
        )
        session = async_sessionmaker(engine, expire_on_commit=False)()
        
        try:
            from app.services.restore_service import restore_service
            validation = await restore_service._validate_provenance(session)
            context.validation_reports["provenance"] = validation
            
            if validation.overall_status == ValidationStatus.FAILED:
                result.add_check(ValidationCheck(
                    name="provenance",
                    status=ValidationStatus.FAILED,
                    message=f"Provenance validation failed: {validation.message}",
                ))
            elif validation.overall_status == ValidationStatus.VERIFIED:
                result.add_check(ValidationCheck(
                    name="provenance",
                    status=ValidationStatus.VERIFIED,
                    message="Provenance validated",
                ))
            else:
                result.add_check(ValidationCheck(
                    name="provenance",
                    status=validation.overall_status,
                    message=(
                        f"Provenance not fully verified ({validation.overall_status.value}): "
                        f"{validation.message}"
                    ),
                ))
        finally:
            await session.close()
            await engine.dispose()
        
        result.determine_overall()
        return result
    
    async def _validate_governance(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate governance rules."""
        result = ValidationResult(domain="governance")
        
        from app.services.isolated_restore import isolated_restore_service
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        
        restore_result = self._get_active_restore(context)
        if not restore_result:
            result.add_check(ValidationCheck(
                name="governance",
                status=ValidationStatus.FAILED,
                message="No restore result available",
            ))
            result.determine_overall()
            return result
        
        engine = create_async_engine(
            f"postgresql+asyncpg://postgres:postgres@localhost:{restore_result.isolated_port}/{restore_result.validation_database}",
            pool_pre_ping=True,
        )
        session = async_sessionmaker(engine, expire_on_commit=False)()
        
        try:
            from app.services.restore_service import restore_service
            validation = await restore_service._validate_governance(session)
            context.validation_reports["governance"] = validation
            
            if validation.overall_status == ValidationStatus.FAILED:
                result.add_check(ValidationCheck(
                    name="governance",
                    status=ValidationStatus.FAILED,
                    message=f"Governance validation failed: {validation.message}",
                ))
            elif validation.overall_status == ValidationStatus.VERIFIED:
                result.add_check(ValidationCheck(
                    name="governance",
                    status=ValidationStatus.VERIFIED,
                    message="Governance validated",
                ))
            else:
                result.add_check(ValidationCheck(
                    name="governance",
                    status=validation.overall_status,
                    message=(
                        f"Governance not fully verified ({validation.overall_status.value}): "
                        f"{validation.message}"
                    ),
                ))
        finally:
            await session.close()
            await engine.dispose()
        
        result.determine_overall()
        return result
    
    async def _validate_longitudinal(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate longitudinal integrity."""
        result = ValidationResult(domain="longitudinal")
        
        from app.services.isolated_restore import isolated_restore_service
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        
        restore_result = self._get_active_restore(context)
        if not restore_result:
            result.add_check(ValidationCheck(
                name="longitudinal",
                status=ValidationStatus.FAILED,
                message="No restore result available",
            ))
            result.determine_overall()
            return result
        
        engine = create_async_engine(
            f"postgresql+asyncpg://postgres:postgres@localhost:{restore_result.isolated_port}/{restore_result.validation_database}",
            pool_pre_ping=True,
        )
        session = async_sessionmaker(engine, expire_on_commit=False)()
        
        try:
            from app.services.restore_service import restore_service
            validation = await restore_service._validate_longitudinal(session)
            context.validation_reports["longitudinal"] = validation
            
            if validation.overall_status == ValidationStatus.FAILED:
                result.add_check(ValidationCheck(
                    name="longitudinal",
                    status=ValidationStatus.FAILED,
                    message=f"Longitudinal validation failed: {validation.message}",
                ))
            elif validation.overall_status == ValidationStatus.VERIFIED:
                result.add_check(ValidationCheck(
                    name="longitudinal",
                    status=ValidationStatus.VERIFIED,
                    message="Longitudinal integrity validated",
                ))
            else:
                result.add_check(ValidationCheck(
                    name="longitudinal",
                    status=validation.overall_status,
                    message=(
                        f"Longitudinal integrity not fully verified ({validation.overall_status.value}): "
                        f"{validation.message}"
                    ),
                ))
        finally:
            await session.close()
            await engine.dispose()
        
        result.determine_overall()
        return result
    
    async def _validate_dependencies(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Validate Company Brain and Digital Twin dependencies."""
        result = ValidationResult(domain="dependencies")
        
        from app.services.isolated_restore import isolated_restore_service
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        
        restore_result = self._get_active_restore(context)
        if not restore_result:
            result.add_check(ValidationCheck(
                name="dependencies",
                status=ValidationStatus.FAILED,
                message="No restore result available",
            ))
            result.determine_overall()
            return result
        
        engine = create_async_engine(
            f"postgresql+asyncpg://postgres:postgres@localhost:{restore_result.isolated_port}/{restore_result.validation_database}",
            pool_pre_ping=True,
        )
        session = async_sessionmaker(engine, expire_on_commit=False)()
        
        try:
            from app.services.restore_service import restore_service
            
            # Brain dependencies
            brain_validation = await restore_service._validate_brain_dependencies(session)
            context.validation_reports["brain_dependencies"] = brain_validation
            
            # Digital twin
            twin_validation = await restore_service._validate_digital_twin_dependencies(session)
            context.validation_reports["digital_twin"] = twin_validation
            
            if brain_validation.overall_status == ValidationStatus.FAILED or \
               twin_validation.overall_status == ValidationStatus.FAILED:
                result.add_check(ValidationCheck(
                    name="dependencies",
                    status=ValidationStatus.FAILED,
                    message="Dependencies validation failed",
                ))
            elif (
                brain_validation.overall_status == ValidationStatus.VERIFIED
                and twin_validation.overall_status == ValidationStatus.VERIFIED
            ):
                result.add_check(ValidationCheck(
                    name="dependencies",
                    status=ValidationStatus.VERIFIED,
                    message="Dependencies validated",
                ))
            else:
                worst = (
                    brain_validation.overall_status
                    if brain_validation.overall_status != ValidationStatus.VERIFIED
                    else twin_validation.overall_status
                )
                result.add_check(ValidationCheck(
                    name="dependencies",
                    status=worst,
                    message=f"Dependencies not fully verified ({worst.value})",
                ))
        finally:
            await session.close()
            await engine.dispose()
        
        result.determine_overall()
        return result
    
    async def _validate_approval_request(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Require every prior gate to be verified and record the approval request."""
        result = ValidationResult(domain="approval_request")
        
        excluded = {"approval_request", "activation"}
        unverified = sorted(
            name for name, gate in context.gates.items()
            if name not in excluded and gate.status not in (GateStatus.PASSED, GateStatus.SKIPPED)
        )
        result.add_check(ValidationCheck(
            name="prior_gates_verified",
            status=ValidationStatus.VERIFIED if not unverified else ValidationStatus.FAILED,
            message=(
                "All prior gates passed or were explicitly skipped"
                if not unverified else f"Unverified gates: {unverified}"
            ),
        ))
        
        result.add_check(ValidationCheck(
            name="operator_identified",
            status=ValidationStatus.VERIFIED if context.initiated_by else ValidationStatus.FAILED,
            message=(
                f"Approval requested by {context.initiated_by}"
                if context.initiated_by else "No operator identity (initiated_by) recorded"
            ),
        ))
        
        result.determine_overall()
        if result.overall_status == ValidationStatus.VERIFIED:
            skipped = sorted(
                name for name, gate in context.gates.items() if gate.status == GateStatus.SKIPPED
            )
            context.metadata["approval_requested_at"] = utcnow().isoformat()
            context.metadata["approval_requested_by"] = context.initiated_by
            context.metadata["skipped_gates_at_approval"] = skipped
        return result
    
    async def _validate_activation(self, db: AsyncSession, context: RecoveryContext) -> ValidationResult:
        """Activate only with a recorded approval and every prior gate verified."""
        result = ValidationResult(domain="activation")
        
        approved_at = context.metadata.get("approval_requested_at")
        result.add_check(ValidationCheck(
            name="approval_recorded",
            status=ValidationStatus.VERIFIED if approved_at else ValidationStatus.FAILED,
            message=(
                f"Approval requested at {approved_at}"
                if approved_at else "No approval request recorded; refusing activation"
            ),
        ))
        
        excluded = {"approval_request", "activation"}
        blocking = sorted(
            name for name, gate in context.gates.items()
            if name not in excluded and gate.status not in (GateStatus.PASSED, GateStatus.SKIPPED)
        )
        result.add_check(ValidationCheck(
            name="prior_gates_verified",
            status=ValidationStatus.VERIFIED if not blocking else ValidationStatus.FAILED,
            message=(
                "All prior gates passed or were explicitly skipped"
                if not blocking else f"Unverified gates: {blocking}"
            ),
        ))
        
        result.determine_overall()
        if result.overall_status == ValidationStatus.VERIFIED:
            context.metadata["activated_at"] = utcnow().isoformat()
            context.metadata["activated_by"] = context.initiated_by
        return result
    
    def get_gate_status(self, recovery_id: str) -> Dict[str, Any]:
        """Get status of all gates for a recovery."""
        context = self._contexts.get(recovery_id)
        if not context:
            return {"error": f"Recovery {recovery_id} not found"}
        
        return {
            "recovery_id": recovery_id,
            "current_state": context.current_state.value,
            "gates": {
                name: {
                    "target_state": gate.target_state.value,
                    "description": gate.description,
                    "status": gate.status.value,
                    "required": gate.required,
                    "started_at": gate.started_at.isoformat() if gate.started_at else None,
                    "completed_at": gate.completed_at.isoformat() if gate.completed_at else None,
                    "error": gate.error,
                }
                for name, gate in context.gates.items()
            },
            "error": context.error,
        }
    
    def is_ready_for_approval(self, recovery_id: str) -> bool:
        """Check if recovery is ready for approval."""
        context = self._contexts.get(recovery_id)
        if not context:
            return False
        return context.current_state == RecoveryGateState.READY_FOR_APPROVAL
    
    def is_activated(self, recovery_id: str) -> bool:
        """Check if recovery is activated."""
        context = self._contexts.get(recovery_id)
        if not context:
            return False
        return context.current_state == RecoveryGateState.ACTIVATED


# Global instance
recovery_readiness_gates = RecoveryReadinessGates()