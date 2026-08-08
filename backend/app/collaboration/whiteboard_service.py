"""Shared whiteboard service (Phase 6.4) — one JSON canvas per meeting, versioned."""

import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.collaboration import MeetingWhiteboard


class WhiteboardService:
    async def get_or_create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting_id: str,
        session_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> MeetingWhiteboard:
        board = (
            await db.execute(
                select(MeetingWhiteboard).where(
                    MeetingWhiteboard.organization_id == organization_id,
                    MeetingWhiteboard.meeting_id == meeting_id,
                )
            )
        ).scalar_one_or_none()
        if board is None:
            board = MeetingWhiteboard(
                organization_id=organization_id,
                meeting_id=meeting_id,
                session_id=session_id,
                content=json.dumps({"shapes": [], "background": None, "pages": {}}),
                version=1,
                created_by=created_by,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            db.add(board)
            await db.flush()
        return board

    async def update(
        self,
        db: AsyncSession,
        *,
        board: MeetingWhiteboard,
        content: dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> MeetingWhiteboard:
        """Save a canvas snapshot. `expected_version` guards lost updates (409)."""
        if expected_version is not None and expected_version != board.version:
            raise ValueError(
                f"Whiteboard changed on the server (local {expected_version}, server {board.version})"
            )
        board.content = json.dumps(content, default=str)
        board.version = (board.version or 1) + 1
        board.updated_at = utcnow()
        return board

    def payload(self, board: MeetingWhiteboard) -> dict[str, Any]:
        try:
            content = json.loads(board.content) if board.content else {"shapes": []}
        except (TypeError, ValueError):
            content = {"shapes": []}
        return {
            "id": board.id,
            "meeting_id": board.meeting_id,
            "session_id": board.session_id,
            "content": content,
            "version": board.version,
            "created_by": board.created_by,
            "created_at": board.created_at,
            "updated_at": board.updated_at,
        }


whiteboard_service = WhiteboardService()
