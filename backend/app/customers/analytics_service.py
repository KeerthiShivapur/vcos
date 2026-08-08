"""Analytics & Customer Health Engine (Phase 12.11/12.12).

The health engine computes a 0-100 customer health score from support,
projects, communication, contracts, engagement and training signals, and
derives renewal probability. Analytics endpoints power the executive
customer intelligence view: growth, health, renewals, support performance,
revenue trends and concentration risk.
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.customers.parse import clamp_score, to_date
from app.events.event_bus import EventBus
from app.models.contract import Contract
from app.models.customer import (
    Customer,
    CustomerHealth,
    CustomerMeetingLink,
    CustomerNote,
    CustomerProjectLink,
    CustomerTimeline,
)
from app.models.employee import Employee
from app.models.ticket import SupportTicket

logger = logging.getLogger("vcos.customers.analytics")

_event_bus = EventBus()


def _status_from_score(score: int) -> str:
    if score >= 80:
        return "healthy"
    if score >= 50:
        return "at_risk"
    return "critical"


class AnalyticsService:
    # ------------------------------------------------------------------ health engine

    async def compute_customer_health(self, db: AsyncSession, *, organization_id: str,
                                      customer_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Recompute health for one or all customers. Returns updated health dicts."""
        query = select(Customer).where(Customer.organization_id == organization_id)
        if customer_id:
            query = query.where(Customer.id == customer_id)
        customers = (await db.execute(query)).scalars().all()
        updated = []
        now = utcnow()
        today = date.today()
        for customer in customers:
            score, factors, signals = await self._health_factors(
                db, organization_id=organization_id, customer_id=customer.id, now=now, today=today,
            )
            status = _status_from_score(score)
            renewal = self._renewal_probability(score, factors)
            row = (
                await db.execute(
                    select(CustomerHealth).where(
                        CustomerHealth.organization_id == organization_id,
                        CustomerHealth.customer_id == customer.id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = CustomerHealth(
                    organization_id=organization_id, customer_id=customer.id,
                    score=score, status=status, renewal_probability=renewal,
                    factors=factors, signals=signals, computed_at=now,
                )
                db.add(row)
            else:
                row.score, row.status = score, status
                row.renewal_probability = renewal
                row.factors, row.signals, row.computed_at = factors, signals, now
            customer.health_score = score
            customer.health_status = status
            updated.append({
                "customer_id": customer.id, "score": score, "status": status,
                "renewal_probability": renewal, "factors": factors, "signals": signals,
            })
        await db.flush()
        return updated

    async def _health_factors(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                              now: Any, today: date) -> tuple[int, dict[str, Any], list[dict[str, Any]]]:
        signals: list[dict[str, Any]] = []
        # ---- support
        tickets = (
            await db.execute(
                select(SupportTicket).where(
                    SupportTicket.organization_id == organization_id, SupportTicket.customer_id == customer_id
                )
            )
        ).scalars().all()
        open_count = sum(1 for t in tickets if t.status in ("open", "in_progress", "waiting_customer", "escalated"))
        escalated = sum(1 for t in tickets if t.status == "escalated" or t.priority == "urgent")
        total = max(1, len(tickets))
        support_score = clamp_score(100 - (open_count * 20) - (escalated * 30), 40)
        if escalated:
            signals.append({"level": "high", "label": f"{escalated} escalated/urgent support ticket(s)"})
        elif open_count == 0:
            signals.append({"level": "good", "label": "No open support tickets"})

        # ---- projects
        project_links = (
            await db.execute(
                select(CustomerProjectLink).where(
                    CustomerProjectLink.organization_id == organization_id, CustomerProjectLink.customer_id == customer_id
                )
            )
        ).scalars().all()
        active_projects = sum(1 for p in project_links if p.status == "active")
        project_score = clamp_score(40 + active_projects * 15, 40)
        if active_projects >= 2:
            signals.append({"level": "good", "label": f"{active_projects} active project(s)"})
        elif active_projects == 0:
            signals.append({"level": "medium", "label": "No linked projects — delivery at risk"})

        # ---- communication / engagement
        meetings = (
            await db.execute(
                select(CustomerMeetingLink).where(
                    CustomerMeetingLink.organization_id == organization_id, CustomerMeetingLink.customer_id == customer_id
                )
            )
        ).scalars().all()
        ninety_days = now - timedelta(days=90)
        recent_meetings = 0
        for meeting in meetings:
            created = ensure_aware(meeting.created_at) if meeting.created_at else None
            if created and created >= ninety_days:
                recent_meetings += 1
        note_count = (
            await db.execute(
                select(func.count(CustomerNote.id)).where(
                    CustomerNote.organization_id == organization_id, CustomerNote.customer_id == customer_id
                )
            )
        ).scalar_one()
        comm_score = clamp_score(30 + recent_meetings * 15 + int(note_count or 0) * 5, 30)
        if recent_meetings == 0:
            signals.append({"level": "high", "label": "No customer meetings in the last 90 days"})
        elif recent_meetings >= 2:
            signals.append({"level": "good", "label": f"{recent_meetings} meeting(s) in the last 90 days"})

        # ---- contracts
        contracts = (
            await db.execute(
                select(Contract).where(
                    Contract.organization_id == organization_id, Contract.customer_id == customer_id,
                    Contract.status.in_(("active", "signed", "expiring")),
                )
            )
        ).scalars().all()
        if contracts:
            nearest_expiry = min((c.expires_at for c in contracts if c.expires_at), default=None)
        else:
            nearest_expiry = None
        contract_score = 50
        if nearest_expiry:
            days_left = (nearest_expiry - today).days
            if days_left < 0:
                contract_score = 10
                signals.append({"level": "high", "label": f"Contract expired on {nearest_expiry}"})
            elif days_left <= 30:
                contract_score = 30
                signals.append({"level": "high", "label": f"Contract expires in {days_left} day(s) ({nearest_expiry})"})
            elif days_left <= 90:
                contract_score = 55
                signals.append({"level": "medium", "label": f"Contract renewal due within 90 days ({nearest_expiry})"})
            else:
                contract_score = 80
        elif contracts:
            contract_score = 70
        else:
            signals.append({"level": "medium", "label": "No signed contracts on record"})

        # ---- weighted total
        score = int(0.25 * support_score + 0.2 * project_score + 0.2 * comm_score + 0.25 * contract_score + 0.1 * 50)
        score = clamp_score(score, 40)
        factors = {
            "support": {"score": support_score, "open_tickets": open_count, "escalated": escalated, "total": len(tickets)},
            "projects": {"score": project_score, "active": active_projects, "total": len(project_links)},
            "communication": {"score": comm_score, "meetings_90d": recent_meetings, "notes": int(note_count or 0)},
            "contracts": {"score": contract_score, "active": len(contracts), "expires_in_days": (nearest_expiry - today).days if nearest_expiry else None},
            "engagement": {"score": min(100, comm_score + int(note_count or 0))},
        }
        return score, factors, signals

    def _renewal_probability(self, score: int, factors: dict[str, Any]) -> float:
        base = float(score) * 0.9
        if factors.get("contracts", {}).get("active", 0) >= 2:
            base += 5
        if factors.get("support", {}).get("escalated", 0):
            base -= 10
        return round(max(0.0, min(100.0, base)), 1)

    # ------------------------------------------------------------------ dashboard / analytics

    async def dashboard(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        customers = (
            await db.execute(select(Customer).where(Customer.organization_id == organization_id))
        ).scalars().all()
        statuses = {"prospect": 0, "customer": 0, "inactive": 0}
        health = {"healthy": 0, "at_risk": 0, "critical": 0, "new": 0}
        tiers: dict[str, int] = {}
        for customer in customers:
            statuses[customer.status] = statuses.get(customer.status, 0) + 1
            health[customer.health_status] = health.get(customer.health_status, 0) + 1
            tiers[customer.tier] = tiers.get(customer.tier, 0) + 1
        open_opps = (
            await db.execute(
                select(func.count()).select_from(Contract).where(
                    Contract.organization_id == organization_id,
                )
            )
        ).scalar_one()
        return {
            "total_customers": len(customers),
            "active_customers": statuses["customer"],
            "prospects": statuses["prospect"],
            "by_status": statuses,
            "by_health": health,
            "by_tier": tiers,
            "contracts": open_opps,
            "health_good": health["healthy"],
            "health_risk": health["at_risk"] + health["critical"],
        }

    async def analytics(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        customers = (
            await db.execute(select(Customer).where(Customer.organization_id == organization_id))
        ).scalars().all()
        contracts = (
            await db.execute(select(Contract).where(Contract.organization_id == organization_id))
        ).scalars().all()
        tickets = (
            await db.execute(select(SupportTicket).where(SupportTicket.organization_id == organization_id))
        ).scalars().all()

        # growth: customers created per month (last 6 months)
        growth: dict[str, int] = defaultdict(int)
        for customer in customers:
            if customer.created_at:
                month = ensure_aware(customer.created_at).strftime("%Y-%m")
                growth[month] += 1
        revenue = sum(c.value or 0 for c in contracts if c.status in ("active", "signed", "expiring"))
        by_customer: dict[str, float] = defaultdict(float)
        for contract in contracts:
            if contract.customer_id and contract.status in ("active", "signed", "expiring"):
                by_customer[contract.customer_id] += contract.value or 0
        top_customers = sorted(
            by_customer.items(), key=lambda item: item[1], reverse=True
        )[:5]
        by_customer_name: list[dict[str, Any]] = []
        customer_by_id = {c.id: c for c in customers}
        for customer_id, value in top_customers:
            customer = customer_by_id.get(customer_id)
            by_customer_name.append({
                "customer_id": customer_id,
                "company_name": customer.company_name if customer else "Unknown",
                "value": value,
            })
        by_status: dict[str, int] = defaultdict(int)
        for ticket in tickets:
            by_status[ticket.status] += 1
        total_value = sum(by_customer.values())
        concentration = 0.0
        if total_value and by_customer:
            concentration = round(100 * max(by_customer.values()) / total_value, 1)
        health_rows = (
            await db.execute(select(CustomerHealth).where(CustomerHealth.organization_id == organization_id))
        ).scalars().all()
        health_distribution = {"healthy": 0, "at_risk": 0, "critical": 0}
        for row in health_rows:
            health_distribution[row.status] = health_distribution.get(row.status, 0) + 1
        return {
            "growth": dict(sorted(growth.items())[-6:]),
            "total_customers": len(customers),
            "revenue": round(total_value, 2),
            "top_customers": by_customer_name,
            "support": dict(by_status),
            "health_distribution": health_distribution,
            "concentration_risk": {"top_customer_share": concentration, "customers": len(by_customer)},
            "contracts_active": sum(1 for c in contracts if c.status == "active"),
            "renewals_due": sum(1 for c in contracts if c.renewal_status == "due_soon"),
        }

    async def renewals(self, db: AsyncSession, *, organization_id: str, horizon_days: int = 120) -> dict[str, Any]:
        from app.customers.contract_service import contract_service

        contracts = await contract_service.list_contracts(db, organization_id=organization_id, expiring_soon=True)
        today = date.today()
        for contract in contracts:
            expires = to_date(contract["expires_at"])
            if expires:
                contract["days_left"] = (expires - today).days
        contracts.sort(key=lambda item: item.get("days_left") or 9999)
        return {
            "total_due": len(contracts),
            "contracts": contracts[:50],
            "horizon_days": horizon_days,
        }

    async def health(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(select(CustomerHealth).where(CustomerHealth.organization_id == organization_id))
        ).scalars().all()
        result = []
        for row in rows:
            customer = await db.get(Customer, row.customer_id)
            if customer is None:
                continue
            result.append({
                "customer_id": row.customer_id,
                "company_name": customer.company_name,
                "score": row.score,
                "status": row.status,
                "renewal_probability": row.renewal_probability,
                "factors": row.factors or {},
                "signals": row.signals or [],
                "computed_at": ensure_aware(row.computed_at).isoformat() if row.computed_at else None,
            })
        result.sort(key=lambda item: item["score"])
        return result


analytics_service = AnalyticsService()
