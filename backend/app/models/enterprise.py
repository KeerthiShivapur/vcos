"""Enterprise Platform, Extensibility & Global Administration models (Phase 15).

Enterprise identity (SSO, SCIM, MFA, passkeys), the plugin & marketplace
ecosystem, the API gateway (keys, rate limits, versioning), integration
connections, monitoring/observability, the security center, compliance
management, licensing, feature flags and temporary/delegated access grants.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class IdentityProvider(Base, TimestampMixin):
    """Enterprise SSO provider: saml | oidc | oauth2 | ldap."""

    __tablename__ = "identity_providers"
    __table_args__ = (
        Index("ix_identity_providers_org", "organization_id"),
        UniqueConstraint("organization_id", "name", name="uq_identity_providers_org_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # saml|oidc|oauth2|ldap
    provider_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # per-type config: entity_id/sso_url/cert, issuer/client_id/client_secret,
    # server_url/bind_dn/base_dn ...
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class EnterpriseUser(Base, TimestampMixin):
    """Enterprise identity binding — external subject <-> VCOS user."""

    __tablename__ = "enterprise_users"
    __table_args__ = (
        Index("ix_enterprise_users_org", "organization_id"),
        Index("ix_enterprise_users_user", "user_id"),
        UniqueConstraint("organization_id", "external_subject", name="uq_enterprise_users_subject"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    external_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="saml")
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_method: Mapped[Optional[str]] = mapped_column(String(30))
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(64))
    passkeys: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ExternalGroup(Base, TimestampMixin):
    """External group from an identity provider (Entra ID, Okta, Google Workspace, etc.)."""
    
    __tablename__ = "external_groups"
    __table_args__ = (
        Index("ix_external_groups_org", "organization_id"),
        Index("ix_external_groups_provider", "identity_provider_id"),
        UniqueConstraint("identity_provider_id", "external_group_id", name="uq_external_groups_provider_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    identity_provider_id: Mapped[str] = mapped_column(
        ForeignKey("identity_providers.id", ondelete="CASCADE"), nullable=False
    )
    external_group_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    members_count: Mapped[int] = mapped_column(Integer, default=0)
    # Raw data from provider for audit/reconciliation
    raw_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # Sync metadata
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(20), default="pending")


class GroupRoleMapping(Base, TimestampMixin):
    """Mapping from external group to VCOS role with governance controls."""
    
    __tablename__ = "group_role_mappings"
    __table_args__ = (
        Index("ix_grm_org", "organization_id"),
        Index("ix_grm_group", "external_group_id"),
        Index("ix_grm_role", "role_id"),
        UniqueConstraint("organization_id", "external_group_id", "role_id", name="uq_group_role_mapping"),
        CheckConstraint(
            "mapping_state IN ('pending', 'active', 'revoked', 'expired', 'conflict')",
            name="ck_grm_state_valid"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    external_group_id: Mapped[str] = mapped_column(
        ForeignKey("external_groups.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    # Governance fields
    mapped_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    mapping_state: Mapped[str] = mapped_column(String(20), default="pending")
    # Justification for audit trail
    justification: Mapped[Optional[str]] = mapped_column(Text)
    # Optional expiry for temporary access
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Validation fields
    tenant_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    group_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Audit fields
    validated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text)


class Device(Base, TimestampMixin):
    """Trusted devices for MFA / passwordless flows."""

    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_user", "user_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), default="Unknown device")
    device_type: Mapped[str] = mapped_column(String(30), default="unknown")
    trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AuthenticationPolicy(Base, TimestampMixin):
    """Org-wide authentication policy (MFA, session, IP restrictions)."""

    __tablename__ = "authentication_policies"
    __table_args__ = (
        Index("ix_authentication_policies_org", "organization_id"),
        UniqueConstraint("organization_id", "name", name="uq_authentication_policies_org_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mfa_required: Mapped[bool] = mapped_column(Boolean, default=False)
    passkey_required: Mapped[bool] = mapped_column(Boolean, default=False)
    password_policy: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    session_timeout_minutes: Mapped[int] = mapped_column(Integer, default=480)
    ip_restrictions: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Plugin(Base, TimestampMixin):
    """Extensible plugin — installed into an organization from the marketplace."""

    __tablename__ = "plugins"
    __table_args__ = (
        Index("ix_plugins_org_status", "organization_id", "status"),
        UniqueConstraint("organization_id", "plugin_key", name="uq_plugins_org_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    plugin_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    author: Mapped[Optional[str]] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50), default="general")
    # draft|published|installed|disabled|uninstalled
    status: Mapped[str] = mapped_column(String(20), default="draft")
    sandbox: Mapped[bool] = mapped_column(Boolean, default=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    scan_status: Mapped[str] = mapped_column(String(20), default="pending")
    # permissions the plugin requests (permission codes)
    requested_permissions: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    settings: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    installed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class PluginVersion(Base, TimestampMixin):
    """Versioned plugin payloads with verification/scan state."""

    __tablename__ = "plugin_versions"
    __table_args__ = (Index("ix_plugin_versions_plugin", "plugin_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    plugin_id: Mapped[str] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(30), nullable=False)
    changelog: Mapped[Optional[str]] = mapped_column(Text)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    scan_status: Mapped[str] = mapped_column(String(20), default="pending")
    scan_report: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class MarketplaceItem(Base, TimestampMixin):
    """Plugin marketplace listing with ratings, reviews and safety state."""

    __tablename__ = "marketplace_items"
    __table_args__ = (
        Index("ix_marketplace_items_category", "category", "published"),
        UniqueConstraint("plugin_key", name="uq_marketplace_items_plugin_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    plugin_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), default="general")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    downloads: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    scanned: Mapped[bool] = mapped_column(Boolean, default=False)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    manifest: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class MarketplaceReview(Base, TimestampMixin):
    __tablename__ = "marketplace_reviews"
    __table_args__ = (
        Index("ix_marketplace_reviews_item", "item_id"),
        UniqueConstraint("item_id", "user_id", name="uq_marketplace_reviews_user"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("marketplace_items.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text)


class ApiKey(Base, TimestampMixin):
    """API gateway credentials. Only a hash is stored server-side."""

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_org_status", "organization_id", "status"),
        UniqueConstraint("key_hash", name="uq_api_keys_hash"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=120)
    status: Mapped[str] = mapped_column(String(20), default="active")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class IntegrationConnection(Base, TimestampMixin):
    """Enterprise integration connection (webhooks, apps, external services)."""

    __tablename__ = "integration_connections"
    __table_args__ = (
        Index("ix_integration_connections_org", "organization_id"),
        UniqueConstraint("organization_id", "name", name="uq_integration_connections_org_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), default="webhook")
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    auth_type: Mapped[str] = mapped_column(String(30), default="oauth2")
    # active|error|paused
    status: Mapped[str] = mapped_column(String(20), default="active")
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error: Mapped[Optional[str]] = mapped_column(Text)
    # OAuth2 credentials (encrypted at rest via application layer)
    access_token: Mapped[Optional[str]] = mapped_column(Text)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    refresh_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    oauth_scopes: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # OAuth state for CSRF protection during authorization flow
    oauth_state: Mapped[Optional[str]] = mapped_column(String(64))
    # Webhook configuration for providers that support push notifications
    webhook_url: Mapped[Optional[str]] = mapped_column(String(512))
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(128))
    webhook_events: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    webhook_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class SecurityEvent(Base, TimestampMixin):
    """Security center detections (failed logins, brute force, policy violations)."""

    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_org_status", "organization_id", "status"),
        Index("ix_security_events_type", "event_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    source_ip: Mapped[Optional[str]] = mapped_column(String(64))
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # open|reviewing|resolved
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolved_by: Mapped[Optional[str]] = mapped_column(String(32))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ComplianceControl(Base, TimestampMixin):
    """Compliance posture record per framework control."""

    __tablename__ = "compliance_controls"
    __table_args__ = (
        Index("ix_compliance_controls_org_framework", "organization_id", "framework"),
        UniqueConstraint("organization_id", "framework", "control", name="uq_compliance_controls_control"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    framework: Mapped[str] = mapped_column(String(30), nullable=False)
    control: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # pass|warn|fail|pending
    status: Mapped[str] = mapped_column(String(10), default="pending")
    evidence: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class OrganizationLicense(Base, TimestampMixin):
    """Enterprise license: plan, seats, entitlements, expiry."""

    __tablename__ = "organization_licenses"
    __table_args__ = (Index("ix_organization_licenses_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    plan: Mapped[str] = mapped_column(String(30), default="starter")
    seats: Mapped[int] = mapped_column(Integer, default=10)
    features: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class SystemMetric(Base, TimestampMixin):
    """Monitoring time series sample (health, latency, usage)."""

    __tablename__ = "system_metrics"
    __table_args__ = (
        Index("ix_system_metrics_org_name", "organization_id", "name"),
        Index("ix_system_metrics_recorded", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    tags: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScimGroup(Base, TimestampMixin):
    """SCIM 2.0 directory group mirroring external identity provider groups."""

    __tablename__ = "scim_groups"
    __table_args__ = (
        Index("ix_scim_groups_org", "organization_id"),
        UniqueConstraint("organization_id", "external_id", name="uq_scim_groups_external"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # external subjects of group members
    member_external_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class ObservabilityLog(Base, TimestampMixin):
    """Structured observability log line (metrics, spans, events)."""

    __tablename__ = "observability_logs"
    __table_args__ = (
        Index("ix_observability_logs_org_level", "organization_id", "level"),
        Index("ix_observability_logs_trace", "trace_id"),
        Index("ix_observability_logs_recorded", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    level: Mapped[str] = mapped_column(String(10), default="info")
    source: Mapped[str] = mapped_column(String(100), default="app")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64))
    span_id: Mapped[Optional[str]] = mapped_column(String(32))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccessGrant(Base, TimestampMixin):
    """Temporary / delegated access (PBAC) — grant a permission for a window."""

    __tablename__ = "access_grants"
    __table_args__ = (
        Index("ix_access_grants_org_status", "organization_id", "status"),
        Index("ix_access_grants_to", "granted_to_user"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    granted_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    granted_to_user: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    permission_code: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50))
    resource_id: Mapped[Optional[str]] = mapped_column(String(64))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="active")
