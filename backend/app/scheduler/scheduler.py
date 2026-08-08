"""Scheduler facade (Phase 9.16).

The scheduler runs every registered background worker as an asyncio task in
the API process, each on its own cadence. The authoritative registry and loop
live in ``app.workers.scheduler``; this module is the stable public entry
point and adds tier-aware helpers on top.
"""

from app.scheduler.daily_jobs import DAILY_JOBS, interval as daily_interval  # noqa: F401
from app.scheduler.hourly_jobs import HOURLY_JOBS, interval as hourly_interval  # noqa: F401
from app.scheduler.recurring_jobs import (  # noqa: F401
    RECURRING_JOBS,
    interval_for,
    job_names,
    jobs_in_tier,
)
from app.scheduler.weekly_jobs import WEEKLY_JOBS, interval as weekly_interval  # noqa: F401
from app.workers.scheduler import (
    WORKER_REGISTRY,  # noqa: F401
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
