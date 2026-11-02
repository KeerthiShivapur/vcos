"""Organization and user models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, JSON, ForeignKey, Enum as SQLEnum, Index, DateTime, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    INVITED = "invited"
    SUSPENDED = "suspended"


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    website: Mapped[Optional[str]] = mapped_column(String(255))
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    size: Mapped[Optional[int]] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    language: Mapped[str] = mapped_column(String(10), default="en")
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    brand_primary_color: Mapped[str] = mapped_column(String(7), default="#3B82F6", nullable=False)
    settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    subscription_tier: Mapped[str] = mapped_column(String(50), default="free")

    # Relationships
    users: Mapped[List["User"]] = relationship("User", back_populates="organization")
    departments: Mapped[List["Department"]] = relationship(back_populates="organization")
    teams: Mapped[List["Team"]] = relationship(back_populates="organization")
    experience_config: Mapped[Optional["CompanyExperienceConfig"]] = relationship(back_populates="organization", uselist=False)
    adaptive_profile: Mapped[Optional["AdaptiveOperatingProfile"]] = relationship(back_populates="organization", uselist=False)
    adaptive_profile_versions: Mapped[List["AdaptiveOperatingProfileVersion"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
        order_by="AdaptiveOperatingProfileVersion.version"
    )
    capability_lifecycle_records: Mapped[List["CapabilityLifecycleRecord"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    integration_config_records: Mapped[List["IntegrationConfigRecord"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    workflow_configurations: Mapped[List["WorkflowConfigurationRecord"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    adaptation_recommendations: Mapped[List["AdaptationRecommendationRecord"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    experience_profile_history: Mapped[List["CompanyExperienceProfileHistory"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    employees: Mapped[List["Employee"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    user_roles: Mapped[List["UserRoleModel"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    meetings: Mapped[List["Meeting"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    projects: Mapped[List["Project"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    business_units: Mapped[List["BusinessUnit"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    locations: Mapped[List["Location"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    settings_obj: Mapped[Optional["OrganizationSettings"]] = relationship(
        back_populates="organization",
        uselist=False,
        cascade="all, delete-orphan",
    )


class OrganizationSettings(Base, TimestampMixin):
    __tablename__ = "organization_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    # Feature flags
    enable_ai_features: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_analytics: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_collaboration: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_learning: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_wellness: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_finance: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_meetings: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_projects: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_approvals: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_audit_log: Mapped[bool] = mapped_column(Boolean, default=True)
    # Security
    require_mfa: Mapped[bool] = mapped_column(Boolean, default=False)
    password_min_length: Mapped[int] = mapped_column(Integer, default=8)
    session_timeout_minutes: Mapped[int] = mapped_column(Integer, default=60)
    max_failed_login_attempts: Mapped[int] = mapped_column(Integer, default=5)
    lockout_duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    # Compliance
    data_retention_days: Mapped[int] = mapped_column(Integer, default=2555)  # 7 years
    audit_log_retention_days: Mapped[int] = mapped_column(Integer, default=2555)
    # Integrations
    allowed_integrations: Mapped[List[str]] = mapped_column(JSON, default=list)
    # Custom settings
    custom_settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    organization: Mapped["Organization"] = relationship(back_populates="settings_obj", uselist=False)


class PlatformInfo(Base):
    __tablename__ = "platform_info"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(100), default="VCOS")
    version: Mapped[str] = mapped_column(String(20))
    environment: Mapped[str] = mapped_column(String(20), default="development")
    api_version: Mapped[str] = mapped_column(String(20), default="v1")
    ai_provider: Mapped[str] = mapped_column(String(50), default="openai")
    features: Mapped[Dict[str, bool]] = mapped_column(JSON, default=lambda: {
        "foundation": True,
        "ai_foundation": True,
        "redis": True,
    })
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    maintenance_message: Mapped[Optional[str]] = mapped_column(Text)
    uptime_seconds: Mapped[int] = mapped_column(Integer, default=0)