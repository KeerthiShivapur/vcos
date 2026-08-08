"""Wiki API — hierarchical company wiki (Phase 4.2)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.knowledge import knowledge_base as kb
from app.knowledge.presenters import present
from app.knowledge.wiki_service import wiki_service
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.knowledge import WikiPageCreate, WikiPageOut, WikiPageUpdate

router = APIRouter(prefix="/wiki", tags=["Wiki"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


async def _out(db: AsyncSession, org: Organization, entity):
    return await present(db, organization_id=org.id, entity=entity, kind="wiki")


@router.get("", response_model=list[WikiPageOut])
async def list_wiki(
    space: Optional[str] = None,
    parent_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await wiki_service.list_all(
        db, organization_id=org.id, status=status, search=search,
        limit=min(limit, 500), offset=offset,
    )
    if space:
        rows = [r for r in rows if r.space == space]
    if parent_id:
        rows = [r for r in rows if r.parent_id == parent_id]
    return [await _out(db, org, row) for row in rows]


@router.post("", response_model=WikiPageOut, status_code=201)
async def create_wiki_page(
    payload: WikiPageCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await wiki_service.create(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _out(db, org, entity)


@router.get("/tree", response_model=list[dict])
async def wiki_tree(
    space: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    return await wiki_service.tree(db, organization_id=org.id, space=space)


@router.get("/{page_id}", response_model=WikiPageOut)
async def get_wiki_page(
    page_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    entity = await wiki_service.get(db, organization_id=org.id, entity_id=page_id)
    if entity is None:
        raise HTTPException(404, "Wiki page not found")
    await kb.register_view(db, organization_id=org.id, entity_type="wiki", entity_id=page_id, user_id=user.id)
    await db.commit()
    return await _out(db, org, entity)


@router.get("/{page_id}/children", response_model=list[WikiPageOut])
async def wiki_children(
    page_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await wiki_service.children(db, organization_id=org.id, parent_id=page_id)
    return [await _out(db, org, row) for row in rows]


@router.patch("/{page_id}", response_model=WikiPageOut)
async def update_wiki_page(
    page_id: str,
    payload: WikiPageUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await wiki_service.update(
        db, organization_id=org.id, entity_id=page_id,
        payload=payload.model_dump(exclude_unset=True), actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Wiki page not found")
    await db.commit()
    return await _out(db, org, entity)


@router.delete("/{page_id}", response_model=Message)
async def delete_wiki_page(
    page_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if not await wiki_service.delete(
        db, organization_id=org.id, entity_id=page_id, actor=actor, ip_address=get_client_ip(request)
    ):
        raise HTTPException(404, "Wiki page not found")
    await db.commit()
    return Message(message="Wiki page deleted")


@router.post("/{page_id}/move", response_model=WikiPageOut)
async def move_wiki_page(
    page_id: str,
    payload: dict,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    try:
        entity = await wiki_service.move(
            db, organization_id=org.id, entity_id=page_id,
            parent_id=payload.get("parent_id"), actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if entity is None:
        raise HTTPException(404, "Wiki page not found")
    await db.commit()
    return await _out(db, org, entity)


@router.post("/{page_id}/publish", response_model=WikiPageOut)
async def publish_wiki_page(
    page_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await wiki_service.publish(
        db, organization_id=org.id, entity_id=page_id, actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Wiki page not found")
    await db.commit()
    return await _out(db, org, entity)
