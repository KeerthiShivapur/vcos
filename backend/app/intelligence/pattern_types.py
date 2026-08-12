"""Slice 4D.4 — universal organizational pattern type registry.

The canonical rule map: which pattern types exist, which events can evidence
them, and the thresholds that decide when an observation becomes a pattern.

Design laws:

- **Evidence first**: a rule only fires when a significant operating event
  arrives. ``events`` lists the change-driven event names that feed the rule;
  a rule with no events is *dormant* — registered for the taxonomy, never
  auto-created without evidence. One event is never a pattern.
- **Only create with sufficient evidence**: ``min_occurrences`` gates
  creation (2 observed occurrences by default) — a single event only updates
  an existing pattern's context, it never invents one.
- **Thresholds are configurable, not hardcoded**: every lifecycle / confidence
  threshold lives in this module (and the pipeline reads them from here), so
  the behaviour is tunable and testable.
- **No parallel architecture**: this registry only classifies evidence; the
  pipeline, models and API are the canonical 4D.4 surface.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Thresholds (configurable, tested in test_pattern_lifecycle.py)
# ---------------------------------------------------------------------------

# Lifecycle thresholds (occurrence counts).
CANDIDATE_MIN_OCCURRENCES = 2
EMERGING_MIN_OCCURRENCES = 3
CONFIRMED_MIN_OCCURRENCES = 4
PERSISTENT_MIN_OCCURRENCES = 6
# A pattern is persistent when it keeps recurring across windows: its observed
# span must cover at least this multiple of its observation window.
PERSISTENT_WINDOW_MULTIPLIER = 2
# Fading: no new occurrence for this many days (from confirmed/persistent).
FADING_AFTER_DAYS = 14
# Resolved: no new occurrence for this many days (from fading/confirmed).
RESOLVED_AFTER_DAYS = 30

# Confidence bounds and components (sums to <= 1.0, capped at CONFIDENCE_CAP).
CONFIDENCE_FLOOR = 0.3
CONFIDENCE_CAP = 0.95
CONFIDENCE_BASE = 0.35          # an observed pattern starts at this baseline
CONFIDENCE_OCCURRENCES_MAX = 8  # occurrence accumulation saturates here
CONFIDENCE_OCCURRENCES = 0.25   # share driven by occurrence count
CONFIDENCE_QUALITY = 0.10       # evidence quality (entity context present)
CONFIDENCE_TEMPORAL = 0.10      # temporal regularity (consistent intervals)
CONFIDENCE_SUPPORT = 0.10       # graph edges + supporting memories
CONFIDENCE_SEMANTIC = 0.05      # semantic similarity to supporting memories

# Evidence bounds — every collector is capped (no unbounded reads).
MAX_EVIDENCE = 24
MAX_SUPPORTING = 12
MAX_SUPPORTING_EVENTS = 40
MAX_MEMORY_CANDIDATES = 20
MAX_GRAPH_CANDIDATES = 20
MAX_SEMANTIC_CANDIDATES = 8

# Default observation window for a pattern (days).
DEFAULT_WINDOW_DAYS = 30

# ---------------------------------------------------------------------------
# Confidence labels (mirrors the directive's taxonomy).
# ---------------------------------------------------------------------------


def confidence_label(confidence: float) -> str:
    if confidence >= 0.75:
        return "Observed"
    if confidence >= 0.6:
        return "Strongly supported"
    if confidence >= 0.4:
        return "Emerging"
    return "Weak signal"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Rule shape:
#   family: execution | decision | governance | communication | knowledge | organization
#   description: why VCOS believes this is a pattern (explainability text)
#   events: event names that can evidence the pattern (change-driven)
#   anchor: entity the pattern is anchored to (project | task | employee |
#           decision | milestone | conversation)
#   employee_source: which payload key provides the employee anchor when
#                    anchor == "employee" (assignee | requester | approver |
#                    grantor | owner)
#   key: fn(ctx, payload) -> natural key suffix (idempotent upsert key)
#   title / detail: human-readable rendering
#   min_occurrences: minimum observed occurrences before the pattern exists
#   window_days: observation window the pattern tracks

Rule = dict[str, Any]

PATTERN_TYPES: dict[str, Rule] = {
    # ------------------------------------------------------------------ execution
    "repeated_delay": {
        "family": "execution",
        "description": (
            "Work repeatedly falls behind: tasks in the same scope keep getting "
            "blocked or transitioned back to incomplete states."
        ),
        "events": frozenset({"task.transitioned"}),
        "anchor": "project",
        "condition": lambda ctx, payload, event_name: bool(
            ctx.get("task") and ctx["task"].get("status") == "blocked"
        ),
        "key": lambda ctx, payload: (
            f"project:{ctx['project']['id']}" if ctx.get("project")
            else (f"employee:{ctx['employee']['id']}" if ctx.get("employee") else None)
        ),
        "title": lambda ctx, payload: (
            f"Repeated delays: {ctx['project']['name']}" if ctx.get("project")
            else (f"Repeated delays around {ctx['employee']['name']}" if ctx.get("employee") else "Repeated delays")
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} delay-related events were observed in "
            f"'{ctx['project']['name'] if ctx.get('project') else 'this scope'}'."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "repeated_blocker": {
        "family": "execution",
        "description": (
            "The same work keeps getting blocked by unsatisfied dependencies — "
            "a dependency is blocking delivery more than once."
        ),
        "events": frozenset({"task.blocked"}),
        "anchor": "project",
        "condition": lambda ctx, payload, event_name: bool(ctx.get("task") and ctx["task"].get("has_deps")),
        "key": lambda ctx, payload: (
            f"project:{ctx['project']['id']}:blocker" if ctx.get("project")
            else (f"employee:{ctx['employee']['id']}:blocker" if ctx.get("employee") else None)
        ),
        "title": lambda ctx, payload: (
            f"Repeated blockers in {ctx['project']['name']}" if ctx.get("project")
            else "Repeated blockers"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} tasks in this scope were blocked by an unsatisfied dependency."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "dependency_failure": {
        "family": "execution",
        "description": (
            "A task keeps failing because its dependencies are not ready — "
            "the dependency chain itself is the recurring failure."
        ),
        "events": frozenset({"task.blocked"}),
        "anchor": "task",
        "condition": lambda ctx, payload, event_name: bool(
            ctx.get("task") and ctx["task"].get("unsatisfied")
        ),
        "key": lambda ctx, payload: f"task:{ctx['task']['id']}",
        "title": lambda ctx, payload: (
            f"Dependency failure: {ctx['task']['title']}" if ctx.get("task") else "Dependency failure"
        ),
        "detail": lambda ctx, payload, count: (
            f"'{ctx['task']['title'] if ctx.get('task') else 'this task'}' has been blocked "
            f"by unsatisfied dependencies {count} times."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "handoff_failure": {
        "family": "execution",
        "description": (
            "Work handed off between owners keeps bouncing back — status "
            "transitions suggest the handoff was incomplete or wrong."
        ),
        "events": frozenset({"task.transitioned"}),
        "anchor": "project",
        "condition": lambda ctx, payload, event_name: bool(
            ctx.get("task") and ctx["task"].get("status") in ("todo", "in_progress", "review")
        ),
        "key": lambda ctx, payload: (
            f"project:{ctx['project']['id']}:handoff" if ctx.get("project")
            else (f"employee:{ctx['employee']['id']}:handoff" if ctx.get("employee") else None)
        ),
        "title": lambda ctx, payload: (
            f"Handoff churn in {ctx['project']['name']}" if ctx.get("project") else "Handoff churn"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} handoff transitions were observed in this scope."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "ownership_change_delay": {
        "family": "execution",
        "description": (
            "The same owner keeps being reassigned work — ownership changes "
            "repeat and delay delivery."
        ),
        # Dormant: assignee changes are not observable from the event payload
        # (task.updated carries only the current assignee), so this rule is
        # registered but never fed until the event contract grows.
        "events": frozenset(),
        "anchor": "employee",
        "employee_source": "assignee",
        "condition": lambda ctx, payload, event_name: bool(ctx.get("employee")),
        "key": lambda ctx, payload: f"employee:{ctx['employee']['id']}:ownership",
        "title": lambda ctx, payload: (
            f"Ownership changes around {ctx['employee']['name']}" if ctx.get("employee") else "Ownership churn"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} ownership-changing events were observed for this person."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "milestone_slippage": {
        "family": "execution",
        "description": (
            "Work linked to the same milestone keeps slipping past its plan."
        ),
        "events": frozenset({"task.blocked"}),
        "anchor": "milestone",
        "key": lambda ctx, payload: (
            f"milestone:{ctx['milestone']['id']}" if ctx.get("milestone") else None
        ),
        "title": lambda ctx, payload: (
            f"Milestone slippage: {ctx['milestone']['name']}" if ctx.get("milestone") else "Milestone slippage"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} slippage signals were observed around this milestone."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    # ------------------------------------------------------------------- decision
    "decision_reversal": {
        "family": "decision",
        "description": (
            "Decisions in the same scope keep being reversed after they are made."
        ),
        "events": frozenset({"decision.updated"}),
        "anchor": "project",
        "key": lambda ctx, payload: (
            f"project:{ctx['project']['id']}:decision_reversal" if ctx.get("project")
            else (f"employee:{ctx['employee']['id']}:decision_reversal" if ctx.get("employee") else None)
        ),
        "title": lambda ctx, payload: (
            f"Decision reversals in {ctx['project']['name']}" if ctx.get("project") else "Decision reversals"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} decision updates were observed in this scope."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "decision_delay": {
        "family": "decision",
        "description": (
            "Decisions keep getting stuck: approvals in the same scope are "
            "rejected and decisions stall."
        ),
        "events": frozenset({"approval.rejected"}),
        "anchor": "project",
        "key": lambda ctx, payload: (
            f"project:{ctx['project']['id']}:decision_delay" if ctx.get("project")
            else (f"employee:{ctx['employee']['id']}:decision_delay" if ctx.get("employee") else None)
        ),
        "title": lambda ctx, payload: (
            f"Decision delays in {ctx['project']['name']}" if ctx.get("project") else "Decision delays"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} rejected approvals were observed in this scope."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "decision_without_execution": {
        "family": "decision",
        "description": (
            "Decisions are recorded but never executed — intent without follow-up."
        ),
        "events": frozenset({"decision.made"}),
        "anchor": "project",
        "condition": lambda ctx, payload, event_name: not (ctx.get("decision") and ctx["decision"].get("executed")),
        "key": lambda ctx, payload: (
            f"project:{ctx['project']['id']}:no_execution" if ctx.get("project")
            else (f"employee:{ctx['employee']['id']}:no_execution" if ctx.get("employee") else None)
        ),
        "title": lambda ctx, payload: (
            f"Decisions without execution in {ctx['project']['name']}" if ctx.get("project") else "Decisions without execution"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} decisions in this scope have no recorded execution follow-up."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "repeated_approval_dependency": {
        "family": "decision",
        "description": (
            "The same person keeps requesting approvals — approval becomes a "
            "recurring dependency for their work."
        ),
        "events": frozenset({"approval.requested"}),
        "anchor": "employee",
        "employee_source": "requester",
        "key": lambda ctx, payload: f"employee:{ctx['employee']['id']}:approval_dependency",
        "title": lambda ctx, payload: (
            f"Repeated approval dependency: {ctx['employee']['name']}" if ctx.get("employee") else "Repeated approval dependency"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} approval requests were observed from this person."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    # ---------------------------------------------------------------- governance
    "approval_bottleneck": {
        "family": "governance",
        "description": (
            "One approver keeps accumulating pending approvals — a recurring "
            "bottleneck in the governance flow."
        ),
        "events": frozenset({"approval.requested"}),
        "anchor": "employee",
        "employee_source": "approver",
        "key": lambda ctx, payload: f"employee:{ctx['employee']['id']}:approval_bottleneck",
        "title": lambda ctx, payload: (
            f"Approval bottleneck: {ctx['employee']['name']}" if ctx.get("employee") else "Approval bottleneck"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} approval requests were routed to this approver."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "governance_friction": {
        "family": "governance",
        "description": (
            "Work in the same scope keeps being rejected by governance — "
            "policy friction repeats."
        ),
        "events": frozenset({"approval.rejected"}),
        "anchor": "project",
        "key": lambda ctx, payload: (
            f"project:{ctx['project']['id']}:governance_friction" if ctx.get("project")
            else (f"employee:{ctx['employee']['id']}:governance_friction" if ctx.get("employee") else None)
        ),
        "title": lambda ctx, payload: (
            f"Governance friction in {ctx['project']['name']}" if ctx.get("project") else "Governance friction"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} rejections were observed in this scope."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "scope_assignment_churn": {
        "family": "governance",
        "description": (
            "Access scopes keep being assigned and removed for the same person "
            "— governance membership churns."
        ),
        "events": frozenset({"governance.assignment.created", "governance.assignment.removed"}),
        "anchor": "employee",
        "employee_source": "grantor",
        "key": lambda ctx, payload: f"employee:{ctx['employee']['id']}:scope_churn",
        "title": lambda ctx, payload: (
            f"Scope assignment churn: {ctx['employee']['name']}" if ctx.get("employee") else "Scope assignment churn"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} scope assignment changes were observed for this person."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "delegation_dependency": {
        "family": "governance",
        "description": (
            "Authority keeps being delegated by the same person — recurring "
            "delegation dependency."
        ),
        "events": frozenset({"governance.delegation.created", "governance.delegation.revoked"}),
        "anchor": "employee",
        "employee_source": "grantor",
        "key": lambda ctx, payload: f"employee:{ctx['employee']['id']}:delegation",
        "title": lambda ctx, payload: (
            f"Delegation dependency: {ctx['employee']['name']}" if ctx.get("employee") else "Delegation dependency"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} delegation events were observed for this person."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    # -------------------------------------------------------------- communication
    "communication_breakdown": {
        "family": "communication",
        "description": (
            "Work keeps getting blocked without a blocking dependency — manual "
            "blocks signal a recurring coordination gap between people."
        ),
        "events": frozenset({"task.blocked"}),
        "anchor": "project",
        "condition": lambda ctx, payload, event_name: bool(ctx.get("task") and not ctx["task"].get("has_deps")),
        "key": lambda ctx, payload: (
            f"project:{ctx['project']['id']}:communication" if ctx.get("project")
            else (f"employee:{ctx['employee']['id']}:communication" if ctx.get("employee") else None)
        ),
        "title": lambda ctx, payload: (
            f"Communication breakdown in {ctx['project']['name']}" if ctx.get("project") else "Communication breakdown"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} dependency-free blocks were observed in this scope."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "repeated_unresolved_discussion": {
        "family": "communication",
        "description": (
            "The same blocked task keeps attracting comments without resolution "
            "— discussion repeats while the problem stays open."
        ),
        "events": frozenset({"task.commented"}),
        "anchor": "task",
        "condition": lambda ctx, payload, event_name: bool(ctx.get("task") and ctx["task"].get("status") == "blocked"),
        "key": lambda ctx, payload: f"task:{ctx['task']['id']}:discussion",
        "title": lambda ctx, payload: (
            f"Unresolved discussion: {ctx['task']['title']}" if ctx.get("task") else "Unresolved discussion"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} comments were left on this blocked task."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    # ---------------------------------------------------------------- knowledge
    # Dormant rules: registered in the taxonomy but never auto-created until a
    # change-driven evidence source exists. "Only create with sufficient
    # evidence" — no full-scan substitutes are allowed.
    "knowledge_gap": {
        "family": "knowledge",
        "description": (
            "A skill or topic has no covering knowledge while the organization "
            "keeps depending on it. (Dormant: awaiting a change-driven evidence "
            "source — never created by scanning.)"
        ),
        "events": frozenset(),
        "anchor": "project",
        "key": lambda ctx, payload: None,
        "title": lambda ctx, payload: "Knowledge gap",
        "detail": lambda ctx, payload, count: "No evidence observed yet.",
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "repeated_document_lookup": {
        "family": "knowledge",
        "description": (
            "The same information keeps being looked up — knowledge exists but "
            "is not findable. (Dormant: awaiting a change-driven evidence source.)"
        ),
        "events": frozenset(),
        "anchor": "project",
        "key": lambda ctx, payload: None,
        "title": lambda ctx, payload: "Repeated document lookup",
        "detail": lambda ctx, payload, count: "No evidence observed yet.",
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "missing_knowledge_dependency": {
        "family": "knowledge",
        "description": (
            "Delivery keeps depending on knowledge that does not exist yet. "
            "(Dormant: awaiting a change-driven evidence source.)"
        ),
        "events": frozenset(),
        "anchor": "project",
        "key": lambda ctx, payload: None,
        "title": lambda ctx, payload: "Missing knowledge dependency",
        "detail": lambda ctx, payload, count: "No evidence observed yet.",
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    # -------------------------------------------------------------- organization
    "ownership_ambiguity": {
        "family": "organization",
        "description": (
            "People keep moving between teams and departments — ownership and "
            "reporting lines churn."
        ),
        "events": frozenset({"employee.transferred"}),
        "anchor": "employee",
        "employee_source": "owner",
        "key": lambda ctx, payload: f"employee:{ctx['employee']['id']}:ownership_ambiguity",
        "title": lambda ctx, payload: (
            f"Ownership ambiguity: {ctx['employee']['name']}" if ctx.get("employee") else "Ownership ambiguity"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} transfers were observed for this person."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "repeated_cross_team_bottleneck": {
        "family": "organization",
        "description": (
            "The same person keeps escalating across teams — a recurring "
            "cross-team bottleneck."
        ),
        "events": frozenset({"ticket.escalated"}),
        "anchor": "employee",
        "employee_source": "assignee",
        "key": lambda ctx, payload: f"employee:{ctx['employee']['id']}:cross_team",
        "title": lambda ctx, payload: (
            f"Cross-team bottleneck: {ctx['employee']['name']}" if ctx.get("employee") else "Cross-team bottleneck"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} escalations were observed involving this person."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "collaboration_bottleneck": {
        "family": "organization",
        "description": (
            "The same project keeps pausing — collaboration stalls recur."
        ),
        "events": frozenset({"project.paused"}),
        "anchor": "project",
        "key": lambda ctx, payload: (
            f"project:{ctx['project']['id']}:collaboration" if ctx.get("project") else None
        ),
        "title": lambda ctx, payload: (
            f"Collaboration bottleneck: {ctx['project']['name']}" if ctx.get("project") else "Collaboration bottleneck"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} pauses were observed for this project."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
    "concentration_risk": {
        "family": "organization",
        "description": (
            "Too many decisions flow through the same person — a recurring "
            "concentration risk."
        ),
        "events": frozenset({"approval.approved", "approval.rejected"}),
        "anchor": "employee",
        "employee_source": "approver",
        "key": lambda ctx, payload: f"employee:{ctx['employee']['id']}:concentration",
        "title": lambda ctx, payload: (
            f"Concentration risk: {ctx['employee']['name']}" if ctx.get("employee") else "Concentration risk"
        ),
        "detail": lambda ctx, payload, count: (
            f"{count} approvals were decided by this person."
        ),
        "min_occurrences": CANDIDATE_MIN_OCCURRENCES,
        "window_days": DEFAULT_WINDOW_DAYS,
    },
}


def rule_for(pattern_type: str) -> Optional[Rule]:
    return PATTERN_TYPES.get(pattern_type)


def events_to_pattern_types(event_name: str) -> list[tuple[str, Rule]]:
    """Rules that can be evidenced by one event (bounded, registry lookup)."""
    return [
        (pattern_type, rule)
        for pattern_type, rule in PATTERN_TYPES.items()
        if event_name in rule["events"]
    ]


def lifecycle_thresholds() -> dict[str, int]:
    return {
        "candidate": CANDIDATE_MIN_OCCURRENCES,
        "emerging": EMERGING_MIN_OCCURRENCES,
        "confirmed": CONFIRMED_MIN_OCCURRENCES,
        "persistent": PERSISTENT_MIN_OCCURRENCES,
    }


def confidence_thresholds() -> dict[str, float]:
    return {
        "floor": CONFIDENCE_FLOOR,
        "cap": CONFIDENCE_CAP,
        "label_observed": 0.75,
        "label_strong": 0.6,
        "label_emerging": 0.4,
    }
