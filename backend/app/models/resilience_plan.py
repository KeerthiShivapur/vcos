"""Phase 20 — Enterprise resilience plans.

The platform helps organizations prepare for disruptions: key people leaving,
critical vendor failures, demand surges, incidents. Each plan identifies the
affected areas and the coordinated response.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

# key_employee | vendor | demand_surge | incident | natural_disaster | financial | other
RESILIENCE_SCENARIOS = (
    "key_employee", "vendor", "demand_surge", "incident", "financial", "other",
)

# draft | active | tested | archived
RESILIENCE_STATUSES = ("draft", "active", "tested", "archived")


class ResiliencePlan(Base, TimestampMixin):
    """One disruption scenario with its response plan (Phase 20.14)."""

    __tablename__ = "resilience_plans"
    __table_args__ = (
        Index("ix_resilience_org_status", "organization_id", "status"),
        Index("ix_resilience_org_scenario", "organization_id", "scenario"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    scenario: Mapped[str] = mapped_column(String(40), default="other")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # {"domains": ["projects", "customers"], "risk_level": "high", "signals": [...]}
    impact: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # [{"step", "owner", "action"}] — the coordinated response
    response_plan: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    source: Mapped[str] = mapped_column(String(120), default="kernel.resilience")
    assessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
