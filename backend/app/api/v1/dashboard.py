"""Home dashboard: a real, API-driven summary of the company's operating state."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.models.organization import Organization
from app.models.user import User
from app.schemas.search import DashboardSummary
from app.db.database import get_db
from app.services.audit_service import audit_service
from app.services.notification_service import notification_service
from app.services.organization_service import organization_service
from app.services.workspace_service import workspace_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    user: User = Depends(require_permission("dashboard:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    stats = await organization_service.stats(db, org.id)
    notifications, _ = await notification_service.list_notifications(
        db, user_id=user.id, organization_id=org.id, page=1, page_size=5
    )
    activity, _ = await audit_service.list_logs(
        db, organization_id=org.id, page=1, page_size=8
    )
    ws = await workspace_service.get_or_create(db, user_id=user.id, organization_id=org.id)
    workspace_items, _ = await workspace_service.list_items(
        db, user_id=user.id, organization_id=org.id, page=1, page_size=6
    )
    await db.commit()
    return DashboardSummary(
        organization_name=org.name,
        organization_slug=org.slug,
        current_user={
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "job_title": user.job_title,
            "avatar_url": user.avatar_url,
        },
        total_users=stats["total_users"],
        active_users=stats["active_users"],
        unread_notifications=stats["notifications_unread"],
        active_sessions=stats["sessions_active"],
        pending_invitations=stats["pending_invitations"],
        roles_count=stats["roles_count"],
        recent_activity=[
            {
                "id": a.id,
                "action": a.action,
                "actor_email": a.actor_email,
                "severity": a.severity,
                "created_at": a.created_at,
            }
            for a in activity
        ],
        recent_notifications=[
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "priority": n.priority,
                "is_read": n.is_read,
                "created_at": n.created_at,
            }
            for n in notifications
        ],
        workspace={
            "id": ws.id,
            "daily_goal": ws.daily_goal,
            "onboarding_completed": ws.onboarding_completed,
            "items": [
                {
                    "id": i.id,
                    "kind": i.kind,
                    "title": i.title,
                    "pinned": i.pinned,
                    "created_at": i.created_at,
                }
                for i in workspace_items
            ],
        },
    )
