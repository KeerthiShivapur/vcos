"""Slice 4F.1 — Universal People Intelligence Foundation: the canonical
person substrate the whole 4F roadmap stands on.

People intelligence is a special intelligence surface over people data — a
person in the company is the universe that expertise (4F.2), experience
(4F.3), ownership (4F.4) and collaboration (4F.5) attach to. This slice
formalises the foundation layer that Phase 2 people data could not express:

* ``PersonIdentity``        one strong external identifier maps to exactly one
                            canonical person (identity resolution) — ambiguous
                            or conflicting mappings are never silently merged,
* ``PersonMembership``      temporal employment membership windows (active /
                            invited / suspended / inactive / external /
                            contractor / consultant / partner / departed),
* ``PersonRoleAssignment``  temporal role windows — a person may hold many
                            roles concurrently, at most one primary now,
* ``ReportingRelationship`` temporal reporting relationships of any type
                            (reports_to / matrix_manager / mentor / ...) —
                            history is never destroyed; the current open
                            reports_to window drives ``Employee.manager_id``,
* ``PeopleTimeline``        an append-only people evidence journal with an
                            exact-once event key.

Architecture law (inherited from 4E.1-4E.7, preserved here): tenant-scoped
rows, stable unique keys so event replay is exact-once, lineage and actor on
every row, no destructive deletes — state moves forward, history is retained.
Identity != employment != role: the layers never conflate what a person IS
(identity), what they DO here (employment) and what they DO (roles).
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import gen_uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


IDENTITY_SOURCES = (
    "email", "phone", "username", "github", "slack", "jira", "crm", "hris",
    "external", "okta", "azure_ad", "google",
)

MEMBERSHIP_STATUSES = (
    "invited", "active", "probation", "notice", "suspended", "inactive", "departed",
    "external", "contractor", "consultant", "partner",
)

RELATIONSHIP_TYPES = (
    "reports_to", "matrix_manager", "project_manager", "functional_manager",
    "dotted_line_manager", "mentor",
)

ROLE_TYPES = ("functional", "project", "temporary", "acting", "advisory", "matrix")


class PersonIdentity(Base):
    """One strong external identifier (email, phone, github, ...) maps to
    exactly one canonical person. Resolution is deterministic: a key either
    resolves to one person or is flagged ``ambiguous`` — the engine never
    silently merges ambiguity. The identifier chain is the seed of the People
    Graph (4F.1 identity plane)."""

    __tablename__ = "person_identities"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source", "source_key",
            name="uq_person_identity_key",
        ),
        Index("ix_person_identity_org_person", "organization_id", "person_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_key: Mapped[str] = mapped_column(String(360), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), default="primary", nullable=False)
    # primary | work | personal | alias | recovery
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    # active | ambiguous | retired
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class PersonMembership(Base):
    """A temporal membership window of a person in the organisation. A person
    has a LINEAR membership history; the last window with no ``valid_to`` is
    the current membership. A departed person keeps their last closed window,
    so 'who was with us at time T' is always answerable."""

    __tablename__ = "person_memberships"
    __table_args__ = (
        Index("ix_person_memberships_org_person", "organization_id", "person_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employment_status: Mapped[str] = mapped_column(String(30), nullable=False)
    # invited | active | suspended | inactive | departed | external |
    # contractor | consultant | partner
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    employment_type: Mapped[Optional[str]] = mapped_column(String(30))
    designation_snapshot: Mapped[Optional[str]] = mapped_column(String(150))
    note: Mapped[Optional[str]] = mapped_column(Text)
    source_type: Mapped[Optional[str]] = mapped_column(String(40))
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class PersonRoleAssignment(Base):
    """A temporal role window. A person may hold many roles concurrently
    (functional role, project role, acting role, advisory role, ...); at most
    one current primary role per person (engine-enforced). Closing a window
    never deletes it — the full role history is reconstructable."""

    __tablename__ = "person_role_assignments"
    __table_args__ = (
        Index("ix_person_roles_org_person", "organization_id", "person_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), index=True
    )
    role_title: Mapped[str] = mapped_column(String(200), nullable=False)
    role_type: Mapped[str] = mapped_column(String(30), default="functional", nullable=False)
    # functional | project | temporary | acting | advisory | matrix
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_type: Mapped[Optional[str]] = mapped_column(String(40))
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ReportingRelationship(Base):
    """A temporal reporting relationship of any type. When the type is
    ``reports_to`` and the window is open, the engine mirrors it into
    ``Employee.manager_id`` so the live org chart stays coherent — but the
    window is the source of truth, and past relationships are never lost."""

    __tablename__ = "reporting_relationships"
    __table_args__ = (
        Index("ix_reporting_relationships_org_person", "organization_id", "person_id"),
        Index("ix_reporting_relationships_manager", "organization_id", "manager_person_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # reports_to | matrix_manager | project_manager | functional_manager |
    # dotted_line_manager | mentor
    manager_person_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_type: Mapped[Optional[str]] = mapped_column(String(40))
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class PeopleTimeline(Base):
    """Append-only people evidence journal. Event-driven entries are keyed
    (organization_id, person_id, event_id) so replay is exact-once; manual
    operations carry an explicit source_type/source_id instead. Never edited,
    never deleted."""

    __tablename__ = "people_timelines"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "person_id", "event_id",
            name="uq_people_timeline_event",
        ),
        Index("ix_people_timeline_org_person", "organization_id", "person_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # person.created | person.updated | membership.changed | role.assigned |
    # role.changed | role.removed | relationship.changed | identity.linked |
    # identity.resolved
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[Optional[dict]] = mapped_column(JSON)
    event_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(40))
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)