"""Finance AI companion (Phase 13 — Finance & Business Operations).

Deterministic, explainable financial assistant: answers budget, approval,
project, spending and recommendation questions using live data.
"""

import logging
import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.risk_service import risk_service
from app.models.finance import (
    Budget,
    Expense,
    FinancialMetric,
    Invoice,
    PurchaseRequest,
    PurchaseOrder,
    Vendor,
)

logger = logging.getLogger("vcos.finance.ai")

INTENTS = [
    "budget_remaining", "pending_approvals", "at_risk_projects", "next_quarter_spend",
    "recommendations", "overview", "fallback",
]


class FinanceAIService:
    async def chat(self, db: AsyncSession, *, organization_id: str, message: str) -> dict[str, Any]:
        intent = await self._detect_intent(message)
        handler = getattr(self, f"_intent_{intent}", None)
        if handler is None:
            intent = "fallback"
            handler = self._intent_fallback
        content = await handler(db, organization_id=organization_id, message=message)
        return {
            "intent": intent,
            "content": content,
            "source": "finance_ai",
            "reply": content,
        }

    async def _detect_intent(self, message: str) -> str:
        text = message.lower()
        if any(word in text for word in ("budget left", "budget remaining", "how much budget", "budget status")):
            return "budget_remaining"
        if any(word in text for word in ("approval", "pending request", "awaiting", "approve")):
            return "pending_approvals"
        if any(word in text for word in ("risk", "at risk", "loss", "overrun", "overspend")):
            return "at_risk_projects"
        if any(word in text for word in ("next quarter", "forecast", "projection", "will we spend")):
            return "next_quarter_spend"
        if any(word in text for word in ("recommend", "optimize", "save", "cut cost", "improve")):
            return "recommendations"
        if any(word in text for word in ("overview", "summary", "how are we doing", "health")):
            return "overview"
        return "fallback"

    async def _intent_budget_remaining(self, db: AsyncSession, *, organization_id: str, **_: Any) -> str:
        budgets = (
            await db.execute(select(Budget).where(Budget.organization_id == organization_id))
        ).scalars().all()
        if not budgets:
            return "You have no budgets defined yet. Create a budget to start tracking spending."
        lines = []
        for budget in sorted(budgets, key=lambda b: (b.used_amount or 0) / (b.allocated_amount or 1), reverse=True):
            allocated = budget.allocated_amount or 0
            remaining = budget.remaining_amount or 0
            pct = (budget.used_amount or 0) / allocated if allocated else 0
            state = "over budget" if remaining < 0 else f"{pct * 100:.0f}% used"
            lines.append(f"- {budget.name}: {remaining:,.2f} remaining of {allocated:,.2f} ({state})")
        return "Budget status:\n" + "\n".join(lines)

    async def _intent_pending_approvals(self, db: AsyncSession, *, organization_id: str, **_: Any) -> str:
        purchases = (
            await db.execute(
                select(PurchaseRequest).where(
                    PurchaseRequest.organization_id == organization_id,
                    PurchaseRequest.status.in_(("submitted", "manager_approved")),
                )
            )
        ).scalars().all()
        expenses = (
            await db.execute(
                select(Expense).where(
                    Expense.organization_id == organization_id, Expense.status == "submitted",
                )
            )
        ).scalars().all()
        total = len(purchases) + len(expenses)
        if total == 0:
            return "There are no purchases or expenses awaiting approval right now."
        lines = [f"There are {total} items awaiting approval:"]
        for purchase in purchases[:5]:
            lines.append(f"- Purchase request {purchase.id[:8]}: {purchase.estimated_cost:,.2f} for {purchase.title or 'requested item'}")
        for expense in expenses[:5]:
            lines.append(f"- Expense: {expense.amount:,.2f} ({expense.expense_type or 'other'})")
        if total > 10:
            lines.append(f"...and {total - 10} more.")
        return "\n".join(lines)

    async def _intent_at_risk_projects(self, db: AsyncSession, *, organization_id: str, **_: Any) -> str:
        from app.finance.analytics_service import financial_analytics

        data = await financial_analytics.project_financials(db, organization_id=organization_id)
        at_risk = [project for project in data["projects"] if project["risk"] in ("high", "critical")]
        if not at_risk:
            return "No projects are currently at financial risk. All projects are within their budgets."
        lines = [f"{len(at_risk)} project(s) need attention:"]
        for project in at_risk[:5]:
            lines.append(
                f"- {project['project_name']}: {project['actual_cost']:,.2f} spent vs {project['budget_allocated']:,.2f} allocated ({project['risk']})"
            )
        return "\n".join(lines)

    async def _intent_next_quarter_spend(self, db: AsyncSession, *, organization_id: str, **_: Any) -> str:
        from app.finance.forecasting_service import forecasting_service

        expense = await forecasting_service.latest(db, organization_id=organization_id, kind="expense")
        if expense is None or not expense.get("forecast_data"):
            return "Run a forecast first (finance/forecasts) so I can project next-quarter spend."
        data = expense["forecast_data"]
        projected = data.get("projected_total", 0)
        confidence = expense.get("confidence", 0)
        return (
            f"Projected operating spend over the next {expense.get('horizon_months', 6)} months is "
            f"{projected:,.2f} (confidence {confidence}%). "
            f"Trend: {data.get('monthly_trend', 0):+.2f} per month. "
            f"Total actual spend in the last 12 months was {data.get('total_actual', 0):,.2f}."
        )

    async def _intent_recommendations(self, db: AsyncSession, *, organization_id: str, **_: Any) -> str:
        recommendations: list[str] = []
        budgets = (
            await db.execute(select(Budget).where(Budget.organization_id == organization_id))
        ).scalars().all()
        for budget in budgets:
            allocated = budget.allocated_amount or 0
            used = budget.used_amount or 0
            if allocated > 0 and used >= allocated * 0.9:
                recommendations.append(
                    f"Increase or reallocate '{budget.name}' — it is over 90% consumed."
                )
        expenses = (
            await db.execute(
                select(Expense).where(
                    Expense.organization_id == organization_id, Expense.status.in_(("submitted", "pending")),
                )
            )
        ).scalars().all()
        missing = [e for e in expenses if (e.policy_flags or {}).get("missing_receipt")]
        if missing:
            recommendations.append(
                f"Collect receipts for {len(missing)} expenses before month-end to stay audit-ready."
            )
        vendors = (
            await db.execute(select(Vendor).where(Vendor.organization_id == organization_id))
        ).scalars().all()
        from app.finance.vendor_service import vendor_service

        high_risk = []
        for vendor in vendors:
            profile = await vendor_service.risk_profile(db, organization_id=organization_id, vendor_id=vendor.id)
            if profile.get("score", 0) >= 75:
                high_risk.append(vendor)
        if high_risk:
            recommendations.append(
                f"Review vendor relationships: {len(high_risk)} vendor(s) carry high risk scores."
            )
        with_sales = sum(1 for vendor in vendors if (vendor.attributes or {}).get("with_sales_membership"))
        if with_sales and len(vendors) > with_sales * 2:
            recommendations.append(
                "Several vendors do not have a Sales Tax/VAT registration number — verify compliance status."
            )
        if not recommendations:
            recommendations.append("Everything looks healthy. No immediate financial actions required.")
        return "Recommendations:\n" + "\n".join(f"- {item}" for item in recommendations)

    async def _intent_overview(self, db: AsyncSession, *, organization_id: str, **_: Any) -> str:
        from app.finance.analytics_service import financial_analytics

        data = await financial_analytics.dashboard(db, organization_id=organization_id)
        summary = await risk_service.summarize(db, organization_id=organization_id)
        return (
            f"Finance overview — {data.get('month', '')}:\n"
            f"- Total revenue: {data.get('revenue', 0):,.2f}\n"
            f"- Operating costs: {data.get('operating_costs', 0):,.2f}\n"
            f"- Pending approvals: {data.get('pending_approvals', 0)}\n"
            f"- Budget health score: {summary['health_score']} with {summary['total']} open risks"
        )

    async def _intent_fallback(self, db: AsyncSession, *, organization_id: str, message: str, **_: Any) -> str:
        text = message.lower()
        if "metric" in text or "kpi" in text:
            rows = (
                await db.execute(
                    select(FinancialMetric).where(FinancialMetric.organization_id == organization_id).limit(10)
                )
            ).scalars().all()
            if rows:
                return "Tracked metrics:\n" + "\n".join(f"- {row.name}: {row.value:.2f}" for row in rows)
        return (
            "I can help with finance questions like:\n"
            "- 'What is my budget remaining?'\n"
            "- 'What is pending approval?'\n"
            "- 'Which projects are at risk?'\n"
            "- 'What will we spend next quarter?'\n"
            "- 'Give me cost-saving recommendations'"
        )


finance_ai_service = FinanceAIService()
