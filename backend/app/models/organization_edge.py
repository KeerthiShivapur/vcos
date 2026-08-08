"""Phase 19 — Organization Graph edges.

Relationships: works_with, created, reviewed, approved, depends_on, reports_to,
knows, mentored, learned, owns, blocked_by, customer_of, vendor_of, attended,
mentioned, linked_to, member_of, assigned_to, contributed_to.
"""

from typing import Any, Optional

from sqlalchemy import JSON, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

EDGE_RELATIONS = (
    "works_with", "created", "reviewed", "approved", "depends_on", "reports_to",
    "knows", "mentored", "learned", "owns", "blocked_by", "customer_of",
    "vendor_of", "attended", "mentioned", "linked_to", "member_of",
    "assigned_to", "contributed_to",
)


class OrganizationEdge(Base, TimestampMixin):
    """One relationship between two organization graph nodes."""

    __tablename__ = "organization_edges"
    __table_args__ = (
        Index("ix_org_edges_org_source", "organization_id", "source_id"),
        Index("ix_org_edges_org_target", "organization_id", "target_id"),
        Index("ix_org_edges_org_relation", "organization_id", "relation"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False)
    relation: Mapped[str] = mapped_column(String(40), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    properties: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
