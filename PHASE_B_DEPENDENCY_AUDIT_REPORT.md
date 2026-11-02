# Phase B — Dependency Audit Report
## 4H.7 P0 Dependency Hardening

**Date:** 2026-08-22
**Contract:** `SLICE4H7_MASTER_IMPLEMENTATION_CONTRACT.md`
**Status:** AUDIT COMPLETE — READY FOR IMPLEMENTATION

---

## 1. EXECUTIVE SUMMARY

Two P0 dependencies block safe 4H.7 implementation:

| P0 | Issue | Risk |
|----|-------|------|
| **P0-1** | `CompanyDecision.decision_id` (String(64)) travels through columns still defined as `String(32)` | PostgreSQL truncation/error; SQLite passes silently |
| **P0-2** | `event_bus.process_pending(limit=50)` called without `organization_id` in worker + brain route | Cross-tenant event processing; institutional intelligence contamination |

**No Phase C (4H.7 learning code) may begin until both are resolved and verified on PostgreSQL.**

---

## 2. P0-1: VARCHAR(32) TRUNCATION AUDIT

### 2.1 Canonical Identifier Profile
```
CompanyDecision.decision_id = "dec:{kind}:{hex12}"
Longest kind: "commercial_action" (16 chars)
Format: "dec:" (4) + kind (16) + ":" (1) + hex12 (12) = 33 chars minimum
Actual observed: "dec:commercial_action:<hex12>" = 34+ chars
```

### 2.2 Columns Carrying Canonical Decision ID (String(32) — TRUNCATION RISK)

| Table | Column | Current Type | Required Type | Model File | Line |
|-------|--------|--------------|---------------|------------|------|
| `company_decision_precedents` | `precedent_decision_id` | String(32) | String(64) | `company_operating.py` | 640, 782 |
| `company_decision_contradictions` | `precedent_decision_id` | String(32) | String(64) | `company_operating.py` | 782 |
| `company_decision_contradictions` | `lesson_memory_id` | String(32) | String(64) | `company_operating.py` | 780 |
| `knowledge_recommendations` | `decision_id` | String(32) | String(64)* | `knowledge.py` | 676 |

\* **Note:** `KnowledgeRecommendation.decision_id` references legacy `Decision.id` (String(32)). However, if 4E.6+ code stores canonical `CompanyDecision.decision_id` here, it must be widened. Audit shows 4E.6 action_ops_engine passes `source_company_decision_id` to action creation — verify runtime usage.

### 2.3 Columns Already Correct (String(64))

| Table | Column | Type | Model File | Line |
|-------|--------|------|------------|------|
| `company_decisions` | `decision_id` | String(64) | `company_operating.py` | 391 |
| `company_actions` | `source_company_decision_id` | String(64) | `company_actions.py` | 71 |
| `company_actions` | `source_scenario_id` | String(64) | `company_actions.py` | 72 |
| `company_decision_alternatives` | `decision_id` | String(64) | `company_operating.py` | 536 |
| `company_decision_evidence` | `decision_id` | String(64) | `company_operating.py` | 585 |
| `company_decision_quality` | `decision_id` | String(64) | `company_operating.py` | 683 |
| `company_decision_tracks` | `decision_id` | String(64) | `company_operating.py` | 776 |

### 2.4 Database Migration Status
**Already Applied (database.py:251-256):**
```sql
ALTER TABLE company_actions ADD COLUMN IF NOT EXISTS source_company_decision_id VARCHAR(64);
ALTER TABLE company_actions ADD COLUMN IF NOT EXISTS source_scenario_id VARCHAR(64);
ALTER TABLE company_actions ALTER COLUMN source_company_decision_id TYPE VARCHAR(64);
ALTER TABLE company_actions ALTER COLUMN source_scenario_id TYPE VARCHAR(64);
```

**Missing Migrations Required:**
```sql
-- company_decision_precedents
ALTER TABLE company_decision_precedents ALTER COLUMN precedent_decision_id TYPE VARCHAR(64);

-- company_decision_contradictions
ALTER TABLE company_decision_contradictions ALTER COLUMN precedent_decision_id TYPE VARCHAR(64);
ALTER TABLE company_decision_contradictions ALTER COLUMN lesson_memory_id TYPE VARCHAR(64);

-- knowledge_recommendations (if canonical decision IDs stored)
ALTER TABLE knowledge_recommendations ALTER COLUMN decision_id TYPE VARCHAR(64);
```

### 2.5 Model Changes Required

| File | Line | Change |
|------|------|--------|
| `app/models/company_operating.py` | 640 | `precedent_decision_id: Mapped[str] = mapped_column(String(64), nullable=False)` |
| `app/models/company_operating.py` | 780 | `lesson_memory_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)` |
| `app/models/company_operating.py` | 782 | `precedent_decision_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)` |
| `app/models/knowledge.py` | 676 | `decision_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)` |

### 2.6 Unique Constraints & Indexes Affected
| Table | Constraint | Column | Action |
|-------|------------|--------|--------|
| `company_decision_precedents` | `uq_cdp_exact_once` | `precedent_decision_id` | Recreate after ALTER |
| `company_decision_contradictions` | `uq_cdc_key` | `precedent_decision_id` | Recreate after ALTER |

---

## 3. P0-2: EVENT BUS TENANT ISOLATION AUDIT

### 3.1 Current Architecture

```
EventWorker (global)
    ↓
event_bus.process_pending(db, limit=5000)  # NO organization_id
    ↓
SELECT * FROM background_jobs WHERE status IN ('queued','retry')  # ALL TENANTS
    ↓
Process events from ALL organizations in single pass
```

### 3.2 Vulnerable Call Sites

| Call Site | File | Line | Context | Fix |
|-----------|------|------|---------|-----|
| Event Worker | `app/workers/event_worker.py` | 21 | Background worker runs every 15s | Make org-scoped |
| Brain Outcome Route | `app/api/v1/brain.py` | 7489 | Sync drain after outcome recording | Pass `org.id` |
| Intelligence Route | `app/api/v1/intelligence.py` | 130 | **Already correct** — passes `org.id` | — |

### 3.3 Event Bus Capability (Already Exists)
`process_pending()` already supports `organization_id` parameter (event_bus.py:124, 145):
```python
async def _process_pending_unlocked(
    self,
    db: AsyncSession,
    *,
    limit: int = 100,
    event_names: Optional[list[str]] = None,
    organization_id: Optional[str] = None,  # ← SUPPORTED
) -> int:
```
The filtering logic exists at lines 201-203, 219-223, 229-230.

### 3.4 Required Fix Strategy

**Option A: Per-Organization Event Workers (Recommended)**
- Spawn one event worker per organization (dynamic based on active orgs)
- Each worker calls `process_pending(db, organization_id=org_id)`
- Preserves exact-once, CAS, orphan adoption per-org

**Option B: Single Worker with Org-Round-Robin**
- Single worker iterates active organizations
- For each org: `process_pending(db, organization_id=org_id, limit=org_limit)`
- Simpler but adds latency

**Option C: Global Worker with Org-Scoped Claim (Minimal Change)**
- Worker fetches orgs with pending work
- For each org: claim + process batch
- Preserves single worker process

**Contract Requirement:** Must not redesign event bus; only harden tenant boundary while preserving CAS, orphan adoption, exact-once, locking, replay semantics.

---

## 4. FILES REQUIRING MODIFICATION

### 4.1 P0-1: VARCHAR(32) Fix
| File | Type | Changes |
|------|------|---------|
| `app/models/company_operating.py` | Model | 4 column widenings (lines 640, 780, 782) |
| `app/models/knowledge.py` | Model | 1 column widening (line 676) |
| `app/db/database.py` | Migration | 4 ALTER TABLE statements in `_POSTGRES_ALTERS` |
| `alembic/versions/` | Migration | New revision for schema change |

### 4.2 P0-2: Event Bus Tenant Isolation
| File | Type | Changes |
|------|------|---------|
| `app/workers/event_worker.py` | Worker | Org-scoped processing loop |
| `app/api/v1/brain.py` | Route | Pass `org.id` to `process_pending` |

---

## 5. TEST REQUIREMENTS

### 5.1 P0-1 Tests (PostgreSQL Mandatory)

| Test | Description | Expected |
|------|-------------|----------|
| `test_long_decision_id_persist` | Insert `dec:commercial_action:<12hex>` into all 4 fixed columns | No truncation; exact round-trip |
| `test_decision_lineage_full` | Decision → Action → Outcome → Assessment with long IDs | All links intact |
| `test_precedent_long_id` | Create precedent with long canonical ID | Persists correctly |
| `test_contradiction_long_id` | Create contradiction with long canonical ID | Persists correctly |
| `test_migration_up_down` | Apply + rollback migration | Clean schema transitions |

### 5.2 P0-2 Tests

| Test | Description | Expected |
|------|-------------|----------|
| `test_tenant_isolation_worker` | Tenant A + B events; process A only | A processed, B untouched |
| `test_brain_drain_scoped` | Brain outcome route with org context | Only org's events processed |
| `test_cross_tenant_no_leak` | Process A events; verify B's queue unchanged | Zero cross-contamination |
| `test_exact_once_preserved` | Process same event twice with org scope | Single logical result |
| `test_concurrent_workers_same_org` | Two workers same org | One claim succeeds, other no-op |

### 5.3 Regression Tests (Must Remain Green)
- All 4H.1–4H.6 test suites (1223 tests per SLICE4H6 verification)
- `test_4h6_step2..7` (92 tests)
- `test_4g7_engine`, `test_4h1..4h5_engine` (88 tests)
- Full pytest suite

---

## 6. IMPLEMENTATION SEQUENCE

### Step 1: Database Migration + Model Changes (P0-1)
```bash
# 1. Create alembic revision
alembic revision -m "widen_decision_id_columns_to_64"

# 2. Edit migration: add ALTER TABLE for 4 columns
# 3. Edit models: change String(32) -> String(64)
# 4. Run migration on PostgreSQL
# 5. Verify long IDs persist
```

### Step 2: Event Worker Org-Scoping (P0-2)
```python
# app/workers/event_worker.py
async def run_once(limit: int = 5000) -> int:
    async with SessionLocal() as db:
        # Get orgs with pending work
        orgs = await get_orgs_with_pending_events(db)
        total = 0
        for org_id in orgs:
            total += await event_bus.process_pending(
                db, limit=limit, organization_id=org_id
            )
        return total
```

### Step 3: Brain Route Fix (P0-2)
```python
# app/api/v1/brain.py line 7489
processed = await event_bus.process_pending(
    db, limit=50, organization_id=org.id
)
```

### Step 4: Test & Verify
1. Run all P0-1 PostgreSQL tests
2. Run all P0-2 tenant isolation tests
3. Run full 4H.1–4H.6 regression suite
3. Verify 4H.6 schema baseline unchanged (`SLICE4H6_SCHEMA_POST_FREEZE.json`)

---

## 7. ACCEPTANCE CRITERIA (PHASE B DONE)

| Criterion | Verification |
|-----------|--------------|
| **P0-1 Fixed** | `dec:commercial_action:<12hex>` persists in all 4 columns on PostgreSQL; round-trip exact |
| **P0-1 Migration** | Clean apply + rollback; no data loss |
| **P0-2 Fixed** | Event worker processes per-org; brain route passes `org.id` |
| **P0-2 Isolation** | Tenant A events never processed in Tenant B context |
| **Exact-Once Preserved** | Replay tests pass; CAS + orphan adoption intact |
| **Regression Green** | 1223+ tests pass; 4H.6 schema baseline SHA256 unchanged |
| **No 4H.7 Code** | `organizational_learning` table unchanged; no new learning tables |

---

## 8. RISK MITIGATION

| Risk | Mitigation |
|------|------------|
| Migration fails on existing data | Test on production-shaped data first; dry-run |
| Event worker org discovery performance | Cache org list; only query orgs with pending jobs |
| Brain route double-drain logic | Keep 2-pass drain but scoped to org |
| SQLite tests still pass | VARCHAR(64) compatible with SQLite; no truncation there |

---

## 9. SIGN-OFF

| Phase | Auditor | Date | Status |
|-------|---------|------|--------|
| P0-1 Audit | | 2026-08-22 | ✅ COMPLETE |
| P0-2 Audit | | 2026-08-22 | ✅ COMPLETE |
| Implementation | | | PENDING |
| Testing | | | PENDING |
| Phase B Acceptance | | | PENDING |

---

**NEXT ACTION:** Begin implementation of P0-1 (migration + model changes) followed by P0-2 (event worker + brain route). Do not proceed to Phase C until all acceptance criteria are verified on PostgreSQL.