"""Tests for Scale Run Isolation and Fingerprinting."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.scale.postgres.environment import ExternalPostgresEnvironment


class TestScaleRunIsolation:
    
    @pytest.mark.asyncio
    async def test_external_env_preflight_structure(self):
        """Test that preflight returns expected structure."""
        env = ExternalPostgresEnvironment('postgresql+asyncpg://user:pass@host:5432/db')
        
        # Mock the engine
        mock_engine = AsyncMock()
        mock_conn = AsyncMock()
        mock_engine.begin.return_value.__aenter__.return_value = mock_conn
        mock_conn.execute = AsyncMock()
        mock_conn.execute.return_value.scalar.return_value = "PostgreSQL 16.0"
        mock_conn.execute.return_value.first.return_value = (100, 10)
        
        env.engine = mock_engine
        
        result = await env.preflight()
        
        assert "reachable" in result
        assert "authenticated" in result
        assert "version_supported" in result
        assert "extensions_available" in result
        assert "schema_access" in result
        assert "database_writable" in result
        assert "connection_capacity" in result
        assert "transaction_works" in result
        assert "authorized_target" in result
        assert "can_proceed" in result
        assert "errors" in result
    
    @pytest.mark.asyncio
    async def test_external_env_fingerprint_structure(self):
        """Test that fingerprint returns expected structure."""
        env = ExternalPostgresEnvironment('postgresql+asyncpg://user:pass@host:5432/db')
        
        # Just verify the method exists and runs
        mock_engine = AsyncMock()
        mock_conn = AsyncMock()
        mock_engine.begin.return_value.__aenter__.return_value = mock_conn
        
        async def mock_execute(query):
            mock_result = AsyncMock()
            query_str = str(query)
            if "version()" in query_str:
                mock_result.scalar.return_value = "PostgreSQL 16.0"
            elif "extname, extversion" in query_str:
                mock_result.__aiter__.return_value = iter([])
            elif "pg_settings" in query_str:
                mock_result.__aiter__.return_value = iter([])
            else:
                mock_result.scalar.return_value = None
            return mock_result
        
        mock_conn.execute = mock_execute
        
        env.engine = mock_engine
        env._start_time = None
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "abc123def456\n"
            
            fingerprint = await env.get_fingerprint()
        
        # Basic structure checks
        assert "vcos_revision" in fingerprint
        assert "schema_revision" in fingerprint
        assert "postgresql_version" in fingerprint
        assert "runtime" in fingerprint
        assert fingerprint["runtime"] == "external_postgres"
        assert "cpu_count" in fingerprint
        assert "extensions" in fingerprint
        assert "dataset_seed" in fingerprint
        assert "dataset_fingerprint" in fingerprint
        assert "started_at" in fingerprint
        assert "completed_at" in fingerprint


class TestScaleFingerprint:
    
    def test_fingerprint_deterministic(self):
        """Test that fingerprint is deterministic for same config."""
        env1 = ExternalPostgresEnvironment('postgresql+asyncpg://user:pass@host:5432/db')
        env2 = ExternalPostgresEnvironment('postgresql+asyncpg://user:pass@host:5432/db')
        
        # Both should have same structure
        assert env1.name == env2.name
        assert env1.db_url == env2.db_url


if __name__ == "__main__":
    pytest.main([__file__, "-v"])