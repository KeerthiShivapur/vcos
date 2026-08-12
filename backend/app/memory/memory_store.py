"""Slice 4D.3 — governance-scoped memory reads (feed, search, timeline).

The canonical read surface for organizational memory. Every read resolves the
caller's governance access (``resolve_caller_access``, Slice 4C) and applies
the same visibility law as the Slice 4D.2 knowledge layer:

- organization-wide callers see organization-wide memories and every
  project-scoped memory;
- scoped callers see only memories whose ``auth_scope`` is ``project`` and
  whose ``auth_project_id`` is inside their visible projects.

Downward-only, never upward: a project-scoped caller cannot see memories
formed from organization-wide evidence, and memory metadata is never leaked —
a hidden memory is absent from feed, search, timeline, related and evidence
resolutions alike.

All reads are bounded: indexed queries with hard caps, semantic top-K scoring
in Python over a bounded candidate set (no full scans).
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.company_context import resolve_caller_access
from app.models.company_memory import CompanyMemory, MemoryEvent, MemoryOutcome

logger = logging.getLogger("vcos.memory.store")

_FEED_CANDIDATES = 300
_SEARCH_CANDIDATES = 300
_SEARCH_FLOOR = 0.25
_RELATED_CANDIDATES = 100
_MAX_LIMIT = 100

_EVIDENCE_URLS = {
    "task": "/tasks/{id}",
    "project": "/projects/{id}",
    "decision": "/decisions/{id}",
    "document": "/documents/{id}",
    "wiki": "/wiki/{id}",
    "policy": "/policies/{id}",
    "sop": "/sops/{id}",
    "template": "/templates/{id}",
    "employee": "/people/{id}",
    "approval": "/approvals/{id}",
    "milestone": "/milestones/{id}",
    "ticket": "/support/{id}",
    "customer": "/customers/{id}",
    "dependency": "/tasks/{id}",
}


def serialize(memory: CompanyMemory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "memory_type": memory.memory_type,
        "memory_category": memory.memory_category,
        "domain": memory.domain,
        "title": memory.title,
        "summary": memory.summary,
        "content": memory.content,
        "lesson": memory.lesson,
        "outcome": memory.outcome,
        "outcome_type": memory.outcome_type,
        "confidence": memory.confidence,
        "fact_kind": memory.fact_kind,
        "importance": memory.importance,
        "entity_type": memory.entity_type,
        "entity_id": memory.entity_id,
        "occurred_at": memory.occurred_at.isoformat() if memory.occurred_at else None,
        "auth_scope": memory.auth_scope,
        "auth_project_id": memory.auth_project_id,
        "status": memory.status,
        "supersedes_id": memory.supersedes_id,
        "source_event_ids": memory.source_event_ids or [],
        "related_memory_ids": memory.related_memory_ids or [],
        "evidence": memory.evidence_json or [],
        "context": memory.context_json or {},
        "source_event": memory.source_event,
        "tags": memory.tags or [],
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
    }


def _visible(access: Any, memory: CompanyMemory) -> bool:
    if access.org_wide:
        return True
    if memory.auth_scope != "project" or not memory.auth_project_id:
        return False
    return memory.auth_project_id in access.project_ids


async def _load_memories(
    db: AsyncSession,
    *,
    organization_id: str,
    access: Any,
    status: str,
    categories: Optional[tuple[str, ...]],
    limit: int,
    candidates: int = _FEED_CANDIDATES,
    exclude_ids: Optional[set[str]] = None,
) -> list[CompanyMemory]:
    stmt = (
        select(CompanyMemory)
        .where(CompanyMemory.organization_id == organization_id)
        .order_by(CompanyMemory.occurred_at.desc())
        .limit(candidates)
    )
    if status:
        stmt = stmt.where(CompanyMemory.status == status)
    if categories:
        stmt = stmt.where(CompanyMemory.memory_category.in_(categories))
    rows = (await db.execute(stmt)).scalars().all()
    visible: list[CompanyMemory] = []
    for row in rows:
        if not _visible(access, row):
            continue
        if exclude_ids and row.id in exclude_ids:
            continue
        visible.append(row)
        if len(visible) >= limit:
            break
    return visible


async def feed(
    db: AsyncSession,
    *,
    organization_id: str,
    user: Any,
    memory_category: Optional[str] = None,
    status: str = "active",
    limit: int = 50,
) -> dict[str, Any]:
    """Most recent memories the caller can see (memory feed)."""
    access = await resolve_caller_access(db, organization_id=organization_id, user=user)
    limit = max(1, min(limit, _MAX_LIMIT))
    categories = (memory_category,) if memory_category else None
    rows = await _load_memories(
        db,
        organization_id=organization_id,
        access=access,
        status=status,
        categories=categories,
        limit=limit,
    )
    return {"memories": [serialize(row) for row in rows]}


async def get(
    db: AsyncSession,
    *,
    organization_id: str,
    user: Any,
    memory_id: str,
) -> Optional[dict[str, Any]]:
    """One memory, governance-filtered. None when hidden or absent."""
    access = await resolve_caller_access(db, organization_id=organization_id, user=user)
    memory = await db.get(CompanyMemory, memory_id)
    if memory is None or memory.organization_id != organization_id:
        return None
    if not _visible(access, memory):
        return None
    return serialize(memory)


async def search(
    db: AsyncSession,
    *,
    organization_id: str,
    user: Any,
    query: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Semantic historical retrieval over memories the caller can see.

    Deterministic embeddings (Slice 4D.2 provider) score a bounded candidate
    set of experience/lesson/outcome memories; scope filtering happens before
    retrieval. Explicit scores are returned so callers can see the signal.
    """
    access = await resolve_caller_access(db, organization_id=organization_id, user=user)
    limit = max(1, min(limit, _MAX_LIMIT))
    from app.knowledge.embeddings import get_embedding_provider

    provider = get_embedding_provider()
    rows = await _load_memories(
        db,
        organization_id=organization_id,
        access=access,
        status="active",
        categories=("experience", "lesson", "outcome"),
        limit=_SEARCH_CANDIDATES,
        candidates=_SEARCH_CANDIDATES,
    )
    if not query.strip():
        return {"memories": [serialize(row) for row in rows[:limit]], "matched": len(rows[:limit])}

    query_vec = (await provider.embed_many([query]))[0]
    scored: list[tuple[float, CompanyMemory]] = []
    for row in rows:
        text = " ".join(part for part in (row.title, row.summary or "", row.lesson or "") if part)
        vec = (await provider.embed_many([text]))[0]
        sim = provider.cosine(query_vec, vec)
        if sim < _SEARCH_FLOOR:
            continue
        # confidence is a secondary signal: evidence-backed memories rank above
        # equally similar inferences.
        score = 0.8 * sim + 0.2 * (row.confidence or 0.0)
        scored.append((score, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[:limit]
    return {
        "memories": [serialize(row) for row in [pair[1] for pair in top]],
        "matched": len(top),
    }


async def timeline(
    db: AsyncSession,
    *,
    organization_id: str,
    user: Any,
    limit: int = 50,
) -> dict[str, Any]:
    """Episode-style company history: memories with their forming events."""
    access = await resolve_caller_access(db, organization_id=organization_id, user=user)
    limit = max(1, min(limit, _MAX_LIMIT))
    rows = await _load_memories(
        db,
        organization_id=organization_id,
        access=access,
        status="active",
        categories=None,
        limit=limit,
    )
    memory_ids = [row.id for row in rows]
    links: dict[str, list[str]] = {}
    if memory_ids:
        link_rows = (
            await db.execute(
                select(MemoryEvent).where(MemoryEvent.memory_id.in_(memory_ids))
            )
        ).scalars().all()
        for link in link_rows:
            links.setdefault(link.memory_id, []).append(link.event_id)
    episodes = []
    for row in rows:
        item = serialize(row)
        item["episode_events"] = links.get(row.id, [])
        episodes.append(item)
    return {"episodes": episodes}


async def evidence(
    db: AsyncSession,
    *,
    organization_id: str,
    user: Any,
    memory_id: str,
) -> Optional[dict[str, Any]]:
    """Resolve a memory's evidence refs into titles/urls — why VCOS believes it."""
    memory = await get(db, organization_id=organization_id, user=user, memory_id=memory_id)
    if memory is None:
        return None
    resolved: list[dict[str, Any]] = []
    for item in memory.get("evidence") or []:
        ref_type = item.get("type", "")
        ref_id = item.get("id")
        resolved.append(
            {
                **item,
                **await _resolve_evidence_ref(db, organization_id, ref_type, ref_id),
            }
        )
    return {"memory": memory, "evidence": resolved}


async def _resolve_evidence_ref(
    db: AsyncSession, organization_id: str, ref_type: str, ref_id: Optional[str]
) -> dict[str, Any]:
    if not ref_id:
        return {"title": "", "url": "", "resolved": False}
    template = _EVIDENCE_URLS.get(ref_type, "")
    url = template.format(id=ref_id) if template else ""
    if ref_type == "event":
        from app.events.event_models import describe
        from app.models.notification import Event as EventRow

        event = await db.get(EventRow, ref_id)
        if event is None:
            return {"title": "", "url": "", "resolved": False}
        return {
            "title": describe(event.name) if event.name else event.name,
            "url": "",
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "resolved": True,
        }
    from app.models.employee import Employee
    from app.models.knowledge import Decision
    from app.models.project import Project
    from app.models.task import Task

    model = {
        "task": Task,
        "project": Project,
        "decision": Decision,
        "employee": Employee,
    }.get(ref_type)
    if model is not None:
        row = await db.get(model, ref_id)
        if row is not None and row.organization_id == organization_id:
            label = getattr(row, "title", None) or getattr(row, "name", None) or ""
            return {"title": label, "url": url, "resolved": True}
    # dependency + fallback: ref is resolvable by id alone
    if ref_type in ("dependency",):
        from app.models.task import TaskDependency

        row = await db.get(TaskDependency, ref_id)
        if row is not None:
            return {"title": f"dependency {ref_id[:8]}", "url": "", "resolved": True}
    return {"title": "", "url": url, "resolved": False}


async def related(
    db: AsyncSession,
    *,
    organization_id: str,
    user: Any,
    memory_id: str,
) -> Optional[dict[str, Any]]:
    """Memories semantically linked to this one (governance-filtered)."""
    memory = await get(db, organization_id=organization_id, user=user, memory_id=memory_id)
    if memory is None:
        return None
    ids = [item for item in (memory.get("related_memory_ids") or [])]
    results: list[dict[str, Any]] = []
    if ids:
        rows = (
            await db.execute(
                select(CompanyMemory).where(
                    CompanyMemory.organization_id == organization_id,
                    CompanyMemory.id.in_(ids),
                    CompanyMemory.status == "active",
                )
            )
        ).scalars().all()
        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        for row in rows:
            if _visible(access, row):
                results.append(serialize(row))
    return {"memory": memory, "related": results}


async def record_outcome(
    db: AsyncSession,
    *,
    organization_id: str,
    user: Any,
    memory_id: str,
    entity_type: Optional[str],
    entity_id: Optional[str],
    outcome_type: str,
    outcome: Optional[str],
) -> Optional[dict[str, Any]]:
    """Manually attach an observed outcome to a memory (outcome feedback loop).

    The memory layer only records the observation — it never changes any
    operating entity. Outcomes are bounded and traceable in ``memory_outcomes``.
    """
    memory = await get(db, organization_id=organization_id, user=user, memory_id=memory_id)
    if memory is None:
        return None
    row = await db.get(CompanyMemory, memory_id)
    # Monotonic outcome progression: an observation may upgrade the recorded
    # outcome, never downgrade it. History is kept in memory_outcomes either way.
    _OUTCOME_RANK = {"unresolved": 0, "negative": 1, "partial": 2, "positive": 3}
    if _OUTCOME_RANK.get(outcome_type, 0) > _OUTCOME_RANK.get(row.outcome_type or "", 0):
        row.outcome = outcome
        row.outcome_type = outcome_type
        row.confidence = min(0.95, row.confidence + 0.05)
    db.add(
        MemoryOutcome(
            organization_id=organization_id,
            memory_id=memory_id,
            applied_entity_type=entity_type or row.entity_type,
            applied_entity_id=entity_id or row.entity_id,
            outcome_type=outcome_type,
            outcome=outcome,
            evidence_json=[{"type": "user", "id": user.id, "relationship": "observed"}],
            occurred_at=row.occurred_at,
        )
    )
    await db.flush()
    return serialize(row)
