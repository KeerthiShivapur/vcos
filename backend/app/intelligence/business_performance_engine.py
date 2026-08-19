"""Slice 4G.6 — Commercial & Business Performance Intelligence engine.

The business-performance layer of the Living Company Model: the canonical
metrics that matter, the observations that ground them, the targets the
company commits to, the forecasts that bound expectations, the drivers that
move things, and the multidimensional performance snapshots that tie it all
to strategy (4G.3), capacity/demand (4G.4), customer intelligence (4G.5),
execution (4G.1), coordination (4G.2), knowledge (4E) and learning (4E.7).

Deterministic and universal: one canonical engine for every company size
(5 to 50,000+ people) with org-wide / business-unit / project scopes —
never a separate model per size. Every write is an exact-once, change-driven
reaction to a durable business event; every read is bounded; every connection
is stated in deterministic language (linked to / strongly associated with /
evidence indicates / likely contributor) with its evidence — never invented
certainty. The engine is advisory-only: it writes only its own tables,
never business data, projects, people or capacity.
"""

import asyncio
import math
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Optional, Sequence

from sqlalchemy import func, select

from app.core.timeutils import ensure_aware, utcnow
from app.models.business_performance import (
    BusinessDriver,
    BusinessForecast,
    BusinessMetric,
    BusinessMetricObservation,
    BusinessPerformanceHistory,
    BusinessPerformanceLink,
    BusinessPerformanceSnapshot,
    BusinessTarget,
    COMPUTE_MODES,
    DRIVER_DIRECTIONS,
    DRIVER_STRENGTHS,
    DRIVER_TYPES,
    FORECAST_TYPES,
    HEALTH_DIMENSIONS,
    HEALTH_STATES,
    IMPACT_SHAPES,
    LINK_KINDS,
    METRIC_DIRECTIONS,
    METRIC_GRANULARITIES,
    METRIC_KINDS,
    METRIC_STATUSES,
    METRIC_VISIBILITIES,
    OBSERVATION_LABELS,
    OBSERVATION_SOURCES,
    SNAPSHOT_SCOPES,
    TARGET_BELIEFS,
    TARGET_STATUSES,
)
from app.models.customer_intelligence import CustomerHealthRow, CustomerOutcome
from app.models.execution_coordination import CoordinationIncident
from app.models.execution_intelligence import ProjectExecutionState
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyInitiative,
    CompanyObjective,
    StrategicLink,
)
from app.models.knowledge import KnowledgeTopic
from app.models.organizational_learning import OrganizationalLearning
from app.models.project import Project
from app.models.resource_allocation_intelligence import CapacitySnapshot

# ---------------------------------------------------------------------------
# canonical vocabularies & bounds

# Dimensions -> metric kinds that inform them (one dimension per metric).
DIMENSION_METRIC_KINDS: dict[str, tuple[str, ...]] = {
    "growth": ("growth", "expansion"),
    "customers": ("retention", "churn", "satisfaction"),
    "execution": ("delivery", "quality", "health", "security"),
    "strategy": ("adoption",),
    "capacity": ("utilization",),
    "operations": ("efficiency", "cost"),
    "innovation": ("engagement",),
    "financial": ("revenue",),
}
# Metric kinds not mapped to a health dimension still appear in trajectories.
UNMAPPED_KINDS = ("other",)

# Deterministic linkage language (machine keys -> canonical phrases).
LINK_LABELS: dict[str, str] = {
    "linked_to": "linked to",
    "strongly_associated_with": "strongly associated with",
    "evidence_indicates": "evidence indicates",
    "likely_contributor": "likely contributor",
}
DRIVER_STRENGTH_KIND: dict[str, str] = {
    "strong": "linked_to",
    "moderate": "strongly_associated_with",
    "evidence_limited": "evidence_indicates",
}

HEALTHY_THRESHOLD = 75
CONCERNED_THRESHOLD = 50
TREND_MOVE = 0.02  # >= 2% move = a real trend

ACTIVE_PROJECT_STATUSES = ("active", "in_progress", "planning")
ACTIVE_GOAL_STATUSES = ("active", "in_progress")

MAX_METRICS_SURFACE = 200
MAX_METRICS_SCAN = 200
MAX_OBSERVATIONS_PER_METRIC = 24
MAX_OBSERVATIONS_SURFACE = 24
MAX_TARGETS_SURFACE = 100
MAX_FORECASTS_SURFACE = 60
MAX_DRIVERS_SURFACE = 100
MAX_HISTORY = 40
MAX_HISTORY_SURFACE = 120
MAX_LINKS_SURFACE = 60
MAX_GOALS_SCAN = 200
MAX_PROJECTS_SCAN = 400
MAX_KNOWLEDGE_TOPICS = 500
MAX_LEARNING_SCAN = 100
MAX_CUSTOMERS_SCAN = 500
MAX_CAPACITY_SCAN = 100
MAX_RECOMMENDATIONS = 5
MAX_CHAIN_LINKS = 100
MAX_DRIVER_TOKENS = 6
MAX_DECISIONS = 8


# --------------------------------------------------------------- helpers

def _iso(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _metric_key(raw: Any) -> str:
    """Canonicalize a metric key: lowercase, spaces -> dashes."""
    key = (raw or "").strip().lower().replace(" ", "-")
    return key[:120]


def _tokens(text: str) -> list[str]:
    """Bounded keyword tokens for conservative cross-slice matching."""
    lowered = (text or "").lower()
    out: list[str] = []
    for chunk in lowered.replace("-", " ").replace("_", " ").split():
        if len(chunk) >= 3:
            out.append(chunk)
    return list(dict.fromkeys(out))[:MAX_DRIVER_TOKENS]


def _is_monetary(unit: Any) -> bool:
    u = (unit or "").strip().lower()
    return u in ("usd", "eur", "gbp", "inr", "cad", "aud", "jpy", "chf") or "usd" in u


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


class BusinessPerformanceEngine:
    """Canonical Commercial & Business Performance Intelligence — one engine."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ---------------------------------------------------------------- write

    async def record_event(
        self, db, *, organization_id: str,
        event, payload: dict[str, Any],
    ) -> None:
        """Change-driven entry: exact-once application of the event, then a
        recompute of ONLY the affected performance neighborhood (the affected
        metric's scope snapshot, or the org-wide snapshot)."""
        event_name = getattr(event, "name", "")
        source_event_id = getattr(event, "id", None)
        if not event_name or not source_event_id:
            return

        metric_id: Optional[str] = None
        if event_name == "business.metric.created":
            metric_id = await self._apply_metric(
                db, organization_id=organization_id, payload=payload,
                source_event_id=source_event_id, created=True,
            )
        elif event_name == "business.metric.updated":
            metric_id = await self._apply_metric(
                db, organization_id=organization_id, payload=payload,
                source_event_id=source_event_id, created=False,
            )
        elif event_name == "business.outcome.recorded":
            metric_id = await self._apply_outcome(
                db, organization_id=organization_id, payload=payload,
                source_event_id=source_event_id,
            )
        elif event_name in ("business.target.created", "business.target.updated"):
            metric_id = await self._apply_target(
                db, organization_id=organization_id, payload=payload,
                source_event_id=source_event_id,
                created=event_name == "business.target.created",
            )
        elif event_name in ("business.forecast.created", "business.forecast.updated"):
            metric_id = await self._apply_forecast(
                db, organization_id=organization_id, payload=payload,
                source_event_id=source_event_id,
                created=event_name == "business.forecast.created",
            )
        elif event_name == "business.driver.detected":
            await self._apply_driver(
                db, organization_id=organization_id, payload=payload,
                source_event_id=source_event_id,
            )
        elif event_name == "business.performance.changed":
            scope = (payload.get("scope") or "org_wide").strip()
            if scope not in SNAPSHOT_SCOPES:
                scope = "org_wide"
            await self._refresh_performance(
                db, organization_id=organization_id,
                source_event_id=source_event_id, event_name=event_name,
                scope=scope,
                scope_entity_id=(payload.get("scope_entity_id") or "").strip()[:32],
            )
            return
        else:
            return

        # incremental: refresh the affected metric's target statuses, then
        # recompute the snapshot of the affected scope.
        if metric_id:
            scope, scope_entity_id = await self._metric_scope(
                db, organization_id=organization_id, metric_id=metric_id,
            )
            if event_name in (
                "business.metric.updated", "business.outcome.recorded",
                "business.target.created", "business.target.updated",
            ):
                await self._refresh_target_statuses(
                    db, organization_id=organization_id, metric_id=metric_id,
                    source_event_id=source_event_id,
                )
            await self._refresh_performance(
                db, organization_id=organization_id,
                source_event_id=source_event_id, event_name=event_name,
                scope=scope, scope_entity_id=scope_entity_id,
            )
        else:
            await self._refresh_performance(
                db, organization_id=organization_id,
                source_event_id=source_event_id, event_name=event_name,
                scope="org_wide", scope_entity_id="",
            )

    async def _metric_by_key(
        self, db, *, organization_id: str, key: str,
    ) -> Optional[BusinessMetric]:
        if not key:
            return None
        return (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == organization_id,
                    BusinessMetric.key == key,
                )
            )
        ).scalar_one_or_none()

    async def _metric_scope(
        self, db, *, organization_id: str, metric_id: str,
    ) -> tuple[str, str]:
        row = (
            await db.execute(
                select(BusinessMetric.scope, BusinessMetric.scope_entity_id).where(
                    BusinessMetric.organization_id == organization_id,
                    BusinessMetric.id == metric_id,
                )
            )
        ).first()
        if row is None:
            return "org_wide", ""
        return row.scope or "org_wide", row.scope_entity_id or ""

    # -------------------------------------------------------------- applies

    async def _apply_metric(
        self, db, *, organization_id: str, payload: dict[str, Any],
        source_event_id: str, created: bool,
    ) -> Optional[str]:
        """business.metric.created / business.metric.updated: one live metric
        per canonical key; updates mutate the live row (exact-once through
        the existence check, observations are themselves exact-once rows)."""
        key = _metric_key(payload.get("key") or payload.get("metric_key"))
        if not key:
            return None
        metric = await self._metric_by_key(db, organization_id=organization_id, key=key)
        if metric is None:
            kind = (payload.get("kind") or "other").strip()[:40]
            if kind not in METRIC_KINDS:
                kind = "other"
            direction = (payload.get("direction") or "up_is_good").strip()[:16]
            if direction not in METRIC_DIRECTIONS:
                direction = "up_is_good"
            granularity = (payload.get("period_granularity") or "monthly").strip()[:16]
            if granularity not in METRIC_GRANULARITIES:
                granularity = "monthly"
            visibility = (payload.get("visibility") or "internal").strip()[:16]
            if visibility not in METRIC_VISIBILITIES:
                visibility = "internal"
            scope = (payload.get("scope") or "org_wide").strip()[:16]
            if scope not in SNAPSHOT_SCOPES:
                scope = "org_wide"
            metric = BusinessMetric(
                organization_id=organization_id,
                key=key,
                label=(payload.get("label") or key)[:200],
                description=(payload.get("description") or "")[:4000] or None,
                kind=kind, direction=direction,
                unit=(payload.get("unit") or "")[:40],
                status="active", visibility=visibility,
                period_granularity=granularity,
                scope=scope,
                scope_entity_id=(payload.get("scope_entity_id") or "").strip()[:32] or None,
                source_event_id=source_event_id,
            )
            db.add(metric)
            await db.flush()
        else:
            if not created:
                for field, column in (
                    ("label", "label"),
                    ("description", "description"),
                    ("kind", "kind"),
                    ("direction", "direction"),
                    ("unit", "unit"),
                ):
                    value = payload.get(field)
                    if value is None:
                        continue
                    if field == "kind" and str(value) not in METRIC_KINDS:
                        continue
                    if field == "direction" and str(value) not in METRIC_DIRECTIONS:
                        continue
                    setattr(metric, column, str(value)[:4000 if field == "description" else 200])
                status = (payload.get("status") or "").strip()
                if status in METRIC_STATUSES:
                    metric.status = status[:16]
        obs = payload.get("observation") or {}
        if not isinstance(obs, dict):
            obs = {}
        if payload.get("value") is not None:
            obs["value"] = payload["value"]
            if payload.get("observed_at"):
                obs.setdefault("observed_at", payload["observed_at"])
        if obs.get("value") is not None:
            await self._record_observation(
                db, organization_id=organization_id, metric=metric,
                value=float(obs["value"]),
                observed_at=obs.get("observed_at"),
                source=(obs.get("source") or "system"),
                label=(obs.get("label") or "actual"),
                provenance=(
                    obs.get("provenance") or f"business.metric.{'created' if created else 'updated'}:{source_event_id}"
                ),
                note=obs.get("note"),
                source_event_id=source_event_id,
            )
        return metric.id

    async def _apply_outcome(
        self, db, *, organization_id: str, payload: dict[str, Any],
        source_event_id: str,
    ) -> Optional[str]:
        """business.outcome.recorded: an actual business outcome observation
        on a metric (lazily created from the payload when the metric does
        not exist yet — the outcome is evidence a metric matters)."""
        key = _metric_key(payload.get("metric_key") or payload.get("key"))
        if not key:
            return None
        metric = await self._metric_by_key(db, organization_id=organization_id, key=key)
        if metric is None:
            metric = BusinessMetric(
                organization_id=organization_id,
                key=key,
                label=(payload.get("metric_label") or payload.get("label") or key)[:200],
                kind=(payload.get("kind") or "other").strip()[:40],
                direction=(payload.get("direction") or "up_is_good").strip()[:16],
                unit=(payload.get("unit") or "")[:40],
                status="active",
                source_event_id=source_event_id,
            )
            db.add(metric)
            await db.flush()
        value = payload.get("value")
        if value is None and payload.get("actual") is not None:
            value = payload["actual"]
        if value is None:
            return metric.id
        normalized = _iso(
            payload.get("observed_at") or payload.get("recorded_at")
        )
        await self._record_observation(
            db, organization_id=organization_id, metric=metric,
            value=float(value),
            observed_at=normalized,
            source=(payload.get("source") or "financial"),
            label="actual",
            provenance=f"business.outcome.recorded:{source_event_id}",
            note=(payload.get("note") or "")[:4000] or None,
            source_event_id=source_event_id,
        )
        return metric.id

    async def _record_observation(
        self, db, *, organization_id: str, metric: BusinessMetric,
        value: float, observed_at: Any, source: str, label: str,
        provenance: str, note: Any, source_event_id: str,
    ) -> None:
        """One exact-once observation row + the metric's last-value cache."""
        observed_dt = observed_at
        if isinstance(observed_dt, str):
            try:
                observed_dt = datetime.fromisoformat(observed_dt)
            except ValueError:
                observed_dt = None
        if not isinstance(observed_dt, datetime):
            observed_dt = utcnow()
        src = (source or "manual").strip()[:24]
        if src not in OBSERVATION_SOURCES:
            src = "manual"
        lab = (label or "actual").strip()[:16]
        if lab not in OBSERVATION_LABELS:
            lab = "actual"
        existing = (
            await db.execute(
                select(BusinessMetricObservation.id).where(
                    BusinessMetricObservation.organization_id == organization_id,
                    BusinessMetricObservation.metric_id == metric.id,
                    BusinessMetricObservation.observed_at == observed_dt,
                    BusinessMetricObservation.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return
        db.add(BusinessMetricObservation(
            organization_id=organization_id, metric_id=metric.id,
            value=value, observed_at=observed_dt,
            unit=(metric.unit or "")[:40],
            label=lab, source=src,
            provenance=(provenance or "")[:200],
            note=note,
            source_event_id=source_event_id,
        ))
        metric.last_value = value
        metric.last_observed_at = observed_dt
        await db.flush()

    async def _apply_target(
        self, db, *, organization_id: str, payload: dict[str, Any],
        source_event_id: str, created: bool,
    ) -> Optional[str]:
        """business.target.created / business.target.updated: one live target
        per (metric, period_label); updates mutate it. The status is
        re-derived deterministically by _refresh_target_statuses."""
        metric = None
        metric_id = (payload.get("metric_id") or "").strip()
        if metric_id:
            metric = (
                await db.execute(
                    select(BusinessMetric).where(
                        BusinessMetric.organization_id == organization_id,
                        BusinessMetric.id == metric_id,
                    )
                )
            ).scalar_one_or_none()
        if metric is None:
            metric = await self._metric_by_key(
                db, organization_id=organization_id,
                key=_metric_key(payload.get("metric_key") or payload.get("key")),
            )
        if metric is None:
            return None
        period_label = (payload.get("period_label") or "").strip()[:80]
        if not period_label:
            period_raw = _iso(payload.get("end_at") or "")
            period_label = period_raw[:7] if len(period_raw) >= 7 else "target"
        target = (
            await db.execute(
                select(BusinessTarget).where(
                    BusinessTarget.organization_id == organization_id,
                    BusinessTarget.metric_id == metric.id,
                    BusinessTarget.period_label == period_label,
                )
            )
        ).scalar_one_or_none()
        try:
            target_value = float(payload["target_value"])
        except (KeyError, TypeError, ValueError):
            return metric.id
        if target is None:
            end_raw = payload.get("end_at")
            end_at: Optional[date] = None
            if isinstance(end_raw, str):
                try:
                    end_at = date.fromisoformat(end_raw[:10])
                except ValueError:
                    end_at = None
            elif isinstance(end_raw, date):
                end_at = end_raw
            if end_at is None:
                return metric.id
            start_raw = payload.get("start_at")
            start_at: Optional[date] = None
            if isinstance(start_raw, str):
                try:
                    start_at = date.fromisoformat(start_raw[:10])
                except ValueError:
                    start_at = None
            elif isinstance(start_raw, date):
                start_at = start_raw
            belief = (payload.get("belief") or "plausible").strip()[:16]
            if belief not in TARGET_BELIEFS:
                belief = "plausible"
            target = BusinessTarget(
                organization_id=organization_id, metric_id=metric.id,
                metric_label=(metric.label or metric.key)[:200],
                target_value=target_value, unit=(payload.get("unit") or metric.unit or "")[:40],
                start_at=start_at, end_at=end_at,
                period_label=period_label,
                status="pending", belief=belief,
                rationale=(payload.get("rationale") or "")[:4000] or None,
                owner_label=(payload.get("owner_label") or "")[:200],
                initiative_labels_json=payload.get("initiative_labels") or [],
                dependency_labels_json=payload.get("dependency_labels") or [],
                open_decisions_json=payload.get("open_decisions") or [],
                strategy_label=(payload.get("strategy_label") or "")[:300],
                project_labels_json=payload.get("project_labels") or [],
                periods_json=payload.get("periods") or [],
                reviews_json=[],
                source_event_id=source_event_id,
            )
            db.add(target)
            await db.flush()
        else:
            if created:
                return metric.id
            target.target_value = target_value
            for field, maxlen in (
                ("metric_label", 200), ("unit", 40), ("rationale", 4000),
                ("owner_label", 200), ("strategy_label", 300),
            ):
                value = payload.get(field)
                if value is not None:
                    setattr(target, field, str(value)[:maxlen])
            for field in (
                "initiative_labels", "dependency_labels", "open_decisions",
                "project_labels", "periods",
            ):
                if payload.get(field) is not None:
                    setattr(target, f"{field}_json", payload[field])
            end_raw = payload.get("end_at")
            if isinstance(end_raw, str):
                try:
                    target.end_at = date.fromisoformat(end_raw[:10])
                except ValueError:
                    pass
            elif isinstance(end_raw, date):
                target.end_at = end_raw
            belief = (payload.get("belief") or "").strip()
            if belief in TARGET_BELIEFS:
                target.belief = belief[:16]
            target.source_event_id = source_event_id
            await db.flush()
        return metric.id

    async def _apply_forecast(
        self, db, *, organization_id: str, payload: dict[str, Any],
        source_event_id: str, created: bool,
    ) -> Optional[str]:
        """business.forecast.created / business.forecast.updated: one live
        forecast per (metric, horizon_label, forecast_type)."""
        metric = None
        metric_id = (payload.get("metric_id") or "").strip()
        if metric_id:
            metric = (
                await db.execute(
                    select(BusinessMetric).where(
                        BusinessMetric.organization_id == organization_id,
                        BusinessMetric.id == metric_id,
                    )
                )
            ).scalar_one_or_none()
        if metric is None:
            metric = await self._metric_by_key(
                db, organization_id=organization_id,
                key=_metric_key(payload.get("metric_key") or payload.get("key")),
            )
        if metric is None:
            return None
        horizon_label = (payload.get("horizon_label") or "").strip()[:80]
        if not horizon_label:
            return metric.id
        forecast_type = (payload.get("forecast_type") or "base").strip()[:16]
        if forecast_type not in FORECAST_TYPES:
            forecast_type = "base"
        forecast = (
            await db.execute(
                select(BusinessForecast).where(
                    BusinessForecast.organization_id == organization_id,
                    BusinessForecast.metric_id == metric.id,
                    BusinessForecast.horizon_label == horizon_label,
                    BusinessForecast.forecast_type == forecast_type,
                )
            )
        ).scalar_one_or_none()
        if forecast is None:
            forecast = BusinessForecast(
                organization_id=organization_id, metric_id=metric.id,
                metric_label=(metric.label or metric.key)[:200],
                forecast_type=forecast_type, horizon_label=horizon_label,
                basis=(payload.get("basis") or "")[:300],
                path_json=payload.get("path") or [],
                low_value=payload.get("low"),
                midpoint_value=payload.get("midpoint"),
                high_value=payload.get("high"),
                confidence=float(payload.get("confidence") or 0.5),
                confidence_basis=(payload.get("confidence_basis") or "")[:300],
                required_conditions_json=payload.get("required_conditions") or [],
                risk_factors_json=payload.get("risk_factors") or [],
                last_observed_value=metric.last_value,
                growth_rate=payload.get("growth_rate"),
                source_event_id=source_event_id,
            )
            db.add(forecast)
            await db.flush()
        else:
            if created:
                return metric.id
            forecast.basis = (payload.get("basis") or forecast.basis)[:300]
            if payload.get("path") is not None:
                forecast.path_json = payload["path"]
            for field in ("low", "midpoint", "high"):
                if payload.get(field) is not None:
                    setattr(forecast, f"{field}_value", float(payload[field]))
            if payload.get("confidence") is not None:
                forecast.confidence = float(payload["confidence"])
            if payload.get("confidence_basis") is not None:
                forecast.confidence_basis = (payload["confidence_basis"] or "")[:300]
            if payload.get("required_conditions") is not None:
                forecast.required_conditions_json = payload["required_conditions"]
            if payload.get("risk_factors") is not None:
                forecast.risk_factors_json = payload["risk_factors"]
            if payload.get("growth_rate") is not None:
                forecast.growth_rate = float(payload["growth_rate"])
            forecast.last_observed_value = metric.last_value
            forecast.source_event_id = source_event_id
            await db.flush()
        return metric.id

    async def _apply_driver(
        self, db, *, organization_id: str, payload: dict[str, Any],
        source_event_id: str,
    ) -> None:
        """business.driver.detected: one live driver per canonical key. The
        strength/direction vocabulary is enforced; the link language is a
        deterministic function of the strength."""
        key = _metric_key(payload.get("key") or payload.get("driver_key"))
        if not key:
            return
        driver_type = (payload.get("driver_type") or "market").strip()[:24]
        if driver_type not in DRIVER_TYPES:
            driver_type = "market"
        strength = (payload.get("strength") or "moderate").strip()[:20]
        if strength not in DRIVER_STRENGTHS:
            strength = "moderate"
        direction = (payload.get("direction") or "toward").strip()[:12]
        if direction not in DRIVER_DIRECTIONS:
            direction = "toward"
        impact_shape = (payload.get("impact_shape") or "attribute").strip()[:16]
        if impact_shape not in IMPACT_SHAPES:
            impact_shape = "attribute"
        driver = (
            await db.execute(
                select(BusinessDriver).where(
                    BusinessDriver.organization_id == organization_id,
                    BusinessDriver.key == key,
                )
            )
        ).scalar_one_or_none()
        metric_keys = [
            _metric_key(mk) for mk in (payload.get("metric_keys") or [])
            if _metric_key(mk)
        ]
        if driver is None:
            db.add(BusinessDriver(
                organization_id=organization_id, key=key,
                title=(payload.get("title") or key)[:200],
                description=(payload.get("description") or "")[:4000] or None,
                driver_type=driver_type, strength=strength,
                direction=direction, impact_shape=impact_shape,
                metric_keys_json=metric_keys,
                monetized_impact=payload.get("monetized_impact"),
                relation_summary=(payload.get("relation_summary") or "")[:300],
                linked_entities_json=payload.get("linked_entities") or [],
                source_event_id=source_event_id,
            ))
        else:
            for field, maxlen in (("title", 200), ("description", 4000),
                                  ("relation_summary", 300)):
                value = payload.get(field)
                if value is not None:
                    setattr(driver, field, str(value)[:maxlen])
            if payload.get("driver_type") is not None:
                driver.driver_type = driver_type
            if payload.get("strength") is not None:
                driver.strength = strength
            if payload.get("direction") is not None:
                driver.direction = direction
            if payload.get("impact_shape") is not None:
                driver.impact_shape = impact_shape
            if metric_keys:
                driver.metric_keys_json = metric_keys
            if payload.get("monetized_impact") is not None:
                driver.monetized_impact = float(payload["monetized_impact"])
            if payload.get("linked_entities") is not None:
                driver.linked_entities_json = payload["linked_entities"]
            driver.source_event_id = source_event_id
        await db.flush()

    # -------------------------------------------------------- deterministic

    @staticmethod
    def _eval_target_status(
        target: BusinessTarget, current: Optional[float],
        today: date, direction: str = "up_is_good",
    ) -> str:
        """Deterministic status from evidence: whether the current value
        achieves the target (direction-aware), date vs deadline, and a
        progress framing. Terminal states never regress."""
        if target.status in ("delivered", "missed"):
            return target.status
        if current is None:
            return "pending"
        if direction == "up_is_good":
            achieved = current >= target.target_value
        else:
            achieved = current <= target.target_value
        if achieved:
            return "delivered"
        if target.end_at < today:
            return "missed"
        if target.target_value == 0:
            return "on_track"
        if direction == "up_is_good":
            progress = current / target.target_value
        else:
            progress = target.target_value / current if current else 0.0
        if progress >= 0.75:
            return "on_track"
        if progress >= 0.5:
            return "at_risk"
        return "slipped"

    async def _refresh_target_statuses(
        self, db, *, organization_id: str, metric_id: str,
        source_event_id: str,
    ) -> None:
        """Re-derive the live status of every non-terminal target on the
        affected metric; append a review note when the status moved."""
        today = date.today()
        targets = list(
            (
                await db.execute(
                    select(BusinessTarget).where(
                        BusinessTarget.organization_id == organization_id,
                        BusinessTarget.metric_id == metric_id,
                    )
                )
            ).scalars().all()
        )
        if not targets:
            return
        metric = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == organization_id,
                    BusinessMetric.id == metric_id,
                )
            )
        ).scalar_one_or_none()
        direction = metric.direction if metric else "up_is_good"
        observations = list(
            (
                await db.execute(
                    select(BusinessMetricObservation).where(
                        BusinessMetricObservation.organization_id == organization_id,
                        BusinessMetricObservation.metric_id == metric_id,
                        BusinessMetricObservation.label == "actual",
                    ).order_by(BusinessMetricObservation.observed_at.desc()).limit(2)
                )
            ).scalars().all()
        )
        current = observations[0].value if observations else None
        for t in targets:
            old = t.status
            new = self._eval_target_status(t, current, today, direction)
            if new == old:
                continue
            t.status = new
            reviews = list(t.reviews_json or [])
            reviews.append({
                "at": _iso(utcnow()),
                "note": f"status moved {old} -> {new} from {current} vs target {t.target_value}",
            })
            t.reviews_json = reviews[-8:]
        await db.flush()

    # ------------------------------------------------------ snapshot compute

    async def _compute_snapshot(
        self, db, *, organization_id: str,
        scope: str, scope_entity_id: str, compute_mode: str,
        period_label: str,
    ) -> dict[str, Any]:
        """The deterministic, evidence-backed performance assessment of one
        scope. Every number is a function of the canonical ledgers (ours and
        the platform's); every claim carries its evidence."""
        now = utcnow()
        metric_query = select(BusinessMetric).where(
            BusinessMetric.organization_id == organization_id,
            BusinessMetric.status == "active",
            BusinessMetric.scope == scope,
        )
        if scope != "org_wide" and scope_entity_id:
            metric_query = metric_query.where(
                BusinessMetric.scope_entity_id == scope_entity_id
            )
        metrics = list(
            (
                await db.execute(
                    metric_query.order_by(BusinessMetric.key).limit(MAX_METRICS_SCAN)
                )
            ).scalars().all()
        )

        series: dict[str, list[BusinessMetricObservation]] = {}
        for m in metrics:
            obs = list(
                (
                    await db.execute(
                        select(BusinessMetricObservation).where(
                            BusinessMetricObservation.organization_id == organization_id,
                            BusinessMetricObservation.metric_id == m.id,
                        ).order_by(
                            BusinessMetricObservation.observed_at.desc()
                        ).limit(MAX_OBSERVATIONS_PER_METRIC)
                    )
                ).scalars().all()
            )
            obs.reverse()
            series[m.id] = obs

        # metric trajectories
        trajectories: list[dict[str, Any]] = []
        metric_scores: dict[str, tuple[float, int]] = {}
        improving = 0
        worsening = 0
        for m in metrics:
            obs = series.get(m.id) or []
            current = obs[-1].value if obs else None
            prev = obs[-2].value if len(obs) >= 2 else None
            pct = None
            if current is not None and prev not in (None, 0):
                pct = (current - prev) / abs(prev)
            if current is not None and prev is None:
                pct = None
            good = (
                pct is not None and (
                    (pct > 0 and m.direction == "up_is_good")
                    or (pct < 0 and m.direction == "down_is_good")
                )
            )
            if pct is not None and pct >= TREND_MOVE:
                trend = "improving" if good else "worsening"
            elif pct is not None and pct <= -TREND_MOVE:
                trend = "worsening" if good else "improving"
            else:
                trend = "stable"
            if trend == "improving":
                improving += 1
            elif trend == "worsening":
                worsening += 1
            if pct is None:
                score = 65.0
            else:
                growth = 50 * (1 - math.exp(-4 * abs(pct)))
                score = 50 + (growth if good else -growth)
            metric_scores[m.id] = (_clamp(round(score)), len(obs))
            trajectories.append({
                "metric_id": m.id,
                "metric_key": m.key,
                "label": m.label,
                "kind": m.kind,
                "current": current,
                "previous": prev,
                "delta": (current - prev) if current is not None and prev is not None else None,
                "pct_change": round(pct, 4) if pct is not None else None,
                "trend": trend,
                "unit": m.unit,
                "direction": m.direction,
                "status": m.status,
                "observed_count": len(obs),
                "last_observed_at": _iso(obs[-1].observed_at) if obs else "",
            })

        # multidimensional health
        dimensions: list[dict[str, Any]] = []
        for dim in HEALTH_DIMENSIONS:
            kinds = DIMENSION_METRIC_KINDS.get(dim, ())
            members = [
                m for m in metrics
                if m.kind in kinds
            ]
            if not members:
                continue
            scores: list[int] = []
            reasons: list[str] = []
            positives: list[str] = []
            top: list[str] = []
            evidence_count = 0
            latest_at: Optional[datetime] = None
            for m in members:
                score, count = metric_scores.get(m.id, (65, 0))
                evidence_count += count
                obs = series.get(m.id) or []
                obs_times = [ensure_aware(o.observed_at) for o in obs]
                if obs_times:
                    newest = max(obs_times)
                    if latest_at is None or newest > latest_at:
                        latest_at = newest
                scores.append(score)
                top.append(m.label or m.key)
                traj = next(
                    (t for t in trajectories if t["metric_id"] == m.id), None
                )
                if traj is None:
                    continue
                if score < 60 and traj["trend"] != "stable":
                    span = ""
                    if traj["current"] is not None and traj["previous"] is not None:
                        span = f" ({traj['previous']} -> {traj['current']}{traj['unit'] or ''})"
                    reasons.append(
                        f"{traj['label'] or traj['metric_key']} {traj['trend']}{span}"
                    )
                elif score >= 75:
                    positives.append(f"{traj['label'] or traj['metric_key']} {traj['trend']}")
            dim_score = round(sum(scores) / len(scores)) if scores else 0
            if dim_score >= HEALTHY_THRESHOLD:
                state = "healthy"
            elif dim_score >= CONCERNED_THRESHOLD:
                state = "concerned"
            else:
                state = "at_risk"
            dimensions.append({
                "key": dim,
                "label": dim,
                "score": dim_score,
                "state": state,
                "reasons": reasons[:4],
                "positives": positives[:4],
                "top_metrics": top[:3],
                "evidence_count": evidence_count,
                "updated_at": _iso(latest_at) if latest_at else "",
                "metrics_count": len(members),
            })
        if dimensions:
            health_score = round(sum(d["score"] for d in dimensions) / len(dimensions))
        else:
            health_score = 0
        if health_score >= HEALTHY_THRESHOLD:
            health_state = "healthy"
        elif health_score >= CONCERNED_THRESHOLD:
            health_state = "concerned"
        else:
            health_state = "at_risk"

        # targets (with live deterministic status)
        targets = list(
            (
                await db.execute(
                    select(BusinessTarget).where(
                        BusinessTarget.organization_id == organization_id,
                    ).order_by(BusinessTarget.end_at).limit(MAX_TARGETS_SURFACE)
                )
            ).scalars().all()
        )
        today = date.today()
        metric_directions = {
            m.id: m.direction for m in metrics
        }
        target_status_counts: dict[str, int] = defaultdict(int)
        target_items: list[dict[str, Any]] = []
        by_metric = defaultdict(list)
        for t in targets:
            obs = series.get(t.metric_id) or []
            current = obs[-1].value if obs else None
            status = self._eval_target_status(
                t, current, today, metric_directions.get(t.metric_id, "up_is_good"),
            )
            by_metric[t.metric_id].append(t)
            target_items.append({
                "target_id": t.id,
                "metric_id": t.metric_id,
                "metric_key": next(
                    (m.key for m in metrics if m.id == t.metric_id), t.metric_label
                ),
                "metric_label": t.metric_label,
                "target_value": t.target_value,
                "current": current,
                "unit": t.unit,
                "period_label": t.period_label,
                "end_at": t.end_at.isoformat(),
                "status": status,
                "belief": t.belief,
            })
            target_status_counts[status] += 1

        # drivers -> deterministic link language
        drivers = list(
            (
                await db.execute(
                    select(BusinessDriver).where(
                        BusinessDriver.organization_id == organization_id,
                    ).order_by(BusinessDriver.key).limit(MAX_DRIVERS_SURFACE)
                )
            ).scalars().all()
        )
        driver_links = []
        for d in drivers:
            kind = DRIVER_STRENGTH_KIND.get(d.strength, "evidence_indicates")
            driver_links.append({
                "driver_key": d.key,
                "title": d.title,
                "strength": d.strength,
                "direction": d.direction,
                "kind": kind,
                "kind_label": LINK_LABELS[kind],
                "impact_shape": d.impact_shape,
                "metric_keys": d.metric_keys_json or [],
                "monetized_impact": d.monetized_impact,
                "relation_summary": d.relation_summary,
            })

        # monetized gains/losses (currency-unit metrics only)
        gains_losses = []
        for m in metrics:
            if not _is_monetary(m.unit):
                continue
            obs = series.get(m.id) or []
            if len(obs) < 2:
                continue
            delta = obs[-1].value - obs[-2].value
            good = (delta > 0 and m.direction == "up_is_good") or (
                delta < 0 and m.direction == "down_is_good"
            )
            gains_losses.append({
                "metric_key": m.key,
                "label": m.label,
                "delta": round(delta, 2),
                "unit": m.unit,
                "monetized": round(delta, 2),
                "direction": "gain" if good else "loss",
                "confidence": 0.8 if len(obs) >= 3 else 0.5,
                "period": period_label,
            })

        # cross-slice links (bounded, org rollups)
        links = await self._org_links(
            db, organization_id=organization_id,
        )

        narrative = self._narrative(
            health_state=health_state, health_score=health_score,
            dimensions=dimensions, trajectories=trajectories,
            target_items=target_items, driver_links=driver_links,
            links=links, compute_mode=compute_mode, period_label=period_label,
        )

        return {
            "scope": scope,
            "scope_entity_id": scope_entity_id,
            "compute_mode": compute_mode,
            "period_label": period_label,
            "health": {
                "score": health_score,
                "state": health_state,
                "dimensions": dimensions,
            },
            "metrics": {
                "total": len(metrics),
                "improving": improving,
                "worsening": worsening,
                "trajectories": trajectories,
            },
            "targets": {
                "total": len(target_items),
                "by_status": dict(target_status_counts),
                "items": target_items,
            },
            "drivers": driver_links,
            "gains_losses": gains_losses,
            "links": links,
            "summary": narrative,
        }

    async def _org_links(
        self, db, *, organization_id: str,
    ) -> list[dict[str, Any]]:
        """Bounded cross-slice link rollups with deterministic language."""
        links: list[dict[str, Any]] = []

        # strategy (4G.3): active goals carrying a metric
        goals = list(
            (
                await db.execute(
                    select(CompanyGoal).where(
                        CompanyGoal.organization_id == organization_id,
                        CompanyGoal.status.in_(ACTIVE_GOAL_STATUSES),
                    ).limit(MAX_GOALS_SCAN)
                )
            ).scalars().all()
        )
        if goals:
            links.append({
                "target_type": "company_goal",
                "kind": "linked_to",
                "weight": 0.8,
                "summary": f"{len(goals)} active company goal(s) (4G.3)",
                "evidence_count": len(goals),
            })

        # execution (4G.1): projects at risk
        states = list(
            (
                await db.execute(
                    select(ProjectExecutionState).where(
                        ProjectExecutionState.organization_id == organization_id,
                    ).limit(MAX_PROJECTS_SCAN)
                )
            ).scalars().all()
        )
        at_risk = [s for s in states if s.health_status in ("at_risk", "critical")]
        if states:
            links.append({
                "target_type": "project",
                "kind": "strongly_associated_with",
                "weight": 0.7,
                "summary": (
                    f"{len(at_risk)} of {len(states)} project(s) at risk or "
                    f"critical (4G.1)"
                ),
                "evidence_count": len(at_risk),
            })

        # customers (4G.5): customers at risk
        health_rows = list(
            (
                await db.execute(
                    select(CustomerHealthRow).where(
                        CustomerHealthRow.organization_id == organization_id,
                        CustomerHealthRow.state.in_(("at_risk", "concerned")),
                    ).limit(MAX_CUSTOMERS_SCAN)
                )
            ).scalars().all()
        )
        at_risk_customers = sum(1 for r in health_rows if r.state == "at_risk")
        if health_rows:
            links.append({
                "target_type": "customer",
                "kind": "evidence_indicates",
                "weight": 0.6,
                "summary": (
                    f"{at_risk_customers} customer(s) at risk, "
                    f"{len(health_rows) - at_risk_customers} concerned (4G.5)"
                ),
                "evidence_count": len(health_rows),
            })

        # capacity (4G.4): current bottlenecks
        bottlenecks = await self._current_bottlenecks(
            db, organization_id=organization_id,
        )
        if bottlenecks:
            links.append({
                "target_type": "capacity",
                "kind": "evidence_indicates",
                "weight": 0.7,
                "summary": f"{len(bottlenecks)} capacity bottleneck(s) (4G.4)",
                "evidence_count": len(bottlenecks),
            })

        # decisions (4A via 4G.1): open decisions pending on projects
        decisions = [
            d for s in states
            for d in (s.pending_decisions or [])
        ]
        if decisions:
            links.append({
                "target_type": "decision",
                "kind": "likely_contributor",
                "weight": 0.5,
                "summary": f"{len(decisions)} open decision(s) on tracked projects",
                "evidence_count": len(decisions),
            })

        # knowledge (4E): topic coverage of our drivers
        driver_rows = list(
            (
                await db.execute(
                    select(BusinessDriver).where(
                        BusinessDriver.organization_id == organization_id,
                    ).limit(MAX_DRIVERS_SURFACE)
                )
            ).scalars().all()
        )
        if driver_rows:
            topics = list(
                (
                    await db.execute(
                        select(KnowledgeTopic).where(
                            KnowledgeTopic.organization_id == organization_id,
                        ).limit(MAX_KNOWLEDGE_TOPICS)
                    )
                ).scalars().all()
            )
            covered = 0
            for d in driver_rows:
                tokens = _tokens(d.title or d.key)
                if any(
                    any(tok in (t.name or "").lower() or tok in (t.category or "").lower()
                        for tok in tokens)
                    for t in topics
                ):
                    covered += 1
            links.append({
                "target_type": "knowledge",
                "kind": "evidence_indicates",
                "weight": 0.5,
                "summary": (
                    f"{covered} of {len(driver_rows)} driver(s) covered by "
                    f"knowledge topics (4E)"
                ),
                "evidence_count": covered,
            })

        return links[:MAX_LINKS_SURFACE]

    async def _current_bottlenecks(
        self, db, *, organization_id: str, limit: int = 5,
    ) -> list[dict[str, Any]]:
        today = date.today()
        rows = list(
            (
                await db.execute(
                    select(CapacitySnapshot).where(
                        CapacitySnapshot.organization_id == organization_id,
                        CapacitySnapshot.is_bottleneck.is_(True),
                    ).order_by(CapacitySnapshot.occurred_at.desc()).limit(MAX_CAPACITY_SCAN)
                )
            ).scalars().all()
        )
        best: dict[tuple[str, str, str], CapacitySnapshot] = {}
        for r in rows:
            if not (r.window_start <= today and r.window_end >= today):
                continue
            key = (r.capability, r.window_start.isoformat(), r.window_end.isoformat())
            if key not in best:
                best[key] = r
        items = [
            {
                "capability": r.capability,
                "window_start": r.window_start.isoformat(),
                "window_end": r.window_end.isoformat(),
                "utilization": r.utilization,
                "gap": r.gap,
            }
            for r in best.values()
        ]
        items.sort(key=lambda x: (-x["utilization"], x["capability"]))
        return items[:limit]

    def _narrative(
        self, *, health_state: str, health_score: int,
        dimensions: list[dict[str, Any]], trajectories: list[dict[str, Any]],
        target_items: list[dict[str, Any]], driver_links: list[dict[str, Any]],
        links: list[dict[str, Any]], compute_mode: str, period_label: str,
    ) -> list[str]:
        sentences: list[str] = []
        dim_states = [f"{d['label']}: {d['state']} ({d['score']})" for d in dimensions]
        if dim_states:
            sentences.append(
                f"Business health is {health_state} ({health_score}/100) for "
                f"{period_label}: " + "; ".join(dim_states[:4])
            )
        else:
            sentences.append(
                f"No business metric has evidence yet for {period_label} — "
                "record outcomes to ground the assessment."
            )
        if trajectories:
            improving = sum(1 for t in trajectories if t["trend"] == "improving")
            worsening = sum(1 for t in trajectories if t["trend"] == "worsening")
            sentences.append(
                f"{improving} of {len(trajectories)} active metric(s) improving, "
                f"{worsening} worsening."
            )
        for status in ("delivered", "on_track", "at_risk", "slipped", "missed", "pending"):
            count = sum(1 for t in target_items if t["status"] == status)
            if count:
                sentences.append(f"{count} target(s) {status}.")
        for l in links:
            sentences.append(l["summary"] + ".")
        if driver_links:
            strongest = max(
                driver_links,
                key=lambda d: (
                    LINK_KINDS.index(d["kind"]) if d["kind"] in LINK_KINDS else 99,
                ),
            )
            sentences.append(
                f"Principal driver: {strongest['title']} ({strongest['strength']}), "
                f"{strongest['kind_label']} its metrics."
            )
        mode_note = {
            "observed": "computed from recorded observations",
            "derived": "derived from cross-slice evidence",
            "projected": "projected from forecasts — not observed",
            "scenario": "a bounded what-if scenario — not observed",
        }.get(compute_mode, compute_mode)
        sentences.append(f"Compute mode: {compute_mode} ({mode_note}).")
        sentences.append(
            "Advisory only: every connection is evidence-backed; no action "
            "is taken automatically."
        )
        return sentences

    async def _refresh_performance(
        self, db, *, organization_id: str, source_event_id: str,
        event_name: str, scope: str = "org_wide",
        scope_entity_id: str = "", compute_mode: str = "observed",
        period_label: Optional[str] = None,
    ) -> None:
        """Persist the recomputed snapshot for the affected scope and append
        the temporal history row — both exact-once on the source event."""
        if scope not in SNAPSHOT_SCOPES:
            scope = "org_wide"
        if compute_mode not in COMPUTE_MODES:
            compute_mode = "observed"
        row_exists = (
            await db.execute(
                select(BusinessPerformanceSnapshot.id).where(
                    BusinessPerformanceSnapshot.organization_id == organization_id,
                    BusinessPerformanceSnapshot.scope == scope,
                    BusinessPerformanceSnapshot.scope_entity_id == scope_entity_id,
                    BusinessPerformanceSnapshot.compute_mode == compute_mode,
                    BusinessPerformanceSnapshot.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none()
        if row_exists:
            return
        now = utcnow()
        if period_label is None:
            period_label = now.strftime("%Y-%m")
        payload = await self._compute_snapshot(
            db, organization_id=organization_id, scope=scope,
            scope_entity_id=scope_entity_id, compute_mode=compute_mode,
            period_label=period_label,
        )
        snapshot = BusinessPerformanceSnapshot(
            organization_id=organization_id, scope=scope,
            scope_entity_id=scope_entity_id, compute_mode=compute_mode,
            period_label=period_label,
            health_score=payload["health"]["score"],
            health_state=payload["health"]["state"],
            health_dimensions_json=payload["health"]["dimensions"],
            metric_trajectories_json=payload["metrics"]["trajectories"],
            driver_links_json=payload["drivers"],
            gains_losses_json=payload["gains_losses"],
            links_json=payload["links"],
            summary_narrative="\n".join(payload["summary"]),
            started_at=now, ended_at=now,
            event_name=event_name, source_event_id=source_event_id,
        )
        db.add(snapshot)
        db.add(BusinessPerformanceHistory(
            organization_id=organization_id, scope=scope,
            scope_entity_id=scope_entity_id, compute_mode=compute_mode,
            period_label=period_label,
            health_score=payload["health"]["score"],
            health_state=payload["health"]["state"],
            payload_json=payload,
            event_name=event_name, source_event_id=source_event_id,
            occurred_at=now,
        ))
        await db.flush()

    # ---------------------------------------------------------------- reads

    async def metrics(
        self, db, *, organization_id: str, scope: Optional[str] = None,
    ) -> dict[str, Any]:
        """The metric ledger: every active metric with its current/previous
        value, direction-aware trend and linked targets."""
        q = select(BusinessMetric).where(
            BusinessMetric.organization_id == organization_id,
        )
        if scope in SNAPSHOT_SCOPES:
            q = q.where(BusinessMetric.scope == scope)
        rows = list(
            (
                await db.execute(
                    q.order_by(BusinessMetric.created_at.desc()).limit(MAX_METRICS_SURFACE)
                )
            ).scalars().all()
        )
        targets = {
            t.metric_id: t
            for t in list(
                (
                    await db.execute(
                        select(BusinessTarget).where(
                            BusinessTarget.organization_id == organization_id,
                        ).limit(MAX_TARGETS_SURFACE)
                    )
                ).scalars().all()
            )
        }
        items = []
        for m in rows:
            obs = list(
                (
                    await db.execute(
                        select(BusinessMetricObservation).where(
                            BusinessMetricObservation.organization_id == organization_id,
                            BusinessMetricObservation.metric_id == m.id,
                        ).order_by(BusinessMetricObservation.observed_at.desc()).limit(2)
                    )
                ).scalars().all()
            )
            current = obs[0].value if obs else None
            prev = obs[1].value if len(obs) >= 2 else None
            pct = None
            if current is not None and prev not in (None, 0):
                pct = (current - prev) / abs(prev)
            good = pct is not None and (
                (pct > 0 and m.direction == "up_is_good")
                or (pct < 0 and m.direction == "down_is_good")
            )
            if pct is None or abs(pct) < TREND_MOVE:
                trend = "stable"
            elif (pct > 0) == good:
                trend = "improving"
            else:
                trend = "worsening"
            target = targets.get(m.id)
            items.append({
                "metric_id": m.id,
                "key": m.key,
                "label": m.label,
                "kind": m.kind,
                "direction": m.direction,
                "unit": m.unit,
                "status": m.status,
                "visibility": m.visibility,
                "period_granularity": m.period_granularity,
                "scope": m.scope,
                "scope_entity_id": m.scope_entity_id or "",
                "current": current,
                "previous": prev,
                "pct_change": round(pct, 4) if pct is not None else None,
                "trend": trend,
                "observed_count": len(obs) and (await self._observation_count(
                    db, organization_id=organization_id, metric_id=m.id,
                )),
                "last_observed_at": _iso(obs[0].observed_at) if obs else "",
                "target": {
                    "target_id": target.id, "value": target.target_value,
                    "unit": target.unit, "period_label": target.period_label,
                    "status": target.status, "end_at": target.end_at.isoformat(),
                } if target else None,
            })
        return {
            "advisory_only": True,
            "total": len(items),
            "metrics": items,
        }

    async def _observation_count(
        self, db, *, organization_id: str, metric_id: str,
    ) -> int:
        return (
            await db.execute(
                select(func.count(BusinessMetricObservation.id)).where(
                    BusinessMetricObservation.organization_id == organization_id,
                    BusinessMetricObservation.metric_id == metric_id,
                )
            )
        ).scalar_one() or 0

    async def metric(
        self, db, *, organization_id: str, metric_id: str,
    ) -> Optional[dict[str, Any]]:
        """One metric's full evidence: series, targets, forecasts, drivers
        and recorded links."""
        m = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == organization_id,
                    BusinessMetric.id == metric_id,
                )
            )
        ).scalar_one_or_none()
        if m is None:
            return None
        observations = list(
            (
                await db.execute(
                    select(BusinessMetricObservation).where(
                        BusinessMetricObservation.organization_id == organization_id,
                        BusinessMetricObservation.metric_id == metric_id,
                    ).order_by(BusinessMetricObservation.observed_at.desc()).limit(MAX_OBSERVATIONS_SURFACE)
                )
            ).scalars().all()
        )
        targets = list(
            (
                await db.execute(
                    select(BusinessTarget).where(
                        BusinessTarget.organization_id == organization_id,
                        BusinessTarget.metric_id == metric_id,
                    ).order_by(BusinessTarget.end_at).limit(MAX_TARGETS_SURFACE)
                )
            ).scalars().all()
        )
        forecasts = list(
            (
                await db.execute(
                    select(BusinessForecast).where(
                        BusinessForecast.organization_id == organization_id,
                        BusinessForecast.metric_id == metric_id,
                    ).order_by(BusinessForecast.created_at.desc()).limit(MAX_FORECASTS_SURFACE)
                )
            ).scalars().all()
        )
        drivers = [
            d for d in list(
                (
                    await db.execute(
                        select(BusinessDriver).where(
                            BusinessDriver.organization_id == organization_id,
                        ).limit(MAX_DRIVERS_SURFACE)
                    )
                ).scalars().all()
            )
            if m.key in (d.metric_keys_json or [])
        ]
        links_rows = list(
            (
                await db.execute(
                    select(BusinessPerformanceLink).where(
                        BusinessPerformanceLink.organization_id == organization_id,
                        BusinessPerformanceLink.entity_type == "business_metric",
                        BusinessPerformanceLink.entity_id == metric_id,
                    ).limit(MAX_LINKS_SURFACE)
                )
            ).scalars().all()
        )
        today = date.today()
        observations_asc = list(reversed(observations))
        current = observations_asc[-1].value if observations_asc else None
        m_direction = m.direction if m else "up_is_good"
        target_items = []
        for t in targets:
            status = self._eval_target_status(t, current, today, m_direction)
            target_items.append({
                "target_id": t.id,
                "value": t.target_value, "unit": t.unit,
                "period_label": t.period_label,
                "start_at": t.start_at.isoformat() if t.start_at else "",
                "end_at": t.end_at.isoformat(),
                "status": status, "belief": t.belief,
                "gap": (
                    round((t.target_value - current), 4)
                    if current is not None
                    else None
                ),
                "owner_label": t.owner_label,
                "rationale": t.rationale,
                "strategy_label": t.strategy_label,
                "initiative_labels": t.initiative_labels_json or [],
                "dependency_labels": t.dependency_labels_json or [],
                "open_decisions": t.open_decisions_json or [],
                "project_labels": t.project_labels_json or [],
                "periods": t.periods_json or [],
                "reviews": t.reviews_json or [],
            })
        return {
            "advisory_only": True,
            "metric": {
                "metric_id": m.id,
                "key": m.key,
                "label": m.label,
                "kind": m.kind,
                "direction": m.direction,
                "unit": m.unit,
                "status": m.status,
                "visibility": m.visibility,
                "period_granularity": m.period_granularity,
                "scope": m.scope,
                "scope_entity_id": m.scope_entity_id or "",
                "description": m.description,
                "last_value": m.last_value,
                "last_observed_at": _iso(m.last_observed_at) if m.last_observed_at else "",
            },
            "observations": [
                {
                    "observations_id": o.id,
                    "value": o.value,
                    "observed_at": _iso(o.observed_at),
                    "unit": o.unit,
                    "label": o.label,
                    "source": o.source,
                    "provenance": o.provenance,
                    "note": o.note,
                }
                for o in observations
            ],
            "targets": target_items,
            "forecasts": [
                {
                    "forecast_id": f.id,
                    "forecast_type": f.forecast_type,
                    "horizon_label": f.horizon_label,
                    "basis": f.basis,
                    "path": f.path_json or [],
                    "low": f.low_value,
                    "midpoint": f.midpoint_value,
                    "high": f.high_value,
                    "confidence": f.confidence,
                    "confidence_basis": f.confidence_basis,
                    "required_conditions": f.required_conditions_json or [],
                    "risk_factors": f.risk_factors_json or [],
                    "last_observed_value": f.last_observed_value,
                    "growth_rate": f.growth_rate,
                }
                for f in forecasts
            ],
            "drivers": [
                {
                    "driver_key": d.key,
                    "title": d.title,
                    "strength": d.strength,
                    "direction": d.direction,
                    "kind": DRIVER_STRENGTH_KIND.get(d.strength, "evidence_indicates"),
                    "monetized_impact": d.monetized_impact,
                }
                for d in drivers
            ],
            "links": [
                {
                    "link_id": l.id,
                    "target_type": l.target_type,
                    "target_id": l.target_id,
                    "kind": l.kind,
                    "kind_label": LINK_LABELS.get(l.kind, l.kind),
                    "weight": l.weight,
                    "evidence_count": l.evidence_count,
                    "reasoning": l.reasoning,
                }
                for l in links_rows
            ],
            "generated_at": _iso(utcnow()),
        }

    async def targets(
        self, db, *, organization_id: str, status: Optional[str] = None,
    ) -> dict[str, Any]:
        """The target ledger: every committed business target with its live
        deterministic status, current progress and gap."""
        q = select(BusinessTarget).where(
            BusinessTarget.organization_id == organization_id,
        )
        if status in TARGET_STATUSES:
            q = q.where(BusinessTarget.status == status)
        rows = list(
            (
                await db.execute(
                    q.order_by(BusinessTarget.end_at).limit(MAX_TARGETS_SURFACE)
                )
            ).scalars().all()
        )
        latest: dict[str, float] = {}
        for t in rows:
            if t.metric_id not in latest:
                obs = (
                    await db.execute(
                        select(BusinessMetricObservation).where(
                            BusinessMetricObservation.organization_id == organization_id,
                            BusinessMetricObservation.metric_id == t.metric_id,
                            BusinessMetricObservation.label == "actual",
                        ).order_by(BusinessMetricObservation.observed_at.desc()).limit(1)
                    )
                ).scalar_one_or_none()
                latest[t.metric_id] = obs.value if obs else None
        today = date.today()
        metric_ids = list(dict.fromkeys(t.metric_id for t in rows))
        metric_directions = {}
        metric_keys = {}
        if metric_ids:
            metric_rows = list(
                (
                    await db.execute(
                        select(BusinessMetric).where(
                            BusinessMetric.organization_id == organization_id,
                            BusinessMetric.id.in_(metric_ids),
                        )
                    )
                ).scalars().all()
            )
            metric_directions = {m.id: m.direction for m in metric_rows}
            metric_keys = {m.id: m.key for m in metric_rows}
        items = []
        for t in rows:
            current = latest.get(t.metric_id)
            status_now = self._eval_target_status(
                t, current, today, metric_directions.get(t.metric_id, "up_is_good"),
            )
            gap = None
            progress = None
            if current is not None:
                if t.target_value != 0:
                    progress = round(current / t.target_value, 3)
                gap = round(t.target_value - current, 4)
            items.append({
                "target_id": t.id,
                "metric_id": t.metric_id,
                "metric_key": metric_keys.get(t.metric_id, ""),
                "metric_label": t.metric_label,
                "target_value": t.target_value,
                "current": current,
                "unit": t.unit,
                "period_label": t.period_label,
                "start_at": t.start_at.isoformat() if t.start_at else "",
                "end_at": t.end_at.isoformat(),
                "days_left": (t.end_at - today).days,
                "status": status_now,
                "belief": t.belief,
                "progress": progress,
                "gap": gap,
                "owner_label": t.owner_label,
                "strategy_label": t.strategy_label,
            })
        return {
            "advisory_only": True,
            "total": len(items),
            "by_status": {
                s: sum(1 for i in items if i["status"] == s)
                for s in TARGET_STATUSES
            },
            "targets": items,
        }

    async def target(
        self, db, *, organization_id: str, target_id: str,
    ) -> Optional[dict[str, Any]]:
        """One target's full command center: the metric, observations, gap
        analysis, linked initiatives/projects/dependencies/decisions."""
        t = (
            await db.execute(
                select(BusinessTarget).where(
                    BusinessTarget.organization_id == organization_id,
                    BusinessTarget.id == target_id,
                )
            )
        ).scalar_one_or_none()
        if t is None:
            return None
        m = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == organization_id,
                    BusinessMetric.id == t.metric_id,
                )
            )
        ).scalar_one_or_none()
        observations = list(
            (
                await db.execute(
                    select(BusinessMetricObservation).where(
                        BusinessMetricObservation.organization_id == organization_id,
                        BusinessMetricObservation.metric_id == t.metric_id,
                    ).order_by(BusinessMetricObservation.observed_at.desc()).limit(MAX_OBSERVATIONS_SURFACE)
                )
            ).scalars().all()
        )
        current = observations[0].value if observations else None
        today = date.today()
        m_direction = m.direction if m else "up_is_good"
        status = self._eval_target_status(t, current, today, m_direction)
        achievements = [
            o for o in observations
            if o.label == "actual" and (
                (o.value >= t.target_value)
                if m_direction == "up_is_good"
                else (o.value <= t.target_value)
            )
        ][:3]
        related = {
            "initiatives": t.initiative_labels_json or [],
            "dependencies": t.dependency_labels_json or [],
            "decisions": t.open_decisions_json or [],
            "projects": t.project_labels_json or [],
        }
        # project execution health for the targets' named projects
        project_states = await self._project_states_by_labels(
            db, organization_id=organization_id, labels=related["projects"],
        )
        return {
            "advisory_only": True,
            "target": {
                "target_id": t.id,
                "metric_id": t.metric_id,
                "metric_label": t.metric_label,
                "target_value": t.target_value,
                "current": current,
                "unit": t.unit,
                "period_label": t.period_label,
                "start_at": t.start_at.isoformat() if t.start_at else "",
                "end_at": t.end_at.isoformat(),
                "days_left": (t.end_at - today).days,
                "status": status,
                "belief": t.belief,
                "rationale": t.rationale,
                "owner_label": t.owner_label,
                "strategy_label": t.strategy_label,
                "periods": t.periods_json or [],
                "reviews": t.reviews_json or [],
                "progress": (
                    round(current / t.target_value, 3)
                    if current is not None and t.target_value != 0 else None
                ),
                "gap": (
                    round(t.target_value - current, 4)
                    if current is not None else None
                ),
            },
            "metric": {
                "metric_id": m.id if m else "",
                "key": m.key if m else "",
                "label": m.label if m else t.metric_label,
                "kind": m.kind if m else "",
                "direction": m.direction if m else "up_is_good",
                "unit": t.unit,
                "scope": m.scope if m else "org_wide",
                "scope_entity_id": m.scope_entity_id if m else "",
            } if m else {},
            "observations": [
                {
                    "value": o.value, "observed_at": _iso(o.observed_at),
                    "label": o.label, "source": o.source,
                    "provenance": o.provenance,
                }
                for o in observations
            ],
            "achievements": [
                {
                    "value": o.value, "observed_at": _iso(o.observed_at),
                    "provenance": o.provenance,
                }
                for o in achievements
            ],
            "related": related,
            "project_states": project_states,
            "generated_at": _iso(utcnow()),
        }

    async def _project_states_by_labels(
        self, db, *, organization_id: str, labels: Sequence[str],
    ) -> list[dict[str, Any]]:
        if not labels:
            return []
        projects = list(
            (
                await db.execute(
                    select(Project).where(
                        Project.organization_id == organization_id,
                    ).limit(MAX_PROJECTS_SCAN)
                )
            ).scalars().all()
        )
        wanted = {l.strip().lower() for l in labels if l}
        matched = [p for p in projects if (p.name or "").strip().lower() in wanted]
        if not matched:
            return []
        ids = [p.id for p in matched]
        states = {
            s.project_id: s
            for s in list(
                (
                    await db.execute(
                        select(ProjectExecutionState).where(
                            ProjectExecutionState.organization_id == organization_id,
                            ProjectExecutionState.project_id.in_(ids),
                        )
                    )
                ).scalars().all()
            )
        }
        return [
            {
                "project_id": p.id,
                "name": p.name,
                "status": p.status,
                "execution_health": (
                    states[p.id].health_status
                    if p.id in states else "unknown"
                ),
            }
            for p in matched
        ]

    async def forecasts(
        self, db, *, organization_id: str, metric_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """The forecast ledger: conservative/base/optimistic arcs with their
        basis and confidence — always labeled as projected, never observed."""
        metric_id: Optional[str] = None
        if metric_key:
            m = await self._metric_by_key(
                db, organization_id=organization_id, key=_metric_key(metric_key),
            )
            metric_id = m.id if m else None
        q = select(BusinessForecast).where(
            BusinessForecast.organization_id == organization_id,
        )
        if metric_id:
            q = q.where(BusinessForecast.metric_id == metric_id)
        rows = list(
            (
                await db.execute(
                    q.order_by(BusinessForecast.created_at.desc()).limit(MAX_FORECASTS_SURFACE)
                )
            ).scalars().all()
        )
        return {
            "advisory_only": True,
            "total": len(rows),
            "forecasts": [
                {
                    "forecast_id": f.id,
                    "metric_id": f.metric_id,
                    "metric_label": f.metric_label,
                    "forecast_type": f.forecast_type,
                    "horizon_label": f.horizon_label,
                    "basis": f.basis,
                    "path": f.path_json or [],
                    "low": f.low_value,
                    "midpoint": f.midpoint_value,
                    "high": f.high_value,
                    "confidence": f.confidence,
                    "confidence_basis": f.confidence_basis,
                    "required_conditions": f.required_conditions_json or [],
                    "risk_factors": f.risk_factors_json or [],
                    "last_observed_value": f.last_observed_value,
                    "growth_rate": f.growth_rate,
                }
                for f in rows
            ],
        }

    async def drivers(self, db, *, organization_id: str) -> dict[str, Any]:
        """The driver ledger: what moves business performance, with its
        evidence strength and deterministic link language."""
        rows = list(
            (
                await db.execute(
                    select(BusinessDriver).where(
                        BusinessDriver.organization_id == organization_id,
                    ).order_by(BusinessDriver.key).limit(MAX_DRIVERS_SURFACE)
                )
            ).scalars().all()
        )
        items = []
        for d in rows:
            kind = DRIVER_STRENGTH_KIND.get(d.strength, "evidence_indicates")
            items.append({
                "driver_key": d.key,
                "title": d.title,
                "driver_type": d.driver_type,
                "strength": d.strength,
                "direction": d.direction,
                "impact_shape": d.impact_shape,
                "metric_keys": d.metric_keys_json or [],
                "monetized_impact": d.monetized_impact,
                "relation_summary": d.relation_summary,
                "linked_entities": d.linked_entities_json or [],
                "kind": kind,
                "kind_label": LINK_LABELS[kind],
                "description": d.description,
            })
        return {
            "advisory_only": True,
            "total": len(items),
            "by_type": {
                t: sum(1 for i in items if i["driver_type"] == t)
                for t in DRIVER_TYPES
            },
            "drivers": items,
        }

    async def performance(
        self, db, *, organization_id: str, scope: str = "org_wide",
        scope_entity_id: str = "", period_label: Optional[str] = None,
        compute_mode: str = "observed",
    ) -> Optional[dict[str, Any]]:
        """The CURRENT performance assessment of a scope plus its history
        trail (the latest snapshot is the live row)."""
        if scope not in SNAPSHOT_SCOPES:
            scope = "org_wide"
        if compute_mode not in COMPUTE_MODES:
            compute_mode = "observed"
        q = select(BusinessPerformanceSnapshot).where(
            BusinessPerformanceSnapshot.organization_id == organization_id,
            BusinessPerformanceSnapshot.scope == scope,
            BusinessPerformanceSnapshot.scope_entity_id == scope_entity_id,
            BusinessPerformanceSnapshot.compute_mode == compute_mode,
        )
        if period_label:
            q = q.where(BusinessPerformanceSnapshot.period_label == period_label)
        snapshot = (
            await db.execute(
                q.order_by(BusinessPerformanceSnapshot.started_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        history = list(
            (
                await db.execute(
                    select(BusinessPerformanceHistory).where(
                        BusinessPerformanceHistory.organization_id == organization_id,
                        BusinessPerformanceHistory.scope == scope,
                        BusinessPerformanceHistory.scope_entity_id == scope_entity_id,
                        BusinessPerformanceHistory.compute_mode == compute_mode,
                    ).order_by(
                        BusinessPerformanceHistory.occurred_at.desc()
                    ).limit(MAX_HISTORY)
                )
            ).scalars().all()
        )
        if snapshot is None:
            if history:
                latest = history[0]
                health_score = latest.health_score
                health_state = latest.health_state
                payload = latest.payload_json or {}
                period = latest.period_label
                generated = latest.occurred_at
            else:
                return None
        else:
            health_score = snapshot.health_score
            health_state = snapshot.health_state
            payload = {
                "health": {
                    "score": health_score,
                    "state": health_state,
                    "dimensions": snapshot.health_dimensions_json or [],
                },
                "metrics": {
                    "total": len(snapshot.metric_trajectories_json or []),
                    "trajectories": snapshot.metric_trajectories_json or [],
                },
                "targets": {
                    "items": [],
                },
                "drivers": snapshot.driver_links_json or [],
                "gains_losses": snapshot.gains_losses_json or [],
                "links": snapshot.links_json or [],
                "summary": (snapshot.summary_narrative or "").split("\n"),
            }
            period = snapshot.period_label
            generated = snapshot.started_at or snapshot.created_at
        return {
            "advisory_only": True,
            "scope": scope,
            "scope_entity_id": scope_entity_id,
            "compute_mode": compute_mode,
            "period_label": period,
            "health": payload["health"],
            "metrics": payload.get("metrics") or {},
            "drivers": payload.get("drivers") or [],
            "gains_losses": payload.get("gains_losses") or [],
            "links": payload.get("links") or [],
            "summary": payload.get("summary") or [],
            "generated_at": _iso(generated),
            "history": [
                {
                    "period_label": h.period_label,
                    "health_state": h.health_state,
                    "health_score": h.health_score,
                    "event_name": h.event_name,
                    "occurred_at": _iso(h.occurred_at),
                }
                for h in history
            ],
        }

    async def behind_target(
        self, db, *, organization_id: str, metric_key: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """THE flagship surface: 'Why are we behind our business target, and
        what should we do?' — the full evidence chain from the target through
        drivers, customers, knowledge, strategy, projects, dependencies,
        capacity and decisions to expected outcomes and what to do. Every
        step is deterministic and evidence-backed; the language is cautious
        by construction."""
        targets = list(
            (
                await db.execute(
                    select(BusinessTarget).where(
                        BusinessTarget.organization_id == organization_id,
                    ).order_by(BusinessTarget.end_at).limit(MAX_TARGETS_SURFACE)
                )
            ).scalars().all()
        )
        if not targets:
            return None
        if metric_key:
            m0 = await self._metric_by_key(
                db, organization_id=organization_id, key=_metric_key(metric_key),
            )
            if m0 is None:
                return None
            candidates = [t for t in targets if t.metric_id == m0.id]
        else:
            candidates = [
                t for t in targets
                if t.status in ("at_risk", "slipped", "missed", "pending", "on_track")
            ]
        if not candidates:
            return None
        t = candidates[0]
        metric = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == organization_id,
                    BusinessMetric.id == t.metric_id,
                )
            )
        ).scalar_one_or_none()
        if metric is None:
            return None

        observations = list(
            (
                await db.execute(
                    select(BusinessMetricObservation).where(
                        BusinessMetricObservation.organization_id == organization_id,
                        BusinessMetricObservation.metric_id == metric.id,
                    ).order_by(BusinessMetricObservation.observed_at.desc()).limit(MAX_OBSERVATIONS_PER_METRIC)
                )
            ).scalars().all()
        )
        observations.reverse()
        current = observations[-1].value if observations else None
        prev = observations[-2].value if len(observations) >= 2 else None
        today = date.today()
        behind = None
        if current is not None:
            behind = round(t.target_value - current, 4)
        metric_direction = metric.direction or "up_is_good"
        target_status = self._eval_target_status(
            t, current, today, metric_direction,
        )
        drivers = [
            d for d in list(
                (
                    await db.execute(
                        select(BusinessDriver).where(
                            BusinessDriver.organization_id == organization_id,
                        ).limit(MAX_DRIVERS_SURFACE)
                    )
                ).scalars().all()
            )
            if metric.key in (d.metric_keys_json or [])
        ]
        forecasts = list(
            (
                await db.execute(
                    select(BusinessForecast).where(
                        BusinessForecast.organization_id == organization_id,
                        BusinessForecast.metric_id == metric.id,
                    ).order_by(BusinessForecast.created_at.desc()).limit(MAX_FORECASTS_SURFACE)
                )
            ).scalars().all()
        )

        # customers (4G.5): health rollup + outcomes on this metric
        health_rows = list(
            (
                await db.execute(
                    select(CustomerHealthRow).where(
                        CustomerHealthRow.organization_id == organization_id,
                    ).limit(MAX_CUSTOMERS_SCAN)
                )
            ).scalars().all()
        )
        at_risk_customers = sum(1 for r in health_rows if r.state == "at_risk")
        concerned_customers = sum(1 for r in health_rows if r.state == "concerned")
        outcome_rows = list(
            (
                await db.execute(
                    select(CustomerOutcome).where(
                        CustomerOutcome.organization_id == organization_id,
                    ).order_by(CustomerOutcome.recorded_at.desc()).limit(MAX_CUSTOMERS_SCAN)
                )
            ).scalars().all()
        )
        metric_tokens = _tokens(metric.key + " " + metric.label)
        matching_outcomes = [
            o for o in outcome_rows
            if any(tok in (o.metric_kind or "").lower() for tok in metric_tokens)
        ]
        improved_outcomes = 0
        for o in matching_outcomes:
            if o.baseline is not None and o.target is not None and o.actual is not None:
                if abs(o.actual - o.target) < abs(o.baseline - o.target):
                    improved_outcomes += 1

        # knowledge (4E): topics covering the drivers
        topics = list(
            (
                await db.execute(
                    select(KnowledgeTopic).where(
                        KnowledgeTopic.organization_id == organization_id,
                    ).limit(MAX_KNOWLEDGE_TOPICS)
                )
            ).scalars().all()
        )
        knowledge_matches = []
        for d in drivers:
            tokens = _tokens(d.title or d.key)
            hits = [
                {"topic": t.name, "category": t.category}
                for t in topics
                if any(tok in (t.name or "").lower() or tok in (t.category or "").lower()
                       for tok in tokens)
            ][:10]
            if hits:
                knowledge_matches.append({
                    "driver_key": d.key,
                    "title": d.title,
                    "knowledge": hits,
                })

        # strategy (4G.3): goals carrying this metric + target's initiatives
        goals = list(
            (
                await db.execute(
                    select(CompanyGoal).where(
                        CompanyGoal.organization_id == organization_id,
                    ).limit(MAX_GOALS_SCAN)
                )
            ).scalars().all()
        )
        goal_chain = []
        matched_goals = [
            g for g in goals
            if g.metric_kind and _metric_key(g.metric_kind) == metric.key
            or (g.metric_kind or "").lower() == (metric.key or "").lower()
            or (g.metric_kind or "").lower() in (
                metric.label or ""
            ).lower()
        ]
        for g in matched_goals[:3]:
            objectives = list(
                (
                    await db.execute(
                        select(CompanyObjective).where(
                            CompanyObjective.organization_id == organization_id,
                            CompanyObjective.goal_id == g.id,
                        )
                    )
                ).scalars().all()
            )
            for obj in objectives[:3]:
                initiatives = list(
                    (
                        await db.execute(
                            select(CompanyInitiative).where(
                                CompanyInitiative.organization_id == organization_id,
                                CompanyInitiative.objective_id == obj.id,
                            )
                        )
                    ).scalars().all()
                )
                for init in initiatives[:3]:
                    goal_chain.append({
                        "goal_id": g.id,
                        "goal": g.title,
                        "objective_id": obj.id,
                        "objective": obj.title,
                        "initiative_id": init.id,
                        "initiative": init.title,
                        "expected_outcome": init.expected_outcome or None,
                    })
            if not objectives:
                goal_chain.append({
                    "goal_id": g.id, "goal": g.title,
                    "objective_id": "", "objective": "",
                    "initiative_id": "", "initiative": "",
                    "expected_outcome": None,
                })

        # projects (4G.1) + dependencies (4G.2): via strategic links
        links = list(
            (
                await db.execute(
                    select(StrategicLink).where(
                        StrategicLink.organization_id == organization_id,
                    ).limit(MAX_CHAIN_LINKS)
                )
            ).scalars().all()
        )
        chain_init_ids = {c["initiative_id"] for c in goal_chain if c["initiative_id"]}
        project_ids = [l.project_id for l in links if l.initiative_id in chain_init_ids]
        named_projects = [
            p for p in list(
                (
                    await db.execute(
                        select(Project).where(
                            Project.organization_id == organization_id,
                        ).limit(MAX_PROJECTS_SCAN)
                    )
                ).scalars().all()
            )
            if (p.name or "").strip().lower() in {
                (lbl or "").strip().lower() for lbl in (t.project_labels_json or [])
            }
        ]
        project_ids += [p.id for p in named_projects]
        project_ids = list(dict.fromkeys(pid for pid in project_ids if pid))
        projects = []
        if project_ids:
            states = {
                s.project_id: s
                for s in list(
                    (
                        await db.execute(
                            select(ProjectExecutionState).where(
                                ProjectExecutionState.organization_id == organization_id,
                                ProjectExecutionState.project_id.in_(project_ids),
                            )
                        )
                    ).scalars().all()
                )
            }
            project_rows = {
                p.id: p
                for p in list(
                    (
                        await db.execute(
                            select(Project).where(
                                Project.organization_id == organization_id,
                                Project.id.in_(project_ids),
                            )
                        )
                    ).scalars().all()
                )
            }
            for pid in project_ids:
                p = project_rows.get(pid)
                st = states.get(pid)
                projects.append({
                    "project_id": pid,
                    "name": p.name if p else "",
                    "status": p.status if p else "",
                    "execution_health": st.health_status if st else "unknown",
                })
        incidents = []
        if project_ids:
            incident_rows = list(
                (
                    await db.execute(
                        select(CoordinationIncident).where(
                            CoordinationIncident.organization_id == organization_id,
                            CoordinationIncident.status == "open",
                            CoordinationIncident.project_id.in_(project_ids),
                        ).limit(MAX_PROJECTS_SCAN)
                    )
                ).scalars().all()
            )
            for inc in incident_rows:
                incidents.append({
                    "incident_id": inc.id,
                    "kind": inc.kind,
                    "severity": inc.severity,
                    "title": inc.title,
                    "project_id": inc.project_id,
                })
        open_decisions = []
        if project_ids:
            state_rows = list(
                (
                    await db.execute(
                        select(ProjectExecutionState).where(
                            ProjectExecutionState.organization_id == organization_id,
                            ProjectExecutionState.project_id.in_(project_ids),
                        )
                    )
                ).scalars().all()
            )
            for s in state_rows:
                for d in (s.pending_decisions or []):
                    open_decisions.append({
                        "project_id": s.project_id,
                        "decision": d if isinstance(d, str) else str(d),
                    })
        open_decisions = open_decisions[:MAX_DECISIONS]

        # capacity (4G.4): current bottlenecks
        bottlenecks = await self._current_bottlenecks(
            db, organization_id=organization_id, limit=5,
        )

        # learning (4E.7): lessons about this metric
        lessons = []
        try:
            learning_rows = list(
                (
                    await db.execute(
                        select(OrganizationalLearning).where(
                            OrganizationalLearning.organization_id == organization_id,
                            OrganizationalLearning.status == "active",
                        ).order_by(
                            OrganizationalLearning.recorded_by.desc(),
                            OrganizationalLearning.created_at.desc(),
                        ).limit(MAX_LEARNING_SCAN)
                    )
                ).scalars().all()
            )
            lesson_tokens = _tokens(metric.key + " " + metric.label)
            for lesson in learning_rows:
                haystack = " ".join([
                    lesson.title or "", lesson.lesson or "",
                    lesson.topic_name or "", lesson.observation or "",
                ]).lower()
                if any(tok in haystack for tok in lesson_tokens):
                    lessons.append({
                        "lesson_id": lesson.id,
                        "title": lesson.title,
                        "lesson": lesson.lesson,
                        "confidence": lesson.confidence,
                        "lifecycle": lesson.lifecycle,
                        "observed_at": _iso(lesson.observed_at),
                    })
            lessons = lessons[:3]
        except Exception:
            lessons = []

        # what should we do: bounded advisory recommendations
        what_to_do: list[dict[str, Any]] = []
        if behind is not None:
            what_to_do.append({
                "kind": "close_gap",
                "title": f"Close the gap on {metric.label or metric.key}",
                "why": (
                    f"current {current}{t.unit or ''} vs target "
                    f"{t.target_value}{t.unit or ''}"
                ),
                "gap": behind,
                "evidence_count": len(observations),
            })
        for d in drivers[:2]:
            what_to_do.append({
                "kind": "address_driver",
                "title": f"Address driver: {d.title}",
                "why": f"{LINK_LABELS.get(DRIVER_STRENGTH_KIND.get(d.strength, 'evidence_indicates'))} the metric",
                "direction": d.direction,
                "monetized_impact": d.monetized_impact,
                "evidence_count": 0,
            })
        if bottlenecks:
            what_to_do.append({
                "kind": "allocate_capacity",
                "title": "Allocate capacity for bottleneck capability(ies)",
                "why": "; ".join(b["capability"] for b in bottlenecks[:3]),
                "evidence_count": len(bottlenecks),
            })
        if open_decisions:
            what_to_do.append({
                "kind": "resolve_decisions",
                "title": "Resolve open decisions gate-keeping the target",
                "why": f"{len(open_decisions)} open decision(s) on linked projects",
                "evidence_count": len(open_decisions),
            })
        if incidents:
            what_to_do.append({
                "kind": "resolve_coordination",
                "title": "Resolve open coordination findings on linked projects",
                "why": f"{len(incidents)} open finding(s)",
                "evidence_count": len(incidents),
            })
        at_risk_projects = [p for p in projects if p["execution_health"] in ("at_risk", "critical")]
        if at_risk_projects:
            what_to_do.append({
                "kind": "focus_projects",
                "title": "Focus execution on at-risk project(s)",
                "why": "; ".join(p["name"] for p in at_risk_projects[:3]),
                "evidence_count": len(at_risk_projects),
            })
        if improved_outcomes:
            what_to_do.append({
                "kind": "sustain_outcomes",
                "title": "Sustain customer outcome improvements",
                "why": f"{improved_outcomes} outcome(s) improved toward target on this metric",
                "evidence_count": improved_outcomes,
            })

        narrative = [
            f"Target: {t.metric_label or metric.key} at {t.target_value}{t.unit or ''} "
            f"by {t.end_at.isoformat()} ({t.period_label}).",
        ]
        if current is None:
            narrative.append("No actual observation is recorded yet — the gap "
                             "cannot be measured; the target stays pending.")
        else:
            direction_word = "behind" if behind > 0 else "ahead of"
            narrative.append(
                f"The metric is {direction_word} target: {current}{t.unit or ''} "
                f"now, {prev if prev is not None else 'no earlier value'} before "
                f"({behind}{t.unit or ''} {'to close' if behind > 0 else 'of headroom'})."
            )
        if drivers:
            narrative.append(
                f"Drivers: " + "; ".join(
                    f"'{d.title}' ({d.strength}, {d.direction})" for d in drivers[:3]
                ) + "."
            )
        if at_risk_customers:
            narrative.append(
                f"Customer reality (4G.5): {at_risk_customers} customer(s) at "
                f"risk, {concerned_customers} concerned."
            )
        if goal_chain:
            narrative.append(
                f"Strategy (4G.3): the metric maps to "
                + "; ".join(c["goal"] for c in goal_chain[:2]) + "."
            )
        if at_risk_projects:
            narrative.append(
                f"Execution (4G.1): " + "; ".join(
                    f"{p['name']} ({p['execution_health']})"
                    for p in at_risk_projects[:3]
                ) + "."
            )
        narrative.append(
            "The links above are evidence-backed associations, not proof: "
            "the language reflects how much evidence we hold."
        )
        return {
            "advisory_only": True,
            "target": {
                "target_id": t.id,
                "metric_id": t.metric_id,
                "metric_label": t.metric_label,
                "target_value": t.target_value,
                "current": current,
                "unit": t.unit,
                "period_label": t.period_label,
                "end_at": t.end_at.isoformat(),
                "status": target_status,
                "belief": t.belief,
                "gap": behind,
                "owner_label": t.owner_label,
                "strategy_label": t.strategy_label,
            },
            "metric": {
                "metric_id": metric.id,
                "key": metric.key,
                "label": metric.label,
                "kind": metric.kind,
                "direction": metric.direction,
                "unit": metric.unit,
                "scope": metric.scope,
                "last_observed_at": _iso(metric.last_observed_at) if metric.last_observed_at else "",
            },
            "trajectory": [
                {
                    "value": o.value,
                    "observed_at": _iso(o.observed_at),
                    "label": o.label,
                    "source": o.source,
                }
                for o in observations
            ],
            "drivers": [
                {
                    "driver_key": d.key,
                    "title": d.title,
                    "strength": d.strength,
                    "direction": d.direction,
                    "kind": DRIVER_STRENGTH_KIND.get(d.strength, "evidence_indicates"),
                    "monetized_impact": d.monetized_impact,
                }
                for d in drivers
            ],
            "forecasts": [
                {
                    "forecast_id": f.id,
                    "forecast_type": f.forecast_type,
                    "horizon_label": f.horizon_label,
                    "low": f.low_value,
                    "midpoint": f.midpoint_value,
                    "high": f.high_value,
                    "confidence": f.confidence,
                }
                for f in forecasts
            ],
            "customers": {
                "at_risk": at_risk_customers,
                "concerned": concerned_customers,
                "outcomes_matched": len(matching_outcomes),
                "outcomes_improved": improved_outcomes,
            },
            "knowledge": knowledge_matches,
            "strategy": goal_chain,
            "projects": projects,
            "dependencies": {
                "incidents": incidents,
                "incident_count": len(incidents),
            },
            "capacity": {"bottlenecks": bottlenecks},
            "decisions": {
                "open": open_decisions,
                "open_count": len(open_decisions),
            },
            "expected_outcomes": [
                c["expected_outcome"] for c in goal_chain
                if c["expected_outcome"]
            ],
            "learning": lessons,
            "what_to_do": what_to_do[:MAX_RECOMMENDATIONS],
            "summary": narrative,
            "generated_at": _iso(utcnow()),
        }

    async def recommendations(
        self, db, *, organization_id: str,
    ) -> dict[str, Any]:
        """What should leadership do next — derived deterministically from the
        current org-wide snapshot and the live target ledger. Advisory only,
        bounded, every item carries its evidence."""
        result = await self.performance(
            db, organization_id=organization_id, scope="org_wide",
            compute_mode="observed",
        )
        items = []
        if result is None:
            return {
                "advisory_only": True,
                "total": 0,
                "recommendations": items,
                "note": "No performance evidence yet — record metrics, "
                        "outcomes and targets to ground recommendations.",
            }
        health_dims = result["health"]["dimensions"]
        for d in health_dims:
            if d["state"] not in ("at_risk", "concerned"):
                continue
            for reason in d["reasons"][:1]:
                items.append({
                    "kind": "dimension",
                    "title": f"{d['label']} dimension is {d['state']} ({d['score']}/100)",
                    "why": reason,
                    "evidence_count": d["evidence_count"],
                })
        targets = list(
            (
                await db.execute(
                    select(BusinessTarget).where(
                        BusinessTarget.organization_id == organization_id,
                    ).order_by(BusinessTarget.end_at).limit(MAX_TARGETS_SURFACE)
                )
            ).scalars().all()
        )
        latest_by_metric: dict[str, Optional[float]] = {}
        today = date.today()
        for tt in targets:
            if tt.metric_id not in latest_by_metric:
                obs = (
                    await db.execute(
                        select(BusinessMetricObservation).where(
                            BusinessMetricObservation.organization_id == organization_id,
                            BusinessMetricObservation.metric_id == tt.metric_id,
                            BusinessMetricObservation.label == "actual",
                        ).order_by(BusinessMetricObservation.observed_at.desc()).limit(1)
                    )
                ).scalar_one_or_none()
                latest_by_metric[tt.metric_id] = obs.value if obs else None
        for tt in targets:
            m = (
                await db.execute(
                    select(BusinessMetric).where(
                        BusinessMetric.organization_id == organization_id,
                        BusinessMetric.id == tt.metric_id,
                    )
                )
            ).scalar_one_or_none()
            status = self._eval_target_status(
                tt, latest_by_metric.get(tt.metric_id), today,
                (m.direction if m else "up_is_good"),
            )
            if status not in ("at_risk", "slipped", "missed"):
                continue
            current = latest_by_metric.get(tt.metric_id)
            gap = (tt.target_value - current) if current is not None else None
            gap_txt = f", gap {round(gap, 2)}{tt.unit}" if gap is not None else ""
            items.append({
                "kind": "target",
                "title": (
                    f"Target '{tt.metric_label or (m.label if m else tt.metric_id)}' "
                    f"is {status}"
                ),
                "why": (
                    f"{current}{tt.unit} vs {tt.target_value}{tt.unit} by "
                    f"{tt.end_at.isoformat()}{gap_txt}"
                ),
                "target_id": tt.id,
                "evidence_count": 1,
            })
        bottlenecks = await self._current_bottlenecks(
            db, organization_id=organization_id, limit=3,
        )
        for b in bottlenecks:
            items.append({
                "kind": "capacity",
                "title": f"Capacity bottleneck: {b['capability']}",
                "why": (
                    f"utilization {round(b['utilization'] * 100, 1)}% in "
                    f"{b['window_start']}..{b['window_end']}"
                ),
                "evidence_count": 1,
            })
        items.append({
            "kind": "advisory",
            "title": "Business performance is advisory — decisions stay with people",
            "why": "no autonomous change is ever taken by the engine",
            "evidence_count": 0,
        })
        return {
            "advisory_only": True,
            "total": len(items),
            "recommendations": items[:MAX_RECOMMENDATIONS],
        }


business_performance_engine = BusinessPerformanceEngine()