"""Customer Portal service (Phase 12.11 — Secure External Access).

Portal users are external identities scoped to a single customer. They
authenticate with their own JWT (type=portal) and can only ever see data
for their customer — hard tenant + customer isolation.
"""

import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.core.timeutils import ensure_aware, utcnow
from app.customers.parse import to_dt
from app.events.event_bus import EventBus
from app.models.portal import PortalUser

logger = logging.getLogger("vcos.customers.portal")

_event_bus = EventBus()


class PortalService:
    async def create_user(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                          data: dict[str, Any], actor_id: Optional[str] = None) -> Optional[PortalUser]:
        from app.customers.customer_service import customer_service

        customer = await customer_service.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return None
        email = (data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            raise ValueError("a valid email is required")
        password = data.get("password") or "PortalPass123!"
        existing = (
            await db.execute(
                select(PortalUser).where(
                    PortalUser.organization_id == organization_id,
                    PortalUser.email == email,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError("a portal user with this email already exists")
        user = PortalUser(
            organization_id=organization_id, customer_id=customer_id,
            email=email,
            full_name=(data.get("full_name") or "").strip() or email.split("@")[0],
            password_hash=hash_password(password),
            portal_role=data.get("portal_role", "customer_viewer")
            if data.get("portal_role") in ("customer_admin", "customer_viewer") else "customer_viewer",
        )
        db.add(user)
        await db.flush()
        await _event_bus.publish(
            db, name="portal.user.created", organization_id=organization_id, actor_id=actor_id,
            payload={"portal_user_id": user.id, "customer_id": customer_id, "email": user.email},
            flush=False,
        )
        await db.flush()
        return user

    async def authenticate(self, db: AsyncSession, *, email: str, password: str) -> Optional[PortalUser]:
        user = (
            await db.execute(select(PortalUser).where(PortalUser.email == email.lower()))
        ).scalar_one_or_none()
        if user is None or user.status != "active":
            return None
        if not verify_password(password, user.password_hash):
            return None
        user.last_login_at = utcnow()
        await db.flush()
        return user

    async def get(self, db: AsyncSession, *, organization_id: str, portal_user_id: str) -> Optional[PortalUser]:
        return (
            await db.execute(
                select(PortalUser).where(
                    PortalUser.organization_id == organization_id, PortalUser.id == portal_user_id
                )
            )
        ).scalar_one_or_none()

    async def list_users(self, db: AsyncSession, *, organization_id: str, customer_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(PortalUser).where(
                PortalUser.organization_id == organization_id, PortalUser.customer_id == customer_id
            )
        )
        result = []
        for user in rows.scalars().all():
            result.append({
                "id": user.id, "customer_id": user.customer_id, "email": user.email,
                "full_name": user.full_name, "portal_role": user.portal_role, "status": user.status,
                "last_login_at": ensure_aware(user.last_login_at).isoformat() if user.last_login_at else None,
                "created_at": ensure_aware(user.created_at).isoformat() if user.created_at else None,
            })
        return result

    async def update_user(self, db: AsyncSession, *, organization_id: str, portal_user_id: str,
                          data: dict[str, Any]) -> Optional[PortalUser]:
        user = await self.get(db, organization_id=organization_id, portal_user_id=portal_user_id)
        if user is None:
            return None
        if data.get("full_name"):
            user.full_name = data["full_name"]
        if data.get("portal_role") in ("customer_admin", "customer_viewer"):
            user.portal_role = data["portal_role"]
        if data.get("status") in ("active", "suspended"):
            user.status = data["status"]
        if data.get("password"):
            user.password_hash = hash_password(data["password"])
        await db.flush()
        return user

    async def delete_user(self, db: AsyncSession, *, organization_id: str, portal_user_id: str) -> bool:
        user = await self.get(db, organization_id=organization_id, portal_user_id=portal_user_id)
        if user is None:
            return False
        await db.delete(user)
        await db.flush()
        return True

    # ------------------------------------------------------------------ portal-facing data (scoped to the portal user's customer)

    async def customer_data(self, db: AsyncSession, *, organization_id: str, portal_user_id: str) -> Optional[dict[str, Any]]:
        from app.customers.customer_service import customer_service

        user = await self.get(db, organization_id=organization_id, portal_user_id=portal_user_id)
        if user is None:
            return None
        customer = await customer_service.detail(db, organization_id=organization_id, customer_id=user.customer_id)
        if customer is None:
            return None
        return {
            "customer": customer,
            "portal_user": {
                "id": user.id, "email": user.email, "full_name": user.full_name,
                "portal_role": user.portal_role,
            },
        }

    async def raise_ticket(self, db: AsyncSession, *, organization_id: str, portal_user_id: str,
                           data: dict[str, Any]) -> Optional[dict[str, Any]]:
        from app.customers.support_service import support_service

        user = await self.get(db, organization_id=organization_id, portal_user_id=portal_user_id)
        if user is None:
            return None
        ticket = await support_service.create(
            db, organization_id=organization_id,
            data={**data, "customer_id": user.customer_id, "priority": data.get("priority", "medium")},
            via_portal=True, portal_user_id=user.id,
        )
        return {"id": ticket.id, "subject": ticket.subject, "status": ticket.status, "priority": ticket.priority}

    async def tickets(self, db: AsyncSession, *, organization_id: str, portal_user_id: str) -> list[dict[str, Any]]:
        from app.customers.support_service import support_service

        user = await self.get(db, organization_id=organization_id, portal_user_id=portal_user_id)
        if user is None:
            return []
        return await support_service.list_tickets(
            db, organization_id=organization_id, customer_id=user.customer_id)

    async def contracts(self, db: AsyncSession, *, organization_id: str, portal_user_id: str) -> list[dict[str, Any]]:
        from app.customers.contract_service import contract_service

        user = await self.get(db, organization_id=organization_id, portal_user_id=portal_user_id)
        if user is None:
            return []
        return await contract_service.list_contracts(
            db, organization_id=organization_id, customer_id=user.customer_id)


portal_service = PortalService()
