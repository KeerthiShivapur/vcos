"""Industry compliance models (Phase 17.15).

Compliance is configurable per industry, country and region — HIPAA for
healthcare, banking standards for finance, ISO for manufacturing, national
regulations for government, accreditation for education, safety standards
for construction. Rules live in the catalog; per-org check results are
recorded separately so posture can be tracked over time.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class IndustryPolicy(Base, TimestampMixin):
    """Configurable compliance rule for an industry (optionally per region/country)."""

    __tablename__ = "industry_policies"
    __table_args__ = (
        Index("ix_industry_policies_key", "industry_key"),
        Index("ix_industry_policies_framework", "framework"),
        UniqueConstraint(
            "industry_key", "policy_key", "region", name="uq_industry_policies_rule"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    industry_key: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    framework: Mapped[str] = mapped_column(String(60), nullable=False)
    # global, or a country/region code for localized requirements
    region: Mapped[str] = mapped_column(String(20), default="global")
    control: Mapped[Optional[str]] = mapped_column(String(80))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # critical|high|medium|low
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    # evidence kinds expected: backup_test|audit_log|training|inspection|...
    evidence_requirements: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    cadence_days: Mapped[int] = mapped_column(default=90)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # per-org override payload: {"enabled": true, "severity": "high", ...}
    overridable: Mapped[bool] = mapped_column(Boolean, default=True)


class IndustryComplianceCheck(Base, TimestampMixin):
    """Per-organization result of evaluating an industry policy (Phase 17.15)."""

    __tablename__ = "industry_compliance_checks"
    __table_args__ = (
        Index("ix_industry_checks_org_status", "organization_id", "status"),
        Index("ix_industry_checks_org_policy", "organization_id", "policy_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    industry_key: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_id: Mapped[str] = mapped_column(
        ForeignKey("industry_policies.id", ondelete="CASCADE"), nullable=False
    )
    # pass|warn|fail|pending
    status: Mapped[str] = mapped_column(String(10), default="pending")
    # snapshot of the rule severity at check time (critical|high|medium|low)
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    evidence: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    checked_by: Mapped[Optional[str]] = mapped_column(String(32))
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
