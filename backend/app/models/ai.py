"""Phase 7 — Universal AI Companion data models.

The AI layer is a first-class citizen: conversations, messages, memories
(working/episodic/semantic/procedural/organizational), recommendations,
actions, plans, predictions, insights and feedback all persist per
organization with the standard multi-tenancy columns.
"""

from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class AIConversation(Base, TimestampMixin):
    """A companion conversation thread (chat or voice)."""

    __tablename__ = "ai_conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(20), default="chat")  # chat | voice | embedded
    page_url: Mapped[Optional[str]] = mapped_column(String(500))
    updated_at: Mapped[Optional[str]] = mapped_column(String(40))


class AIMessage(Base, TimestampMixin):
    """One message inside an AI conversation, with grounding + usage info."""

    __tablename__ = "ai_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intents: Mapped[Optional[str]] = mapped_column(String(200))
    source: Mapped[Optional[str]] = mapped_column(String(20))  # rules | llm | local
    model: Mapped[Optional[str]] = mapped_column(String(80))
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    context_json: Mapped[Optional[str]] = mapped_column(Text)  # grounded context snapshot
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)


class AIMemory(Base, TimestampMixin):
    """Long-term organizational memory (Phase 7.2).

    memory_type mirrors the cognitive model:
      working | episodic | semantic | procedural | organizational
    """

    __tablename__ = "ai_memories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    memory_type: Mapped[str] = mapped_column(
        String(30), default="semantic", index=True
    )  # working | episodic | semantic | procedural | organizational
    scope: Mapped[str] = mapped_column(String(30), default="organization")  # organization | user | project | meeting | team
    subject_type: Mapped[Optional[str]] = mapped_column(String(40))  # project | task | meeting | employee | document | decision
    subject_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)  # fact | insight | preference | decision | summary | relation | procedure | culture
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(120))
    confidence: Mapped[Optional[float]] = mapped_column(Float, default=0.9)
    importance: Mapped[Optional[int]] = mapped_column(Integer, default=5)  # 1-10
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)


class AIRecommendation(Base, TimestampMixin):
    """Recommendation engine output (Phase 7.12)."""

    __tablename__ = "ai_recommendations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    audience: Mapped[str] = mapped_column(String(20), default="user")  # user | organization
    kind: Mapped[str] = mapped_column(String(40), index=True)  # expert | document | collaborator | training | meeting | knowledge | action | learning
    target_type: Mapped[Optional[str]] = mapped_column(String(40))
    target_id: Mapped[Optional[str]] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[float]] = mapped_column(Float, default=0.7)
    score: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active | accepted | dismissed


class AIAction(Base, TimestampMixin):
    """Action engine executions (Phase 7.13) — every run is audited."""

    __tablename__ = "ai_actions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(60), index=True)  # create_task | schedule_meeting | ...
    status: Mapped[str] = mapped_column(String(20), default="executed")  # pending | executed | rejected | failed
    payload_json: Mapped[Optional[str]] = mapped_column(Text)
    result_json: Mapped[Optional[str]] = mapped_column(Text)
    permission_check: Mapped[Optional[str]] = mapped_column(String(120))
    executed_at: Mapped[Optional[str]] = mapped_column(String(40))


class AIFeedback(Base, TimestampMixin):
    """Feedback + corrections that drive continuous learning (Phase 7.16)."""

    __tablename__ = "ai_feedback"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(32))
    content: Mapped[Optional[str]] = mapped_column(Text)
    rating: Mapped[Optional[int]] = mapped_column(Integer)
    helpful: Mapped[Optional[bool]] = mapped_column(default=True)
    correction: Mapped[Optional[str]] = mapped_column(Text)


class AIPlan(Base, TimestampMixin):
    """Planning engine output (Phase 7.11)."""

    __tablename__ = "ai_plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_type: Mapped[str] = mapped_column(String(30), index=True)  # daily | weekly | sprint | learning | roadmap
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content_json: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")


class AIPrediction(Base, TimestampMixin):
    """Prediction engine output (Phase 7.13)."""

    __tablename__ = "ai_predictions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject_type: Mapped[str] = mapped_column(String(30), index=True)  # project | employee | organization
    subject_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    metric: Mapped[str] = mapped_column(String(40), index=True)  # delay_risk | burnout_risk | overload | attrition_risk | missed_deadline
    score: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    level: Mapped[str] = mapped_column(String(10), default="low")  # low | medium | high
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    factors_json: Mapped[Optional[str]] = mapped_column(Text)


class AIInsight(Base, TimestampMixin):
    """Background intelligence insights (Phase 7.14)."""

    __tablename__ = "ai_insights"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), index=True)  # delay | overload | knowledge_gap | meeting_load | health
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info | warning | critical
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | accepted | dismissed
