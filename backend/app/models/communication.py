"""Communication & Community models (Phase 5).

Communities, posts, comments, reactions, announcements, forums, recognition,
innovation ideas, polls, events, badges and messaging.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import gen_uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Timestamped(Base):
    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# --- Communities -------------------------------------------------------------

class Community(Timestamped):
    __tablename__ = "communities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(24), default="general", nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(String(24), default="public", nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(240))
    banner: Mapped[Optional[str]] = mapped_column(String(500))
    owner_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_communities_org_slug"),)


class CommunityMember(Timestamped):
    __tablename__ = "community_members"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    community_id: Mapped[str] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(24), default="member", nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("community_id", "employee_id", name="uq_community_members_member"),)


# --- Posts -------------------------------------------------------------------

class CommunityPost(Timestamped):
    __tablename__ = "community_posts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    community_id: Mapped[str] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    title: Mapped[Optional[str]] = mapped_column(String(240))
    content: Mapped[Optional[str]] = mapped_column(Text)
    attachments: Mapped[Optional[list]] = mapped_column(JSON)
    visibility: Mapped[str] = mapped_column(String(24), default="members", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="published", nullable=False, index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bookmark_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    share_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PostComment(Timestamped):
    __tablename__ = "post_comments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    post_id: Mapped[str] = mapped_column(
        ForeignKey("community_posts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("post_comments.id", ondelete="SET NULL"), index=True
    )
    author_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolution: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PostReaction(Timestamped):
    __tablename__ = "post_reactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    emoji: Mapped[str] = mapped_column(String(24), nullable=False)

    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "employee_id", name="uq_post_reactions_target_employee"),
    )


class PostBookmark(Timestamped):
    __tablename__ = "post_bookmarks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    post_id: Mapped[str] = mapped_column(
        ForeignKey("community_posts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)

    __table_args__ = (UniqueConstraint("post_id", "employee_id", name="uq_post_bookmarks_employee"),)


# --- Announcements -----------------------------------------------------------

class Announcement(Timestamped):
    __tablename__ = "announcements"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(24), default="general", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(12), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    author_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    team_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledge_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attachments: Mapped[Optional[list]] = mapped_column(JSON)
    read_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    acknowledged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AnnouncementReceipt(Timestamped):
    __tablename__ = "announcement_receipts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("announcement_id", "employee_id", name="uq_announcement_receipts_employee"),
    )


# --- Forums ------------------------------------------------------------------

class ForumThread(Timestamped):
    __tablename__ = "forum_threads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    author_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False, index=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON)
    vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepted_reply_id: Mapped[Optional[str]] = mapped_column(String(32))
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ForumReply(Timestamped):
    __tablename__ = "forum_replies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("forum_threads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("forum_replies.id", ondelete="SET NULL"), index=True
    )
    author_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ForumVote(Timestamped):
    __tablename__ = "forum_votes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "employee_id", name="uq_forum_votes_target_employee"),
    )


# --- Recognition -------------------------------------------------------------

class Recognition(Timestamped):
    __tablename__ = "recognitions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    giver_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    recipient_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message: Mapped[Optional[str]] = mapped_column(Text)
    badge_code: Mapped[Optional[str]] = mapped_column(String(48))
    public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# --- Innovation Hub ----------------------------------------------------------

class InnovationIdea(Timestamped):
    __tablename__ = "innovation_ideas"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    problem: Mapped[Optional[str]] = mapped_column(Text)
    solution: Mapped[Optional[str]] = mapped_column(Text)
    impact: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="submitted", nullable=False, index=True)
    vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tags: Mapped[Optional[list]] = mapped_column(JSON)
    project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    duplicates_of: Mapped[Optional[str]] = mapped_column(String(32))
    ai_insight: Mapped[Optional[str]] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IdeaVote(Timestamped):
    __tablename__ = "idea_votes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    idea_id: Mapped[str] = mapped_column(
        ForeignKey("innovation_ideas.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)

    __table_args__ = (UniqueConstraint("idea_id", "employee_id", name="uq_idea_votes_employee"),)


# --- Polls -------------------------------------------------------------------

class Poll(Timestamped):
    __tablename__ = "polls"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    question: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    community_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    multiple_choice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    participant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PollOption(Timestamped):
    __tablename__ = "poll_options"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    poll_id: Mapped[str] = mapped_column(
        ForeignKey("polls.id", ondelete="CASCADE"), index=True, nullable=False
    )
    text: Mapped[str] = mapped_column(String(240), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PollVote(Timestamped):
    __tablename__ = "poll_votes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    poll_id: Mapped[str] = mapped_column(
        ForeignKey("polls.id", ondelete="CASCADE"), index=True, nullable=False
    )
    option_id: Mapped[str] = mapped_column(
        ForeignKey("poll_options.id", ondelete="CASCADE"), index=True, nullable=False
    )
    voter_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)

    __table_args__ = (
        UniqueConstraint("poll_id", "option_id", "voter_id", name="uq_poll_votes_choice"),
    )


# --- Events ------------------------------------------------------------------

class CommunityEvent(Timestamped):
    __tablename__ = "community_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(24), default="other", nullable=False, index=True)
    community_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    location: Mapped[Optional[str]] = mapped_column(String(240))
    virtual_url: Mapped[Optional[str]] = mapped_column(String(500))
    capacity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False, index=True)
    registration_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    team_based: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    registration_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class EventRegistration(Timestamped):
    __tablename__ = "event_registrations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("community_events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    team_name: Mapped[Optional[str]] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(24), default="participant", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="registered", nullable=False)

    __table_args__ = (UniqueConstraint("event_id", "employee_id", name="uq_event_registrations_employee"),)


# --- Gamification ------------------------------------------------------------

class Badge(Timestamped):
    __tablename__ = "badges"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(String(48))
    category: Mapped[str] = mapped_column(String(48), default="community", nullable=False)

    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_badges_org_code"),)


class EmployeeBadge(Timestamped):
    __tablename__ = "employee_badges"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    badge_id: Mapped[str] = mapped_column(
        ForeignKey("badges.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    awarded_by: Mapped[Optional[str]] = mapped_column(String(32))
    reason: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("badge_id", "employee_id", name="uq_employee_badges_employee"),
    )


# --- Messaging ---------------------------------------------------------------

class Conversation(Timestamped):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[str] = mapped_column(String(16), default="dm", nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(240))
    channel_kind: Mapped[Optional[str]] = mapped_column(String(24), index=True)
    channel_key: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    community_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "channel_kind", "channel_key", name="uq_conversations_channel"),
    )


class ConversationMember(Timestamped):
    __tablename__ = "conversation_members"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(24), default="member", nullable=False)
    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("conversation_id", "employee_id", name="uq_conversation_members_member"),
    )


class Message(Timestamped):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sender_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    content: Mapped[Optional[str]] = mapped_column(Text)
    reply_to: Mapped[Optional[str]] = mapped_column(String(32))
    edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attachments: Mapped[Optional[list]] = mapped_column(JSON)
    mentions: Mapped[Optional[list]] = mapped_column(JSON)
    reaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class MessageReaction(Timestamped):
    __tablename__ = "message_reactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    emoji: Mapped[str] = mapped_column(String(24), nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "employee_id", "emoji", name="uq_message_reactions_employee_emoji"),
    )


class MessageReadReceipt(Timestamped):
    __tablename__ = "message_read_receipts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reader_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "reader_id", name="uq_message_read_receipts_reader"),
    )


class PinnedMessage(Timestamped):
    __tablename__ = "pinned_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    pinned_by: Mapped[Optional[str]] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint("conversation_id", "message_id", name="uq_pinned_messages_pair"),
    )
