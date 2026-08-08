import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.common import ORMModel, RoleBrief, TokenPair
from app.schemas.organization import OrganizationOut


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=255)
    organization_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    industry: Optional[str] = None
    country: Optional[str] = None
    timezone: str = "UTC"
    currency: str = "USD"
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    username: Optional[str] = Field(default=None, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class InviteRegisterRequest(BaseModel):
    """Registration by an invited employee (accept invitation + create account)."""

    token: str
    full_name: str = Field(min_length=2, max_length=255)
    username: Optional[str] = Field(default=None, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False
    device_name: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None
    all_devices: bool = False


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str


class UserOut(ORMModel):
    id: str
    organization_id: str
    email: str
    username: Optional[str] = None
    full_name: str
    status: str
    role: str
    timezone: str
    language: str
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    email_verified_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    roles: List[RoleBrief] = []
    permissions: List[str] = []


class LoginResult(TokenPair):
    user: "UserOut"
    organization: "OrganizationOut"


LoginResult.model_rebuild()


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    username: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    avatar_url: Optional[str] = None


class SessionOut(ORMModel):
    id: str
    device_name: Optional[str] = None
    device_type: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    last_activity_at: Optional[datetime] = None
    expires_at: datetime
    is_current: bool


class InvitationOut(ORMModel):
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    status: str
    message: Optional[str] = None
    created_at: datetime
    expires_at: datetime
