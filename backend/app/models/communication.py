"""Communication models for announcements, communities, forums, messages, etc."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Enum as SQLEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class Announcement(Base, TimestampMixin):
    __tablename__ = "announcements"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)  # low, normal, high, urgent
    target_audience: Mapped[str] = mapped_column(String(20), default="all", nullable=False)  # all, department, team, specific
    target_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    channels: Mapped[List[str]] = mapped_column(JSON, default=list)  # in_app, email, push, slack
    publish_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_acknowledgment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledgment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    announcement_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_announcements_org_publish", "organization_id", "publish_at"),
        Index("ix_announcements_org_priority", "organization_id", "priority"),
    )


class AnnouncementReceipt(Base, TimestampMixin):
    __tablename__ = "announcement_receipts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivery_channel: Mapped[Optional[str]] = mapped_column(String(20))

    __table_args__ = (
        UniqueConstraint("announcement_id", "employee_id", name="uq_announcement_receipts_ann_emp"),
        Index("ix_announcement_receipts_emp", "employee_id"),
    )


class Badge(Base, TimestampMixin):
    __tablename__ = "badges"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(String(500))
    color: Mapped[Optional[str]] = mapped_column(String(7))
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_badges_org_name"),
    )


class Community(Base, TimestampMixin):
    __tablename__ = "communities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    banner_url: Mapped[Optional[str]] = mapped_column(String(500))
    type: Mapped[str] = mapped_column(String(30), default="open", nullable=False)  # open, private, hidden
    category: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_communities_org_slug"),
        Index("ix_communities_org_category", "organization_id", "category"),
    )


class CommunityMember(Base, TimestampMixin):
    __tablename__ = "community_members"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    community_id: Mapped[str] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(24), default="member", nullable=False)  # owner, admin, moderator, member
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    notification_preferences: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("community_id", "employee_id", name="uq_community_members_comm_emp"),
        Index("ix_community_members_comm_role", "community_id", "role"),
    )


class CommunityPost(Base, TimestampMixin):
    __tablename__ = "community_posts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    community_id: Mapped[str] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)  # text, markdown, poll, event
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_announcement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    announcement_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_community_posts_comm_created", "community_id", "created_at"),
        Index("ix_community_posts_comm_author", "community_id", "author_id"),
    )


class ForumThread(Base, TimestampMixin):
    __tablename__ = "forum_threads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    author_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reply_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_reply_by: Mapped[Optional[str]] = mapped_column(String(32))
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("ix_forum_threads_org_category", "organization_id", "category"),
        Index("ix_forum_threads_org_activity", "organization_id", "last_reply_at"),
    )


class ForumReply(Base, TimestampMixin):
    __tablename__ = "forum_replies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("forum_threads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reply_to_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    is_solution: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_forum_replies_thread_created", "thread_id", "created_at"),
    )


class ForumVote(Base, TimestampMixin):
    __tablename__ = "forum_votes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    thread_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("forum_threads.id", ondelete="CASCADE"), index=True
    )
    reply_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("forum_replies.id", ondelete="CASCADE"), index=True
    )
    voter_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    vote_type: Mapped[str] = mapped_column(String(10), nullable=False)  # up, down

    __table_args__ = (
        UniqueConstraint("thread_id", "voter_id", name="uq_forum_votes_thread_voter"),
        UniqueConstraint("reply_id", "voter_id", name="uq_forum_votes_reply_voter"),
    )


class IdeaVote(Base, TimestampMixin):
    __tablename__ = "idea_votes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    idea_id: Mapped[str] = mapped_column(
        ForeignKey("innovation_ideas.id", ondelete="CASCADE"), index=True, nullable=False
    )
    voter_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    vote_type: Mapped[str] = mapped_column(String(10), nullable=False)  # up, down

    __table_args__ = (
        UniqueConstraint("idea_id", "voter_id", name="uq_idea_votes_idea_voter"),
    )


class InnovationIdea(Base, TimestampMixin):
    __tablename__ = "innovation_ideas"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="submitted", nullable=False)  # submitted, reviewing, approved, implemented, rejected
    vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    implementation_notes: Mapped[Optional[str]] = mapped_column(Text)
    implemented_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_innovation_ideas_org_status", "organization_id", "status"),
        Index("ix_innovation_ideas_org_category", "organization_id", "category"),
    )


class CommunityEvent(Base, TimestampMixin):
    __tablename__ = "community_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    community_id: Mapped[str] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(500))
    meeting_link: Mapped[Optional[str]] = mapped_column(String(500))
    organizer_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    capacity: Mapped[Optional[int]] = mapped_column(Integer)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(500))
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_community_events_comm_time", "community_id", "start_time"),
        Index("ix_community_events_org_time", "organization_id", "start_time"),
    )


class EventRegistration(Base, TimestampMixin):
    __tablename__ = "event_registrations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("community_events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="registered", nullable=False)  # registered, attended, cancelled, waitlisted
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    attended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    guest_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("event_id", "employee_id", name="uq_event_registrations_event_emp"),
        Index("ix_event_registrations_event_status", "event_id", "status"),
    )


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[str] = mapped_column(String(24), default="direct", nullable=False)  # direct, group
    name: Mapped[Optional[str]] = mapped_column(String(200))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    last_message_preview: Mapped[Optional[str]] = mapped_column(String(500))
    unread_count: Mapped[dict] = mapped_column(JSON, default=dict)
    announcement_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_conversations_org_updated", "organization_id", "last_message_at"),
    )


class ConversationMember(Base, TimestampMixin):
    __tablename__ = "conversation_members"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(24), default="member", nullable=False)  # admin, member
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("conversation_id", "employee_id", name="uq_conversation_members_conv_emp"),
        Index("ix_conversation_members_emp", "employee_id"),
    )


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sender_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)  # text, image, file, audio, video, location, contact, system
    reply_to_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reactions: Mapped[dict] = mapped_column(JSON, default=dict)
    announcement_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
        Index("ix_messages_sender", "sender_id"),
    )


class MessageReadReceipt(Base, TimestampMixin):
    __tablename__ = "message_read_receipts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "employee_id", name="uq_message_read_receipts_msg_emp"),
        Index("ix_message_read_receipts_msg", "message_id"),
    )


class MessageReaction(Base, TimestampMixin):
    __tablename__ = "message_reactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reaction: Mapped[str] = mapped_column(String(20), nullable=False)  # emoji or short code

    __table_args__ = (
        UniqueConstraint("message_id", "employee_id", "reaction", name="uq_message_reactions_msg_emp_react"),
    )


class PinnedMessage(Base, TimestampMixin):
    __tablename__ = "pinned_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    pinned_by: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    unpinned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("conversation_id", "message_id", name="uq_pinned_messages_conv_msg"),
    )


class Poll(Base, TimestampMixin):
    __tablename__ = "polls"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    community_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    options: Mapped[List[dict]] = mapped_column(JSON, default=list)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_multiple_votes: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_results: Mapped[str] = mapped_column(String(20), default="after_vote", nullable=False)  # always, after_vote, closed, never
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)  # draft, active, closed
    total_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    announcement_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_polls_org_status", "organization_id", "status"),
    )


class PollOption(Base, TimestampMixin):
    __tablename__ = "poll_options"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    poll_id: Mapped[str] = mapped_column(
        ForeignKey("polls.id", ondelete="CASCADE"), index=True, nullable=False
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_poll_options_poll_order", "poll_id", "order"),
    )


class PollVote(Base, TimestampMixin):
    __tablename__ = "poll_votes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    poll_id: Mapped[str] = mapped_column(
        ForeignKey("polls.id", ondelete="CASCADE"), index=True, nullable=False
    )
    option_id: Mapped[str] = mapped_column(
        ForeignKey("poll_options.id", ondelete="CASCADE"), index=True, nullable=False
    )
    voter_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("poll_id", "voter_id", name="uq_poll_votes_poll_voter"),
    )


class PostBookmark(Base, TimestampMixin):
    __tablename__ = "post_bookmarks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # post, thread, article
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "entity_type", "entity_id", name="uq_post_bookmarks_emp_type_id"),
    )


class PostComment(Base, TimestampMixin):
    __tablename__ = "post_comments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    post_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    post_type: Mapped[str] = mapped_column(String(32), nullable=False)  # community_post, forum_thread
    author_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_post_comments_post", "post_id", "post_type"),
        Index("ix_post_comments_author", "author_id"),
    )


class PostReaction(Base, TimestampMixin):
    __tablename__ = "post_reactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    post_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    post_type: Mapped[str] = mapped_column(String(32), nullable=False)
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reaction: Mapped[str] = mapped_column(String(20), nullable=False)  # emoji or short code

    __table_args__ = (
        UniqueConstraint("post_id", "post_type", "employee_id", "reaction", name="uq_post_reactions_post_emp_react"),
    )


class Recognition(Base, TimestampMixin):
    __tablename__ = "recognitions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    to_employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    badge_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("badges.id", ondelete="SET NULL"), index=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("ix_recognitions_org_to", "organization_id", "to_employee_id"),
        Index("ix_recognitions_org_from", "organization_id", "from_employee_id"),
    )


class CanonicalCommunicationThread(Base, TimestampMixin):
    __tablename__ = "canonical_communication_threads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    thread_type: Mapped[str] = mapped_column(String(30), nullable=False)  # direct, group, channel, announcement
    title: Mapped[Optional[str]] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    participant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    announcement_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_canonical_threads_org_updated", "organization_id", "last_message_at"),
    )


class CanonicalMessage(Base, TimestampMixin):
    __tablename__ = "canonical_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_communication_threads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(24), default="text", nullable=False)
    references: Mapped[List[str]] = mapped_column(JSON, default=list)
    announcement_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_canonical_messages_thread_time", "thread_id", "created_at"),
        Index("ix_canonical_messages_author", "author_id"),
    )


class CanonicalCommunicationThreadMember(Base, TimestampMixin):
    __tablename__ = "canonical_communication_thread_members"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_communication_threads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    participant_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), default="member", nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("thread_id", "participant_id", name="uq_canonical_thread_members_thread_part"),
        Index("ix_canonical_thread_members_participant", "participant_id"),
    )