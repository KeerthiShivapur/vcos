# Slice 4E.5 Verification Report — Knowledge Intelligence Operating Layer

**Status: COMPLETE** — all automated tests, the full regression suite, the live
API acceptance script, the Playwright E2E, and the production frontend build
pass. Commit + tag at the end of this slice.

## What this slice delivers

4E.4 turned evidence into intelligence; 4E.5 turns intelligence into
OPERATIONS. The Company Brain now has a governed Knowledge Workspace where the
company observes what its knowledge MEANS and commands it — recommendations are
reviewed, accepted, converted into real governed tasks, executed and verified;
insights are acknowledged and resolved with audit trails; nothing is ever
deleted, nothing is ever invented, and the materializer never overrides a
user-steered row.

```
insights (4E.4: what the knowledge MEANS) + claims + topics
  -> action_engine (ONE singleton — the 4E.5 operating layer)
     brief             what changed, emerged, needs a decision, is affected —
                        plus the three things that need attention first (4.5.1)
     insights          12 kinds, exact-once, evidence-lineaged; detail carries
                        the full lineage + audit; acknowledge/resolve are
                        audited, never destructive (4.5.2)
     temporal          state-at-a-month + the supersession chain (what was
                        true, what replaced it — old versions never erased) (4.5.3)
     propagation       multi-hop impact chains through the graph (4.5.4)
     coverage          per business area: authoritative + fresh share, and why
                        weak areas are weak (4.5.7)
     health-center     0-100 score from seven explainable bars + drill-down
                        counts (contradictions, critical gaps, unverified,
                        stale, orphan) (4.5.7)
     recommendation    review -> accept -> convert (governed task or decision)
       lifecycle         -> execute -> verify; every transition explicit and
                        audited; convert lands a real task with a `[Knowledge]`
                        title; verify requires a note (4.5.6)
     query             12 intents: affected / changes / impact / gaps /
                        contradictions / ownership / health / worry / decide /
                        next / recommendations / missing / confident /
                        stakeholders / provenance / discovery / temporal (4.5.8)
```

Every surface resolves caller access FIRST and returns only evidence the caller
may see — a project-scoped reader's insights and impact are built only from
visible evidence, and a topic with no visible evidence is 404 for them.

## Implementation (diffs from 3c474af)

### `backend/app/knowledge/action_engine.py` (new — the 4E.5 operating layer)
- `materialize()`: universal insights (12 kinds: change, risk, gap,
  contradiction, decision_required, impact, opportunity, trend, stale,
  undocumented_process, cross_functional, verification_required), each keyed by
  a stable fingerprint with evidence lineage (`claim_ids`, `lineage.claims`),
  priority scoring, and auto-resolution when a condition clears
- `insights()` / `insight_detail()`: kind/status/severity filters; the detail
  carries the full evidence lineage (claims with source/authority/valid_from)
  plus the audit trail (`created` → `acknowledged` → `resolved`)
- `acknowledge()` / `resolve()`: audited, non-destructive user actions
  (`brain:manage`); rows are never deleted
- `brief()`: counts (significant_changes, emerging_risks, major_knowledge_gaps,
  decisions_potentially_affected, projects_impacted, customer_changes,
  strategic_signals) + the top-3 attention list
- `health_center()`: 0-100 score, seven explainable bars with per-bar `detail`,
  `drill_down` counts and `why_weak` itemization
- `coverage()`: per business area authoritative/fresh shares + `weak_reasons`
- `evolution_trace()`: the supersession chain with `supersedes`/`replaced_by`
  links; `state_at()`: the understanding valid in a chosen month
- `propagation()`: bounded multi-hop chains (entity_type/entity_id/title/
  relation/via/depth)
- `recommendation_lifecycle()`: the governed flow
  `detected→reviewed→accepted→converted→executed→verified` with the
  materializer never overwriting user-steered rows; `convert` creates a task or
  decision through the existing governed operating services; `verify` requires
  a note; every transition is appended to the lifecycle audit
- `recommendations()` (extended in `intelligence_engine.py`): 4E.5 kinds
  (conflict, stale_critical, gap, undocumented_process, cross_functional)
  persisted exact-once by (kind, fingerprint)

### `backend/app/knowledge/intelligence_engine.py`
- `changes()`: insight events joined into the per-topic change feed
- `query()`: intent router extended with the 4E.5 operating intents (affected /
  worry / decide / next / missing / confident / stakeholders / provenance) and
  the temporal route (`state at <month>` → honest state-at answer, or "No
  understanding recorded by <date>")

### `backend/app/knowledge/synthesis_engine.py` — fix locked by live checks
- `_detect_contradictions()`: a single claim can no longer pair with itself.
  The convert-created `[Knowledge]` task quotes both budget values in one
  statement; that self-referential claim was being reported as a contradiction
  of itself (`pair_ids: [X, X]`). A contradiction now requires two distinct
  claims (`len({claim.id ...}) < 2 → skip`).

### `backend/app/models/knowledge.py` + `backend/app/db/database.py`
- `KnowledgeIntelInsight` / `KnowledgeIntelInsightEvent` (tables
  `knowledge_intel_insights` / `knowledge_intel_insight_events`):
  fingerprint-unique, status + audit columns; legacy Slice 4
  `KnowledgeInsight` is untouched

### `backend/app/api/v1/brain.py` (16 new governed endpoints)
`GET /knowledge/insights`, `GET /knowledge/insights/{id}`,
`POST /knowledge/insights/{id}/acknowledge`, `POST /knowledge/insights/{id}/resolve`,
`GET /knowledge/topics/{topic}/evolution`, `GET /knowledge/topics/{topic}/propagation`,
`GET /knowledge/coverage`, `GET /knowledge/health-center`, `GET /knowledge/brief`,
`POST /knowledge/recommendations/{id}/lifecycle` (+ the 4E.5 query intents on
`POST /knowledge/query`). Read surfaces are `brain:read`; the command surfaces
are `brain:manage`.

### `frontend/` — the Knowledge Workspace
- `frontend/app/(app)/knowledge/workspace/`: six routes — Overview + Ask,
  Changes·Insights·Gaps (insight detail drawer + acknowledge), Impact Analysis
  (topic explorer: ownership/propagation/impact/evolution), Command Center
  (recommendation lifecycle with convert→task select and per-row audit trail),
  Evolution Timeline (supersession chain + state-at-month picker), Health Center
  (score, seven bars, coverage)
- `frontend/components/knowledge/WorkspaceNav.tsx`: sub-navigation
- `frontend/lib/api.ts` + `frontend/types/index.ts`: 4E.5 client functions and
  types (the Slice-4 `KnowledgeRecommendation` name is preserved; the new type
  is `KnowledgeIntelRecommendation`)
- `frontend/lib/knowledge-utils.ts`: shared tone/label helpers

## Design decisions locked by tests

| Decision | Rationale |
|---|---|
| insights are fingerprint-keyed exact-once rows | replaying materialization refreshes, never duplicates; the schema enforces it |
| insight lifecycle = audited, non-destructive | `acknowledged`/`resolved` rows are queryable forever; nothing is deleted |
| recommendation lifecycle = explicit user actions only | the materializer's write path stops at `detected`/`candidate`; a user-steered row is never overwritten |
| convert goes through the governed operating layers | the recommendation becomes a real task (`[Knowledge] …`, project-scoped) or decision — the knowledge layer recommends, humans execute |
| verify requires a note | a verification without a reason is not verification |
| contradiction requires two distinct claims | one self-referential statement (e.g. a task quoting both sides) cannot contradict itself — fixes `pair_ids: [X, X]` |
| temporal = honest state-at | asking about a month before the topic existed answers "No understanding recorded by <date>", never an invention |
| access resolved before any assembly | scoped readers see only visible evidence; hidden topics 404; rival tenants see zeros |
| bounded everywhere | every pass and response list carries a fixed cap |

## Verification

### 1. Unit/integration tests — 14/14 green
`backend/tests/test_4e5_knowledge_operations.py`:
- materialize universal insights exact-once (replay never duplicates)
- decision_required derives from the contradiction and auto-resolves when the
  condition clears
- acknowledge/resolve lifecycle is audited (created → acknowledged → resolved)
- temporal state-at + evolution chain (old versions retained, never erased)
- propagation reaches multi-hop families
- coverage map reports nine business areas
- health center scores and drills down
- brief reports counts and attention
- recommendation full lifecycle to a verified task
- reject path and lifecycle guards (invalid transitions 400)
- scoped reader sees only visible insights
- operating layer never crosses tenants
- universal query routes the new intents
- temporal query route

### 2. Full backend regression — 703 passed (~27 min)
689 prior + 14 slice 4E.5 — zero regressions.

### 3. Live API acceptance — 29/29 green
`backend/scripts/accept_slice4e5.py` against localhost:8999 (Postgres backend):
the brief reports the operating state; the contradiction surfaces as a
decision_required insight whose detail carries the evidence lineage and audit;
acknowledge and resolve are audited and non-destructive; the equal-authority
conflict is a live gap with both values; change intelligence reports the
evolution with insight events; state/evolution/propagation/impact/ownership
resolve for the topic; the health center scores and drills down; coverage
explains weak areas; the recommendation advances review→accept→convert→
execute→verify landing a real `[Knowledge]` governed task and the materializer
never overrides the steered row; the universal query routes every operating
intent deterministically; temporal queries answer honestly; decision queries
surface the decision_required insight; affected queries trace propagation; a
project-scoped reader never leaks unscoped conflict evidence and the hidden
topic is 404; a rival tenant sees nothing.

### 4. Playwright E2E — green
`frontend/e2e/slice4e5-knowledge-workspace.spec.ts` against the live stack
(frontend :3000, backend :8999): seeds the budget conflict end-to-end, verifies
the API contract of the 4E.5 surfaces, then walks the workspace UI — overview
brief + health score, changes/insights with detail drawer and acknowledge,
impact analysis topic explorer, evolution timeline, the full command-center
lifecycle to "No active recommendations" with the verified notice, and the
converted governed task lookup.

### 5. Frontend build — green
`npm run build` passes; all six workspace routes are built.

## Moat directives honored
- Deterministic first: the operating layer is a pure function of persisted
  claims — no LLM, no randomness, no invented statements
- One internal language: insights and recommendations persist only as
  fingerprint-keyed rows over the canonical claim model
- Exact-once: schema-enforced idempotency; resolved rows and superseded claims
  are never deleted
- Governance before assembly: access resolved before any read; command
  surfaces require `brain:manage`
- No full-org scans: every pass is hard-capped and change-driven
- Bounded everywhere: every response list carries a fixed cap

## Files
- `backend/app/knowledge/action_engine.py` (new — the 4E.5 operating layer)
- `backend/app/knowledge/intelligence_engine.py` (changes/query intents)
- `backend/app/knowledge/synthesis_engine.py` (contradiction self-pair guard)
- `backend/app/models/knowledge.py` + `backend/app/db/database.py`
  (KnowledgeIntelInsight/Event)
- `backend/app/api/v1/brain.py` (16 new governed endpoints)
- `backend/tests/test_4e5_knowledge_operations.py` (14 tests)
- `backend/scripts/accept_slice4e5.py` (live acceptance, 29 checks)
- `frontend/app/(app)/knowledge/workspace/` (6 routes)
- `frontend/components/knowledge/WorkspaceNav.tsx`
- `frontend/lib/api.ts`, `frontend/lib/knowledge-utils.ts`, `frontend/types/index.ts`
- `frontend/e2e/slice4e5-knowledge-workspace.spec.ts`
