"""Phase 20 — Universal organization graph engine.

Every major entity participates in one graph: people, projects, tasks,
meetings, knowledge, learning, community, customers, finance, assets,
automation and innovation. The engine rebuilds the full graph and keeps
it searchable as one connected network.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence_network.organization_graph import organization_graph
from app.kernel.event_engine import event_engine
from app.models.course import Course
from app.models.customer import Customer
from app.models.finance import Budget
from app.models.innovation import Innovation
from app.models.knowledge import Document, Policy, WikiPage
from app.models.meeting import Meeting
from app.models.organization_node import OrganizationNode
from app.models.workflow import Workflow

_EXTRA_TYPES = (
    "document", "wiki", "policy", "meeting", "course", "budget", "workflow", "innovation",
)


class GraphEngine:
    """Unified organization graph across every module."""

    async def rebuild(
        self, db: AsyncSession, organization_id: str, *, commit: bool = False
    ) -> dict[str, Any]:
        """Rebuild the universal graph: core entities plus every other domain."""
        core = await organization_graph.rebuild(db, organization_id)
        await self._index_extras(db, organization_id)
        stats = await organization_graph.stats(db, organization_id)
        await event_engine.publish(
            db, organization_id, "graph.updated",
            payload={"nodes": stats["total_nodes"], "edges": stats["total_edges"]},
        )
        if commit:
            await db.commit()
        return {
            "nodes": stats["total_nodes"],
            "edges": stats["total_edges"],
            "nodes_by_type": stats["nodes_by_type"],
            "domains": list(_EXTRA_TYPES) + list(stats["nodes_by_type"].keys()),
        }

    async def _index_extras(self, db: AsyncSession, organization_id: str) -> int:
        """Add knowledge/meetings/learning/finance/automation/innovation nodes."""
        await db.execute(
            OrganizationNode.__table__.delete().where(
                OrganizationNode.organization_id == organization_id,
                OrganizationNode.node_type.in_(_EXTRA_TYPES),
            )
        )
        now = utcnow()
        groups: list[tuple[Any, str]] = [
            (Document, "document"),
            (WikiPage, "wiki"),
            (Policy, "policy"),
            (Meeting, "meeting"),
            (Course, "course"),
            (Budget, "budget"),
            (Workflow, "workflow"),
            (Innovation, "innovation"),
        ]
        total = 0
        for model, node_type in groups:
            rows = (
                await db.execute(
                    select(model).where(model.organization_id == organization_id).limit(2000)
                )
            ).scalars().all()
            for row in rows:
                db.add(
                    OrganizationNode(
                        organization_id=organization_id,
                        node_type=node_type,
                        external_id=row.id,
                        name=str(getattr(row, "name", None) or getattr(row, "title", None) or row.id)[:255],
                        properties={"status": getattr(row, "status", None)},
                        importance=1.0,
                        last_seen_at=now,
                    )
                )
                total += 1
        await db.flush()
        return total

    async def stats(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        return await organization_graph.stats(db, organization_id)

    async def nodes(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        node_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        stmt = select(OrganizationNode).where(OrganizationNode.organization_id == organization_id)
        if node_type:
            stmt = stmt.where(OrganizationNode.node_type == node_type)
        if search:
            stmt = stmt.where(OrganizationNode.name.ilike(f"%{search}%"))
        rows = (
            await db.execute(stmt.order_by(OrganizationNode.importance.desc()).limit(limit))
        ).scalars().all()
        return {
            "total": len(rows),
            "nodes": [
                {
                    "id": r.id,
                    "node_type": r.node_type,
                    "external_id": r.external_id,
                    "name": r.name,
                    "properties": r.properties or {},
                    "importance": r.importance,
                }
                for r in rows
            ],
        }

    async def search(self, db: AsyncSession, organization_id: str, q: str) -> dict[str, Any]:
        stmt = (
            select(OrganizationNode)
            .where(
                OrganizationNode.organization_id == organization_id,
                OrganizationNode.name.ilike(f"%{q}%"),
            )
            .order_by(OrganizationNode.importance.desc())
            .limit(50)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return {
            "query": q,
            "total": len(rows),
            "results": [
                {
                    "id": r.id,
                    "node_type": r.node_type,
                    "external_id": r.external_id,
                    "name": r.name,
                }
                for r in rows
            ],
        }

    async def neighbors(
        self, db: AsyncSession, organization_id: str, node_type: str, node_id: str
    ) -> dict[str, Any]:
        return await organization_graph.neighbors(db, organization_id, node_type, node_id)

    async def path(
        self,
        db: AsyncSession,
        organization_id: str,
        start_type: str,
        start_id: str,
        end_type: str,
        end_id: str,
    ) -> dict[str, Any]:
        return await organization_graph.path(
            db, organization_id, start_type, start_id, end_type, end_id
        )


graph_engine = GraphEngine()
