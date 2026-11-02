"""Run VCOS DR scratch-directory retention (operational guardrail).

Only recognized VCOS scratch entries are ever considered:
  - directories named ``vcos_dr3_restore_YYYYMMDD_HHMMSS``
  - files named ``pg_ctl_vcos_dr3_restore_YYYYMMDD_HHMMSS.log``

Default mode is dry-run. Deletion requires ``--apply``. Names marked with
``canary`` (case-insensitive) are always protected; extra names can be
protected via ``--protect "name1;name2"`` or the ``VCOS_SCRATCH_PROTECTED``
environment variable. Active isolated instances (live ``postmaster.pid``)
are never touched. Every run appends a structured JSON line to the log file.

Usage:
  python scripts/run_scratch_retention.py
  python scripts/run_scratch_retention.py --apply
  python scripts/run_scratch_retention.py --max-age-hours 24 --apply
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.dr_ops_guardrails import (  # noqa: E402
    default_retention_hours,
    execute_retention,
    render_report,
    report_to_dict,
    scan_scratch,
    split_protected,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="VCOS DR scratch retention task")
    parser.add_argument(
        "--base-dir",
        default=tempfile.gettempdir(),
        help="directory containing VCOS scratch entries (default: system temp)",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=None,
        help="minimum age before an entry is a candidate (default: VCOS_SCRATCH_RETENTION_HOURS or 72)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete candidates (default: dry-run)",
    )
    parser.add_argument(
        "--protect",
        default="",
        help="semicolon-separated extra names to protect",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="structured JSON-lines log path (default: <base-dir>/vcos_scratch_retention.log)",
    )
    parser.add_argument("--json", action="store_true", help="also print the report as JSON")
    args = parser.parse_args()

    max_age = args.max_age_hours
    if max_age is None:
        max_age = default_retention_hours()

    report = scan_scratch(
        args.base_dir,
        min_age_hours=max_age,
        protected=split_protected(args.protect),
        dry_run=not args.apply,
    )
    execute_retention(report)

    print(render_report(report))

    log_path = args.log_file or os.path.join(args.base_dir, "vcos_scratch_retention.log")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            record = {"event": "scratch_retention_run"}
            record.update(report_to_dict(report))
            f.write(json.dumps(record) + "\n")
        print(f"Structured log appended: {log_path}")
    except OSError as exc:
        print(f"WARNING: could not append structured log: {exc}")

    if args.json:
        print(json.dumps(report_to_dict(report), indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
