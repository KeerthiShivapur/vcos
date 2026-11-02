"""Slice 4D.3 — organizational memory formation pipeline.

Change-driven, evidence-backed memory automation. The pipeline turns
significant operational events into organizational memories:

    event -> significance detection -> context collection -> memory upsert
             -> evidence lineage -> lesson derivation -> outcome resolution

Design laws:

- **Change-driven, never scanned**: formation is triggered per event (job
  ``memory.formation``), each event is processed exactly once (``MemoryEvent``
  idempotency), and every query used to collect context is small, indexed and
  hard-capped. There is deliberately *no* organization-wide scan.
- **Observational only**: the pipeline reads operating-layer tables and writes
  memory tables. It never mutates tasks, projects, decisions, approvals or any
  other operating entity.
- **Evidence lineage**: every memory records ``evidence_json`` (entity refs:
  type/id/relationship) and ``source_event_ids``. A memory can always answer
  *why VCOS believes it*.
- **Safety**: memories are labeled ``fact`` | ``observation`` | ``inference`` |
  ``lesson``. Inferences and lessons are never presented as facts, and
  confidence distinguishes structured evidence (high) from multiple
  corroborating events (medium) from semantic inference (low).
- **Governance inheritance**: a memory inherits the scope of its evidence —
  project-scoped evidence produces a project-scoped memory visible only to
  users whose access includes that project. Organization-wide events produce
  organization-wide memories.
- **No parallel architecture**: this composes the Phase 19 ``CompanyMemory``
  model and the Slice 3 event machinery. There is no second memory store.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_memory import (
    CompanyMemory,
    FACT_KINDS,
    MemoryEvent,
    MemoryOutcome,
)
from app.models.intelligence import BackgroundJob
from app.models.notification import Event as EventRow

logger = logging.getLogger("vcos.memory.formation")

# Job family for change-driven memory formation.
FORMATION_JOB = "memory.formation"

# Bounds — every collector query is capped so a batch stays proportional to
# the events being processed.
_MAX_DEPENDENCIES = 10
_MAX_DECISIONS = 10
_MAX_COMMENTS = 5
_MAX_RELATED = 5
_SEMANTIC_RELATED_THRESHOLD = 0.55
_CONFIDENCE_CAP = 0.95

# Outcome progression order used when consolidating outcome memories: a later
# event may upgrade the observed outcome, never downgrade it.
_OUTCOME_RANK = {"unresolved": 0, "negative": 1, "partial": 2, "positive": 3}

_MEMORY_CATEGORY_EVENT = "event"
_MEMORY_CATEGORY_EXPERIENCE = "experience"
_MEMORY_CATEGORY_LESSON = "lesson"
_MEMORY_CATEGORY_OUTCOME = "outcome"


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
# Context collectors (small, indexed, capped)
# ---------------------------------------------------------------------------


async def _task(db: AsyncSession, organization_id: str, task_id: Optional[str]) -> Optional[dict]:
    if not task_id:
        return None
    from app.models.task import Task

    row = await db.get(Task, task_id)
    if row is None or row.organization_id != organization_id:
        return None
    return {
        "id": row.id,
        "title": row.title,
        "status": row.status,
        "priority": row.priority,
        "project_id": row.project_id,
        "assignee_id": row.assignee_id,
        "tags": row.tags or [],
    }


async def _project(db: AsyncSession, organization_id: str, project_id: Optional[str]) -> Optional[dict]:
    if not project_id:
        return None
    from app.models.project import Project

    row = await db.get(Project, project_id)
    if row is None or row.organization_id != organization_id:
        return None
    return {"id": row.id, "title": row.name, "status": row.status}


async def _employee(db: AsyncSession, organization_id: str, employee_id: Optional[str]) -> Optional[dict]:
    if not employee_id:
        return None
    from app.models.employee import Employee

    row = await db.get(Employee, employee_id)
    if row is None or row.organization_id != organization_id:
        return None
    return {"id": row.id, "name": getattr(row, "full_name", None) or getattr(row, "name", None)}


async def _dependencies(
    db: AsyncSession, organization_id: str, task_id: Optional[str]
) -> list[dict]:
    if not task_id:
        return []
    from app.models.task import TaskDependency

    rows = (
        await db.execute(
            select(TaskDependency)
            .where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.task_id == task_id,
            )
            .limit(_MAX_DEPENDENCIES)
        )
    ).scalars().all()
    return [
        {"id": row.id, "task_id": row.task_id, "depends_on_task_id": row.depends_on_task_id, "kind": row.kind}
        for row in rows
    ]


async def _decisions(db: AsyncSession, organization_id: str, project_id: Optional[str]) -> list[dict]:
    if not project_id:
        return []
    from app.models.knowledge import Decision

    rows = (
        await db.execute(
            select(Decision)
            .where(Decision.organization_id == organization_id, Decision.project_id == project_id)
            .order_by(Decision.created_at.desc())
            .limit(_MAX_DECISIONS)
        )
    ).scalars().all()
    return [{"id": row.id, "title": row.title, "status": row.status} for row in rows]


async def _comments(db: AsyncSession, organization_id: str, task_id: Optional[str]) -> list[dict]:
    if not task_id:
        return []
    from app.models.task import TaskComment

    rows = (
        await db.execute(
            select(TaskComment)
            .where(TaskComment.organization_id == organization_id, TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at.desc())
            .limit(_MAX_COMMENTS)
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "author_id": row.author_id,
            "body": _snippet(row.body, 200),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def _resolve_project_scope(
    db: AsyncSession, organization_id: str, project_id: Optional[str]
) -> dict[str, Any]:
    """Inherit governance scope from the project that owns the evidence.

    Returns ``{"auth_scope": "org"|"project", "auth_project_id": ...}``.
    A project that belongs to a governance scope produces project-scoped
    memory; a project without a scope node is organization-wide.
    """
    if not project_id:
        return {"auth_scope": "org", "auth_project_id": None, "auth_scope_id": None}
    from app.models.governance import GovernanceScope

    row = (
        await db.execute(
            select(GovernanceScope)
            .where(
                GovernanceScope.organization_id == organization_id,
                GovernanceScope.entity_id == project_id,
                GovernanceScope.scope_type == "project",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return {"auth_scope": "org", "auth_project_id": None, "auth_scope_id": None}
    return {
        "auth_scope": "project",
        "auth_project_id": project_id,
        "auth_scope_id": row.id,
    }


# ---------------------------------------------------------------------------
# Significance policy — the canonical event -> memory rule map
# ---------------------------------------------------------------------------


def _title(ctx: dict[str, Any], fallback: str) -> str:
    task = ctx.get("task") or {}
    project = ctx.get("project") or {}
    decision = ctx.get("decision") or {}
    name = task.get("title") or project.get("title") or decision.get("title")
    return _snippet(name, 120) if name else fallback


def _project_label(ctx: dict[str, Any]) -> str:
    project = ctx.get("project") or {}
    return project.get("title") or "the project"


def _lesson_blocked(ctx: dict[str, Any], payload: dict[str, Any]) -> str:
    task = ctx.get("task") or {}
    deps = ctx.get("dependencies") or []
    if deps:
        return (
            f"Task '{task.get('title', 'task')}' was blocked by an unsatisfied "
            f"dependency ({deps[0].get('kind', 'dependency')}). Verify blocking "
            "dependencies are unblocked before starting dependent work."
        )
    return (
        f"Task '{task.get('title', 'task')}' was blocked during execution. "
        "Blocked work should be surfaced early so the blocker is resolved before the deadline."
    )


def _lesson_completed_after_block(ctx: dict[str, Any], payload: dict[str, Any]) -> str:
    task = ctx.get("task") or {}
    return (
        f"Task '{task.get('title', 'task')}' was completed after being blocked. "
        "Blocked tasks can still be recovered; track blockers explicitly to keep "
        "delivery predictable."
    )


_RULES: dict[str, dict[str, Any]] = {
    # ------------------------------------------------------------------ task
    "task.blocked": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "task",
        "kind": "task_delay",
        "importance": "medium",
        "fact_kind": "observation",
        "base_confidence": 0.6,
        "dedupe": lambda ctx, payload: f"task.blocked:{ctx.get('task_id')}",
        "title": lambda ctx, payload: f"Task blocked: {_title(ctx, 'unknown task')}",
        "summary": lambda ctx, payload: (
            f"Task '{_title(ctx, 'unknown task')}' in {_project_label(ctx)} was blocked during execution."
        ),
        "lesson": _lesson_blocked,
        "context": ["task", "project", "employee", "dependencies", "decisions", "comments"],
    },
    "task.unblocked": {
        "memory_category": _MEMORY_CATEGORY_OUTCOME,
        "domain": "task",
        "kind": "task_delay",
        "importance": "medium",
        "fact_kind": "observation",
        "base_confidence": 0.6,
        "dedupe": lambda ctx, payload: f"task.outcome:{ctx.get('task_id')}",
        "title": lambda ctx, payload: f"Task unblocked: {_title(ctx, 'unknown task')}",
        "requires_resolution": True,
        "resolves": {"dedupe_prefix": "task.blocked:"},
        "outcome_type": "positive",
        "outcome": lambda ctx, payload: f"Task '{_title(ctx, 'unknown task')}' was unblocked.",
        "lesson": lambda ctx, payload: (
            f"Task '{_title(ctx, 'unknown task')}' was unblocked after being blocked. "
            "Early unblocking keeps the delivery flow moving."
        ),
        "context": ["task", "project", "employee", "dependencies", "comments"],
    },
    "task.completed": {
        "memory_category": _MEMORY_CATEGORY_OUTCOME,
        "domain": "task",
        "kind": "task_delay",
        "importance": "medium",
        "fact_kind": "observation",
        "base_confidence": 0.6,
        "dedupe": lambda ctx, payload: f"task.outcome:{ctx.get('task_id')}",
        "title": lambda ctx, payload: f"Task completed: {_title(ctx, 'unknown task')}",
        "requires_resolution": True,
        "resolves": {"dedupe_prefix": "task.blocked:"},
        "outcome_type": "positive",
        "outcome": lambda ctx, payload: (
            f"Task '{_title(ctx, 'unknown task')}' was completed."
        ),
        "lesson": _lesson_completed_after_block,
        "context": ["task", "project", "employee", "dependencies", "comments"],
    },
    "task.commented": {
        "memory_category": _MEMORY_CATEGORY_EVENT,
        "domain": "task",
        "kind": "task_discussion",
        "importance": "low",
        "fact_kind": "observation",
        "base_confidence": 0.5,
        "dedupe": lambda ctx, payload: f"task.commented:{ctx.get('task_id')}",
        "title": lambda ctx, payload: f"Task discussion: {_title(ctx, 'unknown task')}",
        # context-only: enriches an open blocked-task memory, never forms its own.
        "context_only": True,
        "updates": {"dedupe_prefix": "task.blocked:"},
        "context": ["task", "project", "employee", "comments"],
    },
    # --------------------------------------------------------------- project
    "project.started": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "project",
        "kind": "project_started",
        "importance": "high",
        "fact_kind": "observation",
        "base_confidence": 0.6,
        "dedupe": lambda ctx, payload: f"project.started:{ctx.get('project_id')}",
        "title": lambda ctx, payload: f"Project started: {_title(ctx, 'unknown project')}",
        "summary": lambda ctx, payload: (
            f"Project '{_title(ctx, 'unknown project')}' entered active execution."
        ),
        "context": ["project", "decisions"],
    },
    "project.paused": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "project",
        "kind": "project_paused",
        "importance": "high",
        "fact_kind": "observation",
        "base_confidence": 0.6,
        "dedupe": lambda ctx, payload: f"project.paused:{ctx.get('project_id')}",
        "title": lambda ctx, payload: f"Project paused: {_title(ctx, 'unknown project')}",
        "summary": lambda ctx, payload: (
            f"Project '{_title(ctx, 'unknown project')}' was paused."
        ),
        "context": ["project", "decisions"],
    },
    "project.completed": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "project",
        "kind": "project_completed",
        "importance": "high",
        "fact_kind": "observation",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"project.completed:{ctx.get('project_id')}",
        "title": lambda ctx, payload: f"Project completed: {_title(ctx, 'unknown project')}",
        "summary": lambda ctx, payload: (
            f"Project '{_title(ctx, 'unknown project')}' was completed successfully."
        ),
        "outcome_type": "positive",
        "lesson": lambda ctx, payload: (
            f"Project '{_title(ctx, 'unknown project')}' reached completion. "
            "Successful deliveries set the baseline for future planning."
        ),
        "resolves": {"dedupe_prefix": "project.started:"},
        "context": ["project", "decisions"],
    },
    "project.cancelled": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "project",
        "kind": "project_cancelled",
        "importance": "high",
        "fact_kind": "observation",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"project.cancelled:{ctx.get('project_id')}",
        "title": lambda ctx, payload: f"Project cancelled: {_title(ctx, 'unknown project')}",
        "summary": lambda ctx, payload: (
            f"Project '{_title(ctx, 'unknown project')}' was cancelled before completion."
        ),
        "outcome_type": "negative",
        "lesson": lambda ctx, payload: (
            f"Project '{_title(ctx, 'unknown project')}' was cancelled. "
            "Cancelled scope should be reviewed before it is re-attempted."
        ),
        "supersedes": {"dedupe_prefix": "project.started:"},
        "context": ["project", "decisions"],
    },
    "milestone.completed": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "milestone",
        "kind": "milestone_completed",
        "importance": "high",
        "fact_kind": "observation",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"milestone.completed:{ctx.get('milestone_id')}",
        "title": lambda ctx, payload: f"Milestone completed: {_title(ctx, 'unknown milestone')}",
        "summary": lambda ctx, payload: (
            f"Milestone '{_title(ctx, 'unknown milestone')}' was completed."
        ),
        "outcome_type": "positive",
        "context": ["project", "decisions"],
    },
    # -------------------------------------------------------------- decision
    "decision.made": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "decision",
        "kind": "decision_made",
        "importance": "high",
        "fact_kind": "fact",
        "base_confidence": 0.75,
        "dedupe": lambda ctx, payload: f"decision.made:{ctx.get('decision_id')}",
        "title": lambda ctx, payload: f"Decision: {_title(ctx, 'unknown decision')}",
        "summary": lambda ctx, payload: (
            f"A decision was recorded: '{_title(ctx, 'unknown decision')}'."
        ),
        "context": ["decision", "project"],
    },
    "decision.executed": {
        "memory_category": _MEMORY_CATEGORY_OUTCOME,
        "domain": "decision",
        "kind": "decision_executed",
        "importance": "medium",
        "fact_kind": "observation",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"decision.outcome:{ctx.get('decision_id')}",
        "requires_resolution": True,
        "resolves": {"dedupe_prefix": "decision.made:"},
        "outcome_type": "partial",
        "title": lambda ctx, payload: f"Decision executed: {_title(ctx, 'unknown decision')}",
        "outcome": lambda ctx, payload: (
            f"Decision '{_title(ctx, 'unknown decision')}' was executed: follow-up work started."
        ),
        "context": ["decision", "project"],
    },
    "decision.implemented": {
        "memory_category": _MEMORY_CATEGORY_OUTCOME,
        "domain": "decision",
        "kind": "decision_implemented",
        "importance": "high",
        "fact_kind": "observation",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"decision.outcome:{ctx.get('decision_id')}",
        "requires_resolution": True,
        "resolves": {"dedupe_prefix": "decision.made:"},
        "outcome_type": "positive",
        "title": lambda ctx, payload: f"Decision implemented: {_title(ctx, 'unknown decision')}",
        "outcome": lambda ctx, payload: (
            f"Decision '{_title(ctx, 'unknown decision')}' was fully implemented."
        ),
        "lesson": lambda ctx, payload: (
            f"Decision '{_title(ctx, 'unknown decision')}' was fully implemented. "
            "Decisions that reach implementation turn recorded intent into company capability."
        ),
        "context": ["decision", "project"],
    },
    # -------------------------------------------------------------- approval
    "approval.approved": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "approval",
        "kind": "approval_approved",
        "importance": "medium",
        "fact_kind": "observation",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"approval.approved:{ctx.get('approval_id')}",
        "title": lambda ctx, payload: f"Approval granted: {_title(ctx, 'unknown approval')}",
        "summary": lambda ctx, payload: (
            f"Approval '{_title(ctx, 'unknown approval')}' was granted."
        ),
        "outcome_type": "positive",
        "context": ["project"],
    },
    "approval.rejected": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "approval",
        "kind": "approval_rejected",
        "importance": "medium",
        "fact_kind": "observation",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"approval.rejected:{ctx.get('approval_id')}",
        "title": lambda ctx, payload: f"Approval denied: {_title(ctx, 'unknown approval')}",
        "summary": lambda ctx, payload: (
            f"Approval '{_title(ctx, 'unknown approval')}' was rejected."
        ),
        "outcome_type": "negative",
        "lesson": lambda ctx, payload: (
            f"Approval '{_title(ctx, 'unknown approval')}' was rejected. "
            "Rejected approvals should be reviewed before resubmission."
        ),
        "context": ["project"],
    },
    "policy.approved": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "policy",
        "kind": "policy_approved",
        "importance": "high",
        "fact_kind": "fact",
        "base_confidence": 0.8,
        "dedupe": lambda ctx, payload: f"policy.approved:{ctx.get('policy_id')}",
        "title": lambda ctx, payload: f"Policy approved: {_title(ctx, 'unknown policy')}",
        "summary": lambda ctx, payload: (
            f"Policy '{_title(ctx, 'unknown policy')}' was approved and is now in force."
        ),
        "context": ["project"],
    },
    # -------------------------------------------------------------- document
    "document.published": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "document",
        "kind": "document_published",
        "importance": "medium",
        "fact_kind": "fact",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"document.published:{ctx.get('document_id')}",
        "title": lambda ctx, payload: f"Document published: {_title(ctx, 'unknown document')}",
        "summary": lambda ctx, payload: (
            f"Document '{_title(ctx, 'unknown document')}' was published."
        ),
        "context": ["project"],
    },
    "wiki.published": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "document",
        "kind": "document_published",
        "importance": "medium",
        "fact_kind": "fact",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"wiki.published:{ctx.get('wiki_id')}",
        "title": lambda ctx, payload: f"Wiki published: {_title(ctx, 'unknown page')}",
        "summary": lambda ctx, payload: (
            f"Wiki page '{_title(ctx, 'unknown page')}' was published."
        ),
        "context": ["project"],
    },
    "sop.published": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "document",
        "kind": "document_published",
        "importance": "medium",
        "fact_kind": "fact",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"sop.published:{ctx.get('sop_id')}",
        "title": lambda ctx, payload: f"SOP published: {_title(ctx, 'unknown SOP')}",
        "summary": lambda ctx, payload: (
            f"SOP '{_title(ctx, 'unknown SOP')}' was published."
        ),
        "context": ["project"],
    },
    "template.published": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "document",
        "kind": "document_published",
        "importance": "medium",
        "fact_kind": "fact",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"template.published:{ctx.get('template_id')}",
        "title": lambda ctx, payload: f"Template published: {_title(ctx, 'unknown template')}",
        "summary": lambda ctx, payload: (
            f"Template '{_title(ctx, 'unknown template')}' was published."
        ),
        "context": ["project"],
    },
    # -------------------------------------------------------------- customer
    "ticket.escalated": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "customer",
        "kind": "customer_escalation",
        "importance": "high",
        "fact_kind": "observation",
        "base_confidence": 0.7,
        "dedupe": lambda ctx, payload: f"ticket.escalated:{ctx.get('ticket_id')}",
        "title": lambda ctx, payload: f"Support ticket escalated: {_title(ctx, 'unknown ticket')}",
        "summary": lambda ctx, payload: (
            f"Support ticket '{_title(ctx, 'unknown ticket')}' was escalated."
        ),
        "outcome_type": "unresolved",
        "lesson": lambda ctx, payload: (
            f"Support ticket '{_title(ctx, 'unknown ticket')}' escalated. "
            "Escalations signal service gaps worth reviewing after resolution."
        ),
        "context": ["project"],
    },
    "customer.renewed": {
        "memory_category": _MEMORY_CATEGORY_EXPERIENCE,
        "domain": "customer",
        "kind": "customer_renewed",
        "importance": "medium",
        "fact_kind": "fact",
        "base_confidence": 0.75,
        "dedupe": lambda ctx, payload: f"customer.renewed:{ctx.get('contract_id')}",
        "title": lambda ctx, payload: f"Customer renewed: {_title(ctx, 'unknown customer')}",
        "summary": lambda ctx, payload: (
            f"Customer '{_title(ctx, 'unknown customer')}' renewed their contract."
        ),
        "outcome_type": "positive",
        "context": ["project"],
    },
}

# Events that trigger memory formation (change-driven significance policy).
SIGNIFICANT_EVENTS: frozenset[str] = frozenset(_RULES.keys())


# ---------------------------------------------------------------------------
# Job enqueue (called from the event handler, inside the event transaction)
# ---------------------------------------------------------------------------


async def enqueue_formation(
    db: AsyncSession,
    *,
    organization_id: Optional[str],
    event_id: str,
    name: str,
) -> None:
    """Enqueue a ``memory.formation`` job for one event (idempotent)."""
    if name not in _RULES:
        return
    job = BackgroundJob(
        organization_id=organization_id,
        name=FORMATION_JOB,
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
        pass  # already enqueued — formation is idempotent


# ---------------------------------------------------------------------------
# Memory write helpers
# ---------------------------------------------------------------------------


def _dedupe_evidence(
    evidence: list[dict[str, Any]], new: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged = {f"{item['type']}:{item.get('id')}": item for item in evidence}
    for item in new:
        key = f"{item['type']}:{item.get('id')}"
        if item.get("relationship") and key in merged:
            continue
        merged[key] = item
    return list(merged.values())[-24:]


def _merge_ids(existing: Optional[list[str]], new: list[str]) -> list[str]:
    merged = list(existing or [])
    for value in new:
        if value and value not in merged:
            merged.append(value)
    return merged[-40:]


async def _find_open_by_entity(
    db: AsyncSession,
    *,
    organization_id: str,
    entity_type: str,
    entity_id: Optional[str],
    dedupe_prefix: str,
) -> Optional[CompanyMemory]:
    """Find the active memory an outcome resolves (bounded, indexed by dedupe)."""
    if not entity_id:
        return None
    row = (
        await db.execute(
            select(CompanyMemory)
            .where(
                CompanyMemory.organization_id == organization_id,
                CompanyMemory.dedupe_key.startswith(dedupe_prefix),
                CompanyMemory.status == "active",
            )
            .limit(50)
        )
    ).scalars().all()
    for memory in row:
        if memory.entity_type == entity_type and memory.entity_id == entity_id:
            return memory
    return None


async def _similarity(provider: Any, text_a: str, text_b: str) -> float:
    """Deterministic cosine similarity via the shared 4D.2 embedding provider."""
    try:
        vectors = await provider.embed_many([text_a or "", text_b or ""])
    except Exception:  # pragma: no cover - provider fallback
        return 0.0
    if len(vectors) != 2:
        return 0.0
    return provider.cosine(vectors[0], vectors[1])


async def _refresh_related(
    db: AsyncSession, *, organization_id: str, memory: CompanyMemory
) -> None:
    """Link semantically similar active memories (bounded top-K, no scans)."""
    from app.knowledge.embeddings import get_embedding_provider

    provider = get_embedding_provider()
    candidates = (
        await db.execute(
            select(CompanyMemory)
            .where(
                CompanyMemory.organization_id == organization_id,
                CompanyMemory.id != memory.id,
                CompanyMemory.status == "active",
                CompanyMemory.memory_category.in_(
                    (_MEMORY_CATEGORY_EXPERIENCE, _MEMORY_CATEGORY_LESSON)
                ),
            )
            .limit(120)
        )
    ).scalars().all()
    base = " ".join(
        part for part in (memory.title, memory.summary or "") if part
    )
    related: list[str] = []
    for candidate in candidates:
        if memory.auth_scope != candidate.auth_scope:
            continue
        if memory.auth_scope == "project" and memory.auth_project_id != candidate.auth_project_id:
            continue
        text = " ".join(
            part for part in (candidate.title, candidate.summary or "") if part
        )
        if await _similarity(provider, base, text) >= _SEMANTIC_RELATED_THRESHOLD:
            related.append(candidate.id)
        if len(related) >= _MAX_RELATED:
            break
    memory.related_memory_ids = related


def _memory_summary(memory: CompanyMemory) -> dict[str, Any]:
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
    }


async def _upsert_memory(
    db: AsyncSession,
    *,
    organization_id: str,
    rule: dict[str, Any],
    ctx: dict[str, Any],
    event: EventRow,
    payload: dict[str, Any],
    memory_category: str,
    domain: str,
    dedupe_key: str,
    entity_type: str,
    entity_id: Optional[str],
    title: str,
    summary: str,
    evidence: list[dict[str, Any]],
    scope: dict[str, Any],
    lesson: Optional[str] = None,
    outcome_type: Optional[str] = None,
    outcome: Optional[str] = None,
    resolves: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create or consolidate a memory under its org-scoped dedupe key.

    Consolidation (same key, later event): evidence is merged and source
    events appended — the memory grows, it is never silently rewritten.
    """
    row = (
        await db.execute(
            select(CompanyMemory)
            .where(
                CompanyMemory.organization_id == organization_id,
                CompanyMemory.dedupe_key == dedupe_key,
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    now = _now()
    confidence = rule.get("base_confidence", 0.6)
    if ctx.get("task") or ctx.get("project") or ctx.get("decision"):
        confidence = min(_CONFIDENCE_CAP, confidence + 0.25)
    if ctx.get("dependencies"):
        confidence = min(_CONFIDENCE_CAP, confidence + 0.05)

    if row is None:
        memory = CompanyMemory(
            organization_id=organization_id,
            memory_type=rule.get("kind", domain),
            title=title,
            summary=summary,
            memory_category=memory_category,
            domain=domain,
            entity_type=entity_type,
            entity_id=entity_id,
            source_event=event.name,
            source_event_ids=[event.id],
            evidence_json=evidence,
            context_json=ctx.get("context_json") or {},
            lesson=lesson,
            outcome=outcome,
            outcome_type=outcome_type,
            confidence=confidence,
            fact_kind=rule.get("fact_kind", "observation"),
            importance=rule.get("importance", "medium"),
            dedupe_key=dedupe_key,
            auth_scope=scope.get("auth_scope", "org"),
            auth_project_id=scope.get("auth_project_id"),
            auth_scope_id=scope.get("auth_scope_id"),
            status="active",
            occurred_at=event.occurred_at or now,
        )
        db.add(memory)
        await db.flush()
    else:
        # Consolidation: merge evidence + source events, refresh context and
        # apply outcome progression. History is preserved, never rewritten.
        row.evidence_json = _dedupe_evidence(row.evidence_json or [], evidence)
        row.source_event_ids = _merge_ids(row.source_event_ids, [event.id])
        row.context_json = {**(row.context_json or {}), **(ctx.get("context_json") or {})}
        row.summary = summary or row.summary
        if lesson:
            row.lesson = lesson if not row.lesson else row.lesson
        if outcome_type and _OUTCOME_RANK.get(outcome_type, 0) > _OUTCOME_RANK.get(row.outcome_type or "", 0):
            # Outcome evolution: a later event upgrades the observed outcome
            # (e.g. partial execution -> fully implemented). History is kept
            # in memory_outcomes; the memory itself carries the latest state.
            row.outcome = outcome
            row.outcome_type = outcome_type
            row.confidence = min(_CONFIDENCE_CAP, row.confidence + 0.05)
        if not row.occurred_at:
            row.occurred_at = event.occurred_at or now
        memory = row
        await db.flush()

    # Idempotent lineage link: one event may feed a memory exactly once.
    existing_link = (
        await db.execute(
            select(MemoryEvent).where(MemoryEvent.event_id == event.id).limit(1)
        )
    ).scalar_one_or_none()
    if existing_link is None:
        db.add(
            MemoryEvent(
                organization_id=organization_id,
                memory_id=memory.id,
                event_id=event.id,
                relationship=resolves.get("relationship", "formation") if resolves else "formation",
            )
        )

    await _refresh_related(db, organization_id=organization_id, memory=memory)
    await db.flush()
    return _memory_summary(memory)


async def record_decision_lesson(
    db: AsyncSession, *, organization_id: str, event: EventRow,
    decision: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Slice 4H.1 — a closed company decision loop derives its lesson memory.

    The lesson is explicitly ``lesson``-labeled (guidance derived from
    evidence, never a fact) with evidence lineage back to the CompanyDecision.
    Exact-once on the ``lesson:decision:{decision_id}`` dedupe key.
    """
    lesson_text = (decision.get("lesson") or "").strip()
    decision_id = decision.get("decision_id") or ""
    title = (decision.get("title") or "").strip() or "company decision"
    if not lesson_text or not decision_id:
        return None
    rule = {
        "kind": "decision_lesson",
        "base_confidence": 0.6,
        "fact_kind": "lesson",
        "importance": "high",
    }
    ctx = {
        "decision": {"id": decision_id},
        "context_json": {
            "decision_id": decision_id,
            "kind": decision.get("kind"),
            "title": title,
        },
    }
    scope = {"auth_scope": "org", "auth_project_id": None, "auth_scope_id": None}
    return await _upsert_memory(
        db,
        organization_id=organization_id,
        rule=rule,
        ctx=ctx,
        event=event,
        payload={},
        memory_category="decision_lesson",
        domain="company",
        dedupe_key=f"lesson:decision:{decision_id}",
        entity_type="decision",
        entity_id=decision_id,
        title=title,
        summary=_snippet(lesson_text, 300),
        evidence=[
            {
                "entity": "decision",
                "id": decision_id,
                "label": title,
                "kind": "company_decision",
            }
        ],
        scope=scope,
        lesson=lesson_text,
        outcome_type=decision.get("outcome_kind") or None,
        outcome=lesson_text,
    )


async def _record_outcome(
    db: AsyncSession,
    *,
    organization_id: str,
    memory: CompanyMemory,
    rule: dict[str, Any],
    ctx: dict[str, Any],
    event: EventRow,
    payload: dict[str, Any],
    outcome_type: str,
    outcome: Optional[str],
) -> None:
    """Attach an observed outcome to a memory (outcome feedback loop)."""
    from app.models.company_memory import MemoryOutcome

    if _OUTCOME_RANK.get(outcome_type, 0) > _OUTCOME_RANK.get(memory.outcome_type or "", 0):
        memory.outcome = outcome
        memory.outcome_type = outcome_type
        memory.confidence = min(_CONFIDENCE_CAP, memory.confidence + 0.05)
    db.add(
        MemoryOutcome(
            organization_id=organization_id,
            memory_id=memory.id,
            applied_entity_type=memory.entity_type,
            applied_entity_id=memory.entity_id,
            outcome_type=outcome_type,
            outcome=outcome,
            evidence_json=[
                {"type": "event", "id": event.id, "relationship": event.name}
            ],
            occurred_at=event.occurred_at,
        )
    )
    await db.flush()


async def _derive_lesson_memory(
    db: AsyncSession,
    *,
    organization_id: str,
    rule: dict[str, Any],
    ctx: dict[str, Any],
    event: EventRow,
    payload: dict[str, Any],
    source_memory: CompanyMemory,
    lesson_text: Optional[str],
) -> Optional[CompanyMemory]:
    """Create (or refresh) the lesson memory for an experience.

    Lesson memories are explicitly labeled ``lesson`` — they are guidance
    derived from evidence, never facts.
    """
    if not lesson_text:
        return None
    dedupe_key = (
        f"lesson:{source_memory.domain}:{source_memory.entity_id or source_memory.entity_type}"
    )
    row = (
        await db.execute(
            select(CompanyMemory)
            .where(
                CompanyMemory.organization_id == organization_id,
                CompanyMemory.dedupe_key == dedupe_key,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    lesson_text = _snippet(lesson_text, 500)
    if row is None:
        memory = CompanyMemory(
            organization_id=organization_id,
            memory_type=f"lesson_{source_memory.domain}",
            title=source_memory.title,
            summary=f"Lesson learned from '{source_memory.title}'",
            memory_category=_MEMORY_CATEGORY_LESSON,
            domain=source_memory.domain,
            entity_type=source_memory.entity_type,
            entity_id=source_memory.entity_id,
            source_event=event.name,
            source_event_ids=[event.id],
            evidence_json=[{"type": "event", "id": event.id, "relationship": event.name}],
            context_json={},
            lesson=lesson_text,
            confidence=min(_CONFIDENCE_CAP, source_memory.confidence),
            fact_kind="lesson",
            importance=source_memory.importance,
            dedupe_key=dedupe_key,
            auth_scope=source_memory.auth_scope,
            auth_project_id=source_memory.auth_project_id,
            auth_scope_id=source_memory.auth_scope_id,
            status="active",
            occurred_at=event.occurred_at,
        )
        db.add(memory)
        await db.flush()
    else:
        row.lesson = lesson_text
        row.source_event_ids = _merge_ids(row.source_event_ids, [event.id])
        row.evidence_json = _dedupe_evidence(
            row.evidence_json or [],
            [{"type": "event", "id": event.id, "relationship": event.name}],
        )
        memory = row
    return memory


# ---------------------------------------------------------------------------
# The formation pipeline (per event)
# ---------------------------------------------------------------------------


async def process_event(
    db: AsyncSession, *, event: EventRow
) -> Optional[dict[str, Any]]:
    """Form memory from one event. Idempotent: a fed event is never reprocessed.

    Returns a small trace dict (or ``None`` when the event was skipped).
    """
    rule = _RULES.get(event.name)
    if rule is None:
        return None
    payload = _payload(event)
    organization_id = event.organization_id or payload.get("organization_id")
    if not organization_id:
        return None

    # Idempotency guard: this exact event has already fed a memory.
    already = (
        await db.execute(select(MemoryEvent).where(MemoryEvent.event_id == event.id).limit(1))
    ).scalar_one_or_none()
    if already is not None:
        return {"event_id": event.id, "memory_id": already.memory_id, "skipped": True}

    task_id = _first(payload, "task_id", "id") if event.name.startswith("task.") else None
    project_id = (
        _first(payload, "project_id") or (_first(payload, "id") if event.name.startswith("project.") else None)
    )
    decision_id = _first(payload, "decision_id") if event.name.startswith("decision.") else None
    milestone_id = _first(payload, "milestone_id") if event.name.startswith("milestone.") else None

    if event.name == "task.commented":
        return await _process_context_only(db, event, rule, payload, organization_id, task_id)

    ctx: dict[str, Any] = {}
    if task_id:
        ctx["task"] = await _task(db, organization_id, task_id)
        ctx["task_id"] = task_id
        if ctx["task"] and not project_id:
            project_id = ctx["task"].get("project_id")
    if project_id:
        ctx["project"] = await _project(db, organization_id, project_id)
        ctx["project_id"] = project_id
    if decision_id:
        ctx["decision"] = await _decision(db, organization_id, decision_id)
        ctx["decision_id"] = decision_id
    if milestone_id:
        ctx["milestone_id"] = milestone_id

    employee_id = _first(payload, "assignee_id", "owner_id", "decision_maker_id")
    if employee_id:
        ctx["employee"] = await _employee(db, organization_id, employee_id)
    if task_id:
        ctx["dependencies"] = await _dependencies(db, organization_id, task_id)
    if ctx.get("project_id"):
        ctx["decisions"] = await _decisions(db, organization_id, ctx["project_id"])
    if task_id:
        ctx["comments"] = await _comments(db, organization_id, task_id)

    scope = await _resolve_project_scope(db, organization_id, ctx.get("project_id"))
    context_json: dict[str, Any] = {"project": ctx.get("project") or {}}
    if ctx.get("task"):
        context_json["task"] = {
            k: ctx["task"][k] for k in ("id", "title", "status", "priority", "tags")
        }
    if ctx.get("employee"):
        context_json["assignee"] = ctx["employee"]
    if ctx.get("dependencies"):
        context_json["dependencies"] = ctx["dependencies"]
    if ctx.get("decisions"):
        context_json["decisions"] = ctx["decisions"]
    if ctx.get("comments"):
        context_json["discussion"] = [
            {"author_id": c["author_id"], "body": c["body"]} for c in ctx["comments"][:3]
        ]
    ctx["context_json"] = context_json

    evidence: list[dict[str, Any]] = [
        {"type": "event", "id": event.id, "relationship": event.name}
    ]
    if task_id:
        evidence.append({"type": "task", "id": task_id, "relationship": "entity"})
    if ctx.get("project_id"):
        evidence.append({"type": "project", "id": ctx["project_id"], "relationship": "project"})
    if decision_id:
        evidence.append({"type": "decision", "id": decision_id, "relationship": "decision"})
    if ctx.get("dependencies"):
        evidence.append(
            {
                "type": "dependency",
                "id": ctx["dependencies"][0]["id"],
                "relationship": "blocking_dependency",
            }
        )

    entity_type, entity_id = _rule_entity(event.name, ctx, payload)
    dedupe_key = rule["dedupe"](ctx, payload)
    title = rule["title"](ctx, payload)
    outcome_type = rule.get("outcome_type")
    outcome = rule.get("outcome")(ctx, payload) if rule.get("outcome") else None
    summary_rule = rule.get("summary")
    summary = summary_rule(ctx, payload) if summary_rule else (outcome or title)
    lesson_text = rule.get("lesson")(ctx, payload) if rule.get("lesson") else None

    resolves_rule = rule.get("resolves")
    resolved_memory = None
    if resolves_rule:
        resolved_memory = await _find_open_by_entity(
            db,
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            dedupe_prefix=resolves_rule["dedupe_prefix"],
        )
        if resolved_memory is not None and outcome_type and outcome:
            await _record_outcome(
                db,
                organization_id=organization_id,
                memory=resolved_memory,
                rule=rule,
                ctx=ctx,
                event=event,
                payload=payload,
                outcome_type=outcome_type,
                outcome=outcome,
            )

    if rule.get("requires_resolution") and resolved_memory is None:
        # Outcome-only event (task completed / decision implemented) with no
        # open experience to resolve is routine progress, not memory.
        return {"event_id": event.id, "skipped": "no_experience_to_resolve"}

    supersedes_rule = rule.get("supersedes")
    superseded = None
    if supersedes_rule:
        superseded = await _find_open_by_entity(
            db,
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            dedupe_prefix=supersedes_rule["dedupe_prefix"],
        )

    result = await _upsert_memory(
        db,
        organization_id=organization_id,
        rule=rule,
        ctx=ctx,
        event=event,
        payload=payload,
        memory_category=rule["memory_category"],
        domain=rule["domain"],
        dedupe_key=dedupe_key,
        entity_type=entity_type,
        entity_id=entity_id,
        title=title,
        summary=summary,
        evidence=evidence,
        scope=scope,
        lesson=lesson_text,
        outcome_type=outcome_type,
        outcome=outcome,
        resolves=resolves_rule,
    )

    if superseded is not None and superseded.id != result["id"]:
        superseded.status = "superseded"
        superseded.supersedes_id = result["id"]

    if resolved_memory is not None and lesson_text:
        await _derive_lesson_memory(
            db,
            organization_id=organization_id,
            rule=rule,
            ctx=ctx,
            event=event,
            payload=payload,
            source_memory=resolved_memory,
            lesson_text=lesson_text,
        )

    await db.flush()
    return {
        "event_id": event.id,
        "memory_id": result["id"],
        "memory_category": result["memory_category"],
        "domain": result["domain"],
        "confidence": result["confidence"],
        "outcome_type": result["outcome_type"],
    }


async def _process_context_only(
    db: AsyncSession,
    event: EventRow,
    rule: dict[str, Any],
    payload: dict[str, Any],
    organization_id: str,
    task_id: Optional[str],
) -> Optional[dict[str, Any]]:
    """task.commented: enrich the open blocked-task memory with discussion.

    Context-only — no new memory is formed; the blocked-task experience gains
    the latest discussion and evidence of the conversation.
    """
    updates_rule = rule.get("updates")
    if not updates_rule or not task_id:
        return None
    target = await _find_open_by_entity(
        db,
        organization_id=organization_id,
        entity_type="task",
        entity_id=task_id,
        dedupe_prefix=updates_rule["dedupe_prefix"],
    )
    if target is None:
        return {"event_id": event.id, "skipped": "no_open_experience"}
    comments = await _comments(db, organization_id, task_id)
    context_json = dict(target.context_json or {})
    context_json["discussion"] = [
        {"author_id": c["author_id"], "body": c["body"]} for c in comments[:3]
    ]
    target.context_json = context_json
    target.source_event_ids = _merge_ids(target.source_event_ids, [event.id])
    target.evidence_json = _dedupe_evidence(
        target.evidence_json or [],
        [
            {"type": "event", "id": event.id, "relationship": event.name},
            {"type": "task", "id": task_id, "relationship": "entity"},
        ],
    )
    link = MemoryEvent(
        organization_id=organization_id,
        memory_id=target.id,
        event_id=event.id,
        relationship="update",
    )
    db.add(link)
    await db.flush()
    return {"event_id": event.id, "memory_id": target.id, "relationship": "update"}


def _rule_entity(
    event_name: str, ctx: dict[str, Any], payload: dict[str, Any]
) -> tuple[str, Optional[str]]:
    if event_name.startswith("task."):
        return "task", ctx.get("task_id")
    if event_name.startswith("project."):
        return "project", ctx.get("project_id")
    if event_name.startswith("decision."):
        return "decision", ctx.get("decision_id")
    if event_name.startswith("milestone."):
        return "milestone", ctx.get("milestone_id")
    if event_name.startswith("approval."):
        return "approval", _first(payload, "approval_id")
    if event_name.startswith("policy."):
        return "policy", _first(payload, "policy_id")
    if event_name in ("document.published", "wiki.published", "sop.published", "template.published"):
        key = {"document.published": "document_id", "wiki.published": "wiki_id",
               "sop.published": "sop_id", "template.published": "template_id"}[event_name]
        return "document", _first(payload, key)
    if event_name in ("ticket.escalated",):
        return "ticket", _first(payload, "ticket_id")
    if event_name == "customer.renewed":
        return "customer", _first(payload, "customer_id")
    return "event", None


async def _decision(
    db: AsyncSession, organization_id: str, decision_id: Optional[str]
) -> Optional[dict]:
    if not decision_id:
        return None
    from app.models.knowledge import Decision

    row = await db.get(Decision, decision_id)
    if row is None or row.organization_id != organization_id:
        return None
    return {
        "id": row.id,
        "title": row.title,
        "status": row.status,
        "project_id": row.project_id,
    }
