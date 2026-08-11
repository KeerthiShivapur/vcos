"""Slice 4C — governance kernel models: organizational scopes and approval policies.

One governance kernel for every organization size: scoped role assignments
(RBAC) anchored on a scope tree (organization -> business_unit -> region ->
department -> team -> project), scope-anchored delegations and approval
policies (ABAC context). Complexity emerges from the organization's
structure, never from separate authorization products.
"""

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class GovernanceScope(Base, TimestampMixin):
    """A node in the organization's governance tree.

    Role assignments, delegations and approval policies anchor to a scope;
    effective authority at a scope includes every ancestor scope. The scope
    tree is optional — an organization with no scopes behaves exactly like a
    flat role-permission org, so a 5-person startup never configures unused
    hierarchy levels.
    """

    __tablename__ = "governance_scopes"
    __table_args__ = (
        Index("ix_governance_scopes_org", "organization_id"),
        Index("ix_governance_scopes_parent", "parent_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # organization|business_unit|region|department|team|project
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False, default="department")
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("governance_scopes.id", ondelete="CASCADE")
    )
    entity_id: Mapped[Optional[str]] = mapped_column(String(64))
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ApprovalPolicy(Base, TimestampMixin):
    """Which authority decides which approval — the reusable approval mechanism.

    An approval created under a policy may only be decided by a user holding
    the policy's required permission at the policy's scope; self-approval is
    denied unless the policy explicitly allows it.
    """

    __tablename__ = "approval_policies"
    __table_args__ = (Index("ix_approval_policies_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    approval_type: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    description: Mapped[Optional[str]] = mapped_column(Text)
    required_permission: Mapped[str] = mapped_column(String(120), nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("governance_scopes.id", ondelete="SET NULL")
    )
    self_approval_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
