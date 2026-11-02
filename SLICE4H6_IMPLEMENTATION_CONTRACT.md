# SLICE 4H.6 IMPLEMENTATION CONTRACT — v0.2 (RATIFIED)
## Outcome & Performance Intelligence

> **STATUS: RATIFIED v0.2 — 2026-08-21.**
> Ratification scope, verbatim: *"RATIFY SLICE 4H.6 IMPLEMENTATION CONTRACT
> v0.2 as written, including all Q1–Q5 decisions, L20–L28, the zero-write/
> schema boundary, unified read-model, three-level numerical truth, three-level
> attribution truth, temporal basis, COMPARE ≠ RANK, No-Learning,
> No-Forecasting, and No-People-Scoring laws. Authorize Phase D fresh
> post-ratification §0 audit and Phase F pre-implementation baselines. No
> implementation is authorized until those gates pass."*
>
> Implementation order is fixed (§12 Phase G / §13 steps 1–8). Predecessor:
> 4H.5 frozen (`SLICE4H5_VERIFICATION_REPORT.md`). The §0 audit below was
> executed 2026-08-21; Phase D requires a FRESH re-audit immediately after
> ratification because the current repository is the only truth.

**One-sentence definition:**

> 4H.6 turns canonical decisions, actions, outcomes, measurements, state
> history, and causal evidence into one unified, temporally honest performance
> assessment — showing what was observed, what was measured, what changed, what
> evidence supports attribution, what can be assessed, and what remains
> unknown — without inventing facts, forecasting, claiming unsupported
> causality, scoring people, ranking alternatives, or making decisions for
> humans.

**Hard boundary:** **4H.6 measures and assesses; 4H.7 learns.**

**Relationship to 4H.5:** 4H.5 is the execution spine ("what did we authorize
and what did we do?"). 4H.6 is the evidence-interpretation spine ("what
actually happened, what changed, what evidence supports that assessment, and
what remains unknown?"). 4H.6 consumes the 4H.5 lineage and chain read-model;
it rebuilds nothing.

---

## 0. MANDATORY §0 CURRENT-REPO AUDIT (executed 2026-08-21)

### 0.1 Reuse map — the performance substrate already exists

| Existing primitive | Location (current repo) | What it already does |
|---|---|---|
| **Action outcomes** | `CompanyActionOutcome` (`app/models/company_actions.py` ~:120-145) | One-per-action (`uq_company_action_outcomes_action`); `outcome_type`, `verdict`, **`effectiveness` Float 0..1 (RECORDED human input, default 0.5)**, `evidence_json`, `measured_at`. Presented as recorded — never recomputed |
| **Action outcome aggregation** | `action_ops_engine.outcome_intelligence` + `GET /brain/knowledge/actions/outcome-intelligence` | Bounded rollups by outcome type / action type / risk, success_rate, avg_effectiveness |
| **Decision outcome write** | decision outcome handler (`company_operating_engine.py` ~:2400-2470) | `outcome_kind` (`successful\|partial\|unsuccessful`), clamped effectiveness, `outcome_evidence_json`, `lesson`; state → `outcome_recorded`; idempotent |
| **Prediction reconciliation** | same writer, `actual_outcome_compare` :2433 | `{predicted, observed, effectiveness_observed, prediction_confidence, aligned, reviewed_at}` — expected-vs-observed exists since 4H.1 |
| **Per-stage decision quality** | `CompanyDecisionQuality` (:653) + `compose_quality` (:4902) + `GET /decisions/{id}/quality` | `prediction_alignment: None = "not yet measurable", never a fake 0` — the house precedent for UNKNOWN |
| **Prediction track-record** | `CompanyDecisionTrack` (:704) + `update_tracks` (:5022) + `/execution/company/tracks` | Append-only PREDICTION cohorts (aligned/partial/misaligned, avg_effectiveness), as-of reads, history never rewritten. **Semantic ownership stays prediction-history (§0.4 Q2)** |
| **Precedents & contradictions** | `CompanyDecisionPrecedent` (:607), `CompanyDecisionContradiction` (:745) + routes | "What did we do when…" recall; contradicting-memory surfacing |
| **Decision impact trace** | `GET /decisions/{id}/impact` (:7759) | Bounded causal trace decision → allocations → projects → milestones → customers → business → objectives |
| **Metric time-series** | `BusinessMetric` / `BusinessMetricObservation` (`business_performance.py` :101/:147) | Canonical metric registry (key/kind/**direction**/unit/scope/granularity) + exact-once observations `(org, metric, observed_at, source_event_id)` — the measurement primitive 4H.6 reads |
| **Scope-level performance** | `BusinessPerformanceSnapshot` (:341) + History (:395) | Multidimensional health w/ reasons, direction-aware trajectories, gains/losses, compute_mode labels (observed/derived/projected/scenario). Owns scope-level assessment; 4H.6 adds the DECISION-centered view |
| **Performance→reality links** | `BusinessPerformanceLink` (:434) | Evidence-weighted links from metrics/drivers/targets/snapshots **to decisions** ("evidence indicates", "likely contributor") — attribution evidence source |
| **Temporal state basis** | `CompanyStateHistory` (:280) | Append-only per-event state trail (dimensions/delta/signals/dependencies/risks), occurred_at-indexed — the "before" picture |
| **Causal vocabulary** | `CAUSAL_EDGE_KINDS` (:150-170) | `execution->outcome`, `outcome->customer`, `objective->outcome`, `revenue->objective` exist |
| **Event vocabulary** | `event_models.py` :423-425 | `company.decision.recorded`, `company.action.executed`, `company.outcome.recorded` — zero new events |
| **Scope/access** | `resolve_caller_access`/`CallerAccess` (`company_context.py` :172/:221), brain `_people_access` | org_wide flag + project_ids visibility — identical gates to 4H.3–4H.5 |
| **Lineage bridge (4H.5)** | `CompanyAction.source_company_decision_id/source_scenario_id` (:71-72) + execution-chain read-model | Decision→action→outcome joins and the chain summary 4H.6 embeds |

### 0.2 Schema decision gate

> Can decision-centric performance intelligence be represented as deterministic
> read/derivation over existing canonical rows, with ZERO new tables/events?

- **RESOLVED: YES (review-confirmed).** 4H.6 takes the **read-only branch**:
  ZERO new tables · ZERO new columns · ZERO new events · ZERO new states ·
  ZERO new permission codes · ZERO workers · ZERO new engine modules ·
  **ZERO writes of any kind**. Every number is composed on read from canonical
  rows (the 4H.5 chain pattern). If implementation evidence ever contradicts
  this, fallback requires contract amendment BEFORE code.

### 0.3 Gap analysis — composition, not storage

1. **Decision-anchored measurement windows** — nothing binds
   `BusinessMetricObservation` windows to decided/executed/measured timestamps.
2. **One unified read-model** — quality, tracks, impact, reconciliation,
   action outcomes, metric deltas live in five surfaces; nothing composes them
   into Observed / Measured / Attributed / Assessed / Unknown per decision.
3. **Outcome-cohort longitudinal view** — tracks cover predictions only.
4. **Comparative side-by-side** that presents evidence and never ranks.
5. **Brain intents** with conservative collision guards.

### 0.4 Architectural questions — RESOLVED by architectural review

| Q | Decision (binding for v0.2) |
|---|---|
| **Q1** | **Pure read-only.** No cached derivations, no materialized assessments, no second truth layer. Canonical rows → deterministic derivation → surface. |
| **Q2** | **Derive outcome cohorts on read.** `CompanyDecisionTrack` keeps prediction-history semantics; it must NOT drift into a generic analytics table. |
| **Q3** | **Deterministic arithmetic over ≥2 canonical observations IS allowed**, explicitly labeled `derived` with both basis observations cited. Interpolation, filling, estimation remain prohibited (§4). |
| **Q4** | **People scoring prohibited.** Ontology is fixed: decision→quality, action→effectiveness, outcome→result, metric→measurement. Never person→score. Quality/effectiveness must not be silently transformed into employee/manager/team ratings. |
| **Q5** | **Narrowly scoped performance intents** with explicit collision guards protecting 4E.6 outcome-intelligence, 4G.7 what-if, 4H.2 tracks/precedents, 4H.4 rehearsal, and 4H.5 plan/chain phrasings (§8). |

---

## 1. Objective

Additive, governed, deterministic READ layer composing, per decision (and
across cohorts of decisions): what was authorized (4H.5 chain), what outcomes
were recorded (4E.6/4H.2), what measurably changed (metric observations within
explicit temporal windows), what evidence supports attribution (causal edges,
performance links, evidence refs), and what remains unknown — advisory-only,
temporally honest, never predictive, never prescriptive.

## 2. Laws (binding once ratified)

- **L20 Outcome Truth**: performance claims derive only from canonical recorded
  outcomes/evidence. Recorded `effectiveness` is presented as recorded — never
  silently recomputed or overridden.
- **L21 Measurement Honesty — three levels of numerical truth**:
  - `recorded` — value from one canonical observation (source cited);
  - `derived` — deterministic arithmetic over ≥2 canonical observations
    (delta, rate, percentage change), both basis observations cited;
  - `unknown` — no canonical observation exists.
  Never `estimated`, `guessed`, `filled`, interpolated, or forecast. Absence
  of evidence MUST NOT become a number (no fake zeros — extends the
  `prediction_alignment: None` precedent).
- **L22 Attribution Honesty**: temporal sequence ≠ causality. Three levels:
  `SUPPORTED` (canonical relationship exists: causal edge, performance link, or
  evidence ref), `ASSOCIATED` (change followed the decision; no canonical link),
  `UNKNOWN`. Attribution language requires SUPPORTED evidence; otherwise the
  surface says association-only or unknown.
- **L23 Comparative Neutrality**: COMPARE ≠ RANK. Side-by-sides present
  evidence and trade-offs; winner selection / good-decision-bad-decision
  verdicts are prohibited absent a future explicitly ratified governed rule.
- **L24 Temporal Performance Truth**: every comparison carries an explicit
  temporal basis — `baseline_as_of`, `comparison_as_of`, window length, and the
  anchor event (decided/executed/measured). Cross-context comparisons without a
  represented temporal basis are prohibited.
- **L25 Longitudinal Compounding**: historical outcomes remain available as
  institutional evidence enriching future analysis; append-only semantics
  everywhere; no parallel memory system; no history rewrites.
- **L26 No-Learning Boundary**: 4H.6 may report patterns of record ("three
  similar decisions had partial outcomes"); it may NOT recommend ("next time do
  X"), generalize lessons, or adapt behavior. That is 4H.7.
- **L27 No-Forecasting**: no projections, expected-future-effectiveness, or
  trend extrapolation. `projected` compute_mode belongs to the existing
  business-performance slice, not 4H.6.
- **L28 No-People-Scoring**: effectiveness/quality attach to decisions,
  actions, and outcomes only; surfaces must not emit person/manager/team scores
  (extends the existing §5.3 rule).

## 3. Schema boundary (binding once ratified)

ZERO new tables · columns · events · states · permission codes · workers ·
engine modules · **writes**. Diff confinement (DoD): `intelligence/
company_operating_engine.py` (new read fns), `api/v1/brain.py` (routes +
payload models), `knowledge/intelligence_engine.py` (intents), 2 frontend
files, plus new test/acceptance files. Nothing else.

## 4. The unified performance read-model (candidate shape — finalize at ratification)

```
GET /brain/execution/company/decisions/{decision_id}/performance
{
  "decision":        { id, kind, title, state, decided/approved/executed/reviewed },
  "observed":        { lifecycle facts, authorized/completed actions,
                       outcomes recorded, evidence counts — every item cites ids },
  "measured":        [ { metric_key, baseline{value,observed_at,status},
                         comparison{value,observed_at,status},
                         delta{value,unit,direction_aware,status: recorded|derived},
                         basis: [observation_ids] } ],
  "attributed":      [ { target, level: SUPPORTED|ASSOCIATED|UNKNOWN,
                         evidence: [edge/link/ref ids] } ],
  "assessed":        { outcome_kind, effectiveness(recorded),
                       prediction_alignment(from actual_outcome_compare),
                       quality_stage_summary, measured_change_summary },
  "unknown":         [ { what, reason } ],
  "temporal_basis":  { anchor, baseline_as_of, comparison_as_of, window_days },
  "execution_chain": { 4H.5 chain summary (embedded, bounded) },
  "honesty":         { advisory_only: true, not_a_prediction: true,
                       measures_not_judges: true }
}
```

Companion reads (candidates): outcome-cohort longitudinal view (kind/scope
cohorts over time, derived on read per Q2) and a 2–5-decision comparative
side-by-side (L23 — presents, never ranks).

## 5. Determinism / no-LLM

Same canonical rows + same as_of ⇒ byte-identical assessment. No LLM/client
imports on any 4H.6 path (`inspect.getsource` unit-test proof, 4H.5 pattern).

## 6. Scale — large graph, small query

Identity → org scope → decision → bounded neighborhood: ≤ N metric keys
(bound TBD at ratification, house style MAX_*), ≤ recent observations per key,
≤ bounded cohort scan, ≤ embedded chain bounds (10/20/10/5). Unlimited company
history; bounded per-request computation.

## 7. Governance & scope

`brain:read` + org-wide gate identical to 4H.5 routes; scoped callers ⇒ 404;
artifact/metric visibility follows resolved caller access. Advisory-only
everywhere; the human remains the judge of what the evidence means.

## 8. Brain intents (candidate — finalized with collision tests at implementation)

Conservative phrase sets for: decision performance ("how did that decision
perform", "what happened after we decided" — CAREFUL: overlaps 4H.5 chain
phrasing, must be disambiguated), measured change ("did the decision improve
<metric>"), comparison ("compare the outcomes of these decisions").
Collision guards hold for: "my actions"/"action center"/what-if (4G.7/4H.4),
"execution chain"/"action plan" (4H.5), "track record"/"precedent" (4H.2),
"outcome intelligence" (4E.6). Exact vocabularies settled during
implementation with unit-tested guards, within the ratified intent NAMES.

## 9. Anti-duplication (binding)

No PerformanceEngine/AnalyticsEngine/KPIEngine/ScoringEngine/
EffectivenessEngine modules; no performance_runs/decision_scores/
performance_snapshots tables; no new approval systems; no people scoring; no
forecasting; no recommendation generation; no writes to canonical outcome rows;
no extension of CompanyDecisionTrack semantics (Q2).

## 10. Out of scope

4H.7 learning/pattern→lesson/recommendation; next-action suggestions from
performance; employee/team grading; financial forecasting; external benchmarks;
any mutation of canonical rows; retroactive judgment of past decisions.

## 11. Moat T1→T4

T1 young company: thin assessment (one outcome, few observations, unknowns
explicit). T2 operating: more actions/outcomes/observations accumulate. T3: the
SAME decision's assessment is strictly richer — more measured deltas, stronger
attribution, historical comparisons — with zero code change. T4: cohorts of
similar decisions/scales/windows become comparable institutional intelligence
without a second memory system. Value compounds because company history
compounds.

## 12. Definition of DONE (phased)

- **Phase C — Ratification**: this contract's STATUS becomes RATIFIED by
  explicit declaration. Until then nothing below may start.
- **Phase D — Fresh post-ratification §0 re-audit**: re-confirm every §0.1 row
  against the CURRENT repository (not this audit).
- **Phase E — Schema gate proof**: introspection shows zero additions; zero
  writes proven behaviorally (event-total stability + DB row deltas).
- **Phase F — Baselines BEFORE implementation**: 4G.7 14/14 · 4H.1 16/16 ·
  4H.2 19/19 · 4H.3 17/17 · 4H.4 15/15 · 4H.5 17 assertions — all green on
  pre-4H.6 code.
- Then: unit tests green → live acceptance N/N on :8999 → regressions green
  (all baselines unchanged + full pytest + `tsc --noEmit`) → diff confined to
  §3 files → schema/event/diff/anti-duplication audits →
  `SLICE4H6_VERIFICATION_REPORT.md` → freeze.
