"""Prediction models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class PredictionModel(Base, TimestampMixin):
    __tablename__ = "prediction_models"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    algorithm: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="1.0", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    features: Mapped[List[str]] = mapped_column(JSON, default=list)
    target: Mapped[str] = mapped_column(String(100), nullable=False)
    hyperparameters: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    training_data_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    training_data_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deployed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deployed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    predictionmodel_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_prediction_models_org_type", "organization_id", "model_type"),
        Index("ix_prediction_models_org_active", "organization_id", "is_active"),
    )


class Prediction(Base, TimestampMixin):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_id: Mapped[str] = mapped_column(
        ForeignKey("prediction_models.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    prediction_type: Mapped[str] = mapped_column(String(60), nullable=False)
    predicted_value: Mapped[float] = mapped_column(default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    probability_distribution: Mapped[Optional[dict]] = mapped_column(JSON)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    actual_value: Mapped[Optional[float]] = mapped_column(default=None)
    is_correct: Mapped[Optional[bool]] = mapped_column(default=None)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    predictionmodel_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_predictions_org_model", "organization_id", "model_id"),
        Index("ix_predictions_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_predictions_org_created", "organization_id", "created_at"),
    )


class PredictionHistory(Base, TimestampMixin):
    __tablename__ = "prediction_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_id: Mapped[str] = mapped_column(
        ForeignKey("prediction_models.id", ondelete="CASCADE"), index=True, nullable=False
    )
    prediction_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)  # created, evaluated, retrained, deprecated
    old_value: Mapped[Optional[float]] = mapped_column(default=None)
    new_value: Mapped[Optional[float]] = mapped_column(default=None)
    predictionmodel_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_prediction_history_org_model", "organization_id", "model_id"),
        Index("ix_prediction_history_org_prediction", "organization_id", "prediction_id"),
    )


PREDICTION_KINDS = (
    "revenue",
    "cost",
    "demand",
    "churn",
    "conversion",
    "retention",
    "growth",
    "anomaly",
    "risk",
    "opportunity",
    "capacity",
    "performance",
    "quality",
    "satisfaction",
    "engagement",
    "revenue_forecast",
    "cost_forecast",
    "demand_forecast",
    "capacity_forecast",
)

PREDICTION_STATUSES = (
    "pending",
    "completed",
    "evaluated",
    "correct",
    "incorrect",
    "partial",
    "expired",
    "cancelled",
)