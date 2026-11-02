"""AI models for conversations, actions, and insights."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, Enum as SQLEnum, Integer, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class AIActionType(str):
    COMPLETION = "completion"
    CHAT = "chat"
    EMBEDDING = "embedding"
    SUMMARIZATION = "summarization"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    TRANSLATION = "translation"
    CODE_GENERATION = "code_generation"
    REASONING = "reasoning"
    PLANNING = "planning"
    ANALYSIS = "analysis"


class AIActionStatus(str):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AIAction(Base, TimestampMixin):
    __tablename__ = "ai_actions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[Optional[str]] = mapped_column(Text)
    tokens_prompt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_completion: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(default=0.0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=AIActionStatus.PENDING, nullable=False, index=True)
    error: Mapped[Optional[str]] = mapped_column(Text)
    context: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    aiactiontype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_ai_actions_org_user", "organization_id", "user_id"),
        Index("ix_ai_actions_org_status", "organization_id", "status"),
        Index("ix_ai_actions_org_created", "organization_id", "created_at"),
    )


class AIConversation(Base, TimestampMixin):
    __tablename__ = "ai_conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String(300))
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active, archived, deleted
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(default=0.0, nullable=False)
    aiactiontype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    messages: Mapped[List["AIMessage"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_ai_conversations_org_user", "organization_id", "user_id"),
        Index("ix_ai_conversations_org_status", "organization_id", "status"),
    )


class AIMessage(Base, TimestampMixin):
    __tablename__ = "ai_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # system, user, assistant, function
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tool_calls: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(100))
    aiactiontype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    conversation: Mapped["AIConversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_ai_messages_conversation", "conversation_id"),
    )


class AIFeedback(Base, TimestampMixin):
    __tablename__ = "ai_feedback"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ai_actions.id", ondelete="SET NULL"), index=True
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="SET NULL"), index=True
    )
    message_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ai_messages.id", ondelete="SET NULL"), index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False)  # helpful, accurate, creative, etc.
    comment: Mapped[Optional[str]] = mapped_column(Text)
    aiactiontype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


class AIInsight(Base, TimestampMixin):
    __tablename__ = "ai_insights"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    insight_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    impact_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)  # low, medium, high, critical
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)  # new, acknowledged, actioned, dismissed
    source_action_id: Mapped[Optional[str]] = mapped_column(ForeignKey("ai_actions.id", ondelete="SET NULL"), index=True)
    source_conversation_id: Mapped[Optional[str]] = mapped_column(ForeignKey("ai_conversations.id", ondelete="SET NULL"), index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    actionable_recommendations: Mapped[list] = mapped_column(JSON, default=list)
    supporting_evidence: Mapped[list] = mapped_column(JSON, default=list)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dismissed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    aiactiontype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_ai_insights_org_status", "organization_id", "status"),
        Index("ix_ai_insights_org_type", "organization_id", "insight_type"),
        Index("ix_ai_insights_org_priority", "organization_id", "priority"),
    )


class AIPlan(Base, TimestampMixin):
    __tablename__ = "ai_plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    plan_type: Mapped[str] = mapped_column(String(40), nullable=False)  # strategic, project, sprint, personal
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft, active, completed, cancelled
    steps: Mapped[list] = mapped_column(JSON, default=list)
    milestones: Mapped[list] = mapped_column(JSON, default=list)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    progress: Mapped[float] = mapped_column(default=0.0, nullable=False)
    aiactiontype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_ai_plans_org_user", "organization_id", "user_id"),
        Index("ix_ai_plans_org_status", "organization_id", "status"),
    )


class AIPrediction(Base, TimestampMixin):
    __tablename__ = "ai_predictions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    prediction_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    predicted_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    probability_distribution: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    features_used: Mapped[dict] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    is_accurate: Mapped[Optional[bool]] = mapped_column(Boolean)
    actual_value: Mapped[Optional[Any]] = mapped_column(JSON)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    aiactiontype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_ai_predictions_org_model", "organization_id", "model_id"),
        Index("ix_ai_predictions_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_ai_predictions_org_created", "organization_id", "created_at"),
    )


class AIRecommendation(Base, TimestampMixin):
    __tablename__ = "ai_recommendations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recommendation_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)  # new, accepted, dismissed, expired
    entity_type: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    action_url: Mapped[Optional[str]] = mapped_column(String(500))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    aiactiontype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_ai_recommendations_org_user", "organization_id", "user_id"),
        Index("ix_ai_recommendations_org_status", "organization_id", "status"),
        Index("ix_ai_recommendations_org_type", "organization_id", "recommendation_type"),
        Index("ix_ai_recommendations_expires", "expires_at"),
    )


class AIMemory(Base, TimestampMixin):
    """AI memory for persistent context and learning."""

    __tablename__ = "ai_memories"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    memory_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # fact, preference, pattern, context, correction
    key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="user_input", nullable=False)  # user_input, ai_inference, system
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_ai_memory_org_type", "organization_id", "memory_type"),
        Index("ix_ai_memory_org_key", "organization_id", "key"),
        Index("ix_ai_memory_org_expires", "organization_id", "expires_at"),
        UniqueConstraint("organization_id", "memory_type", "key", name="uq_ai_memory_org_type_key"),
        {"extend_existing": True},
    )