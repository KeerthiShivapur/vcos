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

MODEL_VERSION = "4f2.1"

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


def _lifecycle(
    score: float, evidence_count: int, strong_count: int,
    credible_count: int, confidence: float, last_observed: Optional[datetime],
    now: datetime,
) -> str:
    """Deterministic lifecycle: observed -> emerging -> established -> strong
    -> authoritative; inactivity (DORMANT_DAYS) -> dormant. Weak-only cells
    are hard-capped at emerging: no credible evidence, no trust."""
    if last_observed is not None and _safe_diff_days(now, last_observed) > DORMANT_DAYS:
        return "dormant"
    # Weak mentions alone (no strong or medium evidence) never leave emerging.
    if evidence_count > 0 and strong_count == 0 and credible_count == 0:
        return "emerging"
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
    """Deterministic dimension math for one (person x skill) cell."""
    count = len(rows)
    if count == 0:
        return {"score": 0.0, "confidence": 0.0, "depth": 0.0, "breadth": 0}

    strong_w = sum(r.weight for r in rows if r.strength == "strong")
    medium_w = sum(r.weight for r in rows if r.strength == "medium")
    weak_w = sum(r.weight for r in rows if r.strength == "weak")
    total_w = strong_w + medium_w + weak_w
    weighted = strong_w + medium_w * 0.55 + weak_w * 0.2
    strong_count = sum(1 for r in rows if r.strength == "strong")
    medium_count = sum(1 for r in rows if r.strength == "medium")
    weak_count = sum(1 for r in rows if r.strength == "weak")

    occurred = sorted((r.occurred_at for r in rows), key=ensure_aware)
    first_observed = occurred[0]
    last_observed = occurred[-1]
    days_since = _safe_diff_days(now, last_observed)
    span_days = _safe_diff_days(last_observed, first_observed)
    recent_count = sum(
        1 for r in rows if _safe_diff_days(now, r.occurred_at) <= RECENT_DAYS
    )

    depth = _clamp(weighted / STRONG_UNIT_WEIGHT, 0.0, 1.0)
    breadth = min(4.0, float(len({r.source_type for r in rows}))) / 4.0
    recency = _clamp(1.0 - days_since / 730.0, 0.0, 1.0)
    frequency = _clamp(recent_count / 6.0, 0.0, 1.0)
    consistency = _clamp(span_days / 540.0, 0.0, 1.0) if count >= 2 else 0.0
    authority = _clamp(strong_w / total_w, 0.0, 1.0) if total_w > 0 else 0.0
    sufficiency = _clamp(count / 10.0, 0.0, 1.0)

    confidence = _clamp(
        0.30 * authority + 0.25 * sufficiency + 0.20 * recency
        + 0.15 * consistency + 0.10 * strong_count / max(1, count),
        0.0, 0.97,
    )
    score = (
        100.0
        * (0.45 * depth + 0.20 * breadth + 0.15 * recency
           + 0.10 * frequency + 0.10 * consistency)
        * (0.7 + 0.3 * authority)
    )
    lifecycle = _lifecycle(
        score, count, strong_count, strong_count + medium_count,
        confidence, last_observed, now,
    )

    return {
        "score": round(score, 1),
        "confidence": round(confidence, 3),
        "depth": round(depth, 3),
        "breadth": int(len({r.source_type for r in rows})),
        "recency": round(recency, 3),
        "frequency": int(recent_count),
        "consistency": round(consistency, 3),
        "authority": round(authority, 3),
        "sufficiency": round(sufficiency, 3),
        "evidence_count": count,
        "strong_count": strong_count,
        "medium_count": medium_count,
        "weak_count": weak_count,
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
    ) -> list[ExpertiseHistory]:
        """Legacy signature preserved: every existing handler keeps working.
        The canonical pipeline now runs underneath (evidence first, exact
        classes, recompute only affected cells, legacy mirror afterwards).
        ``source_type``/``source_id``/``source_title`` are optional lineage
        overrides (Slice 4F.2 handlers pass real canonical ids)."""
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
        )

    # ------------------------------------------------------------------ pipeline

    async def _ingest(
        self,
        db: AsyncSession, *, organization_id: str, employee: Employee,
        event_name: str, tokens: list[str], reason: Optional[str],
        event_id: Optional[str], points: Optional[float],
        source_type: str, source_id: str, source_title: Optional[str],
        occurred_at: Optional[datetime] = None, topic_id: Optional[str] = None,
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

        strength, _weight = _class_for(event_name, points)

        # 1. bounded deterministic extraction
        matched = await skill_engine.resolve_candidates(
            db, organization_id=organization_id, terms=tokens
        )
        matched_ids = {s.id for s in matched}
        if not matched:
            return []

        now = occurred_at or utcnow()
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
            "span_days": dims["span_days"],
            "evidence_types": sorted({r.source_type for r in rows}),
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
                "strength": r.strength,
                "weight": r.weight,
                "source_type": r.source_type,
                "source_id": r.source_id,
                "source_title": r.source_title,
                "topic": topic_names.get(r.topic_id) if r.topic_id else None,
                "detail": r.detail,
                "event_id": r.event_id,
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