"""Workspace and AI Tenant Memory models."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class AITenantMemory(Base, TimestampMixin):
    """AI memory storage for tenant-specific context and learning."""

    __tablename__ = "ai_tenant_memory"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    namespace: Mapped[str] = mapped_column(String(100), default="default", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    access_level: Mapped[str] = mapped_column(String(20), default="private", nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("organization_id", "namespace", "key", name="uq_ai_tenant_memory_org_ns_key"),
        Index("ix_ai_tenant_memory_org_ns", "organization_id", "namespace"),
        Index("ix_ai_tenant_memory_expires", "expires_at"),
    )


class Workspace(Base, TimestampMixin):
    """User workspace configuration and state."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="Default Workspace")
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    layout: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    pinned_items: Mapped[List[str]] = mapped_column(JSON, default=list)
    recent_items: Mapped[List[str]] = mapped_column(JSON, default=list)
    active_view: Mapped[Optional[str]] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_workspaces_user_name"),
        Index("ix_workspaces_user_org", "user_id", "organization_id"),
    )


class WorkspaceItem(Base, TimestampMixin):
    """Items within a workspace (documents, widgets, shortcuts, etc.)."""

    __tablename__ = "workspace_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    item_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # document, widget, shortcut, note, app
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    size: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)  # width, height
    position_data: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)  # x, y, z
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    aitenantmemory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_workspace_items_workspace_position", "workspace_id", "position"),
        Index("ix_workspace_items_org_type", "organization_id", "item_type"),
    )


class WorkspaceSettings(Base):
    """Global workspace settings for an organization."""

    __tablename__ = "workspace_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    default_workspace_layout: Mapped[dict] = mapped_column(JSON, default=dict)
    allow_custom_workspaces: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_workspaces_per_user: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    default_pinned_items: Mapped[List[str]] = mapped_column(JSON, default=list)
    allowed_item_types: Mapped[List[str]] = mapped_column(JSON, default=list)
    theme: Mapped[str] = mapped_column(String(20), default="system", nullable=False)
    sidebar_collapsed_by_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_recent_items: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_recent_items: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    auto_save_interval_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    enable_ai_suggestions: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    aitenantmemory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


class GameSession(Base, TimestampMixin):
    """Collaborative game/session for team building or planning."""

    __tablename__ = "game_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    game_type: Mapped[str] = mapped_column(String(50), nullable=False)  # planning_poker, retro, brainstorm, etc.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="waiting", nullable=False)  # waiting, active, completed, cancelled
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_game_sessions_org_status", "organization_id", "status"),
        Index("ix_game_sessions_creator", "created_by"),
    )


class WorkspaceSession(Base, TimestampMixin):
    """Active user session within a workspace."""

    __tablename__ = "workspace_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    connection_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    device_info: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_workspace_sessions_workspace_user", "workspace_id", "user_id"),
        Index("ix_workspace_sessions_org_active", "organization_id", "is_active"),
    )


class VirtualOfficeFloor(Base, TimestampMixin):
    """Virtual office floor for spatial collaboration."""

    __tablename__ = "virtual_office_floors"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    floor_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    background_image: Mapped[Optional[str]] = mapped_column(String(500))
    background_color: Mapped[str] = mapped_column(String(7), default="#f5f5f5", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    aitenantmemory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_virtual_office_floors_org", "organization_id"),
    )


class VirtualOfficeRoom(Base, TimestampMixin):
    """Room within a virtual office floor."""

    __tablename__ = "virtual_office_rooms"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    floor_id: Mapped[str] = mapped_column(
        ForeignKey("virtual_office_floors.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    room_type: Mapped[str] = mapped_column(String(40), default="meeting", nullable=False)  # meeting, focus, social, etc.
    x: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    y: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    access_code: Mapped[Optional[str]] = mapped_column(String(50))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    aitenantmemory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_virtual_office_rooms_floor", "floor_id"),
    )