"""Slice 4G.5 — Customer & Market Execution Intelligence engine.

The customer side of the Living Company Model. The engine is change-driven
and exact-once: customer signals, commitments and outcomes arrive as durable
events, the affected theme aggregate and the affected customer health are
recomputed incrementally, and every surface is advisory with evidence.

The engine reuses the existing company layers instead of re-implementing
them: strategic chains (4G.3), execution state (4G.1), coordination incidents
(4G.2), organizational capability & capacity (4F.6/4G.4), knowledge topics
(4E), patterns (4D) and organizational learning (4E.7).
"""

import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Optional, Sequence

from sqlalchemy import func, or_, select

from app.core.timeutils import ensure_aware, utcnow
from app.models.customer import Customer, CustomerProjectLink
from app.models.customer_intelligence import (
    CustomerCommitment,
    CustomerHealthHistory,
    CustomerHealthRow,
    CustomerOutcome,
    CustomerSignal,
    CustomerTheme,
)
from app.models.execution_coordination import CoordinationIncident
from app.models.execution_intelligence import ProjectExecutionState
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyInitiative,
    CompanyObjective,
    StrategicLink,
)
from app.models.intelligence import PatternDetection
from app.models.knowledge import KnowledgeTopic
from app.models.org_capability_intelligence import OrgCapability
from app.models.project import Project

# ---------------------------------------------------------------------------
# canonical vocabularies & bounds
SIGNAL_TYPES = (
    "feedback", "request", "complaint", "issue", "success",
    "churn_risk", "adoption", "outcome", "expansion",
)
SIGNAL_SEVERITIES = ("info", "low", "medium", "high", "critical")
SIGNAL_SOURCES = (
    "support", "crm", "email", "meeting", "usage", "survey",
    "interview", "account", "observation",
)
COMMITMENT_STATUSES = ("pending", "on_track", "at_risk", "slipped", "delivered")

# Projects whose work can address a customer theme.
ACTIVE_PROJECT_STATUSES = ("active", "in_progress", "planning")

MAX_SIGNALS_SURFACE = 50
MAX_THEMES_SURFACE = 25
MAX_THEME_EVIDENCE_SIGNALS = 200
MAX_THEME_EVIDENCE_CUSTOMERS = 100
MAX_HEALTHS_SURFACE = 500
MAX_HEALTH_HISTORY = 20
MAX_RECENT_SIGNALS_HEALTH = 10
MAX_COMMITMENTS_SURFACE = 300
MAX_OUTCOMES_SURFACE = 100
MAX_KNOWLEDGE_LINKS = 10
MAX_PATTERN_LINKS = 10
MAX_LESSON_LINKS = 5
MAX_PROJECT_LINKS = 400
MAX_GOAL_CHAIN = 8
MAX_RECOMMENDATIONS = 3
MAX_GOALS_SCAN = 200
MAX_KNOWLEDGE_TOPICS = 500
MAX_SIGNALS_SCAN = 400

HEALTHY_THRESHOLD = 75
CONCERNED_THRESHOLD = 50
NEGATIVE_DAYS = 30
TREND_DAYS = 30

# Signal kinds that count against / for a customer's health.
NEGATIVE_SIGNAL_TYPES = frozenset(("issue", "complaint", "churn_risk"))
POSITIVE_SIGNAL_TYPES = frozenset(("success", "adoption", "outcome", "expansion"))

# Canonical need groups: key -> (title, keywords). Order = resolution order.
NEED_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "sso": ("single sign-on", ("sso", "single sign-on", "single sign on",
                               "identity provider", "okta", "saml", "oidc", "idp")),
    "audit": ("audit logs", ("audit log", "audit trail", "compliance export",
                             "compliance reporting", "audit")),
    "onboarding": ("onboarding", ("onboard", "onboarding", "implementation delay",
                                  "implementation was slow", "deployment was slow",
                                  "getting started", "ramp up", "set up")),
    "reporting": ("reporting", ("report", "reporting", "dashboard", "analytics")),
    "admin": ("admin controls", ("admin control", "rbac", "role-based", "role based",
                                 "permissions", "user management")),
    "mobile": ("mobile workflow", ("mobile", "ios", "android")),
    "localization": ("localization", ("localiz", "i18n", "l10n", "translation",
                                      "languages")),
    "api": ("api & integrations", ("api", "webhook", "connector", "integration")),
    "performance": ("performance", ("slow", "latency", "performance", "laggy",
                                    "takes too long")),
    "support": ("support experience", ("support", "response time", "service level",
                                       "escalat")),
    "security": ("security", ("security", "vulnerability", "penetration", "breach",
                              "security audit")),
    "availability": ("availability", ("uptime", "outage", "downtime", "availability",
                                      "disaster recovery")),
    "billing": ("billing & pricing", ("billing", "invoice", "pricing", "cost",
                                      "license")),
}
GENERAL_NEED = "general"


def _resolve_need(need: Optional[str], text: str) -> tuple[str, str]:
    """Resolve a signal to its canonical need: explicit need wins, else the
    first deterministic keyword group that matches the signal text."""
    if need:
        key = need.strip().lower().replace(" ", "-")[:120]
        if not key:
            key = GENERAL_NEED
        title = NEED_GROUPS.get(key, (None, None))[0] or need.strip()[:200]
        return key, title
    lowered = (text or "").lower()
    for key, (title, keywords) in NEED_GROUPS.items():
        if any(kw in lowered for kw in keywords):
            return key, title
    return GENERAL_NEED, "general"


def _theme_tokens(key: str, title: str) -> list[str]:
    """Tokens used to match a theme against goals/capabilities/knowledge."""
    tokens = [key]
    lowered = (key + " " + title).lower()
    for kw_group, (_, keywords) in NEED_GROUPS.items():
        if kw_group == key or kw_group in lowered or any(kw in lowered for kw in keywords[:1]):
            tokens.extend(keywords[:4])
            break
    return list(dict.fromkeys(t for t in tokens if len(t) >= 3))


def _iso_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


class CustomerIntelligenceEngine:
    """Canonical Customer & Market Execution Intelligence - one engine."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------ write

    async def record_event(
        self, db, *, organization_id: str,
        event, payload: dict[str, Any],
    ) -> None:
        """Change-driven entry: exact-once capture, then recompute ONLY the
        affected theme aggregate and the affected customer health."""
        event_name = getattr(event, "name", "")
        source_event_id = getattr(event, "id", None)
        if not event_name or not source_event_id:
            return
        customer_id = (payload.get("customer_id") or "").strip()
        if not customer_id:
            return

        if event_name == "customer.signal.recorded":
            await self._apply_signal(
                db, organization_id=organization_id,
                payload=payload, source_event_id=source_event_id,
            )
        elif event_name == "customer.signal.resolved":
            await self._apply_signal_resolved(
                db, organization_id=organization_id,
                payload=payload, source_event_id=source_event_id,
            )
        elif event_name == "customer.commitment.created":
            await self._apply_commitment(
                db, organization_id=organization_id,
                payload=payload, source_event_id=source_event_id,
            )
        elif event_name == "customer.commitment.updated":
            await self._apply_commitment_change(
                db, organization_id=organization_id,
                payload=payload, source_event_id=source_event_id,
            )
        elif event_name == "customer.commitment.delivered":
            await self._apply_commitment_delivered(
                db, organization_id=organization_id,
                payload=payload, source_event_id=source_event_id,
            )
        elif event_name == "customer.outcome.recorded":
            await self._apply_outcome(
                db, organization_id=organization_id,
                payload=payload, source_event_id=source_event_id,
            )
        else:
            return

        # incremental: refresh the affected neighborhood
        key = (payload.get("need_key") or "").strip()
        if event_name == "customer.signal.recorded" and key:
            await self._refresh_theme(db, organization_id=organization_id, key=key)
        if event_name == "customer.signal.resolved":
            sig_id = (payload.get("signal_id") or "").strip()
            if sig_id:
                need_key = (
                    await db.execute(
                        select(CustomerSignal.need_key).where(
                            CustomerSignal.organization_id == organization_id,
                            CustomerSignal.id == sig_id,
                        )
                    )
                ).scalar_one_or_none()
                if need_key:
                    await self._refresh_theme(
                        db, organization_id=organization_id, key=need_key,
                    )
        if event_name == "customer.outcome.recorded":
            sig_id = (payload.get("signal_id") or "").strip()
            if sig_id:
                need_key = (
                    await db.execute(
                        select(CustomerSignal.need_key).where(
                            CustomerSignal.organization_id == organization_id,
                            CustomerSignal.id == sig_id,
                        )
                    )
                ).scalar_one_or_none()
                if need_key:
                    await self._refresh_theme(
                        db, organization_id=organization_id, key=need_key,
                    )
        await self._refresh_health(
            db, organization_id=organization_id, customer_id=customer_id,
            source_event_id=source_event_id,
        )

    # -------------------------------------------------------------- applies

    async def _apply_signal(self, db, *, organization_id, payload, source_event_id):
        customer_id = payload["customer_id"]
        existing = (
            await db.execute(
                select(CustomerSignal.id).where(
                    CustomerSignal.organization_id == organization_id,
                    CustomerSignal.customer_id == customer_id,
                    CustomerSignal.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return
        signal_type = (payload.get("signal_type") or "feedback").strip()[:24]
        if signal_type not in SIGNAL_TYPES:
            signal_type = "feedback"
        severity = (payload.get("severity") or "medium").strip()[:12]
        if severity not in SIGNAL_SEVERITIES:
            severity = "medium"
        source = (payload.get("source") or "observation").strip()[:24]
        if source not in SIGNAL_SOURCES:
            source = "observation"
        title = (payload.get("title") or payload.get("summary") or "").strip()[:300]
        if not title:
            title = f"{signal_type} signal"
        body = (payload.get("body") or "")[:4000] or None
        project_id = (payload.get("project_id") or "").strip()[:32] or None
        occurred_at = payload.get("occurred_at")
        if isinstance(occurred_at, str):
            try:
                occurred_at = datetime.fromisoformat(occurred_at)
            except ValueError:
                occurred_at = None
        if occurred_at is None:
            occurred_at = utcnow()
        need_key, need_title = _resolve_need(
            (payload.get("need") or "").strip(), f"{title} {body or ''}"
        )
        db.add(CustomerSignal(
            organization_id=organization_id, customer_id=customer_id,
            signal_type=signal_type, severity=severity,
            need_key=need_key, title=title, body=body, source=source,
            project_id=project_id,
            status=(payload.get("status") or "open").strip()[:16] or "open",
            occurred_at=occurred_at, source_event_id=source_event_id,
        ))
        await db.flush()
        payload["need_key"] = need_key
        payload["need_title"] = need_title

    async def _apply_signal_resolved(self, db, *, organization_id, payload, source_event_id):
        signal_id = (payload.get("signal_id") or "").strip()
        if not signal_id:
            return
        row = (
            await db.execute(
                select(CustomerSignal).where(
                    CustomerSignal.organization_id == organization_id,
                    CustomerSignal.id == signal_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        if row.status in ("resolved", "closed"):
            return
        row.status = "resolved"
        await db.flush()

    async def _apply_commitment(self, db, *, organization_id, payload, source_event_id):
        customer_id = payload["customer_id"]
        existing = (
            await db.execute(
                select(CustomerCommitment.id).where(
                    CustomerCommitment.organization_id == organization_id,
                    CustomerCommitment.customer_id == customer_id,
                    CustomerCommitment.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return
        expected = _iso_date(payload.get("expected_at"))
        if expected is None:
            return
        status = (payload.get("status") or "on_track").strip()[:16]
        if status not in COMMITMENT_STATUSES:
            status = "on_track"
        db.add(CustomerCommitment(
            organization_id=organization_id, customer_id=customer_id,
            summary=(payload.get("summary") or "commitment")[:300],
            expected_at=expected, status=status,
            project_id=(payload.get("project_id") or "").strip()[:32] or None,
            capability=(payload.get("capability") or "").strip()[:120] or None,
            owner_label=(payload.get("owner_label") or "").strip()[:200] or None,
            note=(payload.get("note") or "")[:4000] or None,
            changed_at=utcnow(), source_event_id=source_event_id,
        ))
        await db.flush()
        payload["commitment_id"] = None

    async def _apply_commitment_change(self, db, *, organization_id, payload, source_event_id):
        commitment_id = (payload.get("commitment_id") or "").strip()
        if not commitment_id:
            return
        row = (
            await db.execute(
                select(CustomerCommitment).where(
                    CustomerCommitment.organization_id == organization_id,
                    CustomerCommitment.id == commitment_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        status = (payload.get("status") or "").strip()
        if status in COMMITMENT_STATUSES:
            row.status = status
        summary = (payload.get("summary") or "").strip()
        if summary:
            row.summary = summary[:300]
        expected = _iso_date(payload.get("expected_at"))
        if expected is not None:
            row.expected_at = expected
        capability = (payload.get("capability") or "").strip()
        if capability:
            row.capability = capability[:120]
        row.changed_at = utcnow()
        await db.flush()
        payload["commitment_id"] = commitment_id
        payload["old_status"] = payload.get("old_status")

    async def _apply_commitment_delivered(self, db, *, organization_id, payload, source_event_id):
        commitment_id = (payload.get("commitment_id") or "").strip()
        if not commitment_id:
            return
        row = (
            await db.execute(
                select(CustomerCommitment).where(
                    CustomerCommitment.organization_id == organization_id,
                    CustomerCommitment.id == commitment_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        if row.status == "delivered":
            return
        row.status = "delivered"
        row.changed_at = utcnow()
        if payload.get("note"):
            row.note = (payload.get("note") or "")[:4000]
        await db.flush()
        payload["commitment_id"] = commitment_id
        payload["customer_id"] = row.customer_id

    async def _apply_outcome(self, db, *, organization_id, payload, source_event_id):
        customer_id = payload["customer_id"]
        existing = (
            await db.execute(
                select(CustomerOutcome.id).where(
                    CustomerOutcome.organization_id == organization_id,
                    CustomerOutcome.customer_id == customer_id,
                    CustomerOutcome.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            await self._capture_outcome_learning(
                db, organization_id=organization_id,
                source_event_id=source_event_id, payload=payload,
            )
            return
        signal_id = (payload.get("signal_id") or "").strip()[:32] or None
        db.add(CustomerOutcome(
            organization_id=organization_id, customer_id=customer_id,
            metric_kind=(payload.get("metric_kind") or "metric")[:60],
            baseline=payload.get("baseline"),
            target=payload.get("target"),
            actual=float(payload.get("actual") or 0.0),
            unit=(payload.get("unit") or "")[:20],
            period_label=(payload.get("period_label") or "")[:80] or None,
            signal_id=signal_id,
            note=(payload.get("note") or "")[:4000] or None,
            recorded_at=utcnow(), source_event_id=source_event_id,
        ))
        if signal_id:
            signal = (
                await db.execute(
                    select(CustomerSignal).where(
                        CustomerSignal.organization_id == organization_id,
                        CustomerSignal.id == signal_id,
                    )
                )
            ).scalar_one_or_none()
            if signal is not None and signal.status in ("open", "acknowledged"):
                signal.status = "resolved"
        await self._capture_outcome_learning(
            db, organization_id=organization_id,
            source_event_id=source_event_id, payload=payload,
        )
        await db.flush()

    async def _capture_outcome_learning(
        self, db, *, organization_id, source_event_id, payload,
    ) -> None:
        """Outcome -> learning pours into the 4E.7 organizational learning
        engine: VCOS gets smarter from its own customer outcome history."""
        baseline = payload.get("baseline")
        actual = payload.get("actual")
        target = payload.get("target")
        try:
            from app.intelligence.learning_engine import learning_engine

            lesson_parts = [
                f"'{payload.get('metric_kind')}' moved "
                f"{baseline} -> {actual}" if baseline is not None else
                f"'{payload.get('metric_kind')}' reached {actual}"
            ]
            if target is not None and baseline is not None:
                better = abs(actual - target) < abs(baseline - target)
                lesson_parts.append("toward target" if better else "away from target")
            await learning_engine.record(
                db, organization_id=organization_id,
                event_type="customer.outcome",
                title=f"Customer outcome: {payload.get('metric_kind')}",
                detail=(
                    f"metric {payload.get('metric_kind')} baseline {baseline} "
                    f"actual {actual} target {target}"
                ),
                lesson=" ".join(lesson_parts),
                entity_type="customer",
                entity_id=payload.get("customer_id") or "",
                tags=["customer", "4g5"],
            )
        except Exception:
            from app.core.logging import logger

            logger.exception("customer outcome learning failed")

    # ------------------------------------------------------- incremental

    async def _refresh_theme(self, db, *, organization_id: str, key: str) -> None:
        """Recompute ONE theme aggregate from the signal ledger (bounded to
        the latest evidence, but counts are exact over the ledger)."""
        if not key:
            return
        rows = list(
            (
                await db.execute(
                    select(CustomerSignal).where(
                        CustomerSignal.organization_id == organization_id,
                        CustomerSignal.need_key == key,
                    ).order_by(CustomerSignal.occurred_at.desc())
                )
            ).scalars().all()
        )
        if not rows:
            return
        occurrences = len(rows)
        customers: list[str] = []
        customer_set: set[str] = set()
        open_count = 0
        high_sev = 0
        for r in rows:
            if r.customer_id not in customer_set:
                customer_set.add(r.customer_id)
                customers.append(r.customer_id)
            if r.status in ("open", "acknowledged"):
                open_count += 1
            if r.severity in ("high", "critical"):
                high_sev += 1
        first_at = min(r.occurred_at for r in rows)
        latest_at = max(r.occurred_at for r in rows)
        now = utcnow()
        recent = sum(
            1 for r in rows
            if now - ensure_aware(r.occurred_at) <= timedelta(days=TREND_DAYS)
        )
        prior = sum(
            1 for r in rows
            if timedelta(days=TREND_DAYS)
            < now - ensure_aware(r.occurred_at)
            <= timedelta(days=2 * TREND_DAYS)
        )
        if recent > prior:
            trend = "worsening"
        elif recent < prior:
            trend = "improving"
        else:
            trend = "stable"
        theme = (
            await db.execute(
                select(CustomerTheme).where(
                    CustomerTheme.organization_id == organization_id,
                    CustomerTheme.key == key,
                )
            )
        ).scalar_one_or_none()
        title = NEED_GROUPS.get(key, (key, None))[0] or key
        signal_ids = [r.id for r in rows[:MAX_THEME_EVIDENCE_SIGNALS]]
        customer_ids = customers[:MAX_THEME_EVIDENCE_CUSTOMERS]
        if theme is None:
            theme = CustomerTheme(
                organization_id=organization_id, key=key, title=title,
                occurrences=occurrences, customer_count=len(customer_set),
                open_count=open_count, high_severity_count=high_sev,
                signal_ids_json=signal_ids, customer_ids_json=customer_ids,
                trend=trend, first_at=first_at, latest_at=latest_at,
            )
            db.add(theme)
        else:
            theme.title = title
            theme.occurrences = occurrences
            theme.customer_count = len(customer_set)
            theme.open_count = open_count
            theme.high_severity_count = high_sev
            theme.signal_ids_json = signal_ids
            theme.customer_ids_json = customer_ids
            theme.trend = trend
            theme.first_at = first_at
            theme.latest_at = latest_at
        await db.flush()

    async def _refresh_health(
        self, db, *, organization_id: str, customer_id: str,
        source_event_id: str,
    ) -> None:
        """Recompute ONE customer's health from the canonical ledger and
        append a temporal history row when the state materially changed
        (exact-once on the source event)."""
        now = utcnow()
        window_start = now - timedelta(days=NEGATIVE_DAYS)
        signals = list(
            (
                await db.execute(
                    select(CustomerSignal).where(
                        CustomerSignal.organization_id == organization_id,
                        CustomerSignal.customer_id == customer_id,
                    ).order_by(CustomerSignal.occurred_at.desc())
                )
            ).scalars().all()
        )
        commitments = list(
            (
                await db.execute(
                    select(CustomerCommitment).where(
                        CustomerCommitment.organization_id == organization_id,
                        CustomerCommitment.customer_id == customer_id,
                    ).order_by(CustomerCommitment.expected_at)
                )
            ).scalars().all()
        )
        outcomes = list(
            (
                await db.execute(
                    select(CustomerOutcome).where(
                        CustomerOutcome.organization_id == organization_id,
                        CustomerOutcome.customer_id == customer_id,
                    ).order_by(CustomerOutcome.recorded_at.desc())
                )
            ).scalars().all()
        )
        today = date.today()

        unresolved_critical = sum(
            1 for s in signals
            if s.status in ("open", "acknowledged") and s.severity in ("high", "critical")
        )
        negative_30d = sum(
            1 for s in signals
            if s.signal_type in NEGATIVE_SIGNAL_TYPES
            and ensure_aware(s.occurred_at) >= window_start
        )
        positive_30d = sum(
            1 for s in signals
            if s.signal_type in POSITIVE_SIGNAL_TYPES
            and ensure_aware(s.occurred_at) >= window_start
        )
        at_risk_commitments = [
            c for c in commitments if c.status in ("at_risk", "slipped")
        ]
        overdue = [
            c for c in commitments
            if c.expected_at < today and c.status not in ("delivered",)
        ]
        improved_outcomes = 0
        for o in outcomes:
            if o.baseline is not None and o.target is not None and o.actual is not None:
                if abs(o.actual - o.target) < abs(o.baseline - o.target):
                    improved_outcomes += 1

        reasons: list[str] = []
        positives: list[str] = []
        if unresolved_critical:
            reasons.append(
                f"{unresolved_critical} unresolved critical signal(s)"
            )
        if negative_30d:
            reasons.append(f"{negative_30d} negative signal(s) in the last 30 days")
        for c in at_risk_commitments:
            label = (c.summary or "commitment")[:60]
            reasons.append(
                f"commitment '{label}' is {c.status} (expected {c.expected_at.isoformat()})"
            )
        for c in overdue[:2]:
            label = (c.summary or "commitment")[:60]
            reasons.append(f"commitment '{label}' is overdue")
        if positive_30d:
            positives.append(f"{positive_30d} positive signal(s) in the last 30 days")
        if improved_outcomes:
            positives.append(f"{improved_outcomes} outcome(s) improved toward target")

        project_ids = [s.project_id for s in signals if s.project_id]
        project_ids += [c.project_id for c in commitments if c.project_id]
        project_ids = list(dict.fromkeys(pid for pid in project_ids if pid))
        project_health = {}
        if project_ids:
            states = list(
                (
                    await db.execute(
                        select(ProjectExecutionState).where(
                            ProjectExecutionState.organization_id == organization_id,
                            ProjectExecutionState.project_id.in_(project_ids),
                        )
                    )
                ).scalars().all()
            )
            project_health = {s.project_id: s for s in states}
        projects_at_risk = 0
        for pid in project_ids:
            st = project_health.get(pid)
            if st is not None and st.health_status in ("at_risk", "critical"):
                projects_at_risk += 1

        score = 100
        score -= unresolved_critical * 12
        score -= negative_30d * 5
        score -= len(at_risk_commitments) * 10
        score -= len(overdue) * 8
        score -= projects_at_risk * 8
        score += positive_30d * 4
        score += improved_outcomes * 6
        score = max(0, min(100, score))
        if score >= HEALTHY_THRESHOLD:
            state = "healthy"
        elif score >= CONCERNED_THRESHOLD:
            state = "concerned"
        else:
            state = "at_risk"

        row = (
            await db.execute(
                select(CustomerHealthRow).where(
                    CustomerHealthRow.organization_id == organization_id,
                    CustomerHealthRow.customer_id == customer_id,
                )
            )
        ).scalar_one_or_none()
        factors = {
            "signals": len(signals),
            "unresolved_critical": unresolved_critical,
            "negative_30d": negative_30d,
            "positive_30d": positive_30d,
            "commitments": len(commitments),
            "commitments_at_risk": len(at_risk_commitments),
            "overdue_commitments": len(overdue),
            "outcomes": len(outcomes),
            "improved_outcomes": improved_outcomes,
            "projects_at_risk": projects_at_risk,
        }
        if row is None:
            row = CustomerHealthRow(
                organization_id=organization_id, customer_id=customer_id,
                state=state, score=score,
                reasons_json=reasons[:5], positives_json=positives[:5],
                factors_json=factors, computed_at=now,
                source_event_id=source_event_id,
            )
            db.add(row)
        else:
            changed = row.state != state or abs(row.score - score) >= 5
            row.state = state
            row.score = score
            row.reasons_json = reasons[:5]
            row.positives_json = positives[:5]
            row.factors_json = factors
            row.computed_at = now
            row.source_event_id = source_event_id
            if not changed:
                return
        # temporal trail (exact-once on the source event)
        history_exists = (
            await db.execute(
                select(CustomerHealthHistory.id).where(
                    CustomerHealthHistory.organization_id == organization_id,
                    CustomerHealthHistory.customer_id == customer_id,
                    CustomerHealthHistory.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none()
        if history_exists:
            return
        db.add(CustomerHealthHistory(
            organization_id=organization_id, customer_id=customer_id,
            state=state, score=score,
            reasons_json=reasons[:5], positives_json=positives[:5],
            occurred_at=now, source_event_id=source_event_id,
        ))
        await db.flush()

    # ------------------------------------------------------------- reads

    async def signals(
        self, db, *, organization_id: str, signal_type: Optional[str] = None,
        customer_id: Optional[str] = None, need: Optional[str] = None,
        severity: Optional[str] = None, limit: int = MAX_SIGNALS_SURFACE,
    ) -> dict[str, Any]:
        """The signal ledger: recent canonical signals with their evidence."""
        q = select(CustomerSignal).where(
            CustomerSignal.organization_id == organization_id,
        )
        conds = [CustomerSignal.organization_id == organization_id]
        if signal_type in SIGNAL_TYPES:
            q = q.where(CustomerSignal.signal_type == signal_type)
            conds.append(CustomerSignal.signal_type == signal_type)
        if customer_id:
            q = q.where(CustomerSignal.customer_id == customer_id)
            conds.append(CustomerSignal.customer_id == customer_id)
        if need:
            q = q.where(CustomerSignal.need_key == need)
            conds.append(CustomerSignal.need_key == need)
        if severity in SIGNAL_SEVERITIES:
            q = q.where(CustomerSignal.severity == severity)
            conds.append(CustomerSignal.severity == severity)
        rows = list(
            (
                await db.execute(
                    q.order_by(CustomerSignal.occurred_at.desc()).limit(
                        min(max(limit, 1), MAX_SIGNALS_SURFACE)
                    )
                )
            ).scalars().all()
        )
        customers = await self._customers_by_id(db, organization_id=organization_id)
        items = [
            {
                "signal_id": r.id,
                "customer_id": r.customer_id,
                "customer": (customers.get(r.customer_id) or {}).get("name", ""),
                "signal_type": r.signal_type,
                "severity": r.severity,
                "need_key": r.need_key,
                "title": r.title,
                "source": r.source,
                "project_id": r.project_id,
                "status": r.status,
                "occurred_at": _iso(r.occurred_at),
            }
            for r in rows
        ]
        total = (
            await db.execute(
                select(func.count(CustomerSignal.id)).where(*conds)
            )
        ).scalar_one() or 0
        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for r in rows:
            by_type[r.signal_type] = by_type.get(r.signal_type, 0) + 1
            by_severity[r.severity] = by_severity.get(r.severity, 0) + 1
        return {
            "advisory_only": True,
            "total": total,
            "signals": items,
            "by_type": by_type,
            "by_severity": by_severity,
        }

    async def themes(self, db, *, organization_id: str) -> dict[str, Any]:
        """Customer need aggregation: each theme keeps its evidence (signal
        and customer ids) so no signal disappears into a summary."""
        rows = list(
            (
                await db.execute(
                    select(CustomerTheme).where(
                        CustomerTheme.organization_id == organization_id,
                    ).order_by(
                        CustomerTheme.occurrences.desc(),
                        CustomerTheme.latest_at.desc(),
                    ).limit(MAX_THEMES_SURFACE)
                )
            ).scalars().all()
        )
        signals = await self._signals_by_id(db, organization_id=organization_id)
        customers = await self._customers_by_id(db, organization_id=organization_id)
        items = []
        for r in rows:
            evidence_signals = []
            for sid in (r.signal_ids_json or [])[:10]:
                s = signals.get(sid)
                if s is None:
                    continue
                evidence_signals.append({
                    "signal_id": s.id,
                    "customer": (customers.get(s.customer_id) or {}).get("name", ""),
                    "signal_type": s.signal_type,
                    "severity": s.severity,
                    "title": s.title,
                    "occurred_at": _iso(s.occurred_at),
                })
            items.append({
                "key": r.key,
                "title": r.title,
                "occurrences": r.occurrences,
                "customers": r.customer_count,
                "open": r.open_count,
                "high_severity": r.high_severity_count,
                "trend": r.trend,
                "first_at": _iso(r.first_at) if r.first_at else "",
                "latest_at": _iso(r.latest_at) if r.latest_at else "",
                "evidence": evidence_signals,
            })
        return {"advisory_only": True, "themes": items}

    async def healths(self, db, *, organization_id: str) -> dict[str, Any]:
        """Customer health: every customer's evidence-backed state with the
        why (never a bare score)."""
        rows = list(
            (
                await db.execute(
                    select(CustomerHealthRow).where(
                        CustomerHealthRow.organization_id == organization_id,
                    ).order_by(
                        CustomerHealthRow.score.asc(),
                        CustomerHealthRow.computed_at.desc(),
                    ).limit(MAX_HEALTHS_SURFACE)
                )
            ).scalars().all()
        )
        customers = await self._customers_by_id(db, organization_id=organization_id)
        items = [
            {
                "customer_id": r.customer_id,
                "customer": (customers.get(r.customer_id) or {}).get("name", ""),
                "segment": (customers.get(r.customer_id) or {}).get("segment", ""),
                "tier": (customers.get(r.customer_id) or {}).get("tier", ""),
                "state": r.state,
                "score": r.score,
                "reasons": r.reasons_json or [],
                "positives": r.positives_json or [],
                "computed_at": _iso(r.computed_at) if r.computed_at else "",
            }
            for r in rows
        ]
        return {
            "advisory_only": True,
            "total": len(items),
            "at_risk": sum(1 for i in items if i["state"] == "at_risk"),
            "concerned": sum(1 for i in items if i["state"] == "concerned"),
            "healthy": sum(1 for i in items if i["state"] == "healthy"),
            "health": items,
        }

    async def health(self, db, *, organization_id: str, customer_id: str) -> Optional[dict[str, Any]]:
        """One customer's full health detail: state, why, positives, factors
        and the temporal history trail."""
        row = (
            await db.execute(
                select(CustomerHealthRow).where(
                    CustomerHealthRow.organization_id == organization_id,
                    CustomerHealthRow.customer_id == customer_id,
                )
            )
        ).scalar_one_or_none()
        customer = (
            await db.execute(
                select(Customer).where(
                    Customer.organization_id == organization_id,
                    Customer.id == customer_id,
                )
            )
        ).scalar_one_or_none()
        if customer is None:
            return None
        history = list(
            (
                await db.execute(
                    select(CustomerHealthHistory).where(
                        CustomerHealthHistory.organization_id == organization_id,
                        CustomerHealthHistory.customer_id == customer_id,
                    ).order_by(CustomerHealthHistory.occurred_at.desc()).limit(MAX_HEALTH_HISTORY)
                )
            ).scalars().all()
        )
        return {
            "advisory_only": True,
            "customer_id": customer.id,
            "customer": customer.company_name,
            "segment": customer.segment,
            "tier": customer.tier,
            "state": (row.state if row else "healthy"),
            "score": (row.score if row else 100),
            "reasons": (row.reasons_json if row else []),
            "positives": (row.positives_json if row else []),
            "factors": (row.factors_json if row else {}),
            "history": [
                {
                    "state": h.state, "score": h.score,
                    "reasons": h.reasons_json or [],
                    "occurred_at": _iso(h.occurred_at),
                }
                for h in history
            ],
            "generated_at": _iso(row.computed_at) if row and row.computed_at else "",
        }

    async def risk(self, db, *, organization_id: str) -> dict[str, Any]:
        """Customer risk: at-risk customers with reasons, and the propagation
        of project delay -> commitment -> customer -> strategic goal."""
        health_rows = list(
            (
                await db.execute(
                    select(CustomerHealthRow).where(
                        CustomerHealthRow.organization_id == organization_id,
                        CustomerHealthRow.state.in_(("at_risk", "concerned")),
                    ).order_by(CustomerHealthRow.score.asc()).limit(MAX_HEALTHS_SURFACE)
                )
            ).scalars().all()
        )
        customers = await self._customers_by_id(db, organization_id=organization_id)
        at_risk_customers = []
        for r in health_rows:
            meta = customers.get(r.customer_id) or {}
            at_risk_customers.append({
                "customer_id": r.customer_id,
                "customer": meta.get("name", ""),
                "segment": meta.get("segment", ""),
                "tier": meta.get("tier", ""),
                "state": r.state,
                "score": r.score,
                "reasons": (r.reasons_json or [])[:4],
            })
        at_risk_customer_ids = {r.customer_id for r in health_rows}
        commitments = list(
            (
                await db.execute(
                    select(CustomerCommitment).where(
                        CustomerCommitment.organization_id == organization_id,
                    ).order_by(CustomerCommitment.expected_at).limit(MAX_COMMITMENTS_SURFACE)
                )
            ).scalars().all()
        )
        project_ids = [c.project_id for c in commitments if c.project_id]
        projects = await self._projects_by_id(db, organization_id=organization_id, ids=project_ids)
        states = await self._project_states(db, organization_id=organization_id, project_ids=project_ids)
        commitments_at_risk = []
        for c in commitments:
            st = states.get(c.project_id)
            propagated = (
                c.status in ("at_risk", "slipped")
                or c.customer_id in at_risk_customer_ids
                or (st is not None and st.health_status in ("at_risk", "critical"))
            )
            if not propagated:
                continue
            pid = c.project_id
            proj = projects.get(pid) or {}
            goal_chain = await self._goal_chain_for_project(db, organization_id=organization_id, project_id=pid) if pid else []
            commitments_at_risk.append({
                "commitment_id": c.id,
                "customer_id": c.customer_id,
                "customer": (customers.get(c.customer_id) or {}).get("name", ""),
                "summary": c.summary,
                "expected_at": c.expected_at.isoformat(),
                "status": c.status,
                "project_id": pid,
                "project": proj.get("name", ""),
                "project_health": (st.health_status if st else "unknown"),
                "capability": c.capability,
                "goals": goal_chain,
            })
        return {
            "advisory_only": True,
            "at_risk_customers": at_risk_customers,
            "commitments_at_risk": commitments_at_risk,
            "propagation_note": (
                "A delayed project propagates to the customer commitments "
                "linked to it, then to the strategic goals above it."
            ),
        }

    async def commitments(
        self, db, *, organization_id: str, status: Optional[str] = None,
    ) -> dict[str, Any]:
        """The commitment ledger: what we promised, to whom, when, and what
        project + capability stands behind it."""
        q = select(CustomerCommitment).where(
            CustomerCommitment.organization_id == organization_id,
        )
        if status in COMMITMENT_STATUSES:
            q = q.where(CustomerCommitment.status == status)
        rows = list(
            (
                await db.execute(
                    q.order_by(CustomerCommitment.expected_at).limit(MAX_COMMITMENTS_SURFACE)
                )
            ).scalars().all()
        )
        customers = await self._customers_by_id(db, organization_id=organization_id)
        project_ids = [r.project_id for r in rows if r.project_id]
        projects = await self._projects_by_id(db, organization_id=organization_id, ids=project_ids)
        states = await self._project_states(db, organization_id=organization_id, project_ids=project_ids)
        caps = await self._capabilities_by_name(db, organization_id=organization_id)
        today = date.today()
        items = []
        for r in rows:
            pid = r.project_id
            st = states.get(pid)
            cap = caps.get((r.capability or "").lower())
            items.append({
                "commitment_id": r.id,
                "customer_id": r.customer_id,
                "customer": (customers.get(r.customer_id) or {}).get("name", ""),
                "summary": r.summary,
                "expected_at": r.expected_at.isoformat(),
                "days_left": (r.expected_at - today).days,
                "status": r.status,
                "project_id": pid,
                "project": (projects.get(pid) or {}).get("name", ""),
                "project_health": (st.health_status if st else "unknown"),
                "capability": r.capability,
                "capacity_state": (cap.capacity_state if cap else "unknown"),
                "owner_label": r.owner_label,
            })
        return {
            "advisory_only": True,
            "total": len(items),
            "at_risk": sum(1 for i in items if i["status"] in ("at_risk", "slipped")),
            "delivered": sum(1 for i in items if i["status"] == "delivered"),
            "commitments": items,
        }

    async def outcomes(self, db, *, organization_id: str) -> dict[str, Any]:
        """Customer outcome records: baseline -> actual per metric, with the
        improvement direction when a target exists."""
        rows = list(
            (
                await db.execute(
                    select(CustomerOutcome).where(
                        CustomerOutcome.organization_id == organization_id,
                    ).order_by(CustomerOutcome.recorded_at.desc()).limit(MAX_OUTCOMES_SURFACE)
                )
            ).scalars().all()
        )
        customers = await self._customers_by_id(db, organization_id=organization_id)
        items = []
        improved = 0
        for r in rows:
            better = None
            if r.baseline is not None and r.target is not None and r.actual is not None:
                better = abs(r.actual - r.target) < abs(r.baseline - r.target)
                if better:
                    improved += 1
            items.append({
                "outcome_id": r.id,
                "customer_id": r.customer_id,
                "customer": (customers.get(r.customer_id) or {}).get("name", ""),
                "metric_kind": r.metric_kind,
                "baseline": r.baseline,
                "target": r.target,
                "actual": r.actual,
                "unit": r.unit,
                "period_label": r.period_label,
                "signal_id": r.signal_id,
                "improved": better,
                "note": r.note,
                "recorded_at": _iso(r.recorded_at),
            })
        return {
            "advisory_only": True,
            "total": len(items),
            "improved": improved,
            "outcomes": items,
        }

    async def impact(self, db, *, organization_id: str) -> dict[str, Any]:
        """Explainable customer impact scoring per theme. Every factor is a
        listed, evidence-backed number; the tier is a deterministic function
        of them. Never a mysterious score."""
        theme_rows = list(
            (
                await db.execute(
                    select(CustomerTheme).where(
                        CustomerTheme.organization_id == organization_id,
                    ).order_by(
                        CustomerTheme.occurrences.desc(),
                        CustomerTheme.latest_at.desc(),
                    ).limit(MAX_THEMES_SURFACE)
                )
            ).scalars().all()
        )
        customers = await self._customers_by_id(db, organization_id=organization_id)
        goals = await self._active_goals(db, organization_id=organization_id)
        addressing = await self._addressing_projects(db, organization_id=organization_id)
        now = utcnow()
        items = []
        for r in theme_rows:
            signals = await self._signals_of_theme(db, organization_id=organization_id, key=r.key)
            involved = [customers.get(cid) or {} for cid in (r.customer_ids_json or [])]
            strategic_accounts = sum(
                1 for m in involved
                if m.get("tier") in ("enterprise", "platinum", "gold")
                or m.get("segment") == "enterprise"
            )
            high_sev = r.high_severity_count
            relevance = 0
            matched_goal = None
            tokens = _theme_tokens(r.key, r.title)
            for g in goals:
                haystack = (g.get("title", "") + " " + " ".join(g.get("capabilities", []))).lower()
                if any(t in haystack for t in tokens):
                    relevance = 1
                    matched_goal = g
                    break
            days_since = (now - ensure_aware(r.latest_at)).days if r.latest_at else 999
            if days_since < 14:
                recency = 3
            elif days_since < 30:
                recency = 2
            else:
                recency = 1
            addressed = bool(addressing.get(r.key))
            score = (
                r.occurrences
                + high_sev * 2
                + strategic_accounts * 2
                + relevance * 4
                + recency
                + (0 if addressed else 3)
                + (1 if r.trend == "worsening" else 0)
            )
            tier = "high" if score >= 25 else "medium" if score >= 12 else "low"
            explanation = [
                f"recurred {r.occurrences} time(s) across {r.customer_count} customer(s)",
            ]
            if high_sev:
                explanation.append(f"{high_sev} high-severity signal(s)")
            if strategic_accounts:
                explanation.append(f"{strategic_accounts} strategic account(s)")
            if matched_goal:
                explanation.append(f"matches active goal '{matched_goal['title'][:80]}'")
            if not addressed:
                explanation.append("no active initiative addresses it")
            if r.trend == "worsening":
                explanation.append("trend worsening (more signals in the last 30 days)")
            explanation.append(f"latest signal {days_since} day(s) ago")
            revenue = round(sum(m.get("annual_value") or 0 for m in involved), 2)
            if revenue > 0:
                explanation.append(f"{revenue} of annual value exposed")
            items.append({
                "key": r.key,
                "title": r.title,
                "impact": tier,
                "score": score,
                "occurrences": r.occurrences,
                "customers": r.customer_count,
                "high_severity": high_sev,
                "strategic_accounts": strategic_accounts,
                "strategic_relevance": bool(relevance),
                "trend": r.trend,
                "addressed": addressed,
                "why": explanation,
            })
        return {
            "advisory_only": True,
            "themes": items[:MAX_THEMES_SURFACE],
        }

    async def coverage(self, db, *, organization_id: str) -> dict[str, Any]:
        """Are we actually addressing what customers need? Per theme:
        traceable coverage = whether an active initiative/project addresses
        it, plus the company coverage summary."""
        theme_rows = list(
            (
                await db.execute(
                    select(CustomerTheme).where(
                        CustomerTheme.organization_id == organization_id,
                    ).order_by(
                        CustomerTheme.occurrences.desc(),
                        CustomerTheme.latest_at.desc(),
                    ).limit(MAX_THEMES_SURFACE)
                )
            ).scalars().all()
        )
        addressing = await self._addressing_projects(db, organization_id=organization_id)
        items = []
        covered = 0
        for r in theme_rows:
            rows = addressing.get(r.key) or []
            items.append({
                "key": r.key,
                "title": r.title,
                "occurrences": r.occurrences,
                "customers": r.customer_count,
                "covered": bool(rows),
                "coverage_pct": 100.0 if rows else 0.0,
                "addressing_projects": [
                    {"project_id": p["project_id"], "name": p["name"], "health": p["health"]}
                    for p in rows
                ],
            })
            if rows:
                covered += 1
        total = len(items)
        return {
            "advisory_only": True,
            "coverage_pct": round(100.0 * covered / total, 1) if total else 0.0,
            "covered_themes": covered,
            "total_themes": total,
            "themes": items,
        }

    async def strategic_gaps(self, db, *, organization_id: str) -> dict[str, Any]:
        """Strategic customer gaps: high-demand themes with no active
        initiative — customer reality that the strategy is not executing."""
        impact = await self.impact(db, organization_id=organization_id)
        addressing = await self._addressing_projects(db, organization_id=organization_id)
        goals = await self._active_goals(db, organization_id=organization_id)
        gaps = []
        for t in impact["themes"]:
            if t["impact"] in ("high", "medium") and not t["addressed"] and t["occurrences"] >= 3:
                tokens = _theme_tokens(t["key"], t["title"])
                related_goals = [
                    {"goal_id": g["id"], "title": g["title"], "priority": g["priority"]}
                    for g in goals
                    if any(tok in (g.get("title", "") + " " + " ".join(g.get("capabilities", []))).lower() for tok in tokens)
                ][:MAX_GOAL_CHAIN]
                gaps.append({
                    "key": t["key"],
                    "title": t["title"],
                    "impact": t["impact"],
                    "occurrences": t["occurrences"],
                    "customers": t["customers"],
                    "why": t["why"],
                    "related_goals": related_goals,
                })
        return {
            "advisory_only": True,
            "total": len(gaps),
            "gaps": gaps,
        }

    async def opportunities(self, db, *, organization_id: str) -> dict[str, Any]:
        """Customer opportunity detection: request/expansion-type needs with
        multiple customers and strategic relevance — advisory only."""
        theme_rows = list(
            (
                await db.execute(
                    select(CustomerTheme).where(
                        CustomerTheme.organization_id == organization_id,
                    ).order_by(
                        CustomerTheme.occurrences.desc(),
                        CustomerTheme.latest_at.desc(),
                    ).limit(MAX_THEMES_SURFACE)
                )
            ).scalars().all()
        )
        customers = await self._customers_by_id(db, organization_id=organization_id)
        addressing = await self._addressing_projects(db, organization_id=organization_id)
        goals = await self._active_goals(db, organization_id=organization_id)
        items = []
        for r in theme_rows:
            signals = await self._signals_of_theme(db, organization_id=organization_id, key=r.key)
            demand_signals = [s for s in signals if s.signal_type in ("request", "expansion", "adoption")]
            if len(demand_signals) < 2:
                continue
            expansion = any(s.signal_type == "expansion" for s in demand_signals)
            involved = [customers.get(s.customer_id) or {} for s in signals]
            strategic_accounts = sum(
                1 for m in involved
                if m.get("tier") in ("enterprise", "platinum", "gold")
                or m.get("segment") == "enterprise"
            )
            tokens = _theme_tokens(r.key, r.title)
            relevance = any(
                any(t in (g.get("title", "") + " " + " ".join(g.get("capabilities", []))).lower() for t in tokens)
                for g in goals
            )
            items.append({
                "key": r.key,
                "title": r.title,
                "signals": len(demand_signals),
                "customers": r.customer_count,
                "strategic_accounts": strategic_accounts,
                "expansion_potential": expansion,
                "strategic_relevance": relevance,
                "addressed": bool(addressing.get(r.key)),
                "decision_linkage": {
                    "requires_decision": not addressing.get(r.key),
                    "note": "no active initiative addresses this demand" if not addressing.get(r.key) else "an active initiative addresses it",
                },
            })
        items.sort(key=lambda x: (-x["signals"], -x["strategic_accounts"]))
        return {
            "advisory_only": True,
            "opportunities": items[:MAX_THEMES_SURFACE],
        }

    async def trends(self, db, *, organization_id: str) -> dict[str, Any]:
        """Signal volume trends: per theme, the last six month buckets —
        deterministic, evidence-backed, never a forecast."""
        theme_rows = list(
            (
                await db.execute(
                    select(CustomerTheme).where(
                        CustomerTheme.organization_id == organization_id,
                    ).order_by(
                        CustomerTheme.occurrences.desc(),
                        CustomerTheme.latest_at.desc(),
                    ).limit(MAX_THEMES_SURFACE)
                )
            ).scalars().all()
        )
        now = utcnow()
        months: list[str] = []
        for i in range(5, -1, -1):
            dt = now - timedelta(days=30 * i)
            months.append(dt.strftime("%Y-%m"))
        items = []
        for r in theme_rows:
            signals = await self._signals_of_theme(db, organization_id=organization_id, key=r.key)
            bucket = {m: 0 for m in months}
            for s in signals:
                key = s.occurred_at.strftime("%Y-%m")
                if key in bucket:
                    bucket[key] += 1
            items.append({
                "key": r.key,
                "title": r.title,
                "trend": r.trend,
                "monthly": [{"month": m, "count": bucket[m]} for m in months],
            })
        return {"advisory_only": True, "themes": items}

    async def knowledge_linkage(self, db, *, organization_id: str) -> dict[str, Any]:
        """Do our own knowledge topics and learnings actually cover the
        customer themes we collect? Coverage first, then the matched items."""
        known = {
            (t.name.lower(), t.category.lower())
            for t in list(
                (
                    await db.execute(
                        select(KnowledgeTopic).where(
                            KnowledgeTopic.organization_id == organization_id,
                        ).limit(MAX_KNOWLEDGE_TOPICS)
                    )
                ).scalars().all()
            )
        }
        theme_rows = list(
            (
                await db.execute(
                    select(CustomerTheme).where(
                        CustomerTheme.organization_id == organization_id,
                    ).order_by(
                        CustomerTheme.occurrences.desc(),
                        CustomerTheme.latest_at.desc(),
                    ).limit(MAX_THEMES_SURFACE)
                )
            ).scalars().all()
        )
        items = []
        covered = 0
        for r in theme_rows:
            tokens = _theme_tokens(r.key, r.title)
            match = [
                {"topic": t, "category": c}
                for t, c in known
                if any(tok in t or tok in c for tok in tokens)
            ][:MAX_KNOWLEDGE_LINKS]
            items.append({
                "key": r.key,
                "title": r.title,
                "customers": r.customer_count,
                "occurrences": r.occurrences,
                "knowledge_covered": bool(match),
                "knowledge": match,
            })
            if match:
                covered += 1
        total = len(items)
        return {
            "advisory_only": True,
            "knowledge_coverage_pct": round(100.0 * covered / total, 1) if total else 0.0,
            "themes": items,
        }

    async def customer_do(self, db, *, organization_id: str, customer_id: str) -> Optional[dict[str, Any]]:
        """One customer's command center: identity, timeline, themes,
        commitments, health trail, signals and touchpoints."""
        customer = (
            await db.execute(
                select(Customer).where(
                    Customer.organization_id == organization_id,
                    Customer.id == customer_id,
                )
            )
        ).scalar_one_or_none()
        if customer is None:
            return None
        signals = list(
            (
                await db.execute(
                    select(CustomerSignal).where(
                        CustomerSignal.organization_id == organization_id,
                        CustomerSignal.customer_id == customer_id,
                    ).order_by(CustomerSignal.occurred_at.desc()).limit(MAX_SIGNALS_SURFACE)
                )
            ).scalars().all()
        )
        commitments = list(
            (
                await db.execute(
                    select(CustomerCommitment).where(
                        CustomerCommitment.organization_id == organization_id,
                        CustomerCommitment.customer_id == customer_id,
                    ).order_by(CustomerCommitment.expected_at).limit(MAX_COMMITMENTS_SURFACE)
                )
            ).scalars().all()
        )
        outcomes = list(
            (
                await db.execute(
                    select(CustomerOutcome).where(
                        CustomerOutcome.organization_id == organization_id,
                        CustomerOutcome.customer_id == customer_id,
                    ).order_by(CustomerOutcome.recorded_at.desc()).limit(MAX_OUTCOMES_SURFACE)
                )
            ).scalars().all()
        )
        themes = [
            t for t in list(
                (
                    await db.execute(
                        select(CustomerTheme).where(
                            CustomerTheme.organization_id == organization_id,
                        ).order_by(CustomerTheme.occurrences.desc()).limit(MAX_THEMES_SURFACE * 4)
                    )
                ).scalars().all()
            )
            if customer_id in (t.customer_ids_json or [])
        ][:MAX_THEMES_SURFACE]
        health_row = (
            await db.execute(
                select(CustomerHealthRow).where(
                    CustomerHealthRow.organization_id == organization_id,
                    CustomerHealthRow.customer_id == customer_id,
                )
            )
        ).scalar_one_or_none()
        history = list(
            (
                await db.execute(
                    select(CustomerHealthHistory).where(
                        CustomerHealthHistory.organization_id == organization_id,
                        CustomerHealthHistory.customer_id == customer_id,
                    ).order_by(CustomerHealthHistory.occurred_at.desc()).limit(MAX_HEALTH_HISTORY)
                )
            ).scalars().all()
        )
        return {
            "advisory_only": True,
            "customer": {
                "id": customer.id,
                "company_name": customer.company_name,
                "segment": customer.segment,
                "tier": customer.tier,
                "annual_value": customer.annual_value,
                "industry": customer.industry,
            },
            "health": {
                "state": (health_row.state if health_row else "healthy"),
                "score": (health_row.score if health_row else 100),
                "reasons": (health_row.reasons_json if health_row else []),
                "positives": (health_row.positives_json if health_row else []),
                "history": [
                    {
                        "state": h.state, "score": h.score,
                        "reasons": h.reasons_json or [],
                        "occurred_at": _iso(h.occurred_at),
                    }
                    for h in history
                ],
            },
            "signals": [
                {
                    "signal_id": s.id,
                    "type": s.signal_type,
                    "severity": s.severity,
                    "need": s.need_key,
                    "summary": s.title,
                    "source": s.source,
                    "occurred_at": _iso(s.occurred_at),
                    "status": s.status,
                }
                for s in signals
            ],
            "commitments": [
                {
                    "commitment_id": c.id,
                    "summary": c.summary,
                    "expected_at": c.expected_at.isoformat(),
                    "status": c.status,
                    "capability": c.capability,
                }
                for c in commitments
            ],
            "outcomes": [
                {
                    "outcome_id": o.id,
                    "metric_kind": o.metric_kind,
                    "baseline": o.baseline,
                    "target": o.target,
                    "actual": o.actual,
                    "period_label": o.period_label,
                    "improved": (
                        o.baseline is not None and o.target is not None and o.actual is not None
                        and abs(o.actual - o.target) < abs(o.baseline - o.target)
                    ),
                }
                for o in outcomes
            ],
            "themes": [
                {
                    "key": t.key,
                    "title": t.title,
                    "occurrences": t.occurrences,
                    "trend": t.trend,
                }
                for t in themes
            ],
        }

    async def _signals_by_id(self, db, *, organization_id: str) -> dict[str, Any]:
        rows = list(
            (
                await db.execute(
                    select(CustomerSignal).where(
                        CustomerSignal.organization_id == organization_id,
                    ).order_by(CustomerSignal.occurred_at.desc()).limit(MAX_SIGNALS_SCAN)
                )
            ).scalars().all()
        )
        return {s.id: s for s in rows}

    async def _customers_by_id(self, db, *, organization_id: str) -> dict[str, dict[str, Any]]:
        rows = list(
            (
                await db.execute(
                    select(Customer).where(
                        Customer.organization_id == organization_id,
                    )
                )
            ).scalars().all()
        )
        return {
            c.id: {
                "id": c.id,
                "name": c.company_name,
                "segment": c.segment or "",
                "tier": c.tier or "",
                "industry": c.industry or "",
                "annual_value": c.annual_value,
            }
            for c in rows
        }

    async def _projects_by_id(
        self, db, *, organization_id: str, ids: Sequence[str],
    ) -> dict[str, dict[str, Any]]:
        if not ids:
            return {}
        rows = list(
            (
                await db.execute(
                    select(Project).where(
                        Project.organization_id == organization_id,
                        Project.id.in_(ids),
                    )
                )
            ).scalars().all()
        )
        return {p.id: {"id": p.id, "name": p.name or "", "status": p.status or ""} for p in rows}

    async def _capabilities_by_name(self, db, *, organization_id: str) -> dict[str, Any]:
        rows = list(
            (
                await db.execute(
                    select(OrgCapability).where(
                        OrgCapability.organization_id == organization_id,
                    )
                )
            ).scalars().all()
        )
        return {c.canonical_name.lower(): c for c in rows}

    async def _project_states(
        self, db, *, organization_id: str, project_ids: Sequence[str],
    ) -> dict[str, Any]:
        if not project_ids:
            return {}
        rows = list(
            (
                await db.execute(
                    select(ProjectExecutionState).where(
                        ProjectExecutionState.organization_id == organization_id,
                        ProjectExecutionState.project_id.in_(project_ids),
                    )
                )
            ).scalars().all()
        )
        return {r.project_id: r for r in rows}

    async def _active_goals(self, db, *, organization_id: str) -> list[dict[str, Any]]:
        rows = list(
            (
                await db.execute(
                    select(CompanyGoal).where(
                        CompanyGoal.organization_id == organization_id,
                        CompanyGoal.status.in_(("in_progress", "active")),
                    ).order_by(CompanyGoal.created_at.desc()).limit(MAX_GOALS_SCAN)
                )
            ).scalars().all()
        )
        goals = []
        for g in rows:
            capabilities = [
                obj.title or ""
                for obj in list(
                    (
                        await db.execute(
                            select(CompanyObjective).where(
                                CompanyObjective.organization_id == organization_id,
                                CompanyObjective.goal_id == g.id,
                            )
                        )
                    ).scalars().all()
                )
            ]
            goals.append({
                "id": g.id,
                "title": g.title or "",
                "status": g.status or "",
                "priority": g.priority or "",
                "capabilities": capabilities,
            })
        return goals

    async def _goal_chain_for_project(
        self, db, *, organization_id: str, project_id: Optional[str],
    ) -> list[dict[str, Any]]:
        if not project_id:
            return []
        links = list(
            (
                await db.execute(
                    select(StrategicLink).where(
                        StrategicLink.organization_id == organization_id,
                        StrategicLink.project_id == project_id,
                    )
                )
            ).scalars().all()
        )
        if not links:
            return []
        init_ids = {l.initiative_id for l in links if l.initiative_id}
        initiatives = {}
        if init_ids:
            initiatives = {
                i.id: i
                for i in list(
                    (
                        await db.execute(
                            select(CompanyInitiative).where(
                                CompanyInitiative.organization_id == organization_id,
                                CompanyInitiative.id.in_(init_ids),
                            )
                        )
                    ).scalars().all()
                )
            }
        obj_ids = {i.objective_id for i in initiatives.values()}
        objectives = {}
        if obj_ids:
            objectives = {
                o.id: o
                for o in list(
                    (
                        await db.execute(
                            select(CompanyObjective).where(
                                CompanyObjective.organization_id == organization_id,
                                CompanyObjective.id.in_(obj_ids),
                            )
                        )
                    ).scalars().all()
                )
            }
        goal_ids = {o.goal_id for o in objectives.values() if o.goal_id}
        goals = {}
        if goal_ids:
            goals = {
                g.id: g
                for g in list(
                    (
                        await db.execute(
                            select(CompanyGoal).where(
                                CompanyGoal.organization_id == organization_id,
                                CompanyGoal.id.in_(goal_ids),
                            )
                        )
                    ).scalars().all()
                )
            }
        chain = []
        for l in links:
            initiative = initiatives.get(l.initiative_id or "")
            obj = objectives.get(initiative.objective_id) if initiative else None
            goal = goals.get(obj.goal_id) if obj else None
            chain.append({
                "goal_id": goal.id if goal else "",
                "goal": goal.title if goal else "",
                "objective_id": obj.id if obj else "",
                "objective": obj.title if obj else "",
                "initiative_id": initiative.id if initiative else "",
                "initiative": initiative.title if initiative else "",
            })
        return chain[:MAX_GOAL_CHAIN]

    async def _addressing_projects(self, db, *, organization_id: str) -> dict[str, list[dict[str, Any]]]:
        """Themes -> projects that address them, using initiative titles /
        descriptions + project names as the keyword trace. Conservative:
        exact goal links only where present."""
        goals = await self._active_goals(db, organization_id=organization_id)
        all_projects = list(
            (
                await db.execute(
                    select(Project).where(
                        Project.organization_id == organization_id,
                    )
                )
            ).scalars().all()
        )
        states = await self._project_states(
            db, organization_id=organization_id,
            project_ids=[p.id for p in all_projects],
        )
        project_rows = {
            p.id: p
            for p in all_projects
            if (p.status or "") in ACTIVE_PROJECT_STATUSES
        }
        project_capabilities: dict[str, str] = {}
        goal_capabilities: dict[str, list[str]] = {}
        for g in goals:
            goal_capabilities[g["id"]] = g.get("capabilities", [])
        links = list(
            (
                await db.execute(
                    select(StrategicLink).where(
                        StrategicLink.organization_id == organization_id,
                    ).limit(MAX_GOALS_SCAN)
                )
            ).scalars().all()
        )
        init_ids = {l.initiative_id for l in links if l.initiative_id}
        initiatives = {}
        if init_ids:
            initiatives = {
                i.id: i
                for i in list(
                    (
                        await db.execute(
                            select(CompanyInitiative).where(
                                CompanyInitiative.organization_id == organization_id,
                                CompanyInitiative.id.in_(init_ids),
                            )
                        )
                    ).scalars().all()
                )
            }
        obj_ids = {i.objective_id for i in initiatives.values()}
        objectives = {}
        if obj_ids:
            objectives = {
                o.id: o
                for o in list(
                    (
                        await db.execute(
                            select(CompanyObjective).where(
                                CompanyObjective.organization_id == organization_id,
                                CompanyObjective.id.in_(obj_ids),
                            )
                        )
                    ).scalars().all()
                )
            }
        goal_by_objective: dict[str, str] = {
            o.id: o.goal_id for o in objectives.values() if o.goal_id
        }
        for l in links:
            pid = l.project_id
            if not pid or pid not in project_rows:
                continue
            initiative = initiatives.get(l.initiative_id or "")
            objective = objectives.get(initiative.objective_id) if initiative else None
            if not objective:
                continue
            project_capabilities.setdefault(pid, "")
            project_capabilities[pid] += " " + (objective.title or "")
            goal_id = goal_by_objective.get(objective.id)
            if goal_id:
                project_capabilities[pid] += " " + " ".join(goal_capabilities.get(goal_id, []))

        buckets: dict[str, list[dict[str, Any]]] = {}
        for theme_row in (
            await db.execute(
                select(CustomerTheme).where(
                    CustomerTheme.organization_id == organization_id,
                ).limit(MAX_THEMES_SURFACE)
            )
        ).scalars().all():
            tokens = _theme_tokens(theme_row.key, theme_row.title)
            hits = []
            for pid, p in project_rows.items():
                haystack = f"{p.name or ''} {project_capabilities.get(pid, '')}".lower()
                if any(t in haystack for t in tokens):
                    st = states.get(pid)
                    hits.append({
                        "project_id": pid,
                        "name": p.name or "",
                        "health": (st.health_status if st else "unknown"),
                    })
            buckets[theme_row.key] = hits
        return buckets

    async def _signals_of_theme(
        self, db, *, organization_id: str, key: str,
    ) -> list[Any]:
        theme_row = (
            await db.execute(
                select(CustomerTheme).where(
                    CustomerTheme.organization_id == organization_id,
                    CustomerTheme.key == key,
                )
            )
        ).scalar_one_or_none()
        if theme_row is None:
            return []
        customer_ids = set(theme_row.customer_ids_json or [])
        candidate_signals = []
        if customer_ids:
            candidate_signals = list(
                (
                    await db.execute(
                        select(CustomerSignal).where(
                            CustomerSignal.organization_id == organization_id,
                            CustomerSignal.customer_id.in_(customer_ids),
                            CustomerSignal.need_key == key,
                        ).order_by(CustomerSignal.occurred_at.desc()).limit(MAX_SIGNALS_SCAN)
                    )
                ).scalars().all()
            )
        matched = []
        tokens = _theme_tokens(key, theme_row.title or key)
        for s in candidate_signals:
            if any(t in (s.title or "").lower() for t in tokens):
                matched.append(s)
        if len(matched) < theme_row.occurrences:
            extra = list(
                (
                    await db.execute(
                        select(CustomerSignal).where(
                            CustomerSignal.organization_id == organization_id,
                            CustomerSignal.need_key == key,
                        ).order_by(CustomerSignal.occurred_at.desc()).limit(MAX_SIGNALS_SCAN)
                    )
                ).scalars().all()
            )
            for s in extra:
                if s.id not in {m.id for m in matched}:
                    matched.append(s)
        return matched[:MAX_SIGNALS_SCAN]


customer_intelligence_engine = CustomerIntelligenceEngine()




