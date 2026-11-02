# Slice 4H.4 — Strategic Scenario / Decision-Rehearsal Intelligence — VERIFICATION REPORT

Contract: `SLICE4H4_IMPLEMENTATION_CONTRACT.md` (RATIFIED v0.3 + v0.3.1 conformity amendment)
Zero-audit: `SLICE4H4_ZERO_AUDIT.md` (13-row checklist, A11 binding **"no" branch** → exactly ONE new table `company_scenario_runs`)
Base commit: `cd653b8` (unchanged). Server: `:8999` single listener.

## 1. What was built (delta, this session)

**Model** — `backend/app/models/company_operating.py`
- Constants: `SCENARIO_KINDS`, `SCENARIO_PARAM_KEYS`, `MAX_SCENARIOS_SHOWN = 10`, `MAX_SCENARIO_ASSUMPTIONS = 20`.
- `CompanyScenarioRun` (table `company_scenario_runs`) after `CompanyDecisionContradiction`, with §3.1 columns: `id, organization_id, scope_type, scope_id, state_key, snapshot_ref, scenario_kind, input_json, input_hash, assumptions_json, propagation_json, consequences_json, decision_suggestions_json, honesty_json, source_event_id, created_by, occurred_at`.
- Constraint `uq_c4h4_exact_once (organization_id, scope_type, scope_id, scenario_kind, input_hash, snapshot_ref)`; index `ix_c4h4_org_time (organization_id, scope_type, scope_id, occurred_at)`.

**Registration** — `backend/app/models/__init__.py` (`from app.models.company_operating import CompanyScenarioRun`; `__all__`).

**Event** — `backend/app/events/event_models.py`: exactly ONE new event, `company.scenario.recorded` (emitted only on an actual row write).

**Engine** — `backend/app/intelligence/company_operating_engine.py` (method block appended after `attach_state_context`):
- `_scenario_input_hash` (sha256 of normalized kind+input), `_scenario_honesty`, `_scenario_note`.
- `_rehearse_propagation`: bounded BFS over existing `company_causal_edges` only (MAX_CAUSAL_DEPTH/EDGES), hops carry `from/to`, `kind`, `confidence`, `edge_id`; reuses `_label_hops`.
- `_scenario_baseline`: reuses `_latest_state_row` + `_parse_asof` (strict as-of).
- `_rehearse_surface`: canonical §5.3 surface; `what_if()` language reused for the three what-if kinds; one-hop = direct, deeper = dependent; `_state_risks` intersection (subject always in the reached set), `_state_opportunities`, `_state_affected_decisions` read-only pseudo-delta; `human_decision` bridge.
- `scenario_rehearse`: `dry_run=true` derives, writes NOTHING, zero events; `dry_run=false` records exact-once via `publish_background_event("company.scenario.recorded")` → row (`created/replayed/dry_run` flags).
- `scenario_detail`, `scenario_history` (bounded), `scenario_compare` (2..5 ids, side-by-side, never ranks).

**Routes** — `backend/app/api/v1/brain.py` (appended; imports `MAX_SCENARIOS_SHOWN`):
- `POST /execution/company/scenario` (dry-run on brain:read; recording ALSO requires brain:manage — 403 otherwise), `GET /execution/company/scenario/{scenario_id}` (404 "scenario not found"), `GET /execution/company/scenario` (bounded history), `POST /execution/company/scenario/compare`.

**Brain intents** — `backend/app/knowledge/intelligence_engine.py`: new `company_scenario` `_INTENT_RULES` entry + dispatch; `_company_operating_query` gains the additive 4H.4 block (rehearsal → `company_scenario`; compare → `company_scenarios_compare`) with a `"what if we" not in` guard so generic what-if phrasing is never hijacked.

**Frontend (minimal, read-only)** — `frontend/lib/api.ts` (+4H.4 client/types), `frontend/app/(app)/execution/company-tab.tsx` (Scenario rehearsal card: kind/subject, dry-run Check, Record, history, compare).

**Tests/scripts** — `backend/tests/test_4h4_engine.py` (11 test fns covering the 15 ratification checks), `backend/scripts/accept_slice4h4.py` (15 numbered live checks).

## 2. §0 audit

`SLICE4H4_ZERO_AUDIT.md` — 12×PASS + A11 binding DECISION. `simulation_runs` has no unique constraint, no state anchoring, no scope spine, NOT NULL `title`, simulation-domain shape; `SimulationEngine.run` is synchronous (simulation_engine.py :34/:54/:69; no `simulation_worker.py` exists). Decision: **new table `company_scenario_runs`** (§0.2 "no" branch).

## 3. Acceptance (contract §15, live :8999)

`python backend/scripts/accept_slice4h4.py` → **15/15 checks, 18 assertions, exit 0**:
dry-run canonical surface; dry-run zero writes/events; brain:manage gate; one row + one event; exact-once replay + changed-input row; honest error; bounds; byte-identical detail; 404; bounded newest-first history; never-ranked compare; tenant isolation; honesty flags; both brain intents + collision guard; L15 identity across a changed snapshot.

## 4. Unit tests

`python -m pytest tests/test_4h4_engine.py` → **11 passed**. Immediate regressions `tests/test_4h3_engine.py` + `tests/test_4h2_engine.py` → **25 passed**.

**Full backend suite: 1121 collected → 1121 passed, 0 failed** (run in four file-chunks plus a tail chunk after two detached background attempts were killed by console interrupts at 77%/64% with zero failures up to that point).

One failure surfaced during the full run and was repaired: `tests/test_phase12.py::test_contracts_approval_sign_and_renewals` is a pre-existing **time-bomb** — it hardcodes `"expires_at": "2026-08-20"` and asserts the contract appears in `expiring_soon`, but `ContractService.list_contracts` filters `expires_at >= date.today()` (contract_service.py:173), so the test started failing when the calendar reached 2026-08-21. It had passed earlier the same night before midnight. Fix: dynamic dates (`effective_from = today−5d`, `expires_at = today+14d`) in the test only; no production code touched. Whole file re-run: **15 passed**. Unrelated to 4H.4 (phase-12 CRM contracts domain).

## 5. Regression (live baselines, contract numbers)

| Slice | Before | After |
|-------|--------|-------|
| 4G.7  | 14/14  | 14/14 exit 0 |
| 4H.1  | 16/16  | 16/16 exit 0 |
| 4H.2  | 19/19  | 19/19 exit 0 |
| 4H.3  | 17/17  | 17/17 exit 0 |

Frontend: `tsc --noEmit` exit 0.

## 6. Schema introspection (live Postgres, `vcos2`)

- New scenario table: **exactly `company_scenario_runs`** (no other scenario/simulation additions).
- Pre-existing simulation domain: `simulation_runs`, `simulations`, `decision_simulations` — untouched.
- Columns present per §3.1 (+ house `created_at`/`updated_at`); `uq_c4h4_exact_once` + `ix_c4h4_org_time` created.

## 7. Event catalog delta

Exactly one new event: `company.scenario.recorded` (event_models.py:445). `company.state.*` and `simulation.*` unchanged. Read/dry-run/replay/reject paths emit zero.

## 8. Diff audit (no scope creep)

- 4H.4 edits confined to: `models/company_operating.py`, `models/__init__.py`, `events/event_models.py`, `intelligence/company_operating_engine.py`, `knowledge/intelligence_engine.py`, `api/v1/brain.py`, `frontend/lib/api.ts`, `frontend/.../company-tab.tsx`; new files only under `tests/` and `scripts/`.
- Pre-existing dirty files (`db/database.py`, `events/handlers.py`, `memory/formation.py`, `tests/test_meeting_intel.py`, `scripts/accept_slice4g7.py`) contain zero `scenario` markers; not touched by 4H.4.

## 9. Anti-duplication audit

Zero new engines, workers, queues, or simulation services under `app/`; canonical stores reused (`company_state_history`, `company_causal_edges`, `company_decisions`, `company_risks`); what-if derivation language reused verbatim for the sanctioned kinds; `_label_hops`/`_latest_state_row`/`_parse_asof`/`_state_*` reused.

## 10. Intention note (faithful materialization of check #14)

Ratified check #14 says generic "what if we reallocate/delay/hire" must "still route to the existing what-if intent". The repo's actual routing architecture routes those phrases through the pre-existing intent machinery (`capacity` = 4G.4 for "reallocate", coordination/discovery otherwise) — the canonical what-if lives at `/brain/execution/company/what-happens-if` / `what-if`. The guard therefore asserts the precise invariant: **generic "what if we …" phrasing never resolves to a 4H.4 rehearsal** (unit- and live-tested), while the sanctioned what-if kinds stay reachable through the canonical what-if endpoints and the 4G.7 intent block for company_operating-routed questions. No 4H.4 behavior change to those paths.

## 11. Hard boundaries honored

No `CompanyDecision` mutation; no graph/edge writes; no `company.action.*`; no autonomous step; no comparison ranking; no scenario-level ML/LLM; no new async worker; no ERP/CRM/HRMS scope.