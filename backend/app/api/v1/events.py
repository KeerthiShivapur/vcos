"""Event stream: the audit trail of the event bus."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.models.organization import Organization
from app.models.user import User
from app.models.notification import Event
from app.schemas.common import Paginated
from app.schemas.notifications import EventOut
from app.db.database import get_db

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("", response_model=Paginated[EventOut])
async def list_events(
    user: User = Depends(require_permission("events:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    name: str = Query(None),
):
    from sqlalchemy import func

    filters = [Event.organization_id == org.id]
    if name:
        filters.append(Event.name == name)
    total = (await db.execute(select(func.count()).select_from(Event).where(*filters))).scalar_one()
    result = await db.execute(
        select(Event).where(*filters).order_by(Event.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [EventOut.model_validate(e) for e in result.scalars().all()]
    return Paginated(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size) if page_size else 0,
    )
