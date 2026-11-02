"""Post-DR Regression Sweep — focused regression tests.

Covers the defects found and fixed during the DR.3 post-regression closure
(2026-10-17):

1. Severity comparison normalization for canonical integrity findings.
   IntegritySeverity enum values are lowercase ("critical"); the previous
   ``f.severity == "CRITICAL"`` filters were always False and silently
   disabled critical-finding blocking across restore/DR/deploy paths.
2. Contradiction preservation scan after restore (missing sides, broken and
   ambiguous supersession lineage, invalid status, missing provenance).
3. Longitudinal (35-I) integrity scan after restore (broken chains, hash
   discontinuity, invalid intervals, missing epistemic state, missing
   genesis).
4. Company Brain dependency scan (dangling decision/commitment references).
5. Recovery gate state machine: a failed or blocked gate must never advance
   the recovery state, and activation is impossible from a non-approved
   state (plus the gateless READY_FOR_APPROVAL -> ACTIVATED advance fixed
   during DR.3).
6. Corrupted backup artifact rejection via checksum verification.
"""

import hashlib
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.organization import Organization
from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
from app.models.company_actions import CompanyAction
from app.models.longitudinal import LongitudinalProvenance, CompanyKnowledgeSnapshot
from app.models.backup_manifest import BackupManifest
from app.validation.capability_contract import (
    ValidationResult,
    ValidationCheck,
    ValidationStatus,
)
from app.services.canonical_reality_integrity_service import (
    canonical_reality_integrity_service,
    severity_matches,
    IntegritySeverity,
    IntegrityFindingType,
)
from app.services.post_restore_validator import (
    PostRestoreCanonicalValidator,
    ValidationVerdict,
)
from app.services.recovery_gates import (
    RecoveryReadinessGates,
    RecoveryGate,
    RecoveryGateState,
    GateStatus,
    TransitionAction,
)
from app.services.backup_executor import (
    backup_executor,
    BackupExecutionResult,
    BackupMethod,
)


# =============================================================================
# Fixtures and seeding helpers
# =============================================================================

@pytest_asyncio.fixture(loop_scope="function")
async def sweep_org(pg_db_session: AsyncSession):
    """Create an isolated organization for a single test.

    loop_scope="function" keeps fixture setup/teardown in the same event loop
    as the test. With the default (session) fixture loop scope, teardown ran
    on a different loop than the test's asyncpg connections and silently
    failed, leaving zombie transactions that blocked later tests.

    Cleanup also mirrors the repo conftest pattern: stale rows are removed at
    fixture setup, so residue from a failed run is purged by the next test
    that uses this fixture.
    """
    await _cleanup_sweep_rows(pg_db_session)

    org = Organization(
        id=f"sweep-org-{uuid.uuid4().hex[:8]}",
        name=f"Sweep Org {uuid.uuid4().hex[:8]}",
        slug=f"sweep-org-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    pg_db_session.add(org)
    await pg_db_session.commit()

    yield org

    try:
        await pg_db_session.rollback()
        await _cleanup_sweep_rows(pg_db_session)
    except Exception:
        pass


async def _cleanup_sweep_rows(session: AsyncSession) -> None:
    """Delete all rows belonging to sweep test organizations."""
    org_ids = (
        await session.execute(
            select(Organization.id).where(Organization.id.like("sweep-org-%"))
        )
    ).scalars().all()
    if not org_ids:
        return
    for model in (
        CompanyDecisionContradiction,
        CompanyAction,
        LongitudinalProvenance,
        CompanyKnowledgeSnapshot,
        CompanyDecision,
    ):
        await session.execute(
            delete(model).where(model.organization_id.in_(org_ids))
        )
    await session.execute(delete(Organization).where(Organization.id.in_(org_ids)))
    await session.commit()


async def _seed_decision(session: AsyncSession, org_id: str, suffix: str) -> CompanyDecision:
    decision = CompanyDecision(
        id=f"cd-{uuid.uuid4().hex[:12]}",
        organization_id=org_id,
        decision_id=f"dec-{suffix}",
        kind="strategic",
        title="Regression sweep decision",
        source_event_id=f"evt-{suffix}",
    )
    session.add(decision)
    await session.flush()
    return decision


def _contradiction(org_id: str, decision_id: str, suffix: str, **overrides) -> CompanyDecisionContradiction:
    kwargs = dict(
        id=f"cx-{uuid.uuid4().hex[:12]}",
        organization_id=org_id,
        decision_id=decision_id,
        contradiction_key=f"cx:{decision_id}:{suffix}",
        side_a_json={"claims": ["side-a"], "evidence_ids": []},
        side_b_json={"claims": ["side-b"], "evidence_ids": []},
        status="open",
        source_event_id=f"evt-{suffix}",
    )
    kwargs.update(overrides)
    return CompanyDecisionContradiction(**kwargs)


def _provenance(org_id: str, chain_id: str, sequence: int, current_hash: str, **overrides) -> LongitudinalProvenance:
    now = utcnow()
    kwargs = dict(
        id=f"lp-{uuid.uuid4().hex[:12]}",
        organization_id=org_id,
        chain_id=chain_id,
        sequence=sequence,
        entity_type="CompanyDecision",
        entity_id="dec-sweep",
        current_hash=current_hash,
        effective_from=now,
        recorded_at=now,
        is_genesis=(sequence == 1),
    )
    kwargs.update(overrides)
    return LongitudinalProvenance(**kwargs)


def _snapshot(org_id: str, suffix: str, **overrides) -> CompanyKnowledgeSnapshot:
    now = utcnow()
    kwargs = dict(
        id=f"ks-{uuid.uuid4().hex[:12]}",
        organization_id=org_id,
        claim_id=f"claim-{suffix}",
        claim_type="belief",
        claim_version=1,
        snapshot_at=now,
        valid_from=now,
        epistemic_state="OBSERVED",
        confidence=0.8,
    )
    kwargs.update(overrides)
    return CompanyKnowledgeSnapshot(**kwargs)


def _action(org_id: str, suffix: str, **overrides) -> CompanyAction:
    kwargs = dict(
        id=f"ca-{uuid.uuid4().hex[:12]}",
        organization_id=org_id,
        action_type="task",
        title="Regression sweep action",
        state="proposed",
        fingerprint=f"fp-{suffix}",
    )
    kwargs.update(overrides)
    return CompanyAction(**kwargs)


# =============================================================================
# 1. Severity comparison (the silently-inert filter defect)
# =============================================================================

class _FindingStub:
    def __init__(self, severity):
        self.severity = severity


def test_severity_matches_normalizes_enum_and_string():
    """Lowercase enum severities and plain strings must both match 'CRITICAL'."""
    assert severity_matches(_FindingStub(IntegritySeverity.CRITICAL), "CRITICAL")
    assert severity_matches(_FindingStub(IntegritySeverity.CRITICAL), "critical")
    assert severity_matches(_FindingStub("HIGH"), "HIGH")
    assert not severity_matches(_FindingStub(IntegritySeverity.LOW), "CRITICAL")
    assert not severity_matches(_FindingStub(IntegritySeverity.MEDIUM), "HIGH")


# =============================================================================
# 5. Recovery gate state machine
# =============================================================================

@pytest.mark.asyncio
async def test_failed_gate_prevents_state_advance(pg_db_session):
    """A gate whose validator FAILS must move the context to FAILED, not forward."""
    gates = RecoveryReadinessGates()
    context = gates.create_recovery_context(backup_id="bkp-sweep", organization_id="org-sweep")

    async def failing_validator(db, ctx):
        result = ValidationResult(domain="preflight")
        result.add_check(ValidationCheck(
            name="pitr_capability",
            status=ValidationStatus.FAILED,
            message="PITR capability unavailable",
        ))
        result.determine_overall()
        result.message = "PITR capability unavailable"
        return result

    context.gates["preflight"] = RecoveryGate(
        name="preflight",
        target_state=RecoveryGateState.PREFLIGHTED,
        description="test preflight",
        validator=failing_validator,
    )

    context = await gates.transition(None, context.recovery_id, TransitionAction.PREFLIGHT)

    assert context.current_state == RecoveryGateState.FAILED
    assert context.current_state != RecoveryGateState.PREFLIGHTED
    assert context.error == "PITR capability unavailable"


@pytest.mark.asyncio
async def test_blocked_gate_prevents_state_advance(pg_db_session):
    """A gate whose validator is BLOCKED must move the context to BLOCKED."""
    gates = RecoveryReadinessGates()
    context = gates.create_recovery_context(backup_id="bkp-sweep", organization_id="org-sweep")

    async def blocked_validator(db, ctx):
        result = ValidationResult(domain="preflight")
        result.add_check(ValidationCheck(
            name="wal_archive_health",
            status=ValidationStatus.BLOCKED,
            message="WAL archive unhealthy",
        ))
        result.determine_overall()
        result.message = "WAL archive unhealthy"
        return result

    context.gates["preflight"] = RecoveryGate(
        name="preflight",
        target_state=RecoveryGateState.PREFLIGHTED,
        description="test preflight",
        validator=blocked_validator,
    )

    context = await gates.transition(None, context.recovery_id, TransitionAction.PREFLIGHT)

    assert context.current_state == RecoveryGateState.BLOCKED


@pytest.mark.asyncio
async def test_activation_rejected_before_dependencies_validated(pg_db_session):
    """ACTIVATE from CREATED is an invalid transition and must not advance state."""
    gates = RecoveryReadinessGates()
    context = gates.create_recovery_context(backup_id="bkp-sweep", organization_id="org-sweep")

    with pytest.raises(ValueError, match="Invalid transition"):
        await gates.transition(None, context.recovery_id, TransitionAction.ACTIVATE)

    assert context.current_state == RecoveryGateState.CREATED


@pytest.mark.asyncio
async def test_activation_rejected_without_recorded_approval(pg_db_session):
    """Premise corrected (Track A A4): activation is gated.

    A context pushed straight to READY_FOR_APPROVAL without running the prior
    gates must NOT be marked ACTIVATED - the fail-closed activation gate moves
    it to FAILED instead.
    """
    gates = RecoveryReadinessGates()
    context = gates.create_recovery_context(
        backup_id="bkp-sweep", organization_id="org-sweep", initiated_by="sweep-test"
    )
    context.current_state = RecoveryGateState.READY_FOR_APPROVAL

    context = await gates.transition(None, context.recovery_id, TransitionAction.ACTIVATE)

    assert context.current_state == RecoveryGateState.FAILED
    assert context.current_state != RecoveryGateState.ACTIVATED


@pytest.mark.asyncio
async def test_activation_allowed_after_verified_gates_and_approval(pg_db_session):
    """Activation succeeds exactly when every prior gate passed and approval was recorded."""
    gates = RecoveryReadinessGates()
    context = gates.create_recovery_context(
        backup_id="bkp-sweep", organization_id="org-sweep", initiated_by="sweep-test"
    )

    excluded = {"approval_request", "activation"}
    for name, gate in context.gates.items():
        if name not in excluded:
            gate.status = GateStatus.PASSED
    context.current_state = RecoveryGateState.DEPENDENCIES_VALIDATED

    context = await gates.transition(None, context.recovery_id, TransitionAction.REQUEST_APPROVAL)
    assert context.current_state == RecoveryGateState.READY_FOR_APPROVAL
    assert context.metadata.get("approval_requested_at")
    assert context.metadata.get("approval_requested_by") == "sweep-test"

    context = await gates.transition(None, context.recovery_id, TransitionAction.ACTIVATE)
    assert context.current_state == RecoveryGateState.ACTIVATED
    assert context.metadata.get("activated_at")
    assert context.metadata.get("activated_by") == "sweep-test"


@pytest.mark.asyncio
async def test_approval_rejected_when_prior_gate_unverified(pg_db_session):
    """REQUEST_APPROVAL must fail when any prior gate is not verified."""
    gates = RecoveryReadinessGates()
    context = gates.create_recovery_context(
        backup_id="bkp-sweep", organization_id="org-sweep", initiated_by="sweep-test"
    )

    for name, gate in context.gates.items():
        if name not in {"approval_request", "activation"}:
            gate.status = GateStatus.PASSED
    context.gates["canonical_validate"].status = GateStatus.BLOCKED
    context.current_state = RecoveryGateState.DEPENDENCIES_VALIDATED

    context = await gates.transition(None, context.recovery_id, TransitionAction.REQUEST_APPROVAL)

    assert context.current_state == RecoveryGateState.FAILED
    assert context.metadata.get("approval_requested_at") is None


# =============================================================================
# 6. Corrupted backup rejection
# =============================================================================

@pytest.mark.asyncio
async def test_corrupted_backup_checksum_rejected(tmp_path):
    """A backup artifact whose checksum does not match must be rejected."""
    artifact = tmp_path / "base.tar.gz"
    artifact.write_bytes(b"authentic backup payload")

    good_hash = hashlib.sha256(b"authentic backup payload").hexdigest()

    result = BackupExecutionResult(
        success=True,
        backup_id="bkp-sweep-corrupt",
        backup_method=BackupMethod.PG_BASEBACKUP,
        started_at=utcnow(),
        backup_location=str(artifact),
        checksum_sha256="0" * 64,
    )
    manifest = BackupManifest(backup_format="pg_basebackup", vault_path=str(artifact))

    assert await backup_executor._verify_backup_artifact(None, manifest, result) is False

    result.checksum_sha256 = good_hash
    assert await backup_executor._verify_backup_artifact(None, manifest, result) is True

    artifact.write_bytes(b"tampered payload")
    assert await backup_executor._verify_backup_artifact(None, manifest, result) is False


# =============================================================================
# 2. Contradiction preservation scan
# =============================================================================

@pytest.mark.postgres
@pytest.mark.asyncio
async def test_full_post_restore_phases_verified_on_clean_org(pg_db_session, sweep_org):
    """The previously-broken phases must run end-to-end and pass on clean data.

    Before the fix, 'contradiction' called validate_contradiction_preservation
    with the wrong signature (INCONCLUSIVE) and 'longitudinal' called a
    nonexistent check_longitudinal_integrity (AttributeError -> FAILED), and
    'company_brain' called a nonexistent check_company_brain_dependencies.
    """
    validator = PostRestoreCanonicalValidator()
    report = await validator.validate_restored_database(
        db=pg_db_session,
        organization_id=sweep_org.id,
        restore_id="rst-sweep-clean",
        checks=["contradiction", "longitudinal", "company_brain"],
    )

    assert report.overall_verdict == ValidationVerdict.VERIFIED, [
        (p.phase.value, p.verdict.value, p.message) for p in report.phases
    ]
    assert len(report.phases) == 3


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_contradiction_phase_fails_on_missing_side(pg_db_session, sweep_org):
    decision = await _seed_decision(pg_db_session, sweep_org.id, "missing-side")
    pg_db_session.add(_contradiction(
        sweep_org.id, decision.decision_id, "missing-side", side_b_json={}
    ))
    await pg_db_session.flush()

    findings = await canonical_reality_integrity_service.check_contradiction_integrity(
        db=pg_db_session, organization_id=sweep_org.id
    )
    missing_side = [
        f for f in findings
        if f.finding_type == IntegrityFindingType.CONTRADICTION_MISSING_SIDE
    ]
    assert missing_side, [f.finding_type.value for f in findings]
    assert severity_matches(missing_side[0], "CRITICAL")

    validator = PostRestoreCanonicalValidator()
    phase = await validator._validate_contradiction(pg_db_session, sweep_org.id, 100, None)
    assert phase["verdict"] == ValidationVerdict.FAILED
    assert phase["critical_count"] >= 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_contradiction_scan_flags_broken_and_ambiguous_lineage(pg_db_session, sweep_org):
    decision = await _seed_decision(pg_db_session, sweep_org.id, "lineage")

    # supersedes_id has a real FK, so a "broken" lineage can only be a
    # cross-organization reference. The scanner must still reject it. The
    # contradiction->decision FK is composite (org + decision), so the
    # foreign parent needs a decision in its own organization.
    foreign_org = Organization(
        id=f"sweep-org-{uuid.uuid4().hex[:8]}",
        name="Sweep Foreign Org",
        slug=f"sweep-foreign-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    pg_db_session.add(foreign_org)
    await pg_db_session.flush()

    foreign_decision = await _seed_decision(pg_db_session, foreign_org.id, "lineage-foreign")
    foreign_parent = _contradiction(
        foreign_org.id, foreign_decision.decision_id, "foreign-parent"
    )
    pg_db_session.add(foreign_parent)
    await pg_db_session.flush()

    broken = _contradiction(
        sweep_org.id, decision.decision_id, "broken",
        supersedes_id=foreign_parent.id,
    )
    pg_db_session.add(broken)
    await pg_db_session.flush()

    parent = _contradiction(sweep_org.id, decision.decision_id, "parent")
    pg_db_session.add(parent)
    await pg_db_session.flush()

    child_a = _contradiction(
        sweep_org.id, decision.decision_id, "child-a", supersedes_id=parent.id
    )
    child_b = _contradiction(
        sweep_org.id, decision.decision_id, "child-b", supersedes_id=parent.id
    )
    pg_db_session.add_all([child_a, child_b])
    await pg_db_session.flush()

    findings = await canonical_reality_integrity_service.check_contradiction_integrity(
        db=pg_db_session, organization_id=sweep_org.id
    )

    broken_findings = [
        f for f in findings
        if f.finding_type == IntegrityFindingType.CONTRADICTION_BROKEN_LINEAGE
    ]
    ambiguous_findings = [
        f for f in findings
        if f.finding_type == IntegrityFindingType.CONTRADICTION_AMBIGUOUS_LINEAGE
    ]
    assert len(broken_findings) == 1
    assert severity_matches(broken_findings[0], "CRITICAL")
    assert broken_findings[0].entity_id == broken.id
    assert len(ambiguous_findings) == 1
    assert severity_matches(ambiguous_findings[0], "HIGH")
    assert ambiguous_findings[0].entity_id == parent.id

    validator = PostRestoreCanonicalValidator()
    phase = await validator._validate_contradiction(pg_db_session, sweep_org.id, 100, None)
    assert phase["verdict"] == ValidationVerdict.FAILED


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_contradiction_scan_flags_invalid_status_and_missing_provenance(pg_db_session, sweep_org):
    decision = await _seed_decision(pg_db_session, sweep_org.id, "status")
    pg_db_session.add(_contradiction(
        sweep_org.id, decision.decision_id, "bad-status", status="bogus"
    ))
    pg_db_session.add(_contradiction(
        sweep_org.id, decision.decision_id, "no-provenance", source_event_id=""
    ))
    await pg_db_session.flush()

    findings = await canonical_reality_integrity_service.check_contradiction_integrity(
        db=pg_db_session, organization_id=sweep_org.id
    )
    types = {f.finding_type for f in findings}
    assert IntegrityFindingType.CONTRADICTION_INVALID_STATUS in types
    assert IntegrityFindingType.CONTRADICTION_MISSING_PROVENANCE in types
    for f in findings:
        if f.finding_type in (
            IntegrityFindingType.CONTRADICTION_INVALID_STATUS,
            IntegrityFindingType.CONTRADICTION_MISSING_PROVENANCE,
        ):
            assert severity_matches(f, "HIGH")


# =============================================================================
# 3. Longitudinal integrity scan
# =============================================================================

@pytest.mark.postgres
@pytest.mark.asyncio
async def test_longitudinal_phase_fails_on_broken_chain_and_hash_discontinuity(pg_db_session, sweep_org):
    chain = f"chain-{uuid.uuid4().hex[:8]}"
    pg_db_session.add(_provenance(
        sweep_org.id, chain, 1, "hash-1",
        broken=True, broken_reason="source system lost",
    ))
    pg_db_session.add(_provenance(
        sweep_org.id, chain, 2, "hash-2", previous_hash="wrong-hash",
    ))
    await pg_db_session.flush()

    findings = await canonical_reality_integrity_service.check_longitudinal_integrity(
        db=pg_db_session, organization_id=sweep_org.id
    )
    types = {f.finding_type for f in findings}
    assert IntegrityFindingType.LONGITUDINAL_BROKEN_CHAIN in types
    assert IntegrityFindingType.LONGITUDINAL_HASH_DISCONTINUITY in types

    validator = PostRestoreCanonicalValidator()
    phase = await validator._validate_longitudinal(pg_db_session, sweep_org.id, 100, None)
    assert phase["verdict"] == ValidationVerdict.FAILED
    assert phase["critical_count"] >= 2


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_longitudinal_scan_flags_interval_epistemic_and_genesis(pg_db_session, sweep_org):
    now = utcnow()
    chain = f"chain-{uuid.uuid4().hex[:8]}"
    pg_db_session.add(_provenance(
        sweep_org.id, chain, 3, "hash-3", is_genesis=False,
        effective_from=now,
        effective_to=now - timedelta(hours=1),
    ))
    pg_db_session.add(_snapshot(sweep_org.id, "no-epistemic", epistemic_state=""))
    await pg_db_session.flush()

    findings = await canonical_reality_integrity_service.check_longitudinal_integrity(
        db=pg_db_session, organization_id=sweep_org.id
    )
    types = {f.finding_type for f in findings}
    assert IntegrityFindingType.LONGITUDINAL_INVALID_INTERVAL in types
    assert IntegrityFindingType.LONGITUDINAL_MISSING_EPISTEMIC in types
    assert IntegrityFindingType.LONGITUDINAL_MISSING_GENESIS in types

    interval_findings = [
        f for f in findings
        if f.finding_type == IntegrityFindingType.LONGITUDINAL_INVALID_INTERVAL
    ]
    assert severity_matches(interval_findings[0], "HIGH")

    validator = PostRestoreCanonicalValidator()
    phase = await validator._validate_longitudinal(pg_db_session, sweep_org.id, 100, None)
    assert phase["verdict"] == ValidationVerdict.WARNING
    assert phase["critical_count"] == 0
    assert phase["high_count"] >= 2


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_longitudinal_scan_clean_chain_passes(pg_db_session, sweep_org):
    chain = f"chain-{uuid.uuid4().hex[:8]}"
    pg_db_session.add(_provenance(sweep_org.id, chain, 1, "hash-1"))
    pg_db_session.add(_provenance(
        sweep_org.id, chain, 2, "hash-2", previous_hash="hash-1",
    ))
    await pg_db_session.flush()

    findings = await canonical_reality_integrity_service.check_longitudinal_integrity(
        db=pg_db_session, organization_id=sweep_org.id
    )
    assert findings == []


# =============================================================================
# 4. Company Brain dependency scan
# =============================================================================

@pytest.mark.postgres
@pytest.mark.asyncio
async def test_brain_phase_fails_on_dangling_decision_reference(pg_db_session, sweep_org):
    pg_db_session.add(_action(
        sweep_org.id, "dangling",
        source_company_decision_id="decision-that-was-lost",
    ))
    await pg_db_session.flush()

    findings = await canonical_reality_integrity_service.check_company_brain_dependencies(
        db=pg_db_session, organization_id=sweep_org.id
    )
    dangling = [
        f for f in findings
        if f.finding_type == IntegrityFindingType.BRAIN_DEPENDENCY_DANGLING_DECISION
    ]
    assert dangling
    assert severity_matches(dangling[0], "CRITICAL")

    validator = PostRestoreCanonicalValidator()
    phase = await validator._validate_company_brain(pg_db_session, sweep_org.id, 100, None)
    assert phase["verdict"] == ValidationVerdict.FAILED
    assert phase["critical_count"] >= 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_brain_scan_clean_when_references_intact(pg_db_session, sweep_org):
    decision = await _seed_decision(pg_db_session, sweep_org.id, "brain-clean")
    pg_db_session.add(_action(
        sweep_org.id, "brain-clean",
        source_company_decision_id=decision.decision_id,
    ))
    await pg_db_session.flush()

    findings = await canonical_reality_integrity_service.check_company_brain_dependencies(
        db=pg_db_session, organization_id=sweep_org.id
    )
    assert findings == []
