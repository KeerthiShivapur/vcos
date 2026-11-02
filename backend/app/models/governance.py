"""Governance models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, Date, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class GovernanceScopeType(str):
    ORGANIZATION = "organization"
    DEPARTMENT = "department"
    TEAM = "team"
    PROJECT = "project"
    RESOURCE = "resource"


class GovernanceScope(Base, TimestampMixin):
    __tablename__ = "governance_scopes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    scope_type: Mapped[str] = mapped_column(String(40), default=GovernanceScopeType.ORGANIZATION, nullable=False)
    scope_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    parent_scope_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("governance_scopes.id", ondelete="SET NULL"), index=True
    )
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    policies: Mapped[List[dict]] = mapped_column(JSON, default=list)
    compliance_requirements: Mapped[List[str]] = mapped_column(JSON, default=list)
    review_cadence_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    governancescopetype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    parent: Mapped[Optional["GovernanceScope"]] = relationship(
        back_populates="children", remote_side="GovernanceScope.id"
    )
    children: Mapped[List["GovernanceScope"]] = relationship(back_populates="parent")

    __table_args__ = (
        Index("ix_governance_scopes_org_type", "organization_id", "scope_type"),
        Index("ix_governance_scopes_org_active", "organization_id", "is_active"),
        Index("ix_governance_scopes_next_review", "next_review_at"),
    )


class ApprovalPolicy(Base, TimestampMixin):
    __tablename__ = "approval_policies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    scope_type: Mapped[str] = mapped_column(String(40), default="organization", nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    required_approvers: Mapped[List[str]] = mapped_column(JSON, default=list)
    min_approvals: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    requires_unanimous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_self_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    escalation_days: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    escalation_to: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    governancescopetype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_approval_policies_org_entity", "organization_id", "entity_type"),
        Index("ix_approval_policies_org_active", "organization_id", "is_active"),
    )