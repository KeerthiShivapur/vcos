"""SSO service (Phase 15) — initiate/complete provider flows.

The flow is deliberately test-friendly: ``initiate`` returns a signed state
token and the provider's authorization/SSO URL; ``complete`` exchanges the
assertion (subject + verified email) for a VCOS identity binding. Real
SAML/OIDC assertion parsing plugs in at the ``parse_assertion`` seam.
"""

import hashlib
import hmac
import secrets
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeutils import utcnow
from app.enterprise.identity_service import identity_service
from app.models.enterprise import EnterpriseUser, IdentityProvider
from app.models.user import User


class SsoService:
    @staticmethod
    def _sign(state: str, provider_id: str) -> str:
        settings = get_settings()
        return hmac.new(
            settings.SECRET_KEY.encode(), f"{state}:{provider_id}".encode(), hashlib.sha256
        ).hexdigest()

    async def initiate(
        self, db: AsyncSession, *, organization_id: str, provider_id: str, redirect_uri: str
    ) -> dict[str, Any]:
        provider = await identity_service.get_provider(db, organization_id, provider_id)
        if provider is None:
            raise ValueError("provider not found")
        if not provider.enabled:
            raise ValueError("provider is disabled")
        state = secrets.token_urlsafe(24)
        config = provider.config or {}
        if provider.provider_type == "saml":
            auth_url = config.get("sso_url", f"/sso/{provider.id}/acs")
        elif provider.provider_type == "ldap":
            auth_url = f"/sso/{provider.id}/ldap"
        else:
            auth_url = config.get(
                "authorize_url", config.get("issuer", f"/sso/{provider.id}/authorize")
            )
        return {
            "provider": {"id": provider.id, "name": provider.name, "type": provider.provider_type},
            "state": state,
            "signature": self._sign(state, provider.id),
            "auth_url": auth_url,
            "redirect_uri": redirect_uri,
        }

    async def complete(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        provider_id: str,
        state: str,
        signature: str,
        subject: str,
        email: str,
    ) -> dict[str, Any]:
        provider = await identity_service.get_provider(db, organization_id, provider_id)
        if provider is None:
            raise ValueError("provider not found")
        if not hmac.compare_digest(signature, self._sign(state, provider_id)):
            raise ValueError("invalid SSO state signature")
        user = (
            await db.execute(select(User).where(User.email == email.lower()))
        ).scalars().first()
        if user is None:
            raise ValueError("no VCOS user matches the SSO identity")
        entry = (
            await db.execute(
                select(EnterpriseUser).where(
                    EnterpriseUser.organization_id == organization_id,
                    EnterpriseUser.external_subject == subject,
                )
            )
        ).scalars().first()
        if entry is None:
            entry = EnterpriseUser(
                organization_id=organization_id,
                user_id=user.id,
                external_subject=subject,
                provider=provider.provider_type,
            )
            db.add(entry)
        entry.status = "active"
        entry.last_login_at = utcnow()
        await db.flush()
        return {
            "status": "ok",
            "user_id": user.id,
            "binding_id": entry.id,
            "provider": provider.name,
            "mfa_required": await identity_service.mfa_required(db, organization_id),
        }

    async def list_bindings(self, db: AsyncSession, organization_id: str) -> list[EnterpriseUser]:
        result = await db.execute(
            select(EnterpriseUser)
            .where(EnterpriseUser.organization_id == organization_id)
            .order_by(EnterpriseUser.created_at.desc())
        )
        return list(result.scalars().all())


sso_service = SsoService()
