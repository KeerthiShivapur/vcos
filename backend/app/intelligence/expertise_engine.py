"""Phase 9.3 / Slice 4F.2 — Expertise evolution engine (extended).

4F.1 delivered structural people intelligence; 4F.2 upgrades the engine to
evidence-driven expertise:

    company activity -> canonical evidence (exact-once) -> deterministic
    dimensions -> expertise state (lifecycle, confidence, lineage) ->
    governed surfaces.

The legacy surface is preserved as a compatibility layer: ``record_activity``
keeps its exact signature (every existing handler call site still works), the
audit trail still lands in ``ExpertiseHistory``, legacy ``ExpertiseScore``
rows and ``Employee.expertise_score`` are mirrored from canonical state so
Phase-2 pages stay coherent with the canonical truth.

Rules enforced here (Slice 4F.2 spec):

    * evidence classes are deterministic (strong / medium / weak) with
      explicit weights; a weak message mention alone can never reach
      ``established``, never mind authoritative,
    * replay of an event creates no duplicate evidence (natural keys on
      (person, event) and (person, source)),
    * recomputation touches ONLY the affected (person x skill) cells and the
      affected team/department/business-unit/organization aggregates —
      complexity follows change volume, never company size,
    * no AI writes expertise: the authority chain is activity -> canonical
      evidence -> deterministic scoring -> state,
    * historical expertise is never deleted: decay produces ``dormant`` and
      ``historical_peak`` is preserved.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.event_models import EXPERTISE_EVENTS, describe
from app.models.employee import Employee, EmployeeSkill
from app.models.intelligence import ExpertiseHistory
from app.models.skill import ExpertiseScore, Skill
from app.models.skills_intelligence import (
    AGGREGATE_SCOPE_TYPES,  # noqa: F401
    CanonicalSkill,
    Expertise as ExpertiseState,
    ExpertiseEvidence,
    PersonSkill,
)
from app.people.skill_engine import skill_engine, MAX_EXTRACT

logger = logging.getLogger("vcos.intelligence.expertise")

MODEL_VERSION = "4f3.1"

MAX_EVIDENCE_PER_CELL = 500   # bounded evidence load per recomputed cell
DORMANT_DAYS = 270            # no observed evidence -> dormant
RECENT_DAYS = 90              # "recent activity" window
STRONG_UNIT_WEIGHT = 6.0      # depth == 1.0 at ~6 strong-class units

# Deterministic evidence classes: event name -> (strength, weight).
# Strong = repeatedly completed work, authored authoritative knowledge,
# validated certification, implemented decisions, completed goals.
# Medium = decision participation, substantial contributions, learning
# completions. Weak = mentions, attendance, one-off interactions.
EVIDENCE_CLASS_BY_EVENT: dict[str, tuple[str, float]] = {
    "task.completed": ("strong", 1.0),
    "milestone.completed": ("strong", 1.0),
    "document.created": ("strong", 0.9),
    "wiki.created": ("strong", 0.9),
    "decision.implemented": ("strong", 0.9),
    "goal.completed": ("strong", 0.9),
    "certificate.earned": ("strong", 0.95),
    "document.updated": ("medium", 0.6),
    "decision.made": ("medium", 0.7),
    "decision.executed": ("medium", 0.6),
    "policy.approved": ("medium", 0.5),
    "course.completed": ("medium", 0.6),
    "learning.path.completed": ("medium", 0.6),
    "assessment.finished": ("medium", 0.55),
    "community.posted": ("weak", 0.3),
    "recognition.given": ("weak", 0.4),
    "meeting.ended": ("weak", 0.25),
    "forum.replied": ("weak", 0.3),
    "innovation.submitted": ("weak", 0.4),
    "approval.approved": ("weak", 0.4),
    "knowledge.comment": ("weak", 0.3),
    "template.used": ("weak", 0.2),
    # Slice 4F.3 — outcome-bearing operations evidence (infrastructure work).
    # Successes and failures are BOTH first-class: a failed deployment writes
    # negative evidence for the operator, most-strongly weighted.
    "deployment.completed": ("strong", 1.0),
    "deployment.promoted": ("strong", 0.95),
    "disaster.recovery.recovered": ("strong", 0.95),
    "cluster.recovered": ("strong", 0.9),
    "backup.restored": ("strong", 0.9),
    "workflow.completed": ("medium", 0.6),
    "deployment.failed": ("strong", 1.0),
    "deployment.rolled_back": ("strong", 0.95),
    "backup.failed": ("medium", 0.6),
    "replica.failed": ("medium", 0.6),
    "workflow.failed": ("medium", 0.6),
    "health.degraded": ("medium", 0.5),
    "health.unhealthy": ("strong", 0.8),
    "disaster.recovery.failover": ("medium", 0.55),
    "approval.rejected": ("medium", 0.55),
    "expense.rejected": ("weak", 0.35),
    "purchase.rejected": ("weak", 0.35),
}

# Slice 4F.3 — canonical source taxonomy (evidence kinds for corroboration).
# One event -> one kind; corroboration counts DISTINCT kinds with effective
# evidence, so "work + knowledge + decision + recognition" corroborates far
# more strongly than four observations of the same kind.
EVIDENCE_KIND_BY_EVENT: dict[str, str] = {}
for _event in (
    "task.completed", "milestone.completed", "goal.completed",
    "deployment.completed", "deployment.promoted", "deployment.failed",
    "deployment.rolled_back", "backup.restored", "backup.failed",
    "replica.failed", "workflow.completed", "workflow.failed",
    "health.degraded", "health.unhealthy",
    "disaster.recovery.recovered", "disaster.recovery.failover",
    "cluster.recovered",
):
    EVIDENCE_KIND_BY_EVENT[_event] = "work"
for _event in (
    "document.created", "wiki.created", "document.updated", "wiki.updated",
    "template.used", "knowledge.comment", "innovation.submitted",
):
    EVIDENCE_KIND_BY_EVENT[_event] = "knowledge"
for _event in (
    "decision.made", "decision.executed", "decision.implemented",
    "policy.approved", "approval.approved", "approval.rejected",
    "expense.rejected", "purchase.rejected",
):
    EVIDENCE_KIND_BY_EVENT[_event] = "decision"
for _event in ("meeting.ended", "community.posted", "forum.replied"):
    EVIDENCE_KIND_BY_EVENT[_event] = "communication"
EVIDENCE_KIND_BY_EVENT["recognition.given"] = "recognition"
for _event in (
    "course.completed", "certificate.earned", "assessment.finished",
    "learning.path.completed",
):
    EVIDENCE_KIND_BY_EVENT[_event] = "learning"

# Slice 4F.3 — outcome signals. "neutral" is a mention/participation without
# a proven outcome; "successful" is proven by completion/delivery/recovery;
# "failed" is a contradiction (a failed deployment, a rejected approval).
EVIDENCE_OUTCOME_BY_EVENT: dict[str, str] = {
    "task.completed": "successful",
    "milestone.completed": "successful",
    "goal.completed": "successful",
    "document.created": "successful",
    "wiki.created": "successful",
    "decision.made": "successful",
    "decision.executed": "successful",
    "decision.implemented": "successful",
    "policy.approved": "successful",
    "approval.approved": "successful",
    "course.completed": "successful",
    "certificate.earned": "successful",
    "assessment.finished": "successful",
    "learning.path.completed": "successful",
    "recognition.given": "successful",
    "deployment.completed": "successful",
    "deployment.promoted": "successful",
    "cluster.recovered": "successful",
    "backup.restored": "successful",
    "workflow.completed": "successful",
    "disaster.recovery.recovered": "successful",
    "deployment.failed": "failed",
    "deployment.rolled_back": "failed",
    "backup.failed": "failed",
    "replica.failed": "failed",
    "workflow.failed": "failed",
    "health.degraded": "failed",
    "health.unhealthy": "failed",
    "disaster.recovery.failover": "failed",
    "approval.rejected": "failed",
    "expense.rejected": "failed",
    "purchase.rejected": "failed",
}

# Lifecycle thresholds (deterministic; documented in SLICE4F2 report).
LIFECYCLE_RULES = (
    # (min_score, min_evidence, min strong, min credible, min confidence, lifecycle)
    # Ordered most-restrictive first; the first satisfied rule wins.
    (80.0, 8, 6, 0, 0.75, "authoritative"),
    (60.0, 5, 3, 0, 0.60, "strong"),
    (35.0, 3, 0, 3, 0.0, "established"),   # credible = strong + medium
    (12.0, 2, 0, 0, 0.0, "emerging"),
)

LIFECYCLE_TO_LEGACY_LEVEL = {
    "observed": 1,
    "emerging": 2,
    "established": 3,
    "strong": 4,
    "authoritative": 5,
    "dormant": 3,
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_diff_days(now: datetime, past: Optional[datetime]) -> int:
    """Timezone-safe day gap: SQLite returns naive UTC, Postgres aware."""
    if past is None:
        return 0
    return max(0, (ensure_aware(now) - ensure_aware(past)).days)


def _class_for(event_name: str, points: Optional[float]) -> tuple[str, float]:
    """Deterministic evidence class for an event. Explicit ``points`` (legacy
    damped scale) map to classes: 2+ -> strong, 1..2 -> medium, else weak."""
    hit = EVIDENCE_CLASS_BY_EVENT.get(event_name)
    if hit is not None:
        return hit
    if points is not None:
        if points >= 2.0:
            return ("strong", 0.9)
        if points >= 1.0:
            return ("medium", 0.6)
        return ("weak", 0.3)
    return ("weak", 0.3)


def _taxonomy_for(
    event_name: str, points: Optional[float],
) -> tuple[str, float, str, str]:
    """Deterministic (strength, weight, kind, outcome) for an event.
    Missing entries fall back to the legacy class mapping with kind ``work``
    and no outcome signal (``neutral``) — never guessed."""
    strength, weight = _class_for(event_name, points)
    kind = EVIDENCE_KIND_BY_EVENT.get(event_name, "work")
    outcome = EVIDENCE_OUTCOME_BY_EVENT.get(event_name, "neutral")
    return strength, weight, kind, outcome


def _lifecycle(
    score: float, evidence_count: int, strong_count: int,
    credible_count: int, confidence: float, last_observed: Optional[datetime],
    now: datetime, outcome_validation: float = 1.0,
) -> str:
    """Deterministic lifecycle: observed -> emerging -> established -> strong
    -> authoritative; inactivity (DORMANT_DAYS) -> dormant. Weak-only cells
    are hard-capped at emerging: no credible evidence, no trust. A material
    share of failed outcomes (outcome_validation < 0.6) hard-caps the cell at
    established: contradicting evidence is never ignored."""
    if last_observed is not None and _safe_diff_days(now, last_observed) > DORMANT_DAYS:
        return "dormant"
    # Weak mentions alone (no strong or medium evidence) never leave emerging.
    if evidence_count > 0 and strong_count == 0 and credible_count == 0:
        return "emerging"
    # Contradicting outcomes cap trust: failed evidence can never be bundled
    # into an authoritative claim.
    if outcome_validation < 0.6:
        score = min(score, 34.0)
        confidence = min(confidence, 0.59)
    for min_score, min_evidence, min_strong, min_credible, min_conf, lifecycle in LIFECYCLE_RULES:
        if (score >= min_score and evidence_count >= min_evidence
                and strong_count >= min_strong and credible_count >= min_credible
                and confidence >= min_conf):
            return lifecycle
    if evidence_count >= 2 and score >= 12.0:
        return "emerging"
    return "observed"


def _dimensions(
    rows: list[ExpertiseEvidence], now: datetime,
) -> dict[str, Any]:
    """Deterministic dimension math for one (person x skill) cell.

    Evidence INDEPENDENCE (Slice 4F.3): rows from the same underlying action
    (lineage_key) within the same kind are counted once — the strongest row
    of the group wins — so a derived cascade can never inflate trust. Expired
    claims (valid_to passed) are excluded from current math but remain in
    lineage history. Outcome signals deflate score/confidence deterministically
    when failures are material; corroboration rewards INDEPENDENT kinds.
    """
    active = [
        r for r in rows
        if r.valid_to is None
        or (r.valid_to is not None and ensure_aware(r.valid_to) > now)
    ]
    expired_count = len(rows) - len(active)
    rows = active[:MAX_EVIDENCE_PER_CELL]
    count = len(rows)
    if count == 0:
        return {
            "score": 0.0, "confidence": 0.0, "depth": 0.0, "breadth": 0,
            "successful_count": 0, "failed_count": 0, "outcome_ratio": None,
            "outcome_validation": 1.0, "corroboration": 0.0,
            "distinct_lineages": 0, "corroborated_kinds": 0,
            "evidence_count": 0, "strong_count": 0, "medium_count": 0,
            "weak_count": 0, "frequency": 0, "span_days": 0,
            "first_observed": None, "last_observed": None,
            "lifecycle": "none", "deduplicated_count": 0, "recency": 0.0,
            "consistency": 0.0, "authority": 0.0, "sufficiency": 0.0,
            "freshness": "historical", "expired_count": expired_count,
        }

    # One underlying action -> the strongest row per (lineage_key, kind).
    best: dict[tuple[str, str], ExpertiseEvidence] = {}
    for r in rows:
        key = (r.lineage_key or r.event_id or r.id, r.evidence_kind)
        current = best.get(key)
        if current is None or r.weight > current.weight:
            best[key] = r
    effective = list(best.values())
    deduplicated = count - len(effective)

    strong_w = sum(r.weight for r in effective if r.strength == "strong")
    medium_w = sum(r.weight for r in effective if r.strength == "medium")
    weak_w = sum(r.weight for r in effective if r.strength == "weak")
    total_w = strong_w + medium_w + weak_w
    weighted = strong_w + medium_w * 0.55 + weak_w * 0.2
    strong_count = sum(1 for r in effective if r.strength == "strong")
    medium_count = sum(1 for r in effective if r.strength == "medium")
    weak_count = sum(1 for r in effective if r.strength == "weak")

    successful_count = sum(1 for r in effective if r.outcome == "successful")
    failed_count = sum(1 for r in effective if r.outcome == "failed")
    outcome_ratio = (
        successful_count / (successful_count + failed_count)
        if (successful_count + failed_count) > 0 else None
    )
    # outcome_validation: how much the sample PROVES the claim.
    if outcome_ratio is None:
        outcome_validation = 1.0
    elif outcome_ratio >= 0.8:
        outcome_validation = 1.0
    elif outcome_ratio >= 0.4:
        outcome_validation = outcome_ratio
    else:
        outcome_validation = 0.2

    occurred = sorted(
        (r.occurred_at for r in effective), key=ensure_aware
    )
    first_observed = occurred[0]
    last_observed = occurred[-1]
    days_since = _safe_diff_days(now, last_observed)
    span_days = _safe_diff_days(last_observed, first_observed)
    recent_count = sum(
        1 for r in effective if _safe_diff_days(now, r.occurred_at) <= RECENT_DAYS
    )

    depth = _clamp(weighted / STRONG_UNIT_WEIGHT, 0.0, 1.0)
    breadth = min(4.0, float(len({r.source_type for r in effective}))) / 4.0
    recency = _clamp(1.0 - days_since / 730.0, 0.0, 1.0)
    frequency = _clamp(recent_count / 6.0, 0.0, 1.0)
    consistency = _clamp(span_days / 540.0, 0.0, 1.0) if len(effective) >= 2 else 0.0
    authority = _clamp(strong_w / total_w, 0.0, 1.0) if total_w > 0 else 0.0
    sufficiency = _clamp(len(effective) / 10.0, 0.0, 1.0)

    # corroboration: distinct INDEPENDENT kinds (<= 5 contributing kinds).
    kinds = {r.evidence_kind for r in effective}
    corroborated_kinds = len(kinds)
    corroboration = _clamp(corroborated_kinds / 5.0, 0.0, 1.0)
    distinct_lineages = len({r.lineage_key or r.id for r in effective})

    # confidence v2 (Slice 4F.3): authority + sufficiency + recency +
    # consistency + strong share + CORROBORATION + OUTCOME VALIDATION.
    # Weights documented in the 4F.3 report; sum to 1.0.
    confidence = _clamp(
        0.25 * authority + 0.20 * sufficiency + 0.15 * recency
        + 0.12 * consistency + 0.08 * strong_count / max(1, len(effective))
        + 0.10 * corroboration + 0.10 * outcome_validation,
        0.0, 0.97,
    )
    # outcome gate: failed evidence deflates the score deterministically only
    # when it is material; a clean record is never punished.
    if failed_count > 0 and outcome_ratio is not None and outcome_ratio < 0.8:
        outcome_gate = 0.55 + 0.45 * outcome_ratio
    else:
        outcome_gate = 1.0
    score = (
        100.0
        * (0.45 * depth + 0.20 * breadth + 0.15 * recency
           + 0.10 * frequency + 0.10 * consistency)
        * (0.7 + 0.3 * authority)
        * outcome_gate
    )
    if days_since <= RECENT_DAYS:
        freshness = "active"
    elif days_since <= 365:
        freshness = "recent"
    else:
        freshness = "historical"
    lifecycle = _lifecycle(
        score, len(effective), strong_count, strong_count + medium_count,
        confidence, last_observed, now, outcome_validation,
    )

    return {
        "score": round(score, 1),
        "confidence": round(confidence, 3),
        "depth": round(depth, 3),
        "breadth": int(len({r.source_type for r in effective})),
        "recency": round(recency, 3),
        "frequency": int(recent_count),
        "consistency": round(consistency, 3),
        "authority": round(authority, 3),
        "sufficiency": round(sufficiency, 3),
        "evidence_count": len(effective),
        "strong_count": strong_count,
        "medium_count": medium_count,
        "weak_count": weak_count,
        "successful_count": successful_count,
        "failed_count": failed_count,
        "outcome_ratio": round(outcome_ratio, 3) if outcome_ratio is not None else None,
        "outcome_validation": round(outcome_validation, 3),
        "corroboration": round(corroboration, 3),
        "corroborated_kinds": corroborated_kinds,
        "distinct_lineages": distinct_lineages,
        "deduplicated_count": deduplicated,
        "expired_count": expired_count,
        "freshness": freshness,
        "first_observed": first_observed,
        "last_observed": last_observed,
        "span_days": span_days,
        "lifecycle": lifecycle,
    }


class ExpertiseEngine:
    # ------------------------------------------------------------------ legacy entry point

    async def record_activity(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: str,
        event_name: str,
        tokens: Optional[list[str]] = None,
        reason: Optional[str] = None,
        event_id: Optional[str] = None,
        points: Optional[float] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        source_title: Optional[str] = None,
        outcome: Optional[str] = None,
        origin_event_id: Optional[str] = None,
        lineage_key: Optional[str] = None,
        valid_to: Optional[datetime] = None,
    ) -> list[ExpertiseHistory]:
        """Legacy signature preserved: every existing handler keeps working.
        The canonical pipeline now runs underneath (evidence first, exact
        classes, recompute only affected cells, legacy mirror afterwards).
        ``source_type``/``source_id``/``source_title`` are optional lineage
        overrides (Slice 4F.2 handlers pass real canonical ids). Slice 4F.3
        adds explicit outcome / ancestry (``origin_event_id``, ``lineage_key``
        — for the trust model and the double-count guard)."""
        employee = await db.get(Employee, employee_id)
        if employee is None or employee.organization_id != organization_id:
            return []
        if event_name not in EXPERTISE_EVENTS and points is None:
            return []
        return await self._ingest(
            db,
            organization_id=organization_id,
            employee=employee,
            event_name=event_name,
            tokens=tokens or [],
            reason=reason or describe(event_name),
            event_id=event_id,
            points=points,
            source_type=source_type or event_name.split(".")[0] or "event",
            source_id=source_id or event_id or f"event-{event_name}",
            source_title=source_title or reason or describe(event_name),
            outcome=outcome,
            origin_event_id=origin_event_id,
            lineage_key=lineage_key,
            valid_to=valid_to,
        )

    async def record_evidence(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: str,
        event_name: str,
        tokens: Optional[list[str]] = None,
        reason: Optional[str] = None,
        event_id: Optional[str] = None,
        points: Optional[float] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        source_title: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        topic_id: Optional[str] = None,
        outcome: Optional[str] = None,
        origin_event_id: Optional[str] = None,
        lineage_key: Optional[str] = None,
        valid_to: Optional[datetime] = None,
    ) -> list[ExpertiseHistory]:
        """Canonical entry point with explicit source lineage (the 4F.2 path)."""
        employee = await db.get(Employee, employee_id)
        if employee is None or employee.organization_id != organization_id:
            return []
        event_name = event_name or "expertise.signal"
        return await self._ingest(
            db,
            organization_id=organization_id,
            employee=employee,
            event_name=event_name,
            tokens=tokens or [],
            reason=reason,
            event_id=event_id,
            points=points,
            source_type=source_type or event_name.split(".")[0] or "event",
            source_id=source_id or event_id or f"event-{event_name}",
            source_title=source_title,
            occurred_at=occurred_at,
            topic_id=topic_id,
            outcome=outcome,
            origin_event_id=origin_event_id,
            lineage_key=lineage_key,
            valid_to=valid_to,
        )

    # ------------------------------------------------------------------ pipeline

    async def _ingest(
        self,
        db: AsyncSession, *, organization_id: str, employee: Employee,
        event_name: str, tokens: list[str], reason: Optional[str],
        event_id: Optional[str], points: Optional[float],
        source_type: str, source_id: str, source_title: Optional[str],
        occurred_at: Optional[datetime] = None, topic_id: Optional[str] = None,
        outcome: Optional[str] = None, origin_event_id: Optional[str] = None,
        lineage_key: Optional[str] = None, valid_to: Optional[datetime] = None,
    ) -> list[ExpertiseHistory]:
        """Change-driven: resolve the person's canonical skills for this
        event, write exact-once evidence, recompute the affected cells only,
        mirror legacy surfaces, refresh bounded aggregates, publish the
        expertise.updated signal."""
        from app.people.capability_engine import capability_engine
        from app.intelligence.graph_engine import graph_engine

        await skill_engine.ensure_taxonomy(
            db, organization_id=organization_id
        )

        strength, _weight, kind, default_outcome = _taxonomy_for(event_name, points)

        # 1. bounded deterministic extraction
        matched = await skill_engine.resolve_candidates(
            db, organization_id=organization_id, terms=tokens
        )
        matched_ids = {s.id for s in matched}
        if not matched:
            return []

        now = occurred_at or utcnow()
        effective_outcome = outcome or default_outcome
        effective_lineage = (
            lineage_key or origin_event_id or event_id
            or f"{source_type}:{source_id}"
        )
        history: list[ExpertiseHistory] = []
        changed: list[ExpertiseState] = []
        for skill in matched[:MAX_EXTRACT]:
            # 3. exact-once evidence
            evidence = await self._evidence_for(
                db, organization_id=organization_id, person_id=employee.id,
                skill_id=skill.id, event_id=event_id, source_type=source_type,
                source_id=source_id,
            )
            if evidence is None:
                evidence = ExpertiseEvidence(
                    organization_id=organization_id,
                    person_id=employee.id,
                    skill_id=skill.id,
                    evidence_type=event_name,
                    strength=strength,
                    weight=_weight,
                    evidence_kind=kind,
                    outcome=effective_outcome,
                    valid_from=now,
                    valid_to=valid_to,
                    lineage_key=effective_lineage,
                    origin_event_id=origin_event_id,
                    source_type=source_type,
                    source_id=source_id,
                    source_title=source_title,
                    topic_id=topic_id,
                    detail=reason,
                    event_id=event_id,
                    occurred_at=now,
                )
                db.add(evidence)
                await db.flush()

            # the association (skills) always advances; only evidence moves
            # expertise.
            await skill_engine.bump_person_skill(
                db, organization_id=organization_id, person_id=employee.id,
                skill_id=skill.id, source="activity",
            )

            # 4. recompute ONLY this cell
            state = await self._recompute_cell(
                db, organization_id=organization_id,
                person_id=employee.id, skill_id=skill.id,
            )
            if state is not None and state.evidence_count > 0:
                changed.append(state)
                if state.lifecycle in ("strong", "authoritative"):
                    await graph_engine.upsert_edge(
                        db, organization_id=organization_id,
                        source_type="employee", source_id=employee.id,
                        target_type="skill", target_id=skill.id,
                        relation="expert_in",
                        evidence=f"{state.lifecycle} expertise in {skill.canonical_name}",
                    )
                await graph_engine.upsert_edge(
                    db, organization_id=organization_id,
                    source_type="employee", source_id=employee.id,
                    target_type="skill", target_id=skill.id,
                    relation="has_skill",
                    evidence=f"Demonstrated {skill.canonical_name} via {source_type}",
                )

            # 5. legacy mirror + audit
            cell_history = await self._mirror_legacy(
                db, organization_id=organization_id, employee=employee,
                skill=skill, event_name=event_name, reason=reason,
                event_id=event_id,
            )
            history.extend(cell_history)

        # 6. bounded aggregate refresh (person's scopes only)
        await capability_engine.refresh_person(
            db, organization_id=organization_id, person_id=employee.id,
        )

        # 7. legacy aggregate score + signal
        total = (
            await db.execute(
                select(func.coalesce(func.sum(ExpertiseScore.score), 0.0)).where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.employee_id == employee.id,
                )
            )
        ).scalar_one()
        employee.expertise_score = round(total or 0.0, 2)
        if changed:
            from app.events.publisher import publish_background_event

            await publish_background_event(
                db,
                name="expertise.updated",
                organization_id=organization_id,
                payload={
                    "employee_id": employee.id,
                    "event": event_name,
                    "changed_skills": len(changed),
                    "delta": round(sum(c.score for c in changed), 2),
                },
            )
        await db.flush()
        return history

    async def _evidence_for(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
        skill_id: str, event_id: Optional[str], source_type: str,
        source_id: str,
    ) -> Optional[ExpertiseEvidence]:
        """Exact-once lookups: event key when present, source key otherwise."""
        if event_id:
            return (
                await db.execute(
                    select(ExpertiseEvidence).where(
                        ExpertiseEvidence.organization_id == organization_id,
                        ExpertiseEvidence.person_id == person_id,
                        ExpertiseEvidence.skill_id == skill_id,
                        ExpertiseEvidence.event_id == event_id,
                    )
                )
            ).scalar_one_or_none()
        return (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.organization_id == organization_id,
                    ExpertiseEvidence.person_id == person_id,
                    ExpertiseEvidence.skill_id == skill_id,
                    ExpertiseEvidence.source_type == source_type,
                    ExpertiseEvidence.source_id == source_id,
                )
            )
        ).scalar_one_or_none()

    async def _recompute_cell(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
        skill_id: str,
    ) -> Optional[ExpertiseState]:
        """Deterministic recompute of ONE (person x skill) cell."""
        rows = list(
            (
                await db.execute(
                    select(ExpertiseEvidence).where(
                        ExpertiseEvidence.organization_id == organization_id,
                        ExpertiseEvidence.person_id == person_id,
                        ExpertiseEvidence.skill_id == skill_id,
                    ).order_by(ExpertiseEvidence.occurred_at.desc())
                    .limit(MAX_EVIDENCE_PER_CELL)
                )
            ).scalars().all()
        )
        if not rows:
            return None
        now = utcnow()
        dims = _dimensions(rows, now)

        state = (
            await db.execute(
                select(ExpertiseState).where(
                    ExpertiseState.organization_id == organization_id,
                    ExpertiseState.person_id == person_id,
                    ExpertiseState.skill_id == skill_id,
                )
            )
        ).scalar_one_or_none()
        if state is None:
            state = ExpertiseState(
                organization_id=organization_id,
                person_id=person_id,
                skill_id=skill_id,
                historical_peak=0.0,
            )
            db.add(state)
        state.score = dims["score"]
        state.confidence = dims["confidence"]
        state.evidence_count = dims["evidence_count"]
        state.strong_count = dims["strong_count"]
        state.medium_count = dims["medium_count"]
        state.weak_count = dims["weak_count"]
        state.successful_count = dims["successful_count"]
        state.failed_count = dims["failed_count"]
        state.outcome_ratio = dims["outcome_ratio"]
        state.distinct_lineages = dims["distinct_lineages"]
        state.corroborated_kinds = dims["corroborated_kinds"]
        state.freshness = dims["freshness"]
        state.breadth = dims["breadth"]
        state.depth = dims["depth"]
        state.recency_days = (
            _safe_diff_days(now, dims["last_observed"])
            if dims["last_observed"] else None
        )
        state.frequency_90d = dims["frequency"]
        state.span_months = int(dims["span_days"] / 30) if dims["span_days"] else None
        state.lifecycle = dims["lifecycle"]
        state.historical_peak = round(
            max(state.historical_peak or 0.0, dims["score"]), 1
        )
        state.first_observed = dims["first_observed"]
        state.last_observed = dims["last_observed"]
        state.factors_json = {
            "depth": dims["depth"],
            "breadth": dims["breadth"],
            "recency": dims["recency"],
            "frequency": dims["frequency"],
            "consistency": dims["consistency"],
            "authority": dims["authority"],
            "sufficiency": dims["sufficiency"],
            "strong": dims["strong_count"],
            "medium": dims["medium_count"],
            "weak": dims["weak_count"],
            "successful": dims["successful_count"],
            "failed": dims["failed_count"],
            "outcome_ratio": dims["outcome_ratio"],
            "outcome_validation": dims["outcome_validation"],
            "corroboration": dims["corroboration"],
            "corroborated_kinds": dims["corroborated_kinds"],
            "distinct_lineages": dims["distinct_lineages"],
            "deduplicated_count": dims["deduplicated_count"],
            "expired_count": dims["expired_count"],
            "freshness": dims["freshness"],
            "span_days": dims["span_days"],
            "evidence_types": sorted({r.source_type for r in rows}),
            "evidence_kinds": sorted({r.evidence_kind for r in rows}),
        }
        state.model_version = MODEL_VERSION
        state.updated_at = now
        await db.flush()
        return state

    async def _mirror_legacy(
        self, db: AsyncSession, *, organization_id: str, employee: Employee,
        skill: CanonicalSkill, event_name: str, reason: Optional[str],
        event_id: Optional[str],
    ) -> list[ExpertiseHistory]:
        """Mirror canonical state into the legacy surfaces (ExpertiseScore +
        ExpertiseHistory audit) so Phase-2 pages stay coherent. Returns the
        audit rows written."""
        legacy = (
            await db.execute(
                select(Skill).where(
                    Skill.organization_id == organization_id,
                    func.lower(Skill.name) == skill.canonical_name.lower(),
                )
            )
        ).scalar_one_or_none()
        if legacy is None:
            # Slice 4F.3 — an evidence-driven org may never have touched the
            # legacy skill surface; create the mirror row so Phase-2 pages
            # always show the same experts the brain trusts.
            legacy = Skill(
                organization_id=organization_id,
                name=skill.canonical_name,
                category=getattr(skill, "category", None),
            )
            db.add(legacy)
            await db.flush()
        state = (
            await db.execute(
                select(ExpertiseState).where(
                    ExpertiseState.organization_id == organization_id,
                    ExpertiseState.person_id == employee.id,
                    ExpertiseState.skill_id == skill.id,
                )
            )
        ).scalar_one_or_none()
        if legacy is None or state is None:
            return []
        legacy_level = LIFECYCLE_TO_LEGACY_LEVEL.get(state.lifecycle, 2)
        score_row = (
            await db.execute(
                select(ExpertiseScore).where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.employee_id == employee.id,
                    ExpertiseScore.skill_id == legacy.id,
                )
            )
        ).scalar_one_or_none()
        before = round(score_row.score if score_row is not None else 0.0, 2)
        if score_row is not None:
            score_row.score = round(state.score, 2)
            score_row.level = legacy_level
            score_row.years_experience = (state.span_months or 0) / 12.0
            score_row.factors = {
                **dict(score_row.factors or {}),
                "model": MODEL_VERSION,
                "lifecycle": state.lifecycle,
                "confidence": state.confidence,
                "evidence_count": state.evidence_count,
            }
            score_row.updated_at = utcnow()
        else:
            score_row = ExpertiseScore(
                organization_id=organization_id,
                employee_id=employee.id,
                skill_id=legacy.id,
                score=round(state.score, 2),
                level=legacy_level,
                years_experience=(state.span_months or 0) / 12.0,
                factors={
                    "model": MODEL_VERSION,
                    "lifecycle": state.lifecycle,
                    "confidence": state.confidence,
                    "evidence_count": state.evidence_count,
                },
            )
            db.add(score_row)
        after = round(state.score, 2)
        if abs(after - before) >= 0.01 or state.evidence_count == 1:
            row = ExpertiseHistory(
                organization_id=organization_id,
                employee_id=employee.id,
                skill_id=legacy.id,
                skill_name=skill.canonical_name,
                before=before,
                after=after,
                delta=round(after - before, 2),
                source_event=event_name,
                reason=reason,
                event_id=event_id,
            )
            db.add(row)
            await db.flush()
            return [row]
        return []

    # ------------------------------------------------------------------ recompute (workers)

    async def recompute_employee(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> float:
        """Refresh every cell of one employee (bounded by their skill set)."""
        cells = list(
            (
                await db.execute(
                    select(ExpertiseState).where(
                        ExpertiseState.organization_id == organization_id,
                        ExpertiseState.person_id == employee_id,
                    ).limit(MAX_EVIDENCE_PER_CELL)
                )
            ).scalars().all()
        )
        total = 0.0
        for cell in cells:
            state = await self._recompute_cell(
                db, organization_id=organization_id,
                person_id=employee_id, skill_id=cell.skill_id,
            )
            if state is not None:
                total += state.score
        employee = await db.get(Employee, employee_id)
        if employee is not None and employee.organization_id == organization_id:
            employee.expertise_score = round(total, 2)
        return total

    async def recompute_all(self, db: AsyncSession, *, organization_id: str) -> int:
        """Explicit worker-triggered full refresh (never on the event path)."""
        employee_ids = (
            await db.execute(
                select(Employee.id).where(Employee.organization_id == organization_id)
            )
        ).scalars().all()
        for employee_id in employee_ids:
            await self.recompute_employee(
                db, organization_id=organization_id, employee_id=employee_id
            )
        return len(employee_ids)

    # ------------------------------------------------------------------ reads

    async def state(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
        skill_id: str,
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(ExpertiseState).where(
                    ExpertiseState.organization_id == organization_id,
                    ExpertiseState.person_id == person_id,
                    ExpertiseState.skill_id == skill_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        skill = await db.get(CanonicalSkill, skill_id)
        return {
            "person_id": person_id,
            "skill_id": skill_id,
            "skill_name": skill.canonical_name if skill else skill_id,
            "category": skill.category if skill else None,
            "score": row.score,
            "confidence": row.confidence,
            "lifecycle": row.lifecycle,
            "historical_peak": row.historical_peak,
            "evidence_count": row.evidence_count,
            "strong_count": row.strong_count,
            "medium_count": row.medium_count,
            "weak_count": row.weak_count,
            "successful_count": row.successful_count,
            "failed_count": row.failed_count,
            "outcome_ratio": row.outcome_ratio,
            "distinct_lineages": row.distinct_lineages,
            "corroborated_kinds": row.corroborated_kinds,
            "freshness": row.freshness,
            "breadth": row.breadth,
            "depth": row.depth,
            "recency_days": row.recency_days,
            "frequency_90d": row.frequency_90d,
            "span_months": row.span_months,
            "first_observed": row.first_observed.isoformat() if row.first_observed else None,
            "last_observed": row.last_observed.isoformat() if row.last_observed else None,
            "factors": row.factors,
            "model_version": row.model_version,
        }

    async def trust(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
        skill_id: str, limit: int = 50,
    ) -> Optional[dict[str, Any]]:
        """Slice 4F.3 — the trust profile of one (person x skill) cell.

        Answers: WHY does VCOS believe it, WHAT evidence supports it, HOW
        reliable is it (confidence + outcome validation), HOW recent is it
        (freshness), WHO corroborates it (independent kinds/lineages), and
        what CONTRADICTS it (negative + expired evidence — never hidden)."""
        base = await self.state(
            db, organization_id=organization_id, person_id=person_id,
            skill_id=skill_id,
        )
        if base is None:
            return None
        employee = await db.get(Employee, person_id)
        items = await self.lineage(
            db, organization_id=organization_id, person_id=person_id,
            skill_id=skill_id, limit=limit,
        )
        contradictions = [
            e for e in items
            if e["outcome"] == "failed" or e["expired"]
        ]
        by_kind: dict[str, int] = {}
        by_source: dict[str, int] = {}
        recent_days = 180
        for e in items:
            by_kind[e["evidence_kind"]] = by_kind.get(e["evidence_kind"], 0) + 1
            by_source[e["source_type"]] = by_source.get(e["source_type"], 0) + 1
        recent = []
        recent_count = 0
        for e in items:
            if e["occurred_at"] is None:
                continue
            age_days = max(
                0, (ensure_aware(utcnow()) - ensure_aware(
                    datetime.fromisoformat(e["occurred_at"])
                )).days
            )
            if age_days <= recent_days:
                recent_count += 1
                recent.append(e)
        return {
            **base,
            "trust": True,
            "person_name": (
                employee.display_name
                or f"{employee.first_name} {employee.last_name or ''}".strip()
            ) if employee is not None and employee.organization_id == organization_id
            else None,
            "evidence_total": len(items),
            "evidence_by_kind": by_kind,
            "evidence_by_source": by_source,
            "recent_evidence": [e for e in recent[:20]],
            "recent_evidence_count": recent_count,
            "recent_evidence_days": recent_days,
            "contradictions": contradictions[:20],
            "contradiction_count": len(contradictions),
        }

    async def evidence(
        self, db: AsyncSession, *, organization_id: str, evidence_id: str,
    ) -> Optional[dict[str, Any]]:
        """One evidence item with full provenance (governed drill-down)."""
        row = await db.get(ExpertiseEvidence, evidence_id)
        if row is None or row.organization_id != organization_id:
            return None
        skill = await db.get(CanonicalSkill, row.skill_id)
        return {
            "evidence_id": row.id,
            "person_id": row.person_id,
            "skill_id": row.skill_id,
            "skill_name": skill.canonical_name if skill else row.skill_id,
            "evidence_type": row.evidence_type,
            "evidence_kind": row.evidence_kind,
            "strength": row.strength,
            "weight": row.weight,
            "outcome": row.outcome,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "source_title": row.source_title,
            "detail": row.detail,
            "event_id": row.event_id,
            "origin_event_id": row.origin_event_id,
            "lineage_key": row.lineage_key,
            "valid_from": row.valid_from.isoformat() if row.valid_from else None,
            "valid_to": row.valid_to.isoformat() if row.valid_to else None,
            "expired": (
                row.valid_to is not None
                and ensure_aware(row.valid_to) <= utcnow()
            ),
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def expire_source(
        self, db: AsyncSession, *, organization_id: str,
        source_type: str, source_id: str, valid_to: Optional[datetime] = None,
    ) -> int:
        """Expire every currently-valid evidence item of one canonical source
        (e.g. a deployment that got rolled back): the claim loses its validity
        window but stays visible as history in lineage/trust surfaces."""
        rows = list(
            (
                await db.execute(
                    select(ExpertiseEvidence).where(
                        ExpertiseEvidence.organization_id == organization_id,
                        ExpertiseEvidence.source_type == source_type,
                        ExpertiseEvidence.source_id == source_id,
                        ExpertiseEvidence.valid_to.is_(None),
                    )
                )
            ).scalars().all()
        )
        at = valid_to or utcnow()
        for row in rows:
            row.valid_to = at
        await db.flush()
        return len(rows)

    async def lineage(
        self, db: AsyncSession, *, organization_id: str, person_id: str,
        skill_id: str, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Every expertise claim is explainable: canonical source ids and the
        event that produced them."""
        rows = (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.organization_id == organization_id,
                    ExpertiseEvidence.person_id == person_id,
                    ExpertiseEvidence.skill_id == skill_id,
                ).order_by(ExpertiseEvidence.occurred_at.desc())
                .limit(min(limit, 200))
            )
        ).scalars().all()
        topic_ids = {r.topic_id for r in rows if r.topic_id}
        topic_names: dict[str, str] = {}
        if topic_ids:
            from app.models.knowledge import KnowledgeTopic

            for topic in (
                await db.execute(
                    select(KnowledgeTopic.id, KnowledgeTopic.name).where(
                        KnowledgeTopic.organization_id == organization_id,
                        KnowledgeTopic.id.in_(topic_ids),
                    )
                )
            ).all():
                topic_names[topic.id] = topic.name
        return [
            {
                "evidence_id": r.id,
                "evidence_type": r.evidence_type,
                "evidence_kind": r.evidence_kind,
                "strength": r.strength,
                "weight": r.weight,
                "outcome": r.outcome,
                "source_type": r.source_type,
                "source_id": r.source_id,
                "source_title": r.source_title,
                "topic": topic_names.get(r.topic_id) if r.topic_id else None,
                "detail": r.detail,
                "event_id": r.event_id,
                "origin_event_id": r.origin_event_id,
                "lineage_key": r.lineage_key,
                "valid_from": r.valid_from.isoformat() if r.valid_from else None,
                "valid_to": r.valid_to.isoformat() if r.valid_to else None,
                "expired": (
                    r.valid_to is not None
                    and ensure_aware(r.valid_to) <= utcnow()
                ),
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            }
            for r in rows
        ]

    async def history(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(ExpertiseHistory)
                .where(
                    ExpertiseHistory.organization_id == organization_id,
                    ExpertiseHistory.employee_id == employee_id,
                )
                .order_by(ExpertiseHistory.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": row.id,
                "employee_id": row.employee_id,
                "skill_id": row.skill_id,
                "skill_name": row.skill_name,
                "before": row.before,
                "after": row.after,
                "delta": row.delta,
                "source_event": row.source_event,
                "reason": row.reason,
                "event_id": row.event_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    async def leaderboard(
        self, db: AsyncSession, *, organization_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(Employee)
                .where(Employee.organization_id == organization_id, Employee.status == "active")
                .order_by(Employee.expertise_score.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "employee_id": e.id,
                "name": e.display_name or f"{e.first_name} {e.last_name or ''}".strip(),
                "designation": e.designation,
                "department_id": e.department_id,
                "expertise_score": round(e.expertise_score or 0.0, 2),
                "top_skills": await self._top_skills(db, organization_id, e.id),
            }
            for e in rows
        ]

    async def _top_skills(
        self, db: AsyncSession, organization_id: str, employee_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(ExpertiseScore)
                .where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.employee_id == employee_id,
                )
                .order_by(ExpertiseScore.score.desc())
                .limit(limit)
            )
        ).scalars().all()
        if not rows:
            return []
        skills = {
            s.id: s.name
            for s in (
                await db.execute(select(Skill).where(Skill.id.in_([r.skill_id for r in rows])))
            ).scalars().all()
        }
        return [
            {"skill_id": r.skill_id, "name": skills.get(r.skill_id, r.skill_id), "score": round(r.score, 2), "level": r.level}
            for r in rows
        ]


expertise_engine = ExpertiseEngine()