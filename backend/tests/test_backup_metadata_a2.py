"""Slice A2 - backup metadata completeness + honest-failure tests.

Premise corrections (Track A A2):
- backup_service must not fabricate mock backup results when pgbackrest is
  unavailable; it has to fail explicitly.
- restore_service must not report simulated restore success either.
- Recovery manifests must record the source database name.
- Recovery evidence identity must come from runtime settings, not constants.
"""

import subprocess
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.models.backup_manifest import BackupKind, RecoveryManifest
from app.services.backup_executor import backup_executor
from app.services.backup_service import backup_service
from app.services.recovery_evidence import recovery_evidence_generator
from app.services.restore_service import restore_service


class TestManifestMetadata:
    def test_recovery_manifest_has_source_database_name(self):
        field = RecoveryManifest.__dataclass_fields__["source_database_name"]
        assert field.default == ""

    @pytest.mark.asyncio
    async def test_executor_database_name_sqlite_fallback(self, db_session):
        name = await backup_executor._get_current_database_name(db_session)
        assert name == "unknown"


class TestNoFabricatedBackupResults:
    @pytest.mark.asyncio
    async def test_missing_pgbackrest_raises(self, monkeypatch):
        def _raise(*args, **kwargs):
            raise FileNotFoundError("pgbackrest")

        monkeypatch.setattr(subprocess, "run", _raise)
        with pytest.raises(RuntimeError, match="not installed"):
            await backup_service._execute_pgbackrest_backup(BackupKind.FULL)

    @pytest.mark.asyncio
    async def test_failed_pgbackrest_raises(self, monkeypatch):
        class _Result:
            returncode = 1
            stdout = ""
            stderr = "boom"

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())
        with pytest.raises(RuntimeError, match="failed"):
            await backup_service._execute_pgbackrest_backup(BackupKind.FULL)

    @pytest.mark.asyncio
    async def test_unparseable_output_raises(self, monkeypatch):
        class _Result:
            returncode = 0
            stdout = "not-json"
            stderr = ""

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())
        with pytest.raises(RuntimeError, match="parsed"):
            await backup_service._execute_pgbackrest_backup(BackupKind.FULL)

    @pytest.mark.asyncio
    async def test_restore_missing_pgbackrest_reports_failure(self, monkeypatch):
        def _raise(*args, **kwargs):
            raise FileNotFoundError("pgbackrest")

        monkeypatch.setattr(subprocess, "run", _raise)
        backup = SimpleNamespace(vault_bucket="vcos-backups")
        result = await restore_service._execute_pgbackrest_restore(backup)
        assert result["success"] is False
        assert "pgbackrest" in result["error"]


class TestEvidenceRuntimeIdentity:
    def test_identity_comes_from_settings(self):
        settings = get_settings()
        identity = recovery_evidence_generator._runtime_identity()
        assert identity["code_revision"] == str(getattr(settings, "APP_VERSION", "unknown"))
        assert identity["environment_identity"].startswith(settings.APP_ENV)
        assert identity["environment_identity"] != "vcos-production-windows"
