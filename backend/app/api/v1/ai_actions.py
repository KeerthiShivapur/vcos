"""AI action endpoints (Phase 7.10) — audited, permission-gated execution."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.actions import action_engine
from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.ai import AIAction
from app.models.organization import Organization
from app.models.user import User
from app.services.permission_service import permission_service

router = APIRouter(prefix="/ai/actions", tags=["ai"])


class ActionIn(BaseModel):
    action_type: str
    payload: dict[str, Any] = {}


@router.post("")
async def execute_action(
    payload: ActionIn,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    required = action_engine.requires_permission(payload.action_type)
    codes = await permission_service.user_permission_codes(db, user.id, org.id)
    permitted = required in codes
    result = await action_engine.execute(
        db,
        organization_id=org.id,
        user=user,
        action_type=payload.action_type,
        payload=payload.payload,
        permitted=permitted,
    )
    await db.commit()
    return result


@router.get("")
async def action_history(
    limit: int = 20,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(AIAction)
            .where(AIAction.organization_id == org.id)
            .order_by(AIAction.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "total": len(rows),
        "actions": [
            {
                "id": a.id,
                "action_type": a.action_type,
                "status": a.status,
                "permission_check": a.permission_check,
                "created_at": a.created_at,
            }
            for a in rows
        ],
    }
