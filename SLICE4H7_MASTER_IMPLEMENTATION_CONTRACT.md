# 4H.7 — MASTER IMPLEMENTATION CONTRACT
## Institutional Learning & Intelligence

**Slice:** 4H.7
**Purpose:** Institutional Learning & Intelligence
**Dependencies:** 4H.1–4H.6 (FROZEN)
**Status:** CONTRACT PHASE — NO IMPLEMENTATION YET
**Date:** 2026-08-22
**Authority:** This contract is the single source of truth for 4H.7 implementation. No code, schema, migration, route, worker, or test may be modified until this contract is reviewed and accepted.

---

## 1. IDENTITY & SCOPE

### 1.1 What 4H.7 Is
4H.7 is the **governed institutional-learning bridge** connecting the canonical 4H.1–4H.6 decision → action → outcome → measurement → attribution → assessment evidence chain into the existing institutional-learning substrate (`OrganizationalLearning`, `LearningEvidence`, `CompanyMemory`, `PatternDetection`, `CompanyDecisionPrecedent`, `CompanyDecisionContradiction`, `CompanyCausalEdge`, `BusinessPerformanceLink`, `OutcomeAssessment`, `CompanyActionOutcome`, `CompanyDecisionQuality`, `CompanyDecisionTrack`).

### 1.2 What 4H.7 Is Not
| Forbidden | Reason |
|-----------|--------|
| New learning tables (`learning_lessons`, `institutional_lessons`, `decision_learning`, etc.) | Destroys architectural advantage |
| Parallel learning engine (`InstitutionalLearningEngine`, etc.) | Multiple learning architectures already exist |
| Automatic recommendation engine | Learning ≠ Recommendation (separate governed layer) |
| LLM-decided truth | Epistemic honesty: LLM = advisory only |
| New pattern engine | `PatternDetection` is canonical |
| New memory database | `CompanyMemory` is canonical |
| Modification of frozen 4H.6 code/schemas | 4H.6 is FROZEN per `SLICE4H6_VERIFICATION_REPORT.md` |

### 1.3 Central Question Transformation
| Before 4H.7 | After 4H.7 | Future |
|-------------|------------|--------|
| "What happened?" (4H.6) | "What did the company learn?" | "What does the company understand about itself?" |

---

## 2. ARCHITECTURAL INVARIANTS (NON-NEGOTIABLE)

| # | Invariant | Enforcement |
|---|-----------|-------------|
| 1 | **Governance before retrieval** — `resolve_caller_access` gates every lesson retrieval | Code review + governance tests |
| 2 | **Deterministic composition** — Same governed inputs → same output | Replay tests |
| 3 | **Exact-once evolution** — Fingerprint `(org, kind, evidence_fingerprint, scope, context)` converges on replay | Replay tests + unique constraints |
| 4 | **Temporal truth** — `valid_from/valid_to/superseded_by` on every lesson | Schema + tests |
| 5 | **Contradiction preservation** — Both sides remain connected, never discarded | Schema + tests |
| 6 | **Learning ≠ Recommendation** — Lesson describes evidence; recommendation proposes action (separate layer) | Contract boundary |
| 7 | **Zero-vendor AI** — LLM = advisory language generation only | No LLM in qualification logic |
| 8 | **PostgreSQL verification** — SQLite tests insufficient; VARCHAR(32) defect proves this | CI gate |
| 9 | **Zero new tables** — Reuse existing substrate only | Schema diff gate |
| 10 | **4H.6 frozen** — No modifications to 4H.6 contracts/code except explicitly approved dependency fixes | Schema diff gate |

---

## 3. CANONICAL SUBSTRATE MAP (FROZEN OWNERSHIP)

### 3.1 Decision Substrate (4H.2)
| Table | Purpose | 4H.7 Role |
|-------|---------|-----------|
| `company_decisions` | Governed human decision artifact | Source of decision cohort |
| `company_decision_alternatives` | Alternatives with `why_not`/`preferable_if` | Context for pattern comparison |
| `company_decision_evidence` | Evidence with `captured_at` (as-of anchor) | Provenance for lesson |
| `company_decision_precedents` | Precedent citations with `context_signature` | Temporal learning integrity |
| `company_decision_quality` | Per-stage quality snapshots | Epistemic qualification input |
| `company_decision_tracks` | Cohort prediction track-record | Longitudinal validation |
| `company_decision_contradictions` | Conflicting evidence (both sides preserved) | Contradiction analysis |

### 3.2 Execution Substrate (4H.5)
| Table | Purpose | 4H.7 Role |
|-------|---------|-----------|
| `company_actions` | Universal governed action (fingerprint exact-once) | Decision→Action lineage |
| `company_action_events` | Immutable audit trail | Execution provenance |
| `company_action_outcomes` | Verified outcome with evidence | Outcome truth |

### 3.3 Measurement Substrate (4G.6 / 4E.5)
| Table | Purpose | 4H.7 Role |
|-------|---------|-----------|
| `business_metric_observations` | Measured business changes | Metric evidence |
| `business_performance_links` | Attribution relationships | Attribution evidence |
| `outcome_assessments` | Expected vs actual per action/decision | Assessment evidence |

### 3.4 Causal Substrate (4H.1)
| Table | Purpose | 4H.7 Role |
|-------|---------|-----------|
| `company_causal_edges` | Derived bounded relationships (evidence, not proof) | Causal evidence only |

### 3.5 Pattern Substrate (4D.4)
| Table | Purpose | 4H.7 Role |
|-------|---------|-----------|
| `pattern_detections` | Recurrence with lifecycle + evidence lineage | Pattern qualification input |
| `pattern_events` | Exact-once event→pattern links | Pattern provenance |

### 3.6 Institutional-Learning Substrate (4E.7)
| Table | Purpose | 4H.7 Role |
|-------|---------|-----------|
| `organizational_learning` | Qualified institutional lessons (exact-once) | **Canonical lesson store** |
| `learning_evidence` | Immutable evidence supporting lessons | **Lesson provenance** |
| `knowledge_claim_lifecycle` | Append-only claim stage ledger | Claim evolution tracking |

### 3.7 Long-Term Memory Substrate (4D.3 / Phase 19)
| Table | Purpose | 4H.7 Role |
|-------|---------|-----------|
| `company_memory` | Durable organizational memory (`memory_category=lesson`, `fact_kind=lesson`) | **Memory surface for Brain** |
| `memory_events` | Event→memory exact-once links | Memory provenance |
| `memory_outcomes` | Outcome history for confidence evolution | Memory outcome tracking |

### 3.8 Knowledge Substrate (4E.1/4E.3)
| Table | Purpose | 4H.7 Role |
|-------|---------|-----------|
| `knowledge_claims` | Temporal truth (`valid_from/valid_to/superseded_by`) | Claim evolution context |
| `knowledge_topics` | Canonical topic registry | Entity resolution anchor |

---

## 4. EVIDENCE MODEL

### 4.1 Evidence Classes (Exhaustive)
| Class | Source | Description |
|-------|--------|-------------|
| **Decision Evidence** | `company_decision_evidence` | What the company knew/believed at decision time (`captured_at`) |
| **Execution Evidence** | `company_action_events` | What actually happened during execution |
| **Outcome Evidence** | `company_action_outcomes` + `outcome_assessments` | What happened after + expected vs actual |
| **Metric Evidence** | `business_metric_observations` | Measured business changes |
| **Attribution Evidence** | `business_performance_links` | Relationships connecting performance to action/decision |
| **Pattern Evidence** | `pattern_detections` + `pattern_events` | Repeated comparable cases |
| **Contradiction Evidence** | `company_decision_contradictions` + contradicting outcomes/metrics | Cases disagreeing with proposed lesson |

### 4.2 Evidence Qualification Rules
| Rule | Description |
|------|-------------|
| **E1** | Every evidence item must reference a real canonical row via primary key |
| **E2** | Evidence carries its own timestamp (`captured_at`, `occurred_at`, `observed_at`) — never write-time |
| **E3** | Evidence is never fabricated; hidden evidence is never retrieved (governance before retrieval) |
| **E4** | Contradictory evidence remains permanently connected to the lesson |
| **E5** | Evidence scope inherits from source (`auth_scope`, `scope_type`, `scope_id`) |

---

## 5. COHORT DEFINITION

### 5.1 Cohort Formation Rules
| Rule | Description |
|------|-------------|
| **C1** | Cohort = decisions sharing contract-defined dimensions, retrieved via indexed queries only |
| **C2** | Maximum cohort size: **50 decisions** (bounded by `MAX_PRECEDENTS = 10` × comparison factor) |
| **C3** | Temporal boundary: decisions within **90-day sliding window** from anchor decision (configurable via contract constant `COHORT_WINDOW_DAYS = 90`) |
| **C4** | Governance filter: only decisions accessible to caller via `resolve_accessible_ids` |
| **C5** | Minimum cohort for pattern detection: **3 comparable decisions** (`MIN_COHORT_SIZE = 3`) |

### 5.2 Cohort Signature Dimensions (Contract-Defined)
| Dimension | Values | Matching |
|-----------|--------|----------|
| `decision_kind` | `reallocate_capacity`, `delay_project`, `hire`, `change_priority`, `resolve_conflict`, `improve_coordination`, `customer_mitigation`, `commercial_action`, `other` | Exact |
| `scope_type` | `org`, `business_unit`, `department`, `team`, `person` | Exact or ancestor |
| `business_context_hash` | Hash of relevant entities (projects, customers, capabilities) | Fuzzy (Jaccard ≥ 0.7) |
| `action_characteristics` | Action kinds, assignee roles, duration bands | Set overlap ≥ 0.6 |
| `outcome_characteristics` | Outcome kinds, metric directions | Set overlap ≥ 0.6 |

### 5.3 Cohort Signature
```
cohort_signature = H(
    organization_id,
    decision_kind,
    scope_type,
    scope_id,
    business_context_hash,
    temporal_window_start,
    temporal_window_end
)
```
Same signature → same cohort → deterministic pattern analysis.

---

## 6. EPISTEMIC LADDER (FROZEN VOCABULARY)

### 6.1 Levels (Mapping to `OrganizationalLearning.lifecycle`)
| Level | OrganizationalLearning.lifecycle | Meaning | Evidence Requirement |
|-------|----------------------------------|---------|---------------------|
| **0** | — | Observation (raw event) | Single canonical row |
| **1** | — | Pattern Candidate | ≥ `MIN_COHORT_SIZE` decisions with recurring outcome direction |
| **2** | `discovered` → `candidate` | Lesson Candidate | Formulated evidence-backed proposition + cohort signature |
| **3** | `supported` | Supported Lesson | ≥ `MIN_SUPPORTING_EVIDENCE = 5` independent evidence items across decisions |
| **4** | `authoritative` | Authoritative Lesson | Supported + crosses contract thresholds (see §7) + acceptable contradiction profile |
| **5** | `confirmed` | Confirmed Lesson | Authoritative + new subsequent cohort confirms same relationship |
| **6** | `superseded` | Superseded Lesson | New lesson invalidates applicability; old lesson retains `superseded_by` link |
| **7** | `archived` | Archived Lesson | No longer operationally active; history preserved |

### 6.2 Epistemic Status Vocabulary (Brain Surface)
| Status | Display | Meaning |
|--------|---------|---------|
| `OBSERVED` | "Observed" | Single evidence item |
| `RECURRING` | "Recurring" | Pattern detected |
| `SUPPORTED` | "Supported" | Lesson candidate with qualifying evidence |
| `SUPPORTED_WITH_CONTRADICTIONS` | "Supported with Contradictions" | Supported but contradicting evidence exists |
| `AUTHORITATIVE` | "Authoritative" | Crossed institutional thresholds |
| `CONFIRMED` | "Confirmed" | Longitudinal confirmation |
| `SUPERSEDED` | "Superseded" | Invalidated by newer evidence |
| `ARCHIVED` | "Archived" | Historical only |
| `UNKNOWN` | "Unknown" | Insufficient evidence |

---

## 7. LESSON QUALIFICATION THRESHOLDS (CONTRACT CONSTANTS)

| Constant | Value | Description |
|----------|-------|-------------|
| `MIN_COHORT_SIZE` | 3 | Minimum comparable decisions for pattern |
| `MIN_PATTERN_OCCURRENCES` | 3 | Minimum pattern occurrences (from `PatternDetection.count`) |
| `MIN_SUPPORTING_EVIDENCE` | 5 | Independent evidence items for Supported |
| `MAX_CONTRADICTION_RATIO` | 0.35 | Max contradictions / (supporting + contradicting) for Authoritative |
| `MIN_OUTCOME_QUALITY` | 0.6 | Minimum `OutcomeAssessment.assessment = "met"` ratio |
| `MIN_TEMPORAL_SPREAD_DAYS` | 30 | Minimum time between first and last cohort decision |
| `MIN_EVIDENCE_COVERAGE` | 0.6 | Fraction of cohort decisions with complete evidence chain |
| `COHORT_WINDOW_DAYS` | 90 | Sliding window for cohort formation |
| `MAX_COHORT_SIZE` | 50 | Hard cap on cohort decisions |
| `PATTERN_CONFIDENCE_THRESHOLD` | 0.5 | Minimum pattern confidence for lesson consideration |

### 7.1 Transition Rules (Deterministic)
| From → To | Condition |
|-----------|-----------|
| Candidate → Supported | `supporting_evidence_count ≥ MIN_SUPPORTING_EVIDENCE` AND `contradiction_ratio ≤ MAX_CONTRADICTION_RATIO` AND `outcome_quality ≥ MIN_OUTCOME_QUALITY` |
| Supported → Authoritative | Supported AND `temporal_spread ≥ MIN_TEMPORAL_SPREAD_DAYS` AND `evidence_coverage ≥ MIN_EVIDENCE_COVERAGE` |
| Authoritative → Confirmed | Authoritative AND new independent cohort (non-overlapping temporal window) confirms same relationship |
| Any → Superseded | New lesson with overlapping scope + stronger evidence + explicit supersession decision |
| Any → Archived | No longer operationally relevant per governance review |

---

## 8. PATTERN QUALIFICATION

### 8.1 Pattern Definition
A **pattern** exists when:
- ≥ `MIN_PATTERN_OCCURRENCES` decisions in a cohort share the same outcome direction under comparable conditions
- Pattern carries `evidence_json` + `supporting_event_ids` + `supporting_memory_ids` + `supporting_relationships`
- `PatternDetection.confidence` ≥ `PATTERN_CONFIDENCE_THRESHOLD`

### 8.2 Pattern ≠ Lesson
| Pattern | Lesson |
|---------|--------|
| "Condition X repeatedly appears with outcome Y" | "Available evidence supports that X is associated with Y under defined scope/conditions" |
| Descriptive recurrence | Epistemically qualified proposition |
| No contradiction handling required | Must preserve contradicting evidence |
| `PatternDetection` lifecycle | `OrganizationalLearning` lifecycle |

### 8.3 Pattern-to-Lesson Flow
```
Pattern Candidate (from PatternDetection)
    ↓
Cohort Validation (governed, bounded)
    ↓
Evidence Aggregation (decisions + actions + outcomes + metrics)
    ↓
Contradiction Analysis (supporting vs contradicting)
    ↓
Epistemic Qualification (thresholds from §7)
    ↓
Lesson Candidate → Supported → Authoritative → Confirmed
```

---

## 9. CONTRADICTION RULES

### 9.1 Contradiction Preservation (Absolute)
| Rule | Description |
|------|-------------|
| **CR1** | Contradictory evidence is **never discarded**, never hidden, never silently resolved |
| **CR2** | Both supporting and contradicting evidence remain permanently linked to lesson |
| **CR3** | Contradiction reduces epistemic status; does not delete lesson |
| **CR4** | Contradiction ratio = `contradicting_count / (supporting_count + contradicting_count)` |
| **CR5** | If `contradiction_ratio > MAX_CONTRADICTION_RATIO` → lesson cannot reach `authoritative` |

### 9.2 Contradiction Status Vocabulary
| Status | Condition |
|--------|-----------|
| `NONE` | No contradicting evidence |
| `MINOR` | `contradiction_ratio ≤ 0.15` |
| `SIGNIFICANT` | `0.15 < contradiction_ratio ≤ MAX_CONTRADICTION_RATIO` |
| `BLOCKING` | `contradiction_ratio > MAX_CONTRADICTION_RATIO` → blocks Authoritative |

### 9.3 Contradiction Surface (Brain)
Every lesson response must include:
```json
"contradictions": [
  {
    "decision_id": "...",
    "outcome": "...",
    "evidence_summary": "...",
    "temporal_relationship": "before|after|concurrent"
  }
]
```

---

## 10. TEMPORAL RULES

### 10.1 Temporal Validity (Every Lesson)
| Field | Source | Purpose |
|-------|--------|---------|
| `valid_from` | `OrganizationalLearning.observed_at` | When lesson became supported |
| `valid_to` | `superseded_by` link or NULL | When lesson ceased to be current |
| `superseded_by` | `OrganizationalLearning` FK | Link to superseding lesson |
| `observed_at` | `OrganizationalLearning.observed_at` | When evidence was observed |
| `as_of_context` | `CompanyDecision.as_of_context_json` | Decision-time knowledge snapshot |

### 10.2 As-Of Semantics (Absolute)
| Rule | Description |
|------|-------------|
| **TR1** | A decision at time T can only cite lessons with `valid_from ≤ T` |
| **TR2** | `CompanyDecisionPrecedent.cited_lesson` is a **snapshot** of lesson at precedent's outcome time |
| **TR3** | Future evidence **never** retroactively injects into past decisions |
| **TR4** | `CompanyStateHistory` + `CompanyHealthHistory` provide company-state-at-T for decision context |

### 10.3 Supersession Protocol
```
Old Lesson (L1)
    ↓
New Evidence → New Lesson (L2) with overlapping scope
    ↓
Explicit Supersession Decision (governed)
    ↓
L1.superseded_by = L2
L1.valid_to = L2.valid_from
L1.lifecycle = "superseded"
L2.lifecycle = "authoritative" (or higher)
```
Old lesson remains queryable with `lifecycle = "superseded"`.

---

## 11. SCOPE RULES

### 11.1 Scope Inheritance
| Rule | Description |
|------|-------------|
| **SC1** | Lesson scope = intersection of all evidence scopes (most restrictive) |
| **SC2** | Evidence scopes: `auth_scope` ∈ {`org`, `project`, `personal`} + `auth_project_id` + `auth_scope_id` |
| **SC3** | Lesson `scope_type`/`scope_id` derived from evidence; never broadened |
| **SC4** | Project-scoped lesson ≠ Organization-scoped lesson |
| **SC5** | Governance resolution: `resolve_caller_access` filters lessons before composition |

### 11.2 Scope Promotion (Contract-Gated)
| From | To | Condition |
|------|----|-----------|
| `project` | `org` | All projects in org show same pattern + governance approval |
| `team` | `department` | All teams in department show same pattern + governance approval |
| `personal` | `project` | Multiple individuals in project show same pattern |

**No automatic promotion.** Requires explicit governance decision.

---

## 12. PROVENANCE CONTRACT (ABSOLUTE)

### 12.1 Required Provenance Chain
Every lesson must be traceable:
```
Lesson
  │
  ├── Pattern
  │     ├── PatternDetection
  │     └── PatternEvent → EventRow
  │
  ├── LearningEvidence (immutable)
  │     ├── decision → CompanyDecision
  │     ├── action → CompanyAction
  │     ├── outcome → CompanyActionOutcome
  │     ├── metric → BusinessMetricObservation
  │     ├── attribution → BusinessPerformanceLink
  │     ├── assessment → OutcomeAssessment
  │     ├── pattern → PatternDetection
  │     └── contradiction → CompanyDecisionContradiction
  │
  └── Assessment
        ├── MetricObservation
        └── ActionOutcome
              └── Action
                    └── Decision
                          ├── Alternative
                          ├── Evidence
                          ├── Precedent
                          ├── Quality
                          ├── Track
                          └── Contradiction
```

### 12.2 Provenance Test (Definition of Done)
> "Show me exactly why VCOS believes this company learned this."
> The system must walk the complete chain above. If any link breaks, the lesson is **not institutionally trustworthy**.

---

## 13. S3 HYBRID IMPLEMENTATION STRATEGY

### 13.1 Stage A — Read-Only Composition (No Persistence)
| Component | Responsibility |
|-----------|----------------|
| `4H7EvidenceComposer` | Read canonical tables → deterministic evidence bundles |
| `4H7CohortBuilder` | Form governed cohorts from `company_decisions` |
| `4H7PatternQualifier` | Connect cohorts to `PatternDetection` |
| `4H7AttributionAnalyzer` | Aggregate `BusinessPerformanceLink` + `OutcomeAssessment` |
| `4H7ContradictionAnalyzer` | Join supporting + contradicting evidence |
| `4H7EpistemicQualifier` | Apply thresholds from §7 → epistemic status |
| `4H7TemporalQualifier` | Apply temporal rules from §10 |

**Output:** `QualifiedLearningView` (in-memory, deterministic, no DB writes)

### 13.2 Stage B — Governed Materialization (After Stage A Verified)
| Step | Engine | Tables |
|------|--------|--------|
| 1 | Existing `OrganizationalLearning` engine | `organizational_learning` |
| 2 | Existing `LearningEvidence` engine | `learning_evidence` |
| 3 | Existing `CompanyMemory` engine | `company_memory` (with `memory_category=lesson`, `fact_kind=lesson`) |

**No direct SQL INSERT.** Use existing engine methods to preserve exact-once semantics.

---

## 14. EXACT-ONCE MATERIALIZATION

### 14.1 Fingerprint Specification
```
lesson_fingerprint = SHA256(
    organization_id || '|' ||
    lesson_kind || '|' ||
    cohort_signature || '|' ||
    evidence_signature || '|' ||
    scope_type || '|' ||
    scope_id || '|' ||
    temporal_anchor
)
```
Where:
- `lesson_kind` ∈ {`outcome_learning`, `decision_learning`, `recommendation_learning`, `contradiction_resolution`, `knowledge_confirmation`}
- `cohort_signature` from §5.3
- `evidence_signature` = hash of sorted evidence primary keys
- `temporal_anchor` = `valid_from` ISO timestamp

### 14.2 Idempotency Guarantee
| Run | Same Evidence | Result |
|-----|---------------|--------|
| 1 | Yes | Creates `OrganizationalLearning` row with `lesson_fingerprint` |
| 2 | Yes | Finds existing row by `lesson_fingerprint` → updates in-place (no duplicate) |
| 3 | Yes | Same as run 2 |
| N | Yes | Same lesson row (replay convergence) |

---

## 15. COMPANY BRAIN INTEGRATION

### 15.1 New Brain Intents (Contract-Defined)
| Intent | Trigger Keywords | Response Includes |
|--------|------------------|-------------------|
| `learning` | "what did we learn", "lessons from", "historical lessons" | Institutional lessons + provenance |
| `precedent` | "precedent", "similar decision", "have we decided" | `CompanyDecisionPrecedent` + cited lessons |
| `contradiction` | "contradiction", "conflicting", "disagrees" | Contradiction surface |
| `supersession` | "superseded", "obsolete", "no longer valid" | Supersession history |

### 15.2 Brain Learning Response Schema
```json
{
  "lesson": {
    "id": "...",
    "statement": "...",
    "epistemic_status": "AUTHORITATIVE",
    "scope": {"type": "org", "id": null},
    "temporal_validity": {"valid_from": "...", "valid_to": null, "superseded_by": null},
    "evidence_qualification": {"supporting_count": 7, "contradicting_count": 2, "outcome_quality": 0.71},
    "provenance": {
      "patterns": ["pattern_id_1", "pattern_id_2"],
      "decisions": ["decision_id_1", "..."],
      "outcomes": ["outcome_id_1", "..."],
      "metrics": ["metric_id_1", "..."],
      "attributions": ["link_id_1", "..."],
      "assessments": ["assessment_id_1", "..."]
    },
    "contradictions": [
      {"decision_id": "...", "outcome": "...", "evidence_summary": "...", "temporal_relationship": "after"}
    ],
    "precedents": [
      {"decision_id": "...", "cited_lesson_snapshot": "...", "relevance_score": 0.82}
    ],
    "supersession_history": [
      {"from_lesson": "...", "to_lesson": "...", "reason": "...", "at": "..."}
    ]
  },
  "governance": {
    "org_wide": true,
    "visible_scope_count": 5,
    "visible_project_count": 12
  }
}
```

### 15.3 Brain Must Distinguish
| Level | Brain Language |
|-------|----------------|
| Observation | "Decision D1 showed outcome O1" |
| Pattern | "3 comparable decisions showed similar outcome direction" |
| Lesson | "Evidence supports that X is associated with Y under these conditions" |
| Recommendation | **NOT PRODUCED BY 4H.7** (separate governed layer) |

---

## 16. API CONTRACT (CONCEPTUAL SURFACES)

| Surface | Method | Purpose |
|---------|--------|---------|
| `/brain/learning` | GET | List lessons (governed, paginated) |
| `/brain/learning/{id}` | GET | Single lesson with full provenance |
| `/brain/learning/{id}/evidence` | GET | Evidence chain walk |
| `/brain/learning/{id}/contradictions` | GET | Contradiction surface |
| `/brain/learning/{id}/history` | GET | Lifecycle + supersession history |
| `/brain/learning/{id}/related` | GET | Related lessons/patterns/precedents |
| `/brain/learning/cohort` | POST | Form cohort for decision (governed) |
| `/brain/learning/qualify` | POST | Stage A qualification (read-only) |

**Exact endpoints frozen during implementation gate.**

---

## 17. TESTING ARCHITECTURE

### 17.1 Layer 1 — Deterministic Unit Tests
| Test | Assertion |
|------|-----------|
| Same evidence bundle | Same cohort, pattern, qualification, fingerprint |
| Empty cohort | No pattern, no lesson |
| Single decision | No pattern (below `MIN_COHORT_SIZE`) |

### 17.2 Layer 2 — Replay Tests
| Test | Assertion |
|------|-----------|
| Run worker twice | No duplicate `OrganizationalLearning`, `LearningEvidence`, `CompanyMemory` |
| Restart between stages | Same fingerprint, same lesson |
| Concurrent workers | CAS converges, no duplicates |

### 17.3 Layer 3 — Contradiction Tests
| Test | Assertion |
|------|-----------|
| 8 supporting + 3 contradicting | Lesson = `SUPPORTED_WITH_CONTRADICTIONS`, not `AUTHORITATIVE` |
| Contradicting evidence | Remains linked, visible in Brain response |
| Contradiction resolution | Human decision updates status; evidence unchanged |

### 17.4 Layer 4 — Temporal Tests
| Test | Assertion |
|------|-----------|
| Decision at T1, Lesson at T2 | Decision cannot cite lesson (as-of semantics) |
| Lesson at T1, Superseded at T2 | T1 decision sees old lesson; T3 decision sees new lesson |
| `CompanyDecisionPrecedent.cited_lesson` | Snapshot at precedent outcome time |

### 17.5 Layer 5 — Governance Tests
| Test | Assertion |
|------|-----------|
| Caller scope A | Cannot see scope B lessons |
| Project-scoped caller | Sees only project lessons + org lessons |
| Cross-tenant | Zero leakage |

### 17.6 Layer 6 — PostgreSQL Tests (MANDATORY)
| Test | Assertion |
|------|-----------|
| `VARCHAR(32)` decision IDs | No truncation on `dec:commercial_action:<hex12>` |
| Unique constraints | Exact-once on all fingerprint keys |
| Foreign keys | Cascade/delete behavior correct |
| Migration | Clean apply on clean + existing schema |

### 17.7 Layer 7 — Longitudinal Integration Test
```
1. Create org + users + governance
2. Create 7 comparable decisions (4H.2)
3. Approve → Execute actions (4H.5)
4. Record outcomes + metrics (4G.6)
5. Record attributions (4E.5)
6. Assess decision quality (4H.2)
7. Detect patterns (4D.4)
8. Qualify lesson (4H.7)
9. Materialize → OrganizationalLearning + CompanyMemory
10. Query Brain → lesson appears with provenance
11. Walk lesson → decision → action → outcome → metric
12. Introduce contradictory outcome
13. Verify lesson status changes, contradiction preserved
14. Supersede lesson
15. Verify old lesson remains, new lesson linked
16. New decision cites lesson via Precedent
17. Replay workers → no duplicates
18. Restart → same state
```

---

## 18. DEPENDENCIES & RISKS (PHASE B GATE)

| Priority | Risk | Resolution Required Before Stage B |
|----------|------|-----------------------------------|
| **P0** | `CompanyDecision.decision_id` `dec:commercial_action:<hex12>` (34 chars) > `VARCHAR(32)` | Sibling-column audit + widening to `VARCHAR(64)` on all decision-ID-bearing columns |
| **P0** | `event_bus.process_pending(limit=50)` drains all tenants | Add `organization_id` parameter; tenant-scoped drain |
| **P1** | Legacy `Decision` (knowledge entity) vs `CompanyDecision` (governed artifact) | Explicit boundary documentation; no silent conflation |
| **P1** | `app/intelligence/learning_engine.py` vs `app/knowledge/learning_engine.py` | Ownership map; 4H.7 uses only canonical substrate engines |
| **P2** | SQLite/PostgreSQL divergence | PostgreSQL CI gate for all 4H.7 tests |

---

## 19. FORBIDDEN BEHAVIORS (EXPLICIT)

| Behavior | Contract Reference |
|----------|-------------------|
| Create new learning/memory/pattern tables | §2 |
| Modify frozen 4H.6 code/schemas | §1.2, §18 |
| LLM decides truth/qualification | §17 |
| Auto-generate recommendations from lessons | §16 |
| Discard contradictory evidence | §9 |
| Retroactively inject future knowledge | §10 |
| Broaden lesson scope beyond evidence | §11 |
| Filter after retrieval | §12, §26 |
| Direct SQL INSERT into learning tables | §13.2 |
| Merge learning engines | §18, §25 |
| Skip PostgreSQL verification | §17.6, §35 |

---

## 20. DEFINITION OF DONE (ACCEPTANCE CRITERIA)

| Category | Criteria |
|----------|----------|
| **Architecture** | Zero new institutional-learning tables; existing engines reused; 4H.6 frozen; no parallel learning engine |
| **Evidence** | Every lesson has evidence; every evidence item has provenance; outcomes distinguishable from inference |
| **Epistemics** | Qualification deterministic; thresholds contract-defined; contradiction preserved; temporal validity works |
| **Governance** | Access resolved before retrieval; scope cannot leak; tenant isolation holds |
| **Persistence** | Exact-once materialization; replay-safe; deterministic fingerprints |
| **Brain** | Lessons discoverable; evidence traversable; contradictions surfacable; historical context honest |
| **Production** | PostgreSQL passes; SQLite passes; migration/schema gates pass; full regression passes; longitudinal test passes |

---

## 21. IMPLEMENTATION GATE SEQUENCE

| Phase | Gate | Artifact | Review Required |
|-------|------|----------|-----------------|
| **A** | Contract Freeze | This document (`SLICE4H7_MASTER_IMPLEMENTATION_CONTRACT.md`) | ✅ |
| **B** | Dependency Hardening | P0/P1 fixes applied + verified | ✅ |
| **C** | Read-Only Composer | `4H7EvidenceComposer` + unit tests | ✅ |
| **D** | Cohort/Pattern Qualification | `4H7CohortBuilder` + `4H7PatternQualifier` + tests | ✅ |
| **E** | Lesson Qualification | `4H7EpistemicQualifier` + thresholds + tests | ✅ |
| **F** | Contradiction/Temporal | `4H7ContradictionAnalyzer` + `4H7TemporalQualifier` + tests | ✅ |
| **G** | Governed Materialization | Engine integration + exact-once + tests | ✅ |
| **H** | Brain Integration | New intents + response schema + governance | ✅ |
| **I** | Longitudinal/Replay/PostgreSQL | Full test suite + live longitudinal test | ✅ |
| **J** | Final Acceptance | All criteria in §20 met | ✅ |

**No phase may begin until previous phase gate is explicitly accepted.**

---

## 22. SIGNATURES

| Role | Name | Date | Status |
|------|------|------|--------|
| Architecture Review | | | PENDING |
| Product Review | | | PENDING |
| Engineering Review | | | PENDING |

---

**END OF CONTRACT — NO IMPLEMENTATION UNTIL ALL REVIEWS COMPLETE**