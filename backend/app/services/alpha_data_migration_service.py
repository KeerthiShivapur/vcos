"""Alpha Data Migration Service — governed import/migration for private alpha.

External data must enter through:
Observation → Evidence → Validation → Reconciliation → Canonical Reality

Do not directly inject external data into canonical truth without validation.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from enum import Enum
from io import BytesIO

from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.department import Department
from app.models.team import Team
from app.models.role import Role
from app.models.project import Project
from app.models.task import Task
from app.models.meeting import Meeting
from app.models.decision_history import DecisionHistory
from app.models.company_operating import (
    CompanyDecision, CompanyAction, CompanyCommitment,
    CompanyAuthorization, CompanyObjective, CompanyGoal,
    CompanyInitiative, CanonicalOperation, OperationAttempt,
)
from app.models.organizational_learning import (
    OrganizationalLearning, LearningEvidence
)
from app.models.company_state import CompanyStateSnapshot
from app.models.canonical_integration import (
    ConnectorInstance, SyncRun, ExternalOperation,
    ExternalIdentityMapping, ExternalConflict,
)
from app.models.observability import CanonicalObservation, Degradation
from app.models.continuous_twin import CompanyAttention
from app.models.canonical_company_continuity import (
    CompanyOperatingContinuity, CompanyStateSnapshotGate30,
)
from app.models.backup_manifest import BackupManifest
from app.models.audit import AuditLog
from app.services.canonical_fingerprint import canonical_fingerprint_service
from app.services.canonical_reality_integrity_service import canonical_reality_integrity_service
from app.intelligence.canonical_mutation import (
    canonical_mutation_boundary,
    MutationType,
)
from app.validation.capability_contract import CapabilityDetector

logger = logging.getLogger("vcos.alpha_migration")


# =============================================================================
# MIGRATION DATA MODELS
# =============================================================================

class MigrationSourceType(str, Enum):
    """Types of external data sources."""
    CSV = "csv"
    JSON = "json"
    EXCEL = "excel"
    API = "api"
    DATABASE = "database"
    WEBHOOK = "webhook"
    MANUAL = "manual"


class MigrationStatus(str, Enum):
    """Migration job status."""
    PENDING = "pending"
    VALIDATING = "validating"
    RECONCILING = "reconciling"
    APPROVED = "approved"
    APPLYING = "applying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    REQUIRES_REVIEW = "requires_review"


class ConflictResolutionStrategy(str, Enum):
    """How to resolve conflicts between external and canonical data."""
    CANONICAL_WINS = "canonical_wins"      # Keep canonical, reject external
    EXTERNAL_WINS = "external_wins"        # Overwrite canonical with external
    MERGE = "merge"                        # Attempt intelligent merge
    MANUAL = "manual"                      # Require human review
    EVIDENCE_BASED = "evidence_based"      # Use evidence to decide


class RecordType(str, Enum):
    """Types of records that can be migrated."""
    EMPLOYEE = "employee"
    DEPARTMENT = "department"
    TEAM = "team"
    ROLE = "role"
    PROJECT = "project"
    TASK = "task"
    MEETING = "meeting"
    DECISION = "decision"
    ACTION = "action"
    COMMITMENT = "commitment"
    AUTHORIZATION = "authorization"
    OBJECTIVE = "objective"
    GOAL = "goal"
    INITIATIVE = "initiative"
    OPERATION = "operation"
    LEARNING = "learning"
    EVIDENCE = "evidence"
    OBSERVATION = "observation"
    INTEGRATION = "integration"
    CUSTOM = "custom"


@dataclass
class MigrationJob:
    """A data migration job."""
    job_id: str
    organization_id: str
    requested_by: str
    source_type: MigrationSourceType
    source_path: str  # file path, API endpoint, etc.
    record_types: List[RecordType]
    status: MigrationStatus = MigrationStatus.PENDING
    governance_approval_id: Optional[str] = None
    conflict_resolution: ConflictResolutionStrategy = ConflictResolutionStrategy.CANONICAL_WINS
    validation_mode: str = "strict"  # strict, lenient, dry_run
    dry_run: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_records: int = 0
    validated_records: int = 0
    reconciled_records: int = 0
    applied_records: int = 0
    rejected_records: int = 0
    conflicts: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    canonical_fingerprint_before: Optional[str] = None
    canonical_fingerprint_after: Optional[str] = None


@dataclass
class MigrationRecord:
    """A single record being migrated."""
    record_id: str
    job_id: str
    record_type: RecordType
    external_id: str  # ID in source system
    canonical_id: Optional[str] = None  # ID in canonical system (if matched)
    external_data: Dict[str, Any] = field(default_factory=dict)
    canonical_data: Optional[Dict[str, Any]] = None  # Current canonical data
    validation_status: str = "pending"  # pending, valid, invalid, requires_review
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    reconciliation_action: str = "pending"  # pending, create, update, skip, conflict, reject
    reconciliation_reason: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    fingerprint: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None


@dataclass
class ReconciliationResult:
    """Result of reconciliation between external and canonical."""
    external_record: MigrationRecord
    canonical_match: Optional[Dict[str, Any]] = None
    match_confidence: float = 0.0
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    recommended_action: str = "create"  # create, update, skip, conflict, reject
    action_reason: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)


# =============================================================================
# ALPHA DATA MIGRATION SERVICE
# =============================================================================

class AlphaDataMigrationService(CapabilityDetector):
    """Service for governed alpha data migration."""
    
    def __init__(self):
        super().__init__()
        self._jobs: Dict[str, MigrationJob] = {}
        self._records: Dict[str, List[MigrationRecord]] = {}
    
    # -------------------------------------------------------------------------
    # JOB MANAGEMENT
    # -------------------------------------------------------------------------
    
    def create_migration_job(
        self,
        organization_id: str,
        requested_by: str,
        source_type: MigrationSourceType,
        source_path: str,
        record_types: List[RecordType],
        governance_approval_id: Optional[str] = None,
        conflict_resolution: ConflictResolutionStrategy = ConflictResolutionStrategy.CANONICAL_WINS,
        validation_mode: str = "strict",
        dry_run: bool = False,
    ) -> MigrationJob:
        """Create a new migration job."""
        
        if not dry_run and not governance_approval_id:
            raise ValueError("Governance approval required for non-dry-run migrations")
        
        job_id = f"mig-{utcnow().strftime('%Y%m%d-%H%M%S')}-{organization_id[:8]}"
        
        job = MigrationJob(
            job_id=job_id,
            organization_id=organization_id,
            requested_by=requested_by,
            source_type=source_type,
            source_path=source_path,
            record_types=record_types,
            governance_approval_id=governance_approval_id,
            dry_run=dry_run,
            conflict_resolution=conflict_resolution,
            validation_mode=validation_mode,
        )
        
        self._jobs[job_id] = job
        self._records[job_id] = []
        
        logger.info(f"Created migration job: {job_id} for org {organization_id}")
        
        return job
    
    def get_job(self, job_id: str) -> Optional[MigrationJob]:
        return self._jobs.get(job_id)
    
    def list_jobs(
        self,
        organization_id: Optional[str] = None,
        status: Optional[MigrationStatus] = None,
    ) -> List[MigrationJob]:
        jobs = list(self._jobs.values())
        
        if organization_id:
            jobs = [j for j in jobs if j.organization_id == organization_id]
        if status:
            jobs = [j for j in jobs if j.status == status]
        
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)
    
    # -------------------------------------------------------------------------
    # DATA LOADING
    # -------------------------------------------------------------------------
    
    async def load_source_data(
        self,
        job_id: str,
    ) -> List[Dict[str, Any]]:
        """Load raw data from source."""
        
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        if job.source_type == MigrationSourceType.JSON:
            return await self._load_json(job.source_path)
        elif job.source_type == MigrationSourceType.CSV:
            return await self._load_csv(job.source_path)
        elif job.source_type == MigrationSourceType.EXCEL:
            return await self._load_excel(job.source_path)
        else:
            raise ValueError(f"Unsupported source type: {job.source_type}")
    
    async def _load_json(self, path: str) -> List[Dict[str, Any]]:
        """Load JSON data from file."""
        import aiofiles
        async with aiofiles.open(path, 'r') as f:
            content = await f.read()
        data = json.loads(content)
        if isinstance(data, dict):
            return [data]
        return data
    
    async def _load_csv(self, path: str) -> List[Dict[str, Any]]:
        """Load CSV data from file."""
        import aiofiles
        import csv
        async with aiofiles.open(path, 'r') as f:
            content = await f.read()
        reader = csv.DictReader(content.splitlines())
        return list(reader)
    
    async def _load_excel(self, path: str) -> List[Dict[str, Any]]:
        """Load Excel data from file."""
        # Would use openpyxl or pandas
        raise NotImplementedError("Excel loading not yet implemented")
    
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
    
    async def validate_records(
        self,
        job_id: str,
        raw_records: List[Dict[str, Any]],
    ) -> List[MigrationRecord]:
        """Validate raw records against schema and business rules."""
        
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        job.status = MigrationStatus.VALIDATING
        job.started_at = utcnow()
        
        records = []
        
        for idx, raw in enumerate(raw_records):
            record = MigrationRecord(
                record_id=f"{job.job_id}-rec-{idx:06d}",
                job_id=job.job_id,
                record_type=self._infer_record_type(raw, job.record_types),
                external_id=self._extract_external_id(raw),
                external_data=raw,
            )
            
            # Validate
            errors, warnings = await self._validate_record(record, job)
            record.validation_errors = errors
            record.validation_warnings = warnings
            
            if errors:
                record.validation_status = "invalid"
            elif warnings:
                record.validation_status = "requires_review"
            else:
                record.validation_status = "valid"
            
            # Compute fingerprint
            record.fingerprint = self._compute_record_fingerprint(record)
            
            records.append(record)
        
        # Store records
        self._records[job.job_id] = records
        
        # Update job stats
        job.total_records = len(records)
        job.validated_records = len([r for r in records if r.validation_status == "valid"])
        job.rejected_records = len([r for r in records if r.validation_status == "invalid"])
        
        return records
    
    def _infer_record_type(self, raw: Dict[str, Any], allowed_types: List[RecordType]) -> RecordType:
        """Infer record type from data."""
        # Check for explicit type field
        if "type" in raw:
            try:
                return RecordType(raw["type"])
            except ValueError:
                pass
        
        # Infer from fields
        if "employee_number" in raw or "designation" in raw:
            return RecordType.EMPLOYEE
        if "department_id" in raw or "code" in raw and "department" in str(raw).lower():
            return RecordType.DEPARTMENT
        if "team_id" in raw:
            return RecordType.TEAM
        if "role" in raw or "permissions" in raw:
            return RecordType.ROLE
        if "project_id" in raw or "project_name" in raw:
            return RecordType.PROJECT
        if "task_id" in raw or "title" in raw and "assignee" in raw:
            return RecordType.TASK
        if "decision_id" in raw or "kind" in raw and "decision" in str(raw).lower():
            return RecordType.DECISION
        
        # Default to first allowed type
        return allowed_types[0] if allowed_types else RecordType.CUSTOM
    
    def _extract_external_id(self, raw: Dict[str, Any]) -> str:
        """Extract external ID from raw data."""
        for key in ["id", "external_id", "source_id", "uuid", "guid"]:
            if key in raw and raw[key]:
                return str(raw[key])
        # Generate from content
        content = json.dumps(raw, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    async def _validate_record(
        self,
        record: MigrationRecord,
        job: MigrationJob,
    ) -> Tuple[List[str], List[str]]:
        """Validate a single record."""
        
        errors = []
        warnings = []
        
        # Basic validation
        if not record.external_id:
            errors.append("Missing external_id")
        
        # Type-specific validation
        if record.record_type == RecordType.EMPLOYEE:
            if not record.external_data.get("email"):
                errors.append("Employee missing email")
            if not record.external_data.get("first_name"):
                warnings.append("Employee missing first_name")
        
        elif record.record_type == RecordType.DEPARTMENT:
            if not record.external_data.get("name"):
                errors.append("Department missing name")
        
        # Check for required fields based on type
        required_fields = {
            RecordType.EMPLOYEE: ["email", "first_name"],
            RecordType.DEPARTMENT: ["name"],
            RecordType.TEAM: ["name"],
            RecordType.PROJECT: ["name"],
            RecordType.DECISION: ["decision_id", "title"],
        }
        
        for field in required_fields.get(record.record_type, []):
            if not record.external_data.get(field):
                errors.append(f"Missing required field: {field}")
        
        return errors, warnings
    
    def _compute_record_fingerprint(self, record: MigrationRecord) -> str:
        """Compute deterministic fingerprint for record."""
        data = {
            "record_type": record.record_type.value,
            "external_id": record.external_id,
            "external_data": record.external_data,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:64]
    
    # -------------------------------------------------------------------------
    # RECONCILIATION
    # -------------------------------------------------------------------------
    
    async def reconcile_records(
        self,
        job_id: str,
        db: AsyncSession,
    ) -> List[ReconciliationResult]:
        """Reconcile validated records against canonical reality."""
        
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        job.status = MigrationStatus.RECONCILING
        
        records = self._records.get(job_id, [])
        valid_records = [r for r in records if r.validation_status == "valid"]
        
        results = []
        
        for record in valid_records:
            result = await self._reconcile_record(db, record, job)
            results.append(result)
            
            # Update record with reconciliation result
            record.reconciliation_action = result.recommended_action
            record.reconciliation_reason = result.action_reason
            record.canonical_data = result.canonical_match
            record.evidence = result.evidence
        
        job.reconciled_records = len(valid_records)
        job.conflicts = len([r for r in results if r.recommended_action == "conflict"])
        
        return results
    
    async def _reconcile_record(
        self,
        db: AsyncSession,
        record: MigrationRecord,
        job: MigrationJob,
    ) -> ReconciliationResult:
        """Reconcile a single record against canonical data."""
        
        # Find potential canonical matches
        canonical_match = await self._find_canonical_match(db, record, job)
        
        if canonical_match:
            # Compare external vs canonical
            conflicts = self._detect_conflicts(record.external_data, canonical_match)
            
            if conflicts:
                if job.conflict_resolution == ConflictResolutionStrategy.CANONICAL_WINS:
                    return ReconciliationResult(
                        external_record=record,
                        canonical_match=canonical_match,
                        match_confidence=0.9,
                        conflicts=conflicts,
                        recommended_action="skip",
                        action_reason="Conflicts detected, canonical wins per policy",
                        evidence=[{"type": "conflict", "details": c} for c in conflicts],
                    )
                elif job.conflict_resolution == ConflictResolutionStrategy.EXTERNAL_WINS:
                    return ReconciliationResult(
                        external_record=record,
                        canonical_match=canonical_match,
                        match_confidence=0.9,
                        conflicts=conflicts,
                        recommended_action="update",
                        action_reason="Conflicts detected, external wins per policy",
                        evidence=[{"type": "conflict", "details": c} for c in conflicts],
                    )
                else:
                    return ReconciliationResult(
                        external_record=record,
                        canonical_match=canonical_match,
                        match_confidence=0.9,
                        conflicts=conflicts,
                        recommended_action="conflict",
                        action_reason="Conflicts detected, manual review required",
                        evidence=[{"type": "conflict", "details": c} for c in conflicts],
                    )
            else:
                # No conflicts - update
                return ReconciliationResult(
                    external_record=record,
                    canonical_match=canonical_match,
                    match_confidence=0.95,
                    conflicts=[],
                    recommended_action="update",
                    action_reason="No conflicts detected, update canonical record",
                    evidence=[{"type": "match", "fields": list(canonical_match.keys())}],
                )
        else:
            # No match - create new
            return ReconciliationResult(
                external_record=record,
                canonical_match=None,
                match_confidence=0.0,
                conflicts=[],
                recommended_action="create",
                action_reason="No existing canonical record found",
                evidence=[{"type": "new_record", "fields": list(record.external_data.keys())}],
            )
    
    async def _find_canonical_match(
        self,
        db: AsyncSession,
        record: MigrationRecord,
        job: MigrationJob,
    ) -> Optional[Dict[str, Any]]:
        """Find matching canonical record."""
        
        # Try to match by external_id if it looks like a canonical ID
        if record.external_id and len(record.external_id) == 32:
            # Could be a canonical ID
            model = self._get_model_for_type(record.record_type)
            if model:
                result = await db.execute(
                    select(model).where(
                        model.organization_id == job.organization_id,
                        model.id == record.external_id,
                    )
                )
                match = result.scalar_one_or_none()
                if match:
                    return self._serialize_canonical(match)
        
        # Try to match by email for employees
        if record.record_type == RecordType.EMPLOYEE:
            email = record.external_data.get("email")
            if email:
                result = await db.execute(
                    select(Employee).where(
                        Employee.organization_id == job.organization_id,
                        Employee.email == email.lower(),
                    )
                )
                match = result.scalar_one_or_none()
                if match:
                    return self._serialize_canonical(match)
        
        # Try to match by name for departments/teams/projects
        if record.record_type in [RecordType.DEPARTMENT, RecordType.TEAM, RecordType.PROJECT]:
            name = record.external_data.get("name")
            if name:
                model = self._get_model_for_type(record.record_type)
                if model:
                    result = await db.execute(
                        select(model).where(
                            model.organization_id == job.organization_id,
                            model.name == name,
                        )
                    )
                    match = result.scalar_one_or_none()
                    if match:
                        return self._serialize_canonical(match)
        
        return None
    
    def _detect_conflicts(
        self,
        external: Dict[str, Any],
        canonical: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Detect conflicts between external and canonical data."""
        
        conflicts = []
        
        # Compare common fields
        common_fields = set(external.keys()) & set(canonical.keys())
        
        for field in common_fields:
            ext_val = external[field]
            can_val = canonical[field]
            
            if ext_val != can_val:
                # Skip timestamp fields
                if field.endswith("_at") or field in ["created_at", "updated_at", "version"]:
                    continue
                
                conflicts.append({
                    "field": field,
                    "external_value": ext_val,
                    "canonical_value": can_val,
                })
        
        return conflicts
    
    def _get_model_for_type(self, record_type: RecordType):
        """Get SQLAlchemy model for record type."""
        models = {
            RecordType.EMPLOYEE: Employee,
            RecordType.DEPARTMENT: Department,
            RecordType.TEAM: Team,
            RecordType.ROLE: Role,
            RecordType.PROJECT: Project,
            RecordType.TASK: Task,
            RecordType.MEETING: Meeting,
            RecordType.DECISION: CompanyDecision,
            RecordType.ACTION: CompanyAction,
            RecordType.COMMITMENT: CompanyCommitment,
            RecordType.AUTHORIZATION: CompanyAuthorization,
            RecordType.OBJECTIVE: CompanyObjective,
            RecordType.GOAL: CompanyGoal,
            RecordType.INITIATIVE: CompanyInitiative,
            RecordType.OPERATION: CanonicalOperation,
        }
        return models.get(record_type)
    
    def _serialize_canonical(self, obj: Any) -> Dict[str, Any]:
        """Serialize canonical object to dict."""
        result = {}
        for column in obj.__table__.columns:
            value = getattr(obj, column.name)
            if isinstance(value, datetime):
                result[column.name] = value.isoformat()
            else:
                result[column.name] = value
        return result
    
    # -------------------------------------------------------------------------
    # APPLICATION
    # -------------------------------------------------------------------------
    
    async def apply_migration(
        self,
        job_id: str,
        db: AsyncSession,
    ) -> Dict[str, int]:
        """Apply reconciled records to canonical reality."""
        
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        if job.dry_run:
            raise ValueError("Cannot apply dry-run job")
        
        if job.status not in [MigrationStatus.RECONCILING, MigrationStatus.APPROVED]:
            raise ValueError(f"Job not ready for application: {job.status}")
        
        if not job.governance_approval_id and not job.dry_run:
            raise ValueError("Governance approval required for application")
        
        job.status = MigrationStatus.APPLYING
        
        records = self._records.get(job_id, [])
        to_apply = [r for r in records if r.reconciliation_action in ["create", "update"]]
        
        applied = 0
        errors = []
        
        for record in to_apply:
            try:
                await self._apply_record(db, record, job)
                record.processed_at = utcnow()
                applied += 1
            except Exception as e:
                errors.append(f"Record {record.record_id}: {e}")
                job.errors.append(f"Record {record.record_id}: {e}")
        
        job.applied_records = applied
        job.errors.extend(errors)
        job.status = MigrationStatus.COMPLETED if not errors else MigrationStatus.FAILED
        job.completed_at = utcnow()
        
        return {
            "applied": applied,
            "errors": len(errors),
        }
    
    async def _apply_record(
        self,
        db: AsyncSession,
        record: MigrationRecord,
        job: MigrationJob,
    ) -> None:
        """Apply a single record to canonical reality."""
        
        model = self._get_model_for_type(record.record_type)
        if not model:
            raise ValueError(f"No model for record type: {record.record_type}")
        
        if record.reconciliation_action == "create":
            # Create new canonical record
            canonical_data = self._transform_to_canonical(record.external_data, record.record_type)
            canonical_data["organization_id"] = job.organization_id
            
            # Generate fingerprint for exact-once
            fp = self._compute_record_fingerprint(record)
            canonical_data["fingerprint"] = fp
            
            obj = model(**canonical_data)
            db.add(obj)
            
        elif record.reconciliation_action == "update":
            # Update existing canonical record
            if not record.canonical_id:
                raise ValueError("No canonical_id for update")
            
            obj = await db.get(model, record.canonical_id)
            if not obj:
                raise ValueError(f"Canonical record not found: {record.canonical_id}")
            
            # Update fields
            canonical_data = self._transform_to_canonical(record.external_data, record.record_type)
            for key, value in canonical_data.items():
                if hasattr(obj, key) and key not in ["id", "organization_id", "created_at", "fingerprint"]:
                    setattr(obj, key, value)
            
            # Update fingerprint
            obj.fingerprint = self._compute_record_fingerprint(record)
        
        await db.flush()
    
    def _transform_to_canonical(
        self,
        external_data: Dict[str, Any],
        record_type: RecordType,
    ) -> Dict[str, Any]:
        """Transform external data to canonical format."""
        
        # Remove migration metadata
        canonical = {k: v for k, v in external_data.items() 
                     if not k.startswith("_")}
        
        # Type-specific transformations
        if record_type == RecordType.EMPLOYEE:
            if "email" in canonical:
                canonical["email"] = canonical["email"].lower()
            if "joining_date" in canonical and isinstance(canonical["joining_date"], str):
                canonical["joining_date"] = datetime.fromisoformat(canonical["joining_date"]).date()
        
        return canonical
    
    # -------------------------------------------------------------------------
    # JOB QUERIES
    # -------------------------------------------------------------------------
    
    def get_job(self, job_id: str) -> Optional[MigrationJob]:
        return self._jobs.get(job_id)
    
    def get_job_records(self, job_id: str) -> List[MigrationRecord]:
        return self._records.get(job_id, [])
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        job = self._jobs.get(job_id)
        if not job:
            return {"error": "Job not found"}
        
        records = self._records.get(job_id, [])
        
        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "total_records": job.total_records,
            "validated": job.validated_records,
            "reconciled": job.reconciled_records,
            "applied": job.applied_records,
            "rejected": job.rejected_records,
            "conflicts": job.conflicts,
            "errors": job.errors,
            "warnings": job.warnings,
            "dry_run": job.dry_run,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }


# Global service
alpha_data_migration_service = AlphaDataMigrationService()