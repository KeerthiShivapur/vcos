"""Phase 9.14 — Autonomous insights engine (daily briefs + notifications).

Every morning (or on demand) the engine assembles:

    Executive brief  — health, risks, achievements, knowledge growth, blocked
                       work, deadlines, community activity, hiring signals,
                       strategic recommendations
    Employee brief   — today's priorities, meetings, tasks, recommended docs,
                       learning suggestions, pending approvals

Briefs are stored (DailyBrief) and a digest Notification is created so users
see them in their notification tray without asking for anything.
"""

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.approval import Approval
from app.models.executive import StrategicRisk
from app.models.intelligence import DailyBrief, KnowledgeInsight, PatternDetection
from app.models.employee import Employee
from app.models.notification import Notification
from app.models.task import Task
from app.models.user import User

logger = logging.getLogger("vcos.intelligence.insights")


class InsightsEngine:
    async def generate_executive_brief(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        """Assemble the organization-wide executive brief (one per day)."""
        today = utcnow().date()
        existing = (
            await db.execute(
                select(DailyBrief).where(
                    DailyBrief.organization_id == organization_id,
                    DailyBrief.brief_type == "executive",
                    DailyBrief.brief_date == today,
                )
            )
        ).scalar_one_or_none()

        sections: list[dict[str, Any]] = []

        # --- organizational health
        from app.executive.health_engine import health_engine

        try:
            health = await health_engine.compute_company_health(db, organization_id=organization_id, persist=False)
            sections.append({
                "title": "Company health",
                "items": [
                    f"{health.get('status', 'n/a').replace('_', ' ').title()} — {health.get('score', 0):.0f}/100",
                ],
                "severity": "neutral",
            })
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("executive brief health failed: %s", exc)

        # --- open strategic risks
        risks = list(
            (
                await db.execute(
                    select(StrategicRisk).where(
                        StrategicRisk.organization_id == organization_id,
                        StrategicRisk.status == "open",
                    ).order_by(StrategicRisk.score.desc()).limit(5)
                )
            ).scalars().all()
        )
        if risks:
            sections.append({
                "title": "Open risks",
                "items": [f"[{r.level}] {r.title}" for r in risks],
                "severity": "warning",
            })

        # --- blocked work
        blocked = (
            await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.status == "blocked",
                ).order_by(Task.updated_at.desc()).limit(8)
            )
        ).scalars().all()
        if blocked:
            sections.append({
                "title": "Blocked work",
                "items": [t.title[:140] for t in blocked],
                "severity": "warning",
            })

        # --- upcoming deadlines (next 7 days)
        upcoming = (
            await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.status.in_(("todo", "in_progress", "review")),
                    Task.due_date.isnot(None),
                    Task.due_date <= today + timedelta(days=7),
                    Task.due_date >= today,
                ).order_by(Task.due_date.asc()).limit(8)
            )
        ).scalars().all()
        if upcoming:
            sections.append({
                "title": "Upcoming deadlines",
                "items": [f"{t.due_date.isoformat()}: {t.title[:120]}" for t in upcoming],
                "severity": "info",
            })

        # --- knowledge growth (recent documents)
        from app.models.knowledge import Document

        doc_count = (
            await db.execute(
                select(func.count(Document.id)).where(
                    Document.organization_id == organization_id,
                    Document.created_at >= utcnow() - timedelta(days=7),
                )
            )
        ).scalar() or 0
        sections.append({
            "title": "Knowledge growth",
            "items": [f"{doc_count} documents created in the last 7 days"],
            "severity": "neutral",
        })

        # --- knowledge insights
        insights = list(
            (
                await db.execute(
                    select(KnowledgeInsight).where(
                        KnowledgeInsight.organization_id == organization_id,
                        KnowledgeInsight.status == "open",
                    ).order_by(KnowledgeInsight.confidence.desc()).limit(5)
                )
            ).scalars().all()
        )
        if insights:
            sections.append({
                "title": "Knowledge health",
                "items": [i.title[:140] for i in insights],
                "severity": "info",
            })

        # --- patterns
        patterns = list(
            (
                await db.execute(
                    select(PatternDetection).where(
                        PatternDetection.organization_id == organization_id,
                        PatternDetection.status == "open",
                    ).order_by(PatternDetection.count.desc()).limit(5)
                )
            ).scalars().all()
        )
        if patterns:
            sections.append({
                "title": "Repeated patterns",
                "items": [p.title[:140] for p in patterns],
                "severity": "info",
            })

        if existing is None:
            brief = DailyBrief(
                organization_id=organization_id,
                brief_type="executive",
                recipient_id=None,
                title="Executive Daily Brief",
                sections_json=json.dumps(sections, default=str),
                brief_date=today,
            )
            db.add(brief)
            await db.flush()
        else:
            existing.sections_json = json.dumps(sections, default=str)
            brief = existing

        await self._notify_executives(db, organization_id, brief)
        return self._payload(brief)

    async def generate_employee_brief(self, db: AsyncSession, *, organization_id: str, user_id: str) -> dict[str, Any]:
        """Personal morning brief for one employee."""
        today = utcnow().date()
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        name = (employee.display_name or employee.first_name) if employee else "You"
        sections: list[dict[str, Any]] = []

        # --- today's tasks
        my_tasks = list(
            (
                await db.execute(
                    select(Task).where(
                        Task.organization_id == organization_id,
                        Task.assignee_id == (employee.id if employee else "none"),
                        Task.status.in_(("todo", "in_progress", "review")),
                    ).order_by(Task.due_date.asc()).limit(10)
                )
            ).scalars().all()
        )
        if my_tasks:
            sections.append({
                "title": "Your open tasks",
                "items": [
                    f"{'[DUE ' + t.due_date.isoformat() + '] ' if t.due_date else ''}{t.title[:120]}" for t in my_tasks
                ],
                "severity": "info",
            })
        else:
            sections.append({"title": "Your open tasks", "items": ["No open tasks — a good day to plan ahead."], "severity": "neutral"})

        # --- meetings today
        from app.models.calendar import CalendarEvent

        meetings = list(
            (
                await db.execute(
                    select(CalendarEvent).where(
                        CalendarEvent.organization_id == organization_id,
                        CalendarEvent.created_by == (employee.id if employee else "none"),
                        CalendarEvent.start_at >= utcnow(),
                        CalendarEvent.start_at < utcnow() + timedelta(hours=24),
                    ).order_by(CalendarEvent.start_at.asc()).limit(8)
                )
            ).scalars().all()
        )
        if meetings:
            sections.append({
                "title": "Meetings today",
                "items": [m.title[:120] for m in meetings],
                "severity": "info",
            })

        # --- pending approvals I need to act on
        pending = (
            await db.execute(
                select(Approval).where(
                    Approval.organization_id == organization_id,
                    Approval.status == "pending",
                    Approval.approver_id == (employee.id if employee else "none"),
                ).order_by(Approval.created_at.asc()).limit(8)
            )
        ).scalars().all()
        if pending:
            sections.append({
                "title": "Awaiting your approval",
                "items": [a.title[:120] for a in pending],
                "severity": "warning",
            })

        # --- personal recommendations
        from app.intelligence.recommendation_engine import recommendation_engine

        try:
            feed = await recommendation_engine.feed(db, organization_id=organization_id, user_id=user_id, limit=5)
            if feed:
                sections.append({
                    "title": "Recommended for you",
                    "items": [i["title"][:120] for i in feed],
                    "severity": "neutral",
                })
        except Exception as exc:  # pragma: no cover
            logger.debug("employee brief recommendations failed: %s", exc)

        existing = (
            await db.execute(
                select(DailyBrief).where(
                    DailyBrief.organization_id == organization_id,
                    DailyBrief.brief_type == "employee",
                    DailyBrief.recipient_id == user_id,
                    DailyBrief.brief_date == today,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            brief = DailyBrief(
                organization_id=organization_id,
                brief_type="employee",
                recipient_id=user_id,
                title=f"Good morning, {name}",
                sections_json=json.dumps(sections, default=str),
                brief_date=today,
            )
            db.add(brief)
            await db.flush()
        else:
            existing.sections_json = json.dumps(sections, default=str)
            brief = existing

        await self._notify(db, organization_id, user_id, brief)
        return self._payload(brief)

    # ------------------------------------------------------------------ notifications

    async def _notify_executives(self, db: AsyncSession, organization_id: str, brief: DailyBrief) -> None:
        from app.models.role import Role, UserRole

        rows = (
            await db.execute(
                select(User.id)
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(
                    User.organization_id == organization_id,
                    User.status == "active",
                    Role.code.in_(("ceo", "admin", "manager")),
                )
            )
        ).scalars().all()
        if not rows:
            rows = (
                await db.execute(
                    select(User.id).where(
                        User.organization_id == organization_id,
                        User.status == "active",
                    )
                )
            ).scalars().all()
        for user_id in set(rows):
            await self._notify(db, organization_id, user_id, brief, high=True)

    async def _notify(self, db: AsyncSession, organization_id: str, user_id: str, brief: DailyBrief, high: bool = False) -> None:
        try:
            db.add(
                Notification(
                    organization_id=organization_id,
                    recipient_id=user_id,
                    actor_id=None,
                    type="intelligence",
                    title=brief.title,
                    body="Your daily brief is ready — review today's priorities and insights.",
                    priority="high" if high else "normal",
                    channel="in_app",
                    link="/intelligence",
                    entity_type="daily_brief",
                    entity_id=brief.id,
                    metadata_json=json.dumps({"brief_type": brief.brief_type, "brief_date": str(brief.brief_date)}),
                )
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("brief notification failed: %s", exc)

    # ------------------------------------------------------------------ queries

    def _payload(self, brief: DailyBrief) -> dict[str, Any]:
        return {
            "id": brief.id,
            "brief_type": brief.brief_type,
            "recipient_id": brief.recipient_id,
            "title": brief.title,
            "sections": brief.sections,
            "brief_date": brief.brief_date.isoformat() if brief.brief_date else None,
        }

    async def latest_brief(
        self, db: AsyncSession, *, organization_id: str,
        brief_type: Optional[str] = None, recipient_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        filters = [DailyBrief.organization_id == organization_id]
        if brief_type:
            filters.append(DailyBrief.brief_type == brief_type)
        if recipient_id:
            filters.append(DailyBrief.recipient_id == recipient_id)
        row = (
            await db.execute(
                select(DailyBrief).where(*filters).order_by(DailyBrief.brief_date.desc(), DailyBrief.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        return self._payload(row) if row else None

    async def list_briefs(
        self, db: AsyncSession, *, organization_id: str, limit: int = 20,
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(DailyBrief).where(DailyBrief.organization_id == organization_id)
                .order_by(DailyBrief.brief_date.desc()).limit(limit)
            )
        ).scalars().all()
        return [self._payload(r) for r in rows]


insights_engine = InsightsEngine()
