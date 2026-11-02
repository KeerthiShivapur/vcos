"""Enterprise Platform, Extensibility & Global Administration API (Phase 15).

One console for enterprise identity (SSO/SCIM/MFA/passkeys), the plugin and
marketplace ecosystem, the API gateway, integrations, monitoring &
observability, the security center, compliance, licensing, feature flags and
governed AI. Reads require enterprise:read; writes require the matching
area permission (identity:manage, plugins:manage, marketplace:manage,
api_keys:manage, integrations:manage, security:manage, compliance:manage,
licenses:manage, feature_flags:manage) or enterprise:manage. All endpoints
are scoped to the caller's organization.
"""

from typing import Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.core.timeutils import utcnow
from app.db.database import get_db
from app.enterprise.ai_service import ai_service
from app.enterprise.api_gateway import api_gateway_service
from app.enterprise.compliance_service import compliance_service
from app.enterprise.identity_service import identity_service
from app.enterprise.integration_service import integration_service
from app.enterprise.licensing_service import licensing_service
from app.enterprise.marketplace_service import marketplace_service
from app.enterprise.monitoring_service import monitoring_service
from app.enterprise.observability_service import observability_service
from app.enterprise.plugin_service import plugin_service
from app.enterprise.scim_service import scim_service
from app.enterprise.security_service import (
    BRUTE_FORCE_THRESHOLD,
    BRUTE_FORCE_WINDOW_MINUTES,
    EVENT_TYPES,
    security_service,
)
from app.enterprise.sso_service import sso_service
from app.models.enterprise import (
    ApiKey,
    ComplianceControl,
    IdentityProvider,
    IntegrationConnection,
    Plugin,
    SecurityEvent,
    SystemMetric,
)
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/enterprise", tags=["Enterprise"])


def _bad(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def _not_found(name: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{name} not found")


# ------------------------------------------------------------ identity (SSO/MFA)

@router.get("/identity/providers")
async def list_identity_providers(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    return await identity_service.list_providers(db, organization_id=org.id)


@router.post("/identity/providers", status_code=201)
async def create_identity_provider(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        provider = await identity_service.create_provider(
            db, organization_id=org.id, created_by=user.id, **payload
        )
        await db.commit()
        return provider
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.patch("/identity/providers/{provider_id}")
async def update_identity_provider(
    provider_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        provider = await identity_service.update_provider(
            db, organization_id=org.id, provider_id=provider_id, **payload
        )
    except ValueError as exc:
        raise _bad(str(exc)) from exc
    if provider is None:
        raise _not_found("Identity provider")
    await db.commit()
    return provider


@router.delete("/identity/providers/{provider_id}", status_code=204)
async def delete_identity_provider(
    provider_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await identity_service.delete_provider(db, org.id, provider_id):
        raise _not_found("Identity provider")
    await db.commit()


@router.post("/identity/mfa/enroll")
async def enroll_mfa(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    entry = await identity_service.enroll_mfa(
        db, organization_id=org.id, user_id=user.id
    )
    await db.commit()
    return {"mfa_method": entry.mfa_method, "mfa_secret": entry.mfa_secret, "mfa_enabled": entry.mfa_enabled}


@router.post("/identity/mfa/verify")
async def verify_mfa(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        entry = await identity_service.enable_mfa(
            db, organization_id=org.id, user_id=user.id, code=payload.get("code", "")
        )
        await db.commit()
        return {"mfa_enabled": entry.mfa_enabled}
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.post("/identity/passkeys")
async def register_passkey(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    entry = await identity_service.register_passkey(
        db,
        organization_id=org.id,
        user_id=user.id,
        credential_id=payload.get("credential_id", ""),
    )
    await db.commit()
    return {"passkeys": entry.passkeys}


@router.post("/identity/devices", status_code=201)
async def trust_device(
    payload: dict[str, Any],
    _org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    device = await identity_service.trust_device(
        db,
        user_id=user.id,
        name=payload.get("name", "New device"),
        device_type=payload.get("device_type", "unknown"),
    )
    await db.commit()
    return device


@router.get("/identity/devices")
async def list_devices(
    _org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    return await identity_service.list_devices(db, user_id=user.id)


@router.get("/identity/policies")
async def list_authentication_policies(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    policy = await identity_service.get_policy(db, org.id)
    return {"policy": policy}


@router.post("/identity/policies", status_code=201)
async def create_authentication_policy(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        policy = await identity_service.create_policy(db, organization_id=org.id, **payload)
        await db.commit()
        return policy
    except TypeError as exc:
        raise _bad(str(exc)) from exc


@router.get("/identity/bindings")
async def list_identity_bindings(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    return await sso_service.list_bindings(db, organization_id=org.id)


# ------------------------------------------------------------------------ SSO

@router.post("/sso/initiate")
async def sso_initiate(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await sso_service.initiate(
            db,
            organization_id=org.id,
            provider_id=payload.get("provider_id", ""),
            redirect_uri=payload.get("redirect_uri", "/"),
        )
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.post("/sso/complete")
async def sso_complete(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await sso_service.complete(
            db,
            organization_id=org.id,
            provider_id=payload.get("provider_id", ""),
            state=payload.get("state", ""),
            signature=payload.get("signature", ""),
            subject=payload.get("subject", ""),
            email=payload.get("email", ""),
        )
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.post("/sso")
async def sso_provider_assertion(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Shorthand SSO assertion endpoint (provider -> VCOS binding)."""
    try:
        result = await sso_service.complete(
            db,
            organization_id=org.id,
            provider_id=payload.get("provider_id", ""),
            state=payload.get("state", "direct"),
            signature=payload.get("signature", ""),
            subject=payload.get("subject", ""),
            email=payload.get("email", ""),
        )
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.post("/sso/assertion")
async def sso_assertion_completion(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Complete SSO from SAML assertion or OIDC ID token."""
    try:
        result = await sso_service.complete_from_assertion(
            db,
            organization_id=org.id,
            provider_id=payload.get("provider_id", ""),
            assertion=payload.get("assertion", ""),
            redirect_uri=payload.get("redirect_uri"),
        )
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


# ----------------------------------------------------------------------- SCIM

@router.post("/scim/users", status_code=201)
async def scim_create_user(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await scim_service.create_user(
            db,
            organization_id=org.id,
            user_name=payload.get("userName", ""),
            emails=payload.get("emails"),
            active=payload.get("active", True),
            external_id=payload.get("externalId"),
            attributes=payload,
        )
        await db.commit()
        return user
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/scim/users")
async def scim_list_users(
    filter: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    users = await scim_service.list_users(db, organization_id=org.id, filter_str=filter)
    return {"schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"], "totalResults": len(users), "Resources": users}


@router.get("/scim/users/{external_id}")
async def scim_get_user(
    external_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    user = await scim_service.get_user(db, organization_id=org.id, external_id=external_id)
    if user is None:
        raise _not_found("SCIM user")
    return user


@router.put("/scim/users/{external_id}")
@router.patch("/scim/users/{external_id}")
async def scim_update_user(
    external_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    user = await scim_service.update_user(
        db,
        organization_id=org.id,
        external_id=external_id,
        active=payload.get("active"),
        user_name=payload.get("userName"),
    )
    if user is None:
        raise _not_found("SCIM user")
    await db.commit()
    return user


@router.delete("/scim/users/{external_id}", status_code=204)
async def scim_delete_user(
    external_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await scim_service.delete_user(db, organization_id=org.id, external_id=external_id):
        raise _not_found("SCIM user")
    await db.commit()


@router.post("/scim/groups", status_code=201)
async def scim_upsert_group(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    members = [
        member.get("value")
        for member in (payload.get("members") or [])
        if member.get("value")
    ]
    group = await scim_service.upsert_group(
        db,
        organization_id=org.id,
        external_id=payload.get("externalId", payload.get("id", "")),
        display_name=payload.get("displayName", "Unnamed group"),
        member_external_ids=members,
        attributes=payload,
    )
    await db.commit()
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id": group.external_id,
        "displayName": group.display_name,
        "members": [{"value": value, "type": "User"} for value in group.member_external_ids or []],
    }


@router.get("/scim/groups")
async def scim_list_groups(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    groups = await scim_service.list_groups(db, organization_id=org.id)
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(groups),
        "Resources": [
            {
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
                "id": group.external_id,
                "displayName": group.display_name,
                "members": [{"value": value, "type": "User"} for value in group.member_external_ids or []],
            }
            for group in groups
        ],
    }


@router.delete("/scim/groups/{external_id}", status_code=204)
async def scim_delete_group(
    external_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("identity:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await scim_service.delete_group(db, organization_id=org.id, external_id=external_id):
        raise _not_found("SCIM group")
    await db.commit()


# --------------------------------------------------------------------- plugins

@router.get("/plugins")
async def list_plugins(
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    return await plugin_service.list_plugins(db, organization_id=org.id, status=status)


@router.post("/plugins", status_code=201)
async def create_plugin(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("plugins:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        plugin = await plugin_service.install(
            db,
            organization_id=org.id,
            plugin_key=payload.get("plugin_key", ""),
            name=payload.get("name", ""),
            manifest=payload.get("manifest", payload),
            created_by=user.id,
            actor_id=user.id,
        )
        await db.commit()
        return plugin
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/plugins/{plugin_id}")
async def get_plugin(
    plugin_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    plugin = await plugin_service.get(db, organization_id=org.id, plugin_id=plugin_id)
    if plugin is None:
        raise _not_found("Plugin")
    return plugin


@router.post("/plugins/{plugin_id}/enable")
async def enable_plugin(
    plugin_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("plugins:manage")),
    db: AsyncSession = Depends(get_db),
):
    plugin = await plugin_service.set_status(
        db, organization_id=org.id, plugin_id=plugin_id,
        status="installed", event_name="plugin.enabled", actor_id=user.id,
    )
    if plugin is None:
        raise _not_found("Plugin")
    await db.commit()
    return plugin


@router.post("/plugins/{plugin_id}/disable")
async def disable_plugin(
    plugin_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("plugins:manage")),
    db: AsyncSession = Depends(get_db),
):
    plugin = await plugin_service.set_status(
        db, organization_id=org.id, plugin_id=plugin_id,
        status="disabled", event_name="plugin.disabled", actor_id=user.id,
    )
    if plugin is None:
        raise _not_found("Plugin")
    await db.commit()
    return plugin


@router.post("/plugins/{plugin_id}/update")
async def update_plugin(
    plugin_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("plugins:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        plugin = await plugin_service.update(
            db,
            organization_id=org.id,
            plugin_id=plugin_id,
            version=payload.get("version", "2.0.0"),
            changelog=payload.get("changelog"),
            payload=payload.get("payload", {}),
            actor_id=user.id,
        )
    except ValueError as exc:
        raise _bad(str(exc)) from exc
    if plugin is None:
        raise _not_found("Plugin")
    await db.commit()
    return plugin


@router.patch("/plugins/{plugin_id}/settings")
async def update_plugin_settings(
    plugin_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("plugins:manage")),
    db: AsyncSession = Depends(get_db),
):
    plugin = await plugin_service.update_settings(
        db, organization_id=org.id, plugin_id=plugin_id,
        settings=payload.get("settings", {}),
    )
    if plugin is None:
        raise _not_found("Plugin")
    await db.commit()
    return plugin


@router.delete("/plugins/{plugin_id}", status_code=204)
async def remove_plugin(
    plugin_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("plugins:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await plugin_service.remove(
        db, organization_id=org.id, plugin_id=plugin_id, actor_id=user.id
    ):
        raise _not_found("Plugin")
    await db.commit()


# ------------------------------------------------------------------ marketplace

@router.get("/marketplace/items")
async def list_marketplace_items(
    category: Optional[str] = None,
    search: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    return await marketplace_service.list_items(
        db, category=category, search=search, published_only=True
    )


@router.get("/marketplace/items/{item_id}")
async def get_marketplace_item(
    item_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    item = await marketplace_service.get_item(db, item_id)
    if item is None:
        raise _not_found("Marketplace item")
    return item


@router.post("/marketplace/items", status_code=201)
async def publish_marketplace_item(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("marketplace:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await marketplace_service.publish(
            db,
            plugin_key=payload.get("plugin_key", ""),
            name=payload.get("name", ""),
            description=payload.get("description"),
            category=payload.get("category", "general"),
            price=payload.get("price", 0.0),
            version=payload.get("version", "1.0.0"),
            manifest=payload.get("manifest", {}),
            actor_id=user.id,
        )
        await db.commit()
        return item
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.post("/marketplace/items/{item_id}/reviews")
async def review_marketplace_item(
    item_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await marketplace_service.review(
            db,
            item_id=item_id,
            user_id=user.id,
            rating=payload.get("rating", 5),
            comment=payload.get("comment"),
        )
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.post("/marketplace/items/{item_id}/install", status_code=201)
async def install_marketplace_item(
    item_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("plugins:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        plugin = await marketplace_service.install(
            db, organization_id=org.id, item_id=item_id, actor_id=user.id
        )
        await db.commit()
        return plugin
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.patch("/marketplace/items/{item_id}")
async def update_marketplace_item(
    item_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("marketplace:manage")),
    db: AsyncSession = Depends(get_db),
):
    if "published" in payload:
        item = await marketplace_service.set_published(db, item_id=item_id, published=payload["published"])
        if item is None:
            raise _not_found("Marketplace item")
        await db.commit()
        return item
    raise _bad("only the published flag is editable on marketplace items")


# ------------------------------------------------------------------ API gateway

@router.get("/api-keys")
async def list_api_keys(
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("api_keys:manage")),
    db: AsyncSession = Depends(get_db),
):
    return await api_gateway_service.list_keys(db, organization_id=org.id, status=status)


@router.post("/api-keys", status_code=201)
async def create_api_key(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("api_keys:manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await api_gateway_service.create_key(
        db,
        organization_id=org.id,
        name=payload.get("name", "API key"),
        scopes=payload.get("scopes"),
        rate_limit_per_minute=payload.get("rate_limit_per_minute", 120),
        expires_at=payload.get("expires_at"),
        actor_id=user.id,
    )
    await db.commit()
    return result


@router.post("/api-keys/{key_id}/rotate")
async def rotate_api_key(
    key_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("api_keys:manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await api_gateway_service.rotate_key(
        db, organization_id=org.id, key_id=key_id, actor_id=user.id
    )
    if result is None:
        raise _not_found("API key")
    await db.commit()
    return result


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("api_keys:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await api_gateway_service.revoke_key(
        db, organization_id=org.id, key_id=key_id, actor_id=user.id
    ):
        raise _not_found("API key")
    await db.commit()


@router.get("/gateway/versions")
async def gateway_versions(
    _org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("enterprise:read")),
    _db: AsyncSession = Depends(get_db),
):
    return api_gateway_service.version_info()


@router.post("/gateway/check")
async def gateway_check(
    payload: dict[str, Any],
    _org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("api_keys:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Demo/proxy hook: authenticate a raw key and apply the rate limit."""
    identity = await api_gateway_service.authenticate(db, payload.get("api_key", ""))
    if identity is None:
        raise HTTPException(status_code=401, detail="invalid or revoked API key")
    rate = api_gateway_service.rate_limit_check(
        identity["key_id"], identity["rate_limit_per_minute"]
    )
    if not rate["allowed"]:
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    return {
        "organization_id": identity["organization_id"],
        "scopes": identity["scopes"],
        "rate_limit": rate,
    }


# ----------------------------------------------------------------- integrations

@router.get("/integrations")
async def list_integrations(
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(get_db),
):
    return await integration_service.list_connections(db, organization_id=org.id, status=status)


@router.post("/integrations", status_code=201)
async def create_integration(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        connection = await integration_service.create(
            db,
            organization_id=org.id,
            name=payload.get("name", ""),
            provider=payload.get("provider", ""),
            kind=payload.get("kind", "webhook"),
            config=payload.get("config", {}),
            auth_type=payload.get("auth_type", "oauth2"),
            actor_id=user.id,
        )
        await db.commit()
        return connection
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.post("/integrations/{connection_id}/test")
async def test_integration(
    connection_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await integration_service.test(
        db, organization_id=org.id, connection_id=connection_id
    )
    if result is None:
        raise _not_found("Integration")
    await db.commit()
    return result


@router.post("/integrations/{connection_id}/sync")
async def sync_integration(
    connection_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await integration_service.sync(
            db, organization_id=org.id, connection_id=connection_id, actor_id=user.id
        )
    except ValueError as exc:
        raise _bad(str(exc)) from exc
    if result is None:
        raise _not_found("Integration")
    await db.commit()
    return result


@router.patch("/integrations/{connection_id}")
async def update_integration(
    connection_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(get_db),
):
    connection = await integration_service.update(
        db, organization_id=org.id, connection_id=connection_id, **payload
    )
    if connection is None:
        raise _not_found("Integration")
    await db.commit()
    return connection


@router.delete("/integrations/{connection_id}", status_code=204)
async def delete_integration(
    connection_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await integration_service.remove(
        db, organization_id=org.id, connection_id=connection_id, actor_id=user.id
    ):
        raise _not_found("Integration")
    await db.commit()


# ---------------------------------------------------- OAuth2 for integrations

class OAuthUrlRequest(BaseModel):
    provider: str
    redirect_uri: str
    scopes: Optional[list[str]] = None


class OAuthUrlResponse(BaseModel):
    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    provider: str
    code: str
    state: str
    redirect_uri: str


class OAuthCallbackResponse(BaseModel):
    success: bool
    connection_id: Optional[str] = None
    detail: str
    provider: str


@router.post("/integrations/oauth/authorize", response_model=OAuthUrlResponse)
async def generate_oauth_authorize_url(
    request: OAuthUrlRequest,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Generate OAuth authorization URL for a provider."""
    import secrets
    from app.services.provider_adapters import GoogleWorkspaceAdapter, Microsoft365Adapter, SlackAdapter, GitHubAdapter, JiraAdapter
    
    provider = request.provider.lower()
    redirect_uri = request.redirect_uri
    scopes = request.scopes
    
    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Create a temporary connection record to store the state
    connection = await integration_service.create(
        db,
        organization_id=org.id,
        name=f"{provider.capitalize()} OAuth (pending)",
        provider=provider,
        kind="api",
        config={"redirect_uri": redirect_uri, "scopes": scopes or [], "base_url": "https://graph.microsoft.com/v1.0" if provider == "microsoft" else None},
        auth_type="oauth2",
    )
    
    # Store the state in the connection
    connection.oauth_state = state
    await db.flush()
    
    # Generate authorization URL using the appropriate adapter
    adapter_map = {
        "google": GoogleWorkspaceAdapter,
        "microsoft": Microsoft365Adapter,
        "slack": SlackAdapter,
        "github": GitHubAdapter,
        "jira": JiraAdapter,
    }
    
    adapter_class = adapter_map.get(provider)
    if not adapter_class:
        raise _bad(f"Unsupported provider: {provider}")
    
    # Create a mock instance for the adapter
    class MockInstance:
        def __init__(self, config):
            self.config = config
            self.credentials = {}
    
    mock_instance = MockInstance(config={"redirect_uri": redirect_uri, "scopes": scopes or []})
    adapter = adapter_class(mock_instance)
    
    try:
        auth_url = adapter.generate_oauth_url(redirect_uri, state, scopes)
    except Exception as e:
        raise _bad(f"Failed to generate OAuth URL: {str(e)}")
    
    return OAuthUrlResponse(authorization_url=auth_url, state=state)


@router.post("/integrations/oauth/callback", response_model=OAuthCallbackResponse)
async def handle_oauth_callback(
    request: OAuthCallbackRequest,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth callback and exchange code for tokens."""
    from app.services.provider_adapters import GoogleWorkspaceAdapter, Microsoft365Adapter, SlackAdapter, GitHubAdapter, JiraAdapter
    from sqlalchemy import select
    
    provider = request.provider.lower()
    code = request.code
    state = request.state
    redirect_uri = request.redirect_uri
    
    # Find the connection with the matching state
    result = await db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.organization_id == org.id,
            IntegrationConnection.oauth_state == state,
            IntegrationConnection.provider == provider,
        )
    )
    connection = result.scalars().first()
    
    if not connection:
        raise _not_found("No pending OAuth connection found for this state")
    
    # Create a mock instance for the adapter
    class MockInstance:
        def __init__(self, config, credentials):
            self.config = config
            self.credentials = credentials
    
    mock_instance = MockInstance(config=connection.config or {}, credentials=connection.credentials or {})
    
    adapter_map = {
        "google": GoogleWorkspaceAdapter,
        "microsoft": Microsoft365Adapter,
        "slack": SlackAdapter,
        "github": GitHubAdapter,
        "jira": JiraAdapter,
    }
    
    adapter_class = adapter_map.get(provider)
    if not adapter_class:
        raise _bad(f"Unsupported provider: {provider}")
    
    adapter = adapter_class(mock_instance)
    
    try:
        token_data = await adapter.handle_oauth_callback(code, state, redirect_uri)
    except Exception as e:
        connection.status = "error"
        connection.error = f"OAuth callback failed: {str(e)}"
        await db.commit()
        return OAuthCallbackResponse(success=False, detail=str(e), provider=provider)
    
    # Update connection with tokens
    connection.access_token = token_data.get("access_token")
    connection.refresh_token = token_data.get("refresh_token")
    connection.token_expires_at = token_data.get("expires_at")
    connection.refresh_token_expires_at = token_data.get("refresh_token_expires_at")
    connection.oauth_scopes = token_data.get("scope", "").split() if token_data.get("scope") else []
    connection.oauth_state = None
    connection.status = "active"
    connection.connected_at = utcnow()
    connection.error = None
    connection.name = f"{provider.capitalize()} Integration"
    
    await db.commit()
    
    return OAuthCallbackResponse(
        success=True,
        connection_id=connection.id,
        detail=f"Successfully connected to {provider.capitalize()}",
        provider=provider
    )


@router.post("/integrations/{connection_id}/refresh-token")
async def refresh_integration_token(
    connection_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Refresh the OAuth access token for an integration."""
    from app.services.provider_adapters import GoogleWorkspaceAdapter, Microsoft365Adapter, SlackAdapter, GitHubAdapter, JiraAdapter
    
    connection = await integration_service.get(db, org.id, connection_id)
    if not connection:
        raise _not_found("Integration not found")
    
    if not connection.refresh_token:
        raise _bad("No refresh token available")
    
    provider = connection.provider.lower()
    adapter_map = {
        "google": GoogleWorkspaceAdapter,
        "microsoft": Microsoft365Adapter,
        "slack": SlackAdapter,
        "github": GitHubAdapter,
        "jira": JiraAdapter,
    }
    
    adapter_class = adapter_map.get(provider)
    if not adapter_class:
        raise _bad(f"Unsupported provider: {provider}")
    
    class MockInstance:
        def __init__(self, credentials):
            self.credentials = credentials
    
    mock_instance = MockInstance(credentials={
        "refresh_token": connection.refresh_token,
        "client_id": (connection.config or {}).get("client_id"),
        "client_secret": (connection.config or {}).get("client_secret"),
    })
    
    adapter = adapter_class(mock_instance)
    
    try:
        success = await adapter._refresh_token(mock_instance.credentials)
    except Exception as e:
        raise _bad(f"Token refresh failed: {str(e)}")
    
    if not success:
        raise _bad("Failed to refresh token")
    
    # Update connection with new tokens
    connection.access_token = mock_instance.credentials.get("access_token")
    connection.refresh_token = mock_instance.credentials.get("refresh_token")
    connection.token_expires_at = mock_instance.credentials.get("expires_at")
    connection.refresh_token_expires_at = mock_instance.credentials.get("refresh_token_expires_at")
    connection.status = "active"
    connection.error = None
    
    await db.commit()
    
    return {"success": True, "detail": "Token refreshed successfully"}


@router.post("/integrations/{connection_id}/disconnect")
async def disconnect_integration(
    connection_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect an integration and revoke tokens if possible."""
    from app.services.provider_adapters import GoogleWorkspaceAdapter, Microsoft365Adapter, SlackAdapter, GitHubAdapter, JiraAdapter
    
    connection = await integration_service.get(db, org.id, connection_id)
    if not connection:
        raise _not_found("Integration not found")
    
    provider = connection.provider.lower()
    adapter_map = {
        "google": GoogleWorkspaceAdapter,
        "microsoft": Microsoft365Adapter,
        "slack": SlackAdapter,
        "github": GitHubAdapter,
        "jira": JiraAdapter,
    }
    
    adapter_class = adapter_map.get(provider)
    
    # Try to revoke tokens if adapter supports it
    if adapter_class and connection.access_token:
        class MockInstance:
            def __init__(self, credentials):
                self.credentials = credentials
        
        mock_instance = MockInstance(credentials={
            "access_token": connection.access_token,
            "refresh_token": connection.refresh_token,
            "client_id": (connection.config or {}).get("client_id"),
            "client_secret": (connection.config or {}).get("client_secret"),
        })
        
        adapter = adapter_class(mock_instance)
        if hasattr(adapter, 'revoke_token'):
            try:
                await adapter.revoke_token(mock_instance)
            except Exception:
                pass  # Best effort
    
    # Remove the connection
    await integration_service.remove(db, org.id, connection_id, actor_id=_user.id)
    await db.commit()
    
    return {"success": True, "detail": "Integration disconnected"}


# ---------------------------------------------------- monitoring & observability

@router.get("/monitoring/health")
async def monitoring_health(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("monitoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await monitoring_service.health(db, organization_id=org.id)


@router.get("/monitoring/metrics")
async def list_metrics(
    name: Optional[str] = None,
    limit: int = 100,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("monitoring:read")),
    db: AsyncSession = Depends(get_db),
):
    metrics = await monitoring_service.recent(
        db, organization_id=org.id, name=name, limit=limit
    )
    return metrics


@router.post("/monitoring/metrics", status_code=201)
async def ingest_metric(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("monitoring:read")),
    db: AsyncSession = Depends(get_db),
):
    metric = await monitoring_service.record_metric(
        db,
        organization_id=org.id,
        name=payload.get("name", ""),
        value=payload.get("value", 0.0),
        unit=payload.get("unit"),
        tags=payload.get("tags"),
        actor_id=user.id,
    )
    await db.commit()
    return metric


@router.get("/monitoring/alerts")
async def monitoring_alerts(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("monitoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await monitoring_service.alerts(db, organization_id=org.id)


@router.post("/observability/logs", status_code=201)
async def ingest_log(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("observability:read")),
    db: AsyncSession = Depends(get_db),
):
    log = await observability_service.ingest(
        db,
        organization_id=org.id,
        message=payload.get("message", ""),
        level=payload.get("level", "info"),
        source=payload.get("source", "app"),
        details=payload.get("details"),
        trace_id=payload.get("trace_id"),
        span_id=payload.get("span_id"),
    )
    await db.commit()
    return log


@router.get("/observability/logs")
async def query_logs(
    level: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("observability:read")),
    db: AsyncSession = Depends(get_db),
):
    return await observability_service.query(
        db,
        organization_id=org.id,
        level=level,
        source=source,
        search=search,
        limit=limit,
    )


@router.get("/observability/logs/{log_id}")
async def get_log(
    log_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("observability:read")),
    db: AsyncSession = Depends(get_db),
):
    log = await observability_service.get(db, log_id)
    if log is None or log.organization_id != org.id:
        raise _not_found("Log line")
    return log


@router.get("/observability/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("observability:read")),
    db: AsyncSession = Depends(get_db),
):
    return await observability_service.trace(db, trace_id)


# -------------------------------------------------------------------- security

@router.get("/security/events")
async def list_security_events(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("security:manage")),
    db: AsyncSession = Depends(get_db),
):
    return await security_service.list_events(
        db, organization_id=org.id, status=status, severity=severity
    )


@router.post("/security/events", status_code=201)
async def record_security_event(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:manage")),
    db: AsyncSession = Depends(get_db),
):
    event = await security_service.record(
        db,
        organization_id=org.id,
        event_type=payload.get("event_type", ""),
        severity=payload.get("severity", "medium"),
        title=payload.get("title"),
        actor_id=user.id,
        source_ip=payload.get("source_ip"),
        details=payload.get("details"),
    )
    await db.commit()
    return event


@router.post("/security/detect/failed-login")
async def detect_failed_login(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("security:manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await security_service.detect_failed_login(
        db,
        organization_id=org.id,
        email=payload.get("email", ""),
        source_ip=payload.get("source_ip", "0.0.0.0"),
    )
    await db.commit()
    return result


@router.post("/security/events/{event_id}/resolve")
async def resolve_security_event(
    event_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("security:manage")),
    db: AsyncSession = Depends(get_db),
):
    event = await security_service.resolve(
        db, organization_id=org.id, event_id=event_id, resolved_by=user.id
    )
    if event is None:
        raise _not_found("Security event")
    await db.commit()
    return event


@router.get("/security/rules")
async def security_rules(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("security:manage")),
    db: AsyncSession = Depends(get_db),
):
    return {
        "event_types": sorted(EVENT_TYPES.keys()),
        "event_type_descriptions": EVENT_TYPES,
        "brute_force_threshold": BRUTE_FORCE_THRESHOLD,
        "brute_force_window_minutes": BRUTE_FORCE_WINDOW_MINUTES,
    }


@router.post("/security/check-ip")
async def security_check_ip(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("security:manage")),
    db: AsyncSession = Depends(get_db),
):
    allowed = await security_service.enforce_ip(
        db, organization_id=org.id, ip=payload.get("ip", "")
    )
    await db.commit()
    return {"allowed": allowed, "ip": payload.get("ip")}


# ------------------------------------------------------------------ compliance

@router.get("/compliance/frameworks")
async def compliance_frameworks(
    _org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("compliance:manage")),
    _db: AsyncSession = Depends(get_db),
):
    return compliance_service.frameworks()


@router.get("/compliance/records")
async def list_compliance_records(
    framework: Optional[str] = None,
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("compliance:manage")),
    db: AsyncSession = Depends(get_db),
):
    return await compliance_service.list_records(
        db, organization_id=org.id, framework=framework, status=status
    )


@router.post("/compliance/records", status_code=201)
async def upsert_compliance_record(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("compliance:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        record = await compliance_service.upsert_control(
            db,
            organization_id=org.id,
            framework=payload.get("framework", ""),
            control=payload.get("control", ""),
            status=payload.get("status", "pending"),
            title=payload.get("title"),
            evidence=payload.get("evidence"),
            notes=payload.get("notes"),
            owner_id=payload.get("owner_id"),
            due_at=payload.get("due_at"),
            actor_id=user.id,
        )
        await db.commit()
        return record
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.patch("/compliance/records/{record_id}")
async def update_compliance_record(
    record_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("compliance:manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ComplianceControl).where(
            ComplianceControl.id == record_id,
            ComplianceControl.organization_id == org.id,
        )
    )
    record = result.scalars().first()
    if record is None:
        raise _not_found("Compliance record")
    for key, value in payload.items():
        if value is not None:
            setattr(record, key, value)
    await db.commit()
    return record


@router.get("/compliance/report")
async def compliance_report(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("compliance:manage")),
    db: AsyncSession = Depends(get_db),
):
    return await compliance_service.report(db, organization_id=org.id)


# -------------------------------------------------------------------- licensing

@router.get("/license")
async def get_license(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("licenses:manage")),
    db: AsyncSession = Depends(get_db),
):
    license_row = await licensing_service.get_license(db, organization_id=org.id)
    await db.flush()
    return license_row


@router.post("/license/refresh")
async def refresh_license(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("licenses:manage")),
    db: AsyncSession = Depends(get_db),
):
    state = await licensing_service.refresh(db, organization_id=org.id)
    await db.commit()
    return state


@router.patch("/license")
async def change_license_plan(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("licenses:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        license_row = await licensing_service.change_plan(
            db, organization_id=org.id, plan=payload.get("plan", ""), actor_id=user.id
        )
        await db.commit()
        return license_row
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/license/plans")
async def license_plans(
    _org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("licenses:manage")),
    _db: AsyncSession = Depends(get_db),
):
    return licensing_service.plans()


# ------------------------------------------------------------------------- AI

@router.get("/ai/models")
async def ai_models(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    return await ai_service.models(db, organization_id=org.id)


@router.get("/ai/usage")
async def ai_usage(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    return await ai_service.usage(db, organization_id=org.id)


@router.post("/ai/consent")
async def set_ai_consent(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("enterprise:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await ai_service.set_consent(
            db,
            organization_id=org.id,
            actor_id=user.id,
            scope=payload.get("scope", ""),
            granted=payload.get("granted", True),
        )
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/ai/memory")
async def ai_memory_settings(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("enterprise:read")),
    db: AsyncSession = Depends(get_db),
):
    return await ai_service.memory_settings(db, organization_id=org.id)


# ------------------------------------------------------------------- admin

@router.get("/admin/overview")
async def enterprise_overview(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("enterprise:manage")),
    db: AsyncSession = Depends(get_db),
):
    providers = (
        await db.execute(
            select(func.count(IdentityProvider.id)).where(IdentityProvider.organization_id == org.id)
        )
    ).scalar_one()
    plugins = (
        await db.execute(
            select(func.count(Plugin.id)).where(
                Plugin.organization_id == org.id, Plugin.status == "installed"
            )
        )
    ).scalar_one()
    keys = (
        await db.execute(
            select(func.count(ApiKey.id)).where(
                ApiKey.organization_id == org.id, ApiKey.status == "active"
            )
        )
    ).scalar_one()
    integrations = (
        await db.execute(
            select(func.count(IntegrationConnection.id)).where(
                IntegrationConnection.organization_id == org.id,
                IntegrationConnection.status == "active",
            )
        )
    ).scalar_one()
    open_security = (
        await db.execute(
            select(func.count(SecurityEvent.id)).where(
                SecurityEvent.organization_id == org.id,
                SecurityEvent.status == "open",
            )
        )
    ).scalar_one()
    metrics = (
        await db.execute(
            select(func.count(SystemMetric.id)).where(SystemMetric.organization_id == org.id)
        )
    ).scalar_one()
    license_state = await licensing_service.refresh(db, organization_id=org.id)
    return {
        "organization_id": org.id,
        "identity_providers": int(providers),
        "installed_plugins": int(plugins),
        "active_api_keys": int(keys),
        "active_integrations": int(integrations),
        "open_security_events": int(open_security),
        "metric_samples": int(metrics),
        "license": license_state,
    }
