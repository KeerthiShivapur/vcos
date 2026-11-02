"""
Canonical Schemas - Universal Data Normalization Layer (Part 1: Enums & Base Models)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class EntityType(str, Enum):
    USER = "person"
    TEAM = "team"
    ORGANIZATION = "organization"
    PROJECT = "project"
    TASK = "task"
    ISSUE = "issue"
    REPOSITORY = "repository"
    PR = "pull_request"
    COMMIT = "commit"
    BRANCH = "branch"
    RELEASE = "release"
    CHANNEL = "channel"
    MESSAGE = "message"
    FILE = "file"
    CONTACT = "contact"
    EVENT = "event"
    DEAL = "deal"
    ACCOUNT = "account"
    LEAD = "lead"
    CAMPAIGN = "campaign"
    INVOICE = "invoice"
    BILL = "bill"
    PAYMENT = "payment"
    SUBSCRIPTION = "subscription"
    PRODUCT = "product"
    ORDER = "order"
    CUSTOMER = "customer"
    METRIC = "metric"
    LOG = "log"
    ALERT = "alert"
    INCIDENT = "incident"
    WORKFLOW = "workflow"
    PIPELINE = "pipeline"
    BUILD = "build"
    DEPLOYMENT = "deployment"
    CUSTOM = "custom"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    SUSPENDED = "suspended"
    DELETED = "deleted"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    BACKLOG = "backlog"


class IssueStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    URGENT = "urgent"


class DealStage(str, Enum):
    PROSPECTING = "prospecting"
    QUALIFICATION = "qualification"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"
    PARTIAL = "partial"


class CanonicalBaseModel(BaseModel):
    model_config = {
        "populate_by_name": True,
        "extra": "allow",
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None},
    }
    external_id: str = Field(..., description="External system's unique identifier")
    source_system: str = Field(..., description="Source system identifier")
    external_url: Optional[str] = Field(None, description="URL to entity in source system")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp in source system")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp in source system")
    deleted_at: Optional[datetime] = Field(None, description="Deletion timestamp if soft deleted")
    last_synced_at: datetime = Field(default_factory=datetime.utcnow, description="Last sync timestamp")
    sync_hash: Optional[str] = Field(None, description="Hash for change detection")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Original data from source")
    custom_fields: Dict[str, Any] = Field(default_factory=dict, description="Custom fields not in canonical schema")


class CanonicalUser(CanonicalBaseModel):
    email: str = Field(..., description="Primary email address")
    email_verified: bool = Field(False, description="Whether email is verified")
    emails: List[Dict[str, Any]] = Field(default_factory=list, description="All email addresses")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    full_name: Optional[str] = Field(None, description="Full name")
    display_name: Optional[str] = Field(None, description="Display name")
    username: Optional[str] = Field(None, description="Username/handle")
    phone: Optional[str] = Field(None, description="Phone number")
    phone_numbers: List[Dict[str, Any]] = Field(default_factory=list, description="All phone numbers")
    address: Optional[Dict[str, Any]] = Field(None, description="Address")
    title: Optional[str] = Field(None, description="Job title")
    department: Optional[str] = Field(None, description="Department")
    manager_id: Optional[str] = Field(None, description="Manager's external ID")
    employee_id: Optional[str] = Field(None, description="Employee ID")
    status: UserStatus = Field(UserStatus.ACTIVE, description="User status")
    is_admin: bool = Field(False, description="Whether user is admin")
    is_bot: bool = Field(False, description="Whether user is a bot/service account")
    mfa_enabled: bool = Field(False, description="Whether MFA is enabled")
    last_login_at: Optional[datetime] = Field(None, description="Last login timestamp")
    avatar_url: Optional[str] = Field(None, description="Avatar image URL")
    avatar_urls: Dict[str, str] = Field(default_factory=dict, description="Avatar URLs by size")
    team_ids: List[str] = Field(default_factory=list, description="Team external IDs")
    group_ids: List[str] = Field(default_factory=list, description="Group external IDs")
    role_ids: List[str] = Field(default_factory=list, description="Role external IDs")


class CanonicalTeam(CanonicalBaseModel):
    name: str = Field(..., description="Team name")
    description: Optional[str] = Field(None, description="Team description")
    display_name: Optional[str] = Field(None, description="Display name")
    handle: Optional[str] = Field(None, description="Team handle/slug")
    organization_id: Optional[str] = Field(None, description="Parent organization external ID")
    parent_team_id: Optional[str] = Field(None, description="Parent team external ID")
    member_ids: List[str] = Field(default_factory=list, description="Member external IDs")
    member_count: int = Field(0, description="Number of members")
    is_private: bool = Field(True, description="Whether team is private")
    is_archived: bool = Field(False, description="Whether team is archived")
    settings: Dict[str, Any] = Field(default_factory=dict, description="Team settings")
    admin_ids: List[str] = Field(default_factory=list, description="Admin external IDs")


class CanonicalOrganization(CanonicalBaseModel):
    name: str = Field(..., description="Organization name")
    display_name: Optional[str] = Field(None, description="Display name")
    domain: Optional[str] = Field(None, description="Primary domain")
    domains: List[str] = Field(default_factory=list, description="Verified domains")
    description: Optional[str] = Field(None, description="Organization description")
    industry: Optional[str] = Field(None, description="Industry")
    size: Optional[str] = Field(None, description="Company size")
    address: Optional[Dict[str, Any]] = Field(None, description="Headquarters address")
    timezone: Optional[str] = Field(None, description="Default timezone")
    locale: Optional[str] = Field(None, description="Default locale")
    settings: Dict[str, Any] = Field(default_factory=dict, description="Organization settings")
    features: List[str] = Field(default_factory=list, description="Enabled features")
    plan: Optional[str] = Field(None, description="Current plan")
    billing_email: Optional[str] = Field(None, description="Billing contact email")
    owner_id: Optional[str] = Field(None, description="Owner's external ID")
    admin_ids: List[str] = Field(default_factory=list, description="Admin external IDs")
    member_ids: List[str] = Field(default_factory=list, description="Member external IDs")


class CanonicalProject(CanonicalBaseModel):
    name: str = Field(..., description="Project name")
    key: Optional[str] = Field(None, description="Project key/short code")
    description: Optional[str] = Field(None, description="Project description")
    organization_id: Optional[str] = Field(None, description="Organization external ID")
    team_id: Optional[str] = Field(None, description="Team external ID")
    parent_project_id: Optional[str] = Field(None, description="Parent project external ID")
    status: str = Field("active", description="Project status")
    visibility: str = Field("private", description="Visibility level")
    start_date: Optional[datetime] = Field(None, description="Project start date")
    due_date: Optional[datetime] = Field(None, description="Project due date")
    completed_at: Optional[datetime] = Field(None, description="Completion date")
    owner_id: Optional[str] = Field(None, description="Project owner external ID")
    lead_id: Optional[str] = Field(None, description="Project lead external ID")
    member_ids: List[str] = Field(default_factory=list, description="Member external IDs")
    settings: Dict[str, Any] = Field(default_factory=dict, description="Project settings")
    custom_fields: Dict[str, Any] = Field(default_factory=dict, description="Custom fields")


class CanonicalTask(CanonicalBaseModel):
    title: str = Field(..., description="Task title")
    description: Optional[str] = Field(None, description="Task description")
    project_id: Optional[str] = Field(None, description="Project external ID")
    project_key: Optional[str] = Field(None, description="Project key")
    status: str = Field("todo", description="Task status")
    priority: str = Field("medium", description="Task priority")
    assignee_id: Optional[str] = Field(None, description="Assignee external ID")
    reporter_id: Optional[str] = Field(None, description="Reporter external ID")
    assignee_ids: List[str] = Field(default_factory=list, description="Multiple assignees")
    parent_task_id: Optional[str] = Field(None, description="Parent task external ID")
    subtask_ids: List[str] = Field(default_factory=list, description="Subtask external IDs")
    depends_on_ids: List[str] = Field(default_factory=list, description="Task dependencies")
    blocks_ids: List[str] = Field(default_factory=list, description="Tasks blocked by this")
    start_date: Optional[datetime] = Field(None, description="Planned start date")
    due_date: Optional[datetime] = Field(None, description="Due date")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    estimate: Optional[float] = Field(None, description="Time estimate (hours)")
    time_spent: Optional[float] = Field(None, description="Time spent (hours)")
    time_remaining: Optional[float] = Field(None, description="Time remaining (hours)")
    labels: List[str] = Field(default_factory=list, description="Labels/tags")
    components: List[str] = Field(default_factory=list, description="Components")
    progress: int = Field(0, ge=0, le=100, description="Completion percentage")


class CanonicalIssue(CanonicalBaseModel):
    title: str = Field(..., description="Issue title")
    description: Optional[str] = Field(None, description="Issue description")
    project_id: Optional[str] = Field(None, description="Project external ID")
    project_key: Optional[str] = Field(None, description="Project key")
    issue_number: Optional[int] = Field(None, description="Issue number in project")
    issue_key: Optional[str] = Field(None, description="Issue key (e.g., PROJ-123)")
    status: str = Field("open", description="Issue status")
    issue_type: str = Field("bug", description="Issue type (bug, feature, task, etc.)")
    priority: str = Field("medium", description="Issue priority")
    severity: Optional[str] = Field(None, description="Severity level")
    assignee_id: Optional[str] = Field(None, description="Assignee external ID")
    reporter_id: Optional[str] = Field(None, description="Reporter external ID")
    resolution: Optional[str] = Field(None, description="Resolution reason")
    resolved_at: Optional[datetime] = Field(None, description="Resolution timestamp")
    resolved_by_id: Optional[str] = Field(None, description="Resolver external ID")
    parent_issue_id: Optional[str] = Field(None, description="Parent issue external ID")
    subtask_ids: List[str] = Field(default_factory=list, description="Subtask external IDs")
    depends_on_ids: List[str] = Field(default_factory=list, description="Depends on issues")
    blocked_by_ids: List[str] = Field(default_factory=list, description="Blocked by issues")
    blocks_ids: List[str] = Field(default_factory=list, description="Blocks issues")
    duplicate_of_id: Optional[str] = Field(None, description="Duplicate of issue")
    labels: List[str] = Field(default_factory=list, description="Labels")
    components: List[str] = Field(default_factory=list, description="Components")
    fix_versions: List[str] = Field(default_factory=list, description="Fix versions")
    affects_versions: List[str] = Field(default_factory=list, description="Affected versions")
    due_date: Optional[datetime] = Field(None, description="Due date")
    resolved_at: Optional[datetime] = Field(None, description="Resolution date")


class CanonicalRepository(CanonicalBaseModel):
    name: str = Field(..., description="Repository name")
    full_name: Optional[str] = Field(None, description="Full name (owner/repo)")
    description: Optional[str] = Field(None, description="Repository description")
    owner_id: Optional[str] = Field(None, description="Owner external ID (user or org)")
    owner_login: Optional[str] = Field(None, description="Owner login")
    organization_id: Optional[str] = Field(None, description="Organization external ID")
    private: bool = Field(False, description="Whether repository is private")
    archived: bool = Field(False, description="Whether repository is archived")
    disabled: bool = Field(False, description="Whether repository is disabled")
    fork: bool = Field(False, description="Whether repository is a fork")
    default_branch: str = Field("main", description="Default branch")
    language: Optional[str] = Field(None, description="Primary language")
    languages: Dict[str, int] = Field(default_factory=dict, description="Languages with byte counts")
    stars_count: int = Field(0, description="Stars count")
    forks_count: int = Field(0, description="Forks count")
    watchers_count: int = Field(0, description="Watchers count")
    open_issues_count: int = Field(0, description="Open issues count")
    size: int = Field(0, description="Repository size (KB)")
    topics: List[str] = Field(default_factory=list, description="Repository topics")
    license: Optional[str] = Field(None, description="License identifier")
    clone_url: Optional[str] = Field(None, description="Clone URL")
    ssh_url: Optional[str] = Field(None, description="SSH URL")
    html_url: Optional[str] = Field(None, description="HTML URL")
    default_branch_protected: bool = Field(False, description="Default branch protected")


class CanonicalPullRequest(CanonicalBaseModel):
    title: str = Field(..., description="PR title")
    body: Optional[str] = Field(None, description="PR description")
    number: int = Field(..., description="PR number")
    repository_id: Optional[str] = Field(None, description="Repository external ID")
    repository_full_name: Optional[str] = Field(None, description="Repository full name")
    head_branch: str = Field(..., description="Head branch name")
    head_sha: str = Field(..., description="Head commit SHA")
    base_branch: str = Field(..., description="Base branch name")
    base_sha: Optional[str] = Field(None, description="Base commit SHA")
    state: str = Field("open", description="PR state (open, closed, merged)")
    draft: bool = Field(False, description="Whether PR is draft")
    merged: bool = Field(False, description="Whether PR is merged")
    merged_at: Optional[datetime] = Field(None, description="Merge timestamp")
    merged_by_id: Optional[str] = Field(None, description="Merger external ID")
    author_id: Optional[str] = Field(None, description="Author external ID")
    assignee_ids: List[str] = Field(default_factory=list, description="Assignee external IDs")
    reviewer_ids: List[str] = Field(default_factory=list, description="Reviewer external IDs")
    review_status: str = Field("pending", description="Review status")
    approved_by_ids: List[str] = Field(default_factory=list, description="Approvers external IDs")
    changes_requested_by_ids: List[str] = Field(default_factory=list, description="Changes requested by")
    mergeable: Optional[bool] = Field(None, description="Whether PR is mergeable")
    merge_commit_sha: Optional[str] = Field(None, description="Merge commit SHA")
    checks_passing: bool = Field(False, description="All checks passing")
    additions: int = Field(0, description="Lines added")
    deletions: int = Field(0, description="Lines deleted")
    changed_files: int = Field(0, description="Files changed")
    commits_count: int = Field(0, description="Number of commits")
    comments_count: int = Field(0, description="Number of comments")
    review_comments_count: int = Field(0, description="Number of review comments")


class CanonicalCommit(CanonicalBaseModel):
    sha: str = Field(..., description="Commit SHA")
    message: str = Field(..., description="Commit message")
    repository_id: Optional[str] = Field(None, description="Repository external ID")
    author_name: str = Field(..., description="Author name")
    author_email: str = Field(..., description="Author email")
    author_id: Optional[str] = Field(None, description="Author external ID")
    author_date: datetime = Field(..., description="Author date")
    committer_name: Optional[str] = Field(None, description="Committer name")
    committer_email: Optional[str] = Field(None, description="Committer email")
    committer_id: Optional[str] = Field(None, description="Committer external ID")
    committer_date: Optional[datetime] = Field(None, description="Committer date")
    tree_sha: Optional[str] = Field(None, description="Tree SHA")
    parent_shas: List[str] = Field(default_factory=list, description="Parent commit SHAs")
    additions: int = Field(0, description="Lines added")
    deletions: int = Field(0, description="Lines deleted")
    files_changed: int = Field(0, description="Files changed")
    verified: bool = Field(False, description="Whether commit is verified")
    signature: Optional[str] = Field(None, description="GPG signature")
    files: List[Dict[str, Any]] = Field(default_factory=list, description="Changed files")


# Export key types
__all__ = [
    "EntityType",
    "UserStatus",
    "TaskStatus",
    "IssueStatus",
    "Priority",
    "DealStage",
    "InvoiceStatus",
    "CanonicalBaseModel",
    "CanonicalUser",
    "CanonicalTeam",
    "CanonicalOrganization",
    "CanonicalProject",
    "CanonicalTask",
    "CanonicalIssue",
    "CanonicalRepository",
    "CanonicalPullRequest",
    "CanonicalCommit",
]