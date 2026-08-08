"""Phase 8.13 — Executive Reports API."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.executive.reporting import REPORT_TYPES, reporting_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/executive/reports", tags=["executive"])


class ReportIn(BaseModel):
    report_type: str = "weekly"
    department_id: Optional[str] = None


@router.post("")
async def generate_report(
    payload: ReportIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = await reporting_service.generate(
            db,
            organization_id=org.id,
            report_type=payload.report_type,
            user_id=user.id,
            department_id=payload.department_id,
            persist=True,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    await db.commit()
    return result


@router.get("")
async def list_reports(
    limit: int = Query(default=50, ge=1, le=100),
    report_type: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await reporting_service.list(db, organization_id=org.id, limit=limit)


@router.get("/types")
async def report_types(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
) -> dict[str, Any]:
    return {"report_types": REPORT_TYPES}
