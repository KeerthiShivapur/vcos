"""Organization lifecycle service.

A company registers -> an organization + owner admin + system roles +
default settings + the owner's workspace are created atomically.
"""

import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import AuditLog
from app.models.organization import Organization, OrganizationSettings
from app.models.user import Session, User
from app.models.invitation import Invitation
from app.models.role import Role, UserRole
from app.models.workspace import Workspace
from app.schemas.auth import RegisterRequest
from app.core.security import hash_password
from app.services.audit_service import audit_service
from app.services.event_service import event_service
from app.services.permission_service import permission_service


def slugify(name: str, fallback: Optional[str] = None) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")
    if not slug:
        slug = fallback or "company"
    return slug[:100]


class OrganizationService:
    async def create_organization_and_owner(
        self,
        db: AsyncSession,
        *,
        payload: RegisterRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        """Atomic company registration: org + settings + roles + owner + workspace."""
        org = Organization(
            name=payload.organization_name,
            slug=payload.organization_slug,
            industry=payload.industry,
            country=payload.country,
            timezone=payload.timezone,
            currency=payload.currency,
        )
        db.add(org)
        await db.flush()

        settings = OrganizationSettings(organization_id=org.id)
        db.add(settings)

        roles = await permission_service.seed_org_roles(db, org.id)
        ceo_role = roles["ceo"]

        owner = User(
            organization_id=org.id,
            email=payload.email,
            username=payload.username,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
            status="active",
            role="ceo",
            timezone=payload.timezone,
            language="en",
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(owner)
        await db.flush()
        org.owner_id = owner.id

        db.add(UserRole(user_id=owner.id, role_id=ceo_role.id, organization_id=org.id))

        workspace = Workspace(organization_id=org.id, user_id=owner.id)
        db.add(workspace)

        from app.people.employee_service import employee_service

        await employee_service.create_for_user(
            db,
            organization_id=org.id,
            user_id=owner.id,
            email=owner.email,
            full_name=owner.full_name,
            designation="Founder & CEO",
        )

        await audit_service.log(
            db,
            organization_id=org.id,
            action="organization.created",
            actor_id=owner.id,
            actor_email=owner.email,
            resource_type="organization",
            resource_id=org.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"name": org.name, "slug": org.slug},
        )
        await event_service.emit(
            db, name="organization.created", actor_id=owner.id, organization_id=org.id,
            payload={"organization_id": org.id, "slug": org.slug},
        )
        await event_service.emit(
            db, name="user.created", actor_id=owner.id, organization_id=org.id,
            payload={"user_id": owner.id, "role": owner.role},
        )
        await db.flush()
        return {"organization": org, "owner": owner, "workspace": workspace}

    async def get_organization(self, db: AsyncSession, organization_id: str) -> Optional[Organization]:
        return await db.get(Organization, organization_id)

    async def update(
        self,
        db: AsyncSession,
        organization: Organization,
        data: dict,
        *,
        actor_id: str,
        actor_email: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Organization:
        for key, value in data.items():
            if value is not None and hasattr(organization, key):
                setattr(organization, key, value)
        await db.flush()
        await audit_service.log(
            db,
            organization_id=organization.id,
            action="organization.updated",
            actor_id=actor_id,
            actor_email=actor_email,
            resource_type="organization",
            resource_id=organization.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={k: v for k, v in data.items() if v is not None},
        )
        await event_service.emit(
            db, name="organization.updated", actor_id=actor_id, organization_id=organization.id,
            payload={"organization_id": organization.id},
        )
        return organization

    async def get_settings(self, db: AsyncSession, organization_id: str) -> Optional[OrganizationSettings]:
        result = await db.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def update_settings(
        self,
        db: AsyncSession,
        organization_id: str,
        data: dict,
        *,
        actor_id: str,
        actor_email: str,
    ) -> OrganizationSettings:
        settings = await self.get_settings(db, organization_id)
        if settings is None:
            settings = OrganizationSettings(organization_id=organization_id)
            db.add(settings)
            await db.flush()
        for key, value in data.items():
            if value is not None and hasattr(settings, key):
                setattr(settings, key, value)
        await audit_service.log(
            db,
            organization_id=organization_id,
            action="organization.settings.updated",
            actor_id=actor_id,
            actor_email=actor_email,
            resource_type="organization",
            resource_id=organization_id,
        )
        return settings

    async def stats(self, db: AsyncSession, organization_id: str) -> dict:
        org = await self.get_organization(db, organization_id)
        total_users = (await db.execute(select(func.count()).select_from(User).where(User.organization_id == organization_id))).scalar_one()
        active_users = (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(User.organization_id == organization_id, User.status == "active")
            )
        ).scalar_one()
        pending_invitations = (
            await db.execute(
                select(func.count())
                .select_from(Invitation)
                .where(Invitation.organization_id == organization_id, Invitation.status == "pending")
            )
        ).scalar_one()
        roles_count = (await db.execute(select(func.count()).select_from(Role).where(Role.organization_id == organization_id))).scalar_one()
        permissions_count = (
            await db.execute(
                select(func.count())
                .select_from(UserRole)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.organization_id == organization_id, Role.is_system.is_(False))
            )
        ).scalar_one()
        sessions_active = (
            await db.execute(
                select(func.count())
                .select_from(Session)
                .where(
                    Session.organization_id == organization_id,
                    Session.revoked_at.is_(None),
                    Session.expires_at > datetime.now(timezone.utc),
                )
            )
        ).scalar_one()
        from app.models.notification import Notification

        notifications_unread = (
            await db.execute(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.organization_id == organization_id,
                    Notification.is_read.is_(False),
                    Notification.is_archived.is_(False),
                )
            )
        ).scalar_one()
        audit_count = (await db.execute(select(func.count()).select_from(AuditLog).where(AuditLog.organization_id == organization_id))).scalar_one()
        return {
            "total_users": total_users,
            "active_users": active_users,
            "pending_invitations": pending_invitations,
            "roles_count": roles_count,
            "permissions_count": permissions_count,
            "sessions_active": sessions_active,
            "notifications_unread": notifications_unread,
            "audit_entries": audit_count,
            "created_at": org.created_at if org else None,
        }


organization_service = OrganizationService()
