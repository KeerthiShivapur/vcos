"""Canonical Knowledge, Documents & Institutional Context Fabric — Gate 20.

This is the SINGLE canonical knowledge layer. It does NOT create a parallel
knowledge graph/brain/RAG system. All knowledge becomes part of the same
canonical company reality.

Key architectural principles:
- Document statement ≠ Company fact ≠ Observed behavior ≠ Verified outcome
- Knowledge artifacts carry provenance, temporal validity, supersession
- Claims are extracted from artifacts and linked to canonical reality
- Conflicts are preserved, not silently overwritten
- External sources (Drive, SharePoint, Notion, Confluence, Slack, Email, Jira, CRM, ERP)
  retain explicit source identity — never silently become unquestioned truth
"""

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# KNOWLEDGE ARTIFACT KINDS — The unified taxonomy
# =============================================================================

KNOWLEDGE_ARTIFACT_KINDS = (
    "policy",           # Governance policies (approval thresholds, delegation of authority)
    "sop",              # Standard operating procedures
    "manual",           # Handbooks, runbooks, operational manuals
    "specification",    # Technical specs, requirements, architecture docs
    "contract",         # Contracts, agreements, legal documents
    "template",         # Reusable templates (documents, processes, checklists)
    "guideline",        # Guidelines, best practices, recommendations
    "standard",         # Standards (coding, security, quality)
    "regulation",       # External regulations, compliance requirements
    "decision_record",  # ADRs, meeting decisions, architectural decisions
    "lesson",           # Institutional lessons learned
    "report",           # Reports, analyses, research
    "meeting_artifact", # Meeting notes, minutes, action items
    "training",         # Training materials, onboarding content
    "faq",              # Frequently asked questions
    "knowledge_article",# General knowledge articles, wiki content
    "requirements",     # Product/feature requirements
    "design",           # Design documents, UX/UI specs
    "incident_report",  # Incident postmortems, RCA
    "audit_finding",    # Audit findings, compliance gaps
    "risk_assessment",  # Risk assessments, threat models
    "external_import",  # Imported from Drive/SharePoint/Notion/Confluence/Slack/Email/Jira/CRM/ERP
)

ARTIFACT_LIFECYCLE_STATES = (
    "draft",           # Being authored
    "in_review",       # Under review/approval
    "published",       # Active and authoritative
    "superseded",      # Replaced by newer version
    "archived",        # Historical reference only
    "withdrawn",       # Explicitly retracted
)

ARTIFACT_SCOPES = (
    "organization",    # Organization-wide
    "department",      # Department-scoped
    "team",            # Team-scoped
    "project",         # Project-scoped
    "personal",        # Personal/private
)

EXTERNAL_SOURCES = (
    "google_drive",
    "sharepoint",
    "notion",
    "confluence",
    "slack",
    "email",
    "jira",
    "crm",
    "erp",
    "github",
    "gitlab",
    "figma",
    "miro",
    "web",
    "pdf_upload",
    "manual_entry",
)


# =============================================================================
# CANONICAL KNOWLEDGE ARTIFACT — The single knowledge entity
# =============================================================================

class CanonicalKnowledgeArtifact(Base, TimestampMixin):
    """
    Canonical Knowledge Artifact — the single representation of company knowledge.
    
    Subsumes: Document, WikiPage, Policy, SOP, Template, Decision, and all
    future knowledge types. Every piece of company knowledge is one of these.
    
    Key distinctions from legacy models:
    - Temporal validity (valid_from, valid_to) for historical queries
    - Explicit supersession chain (supersedes_id, superseded_by_id)
    - Full provenance (source, author, modification history, external origin)
    - Epistemic status: what the artifact SAYS vs what the company DOES
    - Conflict tracking: conflicting artifacts preserved, not overwritten
    - Exact-once via fingerprint + unique constraint
    """
    
    __tablename__ = "canonical_knowledge_artifacts"
    __table_args__ = (
        Index("ix_cka_org_kind", "organization_id", "kind"),
        Index("ix_cka_org_state", "organization_id", "lifecycle_state"),
        Index("ix_cka_org_scope", "organization_id", "scope", "scope_id"),
        Index("ix_cka_org_valid", "organization_id", "valid_from", "valid_to"),
        Index("ix_cka_org_owner", "organization_id", "owner_id"),
        Index("ix_cka_org_topic", "organization_id", "primary_topic_id"),
        Index("ix_cka_fingerprint", "organization_id", "fingerprint"),
        # Exact-once per (org, fingerprint)
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_cka_fingerprint_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Core identity
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)  # Full text/markdown
    summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    
    # Classification
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # KNOWLEDGE_ARTIFACT_KINDS
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    tags_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    
    # Scope & governance
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="organization", index=True)  # ARTIFACT_SCOPES
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # department_id, team_id, project_id
    lifecycle_state: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)  # ARTIFACT_LIFECYCLE_STATES
    
    # Versioning & temporal validity
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)  # Null = currently valid
    supersedes_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # Previous version this replaces
    superseded_by_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # Next version that replaces this
    
    # Ownership & authorship
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # Person/team responsible
    owner_type: Mapped[Optional[str]] = mapped_column(String(30))  # person|team|department|role
    author_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    approver_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[Optional[str]] = mapped_column(Text)
    
    # Review cycle
    review_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_reviewed_by: Mapped[Optional[str]] = mapped_column(String(64))
    review_cadence_days: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Provenance — CRITICAL for epistemic boundaries
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="internal", index=True)  # EXTERNAL_SOURCES + "internal"
    source_id: Mapped[Optional[str]] = mapped_column(String(120), index=True)  # External system ID
    external_ref: Mapped[Optional[str]] = mapped_column(String(500), index=True)  # URL/path in external system
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # For change detection
    ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(20), default="synced")  # synced|stale|conflict|deleted_externally
    provenance_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)  # Full provenance trail
    
    # Quality & usage
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    usefulness_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-1 from feedback
    quality_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-1 from AI assessment
    completeness: Mapped[Optional[int]] = mapped_column(Integer, default=0)  # 0-100
    freshness: Mapped[Optional[int]] = mapped_column(Integer, default=0)  # 0-100
    
    # Epistemic status — THE KEY DISTINCTION
    # This artifact makes CLAIMS. Those claims may or may not match reality.
    # We track this explicitly.
    epistemic_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="asserted", index=True
    )  # asserted | verified | contradicted | partially_verified | unknown
    verification_status: Mapped[Optional[str]] = mapped_column(String(20))  # verified | failed | pending | not_applicable
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Conflict tracking — preserve, don't overwrite
    has_conflicts: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships to canonical reality (populated via CanonicalKnowledgeRelation)
    primary_topic_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Optimistic concurrency
    version_counter: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# KNOWLEDGE ARTIFACT VERSION — Full version history
# =============================================================================

class KnowledgeArtifactVersion(Base, TimestampMixin):
    """
    Immutable version history for every knowledge artifact.
    
    Never deleted. Superseded versions remain for historical queries.
    """
    
    __tablename__ = "knowledge_artifact_versions"
    __table_args__ = (
        Index("ix_kav_artifact", "artifact_id"),
        Index("ix_kav_org_artifact", "organization_id", "artifact_id"),
        UniqueConstraint(
            "artifact_id", "version",
            name="uq_kav_artifact_version",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_knowledge_artifacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Snapshot of artifact at this version
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    tags_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    category: Mapped[Optional[str]] = mapped_column(String(80))
    lifecycle_state: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Validity window for this version
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Change metadata
    editor_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    change_note: Mapped[Optional[str]] = mapped_column(Text)
    change_type: Mapped[str] = mapped_column(String(30), default="update")  # create|update|supersede|archive|withdraw
    
    # Provenance snapshot
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))
    provenance_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# CANONICAL KNOWLEDGE CLAIM — Extracted assertions from artifacts
# =============================================================================

class CanonicalKnowledgeClaim(Base, TimestampMixin):
    """
    Canonical Knowledge Claim — an individual assertion extracted from an artifact.
    
    This is the atomic unit of knowledge. A document might contain 50 claims.
    Each claim is:
    - Extracted from a specific artifact (source)
    - About a specific subject (policy rule, threshold, procedure step, fact)
    - Carries authority from its source
    - Has temporal validity (valid_from, valid_to)
    - Can be verified against observed reality
    - Can be contradicted by other claims or evidence
    
    CRITICAL: A claim ≠ truth. It's what a document SAYS.
    Verification against observed behavior/outcomes is separate.
    """
    
    __tablename__ = "canonical_knowledge_claims"
    __table_args__ = (
        Index("ix_ckc_org_subject", "organization_id", "subject_type", "subject_id"),
        Index("ix_ckc_org_artifact", "organization_id", "source_artifact_id"),
        Index("ix_ckc_org_topic", "organization_id", "topic_id"),
        Index("ix_ckc_org_status", "organization_id", "status"),
        Index("ix_ckc_org_valid", "organization_id", "valid_from", "valid_to"),
        Index("ix_ckc_predicate", "predicate"),
        # Exact-once per (org, subject, predicate, object, valid_from)
        UniqueConstraint(
            "organization_id", "subject_type", "subject_id", "predicate", "object_text", "valid_from",
            name="uq_ckc_occurrence_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # What the claim is about
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # e.g., "approval_threshold", "procedure_step", "policy_rule"
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # Specific instance ID
    
    # The claim itself: subject + predicate + object
    predicate: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "requires_approval_above", "is_mandatory", "has_deadline_days"
    object_text: Mapped[str] = mapped_column(Text, nullable=False)  # e.g., "₹10 lakh", "true", "30"
    object_value: Mapped[Optional[float]] = mapped_column(Float)  # Parsed numeric value if applicable
    object_unit: Mapped[Optional[str]] = mapped_column(String(30))  # e.g., "INR", "days", "percent"
    
    # Claim classification
    claim_type: Mapped[str] = mapped_column(String(30), nullable=False, default="rule", index=True)  # rule|fact|procedure|threshold|requirement|definition|assumption
    
    # Source artifact
    source_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_knowledge_artifacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_location: Mapped[Optional[str]] = mapped_column(String(500))  # Section, page, paragraph reference
    
    # Authority & confidence
    authority_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)  # 1=informal, 2=team, 3=dept, 4=org, 5=regulatory
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    
    # Temporal validity
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    superseded_by: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # Claim ID that supersedes this
    
    # Lifecycle status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="candidate", index=True)  # candidate|supported|authoritative|contested|superseded|retracted
    
    # Context
    context_type: Mapped[Optional[str]] = mapped_column(String(30))  # process|policy|project|meeting|decision
    context_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    topic_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Evidence & verification
    supporting_claim_ids_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    contradicting_claim_ids_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    related_entities_json: Mapped[Optional[list[dict]]] = mapped_column(JSON, default=list)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verification_result: Mapped[Optional[str]] = mapped_column(String(20))  # verified|contradicted|inconclusive
    
    # Provenance
    extracted_by: Mapped[Optional[str]] = mapped_column(String(64))  # "ai_extraction" | user_id
    extraction_method: Mapped[str] = mapped_column(String(30), default="ai")  # ai|manual|import
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.8)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))


# =============================================================================
# CANONICAL KNOWLEDGE EVIDENCE — Links claims to sources
# =============================================================================

class CanonicalKnowledgeEvidence(Base, TimestampMixin):
    """
    Link between a claim and the source excerpt that supports it.
    
    Every claim must be traceable: which source, which excerpt, with what weight.
    """
    
    __tablename__ = "canonical_knowledge_evidence"
    __table_args__ = (
        Index("ix_cke_claim", "claim_id"),
        Index("ix_cke_source", "source_type", "source_id"),
        UniqueConstraint(
            "claim_id", "source_type", "source_id", "excerpt_hash",
            name="uq_cke_source_excerpt",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_knowledge_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Source of evidence
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)  # artifact|meeting|decision|action|outcome|external
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # The evidence excerpt
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
    excerpt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Role of this evidence
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="primary")  # primary|supporting|contextual|contradicting
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    
    # Temporal
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    
    # Provenance
    extracted_by: Mapped[Optional[str]] = mapped_column(String(64))
    extraction_method: Mapped[str] = mapped_column(String(30), default="ai")


# =============================================================================
# CANONICAL KNOWLEDGE RELATION — Typed links to canonical reality
# =============================================================================

class CanonicalKnowledgeRelation(Base, TimestampMixin):
    """
    Canonical Knowledge Relation — typed edges between knowledge and canonical reality.
    
    This is how knowledge CONNECTS to the operating fabric:
    
    KnowledgeArtifact
      ↓ (governs)
    CanonicalBusinessProcess
      ↓ (has_step)
    ProcessStep
      ↓ (requires_approval)
    ProcessApproval
    
    Or:
    
    KnowledgeClaim
      ↓ (defines_threshold_for)
    FinancialTransaction
    
    Or:
    
    KnowledgeArtifact
      ↓ (documents)
    ProcessExecution
      ↓ (had_outcome)
    FinancialOutcomeRecord
    
    These relations make knowledge QUERYABLE from operations.
    """
    
    __tablename__ = "canonical_knowledge_relations"
    __table_args__ = (
        Index("ix_ckr_org_source", "organization_id", "source_type", "source_id"),
        Index("ix_ckr_org_target", "organization_id", "target_type", "target_id"),
        Index("ix_ckr_org_relation", "organization_id", "relation_type"),
        Index("ix_ckr_org_artifact", "organization_id", "artifact_id"),
        UniqueConstraint(
            "source_type", "source_id", "target_type", "target_id", "relation_type",
            name="uq_ckr_edge_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Source (knowledge side)
    artifact_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # CanonicalKnowledgeArtifact
    claim_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # CanonicalKnowledgeClaim
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # artifact|claim|topic
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Target (canonical reality side)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # process|step|approval|commitment|objective|person|role|responsibility|action|outcome|transaction|budget|vendor|resource|project|task|meeting|decision|evidence|learning
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Relation semantics
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # Examples:
    # artifact → process: "governs" | "documents" | "specifies"
    # artifact → step: "defines_procedure_for" | "provides_checklist_for"
    # artifact → approval: "defines_approval_rule_for" | "sets_threshold_for"
    # artifact → responsibility: "documents_responsibility_for"
    # artifact → person: "authored_by" | "owned_by" | "reviewed_by"
    # artifact → vendor: "specifies_vendor_requirements_for"
    # artifact → resource: "documents_resource_requirements_for"
    # artifact → objective: "supports" | "constrains"
    # artifact → decision: "informed" | "recorded_in"
    # artifact → meeting: "discussed_in" | "decided_in"
    # claim → process_step: "applies_to"
    # claim → transaction: "validates" | "violated_by"
    # claim → commitment: "constrains"
    # claim → approval: "defines_rule_for"
    
    # Metadata
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# CANONICAL KNOWLEDGE TOPIC — Canonical topic registry for entity resolution
# =============================================================================

class CanonicalKnowledgeTopic(Base, TimestampMixin):
    """
    Canonical Topic — the agreed name for an organizational concept.
    
    Anchors the knowledge graph without forcing identical naming across sources.
    """
    
    __tablename__ = "canonical_knowledge_topics"
    __table_args__ = (
        Index("ix_ckt_org_name", "organization_id", "name"),
        Index("ix_ckt_org_entity", "organization_id", "entity_type", "entity_id"),
        UniqueConstraint(
            "organization_id", "name",
            name="uq_ckt_org_name",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    aliases_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    canonical_artifact_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # The artifact that best defines this topic
    entity_type: Mapped[Optional[str]] = mapped_column(String(30), index=True)  # process|policy|person|role|vendor|customer|project|objective
    entity_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))


# =============================================================================
# KNOWLEDGE CONFLICT — Preserved conflicts between knowledge sources
# =============================================================================

class KnowledgeConflict(Base, TimestampMixin):
    """
    Canonical Knowledge Conflict — preserved contradiction between knowledge sources.
    
    NEVER silently overwrite. Preserve the conflict so Company Brain can reason over it.
    
    Example:
    Policy A: "Approval requires Finance above ₹10L"
    Document B: "Approval requires CFO above ₹10L"
    Observed behavior: "Managers have been approving directly."
    
    This conflict becomes a first-class entity that feeds Operating Attention.
    """
    
    __tablename__ = "knowledge_conflicts"
    __table_args__ = (
        Index("ix_kcf_org_type", "organization_id", "conflict_type"),
        Index("ix_kcf_org_severity", "organization_id", "severity"),
        Index("ix_kcf_org_artifact", "organization_id", "primary_artifact_id"),
        Index("ix_kcf_org_status", "organization_id", "status"),
        Index("ix_kcf_org_topic", "organization_id", "topic_id"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # What kind of conflict
    conflict_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # policy_vs_policy | policy_vs_document | policy_vs_behavior | document_vs_behavior
    # | claim_vs_claim | claim_vs_evidence | external_vs_internal | version_vs_version
    
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium", index=True)  # info|warning|critical
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)  # open|acknowledged|resolving|resolved|accepted
    
    # Primary artifact (the "official" one if there is one)
    primary_artifact_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("canonical_knowledge_artifacts.id", ondelete="SET NULL"), index=True
    )
    
    # Conflicting artifacts/claims
    conflicting_artifact_ids_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    conflicting_claim_ids_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    
    # Topic this conflict relates to
    topic_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("canonical_knowledge_topics.id", ondelete="SET NULL"), index=True
    )
    
    # Description
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    evidence_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Quantitative impact
    affected_process_ids_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    affected_transaction_count: Mapped[int] = mapped_column(Integer, default=0)
    financial_exposure: Mapped[Optional[float]] = mapped_column(Float)
    
    # Resolution
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(64))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolution_method: Mapped[Optional[str]] = mapped_column(String(30))  # authority_decision|consensus|evidence_based|policy_update|behavior_change
    
    # Detection
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    detected_by: Mapped[str] = mapped_column(String(64), default="system")
    detection_method: Mapped[str] = mapped_column(String(30), default="derived")  # derived|reported|audit|ai_analysis
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# EXTERNAL KNOWLEDGE SOURCE — Registry of imported sources
# =============================================================================

class ExternalKnowledgeSource(Base, TimestampMixin):
    """
    Registry of external knowledge sources (Drive, SharePoint, Notion, etc.).
    
    Every imported artifact retains its source identity. Integration never
    silently transforms external content into unquestioned company truth.
    """
    
    __tablename__ = "external_knowledge_sources"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_type", "external_id",
            name="uq_eks_external_id",
        ),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Source identification
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # EXTERNAL_SOURCES
    external_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)  # File ID, page ID, message ID, etc.
    external_url: Mapped[Optional[str]] = mapped_column(String(500))
    external_path: Mapped[Optional[str]] = mapped_column(String(500))  # Folder/path in external system
    
    # Metadata
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # Sync state
    sync_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)  # pending|synced|stale|conflict|error|deleted_externally
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_synced_hash: Mapped[Optional[str]] = mapped_column(String(64))
    sync_error: Mapped[Optional[str]] = mapped_column(Text)
    sync_schedule: Mapped[Optional[str]] = mapped_column(String(50))  # cron expression
    
    # Mapping to canonical artifacts
    mapped_artifact_ids_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    mapping_status: Mapped[str] = mapped_column(String(20), default="unmapped")  # unmapped|partial|mapped|conflict
    
    # Permissions & access
    permissions_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    access_level: Mapped[str] = mapped_column(String(20), default="read")  # read|write|admin
    
    # Provenance
    imported_by: Mapped[Optional[str]] = mapped_column(String(64))
    import_method: Mapped[str] = mapped_column(String(30), default="api")  # api|manual|bulk|webhook


# =============================================================================
# KNOWLEDGE CONTEXT QUERY — Operational knowledge queries (audit trail)
# =============================================================================

class KnowledgeContextQuery(Base, TimestampMixin):
    """
    Audit trail for operational knowledge queries.
    
    Records: "Employee X asked 'How do I approve this procurement?' at time T
    in context C, and received answer A based on artifacts [A1, A2, A3] with
    confidence C."
    
    Enables: analytics, improvement, compliance, temporal replay.
    """
    
    __tablename__ = "knowledge_context_queries"
    __table_args__ = (
        Index("ix_kcq_org_employee", "organization_id", "employee_id"),
        Index("ix_kcq_org_time", "organization_id", "queried_at"),
        Index("ix_kcq_org_context", "organization_id", "context_type", "context_id"),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Who asked
    employee_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    role_at_time: Mapped[Optional[str]] = mapped_column(String(64))
    permissions_at_time_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # What they asked
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(30), index=True)  # how_to|what_is_policy|what_changed|who_knows|where_is
    
    # Context at query time
    context_type: Mapped[Optional[str]] = mapped_column(String(30), index=True)  # process|task|approval|transaction|project|meeting
    context_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Answer
    answer: Mapped[Optional[str]] = mapped_column(Text)
    answer_confidence: Mapped[Optional[float]] = mapped_column(Float)
    answer_type: Mapped[str] = mapped_column(String(30))  # direct|guided|escalated|not_found
    
    # Sources used
    artifact_ids_used_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    claim_ids_used_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    
    # Epistemic transparency in answer
    answer_epistemic_breakdown_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    # {
    #   "document_states": ["Policy X says Y"],
    #   "company_facts": ["Company actually does Z"],
    #   "observed_behavior": ["Evidence shows W"],
    #   "verified_outcomes": ["Verification confirmed V"],
    #   "conflicts": ["Conflict C exists between A and B"]
    # }
    
    # Timing
    queried_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(Integer)
    
    # Feedback
    was_helpful: Mapped[Optional[bool]] = mapped_column(Boolean)
    feedback_note: Mapped[Optional[str]] = mapped_column(Text)
    feedback_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Constants
    "KNOWLEDGE_ARTIFACT_KINDS",
    "ARTIFACT_LIFECYCLE_STATES",
    "ARTIFACT_SCOPES",
    "EXTERNAL_SOURCES",
    # Models
    "CanonicalKnowledgeArtifact",
    "KnowledgeArtifactVersion",
    "CanonicalKnowledgeClaim",
    "CanonicalKnowledgeEvidence",
    "CanonicalKnowledgeRelation",
    "CanonicalKnowledgeTopic",
    "KnowledgeConflict",
    "ExternalKnowledgeSource",
    "KnowledgeContextQuery",
]