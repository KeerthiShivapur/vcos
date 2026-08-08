"""Recurring background jobs — the tiered catalog the scheduler runs.

Every job is a ``{name, interval_seconds, tier}`` record. The tiers map to
organizational cadence (Phase 9.2 / 9.16):

    hourly  — event dispatch, presence, graph, collaboration, risk
    daily   — knowledge intelligence, burnout, expertise evolution, briefs
    weekly  — pattern mining, lessons learned, recommendation feeds

``RECURRING_JOBS`` is derived from the authoritative ``WORKER_REGISTRY`` in
``app.workers.scheduler`` so the two can never drift apart. Tier labels are
assigned by interval, with explicit overrides for workers whose semantic
cadence differs from their raw seconds (e.g. ``insights`` runs daily).
"""

from app.workers.scheduler import WORKER_REGISTRY

# Workers whose tier label differs from their interval-derived tier.
_TIER_OVERRIDES: dict[str, str] = {
    "insights": "daily",        # runs every 24h but represents the daily brief
    "recommendation_feed": "daily",  # daily personalized feeds
    "pattern": "weekly",        # pattern mining happens weekly
    "learning": "weekly",       # lessons learned consolidate weekly
    "graph": "daily",           # structural validation runs daily
    "audit": "daily",           # audit maintenance is daily
    "analytics": "daily",       # materialization is daily
}

_HOURLY_TIERS = {"hourly", "daily", "weekly"}


def _tier_for(name: str, interval_seconds: int) -> str:
    if name in _TIER_OVERRIDES:
        return _TIER_OVERRIDES[name]
    if interval_seconds < 3600:
        return "hourly"
    if interval_seconds < 86400:
        return "daily"
    return "weekly"


RECURRING_JOBS: list[dict[str, object]] = [
    {
        "name": name,
        "interval_seconds": interval_seconds,
        "tier": _tier_for(name, interval_seconds),
    }
    for name, interval_seconds in WORKER_REGISTRY
]


def jobs_in_tier(tier: str) -> list[str]:
    """Names of the jobs belonging to a cadence tier (hourly | daily | weekly)."""
    return [job["name"] for job in RECURRING_JOBS if job["tier"] == tier]


def job_names() -> list[str]:
    return [job["name"] for job in RECURRING_JOBS]


def interval_for(name: str) -> int | None:
    for job in RECURRING_JOBS:
        if job["name"] == name:
            return int(job["interval_seconds"])
    return None
