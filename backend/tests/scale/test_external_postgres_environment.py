"""Tests for ExternalPostgresEnvironment."""

import pytest
from tests.scale.postgres.environment import (
    ExternalPostgresEnvironment,
    ScaleExecutionEnvironmentFactory,
    EnvironmentType,
)


class TestExternalPostgresEnvironment:
    
    def test_factory_creates_external_environment(self):
        env = ScaleExecutionEnvironmentFactory.create(
            'external', 
            'postgresql+asyncpg://user:pass@host:5432/db'
        )
        assert isinstance(env, ExternalPostgresEnvironment)
        assert env.name == "external_postgres"
    
    def test_environment_type_enum_has_external(self):
        assert EnvironmentType.EXTERNAL_POSTGRES.value == "external_postgres"
        assert "external_postgres" in [e.value for e in EnvironmentType]
    
    def test_external_env_has_required_methods(self):
        env = ExternalPostgresEnvironment('postgresql+asyncpg://user:pass@host:5432/db')
        
        assert hasattr(env, 'initialize')
        assert hasattr(env, 'start')
        assert hasattr(env, 'stop')
        assert hasattr(env, 'health_check')
        assert hasattr(env, 'collect_metrics')
        assert hasattr(env, 'collect_failure_evidence')
        assert hasattr(env, 'cleanup')
        assert hasattr(env, 'get_capability')
        assert hasattr(env, 'get_resource_envelope')
        assert hasattr(env, 'get_fingerprint')
        assert hasattr(env, 'session')
        assert hasattr(env, 'sync_session')
    
    @pytest.mark.asyncio
    async def test_preflight_checks_connection(self):
        """Test that external environment can validate connectivity."""
        # This would require a real PostgreSQL instance
        # Skipping in unit test - integration test will verify
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])