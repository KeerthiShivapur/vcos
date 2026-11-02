"""Canonical Communication, Collaboration & Community Operating Fabric — Gate 22.

This is the SINGLE canonical communication/collaboration layer. It does NOT create a
parallel communication/social/community graph/brain/system. All communication,
collaboration, and community intelligence is derived from existing canonical
primitives.

Key architectural principles:
- Message ≠ Claim ≠ Evidence ≠ Decision ≠ Authorization ≠ Commitment ≠ Execution ≠ Outcome
- Communication is an observational/contextual surface over canonical reality
- Groups/Communities are relationship/projection structures over canonical people and company reality
- NOT another organizational hierarchy or social network
- Communication feeds canonical reality but does not automatically become truth
- Epistemic boundaries preserved: message ≠ claim ≠ evidence ≠ outcome
- Exact-once semantics via fingerprint + unique constraints
- Temporal truth: valid_from/valid_to, supersession chains
- Provenance: every mutation has actor, source_event_id, timestamp
- Governance: tenant/scope isolation
- Scale invariant: same architecture from 5 to 500,000+ employees
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
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
# CANONICAL GROUP KINDS
# =============================================================================

CANONICAL_GROUP_KINDS = (
    "team",                 # Cross-functional team
    "project",              # Project-specific group
    "department",           # Department-aligned group
    "working",              # Working group / task force
    "leadership",           # Leadership group
    "cross_functional",     # Cross-functional working group
    "expertise",            # Expertise-based group
    "mentorship",           # Mentorship circle
    "geography",            # Geographic/regional group
    "innovation",           # Innovation community
    "practice",             # Community of practice
    "interest",             # Interest group
    "social",               # Social/cultural group
    "onboarding",           # Onboarding cohort
    "incident",             # Incident response group
    "governance",           # Governance committee
    "customer",             # Customer-facing group
    "partner",              # Partner/vendor group
    "external",             # External collaboration group
)

CANONICAL_GROUP_LIFECYCLE_STATES = (
    "forming",          # Being formed
    "active",           # Active and operational
    "paused",           # Temporarily paused
    "archived",         # Historical reference
    "dissolved",        # Formally dissolved
)

CANONICAL_GROUP_MEMBERSHIP_ROLES = (
    "owner",            # Group owner
    "moderator",        # Moderator
    "lead",             # Group lead
    "facilitator",      # Facilitator
    "participant",      # Regular participant
    "observer",         # Observer (read-only)
    "guest",            # Guest member
)

CANONICAL_GROUP_SCOPES = (
    "company",          # Company-wide
    "department",       # Department-scoped
    "team",             # Team-scoped
    "project",          # Project-scoped
    "personal",         # Personal/private
)


# =============================================================================
# CANONICAL GROUP — The single canonical group entity
# =============================================================================

class CanonicalGroup(Base, TimestampMixin):
    """
    Canonical Group — the single representation of a group in canonical company reality.
    
    A group is a relationship/projection structure over canonical people and company reality.
    It is NOT an organizational hierarchy. Groups are projections over canonical people
    and company reality for collaboration purposes.
    
    Key distinctions from legacy models:
    - Temporal validity (valid_from, valid_to) for historical queries
    - Explicit supersession chain (supersedes_id, superseded_by_id)
    - Full provenance (source, author, modification history, external origin)
    - Exact-once via fingerprint + unique constraint
    - NOT an organizational hierarchy - purely a collaboration projection
    - Scope-based governance (company, department, team, project, personal)
    - Kind-based taxonomy (team, project, working group, etc.)
    """
    
    __tablename__ = "canonical_groups"
    __table_args__ = (
        Index("ix_cg_org_kind", "organization_id", "kind"),
        Index("ix_cg_org_state", "organization_id", "lifecycle_state"),
        Index("ix_cg_org_scope", "organization_id", "scope", "scope_id"),
        Index("ix_cg_org_valid_temporal", "organization_id", "valid_from", "valid_to"),
        Index("ix_cg_org_owner", "organization_id", "owner_id"),
        Index("ix_cg_fingerprint", "organization_id", "fingerprint"),
        # Exact-once per (org, fingerprint)
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_cg_fingerprint_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Core identity
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)
    
    # Classification
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # CANONICAL_GROUP_KINDS
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    tags_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    
    # Scope & governance
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="company", index=True)  # CANONICAL_GROUP_SCOPES
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # department_id, team_id, project_id
    lifecycle_state: Mapped[str] = mapped_column(String(20), nullable=False, default="forming", index=True)  # CANONICAL_GROUP_LIFECYCLE_STATES
    
    # Temporal validity
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Supersession chain
    supersedes_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    superseded_by_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Ownership & authorship
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # Person/team responsible
    owner_type: Mapped[Optional[str]] = mapped_column(String(30))  # person|team|department|role
    author_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    approver_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[Optional[str]] = mapped_column(Text)
    
    # Provenance
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="internal", index=True)  # internal|external_import|migration
    source_id: Mapped[Optional[str]] = mapped_column(String(120), index=True)  # External system ID
    external_ref: Mapped[Optional[str]] = mapped_column(String(500), index=True)  # URL/path in external system
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # For change detection
    ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(20), default="synced")  # synced|stale|conflict|deleted_externally
    provenance_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)  # Full provenance trail
    
    # Quality & usage
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    activity_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-1 activity metric
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Optimistic concurrency
    version_counter: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# CANONICAL GROUP VERSION — Full version history
# =============================================================================

class CanonicalGroupVersion(Base, TimestampMixin):
    """
    Immutable version history for every canonical group.
    
    Never deleted. Superseded versions remain for historical queries.
    """
    
    __tablename__ = "canonical_group_versions"
    __table_args__ = (
        Index("ix_cgv_group", "group_id"),
        Index("ix_cgv_org_group", "organization_id", "group_id"),
        UniqueConstraint(
            "group_id", "version",
            name="uq_cgv_group_version",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Snapshot of group at this version
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    tags_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    category: Mapped[Optional[str]] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Validity window for this version
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Change metadata
    editor_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    change_note: Mapped[Optional[str]] = mapped_column(Text)
    change_type: Mapped[str] = mapped_column(String(30), default="update")  # create|update|supersede|archive|dissolve
    
    # Provenance snapshot
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))
    provenance_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# CANONICAL GROUP MEMBERSHIP — Temporal membership with roles
# =============================================================================

class CanonicalGroupMembership(Base, TimestampMixin):
    """
    Canonical Group Membership — temporal membership with roles.
    
    Membership is temporal: valid_from/valid_to track membership windows.
    A person can have multiple concurrent memberships with different roles.
    """
    
    __tablename__ = "canonical_group_memberships"
    __table_args__ = (
        Index("ix_cgm_org_group", "organization_id", "group_id"),
        Index("ix_cgm_org_emp", "organization_id", "employee_id"),
        Index("ix_cgm_org_valid_temporal", "organization_id", "valid_from", "valid_to"),
        UniqueConstraint(
            "group_id", "employee_id", "role",
            name="uq_cgm_group_emp_role",
        ),
        UniqueConstraint(
            "organization_id", "group_id", "employee_id",
            name="uq_cgm_org_group_emp",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="participant")  # CANONICAL_GROUP_MEMBERSHIP_ROLES
    
    # Temporal validity
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Role metadata
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    invited_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Permissions within group
    can_post: Mapped[bool] = mapped_column(Boolean, default=True)
    can_moderate: Mapped[bool] = mapped_column(Boolean, default=False)
    can_invite: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_members: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_settings: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Notifications
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# CANONICAL COMMUNITY — The single canonical community entity
# =============================================================================

class CanonicalCommunity(Base, TimestampMixin):
    """
    Canonical Community — the single representation of a community in canonical company reality.
    
    A community is a relationship/projection structure for people with shared interests,
    expertise, or goals. It is NOT a social network or separate hierarchy.
    
    Communities connect:
    - People ↔️ Expertise
    - People ↔️ Knowledge
    - People ↔️ Topics
    - People ↔️ Projects
    - People ↔️ Processes
    - People ↔️ Organizational interests
    """
    
    __tablename__ = "canonical_communities"
    __table_args__ = (
        Index("ix_cc_org_type", "organization_id", "community_type"),
        Index("ix_cc_org_state", "organization_id", "lifecycle_state"),
        Index("ix_cc_org_scope", "organization_id", "scope", "scope_id"),
        Index("ix_cc_org_owner", "organization_id", "owner_id"),
        Index("ix_cc_fingerprint", "organization_id", "fingerprint"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_cc_fingerprint_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Core identity
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    
    # Classification
    community_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # expertise|professional|interest|practice|innovation|mentorship|social|geography|governance
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    tags_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    
    # Topics and expertise
    primary_topic_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    topic_ids_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    expertise_area_ids_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    
    # Scope & governance
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="company", index=True)  # company|department|team|project|personal
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    lifecycle_state: Mapped[str] = mapped_column(String(20), nullable=False, default="forming", index=True)  # forming|active|paused|archived|dormant
    visibility: Mapped[str] = mapped_column(String(24), default="public", nullable=False)  # public|private|invite_only|hidden
    
    # Ownership & authorship
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    owner_type: Mapped[Optional[str]] = mapped_column(String(30))  # person|team|department|role
    author_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    moderator_ids_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    
    # Membership & activity
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    activity_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-1 activity metric
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="internal", index=True)  # internal|external_import|migration
    source_id: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    external_ref: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(20), default="synced")  # synced|stale|conflict|deleted_externally
    provenance_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Quality & usage
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    usefulness_score: Mapped[Optional[float]] = mapped_column(Float)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Optimistic concurrency
    version_counter: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# CANONICAL COMMUNITY MEMBERSHIP — Temporal membership
# =============================================================================

class CanonicalCommunityMembership(Base, TimestampMixin):
    """
    Canonical Community Membership — temporal membership in a community.
    """
    
    __tablename__ = "canonical_community_memberships"
    __table_args__ = (
        Index("ix_ccm_org_community", "organization_id", "community_id"),
        Index("ix_ccm_org_emp", "organization_id", "employee_id"),
        Index("ix_ccm_org_valid_temporal", "organization_id", "valid_from", "valid_to"),
        UniqueConstraint(
            "community_id", "employee_id",
            name="uq_ccm_community_emp",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    community_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_communities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="member")  # owner|moderator|lead|facilitator|member|observer
    
    # Temporal validity
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    invited_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Permissions
    can_post: Mapped[bool] = mapped_column(Boolean, default=True)
    can_moderate: Mapped[bool] = mapped_column(Boolean, default=False)
    can_invite: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Notifications
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# CANONICAL COMMUNITY POST — Threaded discussions in communities
# =============================================================================

class CanonicalCommunityPost(Base, TimestampMixin):
    """
    Canonical Community Post — threaded discussions within a community.
    """
    
    __tablename__ = "canonical_community_posts"
    __table_args__ = (
        Index("ix_ccp_org_community", "organization_id", "community_id"),
        Index("ix_ccp_org_author", "organization_id", "author_id"),
        Index("ix_ccp_org_valid_temporal", "organization_id", "valid_from", "valid_to"),
        Index("ix_ccp_org_status", "organization_id", "status"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    community_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_communities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Core content
    title: Mapped[Optional[str]] = mapped_column(String(300))
    content: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    
    # Classification
    post_type: Mapped[str] = mapped_column(String(30), default="discussion", index=True)  # discussion|question|announcement|poll|resource|event
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    tags_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    
    # Author
    author_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # State
    status: Mapped[str] = mapped_column(String(24), default="published", index=True)  # draft|published|archived|moderated|rejected
    visibility: Mapped[str] = mapped_column(String(24), default="members")  # public|members|private
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Engagement
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    reaction_count: Mapped[int] = mapped_column(Integer, default=0)
    bookmark_count: Mapped[int] = mapped_column(Integer, default=0)
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Threading
    reply_to_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Provenance
    source_type: Mapped[str] = mapped_column(String(30), default="internal")
    source_id: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    external_ref: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))
    ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(20), default="synced")
    provenance_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Temporal truth
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Optimistic concurrency
    version_counter: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# CANONICAL COMMUNITY COMMENT — Threaded comments on posts
# =============================================================================

class CanonicalCommunityComment(Base, TimestampMixin):
    """
    Canonical Community Comment — threaded comments on community posts.
    """
    
    __tablename__ = "canonical_community_comments"
    __table_args__ = (
        Index("ix_ccc_org_post", "organization_id", "post_id"),
        Index("ix_ccc_org_author", "organization_id", "author_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    post_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_community_posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("canonical_community_comments.id", ondelete="SET NULL"), index=True
    )
    author_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolution: Mapped[bool] = mapped_column(Boolean, default=False)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reaction_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# CANONICAL ANNOUNCEMENT — Company/department/team announcements
# =============================================================================

class CanonicalAnnouncement(Base, TimestampMixin):
    """
    Canonical Announcement — governed company/department/team communication.
    
    An announcement is communication. It does not automatically become
    policy, decision, or authorization. It carries provenance and governance.
    """
    
    __tablename__ = "canonical_announcements"
    __table_args__ = (
        Index("ix_can_ann_org_type", "organization_id", "announcement_type"),
        Index("ix_can_ann_org_state", "organization_id", "lifecycle_state"),
        Index("ix_can_ann_org_scope", "organization_id", "scope", "scope_id"),
        Index("ix_can_ann_org_valid", "organization_id", "valid_from", "valid_to"),
        Index("ix_can_ann_org_author", "organization_id", "author_id"),
        Index("ix_can_ann_fingerprint", "organization_id", "fingerprint"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_ca_fingerprint_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Core identity
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    body: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    
    # Classification
    announcement_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # company|department|team|project|operational|policy|emergency|maintenance|celebration
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    tags_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    
    # Scope & governance
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="company", index=True)  # company|department|team|project
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    lifecycle_state: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)  # draft|scheduled|published|archived|withdrawn
    priority: Mapped[str] = mapped_column(String(12), default="normal", nullable=False)  # low|normal|high|critical|emergency
    acknowledge_required: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Scheduling
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Authorship
    author_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    team_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Engagement
    read_count: Mapped[int] = mapped_column(Integer, default=0)
    acknowledged_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Provenance
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="internal", index=True)  # internal|external_import|migration
    source_id: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    external_ref: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(20), default="synced")  # synced|stale|conflict|deleted_externally
    provenance_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Temporal truth
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Optimistic concurrency
    version_counter: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# CANONICAL ANNOUNCEMENT RECEIPT — Read/acknowledgment tracking
# =============================================================================

class CanonicalAnnouncementReceipt(Base, TimestampMixin):
    """
    Canonical Announcement Receipt — read/acknowledgment tracking for announcements.
    """
    
    __tablename__ = "canonical_announcement_receipts"
    __table_args__ = (
        UniqueConstraint(
            "announcement_id", "employee_id",
            name="uq_car_announcement_employee",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# CANONICAL GROUP MESSAGE — Messages within canonical groups
# =============================================================================

class CanonicalGroupMessage(Base, TimestampMixin):
    """
    Canonical Group Message — a governed message within a canonical group.
    
    Extends CanonicalMessage concept to group context.
    """
    
    __tablename__ = "canonical_group_messages"
    __table_args__ = (
        Index("ix_cgm_msg_org_group", "organization_id", "group_id"),
        Index("ix_cgm_org_sender", "organization_id", "sender_id"),
        Index("ix_cgm_msg_org_valid_temporal", "organization_id", "valid_from", "valid_to"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_cgm_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Message identity
    group_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    content: Mapped[Optional[str]] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(30), default="text", nullable=False)
    
    # Threading
    reply_to: Mapped[Optional[str]] = mapped_column(
        ForeignKey("canonical_group_messages.id", ondelete="SET NULL"), index=True
    )
    
    # References to canonical company reality
    decision_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    commitment_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    action_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    objective_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    responsibility_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Attachments and metadata
    attachments: Mapped[Optional[list]] = mapped_column(JSON)
    mentions: Mapped[Optional[list]] = mapped_column(JSON)
    
    # Canonical temporal truth fields
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Canonical version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Canonical fingerprint for exact-once semantics
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Message metadata
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reaction_count: Mapped[int] = mapped_column(Integer, default=0)


# =============================================================================
# CANONICAL GROUP REACTION — Reactions on group messages
# =============================================================================

class CanonicalGroupMessageReaction(Base, TimestampMixin):
    """
    Canonical Group Message Reaction — reactions on group messages.
    """
    
    __tablename__ = "canonical_group_message_reactions"
    __table_args__ = (
        UniqueConstraint(
            "message_id", "employee_id", "emoji",
            name="uq_cgm_reaction_emp_emoji",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_group_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    emoji: Mapped[str] = mapped_column(String(24), nullable=False)


# =============================================================================
# CANONICAL GROUP RELATION — Links between groups and canonical reality
# =============================================================================

class CanonicalGroupRelation(Base, TimestampMixin):
    """
    Canonical Group Relation — typed edges between groups and canonical reality.
    
    This is how groups CONNECT to the operating fabric:
    
    CanonicalGroup
      ↓ (governs)
    CanonicalBusinessProcess
      ↓ (has_step)
    ProcessStep
      ↓ (requires_approval)
    ProcessApproval
    
    Or:
    
    CanonicalGroup
      ↓ (has_member)
    Person
      ↓ (has_expertise)
    Capability
    
    Or:
    
    CanonicalGroup
      ↓ (discusses)
    KnowledgeArtifact
      ↓ (documents)
    Process
    """
    
    __tablename__ = "canonical_group_relations"
    __table_args__ = (
        Index("ix_cgr_org_source", "organization_id", "source_type", "source_id"),
        Index("ix_cgr_org_target", "organization_id", "target_type", "target_id"),
        Index("ix_cgr_org_relation", "organization_id", "relation_type"),
        UniqueConstraint(
            "source_type", "source_id", "target_type", "target_id", "relation_type",
            name="uq_cgr_edge_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Source (group side)
    group_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # group
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Target (canonical reality side)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # process|step|approval|commitment|objective|person|role|responsibility|action|outcome|transaction|budget|vendor|resource|project|task|meeting|decision|evidence|learning
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Relation semantics
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # Examples:
    # group → process: "governs" | "documents" | "specifies"
    # group → step: "defines_procedure_for" | "provides_checklist_for"
    # group → approval: "defines_approval_rule_for" | "sets_threshold_for"
    # group → responsibility: "documents_responsibility_for"
    # group → person: "has_member" | "owned_by" | "led_by"
    # group → vendor: "specifies_vendor_requirements_for"
    # group → resource: "documents_resource_requirements_for"
    # group → objective: "supports" | "constrains"
    # group → decision: "informed" | "recorded_in"
    # group → meeting: "discussed_in" | "decided_in"
    # group → knowledge: "documents" | "discusses"
    
    # Metadata
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Constants
    "CANONICAL_GROUP_KINDS",
    "CANONICAL_GROUP_LIFECYCLE_STATES",
    "CANONICAL_GROUP_MEMBERSHIP_ROLES",
    "CANONICAL_GROUP_SCOPES",
    # Models
    "CanonicalGroup",
    "CanonicalGroupVersion",
    "CanonicalGroupMembership",
    "CanonicalCommunity",
    "CanonicalCommunityMembership",
    "CanonicalCommunityPost",
    "CanonicalCommunityComment",
    "CanonicalAnnouncement",
    "CanonicalAnnouncementReceipt",
    "CanonicalGroupMessage",
    "CanonicalGroupMessageReaction",
    "CanonicalGroupRelation",
]