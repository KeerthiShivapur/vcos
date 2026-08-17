# Slice 4F.7 Verification Report — People Decision Intelligence

**Status: COMPLETE** — 25 slice backend tests, the FULL cross-slice regression
(903 tests), the live API acceptance script (13 checks), and the Playwright
E2E (evidence-backed → explainable → human-governed → one governed UI
surface) pass with zero failures. Commit + tag `vcos-slice-4f7-complete`
created.

## What this slice delivers

4F.7 answers **WHO should own, staff or lead what** as a canonical,
evidence-derived, decision-intelligence surface — but it is decision
intelligence, never automatic employee management: the system recommends and
explains, a **human being decides**, and the recorded outcome becomes
evidence for the next evaluation (Decision → Outcome → Learning). Every
recommendation carries candidates with roles and trade-offs, honest negative
evidence ("why not"), bounded what-if simulation, confidence, and a full
provenance chain back to the 4F.1–4F.6 surfaces.

```
Decision                 one governed decision object per org: decision_type,
                         objective, requirements (canonical skills),
                         lifecycle (detected -> evaluated -> recommended ->
                         reviewed -> approved|rejected -> executed -> verified
                         -> outcome), risk_tier, context anchor, exact-once
                         via the event stream (project.started -> detected)
DecisionCandidate        the candidate set with roles (recommended /
                         alternative / excluded), decision-specific evidence
                         dimensions (skill match, availability, ownership,
                         collaboration, outcomes, expertise currency),
                         rationale, trade_offs and why_not — a person is
                         NEVER scored; excluded candidates are shown, never
                         hidden
DecisionEvidenceItem     the evidence lines behind each candidate claim
DecisionSimulation       bounded what-if runs (per-capability availability
                         delta, concentration, workload, ownership) with
                         verdicts, capped at 20 per decision
DecisionAudit            append-only governance trail of every transition
                         (who, when, from, to, note)
```

Deterministic laws under test:

```
no auto-management       nothing ever acts on the organization: no
                         assignments, no transfers, no promotions. The
                         platform recommends; a human decides; the recorded
                         outcome becomes evidence for the next evaluation
governance               risk_tier tiers: LOW/MEDIUM surface as
                         recommendations; HIGH-tier people decisions
                         (hiring, promotion, termination, compensation,
                         disciplinary) are REFUSED with the human-governance
                         message — by design
lifecycle                one deterministic state machine with allowed
                         transitions and refused transitions listing the
                         allowed moves; every transition appends an audit row
honest negatives         'why not X' answers with evidence-backed negatives
                         (e.g. less trusted evidence, concentration, missing
                         collaboration), never with a score
bounded what-if          simulations run within the decision context only
                         (capacity delta, concentration, workload,
                         ownership), never the 4P engine; the primary can
                         never be simulated against itself; 20-run cap
read-only brain          ask/why-not/what-if resolve with dry_run /
                         dry_what_if: NOTHING persists; only POST /decisions
                         persists
explainability           recommendation = label + confidence + rationale
                         naming trusted evidence counts and outcomes;
                         provenance chain reconstructed 4F.2 -> 4F.7
outcome-to-evidence      a recorded outcome is trusted evidence in the NEXT
                         evaluation of the same context (verified live)
scoped visibility        scoped callers: org-wide surfaces 404, writes 403,
                         project-anchored only, hidden decisions 404 before
                         any reasoning; tenant isolation holds
bounded                  every read is indexed and capped (20 simulations,
                         50 decision list, 6 person-resolution probes)
timezone-safe            all timestamp columns are DateTime(timezone=True)
                         (bare DateTime breaks asyncpg/Postgres)
```

## Certified surfaces

```
POST /brain/decisions                    create + reason immediately:
                                         candidates, evidence, provenance,
                                         confidence, lifecycle recommended;
                                         HIGH-tier refused
GET  /brain/decisions                    list (total + newest first) with
                                         context anchors and recommended
                                         person per decision
GET  /brain/decisions/{id}               full detail: candidates, evidence,
                                         simulations, audit trail,
                                         provenance, outcome
POST /brain/decisions/{id}/lifecycle     governed transition
                                         (review/approve/reject/execute/
                                         verify/reopen/evaluate/recommend);
                                         refused transitions list allowed
                                         moves
POST /brain/decisions/{id}/outcome       record successful/unsuccessful with
                                         note -> audit + next-evaluation
                                         evidence
POST /brain/decisions/{id}/what-if       bounded simulation for an
                                         alternative person (persisted,
                                         capped at 20)
POST /brain/knowledge/query              people_decision intents:
                                         recommendation, why_not,
                                         alternatives, what_if — routed
                                         FIRST in the intent rule block;
                                         person mentions resolved by
                                         people_engine search probes
```

## Implementation (diffs from vcos-slice-4f6-complete)

Backend (new + extended):

- `backend/app/models/people_decision.py` — the canonical tables
  (`Decision`, `DecisionCandidate`, `DecisionEvidenceItem`,
  `DecisionSimulation`, `DecisionAudit`), all timestamps
  `DateTime(timezone=True)` (the Postgres asyncpg fix), JSON-typed evidence
  and provenance columns.
- `backend/app/intelligence/people_decision_engine.py` — the engine:
  requirement → canonical-skill resolution (`CanonicalSkill.canonical_name`),
  candidate evaluation with decision-specific evidence dimensions (no
  employee scores), deterministic confidence/fit, the lifecycle state
  machine with allowed/refused transitions, append-only audit, bounded
  what-if (context deltas, primary excluded, 20-run cap), list/view with
  provenance reconstruction, and governance tier enforcement (HIGH refused).
  Fixes locked by tests: `_resolve_skills` uses `canonical_name`;
  `_people` uses `full_name or display_name or first_name` plus the `"id"`
  key; org context allowed without `context_id`; `_finalize_selection`
  passes `all_verdicts` so EXCLUDED candidates appear with role
  `excluded`; `list` returns `total`.
- `backend/app/knowledge/intelligence_engine.py` — the `people_decision`
  intent block FIRST in `_INTENT_RULES`; person-name token resolution via
  `people_engine.search` probes (subject then tokens longest-first, ≤6);
  person-name tokens and stopwords dropped from requirements so "what if we
  assign Bob to delivery?" never derives requirement "delivery".
- `backend/app/api/v1/brain.py` — the governed `/brain/decisions` surface
  (create, list, detail, lifecycle, outcome, what-if); org context without
  context_id accepted; writes require `employees:manage`, reads
  `brain:read`; scoped callers 404/403 leak-free.
- `backend/app/events/event_models.py` + `backend/app/events/handlers.py` —
  the decision bridge (project.started exact-once detection,
  outcome-to-evidence wiring).
- `backend/app/models/__init__.py` — decision tables registered so
  `create_all` builds them live.
- `backend/tests/test_4f7_decisions.py`, `test_4f7_lifecycle.py`,
  `test_4f7_simulations.py`, `test_4f7_governance.py`,
  `test_4f7_brain.py` — 25 slice tests (idempotent expertise seeding,
  in_progress-task workload semantics, honest-negative assertions).
- `backend/scripts/accept_slice4f7.py` — 13 live acceptance checks.

Frontend (new):

- `frontend/lib/api.ts` — Slice 4F.7 block: types (`PeopleDecisionRecord`,
  `PeopleDecisionDetail`, `PeopleDecisionListResponse`,
  `PeopleDecisionBrainResponse`, `SimulationRow`, `AuditRow`, `Candidate`,
  `Requirement`, `EvidenceItem`) and one function per surface
  (`askPeopleDecision`, `getPeopleDecisions` (query key!), 
  `getPeopleDecisionDetail`, `createPeopleDecision`,
  `peopleDecisionLifecycle`, `recordPeopleDecisionOutcome`,
  `peopleDecisionWhatIf`).
- `frontend/app/(app)/people-decisions/page.tsx` — the People Decision
  Center: stat cards (decisions, awaiting human review, outcomes recorded,
  20-run bound), "Ask the brain" panel (recommendation / why-not /
  alternatives / what-if answered live, provenance surfaced, read-only),
  "Create a governed decision" form (reasoned over immediately),
  decisions list with per-row lifecycle + recommended person, and an
  inline detail panel: candidates with roles/evidence/trade-offs/why-not,
  bounded what-if runs, the append-only Governance trail, provenance —
  with lifecycle/outcome actions gated on `employees:manage`.
- `frontend/components/sidebar/Sidebar.tsx` — "People Decisions" entry in
  the Knowledge group (`brain:read`).
- `frontend/e2e/slice4f7-decisions.spec.ts` — Playwright E2E.

## Design decisions locked by tests

- **Decide, never act.** The lifecycle's terminal actions are recording the
  outcome; no transition mutates employees, projects or teams. Tests and
  the acceptance assert the advisory-only boundary.
- **People are not scored.** Candidates carry decision-specific evidence
  dimensions and rationale; "why not X" answers with honest negative
  evidence. The brain answer and candidate rows render evidence counts,
  never hidden scores.
- **HIGH-tier people decisions are refused by design.** Hiring, promotion,
  termination, compensation and disciplinary requests get the
  human-governance refusal before any reasoning — pinned in slice tests and
  live check 10.
- **Excluded candidates are shown, never hidden.** `_finalize_selection`
  receives the full verdicts so capacity-constrained or non-owning people
  appear with role `excluded` plus why_not — a recommendation always shows
  its negatives.
- **The what-if is bounded to the decision context.** Per-capability
  availability delta, concentration, workload and ownership only — never
  the 4P engine; the primary cannot simulate against herself; 20 runs max
  (check 11 live).
- **Brain queries never persist.** ask/why-not/what-if run dry; only
  `POST /decisions` creates rows (check 6 live: 5 questions → zero rows).
- **Person resolution is token-safe.** "who should own the kubernetes
  platform?" and "why not Bob Johnson?" route deterministically via
  subject/token search probes; person-name tokens and stopwords are
  stripped from derived requirements.
- **Outcome becomes evidence.** The recorded outcome is trusted evidence
  for the next evaluation in the same context (check 9 live).
- **Timestamps are timezone-safe.** Every `DateTime` column is
  `DateTime(timezone=True)` — bare `DateTime` produced the asyncpg/Postgres
  tz mismatch 500 discovered live; the live tables were dropped and
  rebuilt by `create_all`.

## Verification

Backend unit tests (the slice):

```
25 passed  (test_4f7_decisions / lifecycle / simulations / governance / brain)
```

Hermetic SQLite, event-bus drains, register_org per test, tenant isolation
covered.

Full cross-slice regression (the complete backend suite, hermetic SQLite,
pytest-xdist 6 workers):

```
903 passed in 1173.19s (0:19:33)
```

(The 878-test 4F.6 baseline is included; 4F.7 adds 25 collected tests.)

Live acceptance (`backend/scripts/accept_slice4f7.py` against the live
backend on :8999 — final result exactly):

```
13/13 checks passed:
 1. the capability substrate is ready: 3 kubernetes experts with evidence
 2. 'who should own' routes to people_decision with an evidence-backed recommendation
 3. 'why not X' answers with honest negative evidence, never a score
 4. the brain what-if is bounded to the decision context, never a prediction
 5. alternatives surface with the primary and trade-offs
 6. brain queries are read-only: nothing persisted from 5 questions
 7. a people decision is reasoned over immediately with candidates/evidence/provenance
 8. the human-governed lifecycle is append-only audited and outcome is recorded
 9. the recorded outcome becomes evidence for the NEXT evaluation
10. HIGH-tier decisions (hiring/promotion/...) stay under human governance
11. what-if runs are persisted, bounded (20 cap), newest first
12. project.started detects a decision in the project context (exact once)
13. scoped callers: org-wide surfaces 404, writes need employees:manage,
    hidden decisions 404
```

Playwright E2E (`frontend/e2e/slice4f7-decisions.spec.ts`):

```
1 passed (10.6s warm) — full governed trail through the live UI + API:
seeding through the live event bus (7 Ada / 3 Bob / 1 Carol Kubernetes
completions), API contracts (recommendation -> Ada Lovelace with rationale
naming trusted evidence + provenance chain; why-not Bob with honest
negatives; alternatives with Primary + trade-offs; governed decision
recommended with risk_tier medium and 3+ candidates; full lifecycle
review/approve/execute/verify/outcome with the exact append-only audit
sequence detected->evaluated->recommended->review->approve->execute->verify
->outcome; HIGH-tier succession REFUSED 400 with human governance), and the
People Decision Center UI: stat cards, ask-panel answer + provenance, the
governed create form ("Reason now" -> immediate recommendation), and the
inline detail panel walking review -> approve -> execute -> verify ->
"Record successful" -> "outcome: successful" from the UI.
```

Frontend static check: `npx tsc --noEmit` clean (repo gate: tsc/next build;
ESLint is not configured — `npm run lint` is interactive and not a gate).

## Universal Company OS moat test

- **5-person startup:** "who should own the kubernetes work?" — one screen,
  zero configuration: the platform reasons over the completed work the team
  already does, names Ada with alternatives, trade-offs, honest negatives
  and provenance; a human reviews, approves and records the outcome. ✓
- **50,000-person enterprise:** the same canonical tables, indexed bounded
  reads, per-org locks, tenant isolation and scoped visibility answer
  "who should own this project" with the SAME architecture (simulations
  capped at 20, list at 50, resolution probes at 6). ✓
- **Connected, not isolated:** the decision engine consumes the 4F.1–4F.6
  stream (expertise, trust, ownership, collaboration, capability/capacity),
  is fed by the event bus (project.started exact-once), feeds the Company
  Brain intents, and its outcomes become evidence for the next evaluation
  — a competitor cannot copy this as a standalone "skills to people" page. ✓

## Post-acceptance state

- The running backend on :8999 is the verified 4F.7 code (the live
  acceptance and E2E ran against it end-to-end); the live Postgres
  decision tables were rebuilt timezone-safe by `create_all`.
- Commit + tag `vcos-slice-4f7-complete` created; workspace junk cleaned.
- **STOP**: next slice is 4G.1 per the locked roadmap.
