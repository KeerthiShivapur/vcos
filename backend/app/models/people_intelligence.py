"""People Intelligence models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class PeopleTimeline(Base, TimestampMixin):
    __tablename__ = "people_timelines"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    related_entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    related_entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    actor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    peopletimeline_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_people_timelines_emp_date", "employee_id", "event_date"),
        Index("ix_people_timelines_org_date", "organization_id", "event_date"),
    )


class PersonIdentity(Base, TimestampMixin):
    __tablename__ = "person_identities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    legal_name: Mapped[str] = mapped_column(String(300), nullable=False)
    preferred_name: Mapped[Optional[str]] = mapped_column(String(200))
    gender: Mapped[Optional[str]] = mapped_column(String(20))
    date_of_birth: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    nationality: Mapped[Optional[str]] = mapped_column(String(100))
    marital_status: Mapped[Optional[str]] = mapped_column(String(30))
    emergency_contacts: Mapped[List[dict]] = mapped_column(JSON, default=list)
    documents: Mapped[List[dict]] = mapped_column(JSON, default=list)
    peopletimeline_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", name="uq_person_identities_org_emp"),
    )


class PersonMembership(Base, TimestampMixin):
    __tablename__ = "person_memberships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # department, team, project, committee, role
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(60), nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    peopletimeline_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_person_memberships_emp_active", "employee_id", "end_date"),
        Index("ix_person_memberships_entity", "entity_type", "entity_id"),
    )


class PersonRoleAssignment(Base, TimestampMixin):
    __tablename__ = "person_role_assignments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(40), default="organization", nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    assigned_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    peopletimeline_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("employee_id", "role_id", "scope_type", "scope_id", name="uq_person_role_assignments_unique"),
        Index("ix_person_role_assignments_emp_active", "employee_id", "is_active"),
    )


class ReportingRelationship(Base, TimestampMixin):
    __tablename__ = "reporting_relationships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    manager_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    direct_report_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(30), default="direct", nullable=False)  # direct, dotted, matrix
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    peopletimeline_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("manager_id", "direct_report_id", name="uq_reporting_relationships_unique"),
        Index("ix_reporting_relationships_mgr_active", "manager_id", "is_active"),
        Index("ix_reporting_relationships_report_active", "direct_report_id", "is_active"),
        {"extend_existing": True},
    )


# =============================================================================
# CONSTANTS — Mirror canonical_workforce for backward compatibility
# =============================================================================

MEMBERSHIP_STATUSES = (
    "invited",
    "active",
    "probation",
    "notice",
    "suspended",
    "inactive",
    "departed",
    "external",
    "contractor",
    "consultant",
    "partner",
)

RELATIONSHIP_TYPES = (
    "reports_to",
    "matrix_manager",
    "project_manager",
    "functional_manager",
    "dotted_line_manager",
    "mentor",
)

ROLE_TYPES = (
    "functional",
    "project",
    "temporary",
    "acting",
    "advisory",
    "matrix",
)

__all__ = [
    "PeopleTimeline",
    "PersonIdentity",
    "PersonMembership",
    "PersonRoleAssignment",
    "ReportingRelationship",
    "MEMBERSHIP_STATUSES",
    "RELATIONSHIP_TYPES",
    "ROLE_TYPES",
]