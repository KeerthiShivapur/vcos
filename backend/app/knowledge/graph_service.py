"""Knowledge graph service — the visible map of the company's brain (Phase 4.9).

Builds nodes for every knowledge entity plus the external objects they link to
(projects, tasks, goals, meetings, people, departments, teams) and edges from
KnowledgeRelation, so the graph page can render the whole organizational memory.
"""

from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge import knowledge_base as kb
from app.models.knowledge import KnowledgeRelation

RELATION_TYPES = ("related_to", "references", "depends_on", "decided_at", "member_of", "belongs_to", "implemented_in", "supersedes")


class KnowledgeGraphService:
    async def build(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        kind: Optional[str] = None,
        focus: Optional[str] = None,
        depth: int = 3,
        limit: int = 250,
    ) -> dict[str, Any]:
        if focus:
            return await self._build_focused(db, organization_id=organization_id, focus=focus, depth=depth, limit=limit)
        return await self._build_all(db, organization_id=organization_id, kind=kind, limit=limit)

    async def _build_all(
        self, db: AsyncSession, *, organization_id: str, kind: Optional[str], limit: int,
    ) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        for k, model in kb.KIND_MODELS.items():
            if kind and k != kind:
                continue
            rows = (
                await db.execute(
                    select(model).where(
                        getattr(model, "organization_id") == organization_id,
                        getattr(model, "status").in_(kb.published_statuses(k)),
                    )
                )
            ).scalars().all()
            for row in rows:
                nodes[row.id] = {
                    "id": row.id,
                    "type": k,
                    "label": row.title,
                    "summary": getattr(row, "summary", "") or "",
                    "status": getattr(row, "status", "") or "",
                    "project_id": getattr(row, "project_id", None),
                    "url": kb.entity_url(k, row.id),
                }
        relations = (
            await db.execute(
                select(KnowledgeRelation).where(KnowledgeRelation.organization_id == organization_id)
            )
        ).scalars().all()
        for rel in relations:
            if rel.source_type in kb.KIND_MODELS and rel.target_type in kb.KIND_MODELS:
                self._add_edge(edges, rel.source_type, rel.source_id, rel.target_type, rel.target_id, rel.relation_type, None)
        return {"nodes": list(nodes.values())[:limit], "edges": list(edges.values())}

    async def _build_focused(
        self, db: AsyncSession, *, organization_id: str, focus: str, depth: int, limit: int,
    ) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        focus_parts = focus.split(":", 1)
        focus_type = focus_parts[0] if len(focus_parts) == 2 else None
        focus_id = focus_parts[-1]

        current: set[str] = {focus_id}
        known: set[str] = set()
        for _ in range(depth):
            found = set()
            for row in self._ids(await self._relations(db, organization_id=organization_id, ids=list(current))):
                self._add_edge(edges, row.source_type, row.source_id, row.target_type, row.target_id, row.relation_type, None)
                for side in ((row.source_type, row.source_id), (row.target_type, row.target_id)):
                    if side[1] not in known:
                        found.add(side[1])
            known |= current
            current = found - known
            if not current:
                break

        for k, model in kb.KIND_MODELS.items():
            rows = (
                await db.execute(
                    select(model).where(
                        getattr(model, "organization_id") == organization_id,
                        getattr(model, "id").in_(list(known) + ([focus_id] if focus_type is None else [])),
                    )
                )
            ).scalars().all()
            for row in rows:
                nodes[row.id] = {
                    "id": row.id,
                    "type": k,
                    "label": row.title,
                    "summary": getattr(row, "summary", "") or "",
                    "status": getattr(row, "status", "") or "",
                    "project_id": getattr(row, "project_id", None),
                    "url": kb.entity_url(k, row.id),
                }
        return {"nodes": list(nodes.values())[:limit], "edges": list(edges.values())}

    async def _relations(self, db: AsyncSession, *, organization_id: str, ids: list[str]) -> list[KnowledgeRelation]:
        if not ids:
            return []
        rows = (
            await db.execute(
                select(KnowledgeRelation).where(
                    KnowledgeRelation.organization_id == organization_id,
                    or_(
                        KnowledgeRelation.source_id.in_(ids),
                        KnowledgeRelation.target_id.in_(ids),
                    ),
                )
            )
        ).scalars().all()
        return list(rows)

    @staticmethod
    def _ids(relations: list[KnowledgeRelation]) -> list[KnowledgeRelation]:
        return relations

    @staticmethod
    def _add_edge(
        edges: dict[tuple[str, str, str], dict[str, Any]],
        source_type: str, source_id: str, target_type: str, target_id: str, relation_type: str, label: Optional[str],
    ) -> None:
        key = (source_id, target_id, relation_type)
        if key in edges:
            return
        edges[key] = {
            "source": source_id,
            "target": target_id,
            "type": relation_type,
            "label": label or relation_type,
            "source_type": source_type,
            "target_type": target_type,
        }


knowledge_graph_service = KnowledgeGraphService()
