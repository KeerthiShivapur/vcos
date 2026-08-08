"""Personal workspace: daily goal, notes, bookmarks, shortcuts, pins, reminders."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, get_current_user, require_permission
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message, Paginated
from app.schemas.workspace import (
    WorkspaceDashboard,
    WorkspaceItemCreate,
    WorkspaceItemOut,
    WorkspaceItemUpdate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.db.database import get_db
from app.services.audit_service import audit_service
from app.services.event_service import event_service
from app.services.workspace_service import workspace_service

router = APIRouter(prefix="/workspace", tags=["Workspace"])


@router.get("", response_model=WorkspaceOut)
async def get_workspace(
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    ws = await workspace_service.get_or_create(db, user_id=user.id, organization_id=org.id)
    await db.commit()
    return WorkspaceOut.model_validate(ws)


@router.patch("", response_model=WorkspaceOut)
async def update_workspace(
    payload: WorkspaceUpdate,
    request: Request,
    user: User = Depends(require_permission("workspace:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    ws = await workspace_service.get_or_create(db, user_id=user.id, organization_id=org.id)
    ws = await workspace_service.update(db, ws, payload.model_dump(exclude_unset=True))
    await audit_service.log(
        db,
        organization_id=org.id,
        action="workspace.updated",
        actor_id=user.id,
        actor_email=user.email,
        resource_type="workspace",
        resource_id=ws.id,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return WorkspaceOut.model_validate(ws)


@router.get("/dashboard", response_model=WorkspaceDashboard)
async def workspace_dashboard(
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    ws = await workspace_service.get_or_create(db, user_id=user.id, organization_id=org.id)
    items, total = await workspace_service.list_items(
        db, user_id=user.id, organization_id=org.id, page=1, page_size=100
    )
    await db.commit()
    return WorkspaceDashboard(
        workspace=WorkspaceOut.model_validate(ws),
        items=[WorkspaceItemOut.model_validate(i) for i in items],
        recent_items=[WorkspaceItemOut.model_validate(i) for i in items[:8]],
        pinned_items=[
            WorkspaceItemOut.model_validate(i) for i in items if i.pinned
        ],
        notes_count=sum(1 for i in items if i.kind == "note"),
        bookmarks_count=sum(1 for i in items if i.kind == "bookmark"),
    )


@router.post("/items", response_model=WorkspaceItemOut, status_code=201)
async def create_item(
    payload: WorkspaceItemCreate,
    request: Request,
    user: User = Depends(require_permission("workspace:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    ws = await workspace_service.get_or_create(db, user_id=user.id, organization_id=org.id)
    item = await workspace_service.add_item(db, workspace=ws, data=payload.model_dump())
    await audit_service.log(
        db,
        organization_id=org.id,
        action="workspace.item.created",
        actor_id=user.id,
        actor_email=user.email,
        resource_type="workspace_item",
        resource_id=item.id,
        ip_address=get_client_ip(request),
        details={"kind": item.kind},
    )
    await db.commit()
    return WorkspaceItemOut.model_validate(item)


@router.get("/items", response_model=Paginated[WorkspaceItemOut])
async def list_items(
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    kind: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    items, total = await workspace_service.list_items(
        db, user_id=user.id, organization_id=org.id, kind=kind, page=page, page_size=page_size
    )
    return Paginated(
        items=[WorkspaceItemOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size) if page_size else 0,
    )


@router.patch("/items/{item_id}", response_model=WorkspaceItemOut)
async def update_item(
    item_id: str,
    payload: WorkspaceItemUpdate,
    request: Request,
    user: User = Depends(require_permission("workspace:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    from app.models.workspace import WorkspaceItem

    item = await db.get(WorkspaceItem, item_id)
    if item is None or item.user_id != user.id or item.organization_id != org.id:
        raise HTTPException(404, "Item not found")
    item = await workspace_service.update_item(db, item, payload.model_dump(exclude_unset=True))
    await audit_service.log(
        db,
        organization_id=org.id,
        action="workspace.item.updated",
        actor_id=user.id,
        actor_email=user.email,
        resource_type="workspace_item",
        resource_id=item.id,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return WorkspaceItemOut.model_validate(item)


@router.delete("/items/{item_id}", response_model=Message)
async def delete_item(
    item_id: str,
    request: Request,
    user: User = Depends(require_permission("workspace:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    from app.models.workspace import WorkspaceItem

    item = await db.get(WorkspaceItem, item_id)
    if item is None or item.user_id != user.id or item.organization_id != org.id:
        raise HTTPException(404, "Item not found")
    await db.delete(item)
    await audit_service.log(
        db,
        organization_id=org.id,
        action="workspace.item.deleted",
        actor_id=user.id,
        actor_email=user.email,
        resource_type="workspace_item",
        resource_id=item_id,
        ip_address=get_client_ip(request),
    )
    await event_service.emit(
        db,
        name="workspace.item.deleted",
        actor_id=user.id,
        organization_id=org.id,
        payload={"item_id": item_id},
    )
    await db.commit()
    return Message(message="Item deleted")


@router.get("/ai/status", response_model=dict)
async def ai_status(
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
):
    from app.ai.gateway import ai_gateway

    status = await ai_gateway.status()
    return status
