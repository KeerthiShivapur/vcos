# SLICE 4H.4 — STRATEGIC SCENARIO & DECISION-REHEARSAL INTELLIGENCE (RATIFIED — v0.3)

> **STATUS: RATIFIED — v0.3, 2026-08-20.** Ratified by the Architectural Review,
> subject to the incorporation of the final Master Vision / Decision-Rehearsal
> invariants — all of which are now incorporated (see §0.3, §0.4). Ratification
> authorizes the mandated verification gates: §0 CURRENT-REPO AUDIT → REUSE +
> SCHEMA DECISION → clean 4G.7/4H.1/4H.2/4H.3 BASELINES → IMPLEMENT 4H.4 ONLY →
> UNIT + LIVE → 4H.4 ACCEPTANCE → REGRESSION → DIFF AUDIT → DONE.
>
> Ratification does NOT authorize immediate coding before those gates. It authorizes
> NO 4H.5 or unrelated feature. 4H.3 remains frozen.
>
> **What 4H.4 is:** not a Scenario/Simulation product inside VCOS, but the company's
> canonical **Decision-Rehearsal layer** — a capability of the same company
> intelligence spine that understands state, dependencies, decisions, risks,
> opportunities, actions and outcomes. It does NOT create another intelligence
> universe; it interrogates the one that already exists.

---

## 0. Mandatory analyze-then-extend step (do not skip)

### 0.1 Reuse map (binding) — what 4H.4 reuses, what it conditionally adds

Verified reuse anchors in the CURRENT repository (do not re-verify by trusting this
file — the repository is the only truth; the §0 audit must re-confirm each row):

| Reuse anchor | Location (current repo) | What 4H.4 uses it for |
|---|---|---|
| Living company state (4H.3) | `company_operating_engine.living_state`, `state_delta`, `state_risks`, `state_opportunities`, `state_affected_decisions`, `as_of` | The scenario **baseline**: the current (or as-of) snapshot the scenario is anchored to |
| Bounded what-if engine | `company_operating_engine.what_if` (engine :1866), `_what_if_response` (:2020), `decision_what_if` (:5549); `POST /execution/company/what-if` (brain.py :7074); `POST /execution/company/decisions/{id}/what-if` (:7974) | Consequence derivation for the three sanctioned change kinds; scenario→decision advisory linkage |
| Causal edges + causal walk | `_derive_causal_edges` (:3291), `causal_chain` (:3637), `state_dependencies`; `company_causal_edges` (4H.1 table); `MAX_CAUSAL_DEPTH=5`, `MAX_CAUSAL_EDGES=60` | Multi-hop propagation: which entities/risks/decisions the hypothetical change touches |
| Risk surface | `Risk` table + `state_risks` banding (probability, impact, HIGH/MEDIUM/LOW) | Consequence vocabulary "risk exposure change" — probabilities reused AS-IS, never recomputed |
| 4H.2 decision lifecycle | `CompanyDecision` + six `company_decision_*` tables; `decision_what_if`; `state_context_json` anchors | "Affected decision → needs_reconsideration (advisory)" |
| Opportunity surface | `PatternDetection`, `UniversalInsight`, `KnowledgeRecommendation` via `state_opportunities` | Consequence vocabulary "opportunity exposure" (derived, bounded) |
| Scenario persistence (existing, unconditional) | `SimulationRun` (`app/models/simulation.py`, `simulation_runs`), `simulation_worker.py`, event `simulation.completed` (event_models :340) | The ONLY existing scenario-run persistence. §0 must decide reuse vs the contingent table (§3.1) |
| Events fabric | `app/events/` publisher, `EVENT_CATALOG`, `publish_background_event` | One event per scenario decision path |
| Brain router | `intelligence_engine._company_operating_query` phrase rules; `_INTENT_RULES` | New intent routing (additive phrases only) |
| Gates | `require_permission("brain:read")` / `"brain:manage"`, `_people_access` org-wide→404 | Identity governance, identical to 4H.3 |

**What 4H.4 does NOT reuse as a design base:** no new engines, no new workers, no new
event fabric, no new memory store, no new decision engine, no LLM calls (see §12, §13).

### 0.2 The §0 decision rule for schema (binding decision gate)

Before any implementation, §0 must answer exactly one open question:

> Can the existing `simulation_runs` table (Phase 19 `SimulationRun`) persist a
> **deterministic, state-anchored, exact-once** 4H.4 scenario result *without* its
> async worker lifecycle (`queued/running/finished` statuses + `simulation_worker.py`)
> and *without* reshaaping its generic domain semantics?

- If §0 verifies **yes** → 4H.4 adds additive-only columns to `simulation_runs`
  (listed in §3.2) and creates **ZERO** new tables.
- If §0 verifies **no** (worker topology conflict, no state-snapshot keying, lifecycle
  misalignment with the event-anchored exact-once doctrine) → 4H.4 creates **exactly
  ONE** new table, `company_scenario_runs`, with the exact §3.1 column spec below, and
  **no** additive columns on `simulation_runs`.
- The §0 report must state which branch was taken and why, with inspected file/line
  evidence. The acceptance script (§15) must pass under EITHER branch.
- §0 audit finding (2026-08-20): there is NO `simulation_worker.py` in the current
  repository; the SimulationRun lifecycle is synchronous inside
  `app/autonomy/simulation_engine.py` (`SimulationEngine.run` writes
  `running → finished` inline, publishes `simulation.finished`). The §0.2 question
  is therefore decided on the REAL topology, not the drafted premise.

### 0.3 Audit history

- DRAFT v0.1 authored 2026-08-20 from current repository state. Not ratified.
- DRAFT v0.2 2026-08-20 — strengthened per Architectural Review: title re-scoped to
  Decision-Rehearsal Intelligence; Master Vision Constraint added; L9 extended for
  scenarios; scenario-as-canonical-company-primitive; global-scope extensibility;
  "does not pretend to know" honesty boundary; single-ontology/scaling statement.
  Not ratified.
- RATIFIED v0.3 2026-08-20 — final Architectural Review incorporated: **Master Vision
  Constraint — 4H.4** (verbatim, §2); **Scenario Identity Law** (L15, §2/§4.1);
  **Scenario Moat principle** (value from company knowledge, not algorithm
  complexity — §17); four-scale spectrum + large-graph/small-query pipeline (§12);
  comparison-never-ranks kept absolute (§5.6); future-slice identifier contract
  (§4.1); universal VCOS loop as forward direction (§1); expanded hard out-of-scope
  (ERP/CRM/HRMS/autonomous CEO etc. — §19). Ratification record in §0.4.
- RATIFIED v0.3.1 (conformity amendment, 2026-08-20): §3.1 gains explicit
  `scope_type`/`scope_id` columns and the exact-once + listing keys include the
  resolved scope — fulfilling L14/§7.3 ("the resolved scope is stored in the scenario
  row") which §3.1 previously left implicit (scope only inside `state_key`). §0.2
  records the real topology finding (no `simulation_worker.py` exists). No other
  change.

### 0.4 Ratification record (verbatim, 2026-08-20)

> RATIFIED — SLICE 4H.4 v0.2.
> I ratify the SLICE4H4_IMPLEMENTATION_CONTRACT.md v0.2 as the governing contract,
> subject to incorporation of the final Master Vision / Decision-Rehearsal invariants
> stated in the architectural review.
> 4H.4 is authorized only as Strategic Scenario & Decision-Rehearsal Intelligence
> within the existing canonical company-intelligence spine.
> It must extend, not duplicate, the existing company state, causal, risk,
> opportunity, decision, memory and event architecture.
> It must preserve the architectural path toward the Universal Virtual Company OS /
> Virtual Office capable of representing, understanding, coordinating, governing and
> eventually operating the full company lifecycle from small startups through
> globally distributed enterprises.
> 4H.4 must not implement that entire vision.
> No parallel scenario universe, ScenarioGraph, ScenarioMemory, ScenarioAIEngine,
> scenario worker, scenario queue, new simulation engine, new memory store, new
> decision engine or generative simulation path is permitted.
> Scenario intelligence is deterministic, bounded, provenance-traceable, temporally
> anchored, tenant-isolated, advisory-only and never a prediction.
> Scenario comparison presents evidence and consequences but never automatically
> ranks or selects an option.
> Human review remains the decision authority.
> Before implementation, execute the mandatory §0 current-repository audit, make the
> binding simulation_runs versus company_scenario_runs schema decision from actual
> repository evidence, verify the reuse map, and establish clean 4G.7 = 14/14,
> 4H.1 = 16/16, 4H.2 = 19/19 and 4H.3 = 17/17 baselines on one clean server.
> Only after those gates pass may 4H.4 implementation begin.
> No 4H.5 or unrelated feature implementation is authorized by this ratification.

---

## 1. Objective

4H.4 is the company's canonical **Decision-Rehearsal layer**: it lets a human
**rehearse a decision** — ask **"what happens if we change something?"** — and
receive bounded, deterministic, *advisory* consequences composed from the company's
*actual* canonical state and causal relationships — not from a generative model and
not as a forecast.

It sits on the canonical spine:

```
4H.1 Company History → 4H.2 Company Decisions → 4H.3 Living Company State
      → 4H.4 Decision Rehearsal / Scenario Intelligence
      → future: Actions → Outcomes → Learning → Adaptation
```

A scenario is a **canonical company-intelligence primitive**: a reusable, named,
deterministic interpretation over the ONE company graph — never a detached silo,
never a parallel simulation universe. 4H.4 does not create another intelligence
universe; it **interrogates the one that already exists**.

The scenario does not pretend to know the future. It explicitly does **NOT**:
decide anything, forecast outcomes, assign probabilities, rank options, or simulate
beyond dependency propagation.

Core question this slice answers:
> **Given what the company currently is, what bounded consequences should a human
> examine if we change something?**

A CEO asking "what happens if we delay Project A by 30 days?" gets a traversal of
the company's own model — Project A → dependencies → people → resources → customer
commitments → other projects → risks → decisions → opportunities — rendered as the
canonical surface (§5): BASELINE, HYPOTHETICAL CHANGE, DIRECT EFFECTS, DEPENDENT
EFFECTS, RISKS ALREADY PRESENT, OPPORTUNITIES ALREADY PRESENT, DECISIONS THAT SHOULD
BE RECONSIDERED, CAUSAL BASIS, AS-OF SNAPSHOT, HONESTY banner — ending at **HUMAN
DECISION**. A generic AI answers from general knowledge; VCOS answers from the
company's accumulated living institutional model. That is the differentiator.

Forward direction this slice serves (not implemented now): the converging loop
observe/ingest → company state → understand causes → identify risks → identify
opportunities → decisions → **rehearse options (4H.4)** → human decision → action →
outcome → learning → institutional memory → back to company state. Worth is
compounding: the loop is a Virtual Company Operating System, not a collection of
enterprise modules.

---

## 2. Architectural laws (binding)

**Master Vision Constraint (binding, applies to this slice and all future slices).**
VCOS intelligence only grows as a single, compounding understanding — one canonical
trunk: company state → causal dependencies → decisions → outcomes → learning. Every
new slice must attach to this trunk through existing entities, not spawn parallel
tracks. Nothing gets stronger by adding detached artifacts; intelligence compounds
only along honest, measurable paths. 4H.4 must therefore demonstrate its
usefulness as a *scenario-history that becomes company memory* — richer after every
decision/risk/lesson recorded, measurably so via exact-once finite derivations.

**Master Vision Constraint — 4H.4 (binding, verbatim from the ratification review).**
4H.4 is a foundational capability of the Universal Virtual Company OS / Virtual
Office. It must preserve a single canonical company-intelligence representation
capable of progressively representing, understanding, coordinating, governing and
operating the company's entire lifecycle from small organizations through globally
distributed enterprises.
4H.4 shall not implement the entire Universal Virtual Company vision. It shall
implement only bounded Decision-Rehearsal Intelligence. However, every
representation introduced by 4H.4 must remain extensible across future company
capabilities without requiring a parallel scenario ontology, scenario database,
scenario engine, scenario memory or scenario-specific operating system.
Future slices must be able to consume the same canonical company state, entities,
relationships, decisions, actions, outcomes, history and institutional memory rather
than reconstructing company understanding independently.

Carried forward unchanged from ratified contracts: **L1 reuse-first**, **L2 canonical
state is the only source**, **L3 deterministic read paths**, **L4 advisory-before-
action**, **L5 exact-once write doctrine**, **L6 bounded surfaces**, **L7 tenant
isolation + governance**, **L8 append-only temporal truth**, **L9 Virtual Company
Continuity**.

**L9 applied to scenarios (binding interpretation).** A scenario is never an isolated
artifact. Every scenario MUST connect through existing entities to the **living
state** (its `snapshot_ref`), through existing **causal dependencies** (every hop uses
an existing `company_causal_edges` row with `basis`), through existing **decisions**
(advisory reconsideration), through existing **risks/opportunities** (existing probing
lanes), and must remain compatible with later **actions → outcomes → learning** slices
(4H.5+ can grow from scenario rows without redesign — via ids only, no schema surgery).
A scenario that cannot be traced to the company's canonical state is not a scenario;
it is an out-of-scope artifact.

New operational laws for 4H.4:

- **L10 Scenario Honesty (binding).** Every scenario response MUST carry
  `advisory_only: true` and `not_a_prediction: true`. The scenario does not pretend to
  know the future: consequence language is constrained to *"under this hypothetical
  assumption, the existing company relationships indicate these bounded
  consequences."* Prohibited: "will happen", "is likely to", future probability
  scores, confidence-on-outcome, monetized forecasts. Existing risk
  `probability`/`impact` values may be cited only as pre-existing data, never
  recomputed or extended forward.
- **L11 Propagation, not prediction.** A scenario's consequence is the set of
  entities reachable via existing causal edges from the scenario's subject, annotated
  with existing state (risk band, decision state, opportunity kind). No new edges are
  invented; no entity is invented; no probability is generated.
- **L12 Read-only to the decision bridge.** 4H.4 may mark an affected decision as
  `needs_reconsideration` (advisory) only. It never mutates a `CompanyDecision`, never
  writes evidence, never triggers `company.action.executed`, never auto-executes.
- **L13 Scenario Canonicity (binding).** A scenario is one canonical structure —
  `{scenario_kind, subject_type, subject_id, params, assumptions, organization_scope,
  as_of, dry_run}` — every phrased query normalizes onto it. There is NO parallel
  scenario universe: no second graph, no second memory, no second state. Comparison
  is a human relationship over canonical scenarios ("the human decides"), never an
  engine ranking of options.
- **L14 Global-scope extensibility (binding doctrine).** The company model is ONE
  ontology that must extend from a five-person startup to a global enterprise: the
  `scope_type`/`scope_id` spine already accommodates org / business_unit / department
  / team / region / product-line levels. 4H.4 scenarios resolve and honor the caller's
  company scope at every level — a global CEO may explore org-wide scenarios, an
  India regional leader only scenarios within that region. Same spine, same laws,
  no level-specific special cases. Governance is part of the intelligence, not an
  afterthought bolted on. 4H.4 must not introduce any construct that assumes a single
  level of company.
- **L15 Scenario Identity (binding).** A recorded rehearsal is uniquely identified by:
  `organization` + `scope` + `scenario_kind` + `canonical normalized input` +
  `baseline snapshot`. Therefore: same company, same scope, same hypothetical, same
  snapshot → **the same rehearsal** (replayed, zero events); same hypothetical,
  different company state → **a different rehearsal** (new append-only row). This is
  the reproducibility backbone and the exact-once key.

---

## 3. Schema — the exact boundary

### 3.1 ONE new table (contingent on §0.2 "no" branch)

`company_scenario_runs` — append-only scenario history keyed to a 4H.3 state
snapshot. Exact-once on `(organization_id, scenario_kind, input_hash, snapshot_ref)`.
Declared via `create_all`, one row per recorded scenario run, deterministic replay
(byte-identical for identical input + state).

| column | type | note |
|---|---|---|
| `id` | String(32) PK | `gen_uuid` |
| `organization_id` | FK organizations CASCADE | tenant |
| `scope_type` | String(24) | resolved company scope level (`COMPANY_SCOPE_TYPES`, L14) |
| `scope_id` | String(32) | resolved scope key (org id / department id / team id / ...) |
| `state_key` | String(140) | `st:<org>:<scope>:<seq>` of the baseline 4H.3 snapshot |
| `snapshot_ref` | String(64) | `source_event_id` of the baseline snapshot (4H.3) |
| `scenario_kind` | String(32) | sanctioned §7.1 kinds |
| `input_json` | JSON | normalized scenario inputs (whitelisted keys only, §7.1) — the single canonical scenario structure |
| `input_hash` | String(64) | deterministic hash of `(scenario_kind, input_json)` for exact-once |
| `assumptions_json` | JSON | human-declared assumptions echoed verbatim |
| `propagation_json` | JSON | bounded hops walk (bounded by MAX_CAUSAL_DEPTH/EDGES), each hop = existing edge (type/id/label/kind/confidence) + reached entity |
| `consequences_json` | JSON | bounded merged consequence surface (entities, risks, opportunities, decisions) with per-item `basis: {edge_id, source_id, target_id, relation}` — every consequence traces to an existing edge |
| `decision_suggestions_json` | JSON | affected decisions → `{decision_id, state, why: needs_reconsideration, advisory}` (read-only) |
| `honesty_json` | JSON | `{"advisory_only": true, "not_a_prediction": true, "mode": "bounded-scenario"}` |
| `source_event_id` | String(64) | exact-once key (event-anchored) |
| `created_by` | String(32) | user id |
| `occurred_at` | DateTime tz | event time (as-of anchor) |
| `created_at` / `updated_at` | DateTime tz | TimestampMixin |

Unique constraint names: `uq_c4h4_exact_once` over
`(organization_id, scope_type, scope_id, scenario_kind, input_hash, snapshot_ref)`,
index `ix_c4h4_org_time` over `(organization_id, scope_type, scope_id, occurred_at)`.
No worker table, no queue table, no status columns (deterministic synchronous
derivation only — mirrors the 4H.3 no-dispatch-dependency doctrine).

### 3.2 Additive-only columns (contingent on §0.2 "yes" branch)

If §0.2 selects reuse: additive columns on `simulation_runs` — `scenario_kind`,
`state_key`, `snapshot_ref`, `input_hash`, `honesty_json`, `decision_suggestions_json`,
`exact_once_source_event`. The async status lifecycle is NOT used for 4H.4 results
(results are written `finished` at derivation time by the engine, never by the worker).
No other columns anywhere.

### 3.3 Explicit non-moves

- NO new columns/tables for probability distributions, Monte Carlo state, forecast
  series, prediction models, or scenario ensembles.
- NO table for "scenario-to-outcome calibration results" — the 4H.4 learning hook
  (§4.1) links scenario rows to existing `company_decision_tracks` / outcome events via
  ids only; it stores nothing.
- NO "ScenarioGraph", no "ScenarioMemory", no `scenario_worker`, no `scenario_queue`,
  no "ScenarioAIEngine", no scenario-model tables. A scenario is a named,
  deterministic **interpretation over the existing company graph** — nothing in 4H.4
  is a second graph, second memory, or second state.

---

## 4. Scenario lifecycle (append-only, deterministic)

```
human asks "what if ..."
        ↓
normalize inputs (whitelist §7.1)          -- no free-form schema; one canonical
        ↓                                     scenario structure {kind, subject,
        ↓                                     params, assumptions, organization_scope,
capture human-declared assumptions         -- echoed verbatim, never invented
        ↓
resolve company scope (organization_id + scope_type/scope_id; caller governance)
        ↓
anchor to baseline state snapshot (current or as_of §7.1)
        ↓
walk causal edges from the subject (MAX_CAUSAL_DEPTH=5, MAX_CAUSAL_EDGES=60)
        ↓
annotate reached entities with EXISTING state (risk band / decision state / opportunity kind)
        ↓
merge into bounded consequence surface (MAX_WHATIF_CONSEQUENCES=5; totals bounded)
        ↓
mark affected decisions needs_reconsideration (read-only)
        ↓
persist ONE row (exact-once on input_hash + snapshot_ref)      -- or reuse simulation_runs per §0
        ↓
publish ONE event `company.scenario.recorded`                  -- ONLY on an actual write
        ↓
return advisory_only + not_a_prediction surface
        ↓
HUMAN REVIEW STOP — the flow ends here. Nothing in 4H.4 proceeds toward action,
execution, or autonomous decision. The human weighs the advisory surface against
the external world and decides.
```

Replay of the identical `(scenario_kind, input, snapshot_ref)` returns the persisted
row unchanged (created:false/`replayed:true`, zero events). A changed input or a newer
snapshot composes a new row. Reads and replayed runs emit zero events.

### 4.1 Learning hook (design constraint)

Two distinct applications of scenario, kept honest by construction:

- **Dry-run = exploration (`dry_run=true`).** Derive, display, discard. Zero
  persistence, zero events. The sandbox for "show me".
- **Recording = institutional memory (`dry_run=false`).** An append-only scenario row
  becomes part of the company's history — a named point-in-time interpretation the
  company can revisit, trace, and later compare against reality. This is the moat:
  scenarios accumulate as memory.

Scenario rows carry `snapshot_ref` + the subject ids, so after outcomes occur
(`company.outcome.recorded`, `company_decision_tracks`), a later slice may join
scenario→actual as calibration. 4H.4 itself performs NO such comparison, assigns NO
scores, and stores NO derived truth from it. This keeps the moat honest and
difference-measurable later.

**Future-slice identifier contract (L15/L9, binding for 4H.4's output shape).**
Every recorded rehearsal must expose these identifiers to be consumed by later
slices without redesign: `scenario_id`, `snapshot_ref`, `subject_id`, `decision_id`,
`risk_id`, `opportunity_id`, `causal_edge_id`. The intended chain, becoming possible
without touching 4H.4:

- 4H.5 Action Intelligence: "convert this approved human decision into an action."
- 4H.6 Outcome Intelligence: connect scenario → decision → action → outcome.
- Later learning: compare **what was rehearsed** vs **what actually happened**
  (rehearsed consequence rows vs outcome rows, joined by these ids).

This is how the canonical spine compounds. It also becomes **organizational decision
memory**: what the company considered, under what assumptions, against what state,
with which consequences — and later, which decision humans actually made, which
action occurred, which outcome occurred. If proven wrong, an orderly difference is
seen; no calibration truth is pretended until outcomes exist.

---

## 5. Read laws (binding)

1. A scenario result depends only on the baseline snapshot + inputs + existing
   causal edges — byte-identical on replay (re-query must equal the stored row).
2. Every consequence is provenance-traced: it cites `basis: {edge_id, source_id,
   target_id, relation}` pointing at a pre-existing `company_causal_edges` row (or a
   state risk/opportunity/decision row). No invented entities, no graph mutation
   (`company_causal_edges` is never written by 4H.4). A consequence that cannot name
   its basis is not emitted.
3. The consequence surface has ONE canonical shape, human-readable and bounded —
   rendered with exactly these sections:
   - **BASELINE** (current company snapshot the scenario anchors to),
   - **HYPOTHETICAL CHANGE** (the canonical normalized inputs + assumptions echoed
     verbatim),
   - **DIRECT EFFECTS** (subject-touching entities),
   - **DEPENDENT EFFECTS** (entities reached via ≤ MAX_CAUSAL_DEPTH hops),
   - **RISKS ALREADY PRESENT** (existing risk bands, cited unchanged — never
     recomputed),
   - **OPPORTUNITIES ALREADY PRESENT** (existing opportunity kinds),
   - **DECISIONS THAT SHOULD BE RECONSIDERED** (`needs_reconsideration` advisory
     list, read-only),
   - **CAUSAL BASIS** (the walked existing edges),
   - **AS-OF SNAPSHOT** (`snapshot_ref` used),
   - **HONESTY** (`advisory_only: true` + `not_a_prediction: true`),
   - and the response ends at **HUMAN DECISION** — no option is presented as chosen;
     the human decides.
4. All surfaces bounded (§12). `as_of` uses the 4H.3 strict-as-of semantics (never
   composes post-epoch state into a scenario).
5. `advisory_only` + `not_a_prediction` present on every surface and every stored
   honesty record (asserted in tests).
6. Comparison (`/compare`) is a side-by-side human relationship: it presents baselines
   and deltas only. It NEVER ranks, scores, or orders scenarios as better/worse — the
   human decides.

---

## 6. Events (exact names, exact-once)

Exactly ONE event added to `EVENT_CATALOG` (event_models.py) and emitted only when a
scenario row is actually written:

`company.scenario.recorded` — payload: `{organization_id, scenario_id, snapshot_ref,
scenario_kind, consequences_count, not_a_prediction: true, advisory_only: true}`.

Emission rule: emitted in the same transaction path as the row write, once. Reads,
replays, rejected/duplicate runs, and changes that produce no new row emit zero.
(background-audit stream ack handler `handle_company_universal_audit`, extended with
zero recompute — same doctrine as the 4H.3 ack.)

---

## 7. API + brain routing

### 7.1 Surfaces (`brain:read`, org-wide `_people_access` → 404 for scoped callers)

- `POST /execution/company/scenario` — construct + record + run one scenario.
  Body: `{scenario_kind, subject_type, subject_id, params{}, assumptions[],
  organization_scope?, as_of?, dry_run?}` (organization_scope is resolved from the
  caller's identity + subject per §7.3, never caller-declared authority). Whitelisted
  param keys (reuse what-if vocabulary): `project_id,
  days, capability, from_project_id, to_project_id, units, people, ramp_days,
  duration_days, resource_id, customer_id, decision_id`. Sanctioned kinds: the
  existing `WHATIF_SCENARIOS` ("reallocate" | "delay" | "hire") plus contract-sanctioned
  `"resource_loss"` | `"dependency_break"` | `"decision_reconsider"` resolved by the
  SAME derivation functions (causal walk + what_if) — no new engine. `dry_run=true`
  derives and returns without persisting (zero events) — the honest "show me" path.
  Returns the §4-compliant surface.
- `GET /execution/company/scenario/{scenario_id}` — re-query; byte-identical to the
  stored row; `replayed:true`; zero events.
- `GET /execution/company/scenario` — bounded history list (≤ `MAX_SCENARIOS_SHOWN`,
  newest first; summary shape only).
- `POST /execution/company/scenario/compare` — body `{scenario_ids: [2..5]}` → baseline
  (current 4H.3 snapshot) vs each scenario: side-by-side bounded consequence deltas.
  Read-only, advisory-only, deterministic ordering by scenario_id.

### 7.2 Brain intents (additive phrases only, resolved inside `_company_operating_query`)

New phrase rules (registered ADDITIVELY — every existing rule + its routing stays
untouched and is regression-tested):

- `company_scenario` — "what happens if", "what if project X remains", "if we lose
  resource", "scenario", "simulate losing", "consequences of", "what could happen if".
  Collision guard mandated: generic "what if we reallocate/delay/hire" MUST still
  resolve to the existing 4G.7 what-if intent (unit-tested).
- `company_scenarios_compare` — "compare scenarios", "which option", "scenario A vs",
  "baseline vs".

### 7.3 Governance (L7 + L14: scope is a resolved, normalized part of the scenario)

- Reads: `brain:read` + org-wide (scoped → 404, never leak).
- Record (`dry_run=false`): `brain:manage` + org-wide.
- Tenants: every query/write is `organization_id`-scoped; org B can never read org A
  scenario ids (404).
- Company scope (L14): the scenario resolves `organization_scope`
  (`scope_type`/`scope_id`) from the caller's identity and the requested subject.
  A scoped leader (regional, business-unit, team) may only run scenarios whose
  subject falls inside their own scope — never org-wide or sibling-scope subjects.
  The resolved scope is stored in the scenario row and drives that row's governance
  surfaces (same scoped-shadowing approach as 4H.3's state).

---

## 8. Brain intents / routing placement

As §7.2. Implementation must live inside the existing `_company_operating_query`
branch ordering after the 4H.3 block, calling existing engine methods — no new
top-level query handler class.

---

## 9. Frontend (minimal, read-only)

Extend ONLY `frontend/app/(app)/execution/company-tab.tsx` and `frontend/lib/api.ts`:
a scenario form (kind + subject + params) rendering the bounded consequence surface
with the honesty banner ("advisory only — not a prediction"), and a read-only compare
view. No new pages, no state mutation UI, no new API client module.

---

## 10. Governance, tenants, and the :8999 trap

- Single clean server for acceptance; one fresh org per scenario run session; accept
  scripts must prove org B cannot resolve org A scenario ids (404) and that scoped
  callers see 404 (never 403/leak).
- No stacked background workers introduced; scenario derivation is synchronous and
  event-anchored in the request/engine path (no `dispatch` dependency, same doctrine
  as 4H.3 state composition).

---

## 11. Freshness

Scenario always anchors to the newest 4H.3 snapshot (or an explicit `as_of`); the
response includes the `snapshot_ref` used. If the snapshot is older than `STATE_TTL`
the 4H.3 TTL recompose runs first (reusing its exact path); scenario derivation never
triggers state writes of its own.

---

## 12. Scale law — four company scales, and "large graph, small query" (5 → global)

Scale is not "database can store millions of rows". 4H.4 must serve FOUR company
scales through ONE ontology, ONE spine, ONE set of bounds — no per-scale system:

- **Scale 1 — Small startup** (~5 people, 2 projects, 1 founder, 20 decisions):
  "What happens if I move Rahul from Project A to Project B?" — simple surface,
  full company context understood.
- **Scale 2 — Growing company** (~200 people, 30 projects, teams, thousands of
  dependencies): the same question becomes "Engineering capacity moves from
  Product A to Product B" — propagation crosses team → project → milestones →
  customer commitments → resources → risks → decisions. No separate
  "enterprise scenario system" appears.
- **Scale 3 — Enterprise** (20k people, business units, regions, millions of
  relationships): a regional VP must not see the entire company. Resolution chain:
  Global Company → Region → Business Unit → Department → Team → Project — governance
  (L14) determines what the user is allowed to see.
- **Scale 4 — Global corporation** (Americas/Europe/India/APAC/Middle East): still
  ONE COMPANY ONTOLOGY + SCOPE-AWARE GOVERNANCE + BOUNDED QUERY. Never
  "US Scenario Engine / Europe Scenario Engine / India Scenario Engine / ...".

"Large graph, small query" — even at 10M+ entities and 100M+ relationships, one
interaction never traverses everything. Every scenario query follows exactly this
pipeline:

```
identity → organization scope → subject → bounded causal neighborhood (≤60 edges)
        → bounded consequences (≤5) → human-readable canonical surface
```

e.g. 10,000,000 entities → scope resolution → 1 division → 1 project → ≤60 causal
edges → ≤5 consequence surface. This keeps the system scalable AND explainable:

- Propagation hops ≤ `MAX_CAUSAL_DEPTH` (5); explored edges ≤ `MAX_CAUSAL_EDGES` (60).
- Consequences ≤ `MAX_WHATIF_CONSEQUENCES` (5) per surface; totals capped in
  consequences_json; history list ≤ `MAX_SCENARIOS_SHOWN` (10).
- Compare set size `2..5`.
- All list/compare queries LIMIT + ORDER BY id/indexed columns (`ix_c4h4_org_time`).
- No cross-scenario aggregation, no global ordering.
- Scope-indexed reads: every scenario query early-resolves `(organization_id,
  scope_type, scope_id)` before any derivation (same scoped-shadowing path 4H.3 uses).

---

## 13. Anti-duplication rules (binding)

- **Zero** new engines: no scenario engine, no simulation engine, no forecasting
  engine, no AI simulation service, no new decision engine, no new memory/event/causal
  module. All derivation extends the existing `company_operating_engine` methods
  (`what_if`, `causal_chain`, `state_*`).
- **Zero** new workers/queues; zero AI model calls inside derivation.
- The state/decision/risk/memory stores stay canonical and single. A scenario is an
  **interpretation** over the ONE company graph — it is never a second graph, second
  memory, or second state (see forbidden artifact names in §3.3).

---

## 14. No-OpenAI / determinism guarantee

Scenario surfaces are produced by deterministic queries over canonical rows and
causal edges. The acceptance/unit tests assert `not_a_prediction: true` + byte-identical
replay + that no LLM client is imported/used on the scenario derivation path.

---

## 15. Acceptance tests (`backend/scripts/accept_slice4h4.py`, live on :8999)

Drafted check list (each maps to a law; final list fixed at implementation time by
this §15 of the ratified contract — this is the target):

1. Baseline capture: scenario anchored to a real 4H.3 `snapshot_ref`.
2. `dry_run=true`: derived surface honors `advisory_only`/`not_a_prediction`, writes
   nothing, emits zero events.
3. Record + re-query: byte-identical, `replayed:true`, zero events on the re-query.
4. Propagation bounded: hop count ≤ MAX_CAUSAL_DEPTH; every hop cites an existing
   edge/entity id (`basis`).
5. Honesty: consequence language constrained; no "will happen"; risk bands reused
   unchanged.
6. Decision bridge: subject change that traverses a decision-anchored entity yields
   `needs_reconsideration` (advisory); `company_decisions` row is byte-unchanged.
7. Compare: 2-5 scenarios vs baseline side-by-side; deterministic order; advisory.
8. Tenant isolation: org B scenario-id lookup → 404; scoped caller → 404, never leak.
9. Exact-once: duplicate input+snapshot → persisted row reused, zero new events.
10. Event truth: only `company.scenario.recorded` on real writes; reads/replays/rejects
    emit zero.
11. Reuse audit: asyncpg introspect shows §0-selected branch (either the ONE new
    `company_scenario_runs` table with §3.1 columns, or additive `simulation_runs`
    columns) and NO scenario/forecast/simulation engine modules.
12. Moat/L9: scenario history is append-only and each row references a state snapshot;
    after further company events the baseline snapshot is still reproducible via 4H.3
    as_of (temporal grounding holds).
13. Regression within the slice: existing `POST /execution/company/what-if` and
    `company/decisions/{id}/what-if` responses byte-unchanged.
14. Brain intents: `company_scenario` + `company_scenarios_compare` resolve; generic
    "what if we reallocate/delay/hire" still routes to existing what-if.
15. Scenario Identity (L15): identical org+scope+kind+input+snapshot → the SAME
    rehearsal (replayed row, zero events); the same hypothetical on a CHANGED
    snapshot → a NEW rehearsal row.

Exit code 0 only when all pass.

---

## 16. Unit tests (`backend/tests/test_4h4_engine.py`)

Determinism + exact-once, honesty flags on every surface, propagation bounds, decision
bridge read-only, tenant isolation, as_of strictness, replay byte-equality, compare
bounds, AND negative tests: LLM never called, `company_causal_edges` never written,
`CompanyDecision` never mutated, no new engine instantiated.

---

## 17. Moat test (law: compounding dependence — Master Vision Constraint)

**The Scenario Moat (binding principle).** *The value of 4H.4 must increase primarily
because VCOS knows more about the company, not because the scenario algorithm becomes
more complicated.* Day 1: "Delay A" over 2 projects / 3 dependencies / 2 risks /
1 decision → 2 affected entities. Six months later: "Delay A" over 50 projects /
400 employees / 120 resources / 80 customers / 700 dependencies / 150 decisions /
200 risks / 300 opportunities / thousands of historical outcomes → project,
people, customer, and resource dependencies; existing risks; affected decisions;
opportunities; historical context. The engine never became an AI supercomputer; the
**company model became richer**. That is the moat — and it is exactly what a
conventional scenario tool cannot reproduce.

The moat check proves scenario usefulness compounds with company history:
- T1: capture scenario consequences for a subject on empty-ish state (few edges).
- T2: grow state (new decision anchored to a reachable entity, new risk, new run).
- T3: the SAME scenario after growth surfaces MORE affected entities/decisions
  (strictly greater or equal, never less) and still anchors to a 4H.3 snapshot —
  proving scenario intelligence becomes richer as company understanding does, without
  any change to scenario code.
- T4: the scenario history itself accumulates as institutional memory (T1/T2/T3 rows
  append-only, replayable byte-identical, traceable to their baseline snapshots) —
  the recorded scenario stream becomes *company memory* the way decisions and lessons
  do, which is the compounding dependence the Master Vision Constraint demands.

---

## 18. Definition of DONE

Architectural DONE (each element asserted by acceptance + unit tests + the §0 audit):

- **Canonicality (L13):** every scenario normalizes onto the single canonical
  structure; zero parallel universes.
- **Determinism:** identical input + identical snapshot → byte-identical surface and
  stored row; replay equals re-query.
- **Temporal truth (L8, 4H.3):** every scenario anchors to a real `snapshot_ref`
  reproducible via 4H.3 as_of; strict-as-of honored.
- **Honesty (L10):** `advisory_only: true` + `not_a_prediction: true` on every surface
  and every stored row; no future language, no recomputed probabilities.
- **Governance (L7 + L14):** tenant isolation (404 never leak), scoped callers
  restricted to their own `organization_scope`, record requires `brain:manage`.
- **Non-interference (L11/L12):** no graph mutation, no `CompanyDecision` mutation,
  no `company.action.*`, no autonomous step.
- **Exact-once (L5) + Scenario Identity (L15):** one row per
  `(org, scope, kind, input_hash, snapshot_ref)`; `company.scenario.recorded` once per
  actual write, zero events on reads/replays; same hypothetical on changed state →
  new rehearsal.
- **Provenance:** every consequence names its `basis` (existing edge/row ids).
- **Read-only bridge (L12):** decision suggestions are advisory objects only.
- **Moat (Master Vision Constraint, L9):** T1–T4 pass; scenario history compounds as
  memory; scenario rows remain joinable (ids only) for future action→outcome→learning
  slices without schema surgery.
- **Scale (L6/L14):** bounds enforced (depth 5 / edges 60 / consequences 5 / list 10 /
  compare 2..5); indexed, scoped reads; large-graph/small-query path proven.
- **Future extensibility:** 4H.5+ scenario→decision→action→outcome→learning fits
  without redesign (documented in §4.1; §0 audit confirms no construct blocks it).

Process DONE:

- §0 audit (12-row checklist incl. the §0.2 branch decision) green; no blockers.
- Implementation confined to the files §6-§15 name; exactly ONE event; §0-branch
  schema; zero new engines/workers; zero LLM calls.
- `test_4h4_engine.py` green; `accept_slice4h4.py` 15/15 (final ratified list).
- Regressions green: 4G.7 14/14 · 4H.1 16/16 · 4H.2 19/19 · 4H.3 17/17 live;
  full pytest; frontend `tsc --noEmit` exit 0.
- Schema introspection confirms the §0.2 branch only; event catalog shows exactly one
  new event; git diff shows no scope creep; anti-duplication audit clean.

---

## 19. Out of scope (hard boundary)

4H.4 is a narrow capability — rehearsing bounded hypothetical changes against the
living company model — and that narrowness is what makes it safe to build. Explicitly
NOT attempted by 4H.4:

- ERP, CRM, HRMS, or a ServiceNow replacement as a complete feature set;
  project-management replacement; autonomous CEO; autonomous decision maker.
- Stock-market / generic business forecasting; unrestricted ML prediction; a
  forecasting platform; a Monte Carlo platform; a generic AI simulation engine;
  unrestricted business prediction.
- Probability distributions, Monte Carlo infrastructure, ensembles, "confidence in
  outcome" scoring.
- Autonomous strategic decision making / autonomous execution (no execution, no
  `company.action.*` writes, no auto-selection of options).
- A general simulation/AI platform or a new simulation service.
- Scenario-to-outcome calibration/scores (future slice; 4H.4 stores only linkage ids).
- Separate scenario memory, scenario graph, scenario worker, scenario queue, or
  scenario intelligence engine; any new engine, worker, event fabric, memory store,
  or generative path.
- Any per-scale or per-region scenario system (Scale 4 is ONE ontology, not engines
  per geography).

These are future architectural territories. 4H.4's job: make the existing company
intelligence capable of rehearsing bounded hypothetical changes against the living
company model.

---

*Ratified as the governing contract for SLICE 4H.4 v0.3 (2026-08-20). The mandated
verification gates now begin: §0 CURRENT-REPO AUDIT → REUSE + SCHEMA DECISION →
clean 4G.7/4H.1/4H.2/4H.3 BASELINES → IMPLEMENT 4H.4 ONLY. 4H.3 remains frozen.*