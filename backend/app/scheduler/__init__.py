"""Scheduler package — recurring background jobs and cadence tiers.

Phase 9.16: the autonomous organization runs on scheduled intelligence.
``app.scheduler`` exposes the full job catalog and tier organization while
``app.workers.scheduler`` owns the asyncio execution loop (kept there so the
API process bootstrap import path is unchanged).
"""

from app.scheduler.recurring_jobs import RECURRING_JOBS
from app.scheduler.scheduler import (  # noqa: F401
    DAILY_JOBS,
    HOURLY_JOBS,
    WEEKLY_JOBS,
    WORKER_REGISTRY,
    interval_for,
    job_names,
    jobs_in_tier,
    scheduler_tasks,
    start_scheduler,
    stop_scheduler,
)

__all__ = [
    "WORKER_REGISTRY",
    "RECURRING_JOBS",
    "HOURLY_JOBS",
    "DAILY_JOBS",
    "WEEKLY_JOBS",
    "start_scheduler",
    "stop_scheduler",
    "scheduler_tasks",
    "job_names",
    "jobs_in_tier",
    "interval_for",
]
