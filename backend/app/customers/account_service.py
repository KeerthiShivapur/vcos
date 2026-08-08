"""Account management service (Phase 12.10 — Account Management).

Every customer gets an account team: account manager, technical owner,
support owner, success manager and executive sponsor. The team shapes the
account dashboard and AI recommendations.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.event_bus import EventBus
from app.models.employee import Employee
from app.models.portal import AccountTeam

logger = logging.getLogger("vcos.customers.account")

_event_bus = EventBus()

ROLES = ["account_manager", "technical_owner", "support_owner", "success_manager", "executive_sponsor"]


class AccountService:
    async def add_member(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                         data: dict[str, Any]) -> Optional[dict[str, Any]]:
        from app.customers.customer_service import customer_service

        customer = await customer_service.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return None
        role = data.get("role", "account_manager")
        if role not in ROLES:
            raise ValueError(f"invalid account team role: {role}")
        employee_id = data.get("employee_id")
        if not employee_id:
            raise ValueError("employee_id is required")
        if data.get("is_primary"):
            await db.execute(
                AccountTeam.__table__.update()
                .where(AccountTeam.organization_id == organization_id,
                       AccountTeam.customer_id == customer_id,
                       AccountTeam.role == role)
                .values(is_primary=False)
            )
        member = (
            await db.execute(
                select(AccountTeam).where(
                    AccountTeam.organization_id == organization_id,
                    AccountTeam.customer_id == customer_id,
                    AccountTeam.employee_id == employee_id,
                    AccountTeam.role == role,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            member = AccountTeam(
                organization_id=organization_id, customer_id=customer_id,
                employee_id=employee_id, role=role, is_primary=bool(data.get("is_primary", False)),
            )
            db.add(member)
            await db.flush()
        else:
            if "is_primary" in data:
                member.is_primary = bool(data["is_primary"])
        await _event_bus.publish(
            db, name="account.team.updated", organization_id=organization_id,
            actor_id=data.get("actor_id"),
            payload={"customer_id": customer_id, "employee_id": employee_id, "role": role},
            flush=False,
        )
        employee = await db.get(Employee, employee_id)
        return {
            "id": member.id, "employee_id": employee_id,
            "employee_name": employee.full_name if employee else None,
            "role": role, "is_primary": member.is_primary,
        }

    async def list_team(self, db: AsyncSession, *, organization_id: str, customer_id: str) -> list[dict[str, Any]]:
        from app.customers.customer_service import customer_service

        customer = await customer_service.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            raise LookupError("Customer not found")
        return await customer_service._account_team(db, organization_id=organization_id, customer_id=customer_id)

    async def remove_member(self, db: AsyncSession, *, organization_id: str, customer_id: str, member_id: str) -> bool:
        member = (
            await db.execute(
                select(AccountTeam).where(
                    AccountTeam.organization_id == organization_id,
                    AccountTeam.customer_id == customer_id,
                    AccountTeam.id == member_id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            return False
        await db.delete(member)
        await db.flush()
        return True


account_service = AccountService()
