"""Industry template model (Phase 17.12).

Ready-made, industry-specific templates: workflow templates (patient
registration -> diagnosis -> discharge), document templates (consent forms,
tender notices, inspection checklists), dashboard/report layouts and
AI knowledge templates. Templates are configurable data, never code.
"""

from typing import Any, Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class IndustryTemplate(Base, TimestampMixin):
    """Catalog of templates shipped by an industry pack."""

    __tablename__ = "industry_templates"
    __table_args__ = (
        Index("ix_industry_templates_key_kind", "industry_key", "kind"),
        UniqueConstraint("industry_key", "template_key", name="uq_industry_templates_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    industry_key: Mapped[str] = mapped_column(String(50), nullable=False)
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # workflow|document|dashboard|report|knowledge|prompt
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # kind-specific payload: {"steps": [...]} for workflows,
    # {"sections": [...]} for documents, {"panels": [...]} for dashboards,
    # {"metrics": [...]} for reports, {"body": "..."} for knowledge,
    # {"prompt": "...", "examples": [...]} for AI prompts.
    content: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    default: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
