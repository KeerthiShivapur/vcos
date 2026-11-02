"""Adaptive Operating Profile - Universal Company Configuration.

This module extends the existing CompanyExperienceConfig with a comprehensive
adaptive operating profile that controls how VCOS adapts to each company's
needs without creating separate company realities.

The profile represents CONFIGURATION, not company truth.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import String, Text, JSON, ForeignKey, Enum as SQLEnum, Index, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OperatingModel(str, Enum):
    """Company operating model."""
    REMOTE_FIRST = "remote_first"
    HYBRID = "hybrid"
    OFFICE_FIRST = "office_first"
    DISTRIBUTED = "distributed"


class GovernanceProfile(str, Enum):
    """Governance profile for the company."""
    SIMPLE = "simple"
    STANDARD = "standard"
    CONTROLLED = "controlled"
    REGULATED = "regulated"
    FEDERATED = "federated"


class ScalingProfile(str, Enum):
    """Infrastructure scaling profile."""
    MEASURED = "measured"
    FIXED = "fixed"
    AUTO = "auto"
    ENTERPRISE = "enterprise"


class IntegrationState(str, Enum):
    """Integration connection state."""
    CONFIGURED = "configured"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    SYNCHRONIZING = "synchronizing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    REVOKED = "revoked"


class CapabilityLifecycleState(str, Enum):
    """7-stage capability lifecycle."""
    DISCOVERED = "discovered"
    PREREQUISITES_VALIDATED = "prerequisites_validated"
    CONFIGURATION_VALIDATED = "configuration_validated"
    GOVERNANCE_VALIDATED = "governance_validated"
    ENTITLEMENT_VALIDATED = "entitlement_validated"
    ACTIVATION_APPROVED = "activation_approved"
    ENABLED = "enabled"
    HEALTH_MONITORED = "health_monitored"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    DISABLED = "disabled"


class AdaptationMode(str, Enum):
    """Three distinct adaptation modes."""
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class CapabilityKey(str, Enum):
    """All capability keys in the system."""
    EMPLOYEE_MANAGEMENT = "employee_management"
    WORK_MANAGEMENT = "work_management"
    MEETINGS = "meetings"
    MESSAGING = "messaging"
    DOCUMENTS = "documents"
    SEARCH = "search"
    AI_COMPANION = "ai_companion"
    COMPANY_BRAIN = "company_brain"


class AdaptiveOperatingProfile(Base, TimestampMixin):
    """Comprehensive adaptive operating profile for a company."""
    __tablename__ = "adaptive_operating_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    profile_name: Mapped[str] = mapped_column(String(64), default="default")

    operating_model: Mapped[str] = mapped_column(String(20), default="hybrid")
    governance_profile: Mapped[str] = mapped_column(String(20), default="standard")
    scaling_profile: Mapped[str] = mapped_column(String(20), default="measured")

    enabled_capabilities: Mapped[List[str]] = mapped_column(JSON, default=list)
    disabled_capabilities: Mapped[List[str]] = mapped_column(JSON, default=list)

    interface_density: Mapped[str] = mapped_column(String(20), default="comfortable")
    navigation_style: Mapped[str] = mapped_column(String(20), default="adaptive")
    dashboard_layout: Mapped[str] = mapped_column(String(32), default="adaptive")
    progressive_disclosure: Mapped[bool] = mapped_column(default=True)
    show_advanced_features: Mapped[bool] = mapped_column(default=False)

    workflow_complexity: Mapped[str] = mapped_column(String(20), default="standard")
    default_approval_levels: Mapped[int] = mapped_column(Integer, default=1)
    segregation_of_duties: Mapped[bool] = mapped_column(default=False)
    delegation_enabled: Mapped[bool] = mapped_column(default=True)

    default_language: Mapped[str] = mapped_column(String(10), default="en")
    supported_languages: Mapped[List[str]] = mapped_column(JSON, default=["en"])
    default_timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    date_format: Mapped[str] = mapped_column(String(20), default="ISO")
    number_format: Mapped[str] = mapped_column(String(20), default="US")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    working_calendar: Mapped[str] = mapped_column(String(32), default="standard")

    integration_configs: Mapped[Dict[str, Dict[str, Any]]] = mapped_column(JSON, default=dict)
    feature_flags: Mapped[Dict[str, bool]] = mapped_column(JSON, default=dict)

    governance_profile: Mapped[str] = mapped_column(String(20), default="standard")
    require_mfa_for_admin: Mapped[bool] = mapped_column(default=True)
    session_timeout_minutes: Mapped[int] = mapped_column(default=480)
    max_failed_login_attempts: Mapped[int] = mapped_column(default=5)
    password_policy: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    data_retention_days: Mapped[int] = mapped_column(default=2555)
    sensitive_data_fields: Mapped[List[str]] = mapped_column(JSON, default=list)

    scaling_profile: Mapped[str] = mapped_column(String(20), default="measured")
    max_concurrent_users: Mapped[int] = mapped_column(default=10000)
    query_timeout_seconds: Mapped[int] = mapped_column(default=30)
    enable_caching: Mapped[bool] = mapped_column(default=True)
    cache_ttl_seconds: Mapped[int] = mapped_column(default=300)

    ai_companion_enabled: Mapped[bool] = mapped_column(default=True)
    company_brain_enabled: Mapped[bool] = mapped_column(default=True)
    digital_twin_enabled: Mapped[bool] = mapped_column(default=False)
    background_intelligence_enabled: Mapped[bool] = mapped_column(default=False)
    auto_approve_low_risk: Mapped[bool] = mapped_column(default=False)
    max_auto_approval_amount: Mapped[int] = mapped_column(default=0)

    notification_preferences: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    email_notifications_enabled: Mapped[bool] = mapped_column(default=True)
    push_notifications_enabled: Mapped[bool] = mapped_column(default=True)
    in_app_notifications_enabled: Mapped[bool] = mapped_column(default=True)

    auto_adaptation_enabled: Mapped[bool] = mapped_column(default=True)
    adaptation_modes: Mapped[List[str]] = mapped_column(JSON, default=["user", "admin"])
    auto_transition_enabled: Mapped[bool] = mapped_column(default=True)
    transition_cooldown_days: Mapped[int] = mapped_column(default=30)

    capability_lifecycle_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    configured_by: Mapped[Optional[str]] = mapped_column(String(32))
    configured_at: Mapped[Optional[datetime]] = mapped_column()
    last_modified_by: Mapped[Optional[str]] = mapped_column(String(32))
    last_modified_at: Mapped[Optional[datetime]] = mapped_column()

    organization: Mapped["Organization"] = relationship(back_populates="adaptive_profile")
    versions: Mapped[List["AdaptiveOperatingProfileVersion"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="AdaptiveOperatingProfileVersion.version"
    )

    def get_enabled_capability_keys(self) -> Set[str]:
        return set(self.enabled_capabilities) - set(self.disabled_capabilities)

    def is_capability_enabled(self, capability_key: str) -> bool:
        return capability_key in self.get_enabled_capability_keys()


class AdaptiveOperatingProfileVersion(Base, TimestampMixin):
    __tablename__ = "adaptive_operating_profile_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("adaptive_operating_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(nullable=False)
    effective_until: Mapped[Optional[datetime]] = mapped_column()
    config_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    changed_by: Mapped[str] = mapped_column(String(32))
    changed_by_email: Mapped[str] = mapped_column(String(256))
    change_reason: Mapped[str] = mapped_column(Text)
    change_type: Mapped[str] = mapped_column(String(32))
    affected_capabilities: Mapped[List[str]] = mapped_column(JSON, default=list)
    affected_workflows: Mapped[List[str]] = mapped_column(JSON, default=list)
    affected_users: Mapped[List[str]] = mapped_column(JSON, default=list)
    in_flight_policy: Mapped[str] = mapped_column(String(32), default="grandfather")

    profile: Mapped["AdaptiveOperatingProfile"] = relationship(back_populates="versions")
    organization: Mapped["Organization"] = relationship(back_populates="adaptive_profile_versions")


class CapabilityLifecycleRecord(Base, TimestampMixin):
    __tablename__ = "capability_lifecycle_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    capability_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    current_state: Mapped[str] = mapped_column(String(32), default="discovered")
    previous_state: Mapped[Optional[str]] = mapped_column(String(32))

    prerequisites_met: Mapped[bool] = mapped_column(default=False)
    configuration_valid: Mapped[bool] = mapped_column(default=False)
    governance_approved: Mapped[bool] = mapped_column(default=False)
    entitlement_verified: Mapped[bool] = mapped_column(default=False)
    activation_approved: Mapped[bool] = mapped_column(default=False)

    missing_prerequisites: Mapped[List[str]] = mapped_column(JSON, default=list)
    configuration_issues: Mapped[List[str]] = mapped_column(JSON, default=list)
    governance_issues: Mapped[List[str]] = mapped_column(JSON, default=list)
    entitlement_issues: Mapped[List[str]] = mapped_column(JSON, default=list)

    approved_by: Mapped[Optional[str]] = mapped_column(String(32))
    approved_at: Mapped[Optional[datetime]] = mapped_column()
    approval_expires_at: Mapped[Optional[datetime]] = mapped_column()

    missing_prerequisites: Mapped[List[str]] = mapped_column(JSON, default=list)
    configuration_issues: Mapped[List[str]] = mapped_column(JSON, default=list)
    governance_issues: Mapped[List[str]] = mapped_column(JSON, default=list)
    entitlement_issues: Mapped[List[str]] = mapped_column(JSON, default=list)

    approved_by: Mapped[Optional[str]] = mapped_column(String(32))
    approved_at: Mapped[Optional[datetime]] = mapped_column()
    approval_expires_at: Mapped[Optional[datetime]] = mapped_column()

    health_status: Mapped[str] = mapped_column(String(20), default="healthy")
    last_health_check: Mapped[Optional[datetime]] = mapped_column()
    error_count: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    version: Mapped[int] = mapped_column(Integer, default=1)
    state_changed_at: Mapped[datetime] = mapped_column(default=utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="capability_lifecycle_records")

    __table_args__ = (
        Index("ix_capability_lifecycle_org_capability", "organization_id", "capability_key", unique=True),
    )


class IntegrationConfigRecord(Base, TimestampMixin):
    __tablename__ = "integration_config_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    integration_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    integration_type: Mapped[str] = mapped_column(String(32))

    state: Mapped[str] = mapped_column(String(20), default="configured")
    previous_state: Mapped[Optional[str]] = mapped_column(String(20))
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    credentials_ref: Mapped[Optional[str]] = mapped_column(String(128))

    last_sync_at: Mapped[Optional[datetime]] = mapped_column()
    last_successful_sync_at: Mapped[Optional[datetime]] = mapped_column()
    last_sync_status: Mapped[str] = mapped_column(String(20), default="pending")
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text)
    sync_frequency_seconds: Mapped[int] = mapped_column(default=3600)

    health_status: Mapped[str] = mapped_column(String(20), default="healthy")
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    permitted_scopes: Mapped[List[str]] = mapped_column(JSON, default=list)
    admin_users: Mapped[List[str]] = mapped_column(JSON, default=list)

    version: Mapped[int] = mapped_column(Integer, default=1)
    config_changed_at: Mapped[datetime] = mapped_column(default=utcnow)
    state_changed_at: Mapped[datetime] = mapped_column(default=utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="integration_config_records")

    __table_args__ = (
        Index("ix_integration_config_org_integration", "organization_id", "integration_key", unique=True),
    )


class WorkflowConfigurationRecord(Base, TimestampMixin):
    __tablename__ = "workflow_configuration_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    workflow_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workflow_name: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_type: Mapped[str] = mapped_column(String(32))

    complexity: Mapped[str] = mapped_column(String(20), default="standard")
    stages: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    segregation_of_duties: Mapped[bool] = mapped_column(default=False)
    delegation_enabled: Mapped[bool] = mapped_column(default=True)
    timeout_hours: Mapped[int] = mapped_column(default=72)
    escalation_rules: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    failure_handling: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    policy_version: Mapped[str] = mapped_column(String(32), default="1.0")
    requires_segregation_of_duties: Mapped[bool] = mapped_column(default=False)
    requires_dual_approval: Mapped[bool] = mapped_column(default=False)

    version: Mapped[int] = mapped_column(Integer, default=1)
    effective_from: Mapped[datetime] = mapped_column(default=utcnow)
    effective_until: Mapped[Optional[datetime]] = mapped_column()
    created_by: Mapped[str] = mapped_column(String(32))
    approved_by: Mapped[Optional[str]] = mapped_column(String(32))
    in_flight_policy: Mapped[str] = mapped_column(String(32), default="grandfather")

    organization: Mapped["Organization"] = relationship(back_populates="workflow_configurations")

    __table_args__ = (
        Index("ix_workflow_config_org_workflow", "organization_id", "workflow_key", unique=True),
    )


class AdaptationRecommendationRecord(Base, TimestampMixin):
    __tablename__ = "adaptation_recommendations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recommendation_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    evidence: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(default=0.0)
    uncertainty: Mapped[float] = mapped_column(default=0.0)
    impact_level: Mapped[str] = mapped_column(String(20))
    affected_capabilities: Mapped[List[str]] = mapped_column(JSON, default=list)
    affected_workflows: Mapped[List[str]] = mapped_column(JSON, default=list)
    estimated_effort: Mapped[str] = mapped_column(String(32))
    requires_approval: Mapped[bool] = mapped_column(default=True)
    approval_required_by: Mapped[List[str]] = mapped_column(JSON, default=list)
    auto_applicable: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(32))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column()
    applied_at: Mapped[Optional[datetime]] = mapped_column()
    superseded_by: Mapped[Optional[str]] = mapped_column(String(32))
    approval_id: Mapped[Optional[str]] = mapped_column(String(32))
    governance_trail: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    triggered_by: Mapped[str] = mapped_column(String(32))
    source_context: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    organization: Mapped["Organization"] = relationship(back_populates="adaptation_recommendations")