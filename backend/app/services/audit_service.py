import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import AuditLog


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, default=str)


class AuditService:
    """Records every important action. Nothing important is lost."""

    async def log(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        action: str,
        actor_id: Optional[str] = None,
        actor_email: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        severity: str = "info",
        outcome: str = "success",
    ) -> AuditLog:
        entry = AuditLog(
            organization_id=organization_id,
            actor_id=actor_id,
            actor_email=actor_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details_json=_json(details),
            severity=severity,
            outcome=outcome,
            created_at=_now(),
        )
        db.add(entry)
        await db.flush()
        return entry

    async def list_logs(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        page: int,
        page_size: int,
        action: Optional[str] = None,
        actor_id: Optional[str] = None,
        severity: Optional[str] = None,
        outcome: Optional[str] = None,
        resource_type: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> tuple[list[AuditLog], int]:
        filters = [AuditLog.organization_id == organization_id]
        if action:
            filters.append(AuditLog.action == action)
        if actor_id:
            filters.append(AuditLog.actor_id == actor_id)
        if severity:
            filters.append(AuditLog.severity == severity)
        if outcome:
            filters.append(AuditLog.outcome == outcome)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)
        if from_date:
            filters.append(AuditLog.created_at >= from_date)
        if to_date:
            filters.append(AuditLog.created_at <= to_date)

        total = (await db.execute(select(func.count()).select_from(AuditLog).where(*filters))).scalar_one()
        result = await db.execute(
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    def action_names(self) -> list[str]:
        return [
            "auth.login",
            "auth.login.failed",
            "auth.logout",
            "auth.logout.all",
            "auth.refresh",
            "auth.password.changed",
            "auth.password.reset",
            "auth.email.verified",
            "auth.session.revoked",
            "user.created",
            "user.invited",
            "user.status.updated",
            "user.profile.updated",
            "user.role.assigned",
            "role.created",
            "role.updated",
            "role.deleted",
            "organization.created",
            "organization.updated",
            "organization.settings.updated",
            "organization.branding.updated",
            "invitation.accepted",
            "invitation.revoked",
            "workspace.updated",
            "workspace.item.created",
            "workspace.item.updated",
            "workspace.item.deleted",
            "notification.read",
            "employee.created",
            "employee.transferred",
            "employee.promoted",
            "employee.status.changed",
            "employee.archived",
            "manager.changed",
            "department.created",
            "department.updated",
            "team.created",
            "team.updated",
            "team.member.added",
            "team.member.removed",
        ]


audit_service = AuditService()
