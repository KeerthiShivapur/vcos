"""SOP service — standard operating procedures with checklist steps (Phase 4.5)."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.crud_base import KnowledgeCrud
from app.models.employee import Employee
from app.models.knowledge import SOP, SOPStep


class SOPService(KnowledgeCrud):
    model = SOP
    kind = "sop"

    async def _sync_steps(self, db: AsyncSession, *, organization_id: str, sop_id: str, steps: Optional[list[dict[str, Any]]]) -> None:
        if steps is None:
            return
        existing = (
            await db.execute(
                select(SOPStep).where(SOPStep.organization_id == organization_id, SOPStep.sop_id == sop_id)
            )
        ).scalars().all()
        for step in existing:
            await db.delete(step)
        for i, step in enumerate(steps):
            db.add(
                SOPStep(
                    organization_id=organization_id,
                    sop_id=sop_id,
                    title=step.get("title", f"Step {i + 1}"),
                    instruction=step.get("instruction"),
                    is_checklist=bool(step.get("is_checklist", False)),
                    sort_order=step.get("sort_order", i),
                )
            )
        await db.flush()

    async def create(self, db: AsyncSession, *, organization_id: str, payload: dict[str, Any], actor: Optional[Employee], ip_address: Optional[str]) -> Any:
        steps = payload.pop("steps", None)
        entity = await super().create(db, organization_id=organization_id, payload=payload, actor=actor, ip_address=ip_address)
        if steps is not None:
            await self._sync_steps(db, organization_id=organization_id, sop_id=entity.id, steps=steps)
        return entity

    async def update(self, db: AsyncSession, *, organization_id: str, entity_id: str, payload: dict[str, Any], actor: Optional[Employee], ip_address: Optional[str]) -> Optional[Any]:
        steps = payload.pop("steps", None)
        entity = await super().update(db, organization_id=organization_id, entity_id=entity_id, payload=payload, actor=actor, ip_address=ip_address)
        if entity is not None and steps is not None:
            await self._sync_steps(db, organization_id=organization_id, sop_id=entity.id, steps=steps)
        return entity

    async def steps(self, db: AsyncSession, *, organization_id: str, sop_id: str) -> list[SOPStep]:
        rows = (
            await db.execute(
                select(SOPStep)
                .where(SOPStep.organization_id == organization_id, SOPStep.sop_id == sop_id)
                .order_by(SOPStep.sort_order.asc())
            )
        ).scalars().all()
        return list(rows)


sop_service = SOPService()
