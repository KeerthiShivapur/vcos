"""Slice 4G.2 — Execution Coordination & Dependency Intelligence engine.

How the WHOLE organization coordinates work. Where 4G.1 answers "what is
happening in this project", 4G.2 answers "how do the projects coordinate":

* WHICH projects compete for the same constrained people (shared-capacity
  contention, read from the 4F.6 capability ledger),
* WHERE a critical path is blocked at a shared capability (critical
  conflicts),
* WHERE handoffs between owners/teams are failing (a handoff ledger: every
  task ownership transition, pending duration, slow repeats),
* WHERE coordination is required but has no evidence (coordination gaps from
  the 4F.5 team-pair rollups),
* WHAT a blocked project's blockage reaches (propagation: blocked critical
  path -> milestones -> goal chain -> decisions -> capability partners),
* WHAT to coordinate first (deterministic, evidence-backed recommendations
  with confidence),
* WHAT bounded options exist (what-if: shift dates, alternative owners,
  recalled knowledge) — explicitly NOT a prediction, every option carries
  its boundary,
* WHAT changed (incident history, exact-once).

Governance: governance filters run BEFORE assembly — scoped callers never
see org-level incidents (shared_capacity, critical_conflict) or other
projects' names/capacity. The engine is advisory-only: it writes only its
own tables; nothing is ever reallocated, rescheduled or reassigned
automatically. Human-controlled actions only.

Architecture rules (5 -> 50,000+ employees): every pass is bounded by
explicit caps and indexed reads; there is NO pairwise project x project x
person scan — contention and gaps are computed from the persisted ledgers
(4F.6 links + 4F.5 unit pairs + the handoff ledger), never by live scans.

Exact-once: incident fingerprints deduplicate findings; history rows and
handoff rows are unique per source event; replays converge.
"""

import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.collaboration_intelligence import CollaborationUnitPair
from app.models.execution_coordination import (
    CoordinationHandoff,
    CoordinationHistory,
    CoordinationIncident,
    INCIDENT_KINDS,
)
from app.models.execution_intelligence import ProjectExecutionState
from app.models.goal import Goal
from app.models.knowledge import Decision, KnowledgeTopic
from app.models.org_capability_intelligence import CapabilityProjectLink, OrgCapability
from app.models.project import Milestone, Project
from app.models.task import Task

# ---------------------------------------------------------------------------
# bounds — the same architecture must serve 5 people and 50,000+
# ---------------------------------------------------------------------------

MAX_ACTIVE_PROJECTS_SCAN = 200          # projects considered by any pass
MAX_NEIGHBOR_PROJECTS = 40              # projects with team-gap analysis
MAX_CONSTRAINED_SKILLS = 12             # contention skills considered
MAX_CONTENTION_PROJECTS = 6             # projects shown per contention skill
MAX_INCIDENTS_SHOWN = 40                # center / detail incident cap
MAX_HANDOFFS_KEPT = 400                 # handoff ledger cap (prune oldest)
MAX_HISTORY_SHOWN = 40                  # incident history cap
MAX_RECOMMENDATIONS = 12
MAX_WHATIF_OPTIONS = 3
MAX_ALTERNATIVES = 3
MAX_KNOWLEDGE_LINES = 3
MAX_PROPAGATION_STEPS = 4
MAX_TEAMS_PER_PROJECT = 4
MAX_GAP_PAIRS = 40                      # in-memory pair cap (teams² bounded)
MAX_EVIDENCE_LINES = 6

HANDOFF_RISK_HOURS = 72                 # a pending handoff past this is risk
HANDOFF_HIGH_HOURS = 168                # 7 days -> high severity
RECURRING_WINDOW_DAYS = 30
RECURRING_NEEDED = 3                    # slow repeats before a finding
RECURRING_SLOW_HOURS = 72
GAP_WEAK_FAILURES = 3                   # failed interactions -> weak pair
WHATIF_SHIFT_DAYS = 14
SEVERITY_ORDER = ("critical", "high", "medium", "low")

ACTIVE_STATUSES = ("draft", "active", "paused")
_CLOSED_EVENTS = ("task.completed", "task.unblocked", "task.deleted")


def _hours_between(a: datetime, b: datetime) -> float:
    try:
        return round((ensure_aware(b) - ensure_aware(a)).total_seconds() / 3600.0, 1)
    except (TypeError, ValueError):
        return 0.0


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


class CoordinationEngine:
    """Canonical Execution Coordination Intelligence — one engine per org."""

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
        """Change-driven entry: capture handoff transitions first (they are
        exact-once per event), then recompute the coordination findings."""
        event_name = getattr(event, "name", "")
        source_event_id = getattr(event, "id", None)
        if event_name in (
            "task.updated", "task.transitioned", "task.completed",
            "task.unblocked", "task.deleted",
        ):
            await self._capture_handoff(
                db, organization_id=organization_id,
                event_name=event_name, source_event_id=source_event_id,
                payload=payload,
            )
        await self.refresh(
            db, organization_id=organization_id,
            event_name=event_name, source_event_id=source_event_id,
        )

    async def _capture_handoff(
        self, db: AsyncSession, *, organization_id: str,
        event_name: str, source_event_id: Optional[str], payload: dict[str, Any],
    ) -> None:
        """One handoff ledger row per event (exact-once on source_event_id).

        Deterministic transitions:
        * task completed/unblocked -> all pending handoffs for the task close
          with their measured duration,
        * task deleted -> pending handoffs are abandoned,
        * assignee changes -> the pending handoff closes and a new one opens
          from the previous owner to the new owner (a task's FIRST owner is
          not a handoff — ownership needs a real transition).
        """
        task_id = payload.get("task_id")
        if not task_id or not source_event_id:
            return
        if (
            await db.execute(
                select(CoordinationHandoff.id).where(
                    CoordinationHandoff.organization_id == organization_id,
                    CoordinationHandoff.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none():
            return

        task = (
            await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id, Task.id == task_id,
                )
            )
        ).scalar_one_or_none()
        if task is None:
            return
        now = utcnow()

        latest = (
            await db.execute(
                select(CoordinationHandoff)
                .where(
                    CoordinationHandoff.organization_id == organization_id,
                    CoordinationHandoff.task_id == task_id,
                )
                .order_by(CoordinationHandoff.occurred_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if event_name in _CLOSED_EVENTS:
            rows = list(
                (
                    await db.execute(
                        select(CoordinationHandoff)
                        .where(
                            CoordinationHandoff.organization_id == organization_id,
                            CoordinationHandoff.task_id == task_id,
                            CoordinationHandoff.status == "pending",
                        )
                    )
                ).scalars().all()
            )
            for row in rows:
                if event_name == "task.deleted":
                    row.status = "abandoned"
                else:
                    row.status = "completed"
                row.completed_at = now
                row.duration_hours = _hours_between(row.occurred_at, now)
            return

        new_owner = payload.get("assignee_id")
        if not new_owner:
            return
        if latest is None:
            # first observed transition for this task: prefer the previous
            # owner from the event payload (task.updated carries it); fall
            # back to the task's stored owner when the event lacks it (it is
            # still the pre-event owner on this engine's first sight of the
            # task, and replays are excluded by the exact-once guard above).
            previous = payload.get("from_assignee_id") or task.assignee_id
            if not previous or previous == new_owner:
                return
        else:
            if latest.to_owner_id == new_owner:
                return
            # A real transition: close the current pending (if any) and open
            # the next handoff from the previous owner.
            if latest.status == "pending":
                latest.status = "completed"
                latest.completed_at = now
                latest.duration_hours = _hours_between(latest.occurred_at, now)
            previous = latest.to_owner_id or (
                latest.from_owner_id if latest.status == "completed" else None
            )
            if previous is None:
                return
        labels = await self._labels_for(
            db, organization_id=organization_id, ids=[previous, new_owner],
        )
        db.add(
            CoordinationHandoff(
                organization_id=organization_id,
                project_id=task.project_id,
                task_id=task.id,
                task_title=task.title or "",
                from_owner_id=previous,
                from_owner_label=labels.get(previous, ""),
                to_owner_id=new_owner,
                to_owner_label=labels.get(new_owner, ""),
                source_event_id=source_event_id,
                status="pending",
                occurred_at=now,
            )
        )

    # -------------------------------------------------------------- refresh

    async def refresh(
        self, db: AsyncSession, *, organization_id: str,
        event_name: str = "coordination.state_changed",
        source_event_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Recompute the coordination findings from the persisted ledgers.

        Idempotent under replays: findings are keyed by fingerprint; history
        rows are unique per (incident, event). Returns the open incident
        count after the refresh.
        """
        async with self._locks[organization_id]:
            findings = await self._compute_findings(
                db, organization_id=organization_id,
            )
            incidents = {
                i.fingerprint: i
                for i in (
                    await db.execute(
                        select(CoordinationIncident).where(
                            CoordinationIncident.organization_id == organization_id,
                        )
                    )
                ).scalars().all()
            }
            now = utcnow()
            open_count = 0
            for finding in findings:
                existing = incidents.get(finding["fingerprint"])
                if existing is None:
                    incident = CoordinationIncident(
                        organization_id=organization_id,
                        fingerprint=finding["fingerprint"],
                        kind=finding["kind"],
                        severity=finding["severity"],
                        status="open",
                        project_id=finding.get("project_id"),
                        subject_id=finding.get("subject_id", ""),
                        subject_label=finding.get("subject_label", ""),
                        title=finding["title"],
                        summary=finding.get("summary"),
                        evidence=finding.get("evidence", []),
                        propagation=finding.get("propagation"),
                        confidence=finding["confidence"],
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                    db.add(incident)
                    await db.flush()
                    await self._history(
                        db, organization_id=organization_id,
                        incident=incident, event_name="coordination.incident.detected",
                        source_event_id=source_event_id,
                    )
                    open_count += 1
                    continue
                existing.last_seen_at = now
                existing.severity = finding["severity"]
                existing.kind = finding["kind"]
                existing.title = finding["title"]
                existing.summary = finding.get("summary")
                existing.evidence = finding.get("evidence", [])
                existing.propagation = finding.get("propagation")
                existing.confidence = finding["confidence"]
                existing.subject_id = finding.get("subject_id", "")
                existing.subject_label = finding.get("subject_label", "")
                if existing.status == "resolved":
                    existing.status = "open"
                    existing.first_seen_at = now
                    existing.resolved_by = None
                    existing.resolve_note = None
                    existing.resolved_at = None
                    await self._history(
                        db, organization_id=organization_id,
                        incident=existing, event_name="coordination.incident.detected",
                        source_event_id=source_event_id,
                    )
                open_count += 1

            for incident in incidents.values():
                if incident.status != "open":
                    continue
                if any(
                    f["fingerprint"] == incident.fingerprint for f in findings
                ):
                    continue
                incident.status = "resolved"
                incident.resolved_at = now
                await self._history(
                    db, organization_id=organization_id,
                    incident=incident, event_name="coordination.incident.resolved",
                    source_event_id=source_event_id,
                )
            await self._prune_handoffs(db, organization_id=organization_id)
            return {"open_incidents": open_count}

    async def _history(
        self, db: AsyncSession, *, organization_id: str,
        incident: CoordinationIncident, event_name: str,
        source_event_id: Optional[str],
    ) -> None:
        if not source_event_id:
            return
        if (
            await db.execute(
                select(CoordinationHistory.id).where(
                    CoordinationHistory.organization_id == organization_id,
                    CoordinationHistory.incident_id == incident.id,
                    CoordinationHistory.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none():
            return
        db.add(
            CoordinationHistory(
                organization_id=organization_id,
                incident_id=incident.id,
                project_id=incident.project_id,
                fingerprint=incident.fingerprint,
                kind=incident.kind,
                severity=incident.severity,
                event_name=event_name,
                title=incident.title,
                source_event_id=source_event_id,
                occurred_at=utcnow(),
            )
        )

    async def _prune_handoffs(
        self, db: AsyncSession, *, organization_id: str
    ) -> None:
        old = list(
            (
                await db.execute(
                    select(CoordinationHandoff.id)
                    .where(
                        CoordinationHandoff.organization_id == organization_id,
                    )
                    .order_by(CoordinationHandoff.occurred_at.asc())
                )
            ).scalars().all()
        )
        excess = len(old) - MAX_HANDOFFS_KEPT
        if excess > 0:
            for hid in old[:excess]:
                await db.delete(await db.get(CoordinationHandoff, hid))

    # -------------------------------------------------------------- findings

    async def _compute_findings(
        self, db: AsyncSession, *, organization_id: str,
    ) -> list[dict[str, Any]]:
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
        project_by_id = {p.id: p for p in projects}
        if not projects:
            return []
        states = {
            s.project_id: s
            for s in (
                await db.execute(
                    select(ProjectExecutionState).where(
                        ProjectExecutionState.organization_id == organization_id,
                        ProjectExecutionState.project_id.in_(
                            list(project_by_id.keys()) or [""],
                        ),
                    )
                )
            ).scalars().all()
        }
        labels = await self._employee_labels(db, organization_id)
        teams_by_project = await self._project_teams(
            db, organization_id=organization_id,
            project_ids=list(project_by_id.keys()),
        )
        capability_rows = await self._project_capability_rows(
            db, organization_id=organization_id,
            project_ids=list(project_by_id.keys()),
        )

        findings: list[dict[str, Any]] = []
        findings.extend(
            await self._handoff_findings(
                db, organization_id=organization_id,
                project_by_id=project_by_id, labels=labels,
            )
        )
        contention = await self._contention(
            db, organization_id=organization_id,
            project_by_id=project_by_id, states=states,
            capability_rows=capability_rows,
        )
        findings.extend(contention["findings"])
        findings.extend(
            await self._critical_conflicts(
                db, organization_id=organization_id,
                project_by_id=project_by_id, states=states,
                contention=contention,
            )
        )
        findings.extend(
            await self._coordination_gaps(
                db, organization_id=organization_id,
                project_by_id=project_by_id, teams_by_project=teams_by_project,
            )
        )
        findings.extend(
            await self._propagation_risks(
                db, organization_id=organization_id,
                project_by_id=project_by_id, states=states,
                contention=contention, capability_rows=capability_rows,
            )
        )
        findings.sort(
            key=lambda f: (SEVERITY_ORDER.index(f["severity"]), -f["confidence"])
        )
        return findings

    async def _handoff_findings(
        self, db: AsyncSession, *, organization_id: str,
        project_by_id: dict[str, Project], labels: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Pending handoffs past the risk window + slow recurring handoffs."""
        rows = list(
            (
                await db.execute(
                    select(CoordinationHandoff)
                    .where(
                        CoordinationHandoff.organization_id == organization_id,
                    )
                    .order_by(CoordinationHandoff.occurred_at.desc())
                    .limit(MAX_HANDOFFS_KEPT)
                )
            ).scalars().all()
        )
        findings: list[dict[str, Any]] = []
        now = utcnow()
        busy: dict[str, int] = defaultdict(int)
        for h in rows:
            if h.status == "pending":
                busy[h.to_owner_id or ""] += 1
        for h in rows:
            if h.status != "pending":
                continue
            hours = _hours_between(h.occurred_at, now)
            if hours < HANDOFF_RISK_HOURS:
                continue
            owner = labels.get(h.to_owner_id or "", h.to_owner_label)
            other = busy.get(h.to_owner_id or "", 1) - 1
            evidence = [
                f"Task '{h.task_title}' was handed to {owner} "
                f"{round(hours)} hours ago and is still pending",
            ]
            if other > 0:
                evidence.append(
                    f"{owner} currently holds {other} other pending handoff(s)"
                )
            project = project_by_id.get(h.project_id or "")
            if project:
                evidence.append(
                    f"within '{project.name}' (status {project.status})"
                )
            findings.append({
                "kind": "handoff_risk",
                "fingerprint": f"handoff:{h.task_id}",
                "project_id": h.project_id,
                "subject_id": h.task_id,
                "subject_label": h.task_title,
                "title": f"Handoff of '{h.task_title}' has been pending {round(hours)} hours",
                "summary": (
                    f"The task '{h.task_title}' changed owners {round(hours)} "
                    f"hours ago and has not advanced since."
                ),
                "evidence": evidence[:MAX_EVIDENCE_LINES],
                "confidence": 0.84 if hours >= HANDOFF_HIGH_HOURS else 0.72,
                "severity": "high" if hours >= HANDOFF_HIGH_HOURS else "medium",
            })
        # recurring slow handoffs (same from->to, measured window)
        completed = [
            h for h in rows
            if h.status == "completed"
            and h.completed_at
            and (now - ensure_aware(h.completed_at)) <= timedelta(days=RECURRING_WINDOW_DAYS)
            and (h.duration_hours or 0) >= RECURRING_SLOW_HOURS
        ]
        grouped: dict[str, list[CoordinationHandoff]] = defaultdict(list)
        for h in completed:
            key = f"{h.from_owner_id or 'none'}:{h.to_owner_id or 'none'}"
            grouped[key].append(h)
        for key, hs in grouped.items():
            if len(hs) < RECURRING_NEEDED:
                continue
            hs.sort(key=lambda h: h.occurred_at)
            from_label = labels.get(hs[0].from_owner_id or "", hs[0].from_owner_label)
            to_label = labels.get(hs[0].to_owner_id or "", hs[0].to_owner_label)
            evidence = [
                f"{len(hs)} handoff(s) from {from_label} to {to_label} "
                f"took {RECURRING_SLOW_HOURS}+ hours in the last "
                f"{RECURRING_WINDOW_DAYS} days",
            ]
            for h in hs[-3:]:
                evidence.append(
                    f"'{h.task_title}' took {round(h.duration_hours or 0)} hours "
                    f"({_iso(h.occurred_at)[:10]})"
                )
            findings.append({
                "kind": "recurring_handoff",
                "fingerprint": f"recurring:{key}",
                "project_id": hs[-1].project_id,
                "subject_id": key[:64],
                "subject_label": f"{from_label} → {to_label}",
                "title": f"Repeated slow handoffs between {from_label} and {to_label}",
                "summary": (
                    f"{len(hs)} task(s) handed from {from_label} to {to_label} "
                    f"each took over {RECURRING_SLOW_HOURS} hours to settle."
                ),
                "evidence": evidence[:MAX_EVIDENCE_LINES],
                "confidence": min(0.95, 0.80 + 0.05 * (len(hs) - RECURRING_NEEDED)),
                "severity": "high",
            })
        return findings

    async def _project_capability_rows(
        self, db: AsyncSession, *, organization_id: str, project_ids: list[str],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """project_id -> skill_id -> {skill_name, link_status} (one query)."""
        rows = list(
            (
                await db.execute(
                    select(CapabilityProjectLink).where(
                        CapabilityProjectLink.organization_id == organization_id,
                        CapabilityProjectLink.project_id.in_(project_ids or [""]),
                        CapabilityProjectLink.status == "active",
                    )
                )
            ).scalars().all()
        )
        by_project: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for r in rows:
            by_project[r.project_id][r.skill_id] = {
                "skill_name": r.skill_name,
                "link_status": r.status,
            }
        return dict(by_project)

    async def _contention(
        self, db: AsyncSession, *, organization_id: str,
        project_by_id: dict[str, Project], states: dict[str, ProjectExecutionState],
        capability_rows: dict[str, dict[str, dict[str, Any]]],
    ) -> dict[str, Any]:
        """Projects contending for one constrained capability (bounded)."""
        skill_projects: dict[str, list[str]] = defaultdict(list)
        skill_names: dict[str, str] = {}
        for pid, skills in capability_rows.items():
            if pid not in project_by_id:
                continue
            for skill_id, info in skills.items():
                skill_projects[skill_id].append(pid)
                skill_names[skill_id] = info["skill_name"]
        if not skill_projects:
            return {"findings": [], "contention_by_skill": {}}

        caps = {
            r.skill_id: r
            for r in (
                await db.execute(
                    select(OrgCapability).where(
                        OrgCapability.organization_id == organization_id,
                        OrgCapability.skill_id.in_(
                            list(skill_projects.keys())[: MAX_CONSTRAINED_SKILLS + 20]
                        ),
                    )
                )
            ).scalars().all()
        }
        findings: list[dict[str, Any]] = []
        contention_by_skill: dict[str, dict[str, Any]] = {}
        for skill_id in sorted(skill_projects):
            cap = caps.get(skill_id)
            if cap is None or cap.capacity_state not in ("constrained", "stretched"):
                continue
            members = sorted(skill_projects[skill_id])[: MAX_CONTENTION_PROJECTS + 4]
            if len(members) < 2:
                continue
            name = skill_names.get(skill_id) or cap.canonical_name or ""
            projects_shown = members[:MAX_CONTENTION_PROJECTS]
            evidence = [
                f"{len(members)} active project(s) demand '{name}'",
                f"capability state {cap.capacity_state} with "
                f"{cap.capacity_available} free expert(s)",
            ]
            for pid in projects_shown:
                project = project_by_id.get(pid)
                if project:
                    evidence.append(f"'{project.name}' is actively demanding it")
            severity = "critical" if cap.capacity_available <= 0 else "high"
            findings.append({
                "kind": "shared_capacity",
                "fingerprint": f"shared_capacity:{skill_id}",
                "project_id": None,
                "subject_id": skill_id,
                "subject_label": name,
                "title": f"{len(members)} projects compete for '{name}'",
                "summary": (
                    f"'{name}' is {cap.capacity_state} ({cap.capacity_available} "
                    f"free) and {len(members)} active projects demand it."
                ),
                "evidence": evidence[:MAX_EVIDENCE_LINES],
                "confidence": 0.82 if cap.capacity_available <= 0 else 0.72,
                "severity": severity,
            })
            contention_by_skill[skill_id] = {
                "skill_name": name,
                "capacity_state": cap.capacity_state,
                "capacity_available": cap.capacity_available,
                "project_ids": members,
            }
        return {"findings": findings, "contention_by_skill": contention_by_skill}

    async def _critical_conflicts(
        self, db: AsyncSession, *, organization_id: str,
        project_by_id: dict[str, Project], states: dict[str, ProjectExecutionState],
        contention: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """A critical path is blocked where capacity is shared — the sharpest
        coordination signal: two projects cannot both advance without one
        resolving its blockage."""
        findings: list[dict[str, Any]] = []
        for skill_id, info in contention["contention_by_skill"].items():
            members = [pid for pid in info["project_ids"] if pid in project_by_id]
            critical_blocked = []
            for pid in members:
                state = states.get(pid)
                if state is None:
                    continue
                cpath = state.critical_path or {}
                critical_ids = set(cpath.get("critical_task_ids") or [])
                for b in (state.blockers or []):
                    if b["task_id"] in critical_ids:
                        critical_blocked.append((pid, b))
                        break
            if len(critical_blocked) < 2:
                continue
            pair = tuple(sorted(p[0] for p in critical_blocked))
            evidence = [
                f"'{info['skill_name']}' is contended by "
                + ", ".join(f"'{project_by_id[pid].name}'" for pid in pair),
            ]
            for pid, b in critical_blocked:
                evidence.append(
                    f"'{project_by_id[pid].name}' has blocked critical-path "
                    f"task '{b['title']}'"
                )
            findings.append({
                "kind": "critical_conflict",
                "fingerprint": f"critical_conflict:{':'.join(pair)}:{skill_id}",
                "project_id": None,
                "subject_id": skill_id,
                "subject_label": info["skill_name"],
                "title": (
                    "Blocked critical paths contend for the same constrained "
                    f"capability '{info['skill_name']}'"
                ),
                "summary": (
                    f"{len(pair)} projects have blocked work on their critical "
                    f"paths while sharing the constrained '{info['skill_name']}' "
                    f"capability. Both cannot be unblocked by the same experts."
                ),
                "evidence": evidence[:MAX_EVIDENCE_LINES],
                "confidence": 0.85,
                "severity": "critical",
            })
        return findings

    async def _project_teams(
        self, db: AsyncSession, *, organization_id: str, project_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """project_id -> [{team_id, team_name}] (bounded, batched reads)."""
        from app.models.employee import Employee
        from app.models.project import ProjectMember
        from app.models.team import Team

        members = list(
            (
                await db.execute(
                    select(ProjectMember).where(
                        ProjectMember.organization_id == organization_id,
                        ProjectMember.project_id.in_(project_ids or [""]),
                    ).limit(MAX_NEIGHBOR_PROJECTS * MAX_TEAMS_PER_PROJECT * 8)
                )
            ).scalars().all()
        )
        employee_ids = {m.employee_id for m in members}
        if not employee_ids:
            return {}
        employees = {
            e.id: e
            for e in (
                await db.execute(
                    select(Employee.id, Employee.team_id).where(
                        Employee.organization_id == organization_id,
                        Employee.id.in_(list(employee_ids)),
                    )
                )
            ).all()
        }
        team_ids = {tid for _, tid in employees.values() if tid}
        team_names = dict(
            (
                await db.execute(
                    select(Team.id, Team.name).where(
                        Team.organization_id == organization_id,
                        Team.id.in_(list(team_ids)),
                    )
                )
            ).all()
        )
        by_project: dict[str, dict[str, str]] = defaultdict(dict)
        for m in members:
            tid = employees.get(m.employee_id, (None, None))[1]
            if tid:
                by_project[m.project_id][tid] = team_names.get(tid, tid)
        return {
            pid: [
                {"team_id": tid, "team_name": tname}
                for tid, tname in sorted(teams.items())
            ][:MAX_TEAMS_PER_PROJECT]
            for pid, teams in by_project.items()
        }

    async def _coordination_gaps(
        self, db: AsyncSession, *, organization_id: str,
        project_by_id: dict[str, Project],
        teams_by_project: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """A project engages multiple teams whose collaboration has no
        evidence — required coordination with no working path."""
        findings: list[dict[str, Any]] = []
        scanned_projects = [
            pid for pid in list(project_by_id)[:MAX_NEIGHBOR_PROJECTS]
            if pid in teams_by_project
        ]
        team_ids = {
            t["team_id"]
            for teams in teams_by_project.values()
            for t in teams
        }
        pairs: set[tuple[str, str]] = set()
        rows: list[CollaborationUnitPair] = []
        rows_b: list[CollaborationUnitPair] = []
        if team_ids:
            rows = list(
                (
                    await db.execute(
                        select(CollaborationUnitPair).where(
                            CollaborationUnitPair.organization_id == organization_id,
                            CollaborationUnitPair.unit_type == "team",
                            CollaborationUnitPair.unit_a_id.in_(list(team_ids)),
                        )
                    )
                ).scalars().all()
            )
            for r in rows:
                pairs.add((r.unit_a_id, r.unit_b_id))
            rows_b = list(
                (
                    await db.execute(
                        select(CollaborationUnitPair).where(
                            CollaborationUnitPair.organization_id == organization_id,
                            CollaborationUnitPair.unit_type == "team",
                            CollaborationUnitPair.unit_b_id.in_(list(team_ids)),
                        )
                    )
                ).scalars().all()
            )
            for r in rows_b:
                pairs.add((r.unit_a_id, r.unit_b_id))
        row_by_pair: dict[tuple[str, str], CollaborationUnitPair] = {}
        for r in rows + rows_b:
            row_by_pair[(r.unit_a_id, r.unit_b_id)] = r

        for pid in scanned_projects:
            project = project_by_id[pid]
            teams = teams_by_project[pid]
            if len(teams) < 2:
                continue
            for i in range(len(teams)):
                for j in range(i + 1, len(teams)):
                    if len(findings) >= MAX_GAP_PAIRS:
                        return findings
                    a, b = teams[i], teams[j]
                    row = row_by_pair.get(
                        tuple(sorted((a["team_id"], b["team_id"])))
                    )
                    if row is not None and row.evidence_count > 0:
                        if row.failed_interactions >= GAP_WEAK_FAILURES:
                            findings.append({
                                "kind": "coordination_gap",
                                "fingerprint": f"gap:{pid}:{a['team_id']}:{b['team_id']}",
                                "project_id": pid,
                                "subject_id": f"{a['team_id']}:{b['team_id']}"[:64],
                                "subject_label": f"{a['team_name']} ↔ {b['team_name']}",
                                "title": (
                                    f"Weak coordination between {a['team_name']} "
                                    f"and {b['team_name']} in '{project.name}'"
                                ),
                                "summary": (
                                    f"The teams coordinate on '{project.name}' but "
                                    f"{row.failed_interactions} failed interaction(s) "
                                    f"mark the relationship."
                                ),
                                "evidence": [
                                    f"'{project.name}' engages teams "
                                    f"'{a['team_name']}' and '{b['team_name']}'",
                                    f"{row.failed_interactions} failed interaction(s) "
                                    f"on {row.evidence_count} evidence item(s)",
                                ][:MAX_EVIDENCE_LINES],
                                "confidence": 0.60,
                                "severity": "low",
                            })
                        continue
                    findings.append({
                        "kind": "coordination_gap",
                        "fingerprint": f"gap:{pid}:{a['team_id']}:{b['team_id']}",
                        "project_id": pid,
                        "subject_id": f"{a['team_id']}:{b['team_id']}"[:64],
                        "subject_label": f"{a['team_name']} ↔ {b['team_name']}",
                        "title": (
                            f"No collaboration evidence between {a['team_name']} "
                            f"and {b['team_name']} on '{project.name}'"
                        ),
                        "summary": (
                            f"'{project.name}' engages both '{a['team_name']}' and "
                            f"'{b['team_name']}' but the collaboration ledger has "
                            f"no evidence of the teams working together."
                        ),
                        "evidence": [
                            f"'{project.name}' engages teams '{a['team_name']}' "
                            f"and '{b['team_name']}'",
                            "no collaboration evidence exists between the teams",
                        ][:MAX_EVIDENCE_LINES],
                        "confidence": 0.62,
                        "severity": "medium",
                    })
        return findings

    async def _propagation_risks(
        self, db: AsyncSession, *, organization_id: str,
        project_by_id: dict[str, Project], states: dict[str, ProjectExecutionState],
        contention: dict[str, Any],
        capability_rows: dict[str, dict[str, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """A blocked critical path reaches milestones, the goal chain,
        pending decisions and capability partners."""
        findings: list[dict[str, Any]] = []
        for pid in list(project_by_id)[:MAX_NEIGHBOR_PROJECTS]:
            state = states.get(pid)
            if state is None:
                continue
            cpath = state.critical_path or {}
            critical_ids = set(cpath.get("critical_task_ids") or [])
            blocked_critical = [
                b for b in (state.blockers or []) if b["task_id"] in critical_ids
            ]
            if not blocked_critical:
                continue
            project = project_by_id[pid]
            steps: list[dict[str, Any]] = []
            evidence = [
                f"{len(blocked_critical)} blocked task(s) sit on "
                f"'{project.name}' critical path",
            ]
            for b in blocked_critical[:2]:
                root = b["chain"][0]["title"] if b["chain"] else "a dependency"
                steps.append({
                    "step": len(steps) + 1,
                    "from": f"task '{b['title']}'",
                    "via": f"blocked by '{root}'",
                    "to": project.name,
                })
                evidence.append(
                    f"'{b['title']}' is blocked by '{root}' (chain depth "
                    f"{b['chain_depth']})"
                )
            milestone_ids = set()
            if blocked_critical:
                task_rows = (
                    await db.execute(
                        select(Task.id, Task.milestone_id).where(
                            Task.organization_id == organization_id,
                            Task.id.in_([b["task_id"] for b in blocked_critical]),
                        )
                    )
                ).all()
                milestone_ids = {
                    t.milestone_id for t in task_rows if t.milestone_id
                }
            if milestone_ids:
                milestones = list(
                    (
                        await db.execute(
                            select(Milestone).where(
                                Milestone.organization_id == organization_id,
                                Milestone.id.in_(list(milestone_ids)),
                            )
                        )
                    ).scalars().all()
                )
                for m in milestones[:2]:
                    if len(steps) >= MAX_PROPAGATION_STEPS:
                        break
                    steps.append({
                        "step": len(steps) + 1,
                        "from": f"milestone '{m.name}'",
                        "via": "blocked predecessor task",
                        "to": f"due {_iso(m.due_date) or 'unscheduled'}",
                    })
                    evidence.append(
                        f"milestone '{m.name}' follows the blocked work"
                    )
            chain = state.goal_chain or []
            if chain and len(steps) < MAX_PROPAGATION_STEPS:
                steps.append({
                    "step": len(steps) + 1,
                    "from": project.name,
                    "via": "goal chain",
                    "to": f"goal '{chain[0]['title']}'",
                })
                evidence.append(
                    f"the project is anchored to the goal '{chain[0]['title']}'"
                )
            pending = [d for d in (state.pending_decisions or []) if d.get("open_actions", 0) > 0]
            if pending and len(steps) < MAX_PROPAGATION_STEPS:
                steps.append({
                    "step": len(steps) + 1,
                    "from": project.name,
                    "via": "pending decision with open action task(s)",
                    "to": f"decision '{pending[0]['title']}'",
                })
                evidence.append(
                    f"{len(pending)} pending decision(s) with open action task(s)"
                )
            partners: set[str] = set()
            for skill_id in (capability_rows.get(pid) or {}):
                if skill_id in contention["contention_by_skill"]:
                    partners.update(
                        contention["contention_by_skill"][skill_id]["project_ids"]
                    )
            partners.discard(pid)
            if partners and len(steps) < MAX_PROPAGATION_STEPS:
                names = ", ".join(
                    project_by_id[x].name for x in sorted(partners)[:2]
                )
                steps.append({
                    "step": len(steps) + 1,
                    "from": project.name,
                    "via": "shared constrained capability",
                    "to": names,
                })
                evidence.append(
                    f"it shares a constrained capability with {names}"
                )
            if not steps:
                continue
            findings.append({
                "kind": "propagation_risk",
                "fingerprint": f"propagation:{pid}",
                "project_id": pid,
                "subject_id": pid,
                "subject_label": project.name,
                "title": f"'{project.name}' blockage propagates beyond the project",
                "summary": (
                    f"{len(blocked_critical)} blocked critical-path task(s) in "
                    f"'{project.name}' reach further: {steps[-1]['to']}."
                ),
                "evidence": evidence[:MAX_EVIDENCE_LINES],
                "propagation": steps,
                "confidence": 0.80,
                "severity": "high",
            })
        return findings

    # -------------------------------------------------------------- surfaces

    async def center(
        self, db: AsyncSession, *, organization_id: str, access: Any,
    ) -> dict[str, Any]:
        """The Execution Coordination Center — one glance at how the whole
        org coordinates, with recommendations. Org-wide surface."""
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
        project_by_id = {p.id: p for p in projects}
        incidents = list(
            (
                await db.execute(
                    select(CoordinationIncident)
                    .where(
                        CoordinationIncident.organization_id == organization_id,
                        CoordinationIncident.status == "open",
                    )
                    .order_by(
                        CoordinationIncident.severity.desc(),
                        CoordinationIncident.confidence.desc(),
                    )
                    .limit(MAX_INCIDENTS_SHOWN)
                )
            ).scalars().all()
        )
        rows = [
            self._incident_row(i, project_by_id) for i in incidents
        ]
        handoff_stats = await self._handoff_stats(db, organization_id=organization_id)
        recommendations = self._recommendations(rows)
        counts = self._center_counts(rows)
        affected = defaultdict(int)
        for r in rows:
            pid = r.get("project_id")
            if pid:
                affected[pid] += 1
        return {
            "total_incidents": len(rows),
            "counts": counts,
            "incidents": rows,
            "handoffs": handoff_stats,
            "recommendations": recommendations,
            "projects_affected": [
                {
                    "project_id": pid,
                    "name": project_by_id[pid].name,
                    "incident_count": n,
                }
                for pid, n in sorted(affected.items(), key=lambda kv: -kv[1])[:10]
            ],
        }

    def _incident_row(
        self, i: CoordinationIncident, project_by_id: dict[str, Project],
    ) -> dict[str, Any]:
        return {
            "incident_id": i.id,
            "kind": i.kind,
            "severity": i.severity,
            "status": i.status,
            "project_id": i.project_id,
            "project_name": (
                project_by_id[i.project_id].name if i.project_id in project_by_id else None
            ),
            "subject_label": i.subject_label,
            "title": i.title,
            "summary": i.summary,
            "evidence": i.evidence or [],
            "propagation": i.propagation or [],
            "confidence": round(float(i.confidence or 0), 2),
            "first_seen_at": _iso(i.first_seen_at),
            "last_seen_at": _iso(i.last_seen_at),
            "resolved_by": i.resolved_by,
            "resolve_note": i.resolve_note,
            "resolved_at": _iso(i.resolved_at),
        }

    def _center_counts(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        by_kind: dict[str, int] = defaultdict(int)
        by_severity: dict[str, int] = defaultdict(int)
        for r in rows:
            by_kind[r["kind"]] += 1
            by_severity[r["severity"]] += 1
        return {
            "open": len(rows),
            "critical": by_severity.get("critical", 0),
            "high": by_severity.get("high", 0),
            "medium": by_severity.get("medium", 0),
            "low": by_severity.get("low", 0),
            "handoff_risk": by_kind.get("handoff_risk", 0),
            "recurring_handoff": by_kind.get("recurring_handoff", 0),
            "shared_capacity": by_kind.get("shared_capacity", 0),
            "critical_conflict": by_kind.get("critical_conflict", 0),
            "coordination_gap": by_kind.get("coordination_gap", 0),
            "propagation_risk": by_kind.get("propagation_risk", 0),
        }

    def _recommendations(
        self, rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Deterministic priorities: critical conflicts first, then shared
        capacity, propagation, handoffs, gaps — each with its evidence."""
        order = {
            "critical_conflict": 0,
            "shared_capacity": 1,
            "propagation_risk": 2,
            "handoff_risk": 3,
            "recurring_handoff": 4,
            "coordination_gap": 5,
        }
        ranked = sorted(
            rows,
            key=lambda r: (
                order.get(r["kind"], 9),
                SEVERITY_ORDER.index(r["severity"]),
                -r["confidence"],
            ),
        )
        out: list[dict[str, Any]] = []
        for r in ranked[:MAX_RECOMMENDATIONS]:
            why = [f"{e}" for e in (r["evidence"] or [])[:4]]
            summary = {
                "critical_conflict": (
                    "Acknowledge the conflict: have the owners of "
                    f"{r['subject_label']} agree who unblocks first"
                ),
                "shared_capacity": (
                    f"Coordinate who absorbs '{r['subject_label']}' demand first"
                ),
                "propagation_risk": (
                    f"Resolve the blocked critical work in {r['project_name'] or 'the project'}"
                ),
                "handoff_risk": (
                    f"Confirm the handoff on '{r['subject_label']}' is actually underway"
                ),
                "recurring_handoff": (
                    f"Review why {r['subject_label']} handoffs keep taking 72+ hours"
                ),
                "coordination_gap": (
                    f"Open an explicit coordination path for {r['subject_label']}"
                ),
            }.get(r["kind"], "Review the coordination finding")
            out.append({
                "kind": r["kind"],
                "summary": summary,
                "why": why,
                "confidence": r["confidence"],
                "incident_id": r["incident_id"],
                "project_id": r["project_id"],
                "project_name": r["project_name"],
            })
        return out

    async def _handoff_stats(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        rows = list(
            (
                await db.execute(
                    select(CoordinationHandoff).where(
                        CoordinationHandoff.organization_id == organization_id,
                    )
                    .order_by(CoordinationHandoff.occurred_at.desc())
                    .limit(MAX_HANDOFFS_KEPT)
                )
            ).scalars().all()
        )
        pending = sum(1 for h in rows if h.status == "pending")
        completed = [
            h for h in rows
            if h.status == "completed" and h.duration_hours is not None
        ]
        avg = (
            round(sum(h.duration_hours or 0 for h in completed) / len(completed), 1)
            if completed else None
        )
        now = utcnow()
        slow_30d = sum(
            1 for h in completed
            if h.completed_at
            and (now - ensure_aware(h.completed_at)) <= timedelta(days=RECURRING_WINDOW_DAYS)
            and h.duration_hours >= RECURRING_SLOW_HOURS
        )
        return {
            "pending": pending,
            "completed": len(completed),
            "avg_duration_hours": avg,
            "slow_30d": slow_30d,
        }

    async def project_detail(
        self, db: AsyncSession, *, organization_id: str, project_id: str,
    ) -> Optional[dict[str, Any]]:
        """One project's coordination view: its incidents, handoffs,
        propagation, alternatives, what-if and knowledge recall."""
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
        incidents = list(
            (
                await db.execute(
                    select(CoordinationIncident).where(
                        CoordinationIncident.organization_id == organization_id,
                        CoordinationIncident.status == "open",
                        CoordinationIncident.project_id == project_id,
                    )
                    .order_by(
                        CoordinationIncident.severity.desc(),
                        CoordinationIncident.confidence.desc(),
                    )
                    .limit(MAX_INCIDENTS_SHOWN)
                )
            ).scalars().all()
        )
        rows = [self._incident_row(i, {project_id: project}) for i in incidents]
        handoffs = list(
            (
                await db.execute(
                    select(CoordinationHandoff)
                    .where(
                        CoordinationHandoff.organization_id == organization_id,
                        CoordinationHandoff.project_id == project_id,
                    )
                    .order_by(CoordinationHandoff.occurred_at.desc())
                    .limit(50)
                )
            ).scalars().all()
        )
        history = list(
            (
                await db.execute(
                    select(CoordinationHistory)
                    .where(
                        CoordinationHistory.organization_id == organization_id,
                        CoordinationHistory.project_id == project_id,
                    )
                    .order_by(CoordinationHistory.occurred_at.desc())
                    .limit(MAX_HISTORY_SHOWN)
                )
            ).scalars().all()
        )
        return {
            "project_id": project.id,
            "code": project.code,
            "name": project.name,
            "status": project.status,
            "incidents": rows,
            "recommendations": self._recommendations(rows),
            "handoffs": {
                "pending": [
                    {
                        "task_id": h.task_id,
                        "task_title": h.task_title,
                        "from_owner": h.from_owner_label,
                        "to_owner": h.to_owner_label,
                        "pending_hours": (
                            _hours_between(h.occurred_at, utcnow())
                            if h.status == "pending" else None
                        ),
                        "occurred_at": _iso(h.occurred_at),
                    }
                    for h in handoffs if h.status == "pending"
                ],
                "recent_completed": [
                    {
                        "task_id": h.task_id,
                        "task_title": h.task_title,
                        "from_owner": h.from_owner_label,
                        "to_owner": h.to_owner_label,
                        "duration_hours": h.duration_hours,
                        "completed_at": _iso(h.completed_at),
                    }
                    for h in handoffs if h.status == "completed"
                ][:10],
            },
            "propagation": [
                {"event_name": h.event_name, "kind": h.kind,
                 "severity": h.severity, "title": h.title,
                 "occurred_at": _iso(h.occurred_at)}
                for h in history
            ],
            "alternatives": await self._alternatives(
                db, organization_id=organization_id, project=project, rows=rows,
            ),
            "what_if": await self._what_if(
                db, organization_id=organization_id, project=project, rows=rows,
            ),
        }

    async def _alternatives(
        self, db: AsyncSession, *, organization_id: str,
        project: Project, rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Bounded alternative-owner candidates for blocked critical work,
        from expertise + availability + collaboration evidence."""
        from app.models.skills_intelligence import Expertise

        project_rows = [r for r in rows if r["kind"] in (
            "handoff_risk", "propagation_risk",
        )]
        if not project_rows:
            return []
        skill_ids = [
            r["subject_id"] for r in rows if r["kind"] in (
                "shared_capacity", "critical_conflict",
            )
        ]
        if not skill_ids:
            return []
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for skill_id in skill_ids[:3]:
            experts = list(
                (
                    await db.execute(
                        select(Expertise)
                        .where(
                            Expertise.organization_id == organization_id,
                            Expertise.skill_id == skill_id,
                            Expertise.score >= 50,
                        )
                        .order_by(Expertise.score.desc())
                        .limit(MAX_ALTERNATIVES * 3)
                    )
                ).scalars().all()
            )
            for e in experts:
                if e.person_id in seen or len(candidates) >= MAX_ALTERNATIVES * 3:
                    continue
                seen.add(e.person_id)
                candidates.append({
                    "person_id": e.person_id,
                    "skill_name": rows[0]["subject_label"],
                    "expertise_score": round(float(e.score), 1),
                    "freshness": e.freshness,
                    "confidence": round(float(e.confidence or 0), 2),
                })
        if not candidates:
            return []
        labels = await self._employee_labels(db, organization_id)
        pending_owners = await self._pending_owner_ids(
            db, organization_id=organization_id,
        )
        out: list[dict[str, Any]] = []
        for c in candidates:
            if len(out) >= MAX_ALTERNATIVES:
                break
            busy = c["person_id"] in pending_owners
            out.append({
                "person_id": c["person_id"],
                "person_label": labels.get(c["person_id"], "?"),
                "skill": c["skill_name"],
                "expertise_score": c["expertise_score"],
                "freshness": c["freshness"],
                "confidence": c["confidence"],
                "availability": "no pending handoffs" if not busy else "has pending handoffs",
                "reason": (
                    f"expertise {c['expertise_score']} on '{c['skill_name']}' "
                    f"({c['freshness']}) with confidence {c['confidence']}"
                ),
                "boundary": (
                    "The system never reassigns automatically — a human "
                    "decides whether and when to move work."
                ),
            })
        return out

    async def _pending_owner_ids(
        self, db: AsyncSession, *, organization_id: str,
    ) -> set[str]:
        rows = (
            await db.execute(
                select(CoordinationHandoff.to_owner_id).where(
                    CoordinationHandoff.organization_id == organization_id,
                    CoordinationHandoff.status == "pending",
                )
            )
        ).scalars().all()
        return {rid for rid in rows if rid}

    async def _what_if(
        self, db: AsyncSession, *, organization_id: str,
        project: Project, rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Bounded options — explicitly NOT predictions. Each option lists
        its deterministic effects and what it does NOT claim."""
        options: list[dict[str, Any]] = []
        if rows:
            today = date.today()
            shift = WHATIF_SHIFT_DAYS
            effects: list[dict[str, Any]] = []
            before_end = project.end_date
            if before_end:
                effects.append({
                    "surface": "project end date",
                    "before": _iso(before_end),
                    "after": _iso(before_end + timedelta(days=shift)),
                })
            if not effects:
                milestones = list(
                    (
                        await db.execute(
                            select(Milestone).where(
                                Milestone.organization_id == organization_id,
                                Milestone.project_id == project.id,
                                Milestone.status != "completed",
                            )
                            .order_by(Milestone.due_date.asc())
                            .limit(5)
                        )
                    ).scalars().all()
                )
                for m in milestones[:2]:
                    if m.due_date:
                        effects.append({
                            "surface": f"milestone '{m.name}'",
                            "before": _iso(m.due_date),
                            "after": _iso(m.due_date + timedelta(days=shift)),
                        })
            options.append({
                "kind": "delay",
                "title": f"Shift dates by {shift} days",
                "shift_days": shift,
                "effects": effects[:3],
                "triggered_by": [
                    r["title"] for r in rows[:2]
                ],
                "boundary": (
                    "This lists calendar deltas only. It is not a schedule "
                    "prediction: downstream cost, customer commitments and "
                    "team availability are not modeled here."
                ),
            })
            alternatives = await self._alternatives(
                db, organization_id=organization_id, project=project, rows=rows,
            )
            if alternatives:
                options.append({
                    "kind": "reassign",
                    "title": "Move blocked work to an alternative owner",
                    "options": alternatives[:MAX_ALTERNATIVES],
                    "triggered_by": [
                        r["title"] for r in rows[:2]
                    ],
                    "boundary": (
                        "Candidates are evidence-backed, but the choice is a "
                        "human decision; reallocation is never executed by "
                        "this system."
                    ),
                })
        knowledge = await self._knowledge_lines(
            db, organization_id=organization_id, project=project,
        )
        if knowledge:
            options.append({
                "kind": "knowledge",
                "title": "Recall how the company handled similar coordination",
                "topics": knowledge,
                "triggered_by": [],
                "boundary": (
                    "Past projects are context, not precedent — conditions "
                    "may differ from what the ledger shows."
                ),
            })
        return {
            "options": options[:MAX_WHATIF_OPTIONS],
            "boundary": (
                "These are bounded options for humans to evaluate. Nothing "
                "here predicts outcomes or reallocates anyone automatically."
            ),
        }

    async def _knowledge_lines(
        self, db: AsyncSession, *, organization_id: str, project: Project,
    ) -> list[dict[str, Any]]:
        """Bounded topic recall: topics matching the project or its
        capabilities, with the entities they anchor."""
        tokens = {t for t in (project.name or "").lower().split() if len(t) >= 3}
        topics = list(
            (
                await db.execute(
                    select(KnowledgeTopic).where(
                        KnowledgeTopic.organization_id == organization_id,
                        KnowledgeTopic.status == "active",
                    ).limit(100)
                )
            ).scalars().all()
        )
        out: list[dict[str, Any]] = []
        for topic in topics:
            name_tokens = {t for t in (topic.name or "").lower().split()}
            if not (tokens & name_tokens):
                continue
            out.append({
                "topic": topic.name,
                "entity_type": topic.entity_type,
                "entity_id": topic.entity_id,
                "category": topic.category,
            })
            if len(out) >= MAX_KNOWLEDGE_LINES:
                break
        return out

    async def resolve_incident(
        self, db: AsyncSession, *, organization_id: str,
        incident_id: str, note: Optional[str], resolved_by: str,
    ) -> Optional[dict[str, Any]]:
        """A human resolves a finding (advisory record — never mutates the
        org). A resolution is durable; if the condition recurs, the next
        refresh reopens the finding with fresh evidence."""
        incident = (
            await db.execute(
                select(CoordinationIncident).where(
                    CoordinationIncident.organization_id == organization_id,
                    CoordinationIncident.id == incident_id,
                )
            )
        ).scalar_one_or_none()
        if incident is None:
            return None
        if incident.status == "open":
            incident.status = "resolved"
            incident.resolved_at = utcnow()
            incident.resolved_by = resolved_by
            incident.resolve_note = note
            await self._history(
                db, organization_id=organization_id,
                incident=incident,
                event_name="coordination.incident.resolved",
                source_event_id=f"resolve:{uuid4().hex[:24]}",
            )
        return self._incident_row(incident, {})

    # ---------------------------------------------------------------- helpers

    async def _labels_for(
        self, db: AsyncSession, *, organization_id: str, ids: list[Optional[str]],
    ) -> dict[str, str]:
        from app.models.employee import Employee

        wanted = [i for i in ids if i]
        if not wanted:
            return {}
        rows = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.id.in_(wanted),
                )
            )
        ).scalars().all()
        return {emp.id: emp.full_name for emp in rows}

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


coordination_engine = CoordinationEngine()
