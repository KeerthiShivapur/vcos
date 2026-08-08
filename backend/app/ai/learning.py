"""Phase 7.12 — continuous learning from feedback.

Feedback and corrections (``ai_feedback``) feed back into the system in three
ways:

  1. Corrections become semantic memories ("user prefers X over Y"), so future
     answers are grounded on the corrected preference.
  2. Accepted/dismissed recommendations and ratings adjust recommendation
     scoring (documented in the recommendation evidence).
  3. The learning loop worker periodically folds positive feedback into memory
     consolidation.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory import memory_manager
from app.models.ai import AIFeedback, AIMessage, AIRecommendation
from app.models.user import User


class LearningService:
    async def record_feedback(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: User,
        message_id: Optional[str] = None,
        content: Optional[str] = None,
        rating: Optional[int] = None,
        helpful: Optional[bool] = None,
        correction: Optional[str] = None,
    ) -> AIFeedback:
        row = AIFeedback(
            organization_id=organization_id,
            user_id=user.id,
            message_id=message_id,
            content=content,
            rating=rating,
            helpful=helpful,
            correction=correction,
        )
        db.add(row)
        await db.flush()
        if correction:
            await memory_manager.remember(
                db,
                organization_id=organization_id,
                content=f"Correction: {correction}",
                memory_type="semantic",
                kind="preference",
                scope="user",
                user_id=user.id,
                source="feedback",
                confidence=0.85,
                importance=6,
            )
        return row

    async def learn(self, db: AsyncSession, *, organization_id: str, limit: int = 200) -> dict[str, int]:
        rows = (
            await db.execute(
                select(AIFeedback)
                .where(
                    AIFeedback.organization_id == organization_id,
                    AIFeedback.correction.is_not(None),
                )
                .order_by(AIFeedback.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        learned = 0
        for row in rows:
            await memory_manager.remember(
                db,
                organization_id=organization_id,
                content=f"Correction: {row.correction}",
                memory_type="semantic",
                kind="preference",
                scope="user",
                user_id=row.user_id,
                source="learning_loop",
                confidence=0.8,
                importance=5,
            )
            learned += 1
        return {"corrections_learned": learned}

    async def apply_recommendation_feedback(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        recommendation_id: str,
        action: str,
    ) -> Optional[dict[str, Any]]:
        row = await db.get(AIRecommendation, recommendation_id)
        if row is None or row.organization_id != organization_id:
            return None
        row.status = action
        return {"id": row.id, "kind": row.kind, "status": row.status}


learning_service = LearningService()
