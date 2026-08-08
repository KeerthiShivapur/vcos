"""Phase 19 — Innovation intelligence (ideas, research, experiments)."""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

INNOVATION_STAGES = ("idea", "research", "experiment", "prototype", "launched", "archived")
INNOVATION_CATEGORIES = (
    "product", "process", "automation", "customer", "operations", "technology", "other",
)


class Innovation(Base, TimestampMixin):
    """An innovation item tracked by the innovation intelligence engine."""

    __tablename__ = "innovations"
    __table_args__ = (
        Index("ix_innovations_org_stage", "organization_id", "stage"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(30), default="product")
    description: Mapped[Optional[str]] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(20), default="idea")
    creator_id: Mapped[Optional[str]] = mapped_column(String(32))
    votes: Mapped[int] = mapped_column(default=0)
    signals: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")
