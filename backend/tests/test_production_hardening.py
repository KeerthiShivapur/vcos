"""Go-live production hardening tests (Phase 0).

Covers: production config guard, real readiness probe, email transport
hardening, worker runner lifecycle, AI verifier. Run against real
PostgreSQL with DATABASE_URL/TEST_DATABASE_URL pointed at vcos_test.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

SYNC = {"APP_ENV": "production", "DEBUG": False, "CORS_ORIGINS": "https://app.vcos.example"}
STRONG = "S3cure-production-key-0123456789abcdefghijklmnop"


class TestProductionConfigGuard:
    def test_production_rejects_dev_default_secret(self):
        from app.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(**SYNC, SECRET_KEY="vcos-dev-secret-change-me-in-production-0f8a2b1c")

    def test_production_rejects_short_secret(self):
        from app.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(**SYNC, SECRET_KEY="short")

    def test_production_rejects_debug(self):
        from app.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(APP_ENV="production", SECRET_KEY=STRONG, DEBUG=True,
                     CORS_ORIGINS="https://app.vcos.example")

    def test_production_accepts_strong_config(self):
        from app.core.config import Settings

        settings = Settings(**SYNC, SECRET_KEY=STRONG)
        assert settings.APP_ENV == "production"

    def test_development_still_boots_with_defaults(self):
        from app.core.config import Settings

        settings = Settings(APP_ENV="development", SECRET_KEY="vcos-dev-secret-change-me-in-production-0f8a2b1c")
        assert settings.APP_ENV == "development"


class TestReadinessProbe:
    @pytest.mark.asyncio
    async def test_readiness_reports_real_database(self, monkeypatch):
        import os

        import app.db.database as database_module
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.api.v1.health import readiness

        pg_url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test",
        )
        engine = create_async_engine(pg_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(database_module, "SessionLocal", factory)
        try:
            response = await readiness()
            body = json.loads(response.body)
            assert response.status_code == 200, body
            assert body["status"] == "ok"
            assert body["components"]["database"]["status"] == "ok"
            assert "checked_at" in body
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_readiness_returns_503_when_database_down(self, monkeypatch):
        import app.db.database as database_module
        from app.api.v1.health import readiness

        def broken():
            raise RuntimeError("database unreachable")

        monkeypatch.setattr(database_module, "SessionLocal", broken)
        response = await readiness()
        body = json.loads(response.body)
        assert response.status_code == 503
        assert body["status"] == "failed"
        assert body["components"]["database"]["status"] == "failed"


class TestEmailHardening:
    @pytest.mark.asyncio
    async def test_console_transport_suppresses_body_in_production(self, monkeypatch):
        import app.services.email_service as email_module

        fake_settings = SimpleNamespace(
            APP_ENV="production", EMAIL_TRANSPORT="console", SMTP_HOST=None,
            SMTP_PORT=587, SMTP_USER=None, SMTP_PASSWORD=None, SMTP_FROM="noreply@vcos.io",
        )
        monkeypatch.setattr(email_module, "get_settings", lambda: fake_settings)
        result = await email_module.email_service.send(
            to="user@example.com", subject="Invite", body="secret invite token",
        )
        assert result["delivered"] is False
        assert "body" not in result
        assert "secret invite token" not in json.dumps(result)

    @pytest.mark.asyncio
    async def test_console_transport_keeps_body_in_development(self, monkeypatch):
        import app.services.email_service as email_module

        fake_settings = SimpleNamespace(
            APP_ENV="development", EMAIL_TRANSPORT="console", SMTP_HOST=None,
            SMTP_PORT=587, SMTP_USER=None, SMTP_PASSWORD=None, SMTP_FROM="noreply@vcos.io",
        )
        monkeypatch.setattr(email_module, "get_settings", lambda: fake_settings)
        result = await email_module.email_service.send(
            to="user@example.com", subject="Invite", body="dev body",
        )
        assert result["delivered"] is True
        assert result["body"] == "dev body"


class TestWorkerRunner:
    def test_runner_module_imports(self):
        import app.workers.runner as runner

        assert callable(runner.run_forever)
        assert callable(runner.main)

    @pytest.mark.asyncio
    async def test_run_forever_starts_and_stops_scheduler(self, monkeypatch):
        import app.workers.runner as runner

        calls = {"start": 0, "stop": 0}
        monkeypatch.setattr(runner, "start_scheduler", lambda: calls.__setitem__("start", calls["start"] + 1) or [])
        monkeypatch.setattr(runner, "stop_scheduler", lambda tasks=None: calls.__setitem__("stop", calls["stop"] + 1))

        stop = asyncio.Event()
        stop.set()
        await runner.run_forever(stop)
        assert calls["start"] == 1
        assert calls["stop"] == 1


class TestAIVerifier:
    def test_local_provider_verifies_ok(self):
        from app.verify_ai import verify

        code = asyncio.run(verify(live=False))
        assert code == 0
