"""Resilience Plan model."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class ResiliencePlanStatus(str):
    DRAFT = "draft"
    ACTIVE = "active"
    TESTING = "testing"
    ARCHIVED = "archived"


class ResiliencePlanType(str):
    BUSINESS_CONTINUITY = "business_continuity"
    DISASTER_RECOVERY = "disaster_recovery"
    INCIDENT_RESPONSE = "incident_response"
    CRISIS_MANAGEMENT = "crisis_management"
    PANDEMIC = "pandemic"
    CYBERSECURITY = "cybersecurity"
    NATURAL_DISASTER = "natural_disaster"
    SUPPLY_CHAIN = "supply_chain"


class ResiliencePlan(Base, TimestampMixin):
    __tablename__ = "resilience_plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(40), default=ResiliencePlanType.BUSINESS_CONTINUITY, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default=ResiliencePlanStatus.DRAFT, nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(500), nullable=False)
    objectives: Mapped[List[str]] = mapped_column(JSON, default=list)
    scope_entities: Mapped[List[str]] = mapped_column(JSON, default=list)
    critical_functions: Mapped[List[dict]] = mapped_column(JSON, default=list)
    recovery_time_objective: Mapped[Optional[int]] = mapped_column(Integer)
    recovery_point_objective: Mapped[Optional[int]] = mapped_column(Integer)
    maximum_tolerable_downtime: Mapped[Optional[int]] = mapped_column(Integer)
    scenarios: Mapped[List[dict]] = mapped_column(JSON, default=list)
    response_procedures: Mapped[List[dict]] = mapped_column(JSON, default=list)
    communication_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    roles_responsibilities: Mapped[dict] = mapped_column(JSON, default=dict)
    resources: Mapped[List[dict]] = mapped_column(JSON, default=list)
    dependencies: Mapped[List[dict]] = mapped_column(JSON, default=list)
    testing_schedule: Mapped[dict] = mapped_column(JSON, default=dict)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_test_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_updated_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resilienceplanstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_resilience_plans_org_status", "organization_id", "status"),
        Index("ix_resilience_plans_org_type", "organization_id", "plan_type"),
    )