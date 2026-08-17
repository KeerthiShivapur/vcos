"""Slice 4F.6 — Organizational Capability & Capacity Intelligence engine.

The canonical, change-driven engine behind "what can the organization do
and how much is free right now". One bounded pipeline:

    durable event -> normalize (person/project/skill) -> bounded recompute
    of exactly the capabilities the event touches -> lifecycle + capacity +
    demand + concentration -> monthly history markers -> advisory signals

Boundary laws (from the 4F.6 directive):
  * Change-driven: an event touches ONLY the capabilities it can affect
    (the person's evidence-backed skills, or the skill itself). There is NO
    full rescan and NO O(N²) pass anywhere.
  * Exact-once: capability recompute is idempotent (derived truth), and
    project<->capability links are keyed on (org, project, skill,
    source_event_id) so replays converge instead of double-counting.
  * Bounded: per-person skills, per-capability experts, linked projects,
    history rows, knowledge matches and signal lists are all hard-capped.
  * Explainable: every state, capacity share and signal carries the
    deterministic factors behind it — no opaque AI score.
  * Analysis NEVER changes the organization: findings are advisory signals
    that may only be acknowledged; no hire/fire/reassign/ownership change.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.employee import Employee
from app.models.org_capability_intelligence import (
    CapabilityHistory,
    CapabilityProjectLink,
    CapabilitySignal,
    OrgCapability,
)
from app.models.project import ProjectMember
from app.models.task import Task as TaskState
from app.models.skills_intelligence import (
    CanonicalSkill,
    Expertise as ExpertiseState,
    ExpertiseEvidence,
)

logger = logging.getLogger("vcos.intelligence.org_capability")

# Per-organization in-process write locks (same law as 4F.5): serialize
# multi-row updates within this process (event worker + drain endpoints).
_ORG_WRITE_LOCKS: dict[str, asyncio.Lock] = {}


def _org_write_lock(organization_id: str) -> asyncio.Lock:
    lock = _ORG_WRITE_LOCKS.get(organization_id)
    if lock is None:
        lock = asyncio.Lock()
        _ORG_WRITE_LOCKS[organization_id] = lock
    return lock


# ---------------------------------------------------------------------------
# hard bounds — one event may touch at most this much
# ---------------------------------------------------------------------------

MAX_PERSON_CAPABILITIES = 500   # capabilities refreshed per person per event
MAX_TOP_EXPERTS = 20            # expert rows surfaced per capability
MAX_EXPERT_SET = 500            # expert ids considered for set-membership SQL
MAX_LINKED_PROJECTS = 50        # demand reads per capability
MAX_KNOWLEDGE_TOPICS = 200      # knowledge match cap per capability
MAX_HISTORY_ROWS = 24           # detail history window
MAX_SIGNALS_SHOWN = 20          # open signals surfaced per capability

# ---------------------------------------------------------------------------
# deterministic thresholds (all evidence-backed, no invented numbers)
# ---------------------------------------------------------------------------

DORMANT_DAYS = 365              # no fresh evidence -> dormant
FRESH_DAYS = 90                 # "active" evidence window
DECLINE_FACTOR = 0.5            # current points < 0.5 * previous -> declining

# Lifecycle bands (deterministic, from bounded aggregates).
STRATEGIC_MIN_STRONG = 3        # strong experts required for strategic
STRATEGIC_MIN_EVIDENCE = 30
STRONG_MIN_STRONG = 2
STRONG_MIN_EVIDENCE = 10
ESTABLISHED_MIN_EVIDENCE = 4

# Capacity bands.
STRETCHED_FREE_SHARE = 0.3      # fewer free experts than 30% of potential

# Demand bands.
DEMAND_LOW = 2
DEMAND_MODERATE = 5

# Concentration advisory: one person carries this share of capability
# evidence with a second person far behind -> consider secondary ownership
# or knowledge transfer. NEVER an automatic action.
CONCENTRATION_WARNING_SHARE = 0.60
CONCENTRATION_CRITICAL_SHARE = 0.70

# Evidence strength weights for monthly points (deterministic).
STRENGTH_WEIGHTS = {"strong": 1.0, "medium": 0.5, "weak": 0.25}

# Capability lifecycle states (canonical vocabulary).
_CAP_STATES = (
    "unknown", "emerging", "established", "strong", "strategic",
    "declining", "dormant",
)

# Confidence: bounded deterministic function of corroboration, outcomes and
# recency. Never a model score.
CONF_BASE = 0.30
CONF_PER_KIND = 0.05            # up to 7 kinds -> +0.35
CONF_GOOD_OUTCOME = 0.15        # outcome ratio >= 0.7
CONF_FRESH = 0.15               # latest evidence within 90 days
CONF_RECENT = 0.05              # latest evidence within 365 days
CONF_CAP = 0.95


class OrgCapabilityEngine:
    # ------------------------------------------------------------------ entry

    async def record_event(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> None:
        """Dispatch one durable event to exactly the capabilities it touches.

        Never commits (the EventBus owns the transaction). Replays converge:
        link rows are keyed exact-once and every recompute is idempotent.
        """
        name = getattr(event, "name", None) or payload.get("event_name")
        if not name:
            return
        async with _org_write_lock(organization_id):
            if name == "expertise.updated":
                person_id = payload.get("employee_id")
                if person_id:
                    await self.refresh_person(
                        db, organization_id=organization_id, person_id=person_id,
                    )
                return
            if name.startswith("task."):
                await self._apply_task_event(
                    db, organization_id=organization_id, event=event, payload=payload,
                )
                return
            if name.startswith("project."):
                await self._apply_project_event(
                    db, organization_id=organization_id, event=event, payload=payload,
                )
                return
            if name.startswith("ownership."):
                owner = (
                    payload.get("to_owner_id") or payload.get("owner_id")
                    or payload.get("actor_id")
                )
                if owner:
                    await self.refresh_person(
                        db, organization_id=organization_id, person_id=owner,
                    )
                return
            if name in ("skill.created", "skill.updated"):
                skill_id = payload.get("skill_id")
                if skill_id:
                    await self.refresh_capability(
                        db, organization_id=organization_id, skill_id=skill_id,
                        event=event,
                    )
                return
            if name in ("decision.made", "decision.executed", "decision.implemented"):
                person_id = (
                    payload.get("decision_maker_id") or payload.get("actor_id")
                    or payload.get("owner_id")
                )
                if person_id:
                    await self.refresh_person(
                        db, organization_id=organization_id, person_id=person_id,
                    )
                return
            if name in ("approval.approved", "approval.rejected"):
                person_id = (
                    payload.get("approver_id") or payload.get("actor_id")
                    or payload.get("requested_by")
                )
                if person_id:
                    await self.refresh_person(
                        db, organization_id=organization_id, person_id=person_id,
                    )
                return
            if name in (
                "team.member.added", "team.member.removed", "employee.transferred",
            ):
                person_id = payload.get("employee_id") or payload.get("member_id")
                if person_id:
                    await self.refresh_person(
                        db, organization_id=organization_id, person_id=person_id,
                    )
                return

    # ------------------------------------------------------------- refresh

    async def refresh_person(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
    ) -> int:
        """Change-driven: recompute the capabilities of one person's
        evidence-backed skills (bounded to MAX_PERSON_CAPABILITIES)."""
        skills = list(
            (
                await db.execute(
                    select(ExpertiseState.skill_id).where(
                        ExpertiseState.organization_id == organization_id,
                        ExpertiseState.person_id == person_id,
                        ExpertiseState.score > 0,
                    ).limit(MAX_PERSON_CAPABILITIES)
                )
            ).scalars().all()
        )
        refreshed = 0
        for skill_id in skills:
            await self.refresh_capability(
                db, organization_id=organization_id, skill_id=skill_id,
            )
            refreshed += 1
        return refreshed

    async def refresh_capability(
        self, db: AsyncSession, *, organization_id: str, skill_id: str,
        event: Any = None,
    ) -> Optional[OrgCapability]:
        """Bounded recompute of ONE organizational capability row.

        Every field is a deterministic function of indexed aggregates:
        expertise cells, evidence ledger, project links, project members,
        open tasks, ownership windows and knowledge topics — all capped.
        """
        skill = (
            await db.execute(
                select(CanonicalSkill).where(
                    CanonicalSkill.organization_id == organization_id,
                    CanonicalSkill.id == skill_id,
                )
            )
        ).scalar_one_or_none()
        if skill is None:
            return None

        now = utcnow()
        month_key = now.strftime("%Y-%m")
        row = (
            await db.execute(
                select(OrgCapability).where(
                    OrgCapability.organization_id == organization_id,
                    OrgCapability.skill_id == skill_id,
                )
            )
        ).scalar_one_or_none()
        created = row is None
        if row is None:
            row = OrgCapability(
                organization_id=organization_id,
                skill_id=skill_id,
                canonical_name=skill.canonical_name,
                category=skill.category,
                month_key=month_key,
                points_prev_month=0.0,
                points_cur_month=0.0,
            )
            db.add(row)
            await db.flush()

        # 1. strength aggregates (indexed on org+skill)
        (member_count, total_evidence, avg_score, max_score, strong_count,
         success_sum, fail_sum, latest_at) = (
            await db.execute(
                select(
                    func.count(func.distinct(ExpertiseState.person_id)),
                    func.coalesce(func.sum(ExpertiseState.evidence_count), 0),
                    func.coalesce(func.avg(ExpertiseState.score), 0.0),
                    func.coalesce(func.max(ExpertiseState.score), 0.0),
                    func.count(func.distinct(case(
                        (
                            ExpertiseState.lifecycle.in_(("strong", "authoritative")),
                            ExpertiseState.person_id,
                        ),
                        else_=None,
                    ))),
                    func.coalesce(func.sum(ExpertiseState.successful_count), 0),
                    func.coalesce(func.sum(ExpertiseState.failed_count), 0),
                    func.max(ExpertiseState.last_observed),
                ).where(
                    ExpertiseState.organization_id == organization_id,
                    ExpertiseState.skill_id == skill_id,
                    ExpertiseState.score > 0,
                )
            )
        ).one()

        # 2. evidence kinds (corroboration) — bounded distinct groups
        kinds = list(
            (
                await db.execute(
                    select(ExpertiseEvidence.evidence_kind)
                    .where(
                        ExpertiseEvidence.organization_id == organization_id,
                        ExpertiseEvidence.skill_id == skill_id,
                    )
                    .group_by(ExpertiseEvidence.evidence_kind)
                    .order_by(func.count().desc())
                    .limit(8)
                )
            ).scalars().all()
        )

        # 3. top experts (bounded) + labels
        expert_rows = list(
            (
                await db.execute(
                    select(
                        ExpertiseState.person_id,
                        ExpertiseState.score,
                        ExpertiseState.evidence_count,
                        ExpertiseState.lifecycle,
                        ExpertiseState.last_observed,
                    ).where(
                        ExpertiseState.organization_id == organization_id,
                        ExpertiseState.skill_id == skill_id,
                        ExpertiseState.score > 0,
                    ).order_by(
                        ExpertiseState.score.desc(),
                        ExpertiseState.evidence_count.desc(),
                    ).limit(MAX_EXPERT_SET)
                )
            ).all()
        )
        expert_ids = [r[0] for r in expert_rows]
        labels: dict[str, str] = {}
        teams: dict[str, str] = {}
        team_ids: set[str] = set()
        if expert_ids:
            people = list(
                (
                    await db.execute(
                        select(
                            Employee.id, Employee.first_name, Employee.last_name,
                            Employee.team_id,
                        ).where(
                            Employee.organization_id == organization_id,
                            Employee.id.in_(expert_ids),
                        )
                    )
                ).all()
            )
            for person_row in people:
                person_id, first, last, team_id = person_row
                full = " ".join(p for p in (first, last) if p)
                labels[person_id] = full or person_id
                if team_id:
                    team_ids.add(team_id)
            if team_ids:
                from app.models.team import Team

                for t in (
                    await db.execute(
                        select(Team.id, Team.name).where(Team.id.in_(team_ids))
                    )
                ).all():
                    teams[t[0]] = t[1]

        # 4. capacity: committed (experts on active linked projects) and
        #    reserved (experts with open tasks) — both set-membership SQL
        active_project_ids = list(
            (
                await db.execute(
                    select(CapabilityProjectLink.project_id).where(
                        CapabilityProjectLink.organization_id == organization_id,
                        CapabilityProjectLink.skill_id == skill_id,
                        CapabilityProjectLink.status == "active",
                    ).distinct().limit(MAX_LINKED_PROJECTS)
                )
            ).scalars().all()
        )
        committed_ids: set[str] = set()
        if active_project_ids:
            committed_ids = {
                r[0]
                for r in (
                    await db.execute(
                        select(ProjectMember.employee_id)
                        .where(
                            ProjectMember.project_id.in_(active_project_ids),
                            ProjectMember.employee_id.in_(expert_ids or [""]),
                        )
                        .distinct()
                    )
                ).all()
            }
        open_statuses = ("backlog", "todo", "in_progress", "review", "blocked")
        reserved_ids: set[str] = set()
        if expert_ids:
            reserved_ids = {
                r[0]
                for r in (
                    await db.execute(
                        select(TaskState.assignee_id)
                        .where(
                            TaskState.organization_id == organization_id,
                            TaskState.assignee_id.in_(expert_ids),
                            TaskState.status.in_(open_statuses),
                        )
                        .distinct()
                    )
                ).all()
            }
        potential = int(member_count or 0)
        committed = len(committed_ids)
        busy = committed_ids | reserved_ids
        reserved = len(reserved_ids - committed_ids)
        available = max(potential - len(busy), 0)
        if potential == 0:
            capacity_state = "unknown"
        elif committed > 0 and available == 0:
            capacity_state = "constrained"
        elif available < max(1, round(potential * STRETCHED_FREE_SHARE)):
            capacity_state = "stretched"
        else:
            capacity_state = "available"

        # 5. demand (bounded current demand — never a forecast)
        demand_count = len(active_project_ids)
        if demand_count == 0:
            demand_state = "none"
        elif demand_count <= DEMAND_LOW:
            demand_state = "low"
        elif demand_count <= DEMAND_MODERATE:
            demand_state = "moderate"
        else:
            demand_state = "high"

        # 6. concentration (advisory — evidence share of the top experts)
        total_evidence_i = int(total_evidence or 0)
        concentration_share = (
            round(expert_rows[0][2] / total_evidence_i, 3) if total_evidence_i and expert_rows else 0.0
        )
        second_share = (
            round(expert_rows[1][2] / total_evidence_i, 3)
            if total_evidence_i and len(expert_rows) > 1 else 0.0
        )

        # 7. integration counts (bounded)
        owner_count = 0
        if expert_ids:
            from app.models.ownership_intelligence import OwnershipRelationship

            owner_count = (
                await db.execute(
                    select(func.count(func.distinct(OwnershipRelationship.owner_id)))
                    .where(
                        OwnershipRelationship.organization_id == organization_id,
                        OwnershipRelationship.status == "active",
                        OwnershipRelationship.owner_id.in_(expert_ids),
                    )
                )
            ).scalar_one() or 0
        team_count = len(team_ids)
        knowledge_count = 0
        if skill.canonical_name:
            from app.models.knowledge import KnowledgeTopic

            knowledge_count = len(
                (
                    await db.execute(
                        select(KnowledgeTopic.id).where(
                            KnowledgeTopic.organization_id == organization_id,
                            KnowledgeTopic.status == "active",
                            KnowledgeTopic.name.ilike(
                                f"%{skill.canonical_name}%"
                            ),
                        ).limit(MAX_KNOWLEDGE_TOPICS)
                    )
                ).scalars().all()
            )

        # 8. monthly markers + preserved history
        points = await self._month_points(
            db, organization_id=organization_id, skill_id=skill_id, month_key=month_key,
        )
        if row.month_key and row.month_key != month_key:
            # archive the completed month before rolling the markers
            await self._archive_month(
                db, organization_id=organization_id, skill_id=skill_id,
                row=row,
            )
            row.points_prev_month = row.points_cur_month
        elif created:
            row.points_prev_month = 0.0
        row.points_cur_month = points
        row.month_key = month_key

        # 9. lifecycle (deterministic state machine)
        lifecycle = self._derive_lifecycle(
            now=now, expert_count=potential, strong_count=int(strong_count or 0),
            evidence_count=total_evidence_i, avg_score=float(avg_score or 0.0),
            latest_at=latest_at, first_seen=row.first_seen,
            points_cur=row.points_cur_month, points_prev=row.points_prev_month,
        )
        row.lifecycle = lifecycle

        # 10. confidence (bounded deterministic function)
        outcome_ratio = (
            round(success_sum / (success_sum + fail_sum), 3)
            if (success_sum + fail_sum) > 0 else None
        )
        latest = ensure_aware(latest_at) if latest_at else None
        days_since = (now - latest).days if latest else None
        fresh = (
            CONF_FRESH if days_since is not None and days_since <= FRESH_DAYS
            else CONF_RECENT if days_since is not None and days_since <= DORMANT_DAYS
            else 0.0
        )
        confidence = min(
            CONF_BASE
            + CONF_PER_KIND * min(len(kinds), 7)
            + (CONF_GOOD_OUTCOME if (outcome_ratio or 0.0) >= 0.7 else 0.0)
            + fresh,
            CONF_CAP,
        )

        # 11. persist derived truth + explain
        row.expert_count = potential
        row.strong_expert_count = int(strong_count or 0)
        row.evidence_count = total_evidence_i
        row.corroborated_kinds = len(kinds)
        row.outcome_ratio = outcome_ratio
        row.confidence = round(confidence, 3)
        row.latest_evidence_at = latest
        row.capacity_potential = potential
        row.capacity_committed = committed
        row.capacity_reserved = reserved
        row.capacity_available = available
        row.capacity_state = capacity_state
        row.demand_count = demand_count
        row.demand_state = demand_state
        row.concentration_share = concentration_share
        row.second_share = second_share
        row.owner_count = int(owner_count or 0)
        row.team_count = team_count
        row.knowledge_count = knowledge_count
        row.factors_json = json.dumps({
            "experts": potential,
            "strong_experts": int(strong_count or 0),
            "evidence": total_evidence_i,
            "kinds": len(kinds),
            "outcome_ratio": outcome_ratio,
            "avg_score": round(float(avg_score or 0.0), 1),
            "max_score": round(float(max_score or 0.0), 1),
            "days_since_last_evidence": days_since,
            "capacity_committed": committed,
            "capacity_reserved": reserved,
            "capacity_available": available,
            "demand": demand_count,
            "teams": team_count,
            "owners": row.owner_count,
            "knowledge": knowledge_count,
            "month_points": points,
        })
        row.explain = self._explain(row)
        if event is not None:
            row.last_event_id = getattr(event, "id", None) or getattr(event, "name", None)
            row.last_event_at = now
        if created:
            row.first_seen = now
        await db.flush()

        # 12. advisory signals (reconciled per capability — bounded)
        await self._reconcile_signals(
            db, organization_id=organization_id, row=row,
        )
        return row

    async def _month_points(
        self, db: AsyncSession, *, organization_id: str, skill_id: str,
        month_key: str,
    ) -> float:
        """Weighted evidence volume in the current calendar month (bounded
        aggregate over the capability's evidence ledger)."""
        start = datetime.strptime(f"{month_key}-01", "%Y-%m-%d")
        start = ensure_aware(start)
        rows = list(
            (
                await db.execute(
                    select(
                        ExpertiseEvidence.strength,
                        func.count(ExpertiseEvidence.id),
                    ).where(
                        ExpertiseEvidence.organization_id == organization_id,
                        ExpertiseEvidence.skill_id == skill_id,
                        ExpertiseEvidence.occurred_at >= start,
                    ).group_by(ExpertiseEvidence.strength)
                )
            ).all()
        )
        return round(
            sum(
                STRENGTH_WEIGHTS.get(strength, 0.25) * count
                for strength, count in rows
            ),
            2,
        )

    async def _archive_month(
        self, db: AsyncSession, *, organization_id: str, skill_id: str,
        row: OrgCapability,
    ) -> None:
        """Preserve the just-finished month as a CapabilityHistory row."""
        if not row.month_key:
            return
        history = (
            await db.execute(
                select(CapabilityHistory).where(
                    CapabilityHistory.organization_id == organization_id,
                    CapabilityHistory.skill_id == skill_id,
                    CapabilityHistory.month_key == row.month_key,
                )
            )
        ).scalar_one_or_none()
        if history is None:
            history = CapabilityHistory(
                organization_id=organization_id,
                skill_id=skill_id,
                skill_name=row.canonical_name,
                month_key=row.month_key,
            )
            db.add(history)
        history.lifecycle = row.lifecycle
        history.expert_count = row.expert_count
        history.strong_expert_count = row.strong_expert_count
        history.evidence_count = row.evidence_count
        history.capacity_committed = row.capacity_committed
        history.demand_count = row.demand_count
        history.points = row.points_cur_month
        await db.flush()

    def _derive_lifecycle(
        self, *, now: datetime, expert_count: int, strong_count: int,
        evidence_count: int, avg_score: float, latest_at: Optional[datetime],
        first_seen: Optional[datetime], points_cur: float, points_prev: float,
    ) -> str:
        """Deterministic state machine — every transition is evidence-backed."""
        if expert_count == 0:
            return "unknown"
        latest = ensure_aware(latest_at) if latest_at else None
        if latest is None or (now - latest).days > DORMANT_DAYS:
            return "dormant"
        if points_prev > 0 and points_cur < points_prev * DECLINE_FACTOR:
            return "declining"
        if strong_count >= STRATEGIC_MIN_STRONG and evidence_count >= STRATEGIC_MIN_EVIDENCE:
            return "strategic"
        if strong_count >= STRONG_MIN_STRONG or (
            evidence_count >= STRONG_MIN_EVIDENCE and expert_count >= 2
        ):
            return "strong"
        if evidence_count >= ESTABLISHED_MIN_EVIDENCE or expert_count >= 2:
            return "established"
        return "emerging"

    def _explain(self, row: OrgCapability) -> str:
        """One human-readable sentence with the deterministic factors."""
        if row.lifecycle == "unknown":
            return "No evidence-backed experts for this capability yet."
        pieces = [
            f"{row.expert_count} expert(s), {row.evidence_count} evidence item(s)",
            f"{row.corroborated_kinds} evidence kind(s)",
        ]
        if row.outcome_ratio is not None:
            pieces.append(f"outcome ratio {row.outcome_ratio:.2f}")
        if row.latest_evidence_at is not None:
            days = (utcnow() - ensure_aware(row.latest_evidence_at)).days
            pieces.append(f"last evidence {days} day(s) ago")
        base = f"{row.canonical_name} is {row.lifecycle}: " + ", ".join(pieces) + "."
        if row.capacity_state != "unknown":
            base += (
                f" Capacity {row.capacity_state} "
                f"({row.capacity_available} free of {row.capacity_potential} "
                f"expert(s), {row.capacity_committed} committed)."
            )
        if row.demand_count:
            base += f" {row.demand_count} active project(s) demand it."
        return base[:500]

    # ------------------------------------------------------------- project links

    async def _apply_task_event(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> None:
        """task.* -> link the assignee's capabilities to their project.

        Exact-once: the (org, project, skill, source_event_id) key means a
        replayed event never creates a second link. Bounded: at most
        MAX_PERSON_CAPABILITIES skills per event.
        """
        project_id = payload.get("project_id")
        assignee_id = (
            payload.get("assignee_id") or payload.get("reporter_id")
            or payload.get("actor_id")
        )
        if not project_id or not assignee_id:
            return
        skills = list(
            (
                await db.execute(
                    select(ExpertiseState.skill_id).where(
                        ExpertiseState.organization_id == organization_id,
                        ExpertiseState.person_id == assignee_id,
                        ExpertiseState.score > 0,
                    ).limit(MAX_PERSON_CAPABILITIES)
                )
            ).scalars().all()
        )
        if not skills:
            return
        project_name = payload.get("project_name") or ""
        if not project_name:
            from app.models.project import Project

            proj = (
                await db.execute(
                    select(Project.name).where(
                        Project.organization_id == organization_id,
                        Project.id == project_id,
                    )
                )
            ).first()
            project_name = proj[0] if proj else ""
        event_id = getattr(event, "id", None) or str(getattr(event, "name", ""))
        skill_names: dict[str, str] = {}
        for skill in (
            await db.execute(
                select(CanonicalSkill.id, CanonicalSkill.canonical_name).where(
                    CanonicalSkill.organization_id == organization_id,
                    CanonicalSkill.id.in_(skills),
                )
            )
        ).all():
            skill_names[skill[0]] = skill[1]
        for skill_id in skills:
            existing = (
                await db.execute(
                    select(CapabilityProjectLink.id).where(
                        CapabilityProjectLink.organization_id == organization_id,
                        CapabilityProjectLink.project_id == project_id,
                        CapabilityProjectLink.skill_id == skill_id,
                        CapabilityProjectLink.source_event_id == event_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(CapabilityProjectLink(
                organization_id=organization_id,
                project_id=project_id,
                project_name=project_name,
                skill_id=skill_id,
                skill_name=skill_names.get(skill_id, ""),
                source_event_id=event_id,
                status="active",
            ))
            await self.refresh_capability(
                db, organization_id=organization_id, skill_id=skill_id,
                event=event,
            )

    async def _apply_project_event(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> None:
        """project.* -> open/close every link of the project and recompute
        the touched capabilities (bounded by the project's link count)."""
        project_id = payload.get("project_id")
        if not project_id:
            return
        name = getattr(event, "name", "") or payload.get("event_name", "")
        close = name in ("project.completed", "project.cancelled", "project.archived")
        status = "closed" if close else "active"
        links = list(
            (
                await db.execute(
                    select(CapabilityProjectLink).where(
                        CapabilityProjectLink.organization_id == organization_id,
                        CapabilityProjectLink.project_id == project_id,
                    ).limit(MAX_LINKED_PROJECTS)
                )
            ).scalars().all()
        )
        for link in links:
            if link.status != status:
                link.status = status
                await self.refresh_capability(
                    db, organization_id=organization_id, skill_id=link.skill_id,
                    event=event,
                )

    # ------------------------------------------------------------- signals

    async def _reconcile_signals(
        self, db: AsyncSession, *, organization_id: str, row: OrgCapability,
    ) -> None:
        """Deterministic advisory findings, deduplicated per open finding.
        When a finding clears, its open signal is auto-resolved — analysis
        never takes an autonomous organizational action."""
        now = utcnow()
        candidates: list[tuple[str, str, str, list[dict[str, Any]]]] = []
        if row.expert_count >= 2 and row.concentration_share >= CONCENTRATION_WARNING_SHARE:
            severity = (
                "critical" if row.concentration_share >= CONCENTRATION_CRITICAL_SHARE
                else "warning"
            )
            candidates.append((
                "concentration", severity,
                f"{row.concentration_share:.0%} of {row.canonical_name} evidence "
                f"comes from one person (next expert {row.second_share:.0%}).",
                [{"share": row.concentration_share, "next": row.second_share}],
            ))
        if row.expert_count == 1 and row.capacity_committed >= 1:
            candidates.append((
                "single_point_dependency", "critical",
                f"{row.canonical_name} has a single expert who is already "
                f"committed to active work.",
                [{"experts": 1, "committed": row.capacity_committed}],
            ))
        if row.capacity_state == "constrained":
            candidates.append((
                "capacity_constraint", "warning",
                f"Every {row.canonical_name} expert is committed "
                f"({row.capacity_available} free).",
                [{"free": row.capacity_available, "committed": row.capacity_committed}],
            ))
        if row.demand_count > 0 and row.capacity_available == 0:
            candidates.append((
                "capability_gap", "warning",
                f"{row.demand_count} active project(s) demand {row.canonical_name} "
                f"but no expert is free.",
                [{"demand": row.demand_count, "free": 0}],
            ))
        if row.lifecycle == "declining":
            candidates.append((
                "declining", "info",
                f"{row.canonical_name} activity is below its recent history.",
                [{"lifecycle": "declining"}],
            ))
        if row.lifecycle == "emerging" and row.capacity_available == 0:
            candidates.append((
                "emerging_without_capacity", "info",
                f"{row.canonical_name} is emerging but has no free expert.",
                [{"available": 0}],
            ))
        if row.evidence_count >= STRONG_MIN_EVIDENCE and row.capacity_committed == 0:
            candidates.append((
                "expertise_without_capacity", "info",
                f"{row.canonical_name} expertise exists but is not engaged on "
                f"any active project.",
                [{"evidence": row.evidence_count, "committed": 0}],
            ))
        if row.expert_count == 0 and row.demand_count >= 1:
            candidates.append((
                "capacity_without_expertise", "warning",
                f"Active work demands {row.canonical_name} but no evidence-backed "
                f"expert exists.",
                [{"demand": row.demand_count, "experts": 0}],
            ))

        existing = list(
            (
                await db.execute(
                    select(CapabilitySignal).where(
                        CapabilitySignal.organization_id == organization_id,
                        CapabilitySignal.skill_id == row.skill_id,
                        CapabilitySignal.status.in_(("open", "acknowledged")),
                    )
                )
            ).scalars().all()
        )
        by_kind = {s.kind: s for s in existing}
        seen: set[str] = set()
        for kind, severity, detail, evidence in candidates:
            seen.add(kind)
            signal = by_kind.get(kind)
            if signal is None:
                db.add(CapabilitySignal(
                    organization_id=organization_id,
                    skill_id=row.skill_id,
                    skill_name=row.canonical_name,
                    kind=kind,
                    severity=severity,
                    detail=detail,
                    evidence_json=json.dumps(evidence),
                ))
            else:
                signal.severity = severity
                signal.detail = detail
                signal.evidence_json = json.dumps(evidence)
        for signal in existing:
            if signal.kind not in seen:
                signal.status = "resolved"
                signal.resolved_at = now
        await db.flush()

    # ------------------------------------------------------------------ reads

    async def overview(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """The Organizational Capability Center (org-wide callers only)."""
        rows = list(
            (
                await db.execute(
                    select(OrgCapability).where(
                        OrgCapability.organization_id == organization_id,
                    ).order_by(
                        OrgCapability.evidence_count.desc(),
                    ).limit(500)
                )
            ).scalars().all()
        )
        def _brief(r: OrgCapability) -> dict[str, Any]:
            return {
                "skill_id": r.skill_id,
                "name": r.canonical_name,
                "category": r.category,
                "lifecycle": r.lifecycle,
                "confidence": r.confidence,
                "expert_count": r.expert_count,
                "evidence_count": r.evidence_count,
                "capacity_state": r.capacity_state,
                "capacity_potential": r.capacity_potential,
                "capacity_available": r.capacity_available,
                "capacity_committed": r.capacity_committed,
                "capacity_reserved": r.capacity_reserved,
                "demand_state": r.demand_state,
                "demand_count": r.demand_count,
                "concentration_share": r.concentration_share,
                "explain": r.explain,
            }

        by_state: dict[str, int] = {}
        for r in rows:
            by_state[r.lifecycle] = by_state.get(r.lifecycle, 0) + 1
        return {
            "scope_type": "organization",
            "total": len(rows),
            "by_state": by_state,
            "strong": [
                _brief(r) for r in rows
                if r.lifecycle in ("strong", "strategic")
            ][:10],
            "emerging": [
                _brief(r) for r in rows
                if r.lifecycle in ("emerging", "established")
            ][:10],
            "constrained": [
                _brief(r) for r in rows
                if r.capacity_state in ("stretched", "constrained")
                and r.expert_count > 0
            ][:10],
            "concentration_risks": [
                _brief(r) for r in rows
                if r.expert_count >= 2 and r.concentration_share >= CONCENTRATION_WARNING_SHARE
            ][:10],
            "gaps": [
                _brief(r) for r in rows
                if r.demand_count > 0 and r.capacity_available == 0
            ][:10],
            "capabilities": [_brief(r) for r in rows],
        }

    async def capability_detail(
        self, db: AsyncSession, *, organization_id: str, skill_id: str,
    ) -> Optional[dict[str, Any]]:
        """Full evidence-backed detail of one organizational capability."""
        row = (
            await db.execute(
                select(OrgCapability).where(
                    OrgCapability.organization_id == organization_id,
                    OrgCapability.skill_id == skill_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None

        experts = list(
            (
                await db.execute(
                    select(
                        ExpertiseState.person_id,
                        ExpertiseState.score,
                        ExpertiseState.evidence_count,
                        ExpertiseState.lifecycle,
                        ExpertiseState.confidence,
                        ExpertiseState.last_observed,
                    ).where(
                        ExpertiseState.organization_id == organization_id,
                        ExpertiseState.skill_id == skill_id,
                        ExpertiseState.score > 0,
                    ).order_by(
                        ExpertiseState.score.desc(),
                        ExpertiseState.evidence_count.desc(),
                    ).limit(MAX_TOP_EXPERTS)
                )
            ).all()
        )
        expert_ids = [e[0] for e in experts]
        labels: dict[str, str] = {}
        if expert_ids:
            for emp_row in (
                await db.execute(
                    select(
                        Employee.id, Employee.first_name, Employee.last_name,
                    ).where(
                        Employee.organization_id == organization_id,
                        Employee.id.in_(expert_ids),
                    )
                )
            ).all():
                full = " ".join(p for p in (emp_row[1], emp_row[2]) if p)
                labels[emp_row[0]] = full or emp_row[0]

        teams: list[dict[str, str]] = []
        if expert_ids:
            from app.models.team import Team

            team_rows = list(
                (
                    await db.execute(
                        select(
                            Employee.team_id,
                            func.count(func.distinct(Employee.id)),
                        ).where(
                            Employee.organization_id == organization_id,
                            Employee.team_id.isnot(None),
                            Employee.id.in_(expert_ids),
                        ).group_by(Employee.team_id).limit(10)
                    )
                ).all()
            )
            team_ids = [t[0] for t in team_rows]
            team_names: dict[str, str] = {}
            if team_ids:
                for t in (
                    await db.execute(
                        select(Team.id, Team.name).where(Team.id.in_(team_ids))
                    )
                ).all():
                    team_names[t[0]] = t[1]
            teams = [
                {"team_id": tid, "name": team_names.get(tid, tid), "experts": count}
                for tid, count in team_rows
            ]

        owners: list[dict[str, Any]] = []
        if expert_ids:
            from app.models.ownership_intelligence import OwnershipRelationship

            owner_rows = list(
                (
                    await db.execute(
                        select(
                            OwnershipRelationship.owner_id,
                            OwnershipRelationship.object_type,
                            OwnershipRelationship.object_id,
                            OwnershipRelationship.object_name,
                            OwnershipRelationship.responsibility_type,
                        ).where(
                            OwnershipRelationship.organization_id == organization_id,
                            OwnershipRelationship.status == "active",
                            OwnershipRelationship.owner_id.in_(expert_ids),
                        ).order_by(OwnershipRelationship.declared_start.desc())
                        .limit(10)
                    )
                ).all()
            )
            owners = [
                {
                    "owner_id": o[0],
                    "owner_label": labels.get(o[0], o[0]),
                    "object_type": o[1],
                    "object_id": o[2],
                    "object_name": o[3],
                    "responsibility_type": o[4],
                }
                for o in owner_rows
            ]

        projects = [
            {
                "project_id": l.project_id,
                "project_name": l.project_name,
                "status": l.status,
                "first_seen": _iso(l.first_seen),
                "last_seen": _iso(l.last_seen),
            }
            for l in (
                await db.execute(
                    select(CapabilityProjectLink).where(
                        CapabilityProjectLink.organization_id == organization_id,
                        CapabilityProjectLink.skill_id == skill_id,
                    ).order_by(CapabilityProjectLink.last_seen.desc())
                    .limit(MAX_LINKED_PROJECTS)
                )
            ).scalars().all()
        ]

        knowledge: list[dict[str, Any]] = []
        if row.canonical_name:
            from app.models.knowledge import KnowledgeTopic

            knowledge = [
                {
                    "topic_id": t.id,
                    "name": t.name,
                    "category": t.category,
                    "created_by": t.created_by,
                }
                for t in (
                    await db.execute(
                        select(KnowledgeTopic).where(
                            KnowledgeTopic.organization_id == organization_id,
                            KnowledgeTopic.status == "active",
                            KnowledgeTopic.name.ilike(f"%{row.canonical_name}%"),
                        ).limit(MAX_TOP_EXPERTS)
                    )
                ).scalars().all()
            ]

        history = [
            {
                "month": h.month_key,
                "lifecycle": h.lifecycle,
                "expert_count": h.expert_count,
                "strong_expert_count": h.strong_expert_count,
                "evidence_count": h.evidence_count,
                "capacity_committed": h.capacity_committed,
                "demand_count": h.demand_count,
                "points": h.points,
            }
            for h in (
                await db.execute(
                    select(CapabilityHistory).where(
                        CapabilityHistory.organization_id == organization_id,
                        CapabilityHistory.skill_id == skill_id,
                    ).order_by(CapabilityHistory.month_key.desc())
                    .limit(MAX_HISTORY_ROWS)
                )
            ).scalars().all()
        ]

        evidence_by_kind: list[dict[str, Any]] = []
        if row.evidence_count:
            evidence_by_kind = [
                {"kind": k, "count": c}
                for k, c in (
                    await db.execute(
                        select(
                            ExpertiseEvidence.evidence_kind,
                            func.count(ExpertiseEvidence.id),
                        ).where(
                            ExpertiseEvidence.organization_id == organization_id,
                            ExpertiseEvidence.skill_id == skill_id,
                        ).group_by(ExpertiseEvidence.evidence_kind)
                        .order_by(func.count().desc())
                        .limit(8)
                    )
                ).all()
            ]

        signals = [
            {
                "signal_id": s.id,
                "kind": s.kind,
                "severity": s.severity,
                "detail": s.detail,
                "status": s.status,
            }
            for s in (
                await db.execute(
                    select(CapabilitySignal).where(
                        CapabilitySignal.organization_id == organization_id,
                        CapabilitySignal.skill_id == skill_id,
                        CapabilitySignal.status.in_(("open", "acknowledged")),
                    ).order_by(CapabilitySignal.created_at.desc())
                    .limit(MAX_SIGNALS_SHOWN)
                )
            ).scalars().all()
        ]

        # Adjacency: taxonomy neighborhood (parent/children/related/aliases)
        # plus capabilities that SHARE experts with this one — bounded reads.
        adjacent: list[dict[str, Any]] = []
        taxonomy_ids: set[str] = set()
        cs = (
            await db.execute(
                select(CanonicalSkill).where(
                    CanonicalSkill.organization_id == organization_id,
                    CanonicalSkill.id == skill_id,
                )
            )
        ).scalar_one_or_none()
        if cs is not None:
            taxonomy_ids.update(
                x for x in [cs.parent_skill_id] + list(cs.related_skill_ids) if x
            )
            children = list(
                (
                    await db.execute(
                        select(CanonicalSkill.id).where(
                            CanonicalSkill.organization_id == organization_id,
                            CanonicalSkill.parent_skill_id == skill_id,
                        ).limit(20)
                    )
                ).scalars().all()
            )
            taxonomy_ids.update(children)
        shared: dict[str, int] = {}
        if expert_ids:
            for person_id in expert_ids[:MAX_TOP_EXPERTS]:
                for other in (
                    await db.execute(
                        select(ExpertiseState.skill_id).where(
                            ExpertiseState.organization_id == organization_id,
                            ExpertiseState.person_id == person_id,
                            ExpertiseState.score > 0,
                        ).limit(MAX_PERSON_CAPABILITIES)
                    )
                ).scalars().all():
                    if other != skill_id:
                        shared[other] = shared.get(other, 0) + 1
        adjacency_ids = {
            s: c for s, c in shared.items() if c >= 1
        }
        all_adjacent = taxonomy_ids | set(adjacency_ids.keys())
        if all_adjacent:
            adjacent_names = {
                s.id: (s.canonical_name, s.category)
                for s in (
                    await db.execute(
                        select(CanonicalSkill).where(
                            CanonicalSkill.organization_id == organization_id,
                            CanonicalSkill.id.in_(list(all_adjacent)[:40]),
                        )
                    )
                ).scalars().all()
            }
            adjacent = [
                {
                    "skill_id": aid,
                    "name": adjacent_names.get(aid, (aid, None))[0],
                    "category": adjacent_names.get(aid, (aid, None))[1],
                    "shared_experts": adjacency_ids.get(aid, 0),
                }
                for aid in sorted(all_adjacent)[:40]
            ]

        return {
            "skill_id": row.skill_id,
            "name": row.canonical_name,
            "category": row.category,
            "lifecycle": row.lifecycle,
            "confidence": row.confidence,
            "expert_count": row.expert_count,
            "strong_expert_count": row.strong_expert_count,
            "evidence_count": row.evidence_count,
            "corroborated_kinds": row.corroborated_kinds,
            "outcome_ratio": row.outcome_ratio,
            "capacity": {
                "state": row.capacity_state,
                "potential": row.capacity_potential,
                "committed": row.capacity_committed,
                "reserved": row.capacity_reserved,
                "available": row.capacity_available,
            },
            "demand": {
                "state": row.demand_state,
                "count": row.demand_count,
            },
            "concentration": {
                "share": row.concentration_share,
                "second_share": row.second_share,
            },
            "counts": {
                "owners": row.owner_count,
                "teams": row.team_count,
                "knowledge": row.knowledge_count,
            },
            "explain": row.explain,
            "factors": row.factors,
            "experts": [
                {
                    "person_id": e[0],
                    "name": labels.get(e[0], e[0]),
                    "score": e[1],
                    "evidence_count": e[2],
                    "lifecycle": e[3],
                    "confidence": e[4],
                    "last_observed": _iso(e[5]) if e[5] else None,
                }
                for e in experts
            ],
            "teams": teams,
            "owners": owners,
            "projects": projects,
            "knowledge": knowledge,
            "history": history,
            "evidence_by_kind": evidence_by_kind,
            "signals": signals,
            "adjacent": adjacent,
        }

    async def signals(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        rows = list(
            (
                await db.execute(
                    select(CapabilitySignal).where(
                        CapabilitySignal.organization_id == organization_id,
                        CapabilitySignal.status.in_(("open", "acknowledged")),
                    ).order_by(
                        CapabilitySignal.severity.desc(),
                        CapabilitySignal.created_at.desc(),
                    ).limit(100)
                )
            ).scalars().all()
        )
        return {
            "total": len(rows),
            "signals": [
                {
                    "signal_id": s.id,
                    "skill_id": s.skill_id,
                    "skill_name": s.skill_name,
                    "kind": s.kind,
                    "severity": s.severity,
                    "detail": s.detail,
                    "status": s.status,
                    "created_at": _iso(s.created_at),
                }
                for s in rows
            ],
        }

    async def acknowledge_signal(
        self, db: AsyncSession, *, organization_id: str,
        signal_id: str, noted_by: str,
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(CapabilitySignal).where(
                    CapabilitySignal.organization_id == organization_id,
                    CapabilitySignal.id == signal_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.status == "open":
            row.status = "acknowledged"
            row.noted_by = noted_by
            await db.flush()
        return {
            "signal_id": row.id,
            "skill_name": row.skill_name,
            "kind": row.kind,
            "status": row.status,
        }

    async def project_capabilities(
        self, db: AsyncSession, *, organization_id: str, project_id: str,
    ) -> dict[str, Any]:
        """Capabilities evidenced on a project — leak-free for scoped
        callers: names and states, never member counts."""
        links = list(
            (
                await db.execute(
                    select(CapabilityProjectLink).where(
                        CapabilityProjectLink.organization_id == organization_id,
                        CapabilityProjectLink.project_id == project_id,
                    ).order_by(CapabilityProjectLink.last_seen.desc())
                    .limit(MAX_LINKED_PROJECTS)
                )
            ).scalars().all()
        )
        if not links:
            return {"project_id": project_id, "total": 0, "capabilities": []}
        skill_ids = {l.skill_id for l in links}
        states: dict[str, OrgCapability] = {}
        for r in (
            await db.execute(
                select(OrgCapability).where(
                    OrgCapability.organization_id == organization_id,
                    OrgCapability.skill_id.in_(skill_ids),
                )
            )
        ).scalars().all():
            states[r.skill_id] = r
        capabilities = []
        for link in links:
            st = states.get(link.skill_id)
            capabilities.append({
                "skill_id": link.skill_id,
                "skill_name": link.skill_name or (st.canonical_name if st else ""),
                "link_status": link.status,
                "first_seen": _iso(link.first_seen),
                "lifecycle": st.lifecycle if st else "unknown",
                "capacity_state": st.capacity_state if st else "unknown",
                "capacity_available": st.capacity_available if st else 0,
                "demand_state": st.demand_state if st else "none",
            })
        return {
            "project_id": project_id,
            "total": len(capabilities),
            "capabilities": capabilities,
        }

    async def initiative_gap(
        self, db: AsyncSession, *, organization_id: str, question: str,
        access: Any,
    ) -> dict[str, Any]:
        """"Can we take this on?" — deterministic, evidence-backed.

        Resolves the initiative's required capabilities from the canonical
        taxonomy, then reads each capability's stored state and free
        capacity. Ready = proven capability with free experts; partial =
        capability exists but capacity is tight; gap = no evidence or no
        free experts. Never a forecast and never a guarantee.
        """
        from app.people.skill_engine import skill_engine

        await skill_engine.ensure_taxonomy(db, organization_id=organization_id)
        terms = _tokens(question)
        matched = await skill_engine.resolve_candidates(
            db, organization_id=organization_id, terms=terms,
        )
        if not matched:
            return {
                "intent": "capability_gap",
                "total": 0,
                "answers": [],
                "answer": "No required capability in the question resolves to the canonical taxonomy.",
            }
        skill_ids = [s.id for s in matched]
        rows = {
            r.skill_id: r
            for r in (
                await db.execute(
                    select(OrgCapability).where(
                        OrgCapability.organization_id == organization_id,
                        OrgCapability.skill_id.in_(skill_ids),
                    )
                )
            ).scalars().all()
        }
        answers = []
        for skill in matched:
            st = rows.get(skill.id)
            if st is None or st.lifecycle == "unknown":
                answers.append({
                    "skill_id": skill.id,
                    "skill_name": skill.canonical_name,
                    "readiness": "gap",
                    "reason": "no evidence-backed experts",
                    "lifecycle": "unknown",
                })
                continue
            ready = (
                st.capacity_available > 0
                and st.lifecycle in ("strong", "strategic", "established")
            )
            partial = (
                st.capacity_available == 0
                and st.lifecycle not in ("declining", "dormant", "unknown")
            )
            answers.append({
                "skill_id": skill.id,
                "skill_name": skill.canonical_name,
                "readiness": "ready" if ready else ("partial" if partial else "gap"),
                "reason": st.explain,
                "lifecycle": st.lifecycle,
                "capacity_state": st.capacity_state,
                "capacity_available": st.capacity_available,
            })
        ready_count = sum(1 for a in answers if a["readiness"] == "ready")
        gap_count = sum(1 for a in answers if a["readiness"] == "gap")
        if gap_count == 0:
            verdict = (
                f"The organization can take this on: {ready_count} of "
                f"{len(answers)} required capabilities are ready with free experts."
            )
        elif ready_count == 0:
            verdict = (
                f"The organization is NOT ready for this initiative: "
                f"{gap_count} of {len(answers)} required capabilities lack "
                f"evidence-backed experts or free capacity."
            )
        else:
            verdict = (
                f"The organization is partially ready: {ready_count} of "
                f"{len(answers)} required capabilities are ready, "
                f"{gap_count} have gaps or constrained capacity."
            )
        return {
            "intent": "capability_gap",
            "total": len(answers),
            "answers": answers,
            "answer": verdict,
        }


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = ensure_aware(value)
    return value.isoformat()


def _tokens(*parts: Any) -> list[str]:
    tokens: list[str] = []
    for part in parts:
        if not part:
            continue
        text = str(part).lower().replace("_", " ").replace("-", " ")
        tokens.extend(t for t in text.split() if len(t) > 2)
    return tokens


org_capability_engine = OrgCapabilityEngine()
