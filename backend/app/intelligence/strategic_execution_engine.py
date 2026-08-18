"""Slice 4G.3 - Strategic Execution Engine.

Change-driven, advisory-only, evidence-backed strategic execution
intelligence. It consumes the canonical records already maintained by the
platform (projects, tasks, 4G.1 execution health, 4G.2 coordination
findings, 4F.6 capability records, customer project links, decisions) and
answers the strategy questions:

* are we achieving what matters (goal coverage / health),
* which work contributes to which company goal (goal -> work traceability),
* what is NOT aligned and what goals are under-covered (strategic gaps),
* where does the organization need to focus (portfolio focus / attention),
* what is threatening an objective (strategic risk),
* what happens if we delay work or change a priority (bounded what-if,
  impact propagation, alternatives - recommendations only, humans decide),
* did our strategy work (strategy -> outcome learning into 4E.7 memory).

Every write is exact-once on source_event_id and every event refreshes only
the AFFECTED goal's neighborhood, persisted as one StrategicSnapshot row -
never a full-org re-scan (5 -> 50,000+ rule). Nothing here mutates goals,
projects, people or capacity, and nothing is ever ranked for people.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models import CompanyGoal, CompanyInitiative, CompanyObjective
from app.models import StrategicHistory, StrategicLink, StrategicOutcome
from app.models import StrategicSnapshot
from app.models.execution_coordination import CoordinationIncident
from app.models.execution_intelligence import ProjectExecutionState
from app.models.employee import Employee
from app.models.org_capability_intelligence import OrgCapability
from app.models.project import Milestone, Project, ProjectMember
from app.models.task import Task, TaskDependency

from app.models.customer import Customer, CustomerProjectLink
from app.models.goal import Goal

logger = logging.getLogger("vcos.intelligence.strategy")

# --------------------------------------------------------------------------
# Deterministic thresholds and caps (5 -> 50,000+ bounded scans).
# --------------------------------------------------------------------------
HEALTHY_GOAL = 75          # coverage >= 75  -> healthy
AT_RISK_GOAL = 45          # coverage 45..74 -> at_risk; below -> critical
EXECUTION_WEIGHT = 0.5     # goal coverage = f(execution, capability, capacity)
CAPABILITY_WEIGHT = 0.3
CAPACITY_WEIGHT = 0.2
DEFAULT_HEALTH_SCORE = 80  # neutral when no 4G.1 execution row exists yet

ACTIVE_GOAL_STATUSES = ("draft", "active", "paused")
PROJECT_ACTIVE_STATUSES = ("draft", "active", "paused")
ALIGNED_KINDS = ("direct", "indirect", "weak")
CRITICAL_COORD_KINDS = ("critical_conflict", "propagation_risk")

MAX_PROJECTS_PER_GOAL = 200     # bounded neighborhood per goal
MAX_GOALS_PORTFOLIO = 200       # org portfolio view cap
MAX_CHAIN_DEPTH = 6
MAX_HISTORY_ROWS = 10
MAX_OUTCOME_ROWS = 100
MAX_DEPS_FOR_IMPACT = 300
MAX_CUSTOMERS = 10
MAX_PEOPLE = 12

# Event names this engine reacts to.
STRATEGY_EVENTS: frozenset[str] = frozenset(
    (
        "strategy.goal.created",
        "strategy.goal.updated",
        "strategy.goal.priority.changed",
        "strategy.objective.created",
        "strategy.objective.updated",
        "strategy.initiative.created",
        "strategy.initiative.updated",
        "strategy.initiative.linked",
        "strategy.initiative.unlinked",
        "strategy.outcome.recorded",
    )
)


def _coverage_from(exec_scores: list[float], capability_ok: int, capability_total: int,
                   staffed: int, active_projects: int) -> int:
    """The one coverage formula every surface shares (deterministic, 0..100)."""
    if active_projects <= 0:
        return 0
    execution = (sum(exec_scores) / len(exec_scores)) / 100.0
    capability = (capability_ok / capability_total) if capability_total else 1.0
    capacity = staffed / active_projects
    return round(100 * (EXECUTION_WEIGHT * execution
                        + CAPABILITY_WEIGHT * capability
                        + CAPACITY_WEIGHT * capacity))


def _health_for(coverage: int) -> str:
    if coverage >= HEALTHY_GOAL:
        return "healthy"
    if coverage >= AT_RISK_GOAL:
        return "at_risk"
    return "critical"


class StrategicExecutionEngine:
    """Canonical Strategic Execution Intelligence - one engine per org."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------ write

    async def record_event(
        self, db: AsyncSession, *, organization_id: str,
        event, payload: dict[str, Any],
    ) -> None:
        """Change-driven entry: capture the raw observation exact-once, then
        refresh ONLY the affected goal's neighborhood."""
        event_name = getattr(event, "name", "")
        source_event_id = getattr(event, "id", None)
        if event_name not in STRATEGY_EVENTS:
            return

        if event_name == "strategy.outcome.recorded":
            await self._capture_outcome(
                db, organization_id=organization_id,
                source_event_id=source_event_id, payload=payload,
            )
            goal_id = await self._goal_of_initiative(
                db, organization_id=organization_id,
                initiative_id=payload.get("initiative_id"),
            )
            await self.refresh(
                db, organization_id=organization_id, goal_id=goal_id,
                event_name=event_name, source_event_id=source_event_id,
            )
            return

        if event_name in ("strategy.initiative.linked", "strategy.initiative.unlinked"):
            await self._apply_link(
                db, organization_id=organization_id, event_name=event_name,
                source_event_id=source_event_id, payload=payload,
            )
            goal_id = await self._goal_of_initiative(
                db, organization_id=organization_id,
                initiative_id=payload.get("initiative_id"),
            )
            await self.refresh(
                db, organization_id=organization_id, goal_id=goal_id,
                event_name=event_name, source_event_id=source_event_id,
            )
            return

        await self._capture_history(
            db, organization_id=organization_id, event_name=event_name,
            source_event_id=source_event_id, payload=payload,
        )
        goal_id = await self._affected_goal(
            db, organization_id=organization_id, event_name=event_name,
            payload=payload,
        )
        await self.refresh(
            db, organization_id=organization_id, goal_id=goal_id,
            event_name=event_name, source_event_id=source_event_id,
        )

    # ------------------------------------------------------------- captures

    async def _capture_outcome(
        self, db: AsyncSession, *, organization_id: str,
        source_event_id: Optional[str], payload: dict[str, Any],
    ) -> None:
        """One expected-vs-actual observation per (initiative, event)."""
        initiative_id = payload.get("initiative_id")
        if not initiative_id or not source_event_id:
            return
        if (
            await db.execute(
                select(StrategicOutcome.id).where(
                    StrategicOutcome.organization_id == organization_id,
                    StrategicOutcome.initiative_id == initiative_id,
                    StrategicOutcome.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none():
            return
        initiative = (
            await db.execute(
                select(CompanyInitiative).where(
                    CompanyInitiative.organization_id == organization_id,
                    CompanyInitiative.id == initiative_id,
                )
            )
        ).scalar_one_or_none()
        if initiative is None:
            return
        expected = payload.get("expected_value") or (
            (initiative.expected_outcome or {}).get("target_value")
        )
        row = StrategicOutcome(
            organization_id=organization_id,
            initiative_id=initiative_id,
            initiative_label=initiative.title,
            project_id=payload.get("project_id"),
            project_label=payload.get("project_label", ""),
            metric_kind=payload.get("metric_kind") or "",
            unit=payload.get("unit") or "",
            expected_value=expected,
            actual_value=payload.get("actual_value"),
            source_event_id=source_event_id,
            recorded_at=utcnow(),
        )
        db.add(row)
        await db.flush()
        # Strategy -> outcome learning pours into the 4E.7 organizational
        # learning engine so the Company Model improves over time.
        if payload.get("actual_value") is not None and expected:
            try:
                ratio = float(payload["actual_value"]) / float(expected)
            except (TypeError, ValueError, ZeroDivisionError):
                ratio = None
            if ratio is None:
                return
            verdict = (
                "over-optimistic" if ratio < 0.9 else
                "under-optimistic" if ratio > 1.1 else
                "aligned"
            )
            try:
                from app.intelligence.learning_engine import learning_engine

                await learning_engine.record(
                    db, organization_id=organization_id,
                    event_type="strategy.outcome",
                    title=f"Strategy outcome for '{initiative.title}'",
                    detail=(
                        f"{payload.get('metric_kind') or 'metric'} actual "
                        f"{payload.get('actual_value')}{payload.get('unit', '')} "
                        f"vs expected {expected}{payload.get('unit', '')}"
                    ),
                    lesson=(
                        f"Strategic assumptions on {payload.get('metric_kind') or 'metric'} "
                        f"were {verdict} for '{initiative.title}' "
                        f"(actual/expected = {ratio:.2f})."
                    ),
                    entity_type="initiative",
                    entity_id=initiative_id,
                    tags=["strategy", "4g3"],
                )
            except Exception:  # pragma: no cover - learning is best-effort
                logger.exception("strategy outcome learning failed")

    async def _apply_link(
        self, db: AsyncSession, *, organization_id: str, event_name: str,
        source_event_id: Optional[str], payload: dict[str, Any],
    ) -> None:
        """Live link row exact-once; unlink removes the live link (history
        keeps the event trail)."""
        initiative_id = payload.get("initiative_id")
        project_id = payload.get("project_id")
        if not initiative_id or not project_id or not source_event_id:
            return
        if event_name == "strategy.initiative.unlinked":
            row = (
                await db.execute(
                    select(StrategicLink).where(
                        StrategicLink.organization_id == organization_id,
                        StrategicLink.initiative_id == initiative_id,
                        StrategicLink.project_id == project_id,
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                await db.delete(row)
            await db.flush()
            return
        if (
            await db.execute(
                select(StrategicLink.id).where(
                    StrategicLink.organization_id == organization_id,
                    StrategicLink.initiative_id == initiative_id,
                    StrategicLink.project_id == project_id,
                    StrategicLink.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none():
            return
        db.add(StrategicLink(
            organization_id=organization_id,
            initiative_id=initiative_id,
            project_id=project_id,
            source_event_id=source_event_id,
            linked_at=utcnow(),
        ))
        await db.flush()

    async def _capture_history(
        self, db: AsyncSession, *, organization_id: str, event_name: str,
        source_event_id: Optional[str], payload: dict[str, Any],
    ) -> None:
        """Append-only temporal trail: priority / status / field changes with
        the reason a human recorded (organizational memory, exact-once)."""
        if not source_event_id:
            return
        entity_type, label, changes = self._changes_of(event_name, payload)
        if not changes:
            return
        for field, old_value, new_value in changes:
            exists = (
                await db.execute(
                    select(StrategicHistory.id).where(
                        StrategicHistory.organization_id == organization_id,
                        StrategicHistory.entity_type == entity_type,
                        StrategicHistory.entity_id == payload.get("id"),
                        StrategicHistory.field == field,
                        StrategicHistory.source_event_id == source_event_id,
                    )
                )
            ).scalar_one_or_none()
            if exists:
                continue
            db.add(StrategicHistory(
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=payload.get("id"),
                entity_label=label,
                field=field,
                old_value=str(old_value) if old_value is not None else None,
                new_value=str(new_value) if new_value is not None else None,
                reason=payload.get("reason"),
                source_event_id=source_event_id,
                changed_at=utcnow(),
            ))

    def _changes_of(
        self, event_name: str, payload: dict[str, Any],
    ) -> tuple[str, str, list[tuple[str, Any, Any]]]:
        """Which history rows does an event produce? (entity_type, label,
        [(field, old, new)]) - empty when nothing changed."""
        entity_type = {
            "strategy.goal.created": "goal",
            "strategy.goal.updated": "goal",
            "strategy.goal.priority.changed": "goal",
            "strategy.objective.created": "objective",
            "strategy.objective.updated": "objective",
            "strategy.initiative.created": "initiative",
            "strategy.initiative.updated": "initiative",
        }.get(event_name)
        if entity_type is None:
            return "", "", []
        changes: list[tuple[str, Any, Any]] = []
        if event_name == "strategy.goal.priority.changed" and payload.get("old_priority") is not None:
            changes.append(("priority", payload.get("old_priority"),
                            payload.get("priority")))
        if payload.get("old_status") is not None and payload.get("status") is not None:
            changes.append(("status", payload.get("old_status"), payload.get("status")))
        if changes:
            return entity_type, payload.get("title") or payload.get("label") or "", changes
        if event_name.endswith(".created"):
            return entity_type, payload.get("title") or "", [("created", None, payload.get("status") or "active")]
        return entity_type, payload.get("title") or "", []

    # ------------------------------------------------------------- refresh

    async def refresh(
        self, db: AsyncSession, *, organization_id: str,
        goal_id: Optional[str], event_name: str,
        source_event_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Recompute ONE goal's neighborhood and persist the snapshot.

        Exact-once: a replayed event finds its snapshot row and changes
        nothing. Returns the assessment payload (empty dict when skipped).
        """
        if not goal_id or not source_event_id:
            return {}
        if (
            await db.execute(
                select(StrategicSnapshot.id).where(
                    StrategicSnapshot.organization_id == organization_id,
                    StrategicSnapshot.goal_id == goal_id,
                    StrategicSnapshot.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none():
            return {}
        async with self._locks[organization_id]:
            if (
                await db.execute(
                    select(StrategicSnapshot.id).where(
                        StrategicSnapshot.organization_id == organization_id,
                        StrategicSnapshot.goal_id == goal_id,
                        StrategicSnapshot.source_event_id == source_event_id,
                    )
                )
            ).scalar_one_or_none():
                return {}
            payload = await self.assess_goal(
                db, organization_id=organization_id, goal_id=goal_id,
            )
            coverage = payload.get("coverage", 0)
            db.add(StrategicSnapshot(
                organization_id=organization_id,
                goal_id=goal_id,
                source_event_id=source_event_id,
                event_name=event_name,
                coverage=coverage,
                health=_health_for(coverage),
                payload_json=payload,
                occurred_at=utcnow(),
            ))
        return payload

    # ----------------------------------------------------------- assessment

    async def assess_goal(
        self, db: AsyncSession, *, organization_id: str, goal_id: str,
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """The full evidence-backed assessment of one company goal."""
        goal = (
            await db.execute(
                select(CompanyGoal).where(
                    CompanyGoal.organization_id == organization_id,
                    CompanyGoal.id == goal_id,
                )
            )
        ).scalar_one_or_none()
        if goal is None:
            return {}
        chain = await self._chain(db, organization_id=organization_id, goal_id=goal_id)

        active_projects = [p for p in chain["projects"] if p.status in PROJECT_ACTIVE_STATUSES]
        project_ids = [p.id for p in active_projects]

        # ---- execution factor (4G.1 canonical health, neutral default)
        states = {
            s.project_id: s
            for s in (
                await db.execute(
                    select(ProjectExecutionState).where(
                        ProjectExecutionState.organization_id == organization_id,
                        ProjectExecutionState.project_id.in_(project_ids or [""]),
                    )
                )
            ).scalars().all()
        }
        exec_scores = [
            (states[p.id].health_score if p.id in states else DEFAULT_HEALTH_SCORE)
            for p in active_projects
        ]

        # ---- capability factor (4F.6 org capability ledger)
        required = chain["required_capabilities"]
        caps = {
            c.canonical_name.lower(): c
            for c in (
                await db.execute(
                    select(OrgCapability).where(
                        OrgCapability.organization_id == organization_id,
                    )
                )
            ).scalars().all()
        }
        capability_rows: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        capability_ok = 0
        for name in required:
            row = caps.get(name.lower())
            if row is None:
                missing.append({"capability": name, "reason": "capability absent"})
                continue
            state = (row.capacity_state or "unknown")
            capability_rows.append({
                "capability": row.canonical_name, "capacity_state": state,
                "capacity_available": row.capacity_available,
                "experts": row.expert_count,
            })
            if state in ("available", "stretched"):
                capability_ok += 1
            else:
                missing.append({
                    "capability": row.canonical_name,
                    "reason": f"capacity {state}",
                })

        # ---- capacity factor (staffed projects / active projects)
        staffed_ids = set(
            (
                await db.execute(
                    select(ProjectMember.project_id).where(
                        ProjectMember.organization_id == organization_id,
                        ProjectMember.project_id.in_(project_ids or [""]),
                    )
                )
            ).scalars().all()
        )
        staffed = len(staffed_ids)

        coverage = _coverage_from(
            exec_scores, capability_ok, len(required), staffed, len(active_projects),
        )
        health = _health_for(coverage)

        # ---- people contributing (bounded, evidence only)
        member_rows = (
            await db.execute(
                select(ProjectMember.project_id, ProjectMember.employee_id).where(
                    ProjectMember.organization_id == organization_id,
                    ProjectMember.project_id.in_(project_ids or [""]),
                )
            )
        ).all() if project_ids else []
        people_ids = sorted({r.employee_id for r in member_rows})
        people: list[dict[str, Any]] = []
        if people_ids:
            employees = (
                await db.execute(
                    select(Employee).where(
                        Employee.organization_id == organization_id,
                        Employee.id.in_(people_ids[:MAX_PEOPLE]),
                    )
                )
            ).scalars().all()
            by_id = {e.id: e for e in employees}
            for pid in people_ids[:MAX_PEOPLE]:
                emp = by_id.get(pid)
                if emp is None:
                    continue
                people.append({
                    "person_id": pid,
                    "label": employee_label(emp),
                    "project_count": sum(1 for r in member_rows if r.employee_id == pid),
                })

        # ---- coordination pressure on the goal's projects (4G.2 canonical)
        coord_rows = (
            await db.execute(
                select(CoordinationIncident).where(
                    CoordinationIncident.organization_id == organization_id,
                    CoordinationIncident.status == "open",
                    CoordinationIncident.kind.in_(CRITICAL_COORD_KINDS),
                    CoordinationIncident.project_id.in_(project_ids or [""]),
                )
            )
        ).scalars().all() if project_ids else []
        critical_deps: list[dict[str, Any]] = [
            {"incident_id": c.id, "kind": c.kind, "title": c.title,
             "project_id": c.project_id}
            for c in coord_rows[:10]
        ]

        # ---- decisions blocking the goal's chain (4D linkage)
        decision_bottlenecks = 0
        decision_labels: list[str] = []
        for p in active_projects:
            state = states.get(p.id)
            pending = (state.pending_decisions or []) if state else []
            decision_bottlenecks += len(pending)
            decision_labels.extend(
                f"{p.name}: {d.get('title', '')}" for d in pending[:3]
            )

        # ---- timeline evidence
        at_risk_projects = [
            {"project_id": p.id, "name": p.name,
             "health_status": (states[p.id].health_status if p.id in states else "unknown"),
             "primary_cause": (states[p.id].primary_cause if p.id in states else None)}
            for p in active_projects
            if (states[p.id].health_status if p.id in states else "healthy") != "healthy"
        ]

        # ---- customer linkage (lateral: strategy -> customers where linked)
        linked_customer_ids = set(
            (
                await db.execute(
                    select(CustomerProjectLink.customer_id).where(
                        CustomerProjectLink.organization_id == organization_id,
                        CustomerProjectLink.project_id.in_(project_ids or [""]),
                        CustomerProjectLink.status == "active",
                    )
                )
            ).scalars().all()
        )
        linked_customers: list[str] = []
        if linked_customer_ids:
            cust_rows = (
                await db.execute(
                    select(Customer).where(
                        Customer.organization_id == organization_id,
                        Customer.id.in_(list(linked_customer_ids)[:MAX_CUSTOMERS]),
                    )
                )
            ).scalars().all()
            linked_customers = [c.company_name for c in cust_rows]
        declared_commitments: list[dict[str, Any]] = []
        for init in chain["initiatives"]:
            declared_commitments.extend(init.customer_commitments or [])

        # ---- strategic risk lines (evidence, not opinion)
        risks: list[str] = []
        if not active_projects:
            risks.append("No active execution is linked to this goal.")
        if missing:
            risks.append(
                "Required capability not available or constrained: "
                + ", ".join(m["capability"] for m in missing[:4])
            )
        if staffed < len(active_projects):
            risks.append(
                f"{len(active_projects) - staffed} of {len(active_projects)} "
                "linked project(s) have no assigned people."
            )
        if critical_deps:
            risks.append(
                f"{len(critical_deps)} critical coordination finding(s) "
                "affect linked projects."
            )
        if at_risk_projects:
            risks.append(
                f"{len(at_risk_projects)} linked project(s) are not healthy: "
                + ", ".join(p["name"] for p in at_risk_projects[:3])
            )
        if not risks:
            risks.append("No current strategic risk observed on the evidence.")

        primary_reason = self._primary_reason(
            active_projects, missing, staffed, len(active_projects), coverage, health,
        )

        # ---- outcomes + learning (strategy -> outcome -> learning)
        outcomes = await self._outcomes_for_goal(
            db, organization_id=organization_id, chain=chain,
        )

        # ---- temporal memory (why did this become a priority?)
        history = await self._history_for_goal(
            db, organization_id=organization_id, goal_id=goal_id, chain=chain,
        )

        projects_view = [{
            "project_id": p.id, "name": p.name, "status": p.status,
            "health_status": (states[p.id].health_status if p.id in states else "unknown"),
            "health_score": (states[p.id].health_score if p.id in states else DEFAULT_HEALTH_SCORE),
            "staffed": p.id in staffed_ids,
            "behind": bool((states[p.id].counts or {}).get("overdue_tasks"))
            if p.id in states else False,
        } for p in active_projects[:MAX_PROJECTS_PER_GOAL]]

        payload: dict[str, Any] = {
            "goal": {
                "goal_id": goal.id, "title": goal.title, "kind": goal.kind,
                "status": goal.status, "priority": goal.priority,
                "priority_label": _priority_label(goal.priority),
                "metric_kind": goal.metric_kind, "metric_unit": goal.metric_unit,
                "target_value": goal.target_value, "current_value": goal.current_value,
                "owner_label": goal.owner_label, "timeline_label": goal.timeline_label,
            },
            "objectives": [{
                "objective_id": o.id, "title": o.title, "kind": o.kind,
                "status": o.status, "required_capabilities": o.required_capabilities or [],
                "owner_label": o.owner_label,
            } for o in chain["objectives"]],
            "initiatives": [{
                "initiative_id": i.id, "title": i.title, "kind": i.kind,
                "status": i.status, "required_capabilities": i.required_capabilities or [],
                "customer_commitments": i.customer_commitments or [],
                "expected_outcome": i.expected_outcome or {},
                "owner_label": i.owner_label,
            } for i in chain["initiatives"]],
            "coverage": coverage,
            "health": health,
            "factors": {
                "execution": round(
                    (sum(exec_scores) / len(exec_scores) if exec_scores else 0) / 100.0, 3),
                "capability": round(capability_ok / len(required), 3) if required else 1.0,
                "capacity": round(staffed / len(active_projects), 3) if active_projects else 0.0,
                "weights": {"execution": EXECUTION_WEIGHT, "capability": CAPABILITY_WEIGHT,
                            "capacity": CAPACITY_WEIGHT},
            },
            "primary_reason": primary_reason,
            "evidence": risks,
            "missing_capabilities": missing,
            "capabilities": capability_rows[:20],
            "projects": projects_view,
            "people": people,
            "critical_dependencies": critical_deps,
            "decision_bottlenecks": {
                "count": decision_bottlenecks,
                "labels": decision_labels[:6],
            },
            "timeline": {
                "active_projects": len(active_projects),
                "at_risk_projects": at_risk_projects[:8],
                "milestone_count": chain["milestone_count"],
            },
            "customers": {
                "linked_customers": linked_customers,
                "declared_commitments": declared_commitments[:10],
            },
            "risks": risks,
            "outcomes": outcomes["outcomes"],
            "learning": outcomes["learning"],
            "history": history,
        }
        if extra:
            payload.update(extra)
        return payload

    def _primary_reason(
        self, active_projects: list[Any], missing: list[dict[str, Any]],
        staffed: int, active_total: int, coverage: int, health: str,
    ) -> str:
        if health == "healthy":
            return "Goal coverage is healthy on current execution evidence."
        if not active_projects:
            return "No active execution is linked to this goal (coverage 0)."
        constrained = [m["capability"] for m in missing if m["reason"] != "capability absent"]
        if constrained:
            return (
                f"Required capability {', '.join(constrained[:2])} is "
                f"constrained ({coverage}/100)."
            )
        if staffed < active_total:
            return (
                f"{active_total - staffed} linked project(s) have no assigned "
                f"people ({coverage}/100)."
            )
        return f"Execution evidence is below target ({coverage}/100)."

    # ------------------------------------------------------------ chain & io

    async def _chain(
        self, db: AsyncSession, *, organization_id: str, goal_id: str,
    ) -> dict[str, Any]:
        """The goal's neighborhood: objectives -> initiatives -> links ->
        projects (bounded batches, never a full-org scan)."""
        objectives = list(
            (
                await db.execute(
                    select(CompanyObjective).where(
                        CompanyObjective.organization_id == organization_id,
                        CompanyObjective.goal_id == goal_id,
                    )
                )
            ).scalars().all()
        )
        objective_ids = [o.id for o in objectives][:50]
        initiatives = list(
            (
                await db.execute(
                    select(CompanyInitiative).where(
                        CompanyInitiative.organization_id == organization_id,
                        CompanyInitiative.objective_id.in_(objective_ids or [""]),
                    )
                )
            ).scalars().all()
        )
        initiative_ids = [i.id for i in initiatives][:100]
        links = list(
            (
                await db.execute(
                    select(StrategicLink).where(
                        StrategicLink.organization_id == organization_id,
                        StrategicLink.initiative_id.in_(initiative_ids or [""]),
                    )
                )
            ).scalars().all()
        )
        project_ids = list(dict.fromkeys(link.project_id for link in links))[
            :MAX_PROJECTS_PER_GOAL
        ]
        projects = list(
            (
                await db.execute(
                    select(Project).where(
                        Project.organization_id == organization_id,
                        Project.id.in_(project_ids or [""]),
                    )
                )
            ).scalars().all()
        )
        milestone_count = (
            await self._milestone_count(db, organization_id, project_ids)
        )
        required = [
            cap
            for node in [*objectives, *initiatives]
            for cap in (node.required_capabilities or [])
        ]
        return {
            "goal": None,
            "objectives": objectives,
            "initiatives": initiatives,
            "links": links,
            "projects": projects,
            "milestone_count": milestone_count,
            "required_capabilities": list(dict.fromkeys(required)),
        }

    async def _milestone_count(
        self, db: AsyncSession, organization_id: str, project_ids: list[str],
    ) -> int:
        if not project_ids:
            return 0
        return int(
            (
                await db.execute(
                    select(func.count(Milestone.id)).where(
                        Milestone.organization_id == organization_id,
                        Milestone.project_id.in_(project_ids or [""]),
                    )
                )
            ).scalar_one() or 0
        )

    async def _goal_of_initiative(
        self, db: AsyncSession, *, organization_id: str,
        initiative_id: Optional[str],
    ) -> Optional[str]:
        if not initiative_id:
            return None
        initiative = (
            await db.execute(
                select(CompanyInitiative).where(
                    CompanyInitiative.organization_id == organization_id,
                    CompanyInitiative.id == initiative_id,
                )
            )
        ).scalar_one_or_none()
        if initiative is None:
            return None
        objective = (
            await db.execute(
                select(CompanyObjective).where(
                    CompanyObjective.organization_id == organization_id,
                    CompanyObjective.id == initiative.objective_id,
                )
            )
        ).scalar_one_or_none()
        return objective.goal_id if objective else None

    async def _affected_goal(
        self, db: AsyncSession, *, organization_id: str,
        event_name: str, payload: dict[str, Any],
    ) -> Optional[str]:
        """The goal an event touches: payload goal_id directly, or resolved
        from the objective / initiative ids when the event is a child node."""
        goal_id = payload.get("goal_id")
        if goal_id:
            return goal_id
        objective_id = payload.get("objective_id")
        if event_name.startswith("strategy.objective") and objective_id:
            objective = (
                await db.execute(
                    select(CompanyObjective).where(
                        CompanyObjective.organization_id == organization_id,
                        CompanyObjective.id == objective_id,
                    )
                )
            ).scalar_one_or_none()
            return objective.goal_id if objective else None
        initiative_id = payload.get("initiative_id")
        if initiative_id:
            return await self._goal_of_initiative(
                db, organization_id=organization_id, initiative_id=initiative_id,
            )
        if objective_id:
            objective = (
                await db.execute(
                    select(CompanyObjective).where(
                        CompanyObjective.organization_id == organization_id,
                        CompanyObjective.id == objective_id,
                    )
                )
            ).scalar_one_or_none()
            return objective.goal_id if objective else None
        return None

    async def _outcomes_for_goal(
        self, db: AsyncSession, *, organization_id: str, chain: dict[str, Any],
    ) -> dict[str, Any]:
        initiative_ids = [i.id for i in chain["initiatives"]]
        rows = list(
            (
                await db.execute(
                    select(StrategicOutcome).where(
                        StrategicOutcome.organization_id == organization_id,
                        StrategicOutcome.initiative_id.in_(initiative_ids or [""]),
                    )
                )
            ).scalars().all()
        )[:MAX_OUTCOME_ROWS]
        outcomes = [{
            "initiative_id": r.initiative_id, "initiative_label": r.initiative_label,
            "project_label": r.project_label, "metric_kind": r.metric_kind,
            "unit": r.unit, "expected_value": r.expected_value,
            "actual_value": r.actual_value, "recorded_at": _iso(r.recorded_at),
        } for r in rows]
        return {"outcomes": outcomes, "learning": self._learning_from(rows)}

    def _learning_from(
        self, rows: list[StrategicOutcome],
    ) -> list[dict[str, Any]]:
        by_kind: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            if r.expected_value and r.actual_value is not None:
                try:
                    ratio = float(r.actual_value) / float(r.expected_value)
                except (TypeError, ValueError, ZeroDivisionError):
                    continue
                by_kind[r.metric_kind or "other"].append(ratio)
        learning: list[dict[str, Any]] = []
        for kind, ratios in by_kind.items():
            mean = sum(ratios) / len(ratios)
            verdict = (
                "over-optimistic" if mean < 0.9 else
                "under-optimistic" if mean > 1.1 else
                "aligned"
            )
            learning.append({
                "metric_kind": kind, "samples": len(ratios),
                "mean_actual_over_expected": round(mean, 3),
                "verdict": verdict,
                "explain": (
                    f"{len(ratios)} observed outcome(s) for {kind}; actual "
                    f"reached {mean:.0%} of expected on average."
                ),
            })
        return learning

    async def _history_for_goal(
        self, db: AsyncSession, *, organization_id: str, goal_id: str,
        chain: dict[str, Any],
    ) -> list[dict[str, Any]]:
        entity_ids = [goal_id]
        entity_ids += [o.id for o in chain["objectives"]]
        entity_ids += [i.id for i in chain["initiatives"]]
        rows = list(
            (
                await db.execute(
                    select(StrategicHistory).where(
                        StrategicHistory.organization_id == organization_id,
                        StrategicHistory.entity_id.in_(entity_ids or [""]),
                    )
                )
            ).scalars().all()
        )
        rows.sort(key=lambda r: r.changed_at)
        return [{
            "entity_type": r.entity_type, "entity_label": r.entity_label,
            "field": r.field, "old_value": r.old_value, "new_value": r.new_value,
            "reason": r.reason, "changed_at": _iso(r.changed_at),
        } for r in rows[-MAX_HISTORY_ROWS:]]

    # -------------------------------------------------------------- surfaces

    async def portfolio(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """Portfolio health: every number explainable, none invented."""
        goals = list(
            (
                await db.execute(
                    select(CompanyGoal).where(
                        CompanyGoal.organization_id == organization_id,
                        CompanyGoal.status.in_(ACTIVE_GOAL_STATUSES),
                    )
                )
            ).scalars().all()
        )[:MAX_GOALS_PORTFOLIO]

        goals_view: list[dict[str, Any]] = []
        for goal in goals:
            snapshot = await self._latest_snapshot(
                db, organization_id=organization_id, goal_id=goal.id,
            )
            payload = snapshot.payload_json if snapshot else (
                await self.assess_goal(db, organization_id=organization_id, goal_id=goal.id)
            )
            goals_view.append({
                **payload.get("goal", {"goal_id": goal.id, "title": goal.title}),
                "coverage": payload.get("coverage", 0),
                "health": payload.get("health", "critical"),
                "primary_reason": payload.get("primary_reason"),
                "priority": goal.priority,
                "priority_label": _priority_label(goal.priority),
                "active_projects": len(payload.get("projects", [])),
                "risk_count": len(payload.get("risks", [])),
            })
        goals_view.sort(key=lambda g: (g["coverage"], -g["priority"]))

        # bounds for the aggregate rollup (per-goal snapshot O(goals), fine)
        active_goals = [g for g in goals_view if g["status"] in ACTIVE_GOAL_STATUSES]
        mean_coverage = (
            round(sum(g["coverage"] for g in active_goals) / len(active_goals))
            if active_goals else 0
        )

        focus = await self.focus(db, organization_id=organization_id, goals=goals_view)

        # ---- org-wide alignment rollup (bounded scan, advisory)
        alignment = await self._alignment_rollup(db, organization_id=organization_id)

        outcome_confidence, outcome_samples = await self._outcome_confidence(
            db, organization_id=organization_id,
        )

        return {
            "goals": goals_view,
            "health_summary": {
                "total": len(active_goals),
                "healthy": sum(1 for g in active_goals if g["health"] == "healthy"),
                "at_risk": sum(1 for g in active_goals if g["health"] == "at_risk"),
                "critical": sum(1 for g in active_goals if g["health"] == "critical"),
            },
            "mean_goal_coverage": mean_coverage,
            "alignment": alignment,
            "confidence": {
                "outcome_confidence": outcome_confidence,
                "outcome_samples": outcome_samples,
            },
            "focus": focus,
            "advisory_only": True,
        }

    async def _latest_snapshot(
        self, db: AsyncSession, *, organization_id: str, goal_id: str,
    ) -> Optional[StrategicSnapshot]:
        return (
            await db.execute(
                select(StrategicSnapshot)
                .where(
                    StrategicSnapshot.organization_id == organization_id,
                    StrategicSnapshot.goal_id == goal_id,
                )
                .order_by(StrategicSnapshot.occurred_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def goal_detail(
        self, db: AsyncSession, *, organization_id: str, goal_id: str,
        focus: Optional[list[dict[str, Any]]] = None,
    ) -> Optional[dict[str, Any]]:
        goal = (
            await db.execute(
                select(CompanyGoal).where(
                    CompanyGoal.organization_id == organization_id,
                    CompanyGoal.id == goal_id,
                )
            )
        ).scalar_one_or_none()
        if goal is None:
            return None
        snapshot = await self._latest_snapshot(
            db, organization_id=organization_id, goal_id=goal_id,
        )
        payload = snapshot.payload_json if snapshot else (
            await self.assess_goal(db, organization_id=organization_id, goal_id=goal_id)
        )
        if not payload:
            return None
        if focus is None:
            focus = await self.focus(db, organization_id=organization_id)
        payload["focus_rank"] = next(
            (i + 1 for i, f in enumerate(focus) if f.get("goal_id") == goal_id), None,
        )
        payload["snapshot_count"] = int(
            (
                await db.execute(
                    select(func.count(StrategicSnapshot.id)).where(
                        StrategicSnapshot.organization_id == organization_id,
                        StrategicSnapshot.goal_id == goal_id,
                    )
                )
            ).scalar_one() or 0
        )
        return payload

    async def focus(
        self, db: AsyncSession, *, organization_id: str,
        goals: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """TOP COMPANY ATTENTION: priority x (1 - coverage) x health penalty,
        each item explainable with the evidence behind it."""
        if goals is None:
            portfolio = await self.portfolio(db, organization_id=organization_id)
            goals = portfolio["goals"]
        items: list[dict[str, Any]] = []
        for g in goals:
            priority_weight = 6 - int(g.get("priority", 3))
            coverage = g.get("coverage", 0)
            score = priority_weight * (1 - coverage / 100)
            if g.get("health") == "critical":
                score += 6
            elif g.get("health") == "at_risk":
                score += 2
            why: list[str] = []
            why.append(f"company priority {g.get('priority_label', 'P3')}")
            if coverage < HEALTHY_GOAL:
                why.append(f"execution coverage {coverage}%")
            if g.get("health") == "critical":
                why.append("coverage is critical")
            elif g.get("health") == "at_risk":
                why.append("coverage is at risk")
            if g.get("risk_count", 0):
                why.append(f"{g.get('risk_count')} evidence risk(s) open")
            items.append({
                "goal_id": g.get("goal_id"), "title": g.get("title"),
                "kind": g.get("kind"), "priority": g.get("priority"),
                "priority_label": g.get("priority_label"), "coverage": coverage,
                "health": g.get("health"), "score": round(score, 3), "why": why,
            })
        items.sort(key=lambda i: (-i["score"], i["coverage"]))
        return items[:5]

    # ------------------------------------------------- alignment / gaps

    async def _alignment_rollup(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        buckets: dict[str, int] = {"direct": 0, "indirect": 0, "weak": 0, "none": 0}
        rows: list[tuple[str, Optional[str]]] = []
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
        project_ids = list(
            (
                await db.execute(
                    select(ProjectMember.project_id).where(
                        ProjectMember.organization_id == organization_id,
                    )
                )
            ).scalars().all()
        )
        # bounded: projects with members OR execution rows (the work that
        # exists); dedupe and cap before classification.
        seen: set[str] = set()
        for pid in project_ids[:400]:
            seen.add(pid)
        for s in states.values():
            seen.add(s.project_id)
        seen = set(list(seen)[:400])
        active = list(
            (
                await db.execute(
                    select(Project).where(
                        Project.organization_id == organization_id,
                        Project.id.in_(list(seen) or [""]),
                        Project.status.in_(PROJECT_ACTIVE_STATUSES),
                    )
                )
            ).scalars().all()
        )
        aligned_chains = await self._all_chains(db, organization_id=organization_id)
        for project in active:
            kind = self._project_alignment(project, states.get(project.id), aligned_chains)
            buckets[kind] += 1
            rows.append((project.id, project.name, kind, (states.get(project.id).goal_chain or []) if states.get(project.id) else []))
        total = sum(buckets.values())
        return {
            "total_active_projects": total,
            "direct": buckets["direct"],
            "indirect": buckets["indirect"],
            "weak": buckets["weak"],
            "none": buckets["none"],
            "aligned_pct": round(100 * (buckets["direct"] + buckets["indirect"]) / total)
            if total else 0,
            "unaligned_pct": round(100 * (buckets["none"] + buckets["weak"]) / total)
            if total else 0,
        }

    async def _all_chains(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, tuple[str, str, str]]:
        """project_id -> (initiative_status, objective_status, goal_status)."""
        links = list(
            (
                await db.execute(
                    select(StrategicLink).where(
                        StrategicLink.organization_id == organization_id,
                    )
                )
            ).scalars().all()
        )
        initiative_ids = list({l.initiative_id for l in links})
        initiatives = {
            i.id: i for i in (
                await db.execute(
                    select(CompanyInitiative).where(
                        CompanyInitiative.organization_id == organization_id,
                        CompanyInitiative.id.in_(initiative_ids or [""]),
                    )
                )
            ).scalars().all()
        }
        objective_ids = list({i.objective_id for i in initiatives.values()})
        objectives = {
            o.id: o for o in (
                await db.execute(
                    select(CompanyObjective).where(
                        CompanyObjective.organization_id == organization_id,
                        CompanyObjective.id.in_(objective_ids or [""]),
                    )
                )
            ).scalars().all()
        }
        goal_ids = list({o.goal_id for o in objectives.values()})
        goals = {
            g.id: g for g in (
                await db.execute(
                    select(CompanyGoal).where(
                        CompanyGoal.organization_id == organization_id,
                        CompanyGoal.id.in_(goal_ids or [""]),
                    )
                )
            ).scalars().all()
        }
        result: dict[str, tuple[str, str, str]] = {}
        for link in links:
            init = initiatives.get(link.initiative_id)
            obj = objectives.get(init.objective_id) if init else None
            goal = goals.get(obj.goal_id) if obj else None
            result.setdefault(link.project_id, (
                init.status if init else "retired",
                obj.status if obj else "retired",
                goal.status if goal else "retired",
            ))
        return result

    def _project_alignment(
        self, project: Project, state: Optional[ProjectExecutionState],
        aligned_chains: dict[str, tuple[str, str, str]],
    ) -> str:
        chain = aligned_chains.get(project.id)
        if chain is not None:
            init_status, obj_status, goal_status = chain
            if init_status == "active" and obj_status == "active" and goal_status == "active":
                return "direct"
            if init_status == "active" or obj_status == "active":
                return "indirect"
            return "weak"
        if state and state.goal_chain:
            return "weak"
        return "none"

    async def gaps(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """Strategic execution gaps: unaligned active work + under-covered
        goals. Advisory review list - never a verdict on the project itself."""
        aligned_chains = await self._all_chains(db, organization_id=organization_id)
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
        candidate_ids = set(aligned_chains.keys()) | set(states.keys())
        rows = list(
            (
                await db.execute(
                    select(Project).where(
                        Project.organization_id == organization_id,
                        Project.id.in_(list(candidate_ids)[:500] or [""]),
                        Project.status.in_(PROJECT_ACTIVE_STATUSES),
                    )
                )
            ).scalars().all()
        )
        all_active = list(
            (
                await db.execute(
                    select(Project).where(
                        Project.organization_id == organization_id,
                        Project.status.in_(PROJECT_ACTIVE_STATUSES),
                    )
                )
            ).scalars().all()
        )[:400]
        by_id = {p.id: p for p in rows}
        for p in all_active:
            by_id.setdefault(p.id, p)

        unaligned: list[dict[str, Any]] = []
        for project in by_id.values():
            state = states.get(project.id)
            kind = self._project_alignment(project, state, aligned_chains)
            if kind in ("weak", "none"):
                unaligned.append({
                    "project_id": project.id, "name": project.name,
                    "status": project.status,
                    "alignment": kind,
                    "reason": (
                        "no explicit relationship to an active strategic objective"
                        if kind == "none" else
                        "linked through a non-active strategic chain"
                    ),
                })
        unaligned.sort(key=lambda u: (u["alignment"] == "direct", u["name"]))

        under_covered: list[dict[str, Any]] = []
        for goal in (
            await db.execute(
                select(CompanyGoal).where(
                    CompanyGoal.organization_id == organization_id,
                    CompanyGoal.status.in_(ACTIVE_GOAL_STATUSES),
                )
            )
        ).scalars().all()[:MAX_GOALS_PORTFOLIO]:
            snapshot = await self._latest_snapshot(
                db, organization_id=organization_id, goal_id=goal.id,
            )
            coverage = snapshot.coverage if snapshot else 0
            if coverage < HEALTHY_GOAL:
                under_covered.append({
                    "goal_id": goal.id, "title": goal.title,
                    "priority": goal.priority, "priority_label": _priority_label(goal.priority),
                    "coverage": coverage, "health": _health_for(coverage),
                    "primary_reason": (snapshot.payload_json.get("primary_reason")
                                       if snapshot else "no snapshot yet"),
                    "missing": (snapshot.payload_json.get("missing_capabilities", [])
                                if snapshot else []),
                })
        under_covered.sort(key=lambda g: g["coverage"])

        return {
            "unaligned_projects": unaligned[:100],
            "unaligned_count": len(unaligned),
            "under_covered_goals": under_covered,
        }

    async def conflicts(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """Portfolio contention: a required capability constrained and claimed
        by TWO or more active projects under DIFFERENT goals. Advisory only:
        humans sequence; the engine explains the strategic stakes."""
        goals = list(
            (
                await db.execute(
                    select(CompanyGoal).where(
                        CompanyGoal.organization_id == organization_id,
                        CompanyGoal.status.in_(ACTIVE_GOAL_STATUSES),
                    )
                )
            ).scalars().all()
        )
        goal_by_id = {g.id: g for g in goals}
        caps = list(
            (
                await db.execute(
                    select(OrgCapability).where(
                        OrgCapability.organization_id == organization_id,
                        OrgCapability.capacity_state == "constrained",
                    )
                )
            ).scalars().all()
        )
        cap_names = {c.canonical_name.lower(): c.canonical_name for c in caps}
        # map goal -> projects -> required caps
        claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for goal in goals:
            payload = await self.assess_goal(
                db, organization_id=organization_id, goal_id=goal.id,
            )
            for cap in payload.get("missing_capabilities", []):
                if cap["capability"].lower() in cap_names:
                    claim[cap["capability"]].append({
                        "goal_id": goal.id, "goal_title": goal.title,
                        "priority": goal.priority,
                        "projects": [p["name"] for p in payload.get("projects", [])][:5],
                        "active_projects": len(payload.get("projects", [])),
                    })
        items: list[dict[str, Any]] = []
        for cap, claimants in claim.items():
            if len(claimants) < 2:
                continue
            claimants.sort(key=lambda c: c["priority"])
            items.append({
                "capability": cap,
                "claimants": claimants,
                "strategic_stakes": (
                    "Projects under higher-priority goals claim the same "
                    "constrained capability; sequencing review is advisory."
                ),
            })
        items.sort(key=lambda i: min(c["priority"] for c in i["claimants"]))
        return {"conflicts": items, "advisory_only": True}

    async def impact(
        self, db: AsyncSession, *, organization_id: str,
        project_id: str, delay_days: int,
    ) -> Optional[dict[str, Any]]:
        """What a delay reaches: downstream projects, the strategic chain,
        milestones, customers, decisions and the portfolio — recomputed from
        the same bounded graph 4G.2 uses. Not a forecast."""
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
        delay_days = max(0, min(delay_days, 90))

        affected = await self._downstream_projects(
            db, organization_id=organization_id, project_id=project_id,
        )
        chain_goals: list[dict[str, Any]] = []
        for init in await self._initiatives_of_project(
            db, organization_id=organization_id, project_id=project_id,
        ):
            objective = (
                await db.execute(
                    select(CompanyObjective).where(
                        CompanyObjective.organization_id == organization_id,
                        CompanyObjective.id == init.objective_id,
                    )
                )
            ).scalar_one_or_none()
            if objective is None:
                continue
            goal = (
                await db.execute(
                    select(CompanyGoal).where(
                        CompanyGoal.organization_id == organization_id,
                        CompanyGoal.id == objective.goal_id,
                    )
                )
            ).scalar_one_or_none()
            if goal is None:
                continue
            chain_goals.append({"goal": goal, "initiative": init})
        # simulate coverage under the delay (bounded, explicit assumption)
        weeks = max(1, delay_days // 7)
        simulated: list[dict[str, Any]] = []
        for entry in chain_goals:
            base = await self._latest_snapshot(
                db, organization_id=organization_id, goal_id=entry["goal"].id,
            )
            payload = base.payload_json if base else (
                await self.assess_goal(
                    db, organization_id=organization_id, goal_id=entry["goal"].id,
                )
            )
            penalty = min(30, 5 * weeks)
            simulated_coverage = max(0, payload.get("coverage", 0) - penalty)
            simulated.append({
                "goal_id": entry["goal"].id,
                "goal_title": entry["goal"].title,
                "initiative_title": entry["initiative"].title,
                "coverage_now": payload.get("coverage", 0),
                "coverage_simulated": simulated_coverage,
                "health_simulated": _health_for(simulated_coverage),
                "customer_commitments": entry["initiative"].customer_commitments or [],
            })

        commitment_count = sum(
            len(s["customer_commitments"]) for s in simulated
        )
        risk = "high" if any(
            s["health_simulated"] != "healthy" for s in simulated
        ) else "medium"

        return {
            "project_id": project.id,
            "project_name": project.name,
            "delay_days": delay_days,
            "assumption": (
                f"each full week of delay removes up to 5 points from linked "
                f"goal coverage (bounded sensitivity, not a prediction)",
            ),
            "downstream_projects": affected["projects"],
            "downstream_count": len(affected["projects"]),
            "milestone_count": affected["milestone_count"],
            "strategic_chain": simulated,
            "customer_commitments_at_risk": commitment_count,
            "decision_bottlenecks": affected["decision_bottlenecks"],
            "risk": risk,
            "portfolio_projects_affected": len(affected["projects"]) + 1,
            "bounds": (
                "assumes dependencies stay; does not reschedule anything; "
                "does not move milestones; humans decide."
            ),
        }

    async def _downstream_projects(
        self, db: AsyncSession, *, organization_id: str, project_id: str,
    ) -> dict[str, Any]:
        tasks = list(
            (
                await db.execute(
                    select(Task).where(
                        Task.organization_id == organization_id,
                        Task.project_id == project_id,
                    )
                )
            ).scalars().all()
        )[:MAX_DEPS_FOR_IMPACT]
        task_ids = [t.id for t in tasks]
        deps = list(
            (
                await db.execute(
                    select(TaskDependency).where(
                        TaskDependency.organization_id == organization_id,
                        TaskDependency.depends_on_task_id.in_(task_ids or [""]),
                    )
                )
            ).scalars().all()
        )
        dependent_task_ids = list({d.task_id for d in deps})
        dependent_projects = list(
            (
                await db.execute(
                    select(Task.project_id).where(
                        Task.organization_id == organization_id,
                        Task.id.in_(dependent_task_ids or [""]),
                    )
                )
            ).scalars().all()
        )
        dependent_ids = list(dict.fromkeys(dependent_projects))
        project_ids = [p for p in dependent_ids if p != project_id][:20]
        projects = {
            p.id: p for p in (
                await db.execute(
                    select(Project).where(
                        Project.organization_id == organization_id,
                        Project.id.in_(project_ids or [""]),
                    )
                )
            ).scalars().all()
        }
        milestone_count = 0
        decisions = 0
        states = {
            s.project_id: s
            for s in (
                await db.execute(
                    select(ProjectExecutionState).where(
                        ProjectExecutionState.organization_id == organization_id,
                        ProjectExecutionState.project_id.in_(project_ids or [""]),
                    )
                )
            ).scalars().all()
        }
        for pid in project_ids:
            milestone_count += await self._milestone_count(
                db, organization_id, [p.id for p in projects.values()],
            )
            break
        for state in states.values():
            decisions += len(state.pending_decisions or [])
        return {
            "projects": [
                {"project_id": p.id, "name": p.name,
                 "status": p.status,
                 "via": "task dependency",
                 "health": (states[p.id].health_status if p.id in states else "unknown")}
                for p in projects.values()
            ],
            "milestone_count": milestone_count,
            "decision_bottlenecks": decisions,
        }

    async def _initiatives_of_project(
        self, db: AsyncSession, *, organization_id: str, project_id: str,
    ) -> list[CompanyInitiative]:
        links = list(
            (
                await db.execute(
                    select(StrategicLink).where(
                        StrategicLink.organization_id == organization_id,
                        StrategicLink.project_id == project_id,
                    )
                )
            ).scalars().all()
        )
        initiative_ids = [l.initiative_id for l in links]
        return list(
            (
                await db.execute(
                    select(CompanyInitiative).where(
                        CompanyInitiative.organization_id == organization_id,
                        CompanyInitiative.id.in_(initiative_ids or [""]),
                    )
                )
            ).scalars().all()
        )

    async def what_if(
        self, db: AsyncSession, *, organization_id: str,
        goal_id: Optional[str] = None, project_id: Optional[str] = None,
        delay_days: int = 0, priority: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        """Bounded strategic what-if. Two supported changes:
        * delay a project (coverage sensitivity), or
        * change a goal's priority (focus re-ranking).
        Returns assumptions + impact; explicitly NOT a prediction."""
        focus_before = await self.focus(db, organization_id=organization_id)
        if priority is not None and goal_id:
            goal = (
                await db.execute(
                    select(CompanyGoal).where(
                        CompanyGoal.organization_id == organization_id,
                        CompanyGoal.id == goal_id,
                    )
                )
            ).scalar_one_or_none()
            if goal is None:
                return None
            portfolio = await self.portfolio(db, organization_id=organization_id)
            altered = []
            for g in portfolio["goals"]:
                item = dict(g)
                if g.get("goal_id") == goal_id:
                    item["priority"] = max(1, min(5, int(priority)))
                    item["priority_label"] = _priority_label(item["priority"])
                altered.append(item)
            after = await self.focus(db, organization_id=organization_id, goals=altered)
            return {
                "change": {
                    "type": "priority",
                    "goal_id": goal_id,
                    "goal_title": goal.title,
                    "priority": max(1, min(5, int(priority))),
                },
                "rank_before": next(
                    (i + 1 for i, f in enumerate(focus_before)
                     if f.get("goal_id") == goal_id), None),
                "rank_after": next(
                    (i + 1 for i, f in enumerate(after) if f.get("goal_id") == goal_id), None),
                "focus_before": focus_before,
                "focus_after": after,
                "assumptions": ["only the goal's priority changes; all execution evidence unchanged"],
                "not_a_prediction": True,
                "bounds": "re-ranking is deterministic but ignores future decisions",
            }
        if project_id and delay_days:
            impact = await self.impact(
                db, organization_id=organization_id,
                project_id=project_id, delay_days=delay_days,
            )
            if impact is None:
                return None
            return {
                "change": {"type": "delay", "project_id": project_id,
                           "project_name": impact["project_name"],
                           "delay_days": delay_days},
                "impact": impact,
                "assumptions": [impact["assumption"]],
                "not_a_prediction": True,
                "bounds": impact["bounds"],
            }
        return None

    async def alternatives(
        self, db: AsyncSession, *, organization_id: str, project_id: str,
    ) -> Optional[dict[str, Any]]:
        """Three bounded courses of action with the evidence and a
        recommendation. Humans decide; nothing is executed."""
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
        initiatives = await self._initiatives_of_project(
            db, organization_id=organization_id, project_id=project_id,
        )
        required_caps = list(dict.fromkeys(
            cap for i in initiatives for cap in (i.required_capabilities or [])
        ))
        constrained = []
        if required_caps:
            caps = {
                c.canonical_name.lower(): c
                for c in (
                    await db.execute(
                        select(OrgCapability).where(
                            OrgCapability.organization_id == organization_id,
                        )
                    )
                ).scalars().all()
            }
            constrained = [
                name for name in required_caps
                if (caps.get(name.lower()) and
                    (caps[name.lower()].capacity_state or "unknown") in ("constrained",))
            ]
        counts = (state.counts or {}) if state else {}
        overdue = int(counts.get("overdue_tasks") or 0)

        options = [
            {
                "key": "keep_scope",
                "title": "Keep scope",
                "effects": [
                    f"current timeline risk: {overdue} overdue task(s)"
                    if overdue else "no overdue tasks on current evidence",
                    "no dependency or milestone changes",
                ],
                "cost": "capacity pressure unchanged",
                "score": round(6 + (0 if overdue else 2), 1),
            },
            {
                "key": "reduce_scope",
                "title": "Reduce scope",
                "effects": [
                    "relieves capacity pressure on the shared capability",
                    "lower strategic value: coverage is not reduced but scope shrinks",
                ],
                "cost": "delivered value shrinks",
                "score": round(7 - (1 if not overdue else 0) + (1 if constrained else 0), 1),
            },
            {
                "key": "add_external_capability",
                "title": "Add external capability",
                "effects": [
                    f"needed because constrained capability: {', '.join(constrained)}"
                    if constrained else "no constrained capability in the chain — optional",
                    "timeline can hold with added capacity",
                ],
                "cost": "cost increases",
                "score": round(6 + (2 if constrained else -1), 1),
            },
        ]
        options.sort(key=lambda o: (-o["score"], o["cost"]))
        best = options[0]
        return {
            "project_id": project.id,
            "project_name": project.name,
            "options": options,
            "recommendation": (
                f"Option '{best['title']}' currently provides the best balance "
                "under the available evidence (advisory; sequencing and scope "
                "decisions remain with authorized owners)."
            ),
            "decision_linkage": {
                "open_decisions": len(state.pending_decisions or []) if state else 0,
                "labels": [d.get("title", "") for d in (state.pending_decisions or [])[:3]]
                if state else [],
            },
            "advisory_only": True,
        }

    async def _outcome_confidence(
        self, db: AsyncSession, *, organization_id: str,
    ) -> tuple[float, int]:
        rows = list(
            (
                await db.execute(
                    select(StrategicOutcome).where(
                        StrategicOutcome.organization_id == organization_id,
                    )
                )
            ).scalars().all()
        )[:200]
        ratios: list[float] = []
        for r in rows:
            if r.expected_value and r.actual_value is not None:
                try:
                    ratios.append(
                        min(1.0, max(0.0, 1 - abs(float(r.actual_value) / float(r.expected_value) - 1)))
                    )
                except (TypeError, ValueError, ZeroDivisionError):
                    continue
        if not ratios:
            return 0.0, 0
        return round(sum(ratios) / len(ratios), 3), len(ratios)


def _priority_label(priority: int) -> str:
    return f"P{max(1, min(5, int(priority)))}"


def employee_label(emp: Employee) -> str:
    if emp.display_name:
        return emp.display_name
    return " ".join(x for x in (emp.first_name or "", emp.last_name or "") if x)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


strategic_execution_engine = StrategicExecutionEngine()