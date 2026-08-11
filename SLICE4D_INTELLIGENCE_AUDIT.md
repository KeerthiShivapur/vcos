# SLICE 4D.0 — COMPANY INTELLIGENCE READ-ONLY AUDIT

**Date:** 2026-08-11 · **Mode:** READ-ONLY (no files modified; findings verified against source)
**Scope:** Determine what exists, what is incomplete, duplicated, disconnected, and what can become the foundation of the VCOS Company Intelligence Layer.

---

## 1. Executive summary

VCOS is **not a green field** for Company Intelligence. It already contains a large, fully-wired intelligence estate built as "Phase 7–20" scaffolding alongside the 4A/4B/4C operating slices:

- **116/116 API routers registered** in `app/main.py` (including `/brain`, `/intelligence`, `/ai`, `/intelligence`, `/executive`, `/twin`, `/memory`, `/knowledge`, `/network`, `/prediction`, `/autonomy`).
- **85/85 worker modules scheduled** (`app/workers/scheduler.py:22-121`) across 60s–24h intervals.
- **72/72 model modules registered** for `create_all`; the schema includes dedicated intelligence tables (`OrgGraphEdge`, `ExpertiseHistory`, `PatternDetection`, `LearningEvent`, `CompanyMemory`, `OrganizationContext`, `RecommendationItem`, `DailyBrief`, `AIInsight`, `AIPrediction`, `ExecutiveIntelligence`, …).
- A **durable event bus** (`app/events/event_bus.py`) with per-handler isolation, exponential backoff, orphan adoption, and automation hooks; **~250 cataloged events** (`app/events/event_models.py`).
- **Real event→intelligence consumption already exists**: org-graph edges, expertise scoring, learning events, progress rollups, notifications, automation triggers.

**Verdict: the foundation exists but is incomplete, fractured, and unproven at scale.**

Key gaps that 4D must close:

1. **Reasoning is template/keyword retrieval, not connected intelligence.** The flagship "Why is X delayed?" (`intelligence_network/reasoning_engine.py`) inspects tasks/meetings/docs via SQL but does **not** consult task dependencies, decisions, messages, priority changes, ownership changes, or the org graph. It returns no per-claim source IDs, no confidence, no authorization scope, and its "who knows" path cannot function (it compares a non-existent attribute on the Employee model).
2. **The LLM gateway is nearly disconnected from the brain.** Groq/OpenAI/Anthropic providers are real (`ai/gateway.py`), but only the AI Companion (`/ai`) and learning paths use them; the Brain's `ask` is 100% deterministic templates.
3. **Embeddings are deterministic hashes, not semantic.** `knowledge/embedding.py` builds 256-dim bag-of-words hashes; knowledge/search similarity is lexical only. No vector store.
4. **4C governance events are persisted but not consumed by intelligence.** No handler subscribes to `governance.*` / `role.assigned` / `role.removed`. 4B messaging events are consumed only by live push + search — not by graph/expertise/learning/memory. 4A decision events *are* consumed (graph edges `decision→task`, `tasks.decision_id`).
5. **Universal search leaks across permission boundaries.** `services/search_service.py` org-scopes everything but applies **no role/permission filtering** — any employee can search finance vendors/budgets/invoices, enterprise integrations, and full employee records.
6. **Scale is the dominant risk.** Nearly every worker begins with `select(Organization.id).all()` then re-scans entire organizations (employees, messages, tasks, projects) per interval — classic O(N) fan-out that will not survive 1k+, let alone 50k employees.
7. **Evidence lineage primitives exist (confidence, evidence text, source_event, entity ids) but are not composed into explainable answers** with authorization scope.

**4D proposal:** build on the existing estate — do **not** create a parallel intelligence platform. 4D.1 establishes a canonical, governance-filtered Context Layer fed by the event bus, with evidence-backed answers (claim → evidence IDs → confidence → auth scope). Everything is observational; no autonomous mutations.

---

## 2. Existing architecture

```
Frontend (Next.js, 85 routes) ── /ai, /executive, /intelligence, /twin, /knowledge,
                                   /search, /messages(ws), /brain(partial UX)
         │
         ▼
FastAPI (app/main.py: 116 routers) ── RequestContextMiddleware, CORS
         │
   ┌─────┴──────────────────────────────────────────────┐
   │ app/api/v1/   endpoints (permission-gated via      │
   │               api/deps.py require_permission)      │
   ├────────────────────────────────────────────────────┤
   │ app/services/  event_service, notification, audit, │
   │                search, governance, permission,     │
   │                work_alerts, organization, workspace│
   ├────────────────────────────────────────────────────┤
   │ app/kernel/ (Phase 20 Company Brain)               │
   │   organization_kernel → ai, context, graph,        │
   │   memory, health, intelligence, search, events,    │
   │   analytics, orchestration, governance, resilience │
   ├────────────────────────────────────────────────────┤
   │ Intelligence subsystems: app/ai, app/intelligence, │
   │   app/intelligence_network, app/autonomy,          │
   │   app/digital_twin, app/executive, app/memory,     │
   │   app/learning, app/knowledge                      │
   ├────────────────────────────────────────────────────┤
   │ app/events/  event_models → event_bus → handlers   │
   ├────────────────────────────────────────────────────┤
   │ app/workers/ 85 scheduled workers (60s–24h)        │
   ├────────────────────────────────────────────────────┤
   │ app/models/  72 modules → Base.metadata.create_all │
   └────────────────────────────────────────────────────┘
```

- **DB:** async SQLAlchemy; SQLite (dev) / PostgreSQL (pool_size 10, max_overflow 20 — `db/database.py`). Schema via `create_all` + idempotent `_POSTGRES_ALTERS` (4A: `tasks.decision_id`, `tasks.goal_id`, `decisions.goal_id`; 4B: `messages.edited_at`; 4C: `user_roles.scope_id`, `approvals.policy_id`). Alembic configured but **0 migration scripts**.
- **Scheduling:** `start_scheduler()` spawns one asyncio task per worker entry, staggered (0.5s×index, cap 60s). All workers run in-process with the same asyncio loop — a slow worker's awaited DB work can delay others in the same loop, though each task is independent.
- **Gateways:** `ai/gateway.py` — Groq (default), OpenAI-compatible, Anthropic, plus `LocalIntelligenceEngine` (regex/template, deterministic, auto-fallback). Safety phrase filter, in-memory 256-entry cache, in-memory token stats (not persisted).

---

## 3. Existing intelligence components

| Component | File | Status | Notes |
|---|---|---|---|
| AI Gateway | `app/ai/gateway.py` | LIVE | Real HTTP providers + local engine; used by companion, learning, industry AI. Approval: not used by Brain `ask`. |
| AI Companion | `app/ai/companion_service.py` | LIVE | `/ai` chat; receives `user=user` (per-user grounding possible); grounded/LLM tiers. |
| Reasoning engine | `app/intelligence_network/reasoning_engine.py` | LIVE | Brain `/brain/ask` path; keyword intent classification; 8 evidence builders; no per-claim ids/confidence. **Broken "who knows" path** (compares non-existent `Employee.skills`). |
| Org graph | `app/intelligence/graph_engine.py` + kernel graph_engine | LIVE | `OrgGraphEdge` (typed, weighted, evidence, active); structural rebuild O(N); BFS path; bottlenecks. Edge types limited; no task→project or conversation nodes. |
| Expertise | `app/intelligence/expertise_engine.py` | LIVE | Event-driven per-skill deltas, decay, `ExpertiseHistory` audit; needs seed skills; `recompute_all` O(N) per org. |
| Knowledge AI | `app/knowledge/ai_service.py`, `embedding.py` | LIVE | Deterministic hash embeddings (256d, word+bigram); duplicate/quality workers; no neural vectors. |
| Pattern engine | `app/intelligence/pattern_engine.py` (via pattern_worker) | LIVE | `PatternDetection` with count/confidence/evidence/status; runs 12h; per-org scan. |
| Insights | `app/intelligence/insights_engine.py` (insights_worker 24h); `ai/insights.py` (ai_insights_worker 30m) | LIVE | Two parallel insight producers. |
| Learning | `app/intelligence/learning_engine.py` (learning events); `app/learning/` (skill gaps, recs) | LIVE | `LearningEvent` lessons from event handlers; separate `ai/learning.py`. |
| Company memory | `app/memory/` (memory_service, context_service, timeline_service) | LIVE | `CompanyMemory`, `OrganizationTimeline`, `OrganizationContext`; memory.recorded events; kernel reads them. |
| Digital twin | `app/digital_twin/` (11 svc) + twin_worker | LIVE | Twin state/history, predictions, forecasts, simulations, decisions with outcome scoring. Observe + explicit apply only. |
| Executive | `app/executive/` + 8 exec_* workers | LIVE | Health, risk, recommendations, reports, strategy, simulations; CEO/admin UX. |
| Autonomy/awareness | `app/autonomy/awareness_engine.py` etc. | LIVE (partial) | CompanyState snapshot, health, prediction, strategy, briefing. 5 files dead (see §14). |
| Notifications | `app/services/notification_service.py`, notification_worker, work_alerts | LIVE | Per-event targeted notifications; org retention policy (default 90d) exists for notifications/audit. |
| Universal search | `app/services/search_service.py` (19 domains) + kernel/search_engine | LIVE | SQL `LIKE %…%` across ~25 tables/20+ types; org-scoped; **not permission-scoped**; 4B messaging limited to viewer's conversations. |
| Workflow intelligence | `app/intelligence/workflow_engine.py` | LIVE | Approval bottlenecks etc. |
| Collaboration intel | `app/intelligence/collaboration_engine.py` | LIVE | Dept-pair interactions from meetings/messages. |
| Meeting intel | `app/collaboration/meeting_intel.py` | LIVE | Decisions, attendance, action items. |
| Burnout/duplicate/risk/search-intel | `app/intelligence/*` | LIVE | Workers hourly–daily. |

Dead modules (not imported anywhere reachable): `ai/security.py`, `intelligence/event_processor.py`, `autonomy/digital_twin_sync.py`, `autonomy/knowledge_evolution.py`, `autonomy/learning_loop.py`, `autonomy/optimization_engine.py`, `autonomy/workflow_intelligence.py`, `learning/analytics_service.py`, plus the entire `app/scheduler/` façade (test-only).

---

## 4. Existing data sources

Canonical tables (all org-scoped) available for intelligence:

- **People:** `users`, `employees`, `departments`, `teams`, `skills` + `expertise_scores`, `employee_skills`
- **Work:** `projects`, `tasks` (`decision_id`, `goal_id` lineage), `task_dependencies`, `sprints`, `milestones`, `epics`, `roadmaps`, `goals`, `meetings`
- **Communication:** `conversations`, `conversation_members`, `messages` (+reactions/read receipts), `communities`, `announcements`
- **Decisions/Approvals:** `decisions`, `decision_options`, `approvals`, `approval_policies`, `governance_scopes`, `user_roles.scope_id`
- **Knowledge:** `documents`, `wiki_pages`, `policies`, `sops`, `templates`, `knowledge_relations`, `knowledge_index`(hash embeddings/KNN via SQL)
- **Intelligence:** `org_graph_edges`, `expertise_history`, `learning_events`, `pattern_detections`, `knowledge_insights`, `recommendation_items`, `daily_briefs`, `search_metrics/insights`, `collaboration_metrics`, `burnout_signals`, `company_memory`, `organization_timeline`, `organization_context`, `company_state`, `executive_intelligence`, `prediction*`, `simulation*`
- **Governance/RBAC:** `roles`, `permissions`, `user_roles` (+scope), `governance_scopes/assignments/delegations/policies` (4C)
- **Audit/Events:** `audit_logs` (retention 365d default, pruned by audit_worker), `events` (occurred_at, org, actor, payload JSON, processed_at — **no retention/prune path found**), `background_jobs`

---

## 5. Event flow

`event_bus.publish` → persists `Event` + enqueues `BackgroundJob("event.dispatch")` → `event_worker` (60s) / `intelligence/events/process` calls `process_pending(limit=100)` → claims (CAS) → runs registered handlers (per-handler isolation; succeeded-handler names persisted; exponential backoff 60s→1h; stale/crash reaping; orphan adoption) → automation triggers/rules fire → `processed_at` set → commit.

Intelligence consumers (registered `@on` in `app/events/handlers.py`):

| Domain | Events consumed | Consumers (graph/expertise/learning/notify/rollup) |
|---|---|---|
| 4A | `task.created/completed/blocked/deleted/transitioned`, `task.unblocked`, `dependency.added/removed`, `project.created/started/completed/cancelled`, `milestone.*`, `epic.created`, `sprint.*`, `roadmap.*`, `decision.made/executed/implemented`, `approval.approved/rejected`, `goal.completed`, `risk.closed` | graph edges, expertise deltas, learning lessons, progress rollup, notifications |
| Knowledge | `document.*`, `wiki.*`, `policy.approved`, `knowledge.duplicate_detected` | expertise, graph authored/edited, knowledge_engine insight ingest |
| People | `user.created`, `manager.changed`, `employee.transferred`, `team.member.added/removed`, `community.posted`, `recognition.given`, `innovation.submitted` | graph structural/membership, expertise, notifications |
| Learning | `course.completed`, `certificate.earned`, `assessment.finished`, `learning.path.completed`, `onboarding.completed`, `mentor.assigned` | skill gaps + recommendation refresh, learning events |
| CRM | `customer.created`, `lead.qualified`, `opportunity.won/lost`, `contract.*`, `ticket.*`, … | graph ownership, learning lessons, notifications |
| 4B messaging | `messaging.*` (11 events) | **NO handlers** — consumed only by Live WS push and raw DB search |
| 4C governance | `governance.*`, `role.assigned`, `role.removed` | **NO handlers** — persisted only |
| Finance | `expense.*`, `purchase.*`, `budget.*` | handlers (finance notify/audit) — no intelligence graph ingestion |

**Conclusion:** ~250 events cataloged; roughly half have background consumers; the intelligence-relevant event backbone exists and is durable. Missing borders: **message discussion events never reach the graph/expertise/memory**, and **governance events never reach intelligence** — both are exactly the seams 4D must close.

---

## 6. Graph flow

- **Writers:** event handlers (`_graph_link` in `handlers.py`) upsert activity edges in real time; `graph_worker`/`graph_updates_worker` call `rebuild_structural` (all employees→reports_to/member_of, all project members→works_on, all owners→owns, all assigned tasks→assigned_to) per org.
- **Storage:** `OrgGraphEdge` (unique `(org, src_type, src_id, tgt_type, tgt_id, relation)`, weight, evidence string, active flag, updated_at) + `GraphUpdate` audit + `graph.updated` events.
- **Relations today:** `reports_to`, `member_of`, `works_on`, `owns`, `manages`, `assigned_to`, `completed`, `authored`, `edited`, `posted_in`, `recognized`, `decided`, `produces`, `implemented`, `contains`, `attended`, `mentored_by`.
- **Queries:** neighbors, BFS collaboration path (loads ALL org edges into memory — unbounded), bottlenecks (degree count), stats.
- **Gaps:** no `task→project` edge; no `message/conversation` nodes; no `decision→scope` governance edges; no edges for customer/users beyond ownership; path query is O(E) in memory.

---

## 7. Memory flow

- `memory_service` writes `CompanyMemory` (decision/lesson/milestone/failure/success/…) with `entity_type/entity_id`, `source_event`, importance; `timeline_service` writes `OrganizationTimeline`; `context_service.build` computes related bundles (project→tasks/meetings/docs/memories; task→project; meeting→project/docs; document→project/wiki; decision→memories; employee→projects/tasks/docs) persisted in `OrganizationContext` with freshness, emits `context.updated`.
- `memory_worker` + `twin_worker`+ `ai_learning_worker` produce further memory/learning rows. Kernel exposes `/brain/memory`, `/brain/timeline`, `/brain/context`.
- **Gaps:** memory is **manually/implicitly recorded, not derived**; no message→memory; no governance-scope tagging; no per-user authorization annotation on memory entries; context bundles exclude conversations and dependencies.

---

## 8. Search/retrieval flow

- `services/search_service.py` runs ~19 sequential SQL `LIKE '%q%'` queries (users, org, roles, customers, workspace, people, work, knowledge, finance, automation, enterprise, infrastructure, industry, digital twin, developers, memory, messaging) with per-domain limits; returns flat ranked list.
- `knowledge/search_service.py` adds embedding-based cosine over deterministic hash vectors + taxonomy.
- Kernel `/brain/search` and `search_insight_worker`/`search_metrics` record search behavior intelligence.
- **Risks:** (a) no permission/RBAC filtering beyond org+membership (messaging is membership-scoped — good); (b) `LIKE %…%` cannot use btree indexes → full scans at scale; (c) no FTS/vector index; (d) 19 queries per keystroke request.

---

## 9. Expertise flow

Event handlers → `expertise_engine.record_activity` → per-employee skill deltas (token overlap amplification 0.4×/1.5×/2.5×), capped 100, decay 0.98 on recompute; `ExpertiseHistory` rows per change (event_id, reason); aggregates `employees.expertise_score`; `expertise.updated` events; leaderboard/top-skills APIs; `expertise_evolve_worker` hourly, `expertise_worker` daily (`recompute_all` = O(employees) per org).
**Gaps:** requires explicit skill records; text-matching is naive (`expertise_evolve_worker` scans org events); no confidence interval; no exploration of message/decision content.

---

## 10. Recommendation flow

Multiple producers coexisting:
- `ai/recommendations.py` + `/ai/recommendations` (companion recs)
- `intelligence/recommendation_engine.py` + `recommendation_feed_worker` (daily) + `/intelligence/recommendations`, `/recommendations`
- `learning/recommendation_service.py` (skill/course/path per employee — event-triggered)
- `autonomy/recommendation_engine.py`, `digital_twin/recommendation_service.py` (optimization suggestions, explicit apply), `executive/recommendation_engine.py` (CEO),
- `knowledge/recommendation_service.py` (documents/experts)
- Model: `RecommendationItem` (recipient, kind, entity_type/id, score, reasons JSON, status triage active/accepted/dismissed) — **no authorization scope, no confidence, no evidence object ids.**

---

## 11. Pattern detection flow

`pattern_worker` (12h) + `intelligence/pattern_engine.py` → `PatternDetection` (pattern_type/keyed unique, count, confidence, evidence text, first/last_seen, status triage). Currently wired for repeated_delay/repeated_incident/approval_bottleneck/knowledge_gap/onboarding. **Gaps:** pattern→insight→recommendation chain not composed; evidence is text, not objects; no per-scope granularity.

---

## 12. Organizational learning flow

`learning_engine.record` (from event handlers) → `LearningEvent` (lesson text, entity refs, tags); `ai/learning.py`; `learning_worker`/`ai_learning_worker` generate additional lessons + company history; `evolution_worker` runs kernel `orchestration.run_cycle`. **Gap:** lessons aren't linked to measurable outcomes (implemented decisions, velocity) — no feedback loop.

---

## 13. Existing autonomy boundaries

- **No autonomous mutation of other modules exists today.** Workers write to their own (intelligence/domain) tables; decision outcomes/simulations are human-triggered; `governance_engine` (kernel) requires explicit human `decide`; twin optimizations require explicit `apply`. This is a solid, safe boundary to PRESERVE and formalize (advisory-only in 4D).
- `optimization_worker`, `evolution_worker`, `orchestration` compute suggestions/cycles but do not apply changes to tasks/projects/decisions/messages/permissions.

---

## 14. Existing duplicate/conflicting systems

| Capability | Parallel implementations (all live) |
|---|---|
| Search | `services/search_service.py` (universal), `knowledge/search_service.py` (embedding), `kernel/search_engine.py` (brain), `ai/search.py` (companion), `intelligence/search_engine.py` + search_insight |
| Insights | `ai/insights.py`, `intelligence/insights_engine.py`, `knowledge/ai_service.py` (knowledge insights), `executive/health_engine+insights_engine`, `intelligence/burnout_engine` |
| Recommendations | `ai/recommendations.py`, `intelligence/recommendation_engine.py`, `learning/recommendation_service.py`, `autonomy/recommendation_engine.py`, `digital_twin/recommendation_service.py`, `executive/recommendation_engine.py`, `knowledge/recommendation_service.py` (7) |
| Graph | `intelligence/graph_engine.py` (edges), `intelligence_network/organization_graph.py`, `kernel/graph_engine.py`, `knowledge/graph_service.py` (knowledge graph), `people/graph_service.py` |
| Predictions | `ai/predictions.py`, `autonomy/prediction_engine.py`, `digital_twin/prediction_service.py`, `executive/forecasting.py`, `intelligence_network/strategic_ai.py` |
| Memory | `memory/memory_service.py`, `ai/memory/*` (7 files, AITenantMemory), `intelligence/learning_engine.py` |
| Expertise | `intelligence/expertise_engine.py`, `intelligence_network/organization_graph.py` (partial), `learning/skill_service.py` |
| Brain entry | `brain.py`, `intelligence.py`, `intelligence_briefs.py`, `executive.py`, `twin`, `ai.py` — overlapping "ask" surfaces with different semantics |

Each is individually functional; composition is absent. **4D should designate one canonical pipeline (events → graph → context → insight) and treat the rest as producers/consumers of the same canonical tables, not re-implement them.**

---

## 15. Missing capabilities

1. Connected, **evidence-backed answers** (claim → object IDs → confidence → auth scope).
2. **Governance-filtered retrieval** at the intelligence boundary (per-caller RBAC, scopes from 4C).
3. Message/discussion intelligence (conversations not in graph/memory/expertise).
4. Governance-event consumption (scope/role/delegation changes invisible to intelligence).
5. Task→project and decision→outcome graph edges; conversation nodes.
6. Semantic embeddings/vector index beyond deterministic hashing (deferred to 4E by design).
7. Incremental (change-driven) worker processing with watermarks (currently recompute-all).
8. Events-table retention (events grow unbounded).
9. Explainability payload format: `{claim, evidence:[{type,id,title,url}], confidence, scope, timestamp}` in answers and insight records.
10. A single canonical "Company Intelligence" API usable by `/ai`, `/brain`, `/intelligence`, `/executive` — one foundation, not 20 dashboards.

---

## 16. Security / tenant risks

- **Tenant isolation (org level):** strong — org_id on all tables; endpoints dep-inject `get_current_organization`; the verified brain/intelligence/accompanion code paths scope every query by `organization_id`. Cross-tenant leakage was NOT found in paths inspected (brain, ai, search, graph, context, memory, reasoning).
- **Pre-auth surfaces:** `/health` only. Middleware is per-org context enforcement.
- **LLM data boundaries:** companion sends org context to external provider when configured (`GROQ_API_KEY`) — acceptable but must be flagged in enterprise consent (`enterprise/ai_service.py` consent scopes exist); no per-user "this conversation may leave the org" gate today.
- **Search spindle:** universal search exposes **finance (vendors/budgets/invoices/expenses), enterprise (integrations/security events/plugins), HR-adjacent records** to anyone in the org (`search_service.py` §8 risks). Primary leak vector.

---

## 17. RBAC / governance risks

- Endpoints gate via `require_permission` (catalog + role matrices in `permission_service.py:147-148`, `247-248`; `brain:read` granted per role matrix — manager/hr read OK, mutations `brain:manage` restricted to ceo/admin per frontend lib).
- **BUT** the brain's `ask/search/overview` take only `(db, org.id)` — **no caller user/role/scope passed down** → every user with `brain:read` receives the same org-wide answer. 4C scopes (`user_roles.scope_id`, `governance_scopes`) are **not consulted** before retrieval.
- Companion passes `user=user`, so per-user grounding is structurally possible but not enforced against 4C scopes.
- Insight/pattern/recommendation records carry no authorization scope — nothing prevents a manager-visible insight derived from finance data which employees may not see.
- **Mitigations for 4D:** retrieval pipeline must resolve `user → org → role → scope → accessible object ids` (reuse `permission_service`/`governance_service`) before any query/LLM call; tag every stored insight with the scope it was computed under; filter display by caller scope.

---

## 18. Scale risks (1 → 50,000 employees)

| # | Risk | Evidence | Severity |
|---|---|---|---|
| 1 | **Tenant-iteration fan-out:** ~60 workers begin `select(Organization.id).all()` and then loop organizations | `ai_insights_worker.py:25`, `ai_predictions_worker.py:25`, `ai_learning_worker.py:24`, `exec_health_worker.py:26`, `exec_analytics_worker.py:23`, `exec_prediction_worker.py:25`, `exec_reporting_worker.py:23`, `indexing_worker.py:26`, `duplicate_worker.py:25`, `quality_worker.py:26`, `backup_worker.py:32`, `audit_worker.py:25` | CRITICAL (linear in #tenants) |
| 2 | **Per-org whole-table rescan:** graph structural rebuild loads ALL employees/members/projects/tasks of each org; expertise `recompute_all` per employee; insight/collab/pattern workers scan all messages/meetings | `graph_engine.py:144-226`, `expertise_engine.py:183-191`, `ai_worker.py:64,96,104,113,118,132`, `collab_intel_worker.py:23`, `knowledge_intel_worker.py:23`, `pattern_worker.py:23`, `insights_worker.py:28,39`, `risk_worker.py:80-135`, `marketplace_worker.py:35-76`, `developer_analytics_worker.py:43-112`, `hiring_worker.py:35-72` | CRITICAL |
| 3 | **Search:** ~19 `LIKE '%q%'` per request, no index | `services/search_service.py` | HIGH |
| 4 | **Graph BFS loads all org edges into memory** | `graph_engine.py:311-360` | MEDIUM |
| 5 | **Events table unbounded** (no retention/prune) | no DELETE path found for `events`; grep survey | HIGH |
| 6 | **Notification/audit** — retention exists (org policy; defaults 365d/90d) but workers are per-org loop | `audit_worker.py:25-28`, `notification_worker.py` | MEDIUM |
| 7 | **Worker concurrency:** 85 asyncio tasks on one loop, staggered only at start; heavy passes serialize the event loop at awaits | `workers/scheduler.py:142-159` | MEDIUM |
| 8 | **Reasoning in-Python filtering** (`_delay_evidence` loads all project tasks; `_expertise_evidence` loads 500 employees and matches in Python) | `intelligence_network/reasoning_engine.py:121-135,200-222` | MEDIUM |

4D constraint: **every new pipeline must be change-driven** (events/watermark), capped per pass, and index-backed.

---

## 19. Database / query risks

- No Alembic migrations (schema drift risk as columns are hand-patched via `_POSTGRES_ALTERS`).
- `events`, `background_jobs` lack `(org, created_at)` composite indexes; `messages`/`tasks`/`notifications`/`audit_logs` rely on per-model indexes (many have them; event/message tables need `(org, created_at)` for time-window scans).
- JSON payloads on events/messages (large blobs in table scans).
- Embedding index is computed on the fly for knowledge search (KNN in Python over the org's index rows) — org-local but not scalable without pruning.

---

## 20. Worker / queue risks

- All 85 workers in-process on the app's asyncio loop — no queue, no retry policy for workers (retry exists only for event-dispatch jobs via `BackgroundJob`).
- No concurrency cap per worker; overlapping intervals (many 3600s) can pile up; no last-run watermark → recompute-all semantics.
- `POST /intelligence/workers/{name}/run` and `POST /brain/evolve` are permission-gated (`brain:manage`) — OK.
- Event dispatch queue already has backoff/reaping/orphan-recovery — mature; keep as-is.

---

## 21. Exact files that would need modification (4D.1)

Core canonical intelligence layer (new + extended):

- **NEW `app/intelligence/company_context.py`** — canonical scoped-context builder: `resolve_access(user) → org/role/scopes → accessible object ids → assemble connected evidence (project→tasks→deps→decisions→messages→governance)` with per-claim `{type,id,title,url}` + confidence.
- **`app/intelligence_network/reasoning_engine.py`** — swap evidence builders to consume company_context; add per-claim source IDs, dependencies (`TaskDependency`), decisions (`Decision` + `tasks.decision_id`), messages (membership-scoped), priority/ownership changes, confidence, auth_scope in the answer envelope.
- **`app/services/search_service.py`** — add permission/scope filter hook (`user_id`, scope ids) to exclude finance/enterprise/HR results for non-authorized roles.
- **`app/api/v1/brain.py`** — pass `user` + scope context into ask/search/overview; add `/brain/answer` canonical response shape.
- **`app/events/handlers.py`** — add handlers for `messaging.message_sent` (graph conversation nodes + expertise tokens + memory seeds, activity-capped) and `governance.assignment.created/removed`, `role.assigned/removed`, `governance.scope.*` (scope→graph + lineage).
- **`app/intelligence/graph_engine.py`** — add `task→project`, `decision→scope`, `conversation` node/edge upserts; cap BFS.
- **`app/events/event_models.py`** — register new messaging/graph expertise mappings.
- **NEW workers** (change-driven, watermark): `app/workers/company_intel_worker.py` (incremental evidence/insight curation per org, bounded).
- **NEW `app/models/company_insight.py`** (or extend `ExecutiveIntelligence`): `{org_id, title, claim, evidence_json[{type,id,title,url}], confidence, scope_json, status, created_at}`.
- **`app/db/database.py`** — add `(org, created_at)` indexes on events, background_jobs, messages, notifications; events-table retention hook.
- **Frontend (`frontend/app/(app)/intelligence/`, `frontend/lib/api.ts`, `frontend/types/index.ts`)** — canonical "Evidence/Ask" panel consuming `/brain/answer`; replace ad-hoc ask surfaces progressively.

## 22. Exact files that must remain untouched

- **4A:** `app/work/*` core execution services, `app/api/v1/decisions.py`, tasks/projects/sprints/goals APIs + models.
- **4B:** `app/communication/` services, `app/api/v1/messaging.py`, `frontend/lib/websocket.ts`, realtime push (`live.py`, `collaboration_live.py`).
- **4C:** `app/services/governance_service.py`, `app/services/permission_service.py` (catalog may be extended), `app/api/v1/governance.py`, `app/api/v1/approvals.py`, governance models, `MAX_SCOPE_DEPTH` semantics.
- **Core infra:** `app/events/event_bus.py` (dispatch/retry/reaping), `app/events/publisher.py/subscriber.py`, `app/db/database.py` engine/pool, `app/core/*`, auth (user/session), health.
- **Mature workers:** event_worker, delegation_worker, governance_worker, dependency/progress rollup workers.
- No changes to any 4A/4B/4C test or acceptance script.

---

## 23. Proposed 4D implementation boundaries

- **4D.1 only:** Canonical context/retrieval layer + governance-scoped evidence answers + search permission filtering + messaging/governance event ingestion into graph/expertise/memory + canonical insight record + retention index fixes.
- **Strictly observational:** no worker may mutate tasks, decisions, projects, messages, permissions, scopes, or knowledge rows. Workers write only to intelligence tables (org_graph_edges, company_insight, learning_events, recommendation_items with status triage). Human-approval gates unchanged (`governance_engine.decide`, twin `apply`).
- **Intelligence hierarchy target for 4D.1:** Levels 1–4 (Facts → Relationships → Patterns → Insights). Level 5 recommendations advisory only; Level 6 predictions and Level 7 autonomy explicitly deferred.
- **Scale law for new code:** change-driven (consume `events` table / BackgroundJob watermark), per-pass caps, indexed queries, no per-employee/per-message full scans, no new per-recipient fan-out without batch limits.
- **Governance law for new code:** every retrieval begins `user → org → roles → scopes(PermissionService/GovernanceService) → accessible ids`; every stored insight carries `scope` + `evidence` + `confidence`; answers render differently per role.
- **One canonical surface:** `/brain/*` becomes the Company Intelligence API; `/ai`, `/intelligence`, `/executive`, `/twin` remain specialized views over the same canonical tables (no new parallel data stores).

---

## 24. Proposed tests (proposed — not yet written)

- `backend/tests/test_company_context.py`: scope-resolved context assembly; RBAC matrix (employee vs manager vs ceo on finance-grounded question); evidence IDs present; dependency/decision/message lineage join correctness; tenant isolation (org B cannot see org A evidence).
- `backend/tests/test_search_permissions.py`: employees cannot retrieve finance/enterprise results; manager sees scoped results; messaging membership respected.
- `backend/tests/test_messaging_governance_events.py`: `messaging.message_sent` and `governance.assignment.created` handlers update graph/expertise/memory/learning with correct org scoping and idempotency.
- `backend/tests/test_insight_lineage.py`: insight rows carry evidence JSON, confidence bounds [0,1], auth scope, created_at; no orphan source ids.
- `backend/tests/test_events_retention.py`: events older than policy are pruned; dispatch jobs unaffected.
- Full regression: `pytest tests/ -q` (530+ existing).

## 25. Proposed E2E (proposed)

- `frontend/e2e/slice4d-intelligence.spec.ts`: exec logs in → ask a project-delay question on `/brain` (or existing `/executive` ask card) → answer shows claim + evidence chips (decision/task/project ids) + confidence + scope; employee with finance-gated ask sees no finance-derived evidence; manager sees scoped variant; evidence chips deep-link to canonical records; no auto-mutation visible (no task statuses change). Runs against live backend + frontend per 4A–4C harness.

## 26. Proposed acceptance script (proposed)

- `backend/scripts/accept_slice4d.py` — live-API checks (mirroring accept_slice4c.py style):
  1. Setup org A + org B, users (ceo/manager/employee), 4A chain: decision → tasks → deps → delay; messages discussing the delay; governance scopes assigned.
  2. `/brain/answer` on "Why is <Project> behind?" → assert evidence includes the decision id, the blocked task id, the message conversation, confidence present, auth scope present.
  3. RBAC: employee query on finance context → no finance evidence; manager scoped answer; ceo full.
  4. Tenant: org B token → 404/empty on org A entities; no org A evidence in answers.
  5. Event consumption: message_sent created conversation graph node + expertise delta; governance.assignment.created wrote lineage edge.
  6. Insight record written with evidence/confidence/scope; advisory only (no mutation of the decision/task rows).
  7. Search: employee search excludes finance/enterprise records; manager includes.
  8. Verify watermark/incremental behavior and event-retention pruning.
  - Exit 0 = all passed; run to green before report.

## 27. Definition of Done (proposed)

1. Company context layer returns connected, evidence-annotated answers (claim + object IDs + confidence + auth scope + timestamps).
2. Every answer pipeline applies 4C governance scoping before retrieval; no leak proven by tenant + RBAC tests.
3. Messaging and governance events are consumed into graph/expertise/memory; handlers idempotent and org-scoped.
4. Search respects role/scope; employee cannot retrieve finance/enterprise/scope-protected records.
5. No intelligence process mutates operating-layer data (tasks/decisions/projects/messages/permissions); enforced by tests + acceptance.
6. New pipelines are change-driven and bounded; no new org-wide rescan worker; existing rescans flagged for 4D.2+.
7. `test_company_context / search_permissions / messaging_governance_events / insight_lineage / events_retention` green; full `pytest` regression green; full Playwright green.
8. `accept_slice4d.py` green; `SLICE4D_VERIFICATION_REPORT.md` written.
9. Commit + tag `vcos-slice-4d-complete`; STOP (no 4D.2 autonomously).

---

## 28. Explicitly deferred to 4E+

- 4D.2 real embeddings/vector knowledge retrieval (deferred to 4E Knowledge Intelligence by design; deterministic hashing remains).
- 4D.3 deeper organizational memory automation (auto-derive lessons from outcomes).
- 4D.4 universal pattern library with escalation (repeated delays/decision reversals/ownership ambiguity) beyond current partial patterns.
- 4D.5 insight generation at Level 4-5 breadth across all domains (finance/HR/customer/sales intelligence — 4F–4K).
- 4D.6 recommendation autonomy and any human-approval automation loops (4D.7 vision; Level 6-7).
- 4D.7 unified intelligence UX as one brain surface for every persona (executive/employee/org) — partial 4D.6+.
- Predictions, simulations, autonomous actions (Level 6/7), 4O–4Q slices.
- Any cross-tenant or multi-instance/global-enterprise distribution concerns.

---

**End of audit. No source files, schema, APIs, frontend, tests, configuration, event handlers, workers, or intelligence services were modified. Nothing committed yet — this report is the deliverable of 4D.0. STOP.**