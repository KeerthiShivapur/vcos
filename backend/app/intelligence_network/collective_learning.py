"""Collective intelligence engine — the organization learns together.

Aggregates solutions from completed tasks, meeting outcomes and community
discussions into repeatable insights that grow organizational knowledge and
improve future recommendations.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.communication import Community, CommunityPost
from app.models.meeting import MeetingActionItem
from app.models.task import Task


class CollectiveLearning:
    async def run(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        now = utcnow()
        month_ago = now - timedelta(days=30)
        insights: list[dict[str, Any]] = []

        completed_tasks = (
            await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.status.in_(["done", "completed"]),
                    Task.updated_at >= month_ago,
                ).limit(50)
            )
        ).scalars().all()
        for task in completed_tasks:
            summary = getattr(task, "ai_summary", None) or getattr(task, "description", None)
            if summary:
                insights.append({
                    "source": "task",
                    "subject": task.title or task.id,
                    "insight": summary[:200],
                })

        resolved_items = (
            await db.execute(
                select(MeetingActionItem).where(
                    MeetingActionItem.organization_id == organization_id,
                    MeetingActionItem.status.in_(["done", "completed"]),
                ).limit(50)
            )
        ).scalars().all()
        for item in resolved_items:
            title = getattr(item, "title", None) or getattr(item, "action", None)
            if title:
                insights.append({
                    "source": "meeting",
                    "subject": title[:120],
                    "insight": f"Action item completed: {title[:120]}",
                })

        posts = (
            await db.execute(
                select(CommunityPost)
                .join(Community, Community.id == CommunityPost.community_id)
                .where(
                    Community.organization_id == organization_id,
                    CommunityPost.created_at >= month_ago,
                )
                .order_by(CommunityPost.created_at.desc())
                .limit(50)
            )
        ).scalars().all()
        for post in posts:
            body = getattr(post, "content", None) or getattr(post, "body", None)
            if body and len(str(body)) > 120:
                insights.append({
                    "source": "community",
                    "subject": getattr(post, "title", None) or post.id,
                    "insight": str(body)[:200],
                })

        return {
            "collected": len(insights),
            "insights": insights[:30],
            "note": "Insights are folded into AI memory and knowledge by the learning loop.",
        }


collective_learning = CollectiveLearning()
