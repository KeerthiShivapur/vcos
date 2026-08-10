"""Presenters for communication entities — resolve employee/community names inline."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.communication import (
    Announcement,
    Community,
    CommunityEvent,
    CommunityMember,
    CommunityPost,
    Conversation,
    EmployeeBadge,
    EventRegistration,
    ForumReply,
    ForumThread,
    InnovationIdea,
    Message,
    Poll,
    PostComment,
    Recognition,
)
from app.models.employee import Employee


async def _names(db: AsyncSession, employee_ids: list[str]) -> dict[str, str]:
    ids = [eid for eid in set(employee_ids or []) if eid]
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(Employee.id, Employee.display_name, Employee.first_name, Employee.last_name).where(Employee.id.in_(ids))
        )
    ).all()
    return {
        row[0]: row[1] or " ".join(part for part in (row[2], row[3]) if part) or row[0]
        for row in rows
    }


async def _community_names(db: AsyncSession, community_ids: list[str]) -> dict[str, str]:
    ids = [cid for cid in set(community_ids or []) if cid]
    if not ids:
        return {}
    rows = (await db.execute(select(Community.id, Community.name).where(Community.id.in_(ids)))).all()
    return dict(rows)


async def present_community(community: Community, *, is_member: bool = False, my_role: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": community.id,
        "organization_id": community.organization_id,
        "name": community.name,
        "slug": community.slug,
        "description": community.description,
        "type": community.type,
        "visibility": community.visibility,
        "icon": community.icon,
        "banner": community.banner,
        "owner_id": community.owner_id,
        "member_count": community.member_count,
        "post_count": community.post_count,
        "is_featured": community.is_featured,
        "is_archived": community.is_archived,
        "is_member": is_member,
        "my_role": my_role,
        "created_at": community.created_at,
        "updated_at": community.updated_at,
    }


async def present_post(
    post: CommunityPost,
    *,
    community_name: Optional[str] = None,
    author_name: Optional[str] = None,
    is_bookmarked: bool = False,
    my_reaction: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "id": post.id,
        "community_id": post.community_id,
        "community_name": community_name,
        "author_id": post.author_id,
        "author_name": author_name,
        "title": post.title,
        "content": post.content,
        "attachments": post.attachments or [],
        "visibility": post.visibility,
        "status": post.status,
        "pinned": post.pinned,
        "scheduled_at": post.scheduled_at,
        "edited_at": post.edited_at,
        "comment_count": post.comment_count,
        "reaction_count": post.reaction_count,
        "bookmark_count": post.bookmark_count,
        "share_count": post.share_count,
        "is_bookmarked": is_bookmarked,
        "my_reaction": my_reaction,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
    }


async def present_comment(
    comment: PostComment, *, author_name: Optional[str] = None, my_reaction: Optional[str] = None
) -> dict[str, Any]:
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "parent_id": comment.parent_id,
        "author_id": comment.author_id,
        "author_name": author_name,
        "content": comment.content,
        "is_resolution": comment.is_resolution,
        "edited": comment.edited,
        "edited_at": comment.edited_at,
        "reaction_count": comment.reaction_count,
        "my_reaction": my_reaction,
        "created_at": comment.created_at,
        "updated_at": comment.updated_at,
    }


async def present_announcement(
    announcement: Announcement,
    *,
    author_name: Optional[str] = None,
    department_name: Optional[str] = None,
    read_by_me: bool = False,
    acknowledged_by_me: bool = False,
) -> dict[str, Any]:
    return {
        "id": announcement.id,
        "title": announcement.title,
        "body": announcement.body,
        "type": announcement.type,
        "priority": announcement.priority,
        "status": announcement.status,
        "author_id": announcement.author_id,
        "author_name": author_name,
        "department_id": announcement.department_id,
        "department_name": department_name,
        "team_id": announcement.team_id,
        "starts_at": announcement.starts_at,
        "ends_at": announcement.ends_at,
        "pinned": announcement.pinned,
        "acknowledge_required": announcement.acknowledge_required,
        "attachments": announcement.attachments or [],
        "read_count": announcement.read_count,
        "acknowledged_count": announcement.acknowledged_count,
        "read_by_me": read_by_me,
        "acknowledged_by_me": acknowledged_by_me,
        "created_at": announcement.created_at,
        "updated_at": announcement.updated_at,
    }


async def present_thread(
    thread: ForumThread, *, author_name: Optional[str] = None, my_vote: Optional[int] = None
) -> dict[str, Any]:
    return {
        "id": thread.id,
        "category": thread.category,
        "title": thread.title,
        "content": thread.content,
        "author_id": thread.author_id,
        "author_name": author_name,
        "status": thread.status,
        "tags": thread.tags or [],
        "vote_count": thread.vote_count,
        "reply_count": thread.reply_count,
        "view_count": thread.view_count,
        "is_pinned": thread.is_pinned,
        "accepted_reply_id": thread.accepted_reply_id,
        "is_resolved": thread.is_resolved,
        "my_vote": my_vote,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
    }


async def present_reply(
    reply: ForumReply, *, author_name: Optional[str] = None, my_vote: Optional[int] = None
) -> dict[str, Any]:
    return {
        "id": reply.id,
        "thread_id": reply.thread_id,
        "parent_id": reply.parent_id,
        "author_id": reply.author_id,
        "author_name": author_name,
        "content": reply.content,
        "is_accepted": reply.is_accepted,
        "vote_count": reply.vote_count,
        "edited": reply.edited,
        "my_vote": my_vote,
        "created_at": reply.created_at,
        "updated_at": reply.updated_at,
    }


async def present_recognition(
    recognition: Recognition, *, giver_name: Optional[str] = None, recipient_name: Optional[str] = None
) -> dict[str, Any]:
    return {
        "id": recognition.id,
        "giver_id": recognition.giver_id,
        "giver_name": giver_name,
        "recipient_id": recognition.recipient_id,
        "recipient_name": recipient_name,
        "category": recognition.category,
        "message": recognition.message,
        "badge_code": recognition.badge_code,
        "public": recognition.public,
        "created_at": recognition.created_at,
    }


async def present_idea(
    idea: InnovationIdea,
    *,
    author_name: Optional[str] = None,
    project_name: Optional[str] = None,
    voted: bool = False,
) -> dict[str, Any]:
    return {
        "id": idea.id,
        "author_id": idea.author_id,
        "author_name": author_name,
        "title": idea.title,
        "description": idea.description,
        "problem": idea.problem,
        "solution": idea.solution,
        "impact": idea.impact,
        "status": idea.status,
        "vote_count": idea.vote_count,
        "comment_count": idea.comment_count,
        "tags": idea.tags or [],
        "project_id": idea.project_id,
        "project_name": project_name,
        "duplicates_of": idea.duplicates_of,
        "ai_insight": idea.ai_insight,
        "voted": voted,
        "submitted_at": idea.submitted_at,
        "created_at": idea.created_at,
        "updated_at": idea.updated_at,
    }


async def present_poll(
    poll: Poll,
    *,
    creator_name: Optional[str] = None,
    community_name: Optional[str] = None,
    options: Optional[list[dict]] = None,
    voted: bool = False,
    my_choices: Optional[list[str]] = None,
) -> dict[str, Any]:
    return {
        "id": poll.id,
        "title": poll.title,
        "question": poll.question,
        "description": poll.description,
        "community_id": poll.community_id,
        "community_name": community_name,
        "created_by": poll.created_by,
        "creator_name": creator_name,
        "anonymous": poll.anonymous,
        "multiple_choice": poll.multiple_choice,
        "status": poll.status,
        "ends_at": poll.ends_at,
        "vote_count": poll.vote_count,
        "participant_count": poll.participant_count,
        "options": options or [],
        "voted": voted,
        "my_choices": my_choices or [],
        "created_at": poll.created_at,
        "updated_at": poll.updated_at,
    }


async def present_event(
    event: CommunityEvent,
    *,
    creator_name: Optional[str] = None,
    community_name: Optional[str] = None,
    registered: bool = False,
    my_registration: Optional[dict] = None,
) -> dict[str, Any]:
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "type": event.type,
        "community_id": event.community_id,
        "community_name": community_name,
        "created_by": event.created_by,
        "creator_name": creator_name,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "location": event.location,
        "virtual_url": event.virtual_url,
        "capacity": event.capacity,
        "status": event.status,
        "registration_deadline": event.registration_deadline,
        "team_based": event.team_based,
        "registration_count": event.registration_count,
        "registered": registered,
        "my_registration": my_registration,
        "created_at": event.created_at,
        "updated_at": event.updated_at,
    }


async def present_registration(
    registration: EventRegistration, *, employee_name: Optional[str] = None
) -> dict[str, Any]:
    return {
        "id": registration.id,
        "event_id": registration.event_id,
        "employee_id": registration.employee_id,
        "employee_name": employee_name,
        "team_name": registration.team_name,
        "role": registration.role,
        "status": registration.status,
        "created_at": registration.created_at,
    }


async def present_conversation(
    conversation: Conversation,
    *,
    member_count: int = 0,
    unread_count: int = 0,
    last_message_preview: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "type": conversation.type,
        "title": conversation.title,
        "channel_kind": conversation.channel_kind,
        "channel_key": conversation.channel_key,
        "community_id": conversation.community_id,
        "created_by": conversation.created_by,
        "is_archived": conversation.is_archived,
        "last_message_at": conversation.last_message_at,
        "message_count": conversation.message_count,
        "member_count": member_count,
        "unread_count": unread_count,
        "last_message_preview": last_message_preview,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


async def present_message(
    message: Message,
    *,
    sender_name: Optional[str] = None,
    reactions: Optional[list[dict]] = None,
    read_by: Optional[list[str]] = None,
) -> dict[str, Any]:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "sender_name": sender_name,
        "content": message.content,
        "reply_to": message.reply_to,
        "edited": message.edited,
        "edited_at": message.edited_at,
        "deleted": message.deleted,
        "deleted_at": message.deleted_at,
        "attachments": message.attachments or [],
        "mentions": message.mentions or [],
        "reaction_count": message.reaction_count,
        "reactions": reactions or [],
        "read_by": read_by or [],
        "created_at": message.created_at,
        "updated_at": message.updated_at,
    }


async def present_badge(badge: Any) -> dict[str, Any]:
    return {
        "id": badge.id,
        "code": badge.code,
        "name": badge.name,
        "description": badge.description,
        "icon": badge.icon,
        "category": badge.category,
    }


async def present_employee_badge(db: AsyncSession, badge: EmployeeBadge) -> dict[str, Any]:
    from app.models.communication import Badge

    row = (
        await db.execute(
            select(Badge).where(Badge.organization_id == badge.organization_id, Badge.id == badge.badge_id)
        )
    ).scalar_one_or_none()
    return {
        "id": badge.id,
        "badge_id": badge.badge_id,
        "badge_code": row.code if row else None,
        "badge_name": row.name if row else None,
        "badge_icon": row.icon if row else None,
        "badge_category": row.category if row else None,
        "employee_id": badge.employee_id,
        "awarded_by": badge.awarded_by,
        "reason": badge.reason,
        "created_at": badge.created_at,
    }


async def present_member(member: CommunityMember, *, employee_name: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": member.id,
        "community_id": member.community_id,
        "employee_id": member.employee_id,
        "employee_name": employee_name,
        "role": member.role,
        "notifications_enabled": member.notifications_enabled,
        "joined_at": member.joined_at,
    }


__all__ = [
    "present_announcement", "present_badge", "present_comment", "present_community",
    "present_conversation", "present_employee_badge", "present_event", "present_idea",
    "present_member", "present_message", "present_poll", "present_post",
    "present_recognition", "present_registration", "present_reply", "present_thread",
    "_names", "_community_names",
]
