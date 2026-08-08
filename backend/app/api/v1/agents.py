"""Phase 18 — AI Agent Ecosystem API: create/list/install/enable/execute agents."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.developers.agent_service import agent_service
from app.developers.portal_service import developer_portal_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreateIn(BaseModel):
    name: str
    description: Optional[str] = None
    role: str = "assistant"
    capabilities: Optional[list[str]] = None
    permissions: Optional[list[str]] = None
    knowledge_scopes: Optional[list[str]] = None
    config: Optional[dict[str, Any]] = None


class AgentStatusIn(BaseModel):
    status: str


class AgentExecuteIn(BaseModel):
    input_text: str
    context: Optional[dict[str, Any]] = None


async def _developer_id(db: AsyncSession, user: User) -> Optional[str]:
    developer = await developer_portal_service.find_by_user(db, user.id)
    return developer.id if developer else None


@router.post("")
async def create_agent(
    body: AgentCreateIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("agents:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    developer_id = await _developer_id(db, user)
    try:
        row = await agent_service.create(
            db,
            organization_id=org.id,
            developer_id=developer_id,
            name=body.name,
            description=body.description,
            role=body.role,
            capabilities=body.capabilities,
            permissions=body.permissions,
            knowledge_scopes=body.knowledge_scopes,
            config=body.config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


@router.get("")
async def list_agents(
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("agents:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await agent_service.list(db, organization_id=org.id, status=status, limit=limit)
    return {"total": len(rows), "agents": rows}


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("agents:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await agent_service.get(db, agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="agent not found")
    if row["organization_id"] not in (org.id, None):
        raise HTTPException(status_code=403, detail="agent not accessible")
    return row


@router.patch("/{agent_id}/status")
async def set_agent_status(
    agent_id: str,
    body: AgentStatusIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("agents:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await agent_service.set_status(
            db, agent_id, body.status, organization_id=org.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="agent not found")
    await db.commit()
    return row


@router.post("/{agent_id}/execute")
async def execute_agent(
    agent_id: str,
    body: AgentExecuteIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("agents:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await agent_service.execute(
            db, agent_id, input_text=body.input_text, context=body.context
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
