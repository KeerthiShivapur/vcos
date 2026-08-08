"""Documents API — enterprise document management (Phase 4.1)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.knowledge.document_service import document_service
from app.knowledge.presenters import present
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.knowledge import DocumentCreate, DocumentOut, DocumentUpdate

router = APIRouter(prefix="/documents", tags=["Documents"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    owner_id: Optional[str] = None,
    project_id: Optional[str] = None,
    department_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await document_service.list_all(
        db, organization_id=org.id, status=status, category=category, search=search,
        owner_id=owner_id, project_id=project_id, department_id=department_id,
        limit=min(limit, 500), offset=offset,
    )
    return [await present(db, organization_id=org.id, entity=row, kind="document") for row in rows]


@router.post("", response_model=DocumentOut, status_code=201)
async def create_document(
    payload: DocumentCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await document_service.create(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="document")


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    entity = await document_service.get(db, organization_id=org.id, entity_id=document_id)
    if entity is None:
        raise HTTPException(404, "Document not found")
    from app.knowledge import knowledge_base as kb

    await kb.register_view(db, organization_id=org.id, entity_type="document", entity_id=document_id, user_id=user.id)
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="document")


@router.patch("/{document_id}", response_model=DocumentOut)
async def update_document(
    document_id: str,
    payload: DocumentUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await document_service.update(
        db, organization_id=org.id, entity_id=document_id,
        payload=payload.model_dump(exclude_unset=True), actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Document not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="document")


@router.delete("/{document_id}", response_model=Message)
async def delete_document(
    document_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if not await document_service.delete(
        db, organization_id=org.id, entity_id=document_id, actor=actor, ip_address=get_client_ip(request)
    ):
        raise HTTPException(404, "Document not found")
    await db.commit()
    return Message(message="Document deleted")


@router.post("/{document_id}/publish", response_model=DocumentOut)
async def publish_document(
    document_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await document_service.set_status(
        db, organization_id=org.id, entity_id=document_id, status="published",
        actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Document not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="document")


@router.post("/{document_id}/archive", response_model=DocumentOut)
async def archive_document(
    document_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await document_service.set_status(
        db, organization_id=org.id, entity_id=document_id, status="archived",
        actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Document not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="document")


@router.post("/{document_id}/submit", response_model=DocumentOut)
async def submit_document(
    document_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await document_service.submit_for_review(
        db, organization_id=org.id, entity_id=document_id, actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Document not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="document")


@router.post("/{document_id}/approve", response_model=DocumentOut)
async def approve_document(
    document_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:approve")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    entity = await document_service.approve(
        db, organization_id=org.id, entity_id=document_id, actor=actor, ip_address=get_client_ip(request),
    )
    if entity is None:
        raise HTTPException(404, "Document not found")
    await db.commit()
    return await present(db, organization_id=org.id, entity=entity, kind="document")
