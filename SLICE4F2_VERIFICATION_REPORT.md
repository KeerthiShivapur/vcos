# Slice 4F.2 Verification Report — Universal Skills & Expertise Intelligence

**Status: COMPLETE** — all 20 slice tests, the full backend regression suite,
and the live API acceptance script (20 checks) pass with zero failures.
Backend-only slice per the roadmap decision (the People Intelligence UI is
introduced in the later 4F slices once the model is mature, and is ultimately
unified into the Universal Virtual Company OS workspace). Commit + tag at the
end of this slice.

## What this slice delivers

4F.2 is the expertise intelligence layer for the Universal Virtual Company OS:
ONE canonical skill taxonomy per tenant, declared skills that are associations
and NEVER expertise, an exact-once evidence pipeline (task/document/decision/
learning events) feeding deterministic dimensions → lifecycle → bounded
aggregates, governed ranked expert discovery, team/department/organization
capability maps, graph edges, and brain-question intents — all read from the
SAME canonical evidence pipeline already in the schema. No parallel system, no
AI-written expertise, no magic single score.

```
CanonicalSkill        tenant taxonomy (system_seed): name, category, parent
  |-> SkillAlias      aliases (postgres, pg, tf, ...); a colliding alias is
  |                    REFUSED and marked ambiguous on BOTH owners — never
  |                    silently merged; ambiguous aliases resolve to nothing
  |-> PersonSkill     the (person, skill) ASSOCIATION — declared rows keep
  |                    their level/provenance; activity rows advance last_seen
  |-> Expertise       one cell per (person x skill): score, confidence,
  |                    lifecycle, historical_peak (peak preserved on dormancy),
  |                    evidence_count/strong/medium/weak, factors_json lineage
ExpertiseEvidence     append-only, exact-once per (org, person, skill, event):
                      strength from the authority chain (task/document =
                      strong; decision = medium; mention = weak), tokens bound
                      by MAX_EXTRACT, source lineage (source_type/id/title),
                      natural keys make replay/retries idempotent
CapabilityAggregate   bounded per (org, scope) indexes of cell stats
graph edges           has_skill / expert_in: (employee) --("employee")-> skill
```

Decision rules (deterministic, documented):

```
dimensions:  depth    = clamp(weighted/STRONG_UNIT_WEIGHT)     (strong 1.0,
             breadth  = source types/4                          medium 0.55,
             recency  = 1 - days_since/730                      weak 0.20)
             frequency= recent(90d) count/6, consistency= span/540
             authority= strong_weight/total_weight
confidence = 0.30*authority + 0.25*sufficiency + 0.20*recency
           + 0.15*consistency + 0.10*strong_share         (capped at 0.97)
score      = 100*(0.45*depth + 0.20*breadth + 0.15*recency
                  + 0.10*frequency + 0.10*consistency)*(0.7 + 0.3*authority)
lifecycle  = most restrictive rule satisfied (first match):
             authoritative (80.0, 8 ev, 6 strong, conf 0.75)
             strong        (60.0, 5 ev, 3 strong,   conf 0.60)
             established   (35.0, 3 ev, 3 credible, conf 0.00)
             emerging      (12.0, 2 ev)
             weak-only cells (no strong/medium) are hard-capped at emerging;
             inactivity > DORMANT_DAYS (270) -> dormant with the peak kept
```

Certified surfaces:

```
/brain/expertise/skills            canonical taxonomy (aliases, parents,
                                   q-filter exact-first)
/brain/expertise/search            governed ranked experts: sorted by score
                                   desc, evidence counts, team/department/
                                   business_unit scoping, limit bounded 1..50
/brain/expertise/skills/{id}       skill detail + its strongest experts
/brain/expertise/teams|departments/{id}  capability maps for that scope
/brain/expertise/organization      org-wide capability map
/brain/people/{id}/skills          declared skill associations (level 1..5,
                                   clamped; never expertise)
/brain/people/{id}/expertise       evidence-derived expertise per skill
/brain/people/{id}/expertise/{skill_id}/evidence   auditable lineage
brain intents                      "who knows X" -> ranked experts,
                                   "what does X know" -> person expertise,
                                   "where does X expertise live" -> org map,
                                   unknown skills answer honestly (no_skill)
events                             task.completed (strong), document.created
                                   (strong, author from the entity row),
                                   decision.made (medium), meeting.ended
                                   (weak) -> evidence + mirrors
```

Governance is built into every surface: reads need `brain:read`, writes need
`employees:manage` (no new permissions minted); access is resolved before any
data is assembled; scoped readers see only their scope AND only aggregates
whose whole scope they can see (`/expertise/organization` and sibling-team maps
404 for them); hidden persons read as 404 on every surface; tenants never
leak into each other.

## Implementation (diffs from vcos-slice-4f1-complete)

Backend (new + extended):

- `backend/app/models/skills_intelligence.py` — `CanonicalSkill`,
  `SkillAlias`, `PersonSkill`, `Expertise` (state, index
  `ix_expertise_state_org_score`), `ExpertiseEvidence`,
  `CapabilityAggregate`; tenant-scoped with unique natural keys.
- `backend/app/people/skill_engine.py` — 28-entry system seed taxonomy,
  two-pass `ensure_taxonomy` (create+aliases first, then parent links),
  `_attach_alias` collision rule (refuse + mark ambiguous, never merge),
  `resolve_term`/`resolve_candidates` (exact terms shadow containment
  matches), `bump_person_skill`.
- `backend/app/intelligence/expertise_engine.py` — the canonical pipeline
  (`record_evidence`, `record_activity` with optional source lineage,
  `_evidence_for`, `_ingest`, `_recompute_cell`, `_dimensions`, `_lifecycle`,
  `_mirror_legacy` bridging the Phase-2 legacy `ExpertiseScore`/
  `ExpertiseHistory`/`Employee.expertise_score` surfaces so the operating
  layer stays coherent), tz-safe `_safe_diff_days` via `ensure_aware`.
- `backend/app/people/expertise_search.py` — governed ranked search,
  `resolve_for_query` (seeds the taxonomy defensively), `person_expertise`,
  `person_skill`.
- `backend/app/people/capability_engine.py` — bounded team/department/org
  capability indexes.
- `backend/app/events/handlers.py` — `_evolve_expertise` feeds the pipeline
  from task/document/decision/learning events with source lineage; live
  knowledge events (payload only `{entity_type, entity_id, title}`) resolve
  the author from the entity row itself.
- `backend/app/api/v1/brain.py` — the `/brain/expertise` + `/brain/people/...`
  surfaces (all gated, writes committed by the routes, unknown scopes 404).
- `backend/app/knowledge/intelligence_engine.py` — the `expertise` intent with
  deterministic routing (experts / person_expertise / person_skill /
  organization_map / no_skill), governance-scoped, placed after the `people`
  intent so "who owns X" stays knowledge ownership.
- `backend/tests/test_4f2_skills_expertise.py` — 20 tests.
- `backend/scripts/accept_slice4f2.py` — 20 live acceptance checks.

Frontend (new): none — backend-only slice (see roadmap decision above).

## Design decisions locked by tests

- **Skills are associations, never expertise.** Declared skills carry a level
  1..5 (clamped) and provenance; they can never create evidence. A regression
  is locked: an employee with a declared PyTorch skill who completes python
  tasks gets evidence ONLY on Python — the legacy declared-boost that
  appended declared skills to EVERY activity was removed.
- **Evidence is evidence.** Only authority-chain events write evidence; the
  natural key (org, person, skill, event_id) makes durable replay exact-once
  (the same queued event processed twice writes one row).
- **Exact-term resolution shadows containment.** "postgresql" resolves to
  PostgreSQL only (not SQL); confused matches are refused; ambiguous aliases
  resolve to nothing.
- **Deterministic lifecycle with honest gates.** Most-restrictive rule first;
  weak mentions alone cap at `emerging`; inactivity (270 days) moves a cell to
  `dormant` while `historical_peak` is preserved.
- **Bounded everywhere.** Extraction capped by MAX_EXTRACT, search limit
  clamped by the API (422 beyond bounds), aggregates indexed per scope —
  no unbounded scans on read paths.
- **Governance before data; no permission sprawl.** Reads `brain:read`,
  writes `employees:manage`; aggregates require whole-scope visibility;
  hidden people and siblings are 404, tenant access is 404.
- **Reads never mutate.** Read routes never fabricate evidence and never
  enqueue signals (locked by a test that drains to zero, sweeps every read
  surface, and re-drains to zero).
- **Timezone-safe math.** SQLite returns naive UTC, Postgres aware; every
  interval (dormancy, recency, span, 90-day frequency) goes through
  `_safe_diff_days` (and sorting keys) via `ensure_aware`.

## Verification

Backend unit tests:

```
20 passed  (backend/tests/test_4f2_skills_expertise.py)
```

Live acceptance (`backend/scripts/accept_slice4f2.py` against the restarted
running backend on :8999):

```
20 passed, 0 failed   (exit 0) — taxonomy seed/aliases/parents, alias
resolution, declared never expertise, invalid declarations (400 + clamp),
task/document evidence -> deterministic lifecycle, exact-once drain, sorted
ranked experts + bounded limits, team scoping, capability maps + unknown
scope 404, scoped-reader isolation across every surface, write permissions
(401/403/200), tenant isolation, brain questions (experts/person_expertise/
organization_map/no_skill), read paths never mutate
```

Full backend regression (all suites, `backend/tests`):

```
778 passed in 2902.58s (0:48:22)  — plus 2 fixed, see below
```

The full-suite run surfaced two Phase-2 tests in `tests/test_phase9.py`
(`test_event_handlers_update_expertise_and_graph`,
`test_engines_emit_background_audit_events`) that encoded the OLD
declared-skill boost: they completed a generic task ("Core deliverable") and
expected the DECLARED "Project Management" skill to mint expertise. Under the
4F.2 invariant (skills are associations; only activity text matched against
the canonical taxonomy feeds evidence) that expectation is wrong, so the tests
were aligned with the corrected semantics: the activity task now references a
taxonomized skill ("Python"), the declared association is created for the
same skill, and every original assertion is preserved (expertise history
after task completion, CEO on the leaderboard, task graph edges, the
`expertise.updated` background signal, `graph.updated`, `learning.recorded`).
Both tests are green against the current code, together with the full
`tests/test_phase9.py` file and `tests/test_4f2_skills_expertise.py`:

```
49 passed in 135.78s  (test_phase9.py + test_4f2_skills_expertise.py)
```

Total: 780 tests, zero failures against the verified code.

Frontend: out of scope for this slice (backend-only; see roadmap decision).

## Post-acceptance state

- The running backend on :8999 is the verified 4F.2 code (restarted to load
  the repaired pipeline fixes).
- Commit + tag `vcos-slice-4f2-complete` created.
- **STOP**: next slice is 4F.3 (People Intelligence surfaced through the
  Universal Workspace / workspace layers) per the roadmap decision.