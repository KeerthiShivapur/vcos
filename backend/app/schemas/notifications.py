from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class NotificationOut(ORMModel):
    id: str
    type: str
    title: str
    body: Optional[str] = None
    priority: str
    link: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime


class MarkReadRequest(BaseModel):
    ids: Optional[List[str]] = None  # None = all


class NotificationStats(BaseModel):
    total_unread: int
    by_priority: dict[str, int]
    by_type: dict[str, int]


class AuditLogOut(ORMModel):
    id: str
    actor_id: Optional[str] = None
    actor_email: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    severity: str
    outcome: str
    details: Optional[Any] = None
    created_at: datetime


class EventOut(ORMModel):
    id: str
    organization_id: Optional[str] = None
    actor_id: Optional[str] = None
    name: str
    occurred_at: datetime
    processed_at: Optional[datetime] = None
