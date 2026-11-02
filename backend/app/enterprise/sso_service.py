"""SSO service (Phase 15) — initiate/complete provider flows.

The flow is deliberately test-friendly: ``initiate`` returns a signed state
token and the provider's authorization/SSO URL; ``complete`` exchanges the
assertion (subject + verified email) for a VCOS identity binding. Real
SAML/OIDC assertion parsing is implemented for Entra ID, Okta, Google, and generic OIDC/SAML.
"""

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from jose import jwt as jose_jwt
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

    async def complete_from_assertion(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        provider_id: str,
        assertion: str,
        redirect_uri: Optional[str] = None,
    ) -> dict[str, Any]:
        """Complete SSO from a SAML assertion or OIDC ID token."""
        provider = await identity_service.get_provider(db, organization_id, provider_id)
        if provider is None:
            raise ValueError("provider not found")
        if not provider.enabled:
            raise ValueError("provider is disabled")

        config = provider.config or {}
        
        if provider.provider_type == "saml":
            subject, email = await self._parse_saml_assertion(assertion, config)
        elif provider.provider_type == "oidc":
            subject, email = await self._parse_oidc_id_token(assertion, config)
        else:
            raise ValueError(f"assertion parsing not supported for provider type: {provider.provider_type}")

        # Complete the SSO flow with parsed subject and email
        return await self.complete(
            db,
            organization_id=organization_id,
            provider_id=provider_id,
            state="assertion",
            signature="assertion",
            subject=subject,
            email=email,
        )

    async def _parse_saml_assertion(self, assertion: str, config: dict) -> tuple[str, str]:
        """Parse SAML assertion to extract subject (NameID) and email."""
        try:
            # Decode base64 assertion if needed
            if not assertion.startswith("<"):
                assertion = base64.b64decode(assertion).decode("utf-8")
            
            # Parse XML (simplified - production should use proper XML parsing with namespace handling)
            import xml.etree.ElementTree as ET
            root = ET.fromstring(assertion)
            
            # Define namespaces
            ns = {
                "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
                "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
            }
            
            # Extract NameID (subject)
            name_id = root.find(".//saml:NameID", ns)
            subject = name_id.text if name_id is not None else ""
            
            # Extract email from AttributeStatement
            email = ""
            for attr in root.findall(".//saml:Attribute", ns):
                if attr.get("Name") in ("email", "Email", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"):
                    value = attr.find("saml:AttributeValue", ns)
                    if value is not None:
                        email = value.text
                        break
            
            if not subject:
                raise ValueError("SAML assertion missing NameID")
            if not email:
                raise ValueError("SAML assertion missing email attribute")
            
            return subject, email.lower()
        except Exception as e:
            raise ValueError(f"Failed to parse SAML assertion: {e}")

    async def _parse_oidc_id_token(self, id_token: str, config: dict) -> tuple[str, str]:
        """Parse OIDC ID token to extract subject and email."""
        try:
            client_id = config.get("client_id")
            issuer = config.get("issuer")
            
            # Get JWKS for token verification
            jwks_url = f"{issuer}/.well-known/jwks.json"
            async with httpx.AsyncClient() as client:
                jwks_response = await client.get(jwks_url)
                jwks_response.raise_for_status()
                jwks = jwks_response.json()
            
            # Get the key ID from token header
            header = jose_jwt.get_unverified_header(id_token)
            kid = header.get("kid")
            
            # Find the matching key
            key = None
            for jwk in jwks.get("keys", []):
                if jwk.get("kid") == kid:
                    key = jose_jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
                    break
            
            if not key:
                raise ValueError("Unable to find matching JWK for token verification")
            
            # Verify and decode token
            claims = jose_jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=client_id,
                issuer=issuer,
            )
            
            subject = claims.get("sub")
            email = claims.get("email") or claims.get("preferred_username") or ""
            
            if not subject:
                raise ValueError("ID token missing subject (sub) claim")
            if not email:
                raise ValueError("ID token missing email claim")
            
            return subject, email.lower()
        except Exception as e:
            raise ValueError(f"Failed to parse OIDC ID token: {e}")

    async def list_bindings(self, db: AsyncSession, organization_id: str) -> list[EnterpriseUser]:
        result = await db.execute(
            select(EnterpriseUser)
            .where(EnterpriseUser.organization_id == organization_id)
            .order_by(EnterpriseUser.created_at.desc())
        )
        return list(result.scalars().all())


sso_service = SsoService()
