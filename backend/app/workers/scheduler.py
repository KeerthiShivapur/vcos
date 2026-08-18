"""Background worker scheduler (Phase 3 Module 11).

Runs the standalone intelligence workers as asyncio background tasks inside the
API process. Each worker follows the same contract:

    run_once() -> int   # do one pass, return items processed

The scheduler imports the module once, then loops run_once() with a per-worker
interval, catching and logging per-iteration failures so one worker's error
never takes down the rest.
"""

import asyncio
import importlib
import logging
from typing import Optional

logger = logging.getLogger("vcos.workers.scheduler")

# (worker name, interval seconds)
# name maps to app.workers.<name>_worker
WORKER_REGISTRY: list[tuple[str, int]] = [
    ("notification", 120),  # deliver queued notifications
    ("presence", 300),      # expire presence + idle flags
    ("meeting", 300),       # start/end meetings on schedule
    ("collaboration", 300),  # meeting session lifecycle + live presence
    ("meeting_intel", 300),  # AI summaries, action items, attendance for ended meetings
    ("reminder", 900),      # due-soon nudges
    ("dependency", 600),    # block tasks whose deps are incomplete
    ("workload", 3600),     # weekly workload snapshots
    ("risk", 3600),         # auto-detect risks from delays
    ("ai", 3600),           # background AI summaries
    ("expertise", 86400),   # expertise score refreshes
    ("analytics", 86400),   # analytics materialization
    ("organization", 86400),  # org health recompute
    ("recommendation", 86400),  # recommendation refreshes
    ("graph", 86400),       # organization graph validation
    ("audit", 86400),       # audit log maintenance
    ("indexing", 1800),     # knowledge search index repair
    ("duplicate", 86400),   # knowledge duplicate detection
    ("quality", 43200),     # knowledge quality re-scoring
    ("ai_insights", 1800),  # proactive org insights (overload, meeting load, overdue)
    ("ai_predictions", 3600),  # delay/burnout/overload/attrition predictions
    ("ai_learning", 43200),  # fold feedback corrections into durable memory
    ("exec_health", 3600),  # Phase 8: company health + strategic risks + recommendations
    ("exec_prediction", 3600),  # Phase 8: executive predictive analytics
    ("exec_analytics", 86400),  # Phase 8: trend metrics materialization
    ("exec_reporting", 86400),  # Phase 8: weekly/monthly executive reports
    # Phase 9 — Background Intelligence & Autonomous Organization
    ("event", 15),              # dispatch persisted events to handlers (expertise, graph, learning)
    ("graph_updates", 300),     # rebuild structural org-graph edges
    ("search_insight", 1800),   # aggregate search behavior into insights
    ("knowledge_intel", 3600),  # outdated/duplicate/gap/unused knowledge detection
    ("collab_intel", 3600),     # collaboration metrics + silo detection
    ("burnout", 3600),          # workload-pattern detection
    ("expertise_evolve", 3600), # expertise decay + aggregate refresh
    ("workflow_intel", 3600),   # approval bottlenecks + automation chances
    ("pattern", 120),            # Slice 4D.4: change-driven pattern evaluation
    ("insight", 120),            # Slice 4D.5: change-driven universal insight composition
    ("learning", 43200),        # lessons learned + AI memory growth
    ("insights", 86400),        # autonomous daily briefs + notifications
    ("recommendation_feed", 86400),  # personalized recommendation feeds
    # Phase 10 — Learning & Growth Operating System
    ("skill", 3600),            # skill graph snapshots + gap re-detection
    ("certification", 86400),   # expire credentials + expiring-now visibility
    ("mentor", 86400),          # stalled mentorship detection
    ("assessment", 3600),       # auto-finalize stale quiz attempts + expire abandoned ones
    # Phase 11 — HR & Workforce Operations
    ("attendance", 3600),       # flag missing clock-outs / attendance anomalies
    ("performance", 86400),     # cycle status transitions + overdue review hygiene
    ("hiring", 86400),          # expire stale offers + close filled jobs
    ("compliance", 86400),      # refresh document/training expiry posture
    ("wellbeing", 3600),        # recompute pattern-based wellbeing risk levels
    ("workforce", 86400),       # compute daily workforce snapshots
    # Phase 12 — Customers, CRM & External Relationships (CROS)
    ("customer_health", 3600),  # recompute customer health + renewal probability
    ("renewal", 21600),         # contract expiry hygiene + renewal nudges
    ("support", 3600),          # SLA breach auto-escalation
    ("relationship", 3600),     # rebuild customer edges in the organization graph
    # Phase 13 — Finance & Business Operations
    ("budget", 3600),           # refresh budget usage + flag overruns
    ("forecasting", 43200),     # regenerate financial forecasts twice a day
    ("reconciliation", 21600),  # overdue invoices + financial risk scan
    ("finance_analytics", 43200),  # materialize monthly financial metrics
    ("optimization", 86400),    # cost-savings signals from risk posture
    # Phase 14 — Workflow Automation & Business Process OS
    ("workflow", 60),           # resume waiting executions + timeouts + approval escalation
    ("scheduler", 60),          # fire due cron workflows
    ("retry", 300),             # retry failed workflow steps + escalation
    ("integration", 60),        # drain queued automation integration syncs
    ("workflow_analytics", 43200),  # materialize workflow execution metrics
    # Phase 15 — Enterprise Platform, Extensibility & Global Administration
    ("monitoring", 300),        # metrics + observability retention pruning
    ("security", 300),          # auto-resolve stale security events
    ("compliance_policy", 21600),  # flag overdue compliance controls
    ("sync", 3600),             # SCIM + integration connection syncs
    ("plugin", 3600),           # re-verify installed plugin payloads
    ("backup", 86400),          # enterprise configuration snapshots
    # Phase 16 — Global Scale, Cloud Infrastructure & Enterprise Reliability
    ("infra_health", 600),      # cluster heartbeats + health metric snapshots + pruning
    # Phase 17 — Industry Solutions & Vertical Intelligence Platform
    ("industry", 43200),        # industry pack hygiene: catalog, compliance posture, stale workflows
    # Phase 18 — Autonomous Enterprise Intelligence & Developer Ecosystem
    ("twin", 3600),             # digital twin refresh: health, predictions, forecasts, recommendations, optimizations, brief
    ("webhook", 60),            # deliver pending webhook deliveries with retries
    ("marketplace", 3600),      # refresh listing downloads/ratings, expire keys and certifications
    ("developer_analytics", 43200),  # materialize developer ecosystem metrics
    ("billing", 21600),         # record developer monetization usage billing
    # Phase 19 — Company Memory & Universal Context
    ("memory", 43200),          # daily company history, decision capture, warm context
    # Phase 20 — Universal Organizational Intelligence Network
    ("intelligence", 3600),     # regenerate executive intelligence for every org
    ("orchestration", 21600),   # full evolution cycle: observe -> graph -> health -> intelligence
    ("evolution", 86400),       # incremental evolution: health + graph + intelligence refresh
    ("reasoning", 43200),       # company understanding digest into the timeline
    ("simulation", 86400),      # periodic quarterly outlook simulations
    ("innovation", 43200),      # continuous idea and opportunity scanning
    ("resilience", 21600),      # disruption signal scan + response plan refresh
    # Slice 4C — Governance, RBAC & Enterprise Control Foundation
    ("delegation", 300),        # expire overdue delegations (lazy deny already enforced)
    ("governance", 21600),      # escalate AI recommendations awaiting human review
    # Slice 4D.1 — Canonical Company Intelligence & Evidence Layer
    ("company_intel", 900),     # keep CompanyInsight freshness current for recently changed entities
    # Slice 4D.3 — Organizational Memory Automation
    ("memory_formation", 300),  # change-driven memory formation from significant events
]

_tasks: list[asyncio.Task] = []


async def _run_worker(name: str, interval_seconds: int, start_delay: float = 0.0) -> None:
    if start_delay:
        await asyncio.sleep(start_delay)
    module = importlib.import_module(f"app.workers.{name}_worker")
    while True:
        try:
            processed = await module.run_once()
            if processed:
                logger.info("worker %s processed %s items", name, processed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - per-worker isolation
            logger.warning("worker %s failed: %s", name, exc)
        await asyncio.sleep(interval_seconds)


def start_scheduler() -> list[asyncio.Task]:
    """Start all registered workers as background tasks. Idempotent.

    Workers are staggered so the DB pool is never slammed by every worker
    opening a session in the same instant at startup.
    """
    global _tasks
    if _tasks:
        return _tasks
    _tasks = []
    for index, (name, interval) in enumerate(WORKER_REGISTRY):
        task = asyncio.create_task(
            _run_worker(name, interval, start_delay=min(index * 0.5, 60.0)),
            name=f"vcos-worker-{name}",
        )
        _tasks.append(task)
    logger.info("started %s background workers (staggered)", len(_tasks))
    return _tasks


def stop_scheduler(tasks: Optional[list[asyncio.Task]] = None) -> None:
    """Cancel all scheduler tasks. Each worker loop unwinds on CancelledError."""
    global _tasks
    targets = tasks if tasks is not None else _tasks
    for task in targets:
        task.cancel()
    _tasks = []


def scheduler_tasks() -> list[asyncio.Task]:
    return list(_tasks)
