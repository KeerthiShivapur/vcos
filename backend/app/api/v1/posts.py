"""Posts, comments, reactions and bookmarks API (Phase 5.2-5.4)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.communication.post_service import post_service
from app.communication.presenters import _names, present_comment, present_post
from app.communication.community_service import community_service
from app.db.database import get_db
from app.models.communication import PostBookmark
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.communication import CommentCreate, CommentUpdate, PostCreate, PostUpdate, ReactionPayload

router = APIRouter(prefix="/posts", tags=["Posts"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


async def _require_post(db: AsyncSession, org: Organization, post_id: str):
    post = await post_service.get(db, organization_id=org.id, post_id=post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    return post


@router.get("/feed", response_model=list[dict])
async def feed(
    community_id: Optional[str] = None,
    mine_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    posts = await post_service.list_feed(
        db,
        organization_id=org.id,
        employee_id=(actor.id if actor and mine_only else (actor.id if actor else None)),
        community_id=community_id,
        limit=min(limit, 200),
        offset=offset,
    )
    return await _present_posts(db, org, user, posts)


async def _present_posts(db: AsyncSession, org: Organization, user: User, posts):
    from app.communication.presenters import _community_names

    actor = await _actor(db, org, user)
    names = await _names(db, [p.author_id for p in posts if p.author_id])
    communities = await _community_names(db, [p.community_id for p in posts])
    bookmarked: set[str] = set()
    if actor:
        rows = (
            await db.execute(
                select(PostBookmark.post_id).where(
                    PostBookmark.organization_id == org.id,
                    PostBookmark.employee_id == actor.id,
                )
            )
        ).scalars().all()
        bookmarked = set(rows)
    result = []
    for post in posts:
        my_reaction = None
        if actor:
            my_reaction = await post_service.my_reaction(
                db, organization_id=org.id, target_type="post", target_id=post.id, employee_id=actor.id
            )
        result.append(
            await present_post(
                post,
                community_name=communities.get(post.community_id),
                author_name=names.get(post.author_id) if post.author_id else None,
                is_bookmarked=post.id in bookmarked,
                my_reaction=my_reaction,
            )
        )
    return result


@router.post("", response_model=dict, status_code=201)
async def create_post(
    payload: PostCreate,
    request: Request,
    community_id: str = Query(..., description="Community to post into"),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    community = await community_service.get(db, organization_id=org.id, community_id=community_id)
    if community is None:
        raise HTTPException(404, "Community not found")
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    post = await post_service.create(
        db, organization_id=org.id, community_id=community_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    presented = await _present_posts(db, org, user, [post])
    return presented[0]


@router.get("/{post_id}", response_model=dict)
async def get_post(
    post_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_post(db, org, post_id)
    post = await post_service.get(db, organization_id=org.id, post_id=post_id)
    presented = await _present_posts(db, org, user, [post])
    return presented[0]


@router.patch("/{post_id}", response_model=dict)
async def update_post(
    post_id: str,
    payload: PostUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    post = await _require_post(db, org, post_id)
    actor = await _actor(db, org, user)
    is_author = actor is not None and post.author_id == actor.id
    if not is_author:
        raise HTTPException(403, "Only the author can edit this post")
    post = await post_service.update(
        db, organization_id=org.id, post_id=post_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    presented = await _present_posts(db, org, user, [post])
    return presented[0]


@router.delete("/{post_id}", response_model=Message)
async def delete_post(
    post_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    post = await _require_post(db, org, post_id)
    actor = await _actor(db, org, user)
    is_author = actor is not None and post.author_id == actor.id
    if not is_author:
        raise HTTPException(403, "Only the author can delete this post")
    await post_service.delete(
        db, organization_id=org.id, post_id=post_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Post deleted")


@router.post("/{post_id}/pin", response_model=dict)
async def pin_post(
    post_id: str,
    request: Request,
    pinned: bool = Query(True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_post(db, org, post_id)
    post = await post_service.pin(db, organization_id=org.id, post_id=post_id, pinned=pinned)
    await db.commit()
    return {"pinned": post.pinned}


@router.post("/{post_id}/bookmark", response_model=dict)
async def toggle_bookmark(
    post_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_post(db, org, post_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    result = await post_service.toggle_bookmark(db, organization_id=org.id, post_id=post_id, actor=actor)
    await db.commit()
    return result


@router.post("/{post_id}/reactions", response_model=dict)
async def toggle_post_reaction(
    post_id: str,
    payload: ReactionPayload,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_post(db, org, post_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    try:
        result = await post_service.toggle_reaction(
            db, organization_id=org.id, target_type="post", target_id=post_id, emoji=payload.emoji, actor=actor
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return result


@router.get("/{post_id}/reactions", response_model=list[dict])
async def list_post_reactions(
    post_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_post(db, org, post_id)
    return await post_service.reactions(db, organization_id=org.id, target_type="post", target_id=post_id)


# ------------------------------------------------------------- comments

@router.get("/{post_id}/comments", response_model=list[dict])
async def list_comments(
    post_id: str,
    limit: int = 200,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_post(db, org, post_id)
    comments = await post_service.comments(
        db, organization_id=org.id, post_id=post_id, limit=min(limit, 500), offset=offset
    )
    actor = await _actor(db, org, user)
    names = await _names(db, [c.author_id for c in comments if c.author_id])
    result = []
    for comment in comments:
        my_reaction = None
        if actor:
            my_reaction = await post_service.my_reaction(
                db, organization_id=org.id, target_type="comment", target_id=comment.id, employee_id=actor.id
            )
        result.append(
            await present_comment(
                comment, author_name=names.get(comment.author_id) if comment.author_id else None, my_reaction=my_reaction
            )
        )
    return result


@router.post("/{post_id}/comments", response_model=dict, status_code=201)
async def add_comment(
    post_id: str,
    payload: CommentCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_post(db, org, post_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    comment = await post_service.add_comment(
        db, organization_id=org.id, post_id=post_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    names = await _names(db, [comment.author_id])
    return await present_comment(comment, author_name=names.get(comment.author_id) if comment.author_id else None)


@router.patch("/{post_id}/comments/{comment_id}", response_model=dict)
async def update_comment(
    post_id: str,
    comment_id: str,
    payload: CommentUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_post(db, org, post_id)
    actor = await _actor(db, org, user)
    comment = await post_service.get_comment(db, organization_id=org.id, comment_id=comment_id)
    if comment is None:
        raise HTTPException(404, "Comment not found")
    if actor is None or comment.author_id != actor.id:
        raise HTTPException(403, "Only the author can edit this comment")
    comment = await post_service.update_comment(
        db, organization_id=org.id, comment_id=comment_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    names = await _names(db, [comment.author_id])
    return await present_comment(comment, author_name=names.get(comment.author_id) if comment.author_id else None)


@router.delete("/{post_id}/comments/{comment_id}", response_model=Message)
async def delete_comment(
    post_id: str,
    comment_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_post(db, org, post_id)
    actor = await _actor(db, org, user)
    comment = await post_service.get_comment(db, organization_id=org.id, comment_id=comment_id)
    if comment is None:
        raise HTTPException(404, "Comment not found")
    if actor is None or comment.author_id != actor.id:
        raise HTTPException(403, "Only the author can delete this comment")
    await post_service.delete_comment(
        db, organization_id=org.id, comment_id=comment_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Comment deleted")


@router.post("/{post_id}/comments/{comment_id}/reactions", response_model=dict)
async def toggle_comment_reaction(
    post_id: str,
    comment_id: str,
    payload: ReactionPayload,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_post(db, org, post_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    try:
        result = await post_service.toggle_reaction(
            db, organization_id=org.id, target_type="comment", target_id=comment_id, emoji=payload.emoji, actor=actor
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return result
