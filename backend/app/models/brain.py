"""Slice 4D.7 — Brain conversation turns (follow-up continuity artifact).

A conversation is a bounded, tenant- and owner-scoped session record so a
follow-up question ("Has this happened before?", "Who owns it?") can inherit
the anchor entity from the previous utterance — without the user repeating
the entity and without the frontend re-sending the anchor.

Observation-only artifact: turns are appended when a question is answered;
no operating entity is ever mutated through this table.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import utcnow
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class BrainConversation(Base, TimestampMixin):
    __tablename__ = "brain_conversations"
    __table_args__ = (
        Index("ix_brain_conversations_org_user", "organization_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    turn_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_anchor_type: Mapped[Optional[str]] = mapped_column(String(40))
    last_anchor_id: Mapped[Optional[str]] = mapped_column(String(32))
    last_anchor_title: Mapped[Optional[str]] = mapped_column(String(300))


class BrainConversationTurn(Base):
    __tablename__ = "brain_conversation_turns"
    __table_args__ = (
        Index("ix_brain_turns_conversation", "conversation_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("brain_conversations.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    anchor_type: Mapped[Optional[str]] = mapped_column(String(40))
    anchor_id: Mapped[Optional[str]] = mapped_column(String(32))
    anchor_title: Mapped[Optional[str]] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)