"""AI Governance model."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class GovernanceRecommendation(Base, TimestampMixin):
    __tablename__ = "governance_recommendations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recommendation_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    affected_models: Mapped[List[str]] = mapped_column(JSON, default=list)
    affected_processes: Mapped[List[str]] = mapped_column(JSON, default=list)
    affected_data: Mapped[List[str]] = mapped_column(JSON, default=list)
    risk_assessment: Mapped[Optional[str]] = mapped_column(Text)
    remediation_steps: Mapped[List[str]] = mapped_column(JSON, default=list)
    estimated_effort: Mapped[Optional[str]] = mapped_column(String(50))
    estimated_cost: Mapped[Optional[float]] = mapped_column(default=None)
    compliance_frameworks: Mapped[List[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    assigned_to: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    governancerecommendation_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_governance_recs_org_type", "organization_id", "recommendation_type"),
        Index("ix_governance_recs_org_status", "organization_id", "status"),
        Index("ix_governance_recs_org_priority", "organization_id", "priority"),
    )