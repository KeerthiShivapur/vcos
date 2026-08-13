# Slice 4E.3 Verification Report — Universal Knowledge Understanding & Synthesis

**Status: COMPLETE** — all automated tests, the full regression suite, and the live
API acceptance script pass. Commit + tag at the end of this slice.

## What this slice delivers

4E.2 funnels every meaningful piece of activity into the canonical model; 4E.3
connects those claims. Claims from different families that speak about the same
topic are synthesized into ONE topic-anchored understanding claim — deterministic,
governed and evidence-backed — with a full relationship graph.

```
activity events -> KnowledgeSource + KnowledgeClaim (4E.2)
  -> handle_universal_knowledge_ingest (same transaction, after ingest succeeds)
  -> synthesis_engine.synthesize_for_source -> topic candidates from the source
  -> get_or_create_topic -> synthesize_topic
     - bounded evidence selection (40 claims, authority x freshness x mention)
     - facet extraction + contradiction detection (authority, then valid_from)
     - deterministic statement, confidence, risk
     - KnowledgeClaim (claim_type="synthesis", predicate="synthesizes")
       + KnowledgeEvidence rows + KnowledgeRelation edges ("concerns"/"relates_to")
     - supersession on change; last_seen refresh on no-op (exact-once)
```

One internal language holds: an "understanding" IS a `KnowledgeClaim` — nothing is
stored in a parallel model. Replays never re-run handlers, so knowledge is never
duplicated.

## Implementation (diffs from ff040b2)

### `backend/app/models/knowledge.py`
- `KnowledgeClaim` gains the 4E.3 relationship-graph columns: `topic_id` (FK
  `knowledge_topics.id`, SET NULL, indexed), `supporting_claim_ids_json`,
  `contradicting_claim_ids_json`, `related_entities_json` (Text), `last_seen`
  (DateTime, indexed — a refresh with unchanged evidence is never new knowledge).

### `backend/app/db/database.py`
- `_BOOTSTRAP_POSTGRES` extended with `ALTER TABLE knowledge_claims ADD COLUMN IF
  NOT EXISTS` for the five new columns + `ix_knowledge_claims_topic` +
  `ix_knowledge_claims_last_seen` (tests use sqlite `create_all`; live Postgres is
  covered by the bootstrap).

### `backend/app/knowledge/synthesis_engine.py` (new)
- `SynthesisEngine` — deterministic substrate, no LLM:
  - topic derivation from a source: provenance category + keywords + first
    meaningful title token (≥4 chars, stopword-filtered), max 3 topics/source
  - `_collect_evidence`: bounded candidates (newest 160 claims) → visible-filtered
    → relevance = authority_norm × (0.4 + 0.6×freshness) × mention → top 40
  - facet extractors: currency (₹/rs/INR/$/€/£ + lakh/lac/cr/crore/k/m/b, values
    normalized to base units so "5 lakh" vs "0.5 cr" are comparable), percent,
    durations, month-day dates, ISO dates, quantities
  - `_detect_contradictions`: same facet, different value → conflict; winner by
    authority, then valid_from; loser recorded with its resolution
  - `_build_statement`: state phrase (stable / active concern / escalating /
    contested) + latest decision + top pattern + resolved facets + evidence
    snapshot (the statement quotes evidence, so content change always drives
    supersession) + active concerns; risk low/medium/high (≥3 patterns or ≥3
    problems → high)
  - `_confidence = 0.35×auth_norm + 0.25×freshness + 0.25×log2(1+n)/3 + 0.15×agreement`
  - persistence: new claim `status` = `authoritative` (authority ≥ 5) else
    `supported`; supersedes the previous understanding (valid_to + superseded_by);
    unchanged statement+confidence → `last_seen` refresh only
  - `_enrich_graph`: source→topic `concerns` edges + pairwise `relates_to` edges,
    idempotent under the unique edge constraint (dialect-aware
    `on_conflict_do_nothing` for postgres/sqlite), max 12 edges
  - `synthesize_for_source`: the event-driven entry point (topics derived from the
    ingested source, synthesized in the same transaction); `user=None` resolves to
    a system-wide write access — reads stay governed per caller
  - governed read paths: `topic_state`, `current_state` (snapshot + freshness
    label), `timeline` (evidence + understanding evolution), `contradictions`,
    `evidence_answer` (statement + exact citations), `claim_detail` (full
    relationship graph); every read resolves caller access FIRST and a topic with
    no visible evidence is 404

### `backend/app/events/handlers.py`
- `handle_universal_knowledge_ingest`: after a successful `ingest_event`, calls
  `synthesis_engine.synthesize_for_source` inside the same transaction — knowledge
  stays live without a second job queue.

### `backend/app/api/v1/brain.py` (all `brain:read` except synthesize =
`brain:manage`)
- `GET /brain/knowledge/topics/{topic_name}/state`
- `GET /brain/knowledge/topics/{topic_name}/current-state` (knowledge snapshot)
- `GET /brain/knowledge/topics/{topic_name}/timeline`
- `GET /brain/knowledge/topics/{topic_name}/contradictions`
- `GET /brain/knowledge/topics/{topic_name}/evidence?question=...` (evidence-backed
  answer)
- `POST /brain/knowledge/topics/{topic_name}/synthesize` (idempotent recovery
  trigger)
- `GET /brain/knowledge/claims/{claim_id}` (claim graph detail)

## Design decisions locked by tests

| Decision | Rationale |
|---|---|
| synthesis re-runs inside the ingest transaction | no second queue; replay-safe by construction (handlers never re-run) |
| understanding = KnowledgeClaim (claim_type `synthesis`) | one internal language; evolution = supersession, never a parallel model |
| statements quote the evidence snapshot | content change is what drives supersession and the timeline |
| contradiction loser always stays (roles `supporting`/`contradicted`) | the system can always explain *why* the loser lost |
| currency facets normalized to base value | "5 lakh" and "0.5 cr" are comparable — unit-mismatch can no longer hide a conflict |
| equal authority breaks on valid_from | recency resolves ties deterministically; authority always beats recency |
| topic with no visible evidence → 404 | governance constrains retrieval itself (same contract as 4E.1 sources) |
| `user=None` on writes = system-wide access | event-driven writes have no caller; every READ still gates per caller |
| all reads/answers bounded | evidence 40, timeline 60, problems/decisions 6, related 12, contradictions 12, edges 12, answers 12 citations |

## Verification

### 1. Unit/integration tests — 9/9 green
`backend/tests/test_4e3_knowledge_synthesis.py`:
- cross-family synthesis: message + task + memory about "migration" → one current
  understanding (authority = max = 3), cross-family supporting claims, 3 evidence
  rows, graph edges, single topic state via API
- contradiction: "5 lakh" vs "10 lakh" → contested state, resolution
  "newer valid_from", loser visible as `contradicted` evidence
- authority resolution: team record (2) beats both chats (1) — "authority 2 > 1",
  winning facet stated in the understanding
- temporal reasoning: v1 (Friday) → v2 (Monday), v1 superseded with valid_to +
  superseded_by, timeline shows the evolution, claim detail links forward
- exact-once: repeated drains + manual `/synthesize` never duplicate
- governance: scoped reader sees only in-scope evidence; hidden topic 404s while
  the org-wide reader sees it
- evidence-backed answer: citations carry claim ids + excerpts, every cited claim
  resolves
- tenant isolation: rival tenant gets 404 on topic state and claim detail
- provenance: claim detail returns topic, authority label, supporting claims,
  related entities, evidence with source titles

### 2. Full backend regression — 676 passed (3483s)
667 baseline + 9 slice 4E.3 — zero regressions.

### 3. Live API acceptance — 20/20 green
`backend/scripts/accept_slice4e3.py` against localhost:8999 (Postgres backend):
live Postgres applied the new columns via `_BOOTSTRAP_POSTGRES` on startup; all 7
new routes registered. Story verified end-to-end: message + project task + memory
synthesize one "migration" understanding (authority 3, cross-family support),
contradicting budget values resolve ("newer valid_from" then "authority 2 > 1"),
evolution supersedes v1→v2, timeline shows the development, evidence answer cites a
resolvable chain, replay + manual re-synthesis are exact-once, scoped reader sees
only scoped evidence (hidden topic 404), rival tenant sees nothing, synthesis
claim statuses stay inside the claim vocabulary.

### 4. Prior slice still green
`backend/scripts/accept_slice4e2.py` — 17/17 against the same live stack.

## Moat directives honored
- Deterministic first: synthesis, contradiction, authority resolution, confidence
  and risk are pure functions of persisted evidence — no LLM in the substrate
- One internal language: an understanding IS a canonical claim; zero parallel models
- No second job queue: synthesis runs inside the existing ingest transaction
- Governance before assembly: access resolved before any read; hidden → 404
- No full-org scans: every read and write is hard-capped and change-driven

## Files
- `backend/app/knowledge/synthesis_engine.py` (new — the 4E.3 engine)
- `backend/app/models/knowledge.py` (KnowledgeClaim relationship columns)
- `backend/app/db/database.py` (Postgres bootstrap ALTERs + indexes)
- `backend/app/events/handlers.py` (synthesis trigger in the universal handler)
- `backend/app/api/v1/brain.py` (7 new governed endpoints)
- `backend/tests/test_4e3_knowledge_synthesis.py` (9 tests)
- `backend/scripts/accept_slice4e3.py` (live acceptance, 20 checks)