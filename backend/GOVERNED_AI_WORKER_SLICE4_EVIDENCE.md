# Governed AI Worker MVP (Slice 4) — Evidence

**Date:** 2026-10-18 (early morning)
**Scope:** AI work as a governed actor on the canonical operation spine — read-only research over
authorized company context, evidence-backed recommendation with a proposed decision + pending
approval, and approval-gated action execution that creates a real canonical task. No parallel task
system, no second decision engine, no standalone AI dashboard, no mock product data.

## 1. Files created / modified

| File | Change |
|---|---|
| `backend/app/schemas/governed_worker.py` | NEW — `WorkerTaskCreate`, `WorkerModelOutput` (strict model-output contract), evidence/proposed-action shapes |
| `backend/app/services/governed_worker_service.py` | NEW — `GovernedWorkerService`: create/run/execute/cancel/list/detail (1,079 lines) |
| `backend/app/api/v1/governed_worker.py` | NEW — router `/governed-worker`, permission gate `ai:use` |
| `backend/app/main.py` | Router registered (import tuple + `include_router`) |
| `backend/tests/conftest.py` | `app_factory` includes the router |
| `backend/tests/test_governed_worker.py` | NEW — 16 tests (model seam monkeypatched via `_invoke_model`) |
| `backend/app/services/canonical_reliability_service.py` | **Bug fix**: `_create_worker_lease` hardcoded `organization_id="system"` (FK violation on live Postgres for any `create_operation`); now derives org from the operation and records `worker_instance` |
| `frontend/lib/api.ts` | Appended GovernedWorker types + wrappers (`listGovernedWorkerTasks`, `createGovernedWorkerTask`, `getGovernedWorkerTask`, `runGovernedWorkerTask`, `cancelGovernedWorkerTask`, `executeGovernedWorkerAction`) |
| `frontend/components/command-center/GovernedAIWork.tsx` | NEW — Governed AI Work section (create form, task list with phase badges, run/cancel/execute, detail modal with facts/evidence/inferences/uncertainties/recommendations + governance links) |
| `frontend/app/(app)/command-center/page.tsx` | Section wired (`<section aria-label="Governed AI Work">`) |
| `frontend/components/ui/Select.tsx` | Additive fix — label now wires `htmlFor={id}` (previously labels were not associated; `id` still spread onto `<select>`) |
| `frontend/e2e/slice9-governed-worker.spec.ts` | NEW — real-backend e2e: research, recommendation → approval → execution, tenant isolation |

## 2. Architecture (canonical reuse, no parallel engines)

- **Operation spine:** every worker task is a `CanonicalOperation` (`operation_type =
  governed_worker.task`); every authorized action is a child `governed_worker.action` operation
  linked via `payload.parent_operation_id`. Lifecycle, attempts, lease-based recovery, and
  idempotency come from the existing `canonical_reliability_service` (exact-once fingerprint from
  `idempotency_key`, or `nonce:<iso>` when absent; `max_attempts=1` — no blind AI retries).
- **Context:** read-only retrieval over existing canonical services (projects, tasks, decisions,
  risks) with tenant + scope validation; `scope_type` is `company` or `project`.
- **Model seam:** the only AI call is `_invoke_model` → `ai_gateway.chat` with a strict JSON-only
  prompt; 60s timeout via `asyncio.wait_for`.
- **Governance persistence (recommendation):** existing `decision_service.create` (status
  `proposed`, tags `governed-worker`,`ai-proposal`) + `approval_service.create`
  (`approval_type = governed_worker_action`, `entity_type = governed_worker.task`, `entity_id =
  operation.id`) + queued child action operation carrying `authorization_id`/`decision_id`.
- **Execution boundary:** `execute_action` revalidates at execution time — operation state, parent,
  and `approval.status == "approved"` — before creating the real task via `task_service.create`
  (tags `governed-worker`,`authorized-action`; title `Follow-up: <instruction[:180]>` by default, or
  the model's proposed action title when available). Approvals rejected/cancelled → action phase
  `action_rejected`/`action_cancelled`; execution errors → `action_failed`.
- **Phases (derived in the view):** queued, running, completed, awaiting_approval,
  ready_to_execute, executed, action_rejected, action_failed, action_cancelled, failed, cancelled,
  unknown, recovering (retrying→queued, reconciled→completed, expired→failed).
- **Events/audit:** `governed_worker.task.created`, `.context.retrieved`, `.task.completed`,
  `.task.failed`, `.approval.requested`, `.execution.completed`, `.execution.failed`,
  `.task.cancelled`; audit via `work_audit.record`.

## 3. Epistemic behavior (observed vs claimed vs inferred)

- **Observed facts** come only from canonical services; the prompt forbids invention, and the
  persisted result stores observed facts, model-claimed facts, inferences, and uncertainties in
  separate fields with an `epistemic` map. UNKNOWN is preserved as an explicit uncertainty.
- **Honest degradation:** provider `local`/`none` or an unreachable provider → the run completes
  facts-only with an explicit "No AI model was available…" uncertainty — never fake reasoning.
- **Untrusted output rejected:** malformed/incomplete JSON or contract violations →
  `model_output_invalid` failure; nothing is persisted as a result (demonstrated against the real
  Groq API where truncated JSON was rejected — see §7).

## 4. API surface

`POST /api/v1/governed-worker/tasks` (201, returns detail incl. `phase`), `GET
/api/v1/governed-worker/tasks`, `GET .../tasks/{id}`, `POST .../tasks/{id}/run`, `POST
.../tasks/{id}/cancel`, `POST .../actions/{id}/execute`. All gated by existing permission
`ai:use`; invalid transitions → 400; wrong tenant/type/not found → 404; cancel of a completed
task → 400.

## 5. Frontend

`GovernedAIWork` section on `/command-center` (label association fixed via explicit ids; `Select`
`htmlFor` additive fix). Create form (title, kind, scope, instruction), Create & run, task list
with phase badges, per-task Run/Cancel/Execute/View, detail modal (facts/evidence/inferences/
uncertainties/recommendations, proposed decision + authorization links to `/decisions` and
`/approvals`, model-assisted vs facts-only notice). Tenant isolation is server-side only; the
frontend never sends an organization id.

## 6. Verification — backend

| Command | Result |
|---|---|
| `pytest tests/test_governed_worker.py -q` (venv) | **16 passed** (twice: pre- and post-lease-fix) |
| Covers | research w/ model, facts-only degrade, company scope, malformed JSON, incomplete JSON, timeout, recommendation governance, blocked-before-approval, execute-after-approval → real task, rejected approval, cancelled approval, idempotency (same key), cancel→run 400, invalid transitions, project scope validation, tenant isolation |

Live Postgres verification (local provider, deterministic; JSON evidence in `%TEMP%\opencode\
slice4_live_{research,recommendation,execution}.json`): research → `completed`, `model.available
False`, facts-only + explicit uncertainty; recommendation → `awaiting_approval` with pending
approval + proposed decision; execute before approval → 400; after approval → `executed` and a
real task created with tags `governed-worker`,`authorized-action`.

## 7. Verification — real provider (Groq, live API)

Backend restarted with env overrides only (`.env` untouched, remains `AI_PROVIDER=none`):
`AI_PROVIDER=groq`, `GROQ_MODEL=openai/gpt-oss-120b`, `AI_MAX_TOKENS=2048`.

| Run | Result |
|---|---|
| Research | `completed`, provider `groq`, model `openai/gpt-oss-120b`, **assisted: True**; summary grounded in canonical facts (project `draft`, risk score 12, no open tasks); separate facts/inferences/recommendations (`slice4_groq_research2.json`) |
| Recommendation | **assisted: True**; model-proposed action title `Mitigate Vendor Dependency Risk`; phase `awaiting_approval`; approval `pending`; decision `proposed` (`slice4_groq_recommendation.json`) |
| Research @ default `AI_MAX_TOKENS=1024` (two attempts) | `failed` with `model_output_invalid: invalid_json: Unterminated string starting at` — real marked-truncation from the reasoning model; correctly rejected and never persisted (`slice4_groq_research.json`, plus second attempt) |

Environment findings (documented, not "fixed" silently):
- `backend/.env` intentionally ships `AI_PROVIDER=none` → product default is honest facts-only.
- `config.py` default Groq model `llama-3.3-70b-versatile` (L75/77) now returns **404
  model_not_found** from the live Groq API (retired); verification used `openai/gpt-oss-120b` via
  env override.
- `AI_MAX_TOKENS` default 1024 is below what reasoning models need for this JSON contract;
  2048 verified. Config defaults untouched.
- Transient `QueuePool limit of size 10 overflow 20` starvations logged from pre-existing
  background workers (not worker-task specific); run succeeded regardless.

## 8. Verification — frontend

| Command | Result |
|---|---|
| `npx tsc --noEmit` | Clean (twice; final after Select/ids fix) |
| `npm run build` | Success — `/command-center` compiled (9.19 kB / 131 kB first load); 80/80 static pages (dev server stopped first to avoid `.next` clobber) |
| `npx playwright test e2e/slice9-governed-worker.spec.ts` | **1 passed (30.7s)** — real backend + real UI: register org, project, research run (facts-only notice, no fabricated authorization), recommendation → awaiting approval, real pending approval found via REST and decided (approval decision via REST for determinism), execute blocked pre-approval (404 for bogus id), Execute approved action → executed detail + real `Follow-up:` task in `/tasks`, org B sees none of it |
| Regressions: `e2e/slice6-approvals-risks.spec.ts`, `e2e/slice8-command-center.spec.ts` | **2 passed** (51.6s, 35.2s) |

E2E flake fixed during the slice: label association (`Input`/`Textarea` need `id`/`name`; `Select`
had no `htmlFor`) — the component now passes explicit ids. One e2e run was lost mid-slice to a
stray Ctrl+C delivered to the backend console (harness artifact), not a product defect.

## 9. Pre-existing defects (honest disclosure)

- `backend/app/services/auth_service.py` L558–563: `.first()` on `select(Role)` without
  `.scalars()` makes `role_target = r.id` fail → **2 failures in `tests/test_decision_execution.py`**
  (`test_execute_action_converts_to_linked_task` et al). Verified present at HEAD
  (`git show HEAD:backend/app/services/auth_service.py`); **not fixed** (out of Slice 4 scope,
  reported for a dedicated fix).
- `_create_worker_lease` FK bug **was** fixed because it blocked any live `create_operation` on
  Postgres (Slice 4 cannot run without it); 16/16 tests re-passed after the fix.
- Pre-existing 5 gate32 failures (classified in the post-DR sweep) remain untouched.

## 10. Known limitations

- Approval decisioning in the e2e is done via REST (`POST /approvals/{id}/decide`) for
  determinism; the UI path (`/approvals` page) is already covered by `slice6` e2e.
- Actions only create canonical tasks (`task_service.create`); other action types are
  deliberately out of MVP scope.
- Postgres dev backend runs on the **global** Python 3.13 (the `backend/.venv` lacks `stripe`);
  API tests need the venv with `pyotp` + `cryptography` installed (local env fix, no repo change).
- No pagination in the task list (first 50); detail modal renders full result.
- Worker model calls hold their request; concurrent load interacts with the pre-existing DB pool
  pressure noted in §7.

## 11. Independent closeout re-verification (2026-10-18, second pass)

All results below were re-executed against the actual repository after the closeout report, with the
backend restored to its normal configuration (`.env` defaults; provider unavailable → facts-only)
and the frontend dev server running.

| Check | Exact result |
|---|---|
| `pytest tests/test_governed_worker.py -q` (venv) | **16 passed in 13.68s**; test names verified on disk (model assistance, honest degradation, company scope, malformed/incomplete output, timeout, recommendation governance, blocked/executed/rejected/cancelled approval, idempotent creation, cancel→run rejected, invalid transitions, project-scope validation, tenant isolation) |
| `npx tsc --noEmit` | Clean |
| `npx playwright test e2e/slice9 e2e/slice8 e2e/slice6` | **3 passed (41.0s)** — slice6 22.1s, slice8 7.3s, slice9 10.2s |
| `npm run build` | Success — 80/80 static pages; `/command-center` 9.19 kB |
| Dev server health | `GET http://localhost:3000/command-center` → **HTTP 200** (9,351 bytes), not merely a process check |
| Label fix on disk | `GovernedAIWork.tsx` ids at L220/L229/L240/L250; `Select.tsx` `htmlFor={id}` at L14 |
| Evidence/status on disk | `backend/GOVERNED_AI_WORKER_SLICE4_EVIDENCE.md` present; status doc §2.7 at L166 |

Live PostgreSQL governance re-verification (JSON: `%TEMP%\opencode\slice4_final_live_verification.json`):

| Property | Result |
|---|---|
| Provider unavailable ≠ assisted success | `completed`, provider unavailable, `assisted False`, explicit uncertainty text persisted |
| Idempotency (sequential, same key) | Same operation id returned |
| Idempotency (parallel creates, same key) | Both HTTP 201, **same operation id** (`1e7707e7…`) — exact-once under concurrency |
| Concurrent run of same task | HTTP **200 + 400**; final phase `completed` — no duplicate execution |
| Recommendation | `awaiting_approval`; approval `pending`; decision `proposed` |
| Execute before approval | HTTP 400 |
| Rejected approval | Execute → HTTP 400; phase `action_rejected` |
| Approved execution | Phase `executed`; real canonical task `87150416…` exists in `/tasks`; title `Follow-up: …`; tags `governed-worker,authorized-action` |
| Cancel then run | HTTP 400 |

Groq artifacts re-verified on disk (`slice4_groq_research.json` failed-truncation, `slice4_groq_research2.json` assisted, `slice4_groq_recommendation.json` assisted) — unchanged from §7.

## 12. Stop-condition status

- **IMPLEMENTED:** backend service/schemas/API/router/tests, frontend section + wrappers, e2e,
  lease fix, this evidence document, status doc §2.7.
- **LOCALLY VERIFIED:** 16/16 backend tests; live Postgres local-provider runs;
  real-provider (Groq) assisted research + recommendation with approval gate; malformed-output
  rejection against the real API; e2e slice9 + slice6/slice8 regressions; tsc; production build.
- **HOSTED VERIFICATION BLOCKED:** no hosted environment/credentials; local-only verification.
- **REMAINING LIMITATIONS:** listed in §10; pre-existing defects in §9 remain (documented).
