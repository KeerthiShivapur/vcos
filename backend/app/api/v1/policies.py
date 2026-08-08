"""Policies API — company policies with ownership, approval and review cycles (Phase 4.4)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.knowledge.policy_service import policy_service
from app.knowledge.presenters import present
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.knowledge import PolicyCreate, PolicyOut, PolicyUpdate, WorkflowAction

router = APIRouter(prefix="/policies", tags=["Policies"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


@router.get("", response_model=list[PolicyOut])
async def list_policies(
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await policy_service.list_all(
        db, organization_id=org.id, status=status, category=category, search=search,
        limit=min(limit, 500), offset=offset,
    )
    return [await present(db, organization_id=org.id, entity=row, kind="policy") for row in rows]


@router.post("", response_model=PolicyOut, status_code=201)
async def create_policy(
    payload: PolicyCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await policy_service.create(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="policy")


@router.get("/overdue", response_model=list[PolicyOut])
async def overdue_policies(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await policy_service.overdue_reviews(db, organization_id=org.id)
    return [await present(db, organization_id=org.id, entity=row, kind="policy") for row in rows]


@router.get("/{policy_id}", response_model=PolicyOut)
async def get_policy(
    policy_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    entity = await policy_service.get(db, organization_id=org.id, entity_id=policy_id)
    if entity is None:
        raise HTTPException(404, "Policy not found")
    from app.knowledge import knowledge_base as kb

    await kb.register_view(db, organization_id=org.id, entity_type="policy", entity_id=policy_id, user_id=user.id)
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="policy")


@router.patch("/{policy_id}", response_model=PolicyOut)
async def update_policy(
    policy_id: str,
    payload: PolicyUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await policy_service.update(
        db, organization_id=org.id, entity_id=policy_id,
        payload=payload.model_dump(exclude_unset=True), actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Policy not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="policy")


@router.delete("/{policy_id}", response_model=Message)
async def delete_policy(
    policy_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if not await policy_service.delete(
        db, organization_id=org.id, entity_id=policy_id, actor=actor, ip_address=get_client_ip(request)
    ):
        raise HTTPException(404, "Policy not found")
    await db.commit()
    return Message(message="Policy deleted")


@router.post("/{policy_id}/submit", response_model=PolicyOut)
async def submit_policy(
    policy_id: str,
    payload: Optional[WorkflowAction] = None,
    request: Request = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    approver_id = (payload.approver_id if payload else None)
    entity = await policy_service.submit_for_approval(
        db, organization_id=org.id, entity_id=policy_id, actor=actor,
        ip_address=get_client_ip(request), approver_id=approver_id,
    )
    if entity is None:
        raise HTTPException(404, "Policy not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="policy")


@router.post("/{policy_id}/approve", response_model=PolicyOut)
async def approve_policy(
    policy_id: str,
    payload: Optional[WorkflowAction] = None,
    request: Request = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:approve")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    note = payload.note if payload else None
    entity = await policy_service.approve(
        db, organization_id=org.id, entity_id=policy_id, actor=actor,
        ip_address=get_client_ip(request), note=note,
    )
    if entity is None:
        raise HTTPException(404, "Policy not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="policy")


@router.post("/{policy_id}/reject", response_model=PolicyOut)
async def reject_policy(
    policy_id: str,
    payload: Optional[WorkflowAction] = None,
    request: Request = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:approve")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    note = payload.note if payload else None
    entity = await policy_service.reject(
        db, organization_id=org.id, entity_id=policy_id, actor=actor,
        ip_address=get_client_ip(request), note=note,
    )
    if entity is None:
        raise HTTPException(404, "Policy not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="policy")
