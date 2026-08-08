"""Approvals API — polymorphic approval workflows (Phase 3)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.work import ApprovalCreate, ApprovalDecide, ApprovalOut
from app.work.approval_service import approval_service

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    status: Optional[str] = None,
    approval_type: Optional[str] = None,
    employee_id: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("approvals:read")),
    db: AsyncSession = Depends(get_db),
):
    return await approval_service.list_all(
        db, organization_id=org.id, status=status,
        approval_type=approval_type, employee_id=employee_id,
    )


@router.post("", response_model=ApprovalOut, status_code=201)
async def create_approval(
    payload: ApprovalCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("approvals:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        approval = await approval_service.create(
            db, organization_id=org.id, data=payload.model_dump(exclude_unset=True),
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    approval = await approval_service.get(db, organization_id=org.id, approval_id=approval.id)
    return ApprovalOut.model_validate(approval)


@router.get("/stats", response_model=dict)
async def approval_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("approvals:read")),
    db: AsyncSession = Depends(get_db),
):
    return await approval_service.stats(db, organization_id=org.id)


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval(
    approval_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("approvals:read")),
    db: AsyncSession = Depends(get_db),
):
    approval = await approval_service.get(db, organization_id=org.id, approval_id=approval_id)
    if approval is None:
        raise HTTPException(404, "Approval not found")
    return ApprovalOut.model_validate(approval)


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
async def decide_approval(
    approval_id: str,
    payload: ApprovalDecide,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("approvals:manage")),
    db: AsyncSession = Depends(get_db),
):
    approval = await approval_service.get(db, organization_id=org.id, approval_id=approval_id)
    if approval is None:
        raise HTTPException(404, "Approval not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        approval = await approval_service.decide(
            db, organization_id=org.id, approval=approval,
            decision=payload.decision, note=payload.note,
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    approval = await approval_service.get(db, organization_id=org.id, approval_id=approval.id)
    return ApprovalOut.model_validate(approval)


@router.post("/{approval_id}/cancel", response_model=ApprovalOut)
async def cancel_approval(
    approval_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("approvals:manage")),
    db: AsyncSession = Depends(get_db),
):
    approval = await approval_service.get(db, organization_id=org.id, approval_id=approval_id)
    if approval is None:
        raise HTTPException(404, "Approval not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        approval = await approval_service.cancel(
            db, organization_id=org.id, approval=approval,
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    approval = await approval_service.get(db, organization_id=org.id, approval_id=approval.id)
    return ApprovalOut.model_validate(approval)
