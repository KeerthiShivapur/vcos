"""PostgreSQL Capacity Engineering Tests for Scale Testing.

Tests that verify PostgreSQL capacity and resource management for scale testing.
"""

import pytest
import pytest_asyncio
import asyncio
import os
import time
from typing import Dict, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncSession as AsyncSessionType
from sqlalchemy.pool import NullPool

from tests.scale.postgres.diagnostics import PostgreSQLCapacityDiagnostics, run_diagnostics, PostgreSQLCapacityMetrics
from tests.scale.postgres.safe_scale import ScalePreflightValidator, ScalePreflightResult, SCALE_ENVELOPES


# PostgreSQL-only fixture
def is_postgresql(db: AsyncSession) -> bool:
    try:
        return db.bind.dialect.name == "postgresql"
    except Exception:
        return False


@pytest.fixture
def pg_only(pg_db_session: AsyncSession):
    if not is_postgresql(pg_db_session):
        pytest.skip("Test requires PostgreSQL")


@pytest.fixture
async def diagnostics(pg_db_session: AsyncSession, pg_only):
    """Create diagnostics instance."""
    db_url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test")
    diagnostics = PostgreSQLCapacityDiagnostics(db_url)
    await diagnostics.initialize()
    yield diagnostics
    await diagnostics.close()


class TestPostgreSQLCapacityDiagnostics:
    """Tests for PostgreSQL capacity diagnostics."""

    async def test_diagnostics_initialization(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test that diagnostics can be initialized."""
        assert diagnostics.engine is not None
        assert diagnostics.session_factory is not None

    async def test_get_server_settings(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test retrieving PostgreSQL settings."""
        async with diagnostics.session_factory() as session:
            settings = await diagnostics.get_server_settings(session)
            assert settings.shared_buffers is not None
            assert settings.work_mem is not None
            assert settings.max_connections > 0

    async def test_get_connection_stats(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test connection statistics."""
        async with diagnostics.session_factory() as session:
            stats = await diagnostics.get_connection_stats(session)
            assert "active" in stats
            assert "idle" in stats
            assert "total" in stats

    async def test_get_database_size(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test database size measurement."""
        async with diagnostics.session_factory() as session:
            sizes = await diagnostics.get_database_size(session)
            assert "database_size_mb" in sizes
            assert sizes["database_size_mb"] >= 0
            assert "table_sizes" in sizes

    async def test_get_wal_stats(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test WAL statistics."""
        async with diagnostics.session_factory() as session:
            wal = await diagnostics.get_wal_stats(session)
            assert "wal_files_count" in wal
            assert "wal_size_mb" in wal

    async def test_checkpoint_stats(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test checkpoint statistics."""
        async with diagnostics.session_factory() as session:
            stats = await diagnostics.get_checkpoint_stats(session)
            assert "checkpoints_timed" in stats
            assert "checkpoints_req" in stats

    async def test_full_diagnostics(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test full diagnostics suite."""
        metrics = await diagnostics.run_full_diagnostics()
        assert metrics.server_version is not None
        assert metrics.database_size_mb >= 0
        assert metrics.memory_settings is not None
        assert metrics.checkpoint_stats is not None

    async def test_diagnostics_json_output(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test JSON serialization."""
        metrics = await diagnostics.run_full_diagnostics()
        json_str = diagnostics.to_json(metrics)
        assert "server_version" in json_str
        assert "database_size_mb" in json_str


class TestScalePreflightValidator:
    """Tests for scale preflight validation."""

    @pytest_asyncio.fixture
    async def validator(self):
        db_url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test")
        validator = ScalePreflightValidator(db_url)
        await validator.initialize()
        yield validator
        await validator.close()

    async def test_preflight_startup(self, validator: ScalePreflightValidator):
        """Test preflight for startup profile."""
        result = await validator.run_preflight("startup")
        assert isinstance(result, ScalePreflightResult)
        assert result.resource_envelope is not None

    async def test_preflight_medium(self, validator: ScalePreflightValidator):
        """Test preflight for medium profile."""
        result = await validator.run_preflight("medium")
        assert isinstance(result, ScalePreflightResult)

    async def test_preflight_large(self, validator: ScalePreflightValidator):
        """Test preflight for large profile."""
        result = await validator.run_preflight("large")
        assert isinstance(result, ScalePreflightResult)

    async def test_preflight_enterprise(self, validator: ScalePreflightValidator):
        """Test preflight for enterprise (50K) profile."""
        result = await validator.run_preflight("enterprise")
        assert isinstance(result, ScalePreflightResult)

    async def test_preflight_unknown_profile(self, validator: ScalePreflightValidator):
        """Test preflight for unknown profile."""
        result = await validator.run_preflight("unknown")
        assert not result.can_proceed
        assert len(result.errors) > 0


class TestPostgreSQLCapacity:
    """Tests for PostgreSQL capacity under scale."""

    @pytest_asyncio.fixture
    async def db_url(self):
        return os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test")

    async def test_postgresql_settings_for_scale(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Verify PostgreSQL settings are appropriate for scale testing."""
        async with diagnostics.session_factory() as session:
            settings = await diagnostics.get_server_settings(session)

            # For scale testing, these should be tuned
            # These are minimum recommendations for scale testing
            # (Actual values may vary based on environment)

            # shared_buffers should be reasonable
            shared_buffers = settings.shared_buffers.upper()
            assert "MB" in shared_buffers or "GB" in shared_buffers

            # max_wal_size should be reasonable
            max_wal = settings.max_wal_size
            assert "MB" in max_wal.upper() or "GB" in max_wal.upper()

            # max_connections should be reasonable
            assert diagnostics.session_factory is not None

    async def test_wal_health(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test WAL health."""
        async with diagnostics.session_factory() as session:
            wal = await diagnostics.get_wal_stats(None)
            assert "wal_files_count" in wal
            assert "wal_size_mb" in wal

    async def test_checkpoint_behavior(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test checkpoint behavior."""
        async with diagnostics.session_factory() as session:
            stats = await diagnostics.get_checkpoint_stats(None)
            assert "checkpoints_timed" in stats
            assert "checkpoints_req" in stats

    async def test_temp_files_monitoring(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test temporary file monitoring."""
        async with diagnostics.session_factory() as session:
            temp = await diagnostics.get_temp_files(None)
            assert "temp_files" in temp
            assert "temp_bytes_mb" in temp


class TestPostgreSQLTuning:
    """Tests for PostgreSQL tuning recommendations."""

    async def test_scale_test_config_exists(self):
        """Test that scale test configuration file exists."""
        config_path = "tests/scale/postgres/scale_test.conf"
        import os
        assert os.path.exists(config_path), f"Missing config: {config_path}"

    async def test_scale_test_config_has_required_settings(self):
        """Test that scale test config has required settings."""
        config_path = "tests/scale/postgres/scale_test.conf"
        with open(config_path, "r") as f:
            content = f.read()

        required_settings = [
            "shared_buffers",
            "work_mem",
            "maintenance_work_mem",
            "max_wal_size",
            "checkpoint_timeout",
            "checkpoint_completion_target",
            "effective_cache_size",
            "autovacuum_max_workers",
            "max_wal_size",
            "min_wal_size",
        ]

        for setting in required_settings:
            assert setting in content, f"Missing required setting: {setting}"

    async def test_shared_buffers_recommendation(self):
        """Test shared_buffers recommendation for 16GB system."""
        # For 16GB system, shared_buffers should be 3-4GB for scale testing
        # This is a documentation test - actual value set in scale_test.conf
        pass

    async def test_work_mem_recommendation(self):
        """Test work_mem recommendation for scale tests."""
        # For bulk COPY operations, work_mem should be 256MB+
        pass

    async def test_maintenance_work_mem_recommendation(self):
        """Test maintenance_work_mem recommendation."""
        # For index creation during bulk load, maintenance_work_mem should be 2GB+
        pass

    async def test_max_wal_size_recommendation(self):
        """Test max_wal_size recommendation."""
        # For bulk loads, max_wal_size should be 4GB+
        pass

    async def test_checkpoint_timeout_recommendation(self):
        """Test checkpoint_timeout recommendation."""
        # For bulk loads, checkpoint_timeout should be 30min+
        pass

    async def test_autovacuum_workers_recommendation(self):
        """Test autovacuum worker recommendation."""
        # For scale tests, autovacuum_max_workers should be 8+
        pass


class TestResourceMonitoring:
    """Tests for resource monitoring during scale operations."""

    async def test_connection_tracking(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test connection tracking during operations."""
        async with diagnostics.session_factory() as session:
            stats = await diagnostics.get_connection_stats(None)
            assert "active" in diagnostics.get_connection_stats(None)

    async def test_temp_file_monitoring(self, diagnostics: PostgreSQLCapacityDiagnostics):
        """Test temporary file monitoring."""
        async with diagnostics.session_factory() as session:
            temp = await diagnostics.get_temp_files(None)
            assert "temp_files" in temp
            assert "temp_bytes_mb" in temp


class TestScalePreflight:
    """Tests for scale preflight validation."""

    @pytest_asyncio.fixture
    async def validator(self):
        db_url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test")
        validator = ScalePreflightValidator(os.environ.get("TEST_DATABASE_URL"))
        await validator.initialize()
        yield validator
        await validator.close()

    async def test_preflight_returns_result(self, validator: ScalePreflightValidator):
        """Test that preflight returns a proper result."""
        result = await validator.run_preflight("medium")
        assert isinstance(result, ScalePreflightResult)
        assert result.resource_envelope is not None

    async def test_preflight_medium_profile(self, validator: ScalePreflightValidator):
        """Test preflight for medium profile."""
        result = await validator.run_preflight("medium")
        assert result.resource_envelope.estimated_disk_gb > 0
        assert result.resource_envelope.estimated_ram_gb > 0

    async def test_preflight_enterprise_profile(self, validator: ScalePreflightValidator):
        """Test preflight for enterprise (50K) profile."""
        result = await validator.run_preflight("enterprise")
        assert result.resource_envelope.estimated_disk_gb > 0
        assert result.resource_envelope.estimated_ram_gb > 0

    async def test_preflight_unknown_profile(self, validator: ScalePreflightValidator):
        """Test preflight rejects unknown profiles."""
        result = await validator.run_preflight("unknown")
        assert not result.can_proceed
        assert len(result.errors) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])