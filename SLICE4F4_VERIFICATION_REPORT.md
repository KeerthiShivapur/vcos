# Slice 4F.4 Verification Report — Ownership & Responsibility Intelligence

**Status: COMPLETE** — 12 slice backend tests, the FULL cross-slice
regression (818 tests), the live API acceptance script (38 checks), and the
Playwright E2E (declared → temporal → advisory-only → one UI surface) pass
with zero failures. Commit + tag `vcos-slice-4f4-complete` created.

## What this slice delivers

4F.4 answers **WHO is actually responsible for WHAT** as a canonical,
temporal, evidence-backed governed record — separate from "who knows this"
(4F.2/4F.3) and never a second copy of 4A task ownership, 4C delegation,
project fields or an HR system. Every ownership relationship is a window
(owner, object, responsibility type, scope, start/end, source, evidence,
confidence, backup, escalation) and every change closes the old window and
opens a new one — history is NEVER overwritten, so the Company Brain can
reconstruct "who owned Payments when the incident happened".

```
OwnershipRelationship  one window: (org, object_type, object_id,
                        responsibility_type, owner, scope, status,
                        declared_start/end, source, backup, escalation,
                        confidence, evidence_json); a unique PARTIAL index
                        enforces one active window per (object,type)
                        atomically — replay-safe under concurrent workers
OwnershipChange        append-only ledger: assigned / transferred /
                        backup_set / backup_removed / closed / expired /
                        reopened with actor, reason and origin event id
OwnershipSignal        advisory findings (gap / single_point / mismatch) —
                        analysis NEVER auto-fixes; only an explicit governed
                        write changes a responsibility
responsibility types   primary, operational, technical, business, knowledge,
                        decision, customer, backup, delegated (one primary
                        per object at a moment; others stack)
```

Deterministic laws under test:

```
temporal            a transfer closes the old window at the boundary and
                    opens the next at the same instant (half-open interval);
                    as_of(at) returns who owned it AT that moment
exact-once          reconcile replays write one window (same owner ->
                    refresh, changed owner -> spaced transfer window)
declared vs app     project.created/updated owns -> project primary through
                    the event bridge; terminal states close the window
observe-only        analysis NEVER re-assigns: inactive owners surface as
                    gap signals WITH read-only suggested candidates,
                    single-person dependency (N active responsibilities, no
                    backup) is a warning signal, declared-vs-observed
                    mismatch is a 0.83-confidence advisory only
governance          uninvited callers cannot read or write ownership
continuity          primary -> backup -> 4C delegation (read-only) ->
                    escalation scope; never invents a successor
bounded             every read is an indexed lookup; analyze() processes
                    <=200 active primaries per pass with next_offset
```

## Certified surfaces

```
/brain/ownership/objects/{type}/{id}            current world: primary +
                                                stacked types + open signals
/brain/ownership/objects/.../history            full change ledger per object
/brain/ownership/objects/.../as-of?at=...       temporal reconstruction
/brain/ownership/objects/.../continuity         primary -> backup ->
                                                delegation -> escalation
/brain/ownership/people/{id}/responsibilities   what a person owns (active,
                                                history, backup roles)
/brain/ownership/assign | transfer | backup | close   the ONLY governed
                                                writes (employees:manage)
/brain/ownership/analyze (GET / POST)           dry-run or one bounded
                                                advisory batch
/brain/ownership/signals + resolve              advisory list + governed ack
/brain/ownership/summary                        one-glance posture
/brain/ownership/coverage-check                 named bounded list gaps
brain NL intents                                responsibility / continuity /
                                                responsibility_history /
                                                responsibility_gaps ...
                                                ("who is responsible for
                                                X", "who takes over if the
                                                owner is unavailable",
                                                "who owned X", "ownership
                                                gap") answered from the
                                                canonical record
```

Governance: reads need `brain:read`; writes need `employees:manage`;
person visibility is resolved before data is assembled (hidden persons and
foreign tenants 404); scope-anchored callers only see records on their
visible scopes (downward-only, consistent with 4C).

## Implementation (diffs from vcos-slice-4f3-complete)

Backend (new + extended):

- `backend/app/models/ownership_intelligence.py` — the three canonical
  tables (`OwnershipRelationship`, `OwnershipChange`, `OwnershipSignal`),
  fixed responsibility-type and object-type vocabularies, provenance
  columns (`actor_id`, `event_name`, `source_event_id`), and the
  partial-unique active-window index (portable to SQLite and Postgres).
- `backend/app/intelligence/ownership_engine.py` — the engine: governed
  record/transfer/close/close_all_for_owner/backup writes, bounded indexed
  reads (current/history/as_of/responsibilities_of/continuity), bounded
  advisory analysis (gap with same-unit candidate suggestions, single-point
  dependency, declared-vs-observed mismatch from successful expertise
  evidence within a 90-day window), signal lifecycle, summary and
  coverage-check; `_graph_owns` mirrors active ownership/backup into the
  Company Graph guarded by a savepoint (`owns`, `backup_for` edges).
- `backend/app/events/handlers.py` — change-driven bridge: project
  created/updated/terminal events reconcile the canonical primary; explicit
  offboarding (`employee.offboarded`) and departure/status transitions
  close the person's windows (bounded) — declarations only, never invented.
- `backend/app/events/event_models.py` — `ownership.*` event catalog
  (assigned/transferred/closed/expired/backup_set/backup_removed/reopened/
  gap_detected/single_point_detected/mismatch_detected/signal_resolved/
  coverage_checked) and graph-edge mirror entries.
- `backend/app/events/event_bus.py` + `backend/app/api/v1/intelligence.py`
  — the on-demand drain endpoint is now scoped to the requesting
  organization (a tenant drain never touches another tenant's queue; the
  standalone worker keeps draining globally). This also fixed two phase-9
  tests that broadly drained the whole platform from within a single org.
- `backend/app/db/database.py` — Postgres migration list extended with the
  partial unique index.
- `backend/app/api/v1/brain.py` — the `/brain/ownership/*` surface and the
  governed write endpoints.
- `backend/app/knowledge/intelligence_engine.py` — four new intents
  (`responsibility`, `continuity`, `responsibility_history`,
  `responsibility_gaps`) + bounded object resolution (project/customer/
  partner/budget/unit by name overlap) answered from the canonical record;
  "who owns X" with no knowledge-topic match falls through to the
  responsibility record instead of a dead end.
- `backend/tests/test_4f4_ownership.py` — 12 tests.
- `scripts/accept_slice4f4.py` — 38 live acceptance checks.

Frontend (new):

- `frontend/lib/api.ts` — Slice 4F.4 block: types
  (`OwnershipRelationshipRow`, `OwnershipObjectView`, `OwnershipChangeEvent`,
  `OwnershipHistoryResponse`, `OwnershipAsOfResponse`,
  `OwnershipContinuityResponse`, `PersonResponsibilitiesResponse`,
  `OwnershipSignalRow`, `OwnershipSummary`, `OwnershipAnalysisSummary`) and
  functions for every surface above.
- `frontend/app/(app)/ownership/page.tsx` — the ownership posture page:
  stat cards (active responsibilities, open signals, gaps, mismatches),
  advisory analysis card ("preview advisory" dry-run + "run bounded batch"
  with honest "responsibilities never changed" copy), and the open-signals
  list with Acknowledge (governed, `employees:manage`).
- `frontend/components/people/ResponsibilitiesPanel.tsx` — per-person card:
  active responsibilities with type/backup badges, "since" dates, backup
  role line, and expandable past responsibilities.
- `frontend/app/(app)/people/[id]/page.tsx` — Responsibilities card wired
  into every profile.
- `frontend/e2e/slice4f4-ownership.spec.ts` — Playwright E2E.

## Design decisions locked by tests

- **Ownership ≠ expertise.** The canonical record is separate from skill
  cells; an expert is not automatically an owner in any direction.
- **History is never destroyed.** Transfer closes the old window and opens
  the next at the exact boundary; `as_of` before the first window returns
  nobody, after the transfer returns the new owner, and the change ledger
  keeps the full "assigned → transferred" chain.
- **Exact-once under replay.** The partial-unique active-window index makes
  concurrent event replays converge: same owner refreshes the window,
  different owner creates one spaced transfer window, never duplicates.
- **Analysis is advisory, period.** Gap signals hold read-only suggested
  candidates; mismatch signals say "ownership was NOT changed"; the suite
  asserts the owner is untouched after an analyze pass.
- **Offboarding closes, never reassigns.** `employee.offboarded` (and
  departure status transitions) close the person's windows for gap analysis
  — hiring a replacement is a human, governed write.
- **Single-person dependency is derived, not guessed.** An owner with >=3
  active responsibilities and no backup on this one is flagged (warning);
  the surface explains the reason and never fixes it.
- **Continuity is real.** primary → explicit backup → governed 4C
  delegation read (active grants at the scope) → escalation scope; no
  invented successors.
- **Scalability.** Reads are indexed lookups; analyze is bounded (<=200 per
  pass, `next_offset`); event bridges touch one object; no full rescan at
  any level — 5-person startup and 50,000-person enterprise use the same
  canonical architecture.
- **One architecture across sizes.** No company-size-specific code path,
  no tenant leakage (drain scoping + partial unique index + foreign-tenant
  404s all tested).

## Verification

Backend unit tests:

```
12 passed  (tests/test_4f4_ownership.py)
```

Full cross-slice regression (the complete backend suite, hermetic SQLite):

```
818 passed in 2311.18s (0:38:31)
```

This also re-locks the two phase-9 tests that had failed in an earlier
pre-fix broad-drain run (`test_event_handlers_update_expertise_and_graph`,
`test_engines_emit_background_audit_events`) — they pass now that the
on-demand drain is org-scoped.

Live acceptance (`scripts/accept_slice4f4.py` against the restarted backend
on :8999, exit 0):

```
38/38 checks passed — register/login, 4 hires, 5 projects with declared
owners, assign x5, backup set, current object read (primary + backup),
history retains assignment, transfer payments -> bob, backup re-declared,
current owner is bob, as-of before tenure = nobody, as-of now = bob,
continuity (primary + backup), person responsibilities (3 for bob), archive
dee, advisory dry-run read-only, bounded analyze batch (scanned=5 gap=1
single_point=2 mismatch=0), analysis did not mutate ownership, open signals
listed, gap signal critical + honest, signal resolve, ownership summary,
coverage check, NL responsibility intent, NL continuity intent
```

Playwright E2E (`frontend/e2e/slice4f4-ownership.spec.ts`):

```
1 passed (35.4s) — full governed trail through the live UI: declared
ownership via assign, backup, transfer with history preserved, as-of
reconstruction, archive arc, advisory analysis (1 gap + 2 single-point, 0
mismatch), signal severity/details, resolve + honest re-surface, coverage
check, per-person Responsibilities panel (bob's 3, cy's backup line), the
ownership posture page (stats, preview dry-run, bounded batch, acknowledge
-> counts drop), NL responsibility and continuity intents
```

Frontend static check: `npx tsc --noEmit` clean (repo gate: tsc; ESLint is
not configured).

## Universal Company OS moat test

- **5-person startup:** founder asks "who owns everything important?" —
  assign 5 windows, one screen, no enterprise configuration. ✓
- **50,000-person enterprise:** the same canonical tables, scoped reads,
  bounded batches, org-scoped drain and governance visibility answer "who
  owns this responsibility within this business unit / scope" with the SAME
  architecture. ✓
- **Connected, not isolated:** ownership reads 4C delegations (read-only),
  mirrors into the Company Graph as `owns`/`backup_for` edges, consumes
  4F.3 evidence for observed-mismatch analysis, feeds 4D knowledge queries
  and falls through into Company Brain intents — a competitor cannot copy
  this as a standalone "owner dropdown". ✓

## Post-acceptance state

- The running backend on :8999 is the verified 4F.4 code.
- Commit + tag `vcos-slice-4f4-complete` created.
- **STOP**: next slice is 4F.5 Collaboration Intelligence per the locked
  roadmap.