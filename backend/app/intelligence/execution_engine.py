"""Slice 4G.1 — Project & Execution Intelligence engine.

One canonical execution record per project, fed change-driven by the SAME
durable events the platform already emits. The engine answers:

* WHAT is the company trying to accomplish (goal chain: company goal ->
  business objective -> project -> milestone -> task),
* HOW is the work progressing (deterministic health score + factors +
  one human explain + primary cause, persisted with history),
* WHAT is blocking it (blocker analysis with root-cause chains + systemic
  grouping over the existing TaskDependency graph),
* WHAT could change the outcome (a real critical path: CPM forward/backward
  passes with slack over estimates and due dates),
* WHETHER capacity constrains it (read from the 4F.6 capability record —
  never recomputed here),
* WHICH decisions affect it (read from the 4A decision registry),
* WHAT should happen next (prioritized, cross-project),
* WHAT the eventual outcome achieved (mandatory outcome record: planned vs
  actual + assessment, fed forward as evidence).

Everything is advisory: the engine only writes its own canonical tables,
never projects, tasks, people or capacity. All queries are bounded by
project and by explicit caps.

Exact-once: every event-driven refresh is keyed on source_event_id
(unique per project). Replays converge. Snapshots keep "what changed"
answerable over time (capped history, oldest pruned).
"""

import asyncio
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_intelligence import (
    ProjectExecutionSnapshot,
    ProjectExecutionState,
)
from app.models.goal import Goal
from app.models.knowledge import Decision
from app.models.project import Milestone, Project
from app.models.task import Task, TaskDependency

# ---------------------------------------------------------------------------
# bounds — the same architecture must serve 5 people and 50,000+
# ---------------------------------------------------------------------------

MAX_ACTIVE_PROJECTS_SCAN = 200          # command center / next surfaces
MAX_TASKS_PER_PROJECT = 300             # CPM + blocker scan cap
MAX_BLOCKER_CHAIN_DEPTH = 5
MAX_SYSTEMIC_GROUPS = 6
MAX_BLOCKED_ROWS = 40
MAX_CAPACITY_ROWS = 12
MAX_DECISION_ROWS = 20
MAX_GOAL_CHAIN_DEPTH = 3
MAX_SNAPSHOT_HISTORY = 40
MAX_HISTORY_SHOWN = 10
MAX_NEXT_ITEMS = 20
MAX_NEXT_DECISIONS = 8
MAX_NEXT_READY_PER_PROJECT = 2
MAX_READY_PROJECTS = 15
MAX_MILESTONES_PER_PROJECT = 50

HEALTH_BASE = 80
ACTIVE_STATUSES = ("draft", "active", "paused")
CLOSED_STATUSES = ("completed", "cancelled", "archived")

_HEALTH_BANDS = (
    (80, "healthy"),
    (65, "watch"),
    (50, "at_risk"),
    (0, "critical"),
)


def _band(score: int) -> str:
    for threshold, label in _HEALTH_BANDS:
        if score >= threshold:
            return label
    return "critical"


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _round1(value: float) -> float:
    return round(value, 1)


class ExecutionEngine:
    """Canonical Project & Execution Intelligence — one engine per org."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------ write

    async def record_event(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        event,
        payload: dict[str, Any],
    ) -> None:
        """Change-driven entry: resolve the project and refresh its record.

        Payload carries project_id for task.*/project.*/milestone.*; for
        dependency.*/decision.*/goal.* the owning row is resolved by a
        single bounded lookup. Replays are exact-once on source_event_id.
        """
        project_id: Optional[str] = payload.get("project_id")
        if not project_id:
            task_id = payload.get("task_id")
            if task_id:
                project_id = (
                    await db.execute(
                        select(Task.project_id).where(
                            Task.organization_id == organization_id,
                            Task.id == task_id,
                        )
                    )
                ).scalar_one_or_none()
            if not project_id:
                decision_id = payload.get("decision_id")
                if decision_id:
                    project_id = (
                        await db.execute(
                            select(Decision.project_id).where(
                                Decision.organization_id == organization_id,
                                Decision.id == decision_id,
                            )
                        )
                    ).scalar_one_or_none()
            if not project_id:
                goal_id = payload.get("goal_id")
                if goal_id:
                    project_id = (
                        await db.execute(
                            select(Goal.project_id).where(
                                Goal.organization_id == organization_id,
                                Goal.id == goal_id,
                            )
                        )
                    ).scalar_one_or_none()
        if not project_id:
            return
        await self.refresh_project(
            db,
            organization_id=organization_id,
            project_id=project_id,
            event_name=getattr(event, "name", ""),
            source_event_id=getattr(event, "id", None),
        )

    async def refresh_project(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        event_name: str,
        source_event_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Recompute and persist one project's execution record.

        Idempotent: the unique (org, project, source_event_id) constraint
        makes replays converge exactly-once. Returns the computed record or
        None when the project does not exist or the event is a replay.
        """
        async with self._locks[organization_id]:
            project = (
                await db.execute(
                    select(Project).where(
                        Project.organization_id == organization_id,
                        Project.id == project_id,
                    )
                )
            ).scalar_one_or_none()
            if project is None:
                return None

            if source_event_id:
                existing = (
                    await db.execute(
                        select(ProjectExecutionSnapshot.id).where(
                            ProjectExecutionSnapshot.organization_id == organization_id,
                            ProjectExecutionSnapshot.project_id == project_id,
                            ProjectExecutionSnapshot.source_event_id == source_event_id,
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    return None

            computed = await self._compute_project(
                db, organization_id=organization_id, project=project
            )

            state = (
                await db.execute(
                    select(ProjectExecutionState).where(
                        ProjectExecutionState.organization_id == organization_id,
                        ProjectExecutionState.project_id == project_id,
                    )
                )
            ).scalar_one_or_none()
            if state is None:
                state = ProjectExecutionState(
                    organization_id=organization_id,
                    project_id=project_id,
                )
                db.add(state)
            state.health_score = computed["health_score"]
            state.health_status = computed["health_status"]
            state.factors = computed["factors"]
            state.explain = computed["explain"]
            state.primary_cause = computed["primary_cause"]
            state.counts = computed["counts"]
            state.critical_path = computed["critical_path"]
            state.blockers = computed["blockers"]
            state.systemic_blockers = computed["systemic_blockers"]
            state.capacity_constraints = computed["capacity_constraints"]
            state.pending_decisions = computed["pending_decisions"]
            state.goal_chain = computed["goal_chain"]
            state.source_event_id = source_event_id

            if source_event_id:
                db.add(
                    ProjectExecutionSnapshot(
                        organization_id=organization_id,
                        project_id=project_id,
                        source_event_id=source_event_id,
                        event_name=event_name or "execution.state_changed",
                        health_score=computed["health_score"],
                        health_status=computed["health_status"],
                        primary_cause=computed["primary_cause"],
                        explain=computed["explain"],
                        factors=computed["factors"],
                        occurred_at=datetime.now(),
                    )
                )
                await self._prune_snapshots(
                    db, organization_id=organization_id, project_id=project_id
                )
            return computed

    async def _prune_snapshots(
        self, db: AsyncSession, *, organization_id: str, project_id: str
    ) -> None:
        old = (
            await db.execute(
                select(ProjectExecutionSnapshot.id)
                .where(
                    ProjectExecutionSnapshot.organization_id == organization_id,
                    ProjectExecutionSnapshot.project_id == project_id,
                )
                .order_by(ProjectExecutionSnapshot.occurred_at.asc())
            )
        ).scalars().all()
        excess = len(old) - MAX_SNAPSHOT_HISTORY
        if excess > 0:
            for snap_id in old[:excess]:
                await db.delete(await db.get(ProjectExecutionSnapshot, snap_id))

    # -------------------------------------------------------------- compute

    async def _compute_project(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        project: Project,
    ) -> dict[str, Any]:
        tasks = list(
            (
                await db.execute(
                    select(Task)
                    .where(
                        Task.organization_id == organization_id,
                        Task.project_id == project.id,
                    )
                    .order_by(Task.created_at.desc())
                    .limit(MAX_TASKS_PER_PROJECT)
                )
            ).scalars().all()
        )
        task_by_id = {t.id: t for t in tasks}
        labels = await self._employee_labels(db, organization_id)
        dependencies = await self._dependencies(db, organization_id, task_by_id)

        overdue_milestones = await self._overdue_milestones(
            db, organization_id=organization_id, project_id=project.id
        )
        critical_path = self._critical_path(dependencies, task_by_id)
        blocked = self._blocked_analysis(dependencies, task_by_id, labels)
        systemic = self._systemic_blockers(blocked["blocked_rows"], task_by_id)
        capacity = await self._capacity_constraints(
            db, organization_id=organization_id, project_id=project.id
        )
        decisions = await self._pending_decisions(
            db, organization_id=organization_id, project_id=project.id
        )
        goal_chain = await self._goal_chain(
            db, organization_id=organization_id, project_id=project.id
        )

        today = date.today()
        counts: dict[str, Any] = {
            "project_status": project.status,
            "active_tasks": sum(
                1 for t in tasks if t.status not in ("completed", "archived")
            ),
            "blocked_tasks": len(blocked["blocked_rows"]),
            "deeply_blocked_tasks": blocked["deeply_blocked"],
            "overdue_tasks": sum(
                1 for t in tasks
                if t.due_date and t.due_date < today
                and t.status not in ("completed", "archived")
            ),
            "overdue_milestones": len(overdue_milestones),
            "critical_tasks": len(critical_path["critical_task_ids"]),
            "critical_overdue_tasks": critical_path["overdue_critical_ids"],
            "unowned": project.owner_id is None,
            "past_end_date": bool(
                project.end_date and project.end_date < today
                and project.status in ACTIVE_STATUSES
            ),
        }

        penalties = self._health_penalties(
            counts=counts, capacity=capacity, decisions=decisions, project=project
        )
        score = max(0, min(100, HEALTH_BASE - penalties["total"]))
        if project.status == "completed":
            status = "healthy"
            score = 100
        elif project.status == "cancelled":
            status = "critical"
        else:
            status = _band(score)

        factors = {
            "health_accounting": dict(penalties["parts"]),
            "timeline": {
                "overdue_tasks": counts["overdue_tasks"],
                "overdue_milestones": counts["overdue_milestones"],
                "past_end_date": counts["past_end_date"],
                "critical_overdue_tasks": counts["critical_overdue_tasks"],
            },
            "dependencies": {
                "blocked_tasks": counts["blocked_tasks"],
                "deeply_blocked_tasks": counts["deeply_blocked_tasks"],
                "critical_path_tasks": counts["critical_tasks"],
                "projected_finish_hours": critical_path["projected_finish_hours"],
                "min_slack_hours": critical_path["min_slack"],
            },
            "capacity": {
                "constrained_skills": [c["skill_name"] for c in capacity],
            },
            "decisions": {
                "pending_open": sum(1 for d in decisions if d.get("open_actions", 0) > 0),
                "total_pending": len(decisions),
            },
            "ownership": {
                "no_owner": counts["unowned"],
            },
        }

        return {
            "health_score": score,
            "health_status": status,
            "factors": factors,
            "explain": self._explain(
                counts=counts, critical_path=critical_path,
                capacity=capacity, decisions=decisions, project=project,
            ),
            "primary_cause": (
                None if project.status == "completed"
                else self._primary_cause(penalties)
            ),
            "counts": counts,
            "critical_path": critical_path,
            "blockers": blocked["blocked_rows"],
            "systemic_blockers": systemic,
            "capacity_constraints": capacity,
            "pending_decisions": decisions,
            "goal_chain": goal_chain,
        }

    # ------------------------------------------------------------------ health

    def _health_penalties(
        self,
        *,
        counts: dict[str, Any],
        capacity: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        project: Project,
    ) -> dict[str, Any]:
        """Deterministic penalty budget per surface (bounded per factor)."""
        timeline = 0
        timeline += min(counts["overdue_tasks"] * 6, 25)
        timeline += min(counts["overdue_milestones"] * 10, 20)
        if counts["past_end_date"]:
            timeline += 15
        timeline += min(counts["critical_overdue_tasks"] * 12, 24)

        dependencies = 0
        dependencies += min(counts["blocked_tasks"] * 8, 30)
        dependencies += min(counts["deeply_blocked_tasks"] * 8, 16)

        capacity_pen = min(len(capacity) * 8, 16) if capacity else 0

        pending_open = sum(1 for d in decisions if d.get("open_actions", 0) > 0)
        decisions_pen = min(pending_open * 5, 10) if pending_open else 0

        ownership_pen = (
            10 if counts["unowned"] and project.status in ACTIVE_STATUSES else 0
        )

        total = timeline + dependencies + capacity_pen + decisions_pen + ownership_pen
        return {
            "total": total,
            "parts": {
                "timeline": timeline,
                "dependencies": dependencies,
                "capacity": capacity_pen,
                "decisions": decisions_pen,
                "ownership": ownership_pen,
            },
        }

    def _explain(
        self,
        *,
        counts: dict[str, Any],
        critical_path: dict[str, Any],
        capacity: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        project: Project,
    ) -> str:
        parts: list[str] = []
        if counts["blocked_tasks"]:
            deep = (
                f" ({counts['deeply_blocked_tasks']} deeply blocked)"
                if counts["deeply_blocked_tasks"] else ""
            )
            parts.append(f"{counts['blocked_tasks']} blocked task(s){deep}")
        if counts["overdue_tasks"]:
            parts.append(f"{counts['overdue_tasks']} overdue task(s)")
        if counts["overdue_milestones"]:
            parts.append(f"{counts['overdue_milestones']} overdue milestone(s)")
        if counts["critical_overdue_tasks"]:
            parts.append(f"{counts['critical_overdue_tasks']} critical-path task(s) past due")
        if counts["past_end_date"]:
            parts.append("past the planned end date")
        if counts["critical_tasks"] and project.status in ACTIVE_STATUSES:
            parts.append(
                f"critical path holds {counts['critical_tasks']} task(s)"
                f" ({_round1(critical_path['total_hours'])} estimated hours, "
                f"projected finish {_round1(critical_path['projected_finish_hours'])} h)"
            )
        if capacity:
            parts.append(f"capacity constrained: {', '.join(c['skill_name'] for c in capacity)}")
        pending_open = [d for d in decisions if d.get("open_actions", 0) > 0]
        if pending_open:
            parts.append(
                f"{len(pending_open)} pending decision(s) with open action task(s)"
            )
        if counts["unowned"] and project.status in ACTIVE_STATUSES:
            parts.append("no project owner assigned")
        if not parts:
            if project.status == "completed":
                return "No adverse signals — the project is completed and its outcome is recorded."
            if project.status in CLOSED_STATUSES:
                return "No adverse signals — the project is closed."
            return "No adverse signals — everything is moving as expected."
        return "Evidence: " + "; ".join(parts) + "."

    def _primary_cause(self, penalties: dict[str, Any]) -> Optional[str]:
        parts = penalties["parts"]
        surface = max(parts, key=parts.get)  # type: ignore[arg-type]
        if parts[surface] <= 0:
            return None
        labels = {
            "timeline": "Timeline pressure",
            "dependencies": "Dependency blockage",
            "capacity": "Capacity constraint",
            "decisions": "Pending decisions",
            "ownership": "Missing ownership",
        }
        return labels.get(surface, surface)

    # ------------------------------------------------------- critical path

    def _critical_path(
        self,
        dependencies: list[TaskDependency],
        task_by_id: dict[str, Task],
    ) -> dict[str, Any]:
        """Real CPM over the TaskDependency graph: forward/backward passes
        with slack. Weight = estimate_hours (min 1.0). Bounded per project."""
        scope = {
            t.id: t for t in task_by_id.values()
            if t.status not in ("completed", "archived")
        }
        if not scope:
            return {
                "total_hours": 0.0,
                "projected_finish_hours": 0.0,
                "min_slack": None,
                "critical_task_ids": [],
                "overdue_critical_ids": 0,
                "tasks": [],
            }
        preds: dict[str, list[str]] = defaultdict(list)
        succs: dict[str, list[str]] = defaultdict(list)
        seen: set[tuple[str, str]] = set()
        for dep in dependencies:
            a, b = dep.task_id, dep.depends_on_task_id
            if a not in scope or b not in scope or (a, b) in seen:
                continue
            seen.add((a, b))
            preds[a].append(b)
            succs[b].append(a)

        weight = {
            t.id: max(float(t.estimate_hours or 0) or 1.0, 1.0)
            for t in scope.values()
        }
        early_start: dict[str, float] = {}
        early_finish: dict[str, float] = {}

        def es(node: str) -> float:
            if node in early_finish:
                return early_finish[node]
            best = 0.0
            for p in preds.get(node, []):
                best = max(best, es(p))
            early_start[node] = best
            ef = best + weight[node]
            early_finish[node] = ef
            return ef

        for node in scope:
            es(node)
        finish = max(early_finish.values())

        late_start: dict[str, float] = {}

        def ls(node: str, late_finish: float) -> None:
            start = late_finish - weight[node]
            if node in late_start:
                if start >= late_start[node]:
                    return
                late_start[node] = start
            else:
                late_start[node] = start
            for p in preds.get(node, []):
                ls(p, start)

        sinks = [t.id for t in scope.values() if not succs.get(t.id)]
        for s in sinks:
            ls(s, finish)

        today = date.today()
        rows: list[dict[str, Any]] = []
        critical_ids: list[str] = []
        overdue_critical = 0
        min_slack: Optional[float] = None
        for t in scope.values():
            start = early_start.get(t.id, 0.0)
            lstart = late_start.get(t.id, finish - weight[t.id])
            slack = _round1(lstart - start)
            if min_slack is None or slack < min_slack:
                min_slack = slack
            critical = slack <= 0.5
            if critical:
                critical_ids.append(t.id)
                if t.due_date and t.due_date < today:
                    overdue_critical += 1
            rows.append({
                "task_id": t.id,
                "title": t.title,
                "status": t.status,
                "estimate_hours": weight[t.id],
                "early_start_hours": _round1(start),
                "slack_hours": slack,
                "due_date": _iso(t.due_date),
                "critical": critical,
            })
        rows.sort(key=lambda r: (not r["critical"], r["early_start_hours"]))
        return {
            "total_hours": _round1(sum(weight.values())),
            "projected_finish_hours": _round1(finish),
            "min_slack": _round1(min_slack) if min_slack is not None else None,
            "critical_task_ids": critical_ids,
            "overdue_critical_ids": overdue_critical,
            "tasks": rows,
        }

    async def _dependencies(
        self,
        db: AsyncSession,
        organization_id: str,
        task_by_id: dict[str, Task],
    ) -> list[TaskDependency]:
        """Task dependencies whose both endpoints are in the scanned task set."""
        rows = list(
            (
                await db.execute(
                    select(TaskDependency).where(
                        TaskDependency.organization_id == organization_id,
                        TaskDependency.task_id.in_(list(task_by_id.keys())),
                    )
                )
            ).scalars().all()
        )
        ids = set(task_by_id.keys())
        return [d for d in rows if d.depends_on_task_id in ids]

    # -------------------------------------------------------------- blockers

    def _blocked_analysis(
        self,
        dependencies: list[TaskDependency],
        task_by_id: dict[str, Task],
        labels: dict[str, str],
    ) -> dict[str, Any]:
        """Blocked tasks with root-cause chains (bounded depth)."""
        status_of = {t.id: t.status for t in task_by_id.values()}
        blockers_of: dict[str, list[str]] = defaultdict(list)
        for d in dependencies:
            if d.kind in ("blocking", "finish_to_start"):
                blockers_of[d.task_id].append(d.depends_on_task_id)

        def unsatisfied(blocker_id: str) -> bool:
            return status_of.get(blocker_id, "completed") in (
                "backlog", "todo", "in_progress", "review", "blocked",
            )

        rows: list[dict[str, Any]] = []
        deeply = 0
        for t in task_by_id.values():
            if t.status != "blocked":
                continue
            chain: list[str] = []
            seen_ids: set[str] = set()
            current: Optional[str] = t.id
            while (
                current and current not in seen_ids
                and len(chain) < MAX_BLOCKER_CHAIN_DEPTH
            ):
                seen_ids.add(current)
                blockers = [
                    b for b in blockers_of.get(current, [])
                    if b in status_of and unsatisfied(b)
                ]
                if not blockers:
                    break
                root = sorted(blockers)[0]
                chain.append(root)
                current = root
            depth = len(chain)
            if depth >= 2:
                deeply += 1
            rows.append({
                "task_id": t.id,
                "title": t.title,
                "assignee_label": labels.get(t.assignee_id or ""),
                "chain_depth": depth,
                "chain": [
                    {
                        "task_id": cid,
                        "title": task_by_id[cid].title if cid in task_by_id else "",
                        "status": status_of.get(cid, ""),
                    }
                    for cid in chain
                ],
            })
        rows.sort(key=lambda r: (-r["chain_depth"], r["title"]))
        return {"blocked_rows": rows[:MAX_BLOCKED_ROWS], "deeply_blocked": deeply}

    def _systemic_blockers(
        self, blocked_rows: list[dict[str, Any]], task_by_id: dict[str, Task]
    ) -> list[dict[str, Any]]:
        """Group blocked tasks by the SAME root cause (3+ occurrences) —
        the seed of a systemic blocker."""
        grouped: dict[str, list[str]] = defaultdict(list)
        for row in blocked_rows:
            if row["chain"]:
                root_id = row["chain"][0]["task_id"]
                grouped[root_id].append(row["task_id"])
        findings: list[dict[str, Any]] = []
        for root_id, affected in grouped.items():
            if len(affected) < 3:
                continue
            root = task_by_id.get(root_id)
            findings.append({
                "kind": "task",
                "subject_id": root_id,
                "subject_label": root.title if root else "",
                "affected_count": len(affected),
                "affected_tasks": affected,
                "explain": (
                    f"{len(affected)} blocked tasks share the same root cause — "
                    f"'{root.title if root else 'the blocker'}' must be resolved "
                    f"before the downstream work can proceed."
                ),
            })
        findings.sort(key=lambda f: -f["affected_count"])
        return findings[:MAX_SYSTEMIC_GROUPS]

    # ---------------------------------------------------------- integrations

    async def _overdue_milestones(
        self, db: AsyncSession, *, organization_id: str, project_id: str
    ) -> list[Milestone]:
        rows = list(
            (
                await db.execute(
                    select(Milestone)
                    .where(
                        Milestone.organization_id == organization_id,
                        Milestone.project_id == project_id,
                    )
                    .limit(MAX_MILESTONES_PER_PROJECT)
                )
            ).scalars().all()
        )
        today = date.today()
        return [
            m for m in rows
            if m.status != "completed" and m.due_date and m.due_date < today
        ]

    async def _capacity_constraints(
        self, db: AsyncSession, *, organization_id: str, project_id: str
    ) -> list[dict[str, Any]]:
        """Read the 4F.6 capability record — never recompute capacity here."""
        from app.intelligence.org_capability_engine import org_capability_engine

        view = await org_capability_engine.project_capabilities(
            db, organization_id=organization_id, project_id=project_id,
        )
        return [
            {
                "skill_name": c["skill_name"],
                "capacity_state": c["capacity_state"],
                "capacity_available": c["capacity_available"],
                "lifecycle": c["lifecycle"],
            }
            for c in view.get("capabilities", [])
            if c["capacity_state"] in ("constrained", "stretched")
        ][:MAX_CAPACITY_ROWS]

    async def _pending_decisions(
        self, db: AsyncSession, *, organization_id: str, project_id: str
    ) -> list[dict[str, Any]]:
        """Pending decisions from the 4A decision registry, anchored on the
        project, with open follow-up action tasks (the 'blocking' signal)."""
        rows = list(
            (
                await db.execute(
                    select(Decision)
                    .where(
                        Decision.organization_id == organization_id,
                        Decision.project_id == project_id,
                        Decision.status.in_(("proposed", "made")),
                    )
                    .order_by(Decision.created_at.asc())
                    .limit(MAX_DECISION_ROWS)
                )
            ).scalars().all()
        )
        if not rows:
            return []
        open_by_decision: dict[str, int] = defaultdict(int)
        task_rows = (
            await db.execute(
                select(Task)
                .where(
                    Task.organization_id == organization_id,
                    Task.project_id == project_id,
                    Task.decision_id.isnot(None),
                    Task.status.notin_(("completed", "archived")),
                )
            )
        ).scalars().all()
        for tsk in task_rows:
            open_by_decision[tsk.decision_id or ""] += 1
        return [
            {
                "decision_id": d.id,
                "title": (d.title or "")[:180],
                "status": d.status,
                "open_actions": open_by_decision.get(d.id, 0),
            }
            for d in rows
        ]

    async def _goal_chain(
        self, db: AsyncSession, *, organization_id: str, project_id: str
    ) -> list[dict[str, Any]]:
        """Goal chain for the project: anchored goals walked up the parent
        line with bounded batch lookups, root-first, bounded depth."""
        rows = list(
            (
                await db.execute(
                    select(Goal)
                    .where(
                        Goal.organization_id == organization_id,
                        Goal.project_id == project_id,
                    )
                    .order_by(Goal.created_at.asc())
                    .limit(10)
                )
            ).scalars().all()
        )
        if not rows:
            return []
        by_id = {g.id: g for g in rows}
        # fetch the unknown parent line in bounded batches (each round adds
        # at most one level; MAX_GOAL_CHAIN_DEPTH rounds cap the work)
        for _ in range(MAX_GOAL_CHAIN_DEPTH):
            wanted = {
                g.parent_goal_id for g in by_id.values()
                if g.parent_goal_id and g.parent_goal_id not in by_id
            }
            if not wanted:
                break
            parents = (
                await db.execute(
                    select(Goal).where(
                        Goal.organization_id == organization_id,
                        Goal.id.in_(list(wanted)),
                    )
                )
            ).scalars().all()
            for parent in parents:
                by_id[parent.id] = parent

        def entry(goal: Goal) -> dict[str, Any]:
            return {
                "goal_id": goal.id,
                "title": goal.name,
                "scope": goal.scope,
                "status": goal.status,
                "progress": round(float(goal.progress or 0), 1),
            }

        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        for anchor in rows:
            steps: list[Goal] = []
            current: Optional[Goal] = anchor
            depth = 0
            while (
                current and current.id not in seen
                and depth < MAX_GOAL_CHAIN_DEPTH
            ):
                steps.append(current)
                seen.add(current.id)
                current = by_id.get(current.parent_goal_id or "")
                depth += 1
            if steps:
                chain.extend(entry(g) for g in reversed(steps))
        return chain

    # -------------------------------------------------------------- surfaces

    async def command_center(
        self, db: AsyncSession, *, organization_id: str
    ) -> dict[str, Any]:
        """The Execution Command Center: one-glance execution state of every
        active project, with counts, per-project health and explain."""
        projects = list(
            (
                await db.execute(
                    select(Project)
                    .where(
                        Project.organization_id == organization_id,
                        Project.status.in_(ACTIVE_STATUSES),
                    )
                    .order_by(Project.created_at.asc())
                    .limit(MAX_ACTIVE_PROJECTS_SCAN)
                )
            ).scalars().all()
        )
        labels = await self._employee_labels(db, organization_id)
        states = {
            s.project_id: s
            for s in (
                await db.execute(
                    select(ProjectExecutionState).where(
                        ProjectExecutionState.organization_id == organization_id,
                    )
                )
            ).scalars().all()
        }
        snapshots = await self._latest_snapshots(
            db, organization_id=organization_id,
            project_ids=[p.id for p in projects],
        )

        rows = []
        at_risk = 0
        blocked_projects = 0
        pending_decisions_total = 0
        for p in projects:
            state = states.get(p.id)
            counts = dict(state.counts or {}) if state else {}
            status = state.health_status if state else "healthy"
            score = state.health_score if state else HEALTH_BASE
            if status in ("at_risk", "critical"):
                at_risk += 1
            if counts.get("blocked_tasks"):
                blocked_projects += 1
            pending_decisions_total += len(state.pending_decisions or []) if state else 0
            history = snapshots.get(p.id, [])
            last = history[0] if history else None
            prev = history[1] if len(history) > 1 else None
            change: Optional[str] = None
            if last and prev and last["health_status"] != prev["health_status"]:
                change = (
                    f"{prev['health_status']} → {last['health_status']} "
                    f"({last['event_name']})"
                )
            elif last:
                change = f"{last['event_name']}"
            rows.append({
                "project_id": p.id,
                "code": p.code,
                "name": p.name,
                "owner_label": labels.get(p.owner_id or "") if p.owner_id else None,
                "status": p.status,
                "health_status": status,
                "health_score": score,
                "primary_cause": state.primary_cause if state else None,
                "explain": state.explain if state else "No execution record yet.",
                "last_change": change,
                "last_event_at": last["occurred_at"] if last else None,
                "counts": counts,
                "capacity_constraints": state.capacity_constraints or [] if state else [],
                "pending_decisions": len(state.pending_decisions or []) if state else 0,
            })
        rows.sort(key=lambda r: (r["health_score"], r["name"]))
        return {
            "total_projects": len(rows),
            "counts": {
                "active_projects": len(rows),
                "at_risk": at_risk,
                "blocked_projects": blocked_projects,
                "pending_decisions": pending_decisions_total,
                "capacity_constraints": await self._org_capacity_constraint_count(
                    db, organization_id=organization_id, projects=projects,
                ),
            },
            "projects": rows,
        }

    async def _org_capacity_constraint_count(
        self, db: AsyncSession, *, organization_id: str, projects: list[Project]
    ) -> int:
        """Distinct constrained capabilities across active projects (bounded)."""
        from app.intelligence.org_capability_engine import org_capability_engine

        names: set[str] = set()
        for p in projects[:20]:
            view = await org_capability_engine.project_capabilities(
                db, organization_id=organization_id, project_id=p.id,
            )
            for c in view.get("capabilities", []):
                if c["capacity_state"] in ("constrained", "stretched"):
                    names.add(c["skill_name"])
        return len(names)

    async def project_detail(
        self, db: AsyncSession, *, organization_id: str, project_id: str
    ) -> Optional[dict[str, Any]]:
        project = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == organization_id,
                    Project.id == project_id,
                )
            )
        ).scalar_one_or_none()
        if project is None:
            return None
        state = (
            await db.execute(
                select(ProjectExecutionState).where(
                    ProjectExecutionState.organization_id == organization_id,
                    ProjectExecutionState.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if state is None:
            await self.refresh_project(
                db, organization_id=organization_id, project_id=project_id,
                event_name="execution.state_changed", source_event_id=None,
            )
            state = (
                await db.execute(
                    select(ProjectExecutionState).where(
                        ProjectExecutionState.organization_id == organization_id,
                        ProjectExecutionState.project_id == project_id,
                    )
                )
            ).scalar_one_or_none()
        if state is None:
            return None
        snapshots = list(
            (
                await db.execute(
                    select(ProjectExecutionSnapshot)
                    .where(
                        ProjectExecutionSnapshot.organization_id == organization_id,
                        ProjectExecutionSnapshot.project_id == project_id,
                    )
                    .order_by(ProjectExecutionSnapshot.occurred_at.desc())
                    .limit(MAX_HISTORY_SHOWN)
                )
            ).scalars().all()
        )
        return {
            "project_id": project.id,
            "code": project.code,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "priority": project.priority,
            "start_date": _iso(project.start_date),
            "end_date": _iso(project.end_date),
            "health_status": state.health_status,
            "health_score": state.health_score,
            "primary_cause": state.primary_cause,
            "explain": state.explain,
            "factors": state.factors,
            "counts": state.counts,
            "critical_path": state.critical_path,
            "blockers": state.blockers,
            "systemic_blockers": state.systemic_blockers,
            "capacity_constraints": state.capacity_constraints,
            "pending_decisions": state.pending_decisions,
            "goal_chain": state.goal_chain,
            "outcome": state.outcome,
            "history": [
                {
                    "id": s.id,
                    "event_name": s.event_name,
                    "health_score": s.health_score,
                    "health_status": s.health_status,
                    "primary_cause": s.primary_cause,
                    "explain": s.explain,
                    "occurred_at": _iso(s.occurred_at),
                }
                for s in snapshots
            ],
        }

    async def execution_next(
        self, db: AsyncSession, *, organization_id: str
    ) -> dict[str, Any]:
        """'What should happen next?' — deterministic, prioritized, bounded:
        unresolved decisions first (they gate downstream work), then
        critical-path pressure, blocked work on the path, overdue
        milestones, then high-priority work ready to start."""
        items: list[dict[str, Any]] = []
        projects = list(
            (
                await db.execute(
                    select(Project)
                    .where(
                        Project.organization_id == organization_id,
                        Project.status.in_(ACTIVE_STATUSES),
                    )
                    .order_by(Project.created_at.asc())
                    .limit(MAX_READY_PROJECTS)
                )
            ).scalars().all()
        )
        project_by_id = {p.id: p for p in projects}
        states = list(
            (
                await db.execute(
                    select(ProjectExecutionState).where(
                        ProjectExecutionState.organization_id == organization_id,
                        ProjectExecutionState.project_id.in_(
                            list(project_by_id.keys()) or [""],
                        ),
                    )
                )
            ).scalars().all()
        )

        today_iso = date.today().isoformat()
        for s in states:
            project = project_by_id.get(s.project_id)
            if project is None:
                continue
            for d in (s.pending_decisions or []):
                if d.get("open_actions", 0) > 0 and len(items) < MAX_NEXT_DECISIONS:
                    items.append({
                        "priority": len(items) + 1,
                        "kind": "decision",
                        "title": f"Resolve decision: {d['title']}",
                        "project_name": project.name,
                        "reason": (
                            f"It has {d['open_actions']} open action task(s) in "
                            f"{project.name} and gates downstream work."
                        ),
                    })
            cpath = s.critical_path or {}
            critical_ids = set(cpath.get("critical_task_ids") or [])
            for t in (cpath.get("tasks") or [])[:20]:
                if not t.get("critical"):
                    continue
                if t.get("due_date") and str(t["due_date"]) < today_iso:
                    items.append({
                        "priority": len(items) + 1,
                        "kind": "critical",
                        "title": f"Complete '{t['title']}' on the critical path",
                        "project_name": project.name,
                        "reason": (
                            f"It is past due and drives the projected finish of "
                            f"{project.name}."
                        ),
                    })
            for b in (s.blockers or []):
                if b["task_id"] in critical_ids:
                    root = b["chain"][0]["title"] if b["chain"] else "a dependency"
                    items.append({
                        "priority": len(items) + 1,
                        "kind": "blocked",
                        "title": f"Unblock '{b['title']}' in {project.name}",
                        "project_name": project.name,
                        "reason": (
                            f"It sits on the critical path and is blocked by "
                            f"'{root}'."
                        ),
                    })
            if (s.counts or {}).get("overdue_milestones"):
                items.append({
                    "priority": len(items) + 1,
                    "kind": "milestone",
                    "title": f"Reschedule the overdue milestone(s) of {project.name}",
                    "project_name": project.name,
                    "reason": (
                        f"{s.counts['overdue_milestones']} milestone(s) are past "
                        f"due — launch risk elevated."
                    ),
                })
            if len(items) >= MAX_NEXT_ITEMS:
                break

        for p in projects:
            ready = (
                await db.execute(
                    select(Task)
                    .where(
                        Task.organization_id == organization_id,
                        Task.project_id == p.id,
                        Task.status.in_(("backlog", "todo")),
                        Task.priority.in_(("high", "critical")),
                    )
                    .order_by(Task.priority.desc(), Task.created_at.asc())
                    .limit(MAX_NEXT_READY_PER_PROJECT)
                )
            ).scalars().all()
            for t in ready:
                items.append({
                    "priority": len(items) + 1,
                    "kind": "ready",
                    "title": f"Start '{t.title}'",
                    "project_name": p.name,
                    "reason": (
                        f"It is {t.priority} priority and not blocked — begin it "
                        f"while {p.name} awaits its critical dependencies."
                    ),
                })
            if len(items) >= MAX_NEXT_ITEMS:
                break
        return {"total": len(items[:MAX_NEXT_ITEMS]), "items": items[:MAX_NEXT_ITEMS]}

    async def record_outcome(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        outcome: dict[str, Any],
        recorded_by: str,
    ) -> Optional[dict[str, Any]]:
        """The mandatory outcome record: planned vs actual + assessment.
        Outcomes become evidence — they never rewrite the project."""
        state = (
            await db.execute(
                select(ProjectExecutionState).where(
                    ProjectExecutionState.organization_id == organization_id,
                    ProjectExecutionState.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if state is None:
            return None
        status = outcome.get("status", "successful")
        if status not in ("successful", "partial", "unsuccessful"):
            status = "successful"
        state.outcome = {
            "status": status,
            "planned_outcome": outcome.get("planned_outcome"),
            "actual_outcome": outcome.get("actual_outcome"),
            "assessment": outcome.get("assessment"),
            "recorded_by": recorded_by,
            "recorded_at": datetime.now().isoformat(),
        }
        db.add(
            ProjectExecutionSnapshot(
                organization_id=organization_id,
                project_id=project_id,
                source_event_id=f"outcome:{uuid4().hex[:24]}",
                event_name="execution.outcome_recorded",
                health_score=state.health_score,
                health_status=state.health_status,
                primary_cause=state.primary_cause,
                explain=state.explain,
                factors=state.factors,
                occurred_at=datetime.now(),
            )
        )
        await self._prune_snapshots(
            db, organization_id=organization_id, project_id=project_id
        )
        return state.outcome

    # ---------------------------------------------------------------- helpers

    async def _employee_labels(
        self, db: AsyncSession, organization_id: str
    ) -> dict[str, str]:
        from app.models.employee import Employee

        rows = list(
            (
                await db.execute(
                    select(Employee).where(
                        Employee.organization_id == organization_id
                    )
                )
            ).scalars().all()
        )
        return {e.id: e.full_name for e in rows}

    async def _latest_snapshots(
        self, db: AsyncSession, *, organization_id: str, project_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        if not project_ids:
            return {}
        rows = list(
            (
                await db.execute(
                    select(ProjectExecutionSnapshot)
                    .where(
                        ProjectExecutionSnapshot.organization_id == organization_id,
                        ProjectExecutionSnapshot.project_id.in_(project_ids),
                    )
                    .order_by(ProjectExecutionSnapshot.occurred_at.desc())
                    .limit(len(project_ids) * 3)
                )
            ).scalars().all()
        )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for s in rows:
            grouped[s.project_id].append({
                "id": s.id,
                "event_name": s.event_name,
                "health_score": s.health_score,
                "health_status": s.health_status,
                "primary_cause": s.primary_cause,
                "occurred_at": _iso(s.occurred_at),
            })
        return dict(grouped)


execution_engine = ExecutionEngine()