"""Slice 4F.7 — People Decision Engine (decision intelligence, not automation).

The 4F capstone: given a real organizational decision context, VCOS
understands the relevant people (4F.2 expertise, 4F.3 trust), ownership
(4F.4), collaboration (4F.5), capability and capacity (4F.6) and produces
an evidence-backed recommendation with alternatives, trade-offs, unknowns
and confidence — then a HUMAN decides, acts, and records the outcome which
becomes evidence for the next decision (Decision -> Outcome -> Learning).

The People Intelligence chain (locked by the 4F.7 directive):

    New initiative -> Required capabilities -> 4F.6 capability state
    -> Available people -> 4F.3 trust -> 4F.4 ownership
    -> 4F.5 collaboration -> Capacity -> 4F.7 recommendation

Design rules:
  * NO employee scores. Candidates carry decision-specific evidence:
    skills (which required capabilities they actually match), expertise
    (trusted evidence volume, honest failure counts), availability
    (workload + capability capacity), ownership (4F.4), collaboration
    (4F.5 edges with the context's people), scope, recency, outcomes.
    The Why is a list of evidence bullets, never a number ranking people.
  * Bounded and deterministic: candidate pool capped, reads are indexed
    org-scoped aggregate queries, ordering is stable (ties break on id),
    and every claim in a recommendation maps to a DecisionEvidenceItem.
  * "What if?" is BOUNDED: deltas are computed only against the decision's
    own context (capacity per required capability, ownership conflicts,
    concentration risk, collaboration, workload). Not the 4P engine.
  * HIGH-tier people decisions (hiring, promotion, termination,
    compensation, disciplinary) are REFUSED — they stay entirely under
    human governance. Low/medium produce recommendations only.
  * Lifecycle is human-controlled: detected -> evaluated -> recommended
    -> reviewed -> approved | rejected -> executed -> verified -> outcome.
    Every transition is audit-logged with its actor.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.event_bus import event_bus
from app.intelligence.company_context import CallerAccess
from app.models.collaboration_intelligence import CollaborationRelationship
from app.models.employee import Employee
from app.models.org_capability_intelligence import OrgCapability
from app.models.ownership_intelligence import OwnershipRelationship
from app.models.people_decision import (
    DECISION_TYPES,
    DecisionAudit,
    DecisionCandidate,
    DecisionEvidenceItem,
    DecisionSimulation,
    LIFECYCLE_STATES,
    OUTCOME_STATUSES,
    PeopleDecision,
    RISK_TIERS,
    ROLE_ALTERNATIVE,
    ROLE_EXCLUDED,
    ROLE_RECOMMENDED,
)
from app.models.project import ProjectMember
from app.models.skills_intelligence import (
    CanonicalSkill,
    Expertise as ExpertiseState,
)
from app.models.task import Task
from app.models.team import TeamMember
from app.people.skill_engine import skill_engine

log = logging.getLogger(__name__)

# Bounded evaluation model.
MAX_CANDIDATES = 30
MAX_ALTERNATIVES = 5
MAX_EVIDENCE_ITEMS = 40
MAX_REQUIRED_SKILLS = 8
MAX_SIMS_PER_DECISION = 20
EXPERTISE_PER_SKILL = 10

ACTIVE_TASK_STATUSES = ("todo", "in_progress", "review", "blocked")
ACTIVE_TASK_WEIGHT = {"todo": 0.25, "in_progress": 0.5, "review": 0.5, "blocked": 0.6}

# Decision types -> risk tier (governance model from the directive).
TYPE_TIERS: dict[str, str] = {
    "expertise": "low",
    "stakeholders": "low",
    "staffing": "medium",
    "ownership": "medium",
    "backup_ownership": "medium",
    "capacity": "medium",
    "collaboration": "medium",
    "team_composition": "medium",
    "succession": "medium",
    "capability_gap": "medium",
}

# Types that always produce a person recommendation vs. analyses.
PERSON_TYPES = set(TYPE_TIERS) - {"capability_gap"}

# Lifecycle state machine — transitions a human (or the system for the
# detected -> evaluated -> recommended spine) may take.
TRANSITIONS: dict[str, dict[str, str]] = {
    "detected": {"evaluate": "evaluated", "recommend": "recommended"},
    "evaluated": {"recommend": "recommended"},
    "recommended": {"review": "reviewed"},
    "reviewed": {"approve": "approved", "reject": "rejected"},
    "approved": {"execute": "executed", "reject": "rejected"},
    "rejected": {"reopen": "evaluated"},
    "executed": {"verify": "verified"},
    "verified": {},
}
OUTCOME_ABLE = {"approved", "executed", "verified", "rejected"}


def _grade_expertise(score: float, evidence_count: int) -> str:
    """Deterministic skill-match grade — never a score, a category."""
    if score >= 0.75 and evidence_count >= 5:
        return "strong"
    if score >= 0.5 and evidence_count >= 2:
        return "fit"
    if score > 0:
        return "partial"
    return "weak"


def _availability_grade(workload: float, sole_expert: bool, capacity_state: str) -> str:
    if workload >= 5.0 or (sole_expert and capacity_state == "constrained"):
        return "constrained"
    if workload >= 3.0 or (sole_expert and capacity_state == "stretched"):
        return "stretched"
    return "free"


class PeopleDecisionEngine:
    """Canonical decision reasoning over the 4F evidence substrate."""

    def __init__(self) -> None:
        self.type_tiers = TYPE_TIERS

    # ------------------------------------------------------------------
    # Creation + evaluation
    # ------------------------------------------------------------------
    async def create_and_evaluate(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        actor_id: Optional[str],
        body: dict[str, Any],
    ) -> dict[str, Any]:
        decision_type = str(body.get("decision_type") or "").strip()
        objective = str(body.get("objective") or "").strip()
        if decision_type not in DECISION_TYPES:
            raise ValueError(
                f"decision_type must be one of: {', '.join(DECISION_TYPES)}"
            )
        if not objective:
            raise ValueError("objective is required (the decision context)")

        risk_tier = str(body.get("risk_tier") or "").strip() or TYPE_TIERS[decision_type]
        if risk_tier not in RISK_TIERS:
            raise ValueError("risk_tier must be one of: low, medium, high")
        if risk_tier == "high":
            raise ValueError(
                "High-impact people decisions (hiring, promotion, termination, "
                "compensation, disciplinary) are refused by design: they remain "
                "entirely under human governance. VCOS can only produce evidence "
                "for the people considering them."
            )

        context_type = (body.get("context_type") or None)
        context_id = (body.get("context_id") or None)
        context_label = (body.get("context_label") or None)
        allowed_contexts = ("org", "project", "team", "capability", "system")
        if context_type and context_type not in allowed_contexts:
            raise ValueError(
                f"context_type must be one of: {', '.join(allowed_contexts)}"
            )
        if context_type and context_type != "org" and not context_id:
            raise ValueError("context_id is required when context_type is set")
        if not context_type or context_type == "org":
            context_type = "org"
            if not context_id:
                context_id = ""

        requirements = body.get("requirements") or []
        if isinstance(requirements, str):
            requirements = [requirements]
        if not isinstance(requirements, list) or not all(
            isinstance(r, str) and r.strip() for r in requirements
        ):
            raise ValueError("requirements must be a list of non-empty strings")

        await skill_engine.ensure_taxonomy(db, organization_id=organization_id)
        skills = await self._resolve_skills(db, organization_id, requirements)
        skill_ids = [s["id"] for s in skills]

        now = utcnow()
        decision = PeopleDecision(
            organization_id=organization_id,
            actor_id=actor_id,
            decision_type=decision_type,
            risk_tier=risk_tier,
            context_type=context_type,
            context_id=context_id,
            context_label=context_label,
            objective=objective,
            requirements_json=json.dumps(
                [{"id": s["id"], "name": s["name"]} for s in skills]
            ),
            lifecycle="detected",
        )
        db.add(decision)
        await db.flush()
        await self._audit(db, decision, "detected", actor_id, "decision created")

        evaluation = await self._evaluate(
            db, decision, organization_id, skill_ids, skills
        )

        decision.lifecycle = "recommended"
        decision.recommended_person_id = evaluation["recommended_person_id"]
        decision.recommended_person_label = evaluation["recommended_person_label"]
        decision.confidence = evaluation["confidence"]
        decision.rationale = evaluation["rationale"]
        decision.provenance_json = json.dumps(evaluation["provenance"])
        for row in evaluation["candidates"]:
            db.add(row)
        for item in evaluation["evidence_items"]:
            db.add(item)
        await self._audit(db, decision, "evaluated", actor_id, "evidence gathered")
        await self._audit(db, decision, "recommended", actor_id, "recommendation produced")
        await db.flush()

        view = await self.view(db, organization_id, decision.id)
        return view

    # ------------------------------------------------------------------
    # Dry-run evaluation — the brain's read-only decision surface.
    #
    # Universal Company Brain questions ("who should own this?", "why not
    # Alice?", "what if we assign Bob?") are answered from LIVE analysis
    # over the same canonical evidence WITHOUT creating a decision record:
    # the brain recommends; only the governed decision surface persists
    # (where a human then owns the lifecycle). Every answer still carries
    # its full provenance so "why did VCOS recommend this?" is always
    # reconstructable.
    # ------------------------------------------------------------------
    async def dry_run(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        decision_type: str,
        objective: str,
        requirements: list[str],
        context_type: Optional[str] = None,
        context_id: Optional[str] = None,
        context_label: Optional[str] = None,
    ) -> dict[str, Any]:
        if decision_type == "high" or str(objective) == "":
            raise ValueError("objective is required (the decision context)")
        await skill_engine.ensure_taxonomy(db, organization_id=organization_id)
        skills = await self._resolve_skills(db, organization_id, requirements)
        skill_ids = [s["id"] for s in skills]
        scratch = PeopleDecision(
            organization_id=organization_id,
            decision_type=decision_type,
            risk_tier=TYPE_TIERS.get(decision_type, "medium"),
            context_type=context_type or "org",
            context_id=context_id or "",
            context_label=context_label,
            objective=objective,
            requirements_json=json.dumps(
                [{"id": s["id"], "name": s["name"]} for s in skills]
            ),
        )
        evaluation = await self._evaluate(
            db, scratch, organization_id, skill_ids, skills
        )
        candidates = [
            {
                "person_id": c.person_id,
                "person_label": c.person_label,
                "role": c.role,
                "rank": c.rank,
                "rationale": c.rationale,
                "trade_off": c.trade_off,
                "why_not": c.why_not,
            }
            for c in evaluation["candidates"]
        ]
        return {
            "persisted": False,
            "decision_type": decision_type,
            "requirements": skills,
            "lifecycle": "recommended",
            "recommendation": {
                "person_id": evaluation["recommended_person_id"],
                "person_label": evaluation["recommended_person_label"],
                "confidence": evaluation["confidence"],
                "rationale": evaluation["rationale"],
            },
            "candidates": candidates,
            "provenance": evaluation["provenance"],
        }

    async def dry_what_if(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        primary_person_id: str,
        primary_label: str,
        person_id: str,
        skill_ids: list[str],
    ) -> dict[str, Any]:
        """Bounded what-if against an evaluated primary (no persistence)."""
        deltas = await self._deltas_for(
            db, organization_id, person_id, skill_ids
        )
        verdict = self._what_if_verdict(deltas, primary_label)
        return {"person": deltas["person"], "deltas": deltas, "verdict": verdict}

    async def _resolve_skills(
        self, db: AsyncSession, organization_id: str, requirements: list[str]
    ) -> list[dict[str, str]]:
        """Requirement terms -> canonical skills (bounded, deterministic)."""
        skills: list[dict[str, str]] = []
        seen: set[str] = set()
        for term in requirements[:MAX_REQUIRED_SKILLS * 2]:
            if len(skills) >= MAX_REQUIRED_SKILLS:
                break
            matches = await skill_engine.resolve_candidates(
                db, organization_id=organization_id, terms=[term]
            )
            if not matches:
                continue
            skill = matches[0]
            if skill.id in seen:
                continue
            seen.add(skill.id)
            skills.append({"id": skill.id, "name": skill.canonical_name})
        return skills

    # ------------------------------------------------------------------
    # Core reasoning
    # ------------------------------------------------------------------
    async def _evaluate(
        self,
        db: AsyncSession,
        decision: PeopleDecision,
        organization_id: str,
        skill_ids: list[str],
        skills: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Gather bounded evidence and reason over the candidate pool."""
        pool = await self._candidate_pool(db, organization_id, decision, skill_ids)
        if not pool:
            return self._empty_evaluation(skills)

        people = await self._people(db, organization_id, list(pool.keys()))
        context_member_ids = await self._context_members(db, organization_id, decision)

        expert_rows = (
            (
                await db.execute(
                    select(ExpertiseState).where(
                        ExpertiseState.organization_id == organization_id,
                        ExpertiseState.person_id.in_(list(pool.keys())),
                        ExpertiseState.skill_id.in_(skill_ids),
                        ExpertiseState.score > 0,
                    )
                )
            )
            .scalars()
            .all()
        )
        expertise_by_person: dict[str, list[Any]] = {}
        sole_experts: dict[str, str] = {}
        for row in expert_rows:
            expertise_by_person.setdefault(row.person_id, []).append(row)
        # Sole-expert detection per required skill (concentration input).
        if skill_ids:
            skill_counts = (
                (
                    await db.execute(
                        select(ExpertiseState.skill_id, func.count())
                        .where(
                            ExpertiseState.organization_id == organization_id,
                            ExpertiseState.skill_id.in_(skill_ids),
                            ExpertiseState.score > 0,
                        )
                        .group_by(ExpertiseState.skill_id)
                    )
                )
                .all()
            )
            counts = {sid: n for sid, n in skill_counts}
            for person_id, rows in expertise_by_person.items():
                for row in rows:
                    if counts.get(row.skill_id) == 1:
                        sole_experts.setdefault(row.skill_id, person_id)

        ownership_rows = (
            (
                await db.execute(
                    select(OwnershipRelationship).where(
                        OwnershipRelationship.organization_id == organization_id,
                        OwnershipRelationship.owner_id.in_(list(pool.keys())),
                        OwnershipRelationship.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        ownership_by_person: dict[str, list[Any]] = {}
        for row in ownership_rows:
            ownership_by_person.setdefault(row.owner_id, []).append(row)

        workload_rows = (
            (
                await db.execute(
                    select(Task.assignee_id, func.count().label("n"))
                    .where(
                        Task.organization_id == organization_id,
                        Task.assignee_id.in_(list(pool.keys())),
                        Task.status.in_(ACTIVE_TASK_STATUSES),
                    )
                    .group_by(Task.assignee_id)
                )
            )
            .all()
        )
        workload = {row.assignee_id: int(row.n) for row in workload_rows}

        capability_rows = (
            (
                await db.execute(
                    select(OrgCapability).where(
                        OrgCapability.organization_id == organization_id,
                        OrgCapability.skill_id.in_(skill_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        capability_by_skill = {row.skill_id: row for row in capability_rows}

        collab_rows = (
            (
                await db.execute(
                    select(CollaborationRelationship).where(
                        CollaborationRelationship.organization_id == organization_id,
                        CollaborationRelationship.scope_type == "org",
                        or_(
                            CollaborationRelationship.person_a_id.in_(list(pool.keys())),
                            CollaborationRelationship.person_b_id.in_(list(pool.keys())),
                        ),
                        CollaborationRelationship.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        collab_by_person: dict[str, list[Any]] = {}
        for row in collab_rows:
            collab_by_person.setdefault(row.person_a_id, []).append(row)
            collab_by_person.setdefault(row.person_b_id, []).append(row)

        outcome_counts = await self._outcome_history(
            db, organization_id, list(pool.keys())
        )

        # Candidates who hold the decision's own context object.
        owns_context: set[str] = set()
        if decision.context_type and decision.context_id:
            ctx_rows = (
                (
                    await db.execute(
                        select(OwnershipRelationship).where(
                            OwnershipRelationship.organization_id == organization_id,
                            OwnershipRelationship.object_type == decision.context_type,
                            OwnershipRelationship.object_id == decision.context_id,
                            OwnershipRelationship.status == "active",
                        )
                    )
                )
                .scalars()
                .all()
            )
            owns_context = {r.owner_id for r in ctx_rows}

        now = utcnow()
        verdicts: list[dict[str, Any]] = []
        for person_id, person in people.items():
            expertise = expertise_by_person.get(person_id, [])
            matched: dict[str, Any] = {}
            for row in expertise:
                matched[row.skill_id] = {
                    "score": round(float(row.score), 3),
                    "evidence_count": int(row.evidence_count or 0),
                    "successful_count": int(row.successful_count or 0),
                    "failed_count": int(row.failed_count or 0),
                    "lifecycle": row.lifecycle,
                    "last_observed": row.last_observed.isoformat() if row.last_observed else None,
                    "grade": _grade_expertise(
                        float(row.score), int(row.evidence_count or 0)
                    ),
                }

            matched_ids = list(matched.keys())
            strong_ids = [k for k, v in matched.items() if v["grade"] == "strong"]
            fit_ids = [k for k, v in matched.items() if v["grade"] in ("strong", "fit")]
            evidence_total = sum(v["evidence_count"] for v in matched.values())
            failed_total = sum(v["failed_count"] for v in matched.values())

            ownership = ownership_by_person.get(person_id, [])
            critical = [
                r
                for r in ownership
                if r.object_type in ("capability", "system", "project")
                and r.object_type != decision.context_type
            ]
            collab = collab_by_person.get(person_id, [])
            peer_strengths = [
                float(r.strength or 0.0)
                for r in collab
                if r.person_a_id in context_member_ids
                or r.person_b_id in context_member_ids
            ]
            max_collab = max(peer_strengths) if peer_strengths else 0.0

            workload_value = workload.get(person_id, 0)
            sole_any = any(sole_experts.get(sid) == person_id for sid in matched_ids)
            caps = [capability_by_skill.get(sid) for sid in matched_ids]
            cap_states = [c.capacity_state for c in caps if c]
            cap_state = "available" if cap_states else "unknown"
            if "constrained" in cap_states:
                cap_state = "constrained"
            elif "stretched" in cap_states:
                cap_state = "stretched"

            recency = max(
                (
                    v["last_observed"]
                    for v in matched.values()
                    if v["last_observed"]
                ),
                default=None,
            )
            if recency is None:
                recency_grade = "unknown"
            else:
                days = (now - ensure_aware(
                    datetime.fromisoformat(recency)
                )).days
                recency_grade = "current" if days <= 180 else ("stale" if days <= 365 else "dormant")

            success, fail = outcome_counts.get(person_id, (0, 0))
            outcome_note = (
                f"{success} successful, {fail} unsuccessful prior "
                f"recommendations" if success or fail else "no prior decisions"
            )

            availability = _availability_grade(
                workload_value, any(sole_experts.get(sid) == person_id for sid in matched_ids),
                cap_state,
            )
            scope_note = self._scope_note(person, context_member_ids, decision)

            verdicts.append(
                {
                    "person_id": person_id,
                    "person_label": person["name"],
                    "team_id": person["team_id"],
                    "skills": {
                        "matched": matched_ids,
                        "strong": strong_ids,
                        "fit": fit_ids,
                        "required": skill_ids,
                        "details": matched,
                    },
                    "expertise": {
                        "grade": (
                            "strong"
                            if len(strong_ids) >= max(1, len(skill_ids) // 2)
                            else "fit" if fit_ids else "partial" if matched_ids else "weak"
                        ),
                        "evidence_total": evidence_total,
                        "failed": failed_total,
                        "lifecycle": [matched[sid]["lifecycle"] for sid in matched_ids],
                        "recency": recency_grade,
                    },
                    "availability": {
                        "grade": availability,
                        "workload": workload_value,
                        "capacity_state": cap_state,
                        "sole_expert": any(
                            sole_experts.get(sid) == person_id for sid in matched_ids
                        ),
                    },
                    "ownership": {
                        "active": len(ownership),
                        "critical": [r.object_id for r in critical],
                        "owns_context": person_id in owns_context,
                    },
                    "collaboration": {
                        "grade": (
                            "strong" if max_collab >= 0.7
                            else "fit" if max_collab >= 0.4
                            else "partial" if max_collab > 0 else "none"
                        ),
                        "strength": round(max_collab, 3),
                        "peers": len(peer_strengths),
                    },
                    "outcomes": {"successful": success, "unsuccessful": fail, "note": outcome_note},
                    "scope": {"note": scope_note},
                }
            )

        evaluation = self._rank_and_select(
            verdicts, skills, decision_type=decision.decision_type,
            organization_id=organization_id, decision_id=decision.id,
        )
        evaluation["evidence_items"] = self._build_evidence_items(
            db, decision, evaluation["candidates"], skills
        )
        evaluation["provenance"] = self._build_provenance(
            decision, skills, evaluation
        )
        return evaluation

    def _empty_evaluation(self, skills: list[dict[str, str]]) -> dict[str, Any]:
        gap_names = ", ".join(s["name"] for s in skills) or "no requirements matched"
        return {
            "recommended_person_id": None,
            "recommended_person_label": None,
            "confidence": 0.0,
            "rationale": (
                f"No people found with evidence in the required capabilities "
                f"({gap_names}). This is itself organizational evidence: the "
                f"capability gap is real, or the capability is new."
            ),
            "candidates": [],
            "evidence_items": [],
            "provenance": {
                "request": {"requirements": skills},
                "chain": ["4F.2 expertise", "4F.6 capability & capacity"],
                "constraints": ["empty candidate pool — no recommendation possible"],
                "recommendation": None,
            },
        }

    async def _candidate_pool(
        self,
        db: AsyncSession,
        organization_id: str,
        decision: PeopleDecision,
        skill_ids: list[str],
    ) -> dict[str, int]:
        """Bounded candidate discovery: experts + context people."""
        pool: dict[str, int] = {}
        if skill_ids:
            rows = (
                (
                    await db.execute(
                        select(ExpertiseState.person_id)
                        .where(
                            ExpertiseState.organization_id == organization_id,
                            ExpertiseState.skill_id.in_(skill_ids),
                            ExpertiseState.score > 0,
                        )
                        .order_by(ExpertiseState.score.desc())
                        .limit(EXPERTISE_PER_SKILL * len(skill_ids))
                    )
                )
                .scalars()
                .all()
            )
            for pid in rows:
                pool[pid] = pool.get(pid, 0) + 1

        if decision.context_type in ("project", "team") and decision.context_id:
            members = await self._context_members(db, organization_id, decision)
            for pid in members:
                pool[pid] = pool.get(pid, 0) + 2

        ordered = sorted(pool.items(), key=lambda kv: (-kv[1], kv[0]))
        return dict(ordered[:MAX_CANDIDATES])

    async def _people(
        self, db: AsyncSession, organization_id: str, person_ids: list[str]
    ) -> dict[str, Any]:
        if not person_ids:
            return {}
        rows = (
            (
                await db.execute(
                    select(Employee).where(
                        Employee.organization_id == organization_id,
                        Employee.id.in_(person_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            r.id: {
                "id": r.id,
                "name": r.full_name or r.display_name or r.first_name,
                "team_id": r.team_id,
                "email": r.email,
            }
            for r in rows
        }

    async def _context_members(
        self, db: AsyncSession, organization_id: str, decision: PeopleDecision
    ) -> set[str]:
        if not decision.context_type or not decision.context_id:
            return set()
        if decision.context_type == "project":
            rows = (
                (
                    await db.execute(
                        select(ProjectMember.employee_id).where(
                            ProjectMember.organization_id == organization_id,
                            ProjectMember.project_id == decision.context_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            return set(rows)
        if decision.context_type == "team":
            rows = (
                (
                    await db.execute(
                        select(TeamMember.employee_id).where(
                            TeamMember.organization_id == organization_id,
                            TeamMember.team_id == decision.context_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            return set(rows)
        return set()

    def _scope_note(
        self,
        person: dict[str, Any],
        context_member_ids: set[str],
        decision: PeopleDecision,
    ) -> str:
        if decision.context_type == "project" and decision.context_id:
            if person["id"] in context_member_ids:
                return "already involved in this project"
            return "not currently on this project"
        if decision.context_type == "team" and decision.context_id:
            if person["team_id"] == decision.context_id:
                return "inside the team"
            return "outside the team"
        return "organizational scope"

    async def _outcome_history(
        self, db: AsyncSession, organization_id: str, person_ids: list[str]
    ) -> dict[str, tuple[int, int]]:
        """Decision -> Outcome -> Learning: prior recommendation outcomes."""
        if not person_ids:
            return {}
        rows = (
            (
                await db.execute(
                    select(
                        PeopleDecision.recommended_person_id,
                        PeopleDecision.outcome_status,
                        func.count(),
                    )
                    .where(
                        PeopleDecision.organization_id == organization_id,
                        PeopleDecision.recommended_person_id.in_(person_ids),
                        PeopleDecision.outcome_status.isnot(None),
                    )
                    .group_by(
                        PeopleDecision.recommended_person_id,
                        PeopleDecision.outcome_status,
                    )
                )
            )
            .all()
        )
        result: dict[str, tuple[int, int]] = {}
        for pid, status, n in rows:
            success, fail = result.get(pid, (0, 0))
            if status == "successful":
                success += int(n)
            elif status == "unsuccessful":
                fail += int(n)
            result[pid] = (success, fail)
        return result

    # ------------------------------------------------------------------
    # Ranking — decision-specific, explainable, NEVER a score ranking.
    # ------------------------------------------------------------------
    def _rank_and_select(
        self,
        verdicts: list[dict[str, Any]],
        skills: list[dict[str, str]],
        *,
        decision_type: str,
        organization_id: str,
        decision_id: str,
    ) -> dict[str, Any]:
        required = len(skills)
        for v in verdicts:
            matched = v["skills"]["fit"]
            v["fit_fraction"] = len(matched) / max(1, required)
            v["evidence_total"] = v["expertise"]["evidence_total"]

        if decision_type == "capability_gap":
            return self._capability_gap_evaluation(verdicts, skills)

        # Decision-specific eligibility: who is REALLY on the table.
        eligible: list[dict[str, Any]] = []
        if decision_type in ("expertise", "stakeholders"):
            # Information retrieval: strength wins, availability does not bar.
            eligible = [
                v for v in verdicts if v["skills"]["matched"]
            ]
        else:
            for v in verdicts:
                if not v["skills"]["matched"]:
                    continue
                if v["availability"]["grade"] == "constrained":
                    continue
                if v["ownership"]["critical"] and not v["ownership"]["owns_context"]:
                    continue
                eligible.append(v)
        eligible.sort(
            key=lambda v: (
                v["fit_fraction"],
                v["expertise"]["grade"] == "strong",
                min(v["evidence_total"], 9999),
                -v["availability"]["workload"],
                v["person_id"],
            ),
            reverse=True,
        )

        if not eligible:
            return self._finalize_selection(
                [], skills, organization_id=organization_id,
                decision_id=decision_id, all_verdicts=verdicts,
            )

        return self._finalize_selection(
            eligible[:1 + MAX_ALTERNATIVES], skills,
            organization_id=organization_id, decision_id=decision_id,
            all_verdicts=verdicts,
        )

    def _capability_gap_evaluation(
        self, verdicts: list[dict[str, Any]], skills: list[dict[str, str]]
    ) -> dict[str, Any]:
        """The recommendation here is the GAP, not a person."""
        names = [s["name"] for s in skills]
        return {
            "recommended_person_id": None,
            "recommended_person_label": None,
            "confidence": 0.0,
            "rationale": (
                f"The capability analysis for {', '.join(names)} is the finding: "
                f"{len(verdicts)} people hold evidence. Use the capability "
                f"surface for capacity/demand; the decision surface for who can "
                f"be grown or moved."
            ),
            "candidates": [],
            "evidence_items": [],
        }

    def _finalize_selection(
        self,
        ordered: list[dict[str, Any]],
        skills: list[dict[str, str]],
        *,
        organization_id: str,
        decision_id: str,
        all_verdicts: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Build candidates with WHY / trade-offs / why-not from evidence."""
        if not ordered:
            return self._empty_evaluation(skills)

        primary = ordered[0]
        candidates: list[DecisionCandidate] = []
        required = len(skills)

        def _why_lines(v: dict[str, Any]) -> list[str]:
            lines: list[str] = []
            for sid in v["skills"]["fit"]:
                d = v["skills"]["details"][sid]
                outcome = (
                    f" ({d['successful_count']} successful, {d['failed_count']} "
                    f"unsuccessful outcomes)"
                    if d["failed_count"] or d["successful_count"]
                    else ""
                )
                lines.append(
                    f"{d['grade']} match on a required capability with "
                    f"{d['evidence_count']} trusted evidence{outcome}"
                )
            if v["availability"]["grade"] != "constrained":
                lines.append(
                    f"available — {v['availability']['workload']} active tasks, "
                    f"capability state {v['availability']['capacity_state']}"
                )
            if v["collaboration"]["grade"] != "none":
                lines.append(
                    f"collaboration strength {v['collaboration']['strength']} "
                    f"with {v['collaboration']['peers']} people in this context"
                )
            if v["ownership"]["owns_context"]:
                lines.append("currently owns this context object (continuity)")
            if v["outcomes"]["successful"] or v["outcomes"]["unsuccessful"]:
                lines.append(
                    f"prior recommendation outcomes: {v['outcomes']['note']}"
                )
            if v["expertise"]["recency"] == "current":
                lines.append("expertise is current")
            if not lines:
                lines.append("no positive evidence in the required capabilities")
            return lines

        def _negative_lines(v: dict[str, Any]) -> list[str]:
            lines: list[str] = []
            if not v["skills"]["matched"]:
                lines.append("no evidence in the required capabilities")
            if v["availability"]["grade"] == "constrained":
                lines.append(
                    f"carrying {v['availability']['workload']} active tasks "
                    f"(capacity constrained)"
                )
            if v["availability"]["sole_expert"] and v["availability"]["grade"] != "free":
                lines.append("is the sole expert on a capability in demand")
            if v["ownership"]["critical"]:
                lines.append(
                    f"holds {len(v['ownership']['critical'])} critical "
                    f"responsibilities that would be put at risk"
                )
            if v["expertise"]["failed"]:
                lines.append(
                    f"{v['expertise']['failed']} unsuccessful outcomes recorded "
                    f"in their expertise history"
                )
            if v["expertise"]["recency"] == "dormant":
                lines.append("expertise has not been observed recently")
            if v["collaboration"]["grade"] == "none" and required:
                lines.append("no collaboration evidence in this context")
            return lines or ["no disqualifying evidence"]

        for rank, v in enumerate(ordered):
            person = v["person_id"]
            label = v["person_label"]
            if rank == 0:
                role = ROLE_RECOMMENDED
                why = "; ".join(_why_lines(v))
                candidates.append(
                    DecisionCandidate(
                        organization_id=organization_id,
                        decision_id=decision_id,
                        person_id=person,
                        person_label=label,
                        role=role,
                        rank=rank,
                        evidence_json=json.dumps(v["skills"], default=str),
                        rationale=why,
                    )
                )
            else:
                role = ROLE_ALTERNATIVE
                primary_lines = _why_lines(ordered[0])
                alt_lines = _why_lines(v)
                trade = (
                    f"Primary is {ordered[0]['person_label']}: "
                    f"{primary_lines[0] if primary_lines else 'no positive evidence'} — "
                    f"this alternative offers: "
                    f"{alt_lines[0] if alt_lines else 'no positive evidence'}."
                )
                candidates.append(
                    DecisionCandidate(
                        organization_id=organization_id,
                        decision_id=decision_id,
                        person_id=person,
                        person_label=label,
                        role=role,
                        rank=rank,
                        evidence_json=json.dumps(v["skills"], default=str),
                        rationale="; ".join(alt_lines),
                        trade_off=trade,
                        why_not="; ".join(_negative_lines(v)),
                    )
                )

        # Excluded: everyone else in the pool, with honest why-not.
        if all_verdicts:
            included = {v["person_id"] for v in ordered}
            excluded = [v for v in all_verdicts if v["person_id"] not in included]
            excluded.sort(
                key=lambda v: (-v["fit_fraction"], v["person_id"])
            )
            for v in excluded:
                candidates.append(
                    DecisionCandidate(
                        organization_id=organization_id,
                        decision_id=decision_id,
                        person_id=v["person_id"],
                        person_label=v["person_label"],
                        role=ROLE_EXCLUDED,
                        rank=len(candidates),
                        evidence_json=json.dumps(v["skills"], default=str),
                        why_not="; ".join(_negative_lines(v)),
                    )
                )

        evidence_total = primary["evidence_total"]
        fit_fraction = primary["fit_fraction"]
        confidence = round(
            0.25 + 0.75 * fit_fraction * min(1.0, evidence_total / 12.0),
            3,
        )
        confidence = min(1.0, max(0.0, confidence))

        return {
            "recommended_person_id": primary["person_id"],
            "recommended_person_label": primary["person_label"],
            "confidence": confidence,
            "rationale": (
                f"{primary['person_label']} is recommended because "
                + "; ".join(_why_lines(primary))
                + f". Confidence {confidence} (fit fraction {fit_fraction:.2f} "
                f"over {required} required capabilities, {evidence_total} "
                f"trusted evidence points)."
            ),
            "candidates": candidates,
            "evidence_items": [],
        }

    def _build_evidence_items(
        self,
        db: AsyncSession,
        decision: PeopleDecision,
        candidates: list[DecisionCandidate],
        skills: list[dict[str, str]],
    ) -> list[DecisionEvidenceItem]:
        """Materialize the top claims behind the recommendation."""
        skill_names = {s["id"]: s["name"] for s in skills}
        items: list[DecisionEvidenceItem] = []
        counter = 0
        for cand in candidates[: MAX_EVIDENCE_ITEMS // 2]:
            if cand.role == ROLE_EXCLUDED:
                continue
            try:
                evidence = json.loads(cand.evidence_json or "{}")
            except Exception:
                evidence = {}
            for sid, detail in (evidence.get("details") or {}).items():
                if counter >= MAX_EVIDENCE_ITEMS:
                    break
                items.append(
                    DecisionEvidenceItem(
                        organization_id=decision.organization_id,
                        decision_id=decision.id,
                        person_id=cand.person_id,
                        dimension="expertise",
                        source_type="expertise",
                        source_id=sid,
                        source_title=skill_names.get(sid, ""),
                        claim=(
                            f"{cand.person_label} holds {detail.get('evidence_count')} "
                            f"trusted evidence on {skill_names.get(sid, 'a required capability')} "
                            f"(grade {detail.get('grade')}, "
                            f"{detail.get('successful_count')} successful, "
                            f"{detail.get('failed_count')} unsuccessful outcomes)"
                        ),
                        points=1.0 if detail.get("failed_count", 0) == 0 else -1.0,
                        occurred_at=(
                            ensure_aware(datetime.fromisoformat(detail["last_observed"]))
                            if detail.get("last_observed")
                            else None
                        ),
                    )
                )
                counter += 1
        return items[:MAX_EVIDENCE_ITEMS]

    def _build_provenance(
        self,
        decision: PeopleDecision,
        skills: list[dict[str, str]],
        evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "request": {
                "objective": decision.objective,
                "decision_type": decision.decision_type,
                "risk_tier": decision.risk_tier,
                "requirements": skills,
            },
            "context": {
                "context_type": decision.context_type,
                "context_id": decision.context_id,
                "context_label": decision.context_label,
            },
            "chain": [
                "4F.2 expertise (skill match)",
                "4F.3 trust (evidence volume, honest failures)",
                "4F.4 ownership (responsibilities, continuity)",
                "4F.5 collaboration (edges with this context)",
                "4F.6 capability & capacity (demand, concentration, availability)",
                "4F.7 people decision (this recommendation)",
            ],
            "constraints": [
                "no employee scores — decision-specific evidence only",
                "capacity constrained people are excluded unless they own the context",
                "critical owners are excluded unless the decision is about their object",
                "HIGH-tier people decisions are refused by design (human governance)",
            ],
            "confidence_formula": "0.25 + 0.75 * fit_fraction * min(1, evidence_total / 12)",
            "recommendation": {
                "person_id": evaluation["recommended_person_id"],
                "person_label": evaluation["recommended_person_label"],
            },
            "created_at": utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # Lifecycle — human-governed state machine.
    # ------------------------------------------------------------------
    async def transition(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        decision_id: str,
        action: str,
        actor_id: Optional[str],
    ) -> dict[str, Any]:
        decision = await self._get(db, organization_id, decision_id)
        if not decision:
            raise LookupError("decision not found")
        allowed = TRANSITIONS.get(decision.lifecycle, {})
        if action not in allowed:
            raise ValueError(
                f"cannot {action} from lifecycle '{decision.lifecycle}' "
                f"(allowed: {', '.join(allowed) or 'none'})"
            )
        decision.lifecycle = allowed[action]
        now = utcnow()
        if action == "approve":
            decision.decided_by = actor_id
            decision.decided_at = now
        elif action == "reject":
            decision.decided_by = actor_id
            decision.decided_at = now
        elif action == "execute":
            decision.executed_by = actor_id
            decision.executed_at = now
        elif action == "verify":
            decision.verified_by = actor_id
            decision.verified_at = now
        await self._audit(db, decision, action, actor_id, None)
        await db.flush()
        if action == "approve":
            await event_bus.publish(
                db,
                name="decision.recommendation.approved",
                organization_id=organization_id,
                actor_id=actor_id,
                payload={
                    "decision_id": decision.id,
                    "decision_type": decision.decision_type,
                    "context_type": decision.context_type,
                    "context_id": decision.context_id,
                    "person_id": decision.recommended_person_id,
                    "person_label": decision.recommended_person_label,
                },
            )
        elif action == "reject":
            await event_bus.publish(
                db,
                name="decision.recommendation.rejected",
                organization_id=organization_id,
                actor_id=actor_id,
                payload={
                    "decision_id": decision.id,
                    "decision_type": decision.decision_type,
                    "context_type": decision.context_type,
                    "context_id": decision.context_id,
                    "person_id": decision.recommended_person_id,
                    "person_label": decision.recommended_person_label,
                },
            )
        return await self.view(db, organization_id, decision.id)

    async def record_outcome(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        decision_id: str,
        status: str,
        note: Optional[str],
        actor_id: Optional[str],
    ) -> dict[str, Any]:
        if status not in OUTCOME_STATUSES:
            raise ValueError("outcome status must be one of: successful, unsuccessful, partial, unknown")
        decision = await self._get(db, organization_id, decision_id)
        if not decision:
            raise LookupError("decision not found")
        if decision.lifecycle not in OUTCOME_ABLE:
            raise ValueError(
                "outcome can only be recorded for approved, executed, verified "
                f"or rejected decisions (lifecycle is '{decision.lifecycle}')"
            )
        decision.outcome_status = status
        decision.outcome_note = note
        decision.outcome_recorded_by = actor_id
        decision.outcome_recorded_at = utcnow()
        decision.lifecycle = "outcome"
        await self._audit(db, decision, "outcome", actor_id, note)
        await db.flush()
        await event_bus.publish(
            db,
            name="decision.analyzed",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={
                "decision_id": decision.id,
                "decision_type": decision.decision_type,
                "status": status,
                "note": note,
                "person_id": decision.recommended_person_id,
                "person_label": decision.recommended_person_label,
            },
        )
        return await self.view(db, organization_id, decision.id)

    # ------------------------------------------------------------------
    # Bounded "what if?" — decision-context deltas, not prediction.
    # ------------------------------------------------------------------
    async def _deltas_for(
        self,
        db: AsyncSession,
        organization_id: str,
        person_id: str,
        skill_ids: list[str],
    ) -> dict[str, Any]:
        """The bounded delta model for one person against a decision's
        required capabilities: expertise match, per-capability availability,
        concentration, workload, ownership conflicts. Never org-wide."""
        people = await self._people(db, organization_id, [person_id])
        label = (people.get(person_id) or {}).get("name") or person_id
        deltas: dict[str, Any] = {"person": {"name": label, "id": person_id}}

        expert_rows = (
            (
                await db.execute(
                    select(ExpertiseState).where(
                        ExpertiseState.organization_id == organization_id,
                        ExpertiseState.person_id == person_id,
                        ExpertiseState.skill_id.in_(skill_ids),
                        ExpertiseState.score > 0,
                    )
                )
            )
            .scalars()
            .all()
        )
        matched = {r.skill_id: r for r in expert_rows}
        if expert_rows:
            name_rows = (
                (
                    await db.execute(
                        select(CanonicalSkill.id, CanonicalSkill.canonical_name)
                        .where(CanonicalSkill.id.in_(list(matched)))
                    )
                )
                .all()
            )
            skill_names = {sid: (cname or sid) for sid, cname in name_rows}
        else:
            skill_names = {}
        deltas["expertise"] = {
            "required_capabilities": len(skill_ids),
            "matched": len(matched),
        }

        cap_deltas: list[dict[str, Any]] = []
        for row in expert_rows:
            cap = (
                (
                    await db.execute(
                        select(OrgCapability).where(
                            OrgCapability.organization_id == organization_id,
                            OrgCapability.skill_id == row.skill_id,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if cap is None:
                continue
            after = max(0, int(cap.capacity_available or 0) - 1)
            cap_deltas.append(
                {
                    "capability": skill_names.get(row.skill_id, row.skill_id),
                    "capacity_available": int(cap.capacity_available or 0),
                    "after": after,
                    "capacity_state": cap.capacity_state,
                    "after_state": (
                        "constrained" if after == 0
                        else "stretched" if after <= 1
                        else "available"
                    ),
                }
            )
        deltas["capacity"] = cap_deltas

        sole = (
            (
                await db.execute(
                    select(func.count())
                    .select_from(ExpertiseState)
                    .where(
                        ExpertiseState.organization_id == organization_id,
                        ExpertiseState.skill_id.in_(skill_ids),
                        ExpertiseState.score > 0,
                    )
                )
            )
            .scalar()
        )
        deltas["concentration"] = {
            "sole_expert": bool(expert_rows) and int(sole or 0) == 1
        }

        workload = (
            (
                await db.execute(
                    select(func.count()).select_from(Task).where(
                        Task.organization_id == organization_id,
                        Task.assignee_id == person_id,
                        Task.status.in_(ACTIVE_TASK_STATUSES),
                    )
                )
            )
            .scalar()
        )
        deltas["workload"] = int(workload or 0)

        owned = (
            (
                await db.execute(
                    select(OwnershipRelationship).where(
                        OwnershipRelationship.organization_id == organization_id,
                        OwnershipRelationship.owner_id == person_id,
                        OwnershipRelationship.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        deltas["ownership"] = {
            "active": len(owned),
            "critical": [
                {
                    "object_type": r.object_type,
                    "object_id": r.object_id,
                }
                for r in owned
                if r.object_type in ("capability", "system", "project")
            ],
        }
        return deltas

    async def what_if(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        decision_id: str,
        person_id: str,
    ) -> dict[str, Any]:
        decision = await self._get(db, organization_id, decision_id)
        if not decision:
            raise LookupError("decision not found")
        if not decision.recommended_person_id:
            raise ValueError("this decision has no person recommendation to compare against")
        if person_id == decision.recommended_person_id:
            raise ValueError(
                "the recommended person cannot be simulated against themselves"
            )

        try:
            requirements = json.loads(decision.requirements_json or "[]")
        except Exception:
            requirements = []
        skill_ids = [r["id"] for r in requirements]

        people = await self._people(db, organization_id, [person_id])
        if person_id not in people:
            raise LookupError("person not found in this organization")
        label = people[person_id]["name"]

        baseline = decision.recommended_person_label or "the primary"
        deltas = await self._deltas_for(
            db, organization_id, person_id, skill_ids
        )

        verdict = self._what_if_verdict(deltas, baseline)
        sim = DecisionSimulation(
            organization_id=organization_id,
            decision_id=decision.id,
            person_id=person_id,
            person_label=label,
            deltas_json=json.dumps(deltas, default=str),
            verdict=verdict,
        )
        db.add(sim)
        # Bounded: keep the most recent MAX_SIMS_PER_DECISION runs.
        existing = (
            (
                await db.execute(
                    select(DecisionSimulation.id)
                    .where(DecisionSimulation.decision_id == decision.id)
                    .order_by(DecisionSimulation.created_at.desc())
                    .offset(MAX_SIMS_PER_DECISION)
                )
            )
            .scalars()
            .all()
        )
        if existing:
            from sqlalchemy import delete

            await db.execute(
                delete(DecisionSimulation).where(DecisionSimulation.id.in_(existing))
            )
        await db.flush()
        return {"person": {"id": person_id, "name": label}, "deltas": deltas, "verdict": verdict}

    def _what_if_verdict(self, deltas: dict[str, Any], baseline: str) -> str:
        name = deltas["person"]["name"]
        parts: list[str] = []
        if deltas["capacity"]:
            risky = [d for d in deltas["capacity"] if d["after_state"] == "constrained"]
            parts.append(
                f"{name} matches {deltas['expertise']['matched']} of "
                f"{deltas['expertise']['required_capabilities']} required "
                f"capabilities"
            )
            if risky:
                parts.append(
                    "creates a capacity constraint on "
                    + ", ".join(d["capability"] for d in risky)
                )
            else:
                parts.append(
                    "keeps capability availability positive "
                    f"({len(deltas['capacity'])} free expert seats remain)"
                )
        else:
            parts.append(
                f"{name} does not currently hold expertise in the required capabilities"
            )
        if deltas["concentration"]["sole_expert"]:
            parts.append("would further concentrate expertise (sole expert risk)")
        if deltas["workload"] >= 5:
            parts.append(f"carries {deltas['workload']} active tasks (busy)")
        if deltas["ownership"]["critical"]:
            parts.append(
                f"holds {len(deltas['ownership']['critical'])} critical "
                f"responsibilities"
            )
        return (
            f"Assigning {name} instead of {baseline}: "
            + "; ".join(parts)
            + ". Bounded to this decision's context — this is not a prediction."
        )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def view(
        self, db: AsyncSession, organization_id: str, decision_id: str
    ) -> dict[str, Any]:
        decision = await self._get(db, organization_id, decision_id)
        if not decision:
            raise LookupError("decision not found")
        candidates = (
            (
                await db.execute(
                    select(DecisionCandidate)
                    .where(DecisionCandidate.decision_id == decision.id)
                    .order_by(DecisionCandidate.rank)
                )
            )
            .scalars()
            .all()
        )
        evidence = (
            (
                await db.execute(
                    select(DecisionEvidenceItem)
                    .where(DecisionEvidenceItem.decision_id == decision.id)
                    .order_by(DecisionEvidenceItem.dimension)
                )
            )
            .scalars()
            .all()
        )
        sims = (
            (
                await db.execute(
                    select(DecisionSimulation)
                    .where(DecisionSimulation.decision_id == decision.id)
                    .order_by(DecisionSimulation.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        audit = (
            (
                await db.execute(
                    select(DecisionAudit)
                    .where(DecisionAudit.decision_id == decision.id)
                    .order_by(DecisionAudit.created_at)
                )
            )
            .scalars()
            .all()
        )
        try:
            requirements = json.loads(decision.requirements_json or "[]")
        except Exception:
            requirements = []
        try:
            provenance = json.loads(decision.provenance_json or "{}")
        except Exception:
            provenance = {}
        return {
            "id": decision.id,
            "organization_id": decision.organization_id,
            "decision_type": decision.decision_type,
            "risk_tier": decision.risk_tier,
            "context": {
                "context_type": decision.context_type,
                "context_id": decision.context_id,
                "context_label": decision.context_label,
            },
            "objective": decision.objective,
            "requirements": requirements,
            "lifecycle": decision.lifecycle,
            "recommendation": {
                "person_id": decision.recommended_person_id,
                "person_label": decision.recommended_person_label,
                "confidence": decision.confidence,
                "rationale": decision.rationale,
            },
            "candidates": [
                {
                    "person_id": c.person_id,
                    "person_label": c.person_label,
                    "role": c.role,
                    "rank": c.rank,
                    "rationale": c.rationale,
                    "trade_off": c.trade_off,
                    "why_not": c.why_not,
                }
                for c in candidates
            ],
            "evidence": [
                {
                    "person_id": e.person_id,
                    "dimension": e.dimension,
                    "source_type": e.source_type,
                    "source_id": e.source_id,
                    "claim": e.claim,
                }
                for e in evidence
            ],
            "simulations": [
                {
                    "person_id": s.person_id,
                    "person_label": s.person_label,
                    "deltas": json.loads(s.deltas_json or "{}"),
                    "verdict": s.verdict,
                }
                for s in sims
            ],
            "audit": [
                {
                    "action": a.action,
                    "actor_id": a.actor_id,
                    "note": a.note,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in audit
            ],
            "outcome": {
                "status": decision.outcome_status,
                "note": decision.outcome_note,
                "recorded_by": decision.outcome_recorded_by,
                "recorded_at": (
                    decision.outcome_recorded_at.isoformat()
                    if decision.outcome_recorded_at
                    else None
                ),
            },
            "provenance": provenance,
            "created_at": decision.created_at.isoformat() if decision.created_at else None,
        }

    async def _get(
        self, db: AsyncSession, organization_id: str, decision_id: str
    ) -> Optional[PeopleDecision]:
        return (
            (
                await db.execute(
                    select(PeopleDecision).where(
                        PeopleDecision.organization_id == organization_id,
                        PeopleDecision.id == decision_id,
                    )
                )
            )
            .scalars()
            .first()
        )

    async def list(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        limit: int = 50,
        lifecycle: Optional[str] = None,
        decision_type: Optional[str] = None,
        access: Optional[CallerAccess] = None,
    ) -> dict[str, Any]:
        q = select(PeopleDecision).where(
            PeopleDecision.organization_id == organization_id
        )
        if access is not None and not access.org_wide:
            # Governance scope: scoped callers only ever see decisions made
            # on projects inside their visible scope.
            q = q.where(
                (PeopleDecision.context_type == "project")
                & (PeopleDecision.context_id.in_(list(access.project_ids)))
            )
        if lifecycle:
            q = q.where(PeopleDecision.lifecycle == lifecycle)
        if decision_type:
            q = q.where(PeopleDecision.decision_type == decision_type)
        rows = (
            (
                await db.execute(
                    q.order_by(PeopleDecision.created_at.desc()).limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return {
            "total": len(rows),
            "decisions": [
                {
                    "id": d.id,
                    "decision_type": d.decision_type,
                    "risk_tier": d.risk_tier,
                    "context": {
                        "context_type": d.context_type,
                        "context_id": d.context_id,
                        "context_label": d.context_label,
                    },
                    "objective": d.objective,
                    "lifecycle": d.lifecycle,
                    "recommended_person_label": d.recommended_person_label,
                    "confidence": d.confidence,
                    "created_at": (
                        d.created_at.isoformat() if d.created_at else None
                    ),
                }
                for d in rows
            ]
        }

    async def _audit(
        self,
        db: AsyncSession,
        decision: PeopleDecision,
        action: str,
        actor_id: Optional[str],
        note: Optional[str],
    ) -> None:
        db.add(
            DecisionAudit(
                organization_id=decision.organization_id,
                decision_id=decision.id,
                action=action,
                actor_id=actor_id,
                note=note,
            )
        )

    # ------------------------------------------------------------------
    # Change-driven detection (exact-once).
    # ------------------------------------------------------------------
    async def detect_from_event(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        event,
        payload: dict[str, Any],
    ) -> Optional[str]:
        """project.started -> a staffing decision is DETECTED (unevaluated).

        Detection is a signal, never an action: the decision stays in
        'detected' until a human asks for evaluation or the caller
        evaluates it explicitly. Exact-once via last_event_id.
        """
        if event.name != "project.started":
            return None
        project_id = payload.get("project_id") or payload.get("id")
        if not project_id:
            return None
        dup = (
            (
                await db.execute(
                    select(PeopleDecision).where(
                        PeopleDecision.organization_id == organization_id,
                        PeopleDecision.last_event_id == event.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if dup:
            return dup.id
        existing = (
            (
                await db.execute(
                    select(PeopleDecision).where(
                        PeopleDecision.organization_id == organization_id,
                        PeopleDecision.context_type == "project",
                        PeopleDecision.context_id == project_id,
                        PeopleDecision.decision_type == "staffing",
                        PeopleDecision.lifecycle.in_(("detected", "evaluated", "recommended")),
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing:
            existing.last_event_id = event.id
            await db.flush()
            return existing.id

        decision = PeopleDecision(
            organization_id=organization_id,
            actor_id=payload.get("actor_id") or payload.get("owner_id"),
            decision_type="staffing",
            risk_tier=TYPE_TIERS["staffing"],
            context_type="project",
            context_id=project_id,
            context_label=payload.get("name") or payload.get("project_name") or "a new project",
            objective=(
                f"Detected: '{payload.get('name') or payload.get('project_name') or 'a new project'}' "
                f"started — who should staff it?"
            ),
            lifecycle="detected",
            last_event_id=event.id,
        )
        db.add(decision)
        await db.flush()
        await self._audit(
            db, decision, "detected", payload.get("actor_id"),
            "auto-detected from project.started (signal only, unevaluated)",
        )
        return decision.id


people_decision_engine = PeopleDecisionEngine()
