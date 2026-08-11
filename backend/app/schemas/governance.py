"""Slice 4C — governance schemas (scopes, scoped roles, delegations, policies)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ScopeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    scope_type: str = Field(default="department", pattern="^(organization|business_unit|region|department|team|project)$")
    parent_id: Optional[str] = None
    entity_id: Optional[str] = None


class ScopeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)


class ScopeOut(ORMModel):
    id: str
    name: str
    scope_type: str
    parent_id: Optional[str] = None
    entity_id: Optional[str] = None
    depth: int
    created_at: datetime


class AssignmentCreate(BaseModel):
    user_id: str
    role_id: str
    scope_id: Optional[str] = None  # null = organization-wide


class AssignmentOut(ORMModel):
    id: str
    user_id: str
    role_id: str
    scope_id: Optional[str] = None
    created_at: datetime


class DelegationCreate(BaseModel):
    granted_to_user: str
    permission_code: str
    scope_id: Optional[str] = None
    reason: Optional[str] = None
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class DelegationOut(ORMModel):
    id: str
    granted_by: Optional[str] = None
    granted_to_user: str
    permission_code: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    reason: Optional[str] = None
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    status: str
    created_at: datetime


class PolicyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    approval_type: str = Field(default="other", max_length=40)
    description: Optional[str] = None
    required_permission: str = Field(min_length=3, max_length=120)
    scope_id: Optional[str] = None
    self_approval_allowed: bool = False


class PolicyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    description: Optional[str] = None
    required_permission: Optional[str] = Field(default=None, min_length=3, max_length=120)
    scope_id: Optional[str] = None
    self_approval_allowed: Optional[bool] = None
    is_active: Optional[bool] = None


class PolicyOut(ORMModel):
    id: str
    name: str
    approval_type: str
    description: Optional[str] = None
    required_permission: str
    scope_id: Optional[str] = None
    self_approval_allowed: bool
    is_active: bool
    created_at: datetime


class EffectivePermissionsOut(BaseModel):
    user_id: str
    scope_id: Optional[str] = None
    permissions: List[str]
    has_permission: dict[str, bool]
