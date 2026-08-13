# Slice 4E.2 Verification Report — Universal Knowledge Ingestion

**Status: COMPLETE** — all automated tests, the full regression suite, and the live
API acceptance script pass. Commit + tag at the end of this slice.

## What this slice delivers

Every meaningful company activity — conversation messages, task lifecycle events,
meetings, recorded memories, detected patterns, decisions — now flows through ONE
ingestion contract into the canonical knowledge model (4E.1). There is one internal
language: every source is a `KnowledgeSource` with claims + evidence, governed by
the 4E.1 lifecycle, authority and visibility model.

```
operating activity (events) -> handle_universal_knowledge_ingest
  -> canonical_engine.ingest_event -> per-family normalizer -> KnowledgeSource
  -> KnowledgeClaim + KnowledgeEvidence (temporal, supersession, exact-once)
```

## Implementation (diffs from e7552ba)

### `backend/app/knowledge/canonical_service.py`
- `ingest_event(db, *, event, payload)` — universal contract:
  - event → source family mapping (message/task/meeting/memory/pattern + decision path)
  - per-family `event_status` derivation: task.deleted→deleted, task.transitioned→payload
    status/to, task.blocked→blocked, task.completed→completed, task.unblocked→status
    or todo, else payload status; meeting.completed→completed, meeting.ended→ended,
    pattern→payload status
  - `source_id` from `{family}_id | entity_id | id`
  - ordering guard: an event older than the last ingested event is rejected
    (`stale_replay`) — out-of-order replays can never rewind history
  - exact-once: unchanged content refreshes freshness only, never a duplicate claim
- per-family normalizers `_normalize_message/_task/_meeting/_memory/_pattern`
  (`_NORMALIZERS` registry), each producing the one canonical shape
- noise filter `_message_meaningful`: signal word list or ≥60 characters (short
  operational chatter like "Cutover is 9pm." never becomes knowledge)
- per-family claim vocabulary: message `stated`, task `status`, meeting `occurred`,
  memory `remembers`, pattern `signals` — one canonical shape per family
- reconcile spans ALL families (typed items `entity_type/entity_id/lifecycle`), and
  recovers out-of-band edits (superseded_by pointing at the external edit's claim)

### `backend/app/events/handlers.py`
- `handle_universal_knowledge_ingest` subscribed to 16 event names:
  `messaging.message_sent`, `task.created/updated/transitioned/blocked/completed/
  unblocked/deleted`, `meeting.created/updated/started/ended/completed`,
  `memory.recorded`, `pattern.detected/updated/confirmed` — per-event exception
  isolation, one call into `canonical_engine.ingest_event`

## Design decisions locked by tests

| Decision | Rationale |
|---|---|
| task status prefers `event_status` | each lifecycle step lands its own temporal claim |
| meeting status prefers row status | `/complete` emits only `meeting.ended`; row `completed` must win |
| message claims are `candidate` (authority 1) | statements are opinion until corroborated |
| supersession is hop-chained | each older claim's `superseded_by` is the immediately-next claim (`valid_to` set); replay yields the exact chain |
| pattern authority 3 + `signals` claim w/ key+confidence | system-derived insight, high trust response |
| source lifecycle by authority | authority ≥ 3 → `validated`, below → `active` (a message is `active`/`sent`) |

## Verification

### 1. Unit/integration tests — 12/12 green
`backend/tests/test_4e2_universal_ingestion.py`:
message→canonical (+ noise rejection), task temporal claim chain (4 hop-linked
claims, current final), completed meeting, memory record, confirmed pattern
(authority 4 via `_AUTHORITY_FIXED_PATTERN`), exact-once under replay, stale-replay
ordering guard, reconcile across families + edit recovery, tenant isolation,
scoped-reader governance (anchored visible, unanchored hidden), registry families.

### 2. Full backend regression — 667 passed (2834s)
646 baseline + 9 slice 4E.1 + 12 slice 4E.2 — zero regressions.

### 3. Live API acceptance — 17/17 green
`backend/scripts/accept_slice4e2.py` against localhost:8999 (Postgres backend):
meaningful message → canonical source + candidate claim + primary evidence
(noise 404s), task lifecycle 4-claim hop chain (completed current), meeting
completion, decision naming chosen option, memory validated/active authority 3,
pattern: repeated project-scoped blocked tasks → pattern worker → candidate
`repeated_delay` → canonical pattern source (`signals`, supported, authority 3),
exact-once replay is a no-op, bounded typed reconcile, tenant isolation, scoped
reader sees anchored task but never unanchored message, registry families ⊆ known
families, vocabulary legality, uniform claim shape across all live families.

### 4. Prior slice still green
`backend/scripts/accept_slice4e1.py` — 14/14 (unchanged contract intact).

### 5. Live evidence (probe transcripts)
- message/task/meeting/memory/decision/pattern all landed on Postgres through the
  normal API + drain flow; pattern required a project+assignee anchor (rules key on
  project/employee by design — project-less tasks never match, so no pattern leaks)
- the older "missing task sources" observation was pre-4E.2 events processed by the
  previous server binary (matched by direct `ingest_event` replay = ok)

## Moat directives honored
- One internal language: five families normalized into one canonical shape
- No duplicate emission: event bus unchanged, single handler per event name
- No second model: pattern/memory workers untouched; 4E.2 only reads their outputs
- Governance constrains retrieval: `KnowledgeSource` scope via provenance
  `project_id`; scoped readers cannot see unanchored activity (404)
- No full-org rescans: reconcile is capped + idempotent; everything is change-driven

## Files
- `backend/app/knowledge/canonical_service.py` (universal engine + normalizers)
- `backend/app/events/handlers.py` (universal event subscriptions)
- `backend/tests/test_4e2_universal_ingestion.py` (12 tests)
- `backend/scripts/accept_slice4e2.py` (live acceptance, 17 checks)