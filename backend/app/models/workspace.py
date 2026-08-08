from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False, unique=True
    )
    daily_goal: Mapped[Optional[str]] = mapped_column(Text)
    onboarding_completed: Mapped[bool] = mapped_column(default=False)
    onboarded_at: Mapped[Optional[str]] = mapped_column(String(40))


class WorkspaceItem(Base, TimestampMixin):
    __tablename__ = "workspace_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), index=True)  # note | bookmark | shortcut | pin | reminder | recent
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    link: Mapped[Optional[str]] = mapped_column(String(500))
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    pinned: Mapped[bool] = mapped_column(default=False)


class AITenantMemory(Base, TimestampMixin):
    """AI memory foundation: per-organization knowledge memory that later
    phases (AI Companion, Background Intelligence) will read and write."""

    __tablename__ = "ai_tenant_memory"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scope: Mapped[str] = mapped_column(String(60), default="organization")  # organization | user | project
    subject_id: Mapped[Optional[str]] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(60), index=True)  # fact | insight | context | preference
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(120))
    confidence: Mapped[Optional[float]] = mapped_column(default=1.0)
