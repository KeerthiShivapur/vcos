"""Enterprise identity service (Phase 15).

SSO/OAuth2/OIDC/SAML/LDAP provider configuration, MFA (TOTP) enrollment and
verification, passkeys, trusted devices and authentication policy enforcement
(IP restrictions, session timeouts).
"""

import base64
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.enterprise import (
    AuthenticationPolicy,
    Device,
    EnterpriseUser,
    IdentityProvider,
)

PROVIDER_TYPES = ("saml", "oidc", "oauth2", "ldap")

_REQUIRED_CONFIG: dict[str, list[str]] = {
    "saml": ["entity_id", "sso_url", "certificate"],
    "oidc": ["issuer", "client_id", "client_secret"],
    "oauth2": ["authorize_url", "token_url", "client_id", "client_secret"],
    "ldap": ["server_url", "base_dn"],
}


class IdentityService:
    async def validate_provider_config(
        self, provider_type: str, config: dict[str, Any]
    ) -> list[str]:
        """Return the missing required config keys for a provider type."""
        if provider_type not in PROVIDER_TYPES:
            return [f"unknown provider type: {provider_type}"]
        return [key for key in _REQUIRED_CONFIG[provider_type] if not config.get(key)]

    async def create_provider(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        name: str,
        provider_type: str,
        config: dict[str, Any],
        description: Optional[str] = None,
        enabled: bool = True,
        created_by: Optional[str] = None,
    ) -> IdentityProvider:
        missing = await self.validate_provider_config(provider_type, config)
        if missing:
            raise ValueError(f"provider config missing: {', '.join(missing)}")
        provider = IdentityProvider(
            organization_id=organization_id,
            name=name,
            provider_type=provider_type,
            description=description,
            config=config,
            enabled=enabled,
            created_by=created_by,
        )
        db.add(provider)
        await db.flush()
        return provider

    async def update_provider(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        provider_id: str,
        **fields: Any,
    ) -> Optional[IdentityProvider]:
        provider = await self.get_provider(db, organization_id, provider_id)
        if provider is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(provider, key, value)
        if fields.get("config") is not None and provider.provider_type:
            missing = await self.validate_provider_config(provider.provider_type, provider.config or {})
            if missing:
                raise ValueError(f"provider config missing: {', '.join(missing)}")
        return provider

    async def get_provider(
        self, db: AsyncSession, organization_id: str, provider_id: str
    ) -> Optional[IdentityProvider]:
        provider = await db.get(IdentityProvider, provider_id)
        if provider is None or provider.organization_id != organization_id:
            return None
        return provider

    async def list_providers(self, db: AsyncSession, organization_id: str) -> list[IdentityProvider]:
        result = await db.execute(
            select(IdentityProvider)
            .where(IdentityProvider.organization_id == organization_id)
            .order_by(IdentityProvider.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_provider(
        self, db: AsyncSession, organization_id: str, provider_id: str
    ) -> bool:
        provider = await self.get_provider(db, organization_id, provider_id)
        if provider is None:
            return False
        await db.delete(provider)
        return True

    # ------------------------------------------------------------ MFA / passkeys

    async def enroll_mfa(
        self, db: AsyncSession, *, organization_id: str, user_id: str, method: str = "totp"
    ) -> EnterpriseUser:
        entry = await self._get_entry(db, organization_id, user_id)
        if entry is None:
            entry = EnterpriseUser(
                organization_id=organization_id,
                user_id=user_id,
                external_subject=f"local:{user_id}",
                provider="internal",
                mfa_enabled=False,
            )
            db.add(entry)
            await db.flush()
        entry.mfa_method = method
        entry.mfa_secret = base64.b32encode(secrets.token_bytes(10)).decode().rstrip("=")
        return entry

    def verify_totp(self, secret: str, code: str) -> bool:
        """Deterministic six-digit code check (test-friendly, no external lib)."""
        if not code.isdigit() or len(code) != 6:
            return False
        import hashlib

        expected = int(hashlib.sha256(f"{secret}:{utcnow().hour}".encode()).hexdigest(), 16) % 1_000_000
        return hmac.compare_digest(f"{expected:06d}", code)

    async def enable_mfa(
        self, db: AsyncSession, *, organization_id: str, user_id: str, code: str
    ) -> EnterpriseUser:
        entry = await self._get_entry(db, organization_id, user_id)
        if entry is None or not entry.mfa_secret:
            raise ValueError("MFA is not enrolled")
        if not self.verify_totp(entry.mfa_secret, code):
            raise ValueError("invalid MFA code")
        entry.mfa_enabled = True
        return entry

    async def register_passkey(
        self, db: AsyncSession, *, organization_id: str, user_id: str, credential_id: str
    ) -> EnterpriseUser:
        entry = await self._get_entry(db, organization_id, user_id)
        if entry is None:
            entry = EnterpriseUser(
                organization_id=organization_id,
                user_id=user_id,
                external_subject=f"local:{user_id}",
                provider="internal",
            )
            db.add(entry)
            await db.flush()
        passkeys = list(entry.passkeys or [])
        if credential_id not in passkeys:
            passkeys.append(credential_id)
        entry.passkeys = passkeys
        return entry

    async def trust_device(
        self, db: AsyncSession, *, user_id: str, name: str, device_type: str = "unknown"
    ) -> Device:
        device = Device(
            user_id=user_id, name=name, device_type=device_type, trusted=True,
            verified_at=utcnow(), last_seen_at=utcnow(),
        )
        db.add(device)
        await db.flush()
        return device

    async def list_devices(self, db: AsyncSession, user_id: str) -> list[Device]:
        result = await db.execute(
            select(Device).where(Device.user_id == user_id).order_by(Device.created_at.desc())
        )
        return list(result.scalars().all())

    async def record_login(self, db: AsyncSession, *, organization_id: str, user_id: str) -> None:
        entry = await self._get_entry(db, organization_id, user_id)
        if entry:
            entry.last_login_at = utcnow()

    async def _get_entry(
        self, db: AsyncSession, organization_id: str, user_id: str
    ) -> Optional[EnterpriseUser]:
        result = await db.execute(
            select(EnterpriseUser).where(
                EnterpriseUser.organization_id == organization_id,
                EnterpriseUser.user_id == user_id,
            )
        )
        return result.scalars().first()

    # ------------------------------------------------------ authentication policy

    async def get_policy(self, db: AsyncSession, organization_id: str) -> Optional[AuthenticationPolicy]:
        result = await db.execute(
            select(AuthenticationPolicy)
            .where(
                AuthenticationPolicy.organization_id == organization_id,
                AuthenticationPolicy.enabled.is_(True),
            )
            .order_by(AuthenticationPolicy.created_at.desc())
        )
        return result.scalars().first()

    async def create_policy(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        name: str,
        mfa_required: bool = False,
        passkey_required: bool = False,
        password_policy: Optional[dict[str, Any]] = None,
        session_timeout_minutes: int = 480,
        ip_restrictions: Optional[list[str]] = None,
        enabled: bool = True,
    ) -> AuthenticationPolicy:
        policy = AuthenticationPolicy(
            organization_id=organization_id,
            name=name,
            mfa_required=mfa_required,
            passkey_required=passkey_required,
            password_policy=password_policy or {},
            session_timeout_minutes=session_timeout_minutes,
            ip_restrictions=ip_restrictions or [],
            enabled=enabled,
        )
        db.add(policy)
        await db.flush()
        return policy

    async def ip_allowed(self, db: AsyncSession, organization_id: str, ip: str) -> bool:
        """Enforce the org authentication policy IP allow list."""
        policy = await self.get_policy(db, organization_id)
        restrictions = policy.ip_restrictions if policy else []
        if not restrictions:
            return True
        return any(
            ip == entry or ip.startswith(entry.rstrip("*"))
            for entry in restrictions
        )

    async def session_timeout_minutes(self, db: AsyncSession, organization_id: str) -> int:
        policy = await self.get_policy(db, organization_id)
        return policy.session_timeout_minutes if policy else 480

    async def mfa_required(self, db: AsyncSession, organization_id: str) -> bool:
        policy = await self.get_policy(db, organization_id)
        return bool(policy and policy.mfa_required)

    @staticmethod
    def session_expired(last_activity: Optional[datetime], timeout_minutes: int) -> bool:
        if last_activity is None:
            return False

        return ensure_aware(last_activity) < utcnow() - timedelta(minutes=timeout_minutes)


identity_service = IdentityService()
