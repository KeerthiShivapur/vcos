# 4H.7 Phase J — Final Freeze Documentation

## Executive Summary

**4H.7 Organizational Learning Pipeline: FROZEN AND RATIFIED**

This document establishes the canonical, frozen implementation of the 4H.7 Organizational Learning Pipeline. All contracts, schemas, APIs, and invariants documented herein are now considered stable and must not be modified without a formal contract amendment.

---

## 1. What Was Built (4H.7 Canonical Architecture)

### 1.1 Phase Overview

| Phase | Component | Status | Purpose |
|-------|-----------|--------|---------|
| A | Master Contract | FROZEN | Authoritative implementation contract |
| B | Dependency Hardening | FROZEN | VARCHAR(64) widening, tenant isolation fixes |
| C | Evidence Composer | FROZEN | Governance-first deterministic evidence bundles |
| D | Pattern Qualification | FROZEN | Cohort-based pattern qualification with contradiction handling |
| E | Lesson Qualification | FROZEN | Epistemic ladder from patterns to qualified lessons |
| F | Governed Materialization | FROZEN | Exact-once lesson persistence with scope inheritance |
| G | Company Brain Integration | FROZEN | Institutional learning routed through Company Brain |
| H | API/Surface Integration | FROZEN | Learning exposed through Projects, Decisions, Dashboard, Intelligence, Knowledge |
| I | Full Verification | COMPLETE | 128 adversarial tests passing |
| J | Final Freeze | **THIS DOCUMENT** | Contract ratification |

### 1.2 Core Learning Pipeline (Canonical)

```
Company Activity/History
         │
         ▼
    Canonical History (Events)
         │
         ▼
       Evidence (Phase C)
         │
         ▼
     Patterns (Phase D)
         │
         ▼
    Qualified Lessons (Phase E)
         │
         ▼
 Governed Materialization (Phase F)
         │
         ▼
   Company Brain (Phase G)
         │
    ┌────┼────┐
    ▼    ▼    ▼
Projects Decisions Knowledge
    │    │    │
    └────┼────┘
         ▼
Dashboard / Intelligence
```

---

## 2. Frozen Contracts

### 2.1 Database Schema (Canonical)

#### 2.1.1 Core Tables (16 tables frozen)

| Table | Purpose | Key Constraints |
|-------|---------|-----------------|
| `organizational_learning` | Qualified lessons | PK(id), UQ(org_id, kind, fingerprint), NOT NULL: org_id, kind, fingerprint, title, status, lifecycle, confidence |
| `learning_evidence` | Immutable evidence links | PK(id), UQ(learning_id, source_type, source_id), FK(learning_id) |
| `pattern_detections` | Qualified patterns | PK(id), UQ(org_id, pattern_type, key), NOT NULL: org_id, pattern_type, key, family, status, count, confidence |
| `company_decisions` | Governed decisions | PK(id), UQ(org_id, decision_id), UQ(org_id, source_event_id) |
| `company_decision_contradictions` | Contradictions | PK(id), UQ(org_id, decision_id, contradiction_key), FK(decision_id) |
| `company_decision_precedents` | Precedent citations | PK(id), UQ(org_id, decision_id, source_event_id) |
| `company_decision_quality` | Quality snapshots | PK(id), UQ(org_id, decision_id, quality_key) |
| `company_decision_evidence` | Decision evidence | PK(id), UQ(org_id, decision_id, evidence_key) |
| `company_decision_alternatives` | Decision alternatives | PK(id), UQ(org_id, decision_id, alternative_key) |
| `company_decision_tracks` | Prediction track records | PK(id), UQ(org_id, cohort_key, source_event_id) |
| `company_causal_edges` | Derived causality | PK(id), UQ(org_id, source_event_id, kind, source_type, source_id, target_type, target_id) |
| `decision_outcomes` | Decision outcomes | PK(id), UQ(org_id, decision_id) |
| `company_memory` | Organizational memory | PK(id), indexes on org/type/importance/category/dedupe/auth |
| `company_changes` | What-changed signals | PK(id), UQ(org_id, kind, fingerprint) |
| `company_health_history` | Health ledger | PK(id), UQ(org_id, source_event_id, scope_type, scope_id) |
| `company_state_history` | State ledger | PK(id), UQ(org_id, scope_type, scope_id, source_event_id) |

#### 2.1.2 Column Type Freeze

- **decision_id**: VARCHAR(64) — widened from VARCHAR(32) in Phase B
- **fingerprint**: VARCHAR(160) — exact-once keys
- **evidence_json**: JSON — structured evidence with lineage
- **claims_updated_json**: JSON — canonical knowledge claims affected
- **lifecycle**: VARCHAR(24) — discovered→candidate→supported→authoritative→confirmed→superseded→archived
- **supersedes_id**: Not in model (fingerprint-based supersession)

### 2.2 API Contracts (Frozen Endpoints)

#### 2.2.1 Company Brain (`/api/v1/brain`)

| Endpoint | Method | Purpose | Contract |
|----------|--------|---------|----------|
| `/brain/answer` | POST | Governed Q&A | Returns claims + patterns + insights + memories + knowledge + **lessons** |
| `/brain/overview` | GET | Living overview | attention + recent_intelligence (insights/patterns/memories) + **learning_summary** |
| `/brain/what-changed` | GET | Temporal digest | categories (tasks/docs/meetings/memories/events) |
| `/brain/evidence/{source_type}/{source_id}` | GET | Evidence drawer | linked patterns/insights/memories/knowledge/graph |
| `/brain/related/{source_type}/{source_id}` | GET | Related view | graph neighbors + cross-source intelligence |
| `/brain/timeline/unified` | GET | Unified timeline | project_timeline + memories + patterns + insights + **lessons** |

#### 2.2.2 Learning Endpoints (`/api/v1/brain/learning`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/learning/lessons` | GET | List lessons (governance-scoped) |
| `/learning/lessons/{lesson_id}` | GET | Lesson detail + evidence + contradictions + pattern + temporal |
| `/learning/patterns` | GET | List patterns (governance-scoped) |
| `/learning/patterns/{pattern_id}` | GET | Pattern detail + evidence + linked lessons + memories |
| `/learning/contradictions` | GET | List contradictions (both sides) |
| `/learning/provenance/{lesson_id}` | GET | Full provenance chain |
| `/learning/temporal` | GET | Historical state at `as_of` timestamp |

#### 2.2.3 Surface Integration Endpoints

| Surface | Endpoint | Purpose |
|---------|----------|---------|
| Projects | `/projects/{id}/learning` | Project-relevant lessons/patterns/contradictions |
| Projects | `/projects/{id}/learning/timeline` | Temporal learning evolution |
| Decisions | `/decisions/{id}/learning` | Decision-relevant lessons/precedents/contradictions |
| Dashboard | `/dashboard/summary` | `learning_summary` with top lessons/patterns |
| Intelligence | `/intelligence/overview` | `institutional_learning` with top lessons/patterns |
| Knowledge | `/knowledge/search/with-learning` | Search + relevant lessons/patterns |

### 2.3 Company Brain Answer Contract (Additive)

The `/brain/answer` response now includes these **additional frozen keys**:

```json
{
  "question": "string",
  "claims": [...],
  "scope_ids": [...],
  "answered_at": "ISO8601",
  "summary": "string",
  "confidence": "float",
  "related_entities": [...],
  "patterns": [...],
  "memories": [...],
  "insights": [...],
  "knowledge": [...],
  "lessons": [
    {
      "id": "string",
      "kind": "outcome_learning|decision_learning|...",
      "fingerprint": "string",
      "title": "string",
      "lesson": "string",
      "status": "active|applied|archived",
      "lifecycle": "discovered|candidate|supported|authoritative|confirmed|superseded|archived",
      "confidence": "float",
      "topic_name": "string|null",
      "evidence_count": "int",
      "contradiction_count": "int",
      "observed_at": "ISO8601|null",
      "source_type": "string",
      "source_id": "string",
      "url": "string"
    }
  ],
  "sources_consulted": ["context","patterns","insights","memory","knowledge","learning"],
  "scope": {"org_wide": "bool"},
  "generated_at": "ISO8601",
  "metrics": {...},
  "timeline": [...],
  "recommended_next_questions": [...],
  "reasoning_chain": [
    {"step": "int", "label": "Institutional learning", "claim": "string", "evidence": [...], "confidence": "float"}
  ]
}
```

---

## 3. Frozen Invariants (Must Never Break)

### 3.1 Governance-First Retrieval
- **NEVER** retrieve all lessons then filter by permission
- **ALWAYS** resolve caller access → scope → accessible IDs → governed retrieval
- Project-scoped lessons visible only to callers with project access
- Personal-scoped visible only to owner
- Org-scoped visible to org-wide callers

### 3.2 Exact-Once Semantics
- Same `(organization_id, kind, fingerprint)` → exactly one `OrganizationalLearning` row
- Same `(organization_id, pattern_type, key)` → exactly one `PatternDetection` row
- Same `(learning_id, source_type, source_id)` → exactly one `LearningEvidence` row
- Replay/retry of any event → zero duplicates
- SHA-256 fingerprint mechanism protects all exact-once keys

### 3.3 Temporal Truth
- History is never rewritten
- `supersedes_id` chain preserves supersession lineage
- Temporal query `as_of` returns historical state
- Current query returns latest by fingerprint
- Current state never overwrites history

### 3.4 Contradiction Preservation
- `CompanyDecisionContradiction` stores BOTH sides
- `side_a_json` (pending decision) + `side_b_json` (recorded lesson/precedent)
- Status: `open` → `acknowledged` → `resolved` (human acts only)
- Contradiction count exposed in lesson summaries
- Nothing silently discarded

### 3.5 Provenance Chain Integrity
- Lesson → Pattern → Evidence → Assessment → Outcome → Action → Decision
- Every lesson must trace back to canonical decisions/outcomes
- Provenance endpoint returns full chain
- No lesson without evidence; no evidence without source event

### 3.5 Tenant Isolation
- Organization A learning **never** visible to Organization B
- Verified across ALL surfaces: Brain, Dashboard, Intelligence, Knowledge, Projects, Decisions
- Tested adversarially in Phase I

### 3.6 Scope Inheritance
- Lessons inherit scope from source pattern
- Project-scoped lesson ≠ Company-wide truth
- Promotion requires explicit governance action
- `auth_scope` / `auth_project_id` on `CompanyMemory` carries scope

### 3.7 Learning ≠ Recommendation
- Lessons carry epistemic status (`lifecycle`, `confidence`, `contradiction_count`)
- **Never** auto-convert lesson → action
- Company Brain answers are evidence-backed, not predictive
- Recommended next questions are investigation-shaped, not autonomous

---

## 4. Frozen Migration Requirements

### 4.1 Required Migrations (PostgreSQL)

```sql
-- 1. Widen decision_id columns to VARCHAR(64)
ALTER TABLE company_decisions ALTER COLUMN decision_id TYPE VARCHAR(64);
ALTER TABLE company_decision_contradictions ALTER COLUMN decision_id TYPE VARCHAR(64);
ALTER TABLE company_decision_precedents ALTER COLUMN decision_id TYPE VARCHAR(64);
ALTER TABLE company_decision_quality ALTER COLUMN decision_id TYPE VARCHAR(64);
ALTER TABLE company_decision_evidence ALTER COLUMN decision_id TYPE VARCHAR(64);
ALTER TABLE company_decision_alternatives ALTER COLUMN decision_id TYPE VARCHAR(64);
ALTER TABLE company_decision_tracks ALTER COLUMN source_event_id TYPE VARCHAR(64);
ALTER TABLE company_causal_edges ALTER COLUMN source_event_id TYPE VARCHAR(64);
ALTER TABLE decision_outcomes ALTER COLUMN decision_id TYPE VARCHAR(64);

-- 2. Create organizational_learning table
CREATE TABLE organizational_learning (
    id VARCHAR(32) PRIMARY KEY,
    organization_id VARCHAR(32) NOT NULL REFERENCES organizations(id),
    kind VARCHAR(40) NOT NULL,
    fingerprint VARCHAR(160) NOT NULL,
    title VARCHAR(240) NOT NULL,
    lesson TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    lifecycle VARCHAR(24) NOT NULL DEFAULT 'discovered',
    confidence FLOAT NOT NULL DEFAULT 0.6,
    source_type VARCHAR(32),
    source_id VARCHAR(32),
    topic_id VARCHAR(32),
    topic_name VARCHAR(120),
    evidence_json TEXT,
    claims_updated_json TEXT,
    observation TEXT,
    expectation TEXT,
    recorded_by VARCHAR(32),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, kind, fingerprint)
);

-- 3. Create learning_evidence
CREATE TABLE learning_evidence (
    id VARCHAR(32) PRIMARY KEY,
    organization_id VARCHAR(32) NOT NULL REFERENCES organizations(id),
    learning_id VARCHAR(32) NOT NULL REFERENCES organizational_learning(id),
    source_type VARCHAR(32) NOT NULL,
    source_id VARCHAR(32) NOT NULL,
    excerpt TEXT,
    role VARCHAR(40) NOT NULL DEFAULT 'primary',
    weight FLOAT NOT NULL DEFAULT 1.0,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (learning_id, source_type, source_id)
);

-- 4. Create pattern_detections
CREATE TABLE pattern_detections (
    id VARCHAR(32) PRIMARY KEY,
    organization_id VARCHAR(32) NOT NULL REFERENCES organizations(id),
    pattern_type VARCHAR(60) NOT NULL,
    key VARCHAR(300) NOT NULL,
    title VARCHAR(300) NOT NULL,
    detail TEXT,
    family VARCHAR(20) NOT NULL DEFAULT 'execution',
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'candidate',
    count INTEGER NOT NULL DEFAULT 0,
    confidence FLOAT NOT NULL DEFAULT 0.3,
    evidence_json JSONB DEFAULT '[]',
    entities_json JSONB DEFAULT '[]',
    supporting_memory_ids JSONB DEFAULT '[]',
    supporting_event_ids JSONB DEFAULT '[]',
    supporting_relationships JSONB DEFAULT '[]',
    detail_json JSONB DEFAULT '{}',
    scope_type VARCHAR(16) NOT NULL DEFAULT 'org',
    scope_id VARCHAR(32),
    auth_project_id VARCHAR(32),
    time_window_days INTEGER NOT NULL DEFAULT 30,
    trend VARCHAR(20) NOT NULL DEFAULT 'stable',
    avg_interval_days FLOAT,
    last_evaluated_at TIMESTAMPTZ,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    UNIQUE (organization_id, pattern_type, key)
);

-- 5. Indexes
CREATE INDEX ix_organizational_learning_org_kind ON organizational_learning(organization_id, kind);
CREATE INDEX ix_learning_evidence_learning ON learning_evidence(learning_id);
CREATE INDEX ix_pattern_detections_org_type ON pattern_detections(organization_id, pattern_type);
CREATE INDEX ix_pattern_detections_org_lifecycle ON pattern_detections(organization_id, status);
```

---

## 5. Test Suite Freeze (128 Tests)

### 5.1 Test Categories (All Must Remain Green)

| Category | Tests | Purpose |
|----------|-------|---------|
| Phase C Evidence Composer | 16 | Governance-first evidence, exact-once, provenance |
| Phase D Pattern Qualifier | 19 | Cohort building, qualification, contradictions |
| Phase E Lesson Qualifier | 12 | Epistemic ladder, no recommendation |
| Phase F Materialization | 9 | Exact-once, governance gate, scope |
| Phase G Brain Integration | 9 | Routing, governance, contradictions, temporal, provenance |
| Phase H Surface Integration | 7 | Projects, Decisions, Dashboard, Intelligence, Knowledge |
| Phase I Adversarial | 11 | Longitudinal, temporal, contradictions, isolation, provenance, exact-once, scope, cross-surface, supersession, schema, regression |
| 4F.7 Brain | 8 | Decision questions, who/why/what-if |
| 4H.6 Step 7 Brain | 13 | Intent routing, collision guards, deterministic |
| **TOTAL** | **128** | **ALL MUST PASS** |

### 5.2 Adversarial Test Scenarios (Must Not Be Removed)

1. **Longitudinal chain** - Decision→Action→Outcome→Evidence→Pattern→Lesson→Materialization→Brain→Surfaces
2. **Temporal truth** - Historical belief queries vs current state
3. **Contradiction preservation** - Both sides visible, nothing discarded
4. **Tenant isolation** - Org B cannot see Org A learning across ALL surfaces
4. **Provenance chain** - Lesson→Pattern→Evidence→Assessment→Outcome→Decision
5. **Exact-once replay** - 5× replay = 1 lesson, 1 materialization
6. **Scope boundaries** - Project learning ≠ Company learning
7. **Cross-surface consistency** - Same learning across Brain/Dashboard/Intelligence/Knowledge
8. **Supersession** - v1→v2→v3 via fingerprint, temporal queries respect history
9. **Schema verification** - All tables/columns/constraints exist
10. **4H.6 regression** - All frozen contracts intact

---

## 6. Out of Scope for 4H.7 (Explicitly NOT Included)

| Capability | Reason |
|------------|--------|
| LLM-generated recommendations | Learning ≠ Recommendation; advisory only |
| Autonomous decision execution | Human-in-the-loop required |
| Predictive analytics / forecasting | Not epistemic; learning is descriptive |
| Cross-organization learning transfer | Tenant isolation is absolute |
| Automatic scope promotion | Requires explicit governance |
| Lesson → automatic action conversion | Human decision required |
| Real-time streaming learning | Batch/event-driven only |
| Unlimited learning retention | Bounded by exact-once + governance |

---

## 6. Verification Artifacts

### 6.1 Test Execution Log (Latest Run)

```
Phase I Adversarial Verification: 11/11 PASS
Phase G Brain Integration: 9/9 PASS
Phase H Surface Integration: 7/7 PASS
Phase C-F Regression: 56/56 PASS
4F.7 Brain: 8/8 PASS
4H.6 Step 7 Brain: 13/13 PASS
4E.1-4E.4 Canonical: 43/43 PASS
----------------------------------------
TOTAL: 128/128 PASS
```

### 6.2 Database Verification

```bash
# PostgreSQL schema verification
psql -d vcos -c "\dt" | grep -E "(organizational_learning|learning_evidence|pattern_detections|company_decision|company_memory|company_changes|company_health|company_state)"
# All 16 tables present ✅

# Column verification
psql -d vcos -c "\d organizational_learning"
# All 22 columns with correct types ✅

# Constraints
psql -d vcos -c "\d organizational_learning" | grep -i unique
# uq_organizational_learning_fingerprint ✅
```

---

## 7. Sign-Off

### 7.1 Architectural Review

- [x] **Contracts frozen** — No API/schema changes without contract amendment
- [x] **Schema frozen** — No table/column/index modifications without migration
- [x] **Invariants documented** — Governance-first, exact-once, temporal, contradictions, provenance, isolation, scope, learning≠recommendation
- [x] **Tests frozen** — 128 tests must remain green
- [x] **Migrations verified** — Fresh PostgreSQL deploys cleanly
- [x] **4H.6 intact** — All frozen contracts still green
- [x] **Out of scope documented** — Clear boundary for future work

### 7.2 Freeze Declaration

> **4H.7 Organizational Learning Pipeline is hereby FROZEN AND RATIFIED.**
>
> The implementation described in this document represents the complete, verified, and stable 4H.7 Organizational Learning Pipeline. All contracts, schemas, APIs, invariants, and test requirements documented herein are now canonical. Any modification requires a formal contract amendment following the established governance process.
>
> **Next Phase:** 4I — Universal Virtual Company OS integration (building ON this frozen foundation).

---

**Document Version:** 1.0  
**Date:** 2026-08-24  
**Status:** FINAL — DO NOT MODIFY WITHOUT CONTRACT AMENDMENT  
**Classification:** Architecture — 4H.7 Final Freeze