"""Phase 9.11 — Duplicate work detection engine.

Detects duplicate projects, tasks, documents, meetings, policies and ideas by
title similarity. Prevents wasted effort by flagging pairs for consolidation.

Knowledge duplicates are already handled by the knowledge engine
(KnowledgeInsight kind=duplicate); this engine covers work + community kinds.
"""

import logging
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.communication import InnovationIdea
from app.models.intelligence import DuplicateDetection
from app.models.knowledge import Policy
from app.models.meeting import Meeting
from app.models.project import Project
from app.models.task import Task

logger = logging.getLogger("vcos.intelligence.duplicate")

THRESHOLD = 0.72


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _similarity(a: str, b: str) -> float:
    ta, tb = set(_norm(a).split()), set(_norm(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _token_set_score(a: str, b: str) -> float:
    """Jaccard with word-boundary bonus: exact title duplicates score 1.0."""
    na, nb = _norm(a), _norm(b)
    if na and na == nb:
        return 1.0
    return _similarity(a, b)


class DuplicateEngine:
    async def scan(
        self, db: AsyncSession, *, organization_id: str,
    ) -> int:
        """Scan all kinds for duplicate pairs; returns number of new detections."""
        created = 0
        for model, kind in (
            (Project, "project"), (Task, "task"), (Meeting, "meeting"),
            (Policy, "policy"), (InnovationIdea, "idea"),
        ):
            rows = list(
                (
                    await db.execute(
                        select(model).where(model.organization_id == organization_id)
                    )
                ).scalars().all()
            )
            for i in range(len(rows)):
                for j in range(i + 1, len(rows)):
                    a, b = rows[i], rows[j]
                    title_a = getattr(a, "title", None) or getattr(a, "name", "")
                    title_b = getattr(b, "title", None) or getattr(b, "name", "")
                    score = _token_set_score(title_a, title_b)
                    if score < THRESHOLD:
                        continue
                    if getattr(a, "id", None) == getattr(b, "id", None):
                        continue
                    ok = await self.record(
                        db, organization_id=organization_id, kind=kind,
                        entity_type_a=model.__tablename__, entity_id_a=a.id, title_a=title_a,
                        entity_type_b=model.__tablename__, entity_id_b=b.id, title_b=title_b,
                        similarity=round(score, 3),
                        reason=f"Titles are {score:.0%} similar.",
                    )
                    created += int(ok)
        return created

    async def record(
        self, db: AsyncSession, *, organization_id: str, kind: str,
        entity_type_a: str, entity_id_a: str, title_a: Optional[str],
        entity_type_b: str, entity_id_b: str, title_b: Optional[str],
        similarity: float, reason: Optional[str],
    ) -> bool:
        existing = (
            await db.execute(
                select(DuplicateDetection).where(
                    DuplicateDetection.organization_id == organization_id,
                    DuplicateDetection.kind == kind,
                    DuplicateDetection.entity_type_a == entity_type_a,
                    DuplicateDetection.entity_id_a == entity_id_a,
                    DuplicateDetection.entity_type_b == entity_type_b,
                    DuplicateDetection.entity_id_b == entity_id_b,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.status == "open":
                return False
            existing.status = "open"
            return False
        db.add(
            DuplicateDetection(
                organization_id=organization_id,
                kind=kind,
                entity_type_a=entity_type_a, entity_id_a=entity_id_a, title_a=title_a,
                entity_type_b=entity_type_b, entity_id_b=entity_id_b, title_b=title_b,
                similarity=similarity, reason=reason, status="open",
            )
        )
        return True

    async def list_detections(
        self, db: AsyncSession, *, organization_id: str, limit: int = 50,
        kind: Optional[str] = None, status: Optional[str] = "open",
    ) -> list[dict[str, Any]]:
        filters = [DuplicateDetection.organization_id == organization_id]
        if kind:
            filters.append(DuplicateDetection.kind == kind)
        if status:
            filters.append(DuplicateDetection.status == status)
        rows = (
            await db.execute(
                select(DuplicateDetection).where(*filters)
                .order_by(DuplicateDetection.similarity.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "entity_type_a": r.entity_type_a,
                "entity_id_a": r.entity_id_a,
                "title_a": r.title_a,
                "entity_type_b": r.entity_type_b,
                "entity_id_b": r.entity_id_b,
                "title_b": r.title_b,
                "similarity": r.similarity,
                "reason": r.reason,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def set_status(self, db: AsyncSession, *, organization_id: str, detection_id: str, status: str) -> Optional[dict[str, Any]]:
        row = await db.get(DuplicateDetection, detection_id)
        if row is None or row.organization_id != organization_id:
            return None
        row.status = status
        return {"id": row.id, "status": row.status}


duplicate_engine = DuplicateEngine()
