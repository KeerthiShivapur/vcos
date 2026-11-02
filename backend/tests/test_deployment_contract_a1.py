"""Slice A1 - deployment/database environment contract tests."""

import pytest

from app.services.deployment_contract_service import (
    DeploymentCheck,
)
from app.services.deployment_contract_service import (
    deployment_contract_service as service,
)


class TestDatabaseIdentity:
    @pytest.mark.asyncio
    async def test_identity_not_enforced_when_unset(self, db_session, monkeypatch):
        monkeypatch.setattr(service.settings, "EXPECTED_DATABASE_NAME", "")
        result = await service._check_database_identity(db_session)
        assert result.check == DeploymentCheck.DATABASE_IDENTITY
        assert result.passed is True
        assert result.details["enforced"] is False
        assert result.details["current_database"]

    @pytest.mark.asyncio
    async def test_identity_mismatch_fails(self, db_session, monkeypatch):
        monkeypatch.setattr(service.settings, "EXPECTED_DATABASE_NAME", "vcos4-expected")
        result = await service._check_database_identity(db_session)
        assert result.passed is False
        assert result.details["expected_database"] == "vcos4-expected"
        assert "mismatch" in result.message.lower()

    @pytest.mark.asyncio
    async def test_identity_match_passes(self, db_session, monkeypatch):
        current = db_session.get_bind().url.database or ":memory:"
        monkeypatch.setattr(service.settings, "EXPECTED_DATABASE_NAME", current)
        result = await service._check_database_identity(db_session)
        assert result.passed is True
        assert result.details["enforced"] is True
        assert result.details["current_database"] == current

    @pytest.mark.asyncio
    async def test_identity_registered_in_infrastructure_checks(self):
        check_types = [check_type for check_type, _ in service._get_infrastructure_checks()]
        assert DeploymentCheck.DATABASE_IDENTITY in check_types


class TestExtensionsCheck:
    @pytest.mark.asyncio
    async def test_extensions_skipped_on_non_postgresql(self, db_session):
        result = await service._check_extensions(db_session)
        assert result.check == DeploymentCheck.EXTENSIONS
        assert result.passed is True
        assert "skipped" in result.message.lower()
        assert result.details["dialect"] != "postgresql"


class TestSchemaRevisionChecks:
    @pytest.mark.asyncio
    async def test_schema_revision_skipped_on_non_postgresql(self, db_session):
        result = await service._check_schema_version(db_session)
        assert result.passed is True
        assert "skipped" in result.message.lower()

    @pytest.mark.asyncio
    async def test_migration_compatibility_skipped_on_non_postgresql(self, db_session):
        result = await service._check_migration_compatibility(db_session)
        assert result.passed is True
        assert "skipped" in result.message.lower()


class TestConfigurationChecks:
    @pytest.mark.asyncio
    async def test_missing_database_url_fails(self, monkeypatch):
        monkeypatch.setattr(service.settings, "DATABASE_URL", "")
        result = await service._check_environment_variables(None)
        assert result.passed is False
        assert "DATABASE_URL" in result.message

    @pytest.mark.asyncio
    async def test_missing_secret_fails(self, monkeypatch):
        monkeypatch.setattr(service.settings, "SECRET_KEY", "")
        result = await service._check_secrets_presence(None)
        assert result.passed is False
        assert "SECRET_KEY" in result.message

    @pytest.mark.asyncio
    async def test_configuration_present_passes(self):
        env_result = await service._check_environment_variables(None)
        secrets_result = await service._check_secrets_presence(None)
        assert env_result.passed is True
        assert secrets_result.passed is True


class TestReadinessAssembly:
    @pytest.mark.asyncio
    async def test_environment_contract_runs_all_critical_checks(self, db_session):
        results = await service.run_environment_contract_checks(db_session)
        kinds = [result.check for result in results]
        assert DeploymentCheck.DATABASE_CONNECTIVITY in kinds
        assert DeploymentCheck.DATABASE_IDENTITY in kinds
        assert DeploymentCheck.SCHEMA_VERSION in kinds
        assert DeploymentCheck.MIGRATION_COMPATIBILITY in kinds
        assert DeploymentCheck.EXTENSIONS in kinds
        assert DeploymentCheck.ENVIRONMENT_VARIABLES in kinds
        assert DeploymentCheck.SECRETS_PRESENCE in kinds
        assert all(result.passed for result in results)
