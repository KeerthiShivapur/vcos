"""Org-wide recording library (Phase 6.16 frontend support).

Lists recordings across all meetings with meeting titles for the
`/recordings` page. Registered before the meetings router so the static
`/recordings` path is never shadowed by `/{meeting_id}`.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.collaboration.recording_service import recording_service
from app.db.database import get_db
from app.models.collaboration import MeetingRecording
from app.models.meeting import Meeting
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/recordings", tags=["Recording Library"])


@router.get("", response_model=list[dict])
async def list_recording_library(
    status: Optional[str] = None,
    limit: int = 100,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await recording_service.list(db, organization_id=org.id, limit=limit)
    if status:
        rows = [r for r in rows if r.status == status]
    meeting_ids = {r.meeting_id for r in rows}
    meetings = {}
    if meeting_ids:
        meetings = {
            m.id: m
            for m in (
                await db.execute(
                    select(Meeting).where(Meeting.id.in_(meeting_ids))
                )
            ).scalars()
        }
    out = []
    for row in rows:
        payload = recording_service.payload(row)
        meeting = meetings.get(row.meeting_id)
        payload["meeting_title"] = meeting.title if meeting else None
        payload["meeting_status"] = meeting.status if meeting else None
        out.append(payload)
    return out
