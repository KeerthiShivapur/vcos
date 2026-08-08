"""SOPs API — standard operating procedures with checklist steps (Phase 4.5)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.knowledge.presenters import present
from app.knowledge.sop_service import sop_service
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.knowledge import SOPCreate, SOPOut, SOPUpdate

router = APIRouter(prefix="/sops", tags=["SOPs"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


@router.get("", response_model=list[SOPOut])
async def list_sops(
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await sop_service.list_all(
        db, organization_id=org.id, status=status, category=category, search=search,
        limit=min(limit, 500), offset=offset,
    )
    return [await present(db, organization_id=org.id, entity=row, kind="sop") for row in rows]


@router.post("", response_model=SOPOut, status_code=201)
async def create_sop(
    payload: SOPCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await sop_service.create(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="sop")


@router.get("/{sop_id}", response_model=SOPOut)
async def get_sop(
    sop_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    entity = await sop_service.get(db, organization_id=org.id, entity_id=sop_id)
    if entity is None:
        raise HTTPException(404, "SOP not found")
    from app.knowledge import knowledge_base as kb

    await kb.register_view(db, organization_id=org.id, entity_type="sop", entity_id=sop_id, user_id=user.id)
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="sop")


@router.patch("/{sop_id}", response_model=SOPOut)
async def update_sop(
    sop_id: str,
    payload: SOPUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await sop_service.update(
        db, organization_id=org.id, entity_id=sop_id,
        payload=payload.model_dump(exclude_unset=True), actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "SOP not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="sop")


@router.delete("/{sop_id}", response_model=Message)
async def delete_sop(
    sop_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if not await sop_service.delete(
        db, organization_id=org.id, entity_id=sop_id, actor=actor, ip_address=get_client_ip(request)
    ):
        raise HTTPException(404, "SOP not found")
    await db.commit()
    return Message(message="SOP deleted")


@router.post("/{sop_id}/publish", response_model=SOPOut)
async def publish_sop(
    sop_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await sop_service.set_status(
        db, organization_id=org.id, entity_id=sop_id, status="published",
        actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "SOP not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="sop")
