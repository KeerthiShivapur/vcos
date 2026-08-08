"""Knowledge AI intelligence (Phase 4).

When no LLM provider is configured the system still needs AI-flavoured
intelligence over the organization's own knowledge. This module provides
deterministic intelligence that is grounded in real data:

  - summaries (first sentences + key signals)
  - keywords / tag suggestions
  - duplicate detection (embedding similarity)
  - outdated detection (review dates, staleness)
  - quality scoring (completeness, freshness, popularity, usage, review)

If an LLM provider is configured, `llm_summary` upgrades the summary quality
while the rule-based signals always stand as fallback.
"""

import json
import math
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.knowledge import knowledge_base as kb
from app.knowledge.embedding import cosine, embed_text, keywords, snippet
from app.models.knowledge import KnowledgeIndex, KnowledgeQuality, Policy

STOP = {
    "about", "after", "again", "all", "also", "any", "because", "been", "before",
    "being", "both", "between", "each", "few", "first", "get", "go", "here",
    "just", "like", "make", "many", "much", "must", "new", "now", "only", "other",
    "our", "out", "over", "same", "some", "such", "than", "then", "there", "thing",
    "things", "through", "too", "under", "until", "upon", "use", "used", "very",
    "way", "would", "year", "years", "also", "make", "need", "work", "one", "two",
    "may", "well", "even", "right", "good", "time", "could", "made", "used",
    "within", "without", "including", "however", "rather", "within",
}


def generate_summary(entity: Any) -> str:
    """Rule-based summary from the entity's own content."""
    parts: list[str] = []
    text = entity_text_clean(entity)
    if text:
        sentences = [
            s.strip()
            for s in text.replace("\n", " ").split(".")
            if len(s.strip()) > 25
        ]
        parts.append(" ".join(sentences[:2])[:280])
    if hasattr(entity, "category") and entity.category:
        parts.append(f"Category: {entity.category}.")
    status = getattr(entity, "status", "")
    parts.append(f"Status: {status}.")
    if hasattr(entity, "view_count"):
        parts.append(f"{entity.view_count or 0} views.")
    return " ".join(parts)


def entity_text_clean(entity: Any) -> str:
    return kb.entity_text(entity)


def suggest_tags(text: str, limit: int = 5) -> list[str]:
    toks = keywords(text, limit=limit * 3)
    out: list[str] = []
    for tok in toks:
        if tok in STOP or tok in out:
            continue
        out.append(tok)
        if len(out) >= limit:
            break
    return out


class KnowledgeAIService:
    async def enrich(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: str,
        organization_id: str,
        persist_summary: bool = True,
    ) -> dict[str, Any]:
        """Compute + persist summary/keywords/quality for one entity."""
        entity = await kb.resolve_entity(db, organization_id=organization_id, kind=entity_type, entity_id=entity_id)
        if entity is None:
            return {}
        text = kb.entity_text(entity)
        if persist_summary and getattr(entity, "ai_summary", None) is None:
            entity.ai_summary = generate_summary(entity)
        if persist_summary and getattr(entity, "keywords", None) is None:
            entity.keywords = json.dumps(keywords(text, limit=8))
        entity.updated_at = utcnow()
        await self._score(db, organization_id=organization_id, entity_type=entity_type, entity=entity)
        await db.flush()
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "summary": entity.ai_summary,
            "keywords": kb.parse_keywords(entity),
        }

    async def _score(self, db: AsyncSession, *, organization_id: str, entity_type: str, entity: Any) -> KnowledgeQuality:
        """Persist quality dimensions (0-100 each) + blended score."""
        completeness = 100 if len((getattr(entity, "content", "") or "")) >= 500 else 40
        if getattr(entity, "description", None):
            completeness = min(100, completeness + 20)
        if getattr(entity, "summary", None) or getattr(entity, "ai_summary", None):
            completeness = min(100, completeness + 20)

        age_days = (utcnow() - entity.updated_at).days if entity.updated_at else 0
        freshness = max(0, 100 - age_days // 3)

        popularity = min(100, (entity.view_count or 0) * 10)
        usage = 0
        if hasattr(entity, "usage_count"):
            usage = min(100, (entity.usage_count or 0) * 25)

        review_status = "unknown"
        if isinstance(entity, Policy):
            if entity.review_date and entity.review_date < date.today():
                review_status = "overdue"
            elif entity.review_date:
                review_status = "scheduled"
            elif entity.status == "published":
                review_status = "ok"
        elif entity.status in ("published", "approved"):
            review_status = "ok"
        elif entity.status == "in_review":
            review_status = "in_review"
        else:
            review_status = "draft"

        score = round(0.35 * completeness + 0.3 * freshness + 0.15 * popularity + 0.1 * usage)
        if review_status == "overdue":
            score = max(0, score - 25)

        row = (
            await db.execute(
                select(KnowledgeQuality).where(
                    KnowledgeQuality.organization_id == organization_id,
                    KnowledgeQuality.entity_type == entity_type,
                    KnowledgeQuality.entity_id == entity.id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = KnowledgeQuality(
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity.id,
            )
            db.add(row)
        row.completeness = completeness
        row.freshness = freshness
        row.popularity = popularity
        row.usage = usage
        row.review_status = review_status
        row.score = score
        row.updated_at = utcnow()
        await db.flush()
        return row

    async def find_duplicates(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_type: str,
        entity_id: str,
        threshold: float = 0.88,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Same-kind entities whose content is near-identical."""
        from app.knowledge.search_service import knowledge_search_service

        entity = await kb.resolve_entity(db, organization_id=organization_id, kind=entity_type, entity_id=entity_id)
        if entity is None:
            return []
        query = f"{entity.title} {getattr(entity, 'description', '') or ''}"
        results = await knowledge_search_service.search(
            db,
            organization_id=organization_id,
            query=query,
            mode="semantic",
            kinds=[entity_type],
            limit=limit + 1,
        )
        mine = embed_text(f"{entity.title} {kb.entity_text(entity)}")
        dupes: list[dict[str, Any]] = []
        for row in results["results"]:
            if row["id"] == entity_id:
                continue
            other = await kb.resolve_entity(db, organization_id=organization_id, kind=entity_type, entity_id=row["id"])
            if other is None:
                continue
            sim = cosine(mine, embed_text(kb.entity_text(other)))
            if sim >= threshold:
                dupes.append({"entity_type": entity_type, "entity_id": other.id, "title": other.title, "similarity": round(sim, 3)})
        return dupes

    async def outdated(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        stale_days: int = 180,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Entities that are stale or past their review date."""
        from app.schemas.knowledge import entity_url

        out: list[dict[str, Any]] = []
        cutoff = utcnow() - timedelta(days=stale_days)
        kinds = ("document", "wiki", "sop", "template", "policy", "decision")
        for kind in kinds:
            model = kb.KIND_MODELS[kind]
            rows = (
                await db.execute(
                    select(model).where(
                        model.organization_id == organization_id,
                        model.status.in_(("published", "approved", "made", "implemented", "reviewed")),
                        model.updated_at < cutoff,
                    )
                    .order_by(model.updated_at.asc())
                    .limit(limit)
                )
            ).scalars().all()
            for entity in rows:
                out.append(
                    {
                        "id": entity.id,
                        "kind": kind,
                        "title": entity.title,
                        "url": entity_url(kind, entity.id),
                        "updated_at": entity.updated_at,
                        "status": entity.status,
                    }
                )
        policies = (
            await db.execute(
                select(Policy).where(
                    Policy.organization_id == organization_id,
                    Policy.status.in_(("approved", "published")),
                    Policy.review_date.isnot(None),
                    Policy.review_date < date.today(),
                )
            )
        ).scalars().all()
        for policy in policies:
            out.append(
                {
                    "id": policy.id,
                    "kind": "policy",
                    "title": policy.title,
                    "url": entity_url("policy", policy.id),
                    "updated_at": policy.updated_at,
                    "status": "review_overdue",
                    "review_date": policy.review_date,
                }
            )
        return sorted(out, key=lambda x: x["updated_at"])[:limit]

    async def suggest_reviewers(self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str, limit: int = 3) -> list[str]:
        """Who reviews this: owner + recent editors + commenters."""
        entity = await kb.resolve_entity(db, organization_id=organization_id, kind=entity_type, entity_id=entity_id)
        if entity is None:
            return []
        ids: list[str] = []
        for field in ("owner_id", "approver_id"):
            value = getattr(entity, field, None)
            if value:
                ids.append(value)
        from app.models.knowledge import DocumentComment, DocumentVersion

        rows = (
            await db.execute(
                select(DocumentVersion.editor_id).where(
                    DocumentVersion.organization_id == organization_id,
                    DocumentVersion.entity_type == entity_type,
                    DocumentVersion.entity_id == entity_id,
                    DocumentVersion.editor_id.isnot(None),
                )
            )
        ).scalars().all()
        ids.extend(rows)
        comments = (
            await db.execute(
                select(DocumentComment.author_id).where(
                    DocumentComment.organization_id == organization_id,
                    DocumentComment.entity_type == entity_type,
                    DocumentComment.entity_id == entity_id,
                )
            )
        ).scalars().all()
        ids.extend(comments)
        seen: list[str] = []
        for uid in ids:
            if uid and uid not in seen:
                seen.append(uid)
        return seen[:limit]

    async def scan_duplicates_org(self, db: AsyncSession, *, organization_id: str, limit_per_kind: int = 200) -> int:
        """Worker pass: mark near-duplicates in quality rows + emit events."""
        from app.services.event_service import event_service

        detected = 0
        for kind in ("document", "policy", "sop", "template"):
            model = kb.KIND_MODELS[kind]
            rows = (
                await db.execute(
                    select(model).where(
                        model.organization_id == organization_id,
                        model.status != "archived",
                    )
                    .order_by(model.updated_at.desc())
                    .limit(limit_per_kind)
                )
            ).scalars().all()
            embeddings: dict[str, list[float]] = {}
            for entity in rows:
                embeddings[entity.id] = embed_text(kb.entity_text(entity))
            ids = list(embeddings)
            for i, entity in enumerate(rows):
                if entity.status == "archived":
                    continue
                dup: Optional[str] = None
                best = threshold = 0.9
                for j in range(i + 1, len(rows)):
                    sim = cosine(embeddings[ids[i]], embeddings[ids[j]])
                    if sim > best:
                        best = sim
                        dup = ids[j]
                quality = (
                    await db.execute(
                        select(KnowledgeQuality).where(
                            KnowledgeQuality.organization_id == organization_id,
                            KnowledgeQuality.entity_type == kind,
                            KnowledgeQuality.entity_id == entity.id,
                        )
                    )
                ).scalar_one_or_none()
                if dup is not None and quality is not None and quality.duplicate_of != dup:
                    quality.duplicate_of = dup
                    detected += 1
                    await event_service.emit(
                        db,
                        name="knowledge.duplicate_detected",
                        organization_id=organization_id,
                        payload={"entity_type": kind, "entity_id": entity.id, "duplicate_of": dup, "similarity": round(best, 3)},
                    )
        await db.flush()
        return detected


ai_service = KnowledgeAIService()
