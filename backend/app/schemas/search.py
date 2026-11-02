from typing import Any, List, Optional

from pydantic import BaseModel


class SearchResult(BaseModel):
    type: str
    id: str
    title: str
    subtitle: Optional[str] = None
    url: str
    snippet: Optional[str] = None
    score: float = 1.0
    metadata: dict[str, Any] = {}


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total: int
    took_ms: int


class DashboardSummary(BaseModel):
    organization_name: str
    organization_slug: str
    current_user: dict[str, Any]
    total_users: int
    active_users: int
    unread_notifications: int
    active_sessions: int
    pending_invitations: int
    roles_count: int
    my_tasks_open_count: int
    pending_decisions_count: int
    pending_approvals_count: int
    recent_activity: List[dict[str, Any]] = []
    recent_notifications: List[dict[str, Any]] = []
    workspace: Optional[dict[str, Any]] = None
    # Phase H �?" institutional learning
    learning_summary: Optional[dict[str, Any]] = None
