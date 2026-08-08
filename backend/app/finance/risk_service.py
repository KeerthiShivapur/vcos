"""Financial risk detection service (Phase 13 — Finance & Business Operations).

Scans budgets, expenses, purchase orders, invoices, payments and vendors for
rule-based anomalies: budget overruns, duplicate payments, late invoices,
vendor risk, unexpected spending, cash-flow risk and compliance gaps.
"""

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.finance.parse import clamp_score
from app.models.finance import (
    Budget,
    Expense,
    FinancialMetric,
    Invoice,
    Payment,
    PurchaseOrder,
    Vendor,
)

logger = logging.getLogger("vcos.finance.risk")

DUPLICATE_WINDOW_DAYS = 90
SUSPICIOUS_CATEGORIES = {"entertainment", "travel", "meals", "gifts"}


class RiskService:
    async def scan(self, db: AsyncSession, *, organization_id: str,
                   actor_id: str | None = None) -> dict[str, Any]:
        risks: list[dict[str, Any]] = []
        risks.extend(await self._budget_overruns(db, organization_id=organization_id))
        risks.extend(await self._duplicate_payments(db, organization_id=organization_id))
        risks.extend(await self._late_invoices(db, organization_id=organization_id))
        risks.extend(await self._vendor_risks(db, organization_id=organization_id))
        risks.extend(await self._unexpected_spending(db, organization_id=organization_id))
        risks.extend(await self._cash_flow_risks(db, organization_id=organization_id))
        risks.extend(await self._compliance_gaps(db, organization_id=organization_id))
        risks.sort(key=lambda risk: {"critical": 0, "high": 1, "medium": 2, "low": 3}[risk["severity"]])
        await self._record_metrics(db, organization_id=organization_id, risks=risks)
        return {"total": len(risks), "risks": risks}

    async def _record_metrics(self, db: AsyncSession, *, organization_id: str, risks: list[dict[str, Any]]) -> None:
        counts: dict[str, int] = {}
        for risk in risks:
            counts[risk["type"]] = counts.get(risk["type"], 0) + 1
        period = date.today().strftime("%Y-%m")
        for name, value in counts.items():
            existing = (
                await db.execute(
                    select(FinancialMetric).where(
                        FinancialMetric.organization_id == organization_id,
                        FinancialMetric.metric_type == f"risk.{name}",
                        FinancialMetric.period == period,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.value = float(value)
            else:
                db.add(FinancialMetric(
                    organization_id=organization_id, metric_type=f"risk.{name}", period=period,
                    value=float(value),
                ))

    async def _budget_overruns(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        budgets = (
            await db.execute(select(Budget).where(Budget.organization_id == organization_id))
        ).scalars().all()
        risks = []
        for budget in budgets:
            allocated = budget.allocated_amount or 0
            used = budget.used_amount or 0
            if allocated <= 0 or used <= 0:
                continue
            pct = used / allocated
            if pct >= 1.0:
                severity = "critical"
                message = f"Budget '{budget.name}' is over its allocation ({pct * 100:.0f}% used)"
            elif pct >= 0.9:
                severity = "high"
                message = f"Budget '{budget.name}' is close to exhaustion ({pct * 100:.0f}% used)"
            elif pct >= 0.75:
                severity = "medium"
                message = f"Budget '{budget.name}' has consumed {pct * 100:.0f}% of its allocation"
            else:
                continue
            risks.append({
                "id": budget.id,
                "type": "budget_overrun",
                "severity": severity,
                "message": message,
                "entity_type": "budget",
                "entity_id": budget.id,
                "value": round(used - allocated, 2) if pct >= 1 else round(allocated - used, 2),
                "budget_id": budget.id,
                "budget_name": budget.name,
            })
        return risks

    async def _duplicate_payments(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        payments = (
            await db.execute(
                select(Payment).where(
                    Payment.organization_id == organization_id, Payment.status == "completed",
                )
            )
        ).scalars().all()
        window = date.today() - timedelta(days=DUPLICATE_WINDOW_DAYS)
        by_key: dict[str, list] = {}
        for payment in payments:
            paid_at = payment.paid_at or payment.created_at.date()
            if paid_at < window:
                continue
            key = (payment.reference or payment.external_id or "").strip().lower()
            if not key:
                continue
            by_key.setdefault(key, []).append(payment)
        risks = []
        for key, group in by_key.items():
            if len(group) < 2:
                continue
            amounts = [p.amount or 0 for p in group]
            if max(amounts) - min(amounts) > 0.01:
                continue
            risks.append({
                "id": group[0].id,
                "type": "duplicate_payment",
                "severity": "high",
                "message": f"Possible duplicate payment of {amounts[0]:.2f} to '{key}' within {DUPLICATE_WINDOW_DAYS} days",
                "entity_type": "payment",
                "entity_id": group[0].id,
                "value": amounts[0],
                "payment_ids": [p.id for p in group],
            })
        return risks

    async def _late_invoices(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        invoices = (
            await db.execute(
                select(Invoice).where(
                    Invoice.organization_id == organization_id, Invoice.status == "overdue",
                )
            )
        ).scalars().all()
        risks = []
        today = date.today()
        for invoice in invoices:
            due = invoice.due_at
            days = (today - due).days if due else 0
            severity = "critical" if days > 30 else "high" if days > 14 else "medium"
            side = "receivable from" if invoice.direction == "receivable" else "payable to"
            risks.append({
                "id": invoice.id,
                "type": "late_invoice",
                "severity": severity,
                "message": f"Invoice {invoice.invoice_number or invoice.id[:8]} is {days} days overdue ({side} {invoice.title or 'counterparty'})",
                "entity_type": "invoice",
                "entity_id": invoice.id,
                "value": invoice.amount or 0,
                "days_overdue": days,
            })
        return risks

    async def _vendor_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        from app.finance.vendor_service import vendor_service

        vendors = (
            await db.execute(select(Vendor).where(Vendor.organization_id == organization_id))
        ).scalars().all()
        risks = []
        for vendor in vendors:
            profile = await vendor_service.risk_profile(db, organization_id=organization_id, vendor_id=vendor.id)
            score = profile.get("score") or 0
            severity = "high" if score >= 75 else "medium" if score >= 60 else "low"
            if severity == "low":
                continue
            risks.append({
                "id": vendor.id,
                "type": "vendor_risk",
                "severity": severity,
                "message": f"Vendor '{vendor.name}' has an elevated risk score of {score}",
                "entity_type": "vendor",
                "entity_id": vendor.id,
                "value": float(score),
                "vendor_id": vendor.id,
            })
        return risks

    async def _unexpected_spending(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        expenses = (
            await db.execute(
                select(Expense).where(
                    Expense.organization_id == organization_id,
                    Expense.status.in_(("submitted", "pending", "approved")),
                    Expense.incurred_at >= date.today() - timedelta(days=30),
                )
            )
        ).scalars().all()
        risks = []
        for expense in expenses:
            flags = expense.policy_flags or {}
            if not flags.get("flagged"):
                continue
            severity = "high" if flags.get("high_amount") else "medium"
            reasons = [reason for reason, active in flags.items() if active and reason != "flagged"]
            risks.append({
                "id": expense.id,
                "type": "unexpected_spending",
                "severity": severity,
                "message": f"Expense of {expense.amount:.2f} ({expense.expense_type or 'other'}) flagged: {', '.join(reasons)}",
                "entity_type": "expense",
                "entity_id": expense.id,
                "value": expense.amount or 0,
            })
        return risks

    async def _cash_flow_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        receivable = (
            await db.execute(
                select(Invoice).where(
                    Invoice.organization_id == organization_id,
                    Invoice.direction == "receivable",
                    Invoice.status.in_(("pending", "overdue")),
                )
            )
        ).scalars().all()
        payable = (
            await db.execute(
                select(Invoice).where(
                    Invoice.organization_id == organization_id,
                    Invoice.direction == "payable",
                    Invoice.status.in_(("pending", "overdue")),
                )
            )
        ).scalars().all()
        paid_in_30 = (
            await db.execute(
                select(Payment).where(
                    Payment.organization_id == organization_id,
                    Payment.status == "completed",
                    Payment.paid_at >= date.today() - timedelta(days=30),
                )
            )
        ).scalars().all()
        receivable_total = sum(i.amount or 0 for i in receivable)
        payable_total = sum(i.amount or 0 for i in payable)
        recent_paid = sum(p.amount or 0 for p in paid_in_30)
        risks = []
        if payable_total > 0 and receivable_total > 0 and payable_total > receivable_total * 1.5:
            risks.append({
                "id": "cash_flow",
                "type": "cash_flow_risk",
                "severity": "high",
                "message": f"Payables ({payable_total:.2f}) exceed receivables ({receivable_total:.2f}) — short-term liquidity pressure",
                "entity_type": "organization",
                "entity_id": organization_id,
                "value": round(payable_total - receivable_total, 2),
            })
        elif receivable_total == 0 and payable_total > recent_paid * 2:
            risks.append({
                "id": "cash_flow_2",
                "type": "cash_flow_risk",
                "severity": "medium",
                "message": f"No pending receivables but {payable_total:.2f} in outstanding payables",
                "entity_type": "organization",
                "entity_id": organization_id,
                "value": round(payable_total, 2),
            })
        return risks

    async def _compliance_gaps(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        expenses = (
            await db.execute(
                select(Expense).where(
                    Expense.organization_id == organization_id,
                    Expense.status.in_(("submitted", "pending")),
                )
            )
        ).scalars().all()
        risks = []
        for expense in expenses:
            flags = expense.policy_flags or {}
            if not flags.get("missing_receipt"):
                continue
            if expense.amount and expense.amount > 25:
                risks.append({
                    "id": expense.id,
                    "type": "compliance_gap",
                    "severity": "medium",
                    "message": f"Expense of {expense.amount:.2f} lacks a receipt and exceeds the $25 threshold",
                    "entity_type": "expense",
                    "entity_id": expense.id,
                    "value": expense.amount,
                })
        return risks

    async def summarize(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        data = await self.scan(db, organization_id=organization_id, actor_id=None)
        by_severity: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        by_type: dict[str, int] = {}
        for risk in data["risks"]:
            by_severity[risk["severity"]] = by_severity.get(risk["severity"], 0) + 1
            by_type[risk["type"]] = by_type.get(risk["type"], 0) + 1
        total = data["total"]
        score = 0
        if total:
            score = min(100, int(
                (by_severity["critical"] * 25 + by_severity["high"] * 10 + by_severity["medium"] * 4) * 100.0 / (total * 25)
            ))
        return {
            "total": total,
            "by_severity": by_severity,
            "by_type": by_type,
            "health_score": clamp_score(100 - score, 50),
            "risks": data["risks"],
        }


risk_service = RiskService()
