"""Tests for Scale Environment Readiness."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.scale.readiness import (
    ScaleEnvironmentReadinessAssessor,
    ScaleEnvironmentReadiness,
    ReadinessState,
    ReadinessCheck,
    ReadinessCheckResult,
    assess_scale_readiness,
)


class TestScaleEnvironmentReadiness:
    
    def test_readiness_creation(self):
        readiness = ScaleEnvironmentReadiness(state=ReadinessState.READY)
        assert readiness.state == ReadinessState.READY
        assert readiness.is_ready is True
        assert readiness.is_blocked is False
    
    def test_readiness_blocked(self):
        readiness = ScaleEnvironmentReadiness(state=ReadinessState.BLOCKED)
        assert readiness.is_ready is False
        assert readiness.is_blocked is True
    
    def test_readiness_warning(self):
        readiness = ScaleEnvironmentReadiness(state=ReadinessState.WARNING)
        assert readiness.is_ready is False  # WARNING is not READY
        assert readiness.is_blocked is False
    
    def test_check_result_to_dict(self):
        result = ReadinessCheckResult(
            check=ReadinessCheck.REACHABLE,
            passed=True,
            details={"message": "ok"},
        )
        data = result.to_dict()
        assert data["check"] == "reachable"
        assert data["passed"] is True
        assert data["details"] == {"message": "ok"}


class TestReadinessAssessor:
    
    @pytest.mark.asyncio
    async def test_assessor_initialization(self):
        assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://user:pass@host:5432/db')
        assert assessor.db_url == 'postgresql+asyncpg://user:pass@host:5432/db'
        assert assessor.environment_identifier == 'host:5432/db'
    
    @pytest.mark.asyncio
    async def test_assessor_environment_identifier_extraction(self):
        test_cases = [
            ('postgresql+asyncpg://user:pass@host:5432/db', 'host:5432/db'),
            ('postgresql+asyncpg://user:pass@localhost:5432/testdb', 'localhost:5432/testdb'),
            ('postgresql+asyncpg://user@remote:5432/proddb', 'remote:5432/proddb'),
        ]
        
        for db_url, expected in test_cases:
            assessor = ScaleEnvironmentReadinessAssessor(db_url)
            assert assessor.environment_identifier == expected
    
    @pytest.mark.asyncio
    async def test_mandatory_checks_set(self):
        assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://test')
        
        # Get the actual values from the ReadinessCheck enum
        mandatory = {rc.value for rc in assessor.MANDATORY_CHECKS}
        
        expected = {
            'reachable', 'authenticated', 'version_supported', 'extensions_available',
            'schema_privileges', 'write_capability', 'transaction_capability',
            'connection_capacity', 'safe_isolation', 'explicit_authorization'
        }
        
        assert mandatory == expected
    
    @pytest.mark.asyncio
    async def test_optional_checks_set(self):
        assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://test')
        
        optional = {rc.value for rc in assessor.OPTIONAL_CHECKS}
        
        expected = {
            'copy_capability', 'connection_utilization', 'storage_information',
            'database_size', 'relevant_settings', 'index_capability'
        }
        
        assert optional == expected
    
    @pytest.mark.asyncio
    async def test_minimum_version(self):
        assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://test')
        assert assessor.MIN_POSTGRES_VERSION == (14, 0)
    
    @pytest.mark.asyncio
    async def test_required_extensions(self):
        assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://test')
        required = {'pg_trgm', 'uuid-ossp', 'btree_gin'}
        assert assessor.REQUIRED_EXTENSIONS == required
    
    @pytest.mark.asyncio
    async def test_min_connections(self):
        assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://test')
        assert assessor.MIN_AVAILABLE_CONNECTIONS == 20


class TestReadinessRecommendations:
    
    @pytest.mark.asyncio
    async def test_generate_recommendations_connection_capacity(self):
        assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://test')
        
        readiness = ScaleEnvironmentReadiness(state=ReadinessState.BLOCKED)
        readiness.checks.append(
            ReadinessCheckResult(
                check=ReadinessCheck.CONNECTION_CAPACITY,
                passed=False,
                details={"available_connections": 5, "minimum_required": 20},
            )
        )
        
        recommendations = assessor._generate_recommendations(readiness)
        assert len(recommendations) >= 1
        assert "max_connections" in recommendations[0] or "connections" in recommendations[0].lower()
    
    @pytest.mark.asyncio
    async def test_generate_recommendations_extensions(self):
        assessor = ScaleEnvironmentReadinessAssessor('postgresql+asyncpg://test')
        
        readiness = ScaleEnvironmentReadiness(state=ReadinessState.WARNING)
        readiness.checks.append(
            ReadinessCheckResult(
                check=ReadinessCheck.EXTENSIONS_AVAILABLE,
                passed=False,
                details={"missing": ["pg_trgm", "btree_gin"]},
            )
        )
        
        recommendations = assessor._generate_recommendations(readiness)
        assert len(recommendations) >= 1
        assert "pg_trgm" in recommendations[0] or "btree_gin" in recommendations[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])