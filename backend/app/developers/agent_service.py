from __future__ import annotations

"""AI agent ecosystem service (Phase 18.4) â€” agents CRUD, install & execution.

Agents are declarative AI assistants: an organization can create private
agents, install agents from the ecosystem, enable/disable them, and run
simple deterministic invocations that resolve against their capabilities.
"""

import secrets
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.developer import AIAgent

AGENT_ROLES = ("finance", "sales", "legal", "research", "security", "executive", "operations", "assistant", "custom")
AGENT_STATUSES = ("draft", "published", "installed", "enabled", "disabled", "removed")


def _new_agent_key() -> str:
    return "agent_" + secrets.token_urlsafe(10)


class AgentService:
    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: Optional[str],
        developer_id: Optional[str],
        name: str,
        description: Optional[str] = None,
        role: str = "assistant",
        capabilities: Optional[list[str]] = None,
        permissions: Optional[list[str]] = None,
        knowledge_scopes: Optional[list[str]] = None,
        config: Optional[dict[str, Any]] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        if role not in AGENT_ROLES:
            raise ValueError(f"role must be one of {AGENT_ROLES}")
        agent_key = _new_agent_key()
        while (
            await db.execute(select(AIAgent).where(AIAgent.agent_key == agent_key))
        ).scalars().first() is not None:
            agent_key = _new_agent_key()
        row = AIAgent(
            organization_id=organization_id,
            developer_id=developer_id,
            agent_key=agent_key,
            name=name,
            description=description,
            role=role,
            capabilities=capabilities or [],
            permissions=permissions or [],
            knowledge_scopes=knowledge_scopes or [],
            config=config or {},
            status="draft",
        )
        db.add(row)
        await db.flush()
        if commit:
            await db.commit()
        return self.serialize(row)

    async def list(
        self,
        db: AsyncSession,
        organization_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = select(AIAgent)
        if organization_id is not None:
            stmt = stmt.where(
                (AIAgent.organization_id == organization_id) | (AIAgent.organization_id.is_(None))
            )
        if status:
            stmt = stmt.where(AIAgent.status == status)
        rows = (
            await db.execute(stmt.order_by(AIAgent.created_at.desc()).limit(limit))
        ).scalars().all()
        return [self.serialize(r) for r in rows]

    async def get(self, db: AsyncSession, agent_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(select(AIAgent).where(AIAgent.id == agent_id))
        ).scalars().first()
        return self.serialize(row) if row else None

    async def set_status(
        self,
        db: AsyncSession,
        agent_id: str,
        status: str,
        *,
        organization_id: Optional[str] = None,
        commit: bool = False,
    ) -> Optional[dict[str, Any]]:
        if status not in AGENT_STATUSES:
            raise ValueError(f"status must be one of {AGENT_STATUSES}")
        stmt = select(AIAgent).where(AIAgent.id == agent_id)
        if organization_id is not None:
            stmt = stmt.where(
                (AIAgent.organization_id == organization_id) | (AIAgent.organization_id.is_(None))
            )
        row = (await db.execute(stmt)).scalars().first()
        if row is None:
            return None
        row.status = status
        if status == "installed":
            row.installed_at = utcnow()
        await db.flush()
        await publish_background_event(
            db, name="agent.installed" if status == "installed" else "agent.updated",
            organization_id=row.organization_id or "system",
            payload={"agent_id": row.id, "status": status},
        )
        if commit:
            await db.commit()
        return self.serialize(row)

    async def execute(
        self,
        db: AsyncSession,
        agent_id: str,
        *,
        input_text: str,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        row = (
            await db.execute(select(AIAgent).where(AIAgent.id == agent_id))
        ).scalars().first()
        if row is None:
            raise ValueError("agent not found")
        if row.status in ("disabled", "removed"):
            raise ValueError(f"agent is {row.status}")
        capabilities = row.capabilities or []
        available = ", ".join(capabilities) if capabilities else "general assistance"
        response = (
            f"[{row.name}] Role: {row.role}. Capabilities: {available}. "
            f"Input: {input_text[:500]}"
        )
        await publish_background_event(
            db, name="agent.executed", organization_id=row.organization_id or "system",
            payload={"agent_id": row.id, "status": "completed"},
        )
        return {
            "agent_id": row.id,
            "agent_key": row.agent_key,
            "name": row.name,
            "role": row.role,
            "response": response,
            "context": context or {},
            "status": "completed",
            "executed_at": utcnow().isoformat(),
        }

    def serialize(self, row: AIAgent) -> dict[str, Any]:
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "developer_id": row.developer_id,
            "agent_key": row.agent_key,
            "name": row.name,
            "description": row.description,
            "role": row.role,
            "capabilities": row.capabilities or [],
            "permissions": row.permissions or [],
            "knowledge_scopes": row.knowledge_scopes or [],
            "status": row.status,
            "config": row.config or {},
            "version": row.version,
            "verified": row.verified,
            "installed_at": row.installed_at.isoformat() if row.installed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


agent_service = AgentService()
