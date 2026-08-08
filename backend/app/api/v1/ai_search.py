"""Universal AI search endpoints (Phase 7.4)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.search import universal_search
from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai/search", tags=["ai"])


class SearchIn(BaseModel):
    query: str
    scopes: Optional[list[str]] = None
    limit: int = 20


@router.post("")
async def search(
    payload: SearchIn,
    user: User = Depends(require_permission("search:global")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await universal_search.search(
        db,
        organization_id=org.id,
        query=payload.query,
        limit=payload.limit,
        scopes=payload.scopes,
    )
    return result
