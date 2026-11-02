# SLICE 4H.2 — Universal Organizational Decision Intelligence

**Status: RATIFIED — implementation authorized (2026-08-19).**
**Repos: `D:\workspace\vcos` (contracts at repo root; backend `backend\`, frontend `frontend\`).
**Supersedes: nothing. Builds on: 4G.7 (ratified, 14/14 live) and 4H.1 (ratified, 16/16 live).**

> This document is the formal **proposed** contract for Slice 4H.2. It is
> deliberately NOT ratified: the author never ratifies slices — a human
> (architect of record) reviews, edits, and either ratifies this contract or
> sends it back with changes. **No implementation work begins until
> ratification.**

---

## 0. Mandatory analyze-then-extend step (do not skip)

Before writing any 4H.2 code, the implementer MUST re-run the analysis below
against the **current** repository state (the repo — not this document — is
the only truth) and confirm every row of the reuse table still holds. Drift
found in this step **blocks** 4H.2 work until resolved.

Analysis re-run checklist:

- [ ] `backend/app/models/company_operating.py` still defines `CompanyDecision`,
      `CompanyHealthHistory`, `CompanyCausalEdge`, with
      `DECISION_KINDS`, `DECISION_STATES = (approved, declined, executed,
      outcome_recorded)`, `OUTCOME_KINDS = (successful, partial,
      unsuccessful)`, `CAUSAL_EDGE_KINDS` (incl. `decision->task`),
      `COMPANY_SCOPE_TYPES`, and the MAX_* bounds.
- [ ] `backend/app/intelligence/company_operating_engine.py` still has
      `record_decision` / `execute_decision` / `record_outcome` (exact-once on
      `decision_id` and `source_event_id`), `_prediction_fields`, `memory()`,
      `changes()`, `health()`, `what_if()`, `what_happens_if()`,
      `temporal_state()`, `causal_chain()`, `_derive_causal_edges()`.
- [ ] `backend/app/events/event_models.py` still catalogues the 4G.7/4H.1
      names 4H.2 extends: `company.decision.recorded`, `company.action.executed`,
      `company.outcome.recorded`, `company.health.recomputed`,
      `company.causal_edge.refreshed`, `company.prediction.recorded`,
      `company.memory.lesson.derived`.
- [ ] `backend/app/events/handlers.py` (4G.7 bridge section ~line 3091) still
      obeys "the bridge never publishes its own events", and the 4H.1 audit
      handlers still ack without recompute.
- [ ] `backend/app/knowledge/intelligence_engine.py` `_company_operating_query`
      (~line 3717) still routes deterministically with the scoped-caller early
      return.
- [ ] `backend/app/api/v1/brain.py` (lines ~6890-7390) still gates reads with
      `brain:read`, writes with `projects:manage`, and both with org-wide
      `_people_access` (scoped → 404).
- [ ] `backend/app/memory/formation.py` `record_decision_lesson` still exists
      (the lesson-loop reuse anchor).
- [ ] `backend/app/models/company_memory.py` remains the ONE canonical memory
      store; 4H.2 adds no second memory table.
- [ ] Re-run 4G.7 + 4H.1 acceptance (`accept_slice4g7.py`, `accept_slice4h1.py`)
      against a SINGLE clean server on :8999 — 14/14 and 16/16 must stay green
      before and after 4H.2 lands (stacked-worker contamination on :8999 is a
      known trap — see §9).
- [ ] `git log --all -i --grep="4h.2"` must stay empty; the 4H.1 contract's
      out-of-scope (§14 of that document) names 4I-4Q, never 4H.2 — if that
      changes, this contract must be reconciled first.

### 0.1 Reuse map (binding) — what 4H.2 reuses, what it adds

| Capability | Reused (never duplicated) | Added by 4H.2 |
|---|---|---|
| Decision record | `CompanyDecision` (4G.7/4H.1): decision_id, kind, rationale, alternatives_json, confidence, state, outcome, lesson, prediction fields | Pre-approval lifecycle states (§4); first-class alternative rows; decision evidence rows (§3) |
| Prediction / reconciliation | `predicted_outcome`, `prediction_confidence`, `actual_outcome_compare` + `company.prediction.recorded` audit | Per-alternative `expected_outcome`; track-record rollups (§5.2) |
| Expected-vs-actual | `record_outcome` reconciliation block (4H.1) — untouched | Decision quality composition (§5.3) |
| Causality | 4H.1 snapshot `CompanyCausalEdge` + `causal_chain()` (edges incl. `decision->task`, `task->execution`) | **No new causal engine.** 4H.2 attaches decision evidence to existing edges; decision-impact questions walk the same chain |
| What-if | `what_if()` / `what_happens_if()` (delay/reallocate/hire) — bounded, advisory-only | Per-alternative scenario framing that reuses the same bounded simulators (§7.2) |
| Lesson memory | `CompanyMemory` via `memory/formation.record_decision_lesson` (4D.3 lineage, evidence_json) | Precedent rows that CITE lessons with evidence counts (§5.4) |
| Temporal as-of | `CompanyHealthHistory` exact-once trail + `temporal_state()` + `ix_chh_org_time` | As-of semantics for decision/precedent reads (§5.1) |
| Event fabric | `events/publisher.publish_event`, `EVENT_CATALOG`, handlers bridge | New event names (§6) — same bridge, no second bridge |
| Brain routing | `_company_operating_query` keyword routing + `company_universal` intent lists | New decision-intelligence intents/keywords (§7.3) |
| API + permissions | `brain.py` `/execution/company/*` pattern; `brain:read` reads; `projects:manage` writes; `_people_access` org-wide gate | New endpoints (§7.1, §7.2) — same gates, zero new access code |
| Multi-level scopes | `COMPANY_SCOPE_TYPES` + existing scope machinery (4H.1 `multi_level_state`) | Decisions/cohorts may carry `scope_type`/`scope_id` |
| Frontend | existing company tab + `frontend/lib/api.ts` helpers | Read-only decision surfaces (§7.4) |

**No new module anywhere**: 4H.2 lives inside existing files —
`models/company_operating.py` (tables), `company_operating_engine.py`
(methods), `event_models.py` (names), `handlers.py` (extended bridge
section), `intelligence_engine.py` (routing), `api/v1/brain.py` (routes),
`scripts/accept_slice4h2.py` (new acceptance script), plus the existing
company tab + `lib/api.ts`.

### 0.2 Audit history

- **v1 (PROPOSED, 2026-08-19)** — pre-ratification contract-only audit
  against the live 4E–4H.1 codebase. All §0.1 reuse claims re-verified
  against current code (models, engine methods, event catalog, handlers
  bridge doctrine, intent routing, brain permission gates,
  `formation.record_decision_lesson`, canonical `CompanyMemory`). Blocking
  issues found and fixed in this revision: (1) §3.5 track rollups were a
  mutable materialized table — rewritten to append-only exact-once
  snapshots (temporal law); (2) §15 acceptance list lacked explicit
  lineage / learning / impact / scale / moat tests — replaced with a
  law-mapped set; (3) §3.1 alternatives now carry `preferable_if`
  (reversibility condition); (4) §3.2 evidence types now include
  `constraint | stakeholder`; (5) §3.6 adds multi-level scope columns;
  (6) §5.3 quality gains reversibility + attribution-safeguard; (7) §7.1
  gains the decision impact endpoint; (8) §16 moat test gains the
  five-year irreplaceability questions + compounding test; (9) §17
  differentiation reframed on architectural abstraction, not absolute
  feature claims. The contract remains **PROPOSED** — no implementation.

### 0.3 Audit history — revision 2 (2026-08-19, contract-only, per architect review)

Second contract-only review round. Fixes applied: (1) schema boundary made
explicit — §3 now enumerates exactly **six** new tables and `§5.5`'s inline
`company_decision_contradictions` definition was promoted to its own §3.6
with the additive `CompanyDecision` columns moved to §3.7; (2) §4 gained a
backward-compatibility law + explicit "pre-approval states are never
executable" assertion; (3) §15 test 12 now enumerates all 8 new events
explicitly; (4) §5.1 gained a precise `as_of` eligibility rule replacing
"knowable-at"; (5) §5.7 pins the confidence vocabulary and forbids
reinterpreting/recalculating 4H.1 `prediction_confidence`; (6) §16 now
separates the strategic moat hypothesis from machine-verifiable acceptance
criteria; (7) §18 Ratification Gate added. Status remains **PROPOSED**.

### 0.4 Audit history — revision 3 (2026-08-19, RATIFIED by architect of record)

Third round — **RATIFICATION**. The architect of record reviewed revision 2
and explicitly authorized implementation (implementation authorization
prompt: "Architectural status: RATIFIED / IMPLEMENTATION AUTHORIZED").
All §0 reuse anchors were re-confirmed against the live repo during the
pre-ratification verification (implementation-readiness report). No contract
amendments were requested at ratification. Status changes from **PROPOSED**
to **RATIFIED**; the §18 Ratification Gate is now open and implementation may
begin. The verification identified two implementation-time requirements that
do not amend the contract but must be enforced by code and acceptance tests:
(a) engine `record_decision` must retain a strict `approved | declined`
whitelist — membership in the expanded `DECISION_STATES` must not mint
pre-approval states through the legacy path; (b) `execute_decision` must
surface an explicit rejection for non-approved states (never a silent
unchanged payload that can be misreported as executed).

### 0.5 Implementation-start verification (2026-08-19)

Contract status at start: **RATIFIED** (flipped by the architect of record).
Repository HEAD: `cd653b8` ("Ratify Slice 4H.1 implementation contract").
`git log --all -i --grep="4h.2"` — empty (no prior 4H.2 work exists).

---

## 1. Objective

One sentence: **the organization learns how well it decides.**

4G.7/4H.1 gave the company one operating state, one health trail, causal
walking, bounded what-if, and a governed decision record with predictions and
lessons. 4H.2 promotes the **decision** to the first-class object of a
decision-intelligence layer:

1. every important decision carries **first-class alternatives** with the
   reason each was chosen or rejected (**why-not**);
2. every decision carries **evidence lineage** — which observed facts, from
   which operating domain, at which time — so answers never float;
3. predictions recorded at approve-time are **reconciled against observed
   outcomes**, producing a prediction track record and decision-quality
   numbers — framed as learning, never as blame;
4. the past is searchable **as-of**: "what did we know, and what did we
   decide, at that time" never leaks later information backward;
5. a **precedent engine** cites past decisions and their lessons — with
   evidence counts — whenever a new decision is on the table;
6. **contradictions** between a pending decision and past lessons or
   precedents are surfaced honestly, both sides' evidence shown, before a
   human decides;
7. everything stays **advisory-only** — 4H.2 recommends, evidences, explains
   and remembers; it never hires, fires, reassigns, re-budgets, changes
   customers, or executes anything without a governed human approval through
   the existing 4G.7 write path.

The moat (§16): a closed **decision → prediction → outcome → lesson →
precedent** loop over the full 4G.1-4G.7 universal operating data, with
temporal as-of knowledge — ServiceNow, Celonis and Palantir each cover only
pieces of this (§17).

---

## 2. Design brief — the 33 points 4H.2 is proposed against

The slice must, and only must, deliver:

1. **Decision memory** — decisions are remembered as first-class entities,
   not chat artifacts.
2. **Lineage** — every decision cites its evidence: which events, metrics,
   insights, patterns, memories and prior decisions it was built on.
3. **First-class alternatives** — each decision records ≥ 2 alternatives with
   expected outcomes; the chosen one is marked with its reasons.
4. **Why-not** — every rejected alternative records why it was rejected.
5. **Prediction-vs-actual** — the prediction recorded at approve-time is
   reconciled against the observed outcome; aligned / not aligned is
   explicit.
6. **Decision quality** — a composite, bounded score per decision and per
   cohort (kind, scope, period), built only from recorded evidence.
7. **Causality** — decision impact is explained through the existing 4H.1
   causal graph; no new causal system.
8. **What-if analysis** — decision-scenario simulation reuses the existing
   bounded what-if engine; advisory-only, never executed, never a prediction
   claim.
9. **Precedent engine** — "what did we do when we faced this before" returns
   ranked past decisions with lessons, outcomes, and evidence counts,
   as-of filtered.
10. **Confidence with evidence counts** — every confidence value is published
    together with the number of evidence items behind it (no naked
    confidence).
11. **Contradiction surfacing** — a proposed decision contradicting a
    recorded lesson or precedent is surfaced with both sides' evidence.
12. **Accountability without blame** — outcomes attribute to decisions and
    evidence, never to individuals as fault; no person-ranking surface.
13. **Temporal as-of knowledge** — every decision query accepts `as_of`;
    answers reconstruct only what the org knew before that instant; test 13
    enforces no-backward-leakage.
14. **Exact-once events** — every new event is idempotent: replays converge,
    never duplicate (4H.1 keying discipline).
15. **Governance** — all 4H.2 surfaces are org-wide; scoped callers filtered
    before assembly (existing `_people_access` gate); tenant isolation via
    `organization_id` on every row and index.
16. **5 → 50,000+** — every query bounded (top-N, paginated, indexed);
    identical behavior at 5 employees and 50,000+.
17. **One canonical architecture** — an extension of the existing stack, not
    a parallel system (anti-module gate §12).
18. **Human-gated writes** — nothing writes itself; every write rides the
    existing governed approval path.
19. **Reuse** — the §0.1 reuse map is binding; duplicating a reused
    capability is a gate failure.
20. **Honesty contract** — `advisory_only`, `not_a_prediction`, and evidence
    counts on every composed surface; no free-text invention.
21. **Determinism** — same state + same question = same answer; the
    acceptance suite re-drains the stream and asserts byte-identical output.
22. **Learning loop closure** — outcome → lesson → `CompanyMemory` →
    precedent citation, queryable end-to-end.
23. **Multi-level scope awareness** — decisions and cohorts may be scoped
    (org / business_unit / department / team / person) via the existing
    scope machinery.
24. **Events are the audit** — every lifecycle transition is an immutable
    event row; rows are never edited or deleted.
25. **Prediction track record** — cohort rollups: "how accurate were our
    predictions" per kind, scope, period (advisory-only).
26. **No new dependencies** — Python stdlib + the existing stack; zero new
    packages.
27. **Frontend parity** — the company tab gains read surfaces for decision
    list/detail/alternatives/why-not/precedent/quality via `lib/api.ts`; no
    new tabs, no new frameworks.
28. **Backward compatibility** — every existing 4G.7/4H.1 response stays
    byte-compatible; new fields and states are additive only.
29. **Fail-safe on evidence reading** — evidence reads tolerate missing rows
    (the 4G.7 lesson: never assume a nested shape you did not verify —
    `behind["target"]["gap"]`).
30. **Bounded text and lists** — string caps mirror 4H.1 (240/4000/120);
    lists capped by MAX_* constants.
31. **Deterministic brain routing** — new intents slot into
    `_company_operating_query` with explicit, ordered keywords and no
    ambiguous overlaps.
32. **No opacity** — every composed answer carries its building blocks
    (evidence ids, event ids, decision ids) so a human can verify.
33. **Moat test (§16) and differentiation (§17) are part of acceptance** —
    the contract is incomplete without them.

---

## 3. Canonical data model (new tables in `models/company_operating.py`)

4H.2 adds exactly **six new tables** (§3.1–§3.6) plus additive columns on
`CompanyDecision` (§3.7). No other new tables may be introduced without a
contract amendment.

Every row carries `organization_id` FK (`ondelete="CASCADE"`), an index on
each lookup key, and 4H.1 exact-once keying.

### 3.1 `company_decision_alternatives` — first-class alternatives

| field | type | notes |
|---|---|---|
| `id` | String(32) PK | gen_uuid |
| `organization_id` | FK | indexed |
| `decision_id` | FK `CompanyDecision.decision_id` | indexed, CASCADE |
| `alternative_key` | String(80) | `alt:<decision_id>:<n>` — deterministic exact-once key |
| `label` | String(240) | |
| `description` | Text | |
| `expected_outcome` | JSON | per-alternative expectation (mirrors `predicted_outcome` shape) |
| `chosen` | Boolean | exactly one `chosen=True` per decision |
| `why_chosen` | Text | required iff chosen |
| `why_not` | Text | **required** for every rejected alternative — the why-not record |
| `preferable_if` | Text \| None | what would need to change (deadline, capacity, dependency, market condition…) for this rejected alternative to become preferable — the reversibility condition |
| `evidence_json` | JSON | evidence ids behind this alternative |
| `created_at` | DateTime(tz) | |

Uniques: `(organization_id, decision_id, alternative_key)`; one chosen per
decision enforced at write time + unique index on `(organization_id,
decision_id)` where `chosen` (partial index).

`preferable_if` makes "why not B?" complete: the answer states both why B was
rejected AND the concrete condition under which B would win ("if the deadline
moves by 5 months, internal development becomes viable").

### 3.2 `company_decision_evidence` — lineage rows

| field | type | notes |
|---|---|---|
| `id` | String(32) PK | |
| `organization_id` | FK | indexed |
| `decision_id` | FK | indexed |
| `alternative_key` | String(80) \| None | optional per-alternative evidence |
| `evidence_key` | String(120) | `ev:<decision_id>:<n>` — exact-once |
| `evidence_type` | String(30) | `event \| metric \| insight \| pattern \| memory \| decision \| constraint \| stakeholder` — constraints and stakeholders are first-class lineage (the canonical model: question → company state → evidence + constraints + stakeholders → alternatives) |
| `source_event_id` | String(64) \| None | link into the event fabric |
| `source_kind` | String(60) | e.g. `business.metric.updated`, `insight.detected` |
| `source_summary` | String(400) | what this evidence said |
| `captured_at` | DateTime(tz) | **the evidence's own timestamp, not write-time** — the as-of anchor |
| `weight` | Float | 0..1 |

### 3.3 `company_decision_precedents` — precedent citations

| field | type | notes |
|---|---|---|
| `id` | String(32) PK | |
| `organization_id` | FK | indexed |
| `decision_id` | FK | the new decision citing the precedent |
| `precedent_decision_id` | String(32) | the past decision cited |
| `context_signature` | String(240) | canonicalized context tokens (kind + scopes + metric/domain keys) — the linker |
| `relevance_score` | Float | 0..1, computed, stored |
| `evidence_count` | Integer | evidence items the precedent carries (confidence-with-counts rule) |
| `cited_lesson` | Text | **snapshot** of the lesson as-of the precedent's outcome (never later edits) |
| `source_event_id` | String(64) | event that created the link (exact-once) |
| `created_at` | DateTime(tz) | |

Indexed `(organization_id, context_signature)`; recall is top-N by
`relevance_score`, as-of filtered (§5.1).

### 3.4 `company_decision_quality` — quality snapshots (per transition, additive)

| field | type | notes |
|---|---|---|
| `id` | String(32) PK | |
| `organization_id` | FK | indexed |
| `decision_id` | FK | indexed |
| `quality_key` | String(120) | `q:<decision_id>:<stage>:<n>` — exact-once per recompute |
| `stage` | String(20) | proposed \| evaluated \| recommended \| approved \| outcome_recorded |
| `evidence_count` | Integer | evidence rows at that stage |
| `confidence_support` | Float | recorded confidence + evidence count (never naked) |
| `prediction_alignment` | Float \| None | 0..1 when reconciliation exists; `None` = "not yet measurable" |
| `risk_band` | String(10) | LOW / MEDIUM / HIGH (reuse 4F.7 vocabulary) |
| `contradictions_surfaced` | Integer | count surfaced for this decision |
| `assess_json` | JSON | the atomic assessment (§5.3) |
| `source_event_id` | String(64) | exact-once |

### 3.5 `company_decision_tracks` — prediction track-record rollups (cohort, advisory, append-only)

| field | type | notes |
|---|---|---|
| `id` | String(32) PK | |
| `organization_id` | FK | indexed |
| `cohort_key` | String(160) | `kind:<kind>` \| `kind:<kind>:scope:<type>:<id>` \| `period:<YYYY-MM>` |
| `decisions_measured` | Integer | |
| `predictions_recorded` | Integer | |
| `aligned` / `partial` / `misaligned` | Integer | from `actual_outcome_compare.aligned` |
| `avg_effectiveness` | Float | |
| `source_event_id` | String(64) | the exact-once key — one snapshot row **per source event**, never an update |
| `snapshot_ts` | DateTime(tz) | when this snapshot was composed |

**Temporal law**: rolls are **append-only exact-once snapshots** keyed
`(organization_id, cohort_key, source_event_id)` — a later outcome NEVER
rewrites a previous snapshot. An `as_of` read returns the latest snapshot
with `snapshot_ts <= as_of`, so "how accurate were our predictions as of
March" is stable forever, byte-identical on replay.

### 3.6 `company_decision_contradictions` — surfaced conflicting evidence

| field | type | notes |
|---|---|---|
| `id` | String(32) PK | |
| `organization_id` | FK | indexed |
| `decision_id` | FK | the pending (recommended-stage) decision with the conflict |
| `contradiction_key` | String(120) | `cx:<decision_id>:<n>` — deterministic exact-once key |
| `lesson_memory_id` | String(32) \| None | the contradicting `CompanyMemory` lesson, when present |
| `precedent_decision_id` | String(32) \| None | the contradicting precedent decision, when present |
| `side_a_json` | JSON | the pending decision side: claims + evidence ids + timestamps |
| `side_b_json` | JSON | the recorded lesson/precedent side: claims + evidence ids + timestamps |
| `status` | String(16) | `open \| acknowledged \| resolved` (resolution is a human act, recorded as a normal lifecycle event) |
| `source_event_id` | String(64) | event that surfaced the contradiction (exact-once) |
| `created_at` | DateTime(tz) | |

Indexed `(organization_id, decision_id, status)`. Contradiction rows are
written once per surfacing event (append-only; rows are never deleted);
`status` transitions are audited lifecycle events.

### 3.7 Additive-only columns on `CompanyDecision`

- `as_of_context_json` (JSON) — the `CompanyHealthHistory` snapshot refs
  (source_event_ids) known at decide-time: the temporal as-of anchor.
- `quality_evidence_count` (Integer) — denormalized display of 3.4 count.
- `scope_type` / `scope_id` (String(12) / String(32) \| None) — optional
  multi-level scoping (org / business_unit / department / team / person,
  from `COMPANY_SCOPE_TYPES`); `None` = org-wide decision. Reuses the
  existing scope machinery of 4H.1; decisions queryable at every level
  (brief: 5-people startup and 50,000-employee enterprise share the same
  semantics).

**No existing column is removed, renamed, or reinterpreted** (point 28).

---

## 4. State machine — the decision lifecycle (extend, never fork)

4H.1 states: `approved | declined | executed | outcome_recorded` (human-gated
from the start). 4H.2 extends the FRONT of the lifecycle so a decision is
reasoned about before it is approved. Transition events in §6.

```
proposed ──evaluated──▶ evaluated ──recommended──▶ recommended ──recorded(approved|declined)──▶ approved
   │                         │                            │                                  │ declined
   └──── advisory stages only; engine never advances past here alone ─────────────────────────┘ (terminal, remembered)
approved ──executed──▶ executed ──outcome──▶ outcome_recorded ──quality──▶ assessed (terminal)
```

Rules:

- `proposed → evaluated → recommended` are **advisory stages**: the engine
  (or a human drafting) may create them; they carry evidence, alternatives,
  why-not, contradictions. Only a human moves a decision to
  `approved | declined`, through the existing `company.decision.recorded`
  write path (unchanged semantics: `state = approved | declined`).
- Existing 4H.1 transitions (`approved → executed → outcome_recorded`) are
  untouched. `DECISION_STATES` grows additively to `(proposed, evaluated,
  recommended, approved, declined, executed, outcome_recorded, assessed)`;
  existing consumers of the old four states keep working.
- Declined decisions are remembered (never deleted) and are valid precedent
  sources: "we considered this and declined — here is why".
- No automatic transitions anywhere: the engine proposes, evidences, and
  analyzes; humans (or the existing governed write path) advance state.

**Backward-compatibility law (binding, asserted in acceptance):**

- Existing 4G.7/4H.1 API responses, event payloads, queries, and consumers
  that operate on `approved | declined | executed | outcome_recorded` must
  retain their existing semantics — byte-for-byte where the surfaces already
  exist. Additive columns and states must never change what an existing
  consumer sees for the states it already handles.
- `proposed`, `evaluated`, and `recommended` are **advisory-only,
  non-executable states**: the existing 4H.1 `execute_decision` path MUST
  reject them (a decision in any of these states never transitions to
  `executed`); these states are invisible to existing 4H.1 execution logic —
  they exist only as pre-approval analysis records.
- This is an explicit acceptance assertion (test 12 in §15), not a
  convention.

---

## 5. Semantics the slice must implement

### 5.1 Temporal as-of knowledge (acceptance test 13 — hard requirement)

Every decision-intelligence read accepts `as_of` (ISO UTC, default = now).

- Evidence assembly uses the evidence's `captured_at`, never write-time.

**`as_of` eligibility rule (one definition, two modes):**

A decision is shown in an `as_of` answer only when **the decision lifecycle
event being represented occurred at or before `as_of`** (approval,
execution, or outcome events each mark their own time). Evidence is then
handled per mode:

- **Strict mode** (default for precedent and decision-detail reads): every
  evidence item required to support the returned representation must satisfy
  `captured_at <= as_of`. A decision whose evidence arrived later is not
  silently enriched — the representation includes only
  `captured_at <= as_of` evidence.
- **Partial mode** (explicit flag `include_partial=true`, only for detail
  views): the decision may be shown with only the evidence that existed by
  `as_of`, AND the response MUST carry
  `evidence_incomplete: ["<post-as_of evidence key>", …]` naming what was
  (correctly) excluded. It is never silently included.

Consequences (deterministic for both engineers):

- A decision made before `as_of` never disappears because of later evidence.
- Evidence captured after `as_of` never appears in any `as_of` answer —
  **no backward leakage**, in both modes.
- `as_of_context_json` references `CompanyHealthHistory` rows that existed at
  decide-time; "state of the company when we decided" replays those
  snapshots, never the live state.
- Reconstruction is deterministic: same `as_of` + same data = byte-identical
  answer.

### 5.2 Prediction-vs-actual

- At approve-time, `predicted_outcome` / `prediction_confidence` are recorded
  exactly as 4H.1 does — unchanged.
- 4H.2 additionally requires the **chosen alternative** to carry
  `expected_outcome`; reconciliation (`record_outcome`, existing path)
  compares the observed `outcome_kind` against the chosen alternative's
  expectation as well as the decision-level prediction.
- Track rollups (§3.5) derive `aligned / partial / misaligned` from
  `actual_outcome_compare.aligned`, cohortable by kind / scope / period;
  snapshots are append-only per source event (never rewritten).
- "Not yet measurable" is an explicit state, never a fake 0.
- **Confidence presentation law** (brief point 21): a prediction is never
  shown as a bare number. Every prediction surface presents:
  expected outcome, confidence band, supporting evidence count,
  contradicting evidence count, comparables (precedent) count, and an
  explicit uncertainty note. Example shape:
  `Expected success: 74% · Confidence: moderate · Supporting evidence: 12 ·
  Contradicting: 3 · Comparable past decisions: 4`.

### 5.3 Decision quality

Composed only from recorded evidence (point 10):

```
quality = weighted sum of:
  evidence_support        (evidence_count / target, capped at 1.0)
  prediction_alignment    (when outcome exists; missing → "not yet measurable" flag)
  contradiction_cleanliness (unresolved contradictions → capped penalty;
                             surfaced-and-resolved is neutral, not punished)
  reversibility           (chosen alternative carries a recorded
                           `preferable_if` / rollback condition → credit;
                           irreversible-by-record → no credit, no penalty)
```

- Every confidence-like number on a 4H.2 surface carries its evidence count
  (naked-confidence ban).
- **Epistemic safeguard**: the assess_json explicitly states that a business
  outcome may have multiple causes; 4H.2 scores the DECISION'S recorded
  prediction, evidence and alternatives against the observed outcome —
  it never claims the outcome was produced solely by this decision.
- Quality is advisory-only and **an attribute of the decision, not of a
  person**: `assess_json` names decision ids, evidence ids, and event ids —
  never persons, never blame language (test 12).

### 5.4 Precedent engine

- Linker: canonicalize a proposed decision's context (kind + scopes + the
  metric/domain keys present in its evidence) into `context_signature`;
  rank candidate past decisions by signature overlap + outcome of record +
  evidence count.
- Results always carry: decision title, state, outcome kind, effectiveness,
  lesson **snapshot**, evidence count, as-of context. Citations point at the
  past exactly as it was knowable.
- Precedent answers read like decision memory, not document search: "Three
  comparable decisions exist — 2027 (succeeded after added capacity), 2029
  (succeeded), 2030 (failed; customer readiness underestimated)" — each with
  its lessons, outcomes and evidence counts (§16).
- A past lesson that contradicts the proposed choice surfaces a
  contradiction row (§5.5).
- Bounded: top-N (new constant `MAX_PRECEDENTS = 10`, mirroring
  `MAX_MEMORY_SHOWN`); signature matching never scans the full table
  (org_id + signature index; as-of filter applied in SQL).

### 5.5 Contradiction surfacing

- A pending decision (recommended stage) whose alternatives or evidence
  contradict a lesson/precedent is surfaced with **both sides**, each
  carrying its evidence ids and timestamps. The human sees the conflict; the
  platform takes no side beyond evidence.
- The surface language is explicit: "**Evidence is conflicting.**" followed
  by each side — e.g. capacity intelligence says 130% utilization, an
  engineering input says sufficient capacity, customer intelligence shows
  three deadlines at risk. VCOS never silently picks a winner.
- Contradiction rows are stored (audited) in `company_decision_contradictions`
  (schema in §3.6) and counted into quality (§3.4); a human resolving one
  records a normal lifecycle event.

### 5.6 Accountability without blame (binding framings)

- Outcomes attribute to decisions and evidence (ids), never to employees.
- No surface ranks, scores, or compares individuals on decision outcomes.
- Lessons are phrased as company lessons ("we learned … when …"), matching
  `record_decision_lesson` formation.
- Governance blame is out of scope; the goal is a better-informed **next**
  decision.
- Canonical framing: "The decision was reasonable given the evidence
  available at the time, but the capacity assumption proved incorrect." —
  never "Person X made a bad decision." Both the decision record (who
  decided, when, on what evidence, expecting what) and the evaluation stay
  separated; the record preserves accountability, the evaluation preserves
  learning.

### 5.7 Confidence vocabulary (mathematically precise — no new confidence model)

The contract distinguishes EXACTLY five quantities. No implementation may
invent or merge a sixth:

| term | definition | who writes it | immutable? |
|---|---|---|---|
| **recorded prediction confidence** | the value entered at approve-time (`CompanyDecision.prediction_confidence`, a Float 0..1, recorded by 4H.1) | the human/approval write | YES — never recalculated, never reinterpreted by 4H.2 |
| **evidence count** | the cardinality of supporting `company_decision_evidence` rows (per decision or per alternative, `captured_at <= as_of` when temporal) | engine, from rows | computed per read (deterministic) |
| **contradicting evidence count** | the cardinality of open `company_decision_contradictions` rows (side_b) | engine, from rows | computed per read (deterministic) |
| **quality score** | the composed 0..1 figure from §5.3 (evidence_support · prediction_alignment · contradiction_cleanliness · reversibility) | engine, exact-once per stage snapshot (§3.4) | append-only per stage; never edited |
| **confidence band** | a PRESENTATION-ONLY classification of the recorded confidence (e.g. `low | moderate | high`), derived by fixed thresholds | display layer | derived per read; never stored |

**Mandatory law**: 4H.2 MUST NOT reinterpret, recalculate, or rewrite the
4H.1 `prediction_confidence`. 4H.2 may only CONTEXTUALIZE the recorded value
with evidence counts, contradicting counts, precedents and uncertainty —
per the presentation law in §5.2. `confidence_support` in §3.4 is a display
composition of (recorded confidence, evidence count) and is never exported
as a stored probability.

---

## 6. Exact-once events (extend the existing catalog & bridge)

New names added to `EVENT_CATALOG` under a 4H.2 header:

| event | fired by | handled by |
|---|---|---|
| `company.decision.evaluated` | advisory stage write (engine or human draft) | `evaluate_decision` — writes evaluation + alternative seeds; idempotent |
| `company.decision.recommended` | advisory stage write | `recommend_decision` — recommended state, contradiction scan, precedent links |
| `company.decision.alternatives.recorded` | alternative write | `record_alternatives` — upsert by `alternative_key`, exact-once |
| `company.decision.why_not.recorded` | alternative write | same handler (rejected alternatives carry why_not) |
| `company.decision.precedents.linked` | internal, from recommended | `link_precedents` — exact-once on `source_event_id` |
| `company.decision.contradiction.surfaced` | internal, from recommended | `surface_contradictions` — exact-once |
| `company.decision.quality.composed` | internal, on state transitions | `compose_quality` — exact-once per stage |
| `company.decision.track.updated` | internal, on outcome | `update_tracks` — writes one append-only snapshot row per source event (never updates history) |

Rules (mirror 4H.1 verbatim):

- **Exact-once keying**: every write keyed on a deterministic
  `(organization_id, entity, natural_key)` tuple — replays converge, a
  re-drain leaves every table and every surface byte-identical.
- **The bridge never publishes its own events** (handlers.py ~3091 doctrine);
  internal 4H.2 events use the existing audit-ack pattern — ack, no
  recompute loops.
- Events are the audit: lifecycle transitions are append-only rows; no
  edits, no deletes.
- 4H.2 handlers extend the EXISTING bridge section of handlers.py; no second
  bridge class (anti-module gate §12).

---

## 7. API surfaces and Universal Brain intents

### 7.1 Read endpoints (`/api/v1/brain/execution/company/…`, all `brain:read` + org-wide gate; scoped caller → 404)

| endpoint | returns |
|---|---|
| `GET /decisions?kind=&state=&scope_type=&scope_id=&since=&as_of=&limit=&page=` | paginated decision list — every row carries evidence_count + prediction/outcome fields when present |
| `GET /decisions/{decision_id}` | full decision: rationale, alternatives (chosen + why-not), evidence lineage, prediction fields, quality, contradictions, precedents |
| `GET /decisions/{decision_id}/alternatives` | first-class alternatives with expected_outcome, why_chosen, why_not |
| `GET /decisions/{decision_id}/why-not` | the rejected-alternatives record (reason per alternative) |
| `GET /decisions/{decision_id}/prediction` | prediction fields + reconciliation (`actual_outcome_compare`) or `"not yet measurable"` |
| `GET /decisions/{decision_id}/quality` | quality snapshot(s) + evidence counts + risk band (advisory-only) |
| `GET /decisions/{decision_id}/precedents?as_of=` | precedent citations, as-of filtered |
| `GET /decisions/{decision_id}/contradictions` | surfaced contradictions, both sides' evidence |
| `GET /decisions/{decision_id}/impact` | bounded causal trace: decision → resource allocation → projects → milestones → customers → revenue/business → strategic objectives — walked on the existing 4H.1 causal chain; evidence-backed, never fictional reasoning |
| `GET /precedents?context=&as_of=&limit=` | free precedent recall by context signature (the precedent engine) |
| `GET /tracks?cohort=kind&value=<kind>&as_of=` | prediction track-record rollups (advisory-only) |

`as_of` is honored on every endpoint above (default = now). All `scope_type`
values come from `COMPANY_SCOPE_TYPES`; org-wide means org scope for callers
with org-wide access.

### 7.2 Advisory stage writes and scenario reads (all `projects:manage` + org-wide gate)

| endpoint | behavior |
|---|---|
| `POST /decisions/evaluate` | human/engine opens a decision; writes `proposed → evaluated` + alternative seeds (advisory) |
| `POST /decisions/{id}/recommend` | moves to `recommended`; runs contradiction scan + precedent linking (advisory) |
| `POST /decisions/{id}/alternatives` | records alternatives + why-not (exact-once) |
| `POST /decisions/{id}/alternatives/{key}/why-not` | records/updates one why-not (audited as `company.decision.why_not.recorded`) |
| `POST /decisions/{id}/what-if` | reuses `what_if()` per alternative: consequences per scenario with `not_a_prediction: True`, `advisory_only: True`; **never creates or executes anything** |

The governed approval/execute/outcome writes remain EXACTLY the existing
4H.1 endpoints (`POST /decisions`, `POST /decisions/{id}/execute`,
`POST /decisions/{id}/outcome`) — 4H.2 adds no second approval path.

### 7.3 Brain intents (`_company_operating_query` routing, ordered keywords)

New deterministic keyword groups, appended after the existing groups with no
ambiguous overlaps:

| intent group | trigger keywords |
|---|---|
| `decision_reason` | "why did we decide", "reason for the decision", "what led to the decision" |
| `alternatives` | "alternatives we considered", "what were the options", "what else could we have done" |
| `why_not` | "why not", "why did we reject", "why didn't we choose" |
| `prediction` | "did the prediction hold", "how accurate was our prediction", "prediction track record" (extends the existing pool at ~3668) |
| `outcome` | "what happened after", "outcome of the decision", "did the decision work" |
| `learning` | joins the existing `learned` / `memory` groups (already routed) |
| `precedent` | "what did we do when", "have we faced this before", "similar situation", "past decision like this" |
| `impact` | "decision impact", "what did this decision affect", "caused by the decision" (walks the 4H.1 causal chain from the decision node) |
| `what_if` | existing what-if keywords — unchanged semantics, now also scoped per alternative |

Answers carry `advisory_only: True` and every cited fact carries its
evidence ids / decision ids / event ids (point 32). Scoped callers get the
existing early return ("your scope does not include them").

### 7.4 Frontend (`frontend/lib/api.ts` + existing company tab)

- New read helpers, mirroring the existing `getCompanyMemory` /
  `recordCompanyDecision` style: `getCompanyDecisions`,
  `getCompanyDecision(detail)`, `getCompanyAlternatives`,
  `getCompanyWhyNot`, `getCompanyPrediction`, `getCompanyQuality`,
  `getCompanyPrecedents`, `getCompanyContradictions`, `getCompanyTracks`.
- The company tab gets one **Decision Intelligence** section (reading the
  new endpoints); no new tabs, no new frameworks.
- `recordCompanyDecision` / `executeCompanyDecision` / `recordCompanyOutcome`
  are reused unchanged for the governed writes.

---

## 8. Governance and tenant isolation

- Every 4H.2 table row carries `organization_id`; every query filters on it.
- Every 4H.2 endpoint checks org-wide access FIRST, before any assembly
  (access filtering precedes intelligence assembly — permanent law).
- Scoped callers (project-scoped, etc.) never see org-wide decision
  surfaces: identical 404 behavior to 4H.1.
- Writes require `projects:manage`; reads require `brain:read` — no new
  permission strings, no new access code.
- 4H.2 introduces no new roles, no new scopes, no new delegation paths.

---

## 9. 5 → 50,000+ employees: bounded scalability

| concern | mechanism |
|---|---|
| Decision list | `(org_id, decided_at)` and `(org_id, state)` indexes; default `limit=20`, max 100, cursor pagination |
| Precedent recall | `(org_id, context_signature)` index + SQL as-of filter + top-N (10); depth-limited signature matching |
| Tracks | append-only snapshots `(org_id, cohort_key, source_event_id)`; `as_of` reads pick the latest snapshot ≤ as_of — indexed, no per-request recompute, never rewrite the past |
| Evidence | indexed `(org_id, decision_id)`; per decision bounded (cap `MAX_DECISION_EVIDENCE = 40`) |
| Temporal as-of | reads against indexed `CompanyHealthHistory` rows (existing `ix_chh_org_time`) by `(org_id, source_event_id)` list — bounded join |
| Engine paths | all loops mirror 4H.1 patterns (`_head`, `_dict_list`, MAX_* caps); no full-table scans; no cross-org joins |
| Testing | the acceptance suite covers a tiny org (5 people path) AND asserts the same bounded shapes hold with large synthetic volumes if the runtime allows — at minimum the query plans are index-backed by construction |

**Known trap**: only run acceptance against a single clean server on :8999.
Earlier contamination (orphaned `multiprocessing-spawn` workers 7416/7748/9440
stacked on :8999) caused 4G.7 check-9 flakiness. To find listeners:
`netstat -ano | Select-String ":8999" | Select-String "LISTENING"` — kill
filters on `*uvicorn*8999*` miss spawn-worker cmdlines.

---

## 10. Determinism and exact-once replay

- Same state + same question = byte-identical answer (all surfaces compose
  deterministic SQL + deterministic rule sets; no free-text in scoring).
- Re-draining the same event stream (tests replay every 4H.2 event) leaves
  every table and every surface unchanged — asserted, not assumed.
- No time-of-day or random inputs enter any stored score or key (keys are
  deterministic; `gen_uuid` is only for row `id` PKs, never for semantics).

---

## 11. Engine methods (all inside `company_operating_engine.py`)

| method | purpose |
|---|---|
| `evaluate_decision` | advisory evaluation: evidence assembly + alternative seeds (exact-once) |
| `recommend_decision` | recommended state + contradiction scan + precedent linking (exact-once) |
| `record_alternatives` | alternatives + why-not upserts (exact-once) |
| `link_precedents` | precedent rows + `company.decision.precedents.linked` (exact-once) |
| `surface_contradictions` | contradiction rows + surfaced event (exact-once) |
| `compose_quality`(decision, stage) | quality snapshot (exact-once per stage) |
| `update_tracks` | append-only cohort snapshot (exact-once per source event; as-of reads stable) |
| `decision_impact` | walks the existing 4H.1 causal chain from the decision node — no new causal code |
| `decision_precedents`(context, as_of) | the precedent engine read |
| `decision_tracks`(cohort, as_of) | track-record read |
| `decisions`(filters, as_of) / `decision_detail`(id, as_of) | list/detail reads |

Reused untouched: `record_decision`, `execute_decision`, `record_outcome`,
`_prediction_fields`, `memory`, `what_if`, `what_happens_if`,
`causal_chain`, `temporal_state`, `_derive_causal_edges`, `health`,
`changes`, `company_state`, `recommendations`.

---

## 12. Anti-module gate (overlap check — must all pass)

4H.2 MUST NOT create, directly or transitively:

- [ ] a second decision store (the ONE decision table is `CompanyDecision`;
      alternatives/evidence/precedents are child rows of it, not a second
      system)
- [ ] a second causal engine (4H.1 `causal_chain` / `CompanyCausalEdge` is the
      ONE causal graph)
- [ ] a second what-if engine (4G.4 + 4H.1 `what_if` / `what_happens_if` are
      reused verbatim)
- [ ] a second memory store (the ONE memory store is `CompanyMemory` via
      `formation`; precedent rows only CITE it)
- [ ] a second event broker or a second handler bridge (4H.2 extends the
      existing `handlers.py` bridge section; the bridge never publishes its
      own events)
- [ ] a second approval/write path (`company.decision.recorded` /
      `company.action.executed` / `company.outcome.recorded` remain the ONLY
      governed writes for decisions)
- [ ] a second access system (every gate reuses `_people_access` +
      `brain:read` / `projects:manage`)
- [ ] a second prediction/reconciliation mechanism (the 4H.1 fields and the
      `record_outcome` reconciliation block are extended, not replaced)
- [ ] a second organizational-health trail (as-of context CITED FROM
      `CompanyHealthHistory`, never re-snapshot duplicated)
- [ ] a parallel frontend (extensions live in the existing company tab and
      `lib/api.ts`)

Fail on any row. The §0.1 reuse map is equally binding.

---

## 13. Deliverables checklist

- [ ] `backend/app/models/company_operating.py` — the six new tables
      (§3.1–§3.6) + additive columns (§3.7) + extended `DECISION_STATES` (§4)
- [ ] `backend/app/intelligence/company_operating_engine.py` — new methods
      (§11), no changes to reused methods
- [ ] `backend/app/events/event_models.py` — 8 new event names (§6)
- [ ] `backend/app/events/handlers.py` — extended bridge section (§6), no
      second bridge
- [ ] `backend/app/knowledge/intelligence_engine.py` — new intent keyword
      groups (§7.3)
- [ ] `backend/app/api/v1/brain.py` — new endpoints (§7.1, §7.2)
- [ ] `frontend/lib/api.ts` + existing company tab — read surfaces (§7.4)
- [ ] `backend/scripts/accept_slice4h2.py` — the 15 acceptance tests (§15)
- [ ] This contract — status flipped to RATIFIED only by a human after review

---

## 14. Out of scope (explicitly NOT delivered by 4H.2)

- Auto-execution of decisions (no autonomous hiring / firing / reassigning /
  budgeting / customer changes — advisory-only stands forever; governed
  human writes are the only writes).
- A new causal inference system (4H.1 graph is sufficient and canonical).
- Free-text LLM decision quality (quality is composed only from recorded
  evidence; no model-generated verdicts).
- Cross-organization benchmarking or data exchange (tenant isolation is
  absolute).
- Person-level decision accountability, blame attribution, or career
  outcomes (explicitly prohibited by §5.6).
- Legal, compliance, or audit-certification semantics (the fabric's audit
  events are records, not certifications).
- Duplicating 4F.7 (people decision lifecycle) — 4F.7 governs people
  decisions; 4H.2 governs company-level operating decisions; no state
  machine is shared, no engine is merged.
- New deployment, queueing, or scheduling infrastructure.
- Offline/model-training components; everything is deterministic,
  SQL-backed, online.

---

## 15. Acceptance tests (`backend/scripts/accept_slice4h2.py`, live API on :8999)

The suite must prove the architectural laws, not just feature behavior. Each
test maps to its law: reuse → temporal integrity → governance → determinism →
prediction/outcome learning → organizational memory → scalability → no
unauthorized execution. Journey mirrors 4G.7/4H.1 scripts (register fresh org
→ seed → drive events → assert). Exit 0 only when all pass:

**Suite-wide invariants (asserted across EVERY response in the suite, not
once):**
- (a) no response ranks, scores, or blames an individual on decision
  outcomes — outcomes cite decision ids and evidence ids only
  (accountability-without-blame scan);
- (b) every confidence-like number is accompanied by its evidence count
  (naked-confidence ban);
- (c) advisory/composed surfaces carry `advisory_only: True` and explicit
  not-a-prediction flags, and every cited fact carries its evidence id or
  event id (no opacity).

1. **Decision capture (law: first-class object)** — an approved decision
   returns kind, title, rationale, owner, evidence_count, state; the row is
   queryable by id through the existing `CompanyDecision` store — no second
   decision table exists.
2. **Decision lineage (law: reuse + no opacity)** — a decision's lineage is
   fully reconstructible: evidence rows (with source event ids, `captured_at`,
   evidence type incl. constraint/stakeholder) answer "why did we decide
   this" without any free text.
3. **Alternatives + why-not (law: organizational reasoning)** — a decision
   with ≥ 2 alternatives returns them with expected_outcome, exactly one
   `chosen=True`; every rejected alternative carries `why_not` and the
   why-not surface lists each rejection reason + `preferable_if` condition.
4. **Prediction at approve-time (law: prediction/outcome learning)** — a
   decision with predicted_outcome + prediction_confidence returns both after
   the existing `POST /decisions` write; the confidence surface shows
   evidence count and contradictions, never a naked number.
5. **Outcome reconciliation (law: prediction-vs-actual measurable)** — after
   `POST /decisions/{id}/outcome`, the prediction surface returns
   `actual_outcome_compare` with `predicted`, `observed`, `aligned`; the
   chosen alternative's expected_outcome is reconciled too.
6. **Learning (law: organizational memory closes the loop)** — recording an
   outcome with a lesson derives a `CompanyMemory` row (evidence lineage to
   the decision, bounded, exact-once); the memory surface cites it and no
   duplicate memory exists after replay.
7. **Precedent (law: compounding memory)** — after two similar decisions,
   "what did we do when …" returns genuinely relevant past decisions —
   "N comparable decisions" with lesson snapshots, outcome kinds,
   effectiveness, evidence counts, relevance ordering; not random documents.
8. **Impact (law: reuse of causality)** — `GET /decisions/{id}/impact`
   traces affected projects, customers, resources and strategic objectives
   through the existing 4H.1 causal chain from the decision node; no new
   causal tables appear in the response.
9. **What-if advisory-only (law: no unauthorized execution)** —
   per-alternative what-if returns `not_a_prediction: True`,
   `advisory_only: True`, bounded consequences; decision count, health rows,
   tasks and approvals are UNCHANGED afterwards — nothing executed.
10. **Contradiction surfacing (law: honest evidence)** — a recommended
    decision contradicting a past lesson returns "Evidence is conflicting"
    with both sides' evidence ids; the contradiction count shows in quality.
11. **Governance before assembly (law: access filters first)** — a scoped
    (non-org-wide) caller receives 404 / no org-wide surface; a second
    organization's data never appears in the first org's responses; no
    evidence, alternative, decision or precedent is visible beyond the
    caller's authorization.
12. **Exact-once on replay (law: determinism + state compatibility)** —
    re-publishing, with the same decision_id/source_event_id/natural keys,
    ALL EIGHT new 4H.2 events — `company.decision.evaluated`,
    `company.decision.recommended`, `company.decision.alternatives.recorded`,
    `company.decision.why_not.recorded`, `company.decision.precedents.linked`,
    `company.decision.contradiction.surfaced`,
    `company.decision.quality.composed`, `company.decision.track.updated` —
    plus the three existing governed writes (`company.decision.recorded`,
    `company.action.executed`, `company.outcome.recorded`) does not duplicate
    any row; list lengths unchanged. Asserted in the same test:
    `execute_decision` on a decision in `proposed / evaluated / recommended`
    is rejected and leaves state unchanged (backward-compatibility law,
    §4).
13. **Temporal as-of (law: temporal integrity, hard)** — `as_of` before a
    decision's deciding moment excludes decisions/evidence captured after
    it; a decision citing evidence created after `as_of` never appears; a
    track rollup recorded after `as_of` is not reflected; replay of the
    same query is byte-identical (no backward leakage).
14. **Scale law (5 → 50,000+)** — the same canonical surfaces work at the
    multi-level scopes (org / business_unit / department / team / person)
    via one parameterized schema (no second engine); all lists bounded
    (`limit`, MAX_* caps, top-N precedents); the suite asserts the bounded
    shapes hold (identical shapes for a 5-person org; plans index-backed by
    construction for enterprise volume).
15. **Moat (law: compounding dependence)** — the five-year irreplaceability
    questions (§16) are answerable from the accumulated suite state with
    provenance and governance; continued usage strictly increases the
    content behind them (more decisions → more precedents → richer
    answers).

---

## 16. Moat test

The Universal Organizational Decision Intelligence slice is a moat if and
only if ALL hold:

- [ ] A closed decision loop exists END-TO-END in one platform:
      alternatives → choice → prediction → execution → observed outcome →
      reconciliation → lesson (CompanyMemory) → precedent citation → next
      decision.
- [ ] Every link of that loop carries lineage (event ids, evidence ids) —
      no link depends on a model's memory or free text.
- [ ] The loop runs over the FULL universal operating data (4G.1-4G.7
      canonical composition) — strategy, execution, capacity, customers,
      financial, people, knowledge, coordination — not a silo.
- [ ] Temporal as-of knowledge is preserved: the org can replay what it
      knew and decided at any past instant.
- [ ] The loop is deterministic, exact-once, advisory-only, and
      governance-gated — an enterprise can bet on it without losing control.

**Strategic moat hypothesis (NOT acceptance-provable, kept deliberately):**
- [Hypothesis] Competitors (§17) could not assemble this loop from their
      data models without rebuilding a universal event fabric + governed
      decision lifecycle from scratch. This is a product/architecture
      hypothesis about the competitive landscape; a repository acceptance
      suite cannot objectively prove what competitors can or cannot build.
      It guides §17's abstraction argument and is NOT a test. The acceptance
      suite proves only what VCOS itself compounds — below.
- [ ] **The five-year irreplaceability questions all have provenance-backed
      answers** — after years of use, VCOS can answer, citing event and
      decision ids: Why did we make this decision? What evidence did we use?
      What alternatives did we reject? What did we predict? What actually
      happened? Why was the prediction wrong? What did we learn? Have we
      faced this situation before? What happened last time? What would
      happen if we chose differently now — and what parts of the company
      would it affect? (A generic AI system answers none of these about
      THIS company without the accumulated decision memory.)
- [ ] **Compounding dependence (Law 3)**: usage begets more decisions,
      outcomes and lessons; each cycle measurably enriches the precedent
      and quality surfaces; leaving the platform means abandoning the
      memory, not just a tool.
- [ ] The moat is the memory, not the price: lower total cost + broader
      unified intelligence + universal architecture are advantages; the
      reason customers stay is that their decision history, outcomes and
      lessons become a competitive asset they cannot export.

---

## 17. Differentiation

The differentiation is **the architectural abstraction, not a feature-list
argument**. Modern enterprise platforms increasingly bundle AI, workflows,
analytics and automation; claiming "they have no AI" is both false and
irrelevant. The honest comparison is the category of the abstraction:

| | ServiceNow | Celonis | Palantir | VCOS 4H.2 |
|---|---|---|---|---|
| Core abstraction | workflow / ticketing / ITSM (record-centric) | process mining over event logs (variant-centric) | ontology-driven data integration & decision support (data-centric) | company-intelligence-centric: one canonical decision → evidence → prediction → outcome → lesson → precedent object across the full operating graph |
| What a decision is | a ticket with approval transitions | a step inside a discovered process variant | an insight object in an ontology | a first-class, governed, temporal organizational object that outlives approval and keeps learning |
| Prediction accountability | approvals, not per-decision predictions | predictions about process behavior, not decisions | ML models; not per-decision recorded-and-reconciled predictions | prediction recorded at approve-time, reconciled on outcome, tracked per cohort, as-of stable |
| Organizational memory | records & KB articles (unstructured) | process history (not decision memory) | ontology snapshots (not decision memory) | compounding decision memory: precedents with lessons, outcomes, evidence counts |
| Learning loop | workflows improve manually | process variants improve | data models improve | decisions measurably improve the NEXT decision (precedent + contradiction + quality) |
| Temporal as-of | point-in-time data, not decision knowledge | point-in-time process snapshots | ontology as-of | decisions + evidence queryable exactly as-of — what the org knew when it decided |
| Governance | workflow-level RBAC | workspace permissions | coarse ontology ACLs | filtering BEFORE assembly, org-wide gates, tenant isolation on every row |
| 5 → 50,000+ | enterprise scale, siloed apps | scale, log-only | enterprise-scale, heavy | ONE canonical stack extended; bounded, indexed, paginated |

The goal is not to rebuild ServiceNow at a lower price — it is to be a
different category: an organization whose decisions are themselves an
intelligence layer that compounds.

---

## 18. Ratification Gate

4H.2 MUST NOT be implemented until the architect of record explicitly
changes the document status from **PROPOSED** to **RATIFIED**.

Ratification means ALL of the following have been confirmed:

- [ ] §0 repository analysis has been re-run against the current repository
      and every reuse anchor remains valid.
- [ ] All schema additions are explicitly enumerated: exactly the six new
      tables (§3.1–§3.6) and the additive `CompanyDecision` columns (§3.7)
      — nothing else.
- [ ] State-transition compatibility is confirmed: existing
      `approved | declined | executed | outcome_recorded` semantics are
      unchanged; pre-approval states are never executable (§4 law).
- [ ] Temporal semantics are unambiguous: the `as_of` eligibility rule with
      strict/partial modes (§5.1) is confirmed to have exactly one reading.
- [ ] Event catalog is complete: the eight new events (§6) are catalogued
      and replayed exactly-once (test 12).
- [ ] The confidence vocabulary (§5.7) is confirmed: recorded
      `prediction_confidence` is never recalculated by 4H.2.
- [ ] Acceptance tests map to every architectural law (§15), and the
      suite-wide invariants (blame-free, naked-confidence ban, no-opacity)
      are implemented.
- [ ] No second decision, memory, causal, what-if, event, authorization, or
      frontend system is introduced (§12 gate all-pass).

**Implementer directive**: OpenCode MUST stop and request clarification if
implementation would require violating any ratified contract clause. It
MUST NOT silently reinterpret, extend, or shrink the ratified contract.
The contract is the law; the implementation is the evidence.

---

*End of proposed contract. Status: RATIFIED (2026-08-19) — implementation
authorized by the architect of record. The implementation-start gate (§0) has
been re-run and the implementation report (§26 of the authorization prompt) is
the evidence that the ratified clauses were implemented.*