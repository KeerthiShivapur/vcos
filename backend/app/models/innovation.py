"""Innovation model."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class Innovation(Base, TimestampMixin):
    __tablename__ = "innovations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    innovation_type: Mapped[str] = mapped_column(String(40), default="product", nullable=False)  # product, process, business_model, technology, organizational
    status: Mapped[str] = mapped_column(String(24), default="ideation", nullable=False, index=True)  # ideation, research, prototyping, testing, pilot, scaling, completed, archived
    author_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    team_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    maturity_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1-5
    investment_required: Mapped[Optional[float]] = mapped_column(default=None)
    expected_roi: Mapped[Optional[float]] = mapped_column(default=None)
    risk_level: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)  # low, medium, high, extreme
    status_detail: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    innovation_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_innovations_org_status", "organization_id", "status"),
        Index("ix_innovations_org_author", "organization_id", "author_id"),
    )