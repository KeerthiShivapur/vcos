"""Audit log: read with filters, list known action names, export."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.models.organization import Organization
from app.models.user import User
from app.models.notification import AuditLog
from app.schemas.common import Paginated
from app.schemas.notifications import AuditLogOut
from app.db.database import get_db
from app.services.audit_service import audit_service

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("", response_model=Paginated[AuditLogOut])
async def list_audit_logs(
    user: User = Depends(require_permission("audit:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
):
    items, total = await audit_service.list_logs(
        db,
        organization_id=org.id,
        page=page,
        page_size=page_size,
        action=action,
        actor_id=actor_id,
        severity=severity,
        outcome=outcome,
        resource_type=resource_type,
        from_date=from_date,
        to_date=to_date,
    )
    return Paginated(
        items=[AuditLogOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size) if page_size else 0,
    )


@router.get("/actions", response_model=list[str])
async def audit_actions(user: User = Depends(require_permission("audit:read")), org: Organization = Depends(get_current_organization)):
    return audit_service.action_names()
