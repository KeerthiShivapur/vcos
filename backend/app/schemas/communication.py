"""Communication & Community schemas (Phase 5)."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Message  # noqa: F401 (re-exported for routers)

# --- Communities -------------------------------------------------------------

COMMUNITY_TYPES = (
    "engineering", "hr", "marketing", "sports", "innovation", "learning",
    "csr", "leadership", "wellness", "interest", "club", "general",
)
COMMUNITY_VISIBILITIES = ("public", "private", "hidden")


class CommunityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None
    type: str = Field(default="general", pattern="^[a-z_]+$")
    visibility: str = Field(default="public", pattern="^(public|private|hidden)$")
    icon: Optional[str] = None
    banner: Optional[str] = None


class CommunityUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = None
    type: Optional[str] = Field(default=None, pattern="^[a-z_]+$")
    visibility: Optional[str] = Field(default=None, pattern="^(public|private|hidden)$")
    icon: Optional[str] = None
    banner: Optional[str] = None
    is_featured: Optional[bool] = None
    is_archived: Optional[bool] = None


class CommunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    slug: str
    description: Optional[str] = None
    type: str
    visibility: str
    icon: Optional[str] = None
    banner: Optional[str] = None
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    member_count: int
    post_count: int
    is_featured: bool
    is_archived: bool
    is_member: bool = False
    my_role: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CommunityMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    community_id: str
    employee_id: str
    employee_name: Optional[str] = None
    role: str
    notifications_enabled: bool
    joined_at: datetime


# --- Posts -------------------------------------------------------------------


class PostCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=240)
    content: Optional[str] = None
    attachments: Optional[list] = None
    visibility: Optional[str] = Field(default="members", pattern="^(members|organization)$")
    status: Optional[str] = Field(default="published", pattern="^(draft|published|scheduled|archived)$")
    pinned: Optional[bool] = False
    scheduled_at: Optional[datetime] = None


class PostUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=240)
    content: Optional[str] = None
    attachments: Optional[list] = None
    visibility: Optional[str] = Field(default=None, pattern="^(members|organization)$")
    status: Optional[str] = Field(default=None, pattern="^(draft|published|scheduled|archived)$")
    pinned: Optional[bool] = None
    scheduled_at: Optional[datetime] = None


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    community_id: str
    community_name: Optional[str] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    attachments: Optional[list] = []
    visibility: str
    status: str
    pinned: bool
    scheduled_at: Optional[datetime] = None
    edited_at: Optional[datetime] = None
    comment_count: int
    reaction_count: int
    bookmark_count: int
    share_count: int
    is_bookmarked: bool = False
    my_reaction: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    parent_id: Optional[str] = None
    is_resolution: Optional[bool] = False


class CommentUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=10000)
    is_resolution: Optional[bool] = None


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    post_id: str
    parent_id: Optional[str] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    content: str
    is_resolution: bool
    edited: bool
    edited_at: Optional[datetime] = None
    reaction_count: int
    my_reaction: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ReactionOut(BaseModel):
    emoji: str
    count: int
    reacted: bool


# --- Announcements -----------------------------------------------------------


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    body: Optional[str] = None
    type: Optional[str] = Field(default="general", pattern="^[a-z_]+$")
    priority: Optional[str] = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    status: Optional[str] = Field(default="draft", pattern="^(draft|scheduled|published|expired|cancelled)$")
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    pinned: Optional[bool] = False
    acknowledge_required: Optional[bool] = False
    attachments: Optional[list] = None


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    body: Optional[str] = None
    type: Optional[str] = Field(default=None, pattern="^[a-z_]+$")
    priority: Optional[str] = Field(default=None, pattern="^(low|normal|high|urgent)$")
    status: Optional[str] = Field(default=None, pattern="^(draft|scheduled|published|expired|cancelled)$")
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    pinned: Optional[bool] = None
    acknowledge_required: Optional[bool] = None
    attachments: Optional[list] = None


class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    body: Optional[str] = None
    type: str
    priority: str
    status: str
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    team_id: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    pinned: bool
    acknowledge_required: bool
    attachments: Optional[list] = []
    read_count: int
    acknowledged_count: int
    read_by_me: bool = False
    acknowledged_by_me: bool = False
    created_at: datetime
    updated_at: datetime


# --- Forums ------------------------------------------------------------------

FORUM_CATEGORIES = (
    "engineering", "devops", "sales", "hr", "finance", "legal", "research",
    "ai", "product", "support", "operations", "general",
)


class ForumThreadCreate(BaseModel):
    category: str = Field(pattern="^[a-z_]+$")
    title: str = Field(min_length=1, max_length=240)
    content: Optional[str] = None
    tags: Optional[list[str]] = None


class ForumThreadUpdate(BaseModel):
    category: Optional[str] = Field(default=None, pattern="^[a-z_]+$")
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    content: Optional[str] = None
    tags: Optional[list[str]] = None
    status: Optional[str] = Field(default=None, pattern="^(open|resolved|closed)$")
    is_pinned: Optional[bool] = None


class ForumThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: str
    title: str
    content: Optional[str] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    status: str
    tags: Optional[list] = []
    vote_count: int
    reply_count: int
    view_count: int
    is_pinned: bool
    accepted_reply_id: Optional[str] = None
    is_resolved: bool
    my_vote: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ForumReplyCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    parent_id: Optional[str] = None


class ForumReplyUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=10000)


class ForumReplyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    thread_id: str
    parent_id: Optional[str] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    content: str
    is_accepted: bool
    vote_count: int
    edited: bool
    my_vote: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# --- Recognition -------------------------------------------------------------

RECOGNITION_CATEGORIES = (
    "innovation", "leadership", "mentorship", "helping_others",
    "knowledge_sharing", "customer_success", "learning", "teamwork",
    "ownership", "community",
)


class RecognitionCreate(BaseModel):
    recipient_id: str = Field(min_length=1)
    category: str = Field(pattern="^[a-z_]+$")
    message: Optional[str] = Field(default=None, max_length=2000)
    badge_code: Optional[str] = None
    public: Optional[bool] = True


class RecognitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    giver_id: Optional[str] = None
    giver_name: Optional[str] = None
    recipient_id: str
    recipient_name: Optional[str] = None
    category: str
    message: Optional[str] = None
    badge_code: Optional[str] = None
    public: bool
    created_at: datetime


class RecognitionStats(BaseModel):
    total: int
    categories: list[dict]
    top_recipients: list[dict]
    top_givers: list[dict]
    this_month: int


# --- Innovation Hub ----------------------------------------------------------

IDEA_STATUSES = (
    "submitted", "in_discussion", "voting", "in_review",
    "approved", "in_progress", "implemented", "rejected",
)


class IdeaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: Optional[str] = None
    problem: Optional[str] = None
    solution: Optional[str] = None
    impact: Optional[str] = None
    tags: Optional[list[str]] = None


class IdeaUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    description: Optional[str] = None
    problem: Optional[str] = None
    solution: Optional[str] = None
    impact: Optional[str] = None
    tags: Optional[list[str]] = None
    status: Optional[str] = Field(default=None, pattern="^[a-z_]+$")


class IdeaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    problem: Optional[str] = None
    solution: Optional[str] = None
    impact: Optional[str] = None
    status: str
    vote_count: int
    comment_count: int
    tags: Optional[list] = []
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    duplicates_of: Optional[str] = None
    ai_insight: Optional[str] = None
    voted: bool = False
    submitted_at: datetime
    created_at: datetime
    updated_at: datetime


# --- Polls -------------------------------------------------------------------


class PollOptionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=240)
    sort_order: Optional[int] = 0


class PollCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    question: Optional[str] = None
    description: Optional[str] = None
    community_id: Optional[str] = None
    anonymous: Optional[bool] = False
    multiple_choice: Optional[bool] = False
    status: Optional[str] = Field(default="open", pattern="^(draft|open|closed)$")
    ends_at: Optional[datetime] = None
    options: list[PollOptionCreate] = Field(default_factory=list)


class PollUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    question: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(draft|open|closed)$")
    ends_at: Optional[datetime] = None


class PollOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    poll_id: str
    text: str
    sort_order: int
    vote_count: int


class PollOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    question: Optional[str] = None
    description: Optional[str] = None
    community_id: Optional[str] = None
    community_name: Optional[str] = None
    created_by: Optional[str] = None
    creator_name: Optional[str] = None
    anonymous: bool
    multiple_choice: bool
    status: str
    ends_at: Optional[datetime] = None
    vote_count: int
    participant_count: int
    options: list[PollOptionOut] = []
    voted: bool = False
    my_choices: list[str] = []
    created_at: datetime
    updated_at: datetime


class PollVotePayload(BaseModel):
    option_ids: list[str] = Field(min_length=1, max_length=50)


class ReactionPayload(BaseModel):
    emoji: str = Field(min_length=1, max_length=24)


class ForumVotePayload(BaseModel):
    value: int = Field(ge=-1, le=1)


class CommunityRolePayload(BaseModel):
    employee_id: str
    role: str = Field(pattern="^(owner|moderator|member)$")


class ConversationMemberPayload(BaseModel):
    employee_id: str


class EventRegisterPayload(BaseModel):
    team_name: Optional[str] = Field(default=None, max_length=120)
    role: Optional[str] = Field(default="participant", max_length=24)


class IdeaStatusPayload(BaseModel):
    status: str = Field(pattern="^[a-z_]+$")
    feedback: Optional[str] = None


class PromotePayload(BaseModel):
    project_id: Optional[str] = None


# --- Events ------------------------------------------------------------------

EVENT_TYPES = (
    "hackathon", "town_hall", "workshop", "training", "volunteer",
    "competition", "celebration", "meetup", "other",
)


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: Optional[str] = None
    type: Optional[str] = Field(default="other", pattern="^[a-z_]+$")
    community_id: Optional[str] = None
    starts_at: datetime
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    virtual_url: Optional[str] = None
    capacity: Optional[int] = Field(default=0, ge=0)
    status: Optional[str] = Field(default="open", pattern="^(draft|open|closed|cancelled|completed)$")
    registration_deadline: Optional[datetime] = None
    team_based: Optional[bool] = False


class EventUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    description: Optional[str] = None
    type: Optional[str] = Field(default=None, pattern="^[a-z_]+$")
    community_id: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    virtual_url: Optional[str] = None
    capacity: Optional[int] = Field(default=None, ge=0)
    status: Optional[str] = Field(default=None, pattern="^(draft|open|closed|cancelled|completed)$")
    registration_deadline: Optional[datetime] = None
    team_based: Optional[bool] = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: Optional[str] = None
    type: str
    community_id: Optional[str] = None
    community_name: Optional[str] = None
    created_by: Optional[str] = None
    creator_name: Optional[str] = None
    starts_at: datetime
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    virtual_url: Optional[str] = None
    capacity: int
    status: str
    registration_deadline: Optional[datetime] = None
    team_based: bool
    registration_count: int
    registered: bool = False
    my_registration: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class EventRegistrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    employee_id: str
    employee_name: Optional[str] = None
    team_name: Optional[str] = None
    role: str
    status: str
    created_at: datetime


# --- Gamification ------------------------------------------------------------

class BadgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    category: str


class EmployeeBadgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    badge_id: str
    badge_code: Optional[str] = None
    badge_name: Optional[str] = None
    badge_icon: Optional[str] = None
    badge_category: Optional[str] = None
    employee_id: str
    awarded_by: Optional[str] = None
    reason: Optional[str] = None
    created_at: datetime


# --- Messaging ---------------------------------------------------------------

CONVERSATION_TYPES = ("dm", "group", "channel")


class ConversationCreate(BaseModel):
    type: Optional[str] = Field(default="dm", pattern="^(dm|group|channel)$")
    title: Optional[str] = Field(default=None, max_length=240)
    member_ids: Optional[list[str]] = None
    channel_kind: Optional[str] = Field(default=None, pattern="^[a-z_]+$")
    channel_key: Optional[str] = None
    community_id: Optional[str] = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    title: Optional[str] = None
    channel_kind: Optional[str] = None
    channel_key: Optional[str] = None
    community_id: Optional[str] = None
    created_by: Optional[str] = None
    is_archived: bool
    last_message_at: Optional[datetime] = None
    message_count: int
    member_count: int
    unread_count: int = 0
    last_message_preview: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: Optional[str] = Field(default=None, max_length=10000)
    reply_to: Optional[str] = None
    attachments: Optional[list] = None
    mentions: Optional[list[str]] = None


class MessageUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=10000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    content: Optional[str] = None
    reply_to: Optional[str] = None
    edited: bool
    deleted: bool
    deleted_at: Optional[datetime] = None
    attachments: Optional[list] = []
    mentions: Optional[list] = []
    reaction_count: int
    reactions: list[dict] = []
    read_by: list[str] = []
    created_at: datetime
    updated_at: datetime


# --- Analytics / feed --------------------------------------------------------

class CommunityFeedItem(BaseModel):
    kind: str
    id: str
    title: Optional[str] = None
    body: Optional[str] = None
    author_name: Optional[str] = None
    community_id: Optional[str] = None
    community_name: Optional[str] = None
    link: str
    created_at: datetime
