"""DR.3 - Production Recovery Baseline Establishment and E2E Disaster Recovery Ratification.

Real end-to-end verification on the Windows production PostgreSQL 18.2 environment:

  Phase 0  Schema convergence via init_db() (create_all + universal indexes + alter migrations)
  Phase 1  Test organization
  Phase 2  Fresh physical backup via ratified BackupExecutor (pg_basebackup)
  Phase 3  Backup verification (artifact checksum via backup_service)
  Phase 4  PITR marker transactions + WAL seal (pg_switch_wal) + archive wait
  Phase 5  WAL archive health + continuity-from-baseline check
  Phase 6  Isolated physical restore on a scratch port (global service instance)
  Phase 7  PITR proof: marker1 (before target) present, marker2 (after target) absent
  Phase 8  Recovery readiness gates: PREFLIGHT -> ... -> ACTIVATED (real validators)
  Phase 9  RPO/RTO measurement from real timestamps
  Phase 10 Evidence generation -> C:/VCOS-Backups/DR3_RECOVERY_BASELINE_EVIDENCE.json

Exit code 0 only if every mandatory check passes with real evidence.
"""

import asyncio
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

BACKEND_DIR = r"D:\vcos1\workspace\vcos\backend"
sys.path.insert(0, BACKEND_DIR)

# --- Environment contract (must be set BEFORE importing app modules) ---
VAULT_DIR = r"C:\VCOS-Backups"
WAL_ARCHIVE_DIR = os.path.join(VAULT_DIR, "wal_archive")
RESULTS_PATH = os.path.join(VAULT_DIR, "DR3_TEST_RESULTS.json")
EVIDENCE_PATH = os.path.join(VAULT_DIR, "DR3_RECOVERY_BASELINE_EVIDENCE.json")
REPO_EVIDENCE_PATH = os.path.join(BACKEND_DIR, "DR3_RECOVERY_BASELINE_EVIDENCE.json")

os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/vcos4"
os.environ["VAULT_BUCKET"] = VAULT_DIR
os.environ["WAL_ARCHIVE_DIR"] = WAL_ARCHIVE_DIR
os.environ.pop("VCOS_TEST_MODE", None)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.timeutils import utcnow
from app.db.database import engine, init_db
from app.models.backup_manifest import BackupKind, BackupManifest, BackupStatus
from app.services.backup_executor import BackupMethod, backup_executor
from app.services.backup_service import backup_service
from app.services.dr_ops_guardrails import (
    DiskSpaceBlocked,
    min_free_space_gb,
    require_free_space,
)
from app.services.isolated_restore import (
    IsolatedRestoreConfig,
    isolated_restore_service,
)
from app.services.recovery_evidence import recovery_evidence_generator
from app.services.recovery_gates import TransitionAction, recovery_readiness_gates
from app.services.rpo_rto_measurement import RecoveryPhase, rpo_rto_service
from app.services.wal_archive_monitor import wal_archive_monitor


GATE_SEQUENCE = [
    TransitionAction.PREFLIGHT,
    TransitionAction.SELECT_BACKUP,
    TransitionAction.VERIFY_BACKUP,
    TransitionAction.INITIALIZE_RESTORE,
    TransitionAction.RESTORE_DATABASE,
    TransitionAction.REPLAY_WAL,
    TransitionAction.VALIDATE_SCHEMA,
    TransitionAction.VALIDATE_CANONICAL,
    TransitionAction.VALIDATE_TENANT,
    TransitionAction.VALIDATE_TEMPORAL,
    TransitionAction.VALIDATE_PROVENANCE,
    TransitionAction.VALIDATE_GOVERNANCE,
    TransitionAction.VALIDATE_LONGITUDINAL,
    TransitionAction.VALIDATE_DEPENDENCIES,
    TransitionAction.REQUEST_APPROVAL,
    TransitionAction.ACTIVATE,
]


def log(msg: str) -> None:
    print(msg, flush=True)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "value"):
        return obj.value
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return str(obj)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _stop_orphaned_isolated_instances() -> None:
    """Stop leftover isolated instances from prior failed/killed runs (idempotency)."""
    pattern = os.path.join(tempfile.gettempdir(), "vcos_dr3_restore_*")
    for data_dir in sorted(glob.glob(pattern)):
        pid_file = os.path.join(data_dir, "postmaster.pid")
        if not os.path.exists(pid_file):
            continue
        try:
            with open(pid_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
            pid = lines[0].strip() if lines else "?"
            port = lines[3].strip() if len(lines) > 3 else "?"
            log(f"  [orphan-cleanup] stopping isolated instance PID {pid} port {port}: {data_dir}")
            pg_ctl = shutil.which("pg_ctl") or r"C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"
            proc = subprocess.run(
                [pg_ctl, "stop", "-D", data_dir, "-m", "fast", "-w", "-t", "60"],
                capture_output=True,
                timeout=120,
            )
            log(f"  [orphan-cleanup] pg_ctl stop exit code: {proc.returncode}")
        except Exception as e:
            log(f"  [orphan-cleanup] WARNING: could not stop {data_dir}: {e}")


async def count_public_tables(db: AsyncSession) -> int:
    result = await db.execute(text(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
    ))
    return int(result.scalar() or 0)


async def column_exists(db: AsyncSession, table: str, column: str) -> bool:
    result = await db.execute(text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column})
    return int(result.scalar() or 0) > 0


async def insert_org(db: AsyncSession, prefix: str) -> Tuple[str, datetime]:
    """Insert a marker organization; returns (id, commit-adjacent timestamp)."""
    org_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
    await db.execute(text("""
        INSERT INTO organizations (id, name, slug, status, timezone, language, currency,
            brand_primary_color, entity_type, created_at, updated_at)
        VALUES (:id, :name, :slug, 'active', 'UTC', 'en', 'USD',
            '#000000', 'standalone', :now, :now)
    """), {
        "id": org_id,
        "name": f"DR3 {prefix} {uuid.uuid4().hex[:8]}",
        "slug": f"{prefix}-{uuid.uuid4().hex[:8]}",
        "now": utcnow(),
    })
    await db.commit()
    ts = (await db.execute(text("SELECT now()"))).scalar()
    return org_id, ts


async def wait_for_archived_segment(segment: str, timeout_sec: int = 240) -> bool:
    """Wait until the given WAL segment file is fully present in the archive."""
    segment_size = 16 * 1024 * 1024
    path = os.path.join(WAL_ARCHIVE_DIR, segment)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if os.path.exists(path) and os.path.getsize(path) == segment_size:
            return True
        await asyncio.sleep(2)
    return os.path.exists(path) and os.path.getsize(path) == segment_size


async def verify_pitr_markers(
    port: int, database: str, marker1: str, marker2: str
) -> Dict[str, Any]:
    """Query the isolated restored database for the PITR marker outcome."""
    iso_engine = create_async_engine(
        f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{port}/{database}",
        pool_pre_ping=True,
    )
    session = async_sessionmaker(iso_engine, expire_on_commit=False)()
    try:
        # Wait for WAL replay to reach the recovery target and promote out of
        # recovery (recovery_target_action = 'promote'); connecting during
        # hot-standby replay would otherwise report in_recovery=True too early.
        deadline = time.time() + 600
        in_recovery = True
        while time.time() < deadline:
            in_recovery = bool(
                (await session.execute(text("SELECT pg_is_in_recovery()"))).scalar()
            )
            if not in_recovery:
                break
            await asyncio.sleep(2)
        m1 = (await session.execute(
            text("SELECT COUNT(*) FROM organizations WHERE id = :id"), {"id": marker1}
        )).scalar()
        m2 = (await session.execute(
            text("SELECT COUNT(*) FROM organizations WHERE id = :id"), {"id": marker2}
        )).scalar()
        last_replay = (await session.execute(text("SELECT pg_last_wal_replay_lsn()"))).scalar()
        return {
            "in_recovery": bool(in_recovery),
            "marker1_present": int(m1 or 0) == 1,
            "marker2_absent": int(m2 or 0) == 0,
            "last_wal_replay_lsn": str(last_replay),
        }
    finally:
        await session.close()
        await iso_engine.dispose()


async def main() -> bool:
    started = utcnow()
    results: Dict[str, Any] = {}
    checks: Dict[str, bool] = {}

    log("=" * 80)
    log("DR.3: PRODUCTION RECOVERY BASELINE ESTABLISHMENT AND E2E DR RATIFICATION")
    log("=" * 80)
    log(f"Started at:        {started.isoformat()}")
    log(f"Production DB:     127.0.0.1:5432/vcos4 (Windows PostgreSQL 18.2)")
    log(f"WAL archive dir:   {WAL_ARCHIVE_DIR}")
    log(f"Vault dir:         {VAULT_DIR}")

    log("\n[pre-flight] Checking for orphaned isolated instances from prior runs...")
    _stop_orphaned_isolated_instances()

    log("\n[pre-flight] Free-space guardrail...")
    min_free_gb = min_free_space_gb()
    try:
        for space_path, space_free in require_free_space(
            [VAULT_DIR, tempfile.gettempdir()], min_gb=min_free_gb, phase="pre-flight"
        ):
            log(f"  {space_path}: {space_free:.2f} GB free (minimum {min_free_gb:.2f} GB)")
        checks["disk_space_preflight"] = True
    except DiskSpaceBlocked as blocked:
        checks["disk_space_preflight"] = False
        results["blocked"] = {"phase": "pre-flight", "reason": str(blocked)}
        log(f"\n[BLOCKED] {blocked}")
        log("Free space, or run the retention task (DR_RUNBOOK.md section 18), then rerun.")
        with open(RESULTS_PATH, "w") as f:
            json.dump(
                {
                    "timestamp": utcnow().isoformat(),
                    "overall_success": False,
                    "blocked": True,
                    "checks": checks,
                    "results": results,
                },
                f,
                indent=2,
                default=_json_default,
            )
        log(f"BLOCKED result saved to: {RESULTS_PATH}")
        await engine.dispose()
        return False

    restore_result = None
    context = None

    async with AsyncSession(engine) as db:
        try:
            # ---------------------------------------------------------------
            # Phase 0: Schema convergence (production mechanism: init_db)
            # ---------------------------------------------------------------
            log("\n=== PHASE 0: Schema Convergence (init_db) ===")
            tables_before = await count_public_tables(db)
            log(f"  Tables before: {tables_before}")
            await init_db()
            tables_after = await count_public_tables(db)
            device_fp_present = await column_exists(db, "sessions", "device_fingerprint")
            results["phase0_schema_convergence"] = {
                "tables_before": tables_before,
                "tables_after": tables_after,
                "device_fingerprint_present": device_fp_present,
            }
            checks["schema_converged"] = True
            log(f"  Tables after:  {tables_after}")
            log(f"  sessions.device_fingerprint present: {device_fp_present}")

            # ---------------------------------------------------------------
            # Phase 1: Test organization
            # ---------------------------------------------------------------
            log("\n=== PHASE 1: Test Organization ===")
            org_id, _ = await insert_org(db, "dr3-test")
            results["test_organization"] = org_id
            log(f"  Organization: {org_id}")

            # ---------------------------------------------------------------
            # Phase 2: Fresh physical backup via ratified BackupExecutor
            # ---------------------------------------------------------------
            log("\n=== PHASE 2: Fresh Base Backup (BackupExecutor, pg_basebackup) ===")
            exec_result = await backup_executor.execute_backup(
                db,
                kind=BackupKind.FULL,
                retention_days=30,
                organization_id=org_id,
                force_method=BackupMethod.PG_BASEBACKUP,
            )
            await db.commit()

            results["fresh_backup"] = {
                "success": exec_result.success,
                "backup_id": exec_result.backup_id,
                "method": exec_result.backup_method.value,
                "size_bytes": exec_result.backup_size_bytes,
                "checksum_sha256": exec_result.checksum_sha256,
                "backup_location": exec_result.backup_location,
                "error": exec_result.error,
                "warnings": exec_result.warnings,
                "execution_log": exec_result.execution_log,
            }
            for line in exec_result.execution_log:
                log(f"  {line}")
            if not exec_result.success:
                raise RuntimeError(f"Fresh backup failed: {exec_result.error}")

            backup_id = exec_result.backup_id
            backup = await db.get(BackupManifest, backup_id)
            checks["fresh_backup_succeeded"] = True
            checks["fresh_backup_manifest_verified"] = backup.status == BackupStatus.VERIFIED
            log(f"  Backup ID:  {backup_id}")
            log(f"  Status:     {backup.status.value}")
            log(f"  Artifact:   {backup.vault_path}")
            log(f"  Size:       {backup.backup_size_bytes} bytes")
            log(f"  Checksum:   {backup.checksum_sha256[:32]}...")
            log(f"  Completed:  {backup.completed_at.isoformat() if backup.completed_at else None}")

            # ---------------------------------------------------------------
            # Phase 3: Backup verification via backup_service (real artifact)
            # ---------------------------------------------------------------
            log("\n=== PHASE 3: Backup Verification (backup_service) ===")
            verification = await backup_service.verify_backup(db, backup_id)
            await db.commit()
            results["backup_verification"] = {
                "verified": bool(verification.verified),
                "errors": list(verification.errors or []),
                "warnings": list(verification.warnings or []),
            }
            checks["backup_verification_passed"] = bool(verification.verified)
            log(f"  Verified: {verification.verified}")
            if verification.errors:
                for err in verification.errors:
                    log(f"  ERROR: {err}")

            # ---------------------------------------------------------------
            # Phase 4: PITR markers + WAL seal + archive wait
            # ---------------------------------------------------------------
            log("\n=== PHASE 4: PITR Markers + WAL Seal + Archive Wait ===")
            marker1_id, t1 = await insert_org(db, "dr3-pitr-marker-1")
            log(f"  Marker1 committed ~ {t1.isoformat()}: {marker1_id}")
            await asyncio.sleep(3)
            marker2_id, t2 = await insert_org(db, "dr3-pitr-marker-2")
            log(f"  Marker2 committed ~ {t2.isoformat()}: {marker2_id}")

            gap = (t2 - t1).total_seconds()
            target_time = t1 + timedelta(seconds=max(1.0, gap / 2.0))
            log(f"  PITR target time:   {target_time.isoformat()}")

            seg_before = (await db.execute(
                text("SELECT pg_walfile_name(pg_current_wal_lsn())")
            )).scalar()
            switch_lsn = (await db.execute(text("SELECT pg_switch_wal()"))).scalar()
            t_switch = utcnow()
            await db.commit()
            log(f"  Sealed segment {seg_before} (switch LSN {switch_lsn})")

            archived = await wait_for_archived_segment(str(seg_before))
            checks["wal_segment_archived"] = archived
            results["wal_seal"] = {
                "segment": str(seg_before),
                "switch_lsn": str(switch_lsn),
                "archived": archived,
            }
            log(f"  Segment archived:   {archived}")
            if not archived:
                raise RuntimeError(f"WAL segment {seg_before} not archived within timeout")

            # ---------------------------------------------------------------
            # Phase 5: WAL archive health + continuity from baseline
            # ---------------------------------------------------------------
            log("\n=== PHASE 5: WAL Archive Health Check ===")
            await wal_archive_monitor.initialize(db)
            wal_report = await wal_archive_monitor.check_health(db)
            wal_dict = wal_report.to_dict()
            results["wal_archive_health"] = wal_dict
            checks["wal_chain_continuous"] = bool(wal_report.continuous_chain_from_baseline)
            checks["wal_archive_not_unhealthy"] = wal_report.overall_state.value != "unhealthy"
            log(f"  Overall state:       {wal_report.overall_state.value}")
            log(f"  Latest segment:      {wal_report.latest_archived_segment}")
            log(f"  Failed archives:     {wal_report.total_failed_count} (new: {wal_report.new_archive_failures})")
            log(f"  Continuous chain:    {wal_report.continuous_chain_from_baseline}")
            log(f"  Archive lag:         {wal_report.archive_lag_minutes:.1f} min")
            if wal_report.alerts:
                for alert in wal_report.alerts:
                    log(f"    [{alert['level']}] {alert['code']}: {alert['message']}")

            # ---------------------------------------------------------------
            # Phase 6: Isolated physical restore (global service instance)
            # ---------------------------------------------------------------
            log("\n=== PHASE 6: Isolated Physical Restore ===")
            try:
                for space_path, space_free in require_free_space(
                    [tempfile.gettempdir(), VAULT_DIR],
                    min_gb=min_free_gb,
                    phase="phase-6-restore",
                ):
                    log(f"  Free space {space_path}: {space_free:.2f} GB")
            except DiskSpaceBlocked as blocked:
                results["blocked"] = {"phase": "phase-6-restore", "reason": str(blocked)}
                log(f"\n[BLOCKED] {blocked}")
                raise RuntimeError(f"BLOCKED before restore: {blocked}") from blocked
            isolated_port = _find_free_port()
            isolated_dir = os.path.join(
                tempfile.gettempdir(), f"vcos_dr3_restore_{started.strftime('%Y%m%d_%H%M%S')}"
            )
            config = IsolatedRestoreConfig(
                backup_id=backup_id,
                target_time=target_time,
                isolated_port=isolated_port,
                isolated_data_dir=isolated_dir,
                cleanup_on_failure=False,
                cleanup_on_success=False,
                validation_database="vcos4",
                validation_organization_id=org_id,
                wal_archive_dir=WAL_ARCHIVE_DIR,
            )
            restore_result = await isolated_restore_service.create_isolated_restore(
                db=db,
                backup_id=backup_id,
                organization_id=org_id,
                target_time=target_time,
                config_override=config,
            )
            await db.commit()

            results["isolated_restore"] = {
                "success": restore_result.success,
                "restore_id": restore_result.restore_id,
                "state": restore_result.state.value,
                "isolated_port": restore_result.isolated_port,
                "isolated_data_dir": restore_result.isolated_data_dir,
                "postgres_pid": restore_result.postgres_pid,
                "validation_database": restore_result.validation_database,
                "canonical_validation_passed": restore_result.canonical_validation_passed,
                "error": restore_result.error,
                "warnings": restore_result.warnings,
                "execution_log": restore_result.execution_log,
            }
            for line in restore_result.execution_log:
                log(f"  {line}")
            checks["isolated_restore_succeeded"] = restore_result.success
            log(f"  Success:            {restore_result.success}")
            log(f"  Isolated port:      {restore_result.isolated_port}")
            log(f"  Data dir:           {restore_result.isolated_data_dir}")
            if restore_result.postgres_pid:
                log(f"  PostgreSQL PID:     {restore_result.postgres_pid}")
            if restore_result.error:
                log(f"  ERROR: {restore_result.error}")
            if not restore_result.success:
                raise RuntimeError(f"Isolated restore failed: {restore_result.error}")

            # ---------------------------------------------------------------
            # Phase 7: PITR proof on the restored database
            # ---------------------------------------------------------------
            log("\n=== PHASE 7: PITR Marker Verification on Restored Database ===")
            pitr_proof = await verify_pitr_markers(
                restore_result.isolated_port,
                "vcos4",
                marker1_id,
                marker2_id,
            )
            results["pitr_marker_verification"] = {
                **pitr_proof,
                "target_time": target_time.isoformat(),
                "marker1": marker1_id,
                "marker2": marker2_id,
            }
            log(f"  In recovery:        {pitr_proof['in_recovery']}")
            log(f"  Marker1 present:    {pitr_proof['marker1_present']} (before target)")
            log(f"  Marker2 absent:     {pitr_proof['marker2_absent']} (after target)")
            log(f"  Last replay LSN:    {pitr_proof['last_wal_replay_lsn']}")
            checks["pitr_target_reached"] = (
                not pitr_proof["in_recovery"]
                and pitr_proof["marker1_present"]
                and pitr_proof["marker2_absent"]
            )
            if not checks["pitr_target_reached"]:
                log("  WARNING: PITR marker verification did not match the expected outcome")
            
            # Record recovery verification facts (truthful readiness inputs) and
            # re-check WAL health so readiness reflects them.
            if restore_result.success and restore_result.canonical_validation_passed:
                wal_archive_monitor.record_restore_test_verified(
                    restore_id=restore_result.restore_id,
                    isolated_port=restore_result.isolated_port,
                )
            if checks["pitr_target_reached"]:
                wal_archive_monitor.record_pitr_test_verified(
                    target_time=target_time.isoformat(),
                    marker1=marker1_id,
                    marker2=marker2_id,
                )
            readiness_report = await wal_archive_monitor.check_health(db)
            results["recovery_readiness"] = readiness_report.to_dict()
            checks["recovery_readiness_ready"] = (
                readiness_report.overall_recovery_readiness == "READY"
            )
            log(f"  Overall recovery readiness: {readiness_report.overall_recovery_readiness}")
            log(
                f"  Readiness inputs: physical_backup={readiness_report.physical_backup_verified}, "
                f"restore_test={readiness_report.restore_test_verified}, "
                f"pitr_test={readiness_report.pitr_test_verified}"
            )

            # ---------------------------------------------------------------
            # Phase 8: Recovery readiness gates
            # ---------------------------------------------------------------
            log("\n=== PHASE 8: Recovery Readiness Gates ===")
            context = recovery_readiness_gates.create_recovery_context(
                backup_id=backup_id,
                organization_id=org_id,
                target_time=target_time,
                initiated_by="dr3_e2e_test",
            )
            context.metadata["restore_id"] = restore_result.restore_id

            gates_started = utcnow()
            gate_log: Dict[str, Any] = {}
            for action in GATE_SEQUENCE:
                context = await recovery_readiness_gates.transition(
                    db, context.recovery_id, action
                )
                gate_name = action.value
                gate = None
                for gname, g in context.gates.items():
                    if g.completed_at and (gate is None or g.completed_at >= gate.completed_at):
                        gate = g
                        gate_name = gname
                gate_status = gate.status.value if gate else "skipped"
                overall_status = None
                if gate is not None and gate.result is not None:
                    overall_status = (
                        gate.result.overall_status.value
                        if gate.result.overall_status is not None else None
                    )
                gate_log[gate_name] = {
                    "action": action.value,
                    "status": gate_status,
                    "overall_status": overall_status,
                    "error": gate.error if gate else None,
                }
                log(
                    f"  {action.value}: -> {context.current_state.value} "
                    f"({gate_name}: {gate_status}, overall={overall_status})"
                )

                if context.current_state.value in ("failed", "blocked", "inconclusive"):
                    log(f"  GATE FAILURE: {context.error}")
                    break

            await db.commit()
            gates_completed = utcnow()
            results["recovery_gates"] = {
                "recovery_id": context.recovery_id,
                "final_state": context.current_state.value,
                "error": context.error,
                "gates": gate_log,
                "approval_requested_at": context.metadata.get("approval_requested_at"),
                "approval_requested_by": context.metadata.get("approval_requested_by"),
                "activated_at": context.metadata.get("activated_at"),
                "activated_by": context.metadata.get("activated_by"),
                "skipped_gates_at_approval": context.metadata.get("skipped_gates_at_approval"),
            }
            checks["gates_activated"] = context.current_state.value == "activated"
            checks["approval_request_recorded"] = bool(
                context.metadata.get("approval_requested_at")
            )
            checks["activation_after_approval"] = bool(
                context.metadata.get("approval_requested_at")
                and context.metadata.get("activated_at")
            )
            log(f"  Final state: {context.current_state.value}")
            log(f"  Approval requested: {context.metadata.get('approval_requested_at')}")
            log(f"  Activated:          {context.metadata.get('activated_at')}")

            # ---------------------------------------------------------------
            # Phase 9: RPO/RTO measurement
            # ---------------------------------------------------------------
            log("\n=== PHASE 9: RPO/RTO Measurement ===")
            rpo_rto_service.start_measurement(
                recovery_id=context.recovery_id,
                disaster_time=t_switch,
                backup_id=backup_id,
                environment="production",
                scale_profile="dr3_baseline",
            )
            rpo_rto_service.record_backup_metadata(backup_id, exec_result.backup_size_bytes)
            rpo_rto_service.record_phase(RecoveryPhase.BACKUP_SELECTED, exec_result.started_at)
            rpo_rto_service.record_phase(RecoveryPhase.BACKUP_VERIFIED, utcnow())
            rpo_rto_service.record_phase(RecoveryPhase.RESTORE_STARTED, restore_result.started_at)
            rpo_rto_service.record_phase(
                RecoveryPhase.RESTORE_COMPLETED, restore_result.completed_at or utcnow()
            )
            rpo_rto_service.record_phase(RecoveryPhase.VALIDATION_STARTED, gates_started)
            rpo_rto_service.record_phase(RecoveryPhase.VALIDATION_COMPLETED, gates_completed)
            rpo_rto_service.record_phase(
                RecoveryPhase.ACTIVATION_AUTHORIZED, context.completed_at or utcnow()
            )
            rpo_rto_service.record_phase(
                RecoveryPhase.ACTIVATED, context.completed_at or utcnow()
            )
            rpo_rto_service.record_latest_recoverable_time(t2)
            measurement = rpo_rto_service.complete_measurement(
                success=checks.get("gates_activated", False),
                validation_results={"gates_final_state": context.current_state.value},
            )
            results["rpo_rto"] = measurement.to_dict()
            rpo_str = f"{measurement.rpo_seconds:.1f}s" if measurement.rpo_seconds is not None else "N/A"
            rto_str = f"{measurement.rto_seconds:.1f}s" if measurement.rto_seconds is not None else "N/A"
            log(f"  RPO: {rpo_str}")
            log(f"  RTO: {rto_str}")
            log(f"  Backup size: {measurement.backup_size_bytes} bytes")

            # ---------------------------------------------------------------
            # Phase 10: Evidence generation
            # ---------------------------------------------------------------
            log("\n=== PHASE 10: Evidence Generation ===")
            canonical_report = context.validation_reports.get("canonical")
            evidence = await recovery_evidence_generator.generate_from_restore(
                db=db,
                recovery_id=context.recovery_id,
                canonical_report=canonical_report,
                restore_result=restore_result,
            )
            rd = evidence.to_dict()
            rd["dr3_test_results"] = results
            evidence_json = json.dumps(rd, indent=2, default=_json_default)
            with open(EVIDENCE_PATH, "w") as f:
                f.write(evidence_json)
            with open(REPO_EVIDENCE_PATH, "w") as f:
                f.write(evidence_json)
            results["evidence"] = {
                "evidence_id": evidence.evidence_id,
                "final_verdict": evidence.final_verdict,
                "path": EVIDENCE_PATH,
                "repo_path": REPO_EVIDENCE_PATH,
            }
            checks["evidence_generated"] = True
            checks["evidence_verified"] = evidence.final_verdict == "VERIFIED"
            log(f"  Evidence ID:    {evidence.evidence_id}")
            log(f"  Final verdict:  {evidence.final_verdict}")
            log(f"  Saved to:       {EVIDENCE_PATH}")
            log(f"  Repo copy:      {REPO_EVIDENCE_PATH}")

        except Exception as e:
            results["error"] = str(e)
            results["traceback"] = traceback.format_exc()
            log("\nFATAL ERROR:")
            traceback.print_exc()
        finally:
            if restore_result and restore_result.postgres_pid:
                log("\nStopping isolated PostgreSQL instance (data dir kept for audit)...")
                await isolated_restore_service.stop_isolated_restore(
                    restore_result.restore_id, remove_data_dir=False
                )

    await engine.dispose()

    # -------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------
    manual_checks = {
        "disk_space_preflight": checks.get("disk_space_preflight", False),
        "fresh_backup_succeeded": checks.get("fresh_backup_succeeded", False),
        "fresh_backup_manifest_verified": checks.get("fresh_backup_manifest_verified", False),
        "backup_verification_passed": checks.get("backup_verification_passed", False),
        "wal_segment_archived": checks.get("wal_segment_archived", False),
        "wal_chain_continuous": checks.get("wal_chain_continuous", False),
        "wal_archive_not_unhealthy": checks.get("wal_archive_not_unhealthy", False),
        "isolated_restore_succeeded": checks.get("isolated_restore_succeeded", False),
        "pitr_target_reached": checks.get("pitr_target_reached", False),
        "gates_activated": checks.get("gates_activated", False),
        "approval_request_recorded": checks.get("approval_request_recorded", False),
        "activation_after_approval": checks.get("activation_after_approval", False),
        "recovery_readiness_ready": checks.get("recovery_readiness_ready", False),
        "evidence_verified": checks.get("evidence_verified", False),
    }
    overall_success = all(manual_checks.values())
    completed = utcnow()

    log("\n" + "=" * 80)
    log("DR.3 TEST SUMMARY")
    log("=" * 80)
    for name, passed in manual_checks.items():
        log(f"  {'PASS' if passed else 'FAIL'}  {name}")
    log(f"Overall success: {overall_success}")
    log(f"Duration:        {(completed - started).total_seconds():.1f}s")

    with open(RESULTS_PATH, "w") as f:
        json.dump(
            {
                "timestamp": completed.isoformat(),
                "overall_success": overall_success,
                "checks": manual_checks,
                "results": results,
            },
            f,
            indent=2,
            default=_json_default,
        )
    log(f"Results saved to: {RESULTS_PATH}")

    if overall_success:
        log("\n[SUCCESS] DR.3 RECOVERY BASELINE ESTABLISHED AND VERIFIED")
    else:
        log("\n[FAILED] DR.3 TEST FAILED")

    return overall_success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
