"""Executive strategy engine — reasons across the entire organization.

Answers: what to focus on next year, which departments are weak, where to
invest, which products to stop, which customers are risky, where money is lost.
Produces strategy reports persisted in strategy_reports.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.customer import Customer, CustomerHealth
from app.models.employee import Employee
from app.models.finance import Budget, Expense
from app.models.knowledge import Document
from app.models.project import Project
from app.models.strategy_report import StrategyReport
from app.models.task import Task


class StrategyEngine:
    async def analyze(
        self, db: AsyncSession, organization_id: str, *, period: str = "weekly",
        commit: bool = False,
    ) -> dict[str, Any]:
        now = utcnow()
        findings: list[dict[str, Any]] = []
        recommendations: list[dict[str, Any]] = []
        priorities: list[dict[str, Any]] = []
        risks: list[dict[str, Any]] = []
        weak_departments: list[str] = []
        focus_areas: list[str] = []

        employees = (
            await db.execute(
                select(func.count(Employee.id)).where(Employee.organization_id == organization_id)
            )
        ).scalar() or 0
        projects = (
            await db.execute(
                select(Project).where(Project.organization_id == organization_id).limit(200)
            )
        ).scalars().all()
        active = [p for p in projects if p.status in ("active", "in_progress", "on_track")]
        at_risk = [p for p in projects if p.status in ("at_risk", "blocked")]
        overdue_tasks = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.due_date.isnot(None),
                    Task.due_date < now,
                    Task.status.notin_(["done", "completed", "cancelled"]),
                )
            )
        ).scalar() or 0

        docs = (
            await db.execute(
                select(func.count(Document.id)).where(Document.organization_id == organization_id)
            )
        ).scalar() or 0

        customers = (
            await db.execute(
                select(CustomerHealth).join(Customer, Customer.id == CustomerHealth.customer_id)
                .where(Customer.organization_id == organization_id).limit(200)
            )
        ).scalars().all()
        risky_customers = [
            {"name": getattr(c, "customer_id", None), "score": c.score}
            for c in customers if getattr(c, "score", 100) is not None and c.score < 50
        ]

        budgets = (
            await db.execute(
                select(Budget).where(Budget.organization_id == organization_id, Budget.status == "active")
            )
        ).scalars().all()
        allocated = sum(b.allocated_amount or 0 for b in budgets)
        used = sum(b.used_amount or 0 for b in budgets)
        underused = [b for b in budgets if (b.allocated_amount or 0) > 0 and (b.used_amount or 0) / b.allocated_amount < 0.3]
        overrun = [b for b in budgets if (b.allocated_amount or 0) > 0 and (b.used_amount or 0) / b.allocated_amount > 0.9]

        expenses = (
            await db.execute(
                select(Expense).where(Expense.organization_id == organization_id).limit(200)
            )
        ).scalars().all()
        spend_by_cat: dict[str, float] = {}
        for e in expenses:
            cat = getattr(e, "category", None) or "other"
            spend_by_cat[cat] = spend_by_cat.get(cat, 0) + (getattr(e, "amount", 0) or 0)

        if at_risk:
            findings.append({"topic": "project_risks", "detail": f"{len(at_risk)} at-risk projects", "severity": "high"})
            risks.append({"title": "At-risk projects", "detail": f"{len(at_risk)} projects need intervention"})
            priorities.append({"title": "Stabilize at-risk projects", "rank": 1})
            focus_areas.append("Project recovery")
        if overdue_tasks >= 5:
            findings.append({"topic": "delivery", "detail": f"{overdue_tasks} overdue tasks", "severity": "medium"})
            priorities.append({"title": "Clear overdue task backlog", "rank": 2})
        if risky_customers:
            findings.append({"topic": "customers", "detail": f"{len(risky_customers)} risky customers", "severity": "high"})
            risks.append({"title": "Customer churn", "detail": f"{len(risky_customers)} customers below 50 health"})
            priorities.append({"title": "Run customer retention program", "rank": 3})
            focus_areas.append("Customer retention")
        if overrun:
            findings.append({"topic": "finance", "detail": f"{len(overrun)} budgets near exhaustion", "severity": "medium"})
            risks.append({"title": "Budget overruns", "detail": f"{len(overrun)} active budgets above 90%"})
            priorities.append({"title": "Contain budget overruns", "rank": 4})
        if underused:
            findings.append({"topic": "finance", "detail": f"{len(underused)} underused budgets", "severity": "low"})
            recommendations.append({
                "title": "Reallocate underused budget lines",
                "detail": f"Move funds from {len(underused)} under-utilized budgets",
                "impact": "medium",
            })
            focus_areas.append("Capital efficiency")
        if spend_by_cat:
            top_spend = max(spend_by_cat, key=spend_by_cat.get)
            findings.append({"topic": "spend", "detail": f"Largest spend category: {top_spend}", "severity": "low"})
        if not docs and projects:
            recommendations.append({
                "title": "Build the knowledge base",
                "detail": "No documents exist for project context",
                "impact": "medium",
            })
            focus_areas.append("Knowledge")

        if not priorities:
            priorities.append({"title": "Maintain growth trajectory", "rank": 1})
        if not focus_areas:
            focus_areas.append("Operational excellence")

        summary = (
            f"Organization health signals: {len(active)} active projects, {employees} employees, "
            f"{len(risky_customers)} risky customers, {round(used / max(allocated, 1) * 100, 1)}% budget usage."
        )
        row = StrategyReport(
            organization_id=organization_id,
            period=period,
            title=f"Strategy report — {period}",
            summary=summary,
            findings=findings,
            recommendations=recommendations,
            priorities=sorted(priorities, key=lambda p: p["rank"]),
            risks=risks,
            focus_areas=focus_areas,
            weak_departments=weak_departments,
            source_event="strategy.updated",
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db, name="strategy.updated", organization_id=organization_id,
            payload={"report_id": row.id, "period": period, "findings": len(findings)},
        )
        if commit:
            await db.commit()
        return {
            "id": row.id, "period": period, "title": row.title, "summary": summary,
            "findings": findings, "recommendations": recommendations,
            "priorities": sorted(priorities, key=lambda p: p["rank"]),
            "risks": risks, "focus_areas": focus_areas, "weak_departments": weak_departments,
        }

    async def list(
        self, db: AsyncSession, organization_id: str, *, limit: int = 30
    ) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(StrategyReport)
                .where(StrategyReport.organization_id == organization_id)
                .order_by(StrategyReport.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return {
            "total": len(rows),
            "reports": [
                {
                    "id": r.id, "period": r.period, "title": r.title, "summary": r.summary,
                    "findings": r.findings or [], "recommendations": r.recommendations or [],
                    "priorities": r.priorities or [], "risks": r.risks or [],
                    "focus_areas": r.focus_areas or [], "weak_departments": r.weak_departments or [],
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }


strategy_engine = StrategyEngine()
