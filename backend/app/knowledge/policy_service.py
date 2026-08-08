"""Policy service — company policies with owner, approver and review dates (Phase 4.4)."""

from datetime import date
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.knowledge.crud_base import KnowledgeCrud
from app.models.employee import Employee
from app.models.knowledge import Policy


class PolicyService(KnowledgeCrud):
    model = Policy
    kind = "policy"

    async def submit_for_approval(
        self, db: AsyncSession, *, organization_id: str, entity_id: str, actor: Optional[Employee], ip_address: Optional[str], approver_id: Optional[str] = None,
    ) -> Any:
        entity = await self.get(db, organization_id=organization_id, entity_id=entity_id)
        if entity is None:
            return None
        await self.set_status(
            db, organization_id=organization_id, entity_id=entity_id, status="in_review", actor=actor, ip_address=ip_address,
            note="Submitted for approval",
        )
        from app.knowledge.workflow_service import workflow_service

        await workflow_service.create_approval(
            db, organization_id=organization_id, entity=entity, actor=actor, approver_id=approver_id
        )
        return entity

    async def approve(
        self, db: AsyncSession, *, organization_id: str, entity_id: str, actor: Optional[Employee], ip_address: Optional[str], note: Optional[str] = None,
    ) -> Any:
        entity = await self.get(db, organization_id=organization_id, entity_id=entity_id)
        if entity is None:
            return None
        if entity.status not in ("in_review", "draft", "approved"):
            return entity
        entity.status = "approved"
        entity.approval_note = note or entity.approval_note
        entity.published_at = entity.published_at or utcnow()
        entity.updated_at = utcnow()
        from app.knowledge.knowledge_base import emit_and_audit

        await emit_and_audit(
            db, organization_id=organization_id, name="policy.approved", actor=actor,
            actor_user_id=actor.user_id if actor else None, ip_address=ip_address,
            payload={"entity_id": entity.id, "title": entity.title},
            resource_type="policy", resource_id=entity.id,
        )
        await db.flush()
        return entity

    async def reject(
        self, db: AsyncSession, *, organization_id: str, entity_id: str, actor: Optional[Employee], ip_address: Optional[str], note: Optional[str] = None,
    ) -> Any:
        entity = await self.get(db, organization_id=organization_id, entity_id=entity_id)
        if entity is None:
            return None
        entity.status = "draft"
        entity.approval_note = note or entity.approval_note
        entity.updated_at = utcnow()
        from app.knowledge.knowledge_base import emit_and_audit

        await emit_and_audit(
            db, organization_id=organization_id, name="policy.rejected", actor=actor,
            actor_user_id=actor.user_id if actor else None, ip_address=ip_address,
            payload={"entity_id": entity.id, "title": entity.title, "note": note},
            resource_type="policy", resource_id=entity.id,
        )
        await db.flush()
        return entity

    async def overdue_reviews(self, db: AsyncSession, *, organization_id: str, limit: int = 50) -> list[Policy]:
        rows = (
            await db.execute(
                select(Policy).where(
                    Policy.organization_id == organization_id,
                    Policy.status.in_(("approved", "published")),
                    Policy.review_date.isnot(None),
                    Policy.review_date < date.today(),
                )
                .order_by(Policy.review_date.asc())
                .limit(limit)
            )
        ).scalars().all()
        return list(rows)


policy_service = PolicyService()
