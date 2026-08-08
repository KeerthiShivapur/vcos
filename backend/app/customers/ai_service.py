"""AI Customer Companion (Phase 12.14).

Deterministic, role-aware executive assistant for the customer lifecycle:
summaries, at-risk customers, renewals, stalled opportunities, next-best
meeting and pipeline forecasts. Slots into the existing AskEngine interface
so it is available from the global assistant and /ask.
"""

import logging
import re
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.customers.parse import clamp_score, to_date
from app.models.contract import Contract
from app.models.customer import Customer, CustomerMeetingLink, CustomerNote
from app.models.lead import Opportunity
from app.models.ticket import SupportTicket

logger = logging.getLogger("vcos.customers.ai")

_SUMMARY_PATTERN = re.compile(r"(?:summar(?:y|ize|ise))\s+(?:the\s+)?(?:company|customer)\s+(.+)", re.IGNORECASE)


class CustomerAI:
    """Slots into the AskEngine interface (question, organization_id, user)."""

    def __init__(self) -> None:
        self.name = "customer_companion"
        self.description = "Customer, contract and pipeline intelligence for the CROS."

    # ------------------------------------------------------------- public interface

    async def answer(self, db: AsyncSession, *, organization_id: str, user: Any,
                     question: str) -> Optional[dict[str, Any]]:
        lowered = question.lower()
        customers = (
            await db.execute(select(Customer).where(Customer.organization_id == organization_id))
        ).scalars().all()
        if not customers:
            return {"answer": "No customers in this workspace yet. Create your first customer to unlock the companion."}

        match = _SUMMARY_PATTERN.search(question)
        if match:
            company = match.group(1).strip().lower()
            for customer in customers:
                if customer.company_name and company in customer.company_name.lower():
                    return {"answer": await self._summarize(db, organization_id, customer)}

        intent = self._detect_intent(lowered)
        if intent == "renewals":
            return {"answer": await self._renewals(db, organization_id)}
        if intent == "at_risk":
            return {"answer": await self._at_risk(db, organization_id, customers)}
        if intent == "meeting":
            return {"answer": await self._next_meeting(db, organization_id, customers)}
        if intent == "opportunities":
            return {"answer": await self._opportunities(db, organization_id)}
        if intent == "health":
            return {"answer": await self._health(db, organization_id, customers)}
        if intent == "overview":
            return {"answer": await self._overview(db, organization_id, customers)}
        return None

    # ------------------------------------------------------------- intents

    def _detect_intent(self, lowered: str) -> Optional[str]:
        if any(word in lowered for word in ("renewal", "expiring", "renewals", "expiry")):
            return "renewals"
        if any(word in lowered for word in ("at risk", "churn", "risk", "unhealthy", "critical")):
            return "at_risk"
        if any(word in lowered for word in ("meeting", "meet next", "meet with", "who should i meet", "visit", "follow up", "follow-up", "contact next", "touch base")):
            return "meeting"
        if any(word in lowered for word in ("opportunit", "pipeline", "deal", "won", "lost", "stalled")):
            return "opportunities"
        if any(word in lowered for word in ("health", "score", "engagement")):
            return "health"
        if any(word in lowered for word in ("overview", "status", "summary", "portfolio", "dashboard", "how are things")):
            return "overview"
        return None

    # ------------------------------------------------------------- answer builders

    async def _overview(self, db: AsyncSession, organization_id: str, customers) -> str:
        total = len(customers)
        active = sum(1 for c in customers if c.status == "customer")
        at_risk = sum(1 for c in customers if c.health_status in ("at_risk", "critical"))
        revenue = sum((c.annual_value or 0) for c in customers)
        best = max(customers, key=lambda c: c.annual_value or 0, default=None)
        parts = [
            f"Portfolio overview: {total} companies ({active} active, {total - active} prospects), "
            f"{at_risk} currently at risk or critical.",
            f"Total lifetime value: ${revenue:,.0f}.",
        ]
        if best:
            parts.append(
                f"Largest account is {best.company_name} at ${best.annual_value or 0:,.0f} "
                f"(health {best.health_score or 0})."
            )
        return " ".join(parts)

    async def _at_risk(self, db: AsyncSession, organization_id: str, customers) -> str:
        risk = sorted(
            [c for c in customers if c.health_status in ("at_risk", "critical")],
            key=lambda c: c.health_score or 0,
        )
        if not risk:
            return "No customers are at risk right now. Health is green across the portfolio."
        parts = [f"{len(risk)} customer(s) need attention. Highest priority:"]
        for customer in risk[:5]:
            parts.append(
                f"{customer.company_name} — health {customer.health_score or 0} ({customer.health_status}), "
                f"renewal probability {customer.renewal_probability or 0}%."
            )
        return " ".join(parts)

    async def _renewals(self, db: AsyncSession, organization_id: str) -> str:
        contracts = (
            await db.execute(select(Contract).where(Contract.organization_id == organization_id))
        ).scalars().all()
        today = date.today()
        due = []
        for contract in contracts:
            if not contract.expires_at or not contract.customer_id:
                continue
            days = (contract.expires_at - today).days
            if 0 <= days <= 120:
                due.append((days, contract))
        if not due:
            return "No contracts expire within the next 120 days."
        due.sort()
        parts = [f"{len(due)} contract(s) expire within 120 days:"]
        for days, contract in due:
            parts.append(
                f"{contract.title or 'Contract'} expires in {days} day(s) — "
                f"value ${contract.value or 0:,.0f}, renewal status {contract.renewal_status}."
            )
        return " ".join(parts)

    async def _next_meeting(self, db: AsyncSession, organization_id: str, customers) -> str:
        from app.models.customer import CustomerMeetingLink, CustomerNote, CustomerTimeline

        candidates = [c for c in customers if c.status in ("customer", "prospect")]
        if not candidates:
            return "No customers to visit."
        meeting_links = (
            await db.execute(
                select(CustomerMeetingLink).where(CustomerMeetingLink.organization_id == organization_id)
            )
        ).scalars().all()
        last_meeting: dict[str, Any] = {}
        for link in meeting_links:
            created = ensure_aware(link.created_at) if link.created_at else None
            previous = last_meeting.get(link.customer_id)
            if created and (previous is None or created > previous):
                last_meeting[link.customer_id] = created
        health_by_id = {c.id: c.health_score or 0 for c in customers}
        ranked = []
        for customer in candidates:
            last = last_meeting.get(customer.id)
            days_since = (date.today() - last.date()).days if last else 365
            weight = (100 - health_by_id.get(customer.id, 0)) + days_since * 2
            ranked.append((weight, customer, days_since))
        ranked.sort(key=lambda item: item[0], reverse=True)
        weight, customer, days_since = ranked[0]
        return (
            f"Recommend reaching out to {customer.company_name} — last meeting "
            f"{days_since} day(s) ago, health {health_by_id.get(customer.id, 0)}. "
            f"Suggested ask: re-confirm roadmap, surface open tickets, and secure a renewal meeting."
        )

    async def _opportunities(self, db: AsyncSession, organization_id: str) -> str:
        opps = (
            await db.execute(
                select(Opportunity).where(
                    Opportunity.organization_id == organization_id,
                    Opportunity.stage.in_(("qualified", "proposal", "negotiation")),
                )
            )
        ).scalars().all()
        if not opps:
            return "No open opportunities in the pipeline."
        total = sum(o.value or 0 for o in opps)
        avg_win = sum(o.probability or 0 for o in opps) / len(opps)
        parts = [
            f"{len(opps)} open opportunity(ies) worth ${total:,.0f} at an average win probability of {avg_win:.0f}%. "
        ]
        for opp in sorted(opps, key=lambda o: o.value or 0, reverse=True)[:5]:
            parts.append(f"{opp.title} — ${opp.value or 0:,.0f} at {opp.probability or 0}%.")
        return " ".join(parts)

    async def _health(self, db: AsyncSession, organization_id: str, customers) -> str:
        avg = round(sum(c.health_score or 0 for c in customers) / len(customers), 1)
        dist = {"healthy": 0, "at_risk": 0, "critical": 0}
        for customer in customers:
            dist[customer.health_status] = dist.get(customer.health_status, 0) + 1
        return (
            f"Average customer health is {avg}/100. Distribution: {dist['healthy']} healthy, "
            f"{dist['at_risk']} at risk, {dist['critical']} critical. "
            f"Top signal: address at-risk accounts first, then chase renewals inside 90 days."
        )

    async def _summarize(self, db: AsyncSession, organization_id: str, customer) -> str:
        from app.models.customer import CustomerMeetingLink, CustomerNote
        from app.models.ticket import SupportTicket

        tickets = (
            await db.execute(
                select(SupportTicket).where(
                    SupportTicket.organization_id == organization_id, SupportTicket.customer_id == customer.id
                )
            )
        ).scalars().all()
        open_tickets = [t for t in tickets if t.status in ("open", "in_progress", "waiting_customer", "escalated")]
        meeting_count = len(
            (
                await db.execute(
                    select(CustomerMeetingLink).where(
                        CustomerMeetingLink.organization_id == organization_id,
                        CustomerMeetingLink.customer_id == customer.id,
                    )
                )
            ).scalars().all()
        )
        contracts = [
            c for c in (
                await db.execute(
                    select(Contract).where(
                        Contract.organization_id == organization_id, Contract.customer_id == customer.id
                    )
                )
            ).scalars().all()
            if c.status in ("active", "signed", "expiring")
        ]
        value = sum(c.value or 0 for c in contracts)
        notes = (
            await db.execute(
                select(CustomerNote).where(
                    CustomerNote.organization_id == organization_id, CustomerNote.customer_id == customer.id
                ).order_by(CustomerNote.created_at.desc())
            )
        ).scalars().all()
        latest_note = notes[0].content if notes else None
        owner = customer.owner_id
        return (
            f"{customer.company_name}: {customer.status} (tier {customer.tier}), health {customer.health_score or 0} "
            f"({customer.health_status}). "
            f"{meeting_count} meeting(s), {len(open_tickets)} open support ticket(s), "
            f"{len(contracts)} active contract(s) worth ${value:,.0f}. "
            + (f"Owner: {owner}. " if owner else "")
            + (f"Latest note: {latest_note[:160]}" if latest_note else "No notes on file yet.")
        )


customer_ai = CustomerAI()
