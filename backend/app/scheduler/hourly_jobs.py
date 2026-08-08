"""Hourly-tier recurring jobs (fast cadence, high frequency).

These jobs keep the organization's live state truthful minute-to-minute:
event dispatch, presence, meetings, collaboration sessions, reminders and
dependency/risk re-checks. Deriving from the registry guarantees the tier
lists always match what the scheduler actually runs.
"""

from app.scheduler.recurring_jobs import interval_for, jobs_in_tier

HOURLY_JOBS: list[str] = jobs_in_tier("hourly")


def interval(name: str) -> int | None:
    return interval_for(name)
