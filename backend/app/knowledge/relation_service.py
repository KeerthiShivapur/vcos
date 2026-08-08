"""Knowledge relations — the knowledge graph edges.

Typed links between knowledge entities and anything else (projects, meetings,
employees, departments, other knowledge…). Edges are auto-created when an
entity carries a project/department/meeting reference, and can be added
manually through the API. The org graph and the knowledge graph viewer both
consume these edges.
"""

from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge import knowledge_base as kb
from app.schemas.knowledge import entity_url


class RelationService:
    async def list_for(
        self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str
    ) -> list[Any]:
        from app.models.knowledge import KnowledgeRelation

        rows = (
            await db.execute(
                select(KnowledgeRelation).where(
                    KnowledgeRelation.organization_id == organization_id,
                    or_(
                        (KnowledgeRelation.source_type == entity_type) & (KnowledgeRelation.source_id == entity_id),
                        (KnowledgeRelation.target_type == entity_type) & (KnowledgeRelation.target_id == entity_id),
                    ),
                )
            )
        ).scalars().all()
        return list(rows)

    async def add(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        relation_type: str = "related_to",
        created_by: Optional[str] = None,
    ) -> Any:
        from app.models.knowledge import KnowledgeRelation

        if source_type == target_type and source_id == target_id:
            raise ValueError("Cannot relate an entity to itself")
        if source_type in kb.KINDS and await kb.resolve_entity(
            db, organization_id=organization_id, kind=source_type, entity_id=source_id
        ) is None:
            raise ValueError("Source entity not found")
        if target_type in kb.KINDS and await kb.resolve_entity(
            db, organization_id=organization_id, kind=target_type, entity_id=target_id
        ) is None:
            raise ValueError("Target entity not found")
        existing = (
            await db.execute(
                select(KnowledgeRelation).where(
                    KnowledgeRelation.organization_id == organization_id,
                    KnowledgeRelation.source_type == source_type,
                    KnowledgeRelation.source_id == source_id,
                    KnowledgeRelation.target_type == target_type,
                    KnowledgeRelation.target_id == target_id,
                    KnowledgeRelation.relation_type == relation_type,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        relation = KnowledgeRelation(
            organization_id=organization_id,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            relation_type=relation_type,
            created_by=created_by,
        )
        db.add(relation)
        await db.flush()
        return relation

    async def remove(
        self, db: AsyncSession, *, organization_id: str, relation_id: str
    ) -> bool:
        from app.models.knowledge import KnowledgeRelation

        relation = (
            await db.execute(
                select(KnowledgeRelation).where(
                    KnowledgeRelation.organization_id == organization_id,
                    KnowledgeRelation.id == relation_id,
                )
            )
        ).scalar_one_or_none()
        if relation is None:
            return False
        await db.delete(relation)
        await db.flush()
        return True

    async def auto_link(
        self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str, entity: Any
    ) -> list[Any]:
        """Create graph edges from the entity's own references."""
        from app.knowledge.relation_service import relation_service

        created: list[Any] = []
        target_map = [
            ("project", getattr(entity, "project_id", None), "belongs_to"),
            ("department", getattr(entity, "department_id", None), "member_of"),
            ("team", getattr(entity, "team_id", None), "member_of"),
            ("meeting", getattr(entity, "meeting_id", None), "decided_at"),
        ]
        for target_type, target_id, relation_type in target_map:
            if not target_id:
                continue
            if target_type == "meeting":
                relation_type = "related_to"
            relation = await relation_service.add(
                db,
                organization_id=organization_id,
                source_type=entity_type,
                source_id=entity_id,
                target_type=target_type,
                target_id=target_id,
                relation_type=relation_type,
            )
            created.append(relation)
        return created

    async def resolve_target(
        self, db: AsyncSession, *, organization_id: str, target_type: str, target_id: str
    ) -> dict[str, Any]:
        """Resolve a relation target to a title + url for display."""
        if target_type in kb.KINDS:
            entity = await kb.resolve_entity(db, organization_id=organization_id, kind=target_type, entity_id=target_id)
            if entity is None:
                return {}
            return {"target_type": target_type, "target_id": target_id, "title": entity.title, "url": entity_url(target_type, target_id)}
        model = self._external_model(target_type)
        if model is None:
            return {"target_type": target_type, "target_id": target_id, "title": target_id, "url": ""}
        row = await db.get(model, target_id)
        if row is None or getattr(row, "organization_id", organization_id) != organization_id:
            return {"target_type": target_type, "target_id": target_id, "title": target_id, "url": ""}
        label = getattr(row, "title", None) or getattr(row, "name", None) or target_id
        return {"target_type": target_type, "target_id": target_id, "title": label, "url": self._external_url(target_type, target_id)}

    def _external_model(self, target_type: str):
        if target_type == "project":
            from app.models.project import Project

            return Project
        if target_type == "task":
            from app.models.task import Task

            return Task
        if target_type == "goal":
            from app.models.goal import Goal

            return Goal
        if target_type == "meeting":
            from app.models.meeting import Meeting

            return Meeting
        if target_type == "employee":
            from app.models.employee import Employee

            return Employee
        if target_type == "department":
            from app.models.department import Department

            return Department
        if target_type == "team":
            from app.models.team import Team

            return Team
        return None

    def _external_url(self, target_type: str, target_id: str) -> str:
        if target_type == "employee":
            return f"/people/{target_id}"
        if target_type == "project":
            return f"/projects/{target_id}"
        if target_type == "task":
            return f"/tasks/{target_id}"
        if target_type == "goal":
            return f"/goals/{target_id}"
        if target_type == "meeting":
            return f"/meetings/{target_id}"
        if target_type in ("department", "team"):
            return f"/{target_type}s/{target_id}" if target_type == "team" else f"/departments/{target_id}"
        return ""


relation_service = RelationService()
