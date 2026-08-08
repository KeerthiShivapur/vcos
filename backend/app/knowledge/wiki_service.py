"""Wiki service — the company's permanent knowledge base (Phase 4.2)."""

from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.knowledge.crud_base import KnowledgeCrud
from app.models.employee import Employee
from app.models.knowledge import WikiPage


class WikiService(KnowledgeCrud):
    model = WikiPage
    kind = "wiki"

    async def children(self, db: AsyncSession, *, organization_id: str, parent_id: str) -> list[WikiPage]:
        rows = (
            await db.execute(
                select(WikiPage).where(
                    WikiPage.organization_id == organization_id, WikiPage.parent_id == parent_id
                ).order_by(WikiPage.title.asc())
            )
        ).scalars().all()
        return list(rows)

    async def tree(self, db: AsyncSession, *, organization_id: str, space: Optional[str] = None, status: Optional[str] = None) -> list[dict[str, Any]]:
        """Nested page tree for the wiki sidebar."""
        filters = [WikiPage.organization_id == organization_id]
        if space:
            filters.append(WikiPage.space == space)
        if status:
            filters.append(WikiPage.status == status)
        rows = (
            await db.execute(select(WikiPage).where(*filters).order_by(WikiPage.title.asc()))
        ).scalars().all()
        pages = {p.id: p for p in rows}
        children: dict[str, list[WikiPage]] = {}
        for page in rows:
            parent = page.parent_id if page.parent_id in pages else None
            children.setdefault(parent, []).append(page)
        for bucket in children.values():
            bucket.sort(key=lambda p: p.title.lower())

        def build(page_id: Optional[str]) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for page in children.get(page_id, []):
                out.append(
                    {
                        "id": page.id,
                        "title": page.title,
                        "space": page.space,
                        "status": page.status,
                        "children": build(page.id),
                    }
                )
            return out

        return build(None)

    async def move(
        self, db: AsyncSession, *, organization_id: str, entity_id: str, parent_id: Optional[str], actor: Optional[Employee], ip_address: Optional[str],
    ) -> Optional[WikiPage]:
        page = await self.get(db, organization_id=organization_id, entity_id=entity_id)
        if page is None:
            return None
        if parent_id:
            parent = await self.get(db, organization_id=organization_id, entity_id=parent_id)
            if parent is None:
                return None
            # no cycles: parent may not be a descendant of page
            probe = parent
            while probe:
                if probe.id == page.id:
                    raise ValueError("Cannot move a page under one of its own children")
                probe = await self.get(db, organization_id=organization_id, entity_id=probe.parent_id) if probe.parent_id else None
        page.parent_id = parent_id
        page.updated_at = utcnow()
        from app.knowledge.knowledge_base import emit_and_audit

        await emit_and_audit(
            db, organization_id=organization_id, name="wiki.moved", actor=actor,
            actor_user_id=actor.user_id if actor else None, ip_address=ip_address,
            payload={"entity_id": page.id, "title": page.title, "parent_id": parent_id},
        )
        await db.flush()
        return page

    async def publish(self, db: AsyncSession, *, organization_id: str, entity_id: str, actor: Optional[Employee], ip_address: Optional[str]) -> Optional[WikiPage]:
        return await self.set_status(
            db, organization_id=organization_id, entity_id=entity_id, status="published", actor=actor, ip_address=ip_address, version_bump=False,
        )


wiki_service = WikiService()
