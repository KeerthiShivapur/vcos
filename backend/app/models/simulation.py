"""Phase 19 — Enterprise simulation runs (what-if analysis)."""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

SIMULATION_STATUSES = ("queued", "running", "finished", "failed")


class SimulationRun(Base, TimestampMixin):
    """One what-if simulation across multiple organizational domains."""

    __tablename__ = "simulation_runs"
    __table_args__ = (
        Index("ix_simulation_runs_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[Optional[str]] = mapped_column(Text)
    assumptions: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    domains: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    results: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    risk: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    completed_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column(default=0)
    source_event: Mapped[Optional[str]] = mapped_column(String(120))
