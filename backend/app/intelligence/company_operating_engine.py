"""Slice 4G.7 — Universal Company Operating Intelligence.

The company-level synthesis layer: it ANSWERS "what does the company as a
whole need to do next?" by composing the canonical systems of record —
execution (4G.1), coordination (4G.2), strategy (4G.3), capacity (4G.4),
customer intelligence (4G.5), business performance (4G.6), people and
knowledge — NEVER by parallel-copying their data.

Closed loop (the 4G.7 spec):

  COMPANY STATE -> OBSERVE -> UNDERSTAND -> DETECT -> CONNECT CAUSES+IMPACT
  -> GENERATE OPTIONS -> SIMULATE/COMPARE -> RECOMMEND -> HUMAN APPROVAL
  -> EXECUTE -> MEASURE OUTCOME -> LEARN -> UPDATE INTELLIGENCE

Surfaces (all advisory-only, bounded, deterministic, org-wide):

  company_state      — one composed picture of the company (7 dimensions).
  health             — eight-domain company health with the primary
                       constraint, its root cause and interventions.
  root_cause         — a business problem -> metric -> driver -> customer
                       impact -> project -> task/dependency -> capacity
                       constraint -> people/capability chain.
  impact             — propagation of a person / project / capability /
                       customer / goal change across the company.
  recommendations    — the universal company recommendation queue
                       (prioritized, evidence-carrying).
  what_if            — bounded deterministic consequences of reallocate /
                       delay / hire scenarios. Never a prediction.
  changes            — "What changed?" — the meaningful company-level deltas
                       since the previous assessment and why they matter.
  memory             — the decision -> reason -> action -> outcome -> learning
                       records that make the organization learn.

Governed writes (HUMAN approved only, never automatic):

  record_decision    — a human approved or declined a recommendation.
  execute_decision   — an approved action was executed.
  record_outcome     — the observed outcome + lesson of an executed action.

Persistence is exact-once (keyed on the source event) and change-driven:
every meaningful upstream event recomputes the company health trail, so
"What changed?" stays answerable over any window. One canonical architecture
for every company size — 5 to 50,000+ people.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select

from app.db.database import AsyncSession
from app.models.company_operating import (
    COMPANY_HEALTH_DOMAINS,
    DECISION_STATES,
    DOMAIN_WEIGHTS,
    MAX_CHANGES_SHOWN,
    MAX_COMPANY_RECOMMENDATIONS,
    MAX_MEMORY_SHOWN,
    MAX_WHATIF_CONSEQUENCES,
    CompanyDecision,
    CompanyHealthHistory,
)
from app.models.customer_intelligence import CustomerCommitment
from app.models.employee import Employee
from app.models.knowledge import (
    KnowledgeIntelInsight,
    KnowledgeRecommendation,
    KnowledgeTopic,
)
from app.models.project import Project
from app.models.task import Task

from app.intelligence.execution_engine import execution_engine
from app.intelligence.coordination_engine import coordination_engine
from app.intelligence.strategic_execution_engine import strategic_execution_engine
from app.intelligence.resource_allocation_engine import resource_allocation_engine
from app.intelligence.customer_intelligence_engine import customer_intelligence_engine
from app.intelligence.business_performance_engine import business_performance_engine

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_PRIORITY_RANK = {
    "critical": 1,
    "urgent": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
    "info": 5,
}

# A sentinel org-wide access for composition inside the engine (surfaces that
# require an access object treat org_wide callers as unconstrained).
_ORG_WIDE = type("_OrgWideAccess", (), {"org_wide": True})()

_NEUTRAL = {"score": 80, "state": "healthy"}
_NEUTRAL_REASON = "no evidence yet — the domain is neutral until the company records activity"

MAX_HISTORY_SHOWN = 40
MAX_FOCUS_ITEMS = 5
MAX_PROJECT_SCAN = 40
MAX_STEP_ENTITIES = 3
MAX_CONSTRAINT_CHAIN = 6


def _band(score: int) -> str:
    if score >= 75:
        return "healthy"
    if score >= 50:
        return "concerned"
    if score >= 30:
        return "at_risk"
    return "critical"


def _clamp(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))


def _iso(dt: Any) -> str:
    if dt is None:
        return ""
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)


def _rank(label: Any, default: int = 3) -> int:
    return _PRIORITY_RANK.get(str(label or "").strip().lower(), default)


_HEALTH_LABEL = {
    "healthy": 80, "good": 80, "concerned": 65, "warning": 60,
    "at_risk": 45, "critical": 20, "red": 25, "poor": 35,
}


def _health_int(value: Any, default: int = 100) -> int:
    if isinstance(value, str):
        label = value.strip().lower()
        if label in _HEALTH_LABEL:
            return _HEALTH_LABEL[label]
        if label.isdigit():
            return int(label)
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dict_list(value: Any, key: str) -> list[Any]:
    """Normalize {"count": n, key: [...]} (assess shape) or a bare list."""
    if isinstance(value, dict):
        return value.get(key) or []
    return value or []


def _head(items: Any, limit: int = MAX_STEP_ENTITIES) -> list[Any]:
    if items is None or isinstance(items, (int, float, str, bool)):
        return []
    return list(items)[:limit]


class CompanyOperatingEngine:
    """Composes the canonical 4G engines into the company operating layer."""

    # ------------------------------------------------------------------
    # 1. Universal company state
    # ------------------------------------------------------------------

    async def company_state(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """One composed picture of the company as a whole.

        Every dimension is the canonical engine's own output, bounded; no
        parallel copy of any underlying record lives here.
        """
        dimensions: dict[str, Any] = {}

        portfolio = await strategic_execution_engine.portfolio(
            db, organization_id=organization_id,
        )
        goals = _head(portfolio.get("goals") or [], 5)
        focus = _head(
            await strategic_execution_engine.focus(db, organization_id=organization_id),
            3,
        )
        dimensions["strategy"] = {
            "label": "Strategy",
            "state": portfolio.get("health_summary", {}).get(
                "company_state", "concerned"
            ),
            "headline": (
                f"{portfolio.get('health_summary', {}).get('healthy', 0)} of "
                f"{portfolio.get('health_summary', {}).get('total', 0)} goals "
                f"healthy; mean coverage "
                f"{portfolio.get('mean_goal_coverage', 0) or 0:.0%}"
            ),
            "goals": [
                {
                    "goal_id": g.get("goal_id"),
                    "title": g.get("title"),
                    "health": g.get("health"),
                    "coverage": g.get("coverage"),
                    "priority_label": g.get("priority_label"),
                }
                for g in goals
            ],
            "focus": [
                {"title": f.get("title"), "why": f.get("why")} for f in focus
            ],
        }

        command = await execution_engine.command_center(
            db, organization_id=organization_id,
        )
        projects = _head(command.get("projects") or [], 5)
        dimensions["execution"] = {
            "label": "Execution",
            "state": _band(80) if not (command.get("projects")) else (
                "concerned" if command.get("counts", {}).get("at_risk", 0)
                else "healthy"
            ),
            "headline": (
                f"{command.get('counts', {}).get('at_risk', 0)} of "
                f"{command.get('counts', {}).get('active_projects', 0)} active "
                f"projects at risk; {command.get('counts', {}).get('blocked_projects', 0)} blocked"
            ),
            "projects": [
                {
                    "project_id": p.get("project_id"),
                    "name": p.get("name"),
                    "health_status": p.get("health_status"),
                    "health_score": p.get("health_score"),
                    "primary_cause": p.get("primary_cause"),
                }
                for p in projects
            ],
        }

        center = await coordination_engine.center(
            db, organization_id=organization_id, access=_ORG_WIDE,
        )
        counts = center.get("counts") or {}
        dimensions["coordination"] = {
            "label": "Coordination",
            "headline": (
                f"{counts.get('open', 0)} open coordination incidents "
                f"({counts.get('critical', 0)} critical, {counts.get('high', 0)} high)"
            ),
            "incidents": _head(center.get("incidents") or [], 3),
        }

        capacity = await resource_allocation_engine.center(
            db, organization_id=organization_id,
        )
        bottlenecks = capacity.get("critical_bottlenecks") or []
        dimensions["capacity"] = {
            "label": "Capacity",
            "headline": (
                f"company utilization {capacity.get('company_utilization', 0):.0%} "
                f"over {capacity.get('window', {}).get('start')} - "
                f"{capacity.get('window', {}).get('end')}; "
                f"{len(bottlenecks)} critical bottlenecks"
            ),
            "top_constraint": capacity.get("top_constraint"),
            "bottlenecks": _head(bottlenecks, 3),
        }

        overloads = await resource_allocation_engine.overloads(
            db, organization_id=organization_id,
        )
        person_overloads = overloads.get("person_overloads") or []
        team_overloads = overloads.get("team_overloads") or []
        dimensions["people"] = {
            "label": "People",
            "headline": (
                f"{len(person_overloads)} people and {len(team_overloads)} "
                f"teams committed over capacity"
            ),
            "person_overloads": _head(person_overloads, 3),
            "team_overloads": _head(team_overloads, 3),
        }

        healths = await customer_intelligence_engine.healths(
            db, organization_id=organization_id,
        )
        risk = await customer_intelligence_engine.risk(
            db, organization_id=organization_id,
        )
        dimensions["customers"] = {
            "label": "Customers",
            "headline": (
                f"{healths.get('at_risk', 0)} of {healths.get('total', 0)} "
                f"customers at risk; {len(risk.get('commitments_at_risk') or [])} "
                f"commitments at risk"
            ),
            "at_risk": _head(
                [h for h in (healths.get("health") or []) if h.get("state") == "at_risk"],
                3,
            ),
        }

        perf = await business_performance_engine.performance(
            db, organization_id=organization_id, scope="org_wide",
        )
        financial = None
        for d in (perf or {}).get("health", {}).get("dimensions") or []:
            if d.get("key") == "financial":
                financial = d
                break
        dimensions["financial"] = {
            "label": "Financial",
            "state": financial.get("state") if financial else "concerned",
            "headline": (
                f"{financial.get('label')} is {financial.get('state')} "
                f"({financial.get('score')}/100)" if financial
                else "no business performance assessment yet"
            ),
            "reasons": _head(financial.get("reasons") or [], 2) if financial else [],
        }

        open_recs = list(
            (
                await db.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.organization_id == organization_id,
                        KnowledgeRecommendation.status == "active",
                    )
                    .order_by(KnowledgeRecommendation.updated_at.desc())
                    .limit(5)
                )
            ).scalars().all()
        )
        dimensions["knowledge"] = {
            "label": "Knowledge",
            "headline": f"{len(open_recs)} open knowledge recommendations",
            "open": [
                {"title": getattr(r, "reason", "")[:160], "confidence": getattr(r, "confidence", 0)}
                for r in open_recs
            ],
        }

        attention: list[dict[str, Any]] = []
        for f in focus:
            attention.append({
                "priority": _rank(f.get("priority_label", 3)),
                "kind": "strategic_focus",
                "title": f.get("title"),
                "why": f.get("why"),
            })
        for item in _head((await execution_engine.execution_next(
            db, organization_id=organization_id,
        )).get("items") or [], 2):
            attention.append({
                "priority": _rank(item.get("priority"), 3),
                "kind": item.get("kind") or "execution",
                "title": item.get("title"),
                "why": item.get("reason"),
            })
        top = capacity.get("top_constraint") or {}
        if top.get("capability"):
            attention.append({
                "priority": 1,
                "kind": "capacity_constraint",
                "title": f"Resolve {top.get('capability')} capacity constraint",
                "why": top.get("recommended_action"),
            })
        attention = sorted(
            attention, key=lambda a: (a.get("priority", 3), a.get("kind", "")),
        )[:_head(attention, 5) and 5]

        return {
            "advisory_only": True,
            "organization_id": organization_id,
            "dimensions": dimensions,
            "attention": attention,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    # ------------------------------------------------------------------
    # 2. Universal company health (eight explainable domains)
    # ------------------------------------------------------------------

    async def _domain_strategy(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        portfolio = await strategic_execution_engine.portfolio(
            db, organization_id=organization_id,
        )
        goals = portfolio.get("goals") or []
        hs = portfolio.get("health_summary") or {}
        total = hs.get("total") or len(goals)
        if total == 0:
            return self._domain_row("strategy", "Strategy", 80, [_NEUTRAL_REASON])
        healthy = int(hs.get("healthy") or 0)
        at_risk = int(hs.get("at_risk") or 0)
        critical = int(hs.get("critical") or 0)
        concerned = total - healthy - at_risk - critical
        score = _clamp(
            (85 * healthy + 62 * concerned + 40 * at_risk + 20 * critical) / total
        )
        mean_cov = portfolio.get("mean_goal_coverage") or 0.0
        reasons = []
        if at_risk or critical:
            reasons.append(
                f"{at_risk + critical} of {total} goals at risk or critical"
            )
        if mean_cov:
            reasons.append(f"mean goal coverage {min(mean_cov, 1.0) * 100:.0f}%")
        positives = [f"{healthy} of {total} goals healthy"] if healthy else []
        worst = min(goals, key=lambda g: _health_int(g.get("health")))
        focus = await strategic_execution_engine.focus(
            db, organization_id=organization_id,
        )
        return self._domain_row(
            "strategy", "Strategy", score,
            reasons or ([_NEUTRAL_REASON] if total == 0 else ["strategy stable"]),
            positives=positives,
            affected=[
                g.get("title") for g in goals if _health_int(g.get("health")) < 75
            ][:3],
            constraint=(
                {
                    "label": worst.get("title"),
                    "detail": worst.get("primary_reason") or "goal under-covered",
                    "affected": _head(worst.get("active_projects") or []),
                }
                if _health_int(worst.get("health")) < 75 else None
            ),
            root_cause=focus[0].get("why") if focus else None,
            interventions=[f.get("title") for f in _head(focus, 2)],
            evidence_count=total,
        )

    async def _domain_execution(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        cc = await execution_engine.command_center(
            db, organization_id=organization_id,
        )
        projects = cc.get("projects") or []
        counts = cc.get("counts") or {}
        active = int(counts.get("active_projects") or len(projects))
        if active == 0 and not projects:
            return self._domain_row("execution", "Execution", 80, [_NEUTRAL_REASON])
        at_risk = int(counts.get("at_risk") or 0)
        blocked = int(counts.get("blocked_projects") or 0)
        cap_con = int(counts.get("capacity_constraints") or 0)
        score = _clamp(80 - 10 * at_risk - 14 * blocked - 4 * cap_con)
        reasons = []
        if at_risk:
            reasons.append(f"{at_risk} of {active} active projects at risk")
        if blocked:
            reasons.append(f"{blocked} projects blocked")
        worst = min(projects, key=lambda p: p.get("health_score", 100))
        next_items = _head(
            (await execution_engine.execution_next(
                db, organization_id=organization_id,
            )).get("items") or [], 3,
        )
        return self._domain_row(
            "execution", "Execution", score,
            reasons or ["execution stable"],
            affected=[
                p.get("name") for p in projects
                if p.get("health_score", 100) < 75
            ][:3],
            constraint=(
                {
                    "label": worst.get("name"),
                    "detail": worst.get("primary_cause") or "health below healthy band",
                    "affected": _head(worst.get("capacity_constraints") or []),
                }
                if worst.get("health_score", 100) < 75 else None
            ),
            root_cause=worst.get("explain") or worst.get("primary_cause"),
            interventions=[i.get("title") for i in next_items],
            evidence_count=active,
        )

    async def _domain_coordination(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        center = await coordination_engine.center(
            db, organization_id=organization_id, access=_ORG_WIDE,
        )
        incidents = center.get("incidents") or []
        counts = center.get("counts") or {}
        open_count = int(counts.get("open") or len(incidents))
        severe = int(counts.get("critical") or 0) + int(counts.get("high") or 0)
        if open_count == 0:
            return self._domain_row(
                "coordination", "Coordination", 80, ["no open coordination incidents"]
            )
        score = _clamp(80 - 8 * severe - 4 * open_count)
        top = incidents[0]
        return self._domain_row(
            "coordination", "Coordination", score,
            [f"{severe} of {open_count} open incidents critical or high"],
            affected=[
                p.get("name") for p in _head(center.get("projects_affected") or [], 3)
            ],
            constraint={
                "label": top.get("title") or top.get("kind"),
                "detail": top.get("summary") or "",
                "affected": _head(top.get("project_name") and [top.get("project_name")] or []),
            },
            root_cause="; ".join(str(e) for e in _head(top.get("evidence") or [], 2)),
            interventions=[
                r.get("summary") for r in _head(center.get("recommendations") or [], 2)
            ],
            evidence_count=open_count,
        )

    async def _domain_capacity(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        center = await resource_allocation_engine.center(
            db, organization_id=organization_id,
        )
        util = center.get("company_utilization") or 0.0
        util_frac = util / 100.0
        bottlenecks = center.get("critical_bottlenecks") or []
        overloaded_raw = center.get("overloaded_capabilities") or 0
        overloaded_count = (
            int(overloaded_raw)
            if isinstance(overloaded_raw, int)
            else len(overloaded_raw or [])
        )
        if not bottlenecks and not overloaded_count and not center.get("top_constraint"):
            return self._domain_row(
                "capacity", "Capacity", _clamp(80 - max(0, util_frac - 0.90) * 50),
                [f"company utilization {util:.0f}%" if util else _NEUTRAL_REASON],
            )
        score = _clamp(
            80 - 12 * len(bottlenecks) - 6 * overloaded_count
            - max(0.0, (util_frac - 0.90)) * 50
        )
        top = center.get("top_constraint") or {}
        reasons = [f"{len(bottlenecks)} critical capacity bottlenecks"]
        top_gap = 0
        try:
            top_gap = max(0, int(top.get("gap") or 0))
        except (TypeError, ValueError):
            top_gap = 0
        if bottlenecks:
            state = (
                "critical"
                if top_gap >= 10 or len(bottlenecks) >= 3
                else "at_risk"
            )
        else:
            state = None  # derive from the utilization score
        return self._domain_row(
            "capacity", "Capacity", score, reasons,
            affected=_head(top.get("affected_projects") or []),
            constraint=(
                {
                    "label": top.get("capability"),
                    "detail": top.get("recommended_action") or f"{top.get('gap')} units short",
                    "affected": _head(top.get("affected_goals") or []),
                }
                if top.get("capability") else None
            ),
            root_cause=f"demand exceeds supply by {top.get('gap')} units" if top.get("gap") else None,
            interventions=[top.get("recommended_action")] if top.get("recommended_action") else [],
            evidence_count=len(bottlenecks) + overloaded_count,
            state=state,
        )

    async def _domain_people(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        overloads = await resource_allocation_engine.overloads(
            db, organization_id=organization_id,
        )
        person_overloads = overloads.get("person_overloads") or []
        team_overloads = overloads.get("team_overloads") or []
        if not person_overloads and not team_overloads:
            return self._domain_row("people", "People", 80, ["no one committed over capacity"])
        score = _clamp(80 - 8 * len(person_overloads) - 5 * len(team_overloads))
        top = person_overloads[0] if person_overloads else (team_overloads[0] if team_overloads else {})
        detail = (
            f"committed {top.get('committed_hours')}h vs "
            f"{top.get('capacity_hours')}h weekly capacity"
            if top.get("committed_hours") is not None else ""
        )
        return self._domain_row(
            "people", "People", score,
            [
                f"{len(person_overloads)} people over committed weekly capacity"
            ],
            affected=[p.get("name") for p in _head(person_overloads, 3)],
            constraint={"label": top.get("name") or top.get("team_id"), "detail": detail, "affected": []},
            root_cause="open assigned tasks exceed weekly capacity",
            interventions=[
                f"rebalance open assignments for {p.get('name')}"
                for p in _head(person_overloads, 1)
            ],
            evidence_count=len(person_overloads) + len(team_overloads),
        )

    async def _domain_customers(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        healths = await customer_intelligence_engine.healths(
            db, organization_id=organization_id,
        )
        total = int(healths.get("total") or 0)
        if total == 0:
            return self._domain_row("customers", "Customers", 80, [_NEUTRAL_REASON])
        at_risk = int(healths.get("at_risk") or 0)
        concerned = int(healths.get("concerned") or 0)
        score = _clamp(80 - 12 * at_risk - 6 * concerned)
        rows = healths.get("health") or []
        worst = next((h for h in rows if h.get("state") == "at_risk"), None) or (
            rows[0] if rows else None
        )
        risk = await customer_intelligence_engine.risk(
            db, organization_id=organization_id,
        )
        commitments = risk.get("commitments_at_risk") or []
        return self._domain_row(
            "customers", "Customers", score,
            [f"{at_risk} of {total} customers at risk"]
            if at_risk else (["customer base stable"] if total else []),
            affected=[h.get("customer") for h in rows if h.get("state") == "at_risk"][:3],
            constraint=(
                {
                    "label": worst.get("customer"),
                    "detail": _head(worst.get("reasons") or [], 1)[0] if worst.get("reasons") else "",
                    "affected": [],
                }
                if worst and worst.get("score", 100) < 75 else None
            ),
            root_cause=(
                _head(commitments, 1)[0].get("summary")
                if commitments else None
            ),
            interventions=[
                c.get("summary") for c in _head(commitments, 3)
            ],
            evidence_count=total,
        )

    async def _domain_financial(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        perf = await business_performance_engine.performance(
            db, organization_id=organization_id, scope="org_wide",
        )
        dim = None
        for d in (perf or {}).get("health", {}).get("dimensions") or []:
            if d.get("key") == "financial":
                dim = d
                break
        if not dim:
            return self._domain_row("financial", "Financial", 80, [_NEUTRAL_REASON])
        behind = await business_performance_engine.behind_target(
            db, organization_id=organization_id,
        )
        what_to_do = behind.get("what_to_do") if behind else None
        interventions = []
        for item in _head(what_to_do, 3):
            interventions.append(
                item.get("title") if isinstance(item, dict) else str(item)
            )
        return self._domain_row(
            "financial", "Financial", int(dim.get("score") or 0),
            _head(dim.get("reasons") or [], 2),
            positives=_head(dim.get("positives") or [], 1),
            constraint=(
                {
                    "label": f"target {behind.get('target', {}).get('metric_key', '')} behind",
                    "detail": behind.get("summary") or "",
                    "affected": [],
                }
                if behind and behind.get("gap", 0) > 0 else None
            ),
            root_cause=behind.get("summary") if behind else None,
            interventions=interventions,
            evidence_count=int(dim.get("evidence_count") or 0),
        )

    async def _domain_knowledge(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        topic_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(KnowledgeTopic)
                    .where(KnowledgeTopic.organization_id == organization_id)
                )
            ).scalar() or 0
        )
        open_recs = list(
            (
                await db.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.organization_id == organization_id,
                        KnowledgeRecommendation.status == "active",
                    )
                    .order_by(KnowledgeRecommendation.updated_at.desc())
                    .limit(MAX_MEMORY_SHOWN)
                )
            ).scalars().all()
        )
        open_insights = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(KnowledgeIntelInsight)
                    .where(
                        KnowledgeIntelInsight.organization_id == organization_id,
                        KnowledgeIntelInsight.status == "active",
                    )
                )
            ).scalar() or 0
        )
        if topic_count == 0 and not open_recs:
            return self._domain_row("knowledge", "Knowledge", 80, [_NEUTRAL_REASON])
        score = _clamp(80 - 5 * min(len(open_recs), 4) - 3 * min(open_insights, 4))
        return self._domain_row(
            "knowledge", "Knowledge", score,
            (
                [f"{len(open_recs)} open knowledge recommendations"]
                if open_recs else ["knowledge base is current"]
            ),
            affected=[],
            constraint=(
                {
                    "label": "open knowledge recommendations",
                    "detail": _head(open_recs, 1)[0].reason[:240] if open_recs else "",
                    "affected": [],
                }
                if open_recs else None
            ),
            root_cause="open knowledge work items not yet acted on" if open_recs else None,
            interventions=[
                r.reason[:120] for r in _head(open_recs, 2)
            ],
            evidence_count=topic_count,
        )

    def _domain_row(
        self, key: str, label: str, score: int,
        reasons: list[str], *,
        positives: Optional[list[str]] = None,
        affected: Optional[list[str]] = None,
        constraint: Optional[dict] = None,
        root_cause: Optional[str] = None,
        interventions: Optional[list[str]] = None,
        evidence_count: int = 0,
        state: Optional[str] = None,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "score": _clamp(score),
            "state": state or _band(score),
            "reasons": _head(reasons, 3),
            "positives": _head(positives or [], 2),
            "affected": _head(affected or [], MAX_STEP_ENTITIES),
            "constraint": constraint,
            "root_cause": root_cause,
            "interventions": _head(interventions or [], 3),
            "evidence_count": evidence_count,
        }

    async def _compute_health(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """The deterministic composed company health assessment (no writes)."""
        domains: list[dict[str, Any]] = []
        for key in COMPANY_HEALTH_DOMAINS:
            helper = getattr(self, f"_domain_{key}")
            domains.append(await helper(db, organization_id=organization_id))

        score = _clamp(
            sum(
                (DOMAIN_WEIGHTS.get(d["key"], 0.0) * d["score"] for d in domains)
            )
        )
        worst = min(domains, key=lambda d: d["score"])
        _STATE_ORDER = ("healthy", "concerned", "at_risk", "critical")
        company_state = _band(score)
        if worst["state"] in ("at_risk", "critical") and company_state == "healthy":
            company_state = "concerned"
        if worst["state"] == "critical" and _STATE_ORDER.index(company_state) < 3:
            company_state = "at_risk"
        primary_constraint = None
        if worst["score"] < 75 and worst.get("constraint"):
            primary_constraint = {
                "domain": worst["key"],
                "domain_label": worst["label"],
                "score": worst["score"],
                "state": worst["state"],
                **worst["constraint"],
                "root_cause": worst.get("root_cause"),
                "interventions": worst.get("interventions") or [],
            }
        summary = self._summary_narrative(domains, primary_constraint)
        attention: list[dict[str, Any]] = []
        for d in sorted(domains, key=lambda d: d["score"]):
            if d["score"] < 75:
                attention.append({
                    "priority": _rank(d["state"]),
                    "kind": f"{d['key']}_health",
                    "title": f"{d['label']} is {d['state']} ({d['score']}/100)",
                    "why": _head(d["reasons"], 1)[0] if d["reasons"] else "",
                })
            if len(attention) >= MAX_FOCUS_ITEMS:
                break
        return {
            "domains": domains,
            "company_score": score,
            "company_state": company_state,
            "primary_constraint": primary_constraint,
            "attention": attention,
            "summary": summary,
        }

    def _summary_narrative(
        self, domains: list[dict[str, Any]], primary_constraint: Optional[dict],
    ) -> str:
        parts: list[str] = []
        if primary_constraint:
            parts.append(
                f"biggest company constraint: {primary_constraint['domain_label']} "
                f"({primary_constraint['score']}/100) — {primary_constraint.get('label')}"
            )
            if primary_constraint.get("root_cause"):
                parts.append(f"root cause: {primary_constraint['root_cause'][:200]}")
        concerned = [d for d in domains if d["state"] in ("at_risk", "critical", "concerned")]
        if not concerned:
            parts.append("all company domains are healthy")
        else:
            parts.append(
                f"{len(concerned)} of {len(domains)} domains need attention: "
                + ", ".join(d["key"] for d in concerned)
            )
        return " | ".join(parts)

    async def refresh(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Change-driven recompute of the company health trail (exact-once).

        Called from the event bridge for every meaningful upstream event;
        persists one CompanyHealthHistory row per unique source event so
        "What changed?" stays deterministic over replays.
        """
        source_event_id = getattr(event, "id", None)
        event_name = getattr(event, "name", "") or ""
        if not source_event_id:
            return None
        existing = (
            await db.execute(
                select(CompanyHealthHistory).where(
                    CompanyHealthHistory.organization_id == organization_id,
                    CompanyHealthHistory.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return None
        assessment = await self._compute_health(
            db, organization_id=organization_id,
        )
        row = CompanyHealthHistory(
            organization_id=organization_id,
            company_score=assessment["company_score"],
            company_state=assessment["company_state"],
            primary_constraint_json=assessment["primary_constraint"],
            domains_json=assessment["domains"],
            attention_json=assessment["attention"],
            summary_narrative=assessment["summary"],
            event_name=event_name,
            source_event_id=str(source_event_id),
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(row)
        return {
            "company_score": assessment["company_score"],
            "company_state": assessment["company_state"],
            "source_event_id": str(source_event_id),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def health(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """The live company health: latest persisted assessment + trail."""
        rows = list(
            (
                await db.execute(
                    select(CompanyHealthHistory)
                    .where(CompanyHealthHistory.organization_id == organization_id)
                    .order_by(CompanyHealthHistory.occurred_at.desc())
                    .limit(MAX_HISTORY_SHOWN)
                )
            ).scalars().all()
        )
        latest = rows[0] if rows else None
        if latest is None:
            assessment = await self._compute_health(
                db, organization_id=organization_id,
            )
            return {
                "advisory_only": True,
                "company_score": assessment["company_score"],
                "company_state": assessment["company_state"],
                "domains": assessment["domains"],
                "primary_constraint": assessment["primary_constraint"],
                "attention": assessment["attention"],
                "summary": assessment["summary"],
                "history": [],
                "generated_at": _iso(datetime.now(timezone.utc)),
            }
        return {
            "advisory_only": True,
            "company_score": latest.company_score,
            "company_state": latest.company_state,
            "domains": latest.domains_json or [],
            "primary_constraint": latest.primary_constraint_json,
            "attention": latest.attention_json or [],
            "summary": latest.summary_narrative,
            "history": [
                {
                    "occurred_at": _iso(r.occurred_at),
                    "company_score": r.company_score,
                    "company_state": r.company_state,
                    "event_name": r.event_name,
                    "summary": r.summary_narrative,
                }
                for r in rows
            ],
            "generated_at": _iso(latest.occurred_at),
        }

    # ------------------------------------------------------------------
    # 3. Root-cause chains
    # ------------------------------------------------------------------

    async def root_cause(
        self, db: AsyncSession, *, organization_id: str, problem: str,
    ) -> dict[str, Any]:
        """Walk a business problem down to people and capability constraints.

        business problem -> metric -> driver -> customer impact -> project ->
        task/dependency -> capacity constraint -> people/capability.
        """
        problem = (problem or "").strip()
        chain: list[dict[str, Any]] = []
        matched_on = "none"

        behind = await business_performance_engine.behind_target(
            db, organization_id=organization_id,
            metric_key=problem or None,
        )
        if behind and behind.get("target"):
            matched_on = "business_target"
            target = behind.get("target") or {}
            chain.append({
                "layer": "business_problem",
                "label": behind.get("summary") or target.get("metric_key", "metric"),
                "detail": f"{target.get('metric_key')} target not on track",
                "references": [],
            })
            chain.append({
                "layer": "metric",
                "label": target.get("metric_key", ""),
                "detail": f"gap {behind.get('gap')}",
                "references": [],
            })
            for driver in _head(behind.get("drivers") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "layer": "driver",
                    "label": (
                        driver.get("title") if isinstance(driver, dict) else str(driver)
                    ),
                    "detail": (
                        driver.get("kind") if isinstance(driver, dict) else ""
                    ),
                    "references": [],
                })
            for customer in _head(behind.get("customers") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "layer": "customer_impact",
                    "label": (
                        customer.get("customer") if isinstance(customer, dict) else str(customer)
                    ),
                    "detail": (
                        customer.get("impact") or customer.get("state")
                        if isinstance(customer, dict) else ""
                    ),
                    "references": [],
                })
            for project in _head(behind.get("projects") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "layer": "project",
                    "label": (
                        project.get("name") if isinstance(project, dict) else str(project)
                    ),
                    "detail": (
                        project.get("health_status") if isinstance(project, dict) else ""
                    ),
                    "references": [],
                })
            for dep in _head(behind.get("dependencies") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "layer": "task_dependency",
                    "label": (
                        dep.get("title") if isinstance(dep, dict) else str(dep)
                    ),
                    "detail": (
                        dep.get("status") if isinstance(dep, dict) else ""
                    ),
                    "references": [],
                })
            for cap in _head(behind.get("capacity") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "layer": "capacity_constraint",
                    "label": (
                        cap.get("capability") if isinstance(cap, dict) else str(cap)
                    ),
                    "detail": (
                        cap.get("gap") if isinstance(cap, dict) else ""
                    ),
                    "references": [],
                })
            chain.append({
                "layer": "people_capability",
                "label": "capability demand vs supply",
                "detail": "people with this capability are committed beyond capacity",
                "references": [],
            })
            what_to_do = behind.get("what_to_do") or []
            return {
                "problem": problem,
                "matched_on": matched_on,
                "chain": chain,
                "resolution_hint": [
                    item.get("title") if isinstance(item, dict) else str(item)
                    for item in _head(what_to_do, 3)
                ],
                "advisory_only": True,
            }

        project = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == organization_id,
                    (Project.id == problem) | (Project.name == problem),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if project is not None:
            matched_on = "project"
            detail = await execution_engine.project_detail(
                db, organization_id=organization_id, project_id=project.id,
            ) or {}
            state = detail.get("health_status") or "unknown"
            chain.append({
                "layer": "business_problem",
                "label": f"{project.name} is {state}",
                "detail": detail.get("primary_cause") or "",
                "references": [],
            })
            chain.append({
                "layer": "metric",
                "label": "delivery health",
                "detail": f"health score {detail.get('health_score')}",
                "references": [],
            })
            for goal in _head(detail.get("goal_chain") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "layer": "strategy",
                    "label": (
                        goal.get("title") if isinstance(goal, dict) else str(goal)
                    ),
                    "detail": "",
                    "references": [],
                })
            for cap in _head(detail.get("capacity_constraints") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "layer": "capacity_constraint",
                    "label": cap.get("capability") if isinstance(cap, dict) else str(cap),
                    "detail": cap.get("gap") if isinstance(cap, dict) else "",
                    "references": [],
                })
            commitments = list(
                (
                    await db.execute(
                        select(CustomerCommitment).where(
                            CustomerCommitment.organization_id == organization_id,
                            CustomerCommitment.project_id == project.id,
                        ).limit(MAX_STEP_ENTITIES)
                    )
                ).scalars().all()
            )
            for c in commitments:
                chain.append({
                    "layer": "customer_impact",
                    "label": c.summary,
                    "detail": f"commitment {c.status}",
                    "references": [],
                })
            chain.append({
                "layer": "people_capability",
                "label": "project capacity demand",
                "detail": "the capabilities this project demands are the people constraint",
                "references": [],
            })
            return {
                "problem": problem,
                "matched_on": matched_on,
                "chain": chain,
                "resolution_hint": _head(detail.get("primary_cause") and [detail["primary_cause"]], 1),
                "advisory_only": True,
            }

        assess = await resource_allocation_engine.assess(
            db, organization_id=organization_id,
            capability=problem,
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
        )
        if assess and assess.get("is_bottleneck"):
            matched_on = "capability"
            chain.append({
                "layer": "business_problem",
                "label": f"{problem} is a company bottleneck",
                "detail": assess.get("gap_reasons") or "",
                "references": [],
            })
            for project in _head(
                _dict_list(assess.get("affected_projects"), "ids"),
                MAX_STEP_ENTITIES,
            ):
                chain.append({
                    "layer": "project",
                    "label": project.get("name") if isinstance(project, dict) else str(project),
                    "detail": "",
                    "references": [],
                })
            for goal in _head(
                _dict_list(assess.get("affected_goals"), "goals"),
                MAX_STEP_ENTITIES,
            ):
                chain.append({
                    "layer": "strategy",
                    "label": goal.get("title") if isinstance(goal, dict) else str(goal),
                    "detail": "",
                    "references": [],
                })
            for c in _head(assess.get("affected_commitments") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "layer": "customer_impact",
                    "label": c.get("summary") if isinstance(c, dict) else str(c),
                    "detail": "",
                    "references": [],
                })
            chain.append({
                "layer": "capacity_constraint",
                "label": problem,
                "detail": f"gap {assess.get('gap')} units over the window",
                "references": [],
            })
            chain.append({
                "layer": "people_capability",
                "label": problem,
                "detail": "demand exceeds the people who can do this work",
                "references": [],
            })
            return {
                "problem": problem,
                "matched_on": matched_on,
                "chain": chain,
                "resolution_hint": [assess.get("gap_reasons") or ""],
                "advisory_only": True,
            }

        return {
            "problem": problem,
            "matched_on": matched_on,
            "chain": [],
            "resolution_hint": [
                "nothing matched yet — the company layer composes evidence; "
                "record business outcomes, targets, projects and capacity to deepen it"
            ],
            "advisory_only": True,
        }

    # ------------------------------------------------------------------
    # 4. Impact propagation
    # ------------------------------------------------------------------

    async def impact(
        self, db: AsyncSession, *, organization_id: str,
        subject_type: str, subject_id: str,
    ) -> dict[str, Any]:
        """Propagate a subject change across the company (bounded, deterministic).

        person / project / capability / customer / goal -> execution ->
        strategy -> customers -> business performance.
        """
        subject_type = (subject_type or "").strip().lower()
        subject_id = (subject_id or "").strip()
        chain: list[dict[str, Any]] = []
        label = subject_id

        if subject_type == "person":
            overloads = await resource_allocation_engine.overloads(
                db, organization_id=organization_id,
            )
            person = next(
                (
                    p for p in (overloads.get("person_overloads") or [])
                    if p.get("person_id") == subject_id
                ),
                None,
            )
            tasks = list(
                (
                    await db.execute(
                        select(Task.project_id).where(
                            Task.organization_id == organization_id,
                            Task.assignee_id == subject_id,
                            Task.status.in_(("active", "blocked", "pending", "todo", "in_progress", "in_review")),
                        ).limit(MAX_PROJECT_SCAN)
                    )
                ).scalars().all()
            )
            project_ids = sorted({p for p in tasks if p})
            label = person.get("name") if person else subject_id
            chain.append({
                "step": "people",
                "label": label,
                "detail": (
                    f"committed {person.get('committed_hours')}h of "
                    f"{person.get('capacity_hours')}h weekly capacity"
                    if person else f"{len(project_ids)} active project commitments"
                ),
            })
            project_names = await self._project_names(
                db, organization_id=organization_id, project_ids=project_ids,
            )
            chain.append({
                "step": "execution",
                "label": "project capacity coverage",
                "detail": f"directly committed to {', '.join(project_names[:3]) or 'no active projects'}",
            })
            for pid in _head(project_ids, MAX_STEP_ENTITIES):
                detail = await execution_engine.project_detail(
                    db, organization_id=organization_id, project_id=pid,
                ) or {}
                for goal in _head(detail.get("goal_chain") or [], 1):
                    chain.append({
                        "step": "strategy",
                        "label": goal.get("title") if isinstance(goal, dict) else str(goal),
                        "detail": f"project {detail.get('name')} serves this goal",
                    })
            commitments = list(
                (
                    await db.execute(
                        select(CustomerCommitment).where(
                            CustomerCommitment.organization_id == organization_id,
                            CustomerCommitment.project_id.in_(project_ids or [""]),
                            CustomerCommitment.status != "delivered",
                        ).limit(MAX_STEP_ENTITIES)
                    )
                ).scalars().all()
            )
            for c in commitments:
                chain.append({
                    "step": "customers",
                    "label": c.summary,
                    "detail": f"commitment {c.status}",
                })
            if not commitments:
                chain.append({
                    "step": "customers",
                    "label": "no open customer commitments linked",
                    "detail": "",
                })

        elif subject_type == "project":
            detail = await execution_engine.project_detail(
                db, organization_id=organization_id, project_id=subject_id,
            )
            if detail is None:
                return {
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "label": subject_id,
                    "chain": [],
                    "consequence_summary": "project not found",
                    "advisory_only": True,
                }
            label = detail.get("name") or subject_id
            chain.append({
                "step": "execution",
                "label": f"{label} is {detail.get('health_status')}",
                "detail": detail.get("primary_cause") or "",
            })
            for goal in _head(detail.get("goal_chain") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "step": "strategy",
                    "label": goal.get("title") if isinstance(goal, dict) else str(goal),
                    "detail": "",
                })
            commitments = list(
                (
                    await db.execute(
                        select(CustomerCommitment).where(
                            CustomerCommitment.organization_id == organization_id,
                            CustomerCommitment.project_id == subject_id,
                            CustomerCommitment.status != "delivered",
                        ).limit(MAX_STEP_ENTITIES)
                    )
                ).scalars().all()
            )
            for c in commitments:
                chain.append({
                    "step": "customers",
                    "label": c.summary,
                    "detail": f"commitment {c.status} expected {_iso(c.expected_at)}",
                })
            for cap in _head(detail.get("capacity_constraints") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "step": "capacity",
                    "label": cap.get("capability") if isinstance(cap, dict) else str(cap),
                    "detail": "this project contributes to the capability demand",
                })

        elif subject_type == "capability":
            assess = await resource_allocation_engine.assess(
                db, organization_id=organization_id,
                capability=subject_id,
                window_start=date.today(),
                window_end=date.today() + timedelta(days=30),
            )
            if assess is None:
                return {
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "label": subject_id,
                    "chain": [],
                    "consequence_summary": "capability not assessed",
                    "advisory_only": True,
                }
            label = subject_id
            chain.append({
                "step": "capacity",
                "label": f"{subject_id} utilization {assess.get('utilization')}",
                "detail": f"gap {assess.get('gap')} units over the window",
            })
            for project in _head(
                _dict_list(assess.get("affected_projects"), "ids"),
                MAX_STEP_ENTITIES,
            ):
                chain.append({
                    "step": "execution",
                    "label": project.get("name") if isinstance(project, dict) else str(project),
                    "detail": "",
                })
            for goal in _head(
                _dict_list(assess.get("affected_goals"), "goals"),
                MAX_STEP_ENTITIES,
            ):
                chain.append({
                    "step": "strategy",
                    "label": goal.get("title") if isinstance(goal, dict) else str(goal),
                    "detail": "",
                })
            for c in _head(assess.get("affected_commitments") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "step": "customers",
                    "label": c.get("summary") if isinstance(c, dict) else str(c),
                    "detail": "",
                })

        elif subject_type == "customer":
            health = await customer_intelligence_engine.health(
                db, organization_id=organization_id, customer_id=subject_id,
            )
            if health is None:
                return {
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "label": subject_id,
                    "chain": [],
                    "consequence_summary": "customer not found",
                    "advisory_only": True,
                }
            label = health.get("customer") or subject_id
            chain.append({
                "step": "customers",
                "label": f"{label} is {health.get('state')}",
                "detail": _head(health.get("reasons") or [], 1)[0] if health.get("reasons") else "",
            })
            commitments = list(
                (
                    await db.execute(
                        select(CustomerCommitment).where(
                            CustomerCommitment.organization_id == organization_id,
                            CustomerCommitment.customer_id == subject_id,
                            CustomerCommitment.status != "delivered",
                        ).limit(MAX_STEP_ENTITIES)
                    )
                ).scalars().all()
            )
            project_ids: list[str] = []
            for c in commitments:
                chain.append({
                    "step": "execution",
                    "label": c.summary,
                    "detail": f"commitment {c.status}",
                })
                if c.project_id:
                    project_ids.append(c.project_id)
            for pid in _head(project_ids, MAX_STEP_ENTITIES):
                detail = await execution_engine.project_detail(
                    db, organization_id=organization_id, project_id=pid,
                ) or {}
                for goal in _head(detail.get("goal_chain") or [], 1):
                    chain.append({
                        "step": "strategy",
                        "label": goal.get("title") if isinstance(goal, dict) else str(goal),
                        "detail": f"delivery project {detail.get('name')}",
                    })

        elif subject_type == "goal":
            portfolio = await strategic_execution_engine.portfolio(
                db, organization_id=organization_id,
            )
            goal = next(
                (
                    g for g in (portfolio.get("goals") or [])
                    if g.get("goal_id") == subject_id
                ),
                None,
            )
            if goal is None:
                return {
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "label": subject_id,
                    "chain": [],
                    "consequence_summary": "goal not found",
                    "advisory_only": True,
                }
            label = goal.get("title") or subject_id
            chain.append({
                "step": "strategy",
                "label": f"{label} coverage {goal.get('coverage')} health {goal.get('health')}",
                "detail": goal.get("primary_reason") or "",
            })
            for project in _head(goal.get("active_projects") or [], MAX_STEP_ENTITIES):
                chain.append({
                    "step": "execution",
                    "label": project.get("name") if isinstance(project, dict) else str(project),
                    "detail": "",
                })
            commitments = list(
                (
                    await db.execute(
                        select(CustomerCommitment)
                        .join(
                            Project,
                            and_(
                                Project.organization_id == organization_id,
                                CustomerCommitment.project_id == Project.id,
                            ),
                        )
                        .where(CustomerCommitment.organization_id == organization_id)
                        .limit(MAX_STEP_ENTITIES)
                    )
                ).scalars().all()
            )
            for c in commitments:
                chain.append({
                    "step": "customers",
                    "label": c.summary,
                    "detail": f"commitment {c.status}",
                })
            trace = await resource_allocation_engine.traceability(
                db, organization_id=organization_id,
            )
            for cap in _head(trace.get("capabilities") or [], 1):
                for g in _head(cap.get("goals") or [], 3):
                    if g.get("goal_id") == subject_id:
                        chain.append({
                            "step": "capacity",
                            "label": cap.get("capability"),
                            "detail": f"{g.get('share_pct')} of demand serves this goal",
                        })
                        break

        else:
            return {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "label": subject_id,
                "chain": [],
                "consequence_summary": (
                    "subject_type must be person | project | capability | customer | goal"
                ),
                "advisory_only": True,
            }

        consequence_summary = "; ".join(
            f"{s['step']}: {s['label']}" for s in _head(chain, 5)
        ) or "no propagation found"
        return {
            "subject_type": subject_type,
            "subject_id": subject_id,
            "label": label,
            "chain": chain,
            "consequence_summary": consequence_summary[:600],
            "advisory_only": True,
        }

    async def _project_names(
        self, db: AsyncSession, *, organization_id: str, project_ids: list[str],
    ) -> list[str]:
        if not project_ids:
            return []
        rows = list(
            (
                await db.execute(
                    select(Project.id, Project.name).where(
                        Project.organization_id == organization_id,
                        Project.id.in_(project_ids),
                    )
                )
            ).all()
        )
        by_id = {r[0]: r[1] for r in rows}
        return [by_id.get(pid, pid) for pid in project_ids]

    # ------------------------------------------------------------------
    # 5. Universal recommendation queue
    # ------------------------------------------------------------------

    async def recommendations(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """The company-level recommendation queue: every item carries its
        impact, confidence, owner and expected improvement — and nothing
        executes without a human."""
        items: list[dict[str, Any]] = []

        for item in _head(
            await strategic_execution_engine.focus(db, organization_id=organization_id),
            MAX_FOCUS_ITEMS,
        ):
            items.append({
                "rank": 1,
                "source": "strategy",
                "kind": "strategic_focus",
                "title": f"Focus on '{item.get('title')}'",
                "why": item.get("why"),
                "impact_label": f"goal coverage {item.get('coverage')}% — health {item.get('health')}",
                "confidence": "high",
                "owner_label": "Executive",
                "expected_improvement": "raise goal coverage toward target",
                "evidence_ref": f"strategy/focus/{item.get('goal_id')}",
            })

        for item in _head(
            (await execution_engine.execution_next(
                db, organization_id=organization_id,
            )).get("items") or [], 5,
        ):
            items.append({
                "rank": _rank(item.get("priority"), 2),
                "source": "execution",
                "kind": item.get("kind") or "execution",
                "title": item.get("title"),
                "why": item.get("reason"),
                "impact_label": f"project {item.get('project_name')}",
                "confidence": "medium",
                "owner_label": item.get("project_name"),
                "expected_improvement": "restore execution health",
                "evidence_ref": "execution/next",
            })

        capacity = await resource_allocation_engine.center(
            db, organization_id=organization_id,
        )
        top = capacity.get("top_constraint") or {}
        if top.get("capability"):
            items.append({
                "rank": 1,
                "source": "capacity",
                "kind": "capacity_constraint",
                "title": f"Resolve {top.get('capability')} capacity constraint",
                "why": top.get("recommended_action"),
                "impact_label": (
                    f"gap {top.get('gap')} units at {top.get('utilization')} "
                    f"utilization ({top.get('window_start')} - {top.get('window_end')})"
                ),
                "confidence": "high",
                "owner_label": "Leadership",
                "expected_improvement": "clear the company's biggest capacity bottleneck",
                "evidence_ref": "capacity/top-constraint",
            })
        for rec in _head(capacity.get("recommendations") or [], 3):
            items.append({
                "rank": 2,
                "source": "capacity",
                "kind": "capacity",
                "title": (
                    (rec.get("title") if isinstance(rec, dict) else str(rec))
                    or (rec.get("action") if isinstance(rec, dict) else "")
                ),
                "why": rec.get("why") if isinstance(rec, dict) else "",
                "impact_label": "",
                "confidence": "medium",
                "owner_label": "Leadership",
                "expected_improvement": "balance supply and demand",
                "evidence_ref": "capacity/center",
            })

        center = await coordination_engine.center(
            db, organization_id=organization_id, access=_ORG_WIDE,
        )
        for rec in _head(center.get("recommendations") or [], 5):
            items.append({
                "rank": _rank(rec.get("kind"), 3),
                "source": "coordination",
                "kind": rec.get("kind"),
                "title": rec.get("summary"),
                "why": "; ".join(str(w) for w in _head(rec.get("why") or [], 2)),
                "impact_label": f"project {rec.get('project_name')}" if rec.get("project_name") else "",
                "confidence": str(rec.get("confidence") or "medium"),
                "owner_label": rec.get("project_name"),
                "expected_improvement": "unblock coordination flow",
                "evidence_ref": f"coordination/incident/{rec.get('incident_id')}",
            })

        risk = await customer_intelligence_engine.risk(
            db, organization_id=organization_id,
        )
        for c in _head(risk.get("commitments_at_risk") or [], 3):
            items.append({
                "rank": 2,
                "source": "customer",
                "kind": "customer_risk",
                "title": f"Commitment at risk: {c.get('summary')}",
                "why": f"delivery project {c.get('project') or 'unknown'} is {c.get('project_health')}",
                "impact_label": f"customer {c.get('customer')}",
                "confidence": "medium",
                "owner_label": c.get("customer"),
                "expected_improvement": "protect the customer commitment",
                "evidence_ref": f"customer/commitment/{c.get('commitment_id')}",
            })

        behind = await business_performance_engine.behind_target(
            db, organization_id=organization_id,
        )
        if behind and behind.get("target"):
            target = behind.get("target") or {}
            items.append({
                "rank": 2,
                "source": "business",
                "kind": "commercial",
                "title": f"Close the gap on {target.get('metric_key')}",
                "why": behind.get("summary"),
                "impact_label": f"gap {behind.get('gap')}",
                "confidence": "high",
                "owner_label": "Executive",
                "expected_improvement": "get the target back on track",
                "evidence_ref": "business/behind-target",
            })
        for rec in _head(
            (await business_performance_engine.recommendations(
                db, organization_id=organization_id,
            )).get("recommendations") or [], 3,
        ):
            items.append({
                "rank": 3,
                "source": "business",
                "kind": rec.get("kind") or "business",
                "title": rec.get("title"),
                "why": rec.get("why"),
                "impact_label": "",
                "confidence": "medium",
                "owner_label": "Executive",
                "expected_improvement": "improve business performance",
                "evidence_ref": "business/recommendations",
            })

        open_recs = list(
            (
                await db.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.organization_id == organization_id,
                        KnowledgeRecommendation.status == "active",
                    )
                    .order_by(KnowledgeRecommendation.updated_at.desc())
                    .limit(3)
                )
            ).scalars().all()
        )
        for r in open_recs:
            items.append({
                "rank": 4,
                "source": "knowledge",
                "kind": "knowledge",
                "title": f"Knowledge: {r.reason[:160]}",
                "why": f"confidence {r.confidence}, risk {r.risk}",
                "impact_label": "",
                "confidence": str(r.confidence or "medium"),
                "owner_label": "Knowledge owner",
                "expected_improvement": "keep organizational knowledge current",
                "evidence_ref": f"knowledge/recommendation/{r.id}",
            })

        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for item in sorted(
            items, key=lambda i: (i["rank"], i["source"], i["title"]),
        ):
            key = (item["title"] or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            item.pop("rank", None)
            item["key"] = f"{item['source']}:{len(deduped) + 1:02d}"
            deduped.append(item)
            if len(deduped) >= MAX_COMPANY_RECOMMENDATIONS:
                break

        return {
            "advisory_only": True,
            "total": len(deduped),
            "recommendations": deduped,
            "note": (
                "advisory-first: nothing in this queue executes without human "
                "approval — approve an item to record the decision"
            ),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    # ------------------------------------------------------------------
    # 6. Bounded what-if
    # ------------------------------------------------------------------

    async def what_if(
        self, db: AsyncSession, *, organization_id: str,
        scenario_type: str, payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Bounded deterministic consequences of a scenario. Never a
        prediction, never executed."""
        scenario_type = (scenario_type or "").strip().lower()
        consequences: list[dict[str, Any]] = []

        if scenario_type == "delay":
            project_id = (payload.get("project_id") or "").strip()
            days = max(1, min(int(payload.get("days") or 0), 90))
            impact = await strategic_execution_engine.impact(
                db, organization_id=organization_id,
                project_id=project_id, delay_days=days,
            )
            if impact is None:
                return self._what_if_response(
                    scenario_type, payload, [],
                    note="project not found for the delay scenario",
                )
            consequences.append({
                "label": f"project {impact.get('project_name')} delayed {days} days",
                "impact": impact.get("risk"),
                "detail": f"{impact.get('downstream_count')} downstream projects, "
                          f"{impact.get('milestone_count')} milestones touched",
                "confidence": "high",
            })
            for s in _head(impact.get("strategic_chain") or [], 2):
                consequences.append({
                    "label": f"goal {s.get('goal_title')}",
                    "impact": s.get("health_simulated"),
                    "detail": (
                        f"coverage {s.get('coverage_now')} -> {s.get('coverage_simulated')}"
                    ),
                    "confidence": "medium",
                })
            if impact.get("customer_commitments_at_risk"):
                consequences.append({
                    "label": f"{impact.get('customer_commitments_at_risk')} customer commitments",
                    "impact": "at_risk",
                    "detail": "commitments tied to the initiative may slip",
                    "confidence": "medium",
                })
            return self._what_if_response(
                scenario_type, payload, consequences,
                note=impact.get("bounds") or "bounded sensitivity — not a prediction",
                change={
                    "type": "delay",
                    "project_id": project_id,
                    "project_name": impact.get("project_name"),
                    "days": days,
                },
            )

        if scenario_type == "reallocate":
            capability = (payload.get("capability") or "").strip()
            from_project_id = (payload.get("from_project_id") or "").strip()
            to_project_id = (payload.get("to_project_id") or "").strip()
            units = max(1, min(int(payload.get("units") or 0), 1000))
            sim = await resource_allocation_engine.what_if(
                db, organization_id=organization_id,
                from_project_id=from_project_id,
                to_project_id=to_project_id,
                capability=capability,
                units=units,
            )
            if sim is None:
                return self._what_if_response(
                    scenario_type, payload, [],
                    note="reallocation needs both projects demanding the capability",
                )
            change = sim.get("change") or {}
            consequences.append({
                "label": (
                    f"move {change.get('units')} units of {change.get('capability')} "
                    f"from {change.get('from_project_name')} to {change.get('to_project_name')}"
                ),
                "impact": "medium",
                "detail": (
                    f"window {change.get('window_start')} - {change.get('window_end')}"
                ),
                "confidence": "high",
            })
            for g in _head(sim.get("goals_affected") or [], 3):
                consequences.append({
                    "label": f"goal {g.get('title')}",
                    "impact": g.get("direction"),
                    "detail": "goal coverage moves with the reallocation",
                    "confidence": "medium",
                })
            return self._what_if_response(
                scenario_type, payload, consequences,
                note=sim.get("not_a_prediction") or "bounded sensitivity — not a prediction",
                change=change,
            )

        if scenario_type == "hire":
            capability = (payload.get("capability") or "").strip()
            people = max(1, min(int(payload.get("people") or 0), 200))
            ramp_days = max(0, min(int(payload.get("ramp_days") or 0), 365))
            assess = await resource_allocation_engine.assess(
                db, organization_id=organization_id,
                capability=capability,
                window_start=date.today(),
                window_end=date.today() + timedelta(days=30),
            )
            if assess is None:
                return self._what_if_response(
                    scenario_type, payload, [],
                    note="capability has no demand assessment to compare against",
                )
            added_hours = people * 40.0
            gap_after = max(0.0, float(assess.get("gap") or 0) - added_hours)
            consequences.append({
                "label": f"hire {people} people for {capability}",
                "impact": "low" if gap_after == 0 else "medium",
                "detail": (
                    f"window gap {assess.get('gap')} -> {gap_after:.0f} units "
                    f"({added_hours:.0f}h of weekly capacity added)"
                ),
                "confidence": "medium",
            })
            for project in _head(
                _dict_list(assess.get("affected_projects"), "ids"), 2,
            ):
                consequences.append({
                    "label": f"project {project.get('name') if isinstance(project, dict) else project}",
                    "impact": "improves",
                    "detail": "capability demand becomes easier to cover",
                    "confidence": "medium",
                })
            consequences.append({
                "label": f"time to effect: {ramp_days} ramp days before productive",
                "impact": "medium",
                "detail": f"{ramp_days} ramp days before the capacity is productive",
                "confidence": "low",
            })
            return self._what_if_response(
                scenario_type, payload, consequences,
                note="hiring changes headcount and cost — the company layer only simulates capacity relief",
                change={
                    "type": "hire",
                    "capability": capability,
                    "people": people,
                    "ramp_days": ramp_days,
                },
            )

        return self._what_if_response(
            scenario_type, payload, [],
            note="scenario_type must be reallocate | delay | hire",
        )

    def _what_if_response(
        self, scenario_type: str, payload: dict[str, Any],
        consequences: list[dict[str, Any]], *,
        note: str = "",
        change: Optional[dict] = None,
    ) -> dict[str, Any]:
        return {
            "advisory_only": True,
            "scenario_type": scenario_type,
            "scenario": {
                **{k: v for k, v in payload.items() if k in (
                    "project_id", "days", "capability", "from_project_id",
                    "to_project_id", "units", "people", "ramp_days",
                )},
                **(change or {}),
            },
            "consequences": _head(consequences, MAX_WHATIF_CONSEQUENCES),
            "not_a_prediction": True,
            "note": note,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    # ------------------------------------------------------------------
    # 7. What changed
    # ------------------------------------------------------------------

    async def changes(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """The meaningful company-level deltas since the last assessment."""
        rows = list(
            (
                await db.execute(
                    select(CompanyHealthHistory)
                    .where(CompanyHealthHistory.organization_id == organization_id)
                    .order_by(CompanyHealthHistory.occurred_at.desc())
                    .limit(2)
                )
            ).scalars().all()
        )
        if len(rows) < 2:
            return {
                "advisory_only": True,
                "window": "insufficient_history",
                "changes": [{
                    "kind": "no_window",
                    "label": "no comparison window yet",
                    "why_matters": (
                        "the company health trail needs at least two assessments "
                        "before 'what changed' can be answered"
                    ),
                    "detail": (
                        f"{len(rows)} assessment recorded — keep recording "
                        "business activity and the window opens"
                    ),
                }],
                "generated_at": _iso(datetime.now(timezone.utc)),
            }
        prev, latest = rows[1], rows[0]
        prev_domains = {d["key"]: d for d in (prev.domains_json or [])}
        now_domains = {d["key"]: d for d in (latest.domains_json or [])}
        out: list[dict[str, Any]] = []
        for key in COMPANY_HEALTH_DOMAINS:
            a = prev_domains.get(key)
            b = now_domains.get(key)
            if not a or not b:
                continue
            delta = int(b.get("score") or 0) - int(a.get("score") or 0)
            state_shift = b.get("state") != a.get("state")
            if not state_shift and abs(delta) < 3:
                continue
            if delta > 0:
                kind = "improved"
            elif delta < 0:
                kind = "declined"
            else:
                kind = "state_shift"
            out.append({
                "kind": kind,
                "domain": key,
                "label": f"{b.get('label')} {a.get('state')} -> {b.get('state')} "
                         f"({a.get('score')} -> {b.get('score')})",
                "why_matters": _head(b.get("reasons") or [], 1)[0] if b.get("reasons") else "",
                "detail": _head(b.get("reasons") or [], 2),
                "from_score": a.get("score"),
                "to_score": b.get("score"),
            })
        pc_prev = prev.primary_constraint_json or {}
        pc_now = latest.primary_constraint_json or {}
        if pc_prev.get("label") != pc_now.get("label"):
            domain_key = pc_now.get("domain") or pc_prev.get("domain")
            a = prev_domains.get(domain_key) or {}
            b = now_domains.get(domain_key) or {}
            if pc_now.get("label"):
                out.append({
                    "kind": "new_constraint",
                    "domain": pc_now.get("domain"),
                    "label": f"new company constraint: {pc_now.get('label')}",
                    "why_matters": pc_now.get("detail") or "the company's biggest constraint changed",
                    "detail": _head(pc_now.get("interventions") or [], 2),
                    "from_score": (
                        pc_prev.get("score")
                        if pc_prev.get("score") is not None else a.get("score")
                    ),
                    "to_score": (
                        pc_now.get("score")
                        if pc_now.get("score") is not None else b.get("score")
                    ),
                })
            elif pc_prev.get("label"):
                out.append({
                    "kind": "resolved_constraint",
                    "domain": pc_prev.get("domain"),
                    "label": f"constraint resolved: {pc_prev.get('label')}",
                    "why_matters": "the biggest company constraint cleared",
                    "detail": [],
                    "from_score": (
                        pc_prev.get("score")
                        if pc_prev.get("score") is not None else a.get("score")
                    ),
                    "to_score": (
                        pc_now.get("score")
                        if pc_now.get("score") is not None else b.get("score")
                    ),
                })
        order = {"new_constraint": 0, "resolved_constraint": 1, "declined": 2, "state_shift": 3, "improved": 4}
        out = sorted(
            out, key=lambda c: (order.get(c["kind"], 5), c.get("domain", "")),
        )[:MAX_CHANGES_SHOWN]
        return {
            "advisory_only": True,
            "window": f"{_iso(prev.occurred_at)} -> {_iso(latest.occurred_at)}",
            "company_score_before": prev.company_score,
            "company_score_after": latest.company_score,
            "company_state_before": prev.company_state,
            "company_state_after": latest.company_state,
            "changes": out,
            "generated_at": _iso(latest.occurred_at),
        }

    # ------------------------------------------------------------------
    # 8. Company memory (decision -> reason -> action -> outcome -> learning)
    # ------------------------------------------------------------------

    async def memory(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """The governed decision history and what the company learned."""
        decisions = list(
            (
                await db.execute(
                    select(CompanyDecision)
                    .where(CompanyDecision.organization_id == organization_id)
                    .order_by(CompanyDecision.updated_at.desc())
                    .limit(MAX_MEMORY_SHOWN)
                )
            ).scalars().all()
        )
        learnings = [
            {
                "decision_id": d.decision_id,
                "title": d.title,
                "kind": d.kind,
                "outcome_kind": d.outcome_kind,
                "effectiveness": d.effectiveness,
                "lesson": d.lesson,
                "recorded_at": _iso(d.updated_at),
            }
            for d in decisions
            if d.lesson
        ]
        return {
            "advisory_only": True,
            "total_decisions": len(decisions),
            "decisions": [
                {
                    "decision_id": d.decision_id,
                    "kind": d.kind,
                    "title": d.title,
                    "recommendation_key": d.recommendation_key,
                    "state": d.state,
                    "impact_label": d.impact_label,
                    "expected_improvement": d.expected_improvement,
                    "confidence": d.confidence,
                    "owner_label": d.owner_label,
                    "approver_label": d.approver_label,
                    "approved_at": _iso(d.approved_at),
                    "executed_at": _iso(d.executed_at),
                    "outcome_kind": d.outcome_kind,
                    "effectiveness": d.effectiveness,
                    "lesson": d.lesson,
                    "note": d.note,
                    "updated_at": _iso(d.updated_at),
                }
                for d in decisions
            ],
            "learnings": learnings,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    # ------------------------------------------------------------------
    # 9. Governed writes (human approval only)
    # ------------------------------------------------------------------

    async def record_decision(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """A human approved or declined a company recommendation. Exact-once."""
        source_event_id = str(getattr(event, "id", ""))
        decision_id = (payload.get("decision_id") or "").strip()
        if not source_event_id or not decision_id:
            return None
        existing = (
            await db.execute(
                select(CompanyDecision).where(
                    CompanyDecision.organization_id == organization_id,
                    CompanyDecision.decision_id == decision_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return self._decision_payload(existing)
        dup = (
            await db.execute(
                select(CompanyDecision).where(
                    CompanyDecision.organization_id == organization_id,
                    CompanyDecision.source_event_id == source_event_id,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            return self._decision_payload(dup)
        state = (payload.get("state") or "approved").strip()
        if state not in DECISION_STATES:
            state = "approved"
        now = datetime.now(timezone.utc)
        row = CompanyDecision(
            organization_id=organization_id,
            decision_id=decision_id,
            kind=(payload.get("kind") or "other").strip()[:32] or "other",
            title=(payload.get("title") or "").strip()[:240],
            recommendation_key=(payload.get("recommendation_key") or "").strip()[:120],
            rationale=(payload.get("rationale") or "").strip()[:4000],
            alternatives_json=payload.get("alternatives") or [],
            impact_label=(payload.get("impact_label") or "").strip()[:160],
            expected_improvement=(payload.get("expected_improvement") or "").strip()[:240],
            confidence=payload.get("confidence"),
            owner_label=(payload.get("owner_label") or "").strip()[:120],
            state=state,
            approver_label=(payload.get("approver_label") or "").strip()[:120],
            note=(payload.get("note") or "").strip()[:4000],
            approved_at=now if state == "approved" else None,
            event_name=getattr(event, "name", "") or "",
            source_event_id=source_event_id,
        )
        db.add(row)
        return self._decision_payload(row)

    async def execute_decision(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Mark an approved decision as executed (idempotent)."""
        decision_id = (payload.get("decision_id") or "").strip()
        row = (
            await db.execute(
                select(CompanyDecision).where(
                    CompanyDecision.organization_id == organization_id,
                    CompanyDecision.decision_id == decision_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.state == "approved":
            row.state = "executed"
            row.executed_by_label = (payload.get("executed_by_label") or "").strip()[:120]
            row.executed_at = datetime.now(timezone.utc)
        return self._decision_payload(row)

    async def record_outcome(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Record the observed outcome + lesson of an executed action
        (idempotent)."""
        decision_id = (payload.get("decision_id") or "").strip()
        row = (
            await db.execute(
                select(CompanyDecision).where(
                    CompanyDecision.organization_id == organization_id,
                    CompanyDecision.decision_id == decision_id,
                )
            )
        ).scalar_one_or_none()
        if row is None or row.state not in ("executed", "outcome_recorded"):
            return None if row is None else self._decision_payload(row)
        row.state = "outcome_recorded"
        row.outcome_kind = (payload.get("outcome_kind") or "").strip()[:16]
        effectiveness = payload.get("effectiveness")
        if effectiveness is not None:
            row.effectiveness = max(0.0, min(1.0, float(effectiveness)))
        row.outcome_evidence_json = payload.get("evidence") or []
        row.lesson = (payload.get("lesson") or "").strip()[:4000]
        return self._decision_payload(row)

    def _decision_payload(self, row: CompanyDecision) -> dict[str, Any]:
        return {
            "decision_id": row.decision_id,
            "kind": row.kind,
            "title": row.title,
            "recommendation_key": row.recommendation_key,
            "state": row.state,
            "impact_label": row.impact_label,
            "expected_improvement": row.expected_improvement,
            "confidence": row.confidence,
            "owner_label": row.owner_label,
            "approver_label": row.approver_label,
            "approved_at": _iso(row.approved_at),
            "executed_at": _iso(row.executed_at),
            "outcome_kind": row.outcome_kind,
            "effectiveness": row.effectiveness,
            "lesson": row.lesson,
            "source_event_id": row.source_event_id,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }


company_operating_engine = CompanyOperatingEngine()
