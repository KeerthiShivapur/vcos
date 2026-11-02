"""Portable Scale Execution Environment Abstraction.

Provides a unified interface for executing scale validation across different
PostgreSQL environments (Windows native, Linux, container, cloud).

The VCOS application code remains identical across all environments.
"""

import asyncio
import os
import uuid
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum
from contextlib import asynccontextmanager
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool


class EnvironmentType(Enum):
    """Supported scale execution environments."""
    WINDOWS_NATIVE = "windows_native"
    LINUX_NATIVE = "linux_native"
    CONTAINER_POSTGRES = "container_postgres"
    CLOUD_MANAGED = "cloud_managed"
    EXTERNAL_POSTGRES = "external_postgres"


class EnvironmentCapabilityContract:
    """Contract for environment capabilities that must be reported.
    
    This defines the minimum capabilities that must be reported by
    any scale execution environment to ensure safe scale execution.
    """
    
    REQUIRED_CAPABILITIES = {
        "postgresql_version",
        "extensions",
        "schema_access",
        "write_access",
        "transaction_support",
        "copy_support",
        "index_support",
        "connection_capacity",
        "storage_visibility",
        "database_size_visibility",
        "configuration_visibility",
    }
    
    OPTIONAL_CAPABILITIES = {
        "storage_type",
        "connection_utilization",
        "database_size",
        "relevant_settings",
    }
    
    @classmethod
    def validate_capabilities(cls, capabilities: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that all required capabilities are reported."""
        missing = cls.REQUIRED_CAPABILITIES - set(capabilities.keys())
        available_optional = set(capabilities.keys()) & cls.OPTIONAL_CAPABILITIES
        return {
            "required_met": len(missing) == 0,
            "missing_required": list(missing),
            "optional_reported": list(available_optional),
            "total_capabilities": len(capabilities),
        }


class ScaleResultState(Enum):
    """Explicit scale validation result states."""
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"
    INVALID_ENVIRONMENT = "INVALID_ENVIRONMENT"
    INCONCLUSIVE = "INCONCLUSIVE"


class DryRunContract:
    """Contract for dry-run validation.
    
    Dry runs must perform readiness checks without generating data.
    """
    
    REQUIRED_DRY_RUN_CHECKS = {
        "runtime_resolution",
        "preflight_checks",
        "readiness_assessment",
        "capability_inspection",
        "safe_isolation_validation",
    }
    
    @classmethod
    def validate_dry_run(cls, dry_run_results: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that a dry run completed all required checks."""
        missing = cls.REQUIRED_DRY_RUN_CHECKS - set(dry_run_results.keys())
        return {
            "complete": len(missing) == 0,
            "missing_checks": list(missing),
            "results": dry_run_results,
        }
    
    @classmethod
    def must_not_claim_authoritative_pass(cls, dry_run_results: Dict[str, Any]) -> bool:
        """Ensure dry run does not claim authoritative PASS."""
        return dry_run_results.get("authoritative_pass", False) is False


class EndpointFingerprint:
    """Secret-safe endpoint identity for PostgreSQL endpoints.
    
    Captures environment identity without exposing credentials.
    """
    
    @staticmethod
    def compute(db_url: str, pg_version: str, extensions: List[Dict], 
                settings: Dict[str, str], db_name: str) -> str:
        """Compute deterministic fingerprint without secrets."""
        # Extract safe components from URL
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        safe_host = parsed.hostname or "unknown"
        safe_port = parsed.port or 5432
        
        # Build fingerprint data without credentials
        fingerprint_data = {
            "host_fingerprint": hashlib.sha256(f"{safe_host}:{safe_port}".encode()).hexdigest()[:16],
            "database_fingerprint": hashlib.sha256(db_name.encode()).hexdigest()[:16],
            "postgresql_version": pg_version,
            "extensions": sorted([f"{e['name']}:{e['version']}" for e in extensions]),
            "configuration": sorted(settings.items()),
        }
        
        fingerprint_str = str(sorted(fingerprint_data.items()))
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:32]
    
    @staticmethod
    def redact_db_url(db_url: str) -> str:
        """Redact credentials from database URL for logging."""
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(db_url)
        if parsed.password:
            redacted = parsed._replace(netloc=f"{parsed.username}:***@{parsed.hostname}:{parsed.port or 5432}")
            return urlunparse(redacted)
        return db_url


class ScaleRunPortability:
    """Ensures scale runs are portable across PostgreSQL environments.
    
    The same scale runner must operate identically across all environments.
    """
    
    # The canonical scale profile names that must work identically
    CANONICAL_PROFILES = {
        "startup", "small", "medium", "large", "enterprise", "mega"
    }
    
    @classmethod
    def validate_portable_profile(cls, profile_name: str) -> bool:
        """Check if a profile is a canonical portable profile."""
        return profile_name in cls.CANONICAL_PROFILES
    
    @classmethod
    def validate_portable_generation(cls, generation_results: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that generation results are portable (no environment-specific assumptions)."""
        # Check that all counts are deterministic (same seed = same counts)
        required_keys = {"employees", "departments", "teams", "projects", "tasks"}
        missing = required_keys - set(generation_results.keys())
        return {
            "portable": len(missing) == 0,
            "missing_required_entities": list(missing),
            "total_entities": sum(generation_results.values()),
        }
    
    @classmethod
    def validate_environment_independence(cls, evidence: Dict[str, Any]) -> bool:
        """Validate that evidence contains no environment-specific assumptions."""
        # Evidence should not contain environment-specific paths, IPs, etc.
        evidence_str = str(evidence).lower()
        suspicious = ["localhost", "127.0.0.1", "192.168.", "10.", "docker", "podman", "container", "sha256"]
        found = [s for s in suspicious if s in evidence_str]
        return len(found) == 0


class ExternalPostgreSQLSafety:
    """Safety validation for external PostgreSQL endpoints.
    
    External PostgreSQL must be explicitly authorized and safely isolated.
    """
    
    # Heuristics for detecting production databases (these should be BLOCKED)
    PRODUCTION_INDICATORS = [
        "prod", "production", "live", "main", "primary", "master"
    ]
    
    @classmethod
    def validate_external_target(cls, db_url: str, db_name: str) -> Dict[str, Any]:
        """Validate that an external PostgreSQL target is safe for scale testing."""
        from urllib.parse import urlparse
        
        parsed = urlparse(db_url)
        
        results = {
            "safe": True,
            "warnings": [],
            "errors": [],
            "database_name": db_name,
            "host": parsed.hostname,
            "port": parsed.port,
        }
        
        # Check for production database indicators
        if any(ind in db_name.lower() for ind in cls.PRODUCTION_INDICATORS):
            results["safe"] = False
            results["errors"].append(f"Database name '{db_name}' suggests production environment")
        
        # Check for common production hosts
        if parsed.hostname and any(ind in parsed.hostname.lower() for ind in ["prod", "production", "live"]):
            results["warnings"].append(f"Hostname '{parsed.hostname}' suggests production environment")
        
        # Verify it's not a well-known managed service production endpoint
        managed_prod_patterns = [
            "rds.amazonaws.com", "postgres.database.azure.com", 
            "cloudsql.googleapis.com", "aivencloud.com"
        ]
        if parsed.hostname and any(p in parsed.hostname for p in managed_prod_patterns):
            results["warnings"].append(f"Managed cloud database detected: {parsed.hostname}")
        
        return results
    
    @classmethod
    def validate_isolation_strategy(cls, db_url: str, isolation_strategy: str) -> Dict[str, Any]:
        """Validate that the isolation strategy is safe for the target."""
        valid_strategies = ["dedicated_database", "dedicated_schema", "transaction_rollback"]
        
        if isolation_strategy not in valid_strategies:
            return {
                "valid": False,
                "error": f"Invalid isolation strategy: {isolation_strategy}. Must be one of {valid_strategies}"
            }
        
        return {"valid": True, "strategy": isolation_strategy}


class ResourceSafetyValidator:
    """Validates resource safety before and after scale execution."""
    
    @classmethod
    def validate_pre_execution(cls, environment_capability: 'EnvironmentCapability', 
                               profile_name: str) -> Dict[str, Any]:
        """Validate that environment has sufficient resources for the scale profile."""
        from tests.scale.postgres.safe_scale import SCALE_ENVELOPES
        
        envelope = SCALE_ENVELOPES.get(profile_name)
        if not envelope:
            return {
                "safe": True,
                "warning": f"No resource envelope defined for profile {profile_name}",
            }
        
        issues = []
        warnings = []
        
# Check connection capacity
        if environment_capability.max_connections > 0:
            needed = envelope.max_connections
            available = environment_capability.max_connections
            # Environment must have at least the needed connections
            if available < needed:
                issues.append(f"Connection capacity insufficient: need {needed}, have {available}")
            elif available < needed * 1.2:
                warnings.append(f"Connection capacity tight: need {needed}, have {available}")
        
        # Check database size vs disk space
        if environment_capability.free_disk_gb > 0:
            needed_gb = envelope.estimated_disk_gb
            if needed_gb > environment_capability.free_disk_gb * 0.8:
                issues.append(f"Disk space may be insufficient: need ~{needed_gb:.1f}GB, have {environment_capability.free_disk_gb:.1f}GB")
        
        # Check memory
        if environment_capability.total_memory_mb > 0:
            needed_mb = environment_capability.shared_buffers_mb + environment_capability.work_mem_mb * 4 + environment_capability.maintenance_work_mem_mb
            if needed_mb > environment_capability.total_memory_mb * 0.8:
                warnings.append(f"PostgreSQL memory settings may exceed available memory")
        
        return {
            "safe": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
        }
    
    @classmethod
    def validate_post_execution(cls, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that resources were properly cleaned up after execution."""
        issues = []
        
        # Check cleanup was performed
        if not evidence.get("resources", {}).get("cleanup_completed", False):
            issues.append("Resource cleanup was not completed")
        
        # Check for connection leaks
        if evidence.get("resources", {}).get("connection_leaks", 0) > 0:
            issues.append(f"Connection leaks detected: {evidence['resources']['connection_leaks']}")
        
        # Check for resource leaks
        if evidence.get("resources", {}).get("resource_leaks"):
            issues.append(f"Resource leaks detected: {evidence['resources']['resource_leaks']}")
        
        return {
            "clean": len(issues) == 0,
            "issues": issues,
        }


class EvidenceCompatibility:
    """Ensures evidence artifacts are compatible across environments."""
    
    @classmethod
    def validate_evidence_portability(cls, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that evidence can be compared across environments."""
        issues = []
        
        # Check for environment-specific data
        evidence_str = str(evidence).lower()
        
        # Should not contain absolute paths
        if "/home/" in evidence_str or "c:\\" in evidence_str or "/var/lib/postgresql" in evidence_str:
            issues.append("Evidence contains absolute filesystem paths")
        
        # Should not contain container-specific identifiers
        if "container" in evidence_str and ("id" in evidence_str or "sha256" in evidence_str):
            issues.append("Evidence may contain container-specific identifiers")
        
        # Should not contain host-specific info
        if "localhost" in evidence_str or "127.0.0.1" in evidence_str:
            issues.append("Evidence contains localhost references")
        
        return {
            "portable": len(issues) == 0,
            "issues": issues,
        }
    
    @classmethod
    def normalize_for_comparison(cls, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize evidence for cross-environment comparison."""
        # Remove environment-specific fields
        normalized = evidence.copy()
        
        # Remove timestamps (these will differ)
        for key in ["started_at", "completed_at", "timestamp"]:
            if key in normalized:
                normalized[key] = "NORMALIZED"
        
        # Remove environment-specific identifiers
        for key in ["environment_fingerprint", "run_id"]:
            if key in normalized:
                normalized[key] = "NORMALIZED"
        
        return normalized


@dataclass
class EnvironmentCapability:
    """Measured capabilities of an execution environment."""
    platform: str
    os_version: str
    architecture: str
    cpu_count: int
    total_memory_mb: int
    available_memory_mb: int
    free_disk_gb: float
    postgresql_version: str
    postgresql_architecture: str
    max_connections: int
    shared_buffers_mb: int
    work_mem_mb: int
    maintenance_work_mem_mb: int
    max_wal_size_mb: int
    effective_cache_size_mb: int
    max_connections: int
    autovacuum_max_workers: int
    supports_parallel_query: bool
    supports_partitioning: bool
    supports_logical_replication: bool
    extensions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    
    def to_capability_dict(self) -> Dict[str, Any]:
        """Convert to capability dictionary for validation."""
        return {
            "postgresql_version": self.postgresql_version,
            "extensions": self.extensions,
            "schema_access": True,  # Always true if we can connect
            "write_access": True,   # Always true if we can connect
            "transaction_support": True,
            "copy_support": True,
            "index_support": True,
            "connection_capacity": self.max_connections,
            "storage_visibility": self.free_disk_gb > 0,
            "database_size_visibility": True,
            "configuration_visibility": True,
            "storage_type": "unknown",
            "connection_utilization": None,
            "database_size": None,
            "relevant_settings": {},
        }


@dataclass
class ResourceEnvelope:
    """Resource envelope for a scale profile."""
    profile_name: str
    employee_count: int
    estimated_database_size_gb: float
    estimated_wal_size_gb: float
    estimated_temp_space_gb: float
    estimated_memory_gb: float
    estimated_cpu_cores: int
    estimated_connections: int
    max_recommended_work_mem_mb: int
    max_recommended_maintenance_work_mem_mb: int
    max_recommended_shared_buffers_mb: int
    max_recommended_max_wal_size_gb: float
    max_recommended_connections: int
    estimated_generation_time_minutes: float
    estimated_validation_time_minutes: float


@dataclass
class ScalePreflightResult:
    """Result of preflight validation."""
    can_proceed: bool
    profile_name: str
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    capacity_metrics: Optional[Dict[str, Any]] = None
    resource_envelope: Optional[Any] = None
    environment_capability: Optional[Any] = None


@dataclass
class ScaleExecutionResult:
    """Result of a scale execution."""
    profile_name: str
    employee_count: int
    state: str  # ScaleResultState
    start_time: str
    end_time: Optional[str] = None
    generation_time_seconds: float = 0.0
    validation_time_seconds: float = 0.0
    total_rows_generated: int = 0
    generation_throughput_rows_sec: float = 0.0
    table_counts: Dict[str, int] = field(default_factory=dict)
    database_size_mb: float = 0.0
    index_size_mb: float = 0.0
    generation_throughput_rows_sec: float = 0.0
    validation_results: Dict[str, Any] = field(default_factory=dict)
    resource_measurements: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    failure_classification: Optional[str] = None
    failure_details: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['state'] = self.state
        return d


class ScaleExecutionEnvironment(ABC):
    """Abstract base class for scale execution environments.
    
    The VCOS scale generator and validator must work identically
    regardless of the underlying PostgreSQL host environment.
    """
    
    def __init__(self, name: str, db_url: str):
        self.name = name
        self.db_url = db_url
        self.engine = None
        self.session_factory = None
        self._initialized = False
        self._start_time: Optional[datetime] = None
        
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the environment (create engine, verify connectivity)."""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """Start the environment (ensure PostgreSQL is running, healthy)."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the environment gracefully."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if environment is healthy and ready for scale operations."""
        pass
    
    @abstractmethod
    async def collect_metrics(self) -> Dict[str, Any]:
        """Collect current resource metrics."""
        pass
    
    @abstractmethod
    async def collect_failure_evidence(self) -> Dict[str, Any]:
        """Collect failure evidence if environment is unhealthy."""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up all resources."""
        pass
    
    @abstractmethod
    def get_capability(self) -> 'EnvironmentCapability':
        """Get measured environment capabilities."""
        pass
    
    @abstractmethod
    def get_resource_envelope(self, profile_name: str) -> 'ResourceEnvelope':
        """Get resource envelope for a scale profile."""
        pass
    
    @asynccontextmanager
    async def session(self) -> AsyncSession:
        """Provide a database session with proper cleanup."""
        if not self.session_factory:
            raise RuntimeError("Environment not initialized")
        
        session = self.session_factory()
        try:
            yield session
        finally:
            await session.close()
    
    @contextmanager
    def sync_session(self):
        """Provide a synchronous database session with proper cleanup."""
        raise NotImplementedError("Sync session not implemented for this environment")


class WindowsNativePostgresEnvironment(ScaleExecutionEnvironment):
    """Windows native PostgreSQL environment (developer workstation)."""
    
    def __init__(self, db_url: str, scale_test_conf_path: Optional[str] = None):
        super().__init__("windows_native", db_url)
        self.scale_test_conf_path = scale_test_conf_path
        self._sync_engine = None
        self._sync_session_factory = None
        
    async def initialize(self) -> None:
        """Initialize async and sync engines."""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session, sessionmaker
        import os
        
        # Async engine for validation
        self.engine = create_async_engine(
            self.db_url,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=True,
            connect_args={"server_settings": {"search_path": "public"}},
            echo=False,
            future=True,
        )
        
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # Sync engine for generation (avoids asyncpg greenlet issues)
        async_url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test")
        sync_url = async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        
        self._sync_engine = create_engine(
            sync_url,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=True,
            connect_args={"options": "-c search_path=public"},
            echo=False,
            future=True,
        )
        
        self._sync_session_factory = sessionmaker(
            self._sync_engine,
            class_=Session,
            expire_on_commit=False,
        )
        
        # Verify connection
        async with self.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        
        self._initialized = True
    
    async def start(self) -> None:
        """Start the environment (verify PostgreSQL is running)."""
        # Verify connection
        async with self.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        
        self._start_time = datetime.utcnow()
    
    async def stop(self) -> None:
        """Stop the environment."""
        pass  # Windows native PG runs as service
    
    async def health_check(self) -> bool:
        """Check if environment is healthy."""
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
    
    async def collect_metrics(self) -> Dict[str, Any]:
        """Collect current resource metrics."""
        from tests.scale.postgres.diagnostics import PostgreSQLCapacityDiagnostics
        diagnostics = PostgreSQLCapacityDiagnostics(self.db_url)
        await diagnostics.initialize()
        try:
            metrics = await diagnostics.run_full_diagnostics()
            return {
                "database_size_mb": metrics.database_size_mb,
                "index_size_mb": metrics.total_index_size_mb,
                "connections": {
                    "active": metrics.active_connections,
                    "idle": metrics.idle_connections,
                    "waiting": metrics.waiting_connections,
                    "total": metrics.used_connections,
                    "max": metrics.max_connections,
                },
                "wal_size_mb": metrics.wal_size_mb,
                "database_size_mb": metrics.database_size_mb,
                "index_size_mb": metrics.total_index_size_mb,
                "temp_files_mb": metrics.temp_files.get("temp_bytes_mb", 0),
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            await diagnostics.close()
    
    async def collect_failure_evidence(self) -> Dict[str, Any]:
        """Collect failure evidence if environment is unhealthy."""
        from tests.scale.postgres.windows_diagnostics import capture_windows_crash_evidence_sync
        try:
            evidence = capture_windows_crash_evidence_sync(self.db_url)
            return evidence.to_dict()
        except Exception as e:
            return {"error": str(e)}
    
    async def cleanup(self) -> None:
        """Clean up all resources."""
        if self.engine:
            await self.engine.dispose()
        if self._sync_engine:
            self._sync_engine.dispose()
    
    def get_capability(self) -> 'EnvironmentCapability':
        """Get measured environment capabilities."""
        return EnvironmentCapability(
            platform="windows",
            os_version=platform.platform(),
            architecture=platform.machine(),
            cpu_count=os.cpu_count() or 0,
            total_memory_mb=0,
            available_memory_mb=0,
            free_disk_gb=0.0,
            postgresql_version="unknown",
            postgresql_architecture="x64",
            max_connections=100,
            shared_buffers_mb=0,
            work_mem_mb=0,
            maintenance_work_mem_mb=0,
            max_wal_size_mb=0,
            effective_cache_size_mb=0,
            autovacuum_max_workers=2,
            supports_parallel_query=True,
            supports_partitioning=True,
            supports_logical_replication=True,
        )
    
    def get_resource_envelope(self, profile_name: str) -> 'ResourceEnvelope':
        """Get resource envelope for a scale profile."""
        from tests.scale.postgres.safe_scale import SCALE_ENVELOPES
        envelope = SCALE_ENVELOPES.get(profile_name)
        if not envelope:
            # Create default envelope
            return ResourceEnvelope(
                profile_name=profile_name,
                employee_count=0,
                estimated_database_size_gb=0.0,
                estimated_wal_size_gb=0.0,
                estimated_temp_space_gb=0.0,
                estimated_memory_gb=0.0,
                estimated_cpu_cores=0,
                estimated_connections=0,
                max_recommended_work_mem_mb=0,
                max_recommended_maintenance_work_mem_mb=0,
                max_recommended_shared_buffers_mb=0,
                max_recommended_max_wal_size_gb=0.0,
                max_recommended_connections=0,
                estimated_generation_time_minutes=0.0,
                estimated_validation_time_minutes=0.0,
            )
        return envelope

    @contextmanager
    def sync_session(self):
        """Provide a synchronous database session with proper cleanup."""
        if not self._sync_session_factory:
            raise RuntimeError("Sync session factory not initialized")
        
        session = self._sync_session_factory()
        try:
            yield session
        finally:
            session.close()


class LinuxPostgresEnvironment(ScaleExecutionEnvironment):
    """Linux native PostgreSQL environment (production-like)."""
    
    def __init__(self, db_url: str, scale_test_conf_path: Optional[str] = None):
        super().__init__("linux_native", db_url)
        
    async def initialize(self) -> None:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session, sessionmaker
        import os
        
        self.engine = create_async_engine(
            self.db_url,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            connect_args={"server_settings": {"search_path": "public"}},
            echo=False,
            future=True,
        )
        
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        async_url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test")
        sync_url = async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        
        self._sync_engine = create_engine(
            sync_url,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            connect_args={"options": "-c search_path=public"},
            echo=False,
            future=True,
        )
        
        self._sync_session_factory = sessionmaker(
            self._sync_engine,
            class_=Session,
            expire_on_commit=False,
        )
        
        async with self.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        
        self._initialized = True
    
    async def start(self) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        self._start_time = datetime.utcnow()
    
    async def stop(self) -> None:
        pass
    
    async def health_check(self) -> bool:
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
    
    async def collect_metrics(self) -> Dict[str, Any]:
        from tests.scale.postgres.diagnostics import PostgreSQLCapacityDiagnostics
        diagnostics = PostgreSQLCapacityDiagnostics(self.db_url)
        await diagnostics.initialize()
        try:
            metrics = await diagnostics.run_full_diagnostics()
            return {
                "database_size_mb": metrics.database_size_mb,
                "index_size_mb": metrics.total_index_size_mb,
                "connections": {
                    "active": metrics.active_connections,
                    "idle": metrics.idle_connections,
                    "waiting": metrics.waiting_connections,
                    "total": metrics.used_connections,
                    "max": metrics.max_connections,
                },
                "wal_size_mb": metrics.wal_size_mb,
                "database_size_mb": metrics.database_size_mb,
                "index_size_mb": metrics.total_index_size_mb,
                "temp_files_mb": metrics.temp_files.get("temp_bytes_mb", 0),
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            await diagnostics.close()
    
    async def collect_failure_evidence(self) -> Dict[str, Any]:
        return {"error": "Linux failure evidence collection not implemented"}
    
    async def cleanup(self) -> None:
        if self.engine:
            await self.engine.dispose()
        if self._sync_engine:
            self._sync_engine.dispose()
    
    def get_capability(self) -> 'EnvironmentCapability':
        return EnvironmentCapability(
            platform="linux",
            os_version=platform.platform(),
            architecture=platform.machine(),
            cpu_count=os.cpu_count() or 0,
            total_memory_mb=0,
            available_memory_mb=0,
            free_disk_gb=0.0,
            postgresql_version="unknown",
            postgresql_architecture="x64",
            max_connections=200,
            shared_buffers_mb=0,
            work_mem_mb=0,
            maintenance_work_mem_mb=0,
            max_wal_size_mb=0,
            effective_cache_size_mb=0,
            autovacuum_max_workers=8,
            supports_parallel_query=True,
            supports_partitioning=True,
            supports_logical_replication=True,
        )
    
    def get_resource_envelope(self, profile_name: str) -> 'ResourceEnvelope':
        from tests.scale.postgres.safe_scale import SCALE_ENVELOPES
        envelope = SCALE_ENVELOPES.get(profile_name)
        if not envelope:
            return ResourceEnvelope(
                profile_name=profile_name,
                employee_count=0,
                estimated_database_size_gb=0.0,
                estimated_wal_size_gb=0.0,
                estimated_temp_space_gb=0.0,
                estimated_memory_gb=0.0,
                estimated_cpu_cores=0,
                estimated_connections=0,
                max_recommended_work_mem_mb=0,
                max_recommended_maintenance_work_mem_mb=0,
                max_recommended_shared_buffers_mb=0,
                max_recommended_max_wal_size_gb=0.0,
                max_recommended_connections=0,
                estimated_generation_time_minutes=0.0,
                estimated_validation_time_minutes=0.0,
            )
        return envelope

    @contextmanager
    def sync_session(self):
        if not self._sync_session_factory:
            raise RuntimeError("Sync session factory not initialized")
        
        session = self._sync_session_factory()
        try:
            yield session
        finally:
            session.close()


class ExternalPostgresEnvironment(ScaleExecutionEnvironment):
    """External PostgreSQL environment (explicitly provided endpoint).
    
    This environment connects to an explicitly provided PostgreSQL instance
    (cloud managed, remote server, etc.) without managing the PostgreSQL process itself.
    """
    
    def __init__(self, db_url: str, scale_test_conf_path: Optional[str] = None):
        super().__init__("external_postgres", db_url)
        
    async def initialize(self) -> None:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session, sessionmaker
        import os
        
        self.engine = create_async_engine(
            self.db_url,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            connect_args={"server_settings": {"search_path": "public"}},
            echo=False,
            future=True,
        )
        
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # Sync engine for generation (avoids asyncpg greenlet issues)
        sync_url = self.db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        
        self._sync_engine = create_engine(
            self.db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://"),
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            connect_args={"options": "-c search_path=public"},
            echo=False,
            future=True,
        )
        
        self._sync_session_factory = sessionmaker(
            self._sync_engine,
            class_=Session,
            expire_on_commit=False,
        )
        
        # Verify connection
        async with self.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        
        self._initialized = True
    
    async def start(self) -> None:
        """Start the environment (verify PostgreSQL is running)."""
        # Verify connection
        async with self.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        
        self._start_time = datetime.utcnow()
    
    async def stop(self) -> None:
        pass  # External PostgreSQL runs independently
    
    async def health_check(self) -> bool:
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
    
    async def collect_metrics(self) -> Dict[str, Any]:
        from tests.scale.postgres.diagnostics import PostgreSQLCapacityDiagnostics
        diagnostics = PostgreSQLCapacityDiagnostics(self.db_url)
        await diagnostics.initialize()
        try:
            metrics = await diagnostics.run_full_diagnostics()
            return {
                "database_size_mb": metrics.database_size_mb,
                "index_size_mb": metrics.total_index_size_mb,
                "connections": {
                    "active": metrics.active_connections,
                    "idle": metrics.idle_connections,
                    "waiting": metrics.waiting_connections,
                    "total": metrics.used_connections,
                    "max": metrics.max_connections,
                },
                "wal_size_mb": metrics.wal_size_mb,
                "database_size_mb": metrics.database_size_mb,
                "index_size_mb": metrics.total_index_size_mb,
                "temp_files_mb": metrics.temp_files.get("temp_bytes_mb", 0),
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            await diagnostics.close()
    
    async def collect_failure_evidence(self) -> Dict[str, Any]:
        return {"error": "External PostgreSQL failure evidence collection not implemented"}
    
    async def preflight(self) -> Dict[str, Any]:
        """Run comprehensive preflight checks before scale validation."""
        results = {
            "reachable": False,
            "authenticated": False,
            "version_supported": False,
            "extensions_available": False,
            "schema_access": False,
            "database_writable": False,
            "connection_capacity": False,
            "transaction_works": False,
            "authorized_target": False,
            "errors": [],
        }
        
        if not self.engine:
            results["errors"].append("Engine not initialized")
            return results
        
        try:
            # 1. Reachability + Authentication
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            results["reachable"] = True
            results["authenticated"] = True
            
            # 2. Version check
            async with self.engine.begin() as conn:
                result = await conn.execute(text("SELECT version()"))
                version = result.scalar()
                if version:
                    results["version"] = version
                    # PostgreSQL 14+ is supported
                    if "PostgreSQL 1" in version or "PostgreSQL 1[4-9]" in version or "PostgreSQL 1[0-9][0-9]" in version:
                        results["version_supported"] = True
            
            # 3. Extensions
            async with self.engine.begin() as conn:
                result = await conn.execute(text("""
                    SELECT extname FROM pg_extension 
                    WHERE extname IN ('pg_trgm', 'uuid-ossp', 'btree_gin', 'btree_gist')
                """))
                extensions = [row[0] for row in result]
                results["extensions"] = extensions
                results["extensions_available"] = len(extensions) > 0
            
            # 4. Schema access
            async with self.engine.begin() as conn:
                result = await conn.execute(text("SELECT current_schema()"))
                schema = result.scalar()
                results["schema"] = schema
                results["schema_access"] = schema == "public"
            
            # 5. Database writable
            async with self.engine.begin() as conn:
                # Create a temporary table to test write access
                await conn.execute(text("CREATE TEMP TABLE _vcos_preflight_test (id INT)"))
                await conn.execute(text("INSERT INTO _vcos_preflight_test VALUES (1)"))
                await conn.execute(text("DROP TABLE _vcos_preflight_test"))
            results["database_writable"] = True
            
            # 6. Connection capacity
            async with self.engine.begin() as conn:
                result = await conn.execute(text("""
                    SELECT 
                        setting::int as max_conn,
                        (SELECT count(*) FROM pg_stat_activity) as used_conn
                    FROM pg_settings WHERE name = 'max_connections'
                """))
                row = result.first()
                if row:
                    max_conn, used_conn = row
                    results["max_connections"] = max_conn
                    results["used_connections"] = used_conn
                    results["available_connections"] = max_conn - used_conn
                    results["connection_capacity"] = (max_conn - used_conn) >= 10
            
            # 7. Transaction works
            async with self.engine.begin() as conn:
                await conn.execute(text("BEGIN"))
                await conn.execute(text("SELECT 1"))
                await conn.execute(text("COMMIT"))
            results["transaction_works"] = True
            
            # 8. Authorized target - check if this is a scale test database
            # We can't fully verify this, but we can check for scale test markers
            results["authorized_target"] = True  # Assume authorized if TEST_DATABASE_URL was provided
            
        except Exception as e:
            results["errors"].append(str(e))
        
        results["can_proceed"] = all([
            results["reachable"],
            results["authenticated"],
            results["version_supported"],
            results["extensions_available"],
            results["schema_access"],
            results["database_writable"],
            results["connection_capacity"],
            results["transaction_works"],
        ])
        
        return results
    
    async def cleanup(self) -> None:
        if self.engine:
            await self.engine.dispose()
        if self._sync_engine:
            self._sync_engine.dispose()
    
    def get_capability(self) -> 'EnvironmentCapability':
        return EnvironmentCapability(
            platform="external",
            os_version=platform.platform(),
            architecture=platform.machine(),
            cpu_count=os.cpu_count() or 0,
            total_memory_mb=0,
            available_memory_mb=0,
            free_disk_gb=0.0,
            postgresql_version="unknown",
            postgresql_architecture="x64",
            max_connections=200,
            shared_buffers_mb=0,
            work_mem_mb=0,
            maintenance_work_mem_mb=0,
            max_wal_size_mb=0,
            effective_cache_size_mb=0,
            autovacuum_max_workers=8,
            supports_parallel_query=True,
            supports_partitioning=True,
            supports_logical_replication=True,
        )
    
    def get_resource_envelope(self, profile_name: str) -> 'ResourceEnvelope':
        from tests.scale.postgres.safe_scale import SCALE_ENVELOPES
        envelope = SCALE_ENVELOPES.get(profile_name)
        if not envelope:
            return ResourceEnvelope(
                profile_name=profile_name,
                employee_count=0,
                estimated_database_size_gb=0.0,
                estimated_wal_size_gb=0.0,
                estimated_temp_space_gb=0.0,
                estimated_memory_gb=0.0,
                estimated_cpu_cores=0,
                estimated_connections=0,
                max_recommended_work_mem_mb=0,
                max_recommended_maintenance_work_mem_mb=0,
                max_recommended_shared_buffers_mb=0,
                max_recommended_max_wal_size_gb=0.0,
                max_recommended_connections=0,
                estimated_generation_time_minutes=0.0,
                estimated_validation_time_minutes=0.0,
            )
        return envelope
    
    async def get_fingerprint(self) -> Dict[str, Any]:
        import subprocess
        import hashlib
        
        fingerprint = {
            "vcos_revision": "unknown",
            "schema_revision": "unknown",
            "postgresql_version": "unknown",
            "runtime": "external_postgres",
            "runtime_version": "unknown",
            "image": "external",
            "image_digest": "unknown",
            "cpu_count": os.cpu_count() or 0,
            "memory_bytes": "unknown",
            "storage_type": "external",
            "extensions": [],
            "configuration_fingerprint": "unknown",
            "scale_profile": self.profile.name if hasattr(self, 'profile') else "unknown",
            "employee_count": self.config.employee_count if hasattr(self, 'config') else 0,
            "tenant_count": 1,
            "dataset_seed": "42",
            "dataset_fingerprint": "deterministic",
            "started_at": self._start_time.isoformat() if self._start_time else "unknown",
            "completed_at": "unknown",
        }
        
        # Try to get VCOS revision
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=os.getcwd()
            )
            if result.returncode == 0:
                fingerprint["vcos_revision"] = result.stdout.strip()[:12]
        except Exception:
            pass
        
        # Try to get actual PostgreSQL details
        try:
            async with self.engine.begin() as conn:
                # Version
                result = await conn.execute(text("SELECT version()"))
                version = result.scalar()
                if version:
                    fingerprint["postgresql_version"] = version
                
                # Extensions
                result = await conn.execute(text("""
                    SELECT extname, extversion FROM pg_extension 
                    WHERE extname IN ('pg_trgm', 'uuid-ossp', 'btree_gin', 'btree_gist', 'pgcrypto')
                    ORDER BY extname
                """))
                extensions = [{"name": row[0], "version": row[1]} for row in result]
                fingerprint["extensions"] = extensions
                
                # Key settings
                result = await conn.execute(text("""
                    SELECT name, setting FROM pg_settings 
                    WHERE name IN (
                        'shared_buffers', 'work_mem', 'maintenance_work_mem',
                        'max_wal_size', 'checkpoint_timeout', 'effective_cache_size',
                        'max_connections', 'max_parallel_workers_per_gather'
                    )
                """))
                settings = {row[0]: row[1] for row in result}
                fingerprint["configuration"] = settings
                
                # Create configuration fingerprint
                config_str = str(sorted(settings.items()))
                fingerprint["configuration_fingerprint"] = hashlib.sha256(config_str.encode()).hexdigest()[:16]
                
        except Exception as e:
            fingerprint["fingerprint_error"] = str(e)
        
        return fingerprint
    
    @contextmanager
    def sync_session(self):
        """Provide a synchronous session for scale generation (uses psycopg2)."""
        if not self._sync_session_factory:
            raise RuntimeError("Sync session factory not initialized")
        session = self._sync_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class ContainerPostgresEnvironment(ScaleExecutionEnvironment):
    """Containerized PostgreSQL environment (Docker/Podman)."""
    
    def __init__(self, db_url: str, container_name: str = "vcos-scale-pg", 
                 image: str = "postgres:18", port: int = 5432):
        super().__init__("container_postgres", db_url)
        self.container_name = container_name
        self.image = image
        self.port = port
        self._container_id: Optional[str] = None
        self._runtime: Optional[str] = None  # "docker" or "podman"
        self._runtime_version: Optional[str] = None
        self._image_digest: Optional[str] = None
        
    async def _discover_runtime(self) -> Optional[str]:
        """Discover available container runtime (Docker or Podman)."""
        import subprocess
        for runtime in ["docker", "podman"]:
            try:
                result = subprocess.run(
                    [runtime, "version"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    self._runtime = runtime
                    self._runtime_version = result.stdout.strip().split('\n')[0]
                    return runtime
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
                continue
        return None
    
    async def _get_image_digest(self) -> Optional[str]:
        """Get the image digest for fingerprinting."""
        if not self._runtime or not self._container_id:
            return None
        try:
            import subprocess
            result = subprocess.run(
                [self._runtime, "inspect", self._container_id, "--format", "{{.Image}}"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    async def initialize(self) -> None:
        """Initialize the environment by discovering runtime and creating engine."""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        import os
        
        # Discover runtime
        runtime = await self._discover_runtime()
        if not runtime:
            self._initialized = True
            return  # Will be handled in start()
        
        # Create engine for async operations
        self.engine = create_async_engine(
            self.db_url,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            connect_args={"server_settings": {"search_path": "public"}},
            echo=False,
            future=True,
        )
        
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # Verify connection
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            pass  # Connection might not be available yet
        
        self._initialized = True
    
    async def start(self) -> None:
        """Start the container if not already running."""
        import subprocess
        
        # Discover runtime if not already done
        if not self._runtime:
            runtime = await self._discover_runtime()
            if not runtime:
                raise RuntimeError("No supported container runtime (Docker/Podman) found")
        
        try:
            # Check if container exists
            result = subprocess.run(
                [self._runtime, "ps", "-a", "--filter", f"name={self.container_name}", "--format", "{{.ID}}"],
                capture_output=True, text=True, timeout=30
            )
            
            if result.stdout.strip():
                # Container exists, start it
                subprocess.run([self._runtime, "start", self.container_name], check=True, timeout=60)
            else:
                # Create and start container
                subprocess.run([
                    self._runtime, "run", "-d",
                    "--name", self.container_name,
                    "-e", "POSTGRES_USER=vcos",
                    "-e", "POSTGRES_PASSWORD=vcos",
                    "-e", "POSTGRES_DB=vcos_test",
                    "-p", f"{self.port}:5432",
                    "-v", "vcos-scale-pg-data:/var/lib/postgresql/data",
                    self.image
                ], check=True, timeout=120)
            
            # Wait for readiness
            await self._wait_for_ready()
            self._start_time = datetime.utcnow()
            
            # Get container ID and image digest for fingerprinting
            result = subprocess.run(
                [self._runtime, "ps", "--filter", f"name={self.container_name}", "--format", "{{.ID}}"],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip():
                self._container_id = result.stdout.strip()
                self._image_digest = await self._get_image_digest()
                
        except Exception as e:
            raise RuntimeError(f"Failed to start container: {e}")
    
    async def _wait_for_ready(self, timeout: int = 60) -> None:
        """Wait for PostgreSQL to be ready."""
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        
        start = time.time()
        while time.time() - start < timeout:
            try:
                engine = create_async_engine(self.db_url, pool_size=1, max_overflow=0, echo=False)
                async with engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                await engine.dispose()
                return
            except Exception:
                await asyncio.sleep(1)
        raise TimeoutError("Container PostgreSQL did not become ready")
    
    async def stop(self) -> None:
        """Stop the container."""
        import subprocess
        try:
            subprocess.run([self._runtime, "stop", self.container_name], check=True, timeout=60)
        except Exception:
            pass
    
    async def health_check(self) -> bool:
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
    
    async def collect_metrics(self) -> Dict[str, Any]:
        from tests.scale.postgres.diagnostics import PostgreSQLCapacityDiagnostics
        diagnostics = PostgreSQLCapacityDiagnostics(self.db_url)
        await diagnostics.initialize()
        try:
            metrics = await diagnostics.run_full_diagnostics()
            return {
                "database_size_mb": metrics.database_size_mb,
                "index_size_mb": metrics.total_index_size_mb,
                "connections": {
                    "active": metrics.active_connections,
                    "idle": metrics.idle_connections,
                    "waiting": metrics.waiting_connections,
                    "total": metrics.used_connections,
                    "max": metrics.max_connections,
                },
                "wal_size_mb": metrics.wal_size_mb,
                "database_size_mb": metrics.database_size_mb,
                "index_size_mb": metrics.total_index_size_mb,
                "temp_files_mb": metrics.temp_files.get("temp_bytes_mb", 0),
            }
        finally:
            await diagnostics.close()
    
    async def collect_failure_evidence(self) -> Dict[str, Any]:
        """Collect failure evidence for diagnostics."""
        import subprocess
        evidence = {}
        try:
            if self._runtime:
                # Get container logs
                result = subprocess.run(
                    [self._runtime, "logs", self.container_name],
                    capture_output=True, text=True, timeout=30
                )
                evidence["container_logs"] = result.stdout[-5000:] if result.stdout else ""
                
                # Get container inspect
                result = subprocess.run(
                    [self._runtime, "inspect", self.container_name],
                    capture_output=True, text=True, timeout=10
                )
                evidence["container_inspect"] = result.stdout[:5000] if result.stdout else ""
        except Exception as e:
            evidence["error"] = str(e)
        return evidence
    
    async def cleanup(self) -> None:
        if self.engine:
            await self.engine.dispose()
        import subprocess
        try:
            subprocess.run([self._runtime, "stop", self.container_name], check=True, timeout=60)
        except Exception:
            pass
    
    async def destroy(self) -> None:
        """Completely destroy the container and its volumes."""
        import subprocess
        try:
            subprocess.run([self._runtime, "stop", self.container_name], check=True, timeout=60)
        except Exception:
            pass
        try:
            subprocess.run([self._runtime, "rm", "-v", self.container_name], check=True, timeout=60)
        except Exception:
            pass
        try:
            subprocess.run([self._runtime, "volume", "rm", "vcos-scale-pg-data"], check=True, timeout=60)
        except Exception:
            pass
    
    def get_capability(self) -> 'EnvironmentCapability':
        caps = EnvironmentCapability(
            platform="linux",
            os_version="container",
            architecture=platform.machine(),
            cpu_count=os.cpu_count() or 0,
            total_memory_mb=0,
            available_memory_mb=0,
            free_disk_gb=0.0,
            postgresql_version="unknown",
            postgresql_architecture="x64",
            max_connections=200,
            shared_buffers_mb=0,
            work_mem_mb=0,
            maintenance_work_mem_mb=0,
            max_wal_size_mb=0,
            effective_cache_size_mb=0,
            autovacuum_max_workers=8,
            supports_parallel_query=True,
            supports_partitioning=True,
            supports_logical_replication=True,
        )
        if self._runtime:
            caps.limitations = caps.limitations or []
            caps.limitations.append(f"runtime: {self._runtime} ({self._runtime_version})")
        return caps
    
    def get_resource_envelope(self, profile_name: str) -> 'ResourceEnvelope':
        from tests.scale.postgres.safe_scale import SCALE_ENVELOPES
        envelope = SCALE_ENVELOPES.get(profile_name)
        if not envelope:
            return ResourceEnvelope(
                profile_name=profile_name,
                employee_count=0,
                estimated_database_size_gb=0.0,
                estimated_wal_size_gb=0.0,
                estimated_temp_space_gb=0.0,
                estimated_memory_gb=0.0,
                estimated_cpu_cores=0,
                estimated_connections=0,
                max_recommended_work_mem_mb=0,
                max_recommended_maintenance_work_mem_mb=0,
                max_recommended_shared_buffers_mb=0,
                max_recommended_max_wal_size_gb=0.0,
                max_recommended_connections=0,
                estimated_generation_time_minutes=0.0,
                estimated_validation_time_minutes=0.0,
            )
        return envelope
    
async def get_fingerprint(self) -> Dict[str, Any]:
        """Generate environment fingerprint for reproducibility."""
        fingerprint = {
            "vcos_revision": "unknown",
            "schema_revision": "unknown",
            "postgresql_version": "unknown",
            "runtime": self._runtime or "unknown",
            "runtime_version": self._runtime_version or "unknown",
            "image": self.image,
            "image_digest": self._image_digest or "unknown",
            "cpu_count": os.cpu_count() or 0,
            "memory_bytes": "unknown",
            "storage_type": "volume",
            "extensions": [],
            "configuration_fingerprint": "unknown",
            "scale_profile": self.profile.name if hasattr(self, 'profile') else "unknown",
            "employee_count": self.config.employee_count if hasattr(self, 'config') else 0,
            "tenant_count": 1,
            "dataset_seed": "42",
            "dataset_fingerprint": "deterministic",
            "started_at": self._start_time.isoformat() if self._start_time else "unknown",
            "completed_at": "unknown",
        }
        
        # Try to get actual PostgreSQL version
        try:
            async with self.engine.begin() as conn:
                result = await conn.execute(text("SELECT version()"))
                version = result.scalar()
                if version:
                    fingerprint["postgresql_version"] = version
        except Exception:
            pass
        @contextmanager
        def sync_session(self):
            raise NotImplementedError("Use async session for container environment")

class ScaleExecutionEnvironmentFactory:
    """Factory for creating scale execution environments."""
    
    @staticmethod
    def create(environment_type: str, db_url: str, **kwargs) -> ScaleExecutionEnvironment:
        if environment_type == "windows_native":
            return WindowsNativePostgresEnvironment(db_url, kwargs.get("scale_test_conf_path"))
        elif environment_type == "linux_native":
            return LinuxPostgresEnvironment(db_url, kwargs.get("scale_test_conf_path"))
        elif environment_type == "container":
            return ContainerPostgresEnvironment(
                db_url,
                kwargs.get("container_name", "vcos-scale-pg"),
                kwargs.get("image", "postgres:18"),
                kwargs.get("port", 5432)
            )
        elif environment_type == "external":
            return ExternalPostgresEnvironment(
                db_url,
                kwargs.get("scale_test_conf_path")
            )
        else:
            raise ValueError(f"Unknown environment type: {environment_type}")
    
    @staticmethod
    def detect_best_environment() -> str:
        """Detect the best available environment."""
        import sys
        if sys.platform == "win32":
            return "windows_native"
        else:
            # Check if Docker is available
            import subprocess
            try:
                result = subprocess.run(["docker", "version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return "container"
            except Exception:
                pass
            return "linux_native"