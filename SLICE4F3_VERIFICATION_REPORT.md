# Slice 4F.3 Verification Report — Expertise Evidence & Trust Intelligence

**Status: COMPLETE** — 26 slice backend tests, the cross-slice regression
(75 tests), the live API acceptance script (19 checks), and the Playwright
E2E (full governed trust trail through the profile UI) pass with zero
failures. Commit `9bb7a71` + tag `vcos-slice-4f3-complete` created.

## What this slice delivers

4F.3 answers **WHY** VCOS may trust an expertise claim. Every cell of
expertise now carries a governed, append-only evidence trail; trust is
derived from outcomes (success/failure/expiry), reckoned from independent
lineages and corroborating kinds, and contradictions are NEVER hidden. The
deterministic laws of 4F.2 are kept (evidence is evidence, exact-once,
bounded, governed), and the rule "failed or expired evidence must remain
visible and count against the claim" is locked by tests.

```
ExpertiseEvidence   append-only; every row carries provenance:
                    evidence_kind (work/decision/learning/certificate),
                    outcome (successful/failed/neutral), strength + weight,
                    valid_from/valid_to (expiry window), lineage_key
                    (source_type:source_id), origin_event_id (the exact
                    event that produced it), source lineage, topic_id,
                    event_id (exact-once natural key: replay writes one row)
Expertise           per-cell state extended with trust facets:
                    successful_count, failed_count, outcome_ratio,
                    distinct_lineages, corroborated_kinds, freshness
trust()             THE trust profile: successful vs failed counts per
                    kind, independent lineages, corroborated kinds,
                    freshness (active/recent/historical), contradictions
                    (negative + expired, listed with their outcomes —
                    never hidden, never zeroed), recent_evidence trail,
                    WHY/WHAT/HOW-much/HOW-recent/WHAT-corroborates/WHAT-
                    contradicts answers
```

Trust decision rules (deterministic, documented):

```
confidence  = 0.30*authority + 0.25*sufficiency + 0.20*recency
            + 0.15*consistency + 0.10*strong_share      (cap 0.97, locked)
lifecycle   = most restrictive rule satisfied (4F.2 rules) WITH failure
              gates: material failure share caps lifecycle and confidence
              (an operator with 6 failed / 24 total python actions cannot
              be authoritative), locked by tests at failed_count=6
outcome     = event's effective outcome; failed decisions and expired
              items deflate trust deterministically and stay visible
contradictions = negative outcome evidence + expired evidence, surfaced
              with outcome and expiry flags on the trust profile
kinds       = independent kinds corroborate (2+ distinct kinds required
              for corroboration); one kind alone never self-corroborates
freshness   = deterministic recency band copied into the cell state for
              read-side display
unknown     = events outside the expertise map stay WEAK-NEUTRAL work
              (no invented expertise), locked by test
```

Certified surfaces:

```
/brain/expertise/search                     expert search now carries trust
                                            facets (successful/failed
                                            counts, confidence, lifecycle)
/brain/people/{id}/expertise                evidence-derived expertise
/brain/people/{id}/expertise/{skill}/state  one cell's defensible state
/brain/people/{id}/expertise/{skill}/trust  the trust profile incl.
                                            contradictions (governed)
/brain/people/{id}/expertise/{skill}/evidence  auditable evidence lineage
/brain/expertise/evidence/{evidence_id}     governed drill-down: full
                                            provenance served only when the
                                            subject person is visible
canonical<->legacy skill bridge             trust/evidence routes resolve a
                                            Phase-2 (legacy) skill id to its
                                            canonical cell deterministically
brain intents                               "why does Py Dev know Python?"
                                            -> intent expertise_trust,
                                            kind trust_profile, answer cites
                                            lineage + person_id
ops/decision/goal events                    approval.rejected (-0.5 failed),
                                            goal.completed (+2.0
                                            successful, real lineage),
                                            deployment outcomes, backups,
                                            disaster recovery, workflow
                                            results -> evidence with real
                                            persons (never invented)
approvals API                               ApprovalCreate now honors
                                            requester_id so a rejection
                                            attributes failed-decision
                                            evidence to the requester
```

Governance is unchanged in spirit: every surface needs `brain:read`, person
visibility is resolved before data is assembled, hidden persons and foreign
tenants 404 on every route including the evidence drill-down.

## Implementation (diffs from vcos-slice-4f2-complete)

Backend (new + extended):

- `backend/app/models/skills_intelligence.py` — `ExpertiseEvidence` extended
  with `evidence_kind`, `outcome`, `valid_from`, `valid_to`, `lineage_key`,
  `origin_event_id` (indexed); the source-unique constraint
  `uq_expertise_evidence_source` is DROPPED (it collapsed one action's
  success/failure history) in favour of the event-key exact-once unique
  `(org, person, event_id, skill_id)`; `Expertise` gains the trust facet
  columns.
- `backend/app/db/database.py` — Postgres migration list extended
  (ADD COLUMN IF NOT EXISTS xN, new indexes, DROP CONSTRAINT; the model
  change is portable to SQLite used by tests).
- `backend/app/events/event_models.py` — `EXPERTISE_EVENTS` extended with
  the ops/decision/goal event names; `record_activity` no longer
  short-circuits those events to zero.
- `backend/app/events/handlers.py` — `_evolve_expertise` forwards real
  source lineage/outcomes/points; `handle_approval_rejected` writes a
  FAILED decision on the requester (a rejection is a contradiction);
  `handle_goal_completed` writes successful positive lineage
  `goal:{id}`; deployment/backup/disaster/workflow handlers feed their
  outcomes; employee resolution drops wrong candidates progressively via
  `people_engine.search`.
- `backend/app/intelligence/expertise_engine.py` — outcome/kind/validity on
  `_ingest`; `_dimensions` zero-row return extended with every key the cell
  recompute consumes (recency, consistency, authority, sufficiency,
  expiry counts); `trust()` building the full profile incl. contradictions
  and recent evidence; `lineage()`/`evidence()` for the governed lists and
  drill-down; `_mirror_legacy` now CREATES the missing legacy `Skill` row
  (an evidence-driven org may never have touched the Phase-2 surface), so
  profile pages always show the same experts the brain trusts; negative
  contribution = failed + expired contradictions; confidence hard-capped
  at 0.97.
- `backend/app/knowledge/intelligence_engine.py` — possessive NL parsing
  fixed: "Py's Python expertise" and "why does Py Dev know Python?" route
  to the `expertise_trust` intent (`knows?(?: about)?` marker, one skill
  word allowed between `'s` and the noun); trust-profile answers carry
  `person_id`; contradictions math reads expired flags.
- `backend/app/people/expertise_search.py` — trust facets in expert
  search results.
- `backend/app/api/v1/brain.py` — new state/trust/evidence routes;
  `_resolve_state_skill` bridges canonical and legacy skill ids
  deterministically (never guessed); evidence drill-down enforces person
  visibility.
- `backend/app/schemas/work.py` — `ApprovalCreate.requester_id` so the
  live API can attribute a rejected claim to its requester.
- `backend/tests/test_4f3_evidence_trust.py` — 25 tests; plus
  `backend/tests/test_4f3_legacy_bridge.py` — the legacy-id bridge and the
  mirror-creation contract.
- `scripts/accept_slice4f3.py` — 19 live acceptance checks.

Frontend (new):

- `frontend/lib/api.ts` — Slice 4F.3 block: types (`TrustContradiction`,
  `TrustProfile`, `EvidenceLine`, `ExpertiseEvidenceResponse`,
  `ExpertiseExpertEntry`, `ExpertiseSearchResponse`) and functions
  `brainExpertiseSearch`, `getPersonTrust`, `getPersonEvidence`,
  `getEvidenceItem`.
- `frontend/components/people/ExpertiseEvidencePanel.tsx` — the
  "Why we trust it" panel: lifecycle/confidence/freshness badges, outcome
  summary ("5 successful / 1 failed outcome(s) across 6 independent
  lineage(s) from 2 evidence kind(s)..."), failed-or-expired warning that
  stays visible, per-item evidence rows with kind/outcome/expired badges,
  and a drill-down card with lineage key, origin event and occurred date.
- `frontend/app/(app)/people/[id]/page.tsx` — panel wired under each
  expertise score row.
- `frontend/e2e/slice4f3-expertise-trust.spec.ts` — Playwright E2E.

## Design decisions locked by tests

- **Failed evidence is never hidden.** Six failed python actions cap the
  lifecycle (cannot be authoritative) and deflate confidence even though
  successes abound; `failed_count == 6` and `outcome_ratio == 0.25` are
  asserted, and the trust profile lists the contradictions with their
  outcomes.
- **Expired evidence still counts.** An expired item stays in the trust
  profile as a contradiction; removing the live-by outcome changes the
  score only after the expiry is recomputed into the cell.
- **One action, one lineage.** Every evidence row carries `lineage_key`
  (source_type:source_id) and `origin_event_id`; replay of the same event
  writes one row (event-key unique); the old source-unique constraint that
  silently erased a second outcome of the SAME source is gone.
- **Corroboration needs independence.** 10 identical declaration-style
  rows count as ONE lineage and never corroborate themselves; 4 genuinely
  independent kinds do add evidence and multiply corroborated kinds.
- **Derived cascades never double-count.** Authoritative edges, same-kind
  repeats and mirrors write evidence exactly once; `evidence_total` is
  deduplicated.
- **Unknown events stay weak-neutral.** A never-mapped event records
  neutral work — it can move a cell but never marks someone an expert.
- **The mirror creates, never guesses.** An evidence-driven org with no
  Phase-2 rows gets its legacy `Skill` row created from the canonical
  name, and the trust/evidence routes accept either the canonical or the
  legacy skill id deterministically.
- **Governance on every read.** Trust, evidence list AND the single-item
  drill-down all 404 for hidden persons/other tenants; suite asserts
  per-route isolation.
- **Reads never mutate.** Accepted via the same geometry as 4F.2: read
  surfaces never fabricate evidence.

## Verification

Backend unit tests:

```
26 passed  (tests/test_4f3_evidence_trust.py: 25 + tests/test_4f3_legacy_bridge.py: 1)
```

Cross-slice regression:

```
75 passed in 204.63s (0:03:24)
  tests/test_4f2_skills_expertise.py + tests/test_4f3_evidence_trust.py
  + tests/test_4f3_legacy_bridge.py + tests/test_phase9.py — no regressions
```

Live acceptance (`scripts/accept_slice4f3.py` against the restarted backend
on :8999, exit 0):

```
19/19 checks passed — register/login, employee, 5 python task completions,
approval created WITH requester, approval REJECTED, event worker drained,
expert search returns trust facets, 5+ successes, 1+ failure kept,
trust profile route (person resolved, 6 distinct lineages, contradiction
present, 2 corroborated kinds), evidence list route with work+decision
kinds, drill-down keeps provenance, NL "why does Py Dev know Python?"
-> expertise_trust/trust_profile, answer cites lineage
```

Playwright E2E (`frontend/e2e/slice4f3-expertise-trust.spec.ts`):

```
1 passed (6.2s) — full governed trail through the live profile UI: search
facets, trust contract, "Why we trust it" panel (lifecycle/confidence,
outcome summary, evidence rows incl. the rejected approval), the visible
"failed or expired item" warning, evidence drill-down, and the brain
why-trust question
```

Frontend static check: `npx tsc --noEmit` clean (ESLint is not configured
in this repo; `next lint` prompts for setup, so `tsc` is the gate used).

## Post-acceptance state

- The running backend on :8999 is the verified 4F.3 code (restarted to
  load the new routes, model changes and migration `DROP CONSTRAINT`).
- Commit `9bb7a71` + tag `vcos-slice-4f3-complete` created
  ("Slice 4f3 complete: expertise evidence & trust intelligence").
- **STOP**: next slice is 4F.4 per the roadmap decision.