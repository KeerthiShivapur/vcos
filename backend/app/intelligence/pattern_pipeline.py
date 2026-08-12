"""Slice 4D.4 — universal organizational pattern intelligence pipeline.

Change-driven, evidence-backed pattern detection on top of the canonical
4A/4B/4C/4D.1-4D.3 foundations:

    event -> BackgroundJob (pattern.evaluate) -> bounded context collection
           -> candidate update -> evidence lineage -> confidence/lifecycle
           -> pattern.* event -> CompanyInsight freshness

Design laws (mirroring Slice 4D.3 memory formation):

- **Change-driven, never scanned**: a significant event enqueues exactly one
  ``pattern.evaluate`` job (idempotent under the ``(name, event_id)`` job
  uniqueness). There is no organization-wide rescan and no per-employee /
  per-message full scan. Fade/resolve maintenance is a bounded, indexed sweep
  over recently-active patterns only.
- **One event is never a pattern**: pattern rows start as hidden observation
  buffers (count = 1); the read surface only exposes patterns whose
  occurrence count meets their rule's ``min_occurrences`` threshold.
- **Observational only**: the pipeline reads operating-layer tables and writes
  pattern / insight tables. It never mutates tasks, projects, decisions,
  messages, approvals, permissions or governance scopes.
- **Evidence lineage**: every occurrence links its source event through
  ``PatternEvent`` (replay-safe, exactly-once) and the pattern carries
  ``evidence_json`` / ``supporting_event_ids`` / ``entities_json`` — real VCOS
  objects, so a pattern can always answer *why VCOS believes it*.
- **Semantic similarity is candidate evidence, not confirmation**: the
  deterministic 4D.2 embedding provider is reused (never recreated) to rank
  related memories; confirmation requires structured links (graph edges or
  memories).
- **Governance inheritance**: a project-anchored pattern inherits the project's
  governance scope; employee/org-anchored patterns are organization-wide.
- **No parallel architecture**: composes the existing PatternDetection model,
  CompanyMemory (4D.3), organization graph (4D.1) and the durable event bus.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from statistics import fmean, pstdev
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.pattern_types import (
    CONFIDENCE_BASE,
    CONFIDENCE_CAP,
    CONFIDENCE_FLOOR,
    CONFIDENCE_OCCURRENCES,
    CONFIDENCE_OCCURRENCES_MAX,
    CONFIDENCE_QUALITY,
    CONFIDENCE_SEMANTIC,
    CONFIDENCE_SUPPORT,
    CONFIDENCE_TEMPORAL,
    CANDIDATE_MIN_OCCURRENCES,
    CONFIRMED_MIN_OCCURRENCES,
    EMERGING_MIN_OCCURRENCES,
    FADING_AFTER_DAYS,
    MAX_EVIDENCE,
    MAX_GRAPH_CANDIDATES,
    MAX_MEMORY_CANDIDATES,
    MAX_SEMANTIC_CANDIDATES,
    MAX_SUPPORTING,
    MAX_SUPPORTING_EVENTS,
    PERSISTENT_MIN_OCCURRENCES,
    PERSISTENT_WINDOW_MULTIPLIER,
    RESOLVED_AFTER_DAYS,
    confidence_label,
    events_to_pattern_types,
    rule_for,
)
from app.models.company_memory import CompanyMemory
from app.models.intelligence import (
    BackgroundJob,
    CompanyInsight,
    OrgGraphEdge,
    PatternDetection,
    PatternEvent,
)
from app.models.notification import Event as EventRow

logger = logging.getLogger("vcos.intelligence.patterns")

# Job family for change-driven pattern evaluation.
EVALUATE_JOB = "pattern.evaluate"

# Events that can evidence patterns (change-driven significance policy).
PATTERN_EVENTS: frozenset[str] = frozenset(
    {
        "task.blocked",
        "task.unblocked",
        "task.transitioned",
        "task.completed",
        "task.commented",
        "task.updated",
        "project.started",
        "project.paused",
        "project.completed",
        "project.cancelled",
        "milestone.completed",
        "decision.made",
        "decision.updated",
        "decision.executed",
        "decision.implemented",
        "approval.requested",
        "approval.approved",
        "approval.rejected",
        "governance.assignment.created",
        "governance.assignment.removed",
        "governance.delegation.created",
        "governance.delegation.revoked",
        "employee.transferred",
        "ticket.escalated",
    }
)

# Semantic similarity floor for a related memory to count as weak support.
_SEMANTIC_SUPPORT_FLOOR = 0.55
_SEMANTIC_RELATED_THRESHOLD = 0.55

# Lifecycle rank — transitions only move forward (fading/resolved are handled
# separately by the fade sweep and by revival rules).
_LIFECYCLE_RANK = {
    "candidate": 0,
    "emerging": 1,
    "confirmed": 2,
    "persistent": 3,
    "fading": 4,
    "resolved": 5,
}

# Confidence labels used for every read response.
CONFIDENCE_LABELS = ("Observed", "Strongly supported", "Emerging", "Weak signal")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _payload(event: EventRow) -> dict[str, Any]:
    if not event.payload_json:
        return {}
    try:
        value = json.loads(event.payload_json)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _first(payload: dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _snippet(value: Optional[str], limit: int = 180) -> str:
    if not value:
        return ""
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1] + "..."


# ---------------------------------------------------------------------------
# Job enqueue (called from the event handler, inside the event transaction)
# ---------------------------------------------------------------------------


async def enqueue_evaluation(
    db: AsyncSession,
    *,
    organization_id: Optional[str],
    event_id: str,
    name: str,
) -> None:
    """Enqueue a ``pattern.evaluate`` job for one event (idempotent)."""
    if name not in PATTERN_EVENTS:
        return
    job = BackgroundJob(
        organization_id=organization_id,
        name=EVALUATE_JOB,
        status="queued",
        event_id=event_id,
        payload_json=json.dumps({"name": name, "event_id": event_id}),
    )
    try:
        # Savepoint-scoped insert: a concurrent pass that already enqueued the
        # same event violates (name, event_id) uniqueness — roll back only the
        # savepoint, never the surrounding transaction.
        async with db.begin_nested():
            db.add(job)
            await db.flush()
    except Exception:
        pass  # already enqueued — evaluation is idempotent


# ---------------------------------------------------------------------------
# Bounded context collectors (small, indexed, capped)
# ---------------------------------------------------------------------------


async def _task_ctx(
    db: AsyncSession, organization_id: str, task_id: Optional[str]
) -> Optional[dict[str, Any]]:
    if not task_id:
        return None
    from app.models.task import Task, TaskDependency

    row = await db.get(Task, task_id)
    if row is None or row.organization_id != organization_id:
        return None
    has_deps = False
    unsatisfied = False
    dep_rows = (
        await db.execute(
            select(TaskDependency)
            .where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.task_id == row.id,
            )
            .limit(5)
        )
    ).scalars().all()
    has_deps = bool(dep_rows)
    if has_deps:
        from app.work.dependency_service import dependency_service

        try:
            unsatisfied = bool(
                await dependency_service.unsatisfied_blockers(
                    db, organization_id=organization_id, task_id=row.id
                )
            )
        except Exception:  # noqa: BLE001 - defensive collector
            unsatisfied = has_deps
    return {
        "id": row.id,
        "title": row.title,
        "status": row.status,
        "priority": row.priority,
        "project_id": row.project_id,
        "assignee_id": row.assignee_id,
        "has_deps": has_deps,
        "unsatisfied": unsatisfied,
    }


async def _project_ctx(
    db: AsyncSession, organization_id: str, project_id: Optional[str]
) -> Optional[dict[str, Any]]:
    if not project_id:
        return None
    from app.models.project import Project

    row = await db.get(Project, project_id)
    if row is None or row.organization_id != organization_id:
        return None
    return {"id": row.id, "name": row.name, "status": row.status, "owner_id": row.owner_id}


async def _employee_ctx(
    db: AsyncSession, organization_id: str, employee_id: Optional[str]
) -> Optional[dict[str, Any]]:
    if not employee_id:
        return None
    from app.models.employee import Employee

    row = await db.get(Employee, employee_id)
    if row is None or row.organization_id != organization_id:
        return None
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": getattr(row, "display_name", None)
        or getattr(row, "full_name", None)
        or " ".join(p for p in (row.first_name, row.last_name) if p),
    }


async def _decision_ctx(
    db: AsyncSession, organization_id: str, decision_id: Optional[str]
) -> Optional[dict[str, Any]]:
    if not decision_id:
        return None
    from app.models.knowledge import Decision

    row = await db.get(Decision, decision_id)
    if row is None or row.organization_id != organization_id:
        return None
    executed = False
    outcome = (
        await db.execute(
            select(CompanyMemory.id)
            .where(
                CompanyMemory.organization_id == organization_id,
                CompanyMemory.entity_type == "decision",
                CompanyMemory.entity_id == row.id,
                CompanyMemory.memory_category == "outcome",
                CompanyMemory.status == "active",
            )
            .limit(1)
        )
    ).scalars().first()
    executed = outcome is not None
    return {
        "id": row.id,
        "title": row.title,
        "status": row.status,
        "project_id": row.project_id,
        "executed": executed,
    }


async def _approval_ctx(
    db: AsyncSession, organization_id: str, approval_id: Optional[str]
) -> Optional[dict[str, Any]]:
    if not approval_id:
        return None
    from app.models.approval import Approval

    row = await db.get(Approval, approval_id)
    if row is None or row.organization_id != organization_id:
        return None
    return {
        "id": row.id,
        "title": row.title,
        "requester_id": row.requester_id,
        "approver_id": row.approver_id,
        "status": row.status,
    }


async def _milestone_ctx(
    db: AsyncSession, organization_id: str, milestone_id: Optional[str]
) -> Optional[dict[str, Any]]:
    if not milestone_id:
        return None
    from app.models.project import Milestone

    row = await db.get(Milestone, milestone_id)
    if row is None or row.organization_id != organization_id:
        return None
    return {"id": row.id, "name": getattr(row, "name", None) or row.id, "project_id": getattr(row, "project_id", None)}


_EMPLOYEE_SOURCES = {
    "assignee": ("assignee_id", "owner_id"),
    "requester": ("requester_id",),
    "approver": ("approver_id", "owner_id"),
    "grantor": ("user_id", "employee_id", "actor_id"),
    "owner": ("employee_id", "owner_id", "recipient_id"),
}


async def _build_context(
    db: AsyncSession,
    event: EventRow,
    payload: dict[str, Any],
    organization_id: str,
) -> dict[str, Any]:
    """Resolve the bounded entity context for one event (never a scan)."""
    name = event.name
    ctx: dict[str, Any] = {}

    task_id = _first(payload, "task_id", "id") if name.startswith("task.") else None
    if task_id:
        ctx["task"] = await _task_ctx(db, organization_id, task_id)
        if ctx["task"] and ctx["task"].get("project_id"):
            ctx["project_id"] = ctx["task"]["project_id"]

    project_id = _first(payload, "project_id")
    if project_id and not ctx.get("project_id"):
        ctx["project_id"] = project_id
    if name.startswith("project.") and not project_id:
        ctx["project_id"] = _first(payload, "id")

    if ctx.get("project_id"):
        ctx["project"] = await _project_ctx(db, organization_id, ctx["project_id"])

    decision_id = _first(payload, "decision_id")
    if decision_id:
        ctx["decision"] = await _decision_ctx(db, organization_id, decision_id)
        if ctx["decision"] and ctx["decision"].get("project_id") and not ctx.get("project"):
            ctx["project_id"] = ctx["decision"]["project_id"]
            ctx["project"] = await _project_ctx(db, organization_id, ctx["project_id"])

    approval_id = _first(payload, "approval_id")
    if approval_id:
        ctx["approval"] = await _approval_ctx(db, organization_id, approval_id)

    milestone_id = _first(payload, "milestone_id")
    if milestone_id:
        ctx["milestone"] = await _milestone_ctx(db, organization_id, milestone_id)

    # Resolve every employee candidate (bounded, indexed lookups).
    seen_employee: dict[str, bool] = {}
    for source, keys in _EMPLOYEE_SOURCES.items():
        raw = _first(payload, *keys)
        if not raw or raw in seen_employee:
            continue
        employee = await _employee_ctx(db, organization_id, raw)
        if employee is not None:
            seen_employee[raw] = True
            if source == "assignee":
                ctx.setdefault("employee", employee)
            elif source in ("requester", "approver", "grantor", "owner"):
                ctx.setdefault(f"{source}_employee", employee)
                ctx.setdefault("employee", employee)

    return ctx


def _resolve_anchor(
    rule: dict[str, Any], ctx: dict[str, Any]
) -> tuple[Optional[str], Optional[str], Optional[dict[str, Any]]]:
    """(anchor_type, anchor_id, meta) from the resolved context (or None)."""
    anchor = rule["anchor"]
    if anchor == "project":
        if not ctx.get("project"):
            return None, None, None
        return "project", ctx["project"]["id"], {"name": ctx["project"]["name"]}
    if anchor == "task":
        if not ctx.get("task"):
            return None, None, None
        return "task", ctx["task"]["id"], {"name": ctx["task"]["title"]}
    if anchor == "employee":
        if not ctx.get("employee"):
            return None, None, None
        return "employee", ctx["employee"]["id"], {"name": ctx["employee"]["name"]}
    if anchor == "decision":
        if not ctx.get("decision"):
            return None, None, None
        return "decision", ctx["decision"]["id"], {"name": ctx["decision"]["title"]}
    if anchor == "milestone":
        if not ctx.get("milestone"):
            return None, None, None
        return "milestone", ctx["milestone"]["id"], {"name": ctx["milestone"]["name"]}
    return None, None, None


async def _anchor_scope(
    db: AsyncSession,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Inherit governance scope from the anchoring project (bounded lookup).

    Returns ``{"scope_type": "org"|"project", "scope_id": ...,
    "auth_project_id": ...}``. A project wrapped by a project-type governance
    scope produces a project-scoped pattern; anything else is org-wide.
    """
    project_id = (ctx.get("project") or {}).get("id") or ctx.get("project_id")
    if not project_id:
        return {"scope_type": "org", "scope_id": None, "auth_project_id": None}
    from app.models.governance import GovernanceScope

    scope = (
        await db.execute(
            select(GovernanceScope)
            .where(
                GovernanceScope.entity_id == project_id,
                GovernanceScope.scope_type == "project",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if scope is None:
        return {"scope_type": "org", "scope_id": None, "auth_project_id": project_id}
    return {"scope_type": "project", "scope_id": scope.id, "auth_project_id": project_id}


# ---------------------------------------------------------------------------
# Supporting evidence (bounded, indexed, never a scan)
# ---------------------------------------------------------------------------


async def _supporting_memories(
    db: AsyncSession,
    organization_id: str,
    pattern: PatternDetection,
) -> list[dict[str, Any]]:
    """CompanyMemory rows anchored to the same entities (Slice 4D.3 memory)."""
    entities = pattern.entities_json or []
    entity_ids = [e["id"] for e in entities if e.get("type") in ("project", "task", "decision")]
    if not entity_ids:
        return []
    entity_ids = entity_ids[:5]
    from sqlalchemy import or_

    rows = (
        await db.execute(
            select(CompanyMemory)
            .where(
                CompanyMemory.organization_id == organization_id,
                CompanyMemory.status == "active",
                or_(
                    *[
                        (CompanyMemory.entity_type == e.get("type")) & (CompanyMemory.entity_id == eid)
                        for e in entities[:5]
                        if (eid := e.get("id"))
                    ]
                ),
            )
            .order_by(CompanyMemory.updated_at.desc())
            .limit(MAX_MEMORY_CANDIDATES)
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "memory_category": row.memory_category,
            "fact_kind": row.fact_kind,
            "confidence": row.confidence,
            "auth_scope": row.auth_scope,
            "auth_project_id": row.auth_project_id,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        }
        for row in rows
    ]


async def _graph_support(
    db: AsyncSession,
    organization_id: str,
    pattern: PatternDetection,
) -> list[dict[str, Any]]:
    """Organization graph edges touching the pattern's entities (4D.1 graph)."""
    entities = pattern.entities_json or []
    if not entities:
        return []
    from sqlalchemy import or_

    conds = []
    for e in entities[:3]:
        etype, eid = e.get("type"), e.get("id")
        if not eid:
            continue
        conds.append((OrgGraphEdge.source_type == etype) & (OrgGraphEdge.source_id == eid))
        conds.append((OrgGraphEdge.target_type == etype) & (OrgGraphEdge.target_id == eid))
    if not conds:
        return []
    rows = (
        await db.execute(
            select(OrgGraphEdge)
            .where(
                OrgGraphEdge.organization_id == organization_id,
                OrgGraphEdge.active.is_(True),
                or_(*conds),
            )
            .order_by(OrgGraphEdge.updated_at.desc())
            .limit(MAX_GRAPH_CANDIDATES)
        )
    ).scalars().all()
    return [
        {
            "source_type": row.source_type,
            "source_id": row.source_id,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "relation": row.relation,
        }
        for row in rows
    ]


async def _semantic_support(
    db: AsyncSession,
    pattern: PatternDetection,
    memories: list[dict[str, Any]],
) -> tuple[float, list[str]]:
    """Deterministic semantic similarity to supporting memories (4D.2 provider).

    This is candidate-generation evidence only — it never confirms a pattern.
    """
    if not memories:
        return 0.0, []
    from app.knowledge.embeddings import get_embedding_provider

    provider = get_embedding_provider()
    base = " ".join(p for p in (pattern.title, pattern.detail or "") if p)
    related: list[str] = []
    scores: list[float] = []
    for memory in memories[:MAX_SEMANTIC_CANDIDATES]:
        text = " ".join(p for p in (memory.get("title") or "", "") if p)
        try:
            vectors = await provider.embed_many([base or "pattern", text or "memory"])
        except Exception:  # pragma: no cover - provider fallback
            continue
        if len(vectors) != 2:
            continue
        sim = provider.cosine(vectors[0], vectors[1])
        if sim >= _SEMANTIC_RELATED_THRESHOLD:
            related.append(memory["id"])
        scores.append(sim)
    avg = fmean(scores) if scores else 0.0
    return max(0.0, min(1.0, avg)), related


def _temporal_regularity(pattern: PatternDetection) -> tuple[float, Optional[float]]:
    """Regularity of recurrence intervals: 1.0 = perfectly regular."""
    timestamps: list[datetime] = []
    for item in pattern.evidence_json or []:
        if item.get("type") == "event" and item.get("occurred_at"):
            try:
                value = datetime.fromisoformat(str(item["occurred_at"]))
            except (ValueError, TypeError):
                continue
            timestamps.append(value)
    timestamps.sort()
    intervals = [
        (b - a).total_seconds() / 86400.0
        for a, b in zip(timestamps, timestamps[1:])
        if b > a
    ]
    if not intervals:
        return 0.0, None
    avg = fmean(intervals)
    if avg <= 0:
        return 1.0, avg
    cv = pstdev(intervals) / avg if len(intervals) > 1 else 0.0
    regularity = max(0.0, 1.0 - cv) if cv <= 1.0 else 0.0
    return regularity, avg


def _trend_for(pattern: PatternDetection) -> str:
    """rising | stable | fading from the last recurrence interval."""
    _, avg = _temporal_regularity(pattern)
    if avg is None:
        return "stable"
    timestamps = [
        datetime.fromisoformat(str(item["occurred_at"]))
        for item in pattern.evidence_json or []
        if item.get("type") == "event" and item.get("occurred_at")
    ]
    timestamps.sort()
    if len(timestamps) < 2:
        return "stable"
    last = (timestamps[-1] - timestamps[-2]).total_seconds() / 86400.0
    if last <= 0.7 * avg:
        return "rising"
    if last >= 1.5 * avg:
        return "fading"
    return "stable"


def _interval_days(pattern: PatternDetection) -> Optional[float]:
    _, avg = _temporal_regularity(pattern)
    return round(avg, 2) if avg is not None else None


# ---------------------------------------------------------------------------
# Confidence (bounded 0..1, component-labeled)
# ---------------------------------------------------------------------------


async def _compute_confidence(
    pattern: PatternDetection,
    rule: dict[str, Any],
    *,
    memories: list[dict[str, Any]],
    graph: list[dict[str, Any]],
    semantic: float,
) -> float:
    count = pattern.count or 0
    occurrence = CONFIDENCE_OCCURRENCES * (
        min(count, CONFIDENCE_OCCURRENCES_MAX) / CONFIDENCE_OCCURRENCES_MAX
    )
    quality = 0.6
    if any(e.get("type") in ("project", "task", "decision") for e in pattern.entities_json or []):
        quality = 1.0
    regularity, _ = _temporal_regularity(pattern)
    support = min(1.0, (len(memories) * 0.5 + len(graph) * 0.5) / 3.0)
    total = (
        CONFIDENCE_BASE
        + occurrence
        + CONFIDENCE_QUALITY * quality
        + CONFIDENCE_TEMPORAL * regularity
        + CONFIDENCE_SUPPORT * support
        + CONFIDENCE_SEMANTIC * semantic
    )
    return max(CONFIDENCE_FLOOR, min(CONFIDENCE_CAP, total))


# ---------------------------------------------------------------------------
# Lifecycle (thresholds from pattern_types; forward-only transitions)
# ---------------------------------------------------------------------------


def _apply_lifecycle(
    pattern: PatternDetection,
    rule: dict[str, Any],
    *,
    memories: list[dict[str, Any]],
    graph: list[dict[str, Any]],
    semantic: float,
) -> Optional[str]:
    """Recompute the lifecycle status; returns the new status (or None).

    Occurrence thresholds drive the lifecycle; corroboration (memory/graph
    links, semantic support) feeds confidence instead, so a pattern that
    repeats enough is always promoted without requiring external support.
    """
    count = pattern.count or 0
    window_days = rule.get("window_days", 30)

    target = pattern.status
    if count >= PERSISTENT_MIN_OCCURRENCES and (
        pattern.last_seen - pattern.first_seen
    ).days >= PERSISTENT_WINDOW_MULTIPLIER * window_days:
        target = "persistent"
    elif count >= CONFIRMED_MIN_OCCURRENCES:
        target = "confirmed"
    elif count >= EMERGING_MIN_OCCURRENCES:
        target = "emerging"
    elif count >= CANDIDATE_MIN_OCCURRENCES:
        target = "candidate"

    current_rank = _LIFECYCLE_RANK.get(pattern.status, 0)
    target_rank = _LIFECYCLE_RANK.get(target, 0)
    if target_rank > current_rank:
        return target
    return None


# ---------------------------------------------------------------------------
# Pattern upsert (create or consolidate one occurrence)
# ---------------------------------------------------------------------------


def _merge_event_ids(existing: Optional[list[str]], new: list[str]) -> list[str]:
    merged = list(existing or [])
    for value in new:
        if value and value not in merged:
            merged.append(value)
    return merged[-MAX_SUPPORTING_EVENTS:]


def _merge_evidence(
    existing: Optional[list[dict[str, Any]]], new: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged = {f"{item.get('type')}:{item.get('id')}": item for item in existing or []}
    for item in new:
        merged[f"{item.get('type')}:{item.get('id')}"] = item
    return list(merged.values())[-MAX_EVIDENCE:]


def _merge_entities(
    existing: Optional[list[dict[str, Any]]], new: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged = {f"{item.get('type')}:{item.get('id')}": item for item in existing or []}
    for item in new:
        merged[f"{item.get('type')}:{item.get('id')}"] = item
    return list(merged.values())[-8:]


async def _refresh_insight(
    db: AsyncSession,
    organization_id: str,
    pattern: PatternDetection,
    reason: str,
) -> None:
    """Keep the canonical CompanyInsight freshness row current (bounded upsert)."""
    row = (
        await db.execute(
            select(CompanyInsight).where(
                CompanyInsight.organization_id == organization_id,
                CompanyInsight.entity_type == "pattern",
                CompanyInsight.entity_id == pattern.id,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(
            CompanyInsight(
                organization_id=organization_id,
                entity_type="pattern",
                entity_id=pattern.id,
                kind="pattern",
                title=pattern.title,
                status=pattern.status,
                scope_id=pattern.scope_id,
                reason=reason,
                detail={
                    "pattern_type": pattern.pattern_type,
                    "key": pattern.key,
                    "count": pattern.count,
                    "confidence": round(pattern.confidence, 3),
                },
                touched_by=None,
            )
        )
    else:
        row.title = pattern.title
        row.status = pattern.status
        row.scope_id = pattern.scope_id
        row.reason = reason
        row.detail = {
            "pattern_type": pattern.pattern_type,
            "key": pattern.key,
            "count": pattern.count,
            "confidence": round(pattern.confidence, 3),
        }


async def _emit_pattern_event(
    db: AsyncSession,
    organization_id: str,
    name: str,
    pattern: PatternDetection,
) -> None:
    """Emit a durable ``pattern.*`` event (observability, no handler fan-out)."""
    from app.services.event_service import event_service

    await event_service.emit(
        db,
        name=name,
        organization_id=organization_id,
        payload={
            "pattern_id": pattern.id,
            "pattern_type": pattern.pattern_type,
            "key": pattern.key,
            "status": pattern.status,
            "count": pattern.count,
            "confidence": round(pattern.confidence, 3),
        },
    )


async def _upsert_pattern(
    db: AsyncSession,
    *,
    organization_id: str,
    pattern_type: str,
    rule: dict[str, Any],
    key: str,
    ctx: dict[str, Any],
    event: EventRow,
    payload: dict[str, Any],
    anchor_type: str,
    anchor_id: str,
    anchor_meta: Optional[dict[str, Any]],
) -> dict[str, Any]:
    row = (
        await db.execute(
            select(PatternDetection).where(
                PatternDetection.organization_id == organization_id,
                PatternDetection.pattern_type == pattern_type,
                PatternDetection.key == key,
            ).limit(1)
        )
    ).scalar_one_or_none()
    now = event.occurred_at or _now()
    scope = await _anchor_scope(db, ctx)

    if row is None:
        title = rule["title"](ctx, payload)
        detail = rule["detail"](ctx, payload, 1)
        row = PatternDetection(
            organization_id=organization_id,
            pattern_type=pattern_type,
            key=key,
            family=rule["family"],
            title=title,
            detail=detail,
            description=rule["description"],
            status="candidate",
            count=1,
            confidence=CONFIDENCE_FLOOR,
            first_seen=now,
            last_seen=now,
            last_evaluated_at=now,
            scope_id=scope.get("scope_id"),
            scope_type=scope.get("scope_type", "org"),
            auth_project_id=scope.get("auth_project_id"),
            time_window_days=rule.get("window_days", 30),
            evidence_json=[
                {
                    "type": "event",
                    "id": event.id,
                    "relationship": event.name,
                    "occurred_at": event.occurred_at.isoformat() if event.occurred_at else now.isoformat(),
                }
            ],
            supporting_event_ids=[event.id],
            entities_json=[
                {"type": anchor_type, "id": anchor_id, "title": (anchor_meta or {}).get("name") or anchor_id}
            ],
            supporting_memory_ids=[],
            supporting_relationships=[],
            detail_json={"quality": 1.0 if anchor_type != "employee" else 0.6},
        )
        db.add(row)
        await db.flush()
        await _emit_pattern_event(db, organization_id, "pattern.detected", row)
        await _refresh_insight(db, organization_id, row, "pattern.detected")
        await db.flush()
        return {"pattern_id": row.id, "pattern_type": pattern_type, "count": 1, "status": row.status, "created": True}

    # Fade/resolve evaluation on touch: a pattern that stopped recurring ages.
    if row.status in ("emerging", "confirmed", "persistent") and (
        now - row.last_seen
    ).days >= FADING_AFTER_DAYS:
        row.status = "fading"
        await _emit_pattern_event(db, organization_id, "pattern.faded", row)
    if row.status in ("candidate", "fading", "confirmed", "persistent") and (
        now - row.last_seen
    ).days >= RESOLVED_AFTER_DAYS:
        row.status = "resolved"
        await _emit_pattern_event(db, organization_id, "pattern.resolved", row)
    # Revival: a resolved/fading pattern that recurs becomes active again.
    if row.status == "resolved" or row.status == "fading":
        row.status = "confirmed" if row.count >= CONFIRMED_MIN_OCCURRENCES else "candidate"

    row.count = (row.count or 0) + 1
    row.title = rule["title"](ctx, payload)
    row.detail = rule["detail"](ctx, payload, row.count)
    row.last_seen = now
    row.last_evaluated_at = now
    row.scope_id = scope.get("scope_id") or row.scope_id
    row.scope_type = scope.get("scope_type") or row.scope_type
    row.auth_project_id = scope.get("auth_project_id") or row.auth_project_id
    row.supporting_event_ids = _merge_event_ids(row.supporting_event_ids, [event.id])
    row.evidence_json = _merge_evidence(
        row.evidence_json,
        [
            {
                "type": "event",
                "id": event.id,
                "relationship": event.name,
                "occurred_at": event.occurred_at.isoformat() if event.occurred_at else now.isoformat(),
            }
        ],
    )
    row.entities_json = _merge_entities(
        row.entities_json,
        [
            {
                "type": anchor_type,
                "id": anchor_id,
                "title": (anchor_meta or {}).get("name") or anchor_id,
            }
        ],
    )

    memories = await _supporting_memories(db, organization_id, row)
    graph = await _graph_support(db, organization_id, row)
    semantic, related = await _semantic_support(db, row, memories)
    row.supporting_memory_ids = [m["id"] for m in memories[:MAX_SUPPORTING]]
    row.supporting_relationships = graph[:MAX_SUPPORTING]
    row.detail_json = {
        "quality": 1.0 if any(
            e.get("type") in ("project", "task", "decision") for e in row.entities_json or []
        ) else 0.6,
        "semantic_related": related,
    }
    row.confidence = await _compute_confidence(row, rule, memories=memories, graph=graph, semantic=semantic)
    row.avg_interval_days = _interval_days(row)
    row.trend = _trend_for(row)

    before = row.status
    new_status = _apply_lifecycle(row, rule, memories=memories, graph=graph, semantic=semantic)
    if new_status is not None:
        row.status = new_status
    await db.flush()
    await _emit_pattern_event(db, organization_id, "pattern.updated", row)
    if new_status == "confirmed":
        await _emit_pattern_event(db, organization_id, "pattern.confirmed", row)
    await _refresh_insight(db, organization_id, row, "pattern.updated")
    await db.flush()
    return {
        "pattern_id": row.id,
        "pattern_type": pattern_type,
        "count": row.count,
        "status": row.status,
        "transitioned": new_status,
        "created": False,
    }


# ---------------------------------------------------------------------------
# The evaluation pipeline (per event)
# ---------------------------------------------------------------------------


async def process_event(db: AsyncSession, *, event: EventRow) -> Optional[dict[str, Any]]:
    """Evaluate one event against the pattern rules. Idempotent and replay-safe.

    Returns a small trace dict (or ``None`` when the event was skipped).
    """
    payload = _payload(event)
    organization_id = event.organization_id or payload.get("organization_id")
    if not organization_id:
        return None
    rules = events_to_pattern_types(event.name)
    if not rules:
        return None

    # Exactly-once guard: an event that already fed any pattern is never
    # re-evaluated (mirrors the 4D.3 MemoryEvent exactly-once rule).
    already = (
        await db.execute(
            select(PatternEvent.event_id).where(PatternEvent.event_id == event.id).limit(1)
        )
    ).scalars().first()
    if already is not None:
        return {"event_id": event.id, "skipped": True}

    ctx = await _build_context(db, event, payload, organization_id)
    traces: list[dict[str, Any]] = []
    for pattern_type, rule in rules:
        if rule.get("condition") and not rule["condition"](ctx, payload, event.name):
            continue
        anchor_type, anchor_id, anchor_meta = _resolve_anchor(rule, ctx)
        if not anchor_id:
            continue
        key = rule["key"](ctx, payload)
        if not key:
            continue
        trace = await _upsert_pattern(
            db,
            organization_id=organization_id,
            pattern_type=pattern_type,
            rule=rule,
            key=key,
            ctx=ctx,
            event=event,
            payload=payload,
            anchor_type=anchor_type,
            anchor_id=anchor_id,
            anchor_meta=anchor_meta,
        )
        # Idempotent lineage link: an event feeds one pattern exactly once.
        link = PatternEvent(
            organization_id=organization_id,
            pattern_id=trace["pattern_id"],
            event_id=event.id,
            relationship="occurrence",
        )
        db.add(link)
        traces.append(trace)
    if traces:
        await db.flush()
    return {"event_id": event.id, "patterns": traces}


# ---------------------------------------------------------------------------
# Fade / resolve maintenance (bounded, indexed — never a whole-org scan)
# ---------------------------------------------------------------------------


async def evaluate_fading(
    db: AsyncSession,
    organization_id: Optional[str] = None,
    limit: int = 50,
) -> dict[str, int]:
    """Age patterns that stopped recurring: confirmed/persistent -> fading ->
    resolved. Bounded to the oldest ``limit`` active patterns by last_seen."""
    now = _now()
    resolved = 0
    faded = 0
    filters = [
        PatternDetection.status.in_(("candidate", "emerging", "confirmed", "persistent", "fading")),
        PatternDetection.last_seen < now - timedelta(days=RESOLVED_AFTER_DAYS),
    ]
    if organization_id:
        filters.append(PatternDetection.organization_id == organization_id)
    rows = (
        await db.execute(
            select(PatternDetection)
            .where(*filters)
            .order_by(PatternDetection.last_seen.asc())
            .limit(limit)
        )
    ).scalars().all()
    for row in rows:
        if row.status == "resolved":
            continue
        row.status = "resolved"
        row.last_evaluated_at = now
        await _emit_pattern_event(db, row.organization_id, "pattern.resolved", row)
        await _refresh_insight(db, row.organization_id, row, "pattern.resolved")
        resolved += 1
    if resolved:
        await db.flush()

    filters = [
        PatternDetection.status.in_(("confirmed", "persistent")),
        PatternDetection.last_seen < now - timedelta(days=FADING_AFTER_DAYS),
    ]
    if organization_id:
        filters.append(PatternDetection.organization_id == organization_id)
    rows = (
        await db.execute(
            select(PatternDetection)
            .where(*filters)
            .order_by(PatternDetection.last_seen.asc())
            .limit(limit)
        )
    ).scalars().all()
    for row in rows:
        row.status = "fading"
        row.last_evaluated_at = now
        await _emit_pattern_event(db, row.organization_id, "pattern.faded", row)
        await _refresh_insight(db, row.organization_id, row, "pattern.faded")
        faded += 1
    if faded:
        await db.flush()
    return {"resolved": resolved, "faded": faded}
