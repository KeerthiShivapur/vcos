# SLICE 4H.5 — STRATEGIC DECISION-TO-ACTION & EXECUTION INTELLIGENCE (RATIFIED — v0.2)

> **STATUS: RATIFIED — v0.2, 2026-08-21.** Ratified by the Architectural Review,
> which strengthened DRAFT v0.1 with ten binding amendments (§0.3) and authorized
> the mandated verification gates: AMEND → RATIFY → FRESH §0 CURRENT-REPO AUDIT →
> clean 4G.7/4H.1/4H.2/4H.3/4H.4 BASELINES → IMPLEMENT 4H.5 ONLY → UNIT + LIVE →
> 4H.5 ACCEPTANCE → REGRESSION → ANTI-DUPLICATION AUDIT → SCOPE AUDIT → DONE →
> FREEZE.
>
> Ratification does NOT authorize any 4H.6+ or unrelated feature. 4H.4 remains
> frozen and verified (`SLICE4H4_VERIFICATION_REPORT.md`).
>
> **What 4H.5 is:** not an action manager, not a workflow engine, not automation.
> **"4H.5 does not create execution capability. It makes the existing execution
> capability intelligible, provenance-connected, governed, and continuous from
> decision to outcome."** It is the canonical Decision-to-Action bridge and
> Execution-Chain intelligence of the ONE company intelligence spine:
> state → scenario → decision → action → execution evidence → outcome linkage.

---

## 0. Mandatory analyze-then-extend step (do not skip)

### 0.1 Reuse map (binding) — audited 2026-08-21 against the current repository

The §0 audit was executed BEFORE drafting (file/line evidence below; the repository
remains the only truth — the post-ratification implementation audit must re-confirm
each row; the drafting audit is evidence for drafting, not a substitute).

| Reuse anchor | Location (current repo) | What 4H.5 uses it for |
|---|---|---|
| **Canonical action primitive (4E.6)** | `CompanyAction` (`app/models/company_actions.py` :41), full lifecycle `proposed → validating → awaiting_approval\|approved → ready → in_progress → blocked → completed → verified`, terminal `rejected/cancelled/expired/failed/superseded`; exact-once `uq_company_actions_fingerprint` (:103); lineage cols `source_recommendation_id/source_insight_id/source_event_id/source_claim_ids_json` (:61–64); governance `policy/approval_required/approver_id/approved_*` (:69–75); routing `target_type/target_id` (:66–67); CAS `version` (:98) | THE action representation. 4H.5 adds **zero** new action tables/engines/workers |
| Action lifecycle engine | `action_ops_engine.propose` (:413), `.transition` (:640), `.record_outcome` (:747), `.evaluate`, `.center`, `.outcome_intelligence` (`app/knowledge/action_ops_engine.py`) | All writes flow through these existing methods — no parallel write path |
| Action audit + outcomes | `company_action_events` append-only audit (`company_actions.py` :120, 16-event vocabulary :112–117); `CompanyActionOutcome` one-per-action (`uq_company_action_outcomes_action` :159) | Execution evidence — "done" always means an evidence row exists |
| Governed decision lifecycle (4H.2) | `CompanyDecision` (`app/models/company_operating.py` :366); `DECISION_STATES proposed→evaluated→recommended→approved\|declined→executed→outcome_recorded→assessed` (:99–108); engine `execute_decision` (:2350), `record_outcome` (:2379) | The anchor entity: only decisions in `approved`+ states may originate actions |
| Scenario rehearsals (4H.4) | `company_scenario_runs` rows; future-slice identifier contract (`scenario_id, snapshot_ref, subject_id, decision_id, …` — 4H.4 contract §4.1) | Provenance: an action may cite the rehearsal that informed its decision |
| Causal edge vocabulary | `CAUSAL_EDGE_KINDS` includes `"decision->task"`, `"task->execution"`, `"execution->outcome"` (`company_operating.py` :160–161) | The chain read-model traverses EXISTING derived edges; no new edge kinds |
| Event vocabulary (complete already) | `event_models.py` :423–425 `company.decision.recorded` / `company.action.executed` / `company.outcome.recorded`; handlers `handle_company_operating_state` (`work/handlers.py` ~:3100–3173) recompute state on each | **Zero new events required** (§6) |
| Human-decision execution bridge | `decision_service.execute_action` (`knowledge/decision_service.py` :264) converts `Decision.follow_up_actions` into real Tasks (`Task.decision_id` FK, `models/task.py` :44); auto-implement on task completion (:359) | Untouched upstream pattern; human `decisions` participate only as routed artifacts |
| Approvals (three systems, all untouched) | simple `approvals` (`models/approval.py` :21); scoped ABAC `GovernanceScope`/`ApprovalPolicy` (`models/governance.py` :29/:57); workflow approvals (`automation/approval_service.py`) | 4E.6's own approval fields govern actions; 4H.5 adds NO approval system |
| Caller scoping | `resolve_caller_access` / `CallerAccess` (`intelligence/company_context.py` :172/:221) | Chain reads honor project-scoped visibility |
| Gates | `require_permission("brain:read"/"brain:manage")`, `_people_access` org-wide→404 | Identical to 4H.3/4H.4 |

### 0.2 The §0 schema decision rule (binding decision gate)

> Can a decision-originated, scenario-provenanced action be represented by the
> existing `company_actions` row via **additive nullable lineage columns only**,
> without reshaping 4E.6 semantics (state machine, fingerprint exact-once,
> approval policy, routing)?

- **Audit finding (2026-08-21): YES.** `CompanyAction` already carries recommendation/
  insight lineage columns (:61–64); decision/scenario provenance is the same concept
  with two more nullable indexed columns. Lifecycle, exact-once, approvals, routing,
  outcomes are untouched.
- Therefore 4H.5 takes the **additive branch**: exactly TWO new columns on
  `company_actions` (§3.1) and **ZERO new tables**.
- If implementation evidence contradicts this (it must not), the fallback — ONE new
  linkage table `company_decision_action_links` — requires returning for contract
  amendment before any code.

### 0.3 The gap 4H.5 closes (audit conclusion) + audit history

Three execution layers exist today, linked only loosely:

```
human Decision.follow_up_actions ──Task.decision_id──▶ tasks      (knowledge layer)
CompanyAction (4E.6) ──target_type/target_id──▶ routed artifacts  (action layer)
CompanyDecision (4H.2) ──state machine──▶ executed/outcome        (company layer)
```

Missing, and ALL that 4H.5 adds:
1. **Provenance**: no column links a `CompanyAction` back to the `CompanyDecision`
   (or 4H.4 scenario) that motivated it.
2. **Advisory plan**: no deterministic surface turns an approved decision into
   *proposed* governed actions for human authorization.
3. **Unified chain view**: no single bounded read stitches
   decision → scenario → actions → routed artifacts → transitions → outcomes → lesson.

Audit history:
- DRAFT v0.1 authored 2026-08-21 from the mandatory §0 current-repository audit.
  Not ratified.
- RATIFIED v0.2 2026-08-21 — Architectural Review incorporated TEN binding
  amendments: (1) Action-plan NON-INVENTION rule; (2) zero-step outcome
  (`insufficient_canonical_basis`) defined valid; (3) L16 origin-classification
  compatibility protecting all existing 4E.6 origins; (4) approval inheritance —
  existing 4E.6 policy remains authoritative without decision-originated overrides;
  (5) `CompanyDecision` is THE strategic anchor, generic decisions remain compatible
  routed artifacts; (6) plan = ephemeral advisory, action = institutionalized
  governed artifact, as binding law; (7) "no provenance, no node" extended to BOTH
  plan steps and chain nodes; (8) scope changes visibility and authorization
  boundaries, never ontology or execution architecture; (9) binding distinction
  between deterministic plan replay and live chain truth; (10) negative test proving
  no hidden planner (no LLM / unsupported natural-language reasoning constructs
  actions). Core question reworded; plan-persistence prohibition strengthened;
  moat reframed as lineage possibility (not a learning engine). Ratification
  record in §0.4.

### 0.4 Ratification record (verbatim from the Architectural Review, 2026-08-21)

> "4H.5 should remain exactly this shape … Company State → Scenario/Rehearsal →
> Human Decision → [4H.5 Decision → Action, Execution Chain] → EXISTING 4E.6 ACTION
> → approvals/routing/execution → existing evidence/events → existing outcome
> system → permanent company intelligence."
>
> "4H.5 does not create execution capability. It makes the existing execution
> capability intelligible, provenance-connected, governed, and continuous from
> decision to outcome."
>
> "A plan step may only be emitted when its target, action type, relationship, and
> provenance are supported by canonical repository data. Missing information
> produces no step; the system never invents a step to satisfy the bound."
>
> "Boundedness is not permission to invent. Five is a maximum, not a required
> number."
>
> "Every CompanyAction must have an explicit canonical origin classification:
> either a CompanyDecision provenance, another existing 4E.6-supported provenance,
> or an explicit human direct-propose origin. 4H.5 does not redefine or invalidate
> existing 4E.6 origins."
>
> "Existing 4E.6 approval policy remains authoritative without special
> decision-originated overrides."
>
> "4H.5 strategic execution chains originate from CompanyDecision. Existing generic
> decision artifacts remain compatible routed artifacts and are not promoted into a
> parallel strategic decision authority."
>
> "Scope changes visibility and authorization boundaries, never ontology or
> execution architecture."
>
> PERMANENT LAW (verbatim): "4H.5 may connect, derive, expose, and govern the
> company's existing intelligence; it may never invent a company fact, relationship,
> responsibility, action target, execution state, approval, outcome, or future
> result merely to complete a plan."

Open questions from v0.1 §0.4 are RESOLVED by ratification: law numbering L16/L17
confirmed (L15 stays Scenario Identity); approval inheritance = preserve 4E.6 policy
exactly; anchor = `CompanyDecision` only; permissions unchanged (`brain:read` reads /
existing `brain:manage` propose); column names as §3.1.

---

## 1. Objective

4H.5 is the company's canonical **Decision-to-Action & Execution Intelligence**
layer. Its core question (as ratified):

> **"Which governed actions are directly supported by the approved decision and
> existing canonical company relationships?"**

and, operationally:

> "A decision has been made. Which candidate actions does the canonical company
> model actually support, what dependencies and approvals apply, what was
> authorized, what actually happened — and how does all of it become part of the
> company's permanent intelligence?"

It completes the spine segment that 4H.4 deliberately left open:

```
COMPANY STATE (4H.3)
      ↓
SCENARIO REHEARSAL (4H.4)          — advisory, ends at HUMAN DECISION
      ↓
HUMAN DECISION (4H.2 CompanyDecision, state ≥ approved)
      ↓ 4H.5 begins
ADVISORY ACTION PLAN               — derived ONLY from canonical support; bounded;
      ↓                              honest ("proposes", never executes, never invents)
HUMAN AUTHORIZATION                — explicit, via the EXISTING 4E.6 propose path
      ↓
GOVERNED ACTION LIFECYCLE (4E.6)   — EXISTING policy evaluation → approvals →
      ↓                              routing into tasks/decisions/docs/…
EXECUTION EVIDENCE                 — company_action_events + routed-artifact state
      ↓
OUTCOME LINKAGE                    — company_action_outcomes + CompanyDecision.outcome_*
      ↓
UNIFIED EXECUTION CHAIN            — one bounded, provenance-traced live read over ALL of it
```

Two governance concepts are kept explicitly separate (never merged):
- **A. Plan authorization (4H.5):** the human says "authorize" → the EXISTING
  `action_ops_engine.propose` creates the governed action with lineage.
- **B. Action approval (4E.6):** the created action then passes through the
  EXISTING 4E.6 policy evaluation exactly as any other action would.

Core honesty statement: a plan says *"given this approved decision and the company's
existing canonical data, these governed actions are directly supported"* — never
*"this will work"*, and never a fabricated step when canonical support is missing.

---

## 2. Architectural laws (binding)

Carried forward unchanged: **L1 reuse-first, L2 canonical state is the only source,
L3 deterministic read paths, L4 advisory-before-action, L5 exact-once write doctrine,
L6 bounded surfaces, L7 tenant isolation + governance, L8 append-only temporal truth,
L9 Virtual Company Continuity, L10 honesty language, L11 propagation-not-prediction,
L13 canonicity, L14 global-scope extensibility, L15 Scenario Identity.**

New operational laws for 4H.5:

- **L16 Universal Execution Continuity (binding, origin-compatible).** Every
  authorized company action exists within the ONE canonical company representation
  regardless of the scope it originates from — organization, region, business unit,
  department, team, project, or individual. There is no startup action system,
  enterprise workflow system, or per-region execution engine; the same
  `company_actions` row, lifecycle, and chain semantics serve all scales.
  **Origin classification (Amendment 3):** every `CompanyAction` has an explicit
  canonical origin — a `CompanyDecision` provenance (`source_company_decision_id`),
  another existing 4E.6-supported provenance (`source_recommendation_id`,
  `source_insight_id`, `source_event_id`), or an explicit human direct-propose
  origin. **4H.5 does not redefine or invalidate existing 4E.6 origins.**
  **Scope is a filter, not a separate universe (Amendment 8):** scope changes
  visibility and authorization boundaries, never ontology or execution architecture.
- **L17 Execution Honesty & Evidence (binding).** 4H.5 never executes anything
  autonomously; authorization is always an explicit human call through the existing
  governed path. A plan proposes; it never promises: plan language is constrained to
  "proposes / addresses / follows from", prohibited: "will succeed", success
  probabilities, monetized forecasts. "Done" never exists without evidence: every
  claimed execution state must trace to an existing `company_action_events` row or a
  routed-artifact record. Plans carry `advisory_only: true` +
  `not_a_prediction: true`.
- **L18 Non-Invention — the Planner Guard (binding, permanent law, verbatim).**
  *"4H.5 may connect, derive, expose, and govern the company's existing
  intelligence; it may never invent a company fact, relationship, responsibility,
  action target, execution state, approval, outcome, or future result merely to
  complete a plan."* A plan step may only be emitted when its target, action type,
  relationship, and provenance are supported by canonical repository data already
  present in the decision, its stored context anchors, existing causal edges,
  existing routed artifacts, or existing governance structures. It may not invent
  people, targets, projects, dependencies, responsibilities, deadlines, resources,
  action types, or causal relationships. Missing information produces no step; the
  system never manufactures a step to satisfy the bound. **Boundedness is not
  permission to invent. Five is a maximum, not a required number.**
- **L19 Ephemeral Plan, Institutional Action (binding).** The PLAN is an ephemeral
  advisory derivation — never persisted, never a table, never a second artifact
  competing with the action. The ACTION is the institutionalized governed artifact.
  Plan authorization (A) and action approval (B) are distinct concepts and are never
  merged. Determinism distinction (Amendment 9): identical `(decision, context,
  canonical edges)` → byte-identical PLAN; the CHAIN is NOT required to be
  byte-frozen — it is required to be TRUTHFUL to current canonical execution
  evidence. Both properties are explicitly tested.
- **L12 inverted for 4H.5 (binding interpretation).** 4H.4 was read-only TO the
  decision bridge. 4H.5 IS the write path across it — but writes only flow through
  the EXISTING 4E.6 `propose` gate after explicit human authorization, carrying
  provenance columns. 4H.5 never mutates `CompanyDecision` state directly (the
  existing 4H.2 `execute_decision`/`record_outcome` paths remain the only writers),
  never mutates causal edges, never bypasses approval policy.

---

## 3. Schema — the exact boundary

### 3.1 Additive-only columns on `company_actions` (per §0.2 "yes" branch)

| column | type | note |
|---|---|---|
| `source_company_decision_id` | String(32), nullable, indexed | FK-by-id (no DB FK, matching house style of `source_recommendation_id`) to `company_decisions.id` — same-org enforced in service code |
| `source_scenario_id` | String(64), nullable, indexed | id of the 4H.4 `company_scenario_runs` row that informed the decision (moat linkage; ids only per 4H.4 §4.1) |

No other schema change anywhere. Existing columns, constraints, the fingerprint
exact-once key, and the state machine are untouched. Because `create_all` does not
alter existing tables, implementation adds an idempotent column-ensure
(`ADD COLUMN IF NOT EXISTS`) on the existing startup table-creation path — schema
addition only, no backfill, no data migration.

### 3.2 Explicit non-moves

- NO new tables (no link table, no plan table, no chain table, no execution-log table
  — `company_action_events` already IS the execution log).
- NO new status values on `company_actions` or `company_decisions`.
- NO changes to `tasks`, `projects`, `approvals`, governance tables.
- NO plan persistence (L19): the advisory plan is derived on demand
  (deterministic), like a 4H.4 dry-run. Institutionalization happens when the human
  authorizes real actions — those ARE the persisted artifact. Storing plans would
  create two competing artifacts (Plan vs Action) and is FORBIDDEN.

---

## 4. Lifecycle

```
human asks "what actions are supported for decision D?" / "turn D into action"
        ↓
resolve caller scope + tenant (org-wide or scoped; else 404)
        ↓
anchor: CompanyDecision D (state ∈ approved|executed|outcome_recorded|assessed;
        pre-approval decisions are REJECTED — advisory-before-action, L4)
        ↓
derive ADVISORY ACTION PLAN (deterministic, bounded, NON-INVENTIVE — L18):
  - inputs: D.kind/title/rationale/chosen alternative, D.state_context_json /
    as_of_context_json anchors, existing causal edges from D's anchored entities
    (kinds decision->task / task->execution / execution->outcome),
    existing risks reached via those edges
  - ≤ MAX_PLAN_STEPS (=5) steps; each step maps to a SANCTIONED 4E.6 action_type
    (task|decision|communication|knowledge|meeting|project) + a target that EXISTS
    canonically (project id / risk subject / decision id from context or walk)
  - every step cites basis: {decision_id, scenario_id?, edge_id?, risk_id?,
    target_id, relation?}  -- NO PROVENANCE, NO STEP
  - flags which steps the EXISTING 4E.6 policy will send to approval (read-only
    echo of policy; never an override)
        ↓
derivation_status: "ok" (≥1 supported step) | "insufficient_canonical_basis"
(proposed_steps = [] — a VALID, honest outcome; never hallucinated filler)
        ↓
dry_run=true  → return plan, write nothing, emit nothing     -- the "show me" path
        ↓
HUMAN AUTHORIZES (explicit): existing POST /brain/knowledge/actions
  (action_ops_engine.propose) with source_company_decision_id /
  source_scenario_id set → 4E.6 exact-once fingerprint applies
        ↓
EXISTING 4E.6 lifecycle proceeds unchanged (policy evaluation → approval behavior
  → routing → transitions → company_action_events audit rows)
        ↓
GET execution-chain stitches: D → scenario? → actions → routed artifacts
  (tasks/decisions/documents/…) → transitions/evidence → outcomes → lesson
        ↓
outcome recording stays where it lives today (4E.6 record_outcome +
  4H.2 record_outcome) — 4H.5 only makes the linkage visible
```

Replay rule: identical `(decision_id, plan inputs)` → byte-identical plan (L3/L19).
The CHAIN is a live truthful read-model over mutable lifecycle rows — it is NOT
byte-frozen; determinism applies to the PLAN derivation, truthfulness applies to
the chain (both tested).

---

## 5. Read laws (binding)

1. Plan derivation depends only on the decision row + its stored context anchors +
   existing edges/state — byte-identical on replay while those inputs are unchanged.
2. **No provenance, no node (Amendment 7)** — applies to BOTH surfaces: every plan
   step AND every chain node cites ids of decision/action/event/artifact/outcome/
   edge. A node that cannot name its basis is not emitted.
3. Canonical surfaces:
   - **ACTION PLAN**: DECISION (id/kind/title/state) · ORIGIN (scenario? rationale?)
     · PROPOSED STEPS (≤5, typed, targeted, each with basis) · DEPENDENCIES
     (existing edges) · APPROVALS EXPECTED (echo of existing 4E.6 policy, read-only)
     · HONESTY banner (`advisory_only`, `not_a_prediction`, `derivation_status`)
     · ends at **HUMAN AUTHORIZATION** — nothing is pre-approved by the surface.
   - **EXECUTION CHAIN**: DECISION → ACTIONS (state, assignee, due) → EVIDENCE
     (event rows) → ROUTED ARTIFACTS (typed ids) → OUTCOMES (effectiveness, verdict)
     → LESSON (if recorded). Bounded, newest-first per section, truthful to current
     canonical rows.
4. Traceability goal (global scale): "Why did this action exist?" must be answerable
   entirely from identifiers: action ← decision ← scenario ← snapshot ← edges;
   action → events → artifact → outcome → lesson. No narrative invention.
5. Bounds: plan steps ≤ 5; chain actions ≤ 10; evidence rows ≤ 20; artifacts ≤ 10;
   outcomes ≤ 5. All queries LIMIT + ORDER BY indexed columns.
6. Pre-approval decisions (`proposed|evaluated|recommended|declined`) yield 409-style
   rejection ("decision not yet approved"), never a plan.

---

## 6. Events

**ZERO new events.** The full vocabulary already exists and stays authoritative:
`company.decision.recorded`, `company.action.executed`, `company.outcome.recorded`
(`event_models.py` :423–425) plus the 4H.2 advisory events (:432–439). Plan
derivation emits nothing; authorization flows through `action_ops_engine.propose`
which already appends `company_action_events` audit rows; downstream state recompute
already listens to the existing events. Proposed names such as
`company.execution.plan.created` / `company.execution.chain.created` /
`company.decision.action.bridged` are FORBIDDEN as observability noise. If
implementation proves one new event unavoidable, implementation STOPS and returns
for ratification amendment.

---

## 7. API + brain routing

### 7.1 Surfaces

- `POST /execution/company/decisions/{decision_id}/action-plan` — body
  `{dry_run?: true}` (only dry_run supported in 4H.5; persistent plans are the
  authorized actions themselves). Returns the §5 ACTION PLAN surface.
  Permission: `brain:read` + `_people_access` org-wide (scoped → 404).
- `GET /execution/company/decisions/{decision_id}/execution-chain` — the §5 CHAIN
  surface. Permission: `brain:read` + org-wide; artifact-level visibility further
  filtered via `resolve_caller_access` project scoping.
- Authorization REUSES `POST /brain/knowledge/actions` (no new route): body gains
  optional `source_company_decision_id` / `source_scenario_id`, validated
  (same-org existence; decision state ≥ approved) then stored verbatim.
  Permission: existing `brain:manage`.

### 7.2 Brain intents (additive phrases only inside `_company_operating_query`)

- `company_execution_plan` — "action plan for", "what should we do about decision",
  "turn this decision into action", "next steps for decision", "how do we execute".
  Collision guard: must NOT steal 4E.6 action-center phrases ("my actions",
  "action center") nor 4G.7 what-if phrases (unit-tested).
- `company_execution_chain` — "execution status of decision", "did we act on",
  "what happened after we decided", "execution chain".

### 7.3 Governance (L7 + L14 + Amendment 8)

Tenant isolation identical to 4H.4 (org B → 404 on org A ids; scoped callers → 404,
never leak). Scope resolution stores nothing new — the action row's existing
`scope_type/scope_id` continues to govern; plan/chain reads resolve the caller's
scope against the decision's and actions' scopes. Scope filters visibility and
authorization boundaries; it never forks ontology or architecture.

---

## 8. Frontend (minimal, read-only)

Extend ONLY `frontend/app/(app)/execution/company-tab.tsx` and
`frontend/lib/api.ts`: an "Action plan" panel on the decision detail area
(derive → review → Authorize button calling the EXISTING propose client) and a
read-only execution-chain view. Lifecycle management of authorized actions stays in
the existing actions workspace page (`knowledge/workspace/actions/page.tsx`) — no
duplication, no new pages.

---

## 9. Scale law — large graph, small query

Same doctrine as 4H.4 §12, now a master law: identity → organization scope →
decision anchor → bounded neighborhood (≤60 edges) → ≤5 plan steps / bounded chain
sections. Unlimited company intelligence, bounded interaction cost. One ontology
from a 12-person startup to a global enterprise; a regional leader's chain shows
only their scope's actions and artifacts; a CEO's shows the company's. Never
NorthAmericaAction/EuropeAction/IndiaAction; never StartupEngine/EnterpriseEngine/
GlobalEngine. The difference between scales is scope, volume, permissions,
relationships — never architecture duplication.

---

## 10. Anti-duplication rules (binding)

- ZERO new engines/services/modules under `backend/app/`. Derivation extends
  `company_operating_engine` (plan + chain assembly) and `action_ops_engine`
  (lineage validation); no other production files beyond `models/company_actions.py`,
  `api/v1/brain.py`, `knowledge/intelligence_engine.py`.
- ZERO new workers, queues, cron wiring. (Wiring `action_ops_engine.evaluate` to a
  scheduler is explicitly OUT of scope — pre-existing gap, not 4H.5's.)
- ZERO new events, tables, status values, permission codes.
- Forbidden artifacts: WorkflowEngine, AutomationEngine, ExecutionEngine,
  ActionPlanStore, chain/plan/link tables, any second task model, any autonomous
  executor, any LLM on the plan/chain path, any hidden planner.

## 11. Determinism / no-LLM guarantee

Plans are composed by deterministic queries over canonical rows. Tests assert
byte-identical replay, `advisory_only`/`not_a_prediction` flags, that no LLM client
is imported on the plan/chain path, AND the Amendment-10 negative test: no step is
constructed from unsupported natural-language reasoning or LLM output (a decision
with rich free-text but zero canonical anchors MUST yield
`insufficient_canonical_basis`, proving text alone cannot manufacture steps).

---

## 12. Acceptance tests (`backend/scripts/accept_slice4h5.py`, live on :8999) — ratified list

1. Plan on an approved decision with canonical context (project anchor + reachable
   risk/decision): bounded ≤5 steps, sanctioned types, existing targets, basis on
   every step, honesty flags true, `derivation_status: "ok"`.
2. Dry-run writes nothing, emits zero events (asyncpg + event-stream proof).
3. Pre-approval decision → rejected plan (advisory-before-action).
4. **Non-invention:** a decision whose free-text suggests work but which has ZERO
   canonical anchors yields `proposed_steps: []` +
   `derivation_status: "insufficient_canonical_basis"` — no invented steps.
5. Authorize via EXISTING `/brain/knowledge/actions` with lineage → row created with
   `source_company_decision_id`/`source_scenario_id`; 4E.6 fingerprint exact-once
   still holds (duplicate propose → replay, no dup row).
6. Authorized action follows the UNCHANGED 4E.6 lifecycle (policy evaluation →
   approve/transition/route); `company_action_events` rows accumulate as evidence;
   low-risk auto-approve behavior (if applicable) is inherited, not overridden.
7. Chain view stitches decision → action(s) → evidence → routed artifact → outcome;
   every node names its basis; bounds respected.
8. Outcome recorded via existing paths appears in chain; `CompanyDecision` mutations
   still only via existing 4H.2 endpoints (byte-compare guard).
9. Tenant isolation: org B decision/action ids → 404; scoped caller → 404.
10. Determinism: identical inputs → byte-identical plan (L19 plan side).
11. Schema introspection: exactly TWO new columns on `company_actions`, ZERO new
    tables; event catalog diff = ZERO new events.
12. Brain intents resolve; collision guards hold (4E.6 + 4G.7 phrases unaffected).
13. Regression within slice: existing `/brain/knowledge/actions*` responses unchanged
    for non-lineage actions; 4H.4 scenario endpoints byte-unchanged.
14. L16 continuity: same decision→action→chain flow exercised at org scope AND a
    sub-scope (department/team) without special-casing; existing 4E.6 direct-propose
    actions (no lineage) remain fully valid (origin compatibility).
15. Moat T1–T4 (§13).
16. No hidden planner / no-LLM proof on both new paths (Amendment 10 + §11).

Exit code 0 only when all pass.

## 13. Moat test (compounding dependence — lineage, not learning)

The moat is NOT "many execution records" (copyable). The moat is that **every
decision becomes connected to the company's actual operating history**: the next
scenario no longer operates against a blank system but against accumulated
decisions, assumptions, actions, dependencies, execution evidence, outcomes,
lessons, and temporal state. T1: young company — decision with 1 action, thin chain.
T2: company operates — more actions, artifacts, events, outcomes accumulate. T3: the
SAME decision's chain is strictly richer (more evidenced nodes) with zero change to
chain code. T4: chains accumulate append-only as institutional memory — later slices
join `scenario_id → decision_id → action_id → outcome` ids (all present by §3.1 +
4H.4 §4.1) to compare rehearsed-vs-actual WITHOUT schema surgery. 4H.5 builds the
lineage POSSIBILITY; it does not build the learning engine (that is 4H.7's territory).

## 14. Definition of DONE

Post-ratification §0 re-audit green; additive-columns-only schema proven by
introspection; zero new events/engines/workers/queues/modules; `test_4h5_engine.py`
green; `accept_slice4h5.py` 16/16; regressions green: 4G.7 14/14 · 4H.1 16/16 ·
4H.2 19/19 · 4H.3 17/17 · 4H.4 15/15 live + full pytest + `tsc --noEmit` exit 0;
diff audit shows changes confined to `models/company_actions.py`,
`knowledge/action_ops_engine.py`, `intelligence/company_operating_engine.py`,
`api/v1/brain.py`, `knowledge/intelligence_engine.py`, the two frontend files,
plus new test/script files; verification report written; 4H.5 frozen.

## 15. Out of scope (hard boundary)

NOT attempted by 4H.5: autonomous execution or auto-approval of anything; a workflow/
automation/BPM engine; a new task/project manager; SLA/cron scheduling (including
wiring `evaluate`); notification fan-out; cross-company orchestration (4I+);
outcome analytics/performance scoring (4H.6); organizational learning (4H.7);
ERP/CRM/HRMS/ticketing replacement; changes to any of the three existing approval
systems; changes to the 4E.6 state machine, fingerprint semantics, or origin
vocabulary; LLM-generated plans; probability/success scoring on plans; plan
persistence; per-scale or per-region execution systems.

---

*RATIFIED as the governing contract for SLICE 4H.5 v0.2 (2026-08-21). The mandated
verification gates now begin: FRESH §0 CURRENT-REPO AUDIT → clean 4G.7/4H.1/4H.2/
4H.3/4H.4 BASELINES → IMPLEMENT 4H.5 ONLY. 4H.4 remains frozen.*
