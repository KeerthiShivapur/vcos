"""Phase 19 — Organizational learning cycles (the learning loop)."""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

LEARNING_STAGES = ("observe", "extract", "store", "apply", "completed")


class LearningCycle(Base, TimestampMixin):
    """One complete learning cycle: project/initiative -> lessons -> knowledge."""

    __tablename__ = "learning_cycles"
    __table_args__ = (
        Index("ix_learning_cycles_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    cycle: Mapped[str] = mapped_column(String(40), nullable=False)  # e.g. "project:completed"
    stage: Mapped[str] = mapped_column(String(20), default="observe")
    source_type: Mapped[Optional[str]] = mapped_column(String(40))
    source_id: Mapped[Optional[str]] = mapped_column(String(32))
    insights: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    lessons: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    knowledge_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    memory_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    started_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
    source_event: Mapped[Optional[str]] = mapped_column(String(120))
