"""Universal search foundation."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.models.organization import Organization
from app.models.user import User
from app.schemas.search import SearchResponse
from app.db.database import get_db
from app.services.search_service import search_service

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("", response_model=SearchResponse)
async def global_search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(require_permission("search:global")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return SearchResponse(
        **await search_service.search(
            db, organization_id=org.id, query=q, user_id=user.id, limit=limit
        )
    )
