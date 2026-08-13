"""Slice 4E.1 + 4E.2 — canonical knowledge foundation & universal ingestion.

The universal ingestion contract for the Living Organizational Knowledge
Model. Every knowledge object and every meaningful piece of company activity
(internal today, external via 4N later) is normalized into one canonical
shape:

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

4E.2 adds the universal funnel: messages, tasks, meetings, memories and
patterns enter through the SAME contract via one ``ingest_event`` path that
reacts to the existing durable event bus — no new emission sites, no second
knowledge model, no independent subsystem.

Behavioral laws (mirroring 4D):

* event-driven: ingestion is triggered by existing durable events, never by
  nightly scans; re-ingesting the same content is a no-op (exact-once) and
  out-of-order replays are rejected by a monotonic ordering guard,
* meaningfulness: noise never becomes knowledge (short greetings, filler);
  opinions/proposals stay weaker claims than decisions/policies,
* governance-first: every read resolves caller access before retrieval and
  never fetches what the caller cannot see; sources inherit the governance
  scope of their origin (project anchor, conversation membership) and derived
  claims inherit it through their source,
* bounded: all reads and the on-demand reconcile cap candidate counts with
  hard SQL limits — no full-org scans,
* tenant-scoped: every query is anchored to the caller's organization_id.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
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
_ARCHIVED_STATUSES = frozenset({"archived", "deleted", "rejected", "cancelled"})
# lifecycle of the underlying object -> superseded (temporal truth preserved)
_SUPERSEDED_STATUSES = frozenset({"resolved", "faded"})

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

# 4E.2 — fixed authority per new source family.
_AUTHORITY_FIXED = {
    "message": 1,   # unverified statement / opinion / proposal
    "task": 2,      # team record
    "meeting": 2,   # team record
    "memory": 3,    # system-judged significant record
    "pattern": 3,   # system-derived insight
}
_AUTHORITY_FIXED_PATTERN = {
    "confirmed": 4,
    "persistent": 4,
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

# 4E.2 — event name -> canonical source family (single universal contract).
_EVENT_SOURCES: dict[str, str] = {
    "messaging.message_sent": "message",
    "task.created": "task",
    "task.updated": "task",
    "task.transitioned": "task",
    "task.blocked": "task",
    "task.completed": "task",
    "task.unblocked": "task",
    "task.deleted": "task",
    "meeting.created": "meeting",
    "meeting.updated": "meeting",
    "meeting.started": "meeting",
    "meeting.ended": "meeting",
    "meeting.completed": "meeting",
    "memory.recorded": "memory",
    "pattern.detected": "pattern",
    "pattern.updated": "pattern",
    "pattern.confirmed": "pattern",
}

# 4E.2 — all source families known to the canonical model (reconcile + reads).
SOURCE_FAMILIES = (
    "document", "wiki", "policy", "sop", "template", "decision",
    "message", "task", "meeting", "memory", "pattern",
)

# ---------------------------------------------------------------------------
# message meaningfulness boundary (deterministic, no LLM)
# ---------------------------------------------------------------------------

_MESSAGE_SIGNAL = re.compile(
    r"\b("
    r"moved|moving|delay|delayed|postpon|postponed|rescheduled|changed|changing|"
    r"decided|decide|approved|approved|rejected|blocked|blocking|unblocked|"
    r"launch|released|release|cancelled|cancel|broken|failing|failure|failed|"
    r"deadline|incident|urgent|risk|agreed|committed|rollout|rollout|migration|"
    r"deployment|deployed|deploy|contract|policy|sla|budget|revenue|signed|"
    r"onboard|hiring|frozen|freeze|extended|paused|restart|resume"
    r")\b",
    re.IGNORECASE,
)
_MESSAGE_NOISE = (
    "good morning", "good afternoon", "good evening", "good night",
    "hello everyone", "hi everyone", "hey everyone", "thanks", "thank you",
    "thank you all", "sounds good", "sounds great", "ok", "okay", "gm",
    "welcome", "welcome aboard", "lol", "haha", "+1", "congrats", "congratulations",
    "noted", "acknowledged", "well done", "great work", "nice", "thanks for sharing",
)


def _message_meaningful(content: Optional[str]) -> bool:
    """Noise never becomes knowledge; meaningful messages may."""
    text = (content or "").strip()
    if not text:
        return False
    if text.lower() in _MESSAGE_NOISE:
        return False
    if len(text) < 12:
        return False
    if _MESSAGE_SIGNAL.search(text):
        return True
    return len(text) >= 60


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _freshness(source_updated_at: Optional[datetime], now: Optional[datetime] = None) -> tuple[int, str]:
    """Age-based freshness model: very_high → high → medium → low → stale."""
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


def _source_hash(title: str, content: Optional[str], status: str, version: int) -> str:
    payload = "|".join(str(x) for x in (title, content or "", status, version))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def _claim_spec_for(kind: str, normalized: dict[str, Any]) -> tuple[str, str, str]:
    """4E.2 — canonical claim shape per source family."""
    title = (normalized.get("title") or "")[:180]
    status = normalized.get("status") or ""
    if kind == "message":
        content = (normalized.get("content") or "")[:240]
        return "statement", "stated", f"Message states: {content}"
    if kind == "task":
        return "status", "status", f"Task '{title}' — status={status}"
    if kind == "meeting":
        return "fact", "occurred", f"Meeting '{title}' — status={status}"
    if kind == "memory":
        mtype = normalized.get("category") or normalized.get("status") or "institutional"
        return "memory", "remembers", f"Memory: '{title}' (type={mtype}, importance={normalized.get('importance') or 'medium'})"
    if kind == "pattern":
        confidence = normalized.get("confidence")
        suffix = f", confidence={confidence}" if confidence is not None else ""
        key = f" — key={normalized.get('keywords')}" if normalized.get("keywords") else ""
        return "pattern", "signals", f"Pattern '{title}'{key} — status={status}{suffix}"
    return _claim_payload_kind_fallback(kind, title, status)


def _claim_payload_kind_fallback(kind: str, title: str, status: str) -> tuple[str, str, str]:
    return "fact", "states", f"{kind.capitalize()} '{title}' records status={status}"


# ---------------------------------------------------------------------------
# 4E.2 — per-family normalizers: any source speaks one internal language
# ---------------------------------------------------------------------------


async def _normalize_message(db: AsyncSession, organization_id: str, source_id: str) -> Optional[dict[str, Any]]:
    from app.models.communication import Message

    row = await db.get(Message, source_id)
    if row is None or row.organization_id != organization_id:
        return None
    return {
        "title": (row.content or row.id)[:240] or "untitled message",
        "content": row.content,
        "summary": None,
        "status": "sent",
        "version": 1,
        "source_updated": row.created_at or row.updated_at,
        "project_id": None,
        "department_id": None,
        "team_id": None,
        "category": None,
        "keywords": None,
        "author_id": row.sender_id,
        "conversation_id": row.conversation_id,
        "authority": _AUTHORITY_FIXED["message"],
        "meaningful": _message_meaningful(row.content),
    }


async def _normalize_task(db: AsyncSession, organization_id: str, source_id: str, event_status: Optional[str] = None) -> Optional[dict[str, Any]]:
    from app.models.task import Task

    row = await db.get(Task, source_id)
    if row is None or row.organization_id != organization_id:
        return None
    return {
        "title": (row.title or "")[:240] or "untitled task",
        "content": getattr(row, "description", None) or getattr(row, "notes", None),
        "summary": None,
        "status": (event_status or row.status or "todo"),
        "version": 1,
        "source_updated": row.updated_at or row.created_at,
        "project_id": row.project_id,
        "department_id": getattr(row, "department_id", None),
        "team_id": getattr(row, "team_id", None),
        "category": None,
        "keywords": None,
        "author_id": row.assignee_id or getattr(row, "reporter_id", None) or getattr(row, "creator_id", None),
        "conversation_id": None,
        "authority": _AUTHORITY_FIXED["task"],
        "meaningful": True,
    }


async def _normalize_meeting(db: AsyncSession, organization_id: str, source_id: str, event_status: Optional[str] = None) -> Optional[dict[str, Any]]:
    from app.models.meeting import Meeting

    row = await db.get(Meeting, source_id)
    if row is None or row.organization_id != organization_id:
        return None
    return {
        "title": (row.title or "")[:240] or "untitled meeting",
        "content": row.transcript_summary or row.ai_summary or row.description,
        "summary": None,
        "status": (row.status or event_status or "scheduled"),
        "version": 1,
        "source_updated": row.updated_at or row.created_at,
        "project_id": row.project_id,
        "department_id": row.department_id,
        "team_id": row.team_id,
        "category": None,
        "keywords": None,
        "author_id": row.organizer_id,
        "conversation_id": None,
        "authority": _AUTHORITY_FIXED["meeting"],
        "meaningful": True,
    }


async def _normalize_memory(db: AsyncSession, organization_id: str, source_id: str) -> Optional[dict[str, Any]]:
    from app.models.company_memory import CompanyMemory

    row = await db.get(CompanyMemory, source_id)
    if row is None or row.organization_id != organization_id:
        return None
    project_id = row.auth_project_id if row.auth_scope == "project" else None
    return {
        "title": (row.title or "")[:240] or "untitled memory",
        "content": row.content,
        "summary": None,
        "status": "active",
        "version": 1,
        "source_updated": row.updated_at or row.created_at,
        "project_id": project_id,
        "department_id": None,
        "team_id": None,
        "category": row.memory_type or row.memory_category or "institutional",
        "keywords": ",".join(row.tags or []) or None,
        "author_id": None,
        "conversation_id": None,
        "authority": _AUTHORITY_FIXED["memory"],
        "meaningful": True,
    }


async def _normalize_pattern(db: AsyncSession, organization_id: str, source_id: str, event_status: Optional[str] = None, confidence: Optional[float] = None) -> Optional[dict[str, Any]]:
    from app.models.intelligence import PatternDetection

    row = await db.get(PatternDetection, source_id)
    if row is None or row.organization_id != organization_id:
        return None
    project_id = getattr(row, "auth_project_id", None)
    authority = _AUTHORITY_FIXED["pattern"]
    status = event_status or (row.status or "candidate")
    authority = _AUTHORITY_FIXED_PATTERN.get(status, authority)
    return {
        "title": (row.title or "")[:240] or "untitled pattern",
        "content": row.description or row.detail,
        "summary": None,
        "status": status,
        "version": 1,
        "source_updated": row.updated_at or row.created_at,
        "project_id": project_id,
        "department_id": None,
        "team_id": None,
        "category": row.family or "execution",
        "keywords": row.key,
        "author_id": None,
        "conversation_id": None,
        "authority": authority,
        "confidence": confidence if confidence is not None else round(row.confidence, 3),
        "meaningful": True,
    }


_NORMALIZERS = {
    "message": _normalize_message,
    "task": _normalize_task,
    "meeting": _normalize_meeting,
    "memory": _normalize_memory,
    "pattern": _normalize_pattern,
}


class CanonicalEngine:
    """4E.1+4E.2 — canonical knowledge model: ingestion, lifecycle, reads."""

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
        return await self._ingest_normalized(
            db,
            organization_id=organization_id,
            source_type=entity_type,
            source_id=entity_id,
            title=getattr(entity, "title", "") or "untitled",
            content=getattr(entity, "content", None),
            summary=getattr(entity, "summary", None),
            status=getattr(entity, "status", "draft") or "draft",
            version=getattr(entity, "version", 1) or 1,
            source_updated=getattr(entity, "updated_at", None) or getattr(entity, "published_at", None),
            project_id=getattr(entity, "project_id", None),
            department_id=getattr(entity, "department_id", None),
            team_id=getattr(entity, "team_id", None),
            category=getattr(entity, "category", None),
            keywords=getattr(entity, "keywords", None),
            author_id=getattr(entity, "author_id", None) or getattr(entity, "owner_id", None),
            conversation_id=None,
            authority=_authority_for(entity),
            claim=(claim_type, predicate, object_text),
            meaningful=True,
            event_name=event_name,
        )

    async def ingest_event(self, db: AsyncSession, *, event: Any, payload: dict[str, Any]) -> dict[str, Any]:
        """4E.2 — universal ingestion from an existing durable event.

        One contract: message/task/meeting/memory/pattern events are
        normalized into the same canonical shape as knowledge objects.
        Out-of-order replays are rejected (monotonic ordering guard) and
        duplicate content is a no-op (exact-once).
        """
        organization_id = payload.get("organization_id") or event.organization_id
        source_type = _EVENT_SOURCES.get(event.name)
        if source_type is None:
            return {"status": "skipped", "reason": f"not a knowledge event: {event.name}"}

        occurred_at = ensure_aware(event.occurred_at)
        event_status: Optional[str] = None
        if source_type == "task":
            if event.name == "task.deleted":
                event_status = "deleted"
            elif event.name == "task.transitioned":
                event_status = payload.get("status") or payload.get("to")
            elif event.name == "task.blocked":
                event_status = "blocked"
            elif event.name == "task.completed":
                event_status = "completed"
            elif event.name == "task.unblocked":
                event_status = payload.get("status") or "todo"
            else:
                event_status = payload.get("status")
        elif source_type == "meeting":
            event_status = "completed" if event.name == "meeting.completed" else "ended" if event.name == "meeting.ended" else None
        elif source_type == "pattern":
            event_status = payload.get("status")

        source_id = (
            payload.get(f"{source_type}_id")
            or payload.get("entity_id")
            or payload.get("id")
        )
        if not source_id:
            return {"status": "skipped", "reason": "no source id in payload"}

        normalizer = _NORMALIZERS.get(source_type)
        if normalizer is None:
            return {"status": "skipped", "reason": f"no normalizer for {source_type}"}
        extra: dict[str, Any] = {}
        if source_type in ("task", "meeting", "pattern"):
            extra["event_status"] = event_status
        if source_type == "pattern":
            extra["confidence"] = payload.get("confidence")
        normalized = await normalizer(db, organization_id, source_id, **extra)
        if normalized is None:
            return {"status": "skipped", "reason": f"{source_type} not found"}

        claim_type, predicate, object_text = _claim_spec_for(source_type, normalized)
        return await self._ingest_normalized(
            db,
            organization_id=organization_id,
            source_type=source_type,
            source_id=source_id,
            title=normalized["title"],
            content=normalized.get("content"),
            summary=normalized.get("summary"),
            status=normalized["status"],
            version=normalized.get("version", 1) or 1,
            source_updated=normalized.get("source_updated"),
            project_id=normalized.get("project_id"),
            department_id=normalized.get("department_id"),
            team_id=normalized.get("team_id"),
            category=normalized.get("category"),
            keywords=normalized.get("keywords"),
            author_id=normalized.get("author_id"),
            conversation_id=normalized.get("conversation_id"),
            authority=normalized.get("authority"),
            confidence=normalized.get("confidence"),
            claim=(claim_type, predicate, object_text),
            meaningful=normalized.get("meaningful", True),
            occurred_at=occurred_at,
            event_name=event.name,
        )

    async def _ingest_normalized(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        source_type: str,
        source_id: str,
        title: str,
        content: Optional[str],
        summary: Optional[str],
        status: str,
        version: int,
        source_updated: Optional[datetime],
        project_id: Optional[str],
        department_id: Optional[str],
        team_id: Optional[str],
        category: Optional[str],
        keywords: Optional[str],
        author_id: Optional[str],
        conversation_id: Optional[str],
        authority: Optional[int],
        claim: Optional[tuple[str, str, str]] = None,
        meaningful: bool = True,
        confidence: Optional[float] = None,
        occurred_at: Optional[datetime] = None,
        event_name: Optional[str] = None,
    ) -> dict[str, Any]:
        if not meaningful:
            return {"status": "skipped", "reason": "noise"}

        content_sum = _source_hash(title, content, status, version)
        source_updated = ensure_aware(source_updated) if source_updated else None
        occurred_at = ensure_aware(occurred_at) if occurred_at else None
        now = now_utc()
        authority = authority or _AUTHORITY_FIXED.get(source_type, 1)

        source = (
            await db.execute(
                select(KnowledgeSource).where(
                    KnowledgeSource.organization_id == organization_id,
                    KnowledgeSource.source_type == source_type,
                    KnowledgeSource.source_id == source_id,
                )
            )
        ).scalar_one_or_none()

        provenance = {
            "kind": source_type,
            "author_id": author_id,
            "category": category,
            "keywords": keywords,
            "project_id": project_id,
            "department_id": department_id,
            "team_id": team_id,
            "conversation_id": conversation_id,
            "last_event": event_name,
        }

        if source is not None and occurred_at is not None:
            latest = _load_provenance(source.provenance_json).get("latest_occurred_at")
            if latest:
                try:
                    if occurred_at < ensure_aware(datetime.fromisoformat(latest)):
                        return {"status": "skipped", "reason": "stale_replay"}
                except (TypeError, ValueError):
                    pass
            provenance["latest_occurred_at"] = occurred_at.isoformat()

        changed = source is None or source.content_hash != content_sum or source.version != version
        score, label = _freshness(source_updated)

        if source is None:
            lifecycle = "validated" if authority >= 3 else "active"
            source = KnowledgeSource(
                organization_id=organization_id,
                source_type=source_type,
                source_id=source_id,
                kind="internal",
                title=title,
                content_hash=content_sum,
                version=version,
                lifecycle=lifecycle,
                source_status=status,
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
            if status in _ARCHIVED_STATUSES:
                lifecycle = "archived"
            elif status in _SUPERSEDED_STATUSES:
                lifecycle = "superseded"
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
            source.source_status = status
            source.authority_level = authority
            source.freshness_score = score
            source.freshness_label = label
            source.last_verified_at = now
            source.source_updated_at = source_updated
            source.provenance_json = json.dumps(provenance, default=str)
            source.synced_at = now

        if changed:
            await self._sync_claims(
                db, organization_id=organization_id,
                source_type=source_type, source_id=source_id,
                source_status=status,
                claim=claim or _claim_spec_for(source_type, {
                    "title": title, "content": content, "status": status, "importance": None,
                }),
                authority=authority,
                confidence=confidence,
                context=(project_id, department_id, team_id),
                valid_from=occurred_at or source_updated or now,
                created_by=author_id,
            )
        await self._sync_topics(
            db, organization_id=organization_id,
            entity_type=source_type, entity_id=source_id,
            category=category, keywords=keywords,
            author_id=author_id,
        )
        await db.flush()
        return {"status": "ok", "entity_type": source_type, "entity_id": source_id, "lifecycle": source.lifecycle}

    async def _sync_claims(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        source_type: str,
        source_id: str,
        source_status: str,
        claim: tuple[str, str, str],
        authority: int,
        confidence: Optional[float],
        context: tuple[Optional[str], Optional[str], Optional[str]],
        valid_from: datetime,
        created_by: Optional[str],
    ) -> None:
        """Supersede the previous claims for this source, never delete them."""
        claim_type, predicate, object_text = claim
        project_id, department_id, team_id = context
        context_type, context_id = None, None
        for value, ctx_type in ((project_id, "project"), (department_id, "department"), (team_id, "team")):
            if value:
                context_type, context_id = ctx_type, value
                break
        claim_status = _claim_state(authority)
        row = KnowledgeClaim(
            organization_id=organization_id,
            subject_type=source_type,
            subject_id=source_id,
            predicate=predicate,
            object_text=object_text,
            claim_type=claim_type,
            status=claim_status,
            authority_level=authority,
            confidence=min(1.0, (confidence if confidence is not None else 0.5 + 0.1 * authority)),
            context_type=context_type,
            context_id=context_id,
            valid_from=ensure_aware(valid_from),
            source_type=source_type,
            source_id=source_id,
            created_by=created_by,
        )
        db.add(row)
        await db.flush()
        db.add(
            KnowledgeEvidence(
                organization_id=organization_id,
                claim_id=row.id,
                source_type=source_type,
                source_id=source_id,
                excerpt=(object_text or "")[:400] or None,
                role="primary",
                confidence=1.0,
            )
        )
        open_claims = (
            await db.execute(
                select(KnowledgeClaim).where(
                    KnowledgeClaim.organization_id == organization_id,
                    KnowledgeClaim.subject_type == source_type,
                    KnowledgeClaim.subject_id == source_id,
                    KnowledgeClaim.status != "superseded",
                )
            )
        ).scalars().all()
        for old in open_claims:
            if old.id == row.id:
                continue
            old.status = "superseded"
            old.valid_to = ensure_aware(valid_from)
            old.superseded_by = row.id

    async def _sync_topics(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_type: Optional[str],
        entity_id: Optional[str],
        category: Optional[str],
        keywords: Optional[str],
        author_id: Optional[str],
    ) -> None:
        """Seed the canonical topic registry from category + keywords (bounded)."""
        names: list[str] = []
        if category:
            names.append(str(category).strip()[:120])
        if keywords:
            for piece in str(keywords).split(","):
                piece = piece.strip()[:120]
                if piece:
                    names.append(piece)
        for name in names[:3]:
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
                        created_by=author_id,
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
        """Bounded on-demand resync across every source family (hard cap).

        Never a full-org scan — this exists only for recovery after schema
        changes or manual corrections; normal flow is event-driven.
        """
        limit = max(1, min(limit, _MAX_RECONCILE))
        kinds = [kind] if kind in SOURCE_FAMILIES else list(SOURCE_FAMILIES)
        processed: list[dict[str, Any]] = []
        remaining = limit
        for entity_kind in kinds:
            if remaining <= 0:
                break
            model = self._model_for(entity_kind)
            if model is None:
                continue
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
                result = await self.ingest_recovered(
                    db, organization_id=organization_id,
                    entity_type=entity_kind, entity_id=entity_id,
                )
                if result.get("status") == "ok":
                    processed.append(
                        {"entity_type": entity_kind, "entity_id": entity_id, "lifecycle": result.get("lifecycle")}
                    )
            remaining -= len(ids)
        await db.flush()
        return {"processed": len(processed), "items": processed, "limit": limit}

    @staticmethod
    def _model_for(entity_type: str) -> Optional[Any]:
        if entity_type in kb.KIND_MODELS:
            return kb.KIND_MODELS[entity_type]
        lazy = {
            "message": ("app.models.communication", "Message"),
            "task": ("app.models.task", "Task"),
            "meeting": ("app.models.meeting", "Meeting"),
            "memory": ("app.models.company_memory", "CompanyMemory"),
            "pattern": ("app.models.intelligence", "PatternDetection"),
        }
        entry = lazy.get(entity_type)
        if not entry:
            return None
        module_name, class_name = entry
        import importlib

        return getattr(importlib.import_module(module_name), class_name)

    async def ingest_recovered(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_type: str,
        entity_id: str,
    ) -> dict[str, Any]:
        """Recovery path: rebuild the canonical row for one source by loading
        the origin object — never a scan."""
        if entity_type in kb.KIND_MODELS:
            return await self.ingest(
                db, organization_id=organization_id,
                entity_type=entity_type, entity_id=entity_id,
                event_name="reconcile.on_demand",
            )
        normalizer = _NORMALIZERS.get(entity_type)
        if normalizer is None:
            return {"status": "skipped", "reason": f"unsupported kind: {entity_type}"}
        normalized = await normalizer(db, organization_id, entity_id)
        if normalized is None:
            return {"status": "skipped", "reason": f"{entity_type} not found"}
        claim_type, predicate, object_text = _claim_spec_for(entity_type, normalized)
        return await self._ingest_normalized(
            db,
            organization_id=organization_id,
            source_type=entity_type,
            source_id=entity_id,
            title=normalized["title"],
            content=normalized.get("content"),
            summary=normalized.get("summary"),
            status=normalized["status"],
            version=normalized.get("version", 1) or 1,
            source_updated=normalized.get("source_updated"),
            project_id=normalized.get("project_id"),
            department_id=normalized.get("department_id"),
            team_id=normalized.get("team_id"),
            category=normalized.get("category"),
            keywords=normalized.get("keywords"),
            author_id=normalized.get("author_id"),
            conversation_id=normalized.get("conversation_id"),
            authority=normalized.get("authority"),
            confidence=normalized.get("confidence"),
            claim=(claim_type, predicate, object_text),
            meaningful=normalized.get("meaningful", True),
            event_name="reconcile.on_demand",
        )

    # ------------------------------------------------------------- governed reads

    async def _access(self, db: AsyncSession, *, organization_id: str, user: Any):
        return await resolve_caller_access(db, organization_id=organization_id, user=user)

    @staticmethod
    def _visible(access: Any, provenance: Optional[dict[str, Any]]) -> bool:
        if access.org_wide:
            return True
        project_id = (provenance or {}).get("project_id")
        if project_id and project_id in access.project_ids:
            return True
        conversation_id = (provenance or {}).get("conversation_id")
        if conversation_id and conversation_id in access.member_conversation_ids:
            return True
        return False

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
        if source_type not in SOURCE_FAMILIES:
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
            "conversation_id": provenance.get("conversation_id"),
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