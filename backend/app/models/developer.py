"""Phase 18 — Developer Ecosystem, AI Agent Ecosystem & Global Innovation Platform models.

The ecosystem models cover the developer platform: developers and their
applications, API keys, webhook endpoints and deliveries, usage records,
marketplace installs, AI agents, themes and certification credentials.

The extension *marketplace* reuses the Phase 15 enterprise MarketplaceItem /
MarketplaceReview tables (they already carry ratings, reviews, downloads and
verification state); this module adds the developer-side entities that feed
them.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
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


class Developer(Base, TimestampMixin):
    """A registered developer on the VCOS ecosystem platform (Phase 18.1)."""

    __tablename__ = "developers"
    __table_args__ = (
        UniqueConstraint("email", name="uq_developers_email"),
        UniqueConstraint("developer_key", name="uq_developers_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    developer_key: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    website: Mapped[Optional[str]] = mapped_column(String(500))
    country: Mapped[Optional[str]] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | active | suspended
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # links the developer to a VCOS user account when provided
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )


class DeveloperApplication(Base, TimestampMixin):
    """A developer's application: plugin, AI agent, widget, theme or app (Phase 18.1)."""

    __tablename__ = "developer_applications"
    __table_args__ = (
        Index("ix_developer_applications_dev", "developer_id"),
        Index("ix_developer_applications_status", "status"),
        UniqueConstraint("application_key", name="uq_developer_applications_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    developer_id: Mapped[str] = mapped_column(
        ForeignKey("developers.id", ondelete="CASCADE"), nullable=False
    )
    application_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    app_type: Mapped[str] = mapped_column(String(30), default="app")  # app | plugin | agent | widget | theme | workflow_pack | integration
    description: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(30), default="0.1.0")
    # draft | published | suspended | archived
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # permission codes the app requests
    scopes: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # webhook/extension registration points
    endpoints: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    settings: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class DeveloperApiKey(Base, TimestampMixin):
    """API credentials for a developer application. Only a hash is stored."""

    __tablename__ = "developer_api_keys"
    __table_args__ = (
        Index("ix_developer_api_keys_app", "application_id"),
        UniqueConstraint("key_hash", name="uq_developer_api_keys_hash"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    developer_id: Mapped[str] = mapped_column(
        ForeignKey("developers.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[str] = mapped_column(
        ForeignKey("developer_applications.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | revoked
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class WebhookEndpoint(Base, TimestampMixin):
    """An organization webhook endpoint subscribed to event names (Phase 18.13)."""

    __tablename__ = "webhook_endpoints"
    __table_args__ = (Index("ix_webhook_endpoints_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    secret: Mapped[Optional[str]] = mapped_column(String(128))  # signature secret
    events: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)  # [] = all
    # active | paused | failing
    status: Mapped[str] = mapped_column(String(20), default="active")
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class WebhookDelivery(Base, TimestampMixin):
    """One webhook delivery attempt with retry state (Phase 18.13)."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_endpoint", "endpoint_id"),
        Index("ix_webhook_deliveries_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    endpoint_id: Mapped[str] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False
    )
    event_name: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # pending | delivered | failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    response_code: Mapped[Optional[int]] = mapped_column(Integer)
    response_body: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class DeveloperUsage(Base, TimestampMixin):
    """Daily API usage record per developer application (Phase 18.14)."""

    __tablename__ = "developer_usage"
    __table_args__ = (
        Index("ix_developer_usage_app_day", "application_id", "usage_date"),
        UniqueConstraint(
            "application_id", "usage_date", "unit", name="uq_developer_usage_app_day_unit"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    developer_id: Mapped[str] = mapped_column(
        ForeignKey("developers.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[str] = mapped_column(
        ForeignKey("developer_applications.id", ondelete="CASCADE"), nullable=False
    )
    usage_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    unit: Mapped[str] = mapped_column(String(20), default="requests")  # requests | errors | latency_ms | installs
    value: Mapped[float] = mapped_column(Float, default=0.0)


class ExtensionInstall(Base, TimestampMixin):
    """An organization's install of a marketplace extension (Phase 18.6)."""

    __tablename__ = "extension_installs"
    __table_args__ = (
        Index("ix_extension_installs_org", "organization_id"),
        UniqueConstraint("marketplace_item_id", "organization_id", name="uq_extension_installs_item_org"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    marketplace_item_id: Mapped[str] = mapped_column(
        ForeignKey("marketplace_items.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # installed | disabled | uninstalled
    status: Mapped[str] = mapped_column(String(20), default="installed")
    settings: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    installed_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    installed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AIAgent(Base, TimestampMixin):
    """An AI agent registered on the ecosystem (Phase 18.4)."""

    __tablename__ = "ai_agents"
    __table_args__ = (
        Index("ix_ai_agents_org", "organization_id"),
        UniqueConstraint("organization_id", "agent_key", name="uq_ai_agents_org_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )  # None = global marketplace agent
    developer_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("developers.id", ondelete="SET NULL")
    )
    agent_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(40), default="assistant")  # finance | sales | legal | research | security | executive | operations | custom
    capabilities: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # permission codes the agent may act with
    permissions: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    knowledge_scopes: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # draft | published | installed | enabled | disabled | removed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    installed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Theme(Base, TimestampMixin):
    """Organization branding theme (Phase 18.9)."""

    __tablename__ = "themes"
    __table_args__ = (Index("ix_themes_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # logo | fonts | colors | layout | icons | dashboard | navigation | widgets
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(30), default="custom")  # custom | marketplace


class CertificationCredential(Base, TimestampMixin):
    """Developer certification credential and badge (Phase 18.19)."""

    __tablename__ = "developer_certifications"
    __table_args__ = (Index("ix_dev_certifications_dev", "developer_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    developer_id: Mapped[str] = mapped_column(
        ForeignKey("developers.id", ondelete="CASCADE"), nullable=False
    )
    exam: Mapped[str] = mapped_column(String(120), nullable=False)  # plugin-developer | solution-architect | professional | partner
    status: Mapped[str] = mapped_column(String(20), default="passed")  # passed | expired | revoked
    score: Mapped[float] = mapped_column(Float, default=0.0)
    badge: Mapped[str] = mapped_column(String(120), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class DeveloperSubscription(Base, TimestampMixin):
    """Developer monetization subscription (Phase 18.18)."""

    __tablename__ = "developer_subscriptions"
    __table_args__ = (Index("ix_dev_subscriptions_dev", "developer_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    developer_id: Mapped[str] = mapped_column(
        ForeignKey("developers.id", ondelete="CASCADE"), nullable=False
    )
    plan: Mapped[str] = mapped_column(String(30), default="free")  # free | pro | enterprise
    revenue_share: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0-0.3
    status: Mapped[str] = mapped_column(String(20), default="active")
    monthly_quota: Mapped[Optional[int]] = mapped_column(Integer)
    current_period_start: Mapped[Optional[str]] = mapped_column(String(40))
    current_period_end: Mapped[Optional[str]] = mapped_column(String(40))
