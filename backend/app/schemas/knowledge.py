"""Knowledge schemas — Phase 4 (documents, wiki, policies, SOPs, templates,
decisions, semantic search, knowledge graph, analytics)."""

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMModel


# --- Shared payload envelope -------------------------------------------------

def entity_url(kind: str, entity_id: str) -> str:
    routes = {
        "document": "documents",
        "wiki": "wiki",
        "policy": "policies",
        "sop": "sops",
        "template": "templates",
        "decision": "decisions",
    }
    route = routes.get(kind, "knowledge")
    return f"/{route}/{entity_id}"


def entity_meta(entity, kind: str, label: str = None) -> dict[str, Any]:
    """Common knowledge entity payload fields (overrides in Out schemas)."""
    return {
        "id": entity.id,
        "kind": kind,
        "url": entity_url(kind, entity.id),
        "title": entity.title,
        "description": entity.description,
        "summary": entity.summary,
        "ai_summary": entity.ai_summary,
        "keywords": entity.keywords,
        "status": entity.status,
        "version": entity.version,
        "view_count": entity.view_count,
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
    }


# --- Categories / tags -------------------------------------------------------

class KnowledgeCategoryOut(ORMModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    color: Optional[str] = None
    item_count: Optional[int] = 0


class KnowledgeCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None
    color: Optional[str] = None


class KnowledgeTagOut(ORMModel):
    id: str
    name: str
    slug: str
    item_count: Optional[int] = 0


# --- Documents ---------------------------------------------------------------

class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    owner_id: Optional[str] = None
    project_id: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    status: Optional[str] = Field(default="draft", pattern="^(draft|in_review|published|archived)$")
    visibility: Optional[str] = Field(default="organization", pattern="^(organization|department|team|private)$")
    summary: Optional[str] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    description: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    owner_id: Optional[str] = None
    project_id: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    visibility: Optional[str] = Field(default=None, pattern="^(organization|department|team|private)$")
    summary: Optional[str] = None
    change_note: Optional[str] = Field(default=None, max_length=500)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str = "document"
    url: str
    title: str
    slug: str
    description: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    ai_summary: Optional[str] = None
    keywords: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = []
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    status: str
    visibility: str
    version: int
    view_count: int
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# --- Wiki --------------------------------------------------------------------

class WikiPageCreate(BaseModel):
    space: Optional[str] = Field(default="organization", pattern="^(organization|department|project|team|personal)$")
    title: str = Field(min_length=1, max_length=240)
    description: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    parent_id: Optional[str] = None
    project_id: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    status: Optional[str] = Field(default="draft", pattern="^(draft|published|archived)$")
    summary: Optional[str] = None


class WikiPageUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    description: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    parent_id: Optional[str] = None
    project_id: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    summary: Optional[str] = None
    change_note: Optional[str] = Field(default=None, max_length=500)


class WikiPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str = "wiki"
    url: str
    title: str
    slug: str
    space: str
    description: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    ai_summary: Optional[str] = None
    keywords: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = []
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    editor_id: Optional[str] = None
    parent_id: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    status: str
    version: int
    view_count: int
    child_count: Optional[int] = 0
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# --- Policies ----------------------------------------------------------------

POLICY_CATEGORIES = [
    "general", "leave", "security", "travel", "expense", "remote_work", "conduct",
    "compliance", "privacy", "it", "access", "procurement", "quality", "safety", "other",
]


class PolicyCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = Field(default="general", pattern="^([a-z_]+)$")
    tags: Optional[list[str]] = None
    owner_id: Optional[str] = None
    approver_id: Optional[str] = None
    effective_date: Optional[date] = None
    review_date: Optional[date] = None
    status: Optional[str] = Field(default="draft", pattern="^(draft|in_review|approved|published|archived)$")
    summary: Optional[str] = None


class PolicyUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    description: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    owner_id: Optional[str] = None
    approver_id: Optional[str] = None
    effective_date: Optional[date] = None
    review_date: Optional[date] = None
    summary: Optional[str] = None
    change_note: Optional[str] = Field(default=None, max_length=500)


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str = "policy"
    url: str
    title: str
    slug: str
    description: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    ai_summary: Optional[str] = None
    keywords: Optional[str] = None
    category: str
    tags: Optional[list[str]] = []
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    approver_id: Optional[str] = None
    approver_name: Optional[str] = None
    effective_date: Optional[date] = None
    review_date: Optional[date] = None
    review_overdue: Optional[bool] = False
    approval_note: Optional[str] = None
    status: str
    version: int
    view_count: int
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# --- SOPs --------------------------------------------------------------------

class SOPCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    status: Optional[str] = Field(default="draft", pattern="^(draft|published|archived)$")
    summary: Optional[str] = None
    steps: Optional[list["SOPStepCreate"]] = None


class SOPUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    description: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    summary: Optional[str] = None
    change_note: Optional[str] = Field(default=None, max_length=500)
    steps: Optional[list["SOPStepCreate"]] = None


class SOPStepCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    instruction: Optional[str] = None
    is_checklist: Optional[bool] = False
    sort_order: Optional[int] = 0


class SOPStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sop_id: str
    title: str
    instruction: Optional[str] = None
    is_checklist: bool
    sort_order: int


class SOPOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str = "sop"
    url: str
    title: str
    slug: str
    description: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    ai_summary: Optional[str] = None
    keywords: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = []
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    status: str
    version: int
    view_count: int
    steps: Optional[list[SOPStepOut]] = []
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# --- Templates ---------------------------------------------------------------

TEMPLATE_KINDS = [
    "meeting_notes", "architecture", "project_plan", "release_plan", "incident_report",
    "research", "customer_proposal", "contract", "training", "onboarding", "other",
]


class TemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: Optional[str] = None
    content: Optional[str] = None
    kind: Optional[str] = Field(default="other", pattern="^([a-z_]+)$")
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    owner_id: Optional[str] = None
    status: Optional[str] = Field(default="draft", pattern="^(draft|published|archived)$")
    summary: Optional[str] = None


class TemplateUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    description: Optional[str] = None
    content: Optional[str] = None
    kind: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    owner_id: Optional[str] = None
    summary: Optional[str] = None
    change_note: Optional[str] = Field(default=None, max_length=500)


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str = "template"
    url: str
    title: str
    slug: str
    description: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    ai_summary: Optional[str] = None
    keywords: Optional[str] = None
    kind_name: str
    category: Optional[str] = None
    tags: Optional[list[str]] = []
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    status: str
    version: int
    usage_count: int
    view_count: int
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# --- Decisions ---------------------------------------------------------------

class DecisionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: Optional[str] = None
    context: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = Field(default="proposed", pattern="^(proposed|made|implemented|reviewed)$")
    decision_maker_id: Optional[str] = None
    decision_date: Optional[date] = None
    impact: Optional[str] = None
    business_impact: Optional[str] = None
    follow_up_actions: Optional[list[str]] = None
    future_review_date: Optional[date] = None
    lessons_learned: Optional[str] = None
    project_id: Optional[str] = None
    meeting_id: Optional[str] = None
    department_id: Optional[str] = None
    tags: Optional[list[str]] = None
    summary: Optional[str] = None
    options: Optional[list["DecisionOptionCreate"]] = None
    participants: Optional[list["DecisionParticipantCreate"]] = None


class DecisionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    description: Optional[str] = None
    context: Optional[str] = None
    content: Optional[str] = None
    decision_maker_id: Optional[str] = None
    decision_date: Optional[date] = None
    impact: Optional[str] = None
    business_impact: Optional[str] = None
    follow_up_actions: Optional[list[str]] = None
    future_review_date: Optional[date] = None
    lessons_learned: Optional[str] = None
    project_id: Optional[str] = None
    meeting_id: Optional[str] = None
    department_id: Optional[str] = None
    tags: Optional[list[str]] = None
    summary: Optional[str] = None
    change_note: Optional[str] = Field(default=None, max_length=500)


class DecisionOptionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: Optional[str] = None
    pros: Optional[str] = None
    cons: Optional[str] = None
    sort_order: Optional[int] = 0


class DecisionOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    decision_id: str
    title: str
    description: Optional[str] = None
    pros: Optional[str] = None
    cons: Optional[str] = None
    chosen: bool
    chosen_reason: Optional[str] = None
    sort_order: int


class DecisionParticipantCreate(BaseModel):
    employee_id: str
    role: Optional[str] = Field(default="consulted", pattern="^(maker|approver|consulted|informed)$")


class DecisionParticipantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    decision_id: str
    employee_id: str
    employee_name: Optional[str] = None
    role: str


class DecisionChoose(BaseModel):
    option_id: str
    reason: Optional[str] = None


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str = "decision"
    url: str
    title: str
    slug: str
    description: Optional[str] = None
    context: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    ai_summary: Optional[str] = None
    keywords: Optional[str] = None
    status: str
    tags: Optional[list[str]] = []
    decision_maker_id: Optional[str] = None
    decision_maker_name: Optional[str] = None
    decision_date: Optional[date] = None
    impact: Optional[str] = None
    business_impact: Optional[str] = None
    follow_up_actions: Optional[list[str]] = None
    future_review_date: Optional[date] = None
    lessons_learned: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    meeting_id: Optional[str] = None
    department_id: Optional[str] = None
    version: int
    view_count: int
    decided_at: Optional[datetime] = None
    options: Optional[list[DecisionOptionOut]] = []
    participants: Optional[list[DecisionParticipantOut]] = []
    created_at: datetime
    updated_at: datetime


# --- Versions / comments / watchers / favorites / presence -------------------

class DocumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    entity_id: str
    version: int
    title: str
    content: Optional[str] = None
    summary: Optional[str] = None
    editor_id: Optional[str] = None
    editor_name: Optional[str] = None
    change_note: Optional[str] = None
    created_at: datetime


class CommentCreate(BaseModel):
    content: str = Field(min_length=1)
    parent_id: Optional[str] = None
    mention_user_ids: Optional[list[str]] = None


class CommentUpdate(BaseModel):
    content: str = Field(min_length=1)
    resolved: Optional[bool] = None


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    entity_id: str
    author_id: str
    author_name: Optional[str] = None
    content: str
    parent_id: Optional[str] = None
    resolved: bool
    created_at: datetime
    updated_at: datetime


class WatcherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    entity_id: str
    user_id: str
    user_name: Optional[str] = None
    created_at: datetime


class FavoriteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    entity_id: str
    user_id: str
    created_at: datetime


class PresenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: str
    entity_id: str
    user_id: str
    user_name: Optional[str] = None
    last_active_at: datetime


# --- Relations / graph -------------------------------------------------------

class RelationCreate(BaseModel):
    target_type: str = Field(min_length=1, max_length=40)
    target_id: str = Field(min_length=1, max_length=32)
    relation_type: Optional[str] = Field(default="related_to", pattern="^([a-z_]+)$")


class RelationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    relation_type: str
    target_title: Optional[str] = None
    target_url: Optional[str] = None
    created_at: datetime


class KnowledgeGraphNode(BaseModel):
    id: str
    label: str
    kind: str
    status: Optional[str] = None
    meta: dict[str, Any] = {}


class KnowledgeGraphEdge(BaseModel):
    source: str
    target: str
    relation: str


class KnowledgeGraphOut(BaseModel):
    nodes: list[KnowledgeGraphNode] = []
    edges: list[KnowledgeGraphEdge] = []


# --- Search ------------------------------------------------------------------

class KnowledgeSearchResult(BaseModel):
    id: str
    kind: str
    title: str
    url: str
    subtitle: Optional[str] = None
    snippet: Optional[str] = None
    score: float
    matched_keywords: list[str] = []
    metadata: dict[str, Any] = {}


class KnowledgeSearchResponse(BaseModel):
    query: str
    mode: str
    results: list[KnowledgeSearchResult] = []
    total: int
    took_ms: int


# --- Recommendations ---------------------------------------------------------

class KnowledgeRecommendation(BaseModel):
    id: str
    kind: str
    title: str
    url: str
    reason: str
    score: float
    status: Optional[str] = None


class ExpertSuggestion(BaseModel):
    employee_id: str
    name: str
    designation: Optional[str] = None
    avatar_url: Optional[str] = None
    expertise_score: Optional[int] = None
    context: Optional[str] = None


# --- Quality / analytics -----------------------------------------------------

class KnowledgeQualityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: str
    entity_id: str
    completeness: int
    freshness: int
    popularity: int
    usage: int
    review_status: str
    score: int
    duplicate_of: Optional[str] = None
    updated_at: datetime


class KnowledgeAnalytics(BaseModel):
    totals: dict[str, int] = {}
    growth_30d: dict[str, int] = {}
    growth_series: list[dict[str, Any]] = []
    top_viewed: list[KnowledgeSearchResult] = []
    top_contributors: list[dict[str, Any]] = []
    category_coverage: list[dict[str, Any]] = []
    department_health: list[dict[str, Any]] = []
    outdated: list[KnowledgeSearchResult] = []
    review_backlog: list[KnowledgeSearchResult] = []
    quality_distribution: dict[str, float] = {}
    expert_distribution: list[dict[str, Any]] = []
    search_trends: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []


# --- Workflow -----------------------------------------------------------------

class WorkflowAction(BaseModel):
    note: Optional[str] = None
    approver_id: Optional[str] = None
