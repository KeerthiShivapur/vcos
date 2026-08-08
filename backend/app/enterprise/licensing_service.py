"""Licensing service (Phase 15).

Plan-based entitlements: seat counting, feature gates (SSO, SCIM, SAML,
plugins, compliance, monitoring), expiry handling and the license.changed
event. A default starter license is provisioned lazily per organization.
"""

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, is_expired, utcnow
from app.events.publisher import publish_event
from app.models.enterprise import OrganizationLicense
from app.models.user import User

PLANS: dict[str, dict[str, Any]] = {
    "starter": {
        "name": "Starter",
        "seats": 10,
        "features": ["dashboard"],
    },
    "professional": {
        "name": "Professional",
        "seats": 50,
        "features": ["sso", "api", "marketplace"],
    },
    "enterprise": {
        "name": "Enterprise",
        "seats": 500,
        "features": [
            "sso", "scim", "saml", "mfa", "api", "plugins", "marketplace",
            "integrations", "monitoring", "observability", "security",
            "compliance", "feature_flags", "ai",
        ],
    },
    "custom": {
        "name": "Custom",
        "seats": 5000,
        "features": [
            "sso", "scim", "saml", "mfa", "api", "plugins", "marketplace",
            "integrations", "monitoring", "observability", "security",
            "compliance", "feature_flags", "ai",
        ],
    },
}


class LicensingService:
    def plans(self) -> dict[str, Any]:
        return {code: plan for code, plan in PLANS.items()}

    async def get_license(
        self, db: AsyncSession, organization_id: str
    ) -> OrganizationLicense:
        license_row = (
            await db.execute(
                select(OrganizationLicense).where(
                    OrganizationLicense.organization_id == organization_id
                )
            )
        ).scalars().first()
        if license_row is None:
            plan = PLANS["starter"]
            license_row = OrganizationLicense(
                organization_id=organization_id,
                plan="starter",
                seats=plan["seats"],
                features=plan["features"],
                status="active",
                started_at=utcnow(),
            )
            db.add(license_row)
            await db.flush()
        return license_row

    async def change_plan(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        plan: str,
        actor_id: Optional[str] = None,
    ) -> Optional[OrganizationLicense]:
        if plan not in PLANS:
            raise ValueError(f"unknown plan: {plan}")
        license_row = await self.get_license(db, organization_id)
        previous = license_row.plan
        license_row.plan = plan
        license_row.seats = PLANS[plan]["seats"]
        license_row.features = PLANS[plan]["features"]
        license_row.status = "active"
        await publish_event(
            db,
            name="license.changed",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"previous_plan": previous, "plan": plan},
        )
        return license_row

    async def refresh(
        self, db: AsyncSession, *, organization_id: str
    ) -> dict[str, Any]:
        """Recompute seat usage and expiry state; keep the license consistent."""
        license_row = await self.get_license(db, organization_id)
        seats_used = (
            await db.execute(
                select(func.count(User.id)).where(
                    User.organization_id == organization_id,
                    User.status == "active",
                )
            )
        ).scalar_one()
        if license_row.expires_at and is_expired(license_row.expires_at):
            license_row.status = "expired"
        elif license_row.status == "expired":
            license_row.status = "active"
        return {
            "id": license_row.id,
            "plan": license_row.plan,
            "plan_name": PLANS[license_row.plan]["name"],
            "seats": license_row.seats,
            "seats_used": int(seats_used),
            "seats_remaining": max(0, license_row.seats - int(seats_used)),
            "features": list(license_row.features or []),
            "status": license_row.status,
            "expires_at": license_row.expires_at,
        }

    async def entitlement(
        self, db: AsyncSession, *, organization_id: str, feature: str
    ) -> bool:
        license_row = await self.get_license(db, organization_id)
        if license_row.status != "active":
            return False
        if license_row.expires_at and is_expired(license_row.expires_at):
            return False
        return feature in (license_row.features or [])

    async def ensure_feature(
        self, db: AsyncSession, *, organization_id: str, feature: str
    ) -> None:
        if not await self.entitlement(db, organization_id=organization_id, feature=feature):
            raise PermissionError(f"feature not included in the {feature} plan")


licensing_service = LicensingService()
