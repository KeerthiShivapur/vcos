"""Templates API — reusable document templates (Phase 4.6)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.knowledge.presenters import present
from app.knowledge.template_service import template_service
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.knowledge import TemplateCreate, TemplateOut, TemplateUpdate

router = APIRouter(prefix="/templates", tags=["Templates"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await template_service.list_all(
        db, organization_id=org.id, status=status, category=category, search=search,
        limit=min(limit, 500), offset=offset,
    )
    return [await present(db, organization_id=org.id, entity=row, kind="template") for row in rows]


@router.post("", response_model=TemplateOut, status_code=201)
async def create_template(
    payload: TemplateCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await template_service.create(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="template")


@router.get("/most-used", response_model=list[TemplateOut])
async def most_used_templates(
    limit: int = 10,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await template_service.most_used(db, organization_id=org.id, limit=min(limit, 50))
    return [await present(db, organization_id=org.id, entity=row, kind="template") for row in rows]


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    entity = await template_service.get(db, organization_id=org.id, entity_id=template_id)
    if entity is None:
        raise HTTPException(404, "Template not found")
    from app.knowledge import knowledge_base as kb

    await kb.register_view(db, organization_id=org.id, entity_type="template", entity_id=template_id, user_id=user.id)
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="template")


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: str,
    payload: TemplateUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await template_service.update(
        db, organization_id=org.id, entity_id=template_id,
        payload=payload.model_dump(exclude_unset=True), actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Template not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="template")


@router.delete("/{template_id}", response_model=Message)
async def delete_template(
    template_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if not await template_service.delete(
        db, organization_id=org.id, entity_id=template_id, actor=actor, ip_address=get_client_ip(request)
    ):
        raise HTTPException(404, "Template not found")
    await db.commit()
    return Message(message="Template deleted")


@router.post("/{template_id}/use", response_model=TemplateOut)
async def use_template(
    template_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    entity = await template_service.record_usage(db, organization_id=org.id, entity_id=template_id)
    if entity is None:
        raise HTTPException(404, "Template not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="template")


@router.post("/{template_id}/publish", response_model=TemplateOut)
async def publish_template(
    template_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await template_service.set_status(
        db, organization_id=org.id, entity_id=template_id, status="published",
        actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Template not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="template")
