"""Execution intelligence API — dependency-aware operational picture (Slice 3 Step 7)."""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.work.intelligence_service import intelligence_service

router = APIRouter(prefix="/execution", tags=["Execution"])


@router.get("/insights")
async def execution_insights(
    project_id: Optional[str] = None,
    limit: int = 50,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    """Overdue, at-risk, stalled, blocked (with chain depth) and ready-to-start tasks."""
    if project_id:
        from app.models.project import Project

        project = await db.get(Project, project_id)
        if project is None or project.organization_id != org.id:
            from fastapi import HTTPException

            raise HTTPException(404, "Project not found")
    return await intelligence_service.execution_insights(
        db, organization_id=org.id, project_id=project_id, limit=limit
    )
