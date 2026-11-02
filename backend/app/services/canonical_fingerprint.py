"""Canonical Fingerprint Service.

Provides deterministic fingerprinting for release candidates and components.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from enum import Enum

from sqlalchemy import select, text, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.validation.capability_contract import (
    CapabilityDetector,
    EnvironmentCapability,
    ValidationCheck,
    ValidationResult,
    ValidationStatus,
    CapabilityAwareValidator,
)

logger = logging.getLogger("vcos.canonical_fingerprint")


def _compute_fingerprint(data: dict) -> str:
    """Compute deterministic SHA-256 fingerprint for exact-once semantics."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:64]


# =============================================================================
# FINGERPRINT COMPONENT DEFINITIONS (Configuration)
# =============================================================================

@dataclass
class FingerprintComponentConfig:
    """Configuration for a canonical component to fingerprint."""
    name: str
    tables: List[str]
    required: bool = False


# Backward compatibility alias for tests
FingerprintComponent = FingerprintComponentConfig


# =============================================================================
# CANONICAL COMPONENTS — List of all canonical component configurations
# =============================================================================

CANONICAL_COMPONENTS: List[FingerprintComponentConfig] = [
    FingerprintComponentConfig(name="organization", tables=["organizations"], required=True),
    FingerprintComponentConfig(name="users", tables=["users"], required=True),
    FingerprintComponentConfig(name="employees", tables=["employees"], required=True),
    FingerprintComponentConfig(name="departments", tables=["departments"], required=True),
    FingerprintComponentConfig(name="teams", tables=["teams"], required=True),
    FingerprintComponentConfig(name="roles", tables=["roles"], required=True),
    FingerprintComponentConfig(name="permissions", tables=["permissions"], required=True),
    FingerprintComponentConfig(name="workforce", tables=["departments", "teams", "roles"], required=False),
    FingerprintComponentConfig(name="projects", tables=["projects"], required=False),
    FingerprintComponentConfig(name="tasks", tables=["tasks"], required=False),
    FingerprintComponentConfig(name="meetings", tables=["meetings"], required=False),
    FingerprintComponentConfig(name="goals", tables=["goals"], required=False),
    FingerprintComponentConfig(name="key_results", tables=["key_results"], required=False),
    FingerprintComponentConfig(name="decisions", tables=["decisions"], required=False),
    FingerprintComponentConfig(name="company_decisions", tables=["company_decisions"], required=True),
    FingerprintComponentConfig(name="company_actions", tables=["company_actions"], required=True),
    FingerprintComponentConfig(name="company_commitments", tables=["company_commitments"], required=True),
    FingerprintComponentConfig(name="company_authorizations", tables=["company_authorizations"], required=True),
    FingerprintComponentConfig(name="company_objectives", tables=["company_objectives"], required=True),
    FingerprintComponentConfig(name="company_goals", tables=["company_goals"], required=True),
    FingerprintComponentConfig(name="company_initiatives", tables=["company_initiatives"], required=False),
    FingerprintComponentConfig(name="canonical_operations", tables=["canonical_operations"], required=True),
    FingerprintComponentConfig(name="operation_attempts", tables=["operation_attempts"], required=True),
    FingerprintComponentConfig(name="organizational_learning", tables=["organizational_learning"], required=False),
    FingerprintComponentConfig(name="learning_evidence", tables=["learning_evidence"], required=False),
    FingerprintComponentConfig(name="canonical_observations", tables=["canonical_observations"], required=True),
    FingerprintComponentConfig(name="correlation_contexts", tables=["correlation_contexts"], required=True),
    FingerprintComponentConfig(name="backup_manifests", tables=["backup_manifests"], required=True),
    FingerprintComponentConfig(name="backup_verification_results", tables=["backup_verification_results"], required=True),
    FingerprintComponentConfig(name="restore_operations", tables=["restore_operations"], required=True),
    FingerprintComponentConfig(name="backup_corruption_tests", tables=["backup_corruption_tests"], required=False),
    FingerprintComponentConfig(name="company_state_snapshots", tables=["company_state_snapshots"], required=True),
    FingerprintComponentConfig(name="company_attention", tables=["company_attention"], required=False),
    FingerprintComponentConfig(name="company_state", tables=["company_state"], required=True),
    FingerprintComponentConfig(name="objective_outcomes", tables=["objective_outcomes"], required=False),
    FingerprintComponentConfig(name="objective_outcome_assessments", tables=["objective_outcome_assessments"], required=False),
    FingerprintComponentConfig(name="canonical_integrations", tables=["canonical_integrations"], required=False),
    FingerprintComponentConfig(name="connector_instances", tables=["connector_instances"], required=False),
    FingerprintComponentConfig(name="sync_runs", tables=["sync_runs"], required=False),
    FingerprintComponentConfig(name="external_operations", tables=["external_operations"], required=False),
    FingerprintComponentConfig(name="integration_health", tables=["integration_health"], required=False),
    FingerprintComponentConfig(name="external_identity_mappings", tables=["external_identity_mappings"], required=False),
    FingerprintComponentConfig(name="external_conflicts", tables=["external_conflicts"], required=False),
    FingerprintComponentConfig(name="source_authority", tables=["source_authority"], required=False),
    FingerprintComponentConfig(name="approval_policies", tables=["approval_policies"], required=True),
    FingerprintComponentConfig(name="governance_scopes", tables=["governance_scopes"], required=True),
]


# =============================================================================
# FINGERPRINT ALGORITHMS & STATUS
# =============================================================================

class FingerprintAlgorithm(str, Enum):
    """Supported fingerprint algorithms."""
    SHA256_64 = "sha256_64"
    SHA256_40 = "sha256_40"


class FingerprintStatus(str, Enum):
    """Fingerprint computation status."""
    COMPUTED = "computed"
    FAILED = "failed"
    PENDING = "pending"
    BLOCKED = "blocked"


# =============================================================================
# NORMALIZATION FUNCTIONS
# =============================================================================

def _normalize_value(value: Any) -> Any:
    """Normalize a single value for deterministic fingerprinting."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Sort keys and recursively normalize
        return {k: _normalize_value(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple, set)):
        # Sort and recursively normalize
        return [_normalize_value(v) for v in sorted(value)]
    # Fallback
    return str(value)


def _normalize_record(record: Dict[str, Any], exclude_fields: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Normalize a database record for fingerprinting."""
    exclude = exclude_fields or {
        # Volatile fields that should not affect canonical fingerprint
        "created_at", "updated_at", "version",
        # Secrets and credentials
        "password", "token", "secret", "key", "credential",
        "authorization", "access_token", "refresh_token",
        "api_key", "api_secret", "client_secret", "private_key",
        "webhook_secret", "signing_secret", "jwt_secret",
        # Runtime metadata
        "request_id", "trace_id", "span_id", "session_id",
        "execution_id", "worker_id", "run_id",
    }
    
    normalized = {}
    for key, value in record.items():
        if key.lower() in exclude:
            continue
        if key.lower().endswith(("_at", "_timestamp")) and isinstance(value, str):
            # Skip volatile timestamps unless they're semantic temporal fields
            semantic_temporal = {"occurred_at", "observed_at", "effective_from", "effective_to",
                              "recorded_at", "decided_at", "started_at", "completed_at",
                              "approved_at", "rejected_at", "superseded_at"}
            if key not in semantic_temporal:
                continue
        normalized[key] = _normalize_value(value)
    return normalized


# =============================================================================
# FINGERPRINT RESULT CLASSES
# =============================================================================

@dataclass
class ComponentFingerprint:
    """Fingerprint for a single canonical component."""
    component_name: str
    fingerprint: str
    entity_count: int
    last_updated: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    algorithm: FingerprintAlgorithm = FingerprintAlgorithm.SHA256_64


@dataclass
class TenantFingerprint:
    """Fingerprint for a single tenant/organization."""
    organization_id: str
    aggregate_fingerprint: str
    entity_count: int
    algorithm: FingerprintAlgorithm = FingerprintAlgorithm.SHA256_64
    metadata: Dict[str, Any] = field(default_factory=dict)
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    components: List[ComponentFingerprint] = field(default_factory=list)
    status: FingerprintStatus = FingerprintStatus.COMPUTED
    error: Optional[str] = None


@dataclass
class ReleaseCandidateFingerprint:
    """Complete release candidate fingerprint evidence."""
    release_candidate_id: str
    application_version: str
    schema_revision: str
    tenants: List[TenantFingerprint] = field(default_factory=list)
    preflight_verdict: str = ""
    preflight_timestamp: Optional[datetime] = None
    fingerprint_algorithm: FingerprintAlgorithm = FingerprintAlgorithm.SHA256_64
    algorithm_version: str = "1.0"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def get_tenant(self, organization_id: str) -> Optional[TenantFingerprint]:
        for t in self.tenants:
            if t.organization_id == organization_id:
                return t
        return None

    @property
    def aggregate_fingerprint(self) -> str:
        """Compute aggregate fingerprint from all tenant fingerprints."""
        if not self.tenants:
            return _compute_fingerprint({"empty": True})

        # Sort tenant fingerprints by organization_id for determinism
        sorted_tenants = sorted(self.tenants, key=lambda t: t.organization_id)
        parts = []
        for tenant in sorted_tenants:
            parts.append(f"{tenant.organization_id}:{tenant.aggregate_fingerprint}")
        combined = "|".join(parts)
        return _compute_fingerprint({"tenants": parts})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "release_candidate_id": self.release_candidate_id,
            "application_version": self.application_version,
            "schema_revision": self.schema_revision,
            "tenants": [t.__dict__ for t in self.tenants],
            "preflight_verdict": self.preflight_verdict,
            "preflight_timestamp": self.preflight_timestamp.isoformat() if self.preflight_timestamp else None,
            "fingerprint_algorithm": self.fingerprint_algorithm.value,
            "algorithm_version": self.algorithm_version,
            "created_at": self.created_at.isoformat(),
        }


# =============================================================================
# CANONICAL FINGERPRINT SERVICE
# =============================================================================

class CanonicalFingerprintService(CapabilityDetector):
    """Service for computing canonical release fingerprints."""

    def __init__(self, algorithm: FingerprintAlgorithm = FingerprintAlgorithm.SHA256_64):
        super().__init__()
        self.algorithm = algorithm
        self._db: Optional[AsyncSession] = None

    def _get_fingerprint_length(self) -> int:
        if self.algorithm == FingerprintAlgorithm.SHA256_64:
            return 64
        elif self.algorithm == FingerprintAlgorithm.SHA256_40:
            return 40
        return 64

    async def _check_table_exists(self, db: AsyncSession, table_name: str) -> bool:
        """Check if a table exists in the database."""
        try:
            result = await db.execute(text(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{table_name}'"))
            return result.scalar() is not None
        except Exception:
            return False

    def _get_org_filter_column(self, table_name: str) -> Optional[str]:
        """Get the column name to filter by organization for a given table.
        
        Returns None if the table doesn't have an organization filter column.
        """
        # Special case: organizations table uses 'id' as the organization identifier
        if table_name == "organizations":
            return "id"
        
        # Tables that don't have organization_id (global catalogs)
        global_tables = {
            "permissions", "roles", "connectors", "connector_capabilities",
            "source_authority", "approval_policies", "governance_scopes",
        }
        if table_name in global_tables:
            return None
            
        return "organization_id"

    async def _has_org_column(self, db: AsyncSession, table_name: str, column_name: str) -> bool:
        """Check if a table has a specific column."""
        try:
            result = await db.execute(text(f"""
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = '{table_name}' AND column_name = '{column_name}'
            """))
            return result.scalar() is not None
        except Exception:
            return False

    async def _get_table_row_count(self, db: AsyncSession, table_name: str, organization_id: str) -> int:
        """Get row count for a table filtered by organization_id."""
        filter_col = self._get_org_filter_column(table_name)
        if filter_col is None:
            # Global table - count all rows
            try:
                result = await db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                return result.scalar() or 0
            except Exception:
                return 0
        
        # Check if column exists
        has_col = await self._has_org_column(db, table_name, filter_col)
        if not has_col:
            # Column doesn't exist - count all rows
            try:
                result = await db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                return result.scalar() or 0
            except Exception:
                return 0
        
        try:
            result = await db.execute(text(f"""
                SELECT COUNT(*) FROM {table_name} 
                WHERE {filter_col} = '{organization_id}'
            """))
            return result.scalar() or 0
        except Exception:
            return 0

    async def _get_table_fingerprint(self, db: AsyncSession, table_name: str, organization_id: str) -> str:
        """Compute fingerprint for a single table's data."""
        filter_col = self._get_org_filter_column(table_name)
        
        # Check if we should filter by organization
        if filter_col is None:
            # Global table - get all rows
            try:
                result = await db.execute(text(f"""
                    SELECT * FROM {table_name} 
                    ORDER BY id
                """))
            except Exception as e:
                logger.warning(f"Failed to compute fingerprint for table {table_name}: {e}")
                return _compute_fingerprint({"table": table_name, "error": str(e)})
        else:
            # Check if column exists
            has_col = await self._has_org_column(db, table_name, filter_col)
            if not has_col:
                # Column doesn't exist - get all rows
                try:
                    result = await db.execute(text(f"""
                        SELECT * FROM {table_name} 
                        ORDER BY id
                    """))
                except Exception as e:
                    logger.warning(f"Failed to compute fingerprint for table {table_name}: {e}")
                    return _compute_fingerprint({"table": table_name, "error": str(e)})
            else:
                # Filter by organization
                try:
                    result = await db.execute(text(f"""
                        SELECT * FROM {table_name} 
                        WHERE {filter_col} = '{organization_id}'
                        ORDER BY id
                    """))
                except Exception as e:
                    logger.warning(f"Failed to compute fingerprint for table {table_name}: {e}")
                    return _compute_fingerprint({"table": table_name, "error": str(e)})
        
        rows = result.fetchall()
        
        if not rows:
            return _compute_fingerprint({"table": table_name, "empty": True})
        
        # Get column names
        columns = result.keys()
        
        # Normalize each row and compute aggregate fingerprint
        normalized_rows = []
        for row in rows:
            record = dict(zip(columns, row))
            normalized = _normalize_record(record)
            normalized_rows.append(normalized)
        
        # Sort for determinism
        normalized_rows.sort(key=lambda x: json.dumps(x, sort_keys=True))
        
        return _compute_fingerprint({
            "table": table_name,
            "organization_id": organization_id,
            "rows": normalized_rows,
        })

    async def compute_tenant_fingerprint(
        self,
        db: AsyncSession,
        organization_id: str,
        components: Optional[List[FingerprintComponentConfig]] = None,
    ) -> TenantFingerprint:
        """Compute canonical fingerprint for a single tenant."""
        self._db = db
        self.db = db  # For capability detector compatibility

        components_list = components or CANONICAL_COMPONENTS
        
        # Compute fingerprint for each component
        components_fp = []
        total_entities = 0
        blocked = False
        error_msg = None
        
        for comp_config in components_list:
            # Compute fingerprint for each table in the component
            component_fingerprints = []
            component_entity_count = 0
            
            for table_name in comp_config.tables:
                table_exists = await self._check_table_exists(db, table_name)
                if not table_exists:
                    # Table doesn't exist - use empty fingerprint
                    if comp_config.required:
                        logger.warning(f"Required table '{table_name}' for component '{comp_config.name}' does not exist")
                        blocked = True
                        if error_msg is None:
                            error_msg = (
                                f"Required table '{table_name}' for component "
                                f"'{comp_config.name}' does not exist"
                            )
                    table_fp = _compute_fingerprint({"table": table_name, "empty": True, "missing": True})
                    table_count = 0
                else:
                    table_fp = await self._get_table_fingerprint(db, table_name, organization_id)
                    table_count = await self._get_table_row_count(db, table_name, organization_id)
                
                component_fingerprints.append(table_fp)
                component_entity_count += table_count
            
            # Aggregate component fingerprint
            comp_fp = _compute_fingerprint({
                "organization_id": organization_id,
                "component": comp_config.name,
                "tables": component_fingerprints,
            })
            
            components_fp.append(ComponentFingerprint(
                component_name=comp_config.name,
                fingerprint=comp_fp,
                entity_count=component_entity_count,
                last_updated=utcnow(),
                algorithm=self.algorithm,
            ))
            total_entities += component_entity_count
        
        # Determine status
        if blocked:
            status = FingerprintStatus.BLOCKED
            aggregate_fp = _compute_fingerprint({"blocked": True, "error": error_msg})
        else:
            status = FingerprintStatus.COMPUTED
            # Compute aggregate fingerprint
            aggregate_fp = _compute_fingerprint({
                "organization_id": organization_id,
                "components": [c.fingerprint for c in components_fp],
            })

        return TenantFingerprint(
            organization_id=organization_id,
            aggregate_fingerprint=aggregate_fp,
            entity_count=total_entities,
            algorithm=self.algorithm,
            components=components_fp,
            status=status,
            error=error_msg,
        )

    async def compute_tenant_fingerprints(
        self,
        db: AsyncSession,
        organization_ids: List[str],
        components: Optional[List[FingerprintComponentConfig]] = None,
    ) -> List[TenantFingerprint]:
        """Compute fingerprints for multiple tenants."""
        results = []
        for org_id in organization_ids:
            fp = await self.compute_tenant_fingerprint(db, org_id, components)
            results.append(fp)
        return results


class ReleaseCandidateFingerprintService:
    """Service for creating release candidate fingerprint evidence."""

    def __init__(self, fingerprint_service: Optional[CanonicalFingerprintService] = None):
        self.fingerprint_service = fingerprint_service or CanonicalFingerprintService()

    async def create_release_candidate_fingerprint(
        self,
        db: AsyncSession,
        release_candidate_id: str,
        application_version: str,
        schema_revision: str,
        organization_ids: Optional[List[str]] = None,
        preflight_verdict: str = "",
        preflight_timestamp: Optional[datetime] = None,
    ) -> ReleaseCandidateFingerprint:
        """Create a release candidate fingerprint evidence."""
        
        # Get organization IDs if not provided
        if organization_ids is None:
            from app.models.organization import Organization
            result = await db.execute(select(Organization.id).where(Organization.status == "active"))
            organization_ids = [row[0] for row in result.fetchall()]

        # Compute tenant fingerprints
        tenant_fps = await self.fingerprint_service.compute_tenant_fingerprints(
            db=db,
            organization_ids=organization_ids,
        )

        # Create release candidate fingerprint
        rc_fingerprint = ReleaseCandidateFingerprint(
            release_candidate_id=release_candidate_id,
            application_version=application_version,
            schema_revision=schema_revision,
            tenants=tenant_fps,
            preflight_verdict=preflight_verdict,
            preflight_timestamp=preflight_timestamp,
        )

        return rc_fingerprint

    async def compare_fingerprints(
        self,
        pre_fp: "ReleaseCandidateFingerprint",
        post_fp: "ReleaseCandidateFingerprint",
    ) -> Dict[str, Any]:
        """Compare pre-release and post-release fingerprints."""
        
        if pre_fp.aggregate_fingerprint == post_fp.aggregate_fingerprint:
            overall = "MATCH"
            component_differences = []
        else:
            overall = "MISMATCH"
            # Find component differences
            component_differences = []
            pre_tenants = {t.organization_id: t for t in pre_fp.tenants}
            post_tenants = {t.organization_id: t for t in post_fp.tenants}
            
            all_orgs = set(pre_tenants.keys()) | set(post_tenants.keys())
            for org_id in all_orgs:
                pre_tenant = pre_tenants.get(org_id)
                post_tenant = post_tenants.get(org_id)
                
                if pre_tenant is None:
                    component_differences.append({
                        "component": f"tenant:{org_id}",
                        "pre_fingerprint": None,
                        "post_fingerprint": post_tenant.aggregate_fingerprint,
                        "change_type": "added",
                    })
                elif post_tenant is None:
                    component_differences.append({
                        "component": f"tenant:{org_id}",
                        "pre_fingerprint": pre_tenant.aggregate_fingerprint,
                        "post_fingerprint": None,
                        "change_type": "removed",
                    })
                elif pre_tenant.aggregate_fingerprint != post_tenant.aggregate_fingerprint:
                    # Find component-level differences
                    pre_comps = {c.component_name: c for c in pre_tenant.components}
                    post_comps = {c.component_name: c for c in post_tenant.components}
                    
                    all_comps = set(pre_comps.keys()) | set(post_comps.keys())
                    for comp_name in all_comps:
                        pre_comp = pre_comps.get(comp_name)
                        post_comp = post_comps.get(comp_name)
                        
                        if pre_comp is None:
                            component_differences.append({
                                "component": f"{org_id}:{comp_name}",
                                "pre_fingerprint": None,
                                "post_fingerprint": post_comp.fingerprint,
                                "change_type": "added",
                            })
                        elif post_comp is None:
                            component_differences.append({
                                "component": f"{org_id}:{comp_name}",
                                "pre_fingerprint": pre_comp.fingerprint,
                                "post_fingerprint": None,
                                "change_type": "removed",
                            })
                        elif pre_comp.fingerprint != post_comp.fingerprint:
                            component_differences.append({
                                "component": f"{org_id}:{comp_name}",
                                "pre_fingerprint": pre_comp.fingerprint,
                                "post_fingerprint": post_comp.fingerprint,
                                "change_type": "modified",
                                "pre_entity_count": pre_comp.entity_count,
                                "post_entity_count": post_comp.entity_count,
                            })
        
        return {
            "overall": overall,
            "pre_aggregate": pre_fp.aggregate_fingerprint,
            "post_aggregate": post_fp.aggregate_fingerprint,
            "component_differences": component_differences,
        }


# Global instances
canonical_fingerprint_service = CanonicalFingerprintService()
release_candidate_fingerprint_service = ReleaseCandidateFingerprintService()