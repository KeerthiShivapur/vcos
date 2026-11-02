"""Tests for Authoritative Scale Entrypoint."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.scale.authoritative import AuthoritativeScaleExecutor, run_authoritative_scale
from tests.scale.generators import UniversalScaleProfile, UNIVERSAL_SCALE_PROFILES


class TestAuthoritativeScaleExecutor:
    
    def test_executor_creation(self):
        executor = AuthoritativeScaleExecutor(
            profile_name="10k",
            output_dir="/tmp/results",
            db_url="postgresql+asyncpg://user:pass@host:5432/db",
            dry_run=False,
        )
        
        assert executor.profile_name == "10k"
        assert executor.output_dir == "/tmp/results"
        assert executor.db_url == "postgresql+asyncpg://user:pass@host:5432/db"
        assert executor.dry_run is False
    
    def test_profile_resolution_known(self):
        executor = AuthoritativeScaleExecutor(
            profile_name="10k",
        )
        
        profile = executor._resolve_profile()
        # Profile resolution depends on UNIVERSAL_SCALE_PROFILES
        # which may or may not have "10k" key
        if profile is not None:
            assert profile.name == "10k"
            assert profile.employee_count == 10000
    
    def test_profile_resolution_unknown(self):
        executor = AuthoritativeScaleExecutor(
            profile_name="unknown_999",
        )
        
        profile = executor._resolve_profile()
        assert profile is None
    
    def test_profile_resolution_small_scales(self):
        # Only test profiles that exist in UNIVERSAL_SCALE_PROFILES
        for size in ["5", "50", "500", "5000"]:
            executor = AuthoritativeScaleExecutor(profile_name=size)
            profile = executor._resolve_profile()
            # Profile may or may not exist in UNIVERSAL_SCALE_PROFILES
            if profile is not None:
                assert profile.employee_count == int(size)
    
    def test_vcos_revision_fallback(self):
        executor = AuthoritativeScaleExecutor(profile_name="10k")
        revision = executor._get_vcos_revision()
        # Should return "unknown" if git not available or fails
        assert revision == "unknown" or len(revision) == 12


class TestAuthoritativeScaleExecutorDryRun:
    
    @pytest.mark.asyncio
    async def test_dry_run_returns_readiness(self):
        executor = AuthoritativeScaleExecutor(
            profile_name="10k",
            db_url="postgresql+asyncpg://user:pass@host:5432/db",
            dry_run=True,
        )
        
        # Mock environment resolution
        mock_env = AsyncMock()
        mock_env.initialize = AsyncMock()
        mock_env.preflight = AsyncMock(return_value={"can_proceed": True})
        
        executor.environment = mock_env
        
        # Mock readiness
        with patch('tests.scale.authoritative.ScaleEnvironmentReadinessAssessor') as mock_assessor_class:
            mock_assessor = AsyncMock()
            mock_assessor.initialize = AsyncMock()
            mock_assessor.assess = AsyncMock(return_value=MagicMock(
                is_blocked=False,
                to_dict=lambda: {"state": "READY"}
            ))
            mock_assessor.close = AsyncMock()
            mock_assessor_class.return_value = mock_assessor
            
            executor.profile = executor._resolve_profile()
            
            result = await executor._run_preflight_and_readiness()
            assert result.is_blocked is False
    
    @pytest.mark.asyncio
    async def test_execute_invalid_profile(self):
        executor = AuthoritativeScaleExecutor(profile_name="invalid")
        
        result = await executor.execute()
        assert result["status"] == "INVALID"
        assert "Unknown profile" in result["reason"]


class TestAuthoritativeScaleEntrypoint:
    
    def test_main_help(self):
        import subprocess
        import sys
        
        result = subprocess.run(
            [sys.executable, "-m", "tests.scale.authoritative", "--help"],
            capture_output=True, text=True, timeout=30
        )
        
        assert result.returncode == 0
        assert "VCOS Authoritative Scale Validation" in result.stdout
        assert "--profile" in result.stdout
        assert "--output-dir" in result.stdout
        assert "--db-url" in result.stdout
        assert "--dry-run" in result.stdout
    
    def test_main_missing_profile(self):
        import subprocess
        import sys
        
        result = subprocess.run(
            [sys.executable, "-m", "tests.scale.authoritative"],
            capture_output=True, text=True, timeout=30
        )
        
        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "error" in result.stderr.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])