# SLICE 4H.5 — VERIFICATION REPORT
## Strategic Decision-to-Action & Execution Intelligence

**Status: DONE — VERIFIED — FROZEN**
Date: 2026-08-21 · Contract: `SLICE4H5_IMPLEMENTATION_CONTRACT.md` v0.2 (ratified)
Predecessor: 4H.4 (frozen, `SLICE4H4_VERIFICATION_REPORT.md`) — unchanged.

---

## 1. What was built (and what was not)

4H.5 creates **no execution capability**. It makes the existing 4E.6 execution
capability **provenance-connected and intelligible** from decision to outcome:

```
CompanyDecision (anchor only)
   → advisory ACTION PLAN   (ephemeral, never persisted, byte-deterministic, no generated_at)
   → HUMAN AUTHORIZATION    (EXISTING POST /brain/knowledge/actions + optional lineage)
   → UNCHANGED 4E.6 lifecycle (policy → approve → transition → route → outcome)
   → EXECUTION CHAIN        (live truthful read-model, regenerated per read)
```

Not built (by contract): no action manager, no workflow engine, no automation,
no new tables, no new events, no new states, no new permission codes, no LLM,
no learning (4H.7 territory).

## 2. Implementation delta (diff-confinement audit vs DoD §14)

| File | Change |
|---|---|
| `backend/app/models/company_actions.py` :71-72 | Two additive nullable indexed lineage columns `source_company_decision_id`, `source_scenario_id` (String(64), see §6 deviation) |
| `backend/app/db/database.py` :245-256 | Idempotent `_POSTGRES_ALTERS`: 2× ADD COLUMN IF NOT EXISTS + 2× ALTER TYPE widening + 2× CREATE INDEX |
| `backend/app/knowledge/action_ops_engine.py` | `_LINEAGE_DECISION_STATES`; `propose()` lineage params + validation (`source decision not found` / state < approved / `source scenario not found`); reason/source_problem fallbacks from the decision; replay+create persist lineage; `_payload` exposes both ids |
| `backend/app/intelligence/company_operating_engine.py` :157-159, :7569, :7778 | Bounds (`MAX_PLAN_STEPS=5`, `MAX_CHAIN_ACTIONS=10`, evidence ≤20, artifacts ≤10, outcomes ≤5); `_PRE_APPROVAL_DECISION_STATES`; `derive_action_plan` (non-inventive; canonical anchors only: live edges touching the decision, live-verified open risks from stored context, projects from scope/context deps; zero-step ⇒ `insufficient_canonical_basis`; NO generated_at); `execution_chain` (lineage-filtered actions, audit evidence, visibility-filtered artifacts, outcomes, lesson, honesty block, generated_at) |
| `backend/app/api/v1/brain.py` :8284, :8320 | `POST /execution/company/decisions/{id}/action-plan` (brain:read, org-wide⇒404, unknown⇒404, pre-approval⇒409 detail.rejected) and `GET .../execution-chain` (brain:read, org-wide gate, caller access honored); `BrainActionProposeIn` + two optional lineage fields passed through to the EXISTING propose surface |
| `backend/app/knowledge/intelligence_engine.py` :151-165, :3900-3957 | Intents `company_execution_plan` / `company_execution_chain` inserted BEFORE the generic `("execution",…)` rule (collision-safe phrasing; "my actions"/"action center"/what-if untouched); plan branch byte-deterministic, chain branch timestamped; `_resolve_decision_anchor` (kind-word or title-token ≥6 chars, newest-first scan ≤50, fallback newest) |
| `frontend/lib/api.ts`, `frontend/app/(app)/execution/company-tab.tsx` | Payload type + interfaces + API fns; "Decision to action" panel (derive plan → authorize step via existing surface with lineage → live chain refresh). `tsc --noEmit` exit 0 |
| NEW `backend/tests/test_4h5_engine.py` | 10 unit tests (§4) |
| NEW `backend/scripts/accept_slice4h5.py` | Live acceptance, 16 ratified checks (§3) |

**Zero**: new tables · new event names · new engines/workers/queues/modules ·
new permission codes · LLM calls on either new path. `publish_event` hits in
`company_operating_engine.py`: **0**. Untracked files are contracts/reports/
accept scripts/tests only.

## 3. Live acceptance — `accept_slice4h5.py` on :8999 — 17/17 assertions (16 ratified checks), exit 0

1 ✅ bounded anchored honest plan · 2 ✅ dry-run writes nothing / zero events ·
3 ✅ pre-approval (declined) ⇒ 409 · 4 ✅ non-invention (`insufficient_canonical_basis`,
zero steps) · 5a/5b ✅ authorize-with-lineage via EXISTING surface + fingerprint
exact-once replay · 6 ✅ unchanged 4E.6 lifecycle (low-risk auto-approve inherited,
transitions + outcome + `company_action_events` trail ≥2) · 7 ✅ chain stitched,
bounded, truthful · 8 ✅ decision row immutable across read-only tail (envelope
`generated_at` excluded — per-request artifact, not a mutation) · 9 ✅ isolation:
sibling org AND project-scoped manager (org-wide assignment removed, brain:read
delegated — 4H.3 pattern) both 404 on both routes · 10 ✅ byte-identical plan ·
11 ✅ schema introspection: exactly 2 columns, 0 forbidden tables, 0 rows for any
candidate new event name · 12 ✅ intents resolve + collision guards hold ·
13 ✅ origin compatibility (unlineaged action valid & absent from chain; 4H.4
scenario surface intact) · 14 ✅ project-scoped authorization keeps lineage ·
15 ✅ moat T1→T3 chain strictly richer ((1,7,1)→(2,14,2)) + T4 joinable ids ·
16 ✅ honesty sweep (advisory_only + not_a_prediction everywhere;
`human_authorization_required` on plans).

## 4. Unit tests — `test_4h5_engine.py` — 10/10 passed

Plan-from-anchors + eventless byte-identical dry-run · pre-approval rejection ·
non-invention · lineage propose + fingerprint replay · validation ValueErrors ·
chain stitching/bounds · tenant isolation · intents + collision guards · L16
origin compatibility · no-LLM source-scan proof (`inspect.getsource` of both
engine paths contains no LLM/client imports).

## 5. Regressions — all green

| Suite | Result |
|---|---|
| 4G.7 live | **14/14** (unchanged) |
| 4H.1 live | **16/16** (unchanged) |
| 4H.2 live | **19/19** (unchanged) |
| 4H.3 live | **17/17** (unchanged) |
| 4H.4 live | **15/15** (unchanged) |
| Full pytest (129 files, xdist chunks) | **1131 passed, 0 failed**, exit 0 every chunk |
| `npx tsc --noEmit` | **exit 0** |

## 6. Contract deviation (one, documented)

`source_company_decision_id` specified as String(32); implemented **VARCHAR(64)**.
Live acceptance caught real decision ids `"dec:{kind}:{hex12}"` reaching 37 chars
(`improve_coordination`) — String(32) truncated (`StringDataRightTruncationError`
on the first lineage authorize). Widening is additive, idempotent (ALTER TYPE is
metadata-only for varchar growth), and covered by a second idempotent ALTER so
installs that already created the narrow column converge. Intent of the contract
("fit a decision id") preserved; no other deviation.

## 7. Operational notes (environment truth for future slices)

- Decision rows are **event-sourced**: `POST /execution/company/decisions` only
  emits `company.decision.recorded`; the row materializes when events are
  processed. Drain before anchored reads.
- Decision create accepts only `state ∈ {approved, declined}`; pre-approval
  probes use `declined` (in `_PRE_APPROVAL_DECISION_STATES`).
- Run the stack with `APP_ENV=test` (disables background workers) — workers
  wedge the connection pool at current data volume.
- Brain query answers inline the chain sections at top level
  (`intent: "company_execution_chain"`, keys `decision/evidence/actions/...`),
  they do NOT nest under an `execution_chain` key.
- pytest-xdist (`-n 4`) is available and green — full suite drops from ~2.5 h
  serial to ~25 min.

## 8. Freeze

**Slice 4H.5 is frozen.** Any further change to the two lineage columns, the
plan/chain derivation, the two routes, or the two intents requires a new
contract amendment. Next slice starts from this report.
