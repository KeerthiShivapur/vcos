"""Deployment Completeness — Universal Completeness Dimensions Tracking.

Tracks the 20 universal completeness dimensions as cross-cutting acceptance requirements.
Each dimension is evaluated against the canonical VCOS architecture.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum

from sqlalchemy import (
    String, DateTime, ForeignKey, Index, Integer, JSON, Text, Enum as SQLEnum,
    Boolean
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class CompletenessDimension(str, Enum):
    """The 20 universal completeness dimensions."""
    UNIVERSAL_ORG_TYPES = "universal_org_types"
    UNIVERSAL_ORG_STRUCTURES = "universal_org_structures"
    MULTI_COMPANY_ENTITY = "multi_company_entity"
    LOCALIZATION = "localization"
    ACCESSIBILITY = "accessibility"
    PORTABILITY = "portability"
    INTEROPERABILITY = "interoperability"
    API_DEVELOPER_PLATFORM = "api_developer_platform"
    WORKFLOW_EXTENSIBILITY = "workflow_extensibility"
    INDUSTRY_EXTENSIONS = "industry_extensions"
    MA_CONTINUITY = "ma_continuity"
    LEGAL_COMPLIANCE_RECORDS = "legal_compliance_records"
    RESIDENCY_SOVEREIGN_DEPLOYMENT = "residency_sovereign_deployment"
    AI_PROVIDER_INDEPENDENCE = "ai_provider_independence"
    AI_GOVERNANCE = "ai_governance"
    HUMAN_OVERRIDE_DEGRADATION = "human_override_degradation"
    MIGRATION_INTELLIGENCE = "migration_intelligence"
    TRUST_CENTER = "trust_center"
    COST_USAGE_INTELLIGENCE = "cost_usage_intelligence"
    UNIVERSAL_ONBOARDING = "universal_onboarding"


class CompletenessStatus(str, Enum):
    """Completeness evaluation status."""
    NOT_EVALUATED = "not_evaluated"
    NOT_YET_IMPLEMENTED = "not_yet_implemented"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    VERIFIED = "verified"
    VERIFIED_WITH_WARNINGS = "verified_with_warnings"


class DeploymentCompletenessMatrix(Base):
    """Universal Completeness Matrix for a deployment.
    
    Tracks all 20 dimensions with evidence and status.
    """
    
    __tablename__ = "deployment_completeness_matrices"
    __table_args__ = (
        Index("ix_dcm_org_deployment", "organization_id", "deployment_id"),
        Index("ix_dcm_status", "overall_status"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"dcm-{uuid.uuid4().hex[:12]}")
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Overall status
    overall_status: Mapped[str] = mapped_column(
        SQLEnum(CompletenessStatus, values_callable=lambda x: [e.value for e in CompletenessStatus]),
        default=CompletenessStatus.NOT_EVALUATED, nullable=False
    )
    dimensions_passed: Mapped[int] = mapped_column(Integer, default=0)
    dimensions_total: Mapped[int] = mapped_column(Integer, default=20)
    dimensions_partial: Mapped[int] = mapped_column(Integer, default=0)
    dimensions_blocked: Mapped[int] = mapped_column(Integer, default=0)
    dimensions_not_implemented: Mapped[int] = mapped_column(Integer, default=0)
    
    # Metadata
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    evaluated_by: Mapped[Optional[str]] = mapped_column(String(32))
    evidence_summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    dimensions = relationship("DeploymentCompletenessDimension", back_populates="matrix", cascade="all, delete-orphan")


class DeploymentCompletenessDimension(Base):
    """Individual dimension evaluation within a completeness matrix."""
    
    __tablename__ = "deployment_completeness_dimensions"
    __table_args__ = (
        Index("ix_dcd_matrix_dimension", "matrix_id", "dimension"),
        Index("ix_dcd_status", "status"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"dcd-{uuid.uuid4().hex[:12]}")
    matrix_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("deployment_completeness_matrices.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    
    dimension: Mapped[str] = mapped_column(
        SQLEnum(CompletenessDimension, values_callable=lambda x: [e.value for e in CompletenessDimension]),
        nullable=False
    )
    status: Mapped[str] = mapped_column(
        SQLEnum(CompletenessStatus, values_callable=lambda x: [e.value for e in CompletenessStatus]),
        default=CompletenessStatus.NOT_EVALUATED, nullable=False
    )
    
    # Evaluation details
    canonical_dependency: Mapped[Optional[str]] = mapped_column(Text)  # Which canonical system this depends on
    capability: Mapped[Optional[str]] = mapped_column(Text)  # What capability this dimension provides
    validation_method: Mapped[Optional[str]] = mapped_column(Text)  # How it's validated
    test_reference: Mapped[Optional[str]] = mapped_column(Text)  # Reference to test
    
    # Evidence
    evidence: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    evidence_quality: Mapped[Optional[str]] = mapped_column(String(32))  # executable, documented, asserted
    
    # Limitations and blockers
    limitation: Mapped[Optional[str]] = mapped_column(Text)
    blocker_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Metadata
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    evaluated_by: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Relationship
    matrix = relationship("DeploymentCompletenessMatrix", back_populates="dimensions")


class DeploymentVerificationCheck(Base):
    """Verification check for a deployment (from DeploymentContract)."""
    
    __tablename__ = "deployment_verification_checks"
    __table_args__ = (
        Index("ix_dvc_deployment_type", "deployment_id", "check_type"),
        Index("ix_dvc_status", "passed"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"dvc-{uuid.uuid4().hex[:12]}")
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    
    check_type: Mapped[str] = mapped_column(String(64), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Capability awareness
    required_capabilities: Mapped[Optional[List[str]]] = mapped_column(JSON)
    available_capabilities: Mapped[Optional[List[str]]] = mapped_column(JSON)
    dialect: Mapped[Optional[str]] = mapped_column(String(32))


class DeploymentRecord(Base):
    """Canonical deployment record with full audit trail."""
    
    __tablename__ = "deployment_records"
    __table_args__ = (
        Index("ix_dr_org_status", "organization_id", "status"),
        Index("ix_dr_version", "version"),
        Index("ix_dr_started", "started_at"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"dep-{uuid.uuid4().hex[:12]}")
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    
    # Contract
    contract_id: Mapped[Optional[str]] = mapped_column(String(64))
    contract_passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    
    # Completeness
    completeness_matrix_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("deployment_completeness_matrices.id", ondelete="SET NULL")
    )
    
    # Feature flags
    feature_flags_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deployed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Rollback
    rolled_back: Mapped[bool] = mapped_column(Boolean, default=False)
    rollback_reason: Mapped[Optional[str]] = mapped_column(Text)
    rollback_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rollback_deployment_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Error
    error: Mapped[Optional[str]] = mapped_column(Text)
    
    # Metadata
    initiated_by: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


# Backup/Restore/DR Models are in backup_manifest.py

# Re-export
__all__ = [
    "CompletenessDimension",
    "CompletenessStatus",
    "DeploymentCompletenessMatrix",
    "DeploymentCompletenessDimension",
    "DeploymentVerificationCheck",
    "DeploymentRecord",
]