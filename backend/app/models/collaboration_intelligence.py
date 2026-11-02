"""Collaboration Intelligence models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class CollaborationEvidence(Base, TimestampMixin):
    __tablename__ = "collaboration_evidence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    participants: Mapped[List[str]] = mapped_column(JSON, default=list)
    strength: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_interaction: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_interaction: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    collaborationevidence_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_collab_evidence_org_participants", "organization_id", "participants"),
        Index("ix_collab_evidence_org_time", "organization_id", "last_interaction"),
    )


class CollaborationOrgRollup(Base, TimestampMixin):
    __tablename__ = "collaboration_org_rollups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_interactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_pairs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cross_department_pairs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_interaction_strength: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    most_active_departments: Mapped[List[dict]] = mapped_column(JSON, default=list)
    silo_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    collaboration_index: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "period_start", "period_end", name="uq_collab_org_rollup_period"),
        Index("ix_collab_org_rollups_org_period", "organization_id", "period_end"),
    )


class CollaborationPersonRollup(Base, TimestampMixin):
    __tablename__ = "collaboration_person_rollups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_interactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_collaborators: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cross_department_collaborators: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_interaction_strength: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    top_collaborators: Mapped[List[dict]] = mapped_column(JSON, default=list)
    network_centrality: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "period_start", "period_end", name="uq_collab_person_rollup_period"),
        Index("ix_collab_person_rollups_org_period", "organization_id", "period_end"),
    )


class CollaborationRelationship(Base, TimestampMixin):
    __tablename__ = "collaboration_relationships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_a_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    employee_b_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    strength: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    first_interaction: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_interaction: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    interaction_types: Mapped[List[str]] = mapped_column(JSON, default=list)
    shared_projects: Mapped[List[str]] = mapped_column(JSON, default=list)
    shared_teams: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_cross_department: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    collaborationevidence_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("employee_a_id", "employee_b_id", name="uq_collab_relationships_pair"),
        Index("ix_collab_rels_org_a", "organization_id", "employee_a_id"),
        Index("ix_collab_rels_org_b", "organization_id", "employee_b_id"),
    )


class CollaborationSignal(Base, TimestampMixin):
    __tablename__ = "collaboration_signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    signal_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    employee_a_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    employee_b_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    signal_strength: Mapped[float] = mapped_column(default=0.0, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(60), default="system", nullable=False)
    collaborationevidence_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_collab_signals_org_type", "organization_id", "signal_type"),
        Index("ix_collab_signals_org_pair", "organization_id", "employee_a_id", "employee_b_id"),
    )


class CollaborationUnitPair(Base, TimestampMixin):
    __tablename__ = "collaboration_unit_pairs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    unit_a_type: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_a_id: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_b_type: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_b_id: Mapped[str] = mapped_column(String(32), nullable=False)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    strength: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_interaction: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_cross_unit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    collaborationevidence_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("unit_a_type", "unit_a_id", "unit_b_type", "unit_b_id", name="uq_collab_unit_pairs_unique"),
        Index("ix_collab_unit_pairs_org", "organization_id"),
    )