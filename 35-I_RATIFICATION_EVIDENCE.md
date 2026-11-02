# 35-I Ratification Evidence

## Executive Summary

**35-I — LONGITUDINAL REALITY ACCEPTANCE** is **FULLY RATIFIED**.

The acceptance suite (`backend/tests/acceptance/test_longitudinal_reality.py`) exercises the
longitudinal architecture through real interfaces only: canonical mutation boundary,
canonical reliability service, company-context governance resolution, and the real
PostgreSQL session. All **16 tests pass on PostgreSQL 18.2** in two independent
databases (the verification matrix DB and the CI-simulation probe DB), re-verified on
the final code state after all session changes.

## Verification Matrix

| Environment | Database | Result | Time |
|-------------|----------|--------|------|
| PostgreSQL 18.2 | `vcos_test_matrix` | ✅ 16/16 | 88.55s |
| PostgreSQL 18.2 | `vcos_ci_probe` (fresh, CI-like) | ✅ 16/16 | 104.90s |

```
16 passed in 88.55s (0:01:28)   # vcos_test_matrix
16 passed in 104.90s (0:01:44)  # vcos_ci_probe
```

## Test Inventory and Coverage Mapping

The 14 coverage areas declared in the suite docstring map to the classes below.

| # | Coverage Area | Class / Tests |
|---|---------------|---------------|
| 1, 2 | Historical immutability (append-only canonical timeline) | `TestHistoricalImmutability` — `test_canonical_create_appends_timeline_event`, `test_timeline_event_duplicate_key_rejected_original_intact` |
| 3, 4, 6, 12 | Point-in-time reconstruction, current-vs-historical separation, supersession chains, out-of-order events | `TestPointInTimeReconstruction` — `test_snapshot_supersession_chain_and_point_in_time_lookup`, `test_reality_and_knowledge_timelines_stay_distinct`, `test_out_of_order_events_reconstruct_by_occurred_at`, `test_company_memory_snapshot_is_derived_projection` |
| 5 | Decision history and provenance preservation | `TestDecisionHistory` — `test_decision_lifecycle_and_provenance_preserved` |
| 8 | Provenance preservation across source loss | `TestProvenancePreservation` — `test_provenance_survives_source_loss_and_flags_breaks` |
| 7 | Tenant isolation of historical queries and reconstruct attempts | `TestTenantHistoricalIsolation` — `test_historical_queries_are_tenant_scoped_and_attempts_recorded` |
| 9 | Epistemic calibration across time (prediction → outcome) | `TestEpistemicCalibration` — `test_prediction_outcome_calibration_trajectory_preserved` |
| 10 | Organizational continuity across structure changes | `TestOrganizationalContinuity` — `test_org_changes_preserve_past_states` |
| 11 | Merger/acquisition lineage preservation | `TestMergerLineage` — `test_ma_lineage_links_entities_and_preserves_history` |
| 13 | Longitudinal integrity invariant detection | `TestLongitudinalIntegrity` — `test_clean_org_produces_no_findings`, `test_all_five_longitudinal_invariants_detected` |
| 14 | Recovery after interrupted operations (35-H reliability infrastructure) | `TestLongitudinalHistoryUnderFailure` — `test_recovery_after_interrupted_external_operation_keeps_history`, `test_replayed_create_after_failure_is_exactly_once` |

## Integration with 35-G / 35-H Infrastructure

- **35-G (canonical validation integrity):** the suite drives writes through the real
  canonical mutation boundary (`app.intelligence.canonical_mutation`, mutation types,
  governance resolution via `resolve_caller_access`, `permission_service`) — no direct
  table fabrication for canonical entities.
- **35-H (failure under load / reliability):** the failure class reuses the 35-H tables
  (`CanonicalOperation`, `ExternalUnknownState`) and `canonical_reliability_service`
  interrupted-operation semantics, and asserts history survives interruption and that
  replayed creates stay exactly-once.
- **Integrity service:** `canonical_reality_integrity_service` findings are asserted for
  both a clean org (no findings) and a deliberately corrupted org (all five longitudinal
  invariants detected).

## Test Environment

- **PostgreSQL**: 18.2 (x86_64-windows / msvc-19.44.35222), `localhost:5432`
- **Databases**: `vcos_test_matrix` (verification matrix) and `vcos_ci_probe` (CI-sim, truncated to a fresh state before the final run)
- **Python**: 3.13.7 · **SQLAlchemy**: 2.0.x (asyncpg) · **pytest**: 8.3.4 · **pytest-asyncio**: 0.24.0
- **Env**: `TEST_DATABASE_URL=<asyncpg url>`, `VCOS_TEST_MODE=0`
- **Marker**: `pytestmark = pytest.mark.postgres` — the suite is PostgreSQL-only by design
  (integrity queries use `LAG` window functions, `bool_or`, `IS DISTINCT FROM`).

### Schema bootstrap

The 35-I tables (`app.models.longitudinal`) are not created by alembic migrations in every
environment. An autouse fixture (`longitudinal_schema`) bootstraps the canonical model
tables with `Base.metadata.create_all(..., tables=[...], checkfirst=True)` — a no-op
wherever they already exist. It never fabricates data and never alters or drops tables.
The fixture also pre-creates the 35-H reliability tables and the integration-layer tables
required by `ExternalUnknownState`'s foreign key.

## Documented Finding (schema coupling — not masked)

`ExternalUnknownState.operation_id` carries a real PostgreSQL FK to
`external_operations.id`, while `reconcile_external_unknown` loads the same id from
`canonical_operations`. On SQLite the FK was unenforced; on PostgreSQL the suite seeds
both layers so the reliability path runs with the real constraint active. This
cross-schema coupling is annotated in the test file (see the failure/recovery class) and
is surfaced here rather than hidden. It does not affect any test outcome.

## CI Integration

`ci.yml` includes a dedicated full-regression step:

```yaml
# .github/workflows/ci.yml (full-regression job)
- name: Run 35-I Longitudinal Reality tests
  run: |
    python -m pytest \
      tests/acceptance/test_longitudinal_reality.py \
      ...
```

CI provisions `postgres:18` with the `pg_trgm` extension; the suite runs against
`TEST_DATABASE_URL`. The same suite is included in the post-fix backend regression
battery (412 passed in 73.08s: longitudinal + gates 6B–6F + 35G.2 + 35H + 13/30/31/32 +
recovery_manifest) and its runtime path is exercised end-to-end by the frontend
Playwright suite (33 passed, full-stack against the real API).

## Runner Commands

```powershell
# PowerShell (Windows dev box)
$env:TEST_DATABASE_URL="postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test_matrix"
$env:VCOS_TEST_MODE="0"
python -m pytest tests/acceptance/test_longitudinal_reality.py -v --no-header -p no:cacheprovider
```

```bash
# CI / bash
export TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test"
export VCOS_TEST_MODE=0
python -m pytest tests/acceptance/test_longitudinal_reality.py -v
```

## Files

| File | Role |
|------|------|
| `backend/tests/acceptance/test_longitudinal_reality.py` | The 35-I acceptance suite (16 tests, 10 classes) |
| `backend/app/models/longitudinal.py` | Canonical longitudinal models under test |
| `backend/app/intelligence/canonical_mutation.py` | Canonical mutation boundary exercised by every write |
| `backend/app/services/canonical_reality_integrity_service.py` | Integrity findings asserted by the integrity class |
| `backend/app/services/canonical_reliability_service.py` | Interrupted-operation / unknown-state semantics (35-H reuse) |
| `.github/workflows/ci.yml` | Full-regression step running this suite |

## Ratification Verdict

| Criterion | Status |
|-----------|--------|
| 16/16 tests pass on PostgreSQL (final code state) | ✅ |
| Passes in two independent databases (matrix + probe) | ✅ |
| Real interfaces only (no mocked canonical boundary) | ✅ |
| Historical immutability verified | ✅ |
| Point-in-time reconstruction verified | ✅ |
| Supersession chains / out-of-order events verified | ✅ |
| Tenant historical isolation verified | ✅ |
| Provenance survival across source loss verified | ✅ |
| Epistemic calibration trajectory verified | ✅ |
| Organizational continuity and M&A lineage verified | ✅ |
| Integrity invariants detected independently | ✅ |
| Recovery/exactly-once under failure verified | ✅ |
| Documented schema-coupling finding surfaced (not hidden) | ✅ |
| CI step present in full-regression workflow | ✅ |
| Evidence artifact created (this file) | ✅ |

## FINAL VERDICT

**35-I — FULLY IMPLEMENTED, VERIFIED, AND RATIFIED**

---

**Evidence captured**: 2026-10-19
**PostgreSQL**: 18.2 on Windows x64
**Tests passing**: 16/16 (two databases, re-verified after all session changes)
**Related**: 35-G (canonical validation integrity) and 35-H (failure under load) infrastructure reused directly
