"""Phase 19 — Organization Graph nodes.

Every major entity (employees, projects, tasks, meetings, goals, knowledge,
customers, documents, workflows, departments, communities, policies, assets,
learning, decisions) participates in a unified enterprise graph as a node.
"""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

NODE_TYPES = (
    "employee", "project", "task", "meeting", "goal", "knowledge", "customer",
    "document", "workflow", "department", "community", "policy", "asset",
    "learning", "idea", "recognition", "decision", "contract", "vendor",
    "innovation", "team",
)


class OrganizationNode(Base, TimestampMixin):
    """One node in the organization intelligence network."""

    __tablename__ = "organization_nodes"
    __table_args__ = (
        Index("ix_org_nodes_org_type", "organization_id", "node_type"),
        Index("ix_org_nodes_org_name", "organization_id", "name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    node_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # stable external id so re-syncs update the same node (e.g. the project id)
    external_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    properties: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    importance: Mapped[float] = mapped_column(Float, default=1.0)
    last_seen_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
