# SLICE 4H.3 — Living Company State

**Status: RATIFIED by architect of record (2026-08-20).**
**Repos: `D:\workspace\vcos` (contracts at repo root; backend `backend\`, frontend `frontend\`).
**Supersedes: nothing. Builds on: 4G.7 (ratified, 14/14 live), 4H.1 (ratified, 16/16 live), 4H.2 (ratified, 1094/1094 full suite, 19/19 live acceptance).**

> This document is the formal **ratified** contract for Slice 4H.3.
> Ratified by the architect of record on 2026-08-20 following the architect
> review and the v2 amendments (Master Vision Constraint + L9). Approval to
> begin implementation given; no contract changes may be made during
> implementation without a new audit entry.

---

## 0. Mandatory analyze-then-extend step (do not skip)

Before writing any 4H.3 code, the implementer MUST re-run the analysis below
against the **current** repository state (the repo — not this document — is
the only truth) and confirm every row of the reuse table still holds. Drift
found in this step **blocks** 4H.3 work until resolved.

Analysis re-run checklist:

- [ ] `backend/app/models/company_operating.py` still defines `CompanyDecision`,
      `CompanyHealthHistory`, `CompanyCausalEdge`, `CompanyDecisionAlternative`,
      `CompanyDecisionEvidence`, `CompanyDecisionPrecedent`,
      `CompanyDecisionQuality`, `CompanyDecisionTrack`,
      `CompanyDecisionContradiction`, with `DECISION_STATES`
      (proposed…assessed), `COMPANY_SCOPE_TYPES`, `CAUSAL_EDGE_KINDS`,
      `DECISION_EVIDENCE_TYPES`, `CONTRADICTION_STATUSES`, and the MAX_*
      bounds.
- [ ] `backend/app/intelligence/company_operating_engine.py` still has
      `health()`, `changes()`, `temporal_state()`, `causal_chain()`,
      `_derive_causal_edges()`, `what_if()`, `what_happens_if()`,
      `evaluate_decision()`, `recommend_decision()`, `_decision_row()`,
      `_metric_keys_from_evidence()`, `decision_what_if()`,
      `decision_precedents()`.
- [ ] `backend/app/events/event_models.py` still catalogues
      `company.health.recomputed`, `company.causal_edge.refreshed`,
      the 8 `company.decision.*` names, and the 4H.1 audit names 4H.3 builds
      on.
- [ ] `backend/app/events/handlers.py` (4G.7 bridge section ~line 3091) still
      obeys "the bridge never publishes its own events"; 4H.1/4H.2 audit
      handlers still ack without recompute.
- [ ] `backend/app/knowledge/intelligence_engine.py` `_company_operating_query`
      and `_INTENT_RULES` still route deterministically with the scoped-caller
      early return; `decision_reason` / `decision_alternatives` /
      `company_operating` / `company_universal` intents still resolve.
- [ ] `backend/app/api/v1/brain.py` still gates reads with `brain:read`,
      writes with `projects:manage`, and both with org-wide `_people_access`
      (scoped → 404).
- [ ] `backend/app/models/company_memory.py` remains the ONE canonical memory
      store; 4H.3 adds no second memory table.
- [ ] `backend/app/models/approval.py` `Risk` (project_id FK, status,
      probability, impact, risk_score) and `backend/app/models/prediction.py`
      or `knowledge_recommendations` decision linkage still exist as the risk/
      opportunity reuse anchors.
- [ ] Re-run 4G.7 + 4H.1 + 4H.2 acceptance (`accept_slice4g7.py`,
      `accept_slice4h1.py`, `accept_slice4h2.py`) against a SINGLE clean
      server on :8999 — 14/14, 16/16, 19/19 must stay green before and after
      4H.3 lands (stacked-worker contamination on :8999 is a known trap —
      see §9).
- [ ] `git log --all -i --grep="4h.3"` must stay empty; the 4H.2 contract's
      out-of-scope section names 4I-4Q, never 4H.3 — if that changes, this
      contract must be reconciled first.

### 0.1 Reuse map (binding) — what 4H.3 reuses, what it adds

| Capability | Reused (never duplicated) | Added by 4H.3 |
|---|---|---|
| Company state trail | `CompanyHealthHistory` exact-once temporal trail + `temporal_state()` (4H.1) | `company_state_history` — the broader living-company snapshot trail (§3.1); the ONLY new table |
| What changed / why | 4H.1 `changes()` + `company.health.recomputed` + attention machinery | State delta composition (row-vs-previous deterministic diff of signals) |
| Dependency graph | `CompanyCausalEdge` + `causal_chain()` + `_derive_causal_edges()` (4H.1) | **No new causal engine and no new edge table.** Additive `CAUSAL_EDGE_KINDS` entries derived from existing rows (`risk->project`, `constraint->project`, `opportunity->decision`, `decision->process`) |
| Risk exposure | `Risk` rows (approvals model; project_id, probability, impact, status) | Deterministic exposure composition (probability×impact → LOW/MEDIUM/HIGH, open-status only) |
| Opportunities | 4D patterns/insights (`pattern_detections`, `UniversalInsight`) and `knowledge_recommendations` | Derived, bounded, transparent opportunity surface (top-N; no new engine) |
| Affected decisions | 4H.2 decision store + evidence + `state_context` bridge | `state_context_json` additive column (§3.2) — the decide-time anchor; affected-decision derivation |
| Decision context bridge | 4H.2 `evaluate_decision` / `as_of_context_json` | `POST /decisions/{id}/state-context` write (exact-once, changed-only) + state-aware reads |
| What could happen next | `what_if()` / `what_happens_if()` bounded simulators (4G.7) | Advisory `next` block in the state surface (per-confidence consequences, never predictions) |
| Event fabric | `events/publisher.publish_event`, `EVENT_CATALOG`, handlers bridge | Two new event names (§6) — same bridge, no second bridge |
| Brain routing | `_INTENT_RULES` + `_company_operating_query` routing | New intents/keywords: `company_state`, `company_changes`, `company_dependencies`, `company_risks`, `company_opportunities` |
| API + permissions | `brain.py` `/execution/company/*` pattern; `brain:read` reads; `projects:manage` writes; `_people_access` org-wide gate | New state endpoints (§7.1) — same gates, zero new access code |
| Multi-level scopes | `COMPANY_SCOPE_TYPES` + 4H.1 scope machinery | State snapshots parameterized the same way (org canonical; scoped rows only for attention-worthy deviations, bounded per event) |
| Frontend | existing company tab + `frontend/lib/api.ts` helpers | Read-only "Living Company State" panel (§8) |
| Temporal as-of | 4H.1 `as_of` semantics + `ix_chh_*`/exact-once pattern | Same strict/partial as-of on state reads — byte-identical replay |
| Lessons | `CompanyMemory` + `record_decision_lesson` (4H.1/4H.2) | State deltas cite lesson/memory ids where they changed the reading |

**No new module anywhere**: 4H.3 lives inside existing files —
`models/company_operating.py` (one new table + additive column),
`company_operating_engine.py` (methods), `event_models.py` (two names),
`handlers.py` (extended bridge section), `intelligence_engine.py` (routing),
`api/v1/brain.py` (routes), `scripts/accept_slice4h3.py` (new acceptance
script), plus the existing company tab + `lib/api.ts`.

### 0.2 Audit history

- **v1 (PROPOSED, 2026-08-19)** — pre-ratification contract-only audit
  against the live 4E–4H.2 codebase. All §0.1 reuse claims re-verified
  against current code (models, engine methods, event catalog, handlers
  bridge doctrine, intent routing, brain permission gates, `Risk` rows,
  `pattern_detections`/`UniversalInsight`, `CompanyCausalEdge` + causal
  chain, canonical `CompanyMemory`). Blocking issues addressed in this
  revision: (1) the state trail must be append-only exact-once snapshots
  (per source event), NOT a mutable materialized view — the 4H.2 §3.5
  temporal law is carried forward (§5.1); (2) the state surface carries
  observed ≠ derived ≠ predicted ≠ recommended ≠ authorized ≠ executed ≠
  outcome faithfully (every block typed, no naked numbers, §5.3);
  (3) affected-decisions derivation is bounded and deterministic (no
  embedding, no free text scoring, §5.4); (4) the dependency surface reuses
  the 4H.1 causal walk (additive kinds only) instead of a second graph;
  (5) `company.state.changed` is emitted ONLY when a real delta exists
  (event truth, §6). The contract remains **PROPOSED** — no implementation.
- **v2 (PROPOSED, 2026-08-20) — contract-only, per architect review** —
  two amendments adopted with no schema/table/event/surface changes and no
  new functionality: (1) **Master Vision Constraint** statement added to
  §1 — 4H.3 is a foundational slice toward the Universal Virtual Company /
  Virtual Office vision, not the vision itself; it must preserve the
  architectural possibility to progressively represent, understand,
  coordinate, govern, and operate the full organization through one
  temporally grounded company-intelligence layer; later slices extend the
  §3 spine, never replace it; (2) **L9 Virtual Company Continuity** law
  added to §2 — every new 4H.3 capability composes with existing state,
  decisions, dependencies, risks, opportunities, actions, outcomes, and
  memory through the canonical representations (L1/L2), so no feature
  becomes an isolated silo when a canonical representation can be extended.
  The contract remains **PROPOSED** — no implementation.
- **v3 (RATIFIED, 2026-08-20)** — ratified by the architect of record. The
  Master Vision Constraint and L9 from v2 are carried forward unchanged.
  Implementation begins under the contract's exact §0 sequence: re-analyze
  repo → verify reuse map → re-run 4G.7/4H.1/4H.2 baselines on a single
  clean :8999 server → implement only 4H.3 → unit tests → live acceptance
  → regression → architecture/diff audit → DONE.

---

## 1. Objective

4H.2 made the decision lifecycle-aware. 4H.3 makes each decision — and each
human reading a company surface — aware of the **changing state of the
company** that surrounds it:

```
                COMPANY STATE
                      │
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
      PEOPLE        WORK         RESOURCES
        ↓             ↓             ↓
   PROCESSES      OUTCOMES      CONSTRAINTS
        └─────────────┼─────────────┘
                      ↓
               OBSERVE → UNDERSTAND → REASON
                      ↓
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
   DECISIONS        RISKS       OPPORTUNITIES
        └─────────────┼─────────────┘
                      ↓
                  ACTIONS → OUTCOMES → LEARNING
                      ↓
            UPDATED COMPANY STATE
```

**Master Vision Constraint.** VCOS is the company-intelligence layer of a
larger vision: a Universal Virtual Company and Virtual Office in which a
founding team can represent, understand, coordinate, govern, and operate
the full lifecycle of an organization — every state, decision, dependency,
action, and outcome — through ONE temporally grounded company-intelligence
layer. 4H.3 is a **foundational slice toward that vision, not the vision
itself**: it must NOT implement the company-wide whole (no HR, no CRM, no
ERP, no org-wide scheduler, no universal state model beyond §3). It must
preserve the architectural possibility of the vision — so that later slices
extend canonical state, decisions, dependencies, actions, outcomes, and
learning through this same layer, and never create disconnected silos
(L9). Every 4H.3 table, event, and surface is therefore designed as an
extensible spine: a temporal trail (§3.1) that later slices may widen with
additive fields, not a closed feature.

The slice composes — deterministically, from existing canonical rows — a
snapshot answering the eight living-state questions:

1. **What is happening?** — state dimensions (people / work / resources /
   processes / outcomes) with evidence counts.
2. **What has changed?** — deterministic delta vs the previous snapshot
   (added/changed signals, edges refreshed, memory ids cited).
3. **Why did it change?** — contributing signals (event ids, pattern/insight
   ids, causal-edge refs).
4. **What depends on it?** — dependency walk via the existing 4H.1 causal
   chain, bounded depth.
5. **What is at risk?** — open `Risk` rows composed into exposures
   (probability × impact, deterministic band), linked to affected projects/
   customers/decisions through existing edges.
6. **What decisions are affected?** — pre-approval/active decisions whose
   evidence or state-context intersects the delta (bounded, deterministic).
7. **What could happen next?** — bounded, advisory-only what-if consequences
   (never predictions).
8. **What should humans consider?** — attention items reusing 4H.1
   attention language.

A decision evaluated under 4H.2 gains a **state-context anchor**
(`state_context_json`, additive column) so "why did we decide this" can be
replayed against "what the company knew then" — the 4H.2 → 4H.3 bridge.

## 2. Architectural laws (binding)

- **L1 Reuse-first** — every capability that exists in 4A–4H.2 is extended,
  never duplicated: one causal graph, one memory store, one event fabric,
  one decision store, one brain router. 4H.3 adds exactly ONE table.
- **L2 Canonical state** — the living state is a composed read over
  canonical rows plus an exact-once snapshot trail; the trail is
  append-only, never mutated by later events.
- **L3 Temporal truth** — as-of reads return the snapshot composition
  knowable at that instant, byte-identical on replay (4H.2 §3.5 law
  carried forward).
- **L4 Observed ≠ derived ≠ predicted ≠ recommended ≠ authorized ≠
  executed ≠ outcome** — every surface block is typed; predictions and
  scenarios carry `not_a_prediction`/`advisory_only`, every cited fact
  carries its id (no naked numbers, no opacity) — 4H.2 suite-wide
  invariants (a)-(c) extend to every 4H.3 response.
- **L5 Event truth** — a state-transition or new-row write publishes its
  audit event; a read, a no-op, or a rejected write never does.
- **L6 Bounded hood** — every surface is bounded (MAX_* caps, top-N),
  identical schema 5 → 50,000+ (one parameterized architecture).
- **L7 Governance before assembly** — org surfaces are org-wide-visible
  only; scoped callers receive 404; tenants are never crossed.
- **L8 No new engines** — no new LLM, no new graph engine, no new memory
  engine, no new event system, no new decision engine. All deterministic.
- **L9 Virtual Company Continuity** — every new company capability in 4H.3
  must contribute to the emerging unified, temporally grounded model of the
  Virtual Company: it composes with existing state, decisions, dependencies,
  risks, opportunities, actions, outcomes, and memory through the canonical
  representations this slice establishes (L1, L2). No 4H.3 capability may
  become an isolated feature silo — when a canonical representation exists
  or can be extended additively, that representation is used, never a
  parallel one. This law survives 4H.3: later slices extend the §3 spine
  rather than replace it (Master Vision Constraint).

## 3. Schema — the exact boundary

### 3.1 `company_state_history` — the ONE new table

An append-only temporal trail of the composed living-company state. One row
per source event (exact-once on `source_event_id`), so the state at any
instant is stable forever and replays converge.

| field | type | notes |
|---|---|---|
| `id` | String(32) PK | gen_uuid |
| `organization_id` | FK organizations | CASCADE, indexed |
| `state_key` | String(140) | `st:<org>:<scope>:<seq>` — deterministic display key |
| `scope_type` | String(12) | default `"org"` (COMPANY_SCOPE_TYPES; scoped rows only for attention-worthy deviations) |
| `scope_id` | String(32) \| None | None = org-wide |
| `dimensions_json` | JSON | 8 fixed dimensions (people, work, resources, processes, outcomes, knowledge, customers, finance) — each: `{"op","signal_count","state","type":"observed/derived"}` |
| `delta_json` | JSON | what changed vs the previous snapshot: `[{"op","entity","id","label","kind","signal":"event/pattern/insight/memory","signal_ids":[],"evidence_count"}]` |
| `signals_json` | JSON | contributing signals behind this snapshot (event ids, pattern/insight ids, refreshed causal-edge refs, memory ids) — the "why" |
| `dependencies_json` | JSON | top-N dependency edges visible from this state (entity pairs + kind + confidence), bounded |
| `risks_json` | JSON | open-risk exposure composition: `[{"risk_id","title","band","probability","impact","affected":[{entity,id,kind}]}]` |
| `opportunities_json` | JSON | derived opportunity surface: `[{"source":"pattern/insight/recommendation","source_id","kind","signal_count","evidence_count"}]` |
| `affected_decisions_json` | JSON | decision ids/state/kind for pre-approval and active decisions intersecting the delta (bounded, deterministic) |
| `attention_json` | JSON | what humans should consider — reuses 4H.1 attention language (priority/kind/title/why) |
| `next_json` | JSON | advisory what-if consequences: `[{"scenario_type","consequences_count","not_a_prediction":true}]` |
| `source_event_id` | String(64) | exact-once key |
| `snapshot_ts` | DateTime(tz) | when composed |
| `occurred_at` | DateTime(tz) | event time (the as-of anchor) |
| `created_at` / `updated_at` | TimestampMixin | |

Uniques: `(organization_id, scope_type, scope_id, source_event_id)` —
`uq_csh_state`. Indexes: `ix_csh_org_time (organization_id, occurred_at)`,
`ix_csh_org_scope_time (organization_id, scope_type, scope_id, occurred_at)`.

### 3.2 Additive-only columns on `CompanyDecision`

- `state_context_json` (JSON, nullable) — the decide-time state anchor: the
  `company_state_history` snapshot refs (source_event_ids) plus bounded
  dependency/risk/opportunity summaries known when the decision was
  evaluated or recommended. Mirrors and extends 4H.2's
  `as_of_context_json`; a decision may carry both.

Schema bootstrap continues the established architecture:
`Base.metadata.create_all()` for the new table plus
`ALTER TABLE company_decisions ADD COLUMN IF NOT EXISTS state_context_json JSON`
and `CREATE INDEX IF NOT EXISTS` statements in `_POSTGRES_ALTERS`
(`app/db/database.py`) — idempotent on every startup, fresh and existing
databases, no Alembic, no destructive migration.

**No existing column is removed, renamed, or reinterpreted. No seventh 4H.3
table may be added without a contract amendment.**

## 4. Living-state lifecycle

Not a mutable state machine: a **snapshot trail**. Each composition is
triggered by a source event and writes a row only when the composed surface
differs from the previous row's surface (no-op compositions stay
unwritten — no false trail entries). Reads are always "latest snapshot ≤
now" or `as_of`; replays of the same event produce the identical row
(exact-once on `source_event_id`).

Decision lifecycle is untouched — 4H.2 states stay exactly as ratified.
4H.3 only attaches `state_context_json` at evaluate/recommend time
(§7.2) and reads it back in surfaces (§7.1).

## 5. Read laws (binding)

- **5.1 Temporal as-of** — `as_of` before a snapshot excludes snapshots/
  deltas composed after it; `include_partial` mirrors 4H.2 semantics
  (strict count 0 + `evidence_incomplete`-style late items listed, never
  mixed). Replays are byte-identical.
- **5.2 Determinism** — same inputs → identical surfaces; `generated_at`
  is the only non-stable field (4H.2 §10 law).
- **5.3 Honesty** — confidence-like numbers always carry
  evidence/signal counts; bands are LOW/MEDIUM/HIGH from recorded inputs
  only; scenario blocks carry `advisory_only: true` and
  `not_a_prediction: true`; observed vs derived vs predicted are distinct
  types on every block.
- **5.4 Affected decisions** — derived by deterministic intersection of
  (a) the delta's entities/kinds with (b) decision evidence
  `source_kind`/`source_summary` tokens and `state_context_json` refs —
  bounded (MAX_STATE_DECISIONS), never free-text embedding.
- **5.5 Bounds** — MAX_STATE_DELTA = 30, MAX_STATE_RISKS = 10,
  MAX_STATE_OPPORTUNITIES = 10, MAX_STATE_DECISIONS = 20,
  MAX_STATE_SIGNALS = 30, dependency depth ≤ MAX_CAUSAL_DEPTH (5, reused),
  MAX_COMPANY_RECOMMENDATIONS reused for `next`. All index-backed;
  identical shapes 5 → 50,000+.

## 6. Events (exact names, exact-once)

| event | emitted | payload invariants |
|---|---|---|
| `company.state.composed` | ONLY when a snapshot row was actually written | organization_id, snapshot ref (source_event_id), scope_type, scope_id, delta_count, snapshot_ts |
| `company.state.changed` | ONLY when the composed delta is non-empty | organization_id, snapshot ref, delta_count, first 3 delta entity kinds |

Both are published through the existing fabric (publisher + catalog + the
single 4G.7 bridge — no second bridge, no handler that republishes). A
read, a no-op composition, or a rejected write never emits either event.

## 7. API + brain routing

### 7.1 Surfaces (all `brain:read`, org-wide `_people_access`, advisory-only)

- `GET /execution/company/state` — the living state: dimensions, delta,
  signals, dependencies (top-N), risks, opportunities, affected decisions,
  attention, next. Query params: `as_of`, `include_partial`, `scope_type`,
  `scope_id`, `explain=true` (expands the "why" signal provenance).
- `GET /execution/company/state/dependencies?entity_type&entity_id&depth`
  — downstream walk reusing `causal_chain()`; bounded depth; unknown
  entity → 404.
- `GET /execution/company/state/risks` — risk exposure composition
  (open statuses only; deterministic band; affected entities).
- `GET /execution/company/state/opportunities` — bounded opportunity
  surface (patterns/insights/recommendations).
- `GET /execution/company/state/decisions` — affected decisions with
  state, kind, evidence_count, and their `state_context_json` summary.

### 7.2 State-context bridge (write, `projects:manage`)

- `POST /execution/company/decisions/{decision_id}/state-context` —
  attaches the current state snapshot refs to the decision as
  `state_context_json`. Exact-once (no-op replays return `created:false`,
  never re-emit); unknown decision → 404; unchanged payload → `changed:
  false`. Rewrites the same `detail.rejected` 409 pattern as 4H.2 for
  decisions already past `outcome_recorded`.

### 7.3 Brain intents (additive to `_INTENT_RULES` + `_company_operating_query`)

| intent | routes | answer shape |
|---|---|---|
| `company_state` | "what is happening / company state / status of the company" | current dimensions + delta summary + attention |
| `company_changes` | "what changed / what has changed" | delta with signal provenance (extends existing `company_changes` phrasing) |
| `company_dependencies` | "what depends on / dependencies" | bounded dependency walk from the asked entity |
| `company_risks` | "what's at risk / key risks / exposures" | risk exposures with affected entities |
| `company_opportunities` | "opportunities / where should we focus" | bounded opportunity surface |

All answers `advisory_only: true`, bounded, typed (observed/derived).
The scoped-caller early return and `decision_*` intents of 4H.2 remain
untouched.

## 8. Frontend (minimal, read-only)

Extend the existing company tab (`frontend/app/(app)/execution/company-tab.tsx`)
with a **Living Company State** panel (`lib/api.ts` gains the matching
helpers/types): eight-dimension state row (observed/derived typed), "What
changed" delta list with provenance counts, at-risk exposures, affected
decisions (linking to the 4H.2 decision rows), and a "what could happen
next" advisory block. Every block shows evidence counts or `advisory_only`
footers. No execute/authorize affordances — the panel is read-only; backend
enforcement is unchanged. `tsc --noEmit` must stay clean.

## 9. Governance, tenants, and the :8999 trap

- Same gates as 4H.1/4H.2: `brain:read` reads, `projects:manage` writes,
  `_people_access` org-wide check (scoped → 404, never 403/leak).
- Tenant isolation: org B's state surfaces are empty/404 for org A's
  entities — asserted live.
- **Known trap**: stacked background workers on a single :8999 instance
  contaminate acceptance runs. Use ONE clean server per suite pass;
  drain the event queue after every write step (`POST /api/v1/
  intelligence/events/process?limit=400`); reprocess leftovers only after
  verifying the queue is quiescent. A force-killed server can leak
  `background_jobs` rows — clear terminal/retry rows before restart (they
  proved to re-claim and melt the connection pool).

## 10. Freshness

The state surface is composed on read when `now - last_composed > 
STATE_TTL (60s)` or on explicit event-driven recompute; both paths write
the same exact-once row (identical composition function — no second
implementations). Recomposes never rewrite prior rows.

## 11. Scale law (5 → 50,000+)

The same parameterized schema serves a 5-person startup and a 50,000-
employee enterprise: scoped snapshots reuse `COMPANY_SCOPE_TYPES`;
deltas/precedents/risks are top-N bounded; every join is index-backed by
construction (`ix_csh_*`); the acceptance suite asserts identical shapes
at org scope (and exercises at least one scoped state read).

## 12. Anti-duplication rules (binding)

- No second company-state database, no second causal graph, no second
  memory store, no second event system, no second brain router, no second
  decision engine, no second what-if simulator, no new LLM calls.
- No migration framework beyond the established `create_all` +
  `ADD COLUMN IF NOT EXISTS` discipline.
- No generic ticks/CRM/ERP/HRMS/workflow builder functionality; the
  customer/people/work surfaces remain compositions over the existing
  canonical stores.

## 13. No-OpenAI / determinism guarantee

Every 4H.3 surface is a deterministic composition of recorded rows: no LLM
anywhere in composition, delta, exposure, affected-decision, or scenario
paths. Insights/patterns are read from their existing deterministic stores;
scenarios reuse the bounded `what_if` engine with `not_a_prediction` and
`advisory_only`.

## 14. Acceptance tests (`backend/scripts/accept_slice4h3.py`, live on :8999)

Each test maps to its law (L1-L8). Suite-wide invariants (a)-(c) are
asserted across EVERY response (no blame, no naked confidence, advisory/
typed blocks). Exit 0 only when all pass:

1. **State composition (L2)** — a seeded change event produces a
   `company_state_history` row with 8 dimensions, typed observed/derived,
   evidence counts.
2. **Delta (L1/L2)** — after a second seeded change, the delta lists only
   the new signals with provenance (event/pattern/memory ids); no-op
   compositions write no row and emit no event.
3. **Why (L1/L4)** — `explain=true` expands signal provenance; every cited
   signal carries its id.
4. **Dependencies (L1/L6)** — a seeded project/customer/risk cluster walks
   via the existing causal chain, bounded depth; unknown entity → 404.
5. **Risks (L1/L4/L6)** — open risks compose into exposures with bands and
   affected entities; closed/mitigated risks are not exposed; bounded top-N.
6. **Opportunities (L1/L4/L6)** — patterns/insights surface as bounded
   opportunities with source ids and evidence counts.
7. **Affected decisions (L1/L5.4/L6)** — a recommended 4H.2 decision whose
   evidence/state-context intersects the delta appears; unrelated decisions
   do not; bounded top-N.
8. **State-context bridge (L5)** — `POST state-context` attaches
   `state_context_json`; replay returns `created:false` and emits no event;
   post-outcome decisions → 409 `detail.rejected`.
9. **Decision surface integration (L3)** — the 4H.2 detail/prediction
   surfaces now expose the `state_context` summary (read-only, additive).
10. **Temporal as-of (L3)** — `as_of` before a change excludes the later
    delta strictly; `include_partial` lists it as late; re-querying is
    byte-identical.
11. **Determinism (L3/5.2)** — identical re-query surfaces modulo
    `generated_at`; exact-once replay of the two new events leaves counts
    stable.
12. **Event truth (L5)** — only `company.state.composed`/`company.state.changed`
    rows actually written produce events; reads and rejected writes emit
    zero.
13. **Governance (L7)** — a scoped caller receives 404 for org state; a
    second organization sees empty/404; tenants never crossed.
14. **Bounded shapes (L6)** — all MAX_STATE_* caps honored; one scoped
    state read returns the identical parameterized shape.
15. **Reuse (L1/L8)** — assert the same/few canonical tables carried state
    (no new tables beyond `company_state_history` in the org's schema),
    and the memory/causal/decision stores are the canonical ones.
16. **Moat accumulation (compounding)** — after more decisions + lessons,
    the state's affected-decisions/dependency/opportunity content strictly
    grows; answers cite provenance and governance consistently.

17. **Brain intents (L1)** — `company_state` / `company_changes` /
    `company_dependencies` / `company_risks` / `company_opportunities`
    resolve deterministically via `/brain/knowledge/query`, bounded and
    advisory-only; 4H.2 intents (`decision_reason`, `decision_alternatives`)
    still resolve (no routing regression).

## 15. Unit tests (`backend/tests/test_4h3_engine.py`)

Backend unit suite (SQLite, mirroring `test_4h2_engine.py` style) covering:
composition function determinism; delta diffing (add/change/remove);
exact-once snapshot on source_event_id replay; as_of strict/partial;
dependency-walk bounds; risk exposure bands; opportunity derivation;
affected-decision intersection; state-context write (created/changed/no-op
replay/409); both new events' trigger-only-on-write; tenant isolation;
bounded shapes; byte-identical determinism. Plus regression:
`test_4g7_engine`, `test_4h1_engine`, `test_4h1_governance`,
`test_4h1_surfaces`, `test_4h2_engine` — all must stay green.

## 16. Moat test (law: compounding dependence)

The five-year irreplaceability questions (§16 of the 4H.2 contract) remain
answerable; additionally:

- The longer an org operates through VCOS, the richer its `company_state_history`
  trail, dependency visibility, and decision state-context anchors become —
  continued usage strictly increases the content behind the living-state
  answers.
- The differentiation claim is architectural: "VCOS understands the company
  as a continuously changing system" — not "VCOS also has tickets." The
  acceptance suite asserts the accumulation direction (test 17 proxy).

## 17. Definition of DONE

4H.3 is complete only when ALL hold:

- **Schema** — `company_state_history` exists with the exact §3.1 columns/
  indexes (verified live); `state_context_json` additive column present;
  fresh DB, existing DB, and repeated bootstrap all idempotent; existing
  data intact (row-count checks in acceptance).
- **Lifecycle** — snapshot trail exact-once per source event; no-op
  compositions leave no rows; `company.state.composed` /
  `company.state.changed` fire only on real writes; no event on reads or
  rejections.
- **API** — §7.1 surfaces + §7.2 bridge exist with 4H.2-era 409/404/
  advisory shapes; 4H.2 endpoints unchanged except the additive
  `state_context` summary on detail/prediction reads.
- **Brain** — the five new intents route deterministically; existing
  decision/company intents unchanged.
- **Frontend** — Living Company State panel renders read-only surfaces
  with typing and evidence counts; `tsc --noEmit` clean.
- **Regression** — 4G.7 14/14, 4H.1 16/16, 4H.2 19/19 live acceptance all
  pass; 4H.2 unit suite green; new 4H.3 unit suite green (≥ 12 tests);
  full `pytest -q` green.
- **Architecture** — exactly ONE new table; additive edge kinds only; no
  duplicate engines/event systems/migration frameworks; diff inspected for
  scope creep, duplicated architecture, or incomplete integration.

## 18. Out of scope

4H.3 does not begin 4I (deeper cross-company understanding), does not add
LLM reasoning, does not authorize any action, and does not build
ServiceNow/ERP/CRM/HRMS/ticketing/project-management clones. Those rise in
their own future contracts (4I-4Q), which — like this document — must come
from ratified source material, never invention.

---

**End of SLICE 4H.3 contract (RATIFIED 2026-08-20).**