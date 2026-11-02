"""Gate 24 — Universal Integration & External-System Operating Fabric.

Canonical connector framework, external identity mapping, synchronization,
exact-once semantics, provenance, temporal truth, source authority,
conflict preservation, and bidirectional operation.

This is NOT an "Integrations page." It is the foundational integration fabric
that connects external systems to the ONE canonical company reality.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Index,
    UniqueConstraint,
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    Integer,
    DateTime,
    Boolean,
    JSON,
    select,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.company_operating import gen_uuid


# =============================================================================
# VOCABULARIES
# =============================================================================

CONNECTOR_KINDS = (
    "productivity",      # Google Workspace, Microsoft 365
    "communication",     # Slack, Teams
    "code",              # GitHub, GitLab
    "work_management",   # Jira, Linear, Asana
    "crm",               # Salesforce, HubSpot
    "hr",                # Workday, BambooHR, Rippling
    "erp",               # SAP, Oracle, NetSuite
    "accounting",        # QuickBooks, Xero
    "cloud",             # AWS, GCP, Azure
    "identity",          # Okta, Entra ID, Auth0
    "knowledge",         # Notion, Confluence, Drive
    "calendar",          # Google Calendar, Outlook
    "video",             # Zoom, Meet
    "custom",
)

CONNECTOR_STATES = (
    "disconnected",
    "connecting",
    "connected",
    "error",
    "paused",
    "revoked",
    "reauthorization_required",
)

CONNECTOR_CAPABILITIES = (
    "read_people",
    "read_groups",
    "read_channels",
    "read_messages",
    "read_files",
    "read_calendar",
    "read_contacts",
    "read_repositories",
    "read_issues",
    "read_pull_requests",
    "read_commits",
    "read_projects",
    "read_tasks",
    "read_customers",
    "read_deals",
    "read_organizations",
    "read_employees",
    "read_departments",
    "read_roles",
    "read_compensation",
    "read_time_off",
    "read_performance",
    "read_financials",
    "read_inventory",
    "read_vendors",
    "read_resources",
    "read_knowledge",
    "read_pages",
    "read_databases",
    "read_comments",
    "write_messages",
    "write_files",
    "write_calendar",
    "write_issues",
    "write_pull_requests",
    "write_tasks",
    "write_customers",
    "write_deals",
    "write_employees",
    "write_knowledge",
    "sync_incremental",
    "sync_full",
    "webhook_events",
    "polling",
)

ENTITY_TYPES = (
    "person",
    "group",
    "team",
    "channel",
    "message",
    "file",
    "event",
    "contact",
    "repository",
    "issue",
    "pull_request",
    "commit",
    "project",
    "task",
    "customer",
    "deal",
    "organization",
    "employee",
    "department",
    "role",
    "compensation",
    "time_off",
    "performance_review",
    "financial_record",
    "invoice",
    "vendor",
    "resource",
    "knowledge_page",
    "database",
    "comment",
)

MAPPING_STATES = (
    "pending",
    "mapped",
    "conflict",
    "ignored",
    "deleted_externally",
)

SYNC_STATES = (
    "pending",
    "running",
    "completed",
    "failed",
    "partial",
    "cancelled",
)

SYNC_MODES = (
    "initial",
    "incremental",
    "webhook",
    "polling",
    "replay",
)

EXTERNAL_EVENT_STATES = (
    "pending",
    "processed",
    "failed",
    "duplicate",
    "ignored",
)

SOURCE_AUTHORITY_LEVELS = (
    "primary",      # Authoritative source for this domain
    "secondary",    # Supplementary source
    "tertiary",     # Reference only
    "ignored",      # Not used for this domain
)

CONFLICT_RESOLUTION_STATES = (
    "open",
    "authority_applied",
    "manual_resolution",
    "merged",
    "superseded",
)


# =============================================================================
# CONNECTOR FRAMEWORK
# =============================================================================

class Connector(Base):
    """
    Universal connector registration — the canonical connector definition.
    
    Each connector represents a provider integration (Google, Microsoft, Slack, etc.)
    that can be instantiated per tenant/organization.
    """
    
    __tablename__ = "connectors"
    __table_args__ = (
        Index("ix_connector_kind", "kind"),
        Index("ix_connector_enabled", "enabled"),
        UniqueConstraint("kind", "provider", name="uq_connector_kind_provider"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    
    # Connector identity
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # CONNECTOR_KINDS
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # google, microsoft, slack, github, jira, etc.
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Versioning
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    
    # Capabilities
    inbound_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)  # CONNECTOR_CAPABILITIES
    outbound_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)  # CONNECTOR_CAPABILITIES
    supported_entities: Mapped[list[str]] = mapped_column(JSON, default=list)  # ENTITY_TYPES
    supported_events: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Sync model
    sync_modes: Mapped[list[str]] = mapped_column(JSON, default=list)  # SYNC_MODES
    supports_webhooks: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_polling: Mapped[bool] = mapped_column(Boolean, default=True)
    default_poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    
    # Authentication
    auth_types: Mapped[list[str]] = mapped_column(JSON, default=list)  # oauth2, api_key, basic, saml, oidc
    oauth_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_config_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    optional_config_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Security
    security_requirements: Mapped[Optional[dict]] = mapped_column(JSON)
    credential_rotation_supported: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Health & monitoring
    health_check_endpoint: Mapped[Optional[str]] = mapped_column(String(500))
    rate_limits: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Marketplace
    category: Mapped[str] = mapped_column(String(50), default="integration")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    documentation_url: Mapped[Optional[str]] = mapped_column(String(500))
    icon_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Lifecycle
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deprecated: Mapped[bool] = mapped_column(Boolean, default=False)
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deprecated_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Metadata
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ConnectorInstance(Base):
    """
    Per-organization connector instance — the actual connection configuration.
    
    This is what an organization connects (e.g., "Our Slack workspace").
    """
    
    __tablename__ = "connector_instances"
    __table_args__ = (
        Index("ix_connector_instance_org", "organization_id"),
        Index("ix_connector_instance_connector", "connector_id"),
        Index("ix_connector_instance_state", "state"),
        UniqueConstraint("organization_id", "connector_id", "name", name="uq_connector_instance_org_name"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Instance identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # "Our Slack Workspace"
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Configuration (validated against connector's required/optional fields)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Credentials (encrypted at rest via application layer)
    credentials: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    credentials_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    credentials_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Authentication
    auth_type: Mapped[str] = mapped_column(String(30), nullable=False, default="oauth2")
    auth_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # State
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="disconnected", index=True)  # CONNECTOR_STATES
    error: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    connector: Mapped["Connector"] = relationship("Connector", lazy="selectin")
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Connection lifecycle
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Sync configuration
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_mode: Mapped[str] = mapped_column(String(20), default="incremental")  # SYNC_MODES
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    full_sync_schedule: Mapped[Optional[str]] = mapped_column(String(50))  # cron expression
    
    # Webhook configuration
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500))
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255))
    webhook_events: Mapped[list[str]] = mapped_column(JSON, default=list)
    webhook_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Permissions & scope
    requested_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    granted_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    scope_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Admin
    admin_id: Mapped[Optional[str]] = mapped_column(String(32))
    admin_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Metadata
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ConnectorCapability(Base):
    """
    Connector capability matrix — what operations a connector supports.
    
    Used for capability discovery and marketplace matching.
    """
    
    __tablename__ = "connector_capabilities"
    __table_args__ = (
        UniqueConstraint("connector_id", "entity_type", "operation", name="uq_connector_capability"),
        Index("ix_connector_capability_connector", "connector_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Capability definition
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ENTITY_TYPES
    operation: Mapped[str] = mapped_column(String(30), nullable=False)  # read|write|delete|sync|webhook
    
    # Details
    description: Mapped[Optional[str]] = mapped_column(Text)
    requires_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    rate_limit: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Support level
    support_level: Mapped[str] = mapped_column(String(20), default="full")  # full|partial|beta|deprecated
    limitations: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# =============================================================================
# EXTERNAL IDENTITY MAPPING
# =============================================================================

class ExternalIdentityMapping(Base):
    """
    Canonical external identity mapping — VCOS entity ↔ External provider identity.
    
    The same person may exist as:
    VCOS Person
       │
       ├── Google ID
       ├── Microsoft ID
       ├── Slack ID
       ├── GitHub ID
       ├── Jira ID
       ├── Salesforce ID
       └── HR-system ID
    
    These must NOT become seven different people.
    But don't blindly merge based on email either.
    """
    
    __tablename__ = "external_identity_mappings"
    __table_args__ = (
        Index("ix_eim_org", "organization_id"),
        Index("ix_eim_vcos_entity", "vcos_entity_type", "vcos_entity_id"),
        Index("ix_eim_external", "connector_instance_id", "external_id"),
        Index("ix_eim_state", "mapping_state"),
        # Partial unique index: only enforce uniqueness when vcos_entity_id is not empty
        # This allows multiple pending mappings (vcos_entity_id='') per connector instance
        Index(
            "uq_eim_vcos_entity",
            "organization_id", "connector_instance_id", "vcos_entity_type", "vcos_entity_id",
            unique=True,
            postgresql_where="vcos_entity_id != ''",
        ),
        UniqueConstraint(
            "organization_id", "connector_instance_id", "external_id",
            name="uq_eim_external_entity"
        ),
        CheckConstraint(
            "mapping_state IN ('pending', 'mapped', 'conflict', 'ignored', 'deleted_externally')",
            name="ck_eim_state_valid"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_instance_id: Mapped[str] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # VCOS entity
    vcos_entity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # person, team, project, customer, etc.
    vcos_entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    
    # External identity
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    external_email: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    external_display_name: Mapped[Optional[str]] = mapped_column(String(255))
    external_avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    external_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Mapping state
    mapping_state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)  # MAPPING_STATES
    confidence: Mapped[Optional[float]] = mapped_column(default=None)  # 0.0-1.0
    
    # Resolution
    resolution_method: Mapped[str] = mapped_column(String(30), default="auto")  # auto|manual|rule|imported
    resolved_by: Mapped[Optional[str]] = mapped_column(String(32))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Conflict tracking
    conflict_with: Mapped[Optional[str]] = mapped_column(String(32))  # Other mapping ID if conflict
    conflict_details: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Temporal
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    sync_run_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Metadata
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ExternalIdentityMappingHistory(Base):
    """
    Historical record of identity mapping changes for audit and temporal queries.
    """
    
    __tablename__ = "external_identity_mapping_history"
    __table_args__ = (
        Index("ix_eimh_mapping", "mapping_id"),
        Index("ix_eimh_org", "organization_id"),
        Index("ix_eimh_time", "changed_at"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mapping_id: Mapped[str] = mapped_column(
        ForeignKey("external_identity_mappings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Change details
    field_changed: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    change_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Actor
    changed_by: Mapped[Optional[str]] = mapped_column(String(32))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Context
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    sync_run_id: Mapped[Optional[str]] = mapped_column(String(32))


# =============================================================================
# SYNCHRONIZATION
# =============================================================================

class SyncRun(Base):
    """
    Synchronization run — a complete sync operation.
    
    Supports: initial sync, incremental sync, webhook batch, polling, replay.
    """
    
    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("ix_sync_run_instance", "connector_instance_id"),
        Index("ix_sync_run_state", "state"),
        Index("ix_sync_run_time", "started_at"),
        Index("ix_sync_run_mode", "sync_mode"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_instance_id: Mapped[str] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Run identity
    sync_mode: Mapped[str] = mapped_column(String(20), nullable=False)  # SYNC_MODES
    triggered_by: Mapped[str] = mapped_column(String(30), default="scheduled")  # scheduled|manual|webhook|replay|retry
    trigger_id: Mapped[Optional[str]] = mapped_column(String(32))  # webhook_id, job_id, etc.
    
    # Cursor for incremental sync
    cursor_before: Mapped[Optional[str]] = mapped_column(String(255))
    cursor_after: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Time window
    since_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    until_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # State
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)  # SYNC_STATES
    error: Mapped[Optional[str]] = mapped_column(Text)
    
    # Statistics
    entities_processed: Mapped[int] = mapped_column(Integer, default=0)
    entities_created: Mapped[int] = mapped_column(Integer, default=0)
    entities_updated: Mapped[int] = mapped_column(Integer, default=0)
    entities_deleted: Mapped[int] = mapped_column(Integer, default=0)
    entities_failed: Mapped[int] = mapped_column(Integer, default=0)
    conflicts_detected: Mapped[int] = mapped_column(Integer, default=0)
    events_processed: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Retry
    retry_of: Mapped[Optional[str]] = mapped_column(String(32))  # Parent sync run ID
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SyncCursor(Base):
    """
    Synchronization cursor — checkpoint for incremental synchronization.
    
    Stores the last known position in the external system's event stream.
    """
    
    __tablename__ = "sync_cursors"
    __table_args__ = (
        Index("ix_sync_cursor_instance", "connector_instance_id"),
        Index("ix_sync_cursor_entity", "entity_type"),
        UniqueConstraint("connector_instance_id", "entity_type", name="uq_sync_cursor_instance_entity"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_instance_id: Mapped[str] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Cursor identity
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ENTITY_TYPES
    cursor_value: Mapped[str] = mapped_column(String(255), nullable=False)
    cursor_type: Mapped[str] = mapped_column(String(30), default="timestamp")  # timestamp|token|sequence|page
    
    # Associated sync run
    last_sync_run_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Metadata
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ExternalEvent(Base):
    """
    External event — an event received from an external system.
    
    Every external event is recorded for:
    - Exact-once processing
    - Provenance chain
    - Replay capability
    - Audit trail
    """
    
    __tablename__ = "external_events"
    __table_args__ = (
        Index("ix_ext_event_instance", "connector_instance_id"),
        Index("ix_ext_event_state", "state"),
        Index("ix_ext_event_type", "event_type"),
        Index("ix_ext_event_time", "received_at"),
        Index("ix_ext_event_source", "source_id"),
        UniqueConstraint(
            "connector_instance_id", "external_event_id", "event_type",
            name="uq_ext_event_exact_once"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_instance_id: Mapped[str] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Event identity
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)  # External object ID
    source_type: Mapped[Optional[str]] = mapped_column(String(50))  # ENTITY_TYPES
    
    # Payload
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # External metadata
    external_actor_id: Mapped[Optional[str]] = mapped_column(String(255))
    external_actor_type: Mapped[Optional[str]] = mapped_column(String(30))
    external_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Processing
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)  # EXTERNAL_EVENT_STATES
    error: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    
    # Epistemic status
    epistemic_status: Mapped[Optional[str]] = mapped_column(String(30), default=None)  # observed|measured|evidence_backed|inferred|predicted|proposed
    
    # Exact-once
    processing_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    processed_by_sync_run: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Provenance
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    webhook_delivery_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)


# =============================================================================
# SOURCE AUTHORITY & CONFLICT PRESERVATION
# =============================================================================

class SourceAuthority(Base):
    """
    Source authority — governed source precedence for entity domains.
    
    Different systems may be authoritative for different domains.
    For example:
    - Identity provider → authentication identity (primary)
    - HR system → employment data (primary)
    - CRM → customer records (primary)
    - ERP → accounting/financial records (primary)
    - GitHub → repository/code state (primary)
    - Jira → external work-management state (primary)
    - VCOS → canonical organizational operating state (primary)
    
    Do NOT hard-code a universal winner. Build governed source-authority semantics.
    """
    
    __tablename__ = "source_authorities"
    __table_args__ = (
        Index("ix_sa_org", "organization_id"),
        Index("ix_sa_entity_type", "entity_type"),
        Index("ix_sa_authority", "authority_level"),
        UniqueConstraint("organization_id", "entity_type", "connector_instance_id", name="uq_sa_org_entity_connector"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Domain
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ENTITY_TYPES
    
    # Authority
    connector_instance_id: Mapped[str] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    authority_level: Mapped[str] = mapped_column(String(20), nullable=False)  # SOURCE_AUTHORITY_LEVELS
    precedence: Mapped[int] = mapped_column(Integer, default=0)  # Higher = more authoritative
    
    # Scope
    field_scope: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)  # Specific fields this authority covers
    conditions: Mapped[Optional[dict]] = mapped_column(JSON)  # Conditional authority
    
    # Governance
    configured_by: Mapped[Optional[str]] = mapped_column(String(32))
    approved_by: Mapped[Optional[str]] = mapped_column(String(32))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ExternalConflict(Base):
    """
    External conflict — preserved disagreement between sources.
    
    Suppose:
    HR system: Employee → Team A
    VCOS: Employee → Team B
    
    Do NOT silently overwrite. Preserve:
    Source A, Source B, Timestamps, Provenance, Conflict, Authority, Resolution
    """
    
    __tablename__ = "external_conflicts"
    __table_args__ = (
        Index("ix_ext_conflict_org", "organization_id"),
        Index("ix_ext_conflict_entity", "entity_type", "entity_id"),
        Index("ix_ext_conflict_state", "resolution_state"),
        Index("ix_ext_conflict_source", "source_a_instance_id", "source_b_instance_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Entity
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ENTITY_TYPES
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))  # VCOS entity ID if exists
    
    # Conflicting sources
    source_a_instance_id: Mapped[str] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_a_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_a_value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_a_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_a_authority: Mapped[int] = mapped_column(Integer, default=0)
    
    source_b_instance_id: Mapped[str] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_b_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_b_value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_b_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_b_authority: Mapped[int] = mapped_column(Integer, default=0)
    
    # Additional sources (for multi-way conflicts)
    additional_sources: Mapped[list[dict]] = mapped_column(JSON, default=list)
    
    # Conflict metadata
    conflict_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    detected_by_sync_run: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Resolution
    resolution_state: Mapped[str] = mapped_column(String(30), default="open")  # CONFLICT_RESOLUTION_STATES
    resolution_method: Mapped[Optional[str]] = mapped_column(String(30))  # authority|manual|merged|policy
    resolved_value: Mapped[Optional[dict]] = mapped_column(JSON)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(32))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Provenance
    source_a_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    source_b_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# =============================================================================
# BIDIRECTIONAL OPERATION
# =============================================================================

class ExternalOperation(Base):
    """
    External operation — VCOS canonical action → external system execution.
    
    VCOS canonical reality
    → decision
    → authorization
    → governed action
    → connector
    → external system
    → external outcome
    → webhook/poll/event
    → VCOS observation
    → verification
    
    Maintains:
    Recommendation ≠ Decision ≠ Authorization ≠ Execution ≠ Outcome
    
    No outbound external mutation may bypass governance.
    """
    
    __tablename__ = "external_operations"
    __table_args__ = (
        Index("ix_ext_op_org", "organization_id"),
        Index("ix_ext_op_instance", "connector_instance_id"),
        Index("ix_ext_op_state", "state"),
        Index("ix_ext_op_action", "source_action_id"),
        Index("ix_ext_op_time", "created_at"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_instance_id: Mapped[str] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Source (VCOS canonical)
    source_action_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # CompanyAction
    source_decision_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # CompanyDecision
    source_authorization_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # CompanyAuthorization
    source_commitment_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # CompanyCommitment
    
    # Operation definition
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # create|update|delete|transition|comment|assign
    target_entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ENTITY_TYPES
    target_external_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Governance chain
    governance_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    governance_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    governance_verified_by: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Execution
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)  # pending|queued|executing|completed|failed|cancelled
    external_operation_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)  # External system's operation ID
    error: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    
    # Result
    result_payload: Mapped[Optional[dict]] = mapped_column(JSON)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Observation & Verification
    observation_received: Mapped[bool] = mapped_column(Boolean, default=False)
    observation_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verification_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timing
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# =============================================================================
# INTEGRATION HEALTH
# =============================================================================

class IntegrationHealth(Base):
    """
    Integration health — operational visibility for administrators.
    
    Google       Connected
    Slack        Healthy
    GitHub       Healthy
    Jira         Syncing
    CRM          Reauthorization required
    ERP          Last sync: ...
    
    Plus: sync lag, failures, retries, rate limits, conflicts, mapping problems,
    data freshness, authentication status
    """
    
    __tablename__ = "integration_health"
    __table_args__ = (
        Index("ix_ih_org", "organization_id"),
        Index("ix_ih_instance", "connector_instance_id"),
        Index("ix_ih_status", "overall_status"),
        UniqueConstraint("connector_instance_id", name="uq_ih_instance"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_instance_id: Mapped[str] = mapped_column(
        ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Overall status
    overall_status: Mapped[str] = mapped_column(String(20), default="unknown")  # healthy|degraded|error|unknown|reauth_required
    
    # Connection
    connection_status: Mapped[str] = mapped_column(String(20), default="unknown")  # connected|disconnected|error|reauth_required
    last_connection_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    connection_error: Mapped[Optional[str]] = mapped_column(Text)
    
    # Authentication
    auth_status: Mapped[str] = mapped_column(String(20), default="unknown")  # valid|expired|revoked|invalid|unknown
    credentials_expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_auth_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Synchronization
    last_successful_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_state: Mapped[Optional[str]] = mapped_column(String(20))  # SYNC_STATES
    sync_lag_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    sync_success_rate: Mapped[Optional[float]] = mapped_column(default=None)  # 0.0-1.0
    
    # Events
    events_processed_24h: Mapped[int] = mapped_column(Integer, default=0)
    events_failed_24h: Mapped[int] = mapped_column(Integer, default=0)
    events_pending: Mapped[int] = mapped_column(Integer, default=0)
    oldest_pending_event_age_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Conflicts & mappings
    active_conflicts: Mapped[int] = mapped_column(Integer, default=0)
    pending_mappings: Mapped[int] = mapped_column(Integer, default=0)
    mapping_conflicts: Mapped[int] = mapped_column(Integer, default=0)
    
    # Rate limits
    rate_limit_remaining: Mapped[Optional[int]] = mapped_column(Integer)
    rate_limit_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rate_limit_exceeded_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Data freshness
    data_freshness_score: Mapped[Optional[float]] = mapped_column(default=None)  # 0.0-1.0
    stale_entities: Mapped[int] = mapped_column(Integer, default=0)
    
    # Metadata
    details_json: Mapped[Optional[dict]] = mapped_column(JSON)
    last_calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# =============================================================================
# NOTIFICATION CENTER RESPONSE
# =============================================================================

class NotificationCenterResponse(Base):
    """
    Response for notification center queries.
    
    Aggregates notifications from canonical events/attention architecture.
    """
    
    __tablename__ = "notification_center_responses"
    __table_args__ = (
        Index("ix_ncr_org", "organization_id"),
        Index("ix_ncr_user", "user_id"),
        Index("ix_ncr_time", "created_at"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Notifications
    notifications: Mapped[list[dict]] = mapped_column(JSON, default=list)
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    grouped: Mapped[dict[str, list]] = mapped_column(JSON, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def __len__(self) -> int:
        return len(self.notifications)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def compute_payload_fingerprint(payload: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 fingerprint for exact-once semantics."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def compute_event_fingerprint(
    connector_instance_id: str,
    external_event_id: str,
    event_type: str,
    source_id: Optional[str] = None,
) -> str:
    """Compute fingerprint for external event exact-once processing."""
    data = {
        "connector_instance_id": connector_instance_id,
        "external_event_id": external_event_id,
        "event_type": event_type,
        "source_id": source_id or "",
    }
    return compute_payload_fingerprint(data)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Vocabularies
    "CONNECTOR_KINDS",
    "CONNECTOR_STATES",
    "CONNECTOR_CAPABILITIES",
    "ENTITY_TYPES",
    "MAPPING_STATES",
    "SYNC_STATES",
    "SYNC_MODES",
    "EXTERNAL_EVENT_STATES",
    "SOURCE_AUTHORITY_LEVELS",
    "CONFLICT_RESOLUTION_STATES",
    # Models
    "Connector",
    "ConnectorInstance",
    "ConnectorCapability",
    "ExternalIdentityMapping",
    "ExternalIdentityMappingHistory",
    "SyncRun",
    "SyncCursor",
    "ExternalEvent",
    "SourceAuthority",
    "ExternalConflict",
    "ExternalOperation",
    "IntegrationHealth",
    "NotificationCenterResponse",
    # Utilities
    "compute_payload_fingerprint",
    "compute_event_fingerprint",
]