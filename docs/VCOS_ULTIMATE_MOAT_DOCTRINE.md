# VCOS Ultimate Moat Doctrine

**Status:** Canonical doctrine, reconstructed from the ratified architecture and evidence trail.
**Purpose:** Every future session MUST read this before making changes. It defines what VCOS is,
what must never be violated, and how work earns the right to be called "done."

---

## 1. The thesis

VCOS (Universal Company Operating System) is not a tool collection and not an "AI features" layer.
It is a single **canonical company reality** with compounding intelligence:

1. **ONE canonical company reality.** All business entities — decisions, authorizations,
   commitments, actions, observations, outcomes — live in one governed substrate.
   There is never a second truth, a parallel brain, or a side-channel write path.
2. **Governance before action.** Authority is explicit: who may decide, authorize,
   commit, and execute. The system knows the difference between stating something and
   being allowed to do it.
3. **Provenance everywhere.** Every canonical fact carries its source, actor, and chain
   of derivation. Untraceable facts are not canonical facts.
4. **Temporal truth.** The company's state is a function of time. Versions, supersession,
   and as-of queries are first-class; history is never overwritten.
5. **The Company Brain.** Intelligence is derived from canonical reality with epistemic
   labeling — observation, inference, prediction are distinct record types with distinct
   confidence semantics.
6. **The compounding loop.** Verified outcomes feed learning. Every loop turn that
   survives validation measurably strengthens the moat. This is why evidence discipline
   (below) is the highest law.

## 2. Semantic distinctions (non-negotiable)

Enforced in schema and services, not just prose:

```
DECISION ≠ AUTHORIZATION ≠ COMMITMENT ≠ RESPONSIBILITY ≠ ACTION ≠ EXECUTION ≠ OUTCOME
OBSERVATION ≠ INFERENCE ≠ PREDICTION
AI OUTPUT ≠ CANONICAL TRUTH
SIMULATION ≠ OUTCOME
UNKNOWN ≠ FAILED ≠ SUCCESS
```

Conflating any of these is a correctness bug of the highest severity. A decision is not an
authorization; an action is not an outcome; "we don't know" is a distinct, honest state.

## 3. Evidence discipline (the law of done)

A slice of work is DONE only when all of the following are true:

1. **Real environment.** Verified against real PostgreSQL / real services. SQLite-only
   green tests do not ratify PostgreSQL-critical behavior.
2. **No mocks in the proof path.** Mock backups, mock restores, fabricated checksums, or
   simulated outages are NOT evidence. They may exist as unit-test scaffolding, but the
   ratification artifact must be produced by real execution.
3. **Reproducible artifact.** A durable markdown/JSON evidence file with: what ran, where,
   exact commands, raw outputs (or faithful summaries with paths to raw outputs), the
   environment identity (versions, host, database names), limitations, and the verdict.
4. **Honest failure.** BLOCKED is an acceptable, reportable outcome. Weakening an
   assertion, skipping a validation, or setting a test-mode bypass to make a demo pass is
   forbidden (`VCOS_TEST_MODE=1` may never be used for evidence runs).
5. **Ratified work is closed.** Once ratified, a workstream is not reopened without
   reproducible evidence of a defect AND a new regression test that captures it.

**Workflow per slice:** EXPLORE → UNDERSTAND → REUSE → EXTEND → IMPLEMENT → STRENGTHEN →
INTEGRATE → VERIFY → RATIFY → STOP. Stop means: do not start the next stage in the same
slice; write the evidence file and stop cleanly.

## 4. Safety rules (data and environments)

1. **Never assume configuration.** Verify the actual database, service, and paths before
   any backup, restore, migration, or destructive operation. (Historical near-miss this
   doctrine exists to prevent: the app database was `vcos4` while `pgbackrest.conf`
   pointed at `vcos_test`.)
2. **Production data is untouchable by tests.** Test data may only be written to
   designated test databases/orgs. Restores must be into isolated instances (scratch port,
   scratch data dir) — never over a live data directory.
3. **Discriminate before you destroy.** `vcos4`, `vcos_test`, `vcos4_restore_test`,
   `vcos4_recovery_verify_*` are different things. A command that drops/overwrites must
   print and check the target first.
4. **Archive integrity is sacred.** The WAL archive and base backup artifacts are the
   ability to recover the company. Never "clean up" archive files, never re-point the
   archive path, never recycle a segment that is part of a verified range.

## 5. Architecture laws

1. All canonical writes go through `app/intelligence/canonical_mutation.py`.
2. Validation services are re-used across live and restored databases — a restore earns
   confidence by passing the SAME canonical validators as production.
3. Capability-aware validation (`app/validation/capability_contract.py`): when a capability
   (pgbackrest, PITR, etc.) is absent, checks report `NOT_APPLICABLE` with the capability
   gap recorded — never a silent pass.
4. Recovery has a state machine (`recovery_gates.py`, 19 states) and every promotion of
   recovery state must execute its gate's real validator. Gates may FAIL; they may not be
   skipped to reach a green state.
5. Evidence generation is machine-readable (`recovery_evidence.py`) so the audit trail is
   queryable, not narrative-only.

## 6. Known permanent limitations (carried forward honestly)

- WAL segment `000000010000008900000014` was lost before the archive fix (2026-10-15).
  No PITR across that gap. Every recovery manifest must carry this limitation.
- Windows-native pgBackRest was blocked by shared-memory cleanup issues; the ratified
  physical path is `pg_basebackup` + WAL archive. pgbackrest remains a capability that,
  when absent, is reported NOT_APPLICABLE, not faked.
- `archive_timeout=0`: idle databases do not produce WAL; "archive lag" is only
  meaningful when WAL is pending or activity exists.

## 7. Anti-patterns (things this doctrine forbids)

- A second recovery/backup engine that bypasses the ratified services.
- "Verified" markers set by configuration (test-mode bypasses) instead of execution.
- Destructive commands against a database whose name was not explicitly checked.
- Evidence files claiming success that no reproducible command sequence can regenerate.
- Reopening ratified workstreams because a new session "prefers" a different design.
