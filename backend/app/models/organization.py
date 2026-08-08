import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def gen_uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(120))
    description: Mapped[Optional[str]] = mapped_column(Text)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    country: Mapped[Optional[str]] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    language: Mapped[str] = mapped_column(String(10), default="en")
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    owner_id: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | suspended | deleted
    domain: Mapped[Optional[str]] = mapped_column(String(255))
    brand_primary_color: Mapped[str] = mapped_column(String(20), default="#4F46E5")
    brand_logo_dark_url: Mapped[Optional[str]] = mapped_column(String(500))

    users: Mapped[list["User"]] = relationship(back_populates="organization")  # noqa: F821
    roles: Mapped[list["Role"]] = relationship(back_populates="organization", cascade="all, delete-orphan")  # noqa: F821


class OrganizationSettings(Base, TimestampMixin):
    __tablename__ = "organization_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    allow_employee_self_registration: Mapped[bool] = mapped_column(Boolean, default=False)
    require_email_verification: Mapped[bool] = mapped_column(Boolean, default=False)
    default_theme: Mapped[str] = mapped_column(String(20), default="system")
    weekly_digest: Mapped[bool] = mapped_column(Boolean, default=True)
    announcement_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    retention_days_audit: Mapped[int] = mapped_column(Integer, default=365)
    retention_days_notifications: Mapped[int] = mapped_column(Integer, default=90)
