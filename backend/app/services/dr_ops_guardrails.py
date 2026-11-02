"""DR operational guardrails: disk-space preflight + scratch-directory retention.

Operational hardening added 2026-10-17 after a real incident: the system drive
reached zero free space, which made DR.3 runs fail (`[Errno 28]` during restore,
`pg_ctl start exit 1`). This module makes that failure class detectable and
manageable. It is operational tooling, not a new engine: it does not touch
canonical reality, recovery gates, or any ratified service.

Guardrails provided:

1. ``require_free_space``  - blocking preflight before expensive backup /
   restore / extraction work; raises ``DiskSpaceBlocked`` with an explicit,
   honest message. Threshold is configurable via ``VCOS_MIN_FREE_SPACE_GB``
   (default 5.0 GB).

2. ``scan_scratch`` / ``execute_retention`` - retention for DR scratch
   directories and per-instance pg_ctl logs created by the isolated-restore
   service. Safety rules:
     * only direct children of the base directory are considered;
     * only names matching the strict VCOS patterns are ever candidates
       (``vcos_dr3_restore_YYYYMMDD_HHMMSS`` and
       ``pg_ctl_vcos_dr3_restore_YYYYMMDD_HHMMSS.log``);
     * symlinks are never followed or deleted;
     * directories with a live ``postmaster.pid`` process are skipped;
     * names flagged as protected (canaries, ``VCOS_SCRATCH_PROTECTED`` env,
       ``--protect`` CLI flag) are skipped;
     * dry-run is the default; every run appends a structured JSON log line.

Nothing outside the recognized patterns is ever deleted; unknown files or
directories are ignored by design.
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

RUN_DIR_RE = re.compile(r"^vcos_dr3_restore_(\d{8})_(\d{6})$")
PG_CTL_LOG_RE = re.compile(r"^pg_ctl_vcos_dr3_restore_(\d{8})_(\d{6})\.log$")

DEFAULT_MIN_FREE_GB = 5.0
DEFAULT_RETENTION_HOURS = 72.0
STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class DiskSpaceBlocked(RuntimeError):
    """Raised when free space is below the configured guardrail threshold."""


# ---------------------------------------------------------------------------
# Disk-space preflight
# ---------------------------------------------------------------------------


def free_space_gb(path: str) -> float:
    """Free space in GB for the volume containing ``path``."""
    usage = shutil.disk_usage(path)
    return usage.free / (1024 ** 3)


def min_free_space_gb() -> float:
    """Configured minimum free space in GB (``VCOS_MIN_FREE_SPACE_GB``)."""
    raw = os.environ.get("VCOS_MIN_FREE_SPACE_GB", "")
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_MIN_FREE_GB
    return value if value > 0 else DEFAULT_MIN_FREE_GB


def _existing_ancestor(path: str) -> Optional[str]:
    current = os.path.abspath(path)
    while current and not os.path.exists(current):
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return current or None


def require_free_space(
    paths: Sequence[str],
    *,
    min_gb: Optional[float] = None,
    phase: str = "",
) -> List[Tuple[str, float]]:
    """Check free space for each path; raise ``DiskSpaceBlocked`` if any is low.

    Paths that do not exist yet are resolved to their nearest existing ancestor
    (the volume that would receive the writes). Returns ``[(path, free_gb)]``.
    """
    threshold = min_gb if min_gb is not None else min_free_space_gb()
    measured: List[Tuple[str, float]] = []
    blocked: List[Tuple[str, float]] = []
    for path in paths:
        probe = _existing_ancestor(path)
        if probe is None:
            continue
        available = free_space_gb(probe)
        measured.append((path, available))
        if available < threshold:
            blocked.append((path, available))
    if blocked:
        detail = "; ".join(f"{p}: {g:.2f} GB free" for p, g in blocked)
        label = f" [{phase}]" if phase else ""
        raise DiskSpaceBlocked(
            f"insufficient free space{label}: minimum {threshold:.2f} GB required, {detail}"
        )
    return measured


# ---------------------------------------------------------------------------
# Process liveness (active isolated instances must never be reaped)
# ---------------------------------------------------------------------------


def pid_is_alive(pid: int) -> bool:
    """True when ``pid`` refers to a live process on this host."""
    if pid <= 0:
        return False
    if os.name == "nt":
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            return bool(ok) and exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:  # pragma: no cover - non-Windows hosts
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_postmaster_pid(data_dir: str) -> Optional[int]:
    pid_file = os.path.join(data_dir, "postmaster.pid")
    try:
        with open(pid_file, "r", encoding="utf-8", errors="replace") as f:
            first = f.readline().strip()
        return int(first)
    except (OSError, ValueError):
        return None


def active_instance_pid(data_dir: str) -> Optional[int]:
    """PID of the PostgreSQL instance running in ``data_dir``, if alive."""
    pid = _read_postmaster_pid(data_dir)
    if pid is None:
        return None
    return pid if pid_is_alive(pid) else None


# ---------------------------------------------------------------------------
# Scratch retention
# ---------------------------------------------------------------------------


@dataclass
class ScratchEntry:
    name: str
    path: str
    kind: str  # "dir" | "pg_ctl_log"
    age_hours: float
    mtime_iso: str


@dataclass
class RetentionReport:
    base_dir: str
    min_age_hours: float
    dry_run: bool
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    scanned: int = 0
    candidates: List[ScratchEntry] = field(default_factory=list)
    skipped_fresh: List[str] = field(default_factory=list)
    skipped_active: List[str] = field(default_factory=list)
    skipped_protected: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    failed: List[Tuple[str, str]] = field(default_factory=list)


def default_retention_hours() -> float:
    raw = os.environ.get("VCOS_SCRATCH_RETENTION_HOURS", "")
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_RETENTION_HOURS
    return value if value >= 0 else DEFAULT_RETENTION_HOURS


def split_protected(raw: str) -> set:
    names = {part.strip() for part in raw.split(";") if part.strip()}
    env = os.environ.get("VCOS_SCRATCH_PROTECTED", "")
    names.update(part.strip() for part in env.split(";") if part.strip())
    return names


def _entry_kind_and_age(
    entry: os.DirEntry, now: float
) -> Optional[Tuple[str, float]]:
    if entry.is_symlink():
        return None
    if entry.is_dir(follow_symlinks=False) and RUN_DIR_RE.match(entry.name):
        kind = "dir"
    elif entry.is_file(follow_symlinks=False) and PG_CTL_LOG_RE.match(entry.name):
        kind = "pg_ctl_log"
    else:
        return None
    try:
        age = (now - entry.stat(follow_symlinks=False).st_mtime) / 3600.0
    except OSError:
        return None
    return kind, age


def scan_scratch(
    base_dir: str,
    *,
    min_age_hours: Optional[float] = None,
    protected: Iterable[str] = (),
    dry_run: bool = True,
    now: Optional[float] = None,
    alive_check: Callable[[str], Optional[int]] = active_instance_pid,
) -> RetentionReport:
    """Scan ``base_dir`` for deletable VCOS scratch entries (never deletes)."""
    threshold = min_age_hours if min_age_hours is not None else default_retention_hours()
    moment = now if now is not None else datetime.now(timezone.utc).timestamp()
    protected_names = set(protected)
    report = RetentionReport(
        base_dir=os.path.abspath(base_dir),
        min_age_hours=threshold,
        dry_run=dry_run,
    )

    try:
        entries = sorted(os.scandir(base_dir), key=lambda e: e.name)
    except OSError:
        return report

    for entry in entries:
        report.scanned += 1
        parsed = _entry_kind_and_age(entry, moment)
        if parsed is None:
            continue
        kind, age = parsed
        if entry.name.lower().find("canary") >= 0 or entry.name in protected_names:
            report.skipped_protected.append(entry.name)
            continue
        if age < threshold:
            report.skipped_fresh.append(entry.name)
            continue
        if kind == "dir" and alive_check(entry.path):
            report.skipped_active.append(entry.name)
            continue
        report.candidates.append(
            ScratchEntry(
                name=entry.name,
                path=entry.path,
                kind=kind,
                age_hours=round(age, 2),
                mtime_iso=datetime.fromtimestamp(
                    entry.stat(follow_symlinks=False).st_mtime, tz=timezone.utc
                ).isoformat(),
            )
        )
    return report


def _is_safe_to_delete(entry: ScratchEntry, base_dir: str) -> bool:
    if os.path.dirname(os.path.abspath(entry.path)) != os.path.abspath(base_dir):
        return False
    if entry.kind == "dir":
        return bool(RUN_DIR_RE.match(entry.name))
    if entry.kind == "pg_ctl_log":
        return bool(PG_CTL_LOG_RE.match(entry.name))
    return False


def execute_retention(report: RetentionReport) -> RetentionReport:
    """Delete the report's candidates when not in dry-run mode."""
    if report.dry_run:
        return report
    for entry in report.candidates:
        if not _is_safe_to_delete(entry, report.base_dir):
            report.failed.append((entry.name, "path safety check failed"))
            continue
        try:
            if entry.kind == "dir":
                shutil.rmtree(entry.path)
            else:
                os.remove(entry.path)
            report.deleted.append(entry.name)
        except OSError as exc:
            report.failed.append((entry.name, str(exc)))
    return report


def report_to_dict(report: RetentionReport) -> Dict:
    return {
        "base_dir": report.base_dir,
        "min_age_hours": report.min_age_hours,
        "dry_run": report.dry_run,
        "generated_at": report.generated_at,
        "scanned": report.scanned,
        "counts": {
            "candidates": len(report.candidates),
            "skipped_fresh": len(report.skipped_fresh),
            "skipped_active": len(report.skipped_active),
            "skipped_protected": len(report.skipped_protected),
            "deleted": len(report.deleted),
            "failed": len(report.failed),
        },
        "candidates": [
            {
                "name": e.name,
                "kind": e.kind,
                "age_hours": e.age_hours,
                "mtime": e.mtime_iso,
            }
            for e in report.candidates
        ],
        "skipped_fresh": report.skipped_fresh,
        "skipped_active": report.skipped_active,
        "skipped_protected": report.skipped_protected,
        "deleted": report.deleted,
        "failed": [{"name": n, "error": err} for n, err in report.failed],
    }


def render_report(report: RetentionReport) -> str:
    mode = "DRY-RUN (nothing deleted)" if report.dry_run else "APPLY"
    lines = [
        f"VCOS scratch retention [{mode}]",
        f"  base dir:                 {report.base_dir}",
        f"  min age:                  {report.min_age_hours:.1f} h",
        f"  entries scanned:          {report.scanned}",
        f"  candidates:               {len(report.candidates)}",
    ]
    for entry in report.candidates:
        lines.append(f"    - {entry.name} ({entry.kind}, {entry.age_hours:.1f} h old)")
    lines.extend(
        [
            f"  skipped (too fresh):      {len(report.skipped_fresh)}",
            f"  skipped (active):         {len(report.skipped_active)}",
            f"  skipped (protected):      {len(report.skipped_protected)}",
            f"  deleted:                  {len(report.deleted)}",
            f"  failed:                   {len(report.failed)}",
        ]
    )
    for name, error in report.failed:
        lines.append(f"    ! {name}: {error}")
    return "\n".join(lines)
