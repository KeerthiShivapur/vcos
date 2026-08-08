"""Phase 7.13 — voice companion.

The companion is fully voice-capable: the frontend captures audio with the
Web Speech API (no uploads, no latency), and the backend handles voice-source
conversations identically to chat. This module adds the small text helpers the
voice path needs (transcript normalization, punctuation-free queries) and a
conversation factory for voice threads.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIConversation


def normalize_transcript(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def strip_fill_words(raw: str) -> str:
    text = normalize_transcript(raw)
    for filler in ("um", "uh", "er", "hmm", "like you know", "you know", "i mean", "kind of"):
        text = re.sub(rf"\b{re.escape(filler)}\b", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


async def ensure_voice_conversation(
    db: AsyncSession, *, organization_id: str, user_id: Optional[str], title: str = "Voice session"
) -> AIConversation:
    conversation = AIConversation(
        organization_id=organization_id,
        user_id=user_id,
        title=title,
        source="voice",
    )
    db.add(conversation)
    await db.flush()
    return conversation
