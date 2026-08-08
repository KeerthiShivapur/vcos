"""Universal Context service (Phase 19.3) — context flows across modules.

Given any organizational entity (project, meeting, knowledge document, task,
decision, customer, person), the context engine links it to every related
item across modules so the context bundle travels automatically: a meeting
recalls the projects it feeds, the knowledge it produced, the people who
attended and the decisions it led to.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.company_memory import OrganizationContext

# entity types the engine knows how to link
SUPPORTED_ENTITY_TYPES = (
    "project", "task", "meeting", "document", "wiki", "decision",
    "employee", "customer", "goal", "community", "innovation",
)

SERIALIZE_BY_TYPE: dict[str, list[str]] = {
    "project": ["id", "name", "status", "progress", "owner_id"],
    "task": ["id", "title", "status", "assignee_id", "project_id"],
    "meeting": ["id", "title", "summary", "starts_at", "participants"],
    "document": ["id", "title", "file_type", "category", "uploaded_by"],
    "wiki": ["id", "title", "category", "content"],
    "decision": ["id", "decision", "category", "status", "outcome"],
    "employee": ["id", "name", "title", "department_id"],
    "customer": ["id", "name", "industry", "health"],
    "goal": ["id", "title", "status", "progress"],
    "community": ["id", "name", "category", "members"],
    "innovation": ["id", "title", "category", "status"],
}


def _pick(source: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {k: v for k, v in source.items() if k in keys and v is not None}


class ContextService:
    """Builds, persists and returns universal context bundles."""

    async def _entity_row(self, db: AsyncSession, organization_id: str, entity_type: str, entity_id: str) -> Optional[dict[str, Any]]:
        """Resolve a single entity row into its serialized dict (defensive)."""
        try:
            from app.models.project import Project
            from app.models.task import Task
            from app.models.meeting import Meeting
            from app.models.knowledge import Document, WikiPage
            from app.models.employee import Employee
            from app.models.customer import Customer
            from app.models.goal import Goal
            from app.models.community import Community

            mapping = {
                "project": Project,
                "task": Task,
                "meeting": Meeting,
                "document": Document,
                "wiki": WikiPage,
                "employee": Employee,
                "customer": Customer,
                "goal": Goal,
                "community": Community,
            }
            model = mapping.get(entity_type)
            if model is None:
                return None
            row = (
                await db.execute(
                    select(model).where(
                        model.organization_id == organization_id,
                        model.id == entity_id,
                    )
                )
            ).scalars().first()
            if row is None:
                return None
            return self._serialize_entity(entity_type, row)
        except Exception:
            return None

    def _serialize_entity(self, entity_type: str, row: Any) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        for attr in SERIALIZE_BY_TYPE.get(entity_type, []):
            if hasattr(row, attr):
                value = getattr(row, attr)
                if value is not None:
                    attrs[attr] = value
        return attrs

    async def build(
        self, db: AsyncSession, organization_id: str, entity_type: str, entity_id: str
    ) -> dict[str, Any]:
        """Compute the related-items bundle for an entity (no persistence)."""
        related: dict[str, list[dict[str, Any]]] = {}
        try:
            from app.models.project import Project
            from app.models.task import Task
            from app.models.meeting import Meeting
            from app.models.knowledge import Document, WikiPage, Decision
            from app.models.company_memory import CompanyMemory
            from app.models.employee import Employee

            # ---- projects: meetings, tasks, knowledge, decisions, people
            if entity_type == "project":
                tasks = (
                    await db.execute(
                        select(Task).where(
                            Task.organization_id == organization_id,
                            Task.project_id == entity_id,
                        ).limit(25)
                    )
                ).scalars().all()
                related["tasks"] = [self._serialize_entity("task", t) for t in tasks]
                meetings = (
                    await db.execute(
                        select(Meeting).where(
                            Meeting.organization_id == organization_id,
                            Meeting.project_id == entity_id,
                        ).limit(25)
                    )
                ).scalars().all()
                related["meetings"] = [self._serialize_entity("meeting", m) for m in meetings]
                docs = (
                    await db.execute(
                        select(Document).where(
                            Document.organization_id == organization_id,
                            Document.project_id == entity_id,
                        ).limit(25)
                    )
                ).scalars().all()
                related["knowledge"] = [self._serialize_entity("document", d) for d in docs]
                memories = (
                    await db.execute(
                        select(CompanyMemory).where(
                            CompanyMemory.organization_id == organization_id,
                            CompanyMemory.entity_type == "project",
                            CompanyMemory.entity_id == entity_id,
                        ).limit(10)
                    )
                ).scalars().all()
                related["memories"] = [memory_service.serialize(m) for m in memories]

            # ---- tasks: project, meetings, people
            elif entity_type == "task":
                task = (
                    await db.execute(
                        select(Task).where(
                            Task.organization_id == organization_id,
                            Task.id == entity_id,
                        )
                    )
                ).scalars().first()
                if task is not None and getattr(task, "project_id", None):
                    project = (
                        await db.execute(
                            select(Project).where(
                                Project.organization_id == organization_id,
                                Project.id == task.project_id,
                            )
                        )
                    ).scalars().first()
                    if project is not None:
                        related["project"] = [self._serialize_entity("project", project)]
                        meetings = (
                            await db.execute(
                                select(Meeting).where(
                                    Meeting.organization_id == organization_id,
                                    Meeting.project_id == project.id,
                                ).limit(10)
                            )
                        ).scalars().all()
                        related["meetings"] = [self._serialize_entity("meeting", m) for m in meetings]

            # ---- meetings: project, attendees, knowledge
            elif entity_type == "meeting":
                meeting = (
                    await db.execute(
                        select(Meeting).where(
                            Meeting.organization_id == organization_id,
                            Meeting.id == entity_id,
                        )
                    )
                ).scalars().first()
                if meeting is not None:
                    if getattr(meeting, "project_id", None):
                        project = (
                            await db.execute(
                                select(Project).where(
                                    Project.organization_id == organization_id,
                                    Project.id == meeting.project_id,
                                )
                            )
                        ).scalars().first()
                        if project is not None:
                            related["project"] = [self._serialize_entity("project", project)]
                    docs = (
                        await db.execute(
                            select(Document).where(
                                Document.organization_id == organization_id,
                                Document.meeting_id == entity_id,
                            ).limit(15)
                        )
                    ).scalars().all()
                    related["knowledge"] = [self._serialize_entity("document", d) for d in docs]

            # ---- documents: project, wiki, meetings
            elif entity_type == "document":
                doc = (
                    await db.execute(
                        select(Document).where(
                            Document.organization_id == organization_id,
                            Document.id == entity_id,
                        )
                    )
                ).scalars().first()
                if doc is not None:
                    if getattr(doc, "project_id", None):
                        project = (
                            await db.execute(
                                select(Project).where(
                                    Project.organization_id == organization_id,
                                    Project.id == doc.project_id,
                                )
                            )
                        ).scalars().first()
                        if project is not None:
                            related["project"] = [self._serialize_entity("project", project)]
                    wiki = (
                        await db.execute(
                            select(WikiPage).where(
                                WikiPage.organization_id == organization_id,
                                WikiPage.document_id == entity_id,
                            ).limit(10)
                        )
                    ).scalars().all()
                    related["wiki"] = [self._serialize_entity("wiki", w) for w in wiki]

            # ---- decisions: memories, projects
            elif entity_type == "decision":
                memories = (
                    await db.execute(
                        select(CompanyMemory).where(
                            CompanyMemory.organization_id == organization_id,
                            CompanyMemory.entity_type == "decision",
                            CompanyMemory.entity_id == entity_id,
                        ).limit(10)
                    )
                ).scalars().all()
                related["memories"] = [memory_service.serialize(m) for m in memories]
                decisions = (
                    await db.execute(
                        select(Decision).where(
                            Decision.organization_id == organization_id,
                            Decision.id == entity_id,
                        )
                    )
                ).scalars().all()
                related["decision"] = [self._serialize_entity("decision", d) for d in decisions]

            # ---- employees: projects, meetings, documents
            elif entity_type == "employee":
                projects = (
                    await db.execute(
                        select(Project).where(
                            Project.organization_id == organization_id,
                            Project.owner_id == entity_id,
                        ).limit(15)
                    )
                ).scalars().all()
                related["projects"] = [self._serialize_entity("project", p) for p in projects]
                tasks = (
                    await db.execute(
                        select(Task).where(
                            Task.organization_id == organization_id,
                            Task.assignee_id == entity_id,
                        ).limit(15)
                    )
                ).scalars().all()
                related["tasks"] = [self._serialize_entity("task", t) for t in tasks]
                docs = (
                    await db.execute(
                        select(Document).where(
                            Document.organization_id == organization_id,
                            Document.uploaded_by == entity_id,
                        ).limit(10)
                    )
                ).scalars().all()
                related["knowledge"] = [self._serialize_entity("document", d) for d in docs]
        except Exception:
            pass
        return related

    async def get(
        self, db: AsyncSession, organization_id: str, entity_type: str, entity_id: str,
        *, rebuild: bool = False, commit: bool = False,
    ) -> Optional[dict[str, Any]]:
        """Return the stored context bundle, rebuilding it when missing or stale."""
        row = (
            await db.execute(
                select(OrganizationContext).where(
                    OrganizationContext.organization_id == organization_id,
                    OrganizationContext.entity_type == entity_type,
                    OrganizationContext.entity_id == entity_id,
                )
            )
        ).scalars().first()
        if row is None or rebuild:
            related = await self.build(db, organization_id, entity_type, entity_id)
            entity = await self._entity_row(db, organization_id, entity_type, entity_id)
            summary = self._summarize(entity_type, related, entity)
            if row is None:
                row = OrganizationContext(
                    organization_id=organization_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    related=related,
                    summary=summary,
                    freshness=1.0,
                    built_at=utcnow(),
                )
                db.add(row)
            else:
                row.related = related
                row.summary = summary
                row.freshness = 1.0
                row.built_at = utcnow()
            await db.flush()
            await publish_background_event(
                db, name="context.updated", organization_id=organization_id,
                payload={"entity_type": entity_type, "entity_id": entity_id},
            )
            if commit:
                await db.commit()
            return self.serialize(row)
        return self.serialize(row)

    def _summarize(
        self, entity_type: str, related: dict[str, list[dict[str, Any]]], entity: Optional[dict[str, Any]]
    ) -> str:
        parts = [f"{entity_type} context"]
        for key, items in related.items():
            if items:
                parts.append(f"{len(items)} related {key}")
        if entity and entity.get("name") or entity and entity.get("title"):
            parts.insert(0, f"{entity.get('name') or entity.get('title')}")
        return " · ".join(parts[:6]) if len(parts) > 1 else "No related context found"

    def serialize(self, row: OrganizationContext) -> dict[str, Any]:
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "related": row.related or {},
            "summary": row.summary,
            "freshness": row.freshness,
            "built_at": row.built_at.isoformat() if row.built_at else None,
        }

    async def attach(
        self,
        db: AsyncSession,
        organization_id: str,
        entity_type: str,
        entity_id: str,
        related: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Merge manually-provided related items into the stored bundle."""
        row = (
            await db.execute(
                select(OrganizationContext).where(
                    OrganizationContext.organization_id == organization_id,
                    OrganizationContext.entity_type == entity_type,
                    OrganizationContext.entity_id == entity_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        merged = dict(row.related or {})
        for key, items in (related or {}).items():
            if not isinstance(items, list):
                continue
            merged[key] = items
        row.related = merged
        row.freshness = 1.0
        row.built_at = utcnow()
        await db.flush()
        return self.serialize(row)

    async def flow(
        self, db: AsyncSession, organization_id: str, entity_type: str, entity_id: str
    ) -> dict[str, Any]:
        """The context bundle — the entry point for 'context that flows'."""
        bundle = await self.get(db, organization_id, entity_type, entity_id)
        if bundle is None:
            return {
                "organization_id": organization_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "related": {},
                "summary": "Entity not found or not linkable",
                "flow": [],
            }
        flow = []
        for key, items in (bundle.get("related") or {}).items():
            for item in items[:5]:
                flow.append({"type": key, "item": item})
        return {**bundle, "flow": flow}


context_service = ContextService()

# imported at runtime to avoid a circular import at module load
from app.memory.memory_service import memory_service  # noqa: E402
