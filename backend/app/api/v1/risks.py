"""Risks API — probability x impact risk register (Phase 3)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.work import RiskCreate, RiskOut, RiskUpdate
from app.work.risk_service import risk_service

router = APIRouter(prefix="/risks", tags=["Risks"])


@router.get("", response_model=list[RiskOut])
async def list_risks(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 200,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("risks:read")),
    db: AsyncSession = Depends(get_db),
):
    return await risk_service.list_all(
        db, organization_id=org.id, project_id=project_id, status=status,
        severity=severity, limit=limit,
    )


@router.post("", response_model=RiskOut, status_code=201)
async def create_risk(
    payload: RiskCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("risks:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        risk = await risk_service.create(
            db, organization_id=org.id, data=payload.model_dump(exclude_unset=True),
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    risk = await risk_service.get(db, organization_id=org.id, risk_id=risk.id)
    return RiskOut.model_validate(risk)


@router.get("/{risk_id}", response_model=RiskOut)
async def get_risk(
    risk_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("risks:read")),
    db: AsyncSession = Depends(get_db),
):
    risk = await risk_service.get(db, organization_id=org.id, risk_id=risk_id)
    if risk is None:
        raise HTTPException(404, "Risk not found")
    return RiskOut.model_validate(risk)


@router.patch("/{risk_id}", response_model=RiskOut)
async def update_risk(
    risk_id: str,
    payload: RiskUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("risks:manage")),
    db: AsyncSession = Depends(get_db),
):
    risk = await risk_service.get(db, organization_id=org.id, risk_id=risk_id)
    if risk is None:
        raise HTTPException(404, "Risk not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        risk = await risk_service.update(
            db, organization_id=org.id, risk=risk,
            data=payload.model_dump(exclude_unset=True), actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    risk = await risk_service.get(db, organization_id=org.id, risk_id=risk.id)
    return RiskOut.model_validate(risk)


@router.post("/{risk_id}/close", response_model=RiskOut)
async def close_risk(
    risk_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("risks:manage")),
    db: AsyncSession = Depends(get_db),
):
    risk = await risk_service.get(db, organization_id=org.id, risk_id=risk_id)
    if risk is None:
        raise HTTPException(404, "Risk not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    risk = await risk_service.close(
        db, organization_id=org.id, risk=risk, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    risk = await risk_service.get(db, organization_id=org.id, risk_id=risk.id)
    return RiskOut.model_validate(risk)


@router.delete("/{risk_id}", response_model=Message)
async def delete_risk(
    risk_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("risks:manage")),
    db: AsyncSession = Depends(get_db),
):
    risk = await risk_service.get(db, organization_id=org.id, risk_id=risk_id)
    if risk is None:
        raise HTTPException(404, "Risk not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    await risk_service.delete(
        db, organization_id=org.id, risk=risk, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Risk deleted")
