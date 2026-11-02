# SLICE 4H.7 — PHASE 0 SUBSTRATE AUDIT REPORT

## Organizational Learning & Institutional Intelligence

- **Date**: 2026-08-22
- **Scope**: READ-ONLY repository + live-database audit. No code changed, no schema touched.
- **Question answered**: *"What institutional-learning substrate already exists in the current Virtual Company OS, and how much of 4H.7 can be composed from it without creating duplicate intelligence infrastructure?"*
- **Method**: full `__tablename__` inventory of all 437 public tables → semantic token scan → model-body reads → live `asyncpg` row counts → writer/route census (greps over `app/`).

---

## 1. Headline verdict

**The substrate already exists — abundantly.** VCOS has shipped at least four prior
learning/memory slices (Phase 19, 4D.3–4D.5, 4E.7, plus the 4H.1/4H.2 evidence
chain). A naive "build a LearningEngine + lessons table" would have duplicated
**five** living systems. The strong-moat rule therefore resolves cleanly:

> **4H.7 requires ZERO new tables.** It is a *governed composition and
> qualification layer* over existing primitives — its real job is connecting the
> 4H.\* decision→outcome→measurement→attribution→assessment chain (which today
> feeds NOTHING that learns) into the existing institutional-memory substrate,
> under an explicit epistemic ladder.

## 2. Living substrate inventory (live row counts, :8999 stack DB)

### 2a. Pattern primitive — Slice 4D.4 ✅ ALIVE
| Table | Rows | Notes |
|---|---|---|
| `pattern_detections` | **792** | Full lifecycle `candidate→emerging→confirmed→persistent→fading→resolved`; `count`, bounded `confidence` + component breakdown (`detail_json`); first-class evidence lineage (`evidence_json`, `supporting_event_ids`, `supporting_memory_ids`, `supporting_relationships`); governance scope (`scope_type/scope_id/auth_project_id`); temporal window fields; natural key `(org, pattern_type, key)` idempotent upsert; **family taxonomy already includes `"decision"`** |
| `pattern_events` | 1,207 | Per-(pattern,event) lineage; replay-safe |

Writer: `app/intelligence/pattern_pipeline.py` (~1,100 ln, change-driven,
self-described "**No parallel architecture**: composes the existing
PatternDetection model"). Presentation: `pattern_engine.py`. Consumers:
risk_engine, notification_engine, insight pipelines, company state composer.
Brain routes already live: `GET /brain/patterns`, `/{id}`, `/evidence`,
`/history`, `/related`.

### 2b. Institutional lesson primitives — TWO living systems
**(i) Slice 4E.7 Universal Knowledge Operating Loop** ✅ ALIVE (small but real)
| Table | Rows |
|---|---|
| `organizational_learning` ("a lesson the company learned", exact-once by (kind,fingerprint), lifecycle `discovered→candidate→supported→authoritative→confirmed→superseded→archived`, confidence, evidence_json, claims_updated_json) | **20** |
| `learning_evidence` (immutable per-source links w/ role+weight) | 54 |
| `outcome_assessments` (expected-vs-actual, exact-once per subject) | 7 |
| `decision_outcomes` (FK → legacy `decisions.id`) | 6 |
| `recommendation_outcomes` (per-kind deterministic quality) | 7 |
| `knowledge_claim_lifecycle` (append-only claim stage ledger) | 14 |

Engine: `app/knowledge/learning_engine.py` (**2,929 ln**) — docstring states the
exact philosophy 4H.7 needs: *"Every operation is deterministic rules +
arithmetic over persisted evidence: the LLM is never asked to decide what is
true."* Wired to brain `/brain/knowledge/loop/learning{,/{id}}`, assess/learn/
contradiction-resolution routes, and universal query intents (`learned`, `why`,
`should`). Also emits `company_changes` (34), `operating_insights` (24),
`company_health_signals` (80), `impact_assessments` (6).

**(ii) Company Memory automation — Phase 19 + Slice 4D.3** ✅ ALIVE (massive)
| Table | Rows |
|---|---|
| `company_memory` | **94,174** |
| `memory_events` (formation lineage, unique per event_id — replay-safe) | 772 |
| `memory_outcomes` (full observed-outcome history per memory) | 99 |
| `organization_timeline` | 135,381 |
| `organization_context` | 1,041 |

CompanyMemory **already has**: `memory_category` = event/experience/**lesson**/
outcome; `fact_kind` = **fact/observation/inference/lesson** ("VCOS never
presents inference as fact"); confidence semantics 1.0 structured / 0.6
corroborated / 0.3 inference; evidence lineage JSON; dedupe_key; governance
auth_scope (org/project/personal); supersedes_id; related_memory_ids;
`memory_type` vocabulary includes **`institutional`**.

### 2c. Canonical insight composition — Slice 4D.5 ✅ ALIVE
`universal_insights` 425 + `insight_events` 2,008 (+ `company_insights`
freshness markers 1,904). Brain routes `/brain/insights{,/{id},/evidence,
/history,/related}` live.

### 2d. The 4H.* evidence chain (4H.1–4H.6) ✅ ALIVE — **but learns nothing**
| Table | Rows |
|---|---|
| `company_decisions` | 246 |
| `company_actions` (incl. 8 lineage actions) | 121 |
| `company_action_outcomes` | 28 |
| `business_metric_observations` | 155 |
| `business_performance_links` (4H.6 attribution) | 8 |
| `company_decision_quality` (additive snapshots) | 353 |
| `company_decision_tracks` (append-only cohort) | 144 |
| `company_decision_precedents` (cited_lesson as-of snapshots!) | 61 |
| `company_decision_contradictions` (both sides preserved) | 8 |
| `company_decision_evidence` | 518 |
| `company_causal_edges` (bounded derived causality window) | 5,837 |
| `decisions` (legacy) | 126 |

Note: `CompanyDecisionPrecedent.cited_lesson` already snapshots lessons as-of
precedent time; `CompanyDecision` carries a lesson payload field.

### 2e. Other learning-adjacent (context only)
- `learning_events` 1,550 — fed by the SECOND, older
  `app/intelligence/learning_engine.py` (.record/.lessons/.summary; used by
  strategic_execution/resource_allocation/customer engines + learning_worker).
- `executive_insights`/`executive_recommendations` 0 / **760,851** (demo-seed
  scale — treat as noise, not substrate).
- Dead/empty: `workflow_insights`, `search_insights`, `ai_recommendations`,
  `ai_tenant_memory`, `learning_cycles`, `learning_paths`, `learning_history`,
  `learning_recommendations`, `governance_recommendations`.
- **NOT institutional learning despite the name**: `lessons`/`lesson_progress`
  (LMS courseware, 0 rows), `learning_profiles` (employee skill labels),
  `collaboration_evidence`, `expertise_evidence` (people-skill domain —
  off-limits per no-people-scoring law).

## 3. The gap analysis — what 4H.7 actually adds

1. **The 4H.* chain is orphaned from learning.** `pattern_pipeline` consumes
   operational events (task.blocked, approvals…); `knowledge/learning_engine`
   consumes ITS OWN OutcomeAssessment loop over legacy decisions /
   knowledge_recommendations. **Nothing** consumes CompanyActionOutcome +
   BusinessMetricObservation deltas + BusinessPerformanceLink attribution +
   company_decision_quality snapshots as a *learning evidence class*.
   → This is exactly the user's thesis: 4H.6 produced the evidence substrate;
   4H.7 makes it feed institutional memory.
2. **No cross-substrate institutional composition.** Patterns, lessons (×2
   systems), causal edges, precedents/contradictions, and performance
   assessments are islands. No surface answers *"what has the company learned
   from similar situations"* with provenance walking Lesson→Pattern→
   Assessment→Measurement→Outcome→Action→Decision.
3. **No governed epistemic ladder.** PatternDetection has a lifecycle but no
   organization-level classification of a *body of evidence* into emerging /
   recurring / established-with-contradictions etc. Thresholds must be defined
   in the contract (not invented ad hoc in code).
4. **Contradiction honesty is un-connected.** `company_decision_contradictions`
   (8 rows) and precedent citations exist; no learning surface aggregates
   support-vs-contradiction into pattern status like SUPPORTED_WITH_
   CONTRADICTIONS.

## 4. Reuse-before-create gate — ruling

Every capability 4H.7 needs maps onto an existing primitive:

| 4H.7 need | Existing substrate | New table? |
|---|---|---|
| Pattern w/ cohort + recurrence + lifecycle | `pattern_detections` (+pipeline) | NO |
| Lesson w/ evidence links + lifecycle | `organizational_learning` + `learning_evidence` | NO |
| Memory-grade institutional record | `company_memory` (category=lesson/institutional) | NO |
| Causal/attribution evidence | `company_causal_edges`, `business_performance_links` | NO |
| Support/contradiction cohort | `company_decision_precedents/_contradictions` | NO |
| Expected-vs-actual raw material | `outcome_assessments`, `company_action_outcomes` | NO |
| Provenance walk-back | evidence_json lineages everywhere + 4H.6 assessment basis | NO |

Candidate 4H.7 shapes (for Phase-A contract decision):
- **(S1) Read-only composed surface** (purest 4H.6-style): deterministic
  institutional-learning composition served on demand; zero writes. Fastest,
  safest, but lessons don't *persist* → weaker "institutional memory" claim.
- **(S2) Governed materialization into EXISTING tables**: 4H.7 writes new
  `OrganizationalLearning`/`PatternDetection`(family=decision)/`CompanyMemory`
  (fact_kind=lesson) rows **through the existing engines' own methods**, keyed
  exact-once, human-governed lifecycle. True compounding loop; more contract
  care (dedupe fingerprints, no auto-recommendation, scope inheritance).
- **(S3) Hybrid**: read-only composition surface first; materialization behind
  an explicit governed action later in the slice or a future slice.

## 5. Hazards & constraints discovered (must shape the contract)

1. **VARCHAR(32) truncation (pre-existing, documented in 4H.6 §4)**:
   `company_memory.entity_id` String(32) cannot hold long CompanyDecision
   public ids (`dec:commercial_action:<hex>` = 34 chars). If 4H.7 links
   decisions into memories/patterns as evidence, this becomes BLOCKING on live
   Postgres (SQLite tests stay blind). Sibling columns likely affected.
2. **Two `learning_engine.py` modules** (`app/knowledge/` vs
   `app/intelligence/`) — naming collision; 4H.7 docs/code must disambiguate
   explicitly and must not fork either.
3. **Name-collision minefield**: `lessons` (LMS), `learning_paths/profiles`
   (employee development), `ai_memories` (chat memory). 4H.7 terminology
   ("pattern", "lesson") must reference canonical tables precisely to avoid
   semantic drift.
4. **Seed noise**: `executive_recommendations` 760k demo rows; any cohort math
   must filter to governed 4H.* chain data, not legacy bulk seeds.
5. **Legacy vs canonical decision universes**: `decision_outcomes.decision_id →
   decisions.id` (legacy) while the 4H chain uses `company_decisions`.
   Composition must bridge deliberately, never conflate.
6. **PatternDetection family=decision exists but is event-fed** — reusing it
   for decision-chain patterns requires new pattern_type vocabularies fed by
   4H.6 evidence; upsert natural keys and lifecycle transitions must be
   contract-defined to avoid fighting the existing pipeline's resolution jobs
   (fading/resolved sweeps).

## 6. Candidate law mapping (Phase-A input, NOT ratified)

User-proposed candidates map cleanly onto substrate reality:
- Learning Truth / No Hallucinated Lessons → 4E.7 docstring already embodies it; reuse fingerprint/exact-once machinery.
- Pattern Evidence / Contradiction Honesty → evidence_json + `_contradictions` both-sides-preserved.
- Learning Scope → auth_scope inheritance (CompanyMemory) + scope_type (PatternDetection).
- Temporal Learning → as-of snapshot precedent (`cited_lesson` precedent law §3.3) + append-only tracks.
- No Automatic Recommendation → 4E.7 authorization ladder (auto/approval/human) already codified.
- Provenance Continuity → walk-back path fully traversable today.

## 7. Phase-0 conclusion

Proceed to **Phase A (draft implementation contract)** with these positions:
1. Zero new tables; composition over creation.
2. Decide S1/S2/S3 persistence stance explicitly (recommend **S3 hybrid**:
   read-only institutional-intelligence composition first, then governed
   materialization through existing engine methods as a later bounded step).
3. Define the epistemic ladder + thresholds as contract constants.
4. Treat VARCHAR(32) as a blocking dependency for any decision-linked memory
   evidence (hardening slice or explicit in-contract fix decision required).
5. Preserve 4H.6 frozen code untouched; new composition lives beside it.

— END OF PHASE 0 —
