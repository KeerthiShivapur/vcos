"""Internal certification platform (Phase 10.9 — Certification Engine).

The organization defines internal certifications (Cloud, Security, AI,
Leadership, Architecture, DevOps, Management, Sales, HR, Finance,
Compliance, Engineering). Employees take certification attempts (often
driven by a passing assessment); a passing attempt creates a
CertificationEarned record that is also mirrored into the employee's
certification profile, the Organization Graph, AI memory and search. The
certification worker manages expiry and renewal reminders.
"""

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Certification(Base, TimestampMixin):
    __tablename__ = "certifications"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_certification_name_org"),
        Index("ix_certifications_org_category", "organization_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(120))
    # cloud | security | ai | leadership | architecture | devops | management
    # sales | hr | finance | engineering | compliance
    level: Mapped[str] = mapped_column(String(30), default="associate")
    # associate | professional | expert
    issuer: Mapped[str] = mapped_column(String(255), default="VCOS Academy")
    validity_years: Mapped[int] = mapped_column(Integer, default=2)
    skills: Mapped[Optional[list[str]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="published")
    # draft | published | retired
    assessment_id: Mapped[Optional[str]] = mapped_column(String(32))


class CertificationAttempt(Base, TimestampMixin):
    __tablename__ = "certification_attempts"
    __table_args__ = (
        Index("ix_cert_attempts_emp", "organization_id", "employee_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    certification_id: Mapped[str] = mapped_column(
        ForeignKey("certifications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    # in_progress | passed | failed
    score: Mapped[Optional[float]] = mapped_column(Float)
    evidence: Mapped[Optional[str]] = mapped_column(Text)
    attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class CertificationEarned(Base, TimestampMixin):
    __tablename__ = "certifications_earned"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "certification_id", "employee_id", name="uq_cert_earned"
        ),
        Index("ix_cert_earned_emp", "organization_id", "employee_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    certification_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("certifications.id", ondelete="CASCADE"), index=True, nullable=True
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    attempt_id: Mapped[Optional[str]] = mapped_column(String(32))
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date)
    credential_id: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="valid")
    # valid | expiring_soon | expired | revoked
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
