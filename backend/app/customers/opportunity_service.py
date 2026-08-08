"""Opportunity service (Phase 12.3 — Opportunity Pipeline).

Pipeline: qualified -> proposal -> negotiation -> won | lost.
AI predicts win probability from stage, value, age and engagement; winning
an opportunity converts the lead into a customer record and optionally
creates the first implementation project.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.customers.parse import clamp_score, to_dt
from app.events.event_bus import EventBus
from app.models.employee import Employee
from app.models.lead import Lead, Opportunity, OpportunityActivity

logger = logging.getLogger("vcos.customers.opportunity")

_event_bus = EventBus()

STAGES = ["qualified", "proposal", "negotiation", "won", "lost"]
ACTIVITY_KINDS = ["created", "stage_changed", "proposed", "negotiated", "won", "lost", "noted"]
STAGE_PROBABILITY = {"qualified": 20, "proposal": 40, "negotiation": 70, "won": 100, "lost": 0}


def predict_probability(stage: str, value: Optional[float], age_days: int, activity_count: int) -> int:
    probability = STAGE_PROBABILITY.get(stage, 20)
    if value:
        if value >= 100000:
            probability -= 5
        elif value >= 25000:
            probability += 5
    if age_days > 60:
        probability -= 10
    elif age_days > 30:
        probability -= 5
    if activity_count >= 3:
        probability += 8
    return clamp_score(probability, probability)


class OpportunityService:
    async def create(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
                     actor_id: Optional[str] = None) -> Opportunity:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        stage = data.get("stage", "qualified")
        if stage not in STAGES:
            stage = "qualified"
        value = data.get("value")
        opportunity = Opportunity(
            organization_id=organization_id,
            lead_id=data.get("lead_id"),
            customer_id=data.get("customer_id"),
            title=title,
            stage=stage,
            value=value,
            currency=data.get("currency", "USD"),
            expected_close_date=to_dt(data.get("expected_close_date")),
            owner_id=data.get("owner_id"),
            description=data.get("description"),
            source=data.get("source", "lead"),
        )
        opportunity.probability = predict_probability(stage, value, 0, 0)
        db.add(opportunity)
        await db.flush()
        await self._activity(db, organization_id=organization_id, opportunity_id=opportunity.id,
                             kind="created", actor_id=actor_id,
                             content=f"Opportunity created in {stage} stage")
        await _event_bus.publish(
            db, name="opportunity.created", organization_id=organization_id, actor_id=actor_id,
            payload={"opportunity_id": opportunity.id, "title": opportunity.title,
                     "stage": opportunity.stage, "value": opportunity.value},
            flush=False,
        )
        await db.flush()
        return opportunity

    async def get(self, db: AsyncSession, *, organization_id: str, opportunity_id: str) -> Optional[Opportunity]:
        return (
            await db.execute(
                select(Opportunity).where(
                    Opportunity.organization_id == organization_id, Opportunity.id == opportunity_id
                )
            )
        ).scalar_one_or_none()

    async def update(self, db: AsyncSession, *, organization_id: str, opportunity_id: str,
                     data: dict[str, Any], actor_id: Optional[str] = None) -> Optional[Opportunity]:
        opportunity = await self.get(db, organization_id=organization_id, opportunity_id=opportunity_id)
        if opportunity is None:
            return None
        for field in ("title", "value", "currency", "expected_close_date", "owner_id",
                      "description", "lead_id", "customer_id"):
            if field in data and data[field] is not None:
                setattr(opportunity, field, data[field])
        if data.get("stage"):
            await self._set_stage(db, opportunity, stage=data["stage"], actor_id=actor_id,
                                  note=data.get("note"))
        opportunity.probability = predict_probability(
            opportunity.stage, opportunity.value, self._age_days(opportunity), 0)
        await db.flush()
        return opportunity

    async def _set_stage(self, db: AsyncSession, opportunity: Opportunity, *, stage: str,
                         actor_id: Optional[str] = None, note: Optional[str] = None) -> None:
        if stage not in STAGES or stage == opportunity.stage:
            return
        old = opportunity.stage
        opportunity.stage = stage
        if stage == "won":
            opportunity.won_at = utcnow()
            opportunity.lost_at = None
            opportunity.risk_level = "low"
        elif stage == "lost":
            opportunity.lost_at = utcnow()
            opportunity.won_at = None
            opportunity.close_reason = note
        else:
            opportunity.won_at = None
            opportunity.lost_at = None
        opportunity.probability = predict_probability(stage, opportunity.value, self._age_days(opportunity), 0)
        await self._activity(db, organization_id=opportunity.organization_id,
                             opportunity_id=opportunity.id, kind="stage_changed", actor_id=actor_id,
                             content=note or f"Stage changed: {old} -> {stage}")
        await _event_bus.publish(
            db, name="opportunity.stage_changed", organization_id=opportunity.organization_id,
            actor_id=actor_id,
            payload={"opportunity_id": opportunity.id, "title": opportunity.title,
                     "from": old, "to": stage, "probability": opportunity.probability},
            flush=False,
        )

    def _age_days(self, opportunity: Opportunity) -> int:
        if opportunity.created_at is None:
            return 0
        return max(0, int((utcnow() - ensure_aware(opportunity.created_at)).total_seconds() // 86400))

    async def close_won(self, db: AsyncSession, *, organization_id: str, opportunity_id: str,
                        note: Optional[str] = None, actor_id: Optional[str] = None,
                        create_customer: bool = True, customer_data: Optional[dict[str, Any]] = None,
                        ) -> dict[str, Any]:
        """Win the deal: creates/updates the customer record and emits events."""
        opportunity = await self.get(db, organization_id=organization_id, opportunity_id=opportunity_id)
        if opportunity is None:
            raise LookupError("Opportunity not found")
        await self._set_stage(db, opportunity, stage="won", actor_id=actor_id, note=note)
        customer_id = opportunity.customer_id
        customer = None
        if create_customer or customer_id is None:
            from app.customers.customer_service import customer_service

            lead = await db.get(Lead, opportunity.lead_id) if opportunity.lead_id else None
            name = (customer_data or {}).get("company_name") or (lead.company_name if lead else None) or opportunity.title
            if customer_id:
                customer = await customer_service.get(db, organization_id=organization_id, customer_id=customer_id)
            if customer is None:
                payload = {
                    "company_name": name,
                    "status": "customer",
                    "industry": (customer_data or {}).get("industry") or (lead.industry if lead else None),
                    "country": (customer_data or {}).get("country") or (lead.country if lead else None),
                    "employee_count": (customer_data or {}).get("employee_count") or (lead.employee_count if lead else None),
                    "source": "opportunity",
                    "owner_id": opportunity.owner_id or (lead.owner_id if lead else None),
                    "annual_value": opportunity.value,
                    "first_contact_at": lead.created_at.isoformat() if lead and lead.created_at else None,
                    "contacts": ([{
                        "name": lead.contact_name, "email": lead.contact_email,
                        "phone": lead.contact_phone, "role": "executive" if lead and lead.contact_name else "other",
                    }] if lead and lead.contact_name else []),
                }
                customer = await customer_service.create(
                    db, organization_id=organization_id, data=payload, actor_id=actor_id)
            elif customer.status == "prospect":
                customer.status = "customer"
            customer_id = customer.id
            opportunity.customer_id = customer.id
        await _event_bus.publish(
            db, name="opportunity.won", organization_id=organization_id, actor_id=actor_id,
            payload={"opportunity_id": opportunity.id, "title": opportunity.title,
                     "value": opportunity.value, "customer_id": customer_id},
            flush=False,
        )
        if customer is not None:
            await customer_service.add_timeline(
                db, organization_id=organization_id, customer_id=customer.id,
                event="opportunity.won", title=f"Deal won — {opportunity.title}",
                detail=note, actor_id=actor_id)
        if lead := await db.get(Lead, opportunity.lead_id) if opportunity.lead_id else None:
            await self._mark_lead_converted(db, lead, actor_id=actor_id)
        await db.flush()
        return {"id": opportunity.id, "stage": "won", "customer_id": customer_id}

    async def close_lost(self, db: AsyncSession, *, organization_id: str, opportunity_id: str,
                         reason: Optional[str] = None, actor_id: Optional[str] = None) -> Optional[Opportunity]:
        opportunity = await self.get(db, organization_id=organization_id, opportunity_id=opportunity_id)
        if opportunity is None:
            return None
        await self._set_stage(db, opportunity, stage="lost", actor_id=actor_id, note=reason)
        await _event_bus.publish(
            db, name="opportunity.lost", organization_id=organization_id, actor_id=actor_id,
            payload={"opportunity_id": opportunity.id, "title": opportunity.title, "reason": reason},
            flush=False,
        )
        await db.flush()
        return opportunity

    async def _mark_lead_converted(self, db: AsyncSession, lead: Lead, *, actor_id: Optional[str] = None) -> None:
        if lead.status != "converted":
            lead.status = "converted"
            lead.converted_at = utcnow()
            await db.flush()

    async def list_opportunities(self, db: AsyncSession, *, organization_id: str, stage: Optional[str] = None,
                                 owner_id: Optional[str] = None, customer_id: Optional[str] = None,
                                 search: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(Opportunity).where(Opportunity.organization_id == organization_id)
        if stage:
            query = query.where(Opportunity.stage == stage)
        if owner_id:
            query = query.where(Opportunity.owner_id == owner_id)
        if customer_id:
            query = query.where(Opportunity.customer_id == customer_id)
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(func.lower(Opportunity.title).like(pattern))
        rows = await db.execute(query.order_by(Opportunity.updated_at.desc()))
        result = []
        for opp in rows.scalars().all():
            owner = await db.get(Employee, opp.owner_id) if opp.owner_id else None
            result.append(self._dict(opp, owner_name=owner.full_name if owner else None))
        return result

    async def pipeline(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        opportunities = (
            await db.execute(select(Opportunity).where(Opportunity.organization_id == organization_id))
        ).scalars().all()
        stages: dict[str, dict[str, Any]] = {}
        total_value = 0.0
        for stage in STAGES:
            stages[stage] = {"count": 0, "value": 0.0, "items": []}
        for opp in opportunities:
            item = self._dict(opp)
            stages[opp.stage]["count"] += 1
            stages[opp.stage]["value"] += opp.value or 0
            stages[opp.stage]["items"].append(item)
            if opp.stage in ("qualified", "proposal", "negotiation"):
                total_value += (opp.value or 0) * (opp.probability / 100)
        return {
            "stages": stages,
            "won": stages["won"]["count"],
            "lost": stages["lost"]["count"],
            "open_count": sum(stages[s]["count"] for s in ("qualified", "proposal", "negotiation")),
            "open_value": sum(stages[s]["value"] for s in ("qualified", "proposal", "negotiation")),
            "weighted_value": round(total_value, 2),
            "win_rate": round(100 * stages["won"]["count"] / max(1, stages["won"]["count"] + stages["lost"]["count"]), 1),
        }

    def _dict(self, opp: Opportunity, owner_name: Optional[str] = None) -> dict[str, Any]:
        return {
            "id": opp.id, "lead_id": opp.lead_id, "customer_id": opp.customer_id,
            "title": opp.title, "stage": opp.stage, "value": opp.value, "currency": opp.currency,
            "probability": opp.probability, "expected_close_date": ensure_aware(opp.expected_close_date).isoformat() if opp.expected_close_date else None,
            "owner_id": opp.owner_id, "owner_name": owner_name, "description": opp.description,
            "risk_level": opp.risk_level, "risk_reasons": opp.risk_reasons or [],
            "close_reason": opp.close_reason,
            "won_at": ensure_aware(opp.won_at).isoformat() if opp.won_at else None,
            "lost_at": ensure_aware(opp.lost_at).isoformat() if opp.lost_at else None,
            "source": opp.source,
            "created_at": ensure_aware(opp.created_at).isoformat() if opp.created_at else None,
            "updated_at": ensure_aware(opp.updated_at).isoformat() if opp.updated_at else None,
        }

    async def _activity(self, db: AsyncSession, *, organization_id: str, opportunity_id: str, kind: str,
                        actor_id: Optional[str] = None, content: Optional[str] = None,
                        metadata: Optional[dict[str, Any]] = None) -> None:
        db.add(OpportunityActivity(
            organization_id=organization_id, opportunity_id=opportunity_id,
            kind=kind if kind in ACTIVITY_KINDS else "noted",
            actor_id=actor_id, content=content, attributes=metadata or {},
        ))
        await db.flush()

    async def add_activity(self, db: AsyncSession, *, organization_id: str, opportunity_id: str, kind: str,
                           content: Optional[str] = None, actor_id: Optional[str] = None) -> bool:
        opp = await self.get(db, organization_id=organization_id, opportunity_id=opportunity_id)
        if opp is None:
            return False
        await self._activity(db, organization_id=organization_id, opportunity_id=opportunity_id,
                             kind=kind, actor_id=actor_id, content=content)
        await db.flush()
        return True

    async def activities(self, db: AsyncSession, *, organization_id: str, opportunity_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(OpportunityActivity).where(
                OpportunityActivity.organization_id == organization_id,
                OpportunityActivity.opportunity_id == opportunity_id,
            ).order_by(OpportunityActivity.created_at.desc())
        )
        result = []
        for entry in rows.scalars().all():
            result.append({
                "id": entry.id, "kind": entry.kind, "actor_id": entry.actor_id,
                "content": entry.content, "metadata": entry.attributes or {},
                "created_at": ensure_aware(entry.created_at).isoformat() if entry.created_at else None,
            })
        return result

    async def delete(self, db: AsyncSession, *, organization_id: str, opportunity_id: str) -> bool:
        opp = await self.get(db, organization_id=organization_id, opportunity_id=opportunity_id)
        if opp is None:
            return False
        await db.delete(opp)
        await db.flush()
        return True


opportunity_service = OpportunityService()
