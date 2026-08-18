"""Slice 4G.4 - Universal Resource & Capacity Allocation Engine.

Change-driven, advisory-only, evidence-backed resource & capacity
intelligence. It consumes the canonical records already maintained by the
platform (projects, tasks, people, 4F.6 capability records, 4F.2/4F.3
expertise trust scores, 4G.3 strategic chains, customer project links) and
answers the allocation questions:

* do we have the right resources in the right places (demand vs supply per
  capability in its EXECUTION WINDOW - never today's snapshot),
* where is the organization over capacity (bottlenecks, overloads),
* where is capacity wasted (under-utilization),
* which projects contend for the same scarce capability (contention with
  strategic stakes and priority ordering),
* how are resources being used against company strategy (traceability),
* what should we allocate (bounded alternatives with benefit/risk/
  confidence/evidence - humans decide, nothing is executed),
* what happens if we move units between projects (bounded what-if),
* did our allocations work (allocation -> outcome learning into 4E.7 memory).

Every write is exact-once on source_event_id and every event refreshes only
the AFFECTED (capability, window) neighborhood, persisted as one
CapacitySnapshot row - never a full-org re-scan (5 -> 50,000+ rule). Nothing
here mutates projects, people, skills or capacity, and nothing is ever
ranked for people. Access filtering happens before assembly (governance
scopes), not after.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models import (
    AllocationDemand,
    CapacityAllocation,
    CapacityHistory,
    CapacitySnapshot,
    CompanyGoal,
    CompanyInitiative,
    CompanyObjective,
    StrategicLink,
)
from app.models.customer import Customer, CustomerProjectLink
from app.models.employee import Employee
from app.models.org_capability_intelligence import OrgCapability
from app.models.project import Project, ProjectMember
from app.models.skill import ExpertiseScore
from app.models.task import Task

logger = logging.getLogger("vcos.intelligence.capacity")

# --------------------------------------------------------------------------
# Deterministic thresholds and caps (5 -> 50,000+ bounded scans).
# --------------------------------------------------------------------------
OVERLOAD_UTILIZATION = 1.0    # demand >= supply -> bottleneck / contention
PERSON_WEEK_HOURS = 40.0      # default per-person weekly capacity (evidence)
UNDER_UTILIZED_HOURS = 8.0    # a person with less committed work than this
DEFAULT_WINDOW_DAYS = 90      # window used when a demand has no explicit one

MAX_DEMANDS_PER_CAPABILITY = 500
MAX_CAPABILITIES_SURFACE = 100
MAX_PROJECTS_DETAIL = 40
MAX_GOALS_STAKES = 30
MAX_PEOPLE_OVERLOAD = 10
MAX_TEAMS_OVERLOAD = 10
MAX_HISTORY_ROWS = 10

ACTIVE_GOAL_STATUSES = ("draft", "active", "paused")
PROJECT_ACTIVE_STATUSES = ("draft", "active", "paused")
OPEN_TASK_STATUSES = ("backlog", "todo", "in_progress", "review", "blocked")

# Event names this engine reacts to.
CAPACITY_EVENTS: frozenset[str] = frozenset(
    (
        "capacity.demand.created",
        "capacity.demand.updated",
        "capacity.demand.removed",
        "capacity.allocation.created",
        "capacity.allocation.completed",
    )
)

_PROFICIENCY_THRESHOLD = {"expert": 70.0, "high": 50.0}


def _iso(d: date | None) -> str:
    return d.isoformat() if d else ""


def _parse_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _window_overlaps(ws: date, we: date, ows: date, owe: date) -> bool:
    return ows <= we and owe >= ws


def _utilization(demand: int, available: int) -> float:
    if available <= 0:
        return round(1.0 * 100 * (1 if demand else 0), 1)
    return round(100.0 * demand / available, 1)


class ResourceAllocationEngine:
    """Canonical Resource & Capacity Allocation Intelligence - one engine."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------ write

    async def record_event(
        self, db: AsyncSession, *, organization_id: str,
        event, payload: dict[str, Any],
    ) -> None:
        """Change-driven entry: capture the temporal trail exact-once, then
        refresh ONLY the affected (capability, window) neighborhood."""
        event_name = getattr(event, "name", "")
        source_event_id = getattr(event, "id", None)
        if event_name not in CAPACITY_EVENTS or not source_event_id:
            return

        capability = (payload.get("capability") or "").strip()[:120]
        window_start = _parse_date(payload.get("window_start"))
        window_end = _parse_date(payload.get("window_end"))
        if not capability or not window_start or not window_end:
            return

        if event_name == "capacity.allocation.completed":
            await self._capture_allocation_learning(
                db, organization_id=organization_id,
                source_event_id=source_event_id, payload=payload,
            )

        await self._capture_history(
            db, organization_id=organization_id, event_name=event_name,
            source_event_id=source_event_id, payload=payload,
        )
        await self.refresh(
            db, organization_id=organization_id,
            capability=capability, window_start=window_start, window_end=window_end,
            event_name=event_name, source_event_id=source_event_id,
        )

    # ------------------------------------------------------------- captures

    async def _capture_history(
        self, db: AsyncSession, *, organization_id: str,
        event_name: str, source_event_id: str, payload: dict[str, Any],
    ) -> None:
        """Append-only temporal trail, one row per (entity, field, event)."""
        capability = (payload.get("capability") or "")[:120]
        project_id = payload.get("project_id") or ""
        project_label = (payload.get("project_label") or "")[:300]
        units = payload.get("units")
        ws = _iso(_parse_date(payload.get("window_start")))
        we = _iso(_parse_date(payload.get("window_end")))

        if event_name in ("capacity.demand.created", "capacity.demand.updated",
                          "capacity.demand.removed"):
            entity_type, entity_id, entity_label = "demand", project_id, project_label
            field = capability
            if event_name == "capacity.demand.created":
                old_value, new_value, reason = None, f"{units}u {ws}..{we}", None
            elif event_name == "capacity.demand.updated":
                old_value = f"{payload.get('old_units', units)}u {ws}..{we}"
                new_value = f"{units}u {ws}..{we}"
                reason = payload.get("reason")
            else:
                old_value = f"{units}u {ws}..{we}"
                new_value = "removed"
                reason = payload.get("reason")
        elif event_name == "capacity.allocation.created":
            entity_type, entity_id = "allocation", payload.get("allocation_id") or ""
            entity_label = project_label
            field, old_value = "created", None
            new_value = f"{units}u {capability} {ws}..{we}"
            reason = None
        else:  # capacity.allocation.completed
            entity_type, entity_id = "allocation", payload.get("allocation_id") or ""
            entity_label = project_label
            field, old_value = "status", "active"
            new_value = f"completed:{payload.get('outcome')}"
            reason = payload.get("note")

        if not entity_id or not source_event_id:
            return
        exists = (
            await db.execute(
                select(CapacityHistory.id).where(
                    CapacityHistory.organization_id == organization_id,
                    CapacityHistory.entity_type == entity_type,
                    CapacityHistory.entity_id == entity_id,
                    CapacityHistory.field == field,
                    CapacityHistory.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none()
        if exists:
            return
        db.add(CapacityHistory(
            organization_id=organization_id,
            entity_type=entity_type, entity_id=entity_id,
            entity_label=entity_label, field=field,
            old_value=old_value, new_value=new_value, reason=reason,
            source_event_id=source_event_id, changed_at=utcnow(),
        ))
        await db.flush()

    async def _capture_allocation_learning(
        self, db: AsyncSession, *, organization_id: str,
        source_event_id: str, payload: dict[str, Any],
    ) -> None:
        """Allocation -> outcome learning pours into the 4E.7 organizational
        learning engine: VCOS gets smarter from its own allocation history."""
        outcome = payload.get("outcome") or ""
        if outcome not in ("achieved", "partial", "missed"):
            return
        verdict = {
            "achieved": "effective",
            "partial": "partially effective",
            "missed": "ineffective",
        }[outcome]
        capability = (payload.get("capability") or "resource")[:120]
        project_label = (payload.get("project_label") or "the project")[:300]
        ws = _iso(_parse_date(payload.get("window_start")))
        we = _iso(_parse_date(payload.get("window_end")))
        try:
            from app.intelligence.learning_engine import learning_engine

            await learning_engine.record(
                db, organization_id=organization_id,
                event_type="capacity.allocation",
                title=f"Allocation outcome for '{project_label}'",
                detail=(
                    f"{payload.get('units')} units of {capability} "
                    f"({ws}..{we}) recorded {outcome}"
                ),
                lesson=(
                    f"Allocating {payload.get('units')} units of {capability} to "
                    f"'{project_label}' in the {ws}..{we} window was {verdict} "
                    f"(outcome {outcome})."
                ),
                entity_type="project",
                entity_id=payload.get("project_id") or "",
                tags=["capacity", "4g4"],
            )
        except Exception:  # pragma: no cover - learning is best-effort
            logger.exception("capacity allocation learning failed")

    # ------------------------------------------------------------- evidence

    async def _supply(
        self, db: AsyncSession, *, organization_id: str, capability: str,
    ) -> dict[str, Any]:
        """Supply for one capability from the 4F.6 ledger (read-only) plus
        the 4F.2/4F.3 expertise fit: how many people have TRUSTED evidence
        at the demanded proficiency - capability fit, not headcount."""
        row = (
            await db.execute(
                select(OrgCapability).where(
                    OrgCapability.organization_id == organization_id,
                    OrgCapability.canonical_name == capability,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return {
                "potential": 0, "committed": 0, "reserved": 0, "available": 0,
                "state": "unknown", "skill_id": None, "experts": 0,
                "fit_high": 0, "fit_expert": 0,
            }
        fit = await self._fit_people(
            db, organization_id=organization_id, skill_id=row.skill_id,
        )
        return {
            "potential": int(row.capacity_potential or 0),
            "committed": int(row.capacity_committed or 0),
            "reserved": int(row.capacity_reserved or 0),
            "available": int(row.capacity_available or 0),
            "state": row.capacity_state or "unknown",
            "skill_id": row.skill_id,
            "experts": int(row.expert_count or 0),
            "fit_high": fit[0], "fit_expert": fit[1],
        }

    async def _fit_people(
        self, db: AsyncSession, *, organization_id: str, skill_id: Optional[str],
    ) -> tuple[int, int]:
        """Count active people with strong/deep trusted expertise evidence."""
        if not skill_id:
            return 0, 0
        rows = (
            await db.execute(
                select(ExpertiseScore.employee_id, ExpertiseScore.score)
                .join(Employee, ExpertiseScore.employee_id == Employee.id)
                .where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.skill_id == skill_id,
                    Employee.organization_id == organization_id,
                    Employee.status == "active",
                )
            )
        ).all()
        strong = deep = 0
        for _, score in rows:
            score = float(score or 0.0)
            if score >= _PROFICIENCY_THRESHOLD["expert"]:
                deep += 1
            if score >= _PROFICIENCY_THRESHOLD["high"]:
                strong += 1
        return strong, deep

    async def _demands(
        self, db: AsyncSession, *, organization_id: str,
        capability: str, window_start: date, window_end: date,
    ) -> list[AllocationDemand]:
        return list(
            (
                await db.execute(
                    select(AllocationDemand)
                    .where(
                        AllocationDemand.organization_id == organization_id,
                        AllocationDemand.capability == capability,
                    )
                    .order_by(AllocationDemand.created_at)
                )
            ).scalars().all()
        )[:MAX_DEMANDS_PER_CAPABILITY]

    async def _allocations(
        self, db: AsyncSession, *, organization_id: str,
        capability: str, window_start: date, window_end: date,
        active_only: bool = True,
    ) -> list[CapacityAllocation]:
        stmt = select(CapacityAllocation).where(
            CapacityAllocation.organization_id == organization_id,
            CapacityAllocation.capability == capability,
        )
        if active_only:
            stmt = stmt.where(CapacityAllocation.status == "active")
        return list((await db.execute(stmt)).scalars().all())

    async def _project_labels(
        self, db: AsyncSession, *, organization_id: str, project_ids: list[str],
    ) -> dict[str, str]:
        if not project_ids:
            return {}
        rows = (
            await db.execute(
                select(Project.id, Project.name).where(
                    Project.organization_id == organization_id,
                    Project.id.in_(project_ids),
                )
            )
        ).all()
        return {r[0]: r[1] for r in rows}

    async def _stakes(
        self, db: AsyncSession, *, organization_id: str, project_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """project -> {initiatives, goals (id/title/priority), customers}.
        Traceability through the 4G.3 strategic chains (read-only)."""
        if not project_ids:
            return {}
        links = list(
            (
                await db.execute(
                    select(StrategicLink).where(
                        StrategicLink.organization_id == organization_id,
                        StrategicLink.project_id.in_(project_ids),
                    )
                )
            ).scalars().all()
        )
        initiative_ids = {l.initiative_id for l in links}
        initiatives = {}
        if initiative_ids:
            initiatives = {
                i.id: i
                for i in (
                    await db.execute(
                        select(CompanyInitiative).where(
                            CompanyInitiative.organization_id == organization_id,
                            CompanyInitiative.id.in_(initiative_ids),
                        )
                    )
                ).scalars().all()
            }
        objective_ids = {i.objective_id for i in initiatives.values()}
        objectives = {}
        if objective_ids:
            objectives = {
                o.id: o
                for o in (
                    await db.execute(
                        select(CompanyObjective).where(
                            CompanyObjective.organization_id == organization_id,
                            CompanyObjective.id.in_(objective_ids),
                        )
                    )
                ).scalars().all()
            }
        goal_ids = {o.goal_id for o in objectives.values()}
        goals = {}
        if goal_ids:
            goals = {
                g.id: g
                for g in (
                    await db.execute(
                        select(CompanyGoal).where(
                            CompanyGoal.organization_id == organization_id,
                            CompanyGoal.id.in_(goal_ids),
                        )
                    )
                ).scalars().all()
            }
        customer_ids = list(
            (
                await db.execute(
                    select(CustomerProjectLink.customer_id).where(
                        CustomerProjectLink.organization_id == organization_id,
                        CustomerProjectLink.project_id.in_(project_ids),
                        CustomerProjectLink.status == "active",
                    )
                )
            ).scalars().all()
        )[:MAX_GOALS_STAKES]
        customers = {}
        if customer_ids:
            customers = {
                c.id: c.name
                for c in (
                    await db.execute(
                        select(Customer).where(
                            Customer.organization_id == organization_id,
                            Customer.id.in_(customer_ids),
                        )
                    )
                ).scalars().all()
            }
        result: dict[str, dict[str, Any]] = {}
        for link in links:
            initiative = initiatives.get(link.initiative_id)
            objective = objectives.get(initiative.objective_id) if initiative else None
            goal = goals.get(objective.goal_id) if objective else None
            entry = result.setdefault(link.project_id, {
                "initiatives": [], "goals": [], "customers": set(),
            })
            if initiative and initiative.id not in entry["initiatives"]:
                entry["initiatives"].append(initiative.id)
            if goal and goal.id not in {g["id"] for g in entry["goals"]}:
                entry["goals"].append({
                    "id": goal.id, "title": goal.title, "priority": goal.priority,
                    "status": goal.status,
                })
        for pid, entry in result.items():
            entry["goals"].sort(key=lambda g: (g["priority"], g["id"]))
            for cid, cname in customers.items():
                entry["customers"].add(cname)
            entry["customers"] = sorted(entry["customers"])
        return result

    async def _supply_reasons(
        self, db: AsyncSession, *, organization_id: str, capability: str,
        supply: dict[str, Any],
    ) -> list[str]:
        """WHY the gap exists - commitments, reservations, expertise fit."""
        reasons: list[str] = []
        if supply["committed"]:
            reasons.append(
                f"{supply['committed']} unit(s) already committed elsewhere"
            )
        if supply["reserved"]:
            reasons.append(
                f"{supply['reserved']} unit(s) reserved for other work"
            )
        if supply["fit_high"] < supply["available"]:
            reasons.append(
                f"only {supply['fit_high']} person(s) have trusted evidence for "
                f"this capability at the demanded proficiency"
            )
        return reasons

    # --------------------------------------------------------------- refresh

    async def refresh(
        self, db: AsyncSession, *, organization_id: str,
        capability: str, window_start: date, window_end: date,
        event_name: str, source_event_id: str,
    ) -> None:
        """Recompute one (capability, window) neighborhood and persist the
        snapshot exact-once on the source event."""
        existing = (
            await db.execute(
                select(CapacitySnapshot.id).where(
                    CapacitySnapshot.organization_id == organization_id,
                    CapacitySnapshot.capability == capability,
                    CapacitySnapshot.window_start == window_start,
                    CapacitySnapshot.window_end == window_end,
                    CapacitySnapshot.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return
        payload = await self.assess(
            db, organization_id=organization_id,
            capability=capability, window_start=window_start, window_end=window_end,
        )
        db.add(CapacitySnapshot(
            organization_id=organization_id,
            capability=capability,
            window_start=window_start, window_end=window_end,
            source_event_id=source_event_id, event_name=event_name,
            supply_potential=payload["supply"]["potential"],
            supply_committed=payload["supply"]["committed"],
            supply_available=payload["supply"]["available"],
            supply_state=payload["supply"]["state"],
            demand_total=payload["demand"]["total"],
            allocated_total=payload["demand"]["allocated"],
            gap=payload["gap"], utilization=payload["utilization"],
            is_bottleneck=payload["is_bottleneck"],
            affected_projects=payload["affected_projects"]["count"],
            affected_goals=payload["affected_goals"]["count"],
            payload_json=payload, occurred_at=utcnow(),
        ))
        await db.flush()

    async def assess(
        self, db: AsyncSession, *, organization_id: str,
        capability: str, window_start: date, window_end: date,
    ) -> dict[str, Any]:
        """One deterministic assessment of a (capability, window) pair."""
        supply = await self._supply(
            db, organization_id=organization_id, capability=capability,
        )
        demands = await self._demands(
            db, organization_id=organization_id,
            capability=capability, window_start=window_start, window_end=window_end,
        )
        allocations = await self._allocations(
            db, organization_id=organization_id,
            capability=capability, window_start=window_start, window_end=window_end,
        )
        windowed_demands = [
            d for d in demands
            if _window_overlaps(window_start, window_end, d.window_start, d.window_end)
        ][:MAX_PROJECTS_DETAIL]
        windowed_allocations = [
            a for a in allocations
            if _window_overlaps(window_start, window_end, a.window_start, a.window_end)
        ][:MAX_PROJECTS_DETAIL]
        demand_total = sum(d.units for d in windowed_demands)
        allocated_total = sum(a.units for a in windowed_allocations)
        by_project: dict[str, dict[str, Any]] = {}
        for d in windowed_demands:
            bucket = by_project.setdefault(d.project_id, {
                "project_id": d.project_id, "units": 0,
                "proficiency": d.proficiency, "window_start": _iso(d.window_start),
                "window_end": _iso(d.window_end),
            })
            bucket["units"] += d.units
        labels = await self._project_labels(
            db, organization_id=organization_id,
            project_ids=[d.project_id for d in windowed_demands],
        )
        for bucket in by_project.values():
            bucket["project_name"] = labels.get(bucket["project_id"], "Unknown project")
        project_units = sorted(
            by_project.values(), key=lambda b: (-b["units"], b["project_id"])
        )[:MAX_PROJECTS_DETAIL]
        stakes = await self._stakes(
            db, organization_id=organization_id,
            project_ids=[d.project_id for d in windowed_demands],
        )
        affected_goals: dict[str, dict[str, Any]] = {}
        affected_projects: dict[str, str] = {}
        for d in windowed_demands:
            affected_projects[d.project_id] = labels.get(d.project_id, "Unknown project")
            for g in stakes.get(d.project_id, {}).get("goals", []):
                affected_goals[g["id"]] = g
        goals_list = sorted(
            affected_goals.values(), key=lambda g: (g["priority"], g["id"])
        )[:MAX_GOALS_STAKES]
        gaps_reasons = await self._supply_reasons(
            db, organization_id=organization_id,
            capability=capability, supply=supply,
        )
        gap = max(demand_total - supply["available"], 0)
        utilization = _utilization(demand_total, supply["available"])
        is_bottleneck = bool(
            gap > 0 or (demand_total > 0 and supply["state"] in ("stretched", "constrained"))
        )
        commitments = sorted(
            {c for pid in by_project for c in stakes.get(pid, {}).get("customers", [])}
        )[:10]
        return {
            "capability": capability,
            "window_start": _iso(window_start),
            "window_end": _iso(window_end),
            "supply": supply,
            "demand": {
                "total": demand_total,
                "allocated": allocated_total,
                "project_count": len(by_project),
                "projects": project_units,
            },
            "gap": gap,
            "utilization": utilization,
            "state": "bottleneck" if is_bottleneck else (
                "covered" if demand_total > 0 else "idle"
            ),
            "is_bottleneck": is_bottleneck,
            "gap_reasons": gaps_reasons,
            "affected_projects": {
                "count": len(affected_projects),
                "ids": sorted(affected_projects.keys())[:MAX_PROJECTS_DETAIL],
            },
            "affected_goals": {"count": len(goals_list), "goals": goals_list},
            "affected_commitments": commitments,
            "advisory_only": True,
        }

    # ------------------------------------------------------------ surfaces

    async def _live_snapshots(
        self, db: AsyncSession, *, organization_id: str,
    ) -> list[CapacitySnapshot]:
        """The latest snapshot per (capability, window) - bounded."""
        rows = list(
            (
                await db.execute(
                    select(CapacitySnapshot)
                    .where(CapacitySnapshot.organization_id == organization_id)
                    .order_by(
                        CapacitySnapshot.capability,
                        CapacitySnapshot.window_start,
                        CapacitySnapshot.occurred_at,
                    )
                )
            ).scalars().all()
        )[:MAX_CAPABILITIES_SURFACE * 10]
        latest: dict[tuple[str, date, date], CapacitySnapshot] = {}
        for row in rows:
            key = (row.capability, row.window_start, row.window_end)
            latest[key] = row
        return sorted(
            latest.values(), key=lambda r: (r.window_start, r.window_end)
        )[:MAX_CAPABILITIES_SURFACE]

    async def center(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """CAPACITY CENTER: company utilization, critical bottlenecks,
        overloaded capabilities, capability gaps, goals at risk and the top
        constraint - with a recommended action. Advisory, deterministic."""
        snapshots = await self._live_snapshots(
            db, organization_id=organization_id,
        )
        today = date.today()
        relevant = [s for s in snapshots if s.window_end >= today]
        relevant.sort(key=lambda s: (s.window_start, s.window_end))
        window = relevant[-1] if relevant else None
        buckets: dict[tuple[str, date, date], CapacitySnapshot] = {}
        for s in snapshots:
            key = (s.capability, s.window_start, s.window_end)
            buckets[key] = s
        bottlenecks = [s for s in buckets.values() if s.is_bottleneck]
        bottlenecks.sort(key=lambda s: (-s.gap, -s.affected_goals, s.capability))
        bottlenecks = bottlenecks[:5]

        critical = [
            {
                "capability": s.capability,
                "window_start": _iso(s.window_start),
                "window_end": _iso(s.window_end),
                "demand": s.demand_total,
                "available": s.supply_available,
                "gap": s.gap,
                "utilization": round(s.utilization, 1),
                "affected_projects": s.affected_projects,
                "affected_goals": s.affected_goals,
            }
            for s in bottlenecks
        ]
        goals_at_risk: dict[str, dict[str, Any]] = {}
        for s in bottlenecks:
            payload = s.payload_json or {}
            for g in (payload.get("affected_goals") or {}).get("goals", []):
                entry = goals_at_risk.setdefault(g["id"], {
                    "goal_id": g["id"], "title": g["title"],
                    "priority": g["priority"], "causes": [],
                })
                if s.capability not in entry["causes"]:
                    entry["causes"].append(s.capability)
        goals_at_risk_list = sorted(
            goals_at_risk.values(), key=lambda g: (g["priority"], g["goal_id"])
        )[:MAX_GOALS_STAKES]

        top = critical[0] if critical else None
        top_constraint = None
        if top is not None:
            top_constraint = {
                "capability": top["capability"],
                "utilization": top["utilization"],
                "gap": top["gap"],
                "window_start": top["window_start"],
                "window_end": top["window_end"],
                "affected_projects": top["affected_projects"],
                "affected_goals": top["affected_goals"],
                "recommended_action": (
                    f"Review allocation across {top['affected_projects']} project(s) "
                    f"demanding {top['capability']}"
                ),
            }
        recommendations = [
            {
                "kind": "capacity",
                "capability": top["capability"],
                "action": (
                    f"Sequence or reallocate {top['capability']} across "
                    f"{top['affected_projects']} project(s)"
                ),
                "why": f"{top['gap']} unit(s) over supply in the {top['window_start']}.."
                       f"{top['window_end']} window",
                "confidence": 0.7,
                "advisory_only": True,
            }
            for top in critical
        ]
        utilization_values = [s.utilization for s in buckets.values() if s.demand_total > 0]
        company_utilization = (
            round(sum(utilization_values) / len(utilization_values), 1)
            if utilization_values else 0.0
        )
        return {
            "advisory_only": True,
            "company_utilization": company_utilization,
            "window": {"start": _iso(window.window_start) if window else None,
                       "end": _iso(window.window_end) if window else None},
            "critical_bottlenecks": critical,
            "overloaded_capabilities": len(critical),
            "capability_gaps": sum(1 for s in buckets.values() if s.gap > 0),
            "goals_at_risk": goals_at_risk_list,
            "top_constraint": top_constraint,
            "recommendations": recommendations,
        }

    async def capability_detail(
        self, db: AsyncSession, *, organization_id: str, capability: str,
    ) -> Optional[dict[str, Any]]:
        """One capability's full record: supply + demand in the latest
        window, the gap with WHY, stakes, commitments and temporal history."""
        snapshots = [
            s for s in await self._live_snapshots(
                db, organization_id=organization_id,
            )
            if s.capability == capability
        ]
        if not snapshots:
            return None
        latest = snapshots[-1]
        payload = dict(latest.payload_json or {})
        rows = (
            await db.execute(
                select(CapacityHistory)
                .where(
                    CapacityHistory.organization_id == organization_id,
                    CapacityHistory.entity_type == "demand",
                    CapacityHistory.field == capability,
                )
                .order_by(CapacityHistory.changed_at.desc())
                .limit(MAX_HISTORY_ROWS)
            )
        ).scalars().all()
        history = [
            {
                "project_id": r.entity_id,
                "entity_label": r.entity_label,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "reason": r.reason,
                "changed_at": r.changed_at.isoformat(),
            }
            for r in rows
        ]
        return {
            **payload,
            "history": history,
            "snapshot_count": len(snapshots),
        }

    async def gaps(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """Current gaps (windows containing today) and FUTURE gaps clearly
        labeled as projections - never presented as fact."""
        snapshots = await self._live_snapshots(
            db, organization_id=organization_id,
        )
        today = date.today()
        current = [s for s in snapshots if s.window_start <= today <= s.window_end]
        future = [
            s for s in snapshots if s.window_start > today
            or (s.window_start == today and s.window_end > today)
        ]
        current.sort(key=lambda s: (-s.gap, s.capability))
        future.sort(key=lambda s: (s.window_start, s.window_end))

        def render(s: CapacitySnapshot) -> dict[str, Any]:
            payload = s.payload_json or {}
            return {
                "capability": s.capability,
                "window_start": _iso(s.window_start),
                "window_end": _iso(s.window_end),
                "demand": s.demand_total,
                "available": s.supply_available,
                "potential": s.supply_potential,
                "gap": s.gap,
                "gap_potential": max(s.demand_total - s.supply_potential, 0),
                "utilization": round(s.utilization, 1),
                "reasons": payload.get("gap_reasons", []),
                "affected_goals": s.affected_goals,
            }

        return {
            "advisory_only": True,
            "current_gaps": [render(s) for s in current if s.gap > 0][:20],
            "future_gaps_projection": [render(s) for s in future][:20],
            "projection_notice": (
                "future gaps are projections from declared demand and current "
                "supply; capacity will change"
            ),
        }

    async def contention(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """Projects competing for the same scarce capability, ordered with
        their strategic stakes. Advisory - humans decide the allocation."""
        snapshots = await self._live_snapshots(
            db, organization_id=organization_id,
        )
        today = date.today()
        buckets: dict[tuple[str, date, date], CapacitySnapshot] = {}
        for s in snapshots:
            if s.window_end < today:
                continue
            key = (s.capability, s.window_start, s.window_end)
            if key not in buckets:
                buckets[key] = s
        groups: list[dict[str, Any]] = []
        for (capability, ws, we), s in sorted(
            buckets.items(), key=lambda kv: (kv[1].window_start, kv[1].window_end)
        ):
            payload = s.payload_json or {}
            projects = payload.get("demand", {}).get("projects", [])
            if s.gap <= 0 or len(projects) < 2:
                continue
            stakes = await self._stakes(
                db, organization_id=organization_id,
                project_ids=[p["project_id"] for p in projects],
            )
            claimants = []
            for p in projects:
                goal_ids = [g for g in stakes.get(p["project_id"], {}).get("goals", [])]
                priority = min((g["priority"] for g in goal_ids), default=5)
                claimants.append({
                    "project_id": p["project_id"],
                    "project_name": p["project_name"],
                    "units": p["units"],
                    "proficiency": p["proficiency"],
                    "goal_priority": priority,
                    "goal_title": next(
                        (g["title"] for g in goal_ids if g["priority"] == priority), None
                    ),
                })
            claimants.sort(key=lambda c: (c["goal_priority"], -c["units"], c["project_id"]))
            strategic_stakes = sorted(
                {
                    g["id"]: g
                    for p in projects
                    for g in stakes.get(p["project_id"], {}).get("goals", [])
                }.values(),
                key=lambda g: (g["priority"], g["id"]),
            )[:MAX_GOALS_STAKES]
            groups.append({
                "capability": capability,
                "window_start": _iso(ws),
                "window_end": _iso(we),
                "total_demand": s.demand_total,
                "available": s.supply_available,
                "gap": s.gap,
                "utilization": round(s.utilization, 1),
                "claimants": claimants,
                "strategic_stakes": [
                    {"goal_id": g["id"], "title": g["title"], "priority": g["priority"]}
                    for g in strategic_stakes
                ],
            })
        groups.sort(key=lambda g: (-g["gap"], g["capability"]))
        return {
            "advisory_only": True,
            "groups": groups[:10],
            "contention_count": len(groups),
        }

    async def traceability(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """RESOURCE-TO-GOAL TRACEABILITY: how each capability's demand maps
        to company goals, initiatives and unaligned work (the drill-down)."""
        snapshots = await self._live_snapshots(
            db, organization_id=organization_id,
        )
        today = date.today()
        latest_per_capability: dict[str, CapacitySnapshot] = {}
        for s in sorted(
            snapshots, key=lambda r: (r.capability, r.occurred_at)
        ):
            if s.window_end >= today:
                latest_per_capability[s.capability] = s
        capabilities: list[dict[str, Any]] = []
        for capability, s in latest_per_capability.items():
            payload = s.payload_json or {}
            projects = payload.get("demand", {}).get("projects", [])
            stakes = await self._stakes(
                db, organization_id=organization_id,
                project_ids=[p["project_id"] for p in projects],
            )
            per_goal: dict[str, dict[str, Any]] = {}
            unaligned = 0
            for p in projects:
                goal_ids = stakes.get(p["project_id"], {}).get("goals", [])
                if not goal_ids:
                    unaligned += p["units"]
                else:
                    g = goal_ids[0]
                    bucket = per_goal.setdefault(g["id"], {
                        "goal_id": g["id"], "title": g["title"],
                        "priority": g["priority"], "units": 0,
                    })
                    bucket["units"] += p["units"]
            total = s.demand_total or 1
            goals = sorted(
                per_goal.values(), key=lambda g: (-g["units"], g["priority"])
            )[:MAX_GOALS_STAKES]
            for g in goals:
                g["share_pct"] = round(100.0 * g["units"] / total, 1)
            capabilities.append({
                "capability": capability,
                "demand_total": s.demand_total,
                "goals": goals,
                "unaligned_units": unaligned,
                "unaligned_pct": round(100.0 * unaligned / total, 1),
            })
        capabilities.sort(key=lambda c: (-c["demand_total"], c["capability"]))
        return {
            "advisory_only": True,
            "capabilities": capabilities[:20],
        }

    async def overloads(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """Overload and under-utilization at capability, team and person
        level - evidence-backed, never a rank for people."""
        snapshots = await self._live_snapshots(
            db, organization_id=organization_id,
        )
        today = date.today()
        latest_per_capability: dict[str, CapacitySnapshot] = {}
        for s in sorted(
            snapshots, key=lambda r: (r.capability, r.occurred_at)
        ):
            if s.window_end >= today:
                latest_per_capability[s.capability] = s
        capability_overloads = [
            {
                "capability": s.capability,
                "utilization": round(s.utilization, 1),
                "demand": s.demand_total,
                "available": s.supply_available,
                "gap": s.gap,
                "affected_goals": s.affected_goals,
            }
            for s in latest_per_capability.values()
            if s.utilization > OVERLOAD_UTILIZATION * 100
        ]
        capability_overloads.sort(key=lambda c: (-c["utilization"], c["capability"]))
        under_utilized = [
            {
                "capability": s.capability,
                "available": s.supply_available,
                "committed": s.supply_committed,
                "potential": s.supply_potential,
            }
            for s in latest_per_capability.values()
            if s.supply_available >= 40 and s.demand_total == 0
        ]
        under_utilized.sort(key=lambda c: (-c["available"], c["capability"]))

        # person + team committed hours from open assigned tasks (bounded).
        rows = (
            await db.execute(
                select(
                    Task.assignee_id,
                    Employee.team_id,
                    Employee.first_name,
                    Employee.last_name,
                    Task.estimate_hours,
                )
                .join(Employee, Task.assignee_id == Employee.id)
                .where(
                    Task.organization_id == organization_id,
                    Task.assignee_id.isnot(None),
                    Task.status.in_(OPEN_TASK_STATUSES),
                    Employee.organization_id == organization_id,
                    Employee.status == "active",
                )
            )
        ).all()
        person_hours: dict[str, dict[str, Any]] = {}
        team_hours: dict[str, dict[str, Any]] = {}
        for assignee_id, team_id, first, last, hours in rows:
            hours = float(hours or 0.0)
            person = person_hours.setdefault(assignee_id, {
                "person_id": assignee_id, "name": f"{first or ''} {last or ''}".strip(),
                "committed_hours": 0.0, "capacity_hours": PERSON_WEEK_HOURS,
            })
            person["committed_hours"] += hours
            if team_id:
                team = team_hours.setdefault(team_id, {
                    "team_id": team_id, "members": 0, "committed_hours": 0.0,
                    "capacity_hours": 0.0,
                })
                team["committed_hours"] += hours
        member_counts = dict(
            (
                await db.execute(
                    select(Employee.team_id, func.count(Employee.id))
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.team_id.isnot(None),
                        Employee.status == "active",
                    )
                    .group_by(Employee.team_id)
                )
            ).all()
        )
        for team_id, team in team_hours.items():
            members = int(member_counts.get(team_id, 0))
            team["members"] = members
            team["capacity_hours"] = round(members * PERSON_WEEK_HOURS, 1)
        people = [p for p in person_hours.values() if p["committed_hours"] > 0]
        person_overloads = [
            {**p, "utilization": round(100.0 * p["committed_hours"] / p["capacity_hours"], 1)}
            for p in people
            if p["committed_hours"] > p["capacity_hours"]
        ]
        person_overloads.sort(key=lambda p: (-p["utilization"], p["person_id"]))
        person_under = [
            {**p, "utilization": round(100.0 * p["committed_hours"] / p["capacity_hours"], 1)}
            for p in people
            if p["committed_hours"] <= UNDER_UTILIZED_HOURS
        ]
        person_under.sort(key=lambda p: (p["committed_hours"], p["person_id"]))
        team_overloads = [
            {
                "team_id": t["team_id"], "members": t["members"],
                "committed_hours": round(t["committed_hours"], 1),
                "capacity_hours": t["capacity_hours"],
                "utilization": round(100.0 * t["committed_hours"] / t["capacity_hours"], 1),
            }
            for t in team_hours.values()
            if t["capacity_hours"] > 0
            and t["committed_hours"] > t["capacity_hours"]
        ]
        team_overloads.sort(key=lambda t: (-t["utilization"], t["team_id"]))
        return {
            "advisory_only": True,
            "capability_overloads": capability_overloads[:20],
            "team_overloads": team_overloads[:MAX_TEAMS_OVERLOAD],
            "person_overloads": person_overloads[:MAX_PEOPLE_OVERLOAD],
            "person_under_utilized": person_under[:MAX_PEOPLE_OVERLOAD],
            "under_utilized_capabilities": under_utilized[:20],
        }

    async def alternatives(
        self, db: AsyncSession, *, organization_id: str,
        project_id: str, capability: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Three bounded allocation courses for one project's contention with
        benefit/risk/confidence/evidence. Humans decide; nothing executes."""
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
        snapshots = await self._live_snapshots(
            db, organization_id=organization_id,
        )
        today = date.today()
        contenders: list[CapacitySnapshot] = []
        for s in snapshots:
            if s.window_end < today:
                continue
            payload = s.payload_json or {}
            projects = payload.get("demand", {}).get("projects", [])
            if any(p["project_id"] == project_id for p in projects):
                contenders.append(s)
        if not contenders:
            return {
                "advisory_only": True,
                "project_id": project_id,
                "options": [], "recommendation": None,
                "decision_linkage": {"requires_decision": False, "open_decisions": 0},
                "note": "no demand window found for this project",
            }
        if capability:
            contenders = [s for s in contenders if s.capability == capability]
            if not contenders:
                return None
        contenders.sort(key=lambda s: (-s.gap, s.occurred_at))
        s = contenders[0]
        payload = s.payload_json or {}
        projects = payload.get("demand", {}).get("projects", [])
        labels = await self._project_labels(
            db, organization_id=organization_id,
            project_ids=[p["project_id"] for p in projects],
        )
        stakes = await self._stakes(
            db, organization_id=organization_id,
            project_ids=[p["project_id"] for p in projects],
        )
        my_units = next(
            (p["units"] for p in projects if p["project_id"] == project_id), 0
        )
        others = [p for p in projects if p["project_id"] != project_id]
        others.sort(key=lambda p: (
            min((g["priority"] for g in stakes.get(p["project_id"], {}).get("goals", [])),
                default=5),
            p["project_id"],
        ))
        other_names = ", ".join(
            labels.get(p["project_id"], "Unknown") for p in others[:3]
        )
        gap_units = s.gap
        move_units = max(min(my_units, gap_units), 0)
        confidence = 0.7
        if payload.get("supply", {}).get("fit_high", 0) < payload.get("supply", {}).get("available", 0):
            confidence = 0.55
        options = [
            {
                "key": "sequence",
                "title": "Sequence the competing work by goal priority",
                "effect": (
                    f"priority order preserves the highest-priority strategic claim "
                    f"on {s.capability}"
                ),
                "benefit": "no capacity change, lowest disruption",
                "risk": "lower-priority demand waits for the full window",
                "affected_projects": [p["project_id"] for p in projects],
                "affected_goals": [
                    g["id"] for g in payload.get("affected_goals", {}).get("goals", [])
                ],
                "capacity_change": 0,
                "confidence": confidence,
                "evidence": [
                    f"{len(projects)} project(s) contend for {s.demand_total} units "
                    f"against {s.supply_available} available",
                    "demand exceeds supply by the recorded gap",
                ],
            },
            {
                "key": "reassign",
                "title": "Reallocate units from lower-priority work",
                "effect": (
                    f"moves up to {move_units} unit(s) of {s.capability} to this "
                    f"project, reducing its gap by up to {move_units}"
                ),
                "benefit": "closes part of the gap without new capacity",
                "risk": "the releasing project's own demand becomes under-covered",
                "affected_projects": [
                    p["project_id"] for p in others[:3]
                ] + [project_id],
                "affected_goals": [
                    g["id"] for g in payload.get("affected_goals", {}).get("goals", [])
                ],
                "capacity_change": move_units,
                "confidence": confidence,
                "evidence": [
                    f"claimants by priority: {other_names or 'none'}",
                    "reallocation is a governed human decision, not an auto-move",
                ],
            },
            {
                "key": "external_capability",
                "title": "Bring external capability",
                "effect": f"adds supply for {s.capability} outside current capacity",
                "benefit": "removes the constraint entirely for the window",
                "risk": "cost and onboarding latency outside this intelligence",
                "affected_projects": [p["project_id"] for p in projects],
                "affected_goals": [
                    g["id"] for g in payload.get("affected_goals", {}).get("goals", [])
                ],
                "capacity_change": gap_units,
                "confidence": 0.5,
                "evidence": [
                    f"gap is {gap_units} unit(s) in {_iso(s.window_start)}..{_iso(s.window_end)}",
                    "this option is financial planning (4I), surfaced here only as a choice",
                ],
            },
        ]
        recommendation = (
            "Option B balances the gap while preserving the highest-priority claim"
            if move_units > 0 else
            "Option A sequences without changing capacity"
        )
        return {
            "advisory_only": True,
            "project_id": project_id,
            "project_name": project.name,
            "capability": s.capability,
            "window_start": _iso(s.window_start),
            "window_end": _iso(s.window_end),
            "options": options,
            "recommendation": recommendation,
            "decision_linkage": {
                "requires_decision": True,
                "open_decisions": len(contenders),
            },
        }

    async def what_if(
        self, db: AsyncSession, *, organization_id: str,
        from_project_id: str, to_project_id: str,
        capability: str, units: int, window_days: int = 30,
    ) -> Optional[dict[str, Any]]:
        """Bounded reallocation scenario: move N units of a capability from
        one project to another. Simulated gaps + goal directions; NEVER a
        prediction and never executed."""
        snapshots = await self._live_snapshots(
            db, organization_id=organization_id,
        )
        today = date.today()
        window_end = today + timedelta(days=max(1, min(window_days, 365)))
        matched = [
            s for s in snapshots
            if s.capability == capability
            and s.window_start <= today <= s.window_end
        ]
        if not matched:
            return None
        s = sorted(matched, key=lambda r: r.occurred_at)[-1]
        payload = s.payload_json or {}
        projects = payload.get("demand", {}).get("projects", [])
        by_project = {p["project_id"]: p["units"] for p in projects}
        if from_project_id not in by_project or to_project_id not in by_project:
            return None
        units = max(1, min(units, by_project[from_project_id]))
        labels = await self._project_labels(
            db, organization_id=organization_id,
            project_ids=[from_project_id, to_project_id],
        )
        stakes = await self._stakes(
            db, organization_id=organization_id,
            project_ids=[from_project_id, to_project_id],
        )
        from_goal = stakes.get(from_project_id, {}).get("goals", [])
        to_goal = stakes.get(to_project_id, {}).get("goals", [])
        from_after = by_project[from_project_id] - units
        to_after = by_project[to_project_id] + units
        supply_available = s.supply_available
        gap_from_before = max(by_project[from_project_id] - supply_available, 0)
        gap_to_before = max(by_project[to_project_id] - supply_available, 0)
        gap_from_after = max(from_after - supply_available, 0)
        gap_to_after = max(to_after - supply_available, 0)
        goals_affected = []
        if from_goal:
            goals_affected.append({
                "goal_id": from_goal[0]["id"], "title": from_goal[0]["title"],
                "direction": "worsens" if gap_from_after > gap_from_before else "unchanged",
            })
        if to_goal:
            goals_affected.append({
                "goal_id": to_goal[0]["id"], "title": to_goal[0]["title"],
                "direction": "improves" if gap_to_after < gap_to_before else "unchanged",
            })
        return {
            "not_a_prediction": True,
            "change": {
                "type": "reallocate",
                "capability": capability,
                "units": units,
                "from_project_id": from_project_id,
                "from_project_name": labels.get(from_project_id, "Unknown"),
                "to_project_id": to_project_id,
                "to_project_name": labels.get(to_project_id, "Unknown"),
                "window_start": _iso(s.window_start),
                "window_end": _iso(s.window_end),
            },
            "demand_before": {
                from_project_id: by_project[from_project_id],
                to_project_id: by_project[to_project_id],
            },
            "demand_after": {
                from_project_id: from_after,
                to_project_id: to_after,
            },
            "gap_before": {
                from_project_id: gap_from_before,
                to_project_id: gap_to_before,
            },
            "gap_after": {
                from_project_id: gap_from_after,
                to_project_id: gap_to_after,
            },
            "goals_affected": goals_affected,
            "assumptions": [
                "only the two projects' demand changes; supply and every other demand are unchanged",
                "utilization is windowed, not a forecast",
            ],
            "bounds": "the scenario never moves people or capacity; a human decides",
        }

    async def _history(
        self, db: AsyncSession, *, organization_id: str,
        entity_type: str, entity_id: str,
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(CapacityHistory)
                .where(
                    CapacityHistory.organization_id == organization_id,
                    CapacityHistory.entity_type == entity_type,
                    CapacityHistory.entity_id == entity_id,
                )
                .order_by(CapacityHistory.changed_at.desc())
                .limit(MAX_HISTORY_ROWS)
            )
        ).scalars().all()
        return [
            {
                "field": r.field,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "reason": r.reason,
                "changed_at": r.changed_at.isoformat(),
            }
            for r in rows
        ]


resource_allocation_engine = ResourceAllocationEngine()
