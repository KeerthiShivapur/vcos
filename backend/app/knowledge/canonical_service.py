"""Slice 4E.1 — Knowledge Foundation & Canonical Model.

The universal ingestion contract for the Living Organizational Knowledge
Model. Every knowledge object (internal today, external via 4N later) is
normalized into one canonical shape:

    KnowledgeSource  — one registry row per (tenant, object) with lifecycle
                       discovered → extracted → validated → active → updated
                       → superseded → archived. Rows are never deleted.
    KnowledgeClaim   — canonical facts about the object with their own
                       lifecycle: candidate → supported → authoritative →
                       contested → superseded. Superseded claims keep
                       valid_to + superseded_by (temporal truth, never
                       delete).
    KnowledgeEvidence— the claim → source link: which source, which excerpt,
                       with what weight.
    KnowledgeTopic   — the canonical name registry seeding entity resolution
                       (4E.4) via aliases.

Behavioral laws (mirroring 4D):

* event-driven: ingestion is triggered by existing durable events, never by
  nightly scans; re-ingesting the same content is a no-op (exact-once),
* governance-first: every read resolves caller access before retrieval and
  never fetches what the caller cannot see,
* bounded: all reads and the on-demand reconcile cap candidate counts with
  hard SQL limits — no full-org scans,
* tenant-scoped: every query is anchored to the caller's organization_id.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.company_context import resolve_caller_access
from app.knowledge import knowledge_base as kb
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEvidence,
    KnowledgeSource,
    KnowledgeTopic,
)

logger = logging.getLogger("vcos.knowledge.canonical")

# lifecycle of the underlying object -> archive states
_ARCHIVED_STATUSES = frozenset({"archived", "deleted", "rejected"})

# deterministic, source-type-based authority, per the 4E authority model:
# official governance decision > approved policy > authoritative system
# record > project decision > team record > unverified statement.
_AUTHORITY: dict[tuple[str, str], int] = {
    ("document", "published"): 3,
    ("wiki", "published"): 3,
    ("sop", "published"): 3,
    ("template", "published"): 3,
    ("policy", "approved"): 5,
    ("policy", "published"): 5,
    ("decision", "made"): 4,
    ("decision", "implemented"): 5,
    ("decision", "reviewed"): 4,
}

_AUTHORITY_LABELS = {
    1: "unverified",
    2: "team_record",
    3: "documented",
    4: "authoritative",
    5: "official",
}

_REGISTRY_CANDIDATES = 60
_CLAIM_CANDIDATES = 100
_TOPIC_CANDIDATES = 50
_DEFAULT_LIMIT = 12
_MAX_LIMIT = 25
_MAX_RECONCILE = 100


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _freshness(source_updated_at: Optional[datetime], now: Optional[datetime] = None) -> tuple[int, str]:
    """Age-based freshness model: very_high → high → medium → low → stale."""
    from app.core.timeutils import ensure_aware

    stamp = ensure_aware(source_updated_at) if source_updated_at else None
    current = ensure_aware(now) if now else now_utc()
    age_days = max(0, (current - stamp).days) if stamp else None
    if age_days is None:
        return 0, "stale"
    if age_days <= 1:
        return 100, "very_high"
    if age_days <= 7:
        return 90, "high"
    if age_days <= 30:
        return 70, "medium"
    if age_days <= 90:
        return 40, "low"
    return 10, "stale"


def _authority_for(entity: Any) -> int:
    kind = getattr(entity, "_kind", None) or ""
    status = getattr(entity, "status", "draft") or "draft"
    return _AUTHORITY.get((kind, status), 1)


def _claim_state(authority_level: int) -> str:
    if authority_level >= 5:
        return "authoritative"
    if authority_level >= 3:
        return "supported"
    return "candidate"


def _source_hash(entity: Any) -> str:
    payload = "|".join(
        str(getattr(entity, field, None) or "") for field in ("title", "content", "summary", "status", "version")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _provenance(entity: Any, event_name: Optional[str]) -> dict[str, Any]:
    return {
        "kind": getattr(entity, "_kind", None),
        "author_id": getattr(entity, "author_id", None) or getattr(entity, "owner_id", None),
        "category": getattr(entity, "category", None),
        "keywords": getattr(entity, "keywords", None),
        "project_id": getattr(entity, "project_id", None),
        "department_id": getattr(entity, "department_id", None),
        "team_id": getattr(entity, "team_id", None),
        "published_at": getattr(entity, "published_at", None),
        "last_event": event_name,
    }


def _context_for(entity: Any) -> tuple[Optional[str], Optional[str]]:
    for attr, ctx_type in (("project_id", "project"), ("department_id", "department"), ("team_id", "team")):
        value = getattr(entity, attr, None)
        if value:
            return ctx_type, value
    return None, None


def _claim_payload(entity: Any, chosen_option: Optional[str]) -> tuple[str, str, str]:
    kind = getattr(entity, "_kind", "")
    title = getattr(entity, "title", "") or "untitled"
    status = getattr(entity, "status", "draft") or "draft"
    if kind == "decision":
        suffix = f" — chose '{chosen_option}'" if chosen_option else ""
        return "decision", "decision", f"Decision '{(title[:180])}' was made{ suffix}: status={status}"
    if kind == "policy":
        return "status", "effective", f"Policy '{(title[:180])}' is effective — status={status}"
    return "fact", "states", f"{kind.capitalize()} '{(title[:180])}' records status={status}"


class CanonicalEngine:
    """4E.1 canonical knowledge model: ingestion, lifecycle and governed reads."""

    # ------------------------------------------------------------ ingestion

    async def ingest(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_type: str,
        entity_id: str,
        event_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update the canonical model for one knowledge object (exact-once).

        Idempotent: unchanged content refreshes freshness only — never a
        duplicate claim and never a spurious lifecycle bump.
        """
        if entity_type not in kb.KIND_MODELS:
            return {"status": "skipped", "reason": f"unsupported kind: {entity_type}"}
        entity = await kb.resolve_entity(
            db, organization_id=organization_id, kind=entity_type, entity_id=entity_id
        )
        if entity is None:
            return {"status": "skipped", "reason": "entity not found"}
        entity._kind = entity_type

        title = getattr(entity, "title", "") or "untitled"
        entity_status = getattr(entity, "status", "draft") or "draft"
        content_sum = _source_hash(entity)
        version = getattr(entity, "version", 1) or 1
        source_updated = getattr(entity, "updated_at", None) or getattr(entity, "published_at", None)

        source = (
            await db.execute(
                select(KnowledgeSource).where(
                    KnowledgeSource.organization_id == organization_id,
                    KnowledgeSource.source_type == entity_type,
                    KnowledgeSource.source_id == entity_id,
                )
            )
        ).scalar_one_or_none()

        now = now_utc()
        changed = source is None or source.content_hash != content_sum or source.version != version
        authority = _authority_for(entity)
        score, label = _freshness(source_updated)
        provenance = _provenance(entity, event_name)

        if source is None:
            lifecycle = "validated" if authority >= 3 else "active"
            source = KnowledgeSource(
                organization_id=organization_id,
                source_type=entity_type,
                source_id=entity_id,
                kind="internal",
                title=title,
                content_hash=content_sum,
                version=version,
                lifecycle=lifecycle,
                source_status=entity_status,
                authority_level=authority,
                freshness_score=score,
                freshness_label=label,
                last_verified_at=now,
                source_updated_at=source_updated,
                provenance_json=json.dumps(provenance, default=str),
                synced_at=now,
            )
            db.add(source)
        else:
            old_lifecycle = source.lifecycle
            if entity_status in _ARCHIVED_STATUSES:
                lifecycle = "archived"
            elif old_lifecycle in ("archived", "superseded"):
                lifecycle = "validated" if authority >= 3 else "active"
            elif changed:
                lifecycle = "updated"
            else:
                lifecycle = old_lifecycle
            source.title = title
            source.content_hash = content_sum
            source.version = version
            source.lifecycle = lifecycle
            source.source_status = entity_status
            source.authority_level = authority
            source.freshness_score = score
            source.freshness_label = label
            source.last_verified_at = now
            source.source_updated_at = source_updated
            source.provenance_json = json.dumps(provenance, default=str)
            source.synced_at = now

        await self._sync_claims(
            db, organization_id=organization_id,
            entity_type=entity_type, entity_id=entity_id,
            entity=entity, changed=changed,
            authority=authority,
            source_updated=source_updated,
        )
        await self._sync_topics(
            db, organization_id=organization_id,
            entity=entity, provenance=provenance,
        )
        await db.flush()
        return {"status": "ok", "entity_type": entity_type, "entity_id": entity_id, "lifecycle": source.lifecycle}

    async def _sync_claims(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_type: str,
        entity_id: str,
        entity: Any,
        changed: bool,
        authority: int,
        source_updated: Optional[datetime],
    ) -> None:
        """Supersede the previous claims for this object, never delete them."""
        if not changed:
            return
        chosen_option: Optional[str] = None
        if entity_type == "decision":
            from app.models.knowledge import DecisionOption

            option = (
                await db.execute(
                    select(DecisionOption).where(
                        DecisionOption.organization_id == organization_id,
                        DecisionOption.decision_id == entity_id,
                        DecisionOption.chosen.is_(True),
                    )
                )
            ).scalars().first()
            if option is not None:
                chosen_option = option.title

        claim_type, predicate, object_text = _claim_payload(entity, chosen_option)
        context_type, context_id = _context_for(entity)
        now = now_utc()
        claim_status = _claim_state(authority)
        claim = KnowledgeClaim(
            organization_id=organization_id,
            subject_type=entity_type,
            subject_id=entity_id,
            predicate=predicate,
            object_text=object_text,
            claim_type=claim_type,
            status=claim_status,
            authority_level=authority,
            confidence=min(1.0, 0.5 + 0.1 * authority),
            context_type=context_type,
            context_id=context_id,
            valid_from=source_updated or now,
            source_type=entity_type,
            source_id=entity_id,
            created_by=provenance_author(entity),
        )
        db.add(claim)
        await db.flush()
        db.add(
            KnowledgeEvidence(
                organization_id=organization_id,
                claim_id=claim.id,
                source_type=entity_type,
                source_id=entity_id,
                excerpt=(getattr(entity, "summary", None) or getattr(entity, "title", ""))[:400] or None,
                role="primary",
                confidence=1.0,
            )
        )
        open_claims = (
            await db.execute(
                select(KnowledgeClaim).where(
                    KnowledgeClaim.organization_id == organization_id,
                    KnowledgeClaim.subject_type == entity_type,
                    KnowledgeClaim.subject_id == entity_id,
                    KnowledgeClaim.status != "superseded",
                )
            )
        ).scalars().all()
        for old in open_claims:
            if old.id == claim.id:
                continue
            old.status = "superseded"
            old.valid_to = now
            old.superseded_by = claim.id

    async def _sync_topics(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity: Any,
        provenance: dict[str, Any],
    ) -> None:
        """Seed the canonical topic registry from category + keywords (bounded)."""
        names: list[tuple[str, str]] = []
        category = provenance.get("category")
        if category:
            names.append((str(category).strip()[:120], "category"))
        keywords = provenance.get("keywords")
        if keywords:
            for piece in str(keywords).split(","):
                piece = piece.strip()[:120]
                if piece:
                    names.append((piece, "keyword"))
        entity_type = getattr(entity, "_kind", None)
        entity_id = getattr(entity, "id", None)
        for name, _origin in names[:3]:
            if not name:
                continue
            topic = (
                await db.execute(
                    select(KnowledgeTopic).where(
                        KnowledgeTopic.organization_id == organization_id,
                        KnowledgeTopic.name == name,
                    )
                )
            ).scalar_one_or_none()
            if topic is None:
                db.add(
                    KnowledgeTopic(
                        organization_id=organization_id,
                        name=name,
                        aliases_json=None,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        category=category or None,
                        status="active",
                        created_by=provenance.get("author_id"),
                    )
                )

    # ------------------------------------------------------- on-demand worker

    async def reconcile(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        kind: Optional[str] = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Bounded on-demand resync: most-recently-updated objects, hard cap.

        Never a full-org scan — this exists only for recovery after schema
        changes or manual corrections; normal flow is event-driven.
        """
        limit = max(1, min(limit, _MAX_RECONCILE))
        kinds = [kind] if kind in kb.KIND_MODELS else list(kb.KIND_MODELS)
        processed: list[dict[str, Any]] = []
        remaining = limit
        for entity_kind in kinds:
            if remaining <= 0:
                break
            model = kb.KIND_MODELS[entity_kind]
            ids = list(
                (
                    await db.execute(
                        select(model.id)
                        .where(model.organization_id == organization_id)
                        .order_by(model.updated_at.desc())
                        .limit(remaining)
                    )
                ).scalars().all()
            )
            for entity_id in ids:
                result = await self.ingest(
                    db, organization_id=organization_id,
                    entity_type=entity_kind, entity_id=entity_id,
                    event_name="reconcile.on_demand",
                )
                if result.get("status") == "ok":
                    processed.append(
                        {"entity_type": entity_kind, "entity_id": entity_id, "lifecycle": result.get("lifecycle")}
                    )
            remaining -= len(ids)
        await db.flush()
        return {"processed": len(processed), "items": processed, "limit": limit}

    # ------------------------------------------------------------- governed reads

    async def _access(self, db: AsyncSession, *, organization_id: str, user: Any):
        return await resolve_caller_access(db, organization_id=organization_id, user=user)

    @staticmethod
    def _visible(access: Any, provenance: Optional[dict[str, Any]]) -> bool:
        if access.org_wide:
            return True
        project_id = (provenance or {}).get("project_id")
        return bool(project_id and project_id in access.project_ids)

    async def registry(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        limit: int = _DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Governed canonical registry map (bounded, never a full scan)."""
        limit = max(1, min(limit, _MAX_LIMIT))
        access = await self._access(db, organization_id=organization_id, user=user)
        candidates = (
            await db.execute(
                select(KnowledgeSource)
                .where(KnowledgeSource.organization_id == organization_id)
                .order_by(KnowledgeSource.updated_at.desc())
                .limit(_REGISTRY_CANDIDATES)
            )
        ).scalars().all()
        visible = [
            s for s in candidates if self._visible(access, _load_provenance(s.provenance_json))
        ]
        by_status: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for s in visible:
            by_status[s.lifecycle] = by_status.get(s.lifecycle, 0) + 1
            by_kind[s.source_type] = by_kind.get(s.source_type, 0) + 1
        return {
            "total": len(visible),
            "scope": "org" if access.org_wide else "project",
            "by_status": by_status,
            "by_kind": by_kind,
            "sources": [self._source_out(s) for s in visible[:limit]],
            "limit": limit,
            "generated_at": now_utc().isoformat(),
        }

    async def source_detail(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        source_type: str,
        source_id: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        """One canonical source with its claims (each with evidence), temporal
        history preserved through superseded claims. 404-worthy when hidden."""
        if source_type not in kb.KIND_MODELS:
            return None
        access = await self._access(db, organization_id=organization_id, user=user)
        source = (
            await db.execute(
                select(KnowledgeSource).where(
                    KnowledgeSource.organization_id == organization_id,
                    KnowledgeSource.source_type == source_type,
                    KnowledgeSource.source_id == source_id,
                )
            )
        ).scalar_one_or_none()
        if source is None or not self._visible(access, _load_provenance(source.provenance_json)):
            return None
        claims = list(
            (
                await db.execute(
                    select(KnowledgeClaim)
                    .where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.subject_type == source_type,
                        KnowledgeClaim.subject_id == source_id,
                    )
                    .order_by(KnowledgeClaim.valid_from.desc())
                    .limit(_CLAIM_CANDIDATES)
                )
            ).scalars().all()
        )
        evidence_rows = []
        if claims:
            evidence_rows = list(
                (
                    await db.execute(
                        select(KnowledgeEvidence).where(
                            KnowledgeEvidence.organization_id == organization_id,
                            KnowledgeEvidence.claim_id.in_([c.id for c in claims]),
                        )
                    )
                ).scalars().all()
            )
        by_claim: dict[str, list[dict[str, Any]]] = {}
        for ev in evidence_rows:
            by_claim.setdefault(ev.claim_id, []).append(
                {
                    "source_type": ev.source_type,
                    "source_id": ev.source_id,
                    "excerpt": ev.excerpt,
                    "role": ev.role,
                    "confidence": ev.confidence,
                }
            )
        claim_out = []
        for c in claims:
            claim_out.append(
                self._claim_out(c, evidence=by_claim.get(c.id, []))
            )
        return {
            "source": self._source_out(source),
            "authority": {
                "level": source.authority_level,
                "label": _AUTHORITY_LABELS.get(source.authority_level, "unverified"),
            },
            "freshness": {
                "score": source.freshness_score,
                "label": source.freshness_label,
                "last_verified_at": source.last_verified_at.isoformat() if source.last_verified_at else None,
                "source_updated_at": source.source_updated_at.isoformat() if source.source_updated_at else None,
            },
            "claims": claim_out,
            "generated_at": now_utc().isoformat(),
        }

    async def recent_claims(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Recent canonical claims across accessible sources (bounded)."""
        limit = max(1, min(limit, _MAX_LIMIT))
        access = await self._access(db, organization_id=organization_id, user=user)
        candidates = list(
            (
                await db.execute(
                    select(KnowledgeClaim)
                    .where(KnowledgeClaim.organization_id == organization_id)
                    .order_by(KnowledgeClaim.updated_at.desc())
                    .limit(_CLAIM_CANDIDATES)
                )
            ).scalars().all()
        )
        if not candidates:
            return {"total": 0, "claims": [], "scope": "org" if access.org_wide else "project", "limit": limit}
        source_rows = list(
            (
                await db.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.organization_id == organization_id,
                        KnowledgeSource.source_type.in_({c.subject_type for c in candidates}),
                    )
                )
            ).scalars().all()
        )
        by_source: dict[tuple[str, str], KnowledgeSource] = {
            (s.source_type, s.source_id): s for s in source_rows
        }
        visible: list[dict[str, Any]] = []
        for c in candidates:
            source = by_source.get((c.subject_type, c.subject_id))
            if source is None or not self._visible(access, _load_provenance(source.provenance_json)):
                continue
            visible.append(self._claim_out(c, evidence=[]))
        return {
            "total": len(visible),
            "claims": visible[:limit],
            "scope": "org" if access.org_wide else "project",
            "limit": limit,
        }

    async def topics(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Canonical topic registry with aliases (bounded)."""
        limit = max(1, min(limit, _MAX_LIMIT))
        access = await self._access(db, organization_id=organization_id, user=user)
        candidates = list(
            (
                await db.execute(
                    select(KnowledgeTopic)
                    .where(KnowledgeTopic.organization_id == organization_id)
                    .order_by(KnowledgeTopic.updated_at.desc())
                    .limit(_TOPIC_CANDIDATES)
                )
            ).scalars().all()
        )
        visible: list[dict[str, Any]] = []
        for topic in candidates:
            if topic.entity_type and topic.entity_id and not access.org_wide:
                source = (
                    await db.execute(
                        select(KnowledgeSource).where(
                            KnowledgeSource.organization_id == organization_id,
                            KnowledgeSource.source_type == topic.entity_type,
                            KnowledgeSource.source_id == topic.entity_id,
                        )
                    )
                ).scalar_one_or_none()
                if source is not None and not self._visible(
                    access, _load_provenance(source.provenance_json)
                ):
                    continue
            visible.append(
                {
                    "id": topic.id,
                    "name": topic.name,
                    "aliases": _load_aliases(topic.aliases_json),
                    "entity_type": topic.entity_type,
                    "entity_id": topic.entity_id,
                    "category": topic.category,
                    "status": topic.status,
                    "updated_at": topic.updated_at.isoformat() if topic.updated_at else None,
                }
            )
        return {"total": len(visible), "topics": visible[:limit], "limit": limit}

    # ---------------------------------------------------------------- shaping

    @staticmethod
    def _source_out(source: KnowledgeSource) -> dict[str, Any]:
        provenance = _load_provenance(source.provenance_json)
        return {
            "id": source.id,
            "source_type": source.source_type,
            "source_id": source.source_id,
            "kind": source.kind,
            "title": source.title,
            "version": source.version,
            "lifecycle": source.lifecycle,
            "source_status": source.source_status,
            "authority_level": source.authority_level,
            "authority_label": _AUTHORITY_LABELS.get(source.authority_level, "unverified"),
            "freshness_score": source.freshness_score,
            "freshness_label": source.freshness_label,
            "last_verified_at": source.last_verified_at.isoformat() if source.last_verified_at else None,
            "source_updated_at": source.source_updated_at.isoformat() if source.source_updated_at else None,
            "url": f"/knowledge/{source.source_type}/{source.source_id}",
            "project_id": provenance.get("project_id"),
            "category": provenance.get("category"),
            "last_event": provenance.get("last_event"),
            "external_ref": source.external_ref,
        }

    @staticmethod
    def _claim_out(claim: KnowledgeClaim, *, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "id": claim.id,
            "subject_type": claim.subject_type,
            "subject_id": claim.subject_id,
            "predicate": claim.predicate,
            "object_text": claim.object_text,
            "claim_type": claim.claim_type,
            "status": claim.status,
            "authority_level": claim.authority_level,
            "authority_label": _AUTHORITY_LABELS.get(claim.authority_level, "unverified"),
            "confidence": claim.confidence,
            "context_type": claim.context_type,
            "context_id": claim.context_id,
            "valid_from": claim.valid_from.isoformat() if claim.valid_from else None,
            "valid_to": claim.valid_to.isoformat() if claim.valid_to else None,
            "superseded_by": claim.superseded_by,
            "source": {"source_type": claim.source_type, "source_id": claim.source_id},
            "evidence": evidence,
        }


def provenance_author(entity: Any) -> Optional[str]:
    return getattr(entity, "author_id", None) or getattr(entity, "owner_id", None)


def _load_provenance(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _load_aliases(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return []


canonical_engine = CanonicalEngine()