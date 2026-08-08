"""Lead & Opportunity models (Phase 12.2/12.3 — Pipeline Operating System).

Lead lifecycle: new -> qualified -> converted. Opportunity pipeline:
qualified -> proposal -> negotiation -> won | lost. AI scores leads and
predicts win probability; every activity is captured for the journey.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Lead(Base, TimestampMixin):
    __tablename__ = "leads"
    __table_args__ = (Index("ix_leads_org", "organization_id"), Index("ix_leads_status", "organization_id", "status"))

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # new | qualified | converted | lost
    status: Mapped[str] = mapped_column(String(20), default="new")
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    contact_email: Mapped[Optional[str]] = mapped_column(String(320))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(60))
    # website | referral | marketing | events | cold_outreach | partner | advertisement
    source: Mapped[str] = mapped_column(String(30), default="website")
    industry: Mapped[Optional[str]] = mapped_column(String(120))
    country: Mapped[Optional[str]] = mapped_column(String(80))
    employee_count: Mapped[Optional[int]] = mapped_column(Integer)
    needs: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    score: Mapped[int] = mapped_column(Integer, default=50)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    # ai signals: fit, budget, urgency, duplicates
    score_factors: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    duplicate_of: Mapped[Optional[str]] = mapped_column(String(32))
    expected_value: Mapped[Optional[float]] = mapped_column(Float)
    qualified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_touch_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class LeadActivity(Base, TimestampMixin):
    __tablename__ = "lead_activities"
    __table_args__ = (Index("ix_lead_activity_lead", "organization_id", "lead_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    # created | called | emailed | met | noted | qualified | converted | lost | status_changed
    kind: Mapped[str] = mapped_column(String(30), default="noted")
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    content: Mapped[Optional[str]] = mapped_column(Text)
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class Opportunity(Base, TimestampMixin):
    __tablename__ = "opportunities"
    __table_args__ = (Index("ix_opps_org", "organization_id"), Index("ix_opps_stage", "organization_id", "stage"))

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[Optional[str]] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    customer_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # qualified | proposal | negotiation | won | lost
    stage: Mapped[str] = mapped_column(String(20), default="qualified")
    value: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    probability: Mapped[int] = mapped_column(Integer, default=20)
    expected_close_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    risk_reasons: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # reasons the AI or sales logged for stage changes
    close_reason: Mapped[Optional[str]] = mapped_column(String(120))
    won_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    lost_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(30), default="lead")


class OpportunityActivity(Base, TimestampMixin):
    __tablename__ = "opportunity_activities"
    __table_args__ = (Index("ix_opp_activity_opp", "organization_id", "opportunity_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    # created | stage_changed | proposed | negotiated | won | lost | noted
    kind: Mapped[str] = mapped_column(String(30), default="noted")
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    content: Mapped[Optional[str]] = mapped_column(Text)
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
