"""Financial analytics service (Phase 13 — Finance & Business Operations).

Business intelligence, not accounting: revenue intelligence, cost
intelligence, budget usage, project profitability, vendor spend and
executive dashboards.
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.finance import (
    Budget,
    Expense,
    FinancialMetric,
    Invoice,
    Payment,
    PurchaseOrder,
    PurchaseRequest,
    Vendor,
    VendorContract,
)

logger = logging.getLogger("vcos.finance.analytics")


class FinancialAnalyticsService:
    async def dashboard(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        budgets = (
            await db.execute(select(Budget).where(Budget.organization_id == organization_id))
        ).scalars().all()
        expenses = (
            await db.execute(select(Expense).where(Expense.organization_id == organization_id))
        ).scalars().all()
        invoices = (
            await db.execute(select(Invoice).where(Invoice.organization_id == organization_id))
        ).scalars().all()
        payments = (
            await db.execute(select(Payment).where(Payment.organization_id == organization_id))
        ).scalars().all()
        requests = (
            await db.execute(select(PurchaseRequest).where(PurchaseRequest.organization_id == organization_id))
        ).scalars().all()
        vendors = (
            await db.execute(select(Vendor).where(Vendor.organization_id == organization_id))
        ).scalars().all()

        allocated = sum(b.allocated_amount or 0 for b in budgets)
        budget_used = sum(b.used_amount or 0 for b in budgets)
        expense_total = sum(e.amount for e in expenses if e.status in ("submitted", "pending", "approved", "reimbursed"))
        payable_due = sum(i.amount for i in invoices if i.direction == "payable" and i.status in ("pending", "overdue"))
        receivable_due = sum(i.amount for i in invoices if i.direction == "receivable" and i.status in ("pending", "overdue"))
        completed_payments = [p for p in payments if p.status == "completed"]
        total_paid = sum(p.amount for p in completed_payments)
        revenue = sum(i.amount for i in invoices if i.direction == "receivable" and i.status == "paid")
        costs = sum(i.amount for i in invoices if i.direction == "payable" and i.status == "paid")

        pending_approvals = sum(1 for e in expenses if e.status in ("submitted", "pending")) + sum(
            1 for r in requests if r.status in ("submitted", "manager_approved")
        )
        return {
            "total_budgets": len(budgets),
            "budget_allocated": round(allocated, 2),
            "budget_used": round(budget_used, 2),
            "budget_remaining": round(max(0.0, allocated - budget_used), 2),
            "budget_usage_pct": round(100 * budget_used / allocated, 1) if allocated > 0 else 0.0,
            "expense_total": round(expense_total, 2),
            "operating_costs": round(expense_total, 2),
            "pending_approvals": pending_approvals,
            "payable_due": round(payable_due, 2),
            "receivable_due": round(receivable_due, 2),
            "total_paid": round(total_paid, 2),
            "revenue": round(revenue, 2),
            "costs": round(costs, 2),
            "overdue_invoices": sum(1 for i in invoices if i.status == "overdue"),
            "open_purchase_requests": sum(1 for r in requests if r.status not in ("rejected", "cancelled", "ordered")),
            "purchase_orders": sum(1 for o in (await db.execute(
                select(PurchaseOrder).where(PurchaseOrder.organization_id == organization_id)
            )).scalars().all() if o.status in ("issued", "accepted", "partially_delivered", "delivered")),
            "vendors": len(vendors),
            "high_risk_budgets": sum(1 for b in budgets if b.risk_level in ("high", "critical")),
        }

    async def revenue(self, db: AsyncSession, *, organization_id: str, months: int = 12) -> dict[str, Any]:
        invoices = (
            await db.execute(
                select(Invoice).where(Invoice.organization_id == organization_id, Invoice.direction == "receivable")
            )
        ).scalars().all()
        today = date.today()
        by_month: dict[str, float] = defaultdict(float)
        by_customer: dict[str, float] = defaultdict(float)
        by_project: dict[str, float] = defaultdict(float)
        by_department: dict[str, float] = defaultdict(float)
        for invoice in invoices:
            if invoice.status != "paid" or not invoice.issued_at:
                continue
            month = invoice.issued_at.strftime("%Y-%m")
            if (today - invoice.issued_at).days <= months * 31:
                by_month[month] += invoice.amount or 0
            if invoice.customer_id:
                by_customer[invoice.customer_id] += invoice.amount or 0
            if invoice.project_id:
                by_project[invoice.project_id] += invoice.amount or 0
        customer_rows = {}
        if by_customer:
            from app.models.customer import Customer
            customer_rows = {c.id: c for c in (await db.execute(
                select(Customer).where(Customer.id.in_(list(by_customer.keys())))
            )).scalars().all()}
        project_rows = {}
        if by_project:
            from app.models.project import Project
            project_rows = {p.id: p for p in (await db.execute(
                select(Project).where(Project.id.in_(list(by_project.keys())))
            )).scalars().all()}
        total = sum(by_month.values())
        return {
            "total_revenue": round(total, 2),
            "by_month": dict(sorted(by_month.items())[-months:]),
            "by_customer": [
                {"customer_id": cid, "company_name": customer_rows.get(cid).company_name if customer_rows.get(cid) else "Unknown",
                 "value": round(value, 2)}
                for cid, value in sorted(by_customer.items(), key=lambda item: item[1], reverse=True)
            ],
            "by_project": [
                {"project_id": pid, "project_name": project_rows.get(pid).title if project_rows.get(pid) else "Unknown",
                 "value": round(value, 2)}
                for pid, value in sorted(by_project.items(), key=lambda item: item[1], reverse=True)
            ],
        }

    async def costs(self, db: AsyncSession, *, organization_id: str, months: int = 12) -> dict[str, Any]:
        expenses = (
            await db.execute(select(Expense).where(Expense.organization_id == organization_id))
        ).scalars().all()
        invoices = (
            await db.execute(select(Invoice).where(Invoice.organization_id == organization_id, Invoice.direction == "payable"))
        ).scalars().all()
        today = date.today()
        by_month: dict[str, float] = defaultdict(float)
        by_type: dict[str, float] = defaultdict(float)
        by_vendor: dict[str, float] = defaultdict(float)
        for expense in expenses:
            if expense.status in ("rejected", "draft") or not expense.incurred_at:
                continue
            if (today - expense.incurred_at).days <= months * 31:
                by_month[expense.incurred_at.strftime("%Y-%m")] += expense.amount or 0
            by_type[expense.expense_type] += expense.amount or 0
        for invoice in invoices:
            if invoice.status != "paid":
                continue
            if invoice.issued_at and (today - invoice.issued_at).days <= months * 31:
                by_month[invoice.issued_at.strftime("%Y-%m")] += invoice.amount or 0
            if invoice.vendor_id:
                by_vendor[invoice.vendor_id] += invoice.amount or 0
        vendor_rows = {}
        if by_vendor:
            vendor_rows = {v.id: v for v in (await db.execute(
                select(Vendor).where(Vendor.id.in_(list(by_vendor.keys())))
            )).scalars().all()}
        total = sum(by_month.values())
        return {
            "total_cost": round(total, 2),
            "by_month": dict(sorted(by_month.items())[-months:]),
            "by_type": dict(sorted(by_type.items(), key=lambda item: item[1], reverse=True)),
            "by_vendor": [
                {"vendor_id": vid, "vendor_name": vendor_rows.get(vid).name if vendor_rows.get(vid) else "Unknown",
                 "value": round(value, 2)}
                for vid, value in sorted(by_vendor.items(), key=lambda item: item[1], reverse=True)
            ],
        }

    async def project_financials(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        from app.models.project import Project

        projects = (
            await db.execute(select(Project).where(Project.organization_id == organization_id))
        ).scalars().all()
        budgets = (
            await db.execute(
                select(Budget).where(Budget.organization_id == organization_id, Budget.project_id.isnot(None))
            )
        ).scalars().all()
        expenses = (
            await db.execute(select(Expense).where(Expense.organization_id == organization_id, Expense.project_id.isnot(None)))
        ).scalars().all()
        invoices = (
            await db.execute(select(Invoice).where(Invoice.organization_id == organization_id, Invoice.project_id.isnot(None)))
        ).scalars().all()
        budget_by_project: dict[str, list[Budget]] = defaultdict(list)
        for budget in budgets:
            budget_by_project[budget.project_id].append(budget)
        expense_total: dict[str, float] = defaultdict(float)
        for expense in expenses:
            if expense.status in ("submitted", "pending", "approved", "reimbursed"):
                expense_total[expense.project_id] += expense.amount or 0
        revenue_by_project: dict[str, float] = defaultdict(float)
        for invoice in invoices:
            if invoice.direction == "receivable" and invoice.status == "paid":
                revenue_by_project[invoice.project_id] += invoice.amount or 0
        result = []
        for project in projects:
            project_budgets = budget_by_project.get(project.id, [])
            allocated = sum(b.allocated_amount or 0 for b in project_budgets)
            used = sum(b.used_amount or 0 for b in project_budgets)
            project_expense = expense_total.get(project.id, 0.0)
            actual_cost = round(max(used, project_expense), 2)
            revenue = round(revenue_by_project.get(project.id, 0.0), 2)
            profit = round(revenue - actual_cost, 2)
            if allocated > 0:
                budget_usage = round(100 * actual_cost / allocated, 1)
                if budget_usage >= 90:
                    risk = "critical"
                elif budget_usage >= 75:
                    risk = "high"
                elif budget_usage >= 50:
                    risk = "medium"
                else:
                    risk = "low"
            else:
                budget_usage = 0.0
                risk = "low"
            result.append({
                "project_id": project.id,
                "project_name": project.name,
                "budget_allocated": round(allocated, 2),
                "budget_used": round(used, 2),
                "actual_cost": actual_cost,
                "budget_usage_pct": budget_usage,
                "revenue": revenue,
                "profit": profit,
                "profitability": round(100 * profit / actual_cost, 1) if actual_cost > 0 else None,
                "risk": risk,
            })
        result.sort(key=lambda item: item.get("profitability") or 0)
        return {
            "projects": result,
            "total_allocated": round(sum(item["budget_allocated"] for item in result), 2),
            "total_cost": round(sum(item["actual_cost"] for item in result), 2),
            "total_revenue": round(sum(item["revenue"] for item in result), 2),
            "total_profit": round(sum(item["profit"] for item in result), 2),
            "at_risk": sum(1 for item in result if item["risk"] in ("high", "critical")),
        }

    async def expense_trends(self, db: AsyncSession, *, organization_id: str, months: int = 6) -> dict[str, Any]:
        today = date.today()
        start = today - timedelta(days=months * 31)
        expenses = (
            await db.execute(
                select(Expense).where(
                    Expense.organization_id == organization_id,
                    Expense.status.in_(("submitted", "pending", "approved", "reimbursed")),
                )
            )
        ).scalars().all()
        by_month: dict[str, float] = defaultdict(float)
        by_employee: dict[str, float] = defaultdict(float)
        for expense in expenses:
            incurred = expense.incurred_at or today
            if incurred >= start:
                by_month[incurred.strftime("%Y-%m")] += expense.amount or 0
            if expense.employee_id:
                by_employee[expense.employee_id] += expense.amount or 0
        employee_rows = {}
        if by_employee:
            from app.models.employee import Employee
            employee_rows = {e.id: e for e in (await db.execute(
                select(Employee).where(Employee.id.in_(list(by_employee.keys())))
            )).scalars().all()}
        return {
            "by_month": dict(sorted(by_month.items())[-months:]),
            "total": round(sum(by_month.values()), 2),
            "by_employee": [
                {"employee_id": eid, "employee_name": employee_rows.get(eid).full_name if employee_rows.get(eid) else "Unknown",
                 "value": round(value, 2)}
                for eid, value in sorted(by_employee.items(), key=lambda item: item[1], reverse=True)[:10]
            ],
        }

    async def vendor_spend(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        payments = (
            await db.execute(
                select(Payment).where(Payment.organization_id == organization_id, Payment.status == "completed")
            )
        ).scalars().all()
        by_vendor: dict[str, float] = defaultdict(float)
        for payment in payments:
            if payment.vendor_id:
                by_vendor[payment.vendor_id] += payment.amount or 0
        vendor_rows = {}
        if by_vendor:
            vendor_rows = {v.id: v for v in (await db.execute(
                select(Vendor).where(Vendor.id.in_(list(by_vendor.keys())))
            )).scalars().all()}
        rows = sorted(
            [
                {"vendor_id": vid, "vendor_name": vendor_rows.get(vid).name if vendor_rows.get(vid) else "Unknown",
                 "total_spend": round(value, 2)}
                for vid, value in by_vendor.items()
            ],
            key=lambda item: item["total_spend"], reverse=True,
        )
        return {"vendors": rows, "total_spend": round(sum(item["total_spend"] for item in rows), 2)}

    async def approvals_pipeline(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        expenses = (
            await db.execute(
                select(Expense).where(
                    Expense.organization_id == organization_id, Expense.status.in_(("submitted", "pending"))
                )
            )
        ).scalars().all()
        requests = (
            await db.execute(
                select(PurchaseRequest).where(
                    PurchaseRequest.organization_id == organization_id,
                    PurchaseRequest.status.in_(("submitted", "manager_approved")),
                )
            )
        ).scalars().all()
        invoices = (
            await db.execute(
                select(Invoice).where(
                    Invoice.organization_id == organization_id, Invoice.status == "pending"
                )
            )
        ).scalars().all()
        return {
            "expenses_pending": len(expenses),
            "expense_value": round(sum(e.amount for e in expenses), 2),
            "purchase_requests_pending": len(requests),
            "purchase_value": round(sum(r.estimated_cost for r in requests), 2),
            "invoices_pending": len(invoices),
            "invoice_value": round(sum(i.amount for i in invoices), 2),
            "total_pending": len(expenses) + len(requests) + len(invoices),
        }

    async def record_metric(
        self, db: AsyncSession, *, organization_id: str, metric_type: str, period: str, value: float,
        payload: Optional[dict[str, Any]] = None,
    ) -> FinancialMetric:
        row = (
            await db.execute(
                select(FinancialMetric).where(
                    FinancialMetric.organization_id == organization_id,
                    FinancialMetric.metric_type == metric_type,
                    FinancialMetric.period == period,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = FinancialMetric(
                organization_id=organization_id, metric_type=metric_type, period=period,
                value=value, payload=payload or {},
            )
            db.add(row)
        else:
            row.value = value
            row.payload = payload or {}
        await db.flush()
        return row

    async def metrics(self, db: AsyncSession, *, organization_id: str, metric_type: Optional[str] = None, limit: int = 60) -> dict[str, Any]:
        query = select(FinancialMetric).where(FinancialMetric.organization_id == organization_id)
        if metric_type:
            query = query.where(FinancialMetric.metric_type == metric_type)
        rows = await db.execute(query.order_by(FinancialMetric.period.desc()).limit(limit))
        items = [{
            "id": m.id, "metric_type": m.metric_type, "period": m.period, "value": m.value,
            "created_at": ensure_aware(m.created_at).isoformat() if m.created_at else None,
        } for m in rows.scalars().all()]
        return {"metrics": items, "total": len(items)}


financial_analytics = FinancialAnalyticsService()
