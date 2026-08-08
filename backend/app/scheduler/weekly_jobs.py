"""Weekly-tier recurring jobs (deep organizational learning).

Weekly jobs run the expensive, cross-cutting analysis that needs a full week
of signal: pattern mining, lessons learned consolidation, and recommendation
feed refresh. Derived from the authoritative worker registry.
"""

from app.scheduler.recurring_jobs import interval_for, jobs_in_tier

WEEKLY_JOBS: list[str] = jobs_in_tier("weekly")


def interval(name: str) -> int | None:
    return interval_for(name)
