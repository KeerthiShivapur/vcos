"""Phase 18 — Webhook management API: endpoints, deliveries and retries."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.developers.webhook_service import webhook_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookCreateIn(BaseModel):
    name: str
    url: str
    events: Optional[list[str]] = None
    secret: Optional[str] = None


class WebhookStatusIn(BaseModel):
    status: str


@router.get("")
async def list_endpoints(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("webhooks:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await webhook_service.list(db, org.id)
    return {"total": len(rows), "endpoints": rows}


@router.post("")
async def create_endpoint(
    body: WebhookCreateIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("webhooks:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await webhook_service.create(
        db,
        organization_id=org.id,
        name=body.name,
        url=body.url,
        events=body.events,
        secret=body.secret,
    )
    await db.commit()
    return row


@router.patch("/{endpoint_id}/status")
async def set_endpoint_status(
    endpoint_id: str,
    body: WebhookStatusIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("webhooks:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await webhook_service.set_status(db, org.id, endpoint_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="endpoint not found")
    await db.commit()
    return row


@router.delete("/{endpoint_id}")
async def delete_endpoint(
    endpoint_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("webhooks:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    deleted = await webhook_service.delete(db, org.id, endpoint_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="endpoint not found")
    await db.commit()
    return {"status": "deleted", "endpoint_id": endpoint_id}


@router.get("/deliveries")
async def list_deliveries(
    endpoint_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("webhooks:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await webhook_service.deliveries(db, org.id, endpoint_id=endpoint_id, limit=limit)
    return {"total": len(rows), "deliveries": rows}


@router.post("/deliveries/{delivery_id}/redeliver")
async def redeliver(
    delivery_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("webhooks:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await webhook_service.redeliver(db, org.id, delivery_id)
    if row is None:
        raise HTTPException(status_code=404, detail="delivery not found")
    await db.commit()
    return row


@router.post("/{endpoint_id}/test")
async def test_endpoint(
    endpoint_id: str,
    payload: Optional[dict[str, Any]] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("webhooks:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    endpoint = await webhook_service.get_raw(db, org.id, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="endpoint not found")
    signature = webhook_service.sign_payload(
        {"event": "webhook.test", "data": payload or {}}, endpoint.secret
    )
    return {"event": "webhook.test", "signature": signature, "delivered": False}
