"""Industry Platform models — the catalog & tenant selection (Phase 17.1).

The universal VCOS core is industry-agnostic; these tables describe *which*
industries exist, how each organization selects and configures them, and the
KPI values that feed industry-specific analytics. Nothing here hardcodes an
industry — packs plug in through the same five model shapes (industry,
module, template, policy, configuration) for every vertical.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Industry(Base, TimestampMixin):
    """Global industry catalog entry — one row per supported industry.

    The row is data-driven: everything VCOS can do for an industry (modules,
    templates, workflows, compliance frameworks, AI profiles, KPIs) is stored
    as JSON so new verticals can be added without touching the core.
    """

    __tablename__ = "industries"
    __table_args__ = (
        Index("ix_industries_enabled", "enabled"),
        UniqueConstraint("industry_key", name="uq_industries_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    # healthcare|manufacturing|education|government|finance|retail|construction|
    # logistics|hospitality|legal|research|agriculture|media|energy|
    # telecommunications|nonprofit|software
    industry_key: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # e.g. ["hospital", "clinic", "diagnostic_lab", "medical_college"]
    business_types: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # e.g. ["US", "UK", "IN", "DE", ...]
    countries: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # module keys the pack ships with
    modules: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # workflow template keys
    workflows: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # compliance frameworks, e.g. ["HIPAA", "GDPR"]
    compliance_frameworks: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # AI profile keys (prompts, terminology, guardrails)
    ai_models: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # KPI keys the industry dashboard tracks
    kpis: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # navigation + dashboard panel hints for the frontend
    navigation: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    icon: Mapped[Optional[str]] = mapped_column(String(50))
    color: Mapped[Optional[str]] = mapped_column(String(20))
    pack_version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    scanned: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class IndustrySelection(Base, TimestampMixin):
    """An organization's industry choice (Phase 17.1 framework).

    Every organization picks Industry -> Business Type -> Company Size ->
    Country -> Regulations; VCOS then enables the matching modules,
    templates, workflows, reports, AI knowledge, permissions and compliance.
    """

    __tablename__ = "industry_selections"
    __table_args__ = (
        Index("ix_industry_selections_org", "organization_id"),
        UniqueConstraint(
            "organization_id", "industry_key", name="uq_industry_selections_org_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    industry_key: Mapped[str] = mapped_column(String(50), nullable=False)
    business_type: Mapped[Optional[str]] = mapped_column(String(80))
    company_size: Mapped[Optional[str]] = mapped_column(String(40))
    country: Mapped[Optional[str]] = mapped_column(String(10))
    regulations: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # primary|secondary — an organization can operate across industries
    role: Mapped[str] = mapped_column(String(20), default="primary")
    status: Mapped[str] = mapped_column(String(20), default="active")
    selected_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class IndustryMetric(Base, TimestampMixin):
    """Industry KPI value (Phase 17.15) — feeds tailored dashboards/benchmarks."""

    __tablename__ = "industry_metrics"
    __table_args__ = (
        Index("ix_industry_metrics_org_key", "organization_id", "industry_key"),
        Index("ix_industry_metrics_recorded", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    industry_key: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(160))
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(30))
    period: Mapped[str] = mapped_column(String(20), default="daily")
    tags: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
