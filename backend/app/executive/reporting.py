"""Phase 8.13 — Executive Reports.

AI automatically generates daily, weekly, monthly, quarterly, board, annual,
department, hiring, innovation, knowledge and compliance reports. Every report
is written from live organizational data with traceable numbers and persisted
for export (text/markdown/csv).
"""

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.ai import AIPrediction
from app.models.approval import Risk
from app.models.communication import CommunityPost, InnovationIdea, Recognition
from app.models.department import Department
from app.models.employee import Employee
from app.models.executive import ExecutiveRecommendation, ExecutiveReport, StrategicRisk
from app.models.goal import Goal
from app.models.knowledge import Decision, Document, Policy, SOP, Template, WikiPage
from app.models.meeting import Meeting
from app.models.project import Project
from app.models.task import Task

logger = logging.getLogger("vcos.executive.reporting")

REPORT_TYPES = [
    "daily", "weekly", "monthly", "quarterly", "board",
    "annual", "department", "hiring", "innovation", "knowledge", "compliance",
]

_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
    "board": 30,
    "annual": 365,
}


class ReportingService:
    async def generate(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        report_type: str = "weekly",
        user_id: str | None = None,
        department_id: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        if report_type not in REPORT_TYPES:
            raise ValueError(f"report_type must be one of {', '.join(REPORT_TYPES)}")

        now = utcnow()
        days = _DAYS.get(report_type, 7)
        since = now - timedelta(days=days)

        from app.models.organization import Organization

        org_row = await db.get(Organization, organization_id)
        org_name = org_row.name if org_row else "The Company"

        projects = (await db.execute(
            select(Project).where(Project.organization_id == organization_id)
        )).scalars().all()
        active_projects = [p for p in projects if p.status not in ("completed", "cancelled", "archived")]
        tasks_total = (
            await db.execute(select(func.count(Task.id)).where(Task.organization_id == organization_id))
        ).scalar() or 0
        tasks_completed_period = (
            await db.execute(select(func.count(Task.id)).where(
                Task.organization_id == organization_id,
                Task.status == "completed",
                Task.completed_at >= since,
            ))
        ).scalar() or 0
        tasks_overdue = (
            await db.execute(select(func.count(Task.id)).where(
                Task.organization_id == organization_id,
                Task.due_date.isnot(None),
                Task.due_date < now.date(),
                Task.status.notin_(("completed", "archived")),
            ))
        ).scalar() or 0
        meetings_period = (
            await db.execute(select(func.count(Meeting.id)).where(
                Meeting.organization_id == organization_id,
                Meeting.status == "completed",
                Meeting.end_at >= since,
            ))
        ).scalar() or 0
        employees_active = (
            await db.execute(select(func.count(Employee.id)).where(
                Employee.organization_id == organization_id, Employee.status == "active"
            ))
        ).scalar() or 0
        employees_joined = (
            await db.execute(select(func.count(Employee.id)).where(
                Employee.organization_id == organization_id, Employee.created_at >= since
            ))
        ).scalar() or 0
        knowledge_published = (
            await db.execute(select(func.count(Document.id)).where(
                Document.organization_id == organization_id,
                Document.status == "published",
                Document.created_at >= since,
            ))
        ).scalar() or 0
        posts_period = (
            await db.execute(select(func.count(CommunityPost.id)).where(
                CommunityPost.organization_id == organization_id, CommunityPost.created_at >= since
            ))
        ).scalar() or 0
        ideas_period = (
            await db.execute(select(func.count(InnovationIdea.id)).where(
                InnovationIdea.organization_id == organization_id, InnovationIdea.created_at >= since
            ))
        ).scalar() or 0
        recognitions_period = (
            await db.execute(select(func.count(Recognition.id)).where(
                Recognition.organization_id == organization_id, Recognition.created_at >= since
            ))
        ).scalar() or 0
        decisions_period = (
            await db.execute(select(func.count(Decision.id)).where(
                Decision.organization_id == organization_id, Decision.created_at >= since
            ))
        ).scalar() or 0
        open_risks = (
            await db.execute(select(func.count(Risk.id)).where(
                Risk.organization_id == organization_id, Risk.status != "closed"
            ))
        ).scalar() or 0

        strategic_risks = (await db.execute(
            select(StrategicRisk).where(
                StrategicRisk.organization_id == organization_id, StrategicRisk.status == "open"
            ).order_by(StrategicRisk.score.desc())
        )).scalars().all()
        recommendations = (await db.execute(
            select(ExecutiveRecommendation).where(
                ExecutiveRecommendation.organization_id == organization_id,
                ExecutiveRecommendation.status == "active",
            ).order_by(ExecutiveRecommendation.confidence.desc())
        )).scalars().all()
        predictions = (await db.execute(
            select(AIPrediction).where(
                AIPrediction.organization_id == organization_id,
                AIPrediction.subject_type == "organization",
            ).order_by(AIPrediction.score.desc())
        )).scalars().all()
        goals = (await db.execute(
            select(Goal).where(Goal.organization_id == organization_id)
        )).scalars().all()

        section_department = ""
        dept_health_rows = []
        if report_type == "department":
            departments = (await db.execute(
                select(Department).where(Department.organization_id == organization_id)
            )).scalars().all()
            for d in departments:
                d_emp = (
                    await db.execute(select(func.count(Employee.id)).where(
                        Employee.organization_id == organization_id,
                        Employee.department_id == d.id,
                        Employee.status == "active",
                    ))
                ).scalar() or 0
                dept_health_rows.append(f"- **{d.name}**: {d_emp} active employees")
            section_department = "\n".join(dept_health_rows)

        lines: list[str] = []
        title = f"{report_type.title()} Report — {org_name}"
        lines.append(f"# {title}")
        lines.append(f"_Generated {now.strftime('%Y-%m-%d %H:%M UTC')} — period: {since.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}_")
        lines.append("")
        lines.append("## 1. Executive Summary")
        completion_rate = (tasks_completed_period / max(1, tasks_total)) * 100
        summary = (
            f"{org_name} has {len(active_projects)} active project(s), {employees_active} active "
            f"employee(s) and {tasks_total} task(s) on record. During this period the organization "
            f"completed {tasks_completed_period} task(s) ({completion_rate:.0f}% of all tasks), held "
            f"{meetings_period} completed meeting(s), published {knowledge_published} knowledge item(s), "
            f"made {decisions_period} decision(s) and welcomed {employees_joined} new employee(s). "
            f"{len(strategic_risks)} strategic risk(s) are currently open."
        )
        lines.append(summary)
        lines.append("")
        lines.append("## 2. Work Delivery")
        lines.append(f"- Tasks completed this period: **{tasks_completed_period}**")
        lines.append(f"- Tasks overdue: **{tasks_overdue}**")
        lines.append(f"- Projects active: **{len(active_projects)}** / total {len(projects)}")
        if active_projects:
            lines.append("- Active projects: " + ", ".join(p.name for p in active_projects[:8]))
        lines.append("")
        lines.append("## 3. Meetings & Collaboration")
        lines.append(f"- Meetings completed: **{meetings_period}**")
        lines.append(f"- Community posts: **{posts_period}**")
        lines.append(f"- Recognitions: **{recognitions_period}**")
        lines.append("")
        lines.append("## 4. Knowledge & Decisions")
        lines.append(f"- Knowledge published: **{knowledge_published}**")
        lines.append(f"- Decisions made: **{decisions_period}**")
        lines.append("")
        lines.append("## 5. Innovation & Learning")
        lines.append(f"- Innovation ideas: **{ideas_period}**")
        lines.append("")
        lines.append("## 6. Strategic Risks")
        if strategic_risks:
            for r in strategic_risks[:8]:
                lines.append(f"- [{r.level.upper()}] {r.title} (score {r.score:.2f})")
        else:
            lines.append("- No open strategic risks detected.")
        lines.append("")
        lines.append("## 7. AI Recommendations")
        if recommendations:
            for rec in recommendations[:8]:
                lines.append(f"- **{rec.title}** (confidence {rec.confidence:.0%}, impact {rec.impact})")
                lines.append(f"  - Why: {rec.rationale}")
                lines.append(f"  - Expected outcome: {rec.expected_outcome}")
        else:
            lines.append("- No active recommendations.")
        lines.append("")
        lines.append("## 8. Predictions")
        if predictions:
            for p in predictions[:8]:
                lines.append(f"- [{p.level.upper()}] {p.metric.replace('_', ' ').title()} ({p.score:.0%}) — {p.rationale}")
        else:
            lines.append("- No predictions available yet.")
        lines.append("")
        lines.append("## 9. Strategic Goals")
        if goals:
            for g in goals[:8]:
                lines.append(f"- {g.name}: {g.progress:.0f}% ({g.status})")
        else:
            lines.append("- No goals tracked.")
        lines.append("")
        lines.append("## 10. Risks & Compliance")
        lines.append(f"- Open project risks: **{open_risks}**")
        if report_type == "department" and section_department:
            lines.append("")
            lines.append("## 11. Department Overview")
            lines.append(section_department)

        content = "\n".join(lines)

        payload = {
            "organization_id": organization_id,
            "report_type": report_type,
            "title": title,
            "content": content,
            "period_start": since.strftime("%Y-%m-%d"),
            "period_end": now.strftime("%Y-%m-%d"),
            "stats": {
                "active_projects": len(active_projects),
                "tasks_completed": tasks_completed_period,
                "tasks_overdue": tasks_overdue,
                "meetings": meetings_period,
                "knowledge_published": knowledge_published,
                "decisions": decisions_period,
                "employees_active": employees_active,
                "employees_joined": employees_joined,
                "posts": posts_period,
                "ideas": ideas_period,
                "recognitions": recognitions_period,
                "open_risks": open_risks,
                "open_strategic_risks": len(strategic_risks),
                "recommendations": len(recommendations),
                "predictions": len(predictions),
            },
        }

        if persist:
            db.add(ExecutiveReport(
                organization_id=organization_id,
                user_id=user_id,
                report_type=report_type,
                title=title,
                content=content,
                period_start=payload["period_start"],
                period_end=payload["period_end"],
                export_format="markdown",
                status="generated",
            ))
        return payload

    async def list(self, db: AsyncSession, *, organization_id: str, limit: int = 50) -> dict[str, Any]:
        rows = (await db.execute(
            select(ExecutiveReport).where(ExecutiveReport.organization_id == organization_id)
            .order_by(ExecutiveReport.created_at.desc()).limit(limit)
        )).scalars().all()
        return {
            "total": len(rows),
            "reports": [
                {
                    "id": r.id,
                    "report_type": r.report_type,
                    "title": r.title,
                    "period_start": r.period_start,
                    "period_end": r.period_end,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }


reporting_service = ReportingService()
