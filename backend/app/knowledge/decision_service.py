"""Decision service — the Decision Registry (Phase 4.3).

Every important decision is recorded with context, alternatives, participants,
the chosen option and the reasoning, so the AI can later answer "why was this
decision made?" from the organization's own memory.
"""

from datetime import date
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.knowledge import knowledge_base as kb
from app.knowledge.crud_base import KnowledgeCrud
from app.models.employee import Employee
from app.models.knowledge import Decision, DecisionOption, DecisionParticipant

DECISION_STATUSES = ("proposed", "made", "implemented", "reviewed")


class DecisionService(KnowledgeCrud):
    model = Decision
    kind = "decision"

    async def create(self, db: AsyncSession, *, organization_id: str, payload: dict[str, Any], actor: Optional[Employee], ip_address: Optional[str]) -> Any:
        options = payload.pop("options", None) or []
        participants = payload.pop("participants", None) or []
        data = dict(payload)
        data.setdefault("status", "proposed")
        entity = await super().create(db, organization_id=organization_id, payload=data, actor=actor, ip_address=ip_address)
        for i, opt in enumerate(options):
            db.add(
                DecisionOption(
                    organization_id=organization_id,
                    decision_id=entity.id,
                    title=opt.get("title", f"Option {i + 1}"),
                    description=opt.get("description"),
                    pros=opt.get("pros"),
                    cons=opt.get("cons"),
                    sort_order=opt.get("sort_order", i),
                )
            )
        for p in participants:
            db.add(
                DecisionParticipant(
                    organization_id=organization_id,
                    decision_id=entity.id,
                    employee_id=p["employee_id"],
                    role=p.get("role", "consulted"),
                )
            )
        await db.flush()
        return entity

    async def update(self, db: AsyncSession, *, organization_id: str, entity_id: str, payload: dict[str, Any], actor: Optional[Employee], ip_address: Optional[str]) -> Optional[Any]:
        options = payload.pop("options", None)
        participants = payload.pop("participants", None)
        entity = await super().update(db, organization_id=organization_id, entity_id=entity_id, payload=payload, actor=actor, ip_address=ip_address)
        if entity is None:
            return None
        if options is not None:
            existing = (
                await db.execute(
                    select(DecisionOption).where(
                        DecisionOption.organization_id == organization_id, DecisionOption.decision_id == entity.id
                    )
                )
            ).scalars().all()
            for row in existing:
                await db.delete(row)
            for i, opt in enumerate(options):
                db.add(
                    DecisionOption(
                        organization_id=organization_id,
                        decision_id=entity.id,
                        title=opt.get("title", f"Option {i + 1}"),
                        description=opt.get("description"),
                        pros=opt.get("pros"),
                        cons=opt.get("cons"),
                        sort_order=opt.get("sort_order", i),
                    )
                )
        if participants is not None:
            existing = (
                await db.execute(
                    select(DecisionParticipant).where(
                        DecisionParticipant.organization_id == organization_id, DecisionParticipant.decision_id == entity.id
                    )
                )
            ).scalars().all()
            for row in existing:
                await db.delete(row)
            for p in participants:
                db.add(
                    DecisionParticipant(
                        organization_id=organization_id,
                        decision_id=entity.id,
                        employee_id=p["employee_id"],
                        role=p.get("role", "consulted"),
                    )
                )
        await db.flush()
        return entity

    async def options(self, db: AsyncSession, *, organization_id: str, decision_id: str) -> list[DecisionOption]:
        rows = (
            await db.execute(
                select(DecisionOption)
                .where(DecisionOption.organization_id == organization_id, DecisionOption.decision_id == decision_id)
                .order_by(DecisionOption.sort_order.asc())
            )
        ).scalars().all()
        return list(rows)

    async def participants(self, db: AsyncSession, *, organization_id: str, decision_id: str) -> list[DecisionParticipant]:
        rows = (
            await db.execute(
                select(DecisionParticipant)
                .where(DecisionParticipant.organization_id == organization_id, DecisionParticipant.decision_id == decision_id)
            )
        ).scalars().all()
        return list(rows)

    async def choose(
        self, db: AsyncSession, *, organization_id: str, decision_id: str, option_id: str, reason: Optional[str] = None,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Optional[Any]:
        """Record the chosen option, make the decision, persist the reason."""
        decision = await self.get(db, organization_id=organization_id, entity_id=decision_id)
        if decision is None:
            return None
        option = (
            await db.execute(
                select(DecisionOption).where(
                    DecisionOption.organization_id == organization_id,
                    DecisionOption.decision_id == decision_id,
                    DecisionOption.id == option_id,
                )
            )
        ).scalar_one_or_none()
        if option is None:
            return None
        all_options = await self.options(db, organization_id=organization_id, decision_id=decision_id)
        for opt in all_options:
            opt.chosen = False
            opt.chosen_reason = None
        option.chosen = True
        option.chosen_reason = reason
        decision.status = "made"
        decision.decided_at = utcnow()
        decision.decision_date = decision.decision_date or date.today()
        decision.updated_at = utcnow()
        await kb.emit_and_audit(
            db, organization_id=organization_id, name="decision.made", actor=actor,
            actor_user_id=actor.user_id if actor else None, ip_address=ip_address,
            payload={"entity_id": decision.id, "title": decision.title, "option": option.title, "reason": reason},
            resource_type="decision", resource_id=decision.id,
        )
        await db.flush()
        return decision

    async def transition(
        self, db: AsyncSession, *, organization_id: str, decision_id: str, status: str, note: Optional[str] = None,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Optional[Any]:
        decision = await self.get(db, organization_id=organization_id, entity_id=decision_id)
        if decision is None or status not in DECISION_STATUSES:
            return None
        decision.status = status
        if status == "made" and not decision.decided_at:
            decision.decided_at = utcnow()
            decision.decision_date = decision.decision_date or date.today()
        if status in ("implemented", "reviewed") and not decision.lessons_learned:
            decision.lessons_learned = decision.lessons_learned
        decision.updated_at = utcnow()
        await kb.emit_and_audit(
            db, organization_id=organization_id, name=f"decision.{status}", actor=actor,
            actor_user_id=actor.user_id if actor else None, ip_address=ip_address,
            payload={"entity_id": decision.id, "title": decision.title, "note": note},
            resource_type="decision", resource_id=decision.id,
        )
        await db.flush()
        return decision


decision_service = DecisionService()
