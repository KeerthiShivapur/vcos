"""Industry module model (Phase 17.1).

Modules are the atomic capability units of an industry pack (e.g. Patients,
Appointments, Medical Equipment for healthcare). Organizations toggle modules
independently; the core platform is never modified — only the pack's module
set is exposed per tenant.
"""

from typing import Any, Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class IndustryModule(Base, TimestampMixin):
    """Catalog of modules shipped by an industry pack."""

    __tablename__ = "industry_modules"
    __table_args__ = (
        Index("ix_industry_modules_key", "industry_key"),
        UniqueConstraint("industry_key", "module_key", name="uq_industry_modules_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    industry_key: Mapped[str] = mapped_column(String(50), nullable=False)
    module_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # care|operations|production|academic|service|compliance|analytics|...
    category: Mapped[str] = mapped_column(String(40), default="operations")
    enabled_by_default: Mapped[bool] = mapped_column(Boolean, default=True)
    # entity shapes the module works with (organization graph integration)
    entities: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # permission codes the module implies when enabled (industry:manage family)
    permissions: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    settings: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(default=0)
