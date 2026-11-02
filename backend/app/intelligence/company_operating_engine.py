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

from sqlalchemy import and_, delete, func, or_, select

from app.core.timeutils import ensure_aware
from app.db.database import AsyncSession
from app.models.company_operating import (
    CAUSAL_EDGE_KINDS,
    COMPANY_HEALTH_DOMAINS,
    COMPANY_SCOPE_TYPES,
    CONTRADICTION_STATUSES,
    DECISION_EVIDENCE_TYPES,
    DECISION_STATES,
    DOMAIN_WEIGHTS,
    MAX_ALTERNATIVES,
    MAX_CAUSAL_DEPTH,
    MAX_CAUSAL_EDGES,
    MAX_CHANGES_SHOWN,
    MAX_COMPANY_RECOMMENDATIONS,
    MAX_DECISION_EVIDENCE,
    MAX_MEMORY_SHOWN,
    MAX_NARRATIVE_STEPS,
    MAX_PRECEDENTS,
    MAX_SCENARIO_ASSUMPTIONS,
    MAX_SCENARIOS_SHOWN,
    MAX_SCOPED_DEVIATIONS,
    MAX_STATE_DECISIONS,
    MAX_STATE_DELTA,
    MAX_STATE_OPPORTUNITIES,
    MAX_STATE_RISKS,
    MAX_STATE_SIGNALS,
    MAX_WHATIF_CONSEQUENCES,
    OUTCOME_KINDS,
    QUALITY_STAGES,
    SCENARIO_KINDS,
    SCENARIO_PARAM_KEYS,
    STATE_DIMENSIONS,
    STATE_TTL,
    WHATIF_SCENARIOS,
    CompanyCausalEdge,
    CompanyDecision,
    CompanyDecisionAlternative,
    CompanyDecisionContradiction,
    CompanyDecisionEvidence,
    CompanyDecisionPrecedent,
    CompanyDecisionQuality,
    CompanyDecisionTrack,
    CompanyHealthHistory,
    CompanyScenarioRun,
    CompanyStateHistory,
)
from app.models.approval import Risk
from app.models.business_performance import (
    BusinessMetric,
    BusinessMetricObservation,
    BusinessPerformanceLink,
)
from app.models.company_actions import CompanyAction, CompanyActionEvent, CompanyActionOutcome
from app.models.company_memory import CompanyMemory
from app.models.customer import Customer, CustomerProjectLink
from app.models.customer_intelligence import CustomerCommitment
from app.models.employee import Employee
from app.models.execution_coordination import CoordinationIncident
from app.models.execution_intelligence import ProjectExecutionState
from app.models.execution_strategy import (
    CompanyInitiative,
    CompanyObjective,
    StrategicLink,
)
from app.models.knowledge import (
    KnowledgeIntelInsight,
    KnowledgeRecommendation,
    KnowledgeTopic,
)
from app.models.project import Milestone, Project
from app.models.resource_allocation_intelligence import AllocationDemand
from app.models.org_capability_intelligence import OrgCapability
from app.models.task import Task, TaskDependency
from app.models.intelligence import PatternDetection, UniversalInsight

from app.intelligence.execution_engine import execution_engine
from app.intelligence.coordination_engine import coordination_engine
from app.intelligence.strategic_execution_engine import strategic_execution_engine
from app.intelligence.resource_allocation_engine import resource_allocation_engine
from app.intelligence.customer_intelligence_engine import customer_intelligence_engine
from app.intelligence.business_performance_engine import business_performance_engine
from app.knowledge.action_ops_engine import action_ops_engine

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

# Slice 4H.5 bounds (contract §5.5): plan steps ≤ 5; chain actions ≤ 10;
# evidence rows ≤ 20; artifacts ≤ 10; outcomes ≤ 5; plan edge scan ≤ 60.
MAX_PLAN_STEPS = 5
MAX_PLAN_EDGES = 60
MAX_CHAIN_ACTIONS = 10
MAX_CHAIN_EVIDENCE = 20
MAX_CHAIN_ARTIFACTS = 10
MAX_CHAIN_OUTCOMES = 5

# 4H.5: decisions that have not reached human approval carry no authority to
# act on — plan derivation is rejected for them (advisory-before-action).
_PRE_APPROVAL_DECISION_STATES = frozenset(
    {"proposed", "evaluated", "recommended", "declined"}
)


class DecisionExecutionRejected(Exception):
    """Raised when an execution attempt targets a decision that is not in an
    executable state (4H.2 §4 law): proposed/evaluated/recommended/declined/
    assessed must NEVER transition to executed — only approved may. The
    message is machine-verifiable (decision_id + state + reason)."""

    def __init__(self, decision_id: str, state: str) -> None:
        self.decision_id = decision_id
        self.state = state
        super().__init__(
            f"execution rejected for decision {decision_id}: state '{state}' "
            "is not executable (only 'approved' may execute)"
        )


class DecisionOutcomeRejected(Exception):
    """Raised when an outcome attempt targets a decision that has not been
    executed: only executed/outcome_recorded decisions may record an outcome.

    Raised for pre-approval states, declined, and assessed; idempotent replays
    on executed/outcome_recorded are never raised (replay-safe).
    """

    def __init__(self, decision_id: str, state: str) -> None:
        self.decision_id = decision_id
        self.state = state
        super().__init__(
            f"outcome recording rejected for decision {decision_id}: state "
            f"'{state}' has no executable outcome to record"
        )
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
        )[:5]

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
        behind_gap = 0.0
        behind_label = ""
        behind_detail = ""
        if behind:
            tgt = behind.get("target") or {}
            behind_gap = float(tgt.get("gap") or 0.0)
            behind_label = tgt.get("metric_label") or tgt.get("metric_key") or ""
            behind_detail = " ".join(
                str(s) for s in (behind.get("summary") or [])[:1]
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
                    "label": f"target {behind_label} behind",
                    "detail": behind_detail,
                    "affected": [],
                }
                if behind_gap > 0 else None
            ),
            root_cause=behind_detail or None,
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
            scope_type="org",
            scope_id=None,
            event_name=event_name,
            source_event_id=str(source_event_id),
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(row)
        # 4H.1: attention-worthy scoped rows + the bounded causality snapshot
        # (both exact-once on the same source event, never recompute loops).
        await self._sync_scoped_rows(
            db, organization_id=organization_id,
            source_event_id=str(source_event_id), event_name=event_name,
            org_score=assessment["company_score"],
        )
        await self._sync_causal_edges(
            db, organization_id=organization_id,
            source_event_id=str(source_event_id),
        )
        # 4H.3: the living-company state snapshot (exact-once on the same
        # source event; writes a row ONLY when the composed surface differs
        # from the previous snapshot — no-op compositions leave no trail).
        await self._compose_state(
            db, organization_id=organization_id,
            scope_type="org", scope_id=None,
            source_event_id=str(source_event_id), event_name=event_name,
            occurred_at=datetime.now(timezone.utc),
        )
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
        decision_id: Optional[str] = None,
        predicted: Optional[bool] = None,
        since: Optional[str] = None,
    ) -> dict[str, Any]:
        """The governed decision history and what the company learned.

        Slice 4H.1 recall filters: a specific decision, only decisions that
        recorded a prediction, and the decisions since a date. Entries carry
        the prediction / reconciliation fields when present.
        """
        stmt = (
            select(CompanyDecision)
            .where(CompanyDecision.organization_id == organization_id)
        )
        if decision_id:
            stmt = stmt.where(CompanyDecision.decision_id == decision_id)
        if predicted:
            stmt = stmt.where(CompanyDecision.prediction_confidence.is_not(None))
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                stmt = stmt.where(CompanyDecision.updated_at >= since_dt)
            except ValueError:
                pass
        decisions = list(
            (
                await db.execute(
                    stmt.order_by(CompanyDecision.updated_at.desc())
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
                **self._prediction_fields(d),
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
                    **self._prediction_fields(d),
                }
                for d in decisions
            ],
            "learnings": learnings,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    def _prediction_fields(self, d: CompanyDecision) -> dict[str, Any]:
        """4H.1 prediction/reconciliation fields — only when present, so the
        existing surfaces stay byte-compatible."""
        out: dict[str, Any] = {}
        if d.predicted_outcome is not None:
            out["predicted_outcome"] = d.predicted_outcome
        if d.prediction_confidence is not None:
            out["prediction_confidence"] = d.prediction_confidence
        if d.actual_outcome_compare is not None:
            out["actual_outcome_compare"] = d.actual_outcome_compare
        if d.reviewed_at is not None:
            out["reviewed_at"] = _iso(d.reviewed_at)
        return out

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
        # 4H.2 §4 backward-compatibility law: the GOVERNED record path MAY
        # only ever mint approved|declined decisions. The expanded
        # DECISION_STATES constant is NOT a license to mint pre-approval
        # states through this path (a strict whitelist, never membership in
        # the full state vocabulary).
        _LEGACY_STATES = ("approved", "declined")
        state = (payload.get("state") or "approved").strip()
        if state not in _LEGACY_STATES:
            state = "approved"
        now = datetime.now(timezone.utc)
        prediction_confidence = payload.get("prediction_confidence")
        if prediction_confidence is not None:
            try:
                prediction_confidence = max(0.0, min(1.0, float(prediction_confidence)))
            except (TypeError, ValueError):
                prediction_confidence = None
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
            predicted_outcome=payload.get("predicted_outcome"),
            prediction_confidence=prediction_confidence,
            owner_label=(payload.get("owner_label") or "").strip()[:120],
            state=state,
            approver_label=(payload.get("approver_label") or "").strip()[:120],
            note=(payload.get("note") or "").strip()[:4000],
            approved_at=now if state == "approved" else None,
            as_of_context_json=payload.get("as_of_context") or None,
            scope_type=(payload.get("scope_type") or "").strip()[:12] or None,
            scope_id=(payload.get("scope_id") or "").strip()[:32] or None,
            event_name=getattr(event, "name", "") or "",
            source_event_id=source_event_id,
        )
        db.add(row)
        await db.flush()
        # 4H.2: an approved governed decision gets its first quality snapshot
        # (exact-once per stage; advisory-only, evidence-counted).
        if state == "approved":
            await self.compose_quality(
                db, organization_id=organization_id, event=event,
                payload={
                    "decision_id": decision_id, "stage": "approved",
                    "kind": row.kind, "title": row.title,
                    "scope_type": row.scope_type, "scope_id": row.scope_id,
                },
            )
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
        # 4H.2 §4 law: only approved may execute. Rejected states raise
        # DecisionExecutionRejected so no caller (and no route) can mistake a
        # rejection for a success. Replays of an already-executed/outcome-
        # recorded decision are idempotent no-ops (never raised).
        if row.state in ("executed", "outcome_recorded"):
            return self._decision_payload(row)
        if row.state != "approved":
            raise DecisionExecutionRejected(decision_id=row.decision_id, state=row.state)
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
        if row is None:
            return None
        # 4H.2 §4 law: only executed/outcome_recorded decisions may record an
        # outcome. Pre-approval/declined/assessed states raise; replays on an
        # outcome_recorded decision are idempotent (never raised).
        if row.state not in ("executed", "outcome_recorded"):
            raise DecisionOutcomeRejected(decision_id=row.decision_id, state=row.state)
        row.state = "outcome_recorded"
        row.outcome_kind = (payload.get("outcome_kind") or "").strip()[:16]
        effectiveness = payload.get("effectiveness")
        if effectiveness is not None:
            row.effectiveness = max(0.0, min(1.0, float(effectiveness)))
        row.outcome_evidence_json = payload.get("evidence") or []
        row.lesson = (payload.get("lesson") or "").strip()[:4000]
        result = self._decision_payload(row)
        # 4H.1: reconcile the prediction recorded at approve-time against the
        # observed outcome — the company's prediction track record.
        if row.predicted_outcome is not None:
            expected = (
                row.predicted_outcome.get("expected_outcome")
                if isinstance(row.predicted_outcome, dict) else None
            )
            row.actual_outcome_compare = {
                "predicted": expected,
                "observed": row.outcome_kind,
                "effectiveness_observed": row.effectiveness,
                "prediction_confidence": row.prediction_confidence,
                "aligned": (
                    (expected or "").strip().lower() == row.outcome_kind.strip().lower()
                ) if expected is not None else None,
                "reviewed_at": _iso(datetime.now(timezone.utc)),
            }
            row.reviewed_at = datetime.now(timezone.utc)
            result = self._decision_payload(row)
        # 4H.1: the lesson becomes a CompanyMemory (via formation.py) with
        # evidence lineage back to this decision (bounded, exact-once).
        if row.lesson:
            try:
                from app.memory.formation import record_decision_lesson

                memory = await record_decision_lesson(
                    db, organization_id=organization_id, event=event,
                    decision={
                        "decision_id": row.decision_id,
                        "kind": row.kind,
                        "title": row.title,
                        "lesson": row.lesson,
                        "outcome_kind": row.outcome_kind,
                    },
                )
                if memory:
                    result["lesson_memory"] = {
                        "memory_id": memory.get("id"),
                        "title": memory.get("title"),
                        "fact_kind": memory.get("fact_kind"),
                        "lesson": memory.get("lesson"),
                        "evidence": memory.get("evidence_json"),
                    }
            except Exception:
                pass
        # 4H.2: the outcome closes the loop — an append-only quality snapshot
        # and the cohort track rollup (exact-once on the decision's own source
        # event, so replays converge and never grow the lists).
        try:
            await self.compose_quality(
                db, organization_id=organization_id, event=event,
                payload={
                    "decision_id": decision_id, "stage": "outcome_recorded",
                    "kind": row.kind, "title": row.title,
                    "scope_type": row.scope_type, "scope_id": row.scope_id,
                },
            )
            await self.update_tracks(
                db, organization_id=organization_id, event=event,
                payload={
                    "decision_id": decision_id, "kind": row.kind,
                    "scope_type": row.scope_type, "scope_id": row.scope_id,
                },
            )
        except Exception:
            # 4H.2 audit hooks are additive; a failure here must never break
            # the 4H.1 outcome/lesson record (the canonical write already
            # committed) nor poison the event worker.
            import logging

            logging.getLogger("vcos.company.operating").exception(
                "4H.2 outcome audit hooks failed", exc_info=True
            )
        return result

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
            **self._prediction_fields(row),
        }

    # ------------------------------------------------------------------
    # 10. Slice 4H.1 — Universal Company / Organizational Intelligence
    # ------------------------------------------------------------------

    async def _scope_entity_ids(
        self, db: AsyncSession, *, organization_id: str,
        scope_type: str, scope_id: str,
    ) -> dict[str, Any]:
        """Resolve one scope to its canonical entity sets (bounded reads).

        person -> the employee's tasks/projects; department/team/business
        unit -> the members' tasks/projects; goals and customers are pulled
        through the same canonical links the org surfaces use.
        """
        empty = {
            "project_ids": set(), "person_ids": set(),
            "customer_ids": set(), "goal_ids": set(),
            "objective_ids": set(), "initiative_ids": set(),
            "label": scope_id or scope_type,
        }
        scope_type = (scope_type or "org").strip().lower()
        if scope_type == "org":
            return {**empty, "label": "company"}
        if scope_type not in COMPANY_SCOPE_TYPES:
            return empty
        person_ids: set[str] = set()
        if scope_type == "person":
            person = (
                await db.execute(
                    select(Employee).where(
                        Employee.organization_id == organization_id,
                        Employee.id == scope_id,
                    )
                )
            ).scalar_one_or_none()
            if person is None:
                return empty
            person_ids = {person.id}
            empty["label"] = (
                person.display_name
                or f"{person.first_name} {person.last_name or ''}".strip()
                or person.email
            )
        else:
            col = {
                "business_unit": Employee.business_unit_id,
                "department": Employee.department_id,
                "team": Employee.team_id,
            }[scope_type]
            members = list(
                (
                    await db.execute(
                        select(Employee.id).where(
                            Employee.organization_id == organization_id,
                            col == scope_id,
                            Employee.status == "active",
                        ).limit(200)
                    )
                ).scalars().all()
            )
            person_ids = set(members)
        project_ids: set[str] = set()
        if person_ids:
            tasks = list(
                (
                    await db.execute(
                        select(Task.project_id).where(
                            Task.organization_id == organization_id,
                            Task.project_id.is_not(None),
                            Task.assignee_id.in_(person_ids),
                        ).limit(400)
                    )
                ).scalars().all()
            )
            project_ids = {p for p in tasks if p}
        initiative_ids: set[str] = set()
        objective_ids: set[str] = set()
        goal_ids: set[str] = set()
        customer_ids: set[str] = set()
        if project_ids:
            initiative_ids = set(
                list(
                    (
                        await db.execute(
                            select(StrategicLink.initiative_id).where(
                                StrategicLink.organization_id == organization_id,
                                StrategicLink.project_id.in_(project_ids),
                            )
                        )
                    ).scalars().all()
                )
            )
            if initiative_ids:
                objective_ids = set(
                    list(
                        (
                            await db.execute(
                                select(CompanyInitiative.objective_id).where(
                                    CompanyInitiative.organization_id == organization_id,
                                    CompanyInitiative.id.in_(initiative_ids),
                                )
                            )
                        ).scalars().all()
                    )
                )
                if objective_ids:
                    goal_ids = set(
                        list(
                            (
                                await db.execute(
                                    select(CompanyObjective.goal_id).where(
                                        CompanyObjective.organization_id == organization_id,
                                        CompanyObjective.id.in_(objective_ids),
                                    )
                                )
                            ).scalars().all()
                        )
                    )
            customer_ids = set(
                list(
                    (
                        await db.execute(
                            select(CustomerProjectLink.customer_id).where(
                                CustomerProjectLink.organization_id == organization_id,
                                CustomerProjectLink.project_id.in_(project_ids),
                            )
                        )
                    ).scalars().all()
                )
            )
        return {
            "project_ids": project_ids,
            "person_ids": person_ids,
            "customer_ids": customer_ids,
            "goal_ids": goal_ids,
            "objective_ids": objective_ids,
            "initiative_ids": initiative_ids,
            "label": empty["label"],
        }

    async def _scope_domains(
        self, db: AsyncSession, *, organization_id: str,
        entity_sets: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Domain rows bounded to one scope's entities. Only evidence-backed
        domains are emitted — an empty dimension is never faked as healthy.
        Financial and knowledge have no scope join and are skipped here."""
        project_ids = entity_sets["project_ids"]
        person_ids = entity_sets["person_ids"]
        domains: list[dict[str, Any]] = []
        proj_in = [p for p in project_ids][:MAX_PROJECT_SCAN]
        if proj_in:
            # execution: mean ProjectExecutionState health of scope projects.
            states = list(
                (
                    await db.execute(
                        select(ProjectExecutionState).where(
                            ProjectExecutionState.organization_id == organization_id,
                            ProjectExecutionState.project_id.in_(proj_in),
                        )
                    )
                ).scalars().all()
            )
            by_project = {s.project_id: s for s in states}
            scores = [
                by_project[p].health_score
                for p in proj_in if p in by_project
            ]
            if scores:
                score = _clamp(sum(scores) / len(scores))
                worst = min(by_project.values(), key=lambda s: s.health_score)
                domains.append(self._domain_row(
                    "execution", "Execution", score,
                    reasons=[f"{len(scores)} of {len(proj_in)} scope projects assessed"],
                    affected=[
                        s.project_id for s in states if s.health_score < 75
                    ][:MAX_STEP_ENTITIES],
                    constraint=(
                        {
                            "label": worst.project_id,
                            "detail": worst.primary_cause or "health below healthy band",
                            "affected": _head(worst.capacity_constraints or []),
                        }
                        if worst.health_score < 75 else None
                    ),
                    root_cause=worst.primary_cause,
                    interventions=[],
                    evidence_count=len(scores),
                ))
        if proj_in:
            # capacity: demand on scope projects vs OrgCapability availability.
            demands = list(
                (
                    await db.execute(
                        select(
                            AllocationDemand.capability,
                            func.sum(AllocationDemand.units),
                        ).where(
                            AllocationDemand.organization_id == organization_id,
                            AllocationDemand.project_id.in_(proj_in),
                        ).group_by(AllocationDemand.capability).limit(20)
                    )
                ).all()
            )
            if demands:
                caps = list(
                    (
                        await db.execute(
                            select(OrgCapability).where(
                                OrgCapability.organization_id == organization_id,
                                OrgCapability.canonical_name.in_(
                                    [d[0] for d in demands]
                                ),
                            )
                        )
                    ).scalars().all()
                )
                by_cap = {c.canonical_name: c for c in caps}
                gaps: list[str] = []
                score = 100
                for capability, units in demands:
                    available = int(getattr(
                        by_cap.get(capability), "capacity_available", 0,
                    ) or 0)
                    if available == 0:
                        gaps.append(capability)
                        score -= 20
                    elif int(units) > available:
                        gaps.append(f"{capability} (+{int(units) - available} units)")
                        score -= 10
                score = _clamp(score)
                domains.append(self._domain_row(
                    "capacity", "Capacity", score,
                    reasons=[f"{len(demands)} capability demands on scope projects"],
                    affected=_head(gaps),
                    constraint=(
                        {
                            "label": gaps[0],
                            "detail": "scope demand exceeds available capability",
                            "affected": _head(gaps),
                        }
                        if gaps else None
                    ),
                    root_cause="scope demand exceeds available capability" if gaps else None,
                    interventions=[],
                    evidence_count=len(demands),
                ))
        if person_ids:
            # people: overloaded members of the scope (bounded).
            overloaded = list(
                (
                    await db.execute(
                        select(Employee.id).where(
                            Employee.organization_id == organization_id,
                            Employee.id.in_(person_ids),
                        ).limit(1)
                    )
                ).scalars().all()
            )
            # workload evidence comes from the resource allocation engine's
            # bounded overload surface; a scope without assessments stays
            # neutral-but-absent: only emit when workload rows exist.
            people_score = await self._scope_people_score(
                db, organization_id=organization_id, person_ids=person_ids,
            )
            if people_score is not None:
                score, overloaded_ids, reason = people_score
                domains.append(self._domain_row(
                    "people", "People", score,
                    reasons=[reason] if reason else [
                        f"{len(overloaded_ids)} of {len(person_ids)} scope members overloaded"
                    ],
                    affected=_head(list(overloaded_ids)),
                    constraint=(
                        {
                            "label": reason,
                            "detail": "scope members over capacity",
                            "affected": _head(list(overloaded_ids)),
                        }
                        if overloaded_ids else None
                    ),
                    root_cause="member workload exceeds capacity" if overloaded_ids else None,
                    interventions=[],
                    evidence_count=len(person_ids),
                ))
        if proj_in:
            # strategy: objectives/initiatives linked to scope projects.
            objectives = list(
                (
                    await db.execute(
                        select(CompanyObjective).where(
                            CompanyObjective.organization_id == organization_id,
                            CompanyObjective.id.in_(entity_sets["objective_ids"] or set()),
                        )
                    )
                ).scalars().all()
            ) if entity_sets["objective_ids"] else []
            if objectives:
                active = [o for o in objectives if o.status == "active"]
                score = _clamp(
                    100 - 15 * len([o for o in active if o.status != "on_track"])
                ) if active else 80
                domains.append(self._domain_row(
                    "strategy", "Strategy", score,
                    reasons=[f"{len(active)} active objectives linked to scope work"],
                    affected=[o.title for o in active][:MAX_STEP_ENTITIES],
                    evidence_count=len(objectives),
                ))
        if proj_in:
            # customers: commitments on scope projects.
            commitments = list(
                (
                    await db.execute(
                        select(CustomerCommitment).where(
                            CustomerCommitment.organization_id == organization_id,
                            CustomerCommitment.project_id.in_(proj_in),
                        ).limit(MAX_PROJECT_SCAN)
                    )
                ).scalars().all()
            )
            if commitments:
                at_risk = [
                    c for c in commitments if (c.status or "on_track") != "on_track"
                ]
                score = _clamp(100 - 20 * len(at_risk))
                domains.append(self._domain_row(
                    "customers", "Customers", score,
                    reasons=[f"{len(at_risk)} of {len(commitments)} scope commitments at risk"],
                    affected=[c.summary for c in at_risk][:MAX_STEP_ENTITIES],
                    constraint=(
                        {
                            "label": at_risk[0].summary,
                            "detail": "a scope commitment is at risk",
                            "affected": _head([c.summary for c in at_risk]),
                        }
                        if at_risk else None
                    ),
                    root_cause="commitment at risk" if at_risk else None,
                    interventions=[],
                    evidence_count=len(commitments),
                ))
        if proj_in:
            # coordination: open incidents on scope projects.
            incidents = list(
                (
                    await db.execute(
                        select(CoordinationIncident).where(
                            CoordinationIncident.organization_id == organization_id,
                            CoordinationIncident.project_id.in_(proj_in),
                            CoordinationIncident.status == "open",
                        ).limit(20)
                    )
                ).scalars().all()
            )
            if incidents:
                score = _clamp(100 - 25 * len(incidents))
                domains.append(self._domain_row(
                    "coordination", "Coordination", score,
                    reasons=[f"{len(incidents)} open coordination incidents on scope projects"],
                    affected=[i.title for i in incidents][:MAX_STEP_ENTITIES],
                    constraint=(
                        {
                            "label": incidents[0].title,
                            "detail": "open coordination incident in scope",
                            "affected": _head([i.title for i in incidents]),
                        }
                        if incidents else None
                    ),
                    root_cause="open coordination incident" if incidents else None,
                    interventions=[],
                    evidence_count=len(incidents),
                ))
        return domains

    async def _scope_people_score(
        self, db: AsyncSession, *, organization_id: str, person_ids: set[str],
    ) -> Optional[tuple[int, set[str], str]]:
        """Bounded workload evidence for a person set: derives overload from
        the canonical task commitments of the scope instead of any manual
        workload table, so absent data stays neutral (no faked health)."""
        if not person_ids:
            return None
        tasks = list(
            (
                await db.execute(
                    select(Task).where(
                        Task.organization_id == organization_id,
                        Task.assignee_id.in_(person_ids),
                        Task.status.in_(
                            ("active", "blocked", "pending", "todo", "in_progress", "in_review")
                        ),
                    ).limit(200)
                )
            ).scalars().all()
        )
        if not tasks:
            return None
        per_person: dict[str, int] = {}
        for t in tasks:
            per_person[t.assignee_id or ""] = per_person.get(t.assignee_id or "", 0) + 1
        overloaded = {
            pid for pid, count in per_person.items()
            if count >= 6
        }
        score = _clamp(100 - 15 * len(overloaded))
        reason = (
            f"{len(overloaded)} of {len(per_person)} scope members carry 6+ open tasks"
            if overloaded else f"{len(per_person)} scope members carry open tasks"
        )
        return score, overloaded, reason

    async def multi_level_state(
        self, db: AsyncSession, *, organization_id: str,
        scope_type: str = "org", scope_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """The SAME state/health computation parameterized by scope — the
        company viewed through one business unit / department / team /
        person. Org stays the default; scoped domains are evidence-only."""
        scope_type = (scope_type or "org").strip().lower()
        if scope_type not in COMPANY_SCOPE_TYPES:
            return {
                "advisory_only": True,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "company_score": None,
                "company_state": "unsupported_scope",
                "domains": [],
                "primary_constraint": None,
                "attention": [],
                "summary": f"unsupported scope_type '{scope_type}'",
                "history": [],
                "generated_at": _iso(datetime.now(timezone.utc)),
            }
        if scope_type == "org":
            return await self.company_state(
                db, organization_id=organization_id,
            )
        entity_sets = await self._scope_entity_ids(
            db, organization_id=organization_id,
            scope_type=scope_type, scope_id=scope_id or "",
        )
        label = entity_sets["label"]
        domains = await self._scope_domains(
            db, organization_id=organization_id, entity_sets=entity_sets,
        )
        if not domains:
            return {
                "advisory_only": True,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "company_score": 80,
                "company_state": "healthy",
                "domains": [],
                "primary_constraint": None,
                "attention": [],
                "summary": (
                    f"{label} has no recorded activity yet — the scope is "
                    "neutral until the company records work for it"
                ),
                "history": [],
                "generated_at": _iso(datetime.now(timezone.utc)),
            }
        present = {d["key"]: d for d in domains}
        weights = {k: DOMAIN_WEIGHTS.get(k, 0.0) for k in present}
        total = sum(weights.values()) or 1.0
        score = _clamp(sum(weights[k] / total * present[k]["score"] for k in present))
        worst = min(domains, key=lambda d: d["score"])
        company_state = _band(score)
        if worst["state"] in ("at_risk", "critical") and company_state == "healthy":
            company_state = "concerned"
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
        attention = [
            {
                "priority": _rank(d["state"]),
                "kind": f"{d['key']}_health",
                "title": f"{d['label']} is {d['state']} ({d['score']}/100)",
                "why": _head(d["reasons"], 1)[0] if d["reasons"] else "",
            }
            for d in sorted(domains, key=lambda d: d["score"])[:MAX_FOCUS_ITEMS]
            if d["score"] < 75
        ]
        return {
            "advisory_only": True,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope_label": label,
            "company_score": score,
            "company_state": company_state,
            "domains": domains,
            "primary_constraint": primary_constraint,
            "attention": attention,
            "summary": summary,
            "history": [],
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def _sync_scoped_rows(
        self, db: AsyncSession, *, organization_id: str,
        source_event_id: str, event_name: str,
        org_score: Optional[int] = None,
    ) -> None:
        """4H.1: persist bounded scoped rows (business unit / department /
        team) for attention-worthy deviations, exact-once per event."""
        if org_score is None:
            org_score = 80
        candidates: list[tuple[str, str]] = []
        for scope_type, col in (
            ("business_unit", Employee.business_unit_id),
            ("department", Employee.department_id),
            ("team", Employee.team_id),
        ):
            scope_ids = list(
                (
                    await db.execute(
                        select(col).where(
                            Employee.organization_id == organization_id,
                            col.is_not(None),
                            Employee.status == "active",
                        ).distinct().limit(10)
                    )
                ).scalars().all()
            )
            candidates.extend((scope_type, sid) for sid in scope_ids if sid)
        scored: list[tuple[int, str, str, int, int, list[dict[str, Any]]]] = []
        for scope_type, scope_id in candidates[:10]:
            try:
                entity_sets = await self._scope_entity_ids(
                    db, organization_id=organization_id,
                    scope_type=scope_type, scope_id=scope_id,
                )
                if len(entity_sets["project_ids"]) < 2:
                    continue
                domains = await self._scope_domains(
                    db, organization_id=organization_id, entity_sets=entity_sets,
                )
                if not domains:
                    continue
                score = self._scope_composed_score(domains)
                scored.append(
                    (abs(score - org_score), scope_type, scope_id, score, len(domains), domains)
                )
            except Exception:
                continue
        scored.sort(key=lambda t: (-t[0], t[1], t[2]))
        for deviation, scope_type, scope_id, score, _, domains in scored[:MAX_SCOPED_DEVIATIONS]:
            if deviation < 15:
                continue
            worst = min(domains, key=lambda d: d["score"])
            state = _band(score)
            if worst["state"] in ("at_risk", "critical") and state == "healthy":
                state = "concerned"
            if worst["state"] == "critical" and _rank(worst["state"]) == 1:
                state = "at_risk" if _band(score) == "healthy" else state
            primary_constraint = None
            if worst["score"] < 75 and worst.get("constraint"):
                primary_constraint = {
                    "domain": worst["key"], "domain_label": worst["label"],
                    "score": worst["score"], "state": worst["state"],
                    **worst["constraint"],
                    "root_cause": worst.get("root_cause"),
                    "interventions": worst.get("interventions") or [],
                }
            summary = self._summary_narrative(domains, primary_constraint)
            attention = [
                {
                    "priority": _rank(d["state"]),
                    "kind": f"{d['key']}_health",
                    "title": f"{d['label']} is {d['state']} ({d['score']}/100)",
                    "why": _head(d["reasons"], 1)[0] if d["reasons"] else "",
                }
                for d in sorted(domains, key=lambda d: d["score"])[:MAX_FOCUS_ITEMS]
                if d["score"] < 75
            ]
            existing = (
                await db.execute(
                    select(CompanyHealthHistory).where(
                        CompanyHealthHistory.organization_id == organization_id,
                        CompanyHealthHistory.source_event_id == source_event_id,
                        CompanyHealthHistory.scope_type == scope_type,
                        CompanyHealthHistory.scope_id == scope_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(CompanyHealthHistory(
                organization_id=organization_id,
                company_score=score,
                company_state=state,
                primary_constraint_json=primary_constraint,
                domains_json=domains,
                attention_json=attention,
                summary_narrative=summary,
                scope_type=scope_type,
                scope_id=scope_id,
                event_name=event_name,
                source_event_id=source_event_id,
                occurred_at=datetime.now(timezone.utc),
            ))

    def _scope_composed_score(self, domains: list[dict[str, Any]]) -> int:
        """Weighted composition over the evidence-backed domains present."""
        present = {d["key"]: d for d in domains}
        weights = {k: DOMAIN_WEIGHTS.get(k, 0.0) for k in present}
        total = sum(weights.values()) or 1.0
        return _clamp(sum(weights[k] / total * present[k]["score"] for k in present))

    async def temporal_state(
        self, db: AsyncSession, *, organization_id: str,
        scope_type: Optional[str] = None, scope_id: Optional[str] = None,
        from_ts: Optional[str] = None, to_ts: Optional[str] = None,
        limit: int = MAX_HISTORY_SHOWN,
    ) -> dict[str, Any]:
        """The bounded health-trail series — 'what is happening across my
        company right now', with per-step dimension scores and evidence."""
        scope_type = (scope_type or "org").strip().lower()
        if scope_type not in COMPANY_SCOPE_TYPES:
            scope_type = "org"
        limit = max(1, min(int(limit or MAX_HISTORY_SHOWN), MAX_HISTORY_SHOWN))
        stmt = (
            select(CompanyHealthHistory)
            .where(CompanyHealthHistory.organization_id == organization_id)
        )
        if scope_type != "org":
            stmt = stmt.where(
                CompanyHealthHistory.scope_type == scope_type,
                CompanyHealthHistory.scope_id == scope_id,
            )
        if from_ts:
            try:
                stmt = stmt.where(
                    CompanyHealthHistory.occurred_at >= datetime.fromisoformat(
                        from_ts.replace("Z", "+00:00")
                    )
                )
            except ValueError:
                pass
        if to_ts:
            try:
                stmt = stmt.where(
                    CompanyHealthHistory.occurred_at <= datetime.fromisoformat(
                        to_ts.replace("Z", "+00:00")
                    )
                )
            except ValueError:
                pass
        rows = list(
            (
                await db.execute(
                    stmt.order_by(CompanyHealthHistory.occurred_at.asc()).limit(limit)
                )
            ).scalars().all()
        )
        series = [
            {
                "occurred_at": _iso(r.occurred_at),
                "company_score": r.company_score,
                "company_state": r.company_state,
                "primary_constraint": (
                    (r.primary_constraint_json or {}).get("label")
                    or (r.primary_constraint_json or {}).get("domain")
                ),
                "domains": {
                    d["key"]: d["score"]
                    for d in (r.domains_json or [])
                },
            }
            for r in rows
        ]
        latest = series[-1] if series else None
        return {
            "advisory_only": True,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "count": len(series),
            "series": series,
            "latest": latest,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def narrative(
        self, db: AsyncSession, *, organization_id: str,
        scope_type: str = "org", scope_id: Optional[str] = None,
        window: int = MAX_NARRATIVE_STEPS,
    ) -> dict[str, Any]:
        """WHY the score moved: deltas between consecutive trail rows composed
        with their evidence — deterministic, bounded (5 steps)."""
        scope_type = (scope_type or "org").strip().lower()
        if scope_type not in COMPANY_SCOPE_TYPES:
            scope_type = "org"
        window = max(1, min(int(window or MAX_NARRATIVE_STEPS), MAX_NARRATIVE_STEPS))
        stmt = (
            select(CompanyHealthHistory)
            .where(CompanyHealthHistory.organization_id == organization_id)
            .order_by(CompanyHealthHistory.occurred_at.desc())
            .limit(window + 1)
        )
        if scope_type != "org":
            stmt = stmt.where(
                CompanyHealthHistory.scope_type == scope_type,
                CompanyHealthHistory.scope_id == scope_id,
            )
        rows = list((await db.execute(stmt)).scalars().all())
        rows.reverse()
        if len(rows) < 2:
            return {
                "advisory_only": True,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "window": "insufficient_history",
                "story": [
                    "not enough assessments recorded yet — the narrative opens "
                    "once the company trail holds at least two points"
                ],
                "steps": [],
                "generated_at": _iso(datetime.now(timezone.utc)),
            }
        steps: list[dict[str, Any]] = []
        for prev, now_ in zip(rows, rows[1:]):
            prev_domains = {d["key"]: d for d in (prev.domains_json or [])}
            now_domains = {d["key"]: d for d in (now_.domains_json or [])}
            deltas: list[dict[str, Any]] = []
            for key in COMPANY_HEALTH_DOMAINS:
                a = prev_domains.get(key)
                b = now_domains.get(key)
                if not a or not b:
                    continue
                delta = int(b.get("score") or 0) - int(a.get("score") or 0)
                if abs(delta) < 3:
                    continue
                deltas.append({
                    "domain": key,
                    "label": b.get("label"),
                    "delta": delta,
                    "direction": "down" if delta < 0 else "up",
                    "why": _head(b.get("reasons") or [], 1)[0] if b.get("reasons") else "",
                })
            pc_prev = prev.primary_constraint_json or {}
            pc_now = now_.primary_constraint_json or {}
            constraint_shift = None
            if pc_prev.get("label") != pc_now.get("label"):
                constraint_shift = pc_now.get("label") or "constraint cleared"
            deltas.sort(key=lambda d: (d["delta"], d["domain"]))
            steps.append({
                "window": f"{_iso(prev.occurred_at)} -> {_iso(now_.occurred_at)}",
                "score_before": prev.company_score,
                "score_after": now_.company_score,
                "state_before": prev.company_state,
                "state_after": now_.company_state,
                "deltas": deltas[:MAX_STEP_ENTITIES],
                "constraint_shift": constraint_shift,
            })
        story_parts: list[str] = []
        for step in steps:
            if step["deltas"]:
                for d in step["deltas"][:1]:
                    story_parts.append(
                        f"{d['label']} {d['direction']} {abs(d['delta'])} points "
                        f"({d['why']})"
                    )
            elif step["constraint_shift"]:
                story_parts.append(
                    f"constraint shifted: {step['constraint_shift']}"
                )
        if not story_parts:
            story_parts.append(
                "the company health trail shows no meaningful deltas in this window"
            )
        return {
            "advisory_only": True,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "window": f"{_iso(rows[0].occurred_at)} -> {_iso(rows[-1].occurred_at)}",
            "story": story_parts,
            "steps": steps,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    # ---- causal graph ----------------------------------------------------

    async def _derive_causal_edges(
        self, db: AsyncSession, *, organization_id: str,
    ) -> list[dict[str, Any]]:
        """Derive bounded causality hops from canonical tables only. Kinds
        without a derivable join carry no rows (evidence-driven, never
        faked): customer->revenue, revenue->objective, objective->outcome,
        outcome->customer, customer->business."""
        edges: list[dict[str, Any]] = []
        # capability->project + capacity->project: demands push into projects.
        demands = list(
            (
                await db.execute(
                    select(
                        AllocationDemand.capability,
                        AllocationDemand.project_id,
                        func.count(AllocationDemand.id),
                    ).where(
                        AllocationDemand.organization_id == organization_id,
                    ).group_by(
                        AllocationDemand.capability, AllocationDemand.project_id,
                    ).limit(MAX_CAUSAL_EDGES)
                )
            ).all()
        )
        for capability, project_id, cnt in demands:
            edges.append({
                "source_type": "capability", "source_id": capability,
                "target_type": "project", "target_id": project_id,
                "kind": "capability->project",
                "confidence": "high" if cnt >= 2 else "medium",
                "evidence_ref": [{"entity": "demand", "id": f"{capability}:{project_id}", "label": f"{capability} -> project", "kind": "allocation"}],
            })
            edges.append({
                "source_type": "capacity", "source_id": capability,
                "target_type": "project", "target_id": project_id,
                "kind": "capacity->project",
                "confidence": "high" if cnt >= 2 else "medium",
                "evidence_ref": [{"entity": "demand", "id": f"{capability}:{project_id}", "label": f"capacity pressure {capability}", "kind": "allocation"}],
            })
        # project->milestone: milestones on projects.
        milestones = list(
            (
                await db.execute(
                    select(Milestone).where(
                        Milestone.organization_id == organization_id,
                        Milestone.project_id.is_not(None),
                        Milestone.status != "completed",
                    ).limit(MAX_CAUSAL_EDGES)
                )
            ).scalars().all()
        )
        for m in milestones:
            edges.append({
                "source_type": "project", "source_id": m.project_id,
                "target_type": "milestone", "target_id": m.id,
                "kind": "project->milestone",
                "confidence": "high" if m.status == "in_progress" else "medium",
                "evidence_ref": [{"entity": "milestone", "id": m.id, "label": m.name, "kind": "milestone"}],
            })
        # project->customer: project links.
        links = list(
            (
                await db.execute(
                    select(CustomerProjectLink).where(
                        CustomerProjectLink.organization_id == organization_id,
                    ).limit(MAX_CAUSAL_EDGES)
                )
            ).scalars().all()
        )
        for link in links:
            edges.append({
                "source_type": "project", "source_id": link.project_id,
                "target_type": "customer", "target_id": link.customer_id,
                "kind": "project->customer",
                "confidence": "high",
                "evidence_ref": [{"entity": "link", "id": f"{link.customer_id}:{link.project_id}", "label": "customer project link", "kind": "link"}],
            })
        # milestone->customer: open milestones on linked projects.
        linked_projects = {l.project_id for l in links}
        for m in milestones:
            if m.project_id in linked_projects:
                edges.append({
                    "source_type": "milestone", "source_id": m.id,
                    "target_type": "customer",
                    "target_id": next(
                        (l.customer_id for l in links if l.project_id == m.project_id), ""
                    ),
                    "kind": "milestone->customer",
                    "confidence": "medium",
                    "evidence_ref": [{"entity": "milestone", "id": m.id, "label": m.name, "kind": "milestone"}],
                })
        # decision->task + task->execution: decision-driven tasks.
        tasks = list(
            (
                await db.execute(
                    select(Task).where(
                        Task.organization_id == organization_id,
                        Task.project_id.is_not(None),
                    ).limit(MAX_CAUSAL_EDGES)
                )
            ).scalars().all()
        )
        for t in tasks:
            if t.decision_id:
                edges.append({
                    "source_type": "decision", "source_id": t.decision_id,
                    "target_type": "task", "target_id": t.id,
                    "kind": "decision->task",
                    "confidence": "high",
                    "evidence_ref": [{"entity": "task", "id": t.id, "label": t.title, "kind": "task"}],
                })
            edges.append({
                "source_type": "task", "source_id": t.id,
                "target_type": "execution", "target_id": t.project_id,
                "kind": "task->execution",
                "confidence": "high",
                "evidence_ref": [{"entity": "task", "id": t.id, "label": t.title, "kind": "task"}],
            })
        # execution->outcome: closed decision loops.
        closed = list(
            (
                await db.execute(
                    select(CompanyDecision).where(
                        CompanyDecision.organization_id == organization_id,
                        CompanyDecision.outcome_kind != "",
                    ).limit(MAX_CAUSAL_EDGES)
                )
            ).scalars().all()
        )
        for d in closed:
            edges.append({
                "source_type": "execution", "source_id": d.decision_id,
                "target_type": "outcome", "target_id": d.decision_id,
                "kind": "execution->outcome",
                "confidence": "high",
                "evidence_ref": [{"entity": "decision", "id": d.decision_id, "label": d.title, "kind": "decision"}],
            })
        # --- Slice 4H.3 additive kinds (no new table, no new engine) --------
        # risk->project: open risk rows (identified/assessing/mitigating/
        # accepted/monitoring) project-anchored through their FK.
        risk_rows = list(
            (
                await db.execute(
                    select(Risk).where(
                        Risk.organization_id == organization_id,
                        Risk.status != "closed",
                        Risk.project_id.is_not(None),
                    ).order_by(Risk.risk_score.desc()).limit(MAX_CAUSAL_EDGES)
                )
            ).scalars().all()
        )
        for rk in risk_rows:
            edges.append({
                "source_type": "risk", "source_id": rk.id,
                "target_type": "project", "target_id": rk.project_id,
                "kind": "risk->project",
                "confidence": "high" if rk.risk_score >= 12 else ("medium" if rk.risk_score >= 6 else "low"),
                "evidence_ref": [{"entity": "risk", "id": rk.id, "label": rk.title, "kind": "risk"}],
            })
        # dependency->project: dependency pairs resolved through their tasks
        # (org-scoped — dependency rows are tenant data, never cross-org).
        deps = list(
            (
                await db.execute(
                    select(TaskDependency).where(
                        TaskDependency.organization_id == organization_id,
                    ).limit(MAX_CAUSAL_EDGES)
                )
            ).scalars().all()
        )
        if deps:
            dep_task_ids = {
                tid for d in deps for tid in (d.task_id, d.depends_on_task_id)
            }
            dep_tasks = {
                t.id: t for t in list(
                    (
                        await db.execute(
                            select(Task).where(
                                Task.organization_id == organization_id,
                                Task.id.in_(dep_task_ids),
                            )
                        )
                    ).scalars().all()
                )
            }
            for dep in deps:
                blocked = dep_tasks.get(dep.task_id)
                if blocked and blocked.project_id:
                    edges.append({
                        "source_type": "dependency", "source_id": dep.depends_on_task_id,
                        "target_type": "project", "target_id": blocked.project_id,
                        "kind": "dependency->project",
                        "confidence": "medium",
                        "evidence_ref": [{"entity": "dependency", "id": f"{dep.depends_on_task_id}->{dep.task_id}", "label": "task dependency", "kind": "dependency"}],
                    })
        # person->capability: members executing on projects that demand it.
        person_tasks = list(
            (
                await db.execute(
                    select(Task).where(
                        Task.organization_id == organization_id,
                        Task.assignee_id.is_not(None),
                        Task.project_id.is_not(None),
                    ).limit(200)
                )
            ).scalars().all()
        )
        demand_by_project: dict[str, set[str]] = {}
        for capability, project_id, _ in demands:
            demand_by_project.setdefault(project_id, set()).add(capability)
        for t in person_tasks:
            for capability in demand_by_project.get(t.project_id or "", set()):
                edges.append({
                    "source_type": "person", "source_id": t.assignee_id,
                    "target_type": "capability", "target_id": capability,
                    "kind": "person->capability",
                    "confidence": "medium",
                    "evidence_ref": [{"entity": "task", "id": t.id, "label": t.title, "kind": "task"}],
                })
        # --- Slice 4H.3 additive kinds (no new table, no new engine) --------
        # risk->project already appended above (before dependency), so the
        # bounded edge budget can never starve the 4H.3 risk surface.
        # constraint->project: the company-level primary constraint's affected
        # projects (deterministic from the latest health snapshot).
        chh_latest = (
            await db.execute(
                select(CompanyHealthHistory)
                .where(
                    CompanyHealthHistory.organization_id == organization_id,
                    CompanyHealthHistory.scope_type == "org",
                )
                .order_by(CompanyHealthHistory.occurred_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if chh_latest is not None and isinstance(chh_latest.primary_constraint_json, dict):
            for aff in _head(chh_latest.primary_constraint_json.get("affected") or [], MAX_SCOPED_DEVIATIONS):
                if isinstance(aff, dict) and str(aff.get("type") or "").lower() == "project":
                    edges.append({
                        "source_type": "constraint",
                        "source_id": f"cc:{chh_latest.id}",
                        "target_type": "project",
                        "target_id": str(aff.get("id") or ""),
                        "kind": "constraint->project",
                        "confidence": "medium",
                        "evidence_ref": [{"entity": "health", "id": chh_latest.id, "label": "company primary constraint", "kind": "health"}],
                    })
        # opportunity->decision: decision evidence whose lineage is a
        # pattern/insight recommendation — the opportunity the decision
        # answers (bounded).
        opp_rows = list(
            (
                await db.execute(
                    select(CompanyDecisionEvidence).where(
                        CompanyDecisionEvidence.organization_id == organization_id,
                        CompanyDecisionEvidence.evidence_type.in_(("insight", "pattern")),
                    ).order_by(CompanyDecisionEvidence.captured_at.desc())
                    .limit(MAX_CAUSAL_EDGES)
                )
            ).scalars().all()
        )
        for ev in opp_rows:
            edges.append({
                "source_type": "opportunity",
                "source_id": (ev.source_event_id or f"evidence:{ev.evidence_key}"),
                "target_type": "decision",
                "target_id": ev.decision_id,
                "kind": "opportunity->decision",
                "confidence": "medium" if ev.weight >= 0.5 else "low",
                "evidence_ref": [{"entity": "evidence", "id": ev.evidence_key, "label": (ev.source_summary or "")[:80], "kind": ev.source_kind}],
            })
        # decision->process: vocabulary-only today — no canonical join maps a
        # company decision to a process entity, so this kind legitimately
        # carries no rows (snapshot stays evidence-driven, never faked).
        # dedupe by hop key (kind + source + target), stable order.
        seen: set[tuple[str, str, str, str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for e in edges:
            key = (e["kind"], e["source_type"], e["source_id"], e["target_type"], e["target_id"])
            if key in seen:
                continue
            seen.add(key)
            if e["kind"] not in CAUSAL_EDGE_KINDS:
                continue
            deduped.append(e)
        return deduped

    async def _sync_causal_edges(
        self, db: AsyncSession, *, organization_id: str, source_event_id: str,
    ) -> None:
        """Persist the bounded causality snapshot (exact-once per event) and
        prune older events to a recent window."""
        existing = (
            await db.execute(
                select(CompanyCausalEdge.id).where(
                    CompanyCausalEdge.organization_id == organization_id,
                    CompanyCausalEdge.source_event_id == source_event_id,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        edges = await self._derive_causal_edges(db, organization_id=organization_id)
        for e in _head(edges, MAX_CAUSAL_EDGES):
            db.add(CompanyCausalEdge(
                organization_id=organization_id,
                source_type=e["source_type"], source_id=e["source_id"],
                target_type=e["target_type"], target_id=e["target_id"],
                kind=e["kind"], confidence=e["confidence"],
                evidence_ref=e["evidence_ref"],
                source_event_id=source_event_id,
            ))
        # prune: keep only the 3 most recent snapshot events per org.
        recent = list(
            (
                await db.execute(
                    select(
                        CompanyCausalEdge.source_event_id,
                        func.max(CompanyCausalEdge.created_at),
                    ).where(
                        CompanyCausalEdge.organization_id == organization_id,
                    ).group_by(CompanyCausalEdge.source_event_id)
                    .order_by(func.max(CompanyCausalEdge.created_at).desc())
                    .limit(3)
                )
            ).all()
        )
        keep = {r[0] for r in recent}
        stale_ids = list(
            (
                await db.execute(
                    select(CompanyCausalEdge.id).where(
                        CompanyCausalEdge.organization_id == organization_id,
                        CompanyCausalEdge.source_event_id.not_in(keep),
                    )
                )
            ).scalars().all()
        )
        if stale_ids:
            await db.execute(
                delete(CompanyCausalEdge).where(
                    CompanyCausalEdge.id.in_(stale_ids)
                )
            )

    async def causal_chain(
        self, db: AsyncSession, *, organization_id: str,
        entity_type: str, entity_id: str, depth: int = MAX_CAUSAL_DEPTH,
    ) -> dict[str, Any]:
        """Walk the derived causality snapshot + the live impact chains from
        a subject — with per-hop confidence and evidence refs, bounded."""
        entity_type = (entity_type or "").strip().lower()
        entity_id = (entity_id or "").strip()
        depth = max(1, min(int(depth or MAX_CAUSAL_DEPTH), MAX_CAUSAL_DEPTH))
        rows = list(
            (
                await db.execute(
                    select(CompanyCausalEdge).where(
                        CompanyCausalEdge.organization_id == organization_id,
                    ).order_by(CompanyCausalEdge.created_at.desc())
                    .limit(MAX_CAUSAL_EDGES * 3)
                )
            ).scalars().all()
        )
        adj: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for e in rows:
            adj.setdefault((e.source_type, e.source_id), []).append({
                "from_type": e.source_type, "from_id": e.source_id,
                "kind": e.kind,
                "to_type": e.target_type, "to_id": e.target_id,
                "confidence": e.confidence, "evidence_ref": e.evidence_ref or [],
                "reverse": False,
            })
            adj.setdefault((e.target_type, e.target_id), []).append({
                "from_type": e.target_type, "from_id": e.target_id,
                "kind": f"{e.kind} (reverse)",
                "to_type": e.source_type, "to_id": e.source_id,
                "confidence": e.confidence, "evidence_ref": e.evidence_ref or [],
                "reverse": True,
            })
        # fall back to live impact chains when the snapshot has no subject rows.
        hops: list[dict[str, Any]] = []
        if (entity_type, entity_id) not in adj:
            try:
                impact = await self.impact(
                    db, organization_id=organization_id,
                    subject_type=entity_type, subject_id=entity_id,
                )
                for group in impact.get("propagation") or []:
                    for item in _head(group.get("items") or [], MAX_STEP_ENTITIES):
                        hops.append({
                            "from_type": entity_type, "from_id": entity_id,
                            "kind": group.get("kind") or "impact",
                            "to_type": item.get("type") or group.get("kind"),
                            "to_id": item.get("id"),
                            "to_label": item.get("name"),
                            "confidence": "medium",
                            "evidence_ref": [],
                        })
            except Exception:
                pass
        else:
            visited = {(entity_type, entity_id)}
            frontier = [(entity_type, entity_id)]
            for _ in range(depth):
                next_frontier: list[tuple[str, str]] = []
                for node in frontier:
                    for hop in sorted(
                        adj.get(node, []),
                        key=lambda h: (
                            {"high": 0, "medium": 1, "low": 2}.get(h["confidence"], 1),
                            h["kind"],
                        ),
                    ):
                        target = (hop["to_type"], hop["to_id"])
                        if target in visited:
                            continue
                        visited.add(target)
                        hops.append(hop)
                        next_frontier.append(target)
                        if len(hops) >= MAX_CAUSAL_EDGES:
                            break
                    if len(hops) >= MAX_CAUSAL_EDGES:
                        break
                frontier = next_frontier
                if not frontier or len(hops) >= MAX_CAUSAL_EDGES:
                    break
        hops = await self._label_hops(db, organization_id=organization_id, hops=hops)
        return {
            "advisory_only": True,
            "subject": {"type": entity_type, "id": entity_id},
            "hops": hops[:MAX_CAUSAL_EDGES],
            "depth": depth,
            "bounded": len(hops) >= MAX_CAUSAL_EDGES,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def _label_hops(
        self, db: AsyncSession, *, organization_id: str,
        hops: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Attach display labels to hop endpoints from canonical tables
        (bounded; text-key entities keep their key as the label)."""
        ids: dict[str, set[str]] = {}
        for h in hops:
            ids.setdefault(h["from_type"], set()).add(h["from_id"])
            ids.setdefault(h["to_type"], set()).add(h["to_id"])
        labels: dict[str, dict[str, str]] = {}
        if ids.get("person"):
            rows = list(
                (
                    await db.execute(
                        select(Employee.id, Employee.display_name, Employee.first_name, Employee.last_name, Employee.email).where(
                            Employee.organization_id == organization_id,
                            Employee.id.in_(ids["person"]),
                        )
                    )
                ).all()
            )
            for r in rows:
                labels.setdefault("person", {})[r[0]] = (
                    r[1] or f"{r[2]} {r[3] or ''}".strip() or r[4]
                )
        if ids.get("project"):
            rows = list(
                (
                    await db.execute(
                        select(Project.id, Project.name).where(
                            Project.organization_id == organization_id,
                            Project.id.in_(ids["project"]),
                        )
                    )
                ).all()
            )
            for r in rows:
                labels.setdefault("project", {})[r[0]] = r[1]
        if ids.get("customer"):
            rows = list(
                (
                    await db.execute(
                        select(Customer.id, Customer.company_name).where(
                            Customer.organization_id == organization_id,
                            Customer.id.in_(ids["customer"]),
                        )
                    )
                ).all()
            )
            for r in rows:
                labels.setdefault("customer", {})[r[0]] = r[1]
        out: list[dict[str, Any]] = []
        for h in hops:
            out.append({
                **h,
                "from_label": (
                    labels.get(h["from_type"], {}).get(h["from_id"], h["from_id"])
                ),
                "to_label": (
                    labels.get(h["to_type"], {}).get(h["to_id"], h["to_id"])
                ),
            })
        return out

    # ---- what-happens-if -------------------------------------------------

    async def _company_hops(
        self, db: AsyncSession, *, organization_id: str,
        project_id: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Company-level consequence hops for the what-happens-if runner:
        dependency, customer, strategy and capacity contention lists."""
        hops: list[dict[str, Any]] = []
        if project_id:
            # dependencies: tasks blocked by tasks on this project.
            tasks = list(
                (
                    await db.execute(
                        select(Task).where(
                            Task.organization_id == organization_id,
                            Task.project_id == project_id,
                        ).limit(100)
                    )
                ).scalars().all()
            )
            task_ids = {t.id for t in tasks}
            if task_ids:
                deps = list(
                    (
                        await db.execute(
                            select(TaskDependency).where(
                                TaskDependency.task_id.in_(task_ids)
                            ).limit(50)
                        )
                    ).scalars().all()
                )
                if deps:
                    blocked_task_ids = {d.task_id for d in deps}
                    blocked = list(
                        (
                            await db.execute(
                                select(Task).where(
                                    Task.id.in_(blocked_task_ids)
                                ).limit(20)
                            )
                        ).scalars().all()
                    )
                    hops.append({
                        "kind": "dependency",
                        "label": f"{len(blocked)} tasks blocked downstream",
                        "impact": "execution slip",
                        "detail": _head([t.title for t in blocked], 2),
                        "confidence": "high",
                    })
            # customers: commitments on this project.
            commitments = list(
                (
                    await db.execute(
                        select(CustomerCommitment).where(
                            CustomerCommitment.organization_id == organization_id,
                            CustomerCommitment.project_id == project_id,
                        ).limit(20)
                    )
                ).scalars().all()
            )
            if commitments:
                hops.append({
                    "kind": "customer",
                    "label": f"{len(commitments)} customer commitments on the project",
                    "impact": "commitment risk",
                    "detail": _head([c.summary for c in commitments], 2),
                    "confidence": "high",
                })
            # strategy: objectives linked through this project's initiatives.
            initiatives = list(
                (
                    await db.execute(
                        select(StrategicLink.initiative_id).where(
                            StrategicLink.organization_id == organization_id,
                            StrategicLink.project_id == project_id,
                        )
                    )
                ).scalars().all()
            )
            if initiatives:
                objectives = list(
                    (
                        await db.execute(
                            select(CompanyInitiative.objective_id).where(
                                CompanyInitiative.organization_id == organization_id,
                                CompanyInitiative.id.in_(initiatives),
                            ).limit(10)
                        )
                    ).scalars().all()
                )
                obj_rows = list(
                    (
                        await db.execute(
                            select(CompanyObjective).where(
                                CompanyObjective.organization_id == organization_id,
                                CompanyObjective.id.in_(objectives),
                            ).limit(10)
                        )
                    ).scalars().all()
                )
                if obj_rows:
                    hops.append({
                        "kind": "strategy",
                        "label": f"{len(obj_rows)} objectives linked to the project",
                        "impact": "goal coverage shift",
                        "detail": _head([o.title for o in obj_rows], 2),
                        "confidence": "medium",
                    })
            # capacity: other projects competing for the same capabilities.
            demands = list(
                (
                    await db.execute(
                        select(AllocationDemand).where(
                            AllocationDemand.organization_id == organization_id,
                            AllocationDemand.project_id == project_id,
                        ).limit(20)
                    )
                ).scalars().all()
            )
            if demands:
                capabilities = {d.capability for d in demands}
                others = list(
                    (
                        await db.execute(
                            select(AllocationDemand.project_id).where(
                                AllocationDemand.organization_id == organization_id,
                                AllocationDemand.capability.in_(capabilities),
                                AllocationDemand.project_id != project_id,
                            ).distinct().limit(10)
                        )
                    ).scalars().all()
                )
                if others:
                    hops.append({
                        "kind": "capacity",
                        "label": f"{len(others)} other projects compete for the same capabilities",
                        "impact": "capability contention",
                        "detail": _head([f"project {p}" for p in others], 2),
                        "confidence": "medium",
                    })
        if capability:
            # hire: projects with unmet demand on the capability.
            demands = list(
                (
                    await db.execute(
                        select(AllocationDemand).where(
                            AllocationDemand.organization_id == organization_id,
                            AllocationDemand.capability == capability,
                        ).limit(20)
                    )
                ).scalars().all()
            )
            if demands:
                hops.append({
                    "kind": "capacity",
                    "label": f"{len(demands)} active demands for {capability}",
                    "impact": "capacity relief",
                    "detail": _head(
                        [f"project {d.project_id} ({d.units} units)" for d in demands], 2,
                    ),
                    "confidence": "medium",
                })
                project_ids = {d.project_id for d in demands}
                linked_customers = list(
                    (
                        await db.execute(
                            select(CustomerProjectLink).where(
                                CustomerProjectLink.organization_id == organization_id,
                                CustomerProjectLink.project_id.in_(project_ids),
                            ).limit(20)
                        )
                    ).scalars().all()
                )
                if linked_customers:
                    hops.append({
                        "kind": "customer",
                        "label": f"{len(linked_customers)} customer projects relieved",
                        "impact": "commitment protection",
                        "detail": _head(
                            [f"customer {l.customer_id}" for l in linked_customers], 2,
                        ),
                        "confidence": "medium",
                    })
        return hops

    async def what_happens_if(
        self, db: AsyncSession, *, organization_id: str,
        scenario_type: str, payload: dict[str, Any],
    ) -> dict[str, Any]:
        """EXTENDS what_if with company-level hops (dependency, customer,
        strategy, capacity contention). Labels stay byte-compatible; the
        honesty contract is unchanged — never a prediction, nothing
        executed, humans decide."""
        base = await self.what_if(
            db, organization_id=organization_id,
            scenario_type=scenario_type, payload=payload,
        )
        out = dict(base)
        scenario_type = (scenario_type or "").strip().lower()
        project_id = (payload.get("project_id") or "").strip()
        capability = (payload.get("capability") or "").strip()
        if scenario_type == "delay" and project_id:
            hops = await self._company_hops(
                db, organization_id=organization_id, project_id=project_id,
            )
        elif scenario_type == "hire" and capability:
            hops = await self._company_hops(
                db, organization_id=organization_id, capability=capability,
            )
        else:
            hops = await self._company_hops(
                db, organization_id=organization_id,
                project_id=project_id or None, capability=capability or None,
            )
        out["company_consequences"] = _head(hops, MAX_WHATIF_CONSEQUENCES)
        out["company_hop_kinds"] = sorted({h["kind"] for h in hops})
        return out

    # ------------------------------------------------------------------
    # 11. Slice 4H.2 — Universal Organizational Decision Intelligence
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_asof(value: Any) -> datetime:
        """ISO UTC timestamp, default = now. Never a write-time anchor."""
        if not value:
            return datetime.now(timezone.utc)
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)

    async def _decision_row(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
    ) -> Optional[CompanyDecision]:
        return (
            await db.execute(
                select(CompanyDecision).where(
                    CompanyDecision.organization_id == organization_id,
                    CompanyDecision.decision_id == decision_id,
                )
            )
        ).scalar_one_or_none()

    async def _evidence_rows(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
        as_of: Optional[datetime] = None,
        include_partial: bool = False,
        alternative_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Bounded evidence lineage read. Uses captured_at as the as-of
        anchor (never write-time). Strict mode excludes post-as_of evidence;
        partial mode returns them named in `evidence_incomplete`."""
        stmt = (
            select(CompanyDecisionEvidence)
            .where(
                CompanyDecisionEvidence.organization_id == organization_id,
                CompanyDecisionEvidence.decision_id == decision_id,
            )
        )
        if alternative_key:
            stmt = stmt.where(
                CompanyDecisionEvidence.alternative_key == alternative_key
            )
        rows = list(
            (
                await db.execute(
                    stmt.order_by(CompanyDecisionEvidence.captured_at.asc())
                    .limit(MAX_DECISION_EVIDENCE * 2)
                )
            ).scalars().all()
        )
        as_of = as_of or datetime.now(timezone.utc)
        eligible = [
            r for r in rows if ensure_aware(r.captured_at) <= as_of
        ][:MAX_DECISION_EVIDENCE]
        excluded = [r.evidence_key for r in rows if ensure_aware(r.captured_at) > as_of]
        items = [
            {
                "evidence_key": r.evidence_key,
                "evidence_type": r.evidence_type,
                "source_event_id": r.source_event_id,
                "source_kind": r.source_kind,
                "source_summary": r.source_summary,
                "captured_at": _iso(r.captured_at),
                "weight": r.weight,
                "alternative_key": r.alternative_key,
                "id": r.id,
            }
            for r in eligible
        ]
        return {
            "evidence": items,
            "evidence_count": len(items),
            "evidence_incomplete": excluded if include_partial else [],
            "excluded_count": len(excluded),
        }

    async def _contradiction_count(
        self, db: AsyncSession, *, organization_id: str,
        decision_id: str, statuses: tuple[str, ...] = ("open",),
    ) -> int:
        total = (
            await db.execute(
                select(func.count(CompanyDecisionContradiction.id)).where(
                    CompanyDecisionContradiction.organization_id == organization_id,
                    CompanyDecisionContradiction.decision_id == decision_id,
                    CompanyDecisionContradiction.status.in_(statuses),
                )
            )
        ).scalar_one()
        return int(total or 0)

    def _context_signature(
        self, *, kind: str, scope_type: Optional[str],
        scope_id: Optional[str], metric_keys: list[str],
        title: str = "",
    ) -> str:
        """Deterministic linker: kind + scopes + canonical metric/domain keys
        present in the decision's evidence (sorted, deduped, capped)."""
        tokens: list[str] = [kind]
        if scope_type and scope_id:
            tokens.append(f"scope:{scope_type}:{scope_id}")
        seen: set[str] = set()
        for key in metric_keys or []:
            key = (key or "").strip().lower()[:60]
            if key and key not in seen:
                seen.add(key)
                tokens.append(key)
        return "|".join(tokens)[:240]

    @staticmethod
    def _confidence_band(value: Optional[float]) -> str:
        """PRESENTATION-ONLY classification of the recorded confidence by
        fixed thresholds (§5.7). Never stored, never exported as a
        probability."""
        if value is None:
            return "not_recorded"
        if value < 0.5:
            return "low"
        if value < 0.75:
            return "moderate"
        return "high"

    def _risk_band(
        self, *, confidence: Optional[float],
        contradictions_open: int, reversible: bool,
    ) -> str:
        """Deterministic LOW/MEDIUM/HIGH band from recorded inputs only."""
        if contradictions_open > 0 or (confidence is not None and confidence < 0.5):
            return "HIGH"
        if confidence is None or not reversible:
            return "MEDIUM"
        if confidence >= 0.75:
            return "LOW"
        return "MEDIUM"

    async def _metric_keys_from_evidence(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
    ) -> list[str]:
        """Canonical metric/domain keys cited by this decision's evidence
        (from source_kind, delimited by '.' or ':'); used for signatures."""
        stmt = (
            select(CompanyDecisionEvidence.source_kind).where(
                CompanyDecisionEvidence.organization_id == organization_id,
                CompanyDecisionEvidence.decision_id == decision_id,
            ).limit(MAX_DECISION_EVIDENCE)
        )
        kinds = list((await db.execute(stmt)).scalars().all())
        keys: list[str] = []
        for kind in kinds:
            for token in str(kind or "").replace(":", ".").split("."):
                token = (token or "").strip().lower()
                if token and token not in {"updated", "created", "recorded", "detected"}:
                    keys.append(token)
        return sorted(set(keys))

    def _risk_banded_quality_summary(self, q: CompanyDecisionQuality) -> dict[str, Any]:
        return {
            "quality_key": q.quality_key,
            "stage": q.stage,
            "evidence_count": q.evidence_count,
            "confidence_support": q.confidence_support,
            "prediction_alignment": q.prediction_alignment,
            "risk_band": q.risk_band,
            "contradictions_surfaced": q.contradictions_surfaced,
            "assess": q.assess_json or {},
            "source_event_id": q.source_event_id,
            "created_at": _iso(q.created_at),
        }

    # -------------------------------------------------------------- writes

    async def evaluate_decision(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Advisory evaluation: opens (or continues) a decision at
        proposed -> evaluated with evidence lineage + alternative seeds.
        Exact-once on the source event; replay is a no-op."""
        decision_id = (payload.get("decision_id") or "").strip()
        source_event_id = str(getattr(event, "id", "") or "") or decision_id
        if not decision_id:
            return {"accepted": False, "reason": "decision_id required"}
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        created = row is None
        if row is None:
            row = CompanyDecision(
                organization_id=organization_id,
                decision_id=decision_id,
                kind=(payload.get("kind") or "other").strip()[:32] or "other",
                title=(payload.get("title") or "").strip()[:240],
                recommendation_key=(payload.get("recommendation_key") or "").strip()[:120],
                rationale=(payload.get("rationale") or "").strip()[:4000],
                impact_label=(payload.get("impact_label") or "").strip()[:160],
                expected_improvement=(payload.get("expected_improvement") or "").strip()[:240],
                confidence=None,
                owner_label=(payload.get("owner_label") or "").strip()[:120],
                state="proposed",
                approver_label="",
                note="",
                approved_at=None,
                as_of_context_json=payload.get("as_of_context") or None,
                scope_type=(payload.get("scope_type") or "").strip()[:12] or None,
                scope_id=(payload.get("scope_id") or "").strip()[:32] or None,
                event_name=getattr(event, "name", "") or "",
                source_event_id=source_event_id,
            )
            db.add(row)
            await db.flush()
        if row.state in ("approved", "declined", "executed", "outcome_recorded", "assessed"):
            return {"accepted": True, "decision_id": decision_id,
                    "state": row.state, "note": "already past the evaluation stage"}
        evidence_written = 0
        for i, ev in enumerate(payload.get("evidence") or []):
            if i >= MAX_DECISION_EVIDENCE:
                break
            if not isinstance(ev, dict):
                continue
            etype = (ev.get("evidence_type") or "").strip()
            if etype not in DECISION_EVIDENCE_TYPES:
                continue
            evidence_key = f"ev:{decision_id}:{i + 1:03d}"
            exists = (
                await db.execute(
                    select(CompanyDecisionEvidence.id).where(
                        CompanyDecisionEvidence.organization_id == organization_id,
                        CompanyDecisionEvidence.decision_id == decision_id,
                        CompanyDecisionEvidence.evidence_key == evidence_key,
                    )
                )
            ).scalar_one_or_none()
            if exists:
                continue
            captured = self._parse_asof(ev.get("captured_at"))
            try:
                weight = max(0.0, min(1.0, float(ev.get("weight") or 1.0)))
            except (TypeError, ValueError):
                weight = 1.0
            db.add(CompanyDecisionEvidence(
                organization_id=organization_id,
                decision_id=decision_id,
                alternative_key=(ev.get("alternative_key") or "").strip()[:80] or None,
                evidence_key=evidence_key,
                evidence_type=etype,
                source_event_id=(ev.get("source_event_id") or "").strip()[:64] or None,
                source_kind=(ev.get("source_kind") or "").strip()[:60],
                source_summary=(ev.get("source_summary") or "").strip()[:400],
                captured_at=captured,
                weight=weight,
            ))
            evidence_written += 1
        if row.state == "proposed":
            row.state = "evaluated"
        # 4H.3 §7.2: attach the decide-time state anchor when the decision is
        # opened (additive; never mutates 4H.2 fields).
        if created and row.state_context_json is None:
            row.state_context_json = await self._state_context_anchor(
                db, organization_id=organization_id,
            )
        await db.flush()
        if evidence_written:
            await self.compose_quality(
                db, organization_id=organization_id, event=event,
                payload={
                    "decision_id": decision_id, "stage": "evaluated",
                    "kind": row.kind, "title": row.title,
                    "scope_type": row.scope_type, "scope_id": row.scope_id,
                },
            )
        # Alternatives are seeded ONLY when the decision is opened: later
        # deliveries of the same payload (replays) must never re-mutate the
        # alternative/why-not rows or re-emit their events — updates belong
        # to the dedicated alternatives / why-not endpoints.
        if created and payload.get("alternatives"):
            await self.record_alternatives(
                db, organization_id=organization_id, event=event, payload={
                    "decision_id": decision_id,
                    "alternatives": payload.get("alternatives"),
                },
            )
        if created or evidence_written:
            from app.events.publisher import publish_background_event

            await publish_background_event(
                db, name="company.decision.evaluated",
                organization_id=organization_id,
                payload={
                    "organization_id": organization_id,
                    "decision_id": decision_id,
                    "state": row.state,
                    "evidence_written": evidence_written,
                },
            )
        return {
            "accepted": True,
            "decision_id": decision_id,
            "state": row.state,
            "evidence_written": evidence_written,
            "decision": self._decision_payload(row),
        }

    async def record_alternatives(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Alternatives + why-not upserts (exact-once on alternative_key).
        Exactly one chosen per decision; why_chosen iff chosen; why_not
        required for rejected alternatives; at least two alternatives for a
        decision reaching recommended."""
        decision_id = (payload.get("decision_id") or "").strip()
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return {"accepted": False, "reason": "decision not found"}
        alternatives = [a for a in (payload.get("alternatives") or []) if isinstance(a, dict)]
        chosen_count = 0
        written = 0
        errors: list[str] = []
        for i, alt in enumerate(alternatives[:MAX_ALTERNATIVES]):
            alternative_key = (alt.get("alternative_key") or f"alt:{decision_id}:{i + 1:02d}").strip()[:80]
            chosen = bool(alt.get("chosen"))
            why_chosen = (alt.get("why_chosen") or "").strip()
            why_not = (alt.get("why_not") or "").strip()
            if chosen:
                chosen_count += 1
            existing = (
                await db.execute(
                    select(CompanyDecisionAlternative).where(
                        CompanyDecisionAlternative.organization_id == organization_id,
                        CompanyDecisionAlternative.decision_id == decision_id,
                        CompanyDecisionAlternative.alternative_key == alternative_key,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.chosen = chosen
                existing.why_chosen = why_chosen
                existing.why_not = why_not
                existing.preferable_if = (alt.get("preferable_if") or "").strip()[:4000] or None
                existing.label = (alt.get("label") or existing.label).strip()[:240]
                existing.description = (alt.get("description") or existing.description).strip()[:4000]
                existing.expected_outcome = alt.get("expected_outcome") or existing.expected_outcome
                existing.evidence_json = alt.get("evidence") or existing.evidence_json or []
                written += 1
                continue
            db.add(CompanyDecisionAlternative(
                organization_id=organization_id,
                decision_id=decision_id,
                alternative_key=alternative_key,
                label=(alt.get("label") or "").strip()[:240],
                description=(alt.get("description") or "").strip()[:4000],
                expected_outcome=alt.get("expected_outcome"),
                chosen=chosen,
                why_chosen=why_chosen,
                why_not=why_not,
                preferable_if=(alt.get("preferable_if") or "").strip()[:4000] or None,
                evidence_json=alt.get("evidence") or [],
            ))
            written += 1
        await db.flush()
        rows = list(
            (
                await db.execute(
                    select(CompanyDecisionAlternative).where(
                        CompanyDecisionAlternative.organization_id == organization_id,
                        CompanyDecisionAlternative.decision_id == decision_id,
                    )
                )
            ).scalars().all()
        )
        chosen = [a for a in rows if a.chosen]
        if len(chosen) > 1:
            errors.append("exactly one chosen alternative allowed")
        for a in rows:
            if a.chosen and not a.why_chosen:
                errors.append(f"{a.alternative_key}: why_chosen required for the chosen alternative")
            if not a.chosen and not a.why_not:
                errors.append(f"{a.alternative_key}: why_not required for rejected alternatives")
        if len(rows) < 2 and row.state in ("evaluated", "recommended"):
            errors.append("at least two alternatives required for evaluated/recommended decisions")
        if written:
            from app.events.publisher import publish_background_event

            await publish_background_event(
                db, name="company.decision.alternatives.recorded",
                organization_id=organization_id,
                payload={
                    "organization_id": organization_id,
                    "decision_id": decision_id,
                    "written": written,
                    "total": len(rows),
                    "chosen": [a.alternative_key for a in chosen],
                },
            )
            if any((not a.chosen) and bool(a.why_not) for a in rows):
                await publish_background_event(
                    db, name="company.decision.why_not.recorded",
                    organization_id=organization_id,
                    payload={
                        "organization_id": organization_id,
                        "decision_id": decision_id,
                        "rejected_count": sum(1 for a in rows if (not a.chosen) and bool(a.why_not)),
                    },
                )
        return {
            "accepted": not errors,
            "decision_id": decision_id,
            "written": written,
            "total": len(rows),
            "chosen": [a.alternative_key for a in chosen],
            "errors": errors,
            "alternatives": [self._alternative_payload(a) for a in rows],
        }

    async def record_why_not(
        self, db: AsyncSession, *, organization_id: str,
        decision_id: str, alternative_key: str, why_not: str,
        preferable_if: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record/update ONE rejected alternative's why-not + reversibility
        condition. Exact-once: the audit event fires only when the record
        actually changed, so replays converge. The chosen alternative carries
        why_chosen, never a why-not."""
        from app.events.publisher import publish_background_event

        decision_id = (decision_id or "").strip()
        alternative_key = (alternative_key or "").strip()
        why_not = (why_not or "").strip()
        preferable_if = (preferable_if or "").strip()[:4000] or None
        if not why_not:
            return {"accepted": False, "reason": "why_not is required"}
        alt = (
            await db.execute(
                select(CompanyDecisionAlternative).where(
                    CompanyDecisionAlternative.organization_id == organization_id,
                    CompanyDecisionAlternative.decision_id == decision_id,
                    CompanyDecisionAlternative.alternative_key == alternative_key,
                )
            )
        ).scalar_one_or_none()
        if alt is None:
            return {"accepted": False, "reason": "alternative not found"}
        if alt.chosen:
            return {"accepted": False, "reason": "the chosen alternative carries why_chosen, not a why-not"}
        why_not = why_not[:4000]
        changed = (alt.why_not != why_not) or (alt.preferable_if != preferable_if)
        alt.why_not = why_not
        alt.preferable_if = preferable_if
        await db.flush()
        if changed:
            await publish_background_event(
                db, name="company.decision.why_not.recorded",
                organization_id=organization_id,
                payload={
                    "organization_id": organization_id,
                    "decision_id": decision_id,
                    "alternative_key": alternative_key,
                    "why_not": why_not,
                },
            )
        return {
            "accepted": True,
            "decision_id": decision_id,
            "alternative_key": alternative_key,
            "why_not": alt.why_not,
            "preferable_if": alt.preferable_if,
            "changed": changed,
        }

    def _alternative_payload(self, a: CompanyDecisionAlternative) -> dict[str, Any]:
        return {
            "alternative_key": a.alternative_key,
            "label": a.label,
            "description": a.description,
            "expected_outcome": a.expected_outcome,
            "chosen": a.chosen,
            "why_chosen": a.why_chosen,
            "why_not": a.why_not,
            "preferable_if": a.preferable_if,
            "evidence": a.evidence_json or [],
            "created_at": _iso(a.created_at),
        }

    async def recommend_decision(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Advisory recommendation: state -> recommended, then precedes the
        recommendation with precedent links + contradiction surfacing + a
        quality snapshot. Each internally-produced artifact is published as
        its own audit event ONLY when new rows were actually written, so
        replays converge (identical list lengths, no duplicate events)."""
        from app.events.publisher import publish_background_event

        decision_id = (payload.get("decision_id") or "").strip()
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return {"accepted": False, "reason": "decision not found"}
        if row.state in ("approved", "declined", "executed", "outcome_recorded", "assessed", "recommended"):
            return {"accepted": True, "decision_id": decision_id,
                    "state": row.state, "note": "already past the recommendation stage"}
        prior_state = row.state
        if row.state == "proposed":
            row.state = "evaluated"
        row.state = "recommended"
        transitioned = prior_state != row.state
        # 4H.3 §7.2: the recommend-time state anchor (additive, once).
        if transitioned and row.state_context_json is None:
            row.state_context_json = await self._state_context_anchor(
                db, organization_id=organization_id,
            )
        await db.flush()
        if transitioned:
            await publish_background_event(
                db, name="company.decision.recommended",
                organization_id=organization_id,
                payload={
                    "organization_id": organization_id,
                    "decision_id": decision_id,
                    "kind": row.kind,
                    "title": row.title,
                },
            )
        metric_keys = await self._metric_keys_from_evidence(
            db, organization_id=organization_id, decision_id=decision_id,
        )
        signature = self._context_signature(
            kind=row.kind, scope_type=row.scope_type, scope_id=row.scope_id,
            metric_keys=metric_keys, title=row.title,
        )
        candidate_ids = await self._precedent_candidates(
            db, organization_id=organization_id, decision_id=decision_id,
            kind=row.kind, metric_keys=metric_keys, limit=MAX_PRECEDENTS,
        )
        linked = 0
        for pid, relevance in candidate_ids:
            ok = await self.link_precedents(
                db, organization_id=organization_id, event=event, payload={
                    "decision_id": decision_id,
                    "precedent_decision_id": pid,
                    "context_signature": signature,
                    "relevance_score": relevance,
                    "metric_keys": metric_keys,
                    "kind": row.kind,
                },
            )
            if ok:
                linked += 1
                await publish_background_event(
                    db, name="company.decision.precedents.linked",
                    organization_id=organization_id,
                    payload={
                        "organization_id": organization_id,
                        "decision_id": decision_id,
                        "precedent_decision_id": pid,
                        "context_signature": signature,
                        "relevance_score": relevance,
                    },
                )
        contradictions = await self._detect_contradictions(
            db, organization_id=organization_id, decision_id=decision_id,
            kind=row.kind, metric_keys=metric_keys,
            precedent_candidates=candidate_ids,
        )
        surfaced = 0
        for i, contra in enumerate(contradictions):
            ok = await self.surface_contradictions(
                db, organization_id=organization_id, event=event, payload={
                    "decision_id": decision_id,
                    "contradiction_index": i + 1,
                    "lesson_memory_id": contra.get("lesson_memory_id"),
                    "precedent_decision_id": contra.get("precedent_decision_id"),
                    "side_a": contra.get("side_a"),
                    "side_b": contra.get("side_b"),
                },
            )
            if ok:
                surfaced += 1
                await publish_background_event(
                    db, name="company.decision.contradiction.surfaced",
                    organization_id=organization_id,
                    payload={
                        "organization_id": organization_id,
                        "decision_id": decision_id,
                        "contradiction_key": f"cx:{decision_id}:{i + 1:03d}",
                        "lesson_memory_id": contra.get("lesson_memory_id"),
                        "precedent_decision_id": contra.get("precedent_decision_id"),
                    },
                )
        await self.compose_quality(
            db, organization_id=organization_id, event=event,
            payload={
                "decision_id": decision_id, "stage": "recommended",
                "kind": row.kind, "title": row.title,
                "scope_type": row.scope_type, "scope_id": row.scope_id,
            },
        )
        return {
            "accepted": True,
            "decision_id": decision_id,
            "state": row.state,
            "precedents_linked": linked,
            "contradictions_surfaced": surfaced,
            "context_signature": signature,
            "decision": self._decision_payload(row),
        }

    async def _precedent_candidates(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
        kind: str, metric_keys: list[str], limit: int = MAX_PRECEDENTS,
    ) -> list[tuple[str, float]]:
        """Rank candidate past decisions by context overlap + outcome of
        record + evidence weight. Indexed, bounded, never a full scan."""
        past = list(
            (
                await db.execute(
                    select(CompanyDecision).where(
                        CompanyDecision.organization_id == organization_id,
                        CompanyDecision.decision_id != decision_id,
                        CompanyDecision.state.in_(
                            ("approved", "declined", "executed", "outcome_recorded")
                        ),
                        CompanyDecision.kind == kind,
                    ).order_by(CompanyDecision.updated_at.desc())
                    .limit(MAX_PRECEDENTS * 3)
                )
            ).scalars().all()
        )
        if not past:
            return []
        metric_set = set(metric_keys)
        scored: list[tuple[float, str]] = []
        for d in past:
            past_keys = await self._metric_keys_from_evidence(
                db, organization_id=organization_id, decision_id=d.decision_id,
            )
            overlap = len(metric_set.intersection(set(past_keys)))
            outcome_bonus = {
                "outcome_recorded": 1.0,
                "executed": 0.7,
                "approved": 0.5,
                "declined": 0.6,
            }.get(d.state, 0.0)
            evidence_bonus = min(0.3, (d.quality_evidence_count or 0) / 40.0 * 0.3)
            if not overlap and overlap != 0:
                pass
            relevance = min(1.0, (overlap / max(1, len(metric_set))) * 0.6 + outcome_bonus * 0.3 + evidence_bonus)
            scored.append((relevance, d.decision_id))
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [(pid, rel) for rel, pid in scored[:limit]]

    async def link_precedents(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> bool:
        """Write ONE precedent citation row, exact-once on
        (org, decision_id, precedent_decision_id). Returns True only when a
        row was actually created (the caller publishes the audit event)."""
        decision_id = (payload.get("decision_id") or "").strip()
        precedent_decision_id = (payload.get("precedent_decision_id") or "").strip()
        if not decision_id or not precedent_decision_id:
            return False
        exists = (
            await db.execute(
                select(CompanyDecisionPrecedent.id).where(
                    CompanyDecisionPrecedent.organization_id == organization_id,
                    CompanyDecisionPrecedent.decision_id == decision_id,
                    CompanyDecisionPrecedent.precedent_decision_id == precedent_decision_id,
                )
            )
        ).scalar_one_or_none()
        if exists:
            return False
        past = await self._decision_row(
            db, organization_id=organization_id, decision_id=precedent_decision_id,
        )
        if past is None:
            return False
        relevance = float(payload.get("relevance_score") or 0.0)
        evidence_count = await self._evidence_count_async(
            db, organization_id=organization_id, decision_id=precedent_decision_id,
        )
        db.add(CompanyDecisionPrecedent(
            organization_id=organization_id,
            decision_id=decision_id,
            precedent_decision_id=precedent_decision_id,
            context_signature=(payload.get("context_signature") or "").strip()[:240],
            relevance_score=max(0.0, min(1.0, relevance)),
            evidence_count=evidence_count,
            cited_lesson=past.lesson[:4000],
            source_event_id=str(getattr(event, "id", "") or "")[:64] or precedent_decision_id,
        ))
        await db.flush()
        return True

    async def _evidence_count_async(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
    ) -> int:
        async def _cnt() -> int:
            scoped = (
                select(func.count(CompanyDecisionEvidence.id)).where(
                    CompanyDecisionEvidence.organization_id == organization_id,
                    CompanyDecisionEvidence.decision_id == decision_id,
                )
            )
            return int((await db.execute(scoped)).scalar_one() or 0)
        return await _cnt()

    async def _detect_contradictions(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
        kind: str, metric_keys: list[str],
        precedent_candidates: list[tuple[str, float]],
    ) -> list[dict[str, Any]]:
        """Honest contradiction surfacing: a recommended decision conflicts
        with a recorded lesson or an unsuccessful precedent. Both sides are
        returned with provenance; no side is silently selected."""
        contradictions: list[dict[str, Any]] = []
        decision = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if decision is None:
            return contradictions
        side_a = {
            "decision_id": decision_id,
            "title": decision.title,
            "kind": kind,
            "claims": [f"{decision.title} recommended based on recorded evidence"],
            "evidence_keys": [
                e.evidence_key for e in await self._evidence_scan(
                    db, organization_id=organization_id, decision_id=decision_id,
                )
            ],
            "captured_at": _iso(datetime.now(timezone.utc)),
        }
        for pid, relevance in precedent_candidates:
            if relevance < 0.45:
                continue
            past = await self._decision_row(db, organization_id=organization_id, decision_id=pid)
            if past is None:
                continue
            if past.outcome_kind in ("unsuccessful", "partial"):
                contradictions.append({
                    "lesson_memory_id": None,
                    "precedent_decision_id": pid,
                    "side_a": side_a,
                    "side_b": {
                        "precedent_decision_id": pid,
                        "title": past.title,
                        "kind": past.kind,
                        "outcome_kind": past.outcome_kind,
                        "effectiveness": past.effectiveness,
                        "lesson": past.lesson,
                        "claims": [
                            f"a comparable decision '{past.title}' "
                            f"recorded outcome '{past.outcome_kind}'"
                            f"{f' (effectiveness {past.effectiveness:.2f})' if past.effectiveness is not None else ''}"
                        ],
                        "evidence_keys": [
                            e.evidence_key for e in await self._evidence_scan(
                                db, organization_id=organization_id, decision_id=pid,
                            )
                        ],
                        "captured_at": _iso(past.updated_at),
                    },
                })
        # past lessons contradicting the recommended choice
        from app.models.company_memory import CompanyMemory as _CompanyMemory

        lessons = list(
            (
                await db.execute(
                    select(_CompanyMemory).where(
                        _CompanyMemory.organization_id == organization_id,
                        _CompanyMemory.fact_kind == "lesson",
                    ).order_by(_CompanyMemory.created_at.desc())
                    .limit(20)
                )
            ).scalars().all()
        )
        for mem in lessons:
            text = f"{(mem.title or '')} {(mem.lesson or '')}".lower()
            conflict = False
            for key in metric_keys:
                if key and key in text:
                    conflict = True
                    break
            if not conflict:
                continue
            outcome = (mem.outcome or "").strip().lower() if isinstance(mem.outcome, str) else ""
            outcome_type = (
                (mem.outcome_type or "").strip().lower()
                if isinstance(mem.outcome_type, str) else ""
            )
            if outcome_type in ("unsuccessful", "partial") or outcome in ("unsuccessful", "partial"):
                contradictions.append({
                    "lesson_memory_id": mem.id,
                    "precedent_decision_id": None,
                    "side_a": side_a,
                    "side_b": {
                        "lesson_memory_id": mem.id,
                        "title": mem.title,
                        "outcome": mem.outcome,
                        "outcome_type": mem.outcome_type,
                        "lesson": mem.lesson,
                        "claims": [
                            f"recorded lesson on '{mem.title}' reports outcome "
                            f"'{mem.outcome}'"
                        ],
                        "evidence_keys": [
                            str(e.get("id") or e.get("memory_id") or "")
                            for e in (mem.evidence_json or [])
                            if isinstance(e, dict)
                        ],
                        "captured_at": _iso(mem.created_at),
                    },
                })
        return contradictions[:MAX_PRECEDENTS]

    async def _evidence_scan(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
    ) -> list[CompanyDecisionEvidence]:
        stmt = (
            select(CompanyDecisionEvidence).where(
                CompanyDecisionEvidence.organization_id == organization_id,
                CompanyDecisionEvidence.decision_id == decision_id,
            ).limit(MAX_DECISION_EVIDENCE)
        )
        return list((await db.execute(stmt)).scalars().all())

    async def surface_contradictions(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> bool:
        """Write ONE contradiction row, exact-once on contradiction_key.
        Returns True only when a row was actually created."""
        decision_id = (payload.get("decision_id") or "").strip()
        index = int(payload.get("contradiction_index") or 1)
        contradiction_key = f"cx:{decision_id}:{index:03d}"
        exists = (
            await db.execute(
                select(CompanyDecisionContradiction.id).where(
                    CompanyDecisionContradiction.organization_id == organization_id,
                    CompanyDecisionContradiction.decision_id == decision_id,
                    CompanyDecisionContradiction.contradiction_key == contradiction_key,
                )
            )
        ).scalar_one_or_none()
        if exists:
            return False
        db.add(CompanyDecisionContradiction(
            organization_id=organization_id,
            decision_id=decision_id,
            contradiction_key=contradiction_key,
            lesson_memory_id=(payload.get("lesson_memory_id") or "").strip()[:32] or None,
            precedent_decision_id=(payload.get("precedent_decision_id") or "").strip()[:32] or None,
            side_a_json=payload.get("side_a") or {},
            side_b_json=payload.get("side_b") or {},
            status="open",
            source_event_id=str(getattr(event, "id", "") or "")[:64],
        ))
        await db.flush()
        return True

    async def compose_quality(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Exact-once quality snapshot per stage (§3.4, §5.3). Quality is an
        attribute of the DECISION built from recorded evidence only; it never
        names or ranks persons. 'Not yet measurable' is explicit, never a
        fake 0."""
        from app.events.publisher import publish_background_event

        decision_id = (payload.get("decision_id") or "").strip()
        stage = (payload.get("stage") or "").strip()
        if stage not in QUALITY_STAGES or not decision_id:
            return {"accepted": False, "reason": "stage/decision required"}
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return {"accepted": False, "reason": "decision not found"}
        quality_key = f"q:{decision_id}:{stage}:1"
        exists = (
            await db.execute(
                select(CompanyDecisionQuality.id).where(
                    CompanyDecisionQuality.organization_id == organization_id,
                    CompanyDecisionQuality.decision_id == decision_id,
                    CompanyDecisionQuality.quality_key == quality_key,
                )
            )
        ).scalar_one_or_none()
        if exists:
            return {"accepted": True, "quality_key": quality_key, "created": False}
        evidence_count = await self._evidence_count_async(
            db, organization_id=organization_id, decision_id=decision_id,
        )
        contradictions_total = await self._contradiction_count(
            db, organization_id=organization_id, decision_id=decision_id,
            statuses=CONTRADICTION_STATUSES,
        )
        contradictions_open = await self._contradiction_count(
            db, organization_id=organization_id, decision_id=decision_id,
            statuses=("open",),
        )
        compare = row.actual_outcome_compare if isinstance(row.actual_outcome_compare, dict) else None
        alignment_value = compare.get("aligned") if compare else None
        prediction_alignment = (
            1.0 if alignment_value is True else 0.0
        ) if alignment_value is not None else None
        alternatives = list(
            (
                await db.execute(
                    select(CompanyDecisionAlternative).where(
                        CompanyDecisionAlternative.organization_id == organization_id,
                        CompanyDecisionAlternative.decision_id == decision_id,
                    )
                )
            ).scalars().all()
        )
        chosen = next((a for a in alternatives if a.chosen), None)
        reversible = bool(chosen is not None and chosen.preferable_if)
        risk_band = self._risk_band(
            confidence=row.prediction_confidence,
            contradictions_open=contradictions_open,
            reversible=reversible,
        )
        evidence_rows = await self._evidence_scan(
            db, organization_id=organization_id, decision_id=decision_id,
        )
        cohort_row = CompanyDecisionQuality(
            organization_id=organization_id,
            decision_id=decision_id,
            quality_key=quality_key,
            stage=stage,
            evidence_count=evidence_count,
            confidence_support=row.prediction_confidence,
            prediction_alignment=prediction_alignment,
            risk_band=risk_band,
            contradictions_surfaced=contradictions_total,
            assess_json={
                "decision_id": decision_id,
                "kind": row.kind,
                "title": row.title,
                "stage": stage,
                "composition": {
                    "evidence_support": min(1.0, evidence_count / max(1, row.quality_evidence_count or 1)) if (row.quality_evidence_count or 0) else min(1.0, evidence_count / 10.0),
                    "prediction_alignment": prediction_alignment,
                    "prediction_alignment_uncertain": prediction_alignment is None,
                    "contradiction_cleanliness": max(0.0, 1.0 - 0.25 * contradictions_open),
                    "reversibility": 1.0 if reversible else 0.0,
                },
                "evidence_ids": [e.id for e in evidence_rows],
                "event_ids": sorted({e.source_event_id for e in evidence_rows if e.source_event_id}),
                "confidence_band": self._confidence_band(row.prediction_confidence),
                "reversibility": {
                    "reversible": reversible,
                    "preferable_if_present": bool(chosen.preferable_if if chosen else None),
                },
                "epistemic_safeguard": (
                    "A business outcome can have multiple causes. 4H.2 evaluates "
                    "the decision's recorded prediction, evidence and alternatives "
                    "against the observed outcome; it does not claim the outcome "
                    "was produced solely by this decision."
                ),
                "advisory_only": True,
            },
            source_event_id=str(getattr(event, "id", "") or "")[:64] or quality_key,
        )
        db.add(cohort_row)
        await db.flush()
        row.quality_evidence_count = evidence_count
        await publish_background_event(
            db, name="company.decision.quality.composed",
            organization_id=organization_id,
            payload={
                "organization_id": organization_id,
                "decision_id": decision_id,
                "quality_key": quality_key,
                "stage": stage,
                "evidence_count": evidence_count,
            },
        )
        return {"accepted": True, "quality_key": quality_key, "created": True}

    async def update_tracks(
        self, db: AsyncSession, *, organization_id: str,
        event: Any, payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Append-only cohort rollup snapshots (§3.5 temporal law). Keys are
        (org, cohort_key, decision's canonical source_event_id) so replays
        converge and never rewrite history."""
        from app.events.publisher import publish_background_event

        decision_id = (payload.get("decision_id") or "").strip()
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return {"accepted": False, "reason": "decision not found"}
        if row.outcome_kind not in OUTCOME_KINDS:
            return {"accepted": False, "reason": "no measured outcome yet"}
        cohorts = [
            f"kind:{row.kind}",
        ]
        if row.scope_type and row.scope_id:
            cohorts.append(f"kind:{row.kind}:scope:{row.scope_type}:{row.scope_id}")
        if row.approved_at is not None:
            cohorts.append(f"period:{row.approved_at.strftime('%Y-%m')}")
        source_event_id = row.source_event_id or str(getattr(event, "id", "") or "")
        created = 0
        for cohort_key in cohorts:
            key_exists = (
                await db.execute(
                    select(CompanyDecisionTrack.id).where(
                        CompanyDecisionTrack.organization_id == organization_id,
                        CompanyDecisionTrack.cohort_key == cohort_key,
                        CompanyDecisionTrack.source_event_id == source_event_id,
                    )
                )
            ).scalar_one_or_none()
            if key_exists:
                continue
            decisions = list(
                (
                    await db.execute(
                        select(CompanyDecision).where(
                            CompanyDecision.organization_id == organization_id,
                            CompanyDecision.state == "outcome_recorded",
                            CompanyDecision.kind == row.kind,
                        )
                    )
                ).scalars().all()
            )
            aligned = partial = misaligned = 0
            measured = 0
            effective_sum = 0.0
            for d in decisions:
                cmp = d.actual_outcome_compare if isinstance(d.actual_outcome_compare, dict) else None
                if cmp is None:
                    continue
                measured += 1
                if cmp.get("aligned") is True:
                    aligned += 1
                elif cmp.get("aligned") is False:
                    misaligned += 1
                else:
                    partial += 1
                if d.effectiveness is not None:
                    effective_sum += d.effectiveness
            db.add(CompanyDecisionTrack(
                organization_id=organization_id,
                cohort_key=cohort_key,
                decisions_measured=measured,
                predictions_recorded=len(decisions),
                aligned=aligned,
                partial=partial,
                misaligned=misaligned,
                avg_effectiveness=(
                    effective_sum / measured if measured else None
                ),
                source_event_id=source_event_id,
                snapshot_ts=datetime.now(timezone.utc),
            ))
            created += 1
        await db.flush()
        if created:
            await publish_background_event(
                db, name="company.decision.track.updated",
                organization_id=organization_id,
                payload={
                    "organization_id": organization_id,
                    "decision_id": decision_id,
                    "cohort_keys": cohorts[:8],
                    "snapshots_created": created,
                },
            )
        return {"accepted": True, "snapshots_created": created, "cohorts": cohorts[:8]}

    # --------------------------------------------------------------- reads

    async def decisions(
        self, db: AsyncSession, *, organization_id: str,
        kind: Optional[str] = None, state: Optional[str] = None,
        scope_type: Optional[str] = None, scope_id: Optional[str] = None,
        since: Optional[str] = None, as_of: Optional[str] = None,
        limit: int = 20, page: int = 1,
    ) -> dict[str, Any]:
        """Paginated decision list with evidence counts + prediction fields.
        Bounded (default 20, max 100), indexed, tenant-scoped."""
        stmt = (
            select(CompanyDecision)
            .where(CompanyDecision.organization_id == organization_id)
        )
        if kind:
            stmt = stmt.where(CompanyDecision.kind == kind)
        if state:
            stmt = stmt.where(CompanyDecision.state == state)
        if scope_type and scope_id:
            stmt = stmt.where(CompanyDecision.scope_type == scope_type)
            stmt = stmt.where(CompanyDecision.scope_id == scope_id)
        if since:
            try:
                since_dt = datetime.fromisoformat(str(since).replace("Z", "+00:00"))
                stmt = stmt.where(CompanyDecision.updated_at >= since_dt)
            except ValueError:
                pass
        as_of_dt = self._parse_asof(as_of)
        stmt = stmt.where(CompanyDecision.updated_at <= as_of_dt)
        limit = max(1, min(int(limit or 20), 100))
        page = max(1, int(page or 1))
        total = int(
            (
                await db.execute(
                    select(func.count()).select_from(stmt.subquery())
                )
            ).scalar_one() or 0
        )
        rows = list(
            (
                await db.execute(
                    stmt.order_by(CompanyDecision.updated_at.desc())
                    .offset((page - 1) * limit).limit(limit)
                )
            ).scalars().all()
        )
        out: list[dict[str, Any]] = []
        for d in rows:
            item = {
                "decision_id": d.decision_id,
                "kind": d.kind,
                "title": d.title,
                "state": d.state,
                "owner_label": d.owner_label,
                "outcome_kind": d.outcome_kind,
                "effectiveness": d.effectiveness,
                "evidence_count": await self._evidence_count_async(
                    db, organization_id=organization_id, decision_id=d.decision_id,
                ),
                "updated_at": _iso(d.updated_at),
                "scope_type": d.scope_type,
                "scope_id": d.scope_id,
                **self._prediction_fields(d),
            }
            out.append(item)
        return {
            "advisory_only": True,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
            "decisions": out,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def decision_detail(
        self, db: AsyncSession, *, organization_id: str,
        decision_id: str, as_of: Optional[str] = None,
        include_partial: bool = False,
    ) -> Optional[dict[str, Any]]:
        """Full decision: rationale, alternatives (chosen + why-not), evidence
        lineage (as_of-filtered), prediction fields, quality snapshots,
        contradictions + precedents. Never leaks post-as_of information."""
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return None
        as_of_dt = self._parse_asof(as_of)
        evidence = await self._evidence_rows(
            db, organization_id=organization_id, decision_id=decision_id,
            as_of=as_of_dt, include_partial=include_partial,
        )
        alternatives = list(
            (
                await db.execute(
                    select(CompanyDecisionAlternative).where(
                        CompanyDecisionAlternative.organization_id == organization_id,
                        CompanyDecisionAlternative.decision_id == decision_id,
                    ).order_by(CompanyDecisionAlternative.alternative_key.asc())
                )
            ).scalars().all()
        )
        quality_rows = list(
            (
                await db.execute(
                    select(CompanyDecisionQuality).where(
                        CompanyDecisionQuality.organization_id == organization_id,
                        CompanyDecisionQuality.decision_id == decision_id,
                    ).order_by(CompanyDecisionQuality.created_at.asc())
                )
            ).scalars().all()
        )
        contradiction_rows = list(
            (
                await db.execute(
                    select(CompanyDecisionContradiction).where(
                        CompanyDecisionContradiction.organization_id == organization_id,
                        CompanyDecisionContradiction.decision_id == decision_id,
                    ).order_by(CompanyDecisionContradiction.created_at.asc())
                )
            ).scalars().all()
        )
        precedent_rows = list(
            (
                await db.execute(
                    select(CompanyDecisionPrecedent).where(
                        CompanyDecisionPrecedent.organization_id == organization_id,
                        CompanyDecisionPrecedent.decision_id == decision_id,
                    ).order_by(CompanyDecisionPrecedent.relevance_score.desc())
                )
            ).scalars().all()
        )
        compare = row.actual_outcome_compare if isinstance(row.actual_outcome_compare, dict) else None
        prediction = self._prediction_fields(row)
        prediction["confidence_band"] = self._confidence_band(row.prediction_confidence)
        prediction["supporting_evidence_count"] = evidence["evidence_count"]
        prediction["contradicting_evidence_count"] = len(contradiction_rows)
        prediction["comparable_precedents_count"] = len(precedent_rows)
        if compare is None and row.state in ("approved", "executed"):
            prediction["not_yet_measurable"] = True
        return {
            "advisory_only": True,
            "decision_id": row.decision_id,
            "kind": row.kind,
            "title": row.title,
            "state": row.state,
            "rationale": row.rationale,
            "recommendation_key": row.recommendation_key,
            "impact_label": row.impact_label,
            "expected_improvement": row.expected_improvement,
            "owner_label": row.owner_label,
            "approver_label": row.approver_label,
            "scope_type": row.scope_type,
            "scope_id": row.scope_id,
            "approved_at": _iso(row.approved_at),
            "executed_at": _iso(row.executed_at),
            "outcome_kind": row.outcome_kind,
            "effectiveness": row.effectiveness,
            "lesson": row.lesson,
            "note": row.note,
            "generated_at": _iso(datetime.now(timezone.utc)),
            "evidence": evidence["evidence"],
            "evidence_count": evidence["evidence_count"],
            "evidence_incomplete": evidence["evidence_incomplete"] if include_partial else [],
            "alternatives": [self._alternative_payload(a) for a in alternatives],
            "quality": [self._risk_banded_quality_summary(q) for q in quality_rows],
            "contradictions": [
                {
                    "contradiction_key": c.contradiction_key,
                    "status": c.status,
                    "lesson_memory_id": c.lesson_memory_id,
                    "precedent_decision_id": c.precedent_decision_id,
                    "side_a": c.side_a_json or {},
                    "side_b": c.side_b_json or {},
                    "source_event_id": c.source_event_id,
                    "created_at": _iso(c.created_at),
                }
                for c in contradiction_rows
            ],
            "precedents": [
                {
                    "precedent_decision_id": p.precedent_decision_id,
                    "context_signature": p.context_signature,
                    "relevance_score": p.relevance_score,
                    "evidence_count": p.evidence_count,
                    "cited_lesson": p.cited_lesson,
                    "source_event_id": p.source_event_id,
                }
                for p in precedent_rows
            ],
            "prediction": prediction,
            # 4H.3 additive: the decide-time living-state anchor (read-only).
            "state_context": row.state_context_json,
        }

    async def decision_precedent_citations(
        self, db: AsyncSession, *, organization_id: str,
        decision_id: str, as_of: Optional[str] = None,
    ) -> dict[str, Any]:
        """Decision-specific precedent citations, as-of filtered on the link
        time, top-N by relevance (bounded)."""
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return {"not_found": True, "decision_id": decision_id}
        as_of_dt = self._parse_asof(as_of)
        stmt = (
            select(CompanyDecisionPrecedent).where(
                CompanyDecisionPrecedent.organization_id == organization_id,
                CompanyDecisionPrecedent.decision_id == decision_id,
            )
        )
        if as_of:
            stmt = stmt.where(CompanyDecisionPrecedent.created_at <= as_of_dt)
        rows = list(
            (
                await db.execute(
                    stmt.order_by(CompanyDecisionPrecedent.relevance_score.desc())
                    .limit(MAX_PRECEDENTS)
                )
            ).scalars().all()
        )
        return {
            "advisory_only": True,
            "decision_id": decision_id,
            "total": len(rows),
            "bounded": True,
            "precedents": [
                {
                    "precedent_decision_id": p.precedent_decision_id,
                    "context_signature": p.context_signature,
                    "relevance_score": p.relevance_score,
                    "evidence_count": p.evidence_count,
                    "cited_lesson": p.cited_lesson,
                    "source_event_id": p.source_event_id,
                    "created_at": _iso(p.created_at),
                }
                for p in rows
            ],
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def decision_precedents(
        self, db: AsyncSession, *, organization_id: str,
        context: Optional[str] = None, as_of: Optional[str] = None,
        limit: int = MAX_PRECEDENTS,
    ) -> dict[str, Any]:
        """Free precedent recall by context signature (indexed, top-N,
        as-of filtered). Reads past decisions; never a document search."""
        limit = max(1, min(int(limit or MAX_PRECEDENTS), MAX_PRECEDENTS))
        as_of_dt = self._parse_asof(as_of)
        stmt = (
            select(CompanyDecisionPrecedent)
            .where(CompanyDecisionPrecedent.organization_id == organization_id)
        )
        if context:
            stmt = stmt.where(
                CompanyDecisionPrecedent.context_signature.contains(
                    f"{context.strip().lower()}",
                    autoescape=True,
                )
            )
        rows = list(
            (
                await db.execute(
                    stmt.order_by(CompanyDecisionPrecedent.relevance_score.desc(),
                                  CompanyDecisionPrecedent.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
        )
        precedents: list[dict[str, Any]] = []
        for p in rows:
            past = await self._decision_row(
                db, organization_id=organization_id,
                decision_id=p.precedent_decision_id,
            )
            if past is None:
                continue
            precedents.append({
                "precedent_decision_id": p.precedent_decision_id,
                "decision_title": past.title,
                "state": past.state,
                "outcome_kind": past.outcome_kind,
                "effectiveness": past.effectiveness,
                "lesson_snapshot": p.cited_lesson,
                "evidence_count": p.evidence_count,
                "relevance_score": p.relevance_score,
                "context_signature": p.context_signature,
                "as_of_context": past.as_of_context_json or {},
                "created_at": _iso(p.created_at),
            })
        return {
            "advisory_only": True,
            "precedents": precedents,
            "total": len(precedents),
            "bounded": True,
            "note": (
                "precedent recall is decision memory, not document search — "
                "each cited past decision carries its outcome, lesson snapshot "
                "and evidence count"
            ),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def decision_tracks(
        self, db: AsyncSession, *, organization_id: str,
        cohort: str = "kind", value: Optional[str] = None,
        as_of: Optional[str] = None,
    ) -> dict[str, Any]:
        """Prediction track-record read: latest append-only snapshot with
        snapshot_ts <= as_of (stable forever, byte-identical on replay)."""
        as_of_dt = self._parse_asof(as_of)
        cohort_key = (cohort or "kind").strip().lower()
        if cohort_key == "period":
            cohort_prefix = "period:"
        elif cohort_key == "scope":
            cohort_prefix = "scope:"
        else:
            cohort_key = "kind"
            cohort_prefix = "kind:"
        like_escape: Optional[str] = None
        if value:
            esc = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            cohort_prefix = f"{cohort_prefix}{esc}"
            like_escape = "\\"
        stmt = (
            select(CompanyDecisionTrack)
            .where(
                CompanyDecisionTrack.organization_id == organization_id,
                CompanyDecisionTrack.cohort_key.like(f"{cohort_prefix}%", escape=like_escape),
                CompanyDecisionTrack.snapshot_ts <= as_of_dt,
            )
            .order_by(CompanyDecisionTrack.snapshot_ts.desc(), CompanyDecisionTrack.cohort_key.asc())
        )
        rows = list((await db.execute(stmt.limit(50))).scalars().all())
        latest_by_cohort: dict[str, CompanyDecisionTrack] = {}
        for r in rows:
            if r.cohort_key not in latest_by_cohort:
                latest_by_cohort[r.cohort_key] = r
        snapshots = [
            {
                "cohort_key": k,
                "decisions_measured": r.decisions_measured,
                "predictions_recorded": r.predictions_recorded,
                "aligned": r.aligned,
                "partial": r.partial,
                "misaligned": r.misaligned,
                "avg_effectiveness": r.avg_effectiveness,
                "snapshot_ts": _iso(r.snapshot_ts),
                "source_event_id": r.source_event_id,
            }
            for k, r in latest_by_cohort.items()
        ]
        snapshots.sort(key=lambda s: (s["cohort_key"], s["snapshot_ts"]))
        return {
            "advisory_only": True,
            "cohort": cohort_key,
            "snapshots": snapshots,
            "note": (
                "append-only cohort rollups as-of the requested time; a later "
                "outcome never rewrites a previous snapshot"
            ),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def decision_impact(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
        depth: int = MAX_CAUSAL_DEPTH,
    ) -> dict[str, Any]:
        """Bounded causal trace from the decision node on the existing 4H.1
        causal graph ONLY — no new causal engine, no fabricated links: the
        response distinguishes observed edges (snapshot) from inferred
        relationships (unknown), and says so when the graph has no path."""
        depth = max(1, min(int(depth or MAX_CAUSAL_DEPTH), MAX_CAUSAL_DEPTH))
        edges = list(
            (
                await db.execute(
                    select(CompanyCausalEdge).where(
                        CompanyCausalEdge.organization_id == organization_id,
                    ).order_by(CompanyCausalEdge.created_at.desc())
                    .limit(MAX_CAUSAL_EDGES * 3)
                )
            ).scalars().all()
        )
        adj: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for e in edges:
            adj.setdefault((e.source_type, e.source_id), []).append({
                "to_type": e.target_type, "to_id": e.target_id,
                "kind": e.kind, "confidence": e.confidence,
                "evidence_ref": e.evidence_ref or [],
            })
        observed: list[dict[str, Any]] = []
        if ("decision", decision_id) in adj:
            visited = {("decision", decision_id)}
            frontier = [("decision", decision_id)]
            for _ in range(depth):
                nxt: list[tuple[str, str]] = []
                for node in frontier:
                    for hop in sorted(
                        adj.get(node, []),
                        key=lambda h: (
                            {"high": 0, "medium": 1, "low": 2}.get(h["confidence"], 1),
                            h["kind"],
                        ),
                    ):
                        target = (hop["to_type"], hop["to_id"])
                        if target in visited:
                            continue
                        visited.add(target)
                        observed.append({
                            "entity_type": hop["to_type"],
                            "entity_id": hop["to_id"],
                            "kind": hop["kind"],
                            "confidence": hop["confidence"],
                            "evidence_ref": hop["evidence_ref"],
                            "observed": True,
                        })
                        nxt.append(target)
                        if len(observed) >= MAX_CAUSAL_EDGES:
                            break
                    if len(observed) >= MAX_CAUSAL_EDGES:
                        break
                frontier = nxt
                if not frontier or len(observed) >= MAX_CAUSAL_EDGES:
                    break
        grouped: dict[str, list[dict[str, Any]]] = {
            "resource_allocation": [], "projects": [], "milestones": [],
            "customers": [], "revenue_business": [], "strategic_objectives": [],
            "outcomes": [],
        }
        mapping = {
            "task": "resource_allocation", "execution": "resource_allocation",
            "dependency": "resource_allocation", "capacity": "resource_allocation",
            "project": "projects", "milestone": "milestones",
            "customer": "customers", "revenue": "revenue_business",
            "business": "revenue_business", "objective": "strategic_objectives",
            "goal": "strategic_objectives", "outcome": "outcomes",
        }
        for hop in observed:
            grouped.setdefault(mapping.get(hop["entity_type"], "outcomes"), []).append(hop)
        return {
            "advisory_only": True,
            "decision_id": decision_id,
            "observed_edges": observed,
            "grouped_impact": {
                k: v for k, v in grouped.items() if v
            },
            "inferred_relationships": [],
            "uncertain": [],
            "note": (
                "causal impact walks the canonical 4H.1 causal graph from the "
                "decision node; only edges actually present in the snapshot are "
                "reported — nothing is fabricated, and an absent path is "
                "reported as unknown, not invented"
            ),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def decision_what_if(
        self, db: AsyncSession, *, organization_id: str,
        decision_id: str, scenario_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Per-alternative advisory scenarios reusing the existing bounded
        what_if engine. Never creates, executes, or mutates anything."""
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return {"not_found": True, "decision_id": decision_id}
        alternatives = list(
            (
                await db.execute(
                    select(CompanyDecisionAlternative).where(
                        CompanyDecisionAlternative.organization_id == organization_id,
                        CompanyDecisionAlternative.decision_id == decision_id,
                    ).order_by(CompanyDecisionAlternative.alternative_key.asc())
                )
            ).scalars().all()
        )
        if not alternatives:
            alternatives = [CompanyDecisionAlternative(
                organization_id=organization_id, decision_id=decision_id,
                alternative_key=f"alt:{decision_id}:01", label="current course",
                description="the decision as recorded", chosen=True,
                why_chosen="the approved course", why_not="",
                expected_outcome=row.predicted_outcome,
            )]
        scenario_type = {
            "reallocate_capacity": "reallocate",
            "delay_project": "delay",
            "hire": "hire",
        }.get(row.kind, "delay")
        payload = dict(scenario_payload or {})
        if scenario_type == "delay" and not payload.get("project_id"):
            payload["project_id"] = ""
        if scenario_type == "hire" and not payload.get("capability"):
            payload["capability"] = ""
        scenarios: list[dict[str, Any]] = []
        for alt in alternatives:
            base = await self.what_if(
                db, organization_id=organization_id,
                scenario_type=scenario_type, payload=payload,
            )
            scenarios.append({
                "alternative_key": alt.alternative_key,
                "label": alt.label,
                "scenario_type": scenario_type,
                "expected_outcome": alt.expected_outcome,
                "consequences": base.get("consequences", []),
                "not_a_prediction": True,
                "advisory_only": True,
            })
        return {
            "advisory_only": True,
            "decision_id": decision_id,
            "scenarios": scenarios,
            "note": (
                "per-alternative scenario framing reuses the existing bounded "
                "what-if engine; nothing is executed, created or mutated — "
                "these are advisory consequences, never predictions"
            ),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def decision_prediction(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
        as_of: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Prediction surface: recorded fields + reconciliation — with
        evidence counts and the confidence band (never a naked number)."""
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return None
        as_of_dt = self._parse_asof(as_of)
        evidence = await self._evidence_rows(
            db, organization_id=organization_id, decision_id=decision_id,
            as_of=as_of_dt,
        )
        contradictions = list(
            (
                await db.execute(
                    select(CompanyDecisionContradiction).where(
                        CompanyDecisionContradiction.organization_id == organization_id,
                        CompanyDecisionContradiction.decision_id == decision_id,
                    )
                )
            ).scalars().all()
        )
        compare = row.actual_outcome_compare if isinstance(row.actual_outcome_compare, dict) else None
        alignment_value = compare.get("aligned") if compare else None
        out = {
            "advisory_only": True,
            "decision_id": decision_id,
            "prediction": self._prediction_fields(row),
            "confidence_band": self._confidence_band(row.prediction_confidence),
            "supporting_evidence_count": evidence["evidence_count"],
            "contradicting_evidence_count": len(contradictions),
            "reconciliation": compare or None,
            "not_yet_measurable": (compare is None and row.state in ("approved", "executed", "outcome_recorded")),
            "state_context": row.state_context_json,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }
        return out

    async def decision_why_not(self, db: AsyncSession, *, organization_id: str, decision_id: str) -> Optional[dict[str, Any]]:
        """The rejected-alternatives record: reason per alternative + the
        reversibility condition (preferable_if)."""
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return None
        alternatives = list(
            (
                await db.execute(
                    select(CompanyDecisionAlternative).where(
                        CompanyDecisionAlternative.organization_id == organization_id,
                        CompanyDecisionAlternative.decision_id == decision_id,
                        CompanyDecisionAlternative.chosen.is_(False),
                    ).order_by(CompanyDecisionAlternative.alternative_key.asc())
                )
            ).scalars().all()
        )
        return {
            "advisory_only": True,
            "decision_id": decision_id,
            "why_not": [
                {
                    "alternative_key": a.alternative_key,
                    "label": a.label,
                    "why_not": a.why_not,
                    "preferable_if": a.preferable_if,
                }
                for a in alternatives
            ],
            "total": len(alternatives),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def decision_alternatives(
        self, db: AsyncSession, *, organization_id: str,
        decision_id: str, as_of: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """First-class alternatives with expected_outcome, why_chosen and
        why_not (as-of filtered on the record time)."""
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return None
        as_of_dt = self._parse_asof(as_of)
        stmt = (
            select(CompanyDecisionAlternative).where(
                CompanyDecisionAlternative.organization_id == organization_id,
                CompanyDecisionAlternative.decision_id == decision_id,
            ).order_by(CompanyDecisionAlternative.alternative_key.asc())
        )
        if as_of:
            stmt = stmt.where(CompanyDecisionAlternative.created_at <= as_of_dt)
        alternatives = list((await db.execute(stmt)).scalars().all())
        chosen = next((a for a in alternatives if a.chosen), None)
        return {
            "advisory_only": True,
            "decision_id": decision_id,
            "total": len(alternatives),
            "chosen": self._alternative_payload(chosen) if chosen else None,
            "alternatives": [self._alternative_payload(a) for a in alternatives],
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def decision_quality(
        self, db: AsyncSession, *, organization_id: str,
        decision_id: str, as_of: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Quality surface: append-only stage snapshots + live evidence
        count + risk band (advisory-only, never a naked score)."""
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return None
        as_of_dt = self._parse_asof(as_of)
        evidence = await self._evidence_rows(
            db, organization_id=organization_id, decision_id=decision_id,
            as_of=as_of_dt,
        )
        qstmt = (
            select(CompanyDecisionQuality).where(
                CompanyDecisionQuality.organization_id == organization_id,
                CompanyDecisionQuality.decision_id == decision_id,
            ).order_by(CompanyDecisionQuality.created_at.asc())
        )
        if as_of:
            qstmt = qstmt.where(CompanyDecisionQuality.created_at <= as_of_dt)
        quality_rows = list((await db.execute(qstmt)).scalars().all())
        contradictions_open = int(
            (
                await db.execute(
                    select(func.count()).select_from(CompanyDecisionContradiction).where(
                        CompanyDecisionContradiction.organization_id == organization_id,
                        CompanyDecisionContradiction.decision_id == decision_id,
                        CompanyDecisionContradiction.status == "open",
                    )
                )
            ).scalar_one() or 0
        )
        alternatives = list(
            (
                await db.execute(
                    select(CompanyDecisionAlternative).where(
                        CompanyDecisionAlternative.organization_id == organization_id,
                        CompanyDecisionAlternative.decision_id == decision_id,
                    )
                )
            ).scalars().all()
        )
        chosen = next((a for a in alternatives if a.chosen), None)
        return {
            "advisory_only": True,
            "decision_id": decision_id,
            "stage": row.state,
            "evidence_count": evidence["evidence_count"],
            "contradictions_open": contradictions_open,
            "reversible": bool(chosen is not None and chosen.preferable_if),
            "risk_band": self._risk_band(
                confidence=row.prediction_confidence,
                contradictions_open=contradictions_open,
                reversible=bool(chosen is not None and chosen.preferable_if),
            ),
            "snapshots": [self._risk_banded_quality_summary(q) for q in quality_rows],
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def decision_contradictions(self, db: AsyncSession, *, organization_id: str, decision_id: str) -> Optional[dict[str, Any]]:
        """Surfaced contradictions, both sides' evidence, with status."""
        row = await self._decision_row(db, organization_id=organization_id, decision_id=decision_id)
        if row is None:
            return None
        rows = list(
            (
                await db.execute(
                    select(CompanyDecisionContradiction).where(
                        CompanyDecisionContradiction.organization_id == organization_id,
                        CompanyDecisionContradiction.decision_id == decision_id,
                    ).order_by(CompanyDecisionContradiction.created_at.asc())
                )
            ).scalars().all()
        )
        return {
            "advisory_only": True,
            "decision_id": decision_id,
            "evidence_is_conflicting": bool(rows),
            "contradictions": [
                {
                    "contradiction_key": c.contradiction_key,
                    "status": c.status,
                    "side_a": c.side_a_json or {},
                    "side_b": c.side_b_json or {},
                    "lesson_memory_id": c.lesson_memory_id,
                    "precedent_decision_id": c.precedent_decision_id,
                    "source_event_id": c.source_event_id,
                    "created_at": _iso(c.created_at),
                }
                for c in rows
            ],
            "total": len(rows),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }


# ------------------------------------------------------------------
    # Slice 4H.3 — Living Company State
    # ------------------------------------------------------------------

    # The 4H.3 state dimensions to the canonical 4G.7 health domains
    # (observed dimensions); "outcomes" is derived from decision rows.
    _STATE_DIMENSION_DOMAINS = {
        "people": "people",
        "work": "execution",
        "resources": "capacity",
        "processes": "coordination",
        "knowledge": "knowledge",
        "customers": "customers",
        "finance": "financial",
    }

    def _state_band(self, score: Any) -> str:
        try:
            score = int(score)
        except (TypeError, ValueError):
            return "concerned"
        if score >= 80:
            return "healthy"
        if score >= 60:
            return "concerned"
        return "at_risk"

    async def _latest_state_row(
        self, db: AsyncSession, *, organization_id: str,
        scope_type: str = "org", scope_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> Optional[CompanyStateHistory]:
        stmt = (
            select(CompanyStateHistory)
            .where(
                CompanyStateHistory.organization_id == organization_id,
                CompanyStateHistory.scope_type == scope_type,
                CompanyStateHistory.scope_id == scope_id,
            )
        )
        if as_of is not None:
            stmt = stmt.where(CompanyStateHistory.occurred_at <= as_of)
        return (
            await db.execute(
                stmt.order_by(CompanyStateHistory.occurred_at.desc()).limit(1)
            )
        ).scalars().first()

    async def _latest_health(
        self, db: AsyncSession, *, organization_id: str, offset: int = 0,
    ) -> Optional[CompanyHealthHistory]:
        """The offset-th latest org health snapshot (0 = newest)."""
        return (
            await db.execute(
                select(CompanyHealthHistory)
                .where(
                    CompanyHealthHistory.organization_id == organization_id,
                    CompanyHealthHistory.scope_type == "org",
                )
                .order_by(CompanyHealthHistory.occurred_at.desc())
                .offset(offset).limit(1)
            )
        ).scalars().first()

    async def _state_dimensions(
        self, db: AsyncSession, *, organization_id: str,
        health_latest: Optional[CompanyHealthHistory],
        health_prev: Optional[CompanyHealthHistory],
    ) -> list[dict[str, Any]]:
        """Eight fixed living-state dimensions, typed observed/derived, with a
        deterministic op (improved/declined/stable) vs the previous snapshot."""
        by_key: dict[str, dict[str, Any]] = {}
        prior: dict[str, dict[str, Any]] = {}
        if health_latest is not None and isinstance(health_latest.domains_json, list):
            for d in health_latest.domains_json:
                if isinstance(d, dict):
                    by_key[str(d.get("key") or "")] = d
        if health_prev is not None and isinstance(health_prev.domains_json, list):
            for d in health_prev.domains_json:
                if isinstance(d, dict):
                    prior[str(d.get("key") or "")] = d
        order = {"healthy": 3, "concerned": 2, "at_risk": 1, "critical": 0}
        out: list[dict[str, Any]] = []
        for dim in STATE_DIMENSIONS:
            if dim not in self._STATE_DIMENSION_DOMAINS:
                out.append(await self._outcomes_dimension(db, organization_id=organization_id))
                continue
            key = self._STATE_DIMENSION_DOMAINS[dim]
            drow = by_key.get(key, {})
            prov = prior.get(key, {})
            now_state = self._state_band(drow.get("score"))
            prev_state = self._state_band(prov.get("score")) if prov else None
            op = "stable"
            if prev_state is not None and now_state != prev_state:
                op = "improved" if order.get(now_state, 0) > order.get(prev_state, 0) else "declined"
            out.append({
                "op": op,
                "signal_count": int(drow.get("evidence_count") or 0),
                "state": now_state,
                "type": "observed",
            })
        return out

    async def _outcomes_dimension(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """Derived outcomes dimension from closed decision loops (bounded)."""
        closed = list(
            (
                await db.execute(
                    select(CompanyDecision).where(
                        CompanyDecision.organization_id == organization_id,
                        CompanyDecision.outcome_kind != "",
                    ).limit(500)
                )
            ).scalars().all()
        )
        total = len(closed)
        if total == 0:
            return {"op": "stable", "signal_count": 0, "state": "concerned", "type": "derived"}
        successes = sum(1 for d in closed if d.outcome_kind == "successful")
        ratio = successes / total
        state = "healthy" if ratio >= 0.6 else ("concerned" if ratio >= 0.4 else "at_risk")
        return {"op": "stable", "signal_count": total, "state": state, "type": "derived"}

    async def _state_signals(
        self, db: AsyncSession, *, organization_id: str,
    ) -> list[dict[str, Any]]:
        """The contributing signals behind the snapshot (bounded, ordered):
        recent triggering events, causal-edge refs, patterns, insights,
        lesson memories — every id cited, nothing naked."""
        signals: list[dict[str, Any]] = []
        health_rows = list(
            (
                await db.execute(
                    select(CompanyHealthHistory).where(
                        CompanyHealthHistory.organization_id == organization_id,
                        CompanyHealthHistory.scope_type == "org",
                    ).order_by(CompanyHealthHistory.occurred_at.desc())
                    .limit(12)
                )
            ).scalars().all()
        )
        for h in health_rows:
            signals.append({
                "kind": "event", "id": str(h.source_event_id),
                "label": h.event_name or "company change",
                "signal_count": 1, "signal": "event",
                "occurred_at": _iso(h.occurred_at),
            })
        refs = list(
            (
                await db.execute(
                    select(CompanyCausalEdge).where(
                        CompanyCausalEdge.organization_id == organization_id,
                    ).order_by(CompanyCausalEdge.created_at.desc()).limit(3)
                )
            ).scalars().all()
        )
        for r in refs:
            signals.append({
                "kind": "causal", "id": f"{r.kind}:{r.source_id}->{r.target_id}",
                "label": r.kind, "signal_count": 1, "signal": "causal",
                "occurred_at": _iso(r.created_at),
            })
        patterns = list(
            (
                await db.execute(
                    select(PatternDetection).where(
                        PatternDetection.organization_id == organization_id,
                        PatternDetection.status.not_in(("resolved", "fading")),
                    ).order_by(PatternDetection.last_seen.desc()).limit(6)
                )
            ).scalars().all()
        )
        for p in patterns:
            signals.append({
                "kind": "pattern", "id": p.id,
                "label": (p.title or "pattern")[:120],
                "signal_count": int(p.count or 0), "signal": "pattern",
                "occurred_at": _iso(p.last_seen),
            })
        insights = list(
            (
                await db.execute(
                    select(UniversalInsight).where(
                        UniversalInsight.organization_id == organization_id,
                        UniversalInsight.status == "active",
                    ).order_by(UniversalInsight.updated_at.desc()).limit(6)
                )
            ).scalars().all()
        )
        for i in insights:
            signals.append({
                "kind": "insight", "id": i.id,
                "label": (i.title or "insight")[:120],
                "signal_count": len(i.evidence_json or []), "signal": "insight",
                "occurred_at": _iso(i.updated_at),
            })
        memories = list(
            (
                await db.execute(
                    select(CompanyMemory).where(
                        CompanyMemory.organization_id == organization_id,
                        CompanyMemory.memory_category == "lesson",
                        CompanyMemory.status == "active",
                    ).order_by(CompanyMemory.updated_at.desc()).limit(6)
                )
            ).scalars().all()
        )
        for m in memories:
            signals.append({
                "kind": "memory", "id": m.id,
                "label": (m.title or "lesson")[:120],
                "signal_count": 1, "signal": "memory",
                "occurred_at": _iso(m.updated_at),
            })
        return signals[:MAX_STATE_SIGNALS]

    @staticmethod
    def _state_signature(
        *, dimensions: list[dict[str, Any]], signals: list[dict[str, Any]],
        dependencies: list[dict[str, Any]], risks: list[dict[str, Any]],
        opportunities: list[dict[str, Any]],
        affected_decisions: list[dict[str, Any]],
        attention: list[dict[str, Any]], next_: list[dict[str, Any]],
    ) -> str:
        """Deterministic canonical fingerprint — the no-op detector. Timestamps
        and free text never enter the signature, so replays converge."""

        def norm(items: list[dict[str, Any]], keys: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
            return tuple(
                tuple(str((i.get(k) if isinstance(i, dict) else "") or "") for k in keys)
                for i in (items or [])
            )

        return repr((
            tuple((d.get("state"), d.get("op"), d.get("signal_count", 0), d.get("type")) for d in dimensions),
            norm(signals, ("kind", "id", "signal_count")),
            norm(dependencies, ("kind", "source_type", "source_id", "target_type", "target_id")),
            norm(risks, ("risk_id", "band")),
            norm(opportunities, ("source", "source_id")),
            norm(affected_decisions, ("decision_id", "state")),
            norm(attention, ("kind",)),
            norm(next_, ("scenario_type",)),
        ))

    async def _state_dependencies(
        self, db: AsyncSession, *, organization_id: str, limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Top-N dependency edges visible from this state — the latest
        derived causality snapshot group, bounded."""
        rows = list(
            (
                await db.execute(
                    select(CompanyCausalEdge).where(
                        CompanyCausalEdge.organization_id == organization_id,
                    ).order_by(CompanyCausalEdge.created_at.desc())
                    .limit(MAX_CAUSAL_EDGES * 3)
                )
            ).scalars().all()
        )
        if not rows:
            return []
        latest_ref = rows[0].source_event_id
        keep = [r for r in rows if r.source_event_id == latest_ref][:limit]
        return [
            {
                "source_type": r.source_type, "source_id": r.source_id,
                "target_type": r.target_type, "target_id": r.target_id,
                "kind": r.kind, "confidence": r.confidence,
            }
            for r in keep
        ]

    async def _state_risks(
        self, db: AsyncSession, *, organization_id: str,
        limit: int = MAX_STATE_RISKS,
    ) -> list[dict[str, Any]]:
        """Open-risk exposure composition: deterministic band from recorded
        probability × impact; affected entities cited; bounded."""
        rows = list(
            (
                await db.execute(
                    select(Risk).where(
                        Risk.organization_id == organization_id,
                        Risk.status != "closed",
                    ).order_by(Risk.risk_score.desc(), Risk.id.asc())
                    .limit(limit)
                )
            ).scalars().all()
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            score = int(r.risk_score or 0)
            band = "HIGH" if score >= 15 else ("MEDIUM" if score >= 8 else "LOW")
            item: dict[str, Any] = {
                "risk_id": r.id,
                "title": r.title,
                "band": band,
                "probability": int(r.probability or 0),
                "impact": int(r.impact or 0),
                "affected": [],
            }
            if r.project_id:
                item["affected"].append({"entity": "project", "id": r.project_id, "kind": "risk"})
            out.append(item)
        return out

    async def _state_opportunities(
        self, db: AsyncSession, *, organization_id: str,
        limit: int = MAX_STATE_OPPORTUNITIES,
    ) -> list[dict[str, Any]]:
        """Bounded opportunity surface: patterns, insights and knowledge
        recommendations with their source ids and evidence counts."""
        items: list[dict[str, Any]] = []
        patterns = list(
            (
                await db.execute(
                    select(PatternDetection).where(
                        PatternDetection.organization_id == organization_id,
                        PatternDetection.status.not_in(("resolved", "fading", "candidate")),
                    ).order_by(PatternDetection.last_seen.desc()).limit(limit)
                )
            ).scalars().all()
        )
        for p in patterns:
            items.append({
                "source": "pattern", "source_id": p.id, "kind": p.pattern_type,
                "signal_count": int(p.count or 0),
                "evidence_count": len(p.evidence_json or []),
            })
        insights = list(
            (
                await db.execute(
                    select(UniversalInsight).where(
                        UniversalInsight.organization_id == organization_id,
                        UniversalInsight.status == "active",
                    ).order_by(UniversalInsight.updated_at.desc()).limit(limit)
                )
            ).scalars().all()
        )
        for i in insights:
            items.append({
                "source": "insight", "source_id": i.id, "kind": i.insight_type,
                "signal_count": 1,
                "evidence_count": len(i.evidence_json or []),
            })
        recs = list(
            (
                await db.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.organization_id == organization_id,
                        KnowledgeRecommendation.status == "active",
                    ).order_by(KnowledgeRecommendation.updated_at.desc()).limit(limit)
                )
            ).scalars().all()
        )
        for r in recs:
            evidence_count = 0
            if isinstance(r.evidence_json, str) and r.evidence_json.strip():
                try:
                    import json as _json
                    evidence_count = len(_json.loads(r.evidence_json) or [])
                except Exception:  # noqa: BLE001 - malformed legacy text
                    evidence_count = 0
            items.append({
                "source": "recommendation", "source_id": r.id, "kind": r.kind,
                "signal_count": 1, "evidence_count": evidence_count,
            })
        return items[:limit]

    async def _state_affected_decisions(
        self, db: AsyncSession, *, organization_id: str,
        delta: Optional[list[dict[str, Any]]] = None,
        limit: int = MAX_STATE_DECISIONS,
    ) -> list[dict[str, Any]]:
        """Deterministic intersection of the delta's entities/kinds with the
        decision evidence lineage and state-context refs — bounded, never
        free-text embedding (§5.4)."""
        delta_ids = {str(d.get("id") or "") for d in delta or []}
        delta_kinds = {str(d.get("kind") or "") for d in delta or []}
        if not delta:
            return []
        rows = list(
            (
                await db.execute(
                    select(CompanyDecision).where(
                        CompanyDecision.organization_id == organization_id,
                        CompanyDecision.state.in_(
                            ("proposed", "evaluated", "recommended", "approved", "executed")
                        ),
                    ).order_by(CompanyDecision.updated_at.desc())
                    .limit(MAX_STATE_DECISIONS * 2)
                )
            ).scalars().all()
        )

        def hits(evidence_rows: list[CompanyDecisionEvidence]) -> bool:
            for ev in evidence_rows:
                if ev.source_kind and ev.source_kind in delta_kinds:
                    return True
                if ev.source_event_id and ev.source_event_id in delta_ids:
                    return True
                summary = ev.source_summary or ""
                if any(tok in summary for tok in delta_ids if len(tok) >= 8):
                    return True
            return False

        out: list[dict[str, Any]] = []
        for d in rows:
            refs = (d.state_context_json or {}).get("snapshot_refs") or []
            if refs and any(str(r) in delta_ids for r in refs):
                out.append({
                    "decision_id": d.decision_id, "state": d.state,
                    "kind": d.kind, "title": d.title,
                    "why": "state-context snapshot intersects the current delta",
                })
                if len(out) >= limit:
                    break
                continue
            evidence_rows = list(
                (
                    await db.execute(
                        select(CompanyDecisionEvidence).where(
                            CompanyDecisionEvidence.organization_id == organization_id,
                            CompanyDecisionEvidence.decision_id == d.decision_id,
                        ).limit(MAX_DECISION_EVIDENCE)
                    )
                ).scalars().all()
            )
            if hits(evidence_rows):
                out.append({
                    "decision_id": d.decision_id, "state": d.state,
                    "kind": d.kind, "title": d.title,
                    "why": "decision evidence intersects the current delta",
                })
                if len(out) >= limit:
                    break
        return out

    async def _state_attention(
        self, db: AsyncSession, *, organization_id: str,
    ) -> list[dict[str, Any]]:
        """What humans should consider — reuses the 4H.1 attention language."""
        h = await self._latest_health(db, organization_id=organization_id)
        items = (h.attention_json if h is not None else None) or []
        out: list[dict[str, Any]] = []
        for a in items:
            if not isinstance(a, dict):
                continue
            out.append({
                "priority": str(a.get("priority") or "medium"),
                "kind": str(a.get("kind") or ""),
                "title": str(a.get("title") or ""),
                "why": str(a.get("why") or ""),
            })
        return out[:10]

    async def _state_next(
        self, db: AsyncSession, *, organization_id: str,
    ) -> list[dict[str, Any]]:
        """Advisory what-if consequences (reuses the bounded 4G.7 simulator);
        never predictions, advisory_only by construction."""
        try:
            command = await execution_engine.command_center(
                db, organization_id=organization_id,
            )
            at_risk = [
                p for p in (command.get("projects") or [])
                if (p.get("health_status") or "") == "at_risk"
            ]
        except Exception:  # noqa: BLE001 - bounded fallback, never blocks
            at_risk = []
        if not at_risk:
            return []
        top = at_risk[0]
        sim = await self.what_if(
            db, organization_id=organization_id, scenario_type="delay",
            payload={"project_id": top.get("project_id") or "", "days": 0},
        )
        return [{
            "scenario_type": "delay",
            "consequences_count": len(sim.get("consequences") or []),
            "not_a_prediction": True,
        }]

    async def _state_delta(
        self, db: AsyncSession, *, organization_id: str,
        current: list[dict[str, Any]],
        prev_signals: Optional[list[Any]],
    ) -> list[dict[str, Any]]:
        """Deterministic add/change/remove diff of signal provenance vs the
        previous snapshot — the "why did the state change" surface."""
        prev: dict[str, dict[str, Any]] = {}
        for s in prev_signals or []:
            if isinstance(s, dict) and s.get("id"):
                prev[str(s["id"])] = s
        cur: dict[str, dict[str, Any]] = {}
        for s in current:
            cur[str(s.get("id") or "")] = s
        delta: list[dict[str, Any]] = []
        for sid, sig in cur.items():
            sig_prev = prev.get(sid)
            if sig_prev is None:
                delta.append({
                    "op": "added", "entity": str(sig.get("kind") or "signal"),
                    "id": sid, "label": str(sig.get("label") or ""),
                    "kind": str(sig.get("kind") or ""),
                    "signal": str(sig.get("signal") or ""),
                    "signal_ids": [sid],
                    "evidence_count": int(sig.get("signal_count") or 0),
                })
            elif (sig_prev.get("signal_count") or 0) != (sig.get("signal_count") or 0):
                delta.append({
                    "op": "changed", "entity": str(sig.get("kind") or "signal"),
                    "id": sid, "label": str(sig.get("label") or ""),
                    "kind": str(sig.get("kind") or ""),
                    "signal": str(sig.get("signal") or ""),
                    "signal_ids": [sid],
                    "evidence_count": int(sig.get("signal_count") or 0),
                })
        for sid in prev:
            if sid not in cur:
                sig_prev = prev[sid]
                delta.append({
                    "op": "removed", "entity": str(sig_prev.get("kind") or "signal"),
                    "id": sid, "label": str(sig_prev.get("label") or ""),
                    "kind": str(sig_prev.get("kind") or ""),
                    "signal": str(sig_prev.get("signal") or ""),
                    "signal_ids": [sid],
                    "evidence_count": 0,
                })
        # stable order: added/changed/removed keep signal source order
        return delta[:MAX_STATE_DELTA]

    async def _compose_surface(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """The SINGLE composition function (§10): every 4H.3 write path and the
        cold-start read path produce byte-identical surfaces for identical
        inputs — no second implementations anywhere."""
        health_latest = await self._latest_health(db, organization_id=organization_id)
        health_prev = await self._latest_health(
            db, organization_id=organization_id, offset=1,
        )
        dimensions = await self._state_dimensions(
            db, organization_id=organization_id,
            health_latest=health_latest, health_prev=health_prev,
        )
        signals = await self._state_signals(db, organization_id=organization_id)
        dependencies = await self._state_dependencies(
            db, organization_id=organization_id,
        )
        risks = await self._state_risks(db, organization_id=organization_id)
        opportunities = await self._state_opportunities(
            db, organization_id=organization_id,
        )
        attention = await self._state_attention(db, organization_id=organization_id)
        next_ = await self._state_next(db, organization_id=organization_id)
        delta = await self._state_delta(
            db, organization_id=organization_id,
            current=signals, prev_signals=None,
        )
        affected_decisions = await self._state_affected_decisions(
            db, organization_id=organization_id, delta=delta,
        )
        return {
            "dimensions": dimensions,
            "signals": signals,
            "dependencies": dependencies,
            "risks": risks,
            "opportunities": opportunities,
            "affected_decisions": affected_decisions,
            "attention": attention,
            "next": next_,
            "delta": [],
        }

    async def _compose_state(
        self, db: AsyncSession, *, organization_id: str,
        scope_type: str = "org", scope_id: Optional[str] = None,
        source_event_id: str = "", event_name: str = "",
        occurred_at: Optional[datetime] = None,
    ) -> Optional[dict[str, Any]]:
        """Write the living-company snapshot (exact-once on the source event,
        ONLY when the composed surface differs from the previous snapshot —
        no-op compositions stay unwritten — and emit the two audit events
        through the background stream, never through the queue)."""
        if not source_event_id:
            return None
        existing = (
            await db.execute(
                select(CompanyStateHistory.id).where(
                    CompanyStateHistory.organization_id == organization_id,
                    CompanyStateHistory.scope_type == scope_type,
                    CompanyStateHistory.scope_id == scope_id,
                    CompanyStateHistory.source_event_id == source_event_id,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return None
        prev_row = await self._latest_state_row(
            db, organization_id=organization_id,
            scope_type=scope_type, scope_id=scope_id,
        )
        surface = await self._compose_surface(db, organization_id=organization_id)
        delta = await self._state_delta(
            db, organization_id=organization_id,
            current=surface["signals"],
            prev_signals=(prev_row.signals_json if prev_row is not None else None),
        )
        surface["delta"] = delta
        if prev_row is not None:
            prev_sig = self._state_signature(
                dimensions=prev_row.dimensions_json or [],
                signals=prev_row.signals_json or [],
                dependencies=prev_row.dependencies_json or [],
                risks=prev_row.risks_json or [],
                opportunities=prev_row.opportunities_json or [],
                affected_decisions=prev_row.affected_decisions_json or [],
                attention=prev_row.attention_json or [],
                next_=prev_row.next_json or [],
            )
            now_sig = self._state_signature(
                dimensions=surface["dimensions"],
                signals=surface["signals"],
                dependencies=surface["dependencies"],
                risks=surface["risks"],
                opportunities=surface["opportunities"],
                affected_decisions=surface["affected_decisions"],
                attention=surface["attention"],
                next_=surface["next"],
            )
            if prev_sig == now_sig:
                return None  # no-op: no false trail entry, no event
        occurrence = occurred_at or datetime.now(timezone.utc)
        seq = int(
            (
                await db.execute(
                    select(func.count(CompanyStateHistory.id)).where(
                        CompanyStateHistory.organization_id == organization_id,
                        CompanyStateHistory.scope_type == scope_type,
                        CompanyStateHistory.scope_id == scope_id,
                    )
                )
            ).scalar_one() or 0
        ) + 1
        row = CompanyStateHistory(
            organization_id=organization_id,
            state_key=(
                f"st:{organization_id[:12]}:{scope_type}:"
                f"{(scope_id or 'org')[:16]}:{seq:05d}"
            ),
            scope_type=scope_type,
            scope_id=scope_id,
            dimensions_json=surface["dimensions"],
            delta_json=delta,
            signals_json=surface["signals"],
            dependencies_json=surface["dependencies"],
            risks_json=surface["risks"],
            opportunities_json=surface["opportunities"],
            affected_decisions_json=surface["affected_decisions"],
            attention_json=surface["attention"],
            next_json=surface["next"],
            source_event_id=source_event_id,
            snapshot_ts=occurrence,
            occurred_at=occurrence,
        )
        db.add(row)
        await db.flush()
        from app.events.publisher import publish_background_event

        await publish_background_event(
            db, name="company.state.composed",
            organization_id=organization_id,
            payload={
                "organization_id": organization_id,
                "snapshot_ref": source_event_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "delta_count": len(delta),
                "snapshot_ts": _iso(occurrence),
            },
        )
        if delta:
            kinds = [str(d.get("kind") or "") for d in delta[:3]]
            await publish_background_event(
                db, name="company.state.changed",
                organization_id=organization_id,
                payload={
                    "organization_id": organization_id,
                    "snapshot_ref": source_event_id,
                    "delta_count": len(delta),
                    "first_delta_kinds": kinds,
                },
            )
        return {
            "state_key": row.state_key,
            "snapshot_ref": source_event_id,
            "delta_count": len(delta),
            "changed": bool(delta),
            "occurred_at": _iso(occurrence),
        }

    async def _explain_signals(
        self, db: AsyncSession, *, organization_id: str,
        signals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """expand=true: attach the deterministic "why" provenance text to each
        cited signal (read-side only — never stored)."""
        event_ids = [s["id"] for s in signals if s.get("kind") == "event"]
        health_by_event: dict[str, str] = {}
        if event_ids:
            hero_rows = list(
                (
                    await db.execute(
                        select(CompanyHealthHistory).where(
                            CompanyHealthHistory.organization_id == organization_id,
                            CompanyHealthHistory.source_event_id.in_(event_ids),
                        )
                    )
                ).scalars().all()
            )
            for h in hero_rows:
                if h.summary_narrative:
                    health_by_event.setdefault(h.source_event_id, h.summary_narrative)
        pattern_ids = [s["id"] for s in signals if s.get("kind") == "pattern"]
        pattern_by_id: dict[str, str] = {}
        if pattern_ids:
            for p in list(
                (
                    await db.execute(
                        select(PatternDetection).where(
                            PatternDetection.organization_id == organization_id,
                            PatternDetection.id.in_(pattern_ids),
                        )
                    )
                ).scalars().all()
            ):
                pattern_by_id[p.id] = p.description or p.detail or ""
        insight_ids = [s["id"] for s in signals if s.get("kind") == "insight"]
        insight_by_id: dict[str, str] = {}
        if insight_ids:
            for i in list(
                (
                    await db.execute(
                        select(UniversalInsight).where(
                            UniversalInsight.organization_id == organization_id,
                            UniversalInsight.id.in_(insight_ids),
                        )
                    )
                ).scalars().all()
            ):
                insight_by_id[i.id] = i.claim or i.summary or ""
        memory_ids = [s["id"] for s in signals if s.get("kind") == "memory"]
        memory_by_id: dict[str, str] = {}
        if memory_ids:
            for m in list(
                (
                    await db.execute(
                        select(CompanyMemory).where(
                            CompanyMemory.organization_id == organization_id,
                            CompanyMemory.id.in_(memory_ids),
                        )
                    )
                ).scalars().all()
            ):
                memory_by_id[m.id] = m.lesson or m.content or ""
        out: list[dict[str, Any]] = []
        for s in signals:
            item = dict(s)
            if s.get("kind") == "event":
                item["why"] = health_by_event.get(s["id"], "")
            elif s.get("kind") == "pattern":
                item["why"] = pattern_by_id.get(s["id"], "")
            elif s.get("kind") == "insight":
                item["why"] = insight_by_id.get(s["id"], "")
            elif s.get("kind") == "memory":
                item["why"] = memory_by_id.get(s["id"], "")
            out.append(item)
        return out

    async def _state_surface(
        self, db: AsyncSession, row: CompanyStateHistory, *,
        organization_id: str, explain: bool = False,
        late: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        signals = row.signals_json or []
        if explain:
            signals = await self._explain_signals(
                db, organization_id=organization_id, signals=signals,
            )
        surface: dict[str, Any] = {
            "advisory_only": True,
            "state_key": row.state_key,
            "scope_type": row.scope_type,
            "scope_id": row.scope_id,
            "snapshot_ref": row.source_event_id,
            "snapshot_ts": _iso(row.snapshot_ts or row.occurred_at),
            "occurred_at": _iso(row.occurred_at),
            "dimensions": row.dimensions_json or [],
            "delta": row.delta_json or [],
            "signals": signals,
            "dependencies": row.dependencies_json or [],
            "risks": row.risks_json or [],
            "opportunities": row.opportunities_json or [],
            "affected_decisions": row.affected_decisions_json or [],
            "attention": row.attention_json or [],
            "next": row.next_json or [],
        }
        if late is not None:
            surface["late_snapshots"] = late
        surface["trail"] = [
            {
                "snapshot_ref": r.source_event_id,
                "occurred_at": _iso(r.occurred_at),
                "delta_count": len(r.delta_json or []),
            }
            for r in list(
                (
                    await db.execute(
                        select(CompanyStateHistory).where(
                            CompanyStateHistory.organization_id == organization_id,
                            CompanyStateHistory.scope_type == row.scope_type,
                            CompanyStateHistory.scope_id == row.scope_id,
                        ).order_by(CompanyStateHistory.occurred_at.desc())
                        .limit(10)
                    )
                ).scalars().all()
            )
        ]
        return surface

    async def living_state(
        self, db: AsyncSession, *, organization_id: str,
        as_of: Optional[str] = None,
        include_partial: bool = False,
        scope_type: str = "org", scope_id: Optional[str] = None,
        explain: bool = False,
    ) -> dict[str, Any]:
        """The living company state surface (§7.1). Reads "latest snapshot <=
        now" or the as_of anchor; the read path never writes outside the
        event-anchored TTL recompose (§10)."""
        as_of_dt = self._parse_asof(as_of)
        late: list[dict[str, Any]] = []
        if as_of_dt is not None and include_partial:
            late_rows = list(
                (
                    await db.execute(
                        select(CompanyStateHistory).where(
                            CompanyStateHistory.organization_id == organization_id,
                            CompanyStateHistory.scope_type == scope_type,
                            CompanyStateHistory.scope_id == scope_id,
                            CompanyStateHistory.occurred_at > as_of_dt,
                        ).order_by(CompanyStateHistory.occurred_at.asc())
                        .limit(10)
                    )
                ).scalars().all()
            )
            late = [
                {
                    "snapshot_ref": r.source_event_id,
                    "occurred_at": _iso(r.occurred_at),
                    "delta_count": len(r.delta_json or []),
                }
                for r in late_rows
            ]
        latest = await self._latest_state_row(
            db, organization_id=organization_id,
            scope_type=scope_type, scope_id=scope_id,
            as_of=as_of_dt if as_of_dt is not None else None,
        )
        now = datetime.now(timezone.utc)
        if as_of_dt is None:
            health_latest = await self._latest_health(
                db, organization_id=organization_id,
            )
            stale = latest is None
            if latest is not None:
                ref_ts = ensure_aware(latest.snapshot_ts or latest.occurred_at)
                stale = (now - ref_ts).total_seconds() > STATE_TTL
            if stale and health_latest is not None:
                # The TTL recompose is event-anchored: the same composition
                # function, the same deterministic surface -> exact-once, and
                # any new rows key on a real event id (never invented).
                await self._compose_state(
                    db, organization_id=organization_id,
                    scope_type=scope_type, scope_id=scope_id,
                    source_event_id=str(health_latest.source_event_id),
                    event_name="state.read.refresh",
                )
                latest = await self._latest_state_row(
                    db, organization_id=organization_id,
                    scope_type=scope_type, scope_id=scope_id,
                )
        if latest is None:
            surface = await self._compose_surface(
                db, organization_id=organization_id,
            )
            return {
                "advisory_only": True,
                "state_key": None,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "snapshot_ref": None,
                "snapshot_ts": None,
                "occurred_at": None,
                "composed": False,
                "note": "no state trail yet — composition will be written on "
                        "the next meaningful company event",
                **surface,
            }
        return await self._state_surface(
            db, row=latest, organization_id=organization_id,
            explain=explain,
            late=late if (as_of_dt is not None and late) else None,
        )

    async def state_delta(
        self, db: AsyncSession, *, organization_id: str,
        as_of: Optional[str] = None,
        include_partial: bool = False,
        explain: bool = False,
    ) -> dict[str, Any]:
        """The "What changed?" state-delta surface (brain company_changes)."""
        as_of_dt = self._parse_asof(as_of)
        latest = await self._latest_state_row(
            db, organization_id=organization_id,
            as_of=as_of_dt if as_of_dt is not None else None,
        )
        if latest is None:
            return {
                "advisory_only": True,
                "delta": [], "signals": [],
                "snapshot_ref": None,
                "note": "no state trail yet",
                "generated_at": _iso(datetime.now(timezone.utc)),
            }
        signals = latest.signals_json or []
        if explain:
            signals = await self._explain_signals(
                db, organization_id=organization_id, signals=signals,
            )
        return {
            "advisory_only": True,
            "delta": latest.delta_json or [],
            "signals": signals,
            "snapshot_ref": latest.source_event_id,
            "occurred_at": _iso(latest.occurred_at),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def state_risks(
        self, db: AsyncSession, *, organization_id: str,
        limit: int = MAX_STATE_RISKS,
    ) -> dict[str, Any]:
        """The exposure-composition surface (open risks, deterministic bands)."""
        return {
            "advisory_only": True,
            "risks": await self._state_risks(db, organization_id=organization_id, limit=limit),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def state_opportunities(
        self, db: AsyncSession, *, organization_id: str,
        limit: int = MAX_STATE_OPPORTUNITIES,
    ) -> dict[str, Any]:
        """The bounded opportunity surface (patterns/insights/recommendations)."""
        return {
            "advisory_only": True,
            "opportunities": await self._state_opportunities(
                db, organization_id=organization_id, limit=limit,
            ),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def state_affected_decisions(
        self, db: AsyncSession, *, organization_id: str,
        limit: int = MAX_STATE_DECISIONS,
    ) -> dict[str, Any]:
        """Affected decisions of the current state delta (bounded)."""
        latest = await self._latest_state_row(db, organization_id=organization_id)
        delta = latest.delta_json or [] if latest is not None else []
        affected = await self._state_affected_decisions(
            db, organization_id=organization_id, delta=delta, limit=limit,
        )
        return {
            "advisory_only": True,
            "affected_decisions": affected,
            "snapshot_ref": latest.source_event_id if latest is not None else None,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def state_dependencies(
        self, db: AsyncSession, *, organization_id: str,
        entity_type: str, entity_id: str, depth: int = MAX_CAUSAL_DEPTH,
    ) -> dict[str, Any]:
        """The bounded downstream-walk surface (§7.1) — reuses the existing
        causal_chain(); unknown (dependency-less) subject -> not_found."""
        result = await self.causal_chain(
            db, organization_id=organization_id,
            entity_type=entity_type, entity_id=entity_id, depth=depth,
        )
        if not (result.get("hops") or []):
            return {**result, "not_found": True}
        return result

    async def _state_context_anchor(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """The decide-time state anchor (§3.2, §7.2): current snapshot refs
        plus bounded dependency/risk/opportunity summaries — what the company
        knew when the decision was evaluated or recommended."""
        refs: list[str] = []
        if organization_id:
            rows = list(
                (
                    await db.execute(
                        select(CompanyStateHistory.source_event_id).where(
                            CompanyStateHistory.organization_id == organization_id,
                        ).order_by(CompanyStateHistory.occurred_at.desc())
                        .limit(3)
                    )
                ).scalars().all()
            )
            refs = [str(r) for r in rows]
        deps = await self._state_dependencies(db, organization_id=organization_id, limit=5)
        risks = await self._state_risks(db, organization_id=organization_id, limit=5)
        opps = await self._state_opportunities(db, organization_id=organization_id, limit=5)
        return {
            "snapshot_refs": refs,
            "dependencies": deps,
            "risks": risks,
            "opportunities": opps,
        }

    async def attach_state_context(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
    ) -> Optional[dict[str, Any]]:
        """§7.2 — attach the current state snapshot refs to the decision as
        state_context_json. Exact-once: replays with an identical payload
        return created:false and change nothing; decisions already past
        outcome_recorded are rejected (the same 409 detail.rejected law as
        4H.2)."""
        row = await self._decision_row(
            db, organization_id=organization_id, decision_id=decision_id,
        )
        if row is None:
            return None
        if row.state in ("outcome_recorded", "assessed"):
            return {
                "rejected": True,
                "decision_id": decision_id,
                "state": row.state,
                "reason": "decisions past outcome_recorded cannot re-anchor "
                          "their state context",
            }
        payload = await self._state_context_anchor(
            db, organization_id=organization_id,
        )
        created = row.state_context_json is None
        if row.state_context_json == payload:
            return {
                "accepted": True,
                "created": False,
                "changed": False,
                "decision_id": decision_id,
                "state_context": row.state_context_json,
                "already_attached": True,
            }
        row.state_context_json = payload
        await db.flush()
        return {
            "accepted": True,
            "created": created,
            "changed": True,
            "decision_id": decision_id,
            "state_context": payload,
            "already_attached": False,
        }

    # ----------------------------------------------------------------------
    # Slice 4H.4 — Decision-Rehearsal Intelligence (contract §2 L10-L15, §5,
    # §7). Rehearsal != prediction: every surface is advisory-only and every
    # consequence is provenance-traced to an existing causal edge or to the
    # existing bounded what-if derivation. The engine never writes the
    # canonical stores from a scenario, never auto-executes, and persists
    # ONLY the append-only rehearsal rows (exact-once, event-anchored).
    # ----------------------------------------------------------------------

    @staticmethod
    def _scenario_input_hash(scenario_kind: str, input_json: dict[str, Any]) -> str:
        """Deterministic exact-once identity §3.1/L15 — identical normalized
        input + identical baseline snapshot hash to the same key."""
        import hashlib
        import json as _json

        canonical = _json.dumps(
            {"kind": scenario_kind, "input": input_json},
            sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _scenario_honesty() -> dict[str, Any]:
        return {
            "advisory_only": True,
            "not_a_prediction": True,
            "mode": "bounded-scenario-rehearsal",
        }

    @staticmethod
    def _scenario_note(kind: str, baseline_missing: bool, hops: list[Any]) -> str:
        base = (
            "no living-state snapshot yet — consequences cite the current "
            "causal edges only"
            if baseline_missing else
            "anchored to the newest living-state snapshot; bounded sensitivity, "
            "not a prediction"
        )
        if not hops:
            return base + "; the subject has no recorded causal dependencies yet"
        return base

    async def _rehearse_propagation(
        self, db: AsyncSession, *, organization_id: str,
        subject_type: str, subject_id: str,
    ) -> dict[str, Any]:
        """Bounded BFS over the EXISTING company_causal_edges snapshot — the
        same table and bounds as causal_chain(), but every hop carries its
        edge_id so consequences are provenance-traced (§5.2). Read-only:
        company_causal_edges is never written by 4H.4 (L11)."""
        rows = list(
            (
                await db.execute(
                    select(CompanyCausalEdge).where(
                        CompanyCausalEdge.organization_id == organization_id,
                    ).order_by(CompanyCausalEdge.created_at.desc())
                    .limit(MAX_CAUSAL_EDGES * 3)
                )
            ).scalars().all()
        )
        adj: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for e in rows:
            adj.setdefault((e.source_type, e.source_id), []).append({
                "edge_id": e.id,
                "from_type": e.source_type, "from_id": e.source_id,
                "to_type": e.target_type, "to_id": e.target_id,
                "kind": e.kind, "confidence": e.confidence,
            })
        hops: list[dict[str, Any]] = []
        visited = {(subject_type, subject_id)}
        frontier = [(subject_type, subject_id)]
        for _ in range(MAX_CAUSAL_DEPTH):
            nxt: list[tuple[str, str]] = []
            for node in frontier:
                for h in sorted(
                    adj.get(node, ()),
                    key=lambda x: (
                        {"high": 0, "medium": 1, "low": 2}.get(x["confidence"], 1),
                        x["kind"], x["edge_id"],
                    ),
                ):
                    target = (h["to_type"], h["to_id"])
                    if target in visited:
                        continue
                    visited.add(target)
                    hops.append(h)
                    nxt.append(target)
                    if len(hops) >= MAX_CAUSAL_EDGES:
                        break
                if len(hops) >= MAX_CAUSAL_EDGES:
                    break
            frontier = nxt
            if not frontier or len(hops) >= MAX_CAUSAL_EDGES:
                break
        hops = await self._label_hops(
            db, organization_id=organization_id, hops=hops,
        )
        return {
            "hops": hops[:MAX_CAUSAL_EDGES],
            "bounded": len(hops) >= MAX_CAUSAL_EDGES,
        }

    async def _scenario_baseline(
        self, db: AsyncSession, *, organization_id: str,
        scope_type: str, scope_id: Optional[str], as_of: Optional[str],
    ) -> dict[str, Any]:
        """The 4H.3 state snapshot the rehearsal anchors to (strict as_of
        semantics — never composes post-epoch state into a scenario)."""
        as_of_dt = self._parse_asof(as_of) if as_of else None
        latest = await self._latest_state_row(
            db, organization_id=organization_id,
            scope_type=scope_type, scope_id=scope_id,
            as_of=as_of_dt if as_of_dt is not None else None,
        )
        if latest is None:
            return {
                "snapshot_ref": None, "state_key": None,
                "occurred_at": None, "scope_type": scope_type,
                "scope_id": scope_id, "as_of": as_of,
            }
        return {
            "snapshot_ref": latest.source_event_id,
            "state_key": latest.state_key,
            "occurred_at": _iso(latest.occurred_at),
            "scope_type": latest.scope_type,
            "scope_id": latest.scope_id,
            "as_of": as_of,
        }

    async def _rehearse_surface(
        self, db: AsyncSession, *, organization_id: str,
        scenario_kind: str, subject_type: str, subject_id: str,
        params: dict[str, Any], assumptions: list[Any],
        scope_type: str, scope_id: Optional[str],
        as_of: Optional[str],
    ) -> dict[str, Any]:
        """The bounded canonical consequence surface (§5.3) composed ONLY
        from existing rows: baseline snapshot, causal-edge walks, risk bands,
        opportunity surface, affected-decision intersection, and — for the
        three what-if kinds — the existing what_if() consequence language."""
        baseline = await self._scenario_baseline(
            db, organization_id=organization_id,
            scope_type=scope_type, scope_id=scope_id, as_of=as_of,
        )
        propagation = await self._rehearse_propagation(
            db, organization_id=organization_id,
            subject_type=subject_type, subject_id=subject_id,
        )
        hops = propagation["hops"]
        edge_ids = {str(h.get("edge_id") or "") for h in hops}
        reached: set[tuple[str, str]] = {(subject_type, subject_id)} | (
            {(str(h.get("from_type")), str(h.get("from_id"))) for h in hops}
            | {(str(h.get("to_type")), str(h.get("to_id"))) for h in hops}
        )
        reached_ids: set[str] = {i for _, i in reached}

        # DIRECT EFFECTS: for the sanctioned what-if kinds the existing
        # derivation language is the direct effect of the change; otherwise
        # hop-1 entities are the direct effects. Bounded (§12).
        direct: list[dict[str, Any]] = []
        what_if_guidance: list[dict[str, Any]] = []
        if scenario_kind in WHATIF_SCENARIOS:
            wi = await self.what_if(
                db, organization_id=organization_id,
                scenario_type=scenario_kind, payload=params,
            )
            for c in (wi.get("consequences") or []):
                item = {
                    "entity_type": "what_if",
                    "entity_id": None,
                    "label": c.get("label"),
                    "impact": c.get("impact"),
                    "detail": c.get("detail"),
                    "confidence": c.get("confidence"),
                    "basis": {
                        "edge_id": None,
                        "source": "what_if",
                        "relation": f"what_if:{scenario_kind}",
                    },
                }
                what_if_guidance.append(item)
                direct.append(item)
        one_hop = [h for h in hops if (str(h.get("from_type")), str(h.get("from_id"))) == (subject_type, subject_id)]
        deeper = [h for h in hops if h not in one_hop]
        for h in one_hop:
            direct.append({
                "entity_type": h.get("to_type"), "entity_id": h.get("to_id"),
                "label": h.get("to_label"),
                "impact": "affected",
                "detail": h.get("kind"),
                "confidence": h.get("confidence"),
                "basis": {
                    "edge_id": h.get("edge_id"),
                    "source_id": h.get("from_id"),
                    "target_id": h.get("to_id"),
                    "relation": h.get("kind"),
                },
            })
        direct = _head(direct, MAX_WHATIF_CONSEQUENCES)
        dependent = _head(
            [
                {
                    "entity_type": h.get("to_type"), "entity_id": h.get("to_id"),
                    "label": h.get("to_label"),
                    "impact": "dependent",
                    "detail": h.get("kind"),
                    "confidence": h.get("confidence"),
                    "basis": {
                        "edge_id": h.get("edge_id"),
                        "source_id": h.get("from_id"),
                        "target_id": h.get("to_id"),
                        "relation": h.get("kind"),
                    },
                }
                for h in deeper
            ],
            MAX_WHATIF_CONSEQUENCES,
        )

        # RISKS ALREADY PRESENT: open-risk exposure intersecting the reached
        # entities — bands/probabilities/impacts cited unchanged (L10).
        risks = [
            r for r in await self._state_risks(db, organization_id=organization_id)
            if any(
                str(a.get("id") or "") in reached_ids
                for a in (r.get("affected") or [])
            )
        ]
        # OPPORTUNITIES ALREADY PRESENT: bounded top-N context, honestly
        # labeled as company-state context — never consequences.
        opportunities = await self._state_opportunities(
            db, organization_id=organization_id,
        )

        # DECISIONS THAT SHOULD BE RECONSIDERED: deterministic intersection
        # with the reached entities (L12, read-only).
        pseudo_delta = [
            {"entity": t, "id": i, "kind": t, "label": ""}
            for t, i in sorted(reached)
        ]
        affected: list[dict[str, Any]] = []
        if pseudo_delta:
            affected = await self._state_affected_decisions(
                db, organization_id=organization_id,
                delta=pseudo_delta, limit=MAX_STATE_DECISIONS,
            )
        if scenario_kind == "decision_reconsider" and subject_type == "decision":
            dec = (
                await db.execute(
                    select(CompanyDecision.id).where(
                        CompanyDecision.organization_id == organization_id,
                        CompanyDecision.decision_id == subject_id,
                    ).limit(1)
                )
            ).scalars().first()
            if dec is not None:
                affected.append({
                    "decision_id": subject_id, "state": "active",
                    "kind": "decision_reconsider", "title": "",
                    "why": "explicit decision-reconsideration rehearsal",
                })
        decisions = [
            {
                "decision_id": a.get("decision_id"),
                "state": a.get("state") or "active",
                "why": a.get("why") or "needs_reconsideration",
                "advisory": True,
            }
            for a in affected[:MAX_STATE_DECISIONS]
        ]

        consequences = {
            "direct_effects": direct,
            "dependent_effects": dependent,
            "risks_already_present": risks,
            "opportunities_already_present": opportunities,
            "what_if_guidance": what_if_guidance,
        }
        note = self._scenario_note(
            scenario_kind,
            baseline_missing=baseline["snapshot_ref"] is None,
            hops=hops,
        )
        return {
            "advisory_only": True,
            "not_a_prediction": True,
            "baseline": baseline,
            "hypothetical_change": {
                "scenario_kind": scenario_kind,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "params": params,
                "assumptions": assumptions,
                "organization_scope": {"scope_type": scope_type, "scope_id": scope_id},
                "as_of": as_of,
            },
            "direct_effects": direct,
            "dependent_effects": dependent,
            "risks_already_present": risks,
            "opportunities_already_present": opportunities,
            "decisions_to_reconsider": decisions,
            "causal_basis": {
                "hops": hops,
                "hop_count": len(hops),
                "edge_ids": sorted(e for e in edge_ids if e),
                "bounded": propagation["bounded"],
            },
            "snapshot_ref": baseline["snapshot_ref"],
            "honesty": self._scenario_honesty(),
            "human_decision": (
                "A human decides what to do next — VCOS presents consequences "
                "and evidence, it never selects among options."
            ),
            "note": note,
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    def _scenario_row_surface(self, row: CompanyScenarioRun) -> dict[str, Any]:
        """Byte-identical re-query surface from the stored row (§5.1) — the
        read path never recomputes; it returns exactly what was recorded."""
        honesty = dict(row.honesty_json or self._scenario_honesty())
        surf = dict(row.consequences_json or {})
        surface: dict[str, Any] = {
            "scenario_id": row.id,
            "organization_id": row.organization_id,
            "scope_type": row.scope_type,
            "scope_id": row.scope_id,
            "advisory_only": True,
            "not_a_prediction": True,
            "baseline": {
                "snapshot_ref": row.snapshot_ref,
                "state_key": row.state_key,
                "occurred_at": _iso(row.occurred_at),
                "scope_type": row.scope_type,
                "scope_id": row.scope_id,
                "as_of": (row.input_json or {}).get("as_of"),
            },
            "hypothetical_change": {
                "scenario_kind": row.scenario_kind,
                "subject_type": (row.input_json or {}).get("subject_type"),
                "subject_id": (row.input_json or {}).get("subject_id"),
                "params": (row.input_json or {}).get("params", {}),
                "assumptions": row.assumptions_json or [],
                "organization_scope": {
                    "scope_type": row.scope_type, "scope_id": row.scope_id,
                },
                "as_of": (row.input_json or {}).get("as_of"),
            },
            "direct_effects": surf.get("direct_effects", []),
            "dependent_effects": surf.get("dependent_effects", []),
            "risks_already_present": surf.get("risks_already_present", []),
            "opportunities_already_present": surf.get("opportunities_already_present", []),
            "decisions_to_reconsider": row.decision_suggestions_json or [],
            "causal_basis": {
                "hops": row.propagation_json or [],
                "hop_count": len(row.propagation_json or []),
                "edge_ids": sorted(
                    str(h.get("edge_id") or "") for h in (row.propagation_json or []) if h.get("edge_id")
                ),
                "bounded": len(row.propagation_json or []) >= MAX_CAUSAL_EDGES,
            },
            "snapshot_ref": row.snapshot_ref,
            "honesty": honesty,
            "human_decision": (
                "A human decides what to do next — VCOS presents consequences "
                "and evidence, it never selects among options."
            ),
            "note": "recorded rehearsal — replayed from the append-only history",
            "created": False,
            "replayed": True,
            "dry_run": False,
            "occurred_at": _iso(row.occurred_at),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }
        return surface

    async def scenario_rehearse(
        self, db: AsyncSession, *, organization_id: str,
        scenario_kind: str, subject_type: str, subject_id: str,
        params: Optional[dict[str, Any]] = None,
        assumptions: Optional[list[Any]] = None,
        scope_type: str = "org", scope_id: Optional[str] = None,
        as_of: Optional[str] = None, dry_run: bool = False,
        created_by: Optional[str] = None,
    ) -> dict[str, Any]:
        """One deterministic rehearsal (§7.1). dry_run=true derives, returns,
        writes NOTHING and emits zero events (the exploration sandbox).
        dry_run=false additionally records the append-only rehearsal row —
        institutional memory — event-anchored, exact-once: an identical
        hypothetical against the identical baseline snapshot REPLAYS the
        stored row (created:false, zero events); the same hypothetical
        against a changed snapshot writes a NEW rehearsal (L15)."""
        kind = (scenario_kind or "").strip().lower()
        st = (subject_type or "").strip().lower()
        sid = (subject_id or "").strip()
        if kind not in SCENARIO_KINDS:
            return {
                "advisory_only": True,
                "not_a_prediction": True,
                "error": (
                    f"scenario_kind must be one of {', '.join(SCENARIO_KINDS)}"
                ),
                "generated_at": _iso(datetime.now(timezone.utc)),
            }
        if not st or not sid:
            return {
                "advisory_only": True,
                "not_a_prediction": True,
                "error": "subject_type and subject_id are required",
                "generated_at": _iso(datetime.now(timezone.utc)),
            }
        params_clean = {
            k: v for k, v in (params or {}).items()
            if k in SCENARIO_PARAM_KEYS and v is not None
        }
        assumptions_clean: list[Any] = []
        for a in (assumptions or [])[:MAX_SCENARIO_ASSUMPTIONS]:
            if isinstance(a, dict) and "name" in a:
                assumptions_clean.append({
                    "name": str(a.get("name") or "")[:200],
                    "value": str(a.get("value") or "")[:500],
                })
            elif isinstance(a, str):
                assumptions_clean.append({"name": a[:200], "value": ""})
        input_json: dict[str, Any] = {
            "scenario_kind": kind,
            "subject_type": st,
            "subject_id": sid,
            "params": params_clean,
            "assumptions": assumptions_clean,
            "organization_scope": {"scope_type": scope_type, "scope_id": scope_id},
            "as_of": as_of,
        }
        input_hash = self._scenario_input_hash(kind, input_json)
        surface = await self._rehearse_surface(
            db, organization_id=organization_id,
            scenario_kind=kind, subject_type=st, subject_id=sid,
            params=params_clean, assumptions=assumptions_clean,
            scope_type=scope_type, scope_id=scope_id, as_of=as_of,
        )
        snapshot_ref = surface["baseline"]["snapshot_ref"] or ""
        if dry_run:
            return {
                **surface,
                "scenario_id": None,
                "input_hash": input_hash,
                "created": False,
                "replayed": False,
                "dry_run": True,
            }
        existing = (
            await db.execute(
                select(CompanyScenarioRun).where(
                    CompanyScenarioRun.organization_id == organization_id,
                    CompanyScenarioRun.scope_type == scope_type,
                    CompanyScenarioRun.scope_id == scope_id,
                    CompanyScenarioRun.scenario_kind == kind,
                    CompanyScenarioRun.input_hash == input_hash,
                    CompanyScenarioRun.snapshot_ref == snapshot_ref,
                ).limit(1)
            )
        ).scalars().first()
        if existing is not None:
            stored = self._scenario_row_surface(existing)
            stored["input_hash"] = input_hash
            return stored
        from app.events.publisher import publish_background_event

        event_row = await publish_background_event(
            db, name="company.scenario.recorded",
            organization_id=organization_id,
            payload={
                "organization_id": organization_id,
                "scenario_kind": kind,
                "subject_type": st,
                "subject_id": sid,
                "snapshot_ref": snapshot_ref or None,
                "consequences_count": (
                    len(surface["direct_effects"]) + len(surface["dependent_effects"])
                ),
                "not_a_prediction": True,
                "advisory_only": True,
            },
        )
        occurrence = datetime.now(timezone.utc)
        row = CompanyScenarioRun(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            state_key=surface["baseline"]["state_key"] or "",
            snapshot_ref=snapshot_ref,
            scenario_kind=kind,
            input_json=input_json,
            input_hash=input_hash,
            assumptions_json=assumptions_clean,
            propagation_json=surface["causal_basis"]["hops"],
            consequences_json={
                "direct_effects": surface["direct_effects"],
                "dependent_effects": surface["dependent_effects"],
                "risks_already_present": surface["risks_already_present"],
                "opportunities_already_present": surface["opportunities_already_present"],
                "what_if_guidance": surface.get("what_if_guidance", []),
            },
            decision_suggestions_json=surface["decisions_to_reconsider"],
            honesty_json=self._scenario_honesty(),
            source_event_id=str(event_row.id),
            created_by=created_by,
            occurred_at=occurrence,
        )
        db.add(row)
        await db.flush()
        result = self._scenario_row_surface(row)
        result["input_hash"] = input_hash
        result["created"] = True
        result["replayed"] = False
        result["dry_run"] = False
        result["note"] = surface["note"]
        result["what_if_guidance"] = surface.get("what_if_guidance", [])
        return result

    async def scenario_detail(
        self, db: AsyncSession, *, organization_id: str, scenario_id: str,
    ) -> Optional[dict[str, Any]]:
        """Re-query a recorded rehearsal — byte-identical to the stored row,
        replayed:true, zero events (§5.1, §6)."""
        row = (
            await db.execute(
                select(CompanyScenarioRun).where(
                    CompanyScenarioRun.organization_id == organization_id,
                    CompanyScenarioRun.id == scenario_id,
                ).limit(1)
            )
        ).scalars().first()
        if row is None:
            return None
        return self._scenario_row_surface(row)

    async def scenario_history(
        self, db: AsyncSession, *, organization_id: str,
        scope_type: str = "org", scope_id: Optional[str] = None,
        limit: int = MAX_SCENARIOS_SHOWN,
    ) -> dict[str, Any]:
        """Bounded history of recorded rehearsals (newest first, summary
        shape only, zero events). Institutional memory the future
        action→outcome→learning slices consume by scenario_id."""
        rows = list(
            (
                await db.execute(
                    select(CompanyScenarioRun).where(
                        CompanyScenarioRun.organization_id == organization_id,
                        CompanyScenarioRun.scope_type == scope_type,
                        CompanyScenarioRun.scope_id == scope_id,
                    ).order_by(CompanyScenarioRun.occurred_at.desc())
                    .limit(min(limit, MAX_SCENARIOS_SHOWN))
                )
            ).scalars().all()
        )
        return {
            "advisory_only": True,
            "scenarios": [
                {
                    "scenario_id": r.id,
                    "scenario_kind": r.scenario_kind,
                    "subject_type": (r.input_json or {}).get("subject_type"),
                    "subject_id": (r.input_json or {}).get("subject_id"),
                    "snapshot_ref": r.snapshot_ref,
                    "consequences_count": (
                        len((r.consequences_json or {}).get("direct_effects", []))
                        + len((r.consequences_json or {}).get("dependent_effects", []))
                    ),
                    "decisions_to_reconsider": len(r.decision_suggestions_json or []),
                    "occurred_at": _iso(r.occurred_at),
                }
                for r in rows
            ],
            "total": len(rows),
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    async def scenario_compare(
        self, db: AsyncSession, *, organization_id: str,
        scenario_ids: list[str],
    ) -> dict[str, Any]:
        """Side-by-side comparison §7.1: baseline (current 4H.3 snapshot) vs
        each recorded rehearsal — deltas only, deterministic order by
        scenario_id, NEVER ranks or selects (the human decides)."""
        ids = [str(i) for i in (scenario_ids or []) if str(i).strip()][:5]
        if len(ids) < 2:
            return {
                "advisory_only": True,
                "not_a_prediction": True,
                "error": "compare requires between 2 and 5 scenario ids",
                "generated_at": _iso(datetime.now(timezone.utc)),
            }
        rows = list(
            (
                await db.execute(
                    select(CompanyScenarioRun).where(
                        CompanyScenarioRun.organization_id == organization_id,
                        CompanyScenarioRun.id.in_(ids),
                    )
                )
            ).scalars().all()
        )
        found = {r.id: r for r in rows}
        baseline = await self._scenario_baseline(
            db, organization_id=organization_id,
            scope_type="org", scope_id=None, as_of=None,
        )
        ordered: list[dict[str, Any]] = []
        for sid in sorted(ids):
            row = found.get(sid)
            if row is None:
                continue
            ordered.append({
                "scenario_id": row.id,
                "scenario_kind": row.scenario_kind,
                "subject": {
                    "type": (row.input_json or {}).get("subject_type"),
                    "id": (row.input_json or {}).get("subject_id"),
                },
                "snapshot_ref": row.snapshot_ref,
                "direct_effects": (row.consequences_json or {}).get("direct_effects", []),
                "dependent_effects": (row.consequences_json or {}).get("dependent_effects", []),
                "risks_already_present": (row.consequences_json or {}).get("risks_already_present", []),
                "opportunities_already_present": (row.consequences_json or {}).get("opportunities_already_present", []),
                "decisions_to_reconsider": row.decision_suggestions_json or [],
            })
        return {
            "advisory_only": True,
            "not_a_prediction": True,
            "baseline": baseline,
            "scenarios": ordered,
            "comparison": "side-by-side evidence only — no option is ranked "
                          "or selected; a human decides",
            "note": sorted(ids) if len(ordered) != len(ids) else "",
            "generated_at": _iso(datetime.now(timezone.utc)),
        }

    # ----------------------------------------------------------------------
    # Slice 4H.5 — Strategic Decision-to-Action & Execution Intelligence.
    # Two read-only surfaces over EXISTING canonical rows: the advisory
    # ACTION PLAN (deterministic, non-inventive, never persisted, emits
    # nothing — L18/L19) and the EXECUTION CHAIN (a live truthful read-model
    # over the decision's authorized actions, evidence, artifacts and
    # outcomes). Authorization itself stays in action_ops_engine.propose via
    # the lineage columns; nothing here writes, routes, approves, or predicts.
    # ----------------------------------------------------------------------

    async def derive_action_plan(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
    ) -> Optional[dict[str, Any]]:
        """Derive the advisory action plan for one approved decision.

        Deterministic and NON-INVENTIVE (L18): a step exists only when a
        canonical anchor supports it — an open risk reached through the
        decision's decide-time context, or a project the decision canonically
        scopes or references. Every step cites its basis; with zero anchors
        the plan is honestly empty (`insufficient_canonical_basis`). The plan
        is never persisted and emits no events; it ends at HUMAN AUTHORIZATION.
        """
        row = await self._decision_row(
            db, organization_id=organization_id, decision_id=decision_id,
        )
        if row is None:
            return None
        if row.state in _PRE_APPROVAL_DECISION_STATES:
            return {
                "rejected": True,
                "decision_id": decision_id,
                "state": row.state,
                "reason": "decision not yet approved",
            }

        # -- canonical anchors: the decide-time context (4H.3 state anchor,
        # falling back to the 4H.2 as-of anchor), deterministically merged.
        state_ctx = (
            row.state_context_json if isinstance(row.state_context_json, dict) else {}
        )
        asof_ctx = (
            row.as_of_context_json if isinstance(row.as_of_context_json, dict) else {}
        )
        ctx_risks = state_ctx.get("risks") or asof_ctx.get("risks") or []
        ctx_deps = state_ctx.get("dependencies") or asof_ctx.get("dependencies") or []

        # live causal edges touching the decision (bounded neighborhood)
        edges = list(
            (
                await db.execute(
                    select(CompanyCausalEdge).where(
                        CompanyCausalEdge.organization_id == organization_id,
                        or_(
                            and_(
                                CompanyCausalEdge.source_type == "decision",
                                CompanyCausalEdge.source_id == decision_id,
                            ),
                            and_(
                                CompanyCausalEdge.target_type == "decision",
                                CompanyCausalEdge.target_id == decision_id,
                            ),
                        ),
                    ).order_by(CompanyCausalEdge.created_at.desc())
                    .limit(MAX_PLAN_EDGES)
                )
            ).scalars().all()
        )

        # open risks reached via the decide-time context (live-verified —
        # a risk that was closed since deciding is no longer a step target)
        risk_ids: list[str] = []
        for r in ctx_risks:
            rid = (r.get("risk_id") or "").strip() if isinstance(r, dict) else ""
            if rid and rid not in risk_ids:
                risk_ids.append(rid)
        open_risks: dict[str, Risk] = {}
        if risk_ids:
            rows = list(
                (
                    await db.execute(
                        select(Risk).where(
                            Risk.organization_id == organization_id,
                            Risk.id.in_(risk_ids[:MAX_PLAN_STEPS * 2]),
                            Risk.status != "closed",
                        )
                    )
                ).scalars().all()
            )
            open_risks = {r.id: r for r in rows}

        # projects the decision canonically scopes or references
        project_ids: list[str] = []
        if row.scope_type == "project" and row.scope_id:
            project_ids.append(row.scope_id)
        for d in ctx_deps:
            tid = (d.get("target_id") or "").strip() if isinstance(d, dict) else ""
            if (
                isinstance(d, dict) and d.get("target_type") == "project"
                and tid and tid not in project_ids
            ):
                project_ids.append(tid)
        known_projects: dict[str, Project] = {}
        if project_ids:
            prows = list(
                (
                    await db.execute(
                        select(Project).where(
                            Project.organization_id == organization_id,
                            Project.id.in_(project_ids[:MAX_PLAN_STEPS * 2]),
                        )
                    )
                ).scalars().all()
            )
            known_projects = {p.id: p for p in prows}

        # -- step derivation: fixed order (context risks, then scoped/referenced
        # projects), each step carrying its basis — NO PROVENANCE, NO STEP.
        steps: list[dict[str, Any]] = []
        for rid in risk_ids:
            if len(steps) >= MAX_PLAN_STEPS:
                break
            risk = open_risks.get(rid)
            if risk is None:
                continue
            policy = action_ops_engine._policy_for("task", "low")
            steps.append({
                "step_no": len(steps) + 1,
                "action_type": "task",
                "title": f"Address open risk '{risk.title}' flagged by this decision",
                "target": {"entity": "risk", "id": risk.id, "label": risk.title},
                "basis": {
                    "decision_id": row.decision_id,
                    "risk_id": risk.id,
                    "relation": "decide_time_risk",
                },
                "approval_expected": {
                    "policy": policy["route"],
                    "approval_required": policy["approval_required"],
                },
            })
        for pid in project_ids:
            if len(steps) >= MAX_PLAN_STEPS:
                break
            project = known_projects.get(pid)
            if project is None:
                continue
            relation = (
                "decision_scope_project"
                if row.scope_type == "project" and row.scope_id == pid
                else "state_context_dependency"
            )
            policy = action_ops_engine._policy_for("task", "low")
            steps.append({
                "step_no": len(steps) + 1,
                "action_type": "task",
                "title": f"Align project '{project.name}' with this decision",
                "target": {"entity": "project", "id": project.id, "label": project.name},
                "basis": {
                    "decision_id": row.decision_id,
                    "target_id": project.id,
                    "relation": relation,
                },
                "approval_expected": {
                    "policy": policy["route"],
                    "approval_required": policy["approval_required"],
                },
            })

        # actions already authorized from this decision (lineage column)
        authorized = list(
            (
                await db.execute(
                    select(CompanyAction).where(
                        CompanyAction.organization_id == organization_id,
                        CompanyAction.source_company_decision_id == decision_id,
                    ).order_by(CompanyAction.created_at.desc())
                    .limit(MAX_CHAIN_ACTIONS)
                )
            ).scalars().all()
        )

        status = "ok" if steps else "insufficient_canonical_basis"
        return {
            "decision": {
                "decision_id": row.decision_id,
                "kind": row.kind,
                "title": row.title,
                "state": row.state,
            },
            "origin": {
                "recommendation_key": row.recommendation_key,
                "rationale": row.rationale,
                "impact_label": row.impact_label,
            },
            "proposed_steps": steps,
            "dependencies": [
                {
                    "edge_id": e.id,
                    "kind": e.kind,
                    "source_type": e.source_type,
                    "source_id": e.source_id,
                    "target_type": e.target_type,
                    "target_id": e.target_id,
                    "confidence": e.confidence,
                }
                for e in edges[:MAX_CHAIN_ARTIFACTS]
            ],
            "authorized_actions": [
                {"id": a.id, "action_type": a.action_type, "title": a.title, "state": a.state}
                for a in authorized
            ],
            "honesty": {
                "advisory_only": True,
                "not_a_prediction": True,
                "derivation_status": status,
                "human_authorization_required": True,
            },
        }

    async def execution_chain(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
        access: Any = None,
    ) -> Optional[dict[str, Any]]:
        """The live truthful execution chain of one decision.

        Stitches decision → authorized actions → audit evidence → routed
        artifacts → outcomes → lesson, every node citing canonical ids (no
        provenance, no node). This is a READ-MODEL over mutable lifecycle
        rows — truthful to current evidence, deliberately NOT byte-frozen.
        """
        row = await self._decision_row(
            db, organization_id=organization_id, decision_id=decision_id,
        )
        if row is None:
            return None

        actions = list(
            (
                await db.execute(
                    select(CompanyAction).where(
                        CompanyAction.organization_id == organization_id,
                        CompanyAction.source_company_decision_id == decision_id,
                    ).order_by(CompanyAction.created_at.desc())
                    .limit(MAX_CHAIN_ACTIONS)
                )
            ).scalars().all()
        )
        action_ids = [a.id for a in actions]

        evidence: list[dict[str, Any]] = []
        if action_ids:
            events = list(
                (
                    await db.execute(
                        select(CompanyActionEvent).where(
                            CompanyActionEvent.organization_id == organization_id,
                            CompanyActionEvent.action_id.in_(action_ids),
                        ).order_by(CompanyActionEvent.created_at.desc())
                        .limit(MAX_CHAIN_EVIDENCE)
                    )
                ).scalars().all()
            )
            evidence = [
                {
                    "event_id": ev.id,
                    "action_id": ev.action_id,
                    "event": ev.event,
                    "actor_id": ev.actor_id,
                    "created_at": _iso(ev.created_at),
                }
                for ev in events
            ]

        org_wide = bool(getattr(access, "org_wide", False))
        visible_projects = getattr(access, "project_ids", frozenset()) or frozenset()
        artifacts: list[dict[str, Any]] = []
        seen_targets: set[tuple[str, str]] = set()
        for a in actions:
            if len(artifacts) >= MAX_CHAIN_ARTIFACTS:
                break
            if not a.target_type or not a.target_id:
                continue
            key = (a.target_type, a.target_id)
            if key in seen_targets:
                continue
            if (
                not org_wide and a.target_type == "project"
                and a.target_id not in visible_projects
            ):
                continue  # artifact-level visibility (L7/L14)
            seen_targets.add(key)
            artifacts.append({
                "target_type": a.target_type,
                "target_id": a.target_id,
                "via_action_id": a.id,
            })

        outcomes: list[dict[str, Any]] = []
        if action_ids:
            orows = list(
                (
                    await db.execute(
                        select(CompanyActionOutcome).where(
                            CompanyActionOutcome.organization_id == organization_id,
                            CompanyActionOutcome.action_id.in_(action_ids),
                        ).order_by(CompanyActionOutcome.measured_at.desc())
                        .limit(MAX_CHAIN_OUTCOMES)
                    )
                ).scalars().all()
            )
            outcomes = [
                {
                    "outcome_id": o.id,
                    "action_id": o.action_id,
                    "outcome_type": o.outcome_type,
                    "effectiveness": o.effectiveness,
                    "verdict": o.verdict,
                    "measured_at": _iso(o.measured_at),
                }
                for o in orows
            ]

        lesson = None
        if row.lesson:
            lesson = {"lesson": row.lesson, "reviewed_at": _iso(row.reviewed_at)}

        return {
            "decision": {
                "decision_id": row.decision_id,
                "kind": row.kind,
                "title": row.title,
                "state": row.state,
                "approved_at": _iso(row.approved_at),
                "executed_at": _iso(row.executed_at),
                "outcome_kind": row.outcome_kind,
                "effectiveness": row.effectiveness,
            },
            "actions": [
                {
                    "action_id": a.id,
                    "action_type": a.action_type,
                    "title": a.title,
                    "state": a.state,
                    "assignee_id": a.assignee_id,
                    "due_at": _iso(a.due_at),
                    "source_company_decision_id": a.source_company_decision_id,
                    "source_scenario_id": a.source_scenario_id,
                }
                for a in actions
            ],
            "evidence": evidence,
            "artifacts": artifacts,
            "outcomes": outcomes,
            "lesson": lesson,
            "generated_at": _iso(datetime.now(timezone.utc)),
            "honesty": {"advisory_only": True, "not_a_prediction": True},
            "note": (
                "Live read-model over mutable lifecycle rows - regenerated "
                "from canonical evidence on every read, never frozen."
            ),
        }

    # ------------------------------------------------------- Slice 4H.6
    # Temporal measurement helpers (Step 2). Deterministic READ-ONLY
    # derivation of decision-anchored measurement windows over canonical
    # BusinessMetricObservation rows. L20/L21/L24/L27: only label="actual"
    # observations are eligible for measurement truth; recorded / derived /
    # unknown are never collapsed; every comparison exposes its explicit
    # temporal basis; direction metadata is preserved but never turned into
    # a judgment; no timestamp is ever invented.

    PERF_WINDOW_DAYS = 90
    MAX_MEASUREMENT_OBSERVATIONS = 200
    MAX_LINKED_METRICS = 20

    def _decision_anchor_dt(
        self, row: CompanyDecision,
    ) -> tuple[Optional[datetime], str]:
        """Canonical decision anchor: executed_at > approved_at > created_at.

        Never invented - basis names the exact canonical column used;
        'unknown' only if the row carries no timing at all."""
        for attr in ("executed_at", "approved_at", "created_at"):
            dt = getattr(row, attr, None)
            if dt is not None:
                return ensure_aware(dt), attr
        return None, "unknown"

    async def decision_temporal_anchor(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
    ) -> Optional[dict[str, Any]]:
        """The explicit temporal anchor of one decision (L24), read-only."""
        row = await self._decision_row(
            db, organization_id=organization_id, decision_id=decision_id,
        )
        if row is None:
            return None
        anchor_dt, basis = self._decision_anchor_dt(row)
        return {
            "decision_id": row.decision_id,
            "anchor": _iso(anchor_dt),
            "anchor_basis": basis,
            "honesty": {"read_only": True, "no_invented_timestamps": True},
        }

    async def decision_linked_metrics(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
    ) -> list[dict[str, Any]]:
        """Canonical decision-to-metric associations from existing
        BusinessPerformanceLink rows (target_type='decision'). Read-only,
        bounded, deterministically ordered - no new linkage system."""
        links = list(
            (
                await db.execute(
                    select(BusinessPerformanceLink, BusinessMetric)
                    .join(
                        BusinessMetric,
                        BusinessMetric.id == BusinessPerformanceLink.entity_id,
                    )
                    .where(
                        BusinessPerformanceLink.organization_id == organization_id,
                        BusinessPerformanceLink.target_type == "decision",
                        BusinessPerformanceLink.target_id == decision_id,
                        BusinessPerformanceLink.entity_type == "business_metric",
                    )
                    .order_by(BusinessMetric.key.asc(), BusinessMetric.id.asc())
                    .limit(self.MAX_LINKED_METRICS)
                )
            ).all()
        )
        return [
            {
                "metric_id": metric.id,
                "key": metric.key,
                "name": metric.label,
                "unit": metric.unit,
                "direction": metric.direction,
                "link": {
                    "link_id": link.id,
                    "kind": link.kind,
                    "weight": link.weight,
                    "reasoning": link.reasoning,
                },
            }
            for link, metric in links
        ]

    async def metric_measurement_window(
        self, db: AsyncSession, *, organization_id: str, metric_id: str,
        anchor: Any, window_days: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        """Deterministic BEFORE/AFTER measurement window for one metric
        around a canonical anchor instant.

        Baseline  = latest label='actual' observation at or before anchor.
        Comparison = earliest label='actual' observation after anchor and
        within the bounded window. Other canonical labels (forecast / plan /
        target / estimated) are counted and exposed but NEVER consumed as
        observed reality (L27). Missing sides resolve to unknown with a
        reason - never zero, never interpolated (L21). The delta is derived
        arithmetic citing both source observations (Q3)."""
        metric = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == organization_id,
                    BusinessMetric.id == metric_id,
                )
            )
        ).scalar_one_or_none()
        if metric is None:
            return None

        if isinstance(anchor, datetime):
            anchor_dt = ensure_aware(anchor)
        else:
            try:
                anchor_dt = datetime.fromisoformat(
                    str(anchor).replace("Z", "+00:00")
                )
            except (TypeError, ValueError):
                return {"rejected": True, "reason": "anchor_not_parseable"}
        window = max(1, min(int(window_days or self.PERF_WINDOW_DAYS), 3650))
        cutoff = anchor_dt + timedelta(days=window)

        obs = list(
            (
                await db.execute(
                    select(BusinessMetricObservation).where(
                        BusinessMetricObservation.organization_id == organization_id,
                        BusinessMetricObservation.metric_id == metric_id,
                        BusinessMetricObservation.label == "actual",
                    ).order_by(
                        BusinessMetricObservation.observed_at.asc(),
                        BusinessMetricObservation.id.asc(),
                    ).limit(self.MAX_MEASUREMENT_OBSERVATIONS)
                )
            ).scalars().all()
        )

        excluded_counts: dict[str, int] = {}
        for label_value, count in (
            await db.execute(
                select(BusinessMetricObservation.label, func.count())
                .where(
                    BusinessMetricObservation.organization_id == organization_id,
                    BusinessMetricObservation.metric_id == metric_id,
                    BusinessMetricObservation.label != "actual",
                )
                .group_by(BusinessMetricObservation.label)
            )
        ).all():
            excluded_counts[str(label_value)] = int(count or 0)

        baseline = next(
            (o for o in reversed(obs) if ensure_aware(o.observed_at) <= anchor_dt),
            None,
        )
        comparison = next(
            (o for o in obs if anchor_dt < ensure_aware(o.observed_at) <= cutoff),
            None,
        )

        def _side(o: Any, missing_reason: str) -> dict[str, Any]:
            if o is None:
                return {
                    "observation_id": None, "value": None, "observed_at": None,
                    "label": None, "truth_level": "unknown",
                    "reason": missing_reason,
                }
            return {
                "observation_id": o.id, "value": o.value,
                "observed_at": _iso(o.observed_at), "label": o.label,
                "truth_level": "recorded",
            }

        baseline_block = _side(baseline, "no_actual_observation_at_or_before_anchor")
        comparison_block = _side(
            comparison, "no_actual_observation_after_anchor_within_window",
        )

        delta = None
        if baseline is not None and comparison is not None:
            base_value = float(baseline.value)
            raw = float(comparison.value) - base_value
            delta = {
                "value": round(raw, 6),
                "percentage_delta": (
                    round(raw / abs(base_value) * 100.0, 4) if base_value != 0.0
                    else None
                ),
                "percentage_unknown_reason": (
                    None if base_value != 0.0 else "baseline_value_zero"
                ),
                "direction": metric.direction,
                "delta_sign": (
                    "positive" if raw > 0 else ("negative" if raw < 0 else "zero")
                ),
                "truth_level": "derived",
                "basis": [baseline.id, comparison.id],
            }

        return {
            "metric": {
                "metric_id": metric.id, "key": metric.key, "name": metric.label,
                "unit": metric.unit, "direction": metric.direction,
            },
            "temporal_basis": {
                "anchor": _iso(anchor_dt),
                "baseline_as_of": _iso(anchor_dt),
                "comparison_as_of": _iso(cutoff),
                "window_days": window,
                "selection_rule": {
                    "baseline": "latest actual observation at or before anchor",
                    "comparison": (
                        "earliest actual observation after anchor within window"
                    ),
                },
            },
            "baseline": baseline_block,
            "comparison": comparison_block,
            "delta": delta,
            "excluded_observations": excluded_counts,
            "honesty": {
                "read_only": True,
                "no_interpolation": True,
                "unknown_is_not_zero": True,
                "forecast_excluded": True,
            },
        }

    async def decision_metric_measurement(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
        metric_key: Optional[str] = None, metric_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """One decision x one metric temporal measurement (Step 2).

        The anchor comes ONLY from canonical decision timing; the metric
        must be canonical too - an explicit id/key, or the single linked
        metric when exactly one BusinessPerformanceLink association exists.
        Ambiguity is rejected, never silently resolved."""
        row = await self._decision_row(
            db, organization_id=organization_id, decision_id=decision_id,
        )
        if row is None:
            return None
        anchor_dt, basis = self._decision_anchor_dt(row)

        metric_row: Optional[BusinessMetric] = None
        if metric_id:
            metric_row = (
                await db.execute(
                    select(BusinessMetric).where(
                        BusinessMetric.organization_id == organization_id,
                        BusinessMetric.id == metric_id,
                    )
                )
            ).scalar_one_or_none()
        elif metric_key:
            metric_row = (
                await db.execute(
                    select(BusinessMetric).where(
                        BusinessMetric.organization_id == organization_id,
                        BusinessMetric.key == metric_key,
                    ).order_by(BusinessMetric.id.asc()).limit(1)
                )
            ).scalars().first()
        else:
            linked = await self.decision_linked_metrics(
                db, organization_id=organization_id, decision_id=decision_id,
            )
            if len(linked) == 1:
                metric_row = (
                    await db.execute(
                        select(BusinessMetric).where(
                            BusinessMetric.organization_id == organization_id,
                            BusinessMetric.id == linked[0]["metric_id"],
                        )
                    )
                ).scalar_one_or_none()
            elif len(linked) > 1:
                return {
                    "decision_id": row.decision_id, "rejected": True,
                    "reason": "multiple_linked_metrics_require_explicit_metric",
                    "linked_metrics": linked,
                }
            if metric_row is None:
                return {
                    "decision_id": row.decision_id, "rejected": True,
                    "reason": (
                        "no_metric_specified_and_no_linked_metrics"
                        if not linked else "linked_metric_row_missing"
                    ),
                }

        if metric_row is None:
            return {
                "decision_id": row.decision_id, "rejected": True,
                "reason": "metric_not_found",
            }

        measurement = await self.metric_measurement_window(
            db, organization_id=organization_id, metric_id=metric_row.id,
            anchor=anchor_dt,
        )
        return {
            "decision_id": row.decision_id,
            "anchor_basis": basis,
            "measurement": measurement,
        }

    # ------------------------------------------------------- Slice 4H.6
    # Truth & attribution classification (Step 3). Deterministic READ-ONLY
    # classifiers over facts that already exist - they never create facts.
    # L20: recorded values surface verbatim. L21: numerical truth is exactly
    # recorded | derived | unknown (never estimated/filled/interpolated).
    # L22: attribution is exactly SUPPORTED | ASSOCIATED | UNKNOWN and
    # temporal sequence alone never upgrades to SUPPORTED. L23/L28: no
    # scores, no confidence numbers, no people scoring.

    ATTRIBUTION_LEVELS = ("SUPPORTED", "ASSOCIATED", "UNKNOWN")
    SUPPORTED_LINK_KINDS = ("evidence_indicates", "likely_contributor")
    ASSOCIATED_LINK_KINDS = ("linked_to", "strongly_associated_with")

    def classify_measurement_truth(
        self, measurement: Optional[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        """Attach canonical numerical-truth classification to a Step 2
        measurement-window result. Pure function - no I/O, no invention."""
        if measurement is None:
            return None
        baseline = measurement.get("baseline") or {}
        comparison = measurement.get("comparison") or {}
        delta = measurement.get("delta")
        metric = measurement.get("metric") or {}
        measured: dict[str, Any] = {
            "metric": {
                k: metric.get(k)
                for k in ("metric_id", "key", "name", "unit", "direction")
            },
            "value": None,
            "percentage_delta": None,
            "truth": "unknown",
            "reason": None,
            "basis": None,
            "baseline": baseline,
            "comparison": comparison,
            "temporal_basis": measurement.get("temporal_basis"),
            "excluded_observations": measurement.get("excluded_observations"),
            "honesty": {
                "read_only": True,
                "unknown_is_not_zero": True,
                "no_interpolation": True,
            },
        }
        if delta is not None:
            measured.update({
                "value": delta.get("value"),
                "percentage_delta": delta.get("percentage_delta"),
                "percentage_unknown_reason": delta.get("percentage_unknown_reason"),
                "delta_sign": delta.get("delta_sign"),
                "direction": delta.get("direction"),
                "truth": "derived",
                "basis": {
                    "baseline_observation_id": baseline.get("observation_id"),
                    "comparison_observation_id": comparison.get("observation_id"),
                },
            })
        else:
            missing = []
            if baseline.get("truth_level") != "recorded":
                missing.append("baseline")
            if comparison.get("truth_level") != "recorded":
                missing.append("comparison")
            measured["reason"] = {
                "baseline": "baseline_observation_missing",
                "comparison": "comparison_observation_missing",
                "baseline+comparison": "no_actual_observation_pair",
            }.get("+".join(missing), "insufficient_canonical_evidence")
        return measured

    async def classify_attribution(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
        metric_id: Optional[str] = None,
        has_temporal_context: bool = False,
    ) -> dict[str, Any]:
        """Classify the evidence linking outcomes to a decision (L22).

        Reads ONLY canonical relationships: CompanyCausalEdge hops touching
        the decision node and BusinessPerformanceLink rows targeting it.
        Evidence-kind links (evidence_indicates / likely_contributor) and
        causal edges support SUPPORTED; association-kind links or bare
        temporal co-presence yield at most ASSOCIATED; silence yields
        UNKNOWN. Chronology is never upgraded."""
        edges = list(
            (
                await db.execute(
                    select(CompanyCausalEdge).where(
                        CompanyCausalEdge.organization_id == organization_id,
                        or_(
                            and_(
                                CompanyCausalEdge.source_type == "decision",
                                CompanyCausalEdge.source_id == decision_id,
                            ),
                            and_(
                                CompanyCausalEdge.target_type == "decision",
                                CompanyCausalEdge.target_id == decision_id,
                            ),
                        ),
                    ).order_by(CompanyCausalEdge.created_at.desc())
                    .limit(MAX_CAUSAL_EDGES)
                )
            ).scalars().all()
        )
        basis: list[dict[str, Any]] = [
            {
                "type": "causal_edge", "id": e.id, "kind": e.kind,
                "confidence": e.confidence,
            }
            for e in edges
        ]

        link_stmt = (
            select(BusinessPerformanceLink).where(
                BusinessPerformanceLink.organization_id == organization_id,
                BusinessPerformanceLink.target_type == "decision",
                BusinessPerformanceLink.target_id == decision_id,
                BusinessPerformanceLink.entity_type == "business_metric",
            ).order_by(
                BusinessPerformanceLink.kind.asc(), BusinessPerformanceLink.id.asc(),
            ).limit(self.MAX_LINKED_METRICS)
        )
        if metric_id:
            link_stmt = link_stmt.where(BusinessPerformanceLink.entity_id == metric_id)
        links = list((await db.execute(link_stmt)).scalars().all())

        basis.extend(
            {
                "type": "business_performance_link", "id": l.id, "kind": l.kind,
                "weight": l.weight,
            }
            for l in links if l.kind in self.SUPPORTED_LINK_KINDS
        )
        if basis:
            return {"level": "SUPPORTED", "basis": basis, "reason": None}

        basis.extend(
            {
                "type": "business_performance_link", "id": l.id, "kind": l.kind,
                "weight": l.weight,
            }
            for l in links if l.kind in self.ASSOCIATED_LINK_KINDS
        )
        if basis:
            return {"level": "ASSOCIATED", "basis": basis, "reason": "association_link_only"}
        if has_temporal_context:
            return {
                "level": "ASSOCIATED",
                "basis": [{"type": "temporal_context"}],
                "reason": "temporal_context_only",
            }
        return {
            "level": "UNKNOWN", "basis": [],
            "reason": "no_canonical_attribution_basis",
        }

    async def decision_metric_classification(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
        metric_key: Optional[str] = None, metric_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Step 3 composition over the Step 2 helpers: the classified
        measurement (measured) and the honest attribution (attributed) for
        one decision x one metric. No scores, no confidence numbers."""
        measurement = await self.decision_metric_measurement(
            db, organization_id=organization_id, decision_id=decision_id,
            metric_key=metric_key, metric_id=metric_id,
        )
        if measurement is None:
            return None
        if measurement.get("rejected"):
            return measurement
        window = measurement.get("measurement") or {}
        measured = self.classify_measurement_truth(window)
        has_temporal_context = (
            (window.get("baseline") or {}).get("truth_level") == "recorded"
            or (window.get("comparison") or {}).get("truth_level") == "recorded"
        )
        attributed = await self.classify_attribution(
            db, organization_id=organization_id, decision_id=decision_id,
            metric_id=(window.get("metric") or {}).get("metric_id"),
            has_temporal_context=has_temporal_context,
        )
        return {
            "decision_id": measurement["decision_id"],
            "anchor_basis": measurement.get("anchor_basis"),
            "measured": measured,
            "attributed": attributed,
            "honesty": {
                "read_only": True,
                "no_scores": True,
                "no_confidence_number": True,
                "temporal_sequence_is_not_causality": True,
                "no_people_scoring": True,
            },
        }


    # ------------------------------------------------------- Slice 4H.6
    # Unified decision-performance assessment (Step 4). Composes the
    # immutable Step 2 temporal helpers and Step 3 truth/attribution
    # classifiers - plus the 4H.5 execution chain, consumed verbatim, never
    # duplicated - into ONE read-only intelligence object with the nine
    # ratified sections: decision / observed / measured / attributed /
    # assessed / unknown / temporal_basis / execution_chain / honesty.
    # It answers "what do we actually know about what happened after this
    # decision?" - NEVER "was this a good decision?". No scores, no
    # ranking, no forecasting, no recommendations, no people evaluation;
    # every field is provenance-backed or explicitly UNKNOWN.

    async def decision_performance_assessment(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
        access: Any = None,
    ) -> Optional[dict[str, Any]]:
        row = await self._decision_row(
            db, organization_id=organization_id, decision_id=decision_id,
        )
        if row is None:
            return None
        anchor_dt, anchor_basis = self._decision_anchor_dt(row)

        chain = await self.execution_chain(
            db, organization_id=organization_id, decision_id=decision_id,
            access=access,
        ) or {}
        # Determinism: the 4H.5 chain carries a volatile generated_at for its
        # own route; the unified assessment strips it so identical canonical
        # rows yield a byte-identical composition. The chain function itself
        # is untouched.
        chain.pop("generated_at", None)

        compare = getattr(row, "actual_outcome_compare", None) or None

        linked = await self.decision_linked_metrics(
            db, organization_id=organization_id, decision_id=decision_id,
        )
        measured_items: list[dict[str, Any]] = []
        unknown_items: list[dict[str, Any]] = []
        attribution_counts = {"SUPPORTED": 0, "ASSOCIATED": 0, "UNKNOWN": 0}
        derived_count = 0
        if not linked:
            unknown_items.append({
                "section": "measured", "subject": "*",
                "reason": "no_linked_canonical_metrics",
            })
        for m in linked[: self.MAX_LINKED_METRICS]:
            window = await self.metric_measurement_window(
                db, organization_id=organization_id, metric_id=m["metric_id"],
                anchor=anchor_dt,
            )
            classified = self.classify_measurement_truth(window)
            has_temporal_context = (
                (window or {}).get("baseline", {}).get("truth_level") == "recorded"
                or (window or {}).get("comparison", {}).get("truth_level") == "recorded"
            )
            attribution = await self.classify_attribution(
                db, organization_id=organization_id, decision_id=decision_id,
                metric_id=m["metric_id"], has_temporal_context=has_temporal_context,
            )
            measured_items.append({
                "metric": m,
                "measurement": classified,
                "attribution": attribution,
            })
            if classified["truth"] == "derived":
                derived_count += 1
            elif classified["truth"] == "unknown":
                unknown_items.append({
                    "section": "measured", "subject": m["key"],
                    "reason": classified.get("reason"),
                })
            attribution_counts[attribution["level"]] += 1
            if attribution["level"] == "UNKNOWN":
                unknown_items.append({
                    "section": "attributed", "subject": m["key"],
                    "reason": attribution.get("reason"),
                })

        outcome_recorded = bool(row.outcome_kind)
        if not outcome_recorded:
            unknown_items.append({
                "section": "observed", "subject": "outcome_record",
                "reason": "no_outcome_recorded",
            })

        return {
            "decision": {
                "decision_id": row.decision_id,
                "kind": row.kind,
                "title": row.title,
                "state": row.state,
                "approved_at": _iso(row.approved_at),
                "executed_at": _iso(row.executed_at),
                "expected_improvement": row.expected_improvement or None,
                "anchor_basis": anchor_basis,
            },
            "observed": {
                "outcome_record": {
                    "outcome_kind": row.outcome_kind or None,
                    "effectiveness": row.effectiveness,
                    "truth": "recorded" if outcome_recorded else "unknown",
                    "reason": None if outcome_recorded else "no_outcome_recorded",
                    "actual_outcome_compare": compare,
                    "evidence_refs_recorded": bool(row.outcome_evidence_json),
                    "reviewed_at": _iso(row.reviewed_at),
                },
                "action_outcomes": chain.get("outcomes", []),
                "execution_actions_count": len(chain.get("actions", [])),
                "evidence_events_count": len(chain.get("evidence", [])),
                "lesson": chain.get("lesson"),
            },
            "measured": {
                "metric_count": len(measured_items),
                "items": measured_items,
            },
            "attributed": {
                "per_metric": [
                    {"metric_key": i["metric"]["key"], **i["attribution"]}
                    for i in measured_items
                ],
                "summary": attribution_counts,
            },
            "assessed": {
                "basis": (
                    "counts of canonical evidence only - descriptive facts, "
                    "not a quality score"
                ),
                "outcome_recorded": outcome_recorded,
                "recorded_effectiveness": row.effectiveness,
                "linked_metrics_count": len(measured_items),
                "derived_measurements_count": derived_count,
                "unknown_measurements_count": sum(
                    1 for i in unknown_items if i["section"] == "measured"
                ),
                "attribution_summary": dict(attribution_counts),
            },
            "unknown": {
                "count": len(unknown_items),
                "items": unknown_items,
            },
            "temporal_basis": {
                "anchor": _iso(anchor_dt),
                "anchor_basis": anchor_basis,
                "per_measurement": (
                    "embedded in measured.items[].measurement.temporal_basis"
                ),
            },
            "execution_chain": chain,
            "honesty": {
                "advisory_only": True,
                "read_only": True,
                "no_scores": True,
                "no_ranking_or_winner": True,
                "not_a_quality_verdict": True,
                "no_forecasting": True,
                "no_recommendations": True,
                "no_learning": True,
                "no_people_scoring": True,
                "temporal_sequence_is_not_causality": True,
                "unknown_is_not_zero": True,
                "chain_consumed_not_duplicated": True,
                "deterministic_composition": True,
            },
        }


    # ------------------------------------------------------- Slice 4H.6
    # Outcome cohort / longitudinal read (Step 5). Historical patterns of
    # RECORD ONLY - composed entirely ON READ from canonical rows through
    # the Step 2-4 primitives (one unified assessment per bounded decision).
    # CompanyDecisionTrack remains prediction-history infrastructure and is
    # NOT touched, queried, or imitated here: no parallel history system.
    # Presents what the record shows; never recommends, ranks, forecasts,
    # scores, or learns (L23/L26/L27/L28). Every derived number cites its
    # canonical basis.

    MAX_COHORT_DECISIONS = 25

    async def decision_performance_cohort(
        self, db: AsyncSession, *, organization_id: str,
        kind: Optional[str] = None, state: Optional[str] = None,
    ) -> dict[str, Any]:
        stmt = select(CompanyDecision).where(
            CompanyDecision.organization_id == organization_id,
        )
        if kind:
            stmt = stmt.where(CompanyDecision.kind == kind)
        if state:
            stmt = stmt.where(CompanyDecision.state == state)
        rows = list(
            (
                await db.execute(
                    stmt.order_by(
                        CompanyDecision.created_at.asc(), CompanyDecision.id.asc(),
                    ).limit(self.MAX_COHORT_DECISIONS)
                )
            ).scalars().all()
        )

        OUTCOME_VOCAB = ("successful", "partial", "unsuccessful")
        by_kind = {k: 0 for k in OUTCOME_VOCAB}
        other_outcome_kinds: set[str] = set()
        effectiveness_values: list[tuple[str, float]] = []
        anchor_values: list[str] = []
        anchor_bases: dict[str, int] = {}
        decisions_summary: list[dict[str, Any]] = []
        unknown_reasons: dict[str, int] = {}
        attribution_totals = {"SUPPORTED": 0, "ASSOCIATED": 0, "UNKNOWN": 0}
        derived_total = 0
        unknown_meas_total = 0
        linked_metric_decision_count = 0

        for row in rows:
            assessment = await self.decision_performance_assessment(
                db, organization_id=organization_id,
                decision_id=row.decision_id,
            )
            if assessment is None:
                continue
            okind = row.outcome_kind
            if okind in by_kind:
                by_kind[okind] += 1
            elif okind:
                other_outcome_kinds.add(okind)
            if row.effectiveness is not None:
                effectiveness_values.append(
                    (row.decision_id, float(row.effectiveness))
                )
            anchor_dt, anchor_basis = self._decision_anchor_dt(row)
            anchor_iso = _iso(anchor_dt)
            if anchor_iso:
                anchor_values.append(anchor_iso)
            anchor_bases[anchor_basis] = anchor_bases.get(anchor_basis, 0) + 1
            decisions_summary.append({
                "decision_id": row.decision_id,
                "kind": row.kind,
                "state": row.state,
                "outcome_kind": okind or None,
                "effectiveness": row.effectiveness,
                "anchor": anchor_iso,
                "anchor_basis": anchor_basis,
            })
            assessed = assessment["assessed"]
            derived_total += int(assessed.get("derived_measurements_count") or 0)
            unknown_meas_total += int(
                assessed.get("unknown_measurements_count") or 0
            )
            if int(assessed.get("linked_metrics_count") or 0) > 0:
                linked_metric_decision_count += 1
            for lvl, cnt in (
                assessment["attributed"].get("summary", {}).items()
            ):
                if lvl in attribution_totals:
                    attribution_totals[lvl] += int(cnt or 0)
            for item in assessment["unknown"].get("items", []):
                reason = item.get("reason") or "unspecified"
                unknown_reasons[reason] = unknown_reasons.get(reason, 0) + 1

        with_outcome = sum(by_kind.values())
        if len(effectiveness_values) >= 2:
            effectiveness_aggregate = {
                "value": round(
                    sum(v for _, v in effectiveness_values)
                    / len(effectiveness_values), 6,
                ),
                "truth_level": "derived",
                "method": (
                    "arithmetic mean of recorded decision effectiveness values"
                ),
                "count": len(effectiveness_values),
                "basis": [d for d, _ in effectiveness_values],
                "reason": None,
            }
        elif len(effectiveness_values) == 1:
            effectiveness_aggregate = {
                "value": effectiveness_values[0][1],
                "truth_level": "recorded",
                "method": None,
                "count": 1,
                "basis": [effectiveness_values[0][0]],
                "reason": None,
            }
        else:
            effectiveness_aggregate = {
                "value": None,
                "truth_level": "unknown",
                "method": None,
                "count": 0,
                "basis": [],
                "reason": "no_recorded_effectiveness_values",
            }

        return {
            "cohort": {
                "filters": {"kind": kind or None, "state": state or None},
                "decision_count": len(rows),
                "max_decisions": self.MAX_COHORT_DECISIONS,
                "bounded": len(rows) >= self.MAX_COHORT_DECISIONS,
                "derived_on_read": True,
            },
            "decisions": decisions_summary,
            "recorded_outcomes": {
                "truth_level": "recorded",
                "by_kind": by_kind,
                "other_recorded_kinds": sorted(other_outcome_kinds),
                "with_outcome_record": with_outcome,
                "without_outcome_record": len(rows) - with_outcome,
            },
            "effectiveness_aggregate": effectiveness_aggregate,
            "measurement_coverage": {
                "decisions_with_linked_metrics": linked_metric_decision_count,
                "derived_measurement_items": derived_total,
                "unknown_measurement_items": unknown_meas_total,
            },
            "attribution_summary": attribution_totals,
            "temporal_coverage": {
                "earliest_anchor": min(anchor_values) if anchor_values else None,
                "latest_anchor": max(anchor_values) if anchor_values else None,
                "anchor_bases": anchor_bases,
            },
            "unknown_aggregate": {
                "total_items": sum(unknown_reasons.values()),
                "reasons": dict(sorted(unknown_reasons.items())),
            },
            "honesty": {
                "advisory_only": True,
                "read_only": True,
                "patterns_not_recommendations": True,
                "no_learning": True,
                "no_forecasting": True,
                "no_ranking_or_winner": True,
                "no_scores": True,
                "no_people_scoring": True,
                "compare_not_rank": True,
                "track_infrastructure_untouched": True,
                "deterministic_composition": True,
            },
        }


    # ------------------------------------------------------- Slice 4H.6
    # Comparative read (Step 6). Side-by-side inspection of a bounded set
    # of decisions, composed ENTIRELY from Step 4 assessments plus Step 5
    # longitudinal context - zero duplicated logic. COMPARE != RANK (L23):
    # evidence, measurements, outcomes, attribution, temporal bases and
    # unknowns are presented neutrally; there is NO winner, rank, score,
    # probability, recommendation, forecast, or person evaluation field -
    # and none may be added without a contract amendment.

    MAX_COMPARE_DECISIONS = 5

    async def decision_performance_comparison(
        self, db: AsyncSession, *, organization_id: str,
        decision_ids: list[str],
    ) -> dict[str, Any]:
        unique = list(dict.fromkeys(decision_ids or []))
        if len(unique) < 2:
            return {
                "rejected": True,
                "reason": "at_least_two_unique_decisions_required",
                "max_decisions": self.MAX_COMPARE_DECISIONS,
            }
        if len(unique) > self.MAX_COMPARE_DECISIONS:
            return {
                "rejected": True,
                "reason": "too_many_decisions",
                "max_decisions": self.MAX_COMPARE_DECISIONS,
                "received": len(unique),
            }

        assessments: dict[str, dict[str, Any]] = {}
        not_found: list[str] = []
        for did in unique:
            assessment = await self.decision_performance_assessment(
                db, organization_id=organization_id, decision_id=did,
            )
            if assessment is None:
                not_found.append(did)
            else:
                assessments[did] = assessment
        found = [d for d in unique if d in assessments]
        if len(found) < 2:
            return {
                "rejected": True,
                "reason": "fewer_than_two_resolvable_decisions",
                "not_found": not_found,
            }

        columns: list[dict[str, Any]] = []
        for did in found:
            a = assessments[did]
            obs = a["observed"]
            assessed = a["assessed"]
            chain = a["execution_chain"]
            unknown_reasons: dict[str, int] = {}
            for item in a["unknown"]["items"]:
                r = item.get("reason") or "unspecified"
                unknown_reasons[r] = unknown_reasons.get(r, 0) + 1
            columns.append({
                "decision_id": did,
                "title": a["decision"]["title"],
                "kind": a["decision"]["kind"],
                "state": a["decision"]["state"],
                "anchor": a["temporal_basis"]["anchor"],
                "anchor_basis": a["temporal_basis"]["anchor_basis"],
                "outcome": {
                    "outcome_kind": obs["outcome_record"]["outcome_kind"],
                    "truth": obs["outcome_record"]["truth"],
                },
                "recorded_effectiveness":
                    assessed.get("recorded_effectiveness"),
                "execution": {
                    "actions": int(obs.get("execution_actions_count") or 0),
                    "evidence_events": int(
                        obs.get("evidence_events_count") or 0),
                    "artifacts": len(chain.get("artifacts", [])),
                    "outcomes": len(obs.get("action_outcomes", [])),
                },
                "measured": {
                    "linked_metrics": int(
                        assessed.get("linked_metrics_count") or 0),
                    "derived_measurements": int(
                        assessed.get("derived_measurements_count") or 0),
                    "unknown_measurement_items": int(
                        assessed.get("unknown_measurements_count") or 0),
                },
                "attribution_summary": dict(
                    assessed.get("attribution_summary", {})
                ),
                "unknowns": {
                    "count": int(a["unknown"].get("count") or 0),
                    "reasons": dict(sorted(unknown_reasons.items())),
                },
            })

        def _with_without(key_fn: Any) -> dict[str, list[str]]:
            present = [d for d in found if key_fn(assessments[d])]
            return {
                "with": present,
                "without": [d for d in found if d not in present],
            }

        contrasts = {
            "outcome_record_present": _with_without(
                lambda a: bool(a["assessed"].get("outcome_recorded")),
            ),
            "derived_measurement_present": _with_without(
                lambda a: int(
                    a["assessed"].get("derived_measurements_count") or 0
                ) > 0,
            ),
            "supported_attribution_present": _with_without(
                lambda a: int(
                    a["assessed"].get("attribution_summary", {}).get(
                        "SUPPORTED", 0)
                ) > 0,
            ),
        }

        longitudinal: dict[str, Any] = {}
        for k in sorted({assessments[d]["decision"]["kind"] for d in found}):
            cohort = await self.decision_performance_cohort(
                db, organization_id=organization_id, kind=k,
            )
            longitudinal[k] = {
                "decision_count": cohort["cohort"]["decision_count"],
                "recorded_outcomes_by_kind":
                    cohort["recorded_outcomes"]["by_kind"],
                "effectiveness_aggregate": cohort["effectiveness_aggregate"],
                "attribution_summary": cohort["attribution_summary"],
            }

        return {
            "comparison": {
                "decision_ids": found,
                "requested": len(unique),
                "compared": len(found),
                "not_found": not_found,
                "max_decisions": self.MAX_COMPARE_DECISIONS,
                "compare_not_rank": True,
                "derived_on_read": True,
            },
            "columns": columns,
            "contrasts": contrasts,
            "longitudinal_context": longitudinal,
            "assessments": assessments,
            "honesty": {
                "advisory_only": True,
                "read_only": True,
                "compare_not_rank": True,
                "no_winner_field": True,
                "no_ranking_or_winner": True,
                "no_scores": True,
                "no_probability": True,
                "no_recommendations": True,
                "no_forecasting": True,
                "no_learning": True,
                "no_people_scoring": True,
                "chronology_is_not_causality": True,
                "deterministic_composition": True,
            },
        }


company_operating_engine = CompanyOperatingEngine()
