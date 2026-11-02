"""Feature Flags Models — Gate 19

Governed feature flags with tenant isolation, rollout strategies,
dependency management, and evaluation tracking.

Key architectural principles:
- Feature flags are CONTROL PLANE state - they control feature availability
- Feature flags do NOT become the canonical source of authorization, permissions, commitments
- Feature flags do NOT bypass governance, tenant isolation, or canonical mutation rules
- Decision != Authorization != Commitment != Responsibility != Action != Execution != Outcome
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Set
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey, Index, UniqueConstraint,
    JSON, Text, Enum as SQLEnum, CheckConstraint, func, Integer
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import gen_uuid, TimestampMixin

logger = logging.getLogger("vcos.feature_flags.models")


class FeatureFlagStatus(str, Enum):
    """Feature flag lifecycle status."""
    OFF = "off"
    BETA = "beta"
    ALPHA = "alpha"
    ENABLED = "enabled"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class RolloutStrategy(str, Enum):
    """Rollout strategy for feature flags."""
    ALL = "all"                      # 100% of eligible users
    PERCENTAGE = "percentage"        # Percentage of users
    SEGMENT = "segment"              # Specific user segments
    RING = "ring"                    # Deployment rings (canary, early, broad)
    CUSTOM = "custom"                # Custom logic


class FeatureFlagScope(str, Enum):
    """Feature flag scope."""
    GLOBAL = "global"                # Platform-wide (VCOS operators only)
    TENANT = "tenant"                # Tenant-specific
    USER = "user"                    # User-specific


class RolloutPrecedence(int, Enum):
    """Explicit precedence for rollout targeting mechanisms."""
    CUSTOM = 0       # Custom rules - highest precedence
    RING = 1         # Deployment rings
    SEGMENT = 2      # User segments
    PERCENTAGE = 3   # Percentage rollout
    ALL = 4          # All users - lowest precedence


# Valid lifecycle transitions
VALID_STATUS_TRANSITIONS = {
    "off": ["beta", "alpha", "enabled", "deprecated", "archived"],
    "beta": ["enabled", "off", "deprecated", "archived"],
    "alpha": ["enabled", "beta", "off", "deprecated", "archived"],
    "enabled": ["off", "beta", "alpha", "deprecated", "archived"],
    "deprecated": ["archived", "off"],
    "archived": [],  # Terminal state - no transitions allowed
}


class FeatureFlag(Base):
    """Feature flag — governed feature toggle.
    
    A feature flag answers ONE question: "Is this capability available?"
    It does NOT answer: "Is this actor allowed to perform this operation?"
    That is the job of the authorization/governance system.
    """
    
    __tablename__ = "feature_flags"
    __table_args__ = (
        Index("ix_ff_org_status", "organization_id", "status"),
        Index("ix_ff_org_key", "organization_id", "key"),
        Index("ix_ff_org_scope", "organization_id", "scope"),
        Index("ix_ff_org_owner", "organization_id", "owner_id"),
        Index("ix_ff_created", "created_at"),
        Index("ix_ff_updated", "updated_at"),
        UniqueConstraint("organization_id", "key", name="uq_feature_flag_org_key"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"ff-{uuid.uuid4().hex[:12]}")
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Identity
    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # State - lifecycle status
    status: Mapped[str] = mapped_column(
        String(20), default="off", nullable=False, index=True
    )
    
    # Rollout configuration
    rollout_strategy: Mapped[str] = mapped_column(
        String(20), default="all", nullable=False
    )
    rollout_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Scope - tenant isolation boundary
    scope: Mapped[str] = mapped_column(
        String(20), default="tenant", nullable=False
    )
    
    # Dependencies - directed acyclic graph within tenant
    depends_on: Mapped[List[str]] = mapped_column(JSON, default=list)  # Feature flag keys
    conflicts_with: Mapped[List[str]] = mapped_column(JSON, default=list)
    
    # Ownership - for governance
    owner_id: Mapped[Optional[str]] = mapped_column(String(32))
    team_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Metadata
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Lifecycle timestamps
    enabled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deprecated_reason: Mapped[Optional[str]] = mapped_column(Text)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    archived_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Emergency kill switch
    emergency_disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    emergency_disabled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    emergency_disabled_by: Mapped[Optional[str]] = mapped_column(String(32))
    emergency_disabled_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Metrics
    exposure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Exact-once semantics
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, default=lambda: hashlib.sha256(f"{uuid.uuid4()}".encode()).hexdigest())
    
    # Optimistic concurrency control
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Governance integration - links to approval/commitment if governed
    governance_context: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    # Example: {"approval_id": "...", "commitment_id": "...", "policy_version": "..."}
    
    # Timestamps (from TimestampMixin)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    def evaluate(
        self,
        organization_id: str,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        actor_roles: Optional[List[str]] = None,
        actor_permissions: Optional[List[str]] = None,
    ) -> bool:
        """Evaluate if flag is available for a user/context.
        
        IMPORTANT: This evaluates FEATURE AVAILABILITY only.
        It does NOT evaluate authorization. The caller must combine
        feature availability with authorization checks.
        
        Args:
            organization_id: Tenant ID (must match flag's organization)
            user_id: User identifier for targeting
            context: Additional context for custom rules
            actor_roles: Actor's roles for segment/ring evaluation
            actor_permissions: Actor's permissions for custom rules
            
        Returns:
            True if feature is available, False otherwise
        """
        # Emergency kill switch takes absolute precedence
        if self.emergency_disabled:
            return False
        
        # Feature must be in enabled state
        if self.status != "enabled":
            return False
        
        # Check dependencies - all must be enabled
        # Note: This is a simplified check; full dependency resolution
        # should be done at the service layer with proper graph traversal
        # TODO: Full dependency evaluation
        
        # Check conflicts - none should be enabled
        # TODO: Full conflict evaluation
        
        # Evaluate rollout with explicit precedence
        config = self.rollout_config or {}
        strategy = self.rollout_strategy
        
        # Explicit precedence order: CUSTOM > RING > SEGMENT > PERCENTAGE > ALL
        # If multiple strategies are configured, highest precedence wins
        
        if strategy == "custom":
            rules = config.get("custom_rules", [])
            if self._evaluate_custom_rules(rules, user_id, context, actor_roles, actor_permissions):
                return True
            # If custom rules don't match, fall through to next precedence
        
        if strategy == "ring":
            rings = config.get("rings", [])
            if actor_roles and self._evaluate_ring_membership(rings, actor_roles):
                return True
            # Fall through
        
        if strategy == "segment":
            segments = config.get("segments", [])
            if user_id and self._evaluate_segment_membership(segments, user_id, context):
                return True
            # Fall through
        
        if strategy == "percentage":
            percentage = config.get("percentage", 100.0)
            if user_id:
                # Deterministic hash-based assignment - stable across evaluations
                hash_input = f"{self.id}:{user_id}"
                hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
                return (hash_value % 100) < percentage
            return False
        
        if strategy == "all":
            return True
        
        return False
    
    def _evaluate_custom_rules(
        self,
        rules: List[Dict[str, Any]],
        user_id: Optional[str],
        context: Optional[Dict[str, Any]],
        actor_roles: Optional[List[str]],
        actor_permissions: Optional[List[str]],
    ) -> bool:
        """Evaluate custom rollout rules.
        
        Rules format:
        [
            {"type": "role", "values": ["admin", "manager"], "operator": "any"},
            {"type": "permission", "values": ["feature:x:use"], "operator": "all"},
            {"type": "context", "key": "department", "values": ["engineering"], "operator": "any"},
            {"type": "expression", "expression": "user.tenure_days > 30", "operator": "any"},
        ]
        """
        for rule in rules:
            rule_type = rule.get("type")
            operator = rule.get("operator", "any")
            values = rule.get("values", [])
            
            if rule_type == "role" and actor_roles:
                matches = any(r in actor_roles for r in values)
                if operator == "any" and matches:
                    return True
                elif operator == "all" and not matches:
                    return False
                    
            elif rule_type == "permission" and actor_permissions:
                matches = any(p in actor_permissions for p in values)
                if operator == "any" and matches:
                    return True
                elif operator == "all" and not matches:
                    return False
                    
            elif rule_type == "context" and context:
                key = rule.get("key")
                if key and context.get(key) in values:
                    if operator == "any":
                        return True
                elif operator == "all" and (not key or context.get(key) not in values):
                    return False
                    
            elif rule_type == "expression":
                # Safe expression evaluation - would use a proper expression evaluator
                # For now, return False for unimplemented expressions
                pass
        
        return False
    
    def _evaluate_ring_membership(self, rings: List[str], actor_roles: List[str]) -> bool:
        """Evaluate ring membership based on actor roles."""
        ring_role_mapping = {
            "canary": ["canary", "internal", "admin"],
            "early": ["early", "canary", "internal", "admin"],
            "broad": ["broad", "early", "canary", "internal", "admin"],
        }
        
        for ring in rings:
            allowed_roles = ring_role_mapping.get(ring, [ring])
            if any(role in actor_roles for role in allowed_roles):
                return True
        return False
    
    def _evaluate_segment_membership(
        self,
        segments: List[str],
        user_id: str,
        context: Optional[Dict[str, Any]],
    ) -> bool:
        """Evaluate segment membership.
        
        Segments can be:
        - Static user lists
        - Dynamic segments based on attributes
        - Predefined segments (e.g., "premium_users", "beta_testers")
        """
        # Check static user lists in context
        if context and "segments" in context:
            user_segments = context.get("segments", [])
            if isinstance(user_segments, list):
                if any(s in segments for s in user_segments):
                    return True
        
        # Check predefined segments in metadata
        if context and "user_attributes" in context:
            attrs = context.get("user_attributes", {})
            segment_attrs = {
                "premium_users": lambda a: a.get("plan") == "premium",
                "beta_testers": lambda a: a.get("beta_opt_in", False),
                "internal": lambda a: a.get("is_internal", False),
            }
            for segment in segments:
                if segment in segment_attrs:
                    if segment_attrs[segment](attrs):
                        return True
        
        return False
    
    def is_emergency_disabled(self) -> bool:
        """Check if feature is emergency disabled."""
        return self.emergency_disabled
    
    def can_transition_to(self, new_status: str) -> bool:
        """Check if status transition is valid."""
        return new_status in VALID_STATUS_TRANSITIONS.get(self.status, [])


class FeatureFlagEvaluation(Base):
    """Record of a feature flag evaluation.
    
    This provides audit trail for feature availability decisions.
    Does NOT record authorization decisions - those are separate.
    """
    
    __tablename__ = "feature_flag_evaluations"
    __table_args__ = (
        Index("ix_ffe_org_flag", "organization_id", "feature_flag_id"),
        Index("ix_ffe_user", "user_id"),
        Index("ix_ffe_evaluated", "evaluated_at"),
        Index("ix_ffe_result", "result"),
        Index("ix_ffe_org_user", "organization_id", "user_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"ffe-{uuid.uuid4().hex[:10]}")
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_flag_id: Mapped[str] = mapped_column(
        ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    result: Mapped[bool] = mapped_column(Boolean, nullable=False)
    context_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    
    # Governance context at time of evaluation
    flag_version: Mapped[int] = mapped_column(Integer, default=1)
    flag_status: Mapped[str] = mapped_column(String(20))
    flag_rollout_strategy: Mapped[str] = mapped_column(String(20))
    rollout_config_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class FeatureFlagAuditLog(Base):
    """Audit log for feature flag administrative actions.
    
    Records all governance-relevant changes to feature flags.
    Separate from evaluation log - this is for admin actions.
    """
    
    __tablename__ = "feature_flag_audit_log"
    __table_args__ = (
        Index("ix_ffa_org_flag", "organization_id", "feature_flag_id"),
        Index("ix_ffa_actor", "actor_id"),
        Index("ix_ffa_action", "action"),
        Index("ix_ffa_created", "created_at"),
        Index("ix_ffa_org_created", "organization_id", "created_at"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"ffa-{uuid.uuid4().hex[:10]}")
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_flag_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("feature_flags.id", ondelete="SET NULL"), index=True
    )
    actor_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Actions: create, update, delete, enable, disable, deprecate, archive,
    #          rollout_change, dependency_change, emergency_disable, emergency_enable,
    #          governance_override
    
    # Before/after state for audit trail
    before_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    after_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Governance context
    governance_context: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    # Example: {"approval_id": "...", "policy_version": "...", "justification": "..."}
    
    # Reason for action
    reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Request metadata
    request_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class FeatureFlagHistory(Base):
    """Historical configuration snapshots for longitudinal queries.
    
    Enables answering: "What was the configuration three months ago?"
    Never overwrites - only appends new snapshots.
    """
    
    __tablename__ = "feature_flag_history"
    __table_args__ = (
        Index("ix_ffh_org_flag", "organization_id", "feature_flag_id"),
        Index("ix_ffh_valid_from", "valid_from"),
        Index("ix_ffh_org_valid", "organization_id", "valid_from"),
        UniqueConstraint("feature_flag_id", "valid_from", name="uq_feature_flag_history"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"ffh-{uuid.uuid4().hex[:10]}")
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_flag_id: Mapped[str] = mapped_column(
        ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Configuration snapshot
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    rollout_strategy: Mapped[str] = mapped_column(String(20), nullable=False)
    rollout_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    depends_on: Mapped[List[str]] = mapped_column(JSON, default=list)
    conflicts_with: Mapped[List[str]] = mapped_column(JSON, default=list)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    emergency_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Governance context at time of snapshot
    governance_context: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    
    # Version tracking
    flag_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Validity period - enables longitudinal queries
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    
    # Actor who triggered the snapshot
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


# Re-export for convenience
__all__ = [
    "FeatureFlag",
    "FeatureFlagEvaluation",
    "FeatureFlagAuditLog",
    "FeatureFlagHistory",
    "FeatureFlagStatus",
    "RolloutStrategy",
    "FeatureFlagScope",
    "RolloutPrecedence",
    "VALID_STATUS_TRANSITIONS",
]