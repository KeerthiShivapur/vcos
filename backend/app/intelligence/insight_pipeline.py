"""Slice 4D.5 — universal company insight intelligence pipeline.

Composition layer above Slices 4D.1–4D.4: it connects patterns, memories,
decisions, approvals, tasks, dependencies and the governance tree into one
canonical, evidence-backed, governance-scoped ``UniversalInsight``.

    event -> insight.evaluate job -> bounded neighborhood collection
          -> rule evaluation (9 insight types) -> evidence lineage
          -> compositional confidence -> upsert -> insight.* event

Design laws (mirroring Slices 4D.3 / 4D.4):

- **Change-driven, never scanned**: an observable event (pattern.*,
  ``memory.recorded``, ``decision.made``, ``approval.*``) enqueues exactly one
  ``insight.evaluate`` job (idempotent under the ``(name, event_id)`` job
  uniqueness). There is no organization-wide reasoning pass. Fade/resolve is a
  bounded, indexed sweep.
- **Observation only, never prescription**: an insight states what is
  happening in the organization and *why VCOS believes it* (compositional
  confidence components + evidence lineage). It never recommends, predicts,
  or mutates any operating-layer entity.
- **Composition over creation**: insights are composed from existing patterns
  and memories, never invented by the pipeline. A candidate needs a supporting
  pattern or supporting memory (or an undecided decision / pending approval).
- **Evidence lineage & exactly-once**: every evaluation links its source event
  through ``InsightEvent`` (replay-safe) so replays never double-count.
- **Governance inheritance**: a project-anchored insight inherits the
  project's governance scope; org-anchored insights (governance / employee
  concentration) are organization-wide. Read surface mirrors
  ``pattern_engine`` visibility.
- **Bounded everything**: each evaluation reads a small indexed, capped
  neighborhood around one event (never a scan).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select

from app.db.database import AsyncSession
from app.models.company_memory import CompanyMemory
from app.models.intelligence import (
    BackgroundJob,
    InsightEvent,
    PatternDetection,
    UniversalInsight,
)
from app.models.notification import Event as EventRow

logger = logging.getLogger("vcos.intelligence.insights")

# Job family for change-driven insight evaluation.
EVALUATE_JOB = "insight.evaluate"

# Events that can feed insight composition (change-driven significance policy).
TRIGGER_EVENTS: frozenset[str] = frozenset(
    {
        "pattern.detected",
        "pattern.updated",
        "pattern.confirmed",
        "pattern.faded",
        "pattern.resolved",
        "memory.recorded",
        "decision.made",
        "approval.requested",
        "approval.approved",
        "approval.rejected",
    }
)

# How each trigger event seeds the component candidates.
_SEED_KEY = {
    "pattern.detected": "pattern_id",
    "pattern.updated": "pattern_id",
    "pattern.confirmed": "pattern_id",
    "pattern.faded": "pattern_id",
    "pattern.resolved": "pattern_id",
    "memory.recorded": "memory_id",
    "decision.made": "decision_id",
    "approval.requested": "approval_id",
    "approval.approved": "approval_id",
    "approval.rejected": "approval_id",
}

# Maximum number of candidate insights produced from one evaluation.
CANDIDATE_LIMIT = 9

# Bounded neighborhood caps.
MAX_PATTERNS = 8
MAX_MEMORIES = 10
MAX_DECISIONS = 6
MAX_APPROVALS = 6
MAX_TASKS = 40
MAX_DEPENDENCIES = 30

# Lifecycle windows (mirror 4D.4 fading).
FADING_AFTER_DAYS = 14
RESOLVED_AFTER_DAYS = 30
ORPHAN_RESOLVED_DAYS = 60

# Confidence weights (compositional, self-explaining).
W_OCCURRENCE = 0.35
W_EVIDENCE = 0.20
W_PATTERN = 0.20
W_MEMORY = 0.15
W_RECENCY = 0.10

# Pattern families that signal each insight dimension.
EXECUTION_PATTERNS = frozenset(
    {
        "repeated_delay",
        "repeated_blocker",
        "dependency_failure",
        "handoff_failure",
        "milestone_slippage",
        "ownership_change_delay",
    }
)
DECISION_PATTERNS = frozenset(
    {
        "decision_reversal",
        "decision_delay",
        "decision_without_execution",
    }
)
GOVERNANCE_PATTERNS = frozenset(
    {
        "repeated_approval_dependency",
        "approval_bottleneck",
        "governance_friction",
        "scope_assignment_churn",
        "delegation_dependency",
    }
)
COMMUNICATION_PATTERNS = frozenset(
    {
        "communication_breakdown",
        "repeated_unresolved_discussion",
    }
)
KNOWLEDGE_PATTERNS = frozenset(
    {
        "knowledge_gap",
        "repeated_document_lookup",
        "missing_knowledge_dependency",
    }
)
ORGANIZATION_PATTERNS = frozenset(
    {
        "ownership_ambiguity",
        "repeated_cross_team_bottleneck",
        "collaboration_bottleneck",
        "concentration_risk",
    }
)

ACTIVE_PATTERN_STATUSES = ("candidate", "emerging", "confirmed", "persistent", "fading")


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
    """Enqueue an ``insight.evaluate`` job for one event (idempotent)."""
    if name not in TRIGGER_EVENTS:
        return
    job = BackgroundJob(
        organization_id=organization_id,
        name=EVALUATE_JOB,
        status="queued",
        event_id=event_id,
        payload_json=json.dumps({"name": name, "event_id": event_id}),
    )
    try:
        async with db.begin_nested():
            db.add(job)
            await db.flush()
    except Exception:
        pass  # already enqueued — evaluation is idempotent


# ---------------------------------------------------------------------------
# Bounded neighborhood collector (indexed, capped — never a scan)
# ---------------------------------------------------------------------------


async def _collect_neighborhood(
    db: AsyncSession,
    event: EventRow,
    payload: dict[str, Any],
    organization_id: str,
) -> dict[str, Any]:
    """Resolve the bounded component neighborhood for one event."""
    name = event.name
    ctx: dict[str, Any] = {"event_name": name, "seen_patterns": [], "seen_memories": []}

    pattern_id = _first(payload, "pattern_id") if name.startswith("pattern.") else None
    if pattern_id:
        pattern = await db.get(PatternDetection, pattern_id)
        if pattern is not None and pattern.organization_id == organization_id:
            ctx["seen_patterns"].append(pattern)

    memory_id = _first(payload, "memory_id") if name == "memory.recorded" else None
    if memory_id:
        memory = await db.get(CompanyMemory, memory_id)
        if memory is not None and memory.organization_id == organization_id:
            ctx["seen_memories"].append(memory)

    approval_id = _first(payload, "approval_id") if name.startswith("approval.") else None
    if approval_id:
        from app.models.approval import Approval

        approval = await db.get(Approval, approval_id)
        if approval is not None and approval.organization_id == organization_id:
            ctx["approval"] = approval

    decision_id = _first(payload, "decision_id") if name == "decision.made" else None
    if decision_id:
        from app.models.knowledge import Decision

        decision = await db.get(Decision, decision_id)
        if decision is not None and decision.organization_id == organization_id:
            ctx["decision"] = decision

    # --- resolve the anchor project (bounded lookups) -----------------------
    anchor_ids: list[str] = []
    for pattern in ctx["seen_patterns"]:
        pid = pattern.auth_project_id or (
            pattern.scope_type == "project" and pattern.scope_id
        )
        if pid:
            anchor_ids.append(pid)
    for memory in ctx["seen_memories"]:
        pid = memory.auth_project_id or memory.auth_scope_id
        if pid:
            anchor_ids.append(pid)
    if ctx.get("decision"):
        pid = ctx["decision"].project_id
        if pid:
            anchor_ids.append(pid)
    approval = ctx.get("approval")
    if approval is not None:
        pid = await _project_id_for_anchor(
            db, organization_id, approval.entity_type, approval.entity_id
        )
        if pid:
            anchor_ids.append(pid)
    if not anchor_ids:
        return ctx
    project_id = anchor_ids[0]
    ctx["project_id"] = project_id

    from app.models.governance import GovernanceScope
    from app.models.project import Project
    from app.models.task import Task, TaskDependency

    project = await db.get(Project, project_id)
    if project is None or project.organization_id != organization_id:
        ctx.pop("project_id", None)
        return ctx
    ctx["project"] = {"id": project.id, "name": project.name, "status": project.status}

    scope = (
        await db.execute(
            select(GovernanceScope).where(
                GovernanceScope.organization_id == organization_id,
                GovernanceScope.scope_type == "project",
                GovernanceScope.entity_id == project_id,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if scope is not None:
        ctx["scope_id"] = scope.id

    task_ids = list(
        (
            await db.execute(
                select(Task.id)
                .where(
                    Task.organization_id == organization_id,
                    Task.project_id == project_id,
                )
                .limit(200)
            )
        ).scalars().all()
    )
    blocked_tasks = (
        await db.execute(
            select(Task)
            .where(
                Task.organization_id == organization_id,
                Task.project_id == project_id,
                Task.id.in_(task_ids or [""]),
                Task.status.in_(["blocked"]),
            )
            .order_by(Task.updated_at.desc())
            .limit(MAX_TASKS)
        )
    ).scalars().all()
    ctx["blocked_tasks"] = [
        {
            "id": task.id,
            "title": _snippet(task.title, 120),
            "status": task.status,
            "assignee_id": task.assignee_id,
        }
        for task in blocked_tasks
    ]

    if task_ids:
        dep_rows = (
            await db.execute(
                select(TaskDependency)
                .where(
                    TaskDependency.organization_id == organization_id,
                    TaskDependency.task_id.in_(task_ids),
                )
                .limit(MAX_DEPENDENCIES)
            )
        ).scalars().all()
        ctx["dependencies"] = [
            {
                "id": dep.id,
                "task_id": dep.task_id,
                "depends_on": dep.depends_on,
            }
            for dep in dep_rows
        ]

    ctx["patterns"] = list(
        (
            await db.execute(
                select(PatternDetection)
                .where(
                    PatternDetection.organization_id == organization_id,
                    PatternDetection.auth_project_id == project_id,
                    PatternDetection.status.in_(ACTIVE_PATTERN_STATUSES),
                )
                .order_by(PatternDetection.confidence.desc())
                .limit(MAX_PATTERNS)
            )
        ).scalars().all()
    )
    ctx["memories"] = list(
        (
            await db.execute(
                select(CompanyMemory)
                .where(
                    CompanyMemory.organization_id == organization_id,
                    CompanyMemory.auth_project_id == project_id,
                    CompanyMemory.status == "active",
                )
                .order_by(CompanyMemory.importance.desc(), CompanyMemory.created_at.desc())
                .limit(MAX_MEMORIES)
            )
        ).scalars().all()
    )

    from app.models.knowledge import Decision

    decisions = (
        await db.execute(
            select(Decision)
            .where(
                Decision.organization_id == organization_id,
                Decision.project_id == project_id,
            )
            .order_by(Decision.created_at.desc())
            .limit(MAX_DECISIONS)
        )
    ).scalars().all()
    decision_dicts = [
        {
            "id": d.id,
            "title": _snippet(d.title, 120),
            "status": d.status,
            "decision_maker_id": d.decision_maker_id,
        }
        for d in decisions
    ]
    ctx["decisions"] = decision_dicts

    from app.models.approval import Approval

    entity_or = [
        (Approval.entity_type == "project") & (Approval.entity_id == project_id)
    ]
    if task_ids:
        entity_or.append(
            (Approval.entity_type == "task") & (Approval.entity_id.in_(task_ids))
        )
    if decision_dicts:
        entity_or.append(
            (Approval.entity_type == "decision")
            & (Approval.entity_id.in_([d["id"] for d in decision_dicts]))
        )
    approvals = (
        await db.execute(
            select(Approval)
            .where(
                Approval.organization_id == organization_id,
                Approval.status == "pending",
                __import__("sqlalchemy").or_(*entity_or),
            )
            .order_by(Approval.created_at.asc())
            .limit(MAX_APPROVALS)
        )
    ).scalars().all()
    ctx["approvals"] = [
        {
            "id": a.id,
            "title": _snippet(a.title, 120),
            "status": a.status,
            "approval_type": a.approval_type,
            "requester_id": a.requester_id,
            "approver_id": a.approver_id,
            "due_at": a.due_at,
            "created_at": a.created_at,
        }
        for a in approvals
    ]

    # Employee concentration (bounded local tally).
    counts: dict[str, int] = {}
    for task in ctx["blocked_tasks"]:
        if task.get("assignee_id"):
            counts[task["assignee_id"]] = counts.get(task["assignee_id"], 0) + 1
    for approval in ctx["approvals"]:
        for key in ("requester_id", "approver_id"):
            value = approval.get(key)
            if value:
                counts[value] = counts.get(value, 0) + 1
    if counts:
        ctx["employee_concentration"] = max(counts.items(), key=lambda kv: kv[1])
    return ctx


async def _project_id_for_anchor(
    db: AsyncSession, organization_id: str, entity_type: Optional[str], entity_id: Optional[str]
) -> Optional[str]:
    if not entity_type or not entity_id:
        return None
    if entity_type == "project":
        return entity_id
    if entity_type == "task":
        from app.models.project import Task

        row = await db.get(Task, entity_id)
        return row.project_id if row is not None else None
    if entity_type == "decision":
        from app.models.knowledge import Decision

        row = await db.get(Decision, entity_id)
        return row.project_id if row is not None else None
    return None


# ---------------------------------------------------------------------------
# Rule evaluation — one bounded candidate per rule (composition only)
# ---------------------------------------------------------------------------


def _evidence(
    *,
    kind: str,
    id: str,
    title: str,
    meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"type": kind, "id": id, "title": title, "relationship": "supports"}
    if meta:
        item["meta"] = meta
    return item


def _pattern_item(pattern: PatternDetection) -> dict[str, Any]:
    return _evidence(
        kind="pattern",
        id=pattern.id,
        title=_snippet(pattern.title, 120),
        meta={
            "pattern_type": pattern.pattern_type,
            "status": pattern.status,
            "count": pattern.count,
            "confidence": round(pattern.confidence or 0.0, 3),
        },
    )


def _memory_item(memory: CompanyMemory) -> dict[str, Any]:
    return _evidence(
        kind="memory",
        id=memory.id,
        title=_snippet(memory.title, 120),
        meta={
            "memory_category": memory.memory_category,
            "importance": memory.importance,
        },
    )


def _domain_counts(ctx: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pattern in ctx.get("patterns", []):
        family = getattr(pattern, "family", None) or "pattern"
        counts[family] = counts.get(family, 0) + 1
    for memory in ctx.get("memories", []):
        domain = getattr(memory, "memory_type", None) or memory.memory_category
        counts[f"memory:{domain}"] = counts.get(f"memory:{domain}", 0) + 1
    for decision in ctx.get("decisions", []):
        counts["decision"] = counts.get("decision", 0) + 1
    for approval in ctx.get("approvals", []):
        counts[f"approval:{approval['approval_type']}"] = (
            counts.get(f"approval:{approval['approval_type']}", 0) + 1
        )
    return counts


def _rule_execution_bottleneck(ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    patterns = [
        p for p in ctx.get("patterns", [])
        if p.pattern_type in EXECUTION_PATTERNS and p.status != "fading"
    ]
    if not patterns and not ctx.get("blocked_tasks"):
        return None
    blocked = ctx.get("blocked_tasks", [])
    dependencies = ctx.get("dependencies", [])
    decisions = ctx.get("decisions", [])
    approvals = ctx.get("approvals", [])
    key = f"project:{ctx['project_id']}"
    title = f"{ctx['project']['name']} shows execution bottlenecks"
    summary_parts: list[str] = []
    if patterns:
        summary_parts.append(
            f"{len(patterns)} recurring execution pattern(s) observed"
        )
    if blocked:
        summary_parts.append(f"{len(blocked)} task(s) currently blocked")
    evidence: list[dict[str, Any]] = (
        [_pattern_item(p) for p in patterns[:4]]
        + [_evidence(kind="task", id=t["id"], title=t["title"], meta={"status": t["status"]}) for t in blocked[:4]]
    )
    for dep in dependencies[:3]:
        evidence.append(_evidence(kind="dependency", id=dep["id"], title=f"Task {dep['task_id']} depends on {dep['depends_on']}"))
    for d in decisions[:2]:
        evidence.append(_evidence(kind="decision", id=d["id"], title=d["title"], meta={"status": d["status"]}))
    for a in approvals[:3]:
        evidence.append(_evidence(kind="approval", id=a["id"], title=a["title"], meta={"status": a["status"]}))
    return {
        "insight_type": "execution_bottleneck",
        "domain": "execution",
        "key": key,
        "title": title,
        "claim": f"{ctx['project']['name']} is experiencing a recurring execution bottleneck",
        "summary": "; ".join(summary_parts) or f"{len(evidence)} signals observed",
        "severity": "warning" if (len(patterns) >= 2 or len(blocked) >= 3 or len(dependencies) >= 3) else "info",
        "evidence": evidence[:8],
        "pattern_ids": [p.id for p in patterns],
        "memory_ids": [],
        "entities": [{"type": "project", "id": ctx["project_id"], "title": ctx["project"]["name"]}],
    }


def _rule_decision_bottleneck(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    patterns = [p for p in ctx.get("patterns", []) if p.pattern_type in DECISION_PATTERNS]
    pending_decisions = [
        d for d in ctx.get("decisions", []) if d["status"] not in ("made", "rejected")
    ]
    if not patterns and not pending_decisions:
        return []
    results: list[dict[str, Any]] = []
    deadline = _now() - timedelta(days=1)
    risky = [
        d for d in pending_decisions if (d.get("decision_maker_id")) and not any(
            a["entity_type"] == "decision" and a["entity_id"] == d["id"] for a in ctx.get("approvals", [])
        )
    ]
    blocked = ctx.get("blocked_tasks", [])
    for decision in (risky or pending_decisions)[:2]:
        evidence: list[dict[str, Any]] = [
            _evidence(kind="decision", id=decision["id"], title=decision["title"], meta={"status": decision["status"]})
        ]
        for p in patterns[:2]:
            evidence.append(_pattern_item(p))
        for t in blocked[:2]:
            evidence.append(_evidence(kind="task", id=t["id"], title=t["title"], meta={"status": t["status"]}))
        severity = "warning" if patterns else "info"
        results.append(
            {
                "insight_type": "decision_bottleneck",
                "domain": "decision",
                "key": f"decision:{decision['id']}",
                "title": f"Decision '{_snippet(decision['title'], 60)}' is waiting",
                "claim": f"Decision '{_snippet(decision['title'], 80)}' is still pending while downstream work shows signs of stalling",
                "summary": (
                    f"Decision has not been made; {len(patterns)} decision pattern(s) and "
                    f"{len(blocked)} blocked task(s) observed"
                ),
                "severity": severity,
                "evidence": evidence[:6],
                "pattern_ids": [p.id for p in patterns],
                "memory_ids": [],
                "entities": [
                    {"type": "decision", "id": decision["id"], "title": decision["title"]},
                    {"type": "project", "id": ctx["project_id"], "title": ctx["project"]["name"]},
                ],
            }
        )
        if len(results) >= CANDIDATE_LIMIT:
            break
    return results


def _rule_governance_bottleneck(ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    patterns = [p for p in ctx.get("patterns", []) if p.pattern_type in GOVERNANCE_PATTERNS]
    approvals = ctx.get("approvals", [])
    if not patterns and not approvals:
        return None
    now = _now()
    overdue = [a for a in approvals if (a["due_at"] and a["due_at"] < now) or (a["created_at"] and a["created_at"] < now - timedelta(days=1))]
    evidence: list[dict[str, Any]] = []
    for p in patterns[:3]:
        evidence.append(_pattern_item(p))
    for a in approvals[:4]:
        evidence.append(
            _evidence(
                kind="approval", id=a["id"], title=a["title"],
                meta={"status": a["status"], "due_at": (a["due_at"].isoformat() if a["due_at"] else None)},
            )
        )
    severity = "critical" if len(overdue) >= 2 or any(
        a["created_at"] and a["created_at"] < now - timedelta(days=3) for a in approvals
    ) else ("warning" if (patterns or overdue) else "info")
    return {
        "insight_type": "governance_bottleneck",
        "domain": "governance",
        "key": f"project:{ctx['project_id']}",
        "title": f"Approvals slow down {ctx['project']['name']}",
        "claim": f"Work in {ctx['project']['name']} is waiting on approval or governance steps",
        "summary": (
            f"{len(approvals)} pending approval(s), {len(overdue)} overdue or stale; "
            f"{len(patterns)} governance pattern(s) observed"
        ),
        "severity": severity,
        "evidence": evidence[:8],
        "pattern_ids": [p.id for p in patterns],
        "memory_ids": [],
        "entities": [{"type": "project", "id": ctx["project_id"], "title": ctx["project"]["name"]}],
    }


def _rule_ownership_ambiguity(ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    patterns = [p for p in ctx.get("patterns", []) if p.pattern_type in ("ownership_ambiguity", "ownership_change_delay")]
    if not patterns:
        return None
    from app.models.notification import Event as EventRow

    evidence: list[dict[str, Any]] = []
    for p in patterns[:3]:
        evidence.append(_pattern_item(p))
        anchors = json.loads(p.entities_json) if p.entities_json else []
        for anchor in anchors[:3]:
            evidence.append(
                _evidence(kind=anchor.get("type", "entity"), id=anchor.get("id", "0"), title=anchor.get("title", "unknown") or str(anchor.get("id", "?")))
            )
    if ctx.get("blocked_tasks"):
        evidence.append(
            _evidence(
                kind="task",
                id=ctx["blocked_tasks"][0]["id"],
                title=ctx["blocked_tasks"][0]["title"],
                meta={"status": "blocked", "hint": "blocked work may relate to unclear ownership"},
            )
        )
    return {
        "insight_type": "ownership_ambiguity",
        "domain": "organization",
        "key": f"project:{ctx['project_id']}",
        "title": f"Ownership ambiguity in {ctx['project']['name']}",
        "claim": f"Some work in {ctx['project']['name']} lacks clear ownership",
        "summary": f"{len(patterns)} ownership-related pattern(s) observed; "
                   f"{len(ctx.get('blocked_tasks', []))} task(s) blocked",
        "severity": "warning",
        "evidence": evidence[:6],
        "pattern_ids": [p.id for p in patterns],
        "memory_ids": [],
        "entities": [{"type": "project", "id": ctx["project_id"], "title": ctx["project"]["name"]}],
    }


def _rule_knowledge_gap(ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    patterns = [p for p in ctx.get("patterns", []) if p.pattern_type in KNOWLEDGE_PATTERNS]
    if not patterns:
        return None
    evidence = [_pattern_item(p) for p in patterns[:3]]
    related_memories = [
        m for m in ctx.get("memories", []) if getattr(m, "memory_category", None) in ("event", "experience")
    ][:3]
    for memory in related_memories:
        evidence.append(_memory_item(memory))
    return {
        "insight_type": "knowledge_gap",
        "domain": "knowledge",
        "key": f"project:{ctx['project_id']}",
        "title": f"Knowledge gaps in {ctx['project']['name']}",
        "claim": f"Information needed for {ctx['project']['name']} keeps being re-looked-up or is missing",
        "summary": f"{len(patterns)} knowledge gap pattern(s) observed",
        "severity": "info" if len(patterns) < 2 else "warning",
        "evidence": evidence[:6],
        "pattern_ids": [p.id for p in patterns],
        "memory_ids": [],
        "entities": [{"type": "project", "id": ctx["project_id"], "title": ctx["project"]["name"]}],
    }


def _rule_communication_breakdown(ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    patterns = [p for p in ctx.get("patterns", []) if p.pattern_type in COMMUNICATION_PATTERNS]
    if not patterns:
        return None
    evidence = [_pattern_item(p) for p in patterns[:3]]
    for t in ctx.get("blocked_tasks", [])[:2]:
        evidence.append(_evidence(kind="task", id=t["id"], title=t["title"], meta={"status": t["status"]}))
    return {
        "insight_type": "communication_breakdown",
        "domain": "communication",
        "key": f"project:{ctx['project_id']}",
        "title": f"Communication breakdown in {ctx['project']['name']}",
        "claim": f"Communication between people in {ctx['project']['name']} shows recurring disconnects",
        "summary": f"{len(patterns)} communication pattern(s) observed",
        "severity": "info",
        "evidence": evidence[:6],
        "pattern_ids": [p.id for p in patterns],
        "memory_ids": [],
        "entities": [{"type": "project", "id": ctx["project_id"], "title": ctx["project"]["name"]}],
    }


async def _rule_organizational_bottleneck(db, ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    patterns = [p for p in ctx.get("patterns", []) if p.pattern_type in ORGANIZATION_PATTERNS]
    concentration = ctx.get("employee_concentration")
    if not patterns and not concentration:
        return None
    evidence: list[dict[str, Any]] = []
    for p in patterns[:3]:
        evidence.append(_pattern_item(p))
    employee_id = concentration[0] if concentration else None
    if employee_id:
        from app.models.employee import Employee

        employee = await db.get(Employee, employee_id)
        employee_title = (
            getattr(employee, "display_name", None)
            or getattr(employee, "full_name", None)
            or (employee.first_name + " " + employee.last_name).strip()
            or "a single employee"
            if employee is not None
            else "a single employee"
        )
        evidence.append(
            _evidence(
                kind="employee", id=employee_id,
                title=employee_title,
                meta={"concentration": concentration[1], "hint": "appears repeatedly across signals"},
            )
        )
    return {
        "insight_type": "organizational_bottleneck",
        "domain": "organization",
        "key": f"project:{ctx['project_id']}",
        "title": f"Organizational bottleneck in {ctx['project']['name']}",
        "claim": f"A person or role in {ctx['project']['name']} appears across multiple recurring issues",
        "summary": (
            f"{len(patterns)} organization pattern(s)" +
            (f" and {concentration[1]} signals concentrated on one employee" if concentration else "")
        ),
        "severity": "warning" if employee_id else "info",
        "evidence": evidence[:6],
        "pattern_ids": [p.id for p in patterns],
        "memory_ids": [],
        "entities": [{"type": "project", "id": ctx["project_id"], "title": ctx["project"]["name"]}],
    }


def _rule_repeated_organizational_issue(ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    patterns = [p for p in ctx.get("patterns", []) if p.status in ("confirmed", "persistent")]
    corroborating = [
        m for m in ctx.get("memories", []) if m.importance in ("high", "critical")
    ]
    if len(patterns) < 2 and not (patterns and corroborating):
        return None
    evidence: list[dict[str, Any]] = [_pattern_item(p) for p in patterns[:3]]
    for memory in corroborating[:3]:
        evidence.append(_memory_item(memory))
    families = sorted({p.pattern_type for p in patterns})
    return {
        "insight_type": "repeated_organizational_issue",
        "domain": "organization",
        "key": f"project:{ctx['project_id']}",
        "title": f"Repeated organizational issue in {ctx['project']['name']}",
        "claim": f"The same organizational friction ({', '.join(families[:3])}) keeps recurring despite prior observations",
        "summary": (
            f"{len(patterns)} confirmed/persistent pattern(s) corroborated by "
            f"{len(corroborating)} high-importance memory(ies)"
        ),
        "severity": "warning",
        "evidence": evidence[:8],
        "pattern_ids": [p.id for p in patterns],
        "memory_ids": [m.id for m in corroborating],
        "entities": [{"type": "project", "id": ctx["project_id"], "title": ctx["project"]["name"]}],
    }


def _rule_cross_domain_risk(ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    counts = _domain_counts(ctx)
    if len(counts) < 3:
        return None
    evidence: list[dict[str, Any]] = []
    domains = sorted(counts, key=counts.get, reverse=True)
    for p in ctx.get("patterns", [])[:3]:
        evidence.append(_pattern_item(p))
    for m in ctx.get("memories", [])[:2]:
        evidence.append(_memory_item(m))
    for d in ctx.get("decisions", [])[:1]:
        evidence.append(_evidence(kind="decision", id=d["id"], title=d["title"], meta={"status": d["status"]}))
    return {
        "insight_type": "cross_domain_risk",
        "domain": "cross_domain",
        "key": f"project:{ctx['project_id']}",
        "title": f"Cross-domain risk in {ctx['project']['name']}",
        "claim": f"Issues in {ctx['project']['name']} span {len(counts)} independent domains",
        "summary": f"Signals observed across domains: {', '.join(domains[:5])}",
        "severity": "warning" if len(counts) >= 4 else "info",
        "evidence": evidence[:6],
        "pattern_ids": [p.id for p in ctx.get("patterns", [])[:3]],
        "memory_ids": [m.id for m in ctx.get("memories", [])[:2]],
        "entities": [{"type": "project", "id": ctx["project_id"], "title": ctx["project"]["name"]}],
    }


# ---------------------------------------------------------------------------
# Rule dispatch (bounded, one pass, several candidate types)
# ---------------------------------------------------------------------------


async def _evaluate_rules(
    db: AsyncSession, ctx: dict[str, Any]
) -> list[dict[str, Any]]:
    if "project_id" not in ctx:
        return []
    candidates: list[dict[str, Any]] = []
    rules = (
        _rule_execution_bottleneck,
        _rule_governance_bottleneck,
        _rule_ownership_ambiguity,
        _rule_knowledge_gap,
        _rule_communication_breakdown,
        _rule_repeated_organizational_issue,
        _rule_cross_domain_risk,
    )
    for rule in rules:
        candidate = rule(ctx)
        if candidate:
            candidates.append(candidate)
    decision_items = _rule_decision_bottleneck(ctx)
    if decision_items:
        candidates.extend(decision_items)
    org_item = await _rule_organizational_bottleneck(db, ctx)
    if org_item:
        candidates.append(org_item)
    return candidates[:CANDIDATE_LIMIT]


# ---------------------------------------------------------------------------
# Compositional confidence (self-explaining, bounded to [0, 1])
# ---------------------------------------------------------------------------


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def _compose_confidence(
    candidate: dict[str, Any], ctx: dict[str, Any]
) -> tuple[float, dict[str, Any]]:
    patterns = ctx.get("patterns", [])
    pattern_confidences = [p.confidence or 0.0 for p in patterns if p.confidence]
    occurrence = min(
        sum(p.count or 0 for p in patterns) / 6.0, 1.0
    ) if patterns else min(len(ctx.get("blocked_tasks", [])) / 3.0, 1.0)
    if not patterns and not ctx.get("blocked_tasks"):
        occurrence = min(len(ctx.get("approvals", [])) / 2.0, 1.0)

    corroborating = [
        m for m in ctx.get("memories", []) if m.importance in ("high", "critical")
    ]
    pattern_mean = (sum(pattern_confidences) / len(pattern_confidences)) if pattern_confidences else 0.0
    memory_boost = min(len(corroborating) / 2.0, 1.0)

    required = {
        "execution_bottleneck": {"pattern", "task"},
        "decision_bottleneck": {"decision", "task"},
        "governance_bottleneck": {"approval", "project"},
        "ownership_ambiguity": {"pattern"},
        "knowledge_gap": {"pattern"},
        "communication_breakdown": {"pattern"},
        "organizational_bottleneck": {"pattern", "employee"},
        "repeated_organizational_issue": {"pattern", "memory"},
        "cross_domain_risk": {"pattern", "memory"},
    }
    needed = required.get(candidate["insight_type"], {"pattern"})
    have = {e["type"] for e in candidate["evidence"]}
    completeness = min(len(have & needed) / max(len(needed), 1), 1.0)

    # Recency: decay from the most recent observation (24h half-life).
    last_observed = max(
        (p.last_seen for p in patterns if getattr(p, "last_seen", None)),
        default=None,
    )
    if last_observed is None:
        recency = 1.0
    else:
        if last_observed.tzinfo is None:
            last_observed = last_observed.replace(tzinfo=timezone.utc)
        hours = max((_now() - last_observed).total_seconds() / 3600.0, 0.0)
        recency = max(0.0, 1.0 - hours / (24.0 * 21.0))

    components = {
        "occurrence_strength": round(occurrence, 3),
        "evidence_completeness": round(completeness, 3),
        "pattern_confidence": round(pattern_mean, 3),
        "memory_corroboration": round(memory_boost, 3),
        "recency": round(recency, 3),
        "weights": {
            "occurrence_strength": W_OCCURRENCE,
            "evidence_completeness": W_EVIDENCE,
            "pattern_confidence": W_PATTERN,
            "memory_corroboration": W_MEMORY,
            "recency": W_RECENCY,
        },
    }
    confidence = clamp01(
        W_OCCURRENCE * occurrence
        + W_EVIDENCE * completeness
        + W_PATTERN * pattern_mean
        + W_MEMORY * memory_boost
        + W_RECENCY * recency
    )
    return confidence, components


# ---------------------------------------------------------------------------
# Insight upsert (create or recompose one insight)
# ---------------------------------------------------------------------------


def _merge_lines(existing: Optional[list[dict[str, Any]]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {f"{item.get('type')}:{item.get('id')}": item for item in existing or []}
    for item in new:
        merged[f"{item.get('type')}:{item.get('id')}"] = item
    return list(merged.values())[-12:]


def _merge_ids(existing: Optional[list[str]], new: list[str]) -> list[str]:
    merged = list(existing or [])
    for value in new:
        if value and value not in merged:
            merged.append(value)
    return merged[-16:]


async def _link_event(
    db: AsyncSession, organization_id: str, insight_id: str, event_id: str, kind: str
) -> None:
    """Exactly-once evidence lineage for one evaluation (replay-safe)."""
    row = InsightEvent(
        organization_id=organization_id,
        insight_id=insight_id,
        event_id=event_id,
        relationship=kind,
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except Exception:
        pass  # already linked — replay-safe


async def _emit_insight_event(
    db: AsyncSession,
    organization_id: str,
    name: str,
    insight: UniversalInsight,
) -> None:
    from app.services.event_service import event_service

    await event_service.emit(
        db,
        name=name,
        organization_id=organization_id,
        payload={
            "insight_id": insight.id,
            "insight_type": insight.insight_type,
            "key": insight.key,
            "status": insight.status,
            "severity": insight.severity,
            "confidence": round(insight.confidence or 0.0, 3),
        },
    )


async def _upsert_insight(
    db: AsyncSession,
    organization_id: str,
    candidate: dict[str, Any],
    ctx: dict[str, Any],
    event_id: str,
) -> Optional[UniversalInsight]:
    confidence, components = _compose_confidence(candidate, ctx)
    if confidence < 0.05:
        return None

    scope_type = "project" if ctx.get("scope_id") else "org"
    scope_id = ctx.get("scope_id")
    auth_project_id = ctx.get("project_id")

    evaluation = (
        await db.execute(
            select(UniversalInsight).where(
                UniversalInsight.organization_id == organization_id,
                UniversalInsight.insight_type == candidate["insight_type"],
                UniversalInsight.key == candidate["key"],
            ).limit(1)
        )
    ).scalar_one_or_none()

    now = _now()
    if evaluation is None:
        insight = UniversalInsight(
            organization_id=organization_id,
            insight_type=candidate["insight_type"],
            key=candidate["key"],
            domain=candidate["domain"],
            severity=candidate["severity"],
            title=candidate["title"],
            claim=candidate["claim"],
            summary=candidate["summary"],
            confidence=confidence,
            confidence_components=components,
            evidence_json=candidate["evidence"],
            relationships_json=[],
            supporting_pattern_ids=candidate["pattern_ids"],
            supporting_memory_ids=candidate["memory_ids"],
            affected_entities=candidate["entities"],
            scope_type=scope_type,
            scope_id=scope_id,
            auth_project_id=auth_project_id,
            status="active",
            first_observed_at=now,
            last_observed_at=now,
        )
        db.add(insight)
        await db.flush()
        await _link_event(db, organization_id, insight.id, event_id, "seed")
        await _emit_insight_event(db, organization_id, "insight.detected", insight)
        return insight

    if evaluation.status in ("faded", "resolved"):
        # Revive: new evidence reconstitutes the insight as active.
        evaluation.status = "active"
    evaluation.domain = candidate["domain"]
    evaluation.severity = candidate["severity"]
    evaluation.title = candidate["title"]
    evaluation.claim = candidate["claim"]
    evaluation.summary = candidate["summary"]
    evaluation.confidence = confidence
    evaluation.confidence_components = components
    evaluation.evidence_json = _merge_lines(evaluation.evidence_json, candidate["evidence"])
    evaluation.supporting_pattern_ids = _merge_ids(
        evaluation.supporting_pattern_ids, candidate["pattern_ids"]
    )
    evaluation.supporting_memory_ids = _merge_ids(
        evaluation.supporting_memory_ids, candidate["memory_ids"]
    )
    evaluation.affected_entities = _merge_lines(evaluation.affected_entities, candidate["entities"])
    if scope_id:
        evaluation.scope_id = scope_id
    if auth_project_id:
        evaluation.auth_project_id = auth_project_id
    evaluation.last_observed_at = now
    await db.flush()
    await _link_event(db, organization_id, evaluation.id, event_id, "support")
    await _emit_insight_event(db, organization_id, "insight.updated", evaluation)
    return evaluation


# ---------------------------------------------------------------------------
# Change-driven entry point
# ---------------------------------------------------------------------------


async def process_event(db: AsyncSession, *, event: EventRow) -> Optional[dict[str, Any]]:
    """Evaluate one event against the insight rules (idempotent, replay-safe)."""
    if not event.organization_id or event.name not in TRIGGER_EVENTS:
        return None
    payload = _payload(event)
    ctx = await _collect_neighborhood(db, event, payload, event.organization_id)
    if "project_id" not in ctx:
        return None
    candidates = await _evaluate_rules(db, ctx)
    touched = 0
    names: set[str] = set()
    for candidate in candidates:
        insight = await _upsert_insight(
            db, event.organization_id, candidate, ctx, event.id
        )
        if insight is not None:
            touched += 1
            names.add(insight.insight_type)
    return {"insights": touched, "types": sorted(names)}


# ---------------------------------------------------------------------------
# Bounded fade / resolve sweep (indexed, capped)
# ---------------------------------------------------------------------------


async def evaluate_fading(
    db: AsyncSession,
    organization_id: Optional[str] = None,
    limit: int = 50,
) -> dict[str, int]:
    """Age insights whose last observation stopped: active -> faded -> resolved.

    Bounded: only active/faded insights observed within the last
    ``ORPHAN_RESOLVED_DAYS`` are considered, oldest first.
    """
    results: dict[str, int] = {"faded": 0, "resolved": 0, "revived": 0, "evaluated": 0}
    now = _now()
    orphan_cutoff = now - timedelta(days=ORPHAN_RESOLVED_DAYS)
    rows = (
        await db.execute(
            select(UniversalInsight).where(
                UniversalInsight.organization_id == organization_id
                if organization_id is not None
                else UniversalInsight.organization_id.is_not(None),
                UniversalInsight.status.in_(["active", "faded"]),
                UniversalInsight.last_observed_at >= orphan_cutoff,
            )
            .order_by(UniversalInsight.last_observed_at.asc())
            .limit(limit)
        )
    ).scalars().all()
    for insight in rows:
        last_observed = insight.last_observed_at or now
        if last_observed.tzinfo is None:
            last_observed = last_observed.replace(tzinfo=timezone.utc)
        stale_days = (now - last_observed).days
        if insight.status == "active":
            if stale_days >= FADING_AFTER_DAYS:
                insight.status = "faded"
                await _emit_insight_event(db, insight.organization_id, "insight.faded", insight)
                results["faded"] += 1
        elif insight.status == "faded":
            if stale_days >= RESOLVED_AFTER_DAYS:
                insight.status = "resolved"
                await _emit_insight_event(db, insight.organization_id, "insight.resolved", insight)
                results["resolved"] += 1
        results["evaluated"] += 1
    return results