"""Financial forecasting service (Phase 13 — Finance & Business Operations).

Explainable, rule-based AI forecasts: cash flow, budget usage, expenses,
revenue and project profitability are extrapolated from actuals with a
simple linear trend and confidence bands.
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.events.event_bus import EventBus
from app.finance.parse import clamp_score
from app.models.finance import (
    Budget,
    Expense,
    FinancialForecast,
    Invoice,
    Payment,
)

logger = logging.getLogger("vcos.finance.forecasting")

_event_bus = EventBus()

FORECAST_KINDS = ["cash_flow", "budget_usage", "expense", "revenue", "project_profitability"]


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _trend(series: dict[str, float]) -> tuple[float, float]:
    """Linear regression over (index, value); returns (slope, intercept)."""
    if not series:
        return 0.0, 0.0
    points = sorted(series.items())
    n = len(points)
    xs = list(range(n))
    ys = [v for _, v in points]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    slope = num / den if den else 0.0
    intercept = mean_y - slope * mean_x
    return slope, intercept


class ForecastingService:
    async def generate(self, db: AsyncSession, *, organization_id: str,
                       kind: str = "all", actor_id: Optional[str] = None,
                       horizon_months: int = 6) -> dict[str, Any]:
        kinds = FORECAST_KINDS if kind == "all" else [kind]
        if kind != "all" and kind not in FORECAST_KINDS:
            raise ValueError(f"Invalid forecast kind: {kind}")
        generated: list[dict[str, Any]] = []
        for forecast_kind in kinds:
            forecast = await self._generate_kind(
                db, organization_id=organization_id, kind=forecast_kind, horizon_months=horizon_months,
            )
            db.add(forecast)
            await db.flush()
            generated.append(await self._dict(forecast))
            await _event_bus.publish(
                db, name="forecast.generated", organization_id=organization_id, actor_id=actor_id,
                payload={"forecast_id": forecast.id, "kind": forecast.kind, "horizon_months": horizon_months},
                flush=False,
            )
        return {"generated": len(generated), "forecasts": generated}

    async def _generate_kind(self, db: AsyncSession, *, organization_id: str, kind: str,
                             horizon_months: int) -> FinancialForecast:
        today = date.today()
        period_start = today
        period_end = today + timedelta(days=horizon_months * 30)
        if kind == "cash_flow":
            data = await self._forecast_cash_flow(db, organization_id=organization_id, horizon_months=horizon_months)
        elif kind == "budget_usage":
            data = await self._forecast_budget_usage(db, organization_id=organization_id, horizon_months=horizon_months)
        elif kind == "expense":
            data = await self._forecast_expense(db, organization_id=organization_id, horizon_months=horizon_months)
        elif kind == "revenue":
            data = await self._forecast_revenue(db, organization_id=organization_id, horizon_months=horizon_months)
        else:
            data = await self._forecast_project_profitability(db, organization_id=organization_id, horizon_months=horizon_months)
        confidence = clamp_score(int(data.get("confidence", 70)), 50)
        return FinancialForecast(
            organization_id=organization_id,
            kind=kind,
            horizon_months=horizon_months,
            period_start=period_start,
            period_end=period_end,
            forecast_data=data,
            confidence=confidence,
            generated_by="worker",
            status="generated",
        )

    async def _actual_monthly(self, db: AsyncSession, organization_id: str, *, model, date_field, months: int = 12,
                              status_filter: Optional[list[str]] = None) -> dict[str, float]:
        rows = (
            await db.execute(select(model).where(model.organization_id == organization_id))
        ).scalars().all()
        by_month: dict[str, float] = defaultdict(float)
        today = date.today()
        for row in rows:
            value = getattr(row, "amount", None) or getattr(row, "value", None)
            if value is None:
                continue
            if status_filter and getattr(row, "status", None) not in status_filter:
                continue
            when = getattr(row, date_field)
            if when is None:
                when = (row.created_at or today).date() if isinstance(row.created_at, date) else today
            if isinstance(when, str):
                continue
            if (today - when).days > months * 31:
                continue
            by_month[_month_key(when)] += float(value or 0)
        return dict(by_month)

    async def _forecast_cash_flow(self, db: AsyncSession, *, organization_id: str, horizon_months: int) -> dict[str, Any]:
        inflows = await self._actual_monthly(
            db, organization_id, model=Invoice, date_field="issued_at",
            months=horizon_months, status_filter=["paid"],
        )
        inflow_slope, inflow_base = _trend(inflows)
        current_balance = sum(inflows.values())
        monthly_inflow = (inflow_base + inflow_slope * (horizon_months - 1)) if inflows else current_balance / max(1, len(inflows))
        pending_receivables = sum(
            i.amount or 0 for i in (await db.execute(
                select(Invoice).where(
                    Invoice.organization_id == organization_id,
                    Invoice.direction == "receivable",
                    Invoice.status.in_(("pending", "overdue")),
                )
            )).scalars().all()
        )
        outflows = await self._actual_monthly(
            db, organization_id, model=Payment, date_field="paid_at", months=horizon_months, status_filter=["completed"],
        )
        outflow_slope, outflow_base = _trend(outflows)
        monthly_outflow = (outflow_base + outflow_slope * (horizon_months - 1)) if outflows else current_balance / max(1, len(outflows) or 1)
        pending_payables = sum(
            i.amount or 0 for i in (await db.execute(
                select(Invoice).where(
                    Invoice.organization_id == organization_id,
                    Invoice.direction == "payable",
                    Invoice.status.in_(("pending", "overdue")),
                )
            )).scalars().all()
        )
        months = []
        projected = current_balance + pending_receivables - pending_payables
        for index in range(1, horizon_months + 1):
            projected += monthly_inflow - monthly_outflow
            month = (date.today() + timedelta(days=index * 30)).strftime("%Y-%m")
            months.append({"month": month, "projected_balance": round(projected, 2)})
        run_out_month = None
        for index, item in enumerate(months, start=1):
            if item["projected_balance"] < 0:
                run_out_month = item["month"]
                break
        return {
            "current_balance": round(current_balance, 2),
            "monthly_inflow": round(monthly_inflow, 2),
            "monthly_outflow": round(monthly_outflow, 2),
            "pending_receivables": round(pending_receivables, 2),
            "pending_payables": round(pending_payables, 2),
            "months": months,
            "run_out_month": run_out_month,
            "confidence": 65,
            "basis": "Paid invoices and completed payments over the last 12 months.",
        }

    async def _forecast_budget_usage(self, db: AsyncSession, *, organization_id: str, horizon_months: int) -> dict[str, Any]:
        budgets = (
            await db.execute(select(Budget).where(Budget.organization_id == organization_id))
        ).scalars().all()
        items = []
        today = date.today()
        for budget in budgets:
            expenses = await self._actual_monthly(
                db, organization_id, model=Expense, date_field="incurred_at",
                months=horizon_months, status_filter=["submitted", "pending", "approved", "reimbursed"],
            )
            slope, base = _trend(expenses)
            monthly = (base + slope * (horizon_months - 1)) if expenses else 0.0
            allocated = budget.allocated_amount or 0
            remaining = budget.remaining_amount or 0
            projected_usage = 100
            months_to_exhaust = None
            if monthly > 0 and remaining >= 0:
                months_to_exhaust = remaining / monthly
                projected_usage = 100 * (budget.used_amount or 0) / allocated if allocated else 0
                projected_usage = round(projected_usage + (100 - projected_usage) * min(1.0, (remaining / (monthly * horizon_months)) if monthly * horizon_months > 0 else 0), 1)
            if allocated > 0 and (budget.used_amount or 0) / allocated >= 0.9:
                risk = "critical"
            elif months_to_exhaust is not None and months_to_exhaust <= 3:
                risk = "high"
            elif months_to_exhaust is not None and months_to_exhaust <= 6:
                risk = "medium"
            else:
                risk = "low"
            items.append({
                "budget_id": budget.id,
                "name": budget.name,
                "budget_type": budget.budget_type,
                "allocated": allocated,
                "used": budget.used_amount or 0,
                "remaining": remaining,
                "monthly_burn": round(monthly, 2),
                "months_to_exhaust": round(months_to_exhaust, 1) if months_to_exhaust is not None else None,
                "risk": risk,
            })
        items.sort(key=lambda item: item.get("months_to_exhaust") or 999)
        return {
            "items": items,
            "at_risk": sum(1 for item in items if item["risk"] in ("high", "critical")),
            "confidence": 60,
            "basis": "Historical expense burn extrapolated linearly per budget.",
        }

    async def _forecast_expense(self, db: AsyncSession, *, organization_id: str, horizon_months: int) -> dict[str, Any]:
        actuals = await self._actual_monthly(
            db, organization_id, model=Expense, date_field="incurred_at",
            months=horizon_months, status_filter=["submitted", "pending", "approved", "reimbursed"],
        )
        slope, base = _trend(actuals)
        months = []
        running = sum(actuals.values())
        for index in range(1, horizon_months + 1):
            monthly = max(0.0, base + slope * (len(actuals) + index))
            running += monthly
            month = (date.today() + timedelta(days=index * 30)).strftime("%Y-%m")
            months.append({"month": month, "projected_expense": round(monthly, 2)})
        return {
            "actual_last_12m": dict(sorted(actuals.items())[-12:]),
            "total_actual": round(sum(actuals.values()), 2),
            "monthly_trend": round(slope, 2),
            "months": months,
            "projected_total": round(sum(item["projected_expense"] for item in months), 2),
            "confidence": 62,
            "basis": "Expense categories extrapolated from submitted, approved and reimbursed expenses.",
        }

    async def _forecast_revenue(self, db: AsyncSession, *, organization_id: str, horizon_months: int) -> dict[str, Any]:
        actuals = await self._actual_monthly(
            db, organization_id, model=Invoice, date_field="issued_at",
            months=12, status_filter=["paid"],
        )
        slope, base = _trend(actuals)
        months = []
        for index in range(1, horizon_months + 1):
            monthly = max(0.0, base + slope * (len(actuals) + index))
            month = (date.today() + timedelta(days=index * 30)).strftime("%Y-%m")
            months.append({"month": month, "projected_revenue": round(monthly, 2)})
        pending = sum(
            i.amount or 0 for i in (await db.execute(
                select(Invoice).where(
                    Invoice.organization_id == organization_id,
                    Invoice.direction == "receivable",
                    Invoice.status.in_(("pending", "overdue")),
                )
            )).scalars().all()
        )
        return {
            "actual_revenue_last_12m": dict(sorted(actuals.items())[-12:]),
            "total_actual": round(sum(actuals.values()), 2),
            "pending_receivables": round(pending, 2),
            "months": months,
            "projected_total": round(sum(item["projected_revenue"] for item in months), 2),
            "confidence": 65,
            "basis": "Paid receivable invoices extrapolated linearly.",
        }

    async def _forecast_project_profitability(self, db: AsyncSession, *, organization_id: str, horizon_months: int) -> dict[str, Any]:
        from app.finance.analytics_service import financial_analytics

        data = await financial_analytics.project_financials(db, organization_id=organization_id)
        items = []
        for project in data["projects"]:
            actual_cost = project["actual_cost"] or 0
            budget_allocated = project["budget_allocated"] or 0
            projected_cost = actual_cost
            if budget_allocated > 0 and actual_cost > 0:
                projected_cost = min(actual_cost * 1.15, budget_allocated * 1.05)
            projected_revenue = project["revenue"] or 0
            projected_profit = projected_revenue - projected_cost
            items.append({
                "project_id": project["project_id"],
                "project_name": project["project_name"],
                "actual_cost": round(actual_cost, 2),
                "projected_cost": round(projected_cost, 2),
                "projected_revenue": round(projected_revenue, 2),
                "projected_profit": round(projected_profit, 2),
                "risk": project["risk"],
            })
        items.sort(key=lambda item: item["projected_profit"])
        return {
            "items": items,
            "projected_total_cost": round(sum(item["projected_cost"] for item in items), 2),
            "projected_total_profit": round(sum(item["projected_profit"] for item in items), 2),
            "loss_makers": [item["project_name"] for item in items if item["projected_profit"] < 0],
            "confidence": 55,
            "basis": "Project budgets, actual costs and paid revenue; 15% cost drift buffer applied.",
        }

    async def list_forecasts(self, db: AsyncSession, *, organization_id: str,
                             kind: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        query = select(FinancialForecast).where(FinancialForecast.organization_id == organization_id)
        if kind:
            query = query.where(FinancialForecast.kind == kind)
        rows = await db.execute(query.order_by(FinancialForecast.created_at.desc()).limit(limit))
        return [await self._dict(forecast) for forecast in rows.scalars().all()]

    async def latest(self, db: AsyncSession, *, organization_id: str, kind: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(FinancialForecast).where(
                    FinancialForecast.organization_id == organization_id, FinancialForecast.kind == kind
                ).order_by(FinancialForecast.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return await self._dict(row)

    async def _dict(self, forecast: FinancialForecast) -> dict[str, Any]:
        return {
            "id": forecast.id,
            "kind": forecast.kind,
            "horizon_months": forecast.horizon_months,
            "period_start": forecast.period_start.isoformat() if forecast.period_start else None,
            "period_end": forecast.period_end.isoformat() if forecast.period_end else None,
            "forecast_data": forecast.forecast_data or {},
            "confidence": forecast.confidence,
            "generated_by": forecast.generated_by,
            "status": forecast.status,
            "created_at": ensure_aware(forecast.created_at).isoformat() if forecast.created_at else None,
        }


forecasting_service = ForecastingService()
