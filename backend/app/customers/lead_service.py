"""Lead service (Phase 12.2 — Lead Management).

Lead lifecycle: new -> qualified -> converted -> (opportunity/customer).
AI scoring covers fit, budget, urgency and duplicates; every interaction is
recorded as lead activity so the journey is fully auditable.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.customers.parse import clamp_score, to_dt
from app.events.event_bus import EventBus
from app.models.employee import Employee
from app.models.lead import Lead, LeadActivity

logger = logging.getLogger("vcos.customers.lead")

_event_bus = EventBus()

LEAD_STATUSES = ["new", "qualified", "converted", "lost"]
LEAD_SOURCES = ["website", "referral", "marketing", "events", "cold_outreach", "partner", "advertisement"]
ACTIVITY_KINDS = ["created", "called", "emailed", "met", "noted", "qualified", "converted", "lost", "status_changed"]


def score_lead(data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Deterministic AI-style scoring: fit, budget, urgency, engagement."""
    score = 50
    factors: dict[str, Any] = {}
    industry = (data.get("industry") or "").lower()
    if any(k in industry for k in ("software", "tech", "saas", "ai", "fintech")):
        score += 15
        factors["fit"] = "high-fit industry"
    elif industry:
        score += 5
        factors["fit"] = "industry known"
    else:
        factors["fit"] = "industry unknown"
    if data.get("employee_count"):
        count = int(data["employee_count"])
        if count >= 500:
            score += 15
            factors["budget"] = "enterprise scale"
        elif count >= 50:
            score += 8
            factors["budget"] = "mid-market scale"
        else:
            factors["budget"] = "small account"
    else:
        factors["budget"] = "size unknown"
    needs = (data.get("needs") or "").lower()
    if any(word in needs for word in ("urgent", "asap", "now", "immediately")):
        score += 10
        factors["urgency"] = "urgent need stated"
    else:
        factors["urgency"] = "no explicit urgency"
    if data.get("source") in ("referral", "partner", "events"):
        score += 8
        factors["engagement"] = "warm source"
    else:
        factors["engagement"] = "cold source"
    if data.get("expected_value"):
        value = float(data["expected_value"])
        if value >= 100000:
            score += 12
            factors["value"] = "high value"
        elif value >= 25000:
            score += 6
            factors["value"] = "mid value"
    return clamp_score(score), factors


class LeadService:
    async def create(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
                     actor_id: Optional[str] = None) -> Lead:
        company = (data.get("company_name") or "").strip()
        if not company:
            raise ValueError("company_name is required")
        duplicate = await self._find_duplicate(db, organization_id=organization_id,
                                               company=company, email=data.get("contact_email"))
        score, factors = score_lead(data)
        lead = Lead(
            organization_id=organization_id,
            status="new",
            company_name=company,
            contact_name=data.get("contact_name"),
            contact_email=data.get("contact_email"),
            contact_phone=data.get("contact_phone"),
            source=data.get("source", "website") if data.get("source") in LEAD_SOURCES else "website",
            industry=data.get("industry"),
            country=data.get("country"),
            employee_count=data.get("employee_count"),
            needs=data.get("needs"),
            owner_id=data.get("owner_id"),
            score=score,
            score_factors=factors,
            duplicate_of=duplicate.id if duplicate else None,
            expected_value=data.get("expected_value"),
            last_touch_at=utcnow(),
        )
        lead.priority = "high" if score >= 75 else ("medium" if score >= 50 else "low")
        db.add(lead)
        await db.flush()
        await self._activity(db, organization_id=organization_id, lead_id=lead.id,
                             kind="created", actor_id=actor_id,
                             content=f"Lead created from {lead.source} with score {lead.score}")
        await _event_bus.publish(
            db, name="lead.created", organization_id=organization_id, actor_id=actor_id,
            payload={"lead_id": lead.id, "company_name": lead.company_name,
                     "score": lead.score, "duplicate_of": lead.duplicate_of},
            flush=False,
        )
        await db.flush()
        return lead

    async def _find_duplicate(self, db: AsyncSession, *, organization_id: str,
                              company: str, email: Optional[str]) -> Optional[Lead]:
        query = select(Lead).where(
            Lead.organization_id == organization_id,
            Lead.status != "lost",
            func.lower(Lead.company_name) == company.lower(),
        )
        row = (await db.execute(query.limit(1))).scalar_one_or_none()
        if row is not None:
            return row
        if email:
            row = (
                await db.execute(
                    select(Lead).where(
                        Lead.organization_id == organization_id,
                        Lead.status != "lost",
                        func.lower(Lead.contact_email) == email.lower(),
                    ).limit(1)
                )
            ).scalar_one_or_none()
        return row

    async def get(self, db: AsyncSession, *, organization_id: str, lead_id: str) -> Optional[Lead]:
        return (
            await db.execute(
                select(Lead).where(Lead.organization_id == organization_id, Lead.id == lead_id)
            )
        ).scalar_one_or_none()

    async def update(self, db: AsyncSession, *, organization_id: str, lead_id: str, data: dict[str, Any],
                     actor_id: Optional[str] = None) -> Optional[Lead]:
        lead = await self.get(db, organization_id=organization_id, lead_id=lead_id)
        if lead is None:
            return None
        for field in ("company_name", "contact_name", "contact_email", "contact_phone", "industry",
                      "country", "employee_count", "needs", "owner_id", "expected_value"):
            if field in data and data[field] is not None:
                setattr(lead, field, data[field])
        if data.get("source") in LEAD_SOURCES:
            lead.source = data["source"]
        if data.get("status"):
            await self._transition(db, lead, status=data["status"], actor_id=actor_id,
                                   content=data.get("note"))
        lead.last_touch_at = utcnow()
        await db.flush()
        return lead

    async def _transition(self, db: AsyncSession, lead: Lead, *, status: str,
                          actor_id: Optional[str] = None, content: Optional[str] = None) -> None:
        if status not in LEAD_STATUSES or status == lead.status:
            return
        old = lead.status
        lead.status = status
        if status == "qualified":
            lead.qualified_at = utcnow()
        elif status == "converted":
            lead.converted_at = utcnow()
        elif status == "lost":
            lead.converted_at = None
        await self._activity(db, organization_id=lead.organization_id, lead_id=lead.id,
                             kind="status_changed", actor_id=actor_id,
                             content=content or f"Status changed: {old} -> {status}")
        await _event_bus.publish(
            db, name="lead.qualified" if status == "qualified" else "lead.status_changed",
            organization_id=lead.organization_id, actor_id=actor_id,
            payload={"lead_id": lead.id, "company_name": lead.company_name, "from": old, "to": status},
            flush=False,
        )

    async def list_leads(self, db: AsyncSession, *, organization_id: str, status: Optional[str] = None,
                         source: Optional[str] = None, owner_id: Optional[str] = None,
                         search: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(Lead).where(Lead.organization_id == organization_id)
        if status:
            query = query.where(Lead.status == status)
        if source:
            query = query.where(Lead.source == source)
        if owner_id:
            query = query.where(Lead.owner_id == owner_id)
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(Lead.company_name).like(pattern),
                    func.lower(Lead.contact_name).like(pattern),
                    func.lower(Lead.contact_email).like(pattern),
                )
            )
        rows = await db.execute(query.order_by(Lead.score.desc(), Lead.created_at.desc()))
        result = []
        for lead in rows.scalars().all():
            owner = await db.get(Employee, lead.owner_id) if lead.owner_id else None
            result.append(self._dict(lead, owner_name=owner.full_name if owner else None))
        return result

    def _dict(self, lead: Lead, owner_name: Optional[str] = None) -> dict[str, Any]:
        return {
            "id": lead.id, "status": lead.status, "company_name": lead.company_name,
            "contact_name": lead.contact_name, "contact_email": lead.contact_email,
            "contact_phone": lead.contact_phone, "source": lead.source, "industry": lead.industry,
            "country": lead.country, "employee_count": lead.employee_count, "needs": lead.needs,
            "owner_id": lead.owner_id, "owner_name": owner_name, "score": lead.score,
            "priority": lead.priority, "score_factors": lead.score_factors or {},
            "duplicate_of": lead.duplicate_of, "expected_value": lead.expected_value,
            "qualified_at": ensure_aware(lead.qualified_at).isoformat() if lead.qualified_at else None,
            "converted_at": ensure_aware(lead.converted_at).isoformat() if lead.converted_at else None,
            "last_touch_at": ensure_aware(lead.last_touch_at).isoformat() if lead.last_touch_at else None,
            "created_at": ensure_aware(lead.created_at).isoformat() if lead.created_at else None,
        }

    async def _activity(self, db: AsyncSession, *, organization_id: str, lead_id: str, kind: str,
                        actor_id: Optional[str] = None, content: Optional[str] = None,
                        metadata: Optional[dict[str, Any]] = None) -> None:
        db.add(LeadActivity(
            organization_id=organization_id, lead_id=lead_id,
            kind=kind if kind in ACTIVITY_KINDS else "noted",
            actor_id=actor_id, content=content, attributes=metadata or {},
        ))
        await db.flush()

    async def add_activity(self, db: AsyncSession, *, organization_id: str, lead_id: str, kind: str,
                           content: Optional[str] = None, actor_id: Optional[str] = None) -> bool:
        lead = await self.get(db, organization_id=organization_id, lead_id=lead_id)
        if lead is None:
            return False
        await self._activity(db, organization_id=organization_id, lead_id=lead_id, kind=kind,
                             actor_id=actor_id, content=content)
        lead.last_touch_at = utcnow()
        await db.flush()
        return True

    async def activities(self, db: AsyncSession, *, organization_id: str, lead_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(LeadActivity).where(
                LeadActivity.organization_id == organization_id, LeadActivity.lead_id == lead_id
            ).order_by(LeadActivity.created_at.desc())
        )
        result = []
        for entry in rows.scalars().all():
            result.append({
                "id": entry.id, "kind": entry.kind, "actor_id": entry.actor_id,
                "content": entry.content, "metadata": entry.attributes or {},
                "created_at": ensure_aware(entry.created_at).isoformat() if entry.created_at else None,
            })
        return result

    async def delete(self, db: AsyncSession, *, organization_id: str, lead_id: str) -> bool:
        lead = await self.get(db, organization_id=organization_id, lead_id=lead_id)
        if lead is None:
            return False
        await db.delete(lead)
        await db.flush()
        return True


lead_service = LeadService()
