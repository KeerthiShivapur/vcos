"""Daily-tier recurring jobs (24h intelligence refresh).

Daily jobs keep intelligence fresh: knowledge problem detection, collaboration
metrics, burnout patterns, expertise evolution, workflow bottlenecks, health
recomputation, and the executive reports. Derived from the authoritative
worker registry.
"""

from app.scheduler.recurring_jobs import interval_for, jobs_in_tier

DAILY_JOBS: list[str] = jobs_in_tier("daily")


def interval(name: str) -> int | None:
    return interval_for(name)
