"""Customer Portal & account team models (Phase 12.11/12.12/12.10).

Portal users are external identities (customer employees) that authenticate
against their own token and are hard-scoped to a single customer record.
Account teams map internal employees (account manager, technical owner,
support owner, success manager, executive sponsor) to customers.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class PortalUser(Base, TimestampMixin):
    __tablename__ = "portal_users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_portal_user_email"),
        Index("ix_portal_users_customer", "organization_id", "customer_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    # customer_admin | customer_viewer
    portal_role: Mapped[str] = mapped_column(String(30), default="customer_viewer")
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notification_prefs: Mapped[Optional[dict]] = mapped_column(type_=String(2000), default=None)


class AccountTeam(Base, TimestampMixin):
    __tablename__ = "account_teams"
    __table_args__ = (
        UniqueConstraint("organization_id", "customer_id", "employee_id", "role", name="uq_account_team"),
        Index("ix_account_team_customer", "organization_id", "customer_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # account_manager | technical_owner | support_owner | success_manager | executive_sponsor
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
