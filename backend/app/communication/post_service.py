"""Post service — posts, comments, reactions, bookmarks (Phase 5.2-5.4)."""

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.community_service import community_service
from app.communication.events import emit_and_audit, notify_community_members, notify_mentions
from app.models.communication import CommunityPost, PostBookmark, PostComment, PostReaction
from app.models.employee import Employee

REACTION_EMOJIS = {"helpful", "congrats", "great_idea", "excellent", "appreciate", "support", "love", "insightful"}


class PostService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, community_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> CommunityPost:
        post = CommunityPost(
            organization_id=organization_id,
            community_id=community_id,
            author_id=actor.id,
            title=payload.get("title"),
            content=payload.get("content"),
            attachments=payload.get("attachments"),
            visibility=payload.get("visibility", "members"),
            status=payload.get("status", "published"),
            pinned=payload.get("pinned", False),
            scheduled_at=payload.get("scheduled_at"),
        )
        db.add(post)
        await db.flush()
        community = await community_service.get(db, organization_id=organization_id, community_id=community_id)
        if community is not None:
            community.post_count = (community.post_count or 0) + 1
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="community.posted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"post_id": post.id, "community_id": community_id},
            resource_type="post",
            resource_id=post.id,
        )
        if post.status == "published":
            await notify_community_members(
                db,
                organization_id=organization_id,
                community_id=community_id,
                type="community.activity",
                title=f"New post in {community.name if community else 'community'}",
                body=post.title or (post.content or "")[:160],
                actor_id=actor.id,
                link=f"/posts/{post.id}",
                entity_type="post",
                entity_id=post.id,
            )
            await notify_mentions(
                db,
                organization_id=organization_id,
                text=post.content,
                type="mention",
                title="You were mentioned in a post",
                body=post.title or (post.content or "")[:120],
                actor_id=actor.id,
                link=f"/posts/{post.id}",
                entity_type="post",
                entity_id=post.id,
            )
        return post

    async def get(self, db: AsyncSession, *, organization_id: str, post_id: str) -> Optional[CommunityPost]:
        return (
            await db.execute(
                select(CommunityPost).where(
                    CommunityPost.organization_id == organization_id,
                    CommunityPost.id == post_id,
                )
            )
        ).scalar_one_or_none()

    async def list_by_community(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        community_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CommunityPost]:
        filters = [CommunityPost.organization_id == organization_id, CommunityPost.community_id == community_id]
        if status:
            filters.append(CommunityPost.status == status)
        return list(
            (
                await db.execute(
                    select(CommunityPost)
                    .where(*filters)
                    .order_by(CommunityPost.pinned.desc(), CommunityPost.created_at.desc())
                    .limit(min(limit, 200))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def list_feed(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: Optional[str] = None,
        community_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CommunityPost]:
        filters = [CommunityPost.organization_id == organization_id, CommunityPost.status == "published"]
        if community_id:
            filters.append(CommunityPost.community_id == community_id)
        elif employee_id:
            member_communities = select(CommunityPost.community_id).where(
                CommunityPost.organization_id == organization_id
            )
            from app.models.communication import CommunityMember

            member_communities = select(CommunityMember.community_id).where(
                CommunityMember.organization_id == organization_id,
                CommunityMember.employee_id == employee_id,
            )
            filters.append(CommunityPost.community_id.in_(member_communities))
        return list(
            (
                await db.execute(
                    select(CommunityPost)
                    .where(*filters)
                    .order_by(CommunityPost.pinned.desc(), CommunityPost.created_at.desc())
                    .limit(min(limit, 200))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def update(
        self, db: AsyncSession, *, organization_id: str, post_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Optional[CommunityPost]:
        post = await self.get(db, organization_id=organization_id, post_id=post_id)
        if post is None:
            return None
        for key, value in payload.items():
            if value is not None and hasattr(post, key):
                setattr(post, key, value)
        post.edited_at = post.updated_at
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="community.post_updated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"post_id": post_id},
            resource_type="post",
            resource_id=post_id,
        )
        return post

    async def delete(
        self, db: AsyncSession, *, organization_id: str, post_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        post = await self.get(db, organization_id=organization_id, post_id=post_id)
        if post is None:
            return False
        await db.delete(post)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="community.post_deleted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"post_id": post_id},
            resource_type="post",
            resource_id=post_id,
        )
        return True

    async def pin(self, db: AsyncSession, *, organization_id: str, post_id: str, pinned: bool) -> Optional[CommunityPost]:
        post = await self.get(db, organization_id=organization_id, post_id=post_id)
        if post is None:
            return None
        post.pinned = pinned
        return post

    # ------------------------------------------------------------- bookmarks

    async def toggle_bookmark(
        self, db: AsyncSession, *, organization_id: str, post_id: str, actor: Employee
    ) -> dict[str, Any]:
        post = await self.get(db, organization_id=organization_id, post_id=post_id)
        if post is None:
            raise ValueError("Post not found")
        row = (
            await db.execute(
                select(PostBookmark).where(
                    PostBookmark.organization_id == organization_id,
                    PostBookmark.post_id == post_id,
                    PostBookmark.employee_id == actor.id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(PostBookmark(organization_id=organization_id, post_id=post_id, employee_id=actor.id))
            post.bookmark_count = (post.bookmark_count or 0) + 1
            bookmarked = True
        else:
            await db.delete(row)
            post.bookmark_count = max(0, (post.bookmark_count or 1) - 1)
            bookmarked = False
        return {"bookmarked": bookmarked, "bookmark_count": post.bookmark_count}

    async def bookmark_count(self, db: AsyncSession, *, organization_id: str, post_id: str) -> int:
        return (
            await db.execute(
                select(func.count(PostBookmark.id)).where(
                    PostBookmark.organization_id == organization_id,
                    PostBookmark.post_id == post_id,
                )
            )
        ).scalar_one()

    # ------------------------------------------------------------- comments

    async def add_comment(
        self, db: AsyncSession, *, organization_id: str, post_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> PostComment:
        comment = PostComment(
            organization_id=organization_id,
            post_id=post_id,
            parent_id=payload.get("parent_id"),
            author_id=actor.id,
            content=payload["content"],
            is_resolution=payload.get("is_resolution", False),
        )
        db.add(comment)
        post = await self.get(db, organization_id=organization_id, post_id=post_id)
        if post is not None:
            post.comment_count = (post.comment_count or 0) + 1
        await db.flush()
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="community.commented",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"post_id": post_id, "comment_id": comment.id},
            resource_type="comment",
            resource_id=comment.id,
        )
        if post is not None:
            await notify_community_members(
                db,
                organization_id=organization_id,
                community_id=post.community_id,
                type="community.activity",
                title="New comment on a post",
                body=comment.content[:160],
                actor_id=actor.id,
                link=f"/posts/{post_id}",
                entity_type="post",
                entity_id=post_id,
            )
            await notify_mentions(
                db,
                organization_id=organization_id,
                text=comment.content,
                type="mention",
                title="You were mentioned in a comment",
                body=comment.content[:120],
                actor_id=actor.id,
                link=f"/posts/{post_id}",
                entity_type="post",
                entity_id=post_id,
            )
        return comment

    async def update_comment(
        self, db: AsyncSession, *, organization_id: str, comment_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Optional[PostComment]:
        comment = await self.get_comment(db, organization_id=organization_id, comment_id=comment_id)
        if comment is None:
            return None
        if "content" in payload:
            comment.content = payload["content"]
            comment.edited = True
        if "is_resolution" in payload:
            comment.is_resolution = payload["is_resolution"]
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="community.comment_updated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"comment_id": comment_id},
            resource_type="comment",
            resource_id=comment_id,
        )
        return comment

    async def delete_comment(
        self, db: AsyncSession, *, organization_id: str, comment_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        comment = await self.get_comment(db, organization_id=organization_id, comment_id=comment_id)
        if comment is None:
            return False
        post = await self.get(db, organization_id=organization_id, post_id=comment.post_id)
        if post is not None:
            post.comment_count = max(0, (post.comment_count or 1) - 1)
        await db.delete(comment)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="community.comment_deleted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"comment_id": comment_id},
            resource_type="comment",
            resource_id=comment_id,
        )
        return True

    async def get_comment(self, db: AsyncSession, *, organization_id: str, comment_id: str) -> Optional[PostComment]:
        return (
            await db.execute(
                select(PostComment).where(
                    PostComment.organization_id == organization_id,
                    PostComment.id == comment_id,
                )
            )
        ).scalar_one_or_none()

    async def comments(
        self, db: AsyncSession, *, organization_id: str, post_id: str, limit: int = 200, offset: int = 0
    ) -> list[PostComment]:
        return list(
            (
                await db.execute(
                    select(PostComment)
                    .where(PostComment.organization_id == organization_id, PostComment.post_id == post_id)
                    .order_by(PostComment.created_at.asc())
                    .limit(min(limit, 500))
                    .offset(offset)
                )
            ).scalars().all()
        )

    # ------------------------------------------------------------- reactions

    async def toggle_reaction(
        self, db: AsyncSession, *, organization_id: str, target_type: str, target_id: str, emoji: str, actor: Employee
    ) -> dict[str, Any]:
        if target_type not in ("post", "comment"):
            raise ValueError("Unknown reaction target")
        if emoji not in REACTION_EMOJIS:
            raise ValueError("Unknown reaction emoji")
        if target_type == "post":
            target = await self.get(db, organization_id=organization_id, post_id=target_id)
        else:
            target = await self.get_comment(db, organization_id=organization_id, comment_id=target_id)
        if target is None:
            raise ValueError("Target not found")
        row = (
            await db.execute(
                select(PostReaction).where(
                    PostReaction.organization_id == organization_id,
                    PostReaction.target_type == target_type,
                    PostReaction.target_id == target_id,
                    PostReaction.employee_id == actor.id,
                )
            )
        ).scalar_one_or_none()
        if row is not None and row.emoji == emoji:
            await db.delete(row)
            if target_type == "post":
                target.reaction_count = max(0, (target.reaction_count or 1) - 1)
            reacted = False
        else:
            if row is not None:
                await db.delete(row)
            db.add(
                PostReaction(
                    organization_id=organization_id,
                    target_type=target_type,
                    target_id=target_id,
                    employee_id=actor.id,
                    emoji=emoji,
                )
            )
            if target_type == "post":
                target.reaction_count = (target.reaction_count or 0) + 1
            reacted = True
        return {"reacted": reacted, "emoji": emoji}

    async def reactions(
        self, db: AsyncSession, *, organization_id: str, target_type: str, target_id: str
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(PostReaction.emoji, func.count(PostReaction.id))
                .where(
                    PostReaction.organization_id == organization_id,
                    PostReaction.target_type == target_type,
                    PostReaction.target_id == target_id,
                )
                .group_by(PostReaction.emoji)
                .order_by(func.count(PostReaction.id).desc())
            )
        ).all()
        return [{"emoji": row[0], "count": row[1]} for row in rows]

    async def my_reaction(
        self, db: AsyncSession, *, organization_id: str, target_type: str, target_id: str, employee_id: str
    ) -> Optional[str]:
        return (
            await db.execute(
                select(PostReaction.emoji).where(
                    PostReaction.organization_id == organization_id,
                    PostReaction.target_type == target_type,
                    PostReaction.target_id == target_id,
                    PostReaction.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()


post_service = PostService()
