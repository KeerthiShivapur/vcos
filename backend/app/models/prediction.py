"""Phase 19 — Predictive intelligence (predictions, history, models)."""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

PREDICTION_KINDS = (
    "project_failure", "employee_burnout", "customer_churn", "budget_overrun",
    "knowledge_loss", "missed_deadline", "hiring_need", "infrastructure_growth",
    "compliance_risk", "innovation_decline", "attrition", "skill_gap",
    "capacity_bottleneck",
)
PREDICTION_STATUSES = ("open", "acknowledged", "dismissed", "validated", "resolved")


class Prediction(Base, TimestampMixin):
    """A forward-looking organizational prediction with evidence."""

    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_org_kind", "organization_id", "kind"),
        Index("ix_predictions_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    probability: Mapped[float] = mapped_column(Float, default=0.5)
    impact: Mapped[str] = mapped_column(String(20), default="medium")
    level: Mapped[str] = mapped_column(String(20), default="medium")
    horizon_days: Mapped[int] = mapped_column(default=30)
    subject_type: Mapped[Optional[str]] = mapped_column(String(40))
    subject_id: Mapped[Optional[str]] = mapped_column(String(32))
    signals: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open")
    source_event: Mapped[Optional[str]] = mapped_column(String(120))
    due_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))


class PredictionHistory(Base, TimestampMixin):
    """Validated outcomes of past predictions (prediction -> outcome)."""

    __tablename__ = "prediction_history"
    __table_args__ = (
        Index("ix_pred_history_org_pred", "organization_id", "prediction_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    prediction_id: Mapped[str] = mapped_column(
        ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    outcome: Mapped[bool] = mapped_column(nullable=False)  # True = prediction came true
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    validated_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))


class PredictionModel(Base, TimestampMixin):
    """Registered prediction model per kind with measured accuracy."""

    __tablename__ = "prediction_models"
    __table_args__ = (
        Index("ix_pred_models_org_kind", "organization_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    params: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    predictions_count: Mapped[int] = mapped_column(default=0)
    last_trained_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
