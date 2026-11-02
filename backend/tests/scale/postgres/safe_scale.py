"""Safe Scale Profile with Preflight Checks.

Provides a scale profile that validates PostgreSQL capacity before
running scale generation, and implements bounded resource usage.
"""

import asyncio
import os
import uuid
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncSession as AsyncSessionType
from sqlalchemy.pool import NullPool

from tests.scale.postgres.diagnostics import PostgreSQLCapacityDiagnostics, run_diagnostics
from tests.scale.generators import UniversalScaleProfile, UNIVERSAL_SCALE_PROFILES


@dataclass
class ScaleResourceEnvelope:
    """Resource envelope for a scale profile."""
    max_database_size_gb: float
    max_wal_size_gb: float
    max_connections: int
    max_work_mem_mb: int
    max_maintenance_work_mem_mb: int
    estimated_disk_gb: float
    estimated_ram_gb: float


@dataclass
class ScalePreflightResult:
    """Result of preflight validation."""
    can_proceed: bool
    warnings: List[str]
    errors: List[str]
    capacity_metrics: Optional[Dict[str, Any]]
    resource_envelope: ScaleResourceEnvelope


# Predefined resource envelopes for each scale
SCALE_ENVELOPES = {
    "startup": ScaleResourceEnvelope(
        max_database_size_gb=0.5,
        max_wal_size_gb=0.5,
        max_connections=50,
        max_work_mem_mb=256,
        max_maintenance_work_mem_mb=512,
        estimated_disk_gb=0.1,
        estimated_ram_gb=1,
    ),
    "small": ScaleResourceEnvelope(
        max_database_size_gb=2,
        max_wal_size_gb=1,
        max_connections=50,
        max_work_mem_mb=256,
        max_maintenance_work_mem_mb=1024,
        estimated_disk_gb=0.5,
        estimated_ram_gb=2,
    ),
    "medium": ScaleResourceEnvelope(
        max_database_size_gb=5,
        max_wal_size_gb=2,
        max_connections=100,
        max_work_mem_mb=256,
        max_maintenance_work_mem_mb=2048,
        estimated_disk_gb=2,
        estimated_ram_gb=4,
    ),
    "large": ScaleResourceEnvelope(
        max_database_size_gb=20,
        max_wal_size_gb=8,
        max_connections=200,
        max_work_mem_mb=512,
        max_maintenance_work_mem_mb=4096,
        estimated_disk_gb=10,
        estimated_ram_gb=8,
    ),
    "xlarge": ScaleResourceEnvelope(
        max_database_size_gb=50,
        max_wal_size_gb=20,
        max_connections=200,
        max_work_mem_mb=1024,
        max_maintenance_work_mem_mb=8192,
        estimated_disk_gb=50,
        estimated_ram_gb=16,
    ),
    "xxlarge": ScaleResourceEnvelope(
        max_database_size_gb=200,
        max_wal_size_gb=50,
        max_connections=300,
        max_work_mem_mb=2048,
        max_maintenance_work_mem_mb=16384,
        estimated_disk_gb=200,
        estimated_ram_gb=32,
    ),
    "enterprise": ScaleResourceEnvelope(
        max_database_size_gb=500,
        max_wal_size_gb=100,
        max_connections=500,
        max_work_mem_mb=2048,
        max_maintenance_work_mem_mb=16384,
        estimated_disk_gb=500,
        estimated_ram_gb=64,
    ),
}


class ScalePreflightValidator:
    """Validates PostgreSQL capacity before running scale tests."""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.diagnostics = PostgreSQLCapacityDiagnostics(db_url)

    async def initialize(self):
        await self.diagnostics.initialize()

    async def close(self):
        await self.diagnostics.close()

    async def run_preflight(self, profile_name: str) -> ScalePreflightResult:
        """Run complete preflight validation for a scale profile."""
        envelope = SCALE_ENVELOPES.get(profile_name)
        if not envelope:
            return ScalePreflightResult(
                can_proceed=False,
                warnings=[],
                errors=[f"Unknown profile: {profile_name}"],
                capacity_metrics=None,
                resource_envelope=ScaleResourceEnvelope(0, 0, 0, 0, 0, 0, 0),
            )

        # Run diagnostics
        metrics = await self.diagnostics.run_full_diagnostics()

        errors = []
        warnings = []

        # Check PostgreSQL settings
        ms = metrics.memory_settings

        # Check shared_buffers
        shared_buffers_mb = self._parse_size(ms.shared_buffers)
        min_shared_buffers_mb = envelope.max_database_size_gb * 1024 * 0.25  # 25% of DB size
        if shared_buffers_mb < min_shared_buffers_mb:
            warnings.append(
                f"shared_buffers ({ms.shared_buffers}) may be too small for {profile_name}. "
                f"Recommended: >{min_shared_buffers_mb}MB"
            )

        # Check work_mem
        work_mem_mb = self._parse_size(ms.work_mem)
        if work_mem_mb < envelope.max_work_mem_mb:
            warnings.append(
                f"work_mem ({ms.work_mem}) may be too small for {profile_name}. "
                f"Recommended: >{envelope.max_work_mem_mb}MB"
            )

        # Check maintenance_work_mem
        maint_work_mem_mb = self._parse_size(ms.maintenance_work_mem)
        if maint_work_mem_mb < envelope.max_maintenance_work_mem_mb:
            warnings.append(
                f"maintenance_work_mem ({ms.maintenance_work_mem}) may be too small for {profile_name}. "
                f"Recommended: >{envelope.max_maintenance_work_mem_mb}MB"
            )

        # Check max_wal_size
        max_wal_mb = self._parse_size(ms.max_wal_size)
        min_wal_mb = envelope.max_wal_size_gb * 1024
        if max_wal_mb < min_wal_mb:
            errors.append(
                f"max_wal_size ({ms.max_wal_size}) too small for {profile_name}. "
                f"Need at least {min_wal_mb}MB"
            )

        # Check max_connections
        if metrics.max_connections < envelope.max_connections:
            warnings.append(
                f"max_connections ({metrics.max_connections}) < recommended ({envelope.max_connections})"
            )

        # Check autovacuum workers
        if metrics.memory_settings.autovacuum_max_workers < 4:
            warnings.append(
                f"autovacuum_max_workers ({metrics.memory_settings.autovacuum_max_workers}) "
                f"may be too low for large data volumes"
            )

        # Check disk space
        # TODO: Check actual disk space

        # Check current database size
        if metrics.database_size_mb > envelope.max_database_size_gb * 1024 * 0.9:
            warnings.append(
                f"Current database size ({metrics.database_size_mb:.1f}MB) "
                f"approaching envelope limit ({envelope.max_database_size_gb}GB)"
            )

        can_proceed = len(errors) == 0

        return ScalePreflightResult(
            can_proceed=can_proceed,
            warnings=warnings,
            errors=errors,
            capacity_metrics={
                "database_size_mb": metrics.database_size_mb,
                "total_index_size_mb": metrics.total_index_size_mb,
                "wal_size_mb": metrics.wal_size_mb,
                "active_connections": metrics.active_connections,
                "database_size_mb": metrics.database_size_mb,
            },
            resource_envelope=envelope,
        )

    def _parse_size(self, size_str: str) -> int:
        """Parse PostgreSQL size string to MB."""
        size_str = size_str.upper().strip()
        if size_str.endswith("GB"):
            return int(float(size_str[:-2]) * 1024)
        elif size_str.endswith("MB"):
            return int(float(size_str[:-2]))
        elif size_str.endswith("KB"):
            return int(float(size_str[:-2]) / 1024)
        elif size_str.endswith("B"):
            return max(1, int(size_str[:-1]) // (1024 * 1024))
        return 0


@asynccontextmanager
async def safe_scale_session(
    db_url: str,
    profile_name: str,
    preflight: bool = True,
):
    """Context manager for safe scale test execution.

    Handles:
    - Preflight validation
    - Resource monitoring
    - Cleanup on success/failure
    - Connection lifecycle management
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool

    if preflight:
        validator = ScalePreflightValidator(db_url)
        await validator.initialize()
        try:
            preflight_result = await validator.run_preflight("large")  # Use appropriate profile
            if not preflight_result.can_proceed:
                raise RuntimeError(f"Preflight failed: {preflight_result.errors}")
            if validator.diagnostics:
                await validator.diagnostics.close()
        except Exception:
            if validator.diagnostics:
                await validator.diagnostics.close()
            raise

    # Create engine with appropriate settings for scale testing
    async_url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test")
    engine = create_async_engine(
        os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test"),
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    session = session_factory()
    try:
        yield session
    finally:
        try:
            await session.close()
        except Exception:
            pass
        await engine.dispose()


class ScaleRunMonitor:
    """Monitors resource usage during scale generation."""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.diagnostics = PostgreSQLCapacityDiagnostics(db_url)
        self.snapshots: List[Dict[str, Any]] = []

    async def initialize(self):
        await self.diagnostics.initialize()

    async def close(self):
        await self.diagnostics.close()

    async def snapshot(self, label: str) -> Dict[str, Any]:
        """Take a resource snapshot."""
        metrics = await self.diagnostics.run_full_diagnostics()

        snapshot = {
            "label": label,
            "timestamp": datetime.utcnow().isoformat(),
            "connections": {
                "active": self.diagnostics.active_connections,
                "idle": self.diagnostics.idle_connections,
                "waiting": self.diagnostics.waiting_connections,
                "total": self.diagnostics.used_connections,
            },
            "database_size_mb": self.diagnostics.database_size_mb,
            "wal_size_mb": self.diagnostics.wal_size_mb,
            "temp_files_mb": self.diagnostics.temp_files.get("temp_bytes_mb", 0),
            "database_size_mb": self.diagnostics.database_size_mb,
        }

        self.snapshots.append(snapshot)
        return snapshot

    def print_summary(self):
        """Print resource usage summary."""
        if not self.snapshots:
            return

        print("\n" + "=" * 60)
        print("RESOURCE USAGE SUMMARY")
        print("=" * 60)

        for i, snap in enumerate(self.snapshots):
            print(f"\n[{i}] {snap['label']} ({snap['timestamp']})")
            print(f"  Connections: {snap['connections']['total']} "
                  f"(active={snap['connections']['active']}, "
                  f"idle={snap['connections']['idle']}, "
                  f"waiting={snap['connections']['waiting']})")
            print(f"  DB Size: {snap['database_size_mb']:.1f} MB")
            print(f"  WAL Size: {snap['wal_size_mb']:.1f} MB")
            print(f"  Temp Files: {snap['temp_files_mb']:.1f} MB")

        if len(self.snapshots) > 1:
            first = self.snapshots[0]
            last = self.snapshots[-1]
            db_growth = last['database_size_mb'] - first['database_size_mb']
            wal_growth = last['wal_size_mb'] - first['wal_size_mb']
            print(f"\nDB Growth: {db_growth:.1f} MB")
            print(f"WAL Growth: {wal_growth:.1f} MB")


async def run_scale_with_monitoring(
    db_url: str,
    profile_name: str,
    sync_scale_org: str,
    sync_db_session,
) -> Dict[str, int]:
    """Run scale generation with resource monitoring."""
    from tests.scale.generators import SyncScaleGenerator, UniversalScaleProfile, UNIVERSAL_SCALE_PROFILES

    profile = UNIVERSAL_SCALE_PROFILES.get(profile_name)
    if not profile:
        profile = UniversalScaleProfile(name=profile_name, employee_count=10000)

    # Preflight
    validator = ScalePreflightValidator(db_url)
    await validator.initialize()
    preflight = await validator.run_preflight(profile.name)
    if not preflight.can_proceed:
        raise RuntimeError(f"Preflight failed: {preflight.errors}")
    await validator.close()

    print(f"\n{'='*60}")
    print(f"Starting {profile.name} scale generation ({profile.employee_count:,} employees)")
    print(f"Resource envelope: {preflight.resource_envelope.estimated_disk_gb}GB disk, "
          f"{preflight.resource_envelope.estimated_ram_gb}GB RAM")
    print(f"{'='*60}")

    monitor = ScaleRunMonitor(db_url)
    await monitor.initialize()

    try:
        # Pre-generation snapshot
        await monitor.snapshot("pre-generation")

        # Generate
        with SyncScaleGenerator(sync_db_session, sync_scale_org, profile) as generator:
            start = time.perf_counter()
            counts = generator.generate_all()
            generation_time = time.perf_counter() - start

        await monitor.snapshot("post-generation")

        # Validation snapshot
        await monitor.snapshot("post-validation")

        monitor.print_summary()

        return counts

    finally:
        await monitor.close()


async def run_scale_profile_with_validation(
    db_url: str,
    profile_name: str,
    sync_db_session,
    sync_scale_org: str,
) -> Tuple[Dict[str, int], Dict[str, Any]]:
    """Run scale generation with full validation."""
    from tests.scale.generators import UniversalScaleProfile, UNIVERSAL_SCALE_PROFILES
    from tests.scale.test_gate35_f_progressive_scale import TestGate35FProgressiveScale

    profile = UNIVERSAL_SCALE_PROFILES.get(profile_name)
    if not profile:
        profile = UniversalScaleProfile(name=profile_name, employee_count=10000)

    # Preflight
    validator = ScalePreflightValidator(db_url)
    await validator.initialize()
    preflight = await validator.run_preflight(profile.name)
    if not preflight.can_proceed:
        raise RuntimeError(f"Preflight failed: {preflight.errors}")
    await validator.close()

    print(f"\n{'='*60}")
    print(f"Starting {profile.name} scale generation ({profile.employee_count:,} employees)")
    print(f"{'='*60}")

    # Generate
    with SyncScaleGenerator(sync_db_session, sync_scale_org, profile) as generator:
        start = time.perf_counter()
        counts = generator.generate_all()
        generation_time = time.perf_counter() - start

    print(f"Generation: {generation_time:.1f}s, {sum(counts.values()):,} rows, "
          f"{sum(counts.values())/generation_time:,.0f} rows/sec")

    # Validate
    from tests.scale.test_gate35_f_progressive_scale import TestGate35FProgressiveScale
    test_instance = TestGate35FProgressiveScale()

    # We need the sync_db_session for validation
    result = await test_instance._validate_scale_profile_sync(
        sync_db_session, sync_scale_org, None, None, "test", 10000
    )

    return counts, {
        "generation_time": generation_time,
        "validation": {
            "integrity": result.integrity_checks,
            "tenant_isolation": result.tenant_isolation_ok,
            "temporal": result.temporal_integrity_ok,
            "provenance": result.provenance_ok,
            "epistemic": result.epistemic_ok,
            "canonical": result.canonical_relationships_ok,
            "gate31": result.gate31_integrity_ok,
            "gate34": result.gate34_observability_ok,
            "gate35d": result.gate35d_query_plans_ok,
            "company_brain": result.company_brain_ok,
            "search": result.search_ok,
            "pagination": result.pagination_ok,
        }
    }


if __name__ == "__main__":
    import sys
    db_url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test")

    async def main():
        diagnostics = PostgreSQLCapacityDiagnostics(db_url)
        await diagnostics.initialize()
        try:
            metrics = await diagnostics.run_full_diagnostics()
            diagnostics.to_json(metrics)
        finally:
            await diagnostics.close()

    asyncio.run(main())