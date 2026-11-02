# SLICE 4H.4 — §0 CURRENT-REPO AUDIT REPORT

**Audit date:** 2026-08-20
**Governing contract:** SLICE4H4_IMPLEMENTATION_CONTRACT.md **v0.3.1 (RATIFIED)**
**Audit basis:** the CURRENT repository is the only truth; every row below was
re-inspected at audit time, not assumed from the contract.
**Repo state at audit:** all work uncommitted on top of `cd653b8` (Ratify 4H.1);
4H.3 implementation live on :8999 (single listener); 4H.3 frozen.

---

## A. Audit checklist (13 rows)

| # | Check | Result | Evidence |
|---|---|---|---|
| A1 | Reuse map — engine anchors exist at contract lines | PASS | `company_operating_engine.py`: `what_if` :1866, `_what_if_response` :2020, `_derive_causal_edges` :3291, `causal_chain` :3637, `decision_what_if` :5549, `living_state` :6648, `state_delta` :6733, `state_risks` :6767, `state_opportunities` :6778, `state_affected_decisions` :6791 |
| A2 | Reuse map — brain surfaces exist | PASS | `brain.py`: `POST /execution/company/what-if` :7074, `POST /execution/company/decisions/{decision_id}/what-if` :7974, `GET /execution/company/state` :6909, `state/dependencies` :8010, `state/risks` :8035, `state/opportunities` :8054, `state/decisions` :8073, `state-context` :8092 |
| A3 | Reuse map — constants/bounds exist | PASS | `models/company_operating.py`: `WHATIF_SCENARIOS` :143, `MAX_WHATIF_CONSEQUENCES=5` :147, `COMPANY_SCOPE_TYPES` :152, `MAX_CAUSAL_EDGES=60` :173, `MAX_CAUSAL_DEPTH=5` :174 |
| A4 | Reuse map — 4H.1 causal + 4H.2 decision stores exist | PASS | `CompanyCausalEdge` :433 / `company_causal_edges` :442; `CompanyDecision` :340 / `company_decisions` :349; exactly six `company_decision_*` tables: alternatives :489, evidence :546, precedents :598, quality :644, tracks :695, contradictions :736 |
| A5 | Reuse map — 4H.3 state store exists | PASS | `CompanyStateHistory` :263 / `company_state_history` :274; state events `company.state.composed`/`company.state.changed` (event_models :441-442, engine :6488/:6502); ack handler `handle_company_universal_audit` (handlers.py :3225) |
| A6 | Reuse map — opportunity surface exists | PASS | `PatternDetection` (models/intelligence.py :315), `UniversalInsight` (:445), `KnowledgeRecommendation` (models/knowledge.py :637) |
| A7 | Reuse map — brain router + intents exist | PASS | `_INTENT_RULES` (intelligence_engine.py :103), `company_operating` rule :322, `_company_operating_query` :3791 with `what_if` routing :3895 and 4H.3 branches (:3824 living state, :3835 state delta, :3871 risks, :3880 opportunities); intent dispatch :4538-4540 |
| A8 | Reuse map — gates exist | PASS | `_people_access` (brain.py :2532), `_scope_allowed` :2536, `_require_scope_visibility` :2912, `require_permission` in `app/api/deps.py` (used throughout) |
| A9 | No pre-existing 4H.4 code/contracts anywhere | PASS | grep `company_scenario|scenario_kind|4h4|4H4|decision_rehearsal` across `backend/**/*.py` → zero matches; no 4H.4 contract/report files exist (glob: only 4H.1/4H.2/4H.3 contracts + 4H.2 report) |
| A10 | SimulationRun premise checked on REAL topology | PASS (finding) | NO `simulation_worker.py` exists. Lifecycle is synchronous inside `app/autonomy/simulation_engine.py` (`SimulationEngine.run` :34 writes `running → finished` inline :54/:69, publishes `simulation.finished` :73-77). `simulation.completed` event defined (event_models :340) and used by `app/digital_twin/simulation_service.py` :109. Contract §0.2 amended to record this finding |
| A11 | §0.2 schema decision made from evidence | DECISION | **"no" branch — exactly ONE new table `company_scenario_runs` (§3.1).** Rationale in section B below |
| A12 | Forbidden artifacts absent | PASS | No ScenarioGraph/ScenarioMemory/ScenarioAIEngine/scenario_worker/scenario_queue classes, tables, workers or queues anywhere in the repo (A9 coverage) |
| A13 | 4H.3 frozen | PASS | No new architectural change since 4H.3 acceptance 17/17; repository unchanged on top of `cd653b8` (only 4H.3/4H.4 contract + report documents added) |

**Result: 12×PASS + 1 binding DECISION (A11). No blockers.**

---

## B. §0.2 schema decision — `simulation_runs` reuse vs ONE new `company_scenario_runs`

**Question (contract §0.2):** can the existing `simulation_runs` table persist a
**deterministic, state-anchored, exact-once** 4H.4 scenario result without its async
worker lifecycle and without reshaping its generic domain semantics?

**Evidence (inspected at audit time):**

1. E1 — Table domain shape (`backend/app/models/simulation.py`, 36 lines). Docstring:
   "One what-if simulation across multiple organizational domains." Columns are
   simulation-domain: `title` (NOT NULL, String(255)), `question` (free text),
   `domains` (subset of `SIMULATION_DOMAINS` — budget/infrastructure/knowledge/
   hiring/projects/training/customers/growth/legal/support, engine :25-28),
   `results`/`risk` (forecast + risk summary), `status` (queued/running/finished/
   failed, :11), `completed_at`, `duration_ms`, `source_event`. Index only on
   `organization_id` (:19). **Zero** unique constraints, zero state anchoring,
   zero scope columns.
2. E2 — Lifecycle. Engine writes `running → finished` synchronously in the request
   path; no worker exists (A10). 4H.4 could write rows "finished at derivation
   time" (contract §3.2) — no topology conflict. This prong of the question is
   satisfied, but it is not the deciding prong.
3. E3 — Domain semantics reshape. 4H.4 persistence needs (per §3.2 the additive
   list): `scenario_kind`, `state_key`, `snapshot_ref`, `input_hash`,
   `honesty_json`, `decision_suggestions_json`, `exact_once_source_event` — PLUS the
   L14 scope fix now in §3.1 (`scope_type`, `scope_id`). Adding 9 columns + a
   6-column unique constraint + a second writer path + a second serializer to a
   Phase-19 table **does** reshape its domain semantics: the row contract of every
   existing simulation write and every future Phase-19 evolution (worker,
   calibration, forecasting extensions) becomes coupled to 4H.4's guarantees, and
   the mandatory `title` NOT NULL would force a fabricated, domain-meaningless title
   per rehearsal.
4. E4 — Master Vision separation. §2/§19 draw a hard line: simulations (forecasting/
   simulation product territory) are NOT 4H.4; rehearsals are deterministic,
   canonical, state-anchored, scope-resolved. Persisting rehearsals inside the
   simulations table would fuse the two domain semantics in one storage row and one
   list surface — exactly the fragmentation the Master Vision Constraint prohibits.
5. E5 — Event truth. The table's native events are `simulation.finished` /
   `simulation.completed`. 4H.4 requires exactly one new event
   `company.scenario.recorded` on an actual rehearsal write. Sharing the table leaves
   the audit stream's row→event mapping ambiguous for the same storage.

**Verdict:** the reshaping prong (E3) fails and the vision separation (E4/E5)
counsels separation. **Branch "no": create exactly ONE new table,**
`company_scenario_runs`, **with the exact §3.1 column spec; zero additive columns on
`simulation_runs`; zero new tables beyond it.**

Consequence: the §3.1 table is the binding schema for implementation, with
`uq_c4h4_exact_once` over `(organization_id, scope_type, scope_id, scenario_kind,
input_hash, snapshot_ref)` and `ix_c4h4_org_time` over `(organization_id,
scope_type, scope_id, occurred_at)`.

---

## C. Conformity amendment record (v0.3.0 → v0.3.1)

L14/§7.3 require *"the resolved scope is stored in the scenario row"*; §3.1 in v0.3.0
had scope only inside `state_key`. To honor the ratified invariant (L14), §3.1 now
declares explicit `scope_type`/`scope_id` columns and the exact-once + listing keys
include the resolved scope (the `organization_scope` of the canonical structure).
Contract §0.2 also records the real-topology finding (no `simulation_worker.py`,
E2/A10). Audit history updated. No other change; no implementation begun.

---

## D. Baseline gate (run 2026-08-20 on the single clean server :8999)

| Baseline | Contract | Result |
|---|---|---|
| 4G.7 | 14/14 | **14 passed, 0 failed** (exit 0) |
| 4H.1 | 16/16 | **16 passed, 0 failed** (exit 0) |
| 4H.2 | 19/19 | **19 passed, 0 failed** (exit 0) |
| 4H.3 | 17/17 | **17 passed, 0 failed** (exit 0) |

All baselines green on ONE clean server with the current (4H.3-final) code.
No 4H.4 code exists yet. Per the ratification statement, every gate is now
satisfied and implementation of 4H.4 ONLY may begin: §3.1 table, ONE event,
engine + routes + intents + compare, minimal frontend, `test_4h4_engine.py`,
`accept_slice4h4.py` 15/15, full regressions, diff audit.