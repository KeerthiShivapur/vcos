# --- Slice 4E.3+ --- ML Models for Forecasting & Anomaly Detection ---


class MLModel(Base, TimestampMixin):
    """Stored ML model metadata."""

    __tablename__ = "ml_models"
    __table_args__ = (
        Index("ix_ml_models_org_type", "organization_id", "model_type"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_type: Mapped[str] = mapped_column(String(40), nullable=False)  # forecasting, anomaly
    algorithm: Mapped[str] = mapped_column(String(40), nullable=False)  # prophet, isolation_forest, etc.
    version: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[Optional[str]] = mapped_column(Text)  # JSON config
    metrics: Mapped[Optional[str]] = mapped_column(Text)  # JSON metrics
    model_data: Mapped[Optional[str]] = mapped_column(Text)  # Pickled model (base64)
    status: Mapped[str] = mapped_column(String(24), default="training")  # training, ready, failed
    trained_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MLPrediction(Base, TimestampMixin):
    """Stored predictions for audit/history."""

    __tablename__ = "ml_predictions"
    __table_args__ = (
        Index("ix_ml_predictions_org_model", "organization_id", "model_id"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    model_id: Mapped[str] = mapped_column(
        ForeignKey("ml_models.id", ondelete="CASCADE"), index=True, nullable=False
    )
    prediction_type: Mapped[str] = mapped_column(String(40), nullable=False)  # forecast, anomaly
    input_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON input
    output_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON output


# --- Knowledge Vector/Search Models ---


class KnowledgeVector(Base, TimestampMixin):
    """Slice 4D.2 - persisted semantic vector per deterministic chunk.

    One row per (tenant, source, chunk) holding the embedding produced by the
    configured embedding provider. The row is the evidence lineage for
    semantic retrieval: every chunk knows its canonical source row
    (source_type + source_id), when that source last changed
    (source_updated_at) and when the vector was (re)indexed
    (indexed_at). Deletes remove the rows, so removed content can never
    resurface through search.
    """

    __tablename__ = "knowledge_vectors"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[Optional[str]] = mapped_column(Text)  # JSON float list
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
    )


class KnowledgeSource(Base, TimestampMixin):
    """4E.1 - the universal ingestion contract: one canonical registry row per
    (tenant, source object).

    Every knowledge object - internal (document, wiki, policy, sop, template,
    decision) or future external (4N adapters: Drive, Slack, Jira, ...) - is
    ingested through this single contract and then consumed identically by
    claims, topics, authority and freshness. Lifecycle follows the knowledge
    model: discovered - extracted - validated - active - updated - superseded
    - archived. Temporal truth: rows are never deleted; archival and
    supersession keep history and provenance.
    """

    __tablename__ = "knowledge_sources"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
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
    external_ref: Mapped[Optional[str]] = mapped_column(String(240))
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_type", "source_id",
            name="uq_knowledge_sources_entity",
        ),
    )


class KnowledgeClaim(Base, TimestampMixin):
    """4E.1 - a canonical claim about an organizational knowledge object.

    Claims carry the authority of their source and follow their own lifecycle:
    candidate - supported - authoritative - contested - superseded. Superseded
    claims are never deleted: valid_to + superseded_by keep the
    temporal truth ("what was true, what is true now").
    """

    __tablename__ = "knowledge_claims"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False)
    predicate: Mapped[str] = mapped_column(String(80), nullable=False)
    object_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(24), default="fact", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="supported", nullable=False)
    authority_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    context_type: Mapped[Optional[str]] = mapped_column(String(32))
    context_id: Mapped[Optional[str]] = mapped_column(String(32))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    superseded_by: Mapped[Optional[str]] = mapped_column(String(32))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    topic_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("knowledge_topics.id", ondelete="SET NULL")
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
            "organization_id", "subject_type", "subject_id", "predicate",
            name="uq_knowledge_claims_unique",
        ),
    )


class KnowledgeTopic(Base, TimestampMixin):
    """4E.3 - a canonical topic that groups related claims and entities."""

    __tablename__ = "knowledge_topics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("knowledge_topics.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "name",
            name="uq_knowledge_topics_org_name",
        ),
    )