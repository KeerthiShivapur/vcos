from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class InviteUserRequest(BaseModel):
    email: EmailStr
    full_name: Optional[str] = Field(default=None, max_length=255)
    role: str = "employee"
    message: Optional[str] = None


class InviteResult(BaseModel):
    invitation: "InvitationOut"
    token: Optional[str] = None  # returned in development transport only
    url: Optional[str] = None


class UpdateUserStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|suspended|deactivated)$")


class AssignRoleRequest(BaseModel):
    role_id: str
    replace_all: bool = True


class InvitationOut(ORMModel):
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    status: str
    message: Optional[str] = None
    created_at: datetime
    expires_at: datetime


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
    roles: List["RoleBrief"] = []
    permissions: List[str] = []


class RoleBrief(ORMModel):
    id: str
    name: str
    code: str
    is_system: bool
    is_default: bool


class PermissionOut(ORMModel):
    id: str
    code: str
    name: str
    resource: str
    action: str
    description: Optional[str] = None


class RoleOut(ORMModel):
    id: str
    name: str
    code: str
    description: Optional[str] = None
    is_system: bool
    is_default: bool
    created_at: datetime
    permissions: List[PermissionOut] = []
    user_count: int = 0


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=120, pattern=r"^[a-z][a-z0-9_]*$")
    description: Optional[str] = None
    permission_ids: List[str] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[List[str]] = None
