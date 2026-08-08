"""Community analytics service (Phase 5.16)."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.communication import (
    Announcement,
    Community,
    CommunityEvent,
    CommunityMember,
    CommunityPost,
    ForumReply,
    ForumThread,
    InnovationIdea,
    Poll,
    PostComment,
    PostReaction,
    Recognition,
)
from app.models.employee import Employee


class AnalyticsService:
    async def overview(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        community_count = (
            await db.execute(select(func.count(Community.id)).where(Community.organization_id == organization_id))
        ).scalar_one()
        member_count = (
            await db.execute(select(func.count(CommunityMember.id)).where(CommunityMember.organization_id == organization_id))
        ).scalar_one()
        post_count = (
            await db.execute(select(func.count(CommunityPost.id)).where(CommunityPost.organization_id == organization_id))
        ).scalar_one()
        comment_count = (
            await db.execute(select(func.count(PostComment.id)).where(PostComment.organization_id == organization_id))
        ).scalar_one()
        reaction_count = (
            await db.execute(select(func.count(PostReaction.id)).where(PostReaction.organization_id == organization_id))
        ).scalar_one()
        thread_count = (
            await db.execute(select(func.count(ForumThread.id)).where(ForumThread.organization_id == organization_id))
        ).scalar_one()
        reply_count = (
            await db.execute(select(func.count(ForumReply.id)).where(ForumReply.organization_id == organization_id))
        ).scalar_one()
        announcement_count = (
            await db.execute(select(func.count(Announcement.id)).where(Announcement.organization_id == organization_id))
        ).scalar_one()
        recognition_count = (
            await db.execute(select(func.count(Recognition.id)).where(Recognition.organization_id == organization_id))
        ).scalar_one()
        idea_count = (
            await db.execute(select(func.count(InnovationIdea.id)).where(InnovationIdea.organization_id == organization_id))
        ).scalar_one()
        poll_count = (
            await db.execute(select(func.count(Poll.id)).where(Poll.organization_id == organization_id))
        ).scalar_one()
        event_count = (
            await db.execute(select(func.count(CommunityEvent.id)).where(CommunityEvent.organization_id == organization_id))
        ).scalar_one()
        active_communities = (
            await db.execute(
                select(func.count(func.distinct(CommunityMember.community_id))).where(
                    CommunityMember.organization_id == organization_id
                )
            )
        ).scalar_one()
        return {
            "communities": community_count,
            "members": member_count,
            "active_communities": active_communities,
            "posts": post_count,
            "comments": comment_count,
            "reactions": reaction_count,
            "forum_threads": thread_count,
            "forum_replies": reply_count,
            "announcements": announcement_count,
            "recognitions": recognition_count,
            "ideas": idea_count,
            "polls": poll_count,
            "events": event_count,
        }

    async def top_communities(self, db: AsyncSession, *, organization_id: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(
                    Community.id,
                    Community.name,
                    Community.type,
                    func.count(func.distinct(CommunityMember.id)).label("member_count"),
                    func.count(func.distinct(CommunityPost.id)).label("post_count"),
                )
                .join(CommunityMember, CommunityMember.community_id == Community.id, isouter=True)
                .join(CommunityPost, CommunityPost.community_id == Community.id, isouter=True)
                .where(Community.organization_id == organization_id)
                .group_by(Community.id)
                .order_by(func.count(func.distinct(CommunityMember.id)).desc())
                .limit(min(limit, 50))
            )
        ).all()
        return [
            {
                "community_id": r[0],
                "name": r[1],
                "type": r[2],
                "member_count": r[3] or 0,
                "post_count": r[4] or 0,
            }
            for r in rows
        ]

    async def top_contributors(self, db: AsyncSession, *, organization_id: str, limit: int = 10) -> list[dict[str, Any]]:
        post_rows = (
            await db.execute(
                select(CommunityPost.author_id, func.count(CommunityPost.id))
                .where(CommunityPost.organization_id == organization_id)
                .group_by(CommunityPost.author_id)
            )
        ).all()
        thread_rows = (
            await db.execute(
                select(ForumThread.author_id, func.count(ForumThread.id))
                .where(ForumThread.organization_id == organization_id)
                .group_by(ForumThread.author_id)
            )
        ).all()
        reply_rows = (
            await db.execute(
                select(ForumReply.author_id, func.count(ForumReply.id))
                .where(ForumReply.organization_id == organization_id)
                .group_by(ForumReply.author_id)
            )
        ).all()
        comment_rows = (
            await db.execute(
                select(PostComment.author_id, func.count(PostComment.id))
                .where(PostComment.organization_id == organization_id)
                .group_by(PostComment.author_id)
            )
        ).all()
        scores: dict[str, int] = {}
        for rows, weight in ((post_rows, 3), (thread_rows, 5), (reply_rows, 2), (comment_rows, 1)):
            for employee_id, count in rows:
                scores[employee_id] = scores.get(employee_id, 0) + (count or 0) * weight
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: min(limit, 50)]
        employees = (
            await db.execute(
                select(Employee).where(Employee.organization_id == organization_id, Employee.id.in_([e for e, _ in ranked]))
            )
        ).scalars().all() if ranked else []
        by_id = {e.id: e for e in employees}
        return [
            {
                "employee_id": employee_id,
                "name": by_id[employee_id].display_name if employee_id in by_id else "Former member",
                "score": score,
            }
            for employee_id, score in ranked
        ]

    async def activity_trend(
        self, db: AsyncSession, *, organization_id: str, days: int = 30
    ) -> list[dict[str, Any]]:
        from datetime import timedelta

        now = datetime.utcnow()
        since = now - timedelta(days=days)
        trend: dict[str, dict[str, int]] = {}
        source = [
            (CommunityPost, "posts"),
            (PostComment, "comments"),
            (PostReaction, "reactions"),
            (ForumThread, "threads"),
            (ForumReply, "replies"),
            (Announcement, "announcements"),
            (Recognition, "recognitions"),
            (Poll, "polls"),
        ]
        for model, label in source:
            rows = (
                await db.execute(
                    select(model.created_at).where(
                        model.organization_id == organization_id,
                        model.created_at >= since,
                        model.created_at <= now,
                    )
                )
            ).scalars().all()
            for value in rows:
                key = (value or now).strftime("%Y-%m-%d")
                entry = trend.setdefault(key, {})
                entry[label] = entry.get(label, 0) + 1
        result = sorted(trend.items())
        return [
            {"date": date_str, "posts": v.get("posts", 0), "comments": v.get("comments", 0), "reactions": v.get("reactions", 0), "threads": v.get("threads", 0), "replies": v.get("replies", 0), "announcements": v.get("announcements", 0), "recognitions": v.get("recognitions", 0), "polls": v.get("polls", 0)}
            for date_str, v in result
        ]


analytics_service = AnalyticsService()
