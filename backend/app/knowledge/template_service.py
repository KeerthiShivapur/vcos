"""Template service — reusable knowledge templates with usage tracking (Phase 4.6)."""

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.knowledge.crud_base import KnowledgeCrud
from app.models.employee import Employee
from app.models.knowledge import Template


class TemplateService(KnowledgeCrud):
    model = Template
    kind = "template"

    async def record_usage(
        self, db: AsyncSession, *, organization_id: str, entity_id: str,
    ) -> Optional[Template]:
        template = await self.get(db, organization_id=organization_id, entity_id=entity_id)
        if template is None:
            return None
        template.usage_count = (template.usage_count or 0) + 1
        template.updated_at = utcnow()
        from app.knowledge.knowledge_base import emit_and_audit

        await emit_and_audit(
            db, organization_id=organization_id, name="template.used", actor=None,
            actor_user_id=None, ip_address=None,
            payload={"entity_id": template.id, "title": template.title},
            resource_type="template", resource_id=template.id,
        )
        await db.flush()
        return template

    async def most_used(self, db: AsyncSession, *, organization_id: str, limit: int = 10) -> list[Template]:
        rows = (
            await db.execute(
                select(Template)
                .where(Template.organization_id == organization_id)
                .order_by(Template.usage_count.desc())
                .limit(limit)
            )
        ).scalars().all()
        return list(rows)


template_service = TemplateService()
