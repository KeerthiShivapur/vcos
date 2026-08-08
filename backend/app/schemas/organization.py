from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    industry: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    currency: Optional[str] = None
    domain: Optional[str] = None


class OrganizationBranding(BaseModel):
    brand_primary_color: Optional[str] = None
    logo_url: Optional[str] = None
    brand_logo_dark_url: Optional[str] = None


class OrganizationSettingsUpdate(BaseModel):
    allow_employee_self_registration: Optional[bool] = None
    require_email_verification: Optional[bool] = None
    default_theme: Optional[str] = None
    weekly_digest: Optional[bool] = None
    announcement_enabled: Optional[bool] = None
    retention_days_audit: Optional[int] = Field(default=None, ge=30, le=3650)
    retention_days_notifications: Optional[int] = Field(default=None, ge=7, le=730)


class OrganizationOut(ORMModel):
    id: str
    name: str
    slug: str
    industry: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    country: Optional[str] = None
    timezone: str
    language: str
    currency: str
    status: str
    domain: Optional[str] = None
    brand_primary_color: str
    created_at: object


class OrganizationSettingsOut(ORMModel):
    allow_employee_self_registration: bool
    require_email_verification: bool
    default_theme: str
    weekly_digest: bool
    announcement_enabled: bool
    retention_days_audit: int
    retention_days_notifications: int


class OrganizationStats(BaseModel):
    total_users: int
    active_users: int
    pending_invitations: int
    roles_count: int
    permissions_count: int
    sessions_active: int
    notifications_unread: int
    audit_entries: int
    created_at: object
