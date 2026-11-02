"""Durable Scale Run State Machine.

Provides durable execution state tracking for authoritative scale validation runs.
"""

import os
import json
import uuid
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from enum import Enum
from pathlib import Path
from contextlib import contextmanager


class ScaleRunState(Enum):
    """Authoritative scale run states."""
    CREATED = "CREATED"
    PREFLIGHTED = "PREFLIGHTED"
    INITIALIZED = "INITIALIZED"
    SCHEMA_READY = "SCHEMA_READY"
    GENERATING = "GENERATING"
    DATA_GENERATED = "DATA_GENERATED"
    INTEGRITY_VALIDATED = "INTEGRITY_VALIDATED"
    QUERY_VALIDATED = "QUERY_VALIDATED"
    PERFORMANCE_MEASURED = "PERFORMANCE_MEASURED"
    FINGERPRINTED = "FINGERPRINTED"
    CLEANUP = "CLEANUP"
    CONCURRENCY_VALIDATED = "CONCURRENCY_VALIDATED"
    COMPLETED = "COMPLETED"
    
    # Failure states
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"
    INCONCLUSIVE = "INCONCLUSIVE"
    INTERRUPTED = "INTERRUPTED"


class ScaleRunPhase(Enum):
    """Scale run phases for checkpointing."""
    DISCOVERY = "discovery"
    CAPABILITY_DETECT = "capability_detection"
    PREFLIGHT = "preflight"
    DATABASE_HEALTH = "database_health"
    SCHEMA_VALIDATION = "schema_validation"
    GENERATION = "generation"
    DATA_GENERATED = "data_generated"
    BULK_INGESTION = "bulk_ingestion"
    INTEGRITY_VALIDATION = "integrity_validation"
    TENANT_ISOLATION = "tenant_isolation"
    TEMPORAL_VALIDATION = "temporal_validation"
    PROVENANCE_VALIDATION = "provenance_validation"
    EPISTEMIC_VALIDATION = "epistemic_validation"
    GOVERNANCE_VALIDATION = "governance_validation"
    COMPANY_BRAIN_VALIDATION = "company_brain_validation"
    QUERY_PLAN_VALIDATION = "query_plan_validation"
    PERFORMANCE_MEASUREMENT = "performance_measurement"
    RESOURCE_MEASUREMENT = "resource_measurement"
    CONCURRENCY_VALIDATION = "concurrency_validation"
    CLEANUP = "cleanup"
    EVIDENCE_REPORT = "evidence_report"
    EVIDENCE_COLLECTION = "evidence_collection"


@dataclass
class ScaleRunCheckpoint:
    """Checkpoint for resumable scale generation."""
    run_id: str
    phase: ScaleRunPhase
    entity_type: str
    batch_number: int
    rows_created: int
    rows_expected: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    fingerprint: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DatasetIdentity:
    """Deterministic dataset identity for reproducibility."""
    vcos_revision: str
    schema_revision: str
    generator_revision: str
    scale_profile: str
    employee_count: int
    tenant_count: int
    seed: int
    density_strategy: str
    environment_fingerprint: str
    
    def to_hash(self) -> str:
        """Generate deterministic hash for this dataset identity."""
        components = [
            self.vcos_revision,
            self.schema_revision,
            self.generator_revision,
            self.scale_profile,
            str(self.employee_count),
            str(self.tenant_count),
            str(self.seed),
            self.density_strategy,
            self.environment_fingerprint,
        ]
        content = "|".join(components)
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScaleRunOwnership:
    """Tracks what resources a scale run owns for safe cleanup."""
    run_id: str
    owns_database: bool = False
    owns_schema: bool = False
    owns_tables: bool = False
    database_name: Optional[str] = None
    schema_name: Optional[str] = None
    created_tables: List[str] = field(default_factory=list)
    temporary_resources: List[str] = field(default_factory=list)
    
    def can_cleanup_database(self) -> bool:
        return self.owns_database and self.database_name is not None
    
    def can_cleanup_schema(self) -> bool:
        return self.owns_schema and self.schema_name is not None


@dataclass
class ScaleRunMetadata:
    """Complete metadata for a scale validation run."""
    run_id: str
    state: ScaleRunState
    profile_name: str
    employee_count: int
    tenant_count: int
    environment_type: str
    dataset_identity: DatasetIdentity
    ownership: ScaleRunOwnership
    checkpoints: List[ScaleRunCheckpoint] = field(default_factory=list)
    current_phase: Optional[ScaleRunPhase] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def add_checkpoint(self, checkpoint: ScaleRunCheckpoint) -> None:
        self.checkpoints.append(checkpoint)
        self.updated_at = datetime.utcnow()
    
    def get_latest_checkpoint(self, phase: ScaleRunPhase) -> Optional[ScaleRunCheckpoint]:
        phase_checkpoints = [c for c in self.checkpoints if c.phase == phase]
        if phase_checkpoints:
            return max(phase_checkpoints, key=lambda c: c.batch_number)
        return None
    
    def can_resume_from(self, phase: ScaleRunPhase) -> bool:
        checkpoint = self.get_latest_checkpoint(phase)
        return checkpoint is not None and checkpoint.completed_at is not None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "state": self.state.value,
            "profile_name": self.profile_name,
            "employee_count": self.employee_count,
            "tenant_count": self.tenant_count,
            "environment_type": self.environment_type,
            "dataset_identity": self.dataset_identity.to_dict(),
            "ownership": asdict(self.ownership),
            "checkpoints": [asdict(c) for c in self.checkpoints],
            "current_phase": self.current_phase.value if self.current_phase else None,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScaleRunMetadata':
        checkpoints = [ScaleRunCheckpoint(**c) for c in data.get("checkpoints", [])]
        ownership = ScaleRunOwnership(**data.get("ownership", {}))
        dataset_identity = DatasetIdentity(**data.get("dataset_identity", {}))
        
        return cls(
            run_id=data["run_id"],
            state=ScaleRunState(data["state"]),
            profile_name=data["profile_name"],
            employee_count=data["employee_count"],
            tenant_count=data["tenant_count"],
            environment_type=data["environment_type"],
            dataset_identity=dataset_identity,
            ownership=ownership,
            checkpoints=checkpoints,
            current_phase=ScaleRunPhase(data["current_phase"]) if data.get("current_phase") else None,
            started_at=datetime.fromisoformat(data["started_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            error=data.get("error"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
        )


class ScaleRunStateStore:
    """Persistent store for scale run metadata."""
    
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.path.join(os.getcwd(), "scale_runs"))
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def _run_path(self, run_id: str) -> Path:
        return self.base_dir / f"{run_id}.json"
    
    def save(self, metadata: ScaleRunMetadata) -> None:
        path = self._run_path(metadata.run_id)
        with open(path, 'w') as f:
            json.dump(metadata.to_dict(), f, indent=2, default=str)
    
    def load(self, run_id: str) -> Optional[ScaleRunMetadata]:
        path = self._run_path(run_id)
        if not path.exists():
            return None
        with open(path, 'r') as f:
            data = json.load(f)
        return ScaleRunMetadata.from_dict(data)
    
    def exists(self, run_id: str) -> bool:
        return self._run_path(run_id).exists()
    
    def list_runs(self) -> List[str]:
        return [f.stem for f in self.base_dir.glob("*.json")]
    
    def delete(self, run_id: str) -> bool:
        path = self._run_path(run_id)
        if path.exists():
            path.unlink()
            return True
        return False


class ScaleRunStateMachine:
    """State machine for authoritative scale run execution."""
    
    VALID_TRANSITIONS = {
        ScaleRunState.CREATED: {ScaleRunState.PREFLIGHTED, ScaleRunState.BLOCKED, ScaleRunState.INVALID, ScaleRunState.FAILED},
        ScaleRunState.PREFLIGHTED: {ScaleRunState.INITIALIZED, ScaleRunState.BLOCKED, ScaleRunState.FAILED},
        ScaleRunState.INITIALIZED: {ScaleRunState.SCHEMA_READY, ScaleRunState.BLOCKED, ScaleRunState.FAILED},
        ScaleRunState.SCHEMA_READY: {ScaleRunState.GENERATING, ScaleRunState.BLOCKED, ScaleRunState.FAILED},
        ScaleRunState.GENERATING: {ScaleRunState.DATA_GENERATED, ScaleRunState.FAILED, ScaleRunState.INTERRUPTED},
        ScaleRunState.DATA_GENERATED: {ScaleRunState.INTEGRITY_VALIDATED, ScaleRunState.FAILED},
        ScaleRunState.INTEGRITY_VALIDATED: {ScaleRunState.QUERY_VALIDATED, ScaleRunState.FAILED},
        ScaleRunState.QUERY_VALIDATED: {ScaleRunState.PERFORMANCE_MEASURED, ScaleRunState.FAILED},
        ScaleRunState.PERFORMANCE_MEASURED: {ScaleRunState.FINGERPRINTED, ScaleRunState.FAILED},
        ScaleRunState.FINGERPRINTED: {ScaleRunState.CLEANUP, ScaleRunState.FAILED},
        ScaleRunState.CLEANUP: {ScaleRunState.COMPLETED, ScaleRunState.FAILED},
        ScaleRunState.COMPLETED: set(),  # Terminal
        ScaleRunState.FAILED: {ScaleRunState.CREATED},  # Allow retry
        ScaleRunState.BLOCKED: {ScaleRunState.CREATED},  # Allow retry after fixing environment
        ScaleRunState.INVALID: set(),  # Terminal
        ScaleRunState.INCONCLUSIVE: {ScaleRunState.CREATED},  # Allow retry
        ScaleRunState.INTERRUPTED: {ScaleRunState.CREATED},  # Allow resume
    }
    
    def __init__(self, store: Optional[ScaleRunStateStore] = None):
        self.store = store or ScaleRunStateStore()
        self._current_metadata: Optional[ScaleRunMetadata] = None
    
    def create_run(
        self,
        profile_name: str,
        employee_count: int,
        tenant_count: int,
        environment_type: str,
        dataset_identity: DatasetIdentity,
        ownership: ScaleRunOwnership,
        run_id: Optional[str] = None,
    ) -> ScaleRunMetadata:
        run_id = run_id or str(uuid.uuid4())[:12]
        
        metadata = ScaleRunMetadata(
            run_id=run_id,
            state=ScaleRunState.CREATED,
            profile_name=profile_name,
            employee_count=employee_count,
            tenant_count=tenant_count,
            environment_type=environment_type,
            dataset_identity=dataset_identity,
            ownership=ownership,
        )
        
        self._current_metadata = metadata
        self.store.save(metadata)
        return metadata
    
    def load_run(self, run_id: str) -> Optional[ScaleRunMetadata]:
        metadata = self.store.load(run_id)
        if metadata:
            self._current_metadata = metadata
        return metadata
    
    def get_current(self) -> Optional[ScaleRunMetadata]:
        return self._current_metadata
    
    def transition(self, new_state: ScaleRunState, error: Optional[str] = None) -> bool:
        if not self._current_metadata:
            raise RuntimeError("No active run")
        
        current_state = self._current_metadata.state
        valid_next = self.VALID_TRANSITIONS.get(current_state, set())
        
        if new_state not in valid_next:
            raise ValueError(f"Invalid transition: {current_state.value} -> {new_state.value}")
        
        self._current_metadata.state = new_state
        self._current_metadata.updated_at = datetime.utcnow()
        
        if new_state in {ScaleRunState.COMPLETED, ScaleRunState.FAILED, ScaleRunState.BLOCKED, 
                         ScaleRunState.INVALID, ScaleRunState.INCONCLUSIVE}:
            self._current_metadata.completed_at = datetime.utcnow()
        
        if error:
            self._current_metadata.error = error
        
        self.store.save(self._current_metadata)
        return True
    
    def advance_phase(self, phase: ScaleRunPhase) -> None:
        if not self._current_metadata:
            raise RuntimeError("No active run")
        self._current_metadata.current_phase = phase
        self._current_metadata.updated_at = datetime.utcnow()
        self.store.save(self._current_metadata)
    
    def add_checkpoint(self, checkpoint: ScaleRunCheckpoint) -> None:
        if not self._current_metadata:
            raise RuntimeError("No active run")
        self._current_metadata.add_checkpoint(checkpoint)
        self.store.save(self._current_metadata)
    
    def can_retry(self) -> bool:
        if not self._current_metadata:
            return False
        return self._current_metadata.state in {ScaleRunState.FAILED, ScaleRunState.BLOCKED, 
                                                 ScaleRunState.INCONCLUSIVE, ScaleRunState.INTERRUPTED} \
            and self._current_metadata.retry_count < self._current_metadata.max_retries
    
    def increment_retry(self) -> None:
        if self._current_metadata:
            self._current_metadata.retry_count += 1
            self._current_metadata.state = ScaleRunState.CREATED
            self._current_metadata.error = None
            self._current_metadata.updated_at = datetime.utcnow()
            self.store.save(self._current_metadata)


def create_dataset_identity(
    vcos_revision: str,
    schema_revision: str,
    generator_revision: str,
    scale_profile: str,
    employee_count: int,
    tenant_count: int,
    seed: int,
    density_strategy: str,
    environment_fingerprint: str,
) -> DatasetIdentity:
    """Create a deterministic dataset identity."""
    return DatasetIdentity(
        vcos_revision=vcos_revision,
        schema_revision=schema_revision,
        generator_revision=generator_revision,
        scale_profile=scale_profile,
        employee_count=employee_count,
        tenant_count=tenant_count,
        seed=seed,
        density_strategy=density_strategy,
        environment_fingerprint=environment_fingerprint,
    )