"""Fail-closed contract for the legacy DR simulation harness.

The legacy ``disaster_recovery_service`` is an in-memory simulation used by
tests and demos. It must never report recovery execution/validation as real:

* outside test/development (APP_ENV/VCOS_TEST_MODE) it must fail closed;
* when permitted, results must be explicitly marked ``simulated: True``;
* the deployment contract's DR readiness check must use persisted restore
  state, not the simulation's in-memory dictionary.
"""

import os

import pytest

from app.services.disaster_recovery_service import (
    SIMULATION_DISABLED_ERROR,
    DisasterSeverity,
    DisasterType,
    disaster_recovery_service,
    simulation_permitted,
)


def _force_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("VCOS_TEST_MODE", raising=False)


@pytest.mark.parametrize(
    "app_env,test_mode,expected",
    [
        ("test", None, True),
        ("development", None, True),
        ("production", None, False),
        ("staging", None, False),
        ("production", "1", True),
        ("", None, False),
    ],
)
def test_simulation_permitted_matrix(monkeypatch, app_env, test_mode, expected):
    monkeypatch.setenv("APP_ENV", app_env)
    if test_mode is None:
        monkeypatch.delenv("VCOS_TEST_MODE", raising=False)
    else:
        monkeypatch.setenv("VCOS_TEST_MODE", test_mode)
    assert simulation_permitted() is expected


@pytest.mark.asyncio
async def test_execute_recovery_fails_closed_outside_test_env(monkeypatch, db_session):
    disaster_recovery_service._active_disasters.clear()
    disaster = await disaster_recovery_service.detect_disaster(
        db_session,
        disaster_type=DisasterType.DB_FAILOVER,
        severity=DisasterSeverity.LOW,
        organization_id="org-sim-fail-closed",
        affected_systems=["db"],
        affected_tenants=["org-sim-fail-closed"],
    )
    await disaster_recovery_service.declare_recovery(db_session, disaster.disaster_id)

    _force_production(monkeypatch)
    with pytest.raises(RuntimeError) as exc:
        await disaster_recovery_service.execute_recovery(db_session, disaster.disaster_id)
    assert "refusing to fabricate" in str(exc.value)

    # The disaster must not be marked COMPLETED by a refused simulation.
    from app.services.disaster_recovery_service import DisasterStatus

    assert disaster.status != DisasterStatus.COMPLETED

    # Restore the active disaster so subsequent teardown is clean.
    disaster_recovery_service._active_disasters.clear()


@pytest.mark.asyncio
async def test_validate_recovery_fails_closed_outside_test_env(monkeypatch, db_session):
    disaster_recovery_service._active_disasters.clear()
    disaster = await disaster_recovery_service.detect_disaster(
        db_session,
        disaster_type=DisasterType.DB_FAILOVER,
        severity=DisasterSeverity.LOW,
        organization_id="org-sim-fail-closed-2",
        affected_systems=["db"],
        affected_tenants=["org-sim-fail-closed-2"],
    )

    _force_production(monkeypatch)
    with pytest.raises(RuntimeError) as exc:
        await disaster_recovery_service.validate_recovery(db_session, disaster)
    assert exc.value.args[0] == SIMULATION_DISABLED_ERROR
    disaster_recovery_service._active_disasters.clear()


@pytest.mark.asyncio
async def test_simulated_validation_is_explicitly_marked(db_session):
    disaster_recovery_service._active_disasters.clear()
    disaster = await disaster_recovery_service.detect_disaster(
        db_session,
        disaster_type=DisasterType.DB_FAILOVER,
        severity=DisasterSeverity.LOW,
        organization_id="org-sim-marked",
        affected_systems=["db"],
        affected_tenants=["org-sim-marked"],
    )
    await disaster_recovery_service.declare_recovery(db_session, disaster.disaster_id)

    result = await disaster_recovery_service.execute_recovery(db_session, disaster.disaster_id)

    assert result["simulated"] is True
    validation = result["validation"]
    assert validation["simulated"] is True
    assert "not evidence of real recovery" in validation["message"]
    disaster_recovery_service._active_disasters.clear()


@pytest.mark.asyncio
async def test_dr_readiness_check_uses_persisted_state_not_simulation(db_session):
    """The deployment contract must not depend on the in-memory sim harness."""
    from app.models.backup_manifest import BackupManifest, RestoreOperation
    from app.models.organization import Organization
    from app.services.deployment_contract_service import deployment_contract_service

    # A simulated active disaster must NOT block deployment readiness.
    disaster_recovery_service._active_disasters.clear()
    disaster = await disaster_recovery_service.detect_disaster(
        db_session,
        disaster_type=DisasterType.DB_FAILOVER,
        severity=DisasterSeverity.LOW,
        organization_id="org-contract-sim",
        affected_systems=["db"],
        affected_tenants=["org-contract-sim"],
    )
    ready = await deployment_contract_service._check_dr_readiness(db_session)
    assert ready.passed is True

    # A persisted in-flight restore MUST block deployment readiness.
    org = Organization(name="DR Contract Org", slug="dr-contract-org-sim")
    db_session.add(org)
    await db_session.flush()

    backup = BackupManifest(organization_id=org.id)
    db_session.add(backup)
    await db_session.flush()

    restore = RestoreOperation(
        backup_id=backup.id,
        organization_id=org.id,
        initiated_by="test",
        status="in_progress",
    )
    db_session.add(restore)
    await db_session.flush()

    blocked = await deployment_contract_service._check_dr_readiness(db_session)
    assert blocked.passed is False
    assert "in progress" in blocked.message

    await db_session.rollback()
    disaster_recovery_service._active_disasters.clear()
