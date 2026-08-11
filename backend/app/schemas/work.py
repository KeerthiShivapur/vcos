"""Phase 3 — Work Execution Engine schemas.

Projects, roadmaps, epics, milestones, sprints, tasks, dependencies,
goals/key results, meetings, calendar events, approvals, risks, workload.
"""

from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# --------------------------------------------------------------------------- Projects

class ProjectLifecycleRequest(BaseModel):
    action: str = Field(pattern="^(start|pause|resume|complete|cancel|archive)$")


class RoadmapLifecycleRequest(BaseModel):
    action: str = Field(pattern="^(activate|complete|archive)$")


class ProjectCreate(BaseModel):
    code: Optional[str] = None
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(default="draft", pattern="^(draft|active|paused|completed|archived)$")
    priority: Optional[str] = Field(default="medium", pattern="^(low|medium|high|critical)$")
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    roadmap_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[float] = None
    tags: Optional[List[str]] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(draft|active|paused|completed|archived)$")
    priority: Optional[str] = Field(default=None, pattern="^(low|medium|high|critical)$")
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    roadmap_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[float] = None
    tags: Optional[List[str]] = None


class ProjectOut(ORMModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    status: str
    priority: str
    progress: int = 0
    health: str = "healthy"
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    roadmap_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[float] = None
    tags: Optional[List[str]] = None
    ai_summary: Optional[str] = None
    members_count: int = 0
    tasks_count: int = 0
    completed_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectMemberOut(ORMModel):
    id: str
    employee_id: str
    name: str
    designation: Optional[str] = None
    avatar_url: Optional[str] = None
    role: Optional[str] = None
    joined_at: Optional[datetime] = None


class ProjectStatsOut(BaseModel):
    project_id: str
    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    blocked_tasks: int
    progress: int
    milestones_total: int
    milestones_completed: int
    status_breakdown: dict[str, int]


class TimelineEntryOut(ORMModel):
    id: str
    project_id: str
    kind: str
    title: str
    description: Optional[str] = None
    meta: Optional[dict] = None
    occurred_at: Optional[datetime] = None


class RoadmapCreate(BaseModel):
    name: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    timeframe: str = "quarter"
    status: str = "draft"


class RoadmapOut(ORMModel):
    id: str
    name: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    timeframe: str
    status: str
    progress: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class EpicCreate(BaseModel):
    project_id: Optional[str] = None
    roadmap_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    status: str = "planned"
    priority: str = "medium"
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class EpicOut(ORMModel):
    id: str
    project_id: Optional[str] = None
    roadmap_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    status: str
    priority: str
    progress: int = 0
    tasks_count: int = 0
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MilestoneCreate(BaseModel):
    project_id: Optional[str] = None
    roadmap_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    due_date: Optional[date] = None


class MilestoneOut(ORMModel):
    id: str
    project_id: Optional[str] = None
    roadmap_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    status: str
    progress: int = 0
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SprintCreate(BaseModel):
    project_id: Optional[str] = None
    name: str
    goal: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: str = "planned"


class SprintOut(ORMModel):
    id: str
    project_id: Optional[str] = None
    name: str
    goal: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: str
    progress: int = 0
    tasks_count: int = 0
    completed_tasks: int = 0
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --------------------------------------------------------------------------- Tasks

class TaskCreate(BaseModel):
    project_id: Optional[str] = None
    epic_id: Optional[str] = None
    milestone_id: Optional[str] = None
    sprint_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    decision_id: Optional[str] = None
    goal_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: Optional[str] = Field(default="backlog", pattern="^(backlog|todo|in_progress|review|blocked|completed|archived)$")
    priority: Optional[str] = Field(default="medium", pattern="^(low|medium|high|critical)$")
    assignee_id: Optional[str] = None
    reporter_id: Optional[str] = None
    estimate_hours: Optional[float] = Field(default=None, ge=0)
    spent_hours: Optional[float] = Field(default=0, ge=0)
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    tags: Optional[List[str]] = None
    dependencies: Optional[List[dict]] = None  # [{"depends_on_task_id": str, "kind": str}]


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(backlog|todo|in_progress|review|blocked|completed|archived)$")
    priority: Optional[str] = Field(default=None, pattern="^(low|medium|high|critical)$")
    assignee_id: Optional[str] = None
    reporter_id: Optional[str] = None
    estimate_hours: Optional[float] = Field(default=None, ge=0)
    spent_hours: Optional[float] = Field(default=None, ge=0)
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    project_id: Optional[str] = None
    epic_id: Optional[str] = None
    milestone_id: Optional[str] = None
    sprint_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    goal_id: Optional[str] = None
    decision_id: Optional[str] = None
    tags: Optional[List[str]] = None


class TaskTransition(BaseModel):
    model_config = {"extra": "forbid"}

    status: str = Field(pattern="^(backlog|todo|in_progress|review|blocked|completed|archived)$")
    force: bool = False  # bypass dependency-satisfaction guard


class TaskOut(ORMModel):
    id: str
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    epic_id: Optional[str] = None
    milestone_id: Optional[str] = None
    sprint_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    parent_title: Optional[str] = None
    decision_id: Optional[str] = None
    decision: Optional[dict] = None
    goal_id: Optional[str] = None
    goal_name: Optional[str] = None
    subtasks_count: int = 0
    subtasks_completed: int = 0
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    assignee_avatar_url: Optional[str] = None
    reporter_id: Optional[str] = None
    reporter_name: Optional[str] = None
    estimate_hours: Optional[float] = None
    spent_hours: float = 0
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    completed_at: Optional[datetime] = None
    progress: int = 0
    tags: Optional[List[str]] = None
    ai_summary: Optional[str] = None
    dependencies: Optional[List[dict]] = None
    blocking_tasks: Optional[List[dict]] = None
    blocked_by: Optional[List[dict]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TaskCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    mentions: Optional[List[str]] = None  # explicit employee ids (also parsed from @email in body)


class TaskCommentOut(ORMModel):
    id: str
    task_id: str
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    body: str
    mentions: Optional[List[str]] = None
    created_at: Optional[datetime] = None


class TaskAttachmentCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1)
    size_bytes: int = Field(default=0, ge=0)
    kind: Optional[str] = None


class TaskAttachmentOut(ORMModel):
    id: str
    task_id: str
    filename: str
    url: str
    size_bytes: int = 0
    kind: Optional[str] = None
    uploaded_by: Optional[str] = None
    uploaded_by_name: Optional[str] = None
    created_at: Optional[datetime] = None


class DependencyOut(ORMModel):
    id: str
    task_id: str
    depends_on_task_id: str
    depends_on_title: Optional[str] = None
    kind: str
    created_at: Optional[datetime] = None


# --------------------------------------------------------------------------- Goals

class KeyResultCreate(BaseModel):
    title: str
    metric: Optional[str] = None
    unit: Optional[str] = None
    target: Optional[float] = None
    current: Optional[float] = 0
    owner_id: Optional[str] = None


class KeyResultUpdate(BaseModel):
    title: Optional[str] = None
    metric: Optional[str] = None
    unit: Optional[str] = None
    target: Optional[float] = None
    current: Optional[float] = None
    owner_id: Optional[str] = None


class KeyResultOut(ORMModel):
    id: str
    goal_id: str
    title: str
    metric: Optional[str] = None
    unit: Optional[str] = None
    target: Optional[float] = None
    current: Optional[float] = None
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GoalCreate(BaseModel):
    parent_goal_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    scope: str = Field(default="team", pattern="^(company|department|team|project|personal)$")
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[str] = Field(default="planned", pattern="^(planned|in_progress|completed|at_risk)$")
    priority: Optional[str] = Field(default="medium", pattern="^(low|medium|high|critical)$")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    key_results: Optional[List[KeyResultCreate]] = None


class GoalUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scope: Optional[str] = Field(default=None, pattern="^(company|department|team|project|personal)$")
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(planned|in_progress|completed|at_risk)$")
    priority: Optional[str] = Field(default=None, pattern="^(low|medium|high|critical)$")
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class GoalOut(ORMModel):
    id: str
    parent_goal_id: Optional[str] = None
    parent_name: Optional[str] = None
    name: str
    description: Optional[str] = None
    scope: str
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    status: str
    progress: float = 0
    priority: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    key_results_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --------------------------------------------------------------------------- Meetings

class AgendaItemCreate(BaseModel):
    title: str
    description: Optional[str] = None
    duration_minutes: Optional[int] = None


class MeetingCreate(BaseModel):
    title: str
    description: Optional[str] = None
    meeting_type: str = "team"
    status: Optional[str] = Field(default="scheduled", pattern="^(scheduled|in_progress|completed|cancelled)$")
    organizer_id: Optional[str] = None
    project_id: Optional[str] = None
    goal_id: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    attendee_ids: Optional[List[str]] = None
    agenda: Optional[List[AgendaItemCreate]] = None


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    meeting_type: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(scheduled|in_progress|completed|cancelled)$")
    organizer_id: Optional[str] = None
    project_id: Optional[str] = None
    goal_id: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None


class AttendeeOut(BaseModel):
    id: str
    employee_id: str
    name: str
    designation: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    status: str
    rsvp_at: Optional[datetime] = None


class MeetingOut(ORMModel):
    id: str
    title: str
    description: Optional[str] = None
    meeting_type: str
    status: str
    organizer_id: Optional[str] = None
    organizer_name: Optional[str] = None
    project_id: Optional[str] = None
    goal_id: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    transcript_summary: Optional[str] = None
    ai_summary: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AgendaItemOut(ORMModel):
    id: str
    meeting_id: str
    title: str
    description: Optional[str] = None
    sort_order: int = 0
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None


class ActionItemOut(ORMModel):
    id: str
    meeting_id: str
    title: str
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    due_date: Optional[datetime] = None
    status: str
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# --------------------------------------------------------------------------- Calendar

class CalendarEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    event_type: str = "event"
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    all_day: bool = False
    location: Optional[str] = None
    calendar_scope: str = "personal"
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    milestone_id: Optional[str] = None
    attendee_ids: Optional[List[str]] = None
    status: str = "confirmed"


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    event_type: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    all_day: Optional[bool] = None
    location: Optional[str] = None
    calendar_scope: Optional[str] = None
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    milestone_id: Optional[str] = None
    attendee_ids: Optional[List[str]] = None
    status: Optional[str] = None


class CalendarEventOut(ORMModel):
    id: str
    title: str
    description: Optional[str] = None
    event_type: str
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    all_day: bool = False
    location: Optional[str] = None
    calendar_scope: str
    department_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    milestone_id: Optional[str] = None
    created_by: Optional[str] = None
    creator_name: Optional[str] = None
    attendee_ids: Optional[List[str]] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --------------------------------------------------------------------------- Approvals

class ApprovalCreate(BaseModel):
    approval_type: str = "project"
    title: str
    description: Optional[str] = None
    approver_id: Optional[str] = None
    priority: str = "medium"
    due_at: Optional[datetime] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    policy_id: Optional[str] = None


class ApprovalDecide(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: Optional[str] = None


class ApprovalOut(ORMModel):
    id: str
    approval_type: str
    title: str
    description: Optional[str] = None
    requester_id: Optional[str] = None
    requester_name: Optional[str] = None
    approver_id: Optional[str] = None
    approver_name: Optional[str] = None
    status: str
    priority: str
    due_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    policy_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --------------------------------------------------------------------------- Risks

class RiskCreate(BaseModel):
    project_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: Optional[str] = Field(default="identified", pattern="^(identified|assessing|mitigating|accepted|monitoring|closed)$")
    probability: int = Field(default=2, ge=1, le=5)
    impact: int = Field(default=2, ge=1, le=5)
    owner_id: Optional[str] = None
    mitigation: Optional[str] = None
    due_at: Optional[datetime] = None
    detected_from: Optional[str] = None


class RiskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(identified|assessing|mitigating|accepted|monitoring|closed)$")
    probability: Optional[int] = Field(default=None, ge=1, le=5)
    impact: Optional[int] = Field(default=None, ge=1, le=5)
    owner_id: Optional[str] = None
    mitigation: Optional[str] = None
    due_at: Optional[datetime] = None


class RiskOut(ORMModel):
    id: str
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: str
    probability: int
    impact: int
    risk_score: int
    severity: Optional[str] = None
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    mitigation: Optional[str] = None
    due_at: Optional[datetime] = None
    detected_from: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
