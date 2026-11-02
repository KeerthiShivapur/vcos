"""User model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid, utcnow


class UserRole(str):
    OWNER = "owner"
    ADMIN = "admin"
    CEO = "ceo"
    MANAGER = "manager"
    MEMBER = "member"
    VIEWER = "viewer"


class UserStatus(str):
    ACTIVE = "active"
    INACTIVE = "inactive"
    INVITED = "invited"
    SUSPENDED = "suspended"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(200))
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.MEMBER, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=UserStatus.INVITED, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    preferences: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="users")
    employee: Mapped[Optional["Employee"]] = relationship(back_populates="user", uselist=False, foreign_keys="Employee.user_id")
    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    trusted_devices: Mapped[list["TrustedDevice"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    mfa_methods: Mapped[list["MFAMethod"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_users_org_email", "organization_id", "email"),
        UniqueConstraint("organization_id", "username", name="uq_users_org_username"),
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        {"extend_existing": True},
    )


class Session(Base, TimestampMixin):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    refresh_token_hash: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    device_name: Mapped[Optional[str]] = mapped_column(String(200))
    device_type: Mapped[Optional[str]] = mapped_column(String(50))
    browser: Mapped[Optional[str]] = mapped_column(String(50))
    os: Mapped[Optional[str]] = mapped_column(String(50))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    session_userrole_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_sessions_user_expires", "user_id", "expires_at"),
    )


class TrustedDevice(Base, TimestampMixin):
    __tablename__ = "trusted_devices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    device_fingerprint: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(200))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    device_userrole_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="trusted_devices")

    __table_args__ = (
        Index("ix_trusted_devices_user_fingerprint", "user_id", "device_fingerprint"),
    )


class MFAMethod(Base, TimestampMixin):
    __tablename__ = "mfa_methods"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    method_type: Mapped[str] = mapped_column(String(20), nullable=False)  # totp, sms, email, backup_codes
    name: Mapped[Optional[str]] = mapped_column(String(100))
    secret_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    phone_number: Mapped[Optional[str]] = mapped_column(String(30))
    email: Mapped[Optional[str]] = mapped_column(String(320))
    backup_codes_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    mfa_userrole_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="mfa_methods")

    __table_args__ = (
        Index("ix_mfa_methods_user_type", "user_id", "method_type"),
    )


class SecurityAuditEvent(Base, TimestampMixin):
    __tablename__ = "security_audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    details: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    resource_type: Mapped[Optional[str]] = mapped_column(String(60))
    resource_id: Mapped[Optional[str]] = mapped_column(String(32))

    __table_args__ = (
        Index("ix_security_audit_org_created", "organization_id", "created_at"),
        Index("ix_security_audit_user_created", "user_id", "created_at"),
    )


class OrganizationSecurityPolicy(Base, TimestampMixin):
    __tablename__ = "organization_security_policies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    password_min_length: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    password_require_uppercase: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_require_lowercase: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_require_numbers: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_require_symbols: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_max_age_days: Mapped[Optional[int]] = mapped_column(Integer)
    password_history_count: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    mfa_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_allowed_methods: Mapped[list] = mapped_column(JSON, default=list)
    session_timeout_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    session_max_duration_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    max_concurrent_sessions: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    require_mfa_for_admin: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_failed_login_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    lockout_duration_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    require_email_verification: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_employee_self_registration: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allowed_domains: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    blocked_domains: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    ip_allowlist: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    ip_blocklist: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    session_idle_timeout_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    require_mfa_for_sensitive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_countries: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    blocked_countries: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("ix_org_security_policy_org", "organization_id"),
    )


class AccessReview(Base, TimestampMixin):
    __tablename__ = "access_reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)  # role, permission, resource
    scope_value: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)  # pending, in_progress, completed, cancelled
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    review_userrole_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_access_reviews_org_status", "organization_id", "status"),
        Index("ix_access_reviews_reviewer", "reviewer_id"),
    )


class AccessReviewItem(Base, TimestampMixin):
    __tablename__ = "access_review_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    review_id: Mapped[str] = mapped_column(ForeignKey("access_reviews.id", ondelete="CASCADE"), index=True, nullable=False)
    subject_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)  # user, group
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(32), nullable=False)
    current_access: Mapped[str] = mapped_column(String(500), nullable=False)
    decision: Mapped[Optional[str]] = mapped_column(String(20))  # approve, revoke, modify
    decided_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    comment: Mapped[Optional[str]] = mapped_column(Text)
    item_userrole_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_access_review_items_review", "review_id"),
        Index("ix_access_review_items_subject", "subject_user_id"),
    )