from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardSummary(BaseModel):
    organization_name: str
    organization_slug: str
    current_user: dict
    total_users: int
    active_users: int
    unread_notifications: int
    active_sessions: int
    pending_invitations: int
    roles_count: int
    recent_activity: List[dict]
    recent_notifications: List[dict]
    workspace: Optional[dict] = None
    my_tasks_open_count: int = 0
    pending_decisions_count: int = 0
    pending_approvals_count: int = 0


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard summary with counts and recent activity."""
    # Mock data for now - would be replaced with actual service calls
    return DashboardSummary(
        organization_name="Test Organization",
        organization_slug="test-org",
        current_user={
            "id": "user-1",
            "full_name": "Test User",
            "email": "test@example.com",
            "role": "admin",
            "job_title": "Administrator",
            "avatar_url": None,
        },
        total_users=42,
        active_users=38,
        unread_notifications=5,
        active_sessions=12,
        pending_invitations=3,
        roles_count=8,
        recent_activity=[
            {
                "id": "1",
                "action": "Created project",
                "actor_email": "user1@example.com",
                "severity": "info",
                "created_at": "2024-01-15T10:30:00Z",
            },
            {
                "id": "2",
                "action": "Approved leave request",
                "actor_email": "manager@example.com",
                "severity": "info",
                "created_at": "2024-01-15T09:15:00Z",
            },
        ],
        recent_notifications=[
            {
                "id": "1",
                "type": "task_assigned",
                "title": "New task assigned",
                "body": "You have been assigned to Project Alpha",
                "priority": "high",
                "is_read": False,
                "created_at": "2024-01-15T10:30:00Z",
            },
        ],
        my_tasks_open_count=7,
        pending_decisions_count=3,
        pending_approvals_count=2,
    )


@router.get("/metrics")
async def get_dashboard_metrics(
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard metrics for charts and visualizations."""
    return {
        "users_over_time": [
            {"date": "2024-01-01", "count": 10},
            {"date": "2024-01-08", "count": 15},
            {"date": "2024-01-15", "count": 22},
            {"date": "2024-01-22", "count": 35},
            {"date": "2024-01-29", "count": 42},
        ],
        "tasks_by_status": {
            "backlog": 12,
            "todo": 8,
            "in_progress": 18,
            "review": 5,
            "done": 42,
        },
        "projects_by_status": {
            "planning": 3,
            "active": 8,
            "on_hold": 2,
            "completed": 15,
        },
        "team_workload": [
            {"team": "Engineering", "utilization": 78, "capacity": 200},
            {"team": "Design", "utilization": 65, "capacity": 80},
            {"team": "Marketing", "utilization": 45, "capacity": 60},
            {"team": "Sales", "utilization": 82, "capacity": 120},
        ],
    }