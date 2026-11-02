"""Truth Center backend contract tests (Phase 0/E).

Verifies the integrity endpoints return REAL scan-derived data on real
PostgreSQL (never fabricated zeros) and that the findings endpoints match
the status summary exactly.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


async def _make_org(session, slug_suffix: str):
    from app.models.organization import Organization

    org = Organization(name=f"Truth Center Test {slug_suffix}", slug=f"tc-test-{slug_suffix}")
    session.add(org)
    await session.flush()
    return org


class TestIntegrityStatus:
    async def test_status_is_real_scan_never_fabricated(self, pg_db_session):
        from app.api.v1.canonical_integrity import get_integrity_status

        org = await _make_org(pg_db_session, "status")
        user = SimpleNamespace(organization_id=org.id, id="tc-test-user")

        status = await get_integrity_status(db=pg_db_session, current_user=user)

        assert status["organization_id"] == org.id
        assert status["last_scan"] is not None
        assert status["total_findings"] == sum(status["by_severity"].values())
        assert status["total_findings"] == sum(status["by_type"].values())
        assert status["open_findings"] <= status["total_findings"]
        assert "coverage_note" in status
        assert "no cached or fabricated status" in status["coverage_note"]

    async def test_findings_match_status_and_are_filterable(self, pg_db_session):
        from app.api.v1.canonical_integrity import (
            get_integrity_status,
            list_integrity_findings,
        )

        org = await _make_org(pg_db_session, "findings")
        user = SimpleNamespace(organization_id=org.id, id="tc-test-user")

        status = await get_integrity_status(db=pg_db_session, current_user=user)
        findings = await list_integrity_findings(
            db=pg_db_session, current_user=user,
            status=None, severity=None, finding_type=None, entity_type=None,
            limit=1000, offset=0,
        )
        assert len(findings) == status["total_findings"]
        for finding in findings:
            assert finding.severity in ("critical", "high", "medium", "low", "info")
            assert finding.organization_id == org.id

        if status["by_severity"]["critical"]:
            critical = await list_integrity_findings(
                db=pg_db_session, current_user=user,
                status=None, severity="critical", finding_type=None, entity_type=None,
                limit=1000, offset=0,
            )
            assert len(critical) == status["by_severity"]["critical"]
            assert all(f.severity == "critical" for f in critical)

    async def test_get_missing_finding_returns_404(self, pg_db_session):
        from app.api.v1.canonical_integrity import get_integrity_finding

        org = await _make_org(pg_db_session, "missing")
        user = SimpleNamespace(organization_id=org.id, id="tc-test-user")

        with pytest.raises(HTTPException) as exc:
            await get_integrity_finding(
                finding_id="does-not-exist", db=pg_db_session, current_user=user,
            )
        assert exc.value.status_code == 404
