"""Tests for DR operational guardrails (disk preflight + scratch retention).

Pure unit tests: no database, no running PostgreSQL required. Filesystem
interactions happen only under pytest tmp_path.
"""

import os
from pathlib import Path

import pytest

from app.services.dr_ops_guardrails import (
    PG_CTL_LOG_RE,
    RUN_DIR_RE,
    DiskSpaceBlocked,
    execute_retention,
    free_space_gb,
    pid_is_alive,
    render_report,
    report_to_dict,
    require_free_space,
    scan_scratch,
)

VALID_DIR = "vcos_dr3_restore_20261017_101203"
VALID_DIR_2 = "vcos_dr3_restore_20250101_000000"
VALID_LOG = "pg_ctl_vcos_dr3_restore_20261017_101203.log"


def _make_dir(base: Path, name: str, age_hours: float, now: float) -> Path:
    target = base / name
    target.mkdir()
    (target / "marker.txt").write_text("x", encoding="utf-8")
    ts = now - age_hours * 3600.0
    os.utime(target, (ts, ts))
    return target


def _make_file(base: Path, name: str, age_hours: float, now: float) -> Path:
    target = base / name
    target.write_text("log", encoding="utf-8")
    ts = now - age_hours * 3600.0
    os.utime(target, (ts, ts))
    return target


class TestPatterns:
    def test_recognizes_strict_scratch_names(self):
        assert RUN_DIR_RE.match(VALID_DIR)
        assert RUN_DIR_RE.match(VALID_DIR_2)
        assert PG_CTL_LOG_RE.match(VALID_LOG)

    def test_rejects_non_scratch_and_traversal_names(self):
        rejected = [
            "vcos_dr3_restore_20261017_1012",
            "vcos_dr3_restore_20261017_101203_extra",
            "vcos_dr3_restore_101203",
            "vcos_dr3_restore_..",
            "..",
            "vcos_dr3_restore_CANARY_20261017",
            "pg_ctl_vcos_dr3_restore_101203.log",
            "pg_ctl_start.log",
        ]
        for name in rejected:
            assert not RUN_DIR_RE.match(name), name
            assert not PG_CTL_LOG_RE.match(name), name


class TestDiskSpacePreflight:
    def test_free_space_is_positive(self, tmp_path):
        assert free_space_gb(str(tmp_path)) > 0

    def test_require_free_space_passes_with_low_threshold(self, tmp_path):
        measured = require_free_space([str(tmp_path)], min_gb=0.0, phase="test")
        assert measured and measured[0][1] > 0

    def test_require_free_space_blocks_with_impossible_threshold(self, tmp_path):
        with pytest.raises(DiskSpaceBlocked) as excinfo:
            require_free_space([str(tmp_path)], min_gb=10_000_000.0, phase="pre-flight")
        assert "pre-flight" in str(excinfo.value)
        assert "insufficient free space" in str(excinfo.value)

    def test_require_free_space_resolves_missing_target(self, tmp_path):
        missing = tmp_path / "does" / "not" / "exist"
        measured = require_free_space([str(missing)], min_gb=0.0)
        assert measured and measured[0][0] == str(missing)


class TestPidLiveness:
    def test_current_process_is_alive(self):
        assert pid_is_alive(os.getpid()) is True

    def test_non_positive_pids_are_not_alive(self):
        assert pid_is_alive(0) is False
        assert pid_is_alive(-5) is False


class TestRetentionScan:
    def test_old_dir_is_candidate_fresh_dir_is_not(self, tmp_path):
        now = 1_800_000_000.0
        old = _make_dir(tmp_path, VALID_DIR, age_hours=100.0, now=now)
        fresh = _make_dir(tmp_path, "vcos_dr3_restore_20261017_120000", age_hours=1.0, now=now)
        unrelated = _make_dir(tmp_path, "random_stuff", age_hours=100.0, now=now)

        report = scan_scratch(
            str(tmp_path), min_age_hours=72.0, now=now, alive_check=lambda p: None
        )

        candidate_names = [c.name for c in report.candidates]
        assert VALID_DIR in candidate_names
        assert fresh.name in report.skipped_fresh
        assert unrelated.name not in candidate_names

    def test_active_instance_is_skipped(self, tmp_path):
        now = 1_800_000_000.0
        active = _make_dir(tmp_path, VALID_DIR, age_hours=100.0, now=now)
        (active / "postmaster.pid").write_text("12345\n", encoding="utf-8")

        report = scan_scratch(
            str(tmp_path), min_age_hours=72.0, now=now, alive_check=lambda p: 12345
        )

        assert [c.name for c in report.candidates] == []
        assert VALID_DIR in report.skipped_active

    def test_canary_names_are_protected(self, tmp_path):
        now = 1_800_000_000.0
        _make_dir(tmp_path, "vcos_dr3_restore_CANARY_20261017", age_hours=500.0, now=now)
        report = scan_scratch(
            str(tmp_path), min_age_hours=72.0, now=now, alive_check=lambda p: None
        )
        assert report.candidates == []

    def test_explicit_protected_name_is_skipped(self, tmp_path):
        now = 1_800_000_000.0
        _make_dir(tmp_path, VALID_DIR_2, age_hours=500.0, now=now)
        report = scan_scratch(
            str(tmp_path),
            min_age_hours=72.0,
            now=now,
            protected={VALID_DIR_2},
            alive_check=lambda p: None,
        )
        assert report.candidates == []
        assert VALID_DIR_2 in report.skipped_protected

    def test_pg_ctl_log_is_candidate(self, tmp_path):
        now = 1_800_000_000.0
        _make_file(tmp_path, VALID_LOG, age_hours=100.0, now=now)
        report = scan_scratch(
            str(tmp_path), min_age_hours=72.0, now=now, alive_check=lambda p: None
        )
        assert [c.name for c in report.candidates] == [VALID_LOG]
        assert report.candidates[0].kind == "pg_ctl_log"


class TestRetentionExecute:
    def test_dry_run_deletes_nothing(self, tmp_path):
        now = 1_800_000_000.0
        old = _make_dir(tmp_path, VALID_DIR, age_hours=100.0, now=now)
        report = scan_scratch(
            str(tmp_path), min_age_hours=72.0, now=now, dry_run=True, alive_check=lambda p: None
        )
        execute_retention(report)
        assert old.exists()
        assert report.deleted == []

    def test_apply_deletes_only_candidates(self, tmp_path):
        now = 1_800_000_000.0
        old_dir = _make_dir(tmp_path, VALID_DIR, age_hours=100.0, now=now)
        old_log = _make_file(tmp_path, VALID_LOG, age_hours=100.0, now=now)
        fresh = _make_dir(tmp_path, "vcos_dr3_restore_20261017_120000", age_hours=1.0, now=now)
        canary = _make_dir(tmp_path, "vcos_dr3_restore_CANARY_20261017", age_hours=500.0, now=now)
        unrelated = _make_dir(tmp_path, "random_stuff", age_hours=500.0, now=now)

        report = scan_scratch(
            str(tmp_path), min_age_hours=72.0, now=now, dry_run=False, alive_check=lambda p: None
        )
        execute_retention(report)

        assert not old_dir.exists()
        assert not old_log.exists()
        assert fresh.exists()
        assert canary.exists()
        assert unrelated.exists()
        assert sorted(report.deleted) == sorted([VALID_DIR, VALID_LOG])
        assert report.failed == []

    def test_report_serialization_and_rendering(self, tmp_path):
        now = 1_800_000_000.0
        _make_dir(tmp_path, VALID_DIR, age_hours=100.0, now=now)
        report = scan_scratch(
            str(tmp_path), min_age_hours=72.0, now=now, alive_check=lambda p: None
        )
        data = report_to_dict(report)
        assert data["counts"]["candidates"] == 1
        assert data["candidates"][0]["name"] == VALID_DIR
        text = render_report(report)
        assert "VCOS scratch retention" in text
        assert VALID_DIR in text
        assert "DRY-RUN" in text
