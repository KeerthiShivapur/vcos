"""Execution Coordination models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class CoordinationIncidentStatus(str):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


INCIDENT_KINDS = (
    "dependency_conflict",
    "resource_contention",
    "priority_conflict",
    "timeline_misalignment",
    "resource_shortage",
    "capability_gap",
    "communication_breakdown",
    "decision_bottleneck",
    "external_dependency",
    "scope_creep",
    "quality_issue",
    "compliance_risk",
    "security_incident",
    "performance_degradation",
    "integration_failure",
)

COORDINATION_INCIDENT_STATUS = ("open", "in_progress", "resolved", "closed")


class CoordinationIncident(Base, TimestampMixin):
    __tablename__ = "coordination_incidents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    incident_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=CoordinationIncidentStatus.OPEN, nullable=False, index=True)
    affected_projects: Mapped[List[str]] = mapped_column(JSON, default=list)
    affected_teams: Mapped[List[str]] = mapped_column(JSON, default=list)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reporter_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    root_cause: Mapped[Optional[str]] = mapped_column(Text)
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    lessons_learned: Mapped[Optional[str]] = mapped_column(Text)
    coordinationincidentstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_coord_incidents_org_status", "organization_id", "status"),
        Index("ix_coord_incidents_org_type", "organization_id", "incident_type"),
    )


class CoordinationHandoff(Base, TimestampMixin):
    __tablename__ = "coordination_handoffs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    to_entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    to_entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    handoff_type: Mapped[str] = mapped_column(String(40), nullable=False)  # project_handoff, task_handoff, ownership_transfer, knowledge_transfer
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    from_owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    to_owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)  # pending, in_progress, completed, cancelled
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    items: Mapped[List[dict]] = mapped_column(JSON, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    coordinationincidentstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_coord_handoffs_org_status", "organization_id", "status"),
        Index("ix_coord_handoffs_org_type", "organization_id", "handoff_type"),
    )


class CoordinationHistory(Base, TimestampMixin):
    __tablename__ = "coordination_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    before_state: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    after_state: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    coordinationincidentstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_coord_history_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_coord_history_org_time", "organization_id", "created_at"),
    )