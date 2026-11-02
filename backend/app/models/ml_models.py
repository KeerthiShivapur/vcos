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
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
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
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_id: Mapped[str] = mapped_column(
        ForeignKey("ml_models.id", ondelete="CASCADE"), index=True, nullable=False
    )
    prediction_type: Mapped[str] = mapped_column(String(40), nullable=False)  # forecast, anomaly
    input_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON input
    output_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON output