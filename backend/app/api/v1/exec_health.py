"""Phase 8.2 — Company & Department Health API."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.executive.health_engine import health_engine
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/executive/health", tags=["executive"])


@router.get("")
async def company_health(
    refresh: bool = False,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await health_engine.compute_company_health(
        db, organization_id=org.id, persist=refresh
    )


@router.get("/departments")
async def departments_health(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await health_engine.departments_health(db, organization_id=org.id)
    return {"total": len(rows), "departments": rows}


@router.get("/departments/{department_id}")
async def department_health(
    department_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await health_engine.department_health(
            db, organization_id=org.id, department_id=department_id
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/projects/{project_id}")
async def project_health(
    project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await health_engine.project_health(
            db, organization_id=org.id, project_id=project_id
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))
