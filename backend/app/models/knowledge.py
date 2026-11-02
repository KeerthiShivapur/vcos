"""Knowledge models for documents, wiki, policies, SOPs, templates, and decisions."""

from datetime import date, datetime, timezone
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid, utcnow


class DocumentStatus(str):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    author_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    team_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT, nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(String(24), default="organization", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_documents_org_slug"),
    )


class WikiPage(Base, TimestampMixin):
    __tablename__ = "wiki_pages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    space: Mapped[str] = mapped_column(String(24), default="organization", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    author_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    editor_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("wiki_pages.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    team_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Policy(Base, TimestampMixin):
    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(60), default="general", nullable=False, index=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    approver_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    effective_date: Mapped[Optional[date]] = mapped_column(Date)
    review_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    approval_note: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_policies_org_slug"),
    )


class SOP(Base, TimestampMixin):
    __tablename__ = "sops"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    team_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class SOPStep(Base):
    __tablename__ = "sop_steps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sop_id: Mapped[str] = mapped_column(
        ForeignKey("sops.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    instruction: Mapped[Optional[str]] = mapped_column(Text)
    is_checklist: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Template(Base, TimestampMixin):
    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40), default="other", nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default=DocumentStatus.DRAFT, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Decision(Base, TimestampMixin):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)
    context: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False, index=True)
    decision_maker_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    decision_date: Mapped[Optional[date]] = mapped_column(Date)
    impact: Mapped[Optional[str]] = mapped_column(Text)
    business_impact: Mapped[Optional[str]] = mapped_column(Text)
    follow_up_actions: Mapped[Optional[list]] = mapped_column(JSON)
    future_review_date: Mapped[Optional[date]] = mapped_column(Date)
    lessons_learned: Mapped[Optional[str]] = mapped_column(Text)
    project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    goal_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    meeting_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_decisions_org_slug"),
    )


class DecisionOption(Base):
    __tablename__ = "decision_options"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    pros: Mapped[Optional[str]] = mapped_column(Text)
    cons: Mapped[Optional[str]] = mapped_column(Text)
    chosen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    chosen_reason: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DecisionParticipant(Base):
    __tablename__ = "decision_participants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), nullable=False)
    role: Mapped[str] = mapped_column(String(24), default="consulted", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    editor_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    change_note: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "version", name="uq_document_versions_entity_version"),
    )


class DocumentComment(Base, TimestampMixin):
    __tablename__ = "document_comments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_document_comments_entity", "entity_type", "entity_id"),
        Index("ix_document_comments_author", "author_id"),
    )


class DocumentWatcher(Base, TimestampMixin):
    __tablename__ = "document_watchers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "user_id", name="uq_document_watchers_entity_user"),
    )


class DocumentFavorite(Base, TimestampMixin):
    __tablename__ = "document_favorites"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "user_id", name="uq_document_favorites_entity_user"),
    )


class DocumentPresence(Base, TimestampMixin):
    __tablename__ = "document_presence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "user_id", name="uq_document_presence_entity_user"),
    )


class KnowledgeCategory(Base):
    __tablename__ = "knowledge_categories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    color: Mapped[Optional[str]] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_knowledge_categories_org_slug"),
    )


class KnowledgeTag(Base):
    __tablename__ = "knowledge_tags"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_knowledge_tags_org_name"),
    )


class KnowledgeItemTag(Base):
    __tablename__ = "knowledge_item_tags"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    tag_id: Mapped[str] = mapped_column(ForeignKey("knowledge_tags.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "tag_id", name="uq_knowledge_item_tags_entity_tag"),
    )


class KnowledgeIndex(Base):
    __tablename__ = "knowledge_search_index"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    keywords_json: Mapped[Optional[str]] = mapped_column(Text)
    embedding_json: Mapped[Optional[str]] = mapped_column(Text)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_knowledge_search_index_entity"),
    )


class KnowledgeVector(Base):
    __tablename__ = "knowledge_vectors"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[Optional[str]] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_type", "source_id", "chunk_index",
            name="uq_knowledge_vector_chunk",
        ),
        {"extend_existing": True},
    )


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), default="internal", nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(24), default="discovered", nullable=False, index=True)
    source_status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    authority_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    freshness_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    freshness_label: Mapped[str] = mapped_column(String(16), default="stale", nullable=False)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    provenance_json: Mapped[Optional[str]] = mapped_column(Text)
    external_ref: Mapped[Optional[str]] = mapped_column(String(240), index=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_type", "source_id",
            name="uq_knowledge_sources_entity",
        ),
        {"extend_existing": True},
    )


class KnowledgeClaim(Base):
    __tablename__ = "knowledge_claims"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    predicate: Mapped[str] = mapped_column(String(80), nullable=False)
    object_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(24), default="fact", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="supported", nullable=False, index=True)
    authority_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    context_type: Mapped[Optional[str]] = mapped_column(String(32))
    context_id: Mapped[Optional[str]] = mapped_column(String(32))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    superseded_by: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    topic_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("knowledge_topics.id", ondelete="SET NULL"), index=True
    )
    supporting_claim_ids_json: Mapped[Optional[str]] = mapped_column(Text)
    contradicting_claim_ids_json: Mapped[Optional[str]] = mapped_column(Text)
    related_entities_json: Mapped[Optional[str]] = mapped_column(Text)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "subject_type", "subject_id", "predicate", "object_text",
            name="uq_knowledge_claims_unique",
        ),
        {"extend_existing": True},
    )


class KnowledgeTopic(Base, TimestampMixin):
    __tablename__ = "knowledge_topics"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("knowledge_topics.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_knowledge_topics_org_name"),
        {"extend_existing": True},
    )


class KnowledgeEvidence(Base, TimestampMixin):
    """Evidence linking a claim to a source excerpt."""

    __tablename__ = "knowledge_evidence"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_claims.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    relevance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    quality: Mapped[str] = mapped_column(String(24), default="estimated", nullable=False)
    page_ref: Mapped[Optional[str]] = mapped_column(String(64))
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_knowledge_evidence_claim", "claim_id"),
        {"extend_existing": True},
    )


class KnowledgeConflict(Base, TimestampMixin):
    __tablename__ = "knowledge_conflicts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    claim_id_1: Mapped[str] = mapped_column(
        ForeignKey("knowledge_claims.id", ondelete="CASCADE"), index=True, nullable=False
    )
    claim_id_2: Mapped[str] = mapped_column(
        ForeignKey("knowledge_claims.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conflict_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)  # open, resolved, dismissed
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(32))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("claim_id_1", "claim_id_2", name="uq_knowledge_conflicts_pair"),
        {"extend_existing": True},
    )


class ExternalKnowledgeSource(Base, TimestampMixin):
    __tablename__ = "external_knowledge_sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)  # google_drive, slack, jira, github, etc.
    source_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(500))
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    sync_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[Optional[str]] = mapped_column(Text)
    config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "source_type", "source_id", name="uq_external_sources_org_type_id"),
        {"extend_existing": True},
    )


class KnowledgeContextQuery(Base, TimestampMixin):
    __tablename__ = "knowledge_context_queries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_vector: Mapped[Optional[str]] = mapped_column(Text)
    filters: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    top_result_id: Mapped[Optional[str]] = mapped_column(String(32))
    user_id: Mapped[Optional[str]] = mapped_column(String(32))
    session_id: Mapped[Optional[str]] = mapped_column(String(32))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="completed", nullable=False)


class KnowledgeRelation(Base, TimestampMixin):
    """Relation between knowledge entities and other entities."""

    __tablename__ = "knowledge_relations"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # claim, document, topic, source
    source_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # claim, document, topic, source, project, task, meeting, person
    target_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)  # supports, contradicts, references, derived_from, part_of, related_to
    strength: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_knowledge_relation_source", "source_type", "source_id"),
        Index("ix_knowledge_relation_target", "target_type", "target_id"),
        UniqueConstraint("organization_id", "source_type", "source_id", "target_type", "target_id", "relation_type", name="uq_knowledge_relation_unique"),
        {"extend_existing": True},
    )


class KnowledgeIntelInsight(Base, TimestampMixin):
    """Intelligence insight derived from knowledge synthesis."""

    __tablename__ = "knowledge_intel_insights"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # pattern, trend, anomaly, correlation, causation, lesson
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="discovered", nullable=False)  # discovered, validated, applied, archived
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_events_json: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_knowledge_intel_insight_org_fingerprint", "organization_id", "fingerprint", unique=True),
        Index("ix_knowledge_intel_insight_org_status", "organization_id", "status"),
        {"extend_existing": True},
    )


class KnowledgeIntelInsightEvent(Base, TimestampMixin):
    """Event log for insight lifecycle."""

    __tablename__ = "knowledge_intel_insight_events"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    insight_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)  # discovered, validated, applied, archived, superseded
    actor_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_knowledge_intel_insight_event_org_insight", "organization_id", "insight_id"),
        {"extend_existing": True},
    )


class KnowledgeRecommendation(Base, TimestampMixin):
    """Recommendation derived from knowledge intelligence."""

    __tablename__ = "knowledge_recommendations"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    insight_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # action, investigation, review, update, create, archive
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0-5
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False)  # proposed, under_review, approved, rejected, implemented, deferred
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    estimated_impact: Mapped[Optional[str]] = mapped_column(Text)
    estimated_effort: Mapped[Optional[str]] = mapped_column(String(32))
    assignee_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_knowledge_recommendation_org_status", "organization_id", "status"),
        Index("ix_knowledge_recommendation_org_insight", "organization_id", "insight_id"),
        {"extend_existing": True},
    )


class KnowledgeQuality(Base, TimestampMixin):
    """Quality metrics for knowledge sources and claims."""
    
    __tablename__ = "knowledge_quality"
    __table_args__ = {"extend_existing": True}
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    quality_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    authority_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    completeness_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    accuracy_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    consistency_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    metrics_json: Mapped[Optional[str]] = mapped_column(Text)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    assessed_by: Mapped[Optional[str]] = mapped_column(String(32))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    __table_args__ = (
        UniqueConstraint("organization_id", "source_type", "source_id", name="uq_knowledge_quality_source"),
        {"extend_existing": True},
    )