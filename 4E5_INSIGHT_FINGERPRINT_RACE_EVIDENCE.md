# 4E.5 — Insight Fingerprint Materialization Race: Evidence

**Date:** 2026-10-19
**Scope:** knowledge-intelligence insight materialization (`action_engine.materialize`)
**Database:** real PostgreSQL 18.2 (x86_64-windows), `vcos_test_matrix`
**Outcome:** defect fixed, 7 new real-PostgreSQL regression tests, full targeted
regression battery green.

## 1. Defect

`GET /api/v1/brain/knowledge/brief` (and every other `materialize()` caller:
`/insights`, `/health-center`) could return HTTP 500 under concurrent calls.
Two workers deriving the same insight from the same canonical substrate read
the same "existing" snapshot, both took the insert branch, and the loser hit

```
sqlalchemy.exc.IntegrityError: duplicate key value violates unique constraint
"uq_knowledge_intel_insight_fingerprint"
```

## 2. Root cause

`materialize()` loaded `KnowledgeIntelInsight` rows for the tenant into
`by_fingerprint`, then inserted candidates whose `(kind, fingerprint)` was
absent. The unique constraint is the correct enforcement mechanism, but the
insert branch had no conflict resolution: the losing flush surfaced the
`IntegrityError` to the endpoint.

Constraint (unchanged, tenant-scoped):

```python
# backend/app/models/knowledge.py:737
UniqueConstraint(
    "organization_id", "kind", "fingerprint",
    name="uq_knowledge_intel_insight_fingerprint",
)
```

## 3. Fix (`backend/app/knowledge/action_engine.py`)

- Added `_is_fingerprint_conflict(exc)` (L162): true only when the underlying
  driver error names `uq_knowledge_intel_insight_fingerprint` (PostgreSQL
  `constraint_name` or message), with an SQLite message fallback. All other
  integrity errors — other unique constraints, foreign-key violations — are
  re-raised.
- Insert is now savepoint-protected (L713-733):

```python
try:
    async with db.begin_nested():
        db.add(row)
        await db.flush()
except IntegrityError as exc:
    if not _is_fingerprint_conflict(exc):
        raise
    if sa_inspect(row).session is db:
        db.expunge(row)
    row = (await db.execute(select(KnowledgeIntelInsight).where(...))).scalar_one_or_none()
    if row is None:
        raise
    by_fingerprint[key] = row
```

- The conflict winner falls through to the existing update path; the "created"
  audit event, notification, and counters fire only for the worker that
  actually inserted. The unique constraint still does the arbitration — no
  logic that could create duplicates was added.
- Exactly-once semantics preserved: one row and one `created` event per
  `(organization_id, kind, fingerprint)`; replay produces zero new rows.

## 4. Tests added

`backend/tests/test_4e5_insight_materialization_race.py` (409 lines, 7 tests,
real PostgreSQL). Concurrency is synchronized by polling the losing backend's
`pg_stat_activity.wait_event_type = 'Lock'` — deterministic race proof, not
sleep-based timing.

1. `test_sequential_replay_is_exact_once` — replay creates nothing new,
   refreshes existing rows, exactly one `created` event per insight.
2. `test_concurrent_materialize_converges_to_one_insight` — leader commits
   while follower is observed waiting on the unique index; follower resolves
   to the winner, creates nothing, commits cleanly.
3. `test_multiple_concurrent_materializers_converge` — two losers, same
   outcome.
4. `test_knowledge_brief_survives_fingerprint_race` — the actual
   `brief()` path used by the HTTP endpoint completes under the same race.
5. `test_fingerprint_conflict_classifier_against_real_constraints` — real
   fingerprint violation classified true; a different real unique violation
   and a real FK violation classified false.
6. `test_fingerprint_unique_per_tenant_not_global` — the same fingerprint is
   legal once per tenant, proving the fix did not change constraint scope.
7. `test_genuine_integrity_error_is_not_swallowed` — with the classifier
   forced false, the `IntegrityError` propagates (no silent swallowing).

## 5. Results (commands and actual output)

Run from `D:\vcos1\workspace\vcos\backend` with
`TEST_DATABASE_URL=postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test_matrix`,
`VCOS_TEST_MODE=0`.

| Command (tests/) | Result | Time |
|---|---|---|
| `pytest test_4e5_insight_materialization_race.py -v` | **7 passed** | 8.26s |
| `pytest test_4e5_knowledge_operations.py -v` | **14 passed** | 23.21s |
| 4E1–4E7 knowledge battery incl. race file | **99 passed** | 67.70s |
| `pytest test_gate32_canonical_reliability.py -v` | **71 passed** | 13.81s |
| `pytest test_gate35g2_canonical_concurrency_stress.py test_gate35h_failure_under_load.py` | **78 passed** | 14.57s |
| `pytest acceptance/test_longitudinal_reality.py -v` (35-I) | **16 passed** | 30.40s |
| `pytest test_gate31_canonical_reality_integrity.py -v` | **36 passed** | 17.07s |

## 6. Pre-existing defect found and fixed during regression

`test_recommendation_full_lifecycle_to_verified_task` failed with
`cannot 'verify' from lifecycle 'verified'`, deterministically. Root cause
(verified identical at `HEAD` via `git show
HEAD:backend/app/knowledge/action_engine.py`): `recommendation_lifecycle`
mutated `row.lifecycle` and the audit list **before** validating
verify/convert/execute preconditions. The API's 400 for a bad verify left the
dirty ORM object in the shared test session, so the subsequent valid verify
saw `lifecycle='verified'`. Fix: precondition checks moved before any
mutation (L1590-1595). The endpoint behavior is unchanged (still 400 with the
same messages); only the invalid-state mutation was removed. Re-run of the
4E5 operations suite after the fix: 14/14.

## 7. Files changed

| File | Change |
|---|---|
| `backend/app/knowledge/action_engine.py` | race fix + `_is_fingerprint_conflict`; lifecycle validate-before-mutate ordering fix |
| `backend/tests/test_4e5_insight_materialization_race.py` | new — 7 real-PG regression tests |
| `backend/app/api/v1/meetings.py` | (earlier task) meeting-notes DELETE route fix — not part of this change |

No RLS-protected files, no alembic revisions, no `.env`, no frontend files
were modified.

## 8. Remaining limitations

- Verified against local PostgreSQL 18.2 only; no hosted/staging environment
  or remote CI run was exercised in this task.
- Playwright e2e (33/33), lint and build were green earlier in the session and
  were not re-run here (no frontend or config changes); the backend-only
  change does not alter their inputs.
- The original "412-passed" full battery composition is not recorded; the
  targeted regression battery above was used instead.
- RLS rollout (0/662 tables) is a separate, protected workstream and remains
  out of scope.
- No production RPO/RTO claims derive from this evidence.
