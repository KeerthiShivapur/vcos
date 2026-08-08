"""Autonomous executive briefing — delivered every morning without asking.

Sections: company summary, project risks, hiring status, knowledge growth,
customer health, financial summary, innovation summary and AI recommendations.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.briefing import ExecutiveBriefing
from app.models.customer import Customer, CustomerHealth
from app.models.employee import Employee
from app.models.finance import Budget
from app.models.innovation import Innovation
from app.models.knowledge import Document
from app.models.project import Project
from app.models.task import Task


class ExecutiveBriefingEngine:
    async def generate(
        self, db: AsyncSession, organization_id: str, *, commit: bool = False
    ) -> dict[str, Any]:
        now = utcnow()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        async def _count(model, **filters):
            stmt = select(func.count(model.id)).where(model.organization_id == organization_id)
            for key, value in filters.items():
                stmt = stmt.where(getattr(model, key) == value)
            return (await db.execute(stmt)).scalar() or 0

        employees = await _count(Employee)
        projects = (
            await db.execute(
                select(Project).where(Project.organization_id == organization_id).limit(200)
            )
        ).scalars().all()
        active = [p for p in projects if p.status in ("active", "in_progress", "on_track")]
        at_risk = [p for p in projects if p.status in ("at_risk", "blocked")]
        overdue = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.due_date.isnot(None),
                    Task.due_date < now,
                    Task.status.notin_(["done", "completed", "cancelled"]),
                )
            )
        ).scalar() or 0
        docs = await _count(Document)
        docs_week = (
            await db.execute(
                select(func.count(Document.id)).where(
                    Document.organization_id == organization_id, Document.created_at >= week_ago
                )
            )
        ).scalar() or 0
        hired = (
            await db.execute(
                select(func.count(Employee.id)).where(
                    Employee.organization_id == organization_id, Employee.created_at >= month_ago
                )
            )
        ).scalar() or 0
        customers = (
            await db.execute(
                select(func.count(Customer.id)).where(Customer.organization_id == organization_id)
            )
        ).scalar() or 0
        low_health = (
            await db.execute(
                select(func.count(CustomerHealth.id))
                .join(Customer, Customer.id == CustomerHealth.customer_id)
                .where(Customer.organization_id == organization_id, CustomerHealth.score < 50)
            )
        ).scalar() or 0
        budgets = (
            await db.execute(
                select(Budget).where(Budget.organization_id == organization_id, Budget.status == "active")
            )
        ).scalars().all()
        allocated = sum(b.allocated_amount or 0 for b in budgets)
        used = sum(b.used_amount or 0 for b in budgets)
        usage_pct = round(used / max(allocated, 1) * 100, 1)
        innovations = await _count(Innovation)
        active_innovations = await _count(Innovation, status="active")

        sections = {
            "company_summary": (
                f"{employees} employees across {len(active)} active projects with "
                f"{docs} knowledge documents."
            ),
            "project_risks": (
                f"{len(at_risk)} project(s) at risk, {overdue} overdue task(s)."
            ),
            "hiring_status": f"{hired} employee(s) hired in the last 30 days.",
            "knowledge_growth": f"{docs_week} document(s) added this week.",
            "customer_health": (
                f"{customers} customers; {low_health} below 50 health."
            ),
            "financial_summary": f"{usage_pct}% of allocated budget used.",
            "innovation_summary": f"{active_innovations} active innovation item(s) of {innovations}.",
            "recommendations": [],
        }
        recommendations: list[dict[str, Any]] = []
        if at_risk:
            recommendations.append({"title": "Intervene on at-risk projects", "impact": "high"})
        if overdue >= 3:
            recommendations.append({"title": "Clear overdue tasks", "impact": "medium"})
        if low_health:
            recommendations.append({"title": "Retain at-risk customers", "impact": "high"})
        if usage_pct >= 90:
            recommendations.append({"title": "Review budget allocation", "impact": "medium"})
        if not recommendations:
            recommendations.append({"title": "Maintain current trajectory", "impact": "low"})
        sections["recommendations"] = recommendations

        highlights = [
            f"{employees} employees",
            f"{len(active)} active projects",
            f"{usage_pct}% budget usage",
        ]
        risks = [f"{len(at_risk)} at-risk projects", f"{overdue} overdue tasks", f"{low_health} risky customers"]
        summary = " | ".join(highlights)

        row = ExecutiveBriefing(
            organization_id=organization_id,
            briefing_date=now,
            title=f"Morning briefing — {now.strftime('%Y-%m-%d')}",
            summary=summary,
            sections=sections,
            highlights=highlights,
            risks=risks,
            recommendations=recommendations,
            source_event="executive.briefing.generated",
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db, name="executive.briefing.generated", organization_id=organization_id,
            payload={"briefing_id": row.id, "date": now.strftime("%Y-%m-%d")},
        )
        if commit:
            await db.commit()
        return {
            "id": row.id, "title": row.title, "summary": summary,
            "sections": sections, "highlights": highlights, "risks": risks,
            "recommendations": recommendations,
            "briefing_date": row.briefing_date.isoformat() if row.briefing_date else None,
        }

    async def latest(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        row = (
            await db.execute(
                select(ExecutiveBriefing)
                .where(ExecutiveBriefing.organization_id == organization_id)
                .order_by(ExecutiveBriefing.briefing_date.desc())
                .limit(1)
            )
        ).scalars().first()
        if row is None:
            return await self.generate(db, organization_id, commit=True)
        return {
            "id": row.id, "title": row.title, "summary": row.summary,
            "sections": row.sections or {}, "highlights": row.highlights or [],
            "risks": row.risks or [], "recommendations": row.recommendations or [],
            "briefing_date": row.briefing_date.isoformat() if row.briefing_date else None,
        }


executive_briefing_engine = ExecutiveBriefingEngine()
