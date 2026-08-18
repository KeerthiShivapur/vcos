"""Slice 4G.5 — Customer & Market Execution Intelligence models.

The canonical customer signal ledger. Customers themselves stay first-class
citizens of the Phase 12 CRM substrate (customers, customer_project_links);
this module adds the INTELLIGENCE layer on top of that identity: signals
(provider-neutral: support / crm / email / meetings / usage / surveys /
interviews / account notes / observations), derived themes (need aggregation
that never loses the individual evidence), governed commitments, outcome
records, and the temporal customer health trail. Every write is an exact-once,
change-driven reaction to a durable customer event.
"""

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

# --- canonical vocabularies ------------------------------------------------

# Provider-neutral signal kinds: the same meaning regardless of origin.
SIGNAL_TYPES = (
    "feedback", "request", "complaint", "issue", "success",
    "churn_risk", "adoption", "outcome", "expansion",
)
SIGNAL_SEVERITIES = ("info", "low", "medium", "high", "critical")
SIGNAL_SOURCES = (
    "support", "crm", "email", "meeting", "usage", "survey",
    "interview", "account", "observation",
)
SIGNAL_STATUSES = ("open", "acknowledged", "resolved", "closed")
COMMITMENT_STATUSES = ("pending", "on_track", "at_risk", "slipped", "delivered")
HEALTH_STATES = ("healthy", "concerned", "at_risk")


class CustomerSignal(Base, TimestampMixin):
    """One canonical customer signal — the atomic unit of customer reality.

    Provider-neutral: the same meaning whether it came from a support ticket,
    a CRM note, an email, a meeting, product usage, a survey, an interview or
    an account-manager observation. The need_key is the canonical theme the
    engine resolved for this signal (or was given), so aggregation never
    loses the individual evidence.
    """

    __tablename__ = "customer_signals"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "customer_id", "source_event_id",
            name="uq_cs_signal_event",
        ),
        Index("ix_cs_signal_org", "organization_id"),
        Index("ix_cs_signal_customer", "organization_id", "customer_id"),
        Index("ix_cs_signal_theme", "organization_id", "need_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    signal_type: Mapped[str] = mapped_column(String(24), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), default="medium")
    need_key: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    # support | crm | email | meeting | usage | survey | interview | account | observation
    source: Mapped[str] = mapped_column(String(24), default="observation")
    project_id: Mapped[Optional[str]] = mapped_column(String(32))
    # open | acknowledged | resolved | closed
    status: Mapped[str] = mapped_column(String(16), default="open")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class CustomerTheme(Base, TimestampMixin):
    """A derived need aggregation — the recurrence of one canonical need.

    Every aggregate keeps its evidence: the individual signal ids and
    customer ids that formed it (bounded to the latest evidence). The theme
    is recomputed incrementally when a signal event arrives; occurrences,
    customer count and the trend (worsening / stable / improving) are
    deterministic functions of the signal ledger.
    """

    __tablename__ = "customer_themes"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_ct_theme_key"),
        Index("ix_ct_theme_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, default=0)
    customer_count: Mapped[int] = mapped_column(Integer, default=0)
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    high_severity_count: Mapped[int] = mapped_column(Integer, default=0)
    # bounded evidence: the latest signals/customers that formed this theme
    signal_ids_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    customer_ids_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # worsening | stable | improving
    trend: Mapped[str] = mapped_column(String(12), default="stable")
    first_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    latest_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class CustomerCommitment(Base, TimestampMixin):
    """A canonical customer commitment: what we promised a customer and when.

    The commitment is the bridge from customer reality to company execution:
    it points at the project that is expected to deliver it and (optionally)
    the capability it needs. Status transitions are governed writes that
    publish customer.commitment.updated / customer.commitment.delivered.
    """

    __tablename__ = "customer_commitments"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "customer_id", "source_event_id",
            name="uq_cc_commitment_event",
        ),
        Index("ix_cc_commitment_org", "organization_id"),
        Index("ix_cc_commitment_customer", "organization_id", "customer_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    expected_at: Mapped[date] = mapped_column(Date, nullable=False)
    # pending | on_track | at_risk | slipped | delivered
    status: Mapped[str] = mapped_column(String(16), default="on_track")
    project_id: Mapped[Optional[str]] = mapped_column(String(32))
    capability: Mapped[Optional[str]] = mapped_column(String(120))
    owner_label: Mapped[Optional[str]] = mapped_column(String(200))
    note: Mapped[Optional[str]] = mapped_column(Text)
    changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class CustomerOutcome(Base, TimestampMixin):
    """A recorded customer outcome: did the customer problem improve?

    Baseline -> actual (with optional target) for one metric, optionally
    linked back to the signal that started it. Outcome records feed the 4E.7
    learning engine (customer outcome lessons) and customer health.
    """

    __tablename__ = "customer_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "customer_id", "source_event_id",
            name="uq_co_outcome_event",
        ),
        Index("ix_co_outcome_org", "organization_id"),
        Index("ix_co_outcome_customer", "organization_id", "customer_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    metric_kind: Mapped[str] = mapped_column(String(60), nullable=False)
    baseline: Mapped[Optional[float]] = mapped_column(Float)
    target: Mapped[Optional[float]] = mapped_column(Float)
    actual: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String(20), default="")
    period_label: Mapped[Optional[str]] = mapped_column(String(80))
    signal_id: Mapped[Optional[str]] = mapped_column(String(32))
    note: Mapped[Optional[str]] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class CustomerHealthRow(Base, TimestampMixin):
    """The CURRENT evidence-backed health of one customer.

    Never a bare score: the state always carries the why (reasons) and the
    positives, plus the deterministic factors that produced it. The temporal
    trail of states lives in CustomerHealthHistory.
    """

    __tablename__ = "customer_health_rows"
    __table_args__ = (
        UniqueConstraint("organization_id", "customer_id", name="uq_chr_customer"),
        Index("ix_chr_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    # healthy | concerned | at_risk
    state: Mapped[str] = mapped_column(String(12), default="healthy")
    score: Mapped[int] = mapped_column(Integer, default=100)
    reasons_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    positives_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    factors_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(32))


class CustomerHealthHistory(Base, TimestampMixin):
    """Temporal health trail: satisfied -> concerned -> at risk -> recovered.

    One row per health-changing event (exact-once on the source event), so
    the history itself becomes organizational intelligence.
    """

    __tablename__ = "customer_health_history"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "customer_id", "source_event_id",
            name="uq_chh_event",
        ),
        Index("ix_chh_customer", "organization_id", "customer_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(12), nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=100)
    reasons_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    positives_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
