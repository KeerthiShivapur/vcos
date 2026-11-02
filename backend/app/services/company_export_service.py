"""Company Export Service — governed company data export/portability.

Implements tenant-scoped export preserving:
- canonical identities
- organization
- provenance
- decisions
- authorizations
- commitments
- actions
- outcomes
- temporal information
- learning
- longitudinal history

External data must enter through:
Observation → Evidence → Validation → Reconciliation → Canonical Reality

Do not directly inject external data into canonical truth without validation.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set
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
from app.validation.capability_contract import CapabilityDetector

logger = logging.getLogger("vcos.export")


# =============================================================================
# EXPORT DATA MODELS
# =============================================================================

class ExportFormat(str, Enum):
    """Export format options."""
    JSON = "json"
    JSONL = "jsonl"
    PARQUET = "parquet"
    SQL = "sql"


class ExportScope(str, Enum):
    """Export scope options."""
    FULL = "full"                    # Complete company export
    CANONICAL_ONLY = "canonical_only"  # Only canonical reality
    OPERATIONAL = "operational"      # Decisions, actions, outcomes
    LEARNING = "learning"            # Learning, evidence, outcomes
    INTEGRATIONS = "integrations"    # Integration data
    OBSERVABILITY = "observability"  # Observations, degradations
    AUDIT = "audit"                  # Audit logs


@dataclass
class ExportRequest:
    """Export request parameters."""
    organization_id: str
    requested_by: str
    scope: ExportScope = ExportScope.FULL
    format: ExportFormat = ExportFormat.JSON
    include_temporal: bool = True
    include_provenance: bool = True
    include_learning: bool = True
    include_integrations: bool = True
    include_observability: bool = True
    include_audit: bool = False
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    tenant_scoped: bool = True
    include_provenance_chain: bool = True
    governance_approval_id: Optional[str] = None


@dataclass
class ExportResult:
    """Export operation result."""
    export_id: str
    organization_id: str
    requested_by: str
    scope: ExportScope
    format: ExportFormat
    status: str  # pending, running, completed, failed
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    record_counts: Dict[str, int] = field(default_factory=dict)
    export_fingerprint: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    governance_approval_id: Optional[str] = None


@dataclass
class ImportRequest:
    """Import request for governed data migration."""
    organization_id: str
    requested_by: str
    source_export_id: str
    file_path: str
    scope: ExportScope
    governance_approval_id: str
    validation_mode: str = "strict"  # strict, lenient, dry_run
    conflict_resolution: str = "canonical_wins"  # canonical_wins, external_wins, manual


@dataclass
class ImportResult:
    """Import operation result."""
    import_id: str
    organization_id: str
    requested_by: str
    source_export_id: str
    scope: ExportScope
    status: str  # pending, validating, importing, completed, failed, rolled_back
    records_imported: Dict[str, int] = field(default_factory=dict)
    records_rejected: Dict[str, int] = field(default_factory=dict)
    conflicts_detected: int = 0
    validation_errors: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    canonical_fingerprint_before: Optional[str] = None
    canonical_fingerprint_after: Optional[str] = None


# =============================================================================
# EXPORT SERVICE
# =============================================================================

class CompanyExportService(CapabilityDetector):
    """Service for governed company data export."""
    
    def __init__(self):
        super().__init__()
        self._exports: Dict[str, ExportResult] = {}
        self._imports: Dict[str, ImportResult] = {}
    
    # -------------------------------------------------------------------------
    # EXPORT OPERATIONS
    # -------------------------------------------------------------------------
    
    async def create_export(
        self,
        db: AsyncSession,
        request: ExportRequest,
    ) -> ExportResult:
        """Create a new company export."""
        
        # Verify governance approval for full exports
        if request.scope == ExportScope.FULL and not request.governance_approval_id:
            raise ValueError("Governance approval required for full company export")
        
        export_id = f"exp-{utcnow().strftime('%Y%m%d-%H%M%S')}-{request.organization_id[:8]}"
        
        export = ExportResult(
            export_id=export_id,
            organization_id=request.organization_id,
            requested_by=request.requested_by,
            scope=request.scope,
            format=request.format,
            status="pending",
            governance_approval_id=request.governance_approval_id,
        )
        
        self._exports[export_id] = export
        
        # Emit event
        from app.services.event_service import event_service
        await event_service.emit(
            db,
            name="export.started",
            actor_id=request.requested_by,
            organization_id=request.organization_id,
            payload={"export_id": export_id, "scope": request.scope.value},
        )
        
        return export
    
    async def execute_export(
        self,
        db: AsyncSession,
        export_id: str,
    ) -> ExportResult:
        """Execute an export request."""
        
        export = self._exports.get(export_id)
        if not export:
            raise ValueError(f"Export not found: {export_id}")
        
        if export.status != "pending":
            raise ValueError(f"Export already {export.status}")
        
        export.status = "running"
        
        try:
            # Execute export based on scope
            data = await self._export_scope(db, export)
            
            # Write to file
            file_path, file_size = await self._write_export(db, export, data)
            
            # Compute export fingerprint
            export_fingerprint = self._compute_export_fingerprint(data)
            
            export.status = "completed"
            export.file_path = file_path
            export.file_size_bytes = file_size
            export.record_counts = self._count_records(data)
            export.export_fingerprint = export_fingerprint
            export.completed_at = utcnow()
            
            # Emit completion event
            from app.services.event_service import event_service
            await event_service.emit(
                None,  # db would be passed in production
                name="export.completed",
                actor_id=export.requested_by,
                organization_id=export.organization_id,
                payload={
                    "export_id": export_id,
                    "record_counts": export.record_counts,
                    "fingerprint": export_fingerprint,
                },
            )
            
        except Exception as e:
            export.status = "failed"
            export.error = str(e)
            export.completed_at = utcnow()
            logger.error(f"Export failed: {export_id}: {e}")
            raise
        
        return export
    
    async def _export_scope(
        self,
        db: AsyncSession,
        export: ExportResult,
    ) -> Dict[str, Any]:
        """Export data based on scope."""
        
        data = {}
        org_id = export.organization_id
        
        # Base scope always included
        if export.scope in [ExportScope.FULL, ExportScope.CANONICAL_ONLY, ExportScope.OPERATIONAL]:
            data.update(await self._export_canonical_reality(db, org_id))
        
        if export.scope in [ExportScope.FULL, ExportScope.LEARNING]:
            data.update(await self._export_learning(db, org_id))
        
        if export.scope in [ExportScope.FULL, ExportScope.INTEGRATIONS]:
            data.update(await self._export_integrations(db, org_id))
        
        if export.scope in [ExportScope.FULL, ExportScope.OBSERVABILITY]:
            data.update(await self._export_observability(db, org_id))
        
        if export.scope in [ExportScope.FULL, ExportScope.AUDIT]:
            data.update(await self._export_audit(db, org_id))
        
        # Add metadata
        data["_metadata"] = {
            "export_id": export.export_id,
            "organization_id": export.organization_id,
            "scope": export.scope.value,
            "format": export.format.value,
            "exported_at": utcnow().isoformat(),
            "exported_by": export.requested_by,
        }
        
        return data
    
    async def _export_canonical_reality(
        self,
        db: AsyncSession,
        org_id: str,
    ) -> Dict[str, Any]:
        """Export canonical company reality."""
        
        data = {}
        
        # Organization
        org = await db.get(Organization, org_id)
        data["organization"] = self._serialize_org(org) if org else None
        
        # Core canonical entities
        entities = {
            "employees": Employee,
            "departments": Department,
            "teams": Team,
            "roles": Role,
            "projects": Project,
            "tasks": Task,
            "meetings": Meeting,
        }
        
        for name, model in entities.items():
            result = await db.execute(
                select(model).where(model.organization_id == org_id)
            )
            data[name] = [self._serialize_obj(obj) for obj in result.scalars().all()]
        
        # Canonical operating entities
        canonical_entities = {
            "company_decisions": CompanyDecision,
            "company_actions": CompanyAction,
            "company_commitments": CompanyCommitment,
            "company_authorizations": CompanyAuthorization,
            "company_objectives": CompanyObjective,
            "company_goals": CompanyGoal,
            "company_initiatives": CompanyInitiative,
            "canonical_operations": CanonicalOperation,
            "operation_attempts": OperationAttempt,
        }
        
        for name, model in canonical_entities.items():
            result = await db.execute(
                select(model).where(model.organization_id == org_id)
            )
            data[name] = [self._serialize_obj(obj) for obj in result.scalars().all()]
        
        # Company continuity
        continuity_result = await db.execute(
            select(CompanyOperatingContinuity).where(CompanyOperatingContinuity.organization_id == org_id)
        )
        data["company_operating_continuity"] = [
            self._serialize_obj(obj) for obj in continuity_result.scalars().all()
        ]
        
        # Company state snapshots
        snapshot_result = await db.execute(
            select(CompanyStateSnapshotGate30).where(CompanyStateSnapshotGate30.organization_id == org_id)
        )
        data["company_state_snapshots"] = [
            self._serialize_obj(obj) for obj in snapshot_result.scalars().all()
        ]
        
        return data
    
    async def _export_learning(
        self,
        db: AsyncSession,
        org_id: str,
    ) -> Dict[str, Any]:
        """Export organizational learning data."""
        
        learning_result = await db.execute(
            select(OrganizationalLearning).where(OrganizationalLearning.organization_id == org_id)
        )
        
        evidence_result = await db.execute(
            select(LearningEvidence).where(LearningEvidence.organization_id == org_id)
        )
        
        return {
            "organizational_learning": [self._serialize_obj(obj) for obj in learning_result.scalars().all()],
            "learning_evidence": [self._serialize_obj(obj) for obj in evidence_result.scalars().all()],
        }
    
    async def _export_integrations(
        self,
        db: AsyncSession,
        org_id: str,
    ) -> Dict[str, Any]:
        """Export integration data."""
        
        from app.models.canonical_integration import (
            ConnectorInstance, SyncRun, ExternalOperation,
            ExternalIdentityMapping, ExternalConflict,
        )
        
        connector_result = await db.execute(
            select(ConnectorInstance).where(ConnectorInstance.organization_id == org_id)
        )
        
        sync_result = await db.execute(
            select(SyncRun).where(SyncRun.organization_id == org_id)
        )
        
        ext_op_result = await db.execute(
            select(ExternalOperation).where(ExternalOperation.organization_id == org_id)
        )
        
        mapping_result = await db.execute(
            select(ExternalIdentityMapping).where(ExternalIdentityMapping.organization_id == org_id)
        )
        
        conflict_result = await db.execute(
            select(ExternalConflict).where(ExternalConflict.organization_id == org_id)
        )
        
        return {
            "connector_instances": [self._serialize_obj(obj) for obj in connector_result.scalars().all()],
            "sync_runs": [self._serialize_obj(obj) for obj in sync_result.scalars().all()],
            "external_operations": [self._serialize_obj(obj) for obj in ext_op_result.scalars().all()],
            "external_identity_mappings": [self._serialize_obj(obj) for obj in mapping_result.scalars().all()],
            "external_conflicts": [self._serialize_obj(obj) for obj in conflict_result.scalars().all()],
        }
    
    async def _export_observability(
        self,
        db: AsyncSession,
        org_id: str,
    ) -> Dict[str, Any]:
        """Export observability data."""
        
        obs_result = await db.execute(
            select(CanonicalObservation).where(CanonicalObservation.organization_id == org_id)
            .order_by(CanonicalObservation.recorded_at.desc())
            .limit(10000)
        )
        
        deg_result = await db.execute(
            select(Degradation).where(Degradation.organization_id == org_id)
        )
        
        attention_result = await db.execute(
            select(CompanyAttention).where(CompanyAttention.organization_id == org_id)
        )
        
        return {
            "canonical_observations": [self._serialize_obj(obj) for obj in obs_result.scalars().all()],
            "degradations": [self._serialize_obj(obj) for obj in deg_result.scalars().all()],
            "company_attention": [self._serialize_obj(obj) for obj in attention_result.scalars().all()],
        }
    
    async def _export_audit(
        self,
        db: AsyncSession,
        org_id: str,
    ) -> Dict[str, Any]:
        """Export audit logs."""
        
        audit_result = await db.execute(
            select(AuditLog)
            .where(AuditLog.organization_id == org_id)
            .order_by(AuditLog.created_at.desc())
            .limit(50000)
        )
        
        return {
            "audit_logs": [self._serialize_obj(obj) for obj in audit_result.scalars().all()],
        }
    
    # -------------------------------------------------------------------------
    # SERIALIZATION HELPERS
    # -------------------------------------------------------------------------
    
    def _serialize_org(self, org: Organization) -> Dict[str, Any]:
        return {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "industry": org.industry,
            "description": org.description,
            "status": org.status,
            "domain": org.domain,
            "created_at": org.created_at.isoformat() if org.created_at else None,
            "updated_at": org.updated_at.isoformat() if org.updated_at else None,
        }
    
    def _serialize_obj(self, obj: Any) -> Dict[str, Any]:
        """Serialize a SQLAlchemy object to dict."""
        if obj is None:
            return None
        
        result = {}
        for column in obj.__table__.columns:
            value = getattr(obj, column.name)
            if isinstance(value, datetime):
                result[column.name] = value.isoformat()
            elif isinstance(value, (bytes, bytearray)):
                result[column.name] = value.hex()
            else:
                result[column.name] = value
        return result
    
    async def _write_export(
        self,
        db: AsyncSession,
        export: ExportResult,
        data: Dict[str, Any],
    ) -> tuple[str, int]:
        """Write export data to file."""
        
        # In production, write to object storage (S3, GCS, etc.)
        # For now, serialize to JSON
        if export.format == ExportFormat.JSON:
            content = json.dumps(data, default=str, indent=2).encode()
        elif export.format == ExportFormat.JSONL:
            lines = []
            for key, value in data.items():
                if isinstance(value, list):
                    for item in value:
                        lines.append(json.dumps({"_type": key, **item}, default=str))
                else:
                    lines.append(json.dumps({key: value}, default=str))
            content = "\n".join(lines).encode()
        else:
            # Default to JSON
            content = json.dumps(data, default=str, indent=2).encode()
        
        # In production: upload to object storage and return path
        file_path = f"exports/{export.export_id}.{export.format.value}"
        file_size = len(content)
        
        # For now, just return mock path and size
        return file_path, file_size
    
    def _compute_export_fingerprint(self, data: Dict[str, Any]) -> str:
        """Compute deterministic fingerprint of export."""
        import hashlib
        # Serialize deterministically
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:64]
    
    def _count_records(self, data: Dict[str, Any]) -> Dict[str, int]:
        """Count records in export data."""
        counts = {}
        for key, value in data.items():
            if key.startswith("_"):
                continue
            if isinstance(value, list):
                counts[key] = len(value)
            elif value is not None:
                counts[key] = 1
        return counts
    
    # -------------------------------------------------------------------------
    # IMPORT OPERATIONS
    # -------------------------------------------------------------------------
    
    async def create_import(
        self,
        db: AsyncSession,
        request: ImportRequest,
    ) -> ImportResult:
        """Create a new import request."""
        
        if not request.governance_approval_id:
            raise ValueError("Governance approval required for import")
        
        import_id = f"imp-{utcnow().strftime('%Y%m%d-%H%M%S')}-{request.organization_id[:8]}"
        
        imp = ImportResult(
            import_id=import_id,
            organization_id=request.organization_id,
            requested_by=request.requested_by,
            source_export_id=request.source_export_id,
            scope=request.scope,
            status="pending",
        )
        
        self._imports[import_id] = imp
        
        return imp
    
    async def execute_import(
        self,
        db: AsyncSession,
        import_id: str,
    ) -> ImportResult:
        """Execute an import request."""
        
        imp = self._imports.get(import_id)
        if not imp:
            raise ValueError(f"Import not found: {import_id}")
        
        if imp.status != "pending":
            raise ValueError(f"Import already {imp.status}")
        
        # Get pre-import canonical fingerprint
        tenant_fp = await canonical_fingerprint_service.compute_tenant_fingerprint(
            db, imp.organization_id
        )
        imp.canonical_fingerprint_before = tenant_fp.aggregate_fingerprint
        
        imp.status = "validating"
        
        try:
            # Validate import file
            await self._validate_import_file(imp)
            
            imp.status = "importing"
            
            # Execute import based on scope
            await self._execute_import(db, imp)
            
            # Verify post-import canonical fingerprint
            tenant_fp_after = await canonical_fingerprint_service.compute_tenant_fingerprint(
                db, imp.organization_id
            )
            imp.canonical_fingerprint_after = tenant_fp_after.aggregate_fingerprint
            
            imp.status = "completed"
            imp.completed_at = utcnow()
            
        except Exception as e:
            imp.status = "failed"
            imp.error = str(e)
            imp.completed_at = utcnow()
            logger.error(f"Import failed: {import_id}: {e}")
            raise
        
        return imp
    
    async def _validate_import_file(self, imp: ImportResult) -> None:
        """Validate import file before import."""
        # In production: read file, validate schema, check fingerprints
        pass
    
    async def _execute_import(self, db: AsyncSession, imp: ImportResult) -> None:
        """Execute the import."""
        # In production: read file, validate each record, reconcile with canonical
        pass
    
    # -------------------------------------------------------------------------
    # EXPORT/IMPORT QUERIES
    # -------------------------------------------------------------------------
    
    def get_export(self, export_id: str) -> Optional[ExportResult]:
        return self._exports.get(export_id)
    
    def list_exports(
        self,
        organization_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ExportResult]:
        exports = list(self._exports.values())
        
        if organization_id:
            exports = [e for e in exports if e.organization_id == organization_id]
        if status:
            exports = [e for e in exports if e.status == status]
        
        return sorted(exports, key=lambda e: e.started_at, reverse=True)[:limit]
    
    def get_import(self, import_id: str) -> Optional[ImportResult]:
        return self._imports.get(import_id)
    
    def list_imports(
        self,
        organization_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ImportResult]:
        imports = list(self._imports.values())
        
        if organization_id:
            imports = [i for i in imports if i.organization_id == organization_id]
        if status:
            imports = [i for i in imports if i.status == status]
        
        return sorted(imports, key=lambda i: i.started_at, reverse=True)[:limit]


# Global service
company_export_service = CompanyExportService()