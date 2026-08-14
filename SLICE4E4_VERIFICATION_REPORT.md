# Slice 4E.4 Verification Report — Knowledge Intelligence

**Status: COMPLETE** — all automated tests, the full regression suite, and the live
API acceptance script pass. Commit + tag at the end of this slice.

## What this slice delivers

4E.3 synthesized evidence into ONE topic-anchored understanding; 4E.4 turns that
foundation into intelligence. One canonical brain answers natural questions with
deterministic, governed, bounded intelligence — never invented, always traceable
to the claims it quotes.

```
understanding claims + sources + topics (4E.3)
  -> intelligence_engine (ONE singleton, pure functions of persisted claims)
     discovery        natural question -> ranked topics, cross-family evidence,
                       exact evidence chain, matching tokens (4.4.1)
     relationships    one entity -> typed edges + topic-peers that share its
                       topic without a direct edge (4.4.2)
     changes          the evolution of an understanding: old -> new, the old
                       version superseded, never deleted (4.4.3)
     impact           if this knowledge changes, what else changes: affected
                       entities by family + dependent knowledge that quotes
                       the facts (4.4.3)
     gaps             equal-authority contradictions surface as a gap with
                       both values, the losing side and the resolution rule
                       (4.4.4)
     confidence       recomputed composite equals recorded, every factor
                       explained (4.4.6)
     ownership        highest-authority source's provenance author; memory-only
                       topics say no owner exists (4.4.6)
     health           seven explainable bars + what drags the company down
                       (4.4.6)
     recommendations  persisted, evidence-backed judgments: fingerprint-keyed
                       exact-once; a condition that clears resolves the row
                       (4.4.7)
     query            ONE surface routes a natural question to the matching
                       intelligence and tags the intent (4.4.8)
```

Every surface resolves caller access FIRST, is hard-capped, and returns only
evidence the caller may see — org-wide reader vs project-scoped reader vs rival
tenant are three different brains over the same substrate.

## Implementation (diffs from f228aef)

### `backend/app/knowledge/intelligence_engine.py` (new — the 4E.4 engine)
- `discover()`: topic candidates derived from the question tokens; evidence
  match = token overlap with claim text + topic name/aliases, inflection-aware
  (`_stem_overlap`: ≥5-char prefix overlap matches "renewal" vs "renewals");
  answers ranked by match + authority + freshness × mention; each answer carries
  the statement, claim_id, families and the exact evidence chain (excerpts +
  matched_tokens + claim ids)
- `relationships()`: typed graph around an entity (message/memory/task edges,
  topic `concerns` edges); neighbors that share the entity's topics without a
  direct edge still surface through a `concerns` relation with
  `direction: "via_topic"` and the topic name
- `changes()`: per-topic evolution from the supersession chain — events sorted
  chronologically, the newest 6 kept; `from`/`to` render the old/new state
  (≤400 chars, ellipsis-marked when truncated) so the change itself stays
  readable; `supersedes_claim_id` chains every evolution
- `impact()`: affected entities by family (graph neighbors of the topic's
  subjects, capped); dependent knowledge = non-superseded claims that quote the
  topic's facts, kept when the entity is also topic evidence and tagged
  `in_topic_evidence`
- `gaps()`: contradiction facets with equal authority (or unresolved
  valid_from-only resolution) surface as gaps carrying both values, the pair's
  claim ids and the resolution rule; stale-critical and uncertainty kinds too
- `confidence()`: recomputes 0.35×authority + 0.25×freshness + 0.25×agreement +
  0.15×consistency (recorded composite) and explains every factor + detail
- `ownership()`: conclusion = provenance author of the highest-authority source
  (team_record/documented); a topic whose only evidence is memory has no author
  and says `resolved: false` honestly
- `health()`: seven bars (coverage, freshness, evidence_quality,
  contradiction_resolution, ownership, documentation, cross_team_consistency)
  plus `why_weak` details itemizing stale/low-confidence/unresolved topics
- `recommendations()`: four deterministic kinds (stale_critical, conflict,
  undocumented_process, cross_functional) — each keyed by a stable fingerprint,
  citing its claims, with computed confidence/risk; persisted rows move
  active -> resolved when the condition clears
- `query()`: one surface — intent router over keyword rules
  (changes/gaps/health/recommendations/contradictions/impact/ownership,
  default discovery); every answer wrapped with `question`, `intent`,
  `generated_at`

### `backend/app/models/knowledge.py`
- `KnowledgeRecommendation`: persisted recommendations, keyed by
  `UniqueConstraint(organization_id, kind, fingerprint)` — materialization is
  idempotent by construction; `resolved_at` marks cleared conditions (rows are
  never deleted).

### `backend/app/knowledge/intelligence_engine.py` — fixes locked by live checks
- `changes()` previously kept the OLDEST 6 events — the recent Friday→Monday
  evolution was invisible. Events are now sorted and the newest 6 kept.
- `from`/`to` were rendered at 220 chars — long evidence states were cut
  mid-word and the change text degenerated to identical strings. Raised to 400
  with an honest ellipsis so the evolution is readable.
- ownership/health read the author ONLY from provenance `author_id`
  (`source.created_by` does not exist — those reads were removed).
- topic names serialized through `_clean_topic_name` (keyword-derived names from
  4E.1 seeds arrive JSON-quoted, e.g. `"renewal"`; intelligence surfaces always
  present the clean name and the raw name stays in the substrate).

### `backend/app/api/v1/brain.py`
- `GET /brain/knowledge/discover?query=`
- `GET /brain/knowledge/entities/{entity_type}/{entity_id}/relations`
- `GET /brain/knowledge/changes?days=`
- `GET /brain/knowledge/topics/{topic_name}/impact`
- `GET /brain/knowledge/gaps`
- `GET /brain/knowledge/topics/{topic_name}/confidence`
- `GET /brain/knowledge/topics/{topic_name}/ownership`
- `GET /brain/knowledge/health`
- `GET /brain/knowledge/recommendations`
- `POST /brain/knowledge/query`
(all `brain:read`; scoped readers get exactly their scope, org-wide readers the
org, and non-visible topics 404)

## Design decisions locked by tests

| Decision | Rationale |
|---|---|
| intelligence = pure functions of persisted claims | no LLM in the substrate; identical inputs always produce identical intelligence |
| capabilities are capped and change-driven | no full-org scans: 100 topics / 400 claims per pass, 10 discovery answers, 20 change topics, 60 impact entities, 40 impact claims, 40 neighbors, 8 gaps per kind (30 total), 25 recommendations, 12 citations per answer |
| inflection-aware matching (≥5-char stem overlap) | "renewal" finds "renewals" without dictionary brittleness; determinism kept in the token algebra |
| topic peers surface via a `concerns` relation | memory that shares an entity's topic but has no direct edge still appears in the graph — the topic is the connective tissue |
| from/to render the superseded state at 400 chars with ellipsis | change intelligence must SHOW the change; truncation is marked, never silent |
| recommendations keyed by (kind, fingerprint) unique | replay never duplicates — exact-once enforced by the schema itself |
| cleared conditions resolve rows, never delete them | a recommendation's history is truth: the conflict that WAS open stays explainable |
| ownership reads provenance author only | there is no "created_by" on a source — the accountable author is the provenance's author, authority 2/3 (team_record/documented) |
| access is resolved before any intelligence is assembled | a scoped reader's discovery evidence is a subset of the org-wide evidence; a topic with no visible evidence is 404; a rival tenant sees zeros |
| one `query()` surface routes every intent | the Company Brain is one surface: question in, `question`/`intent`/`generated_at` + that intelligence's shape out |

## Verification

### 1. Unit/integration tests — 13/13 green
`backend/tests/test_4e4_knowledge_intelligence.py`:
- discovery: question-token match over topic name/aliases + statement tokens with
  inflection-aware stemming; exact evidence chain; unasked topics hidden;
  deterministic ranking
- relationship graph: typed edges resolve; memory surfaces via topic; relation
  cardinality bounds
- change intelligence: old -> new supersession chain; evolution only when the
  understanding actually changed (last_seen refreshes produce none)
- impact: affected entities by family; dependent claims that quote the facts;
  evidence traceable to claims
- gaps: equal-authority contradiction with both values and pair ids; authorities
  > chat (team record) never surface a false gap
- confidence: recompute == recorded; five explained factors with details
- ownership: resolved to team-record author; memory-only topic says unresolved
- health: seven bars; why_weak honest
- recommendations: exact-once under replay; conflict cites exactly the pair;
  condition clears -> resolved
- universal query: intent routing for all intents; discovery grounded in the
  synthesis claim
- governance: scoped discovery only visible evidence; hidden topic 404
- tenant isolation: rival tenant sees nothing on every surface

### 2. Full backend regression — 689 passed (~30 min)
676 prior + 13 slice 4E.4 — zero regressions.

### 3. Live API acceptance — 28/28 green
`backend/scripts/accept_slice4e4.py` against localhost:8999 (Postgres backend):
the 12-section story verified end-to-end: discovery of "why are enterprise
customers delaying renewals?" returns one cross-family answer with the exact
evidence chain; the graph around the migration task resolves typed edges and the
memory neighbor through the topic; the migration understanding's evolution is
reported old -> new — Friday supersedes the window confirmation, "next Monday"
supersedes Friday — with every step chained by `supersedes_claim_id`;
impact lists affected entities by family plus the dependent deployment task that
quotes the facts; the 5 lakh vs 10 lakh equal-authority conflict surfaces as a
gap with both values; confidence recomputes to the recorded value with every
factor explained; ownership resolves to the team-record author and a memory-only
topic says no owner exists; health reports seven explainable bars; recommendations
replay exact-once (identical ids) and the conflict recommendation resolves the
moment a team record settles the budget; the universal query routes every intent;
a project-scoped reader's discovery intelligence is built only from visible
evidence and the hidden stealth topic is 404; a rival tenant sees zeros
everywhere. (The stack runs with `APP_ENV=test` to keep the boot-time scheduler
swarm out of the dev DB pool; script polls for the async outcomes — deterministic
under worker races.)

## Moat directives honored
- Deterministic first: every intelligence is a pure function of persisted
  claims — no LLM in the substrate, no randomness, no invented statements
- One internal language: nothing new stored outside the canonical model except
  fingerprint-keyed recommendation rows; an understanding is still a claim
- Exact-once: recommendation materialization is schema-enforced idempotent;
  superseded claims and resolved recommendations are never deleted
- Governance before assembly: caller access resolved before any read; scoped
  evidence is a subset of org evidence; hidden topics 404; rival tenants see 0
- No full-org scans: every pass is hard-capped (topics 100, claims 400) and
  change-driven
- Bounded everywhere: every response list carries a fixed cap

## Files
- `backend/app/knowledge/intelligence_engine.py` (new — the 4E.4 engine)
- `backend/app/models/knowledge.py` (KnowledgeRecommendation, fingerprint-unique)
- `backend/app/api/v1/brain.py` (10 new governed endpoints)
- `backend/tests/test_4e4_knowledge_intelligence.py` (13 tests)
- `backend/scripts/accept_slice4e4.py` (live acceptance, 28 checks)