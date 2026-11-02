"""35-I — Longitudinal / 10-Year Company Reality.

This module implements the longitudinal architecture that preserves company reality
across time without overwriting historical truth.

Key principles:
- ONE canonical company reality with temporal depth
- Historical state is immutable and queryable
- Knowledge timeline distinct from reality timeline
- Decision/learning provenance preserved across decades
- Organizational continuity across M&A, leadership changes
- Epistemic calibration preserved across time
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Literal
from enum import Enum

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
    and_,
    or_,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid
from app.models.organization import Organization


# =============================================================================
# VOCABULARIES
# =============================================================================

# Timeline types
TIMELINE_TYPES = (
    "reality",           # What actually happened (canonical reality)
    "knowledge",         # What the company knew/believed at the time
    "decision",          # Decision provenance and authority
    "learning",          # Learning events and calibration
    "organizational",    # Organizational structure changes
    "governance",        # Governance/policy changes
)

# Epistemic states (extended for longitudinal)
EPISTEMIC_STATES_LONGITUDINAL = (
    "UNKNOWN",
    "EXPECTED",
    "PREDICTED",
    "RECOMMENDED",
    "OBSERVED",
    "EVIDENCE_BACKED",
    "INFERRED",
    "MEASURED",
    "CONFIRMED",
    "CONFIRMED_CORRECTED",
    "CONFLICTING",
    "SUPERSEDED",
    "HISTORICAL",
    "ARCHIVED",
)

# Snapshot types
SNAPSHOT_TYPES = (
    "FULL",              # Complete state snapshot
    "DELTA",             # Incremental change
    "MILESTONE",         # Significant event marker
    "RECOVERY",          # Post-recovery snapshot
    "RECONCILIATION",    # Post-reconciliation snapshot
    "MIGRATION",         # Migration snapshot
)


# =============================================================================
# LONGITUDINAL ENTITY BASE
# =============================================================================

class LongitudinalMixin:
    """Mixin for entities that participate in longitudinal tracking."""
    
    # Temporal identity
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    
    # Supersession chain
    supersedes_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("id"), nullable=True, index=True
    )
    superseded_by_id: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True
    )
    
    # Temporal validity
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    valid_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    
    # Observed vs effective
    observed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    
    # Provenance
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    recorded_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Epistemic state
    epistemic_state: Mapped[str] = mapped_column(
        String(32), default="OBSERVED", index=True
    )
    confidence: Mapped[float] = mapped_column(default=1.0)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# COMPANY TIMELINE — Universal company event timeline
# =============================================================================

class CompanyTimelineEvent(Base, TimestampMixin):
    """
    Universal Company Timeline — single source of truth for all significant
    company events across all timelines (reality, knowledge, decision, learning,
    organizational, governance).
    
    This is the single canonical timeline. All domain-specific timelines
    (decisions, commitments, organizational changes, learning events, etc.)
    project from this single timeline.
    """
    
    __tablename__ = "company_timeline_events"
    __table_args__ = (
        Index("ix_cte_org_time", "organization_id", "occurred_at"),
        Index("ix_cte_org_type_time", "organization_id", "timeline_type", "occurred_at"),
        Index("ix_cte_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_cte_correlation", "correlation_id"),
        UniqueConstraint(
            "organization_id", "event_key",
            name="uq_cte_org_event_key"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Event identity
    event_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    timeline_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)  # TIMELINE_TYPES
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    event_subtype: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    
    # Entity reference
    entity_type: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Correlation for multi-entity events
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    parent_event_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Timing
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    
    # State change
    from_state: Mapped[Optional[str]] = mapped_column(String(60))
    to_state: Mapped[Optional[str]] = mapped_column(String(60))
    
    # Change details
    change_summary: Mapped[str] = mapped_column(Text)
    delta_json: Mapped[Optional[dict]] = mapped_column(JSON)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Epistemic
    epistemic_state: Mapped[str] = mapped_column(String(32), default="OBSERVED")
    confidence: Mapped[float] = mapped_column(default=1.0)
    recorded_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    recorded_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Correlation
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    caused_by_event_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# KNOWLEDGE TIMELINE — What the company knew vs what happened
# =============================================================================

class CompanyKnowledgeSnapshot(Base, TimestampMixin):
    """
    Knowledge Timeline — preserves what the company knew/believed at each point.
    
    Distinct from reality timeline: records epistemic state, not just facts.
    """
    
    __tablename__ = "company_knowledge_snapshots"
    __table_args__ = (
        Index("ix_cks_org_time", "organization_id", "snapshot_at"),
        Index("ix_cks_org_claim", "organization_id", "claim_id"),
        Index("ix_cks_epistemic", "epistemic_state"),
        UniqueConstraint(
            "organization_id", "claim_id", "snapshot_at",
            name="uq_cks_org_claim_time"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Claim reference
    claim_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    claim_type: Mapped[str] = mapped_column(String(60), index=True)
    claim_version: Mapped[int] = mapped_column(Integer)
    
    # Snapshot timing
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    valid_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    
    # Epistemic state
    epistemic_state: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True  # EPISTEMIC_STATES_LONGITUDINAL
    )
    confidence: Mapped[float] = mapped_column(default=1.0)
    
    # What was known/believed
    belief_json: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    contradiction_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    
    # Provenance
    evidence_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    recorded_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Correction tracking
    corrected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    corrected_by: Mapped[Optional[str]] = mapped_column(String(64))
    correction_reason: Mapped[Optional[str]] = mapped_column(Text)
    supersedes_snapshot_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# DECISION TIMELINE — Decision provenance across time
# =============================================================================

class DecisionTimelineEvent(Base, TimestampMixin):
    """
    Decision Timeline — preserves full decision provenance across time.
    
    Links to existing CompanyDecision but adds temporal projection capability.
    """
    
    __tablename__ = "decision_timeline_events"
    __table_args__ = (
        Index("ix_dte_org_time", "organization_id", "occurred_at"),
        Index("ix_dte_org_decision", "organization_id", "decision_id"),
        Index("ix_dte_event_type", "event_type"),
        UniqueConstraint(
            "organization_id", "decision_id", "event_key",
            name="uq_dte_org_decision_event"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Decision reference
    decision_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    decision_version: Mapped[int] = mapped_column(Integer)
    
    # Event identity
    event_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)  # CREATED, AUTHORIZED, EXECUTED, OUTCOME, SUPERSEDED, CORRECTED
    
    # Timing
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    
    # State transition
    from_state: Mapped[Optional[str]] = mapped_column(String(60))
    to_state: Mapped[Optional[str]] = mapped_column(String(60))
    
    # Decision details at this point
    decision_json: Mapped[dict] = mapped_column(JSON, default=dict)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    evidence_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    
    # Authorization
    authorized_by: Mapped[Optional[str]] = mapped_column(String(64))
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Outcome
    outcome_json: Mapped[Optional[dict]] = mapped_column(JSON)
    outcome_assessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Supersession
    supersedes_event_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    superseded_by_event_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Epistemic
    epistemic_state: Mapped[str] = mapped_column(String(32), default="OBSERVED")
    confidence: Mapped[float] = mapped_column(default=1.0)
    
    # Provenance
    recorded_by: Mapped[Optional[str]] = mapped_column(String(64))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# LEARNING TIMELINE — Learning events and calibration across time
# =============================================================================

class LearningTimelineEvent(Base, TimestampMixin):
    """
    Learning Timeline — preserves learning events and calibration across time.
    
    Captures the full learning loop: prediction -> outcome -> verification -> learning -> calibration
    """
    
    __tablename__ = "learning_timeline_events"
    __table_args__ = (
        Index("ix_lte_org_time", "organization_id", "occurred_at"),
        Index("ix_lte_org_kind", "organization_id", "learning_kind"),
        Index("ix_lte_outcome", "outcome_state"),
        UniqueConstraint(
            "organization_id", "event_key",
            name="uq_lte_org_event"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Event identity
    event_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    learning_kind: Mapped[str] = mapped_column(String(60), index=True)  # PREDICTION, OUTCOME, VERIFICATION, LEARNING, CALIBRATION
    event_subtype: Mapped[Optional[str]] = mapped_column(String(60))
    
    # Timing
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    prediction_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    outcome_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    calibrated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Content
    prediction_json: Mapped[Optional[dict]] = mapped_column(JSON)
    outcome_json: Mapped[Optional[dict]] = mapped_column(JSON)
    verification_json: Mapped[Optional[dict]] = mapped_column(JSON)
    learning_json: Mapped[Optional[dict]] = mapped_column(JSON)
    calibration_json: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Outcome
    outcome_state: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING, VERIFIED, CALIBRATED, SUPERSEDED
    prediction_json: Mapped[Optional[dict]] = mapped_column(JSON)
    actual_outcome_json: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Calibration
    calibration_delta: Mapped[Optional[float]] = mapped_column()
    confidence_before: Mapped[Optional[float]] = mapped_column()
    confidence_after: Mapped[Optional[float]] = mapped_column()
    
    # Evidence
    evidence_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    source_event_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    
    # Provenance
    recorded_by: Mapped[Optional[str]] = mapped_column(String(64))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# ORGANIZATIONAL TIMELINE — Structure and people changes over time
# =============================================================================

class OrganizationalTimelineEvent(Base, TimestampMixin):
    """
    Organizational Timeline — structure, people, and governance changes over time.
    """
    
    __tablename__ = "organizational_timeline_events"
    __table_args__ = (
        Index("ix_ote_org_time", "organization_id", "occurred_at"),
        Index("ix_ote_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_ote_kind", "event_kind"),
        UniqueConstraint(
            "organization_id", "event_key",
            name="uq_ote_org_event"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Event identity
    event_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    event_kind: Mapped[str] = mapped_column(String(60), index=True)  # HIRE, TERMINATE, PROMOTE, TRANSFER, REORG, MERGE, ACQUIRE, SPINOFF, POLICY_CHANGE
    event_subtype: Mapped[Optional[str]] = mapped_column(String(60))
    
    # Entity
    entity_type: Mapped[str] = mapped_column(String(60), index=True)  # EMPLOYEE, DEPARTMENT, TEAM, ROLE, POLICY, LEGAL_ENTITY
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_name: Mapped[Optional[str]] = mapped_column(String(240))
    
    # Timing
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    
    # Change
    from_state_json: Mapped[Optional[dict]] = mapped_column(JSON)
    to_state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    change_summary: Mapped[str] = mapped_column(Text)
    
    # Actor
    actor_id: Mapped[Optional[str]] = mapped_column(String(64))
    actor_type: Mapped[Optional[str]] = mapped_column(String(24))  # HUMAN, SYSTEM, AUTONOMOUS
    
    # Governance
    authorized_by: Mapped[Optional[str]] = mapped_column(String(64))
    policy_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    recorded_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# M&A CONTINUITY — Lineage preservation across mergers/acquisitions
# =============================================================================

class MergerAcquisitionLineage(Base, TimestampMixin):
    """
    M&A Continuity — preserves lineage across mergers and acquisitions.
    
    Ensures historical events remain attributable to original entities
    while establishing new combined entity identity.
    """
    
    __tablename__ = "merger_acquisition_lineage"
    __table_args__ = (
        Index("ix_mal_org_time", "organization_id", "transaction_date"),
        Index("ix_mal_predecessor", "predecessor_type", "predecessor_id"),
        Index("ix_mal_successor", "successor_type", "successor_id"),
        UniqueConstraint(
            "organization_id", "predecessor_id", "successor_id",
            name="uq_mal_lineage"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Transaction
    transaction_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(24), index=True)  # MERGER, ACQUISITION, SPINOFF, DIVESTITURE, REORG
    
    # Entities
    predecessor_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    predecessor_type: Mapped[str] = mapped_column(String(24), index=True)  # COMPANY, DIVISION, DEPARTMENT, TEAM
    predecessor_name: Mapped[str] = mapped_column(String(240))
    
    successor_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    successor_type: Mapped[str] = mapped_column(String(24), index=True)
    successor_name: Mapped[str] = mapped_column(String(240))
    
    # Transaction details
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    
    # Transaction details
    transaction_details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    consideration_json: Mapped[Optional[dict]] = mapped_column(JSON)
    terms_json: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Lineage mapping
    entity_mappings_json: Mapped[list] = mapped_column(JSON, default=list)  # [{"from_entity_id": "...", "from_entity_type": "...", "to_entity_id": "...", "to_entity_type": "..."}]
    attribute_mappings_json: Mapped[list] = mapped_column(JSON, default=list)
    
    # Historical preservation
    preserve_history: Mapped[bool] = mapped_column(Boolean, default=True)
    history_scope_json: Mapped[list] = mapped_column(JSON, default=list)  # Which historical records to preserve
    
    # Governance
    authorized_by: Mapped[Optional[str]] = mapped_column(String(64))
    policy_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    recorded_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# LONGITUDINAL PROVENANCE — Evidence chain across time
# =============================================================================

class LongitudinalProvenance(Base, TimestampMixin):
    """
    Longitudinal Provenance — evidence chain that spans across time.
    
    Ensures evidence remains traceable even after:
    - Source changes
    - Source deletion
    - Employee departure
    - Integration replacement
    - Organizational restructuring
    """
    
    __tablename__ = "longitudinal_provenance"
    __table_args__ = (
        Index("ix_lp_org_time", "organization_id", "created_at"),
        Index("ix_lp_entity", "entity_type", "entity_id"),
        Index("ix_lp_chain", "chain_id"),
        UniqueConstraint(
            "organization_id", "chain_id", "sequence",
            name="uq_lp_chain_seq"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Chain
    chain_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Link
    entity_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    attribute: Mapped[Optional[str]] = mapped_column(String(120))
    
    # Provenance at this point
    value_json: Mapped[Optional[dict]] = mapped_column(JSON)
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Chain integrity
    previous_hash: Mapped[Optional[str]] = mapped_column(String(64))
    current_hash: Mapped[str] = mapped_column(String(64))
    
    # Timing
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    
    # Chain integrity
    is_genesis: Mapped[bool] = mapped_column(Boolean, default=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    broken: Mapped[bool] = mapped_column(Boolean, default=False)
    broken_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# LONGITUDINAL EPISTEMIC CALIBRATION
# =============================================================================

class EpistemicCalibrationEvent(Base, TimestampMixin):
    """
    Epistemic Calibration — tracks how confidence/understanding evolves over time.
    
    Captures: prediction -> outcome -> verification -> learning -> calibration loop
    """
    
    __tablename__ = "epistemic_calibration_events"
    __table_args__ = (
        Index("ix_ece_org_time", "organization_id", "occurred_at"),
        Index("ix_ece_claim", "claim_id"),
        Index("ix_ece_state", "calibration_state"),
        UniqueConstraint(
            "organization_id", "claim_id", "event_key",
            name="uq_ece_org_claim_event"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Claim reference
    claim_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    claim_type: Mapped[str] = mapped_column(String(60), index=True)
    
    # Event
    event_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)  # PREDICTION, OUTCOME, VERIFICATION, LEARNING, CALIBRATION
    
    # Timing
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    prediction_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    outcome_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    calibrated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # States
    calibration_state: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING, VERIFIED, CALIBRATED, SUPERSEDED
    prediction_state: Mapped[Optional[str]] = mapped_column(String(32))
    outcome_state: Mapped[Optional[str]] = mapped_column(String(32))
    verification_state: Mapped[Optional[str]] = mapped_column(String(32))
    calibration_state: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Content
    prediction_json: Mapped[Optional[dict]] = mapped_column(JSON)
    outcome_json: Mapped[Optional[dict]] = mapped_column(JSON)
    verification_json: Mapped[Optional[dict]] = mapped_column(JSON)
    learning_json: Mapped[Optional[dict]] = mapped_column(JSON)
    calibration_json: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Calibration
    confidence_before: Mapped[Optional[float]] = mapped_column()
    confidence_after: Mapped[Optional[float]] = mapped_column()
    calibration_delta: Mapped[Optional[float]] = mapped_column()
    
    # Evidence
    evidence_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    source_event_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    
    # Provenance
    recorded_by: Mapped[Optional[str]] = mapped_column(String(64))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# COMPANY MEMORY — Living Company Memory derived from canonical reality
# =============================================================================

class CompanyMemorySnapshot(Base, TimestampMixin):
    """
    Company Memory Snapshot — a point-in-time materialized view of what the
    company knows, derived from canonical reality + evidence + temporal context.
    
    Memory is a derived projection, NOT an independent truth store.
    """
    
    __tablename__ = "company_memory_snapshots"
    __table_args__ = (
        Index("ix_cms_org_time", "organization_id", "snapshot_at"),
        Index("ix_cms_org_scope", "organization_id", "scope_type", "scope_id"),
        UniqueConstraint(
            "organization_id", "snapshot_key",
            name="uq_cms_org_snapshot"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Snapshot identity
    snapshot_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(24), default="company", index=True)  # company, department, team, project, person
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Content
    memory_json: Mapped[dict] = mapped_column(JSON, default=dict)
    knowledge_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    decisions_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    learning_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    open_contradictions_json: Mapped[list] = mapped_column(JSON, default=list)
    health_signals_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Provenance
    source_event_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    derived_from_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Epistemic
    epistemic_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(default=1.0)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# ASK THE COMPANY ANYTHING — Temporal query capability
# =============================================================================

class TemporalQueryLog(Base, TimestampMixin):
    """
    Ask the Company Anything — temporal query log with provenance.
    
    Every temporal query is logged for audit and learning.
    """
    
    __tablename__ = "temporal_query_log"
    __table_args__ = (
        Index("ix_tql_org_time", "organization_id", "created_at"),
        Index("ix_tql_user", "user_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # Query
    query_text: Mapped[str] = mapped_column(Text)
    query_type: Mapped[str] = mapped_column(String(32))  # CURRENT, HISTORICAL, TEMPORAL_RANGE, CAUSAL, WHAT_IF
    query_params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Temporal scope
    time_range_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    time_range_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    as_of: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Scope
    scope_type: Mapped[Optional[str]] = mapped_column(String(24))
    scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Result
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    result_summary: Mapped[Optional[str]] = mapped_column(Text)
    result_epistemic_state: Mapped[Optional[str]] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(default=1.0)
    
    # Provenance
    source_event_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    evidence_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    
    # Performance
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    rows_scanned: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Actor
    user_id: Mapped[Optional[str]] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(24), default="human")  # human, agent, system


# =============================================================================
# FUTURE SIMULATOR CALIBRATION — Historical outcome calibration
# =============================================================================

class FutureSimulatorCalibration(Base, TimestampMixin):
    """
    Future Simulator Calibration — calibrates simulation engine against
    historical outcomes to improve predictive accuracy.
    
    Tracks: simulation -> projection -> actual outcome -> calibration
    """
    
    __tablename__ = "future_simulator_calibrations"
    __table_args__ = (
        Index("ix_fsc_org_time", "organization_id", "created_at"),
        Index("ix_fsc_scenario", "scenario_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Scenario
    scenario_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scenario_name: Mapped[str] = mapped_column(String(240))
    scenario_type: Mapped[str] = mapped_column(String(60))  # MONTE_CARLO, AGENT_BASED, MONTE_CARLO_TREE, DIFFERENTIAL
    
    # Parameters
    parameters_json: Mapped[dict] = mapped_column(JSON, default=dict)
    assumptions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    time_horizon_days: Mapped[int] = mapped_column(Integer)
    
    # Historical calibration
    calibration_period_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calibration_period_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    historical_outcomes_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Calibration results
    calibration_score: Mapped[float] = mapped_column(default=0.0)
    calibration_details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    bias_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    bias_correction_json: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Projection
    projection_json: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_interval_json: Mapped[dict] = mapped_column(JSON, default=dict)
    uncertainty_bands_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Validation
    validated_against_actual: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_error_json: Mapped[Optional[dict]] = mapped_column(JSON)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# LONGITUDINAL INTEGRITY CHECKER
# =============================================================================

class LongitudinalIntegrityFinding(Base, TimestampMixin):
    """
    Longitudinal Integrity Finder — detects inconsistencies in historical chains.
    
    Detects:
    - broken temporal chains
    - overlapping impossible intervals
    - missing provenance
    - invalid supersession
    - cross-tenant historical references
    - epistemic regressions
    - orphaned history
    - duplicate events
    - timeline inconsistencies
    """
    
    __tablename__ = "longitudinal_integrity_findings"
    __table_args__ = (
        Index("ix_lif_org_time", "organization_id", "detected_at"),
        Index("ix_lif_type", "finding_type"),
        Index("ix_lif_entity", "entity_type", "entity_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Finding
    finding_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    finding_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium")  # low, medium, high, critical
    
    # Entity
    entity_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    
    # Details
    description: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    affected_entities_json: Mapped[list] = mapped_column(JSON, default=list)
    affected_time_range_json: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Detection
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    detection_method: Mapped[str] = mapped_column(String(40))  # automated, manual, scheduled, reported
    
    # Resolution
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, investigating, resolved, accepted_risk, false_positive
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[Optional[str]] = mapped_column(String(64))
    resolution_json: Mapped[Optional[dict]] = mapped_column(JSON)
    remediation_json: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Governance
    requires_governance: Mapped[bool] = mapped_column(Boolean, default=False)
    governance_scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    authorized_by: Mapped[Optional[str]] = mapped_column(String(64))
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# ADVERSARIAL TEST EVENTS
# =============================================================================

class LongitudinalAdversarialTest(Base, TimestampMixin):
    """
    Adversarial Test Events — records adversarial test attempts for
    continuous improvement of longitudinal defenses.
    """
    
    __tablename__ = "longitudinal_adversarial_tests"
    __table_args__ = (
        Index("ix_lat_org_time", "organization_id", "created_at"),
        Index("ix_lat_type", "attack_type"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Attack
    attack_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    attack_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    
    # Payload
    attack_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    target_entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    target_entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Result
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    error_code: Mapped[Optional[str]] = mapped_column(String(60))
    
    # Timing
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    
    # Actor
    actor_id: Mapped[Optional[str]] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(24), default="adversarial_test")


# =============================================================================
# TENANT HISTORICAL ISOLATION
# =============================================================================

class TenantHistoricalIsolation(Base, TimestampMixin):
    """
    Tenant Historical Isolation — enforces tenant boundaries on historical data.
    
    Ensures historical queries and reconstructions never cross tenant boundaries.
    """
    
    __tablename__ = "tenant_historical_isolation"
    __table_args__ = (
        Index("ix_thi_source_time", "source_org_id", "attempted_at"),
        Index("ix_thi_cross", "source_org_id", "target_org_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    
    # Source tenant
    source_org_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_org_name: Mapped[Optional[str]] = mapped_column(String(240))
    
    # Target tenant (if cross-tenant reference attempted)
    target_org_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    target_org_name: Mapped[Optional[str]] = mapped_column(String(240))
    
    # Attempt
    attempt_type: Mapped[str] = mapped_column(String(40))  # QUERY, MUTATION, RECONSTRUCTION, IMPORT, MIGRATION
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Result
    blocked: Mapped[bool] = mapped_column(Boolean, default=True)
    rejection_reason: Mapped[str] = mapped_column(Text)
    
    # Context
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    actor_id: Mapped[Optional[str]] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(24), default="system")
    
    # Evidence
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)


# =============================================================================
# TEMPORAL INDEXES FOR PERFORMANCE
# =============================================================================

# These would be created as database indexes via migrations
# Included here for documentation of the longitudinal index strategy

TEMPORAL_INDEXES = """
-- Point-in-time queries
CREATE INDEX IF NOT EXISTS ix_cte_org_time ON company_timeline_events (organization_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_cte_org_effective ON company_timeline_events (organization_id, effective_from, effective_to);
CREATE INDEX IF NOT EXISTS ix_cks_org_time ON company_knowledge_snapshots (organization_id, snapshot_at);
CREATE INDEX IF NOT EXISTS ix_dte_org_time ON decision_timeline_events (organization_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_lte_org_time ON learning_timeline_events (organization_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_ote_org_time ON organizational_timeline_events (organization_id, occurred_at);

-- Range queries
CREATE INDEX IF NOT EXISTS ix_cte_range ON company_timeline_events (organization_id, effective_from, effective_to);
CREATE INDEX IF NOT EXISTS ix_cks_range ON company_knowledge_snapshots (organization_id, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS ix_dte_range ON decision_timeline_events (organization_id, effective_from, effective_to);

-- Supersession chains
CREATE INDEX IF NOT EXISTS ix_cte_supersedes ON company_timeline_events (organization_id, supersedes_event_id);
CREATE INDEX IF NOT EXISTS ix_dte_supersedes ON decision_timeline_events (organization_id, supersedes_event_id);

-- Correlation
CREATE INDEX IF NOT EXISTS ix_cte_correlation ON company_timeline_events (correlation_id);
CREATE INDEX IF NOT EXISTS ix_cte_caused_by ON company_timeline_events (caused_by_event_id);

-- Tenant isolation
CREATE INDEX IF NOT EXISTS ix_thi_cross ON tenant_historical_isolation (source_org_id, target_org_id);

-- Provenance chains
CREATE INDEX IF NOT EXISTS ix_lp_chain ON longitudinal_provenance (chain_id, sequence);
CREATE INDEX IF NOT EXISTS ix_lp_entity ON longitudinal_provenance (entity_type, entity_id);

-- Temporal ranges
CREATE INDEX IF NOT EXISTS ix_lte_range ON learning_timeline_events (organization_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_ote_range ON organizational_timeline_events (organization_id, effective_from, effective_to);
CREATE INDEX IF NOT EXISTS ix_ece_range ON epistemic_calibration_events (organization_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_cms_time ON company_memory_snapshots (organization_id, snapshot_at);
"""


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Vocabularies
    "TIMELINE_TYPES",
    "EPISTEMIC_STATES_LONGITUDINAL",
    "SNAPSHOT_TYPES",
    
    # Mixins
    "LongitudinalMixin",
    
    # Timeline models
    "CompanyTimelineEvent",
    "CompanyKnowledgeSnapshot",
    "DecisionTimelineEvent",
    "LearningTimelineEvent",
    "OrganizationalTimelineEvent",
    "MergerAcquisitionLineage",
    
    # Provenance and calibration
    "LongitudinalProvenance",
    "EpistemicCalibrationEvent",
    
    # Memory and querying
    "CompanyMemorySnapshot",
    "TemporalQueryLog",
    "FutureSimulatorCalibration",
    
    # Integrity and adversarial
    "LongitudinalIntegrityFinding",
    "LongitudinalAdversarialTest",
    
    # Tenant isolation
    "TenantHistoricalIsolation",
    
    # Indexes
    "TEMPORAL_INDEXES",
]

# Import at the end to avoid circular imports
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import DateTime, Boolean
from app.models.organization import TimestampMixin, gen_uuid