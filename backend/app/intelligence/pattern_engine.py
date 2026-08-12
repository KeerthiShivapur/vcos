"""Slice 4D.4 — canonical organizational pattern intelligence engine.

Change-driven detection lives in ``pattern_pipeline``; this module is the
read facade. It exposes:

- the legacy Phase 9 surface (``list_patterns`` / ``set_status`` / ``scan``),
  now lifecycle-aware and change-driven (``scan`` drains pending evaluation
  jobs — it never rescans the organization),
- the canonical governance-scoped surface used by ``/brain/patterns``:
  caller -> user -> organization -> roles -> governance scopes -> accessible
  entities -> patterns -> evidence. A pattern whose evidence is restricted is
  hidden entirely (never 403-leaked); employee-anchored patterns are only
  visible to organization-wide callers.

The engine never writes operating entities — it only reads them and updates
pattern/intelligence tables.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence import pattern_pipeline
from app.intelligence.pattern_types import (
    PATTERN_TYPES,
    confidence_label,
    rule_for,
)
from app.models.intelligence import (
    ACTIVE_PATTERN_STATUSES,
    LEGACY_PATTERN_STATUSES,
    PatternDetection,
)

logger = logging.getLogger("vcos.intelligence.pattern")

_PRESENT_KEYS = (
    "id", "pattern_type", "pattern_key", "family", "title", "description",
    "detail", "status", "count", "confidence", "confidence_label",
    "first_seen", "last_seen", "time_window_days", "scope_id", "scope_type",
    "entities", "supporting_memory_ids", "supporting_event_ids",
    "supporting_relationships", "trend", "avg_interval_days",
    "created_at", "updated_at",
)


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _present(pattern: PatternDetection) -> dict[str, Any]:
    """Canonical pattern representation (always evidence-backed)."""
    return {
        "id": pattern.id,
        "pattern_type": pattern.pattern_type,
        "pattern_key": pattern.key,
        "family": pattern.family,
        "title": pattern.title,
        "description": pattern.description,
        "detail": pattern.detail,
        "status": pattern.status,
        "count": pattern.count,
        "occurrence_count": pattern.count,
        "confidence": round(pattern.confidence or 0.0, 3),
        "confidence_label": confidence_label(pattern.confidence or 0.0),
        "first_seen": _iso(pattern.first_seen),
        "last_seen": _iso(pattern.last_seen),
        "time_window_days": pattern.time_window_days,
        "scope_id": pattern.scope_id,
        "scope_type": pattern.scope_type,
        "auth_project_id": pattern.auth_project_id,
        "entities": pattern.entities_json or [],
        "supporting_memory_ids": pattern.supporting_memory_ids or [],
        "supporting_event_ids": pattern.supporting_event_ids or [],
        "supporting_relationships": pattern.supporting_relationships or [],
        "trend": pattern.trend,
        "avg_interval_days": pattern.avg_interval_days,
        "created_at": _iso(pattern.created_at),
        "updated_at": _iso(pattern.updated_at),
    }


def _status_filter(status: Optional[str]):
    """Legacy-compatible status semantics: "open" means any active lifecycle."""
    if not status or status == "open":
        return PatternDetection.status.in_(ACTIVE_PATTERN_STATUSES)
    if status in LEGACY_PATTERN_STATUSES or status in ACTIVE_PATTERN_STATUSES:
        return PatternDetection.status == status
    return PatternDetection.status == status


def _is_observable(pattern: PatternDetection) -> bool:
    """A pattern is observable only once it passed its rule's minimum
    occurrence threshold — one event is never a pattern."""
    rule = rule_for(pattern.pattern_type)
    minimum = (rule or {}).get("min_occurrences", 2)
    return (pattern.count or 0) >= minimum


class PatternEngine:
    # ------------------------------------------------------------------ writes
    async def scan(
        self, db: AsyncSession, *, organization_id: Optional[str] = None, limit: int = 50
    ) -> int:
        """Drain pending pattern evaluation work (change-driven, bounded).

        Processes queued ``pattern.evaluate`` jobs for the organization (or
        all organizations), adopts orphan significant events, and ages stale
        patterns. This is the only "scan" left in the system — it processes
        already-enqueued changes and never rescans operating tables.
        """
        from app.workers.pattern_worker import run_once as worker_run

        processed = await worker_run(db, limit=limit, organization_id=organization_id)
        return processed

    async def set_status(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        pattern_id: str,
        status: str,
    ) -> Optional[dict[str, Any]]:
        """Human status update (acknowledge / dismiss / lifecycle override)."""
        row = await db.get(PatternDetection, pattern_id)
        if row is None or row.organization_id != organization_id:
            return None
        row.status = status
        row.last_evaluated_at = pattern_pipeline._now()
        await pattern_pipeline._refresh_insight(db, organization_id, row, f"pattern.status:{status}")
        await pattern_pipeline._emit_pattern_event(db, organization_id, "pattern.updated", row)
        await db.flush()
        return {"id": row.id, "status": row.status}

    # ------------------------------------------------------------ legacy reads
    async def list_patterns(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        limit: int = 50,
        pattern_type: Optional[str] = None,
        status: Optional[str] = "open",
    ) -> list[dict[str, Any]]:
        filters = [PatternDetection.organization_id == organization_id, _status_filter(status)]
        if pattern_type:
            filters.append(PatternDetection.pattern_type == pattern_type)
        rows = (
            await db.execute(
                select(PatternDetection)
                .where(*filters)
                .order_by(PatternDetection.count.desc(), PatternDetection.last_seen.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [_present(row) for row in rows if _is_observable(row)]

    # -------------------------------------------------------- governance reads
    async def list_visible(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        limit: int = 50,
        pattern_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict[str, Any]:
        """Canonical /brain/patterns list: governance-scoped, evidence-backed.

        Caller -> user -> organization -> roles -> scopes -> accessible
        patterns. Scoped callers see exactly the patterns anchored inside
        their visible scope subtree; employee-anchored patterns are
        organization-wide only; observation buffers (count below the rule's
        minimum) are never surfaced.
        """
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        filters = [PatternDetection.organization_id == organization_id, _status_filter(status)]
        if pattern_type:
            filters.append(PatternDetection.pattern_type == pattern_type)
        rows = (
            await db.execute(
                select(PatternDetection)
                .where(*filters)
                .order_by(PatternDetection.count.desc(), PatternDetection.last_seen.desc())
                .limit(min(limit, 200))
            )
        ).scalars().all()
        visible: list[dict[str, Any]] = []
        truncated = False
        for row in rows:
            if not _is_observable(row):
                continue
            if not _visible_to(access, row):
                continue
            visible.append(_present(row))
            if len(visible) >= limit:
                truncated = True
                break
        return {
            "patterns": visible,
            "limit": limit,
            "truncated": truncated,
            "org_wide": access.org_wide,
        }

    async def get_visible(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        pattern_id: str,
    ) -> Optional[dict[str, Any]]:
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        row = await db.get(PatternDetection, pattern_id)
        if row is None or row.organization_id != organization_id:
            return None
        if not _is_observable(row) or not _visible_to(access, row):
            return None
        return _present(row)

    async def evidence_visible(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        pattern_id: str,
    ) -> Optional[dict[str, Any]]:
        """Why VCOS believes this pattern — resolved evidence refs.

        Every item references a real VCOS object the caller may access.
        Restricted evidence is dropped; if the pattern's evidence is entirely
        restricted the pattern itself is hidden (never leaked).
        """
        from app.intelligence.company_context import resolve_accessible_ids, resolve_caller_access

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        row = await db.get(PatternDetection, pattern_id)
        if row is None or row.organization_id != organization_id:
            return None
        if not _is_observable(row) or not _visible_to(access, row):
            return None

        entity_evidence = [
            item for item in (row.evidence_json or []) if item.get("type") != "event"
        ]
        event_ids = [item["id"] for item in (row.evidence_json or []) if item.get("type") == "event"]
        events = (
            await db.execute(
                select(pattern_pipeline.EventRow).where(
                    pattern_pipeline.EventRow.organization_id == organization_id,
                    pattern_pipeline.EventRow.id.in_(event_ids[-40:]),
                )
            )
        ).scalars().all() if event_ids else []
        event_map = {e.id: e for e in events}

        evidence: list[dict[str, Any]] = []
        for item in entity_evidence:
            etype, eid = item.get("type"), item.get("id")
            if not etype or not eid:
                continue
            accessible = await resolve_accessible_ids(
                db, user, organization_id=organization_id, kind=etype, ids=[eid]
            )
            if not accessible:
                continue
            evidence.append(
                {
                    "type": etype,
                    "id": eid,
                    "title": item.get("title") or eid,
                    "relationship": item.get("relationship") or "entity",
                }
            )
        for event_id in event_ids[-20:]:
            event = event_map.get(event_id)
            if event is None:
                continue
            evidence.append(
                {
                    "type": "event",
                    "id": event.id,
                    "title": event.name,
                    "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
                    "relationship": "occurrence",
                }
            )

        memories: list[dict[str, Any]] = []
        memory_ids = (row.supporting_memory_ids or [])[:20]
        if memory_ids:
            memory_rows = (
                await db.execute(
                    select(pattern_pipeline.CompanyMemory)
                    .where(
                        pattern_pipeline.CompanyMemory.organization_id == organization_id,
                        pattern_pipeline.CompanyMemory.id.in_(memory_ids),
                    )
                ).scalars().all()
            )
            for memory in memory_rows:
                if not access.org_wide and (
                    memory.auth_scope == "project"
                    and (memory.auth_project_id is None or memory.auth_project_id not in access.project_ids)
                ):
                    continue
                memories.append(
                    {
                        "id": memory.id,
                        "title": memory.title,
                        "memory_category": memory.memory_category,
                        "fact_kind": memory.fact_kind,
                        "confidence": memory.confidence,
                        "url": f"/brain/memory/{memory.id}",
                    }
                )

        return {
            "pattern_id": row.id,
            "pattern_type": row.pattern_type,
            "evidence": evidence,
            "supporting_memories": memories,
            "relationships": (row.supporting_relationships or [])[:20],
            "entities": row.entities_json or [],
            "source_events": row.supporting_event_ids or [],
        }

    async def history_visible(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        pattern_id: str,
        limit: int = 50,
    ) -> Optional[dict[str, Any]]:
        """Occurrence timeline: when the pattern was observed, from its events."""
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        row = await db.get(PatternDetection, pattern_id)
        if row is None or row.organization_id != organization_id:
            return None
        if not _is_observable(row) or not _visible_to(access, row):
            return None
        event_ids = (row.supporting_event_ids or [])[-40:]
        events = (
            await db.execute(
                select(pattern_pipeline.EventRow).where(
                    pattern_pipeline.EventRow.organization_id == organization_id,
                    pattern_pipeline.EventRow.id.in_(event_ids),
                )
            )
        ).scalars().all() if event_ids else []
        history = sorted(
            (
                {
                    "event_id": e.id,
                    "event_name": e.name,
                    "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                }
                for e in events
            ),
            key=lambda item: item["occurred_at"] or "",
            reverse=True,
        )
        return {
            "pattern_id": row.id,
            "history": history[:limit],
            "first_seen": _iso(row.first_seen),
            "last_seen": _iso(row.last_seen),
            "occurrence_count": row.count,
        }

    async def related_visible(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        pattern_id: str,
        limit: int = 10,
    ) -> Optional[dict[str, Any]]:
        """Related patterns: same family/anchor, or sharing evidence entities."""
        from app.intelligence.company_context import resolve_caller_access

        access = await resolve_caller_access(db, organization_id=organization_id, user=user)
        row = await db.get(PatternDetection, pattern_id)
        if row is None or row.organization_id != organization_id:
            return None
        if not _is_observable(row) or not _visible_to(access, row):
            return None
        entity_ids = {e.get("id") for e in (row.entities_json or []) if e.get("id")}
        same_anchor = entity_ids
        rows = (
            await db.execute(
                select(PatternDetection).where(
                    PatternDetection.organization_id == organization_id,
                    PatternDetection.id != row.id,
                    PatternDetection.status.in_(ACTIVE_PATTERN_STATUSES),
                )
                .order_by(PatternDetection.count.desc())
                .limit(100)
            )
        ).scalars().all()
        related: list[dict[str, Any]] = []
        for candidate in rows:
            if not _is_observable(candidate) or not _visible_to(access, candidate):
                continue
            candidate_ids = {e.get("id") for e in (candidate.entities_json or []) if e.get("id")}
            same_family = candidate.family == row.family
            shares_anchor = bool(same_anchor & candidate_ids)
            if same_family or shares_anchor:
                presented = _present(candidate)
                presented["relation"] = (
                    "shares_anchor" if shares_anchor else "same_family"
                )
                related.append(presented)
                if len(related) >= limit:
                    break
        return {"pattern_id": row.id, "related": related}


def _visible_to(access: Any, pattern: PatternDetection) -> bool:
    """Downward-only governance visibility for one pattern."""
    if access.org_wide:
        return True
    if pattern.scope_type == "project" and pattern.scope_id:
        return pattern.scope_id in access.visible_scope_ids
    # Organization-wide patterns (including employee-anchored ones) are only
    # visible to organization-wide callers — scoped callers see exactly their
    # scope subtree, never more.
    return False


pattern_engine = PatternEngine()
