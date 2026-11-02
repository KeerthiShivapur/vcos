# VCOS Strategic Roadmap — B2B Productization & Moat Layers

**As of:** 2026-10-17 (evening), Windows host, PostgreSQL 18.2
**Audience:** The next engineer or model session, and the founder making go-to-market decisions.
**Read first:** `VCOS_ULTIMATE_MOAT_DOCTRINE.md`, then `VCOS_IMPLEMENTATION_STATUS.md`.
**Rule:** This document is strategy, not evidence. Every phase below earns "done" only by the
evidence discipline in the doctrine (real environment, reproducible artifact, honest failure).
No phase is "done" because this file says so.

---

## 0. Verdict up front

The product substrate is **code-complete far beyond the point most B2B companies have reached
when they start selling**: canonical company reality, 40+ ratified gates, DR verified green,
usage metering + payment reconciliation ratified, a real Stripe provider, enterprise SSO/SCIM/
MFA/passkeys, licensing/entitlements, marketplace, three ratified integrations.

The frontier is no longer features. It is:

1. **Proof under hostile conditions** — hosted deployment, real third-party bindings
   (a real IdP, Stripe in test mode live), restart/rollback drills.
2. **Tenant-isolation hardening** — the app enforces `organization_id` scoping, but there is
   **no database-level RLS** across the ~688-table schema. That is the single largest
   enterprise-blocking gap.
3. **Operations reliability** — today's DR failures (runs 3–5) were caused by the **system
   drive filling to 0 bytes**, not by DR logic. The recovery logic is sound; the environment
   had no guardrails. That class of failure must be eliminated for real customers.

The actual moat is not any single feature. It is the **one canonical reality** + **governance/
provenance/temporal semantics** + the **compounding outcome loop**, all held together by
evidence discipline. The roadmap below protects that thesis. It does not add parallel engines.

---

## 1. Verified baseline (what exists, with evidence)

### 1.1 Recovery (this workstream — closed as of tonight)

| Item | Evidence |
|---|---|
| DR.3 E2E VERIFIED, 10/10 checks, `overall_success: true` | `ev-21a8fdd08415` (morning run, 02:13–02:15 UTC) and re-verified tonight `ev-36db013230fe` (17:40–17:43 local) after hardening |
| Evidence artifacts | `C:\VCOS-Backups\DR3_RECOVERY_BASELINE_EVIDENCE.json` (+ repo copy `backend\DR3_RECOVERY_BASELINE_EVIDENCE.json`), `DR3_TEST_RESULTS.json` |
| Hardening applied tonight | unique per-instance pg_ctl log (was one shared `%TEMP%\pg_ctl_start.log`); orphan-stop now actually stops (`stop` verb was missing → exit 1 forever); extraction integrity verify+retry in `_restore_pg_basebackup`; restore scratch space moved off the system drive |
| Evening incident root cause | System drive at **0 bytes free**; run-5 failed `[Errno 28]`, run-4 failed `pg_ctl start exit 1`. After freeing 8.4 GB (stale restore dirs, canaries preserved) and pointing `TEMP` to `D:\vcos-temp`, run-6 passed. |

### 1.2 Ratified workstreams (see `VCOS_IMPLEMENTATION_STATUS.md` for the full table)

Foundations; Gate 35-G (289 tests), 35-H (415 tests), 35-I (36 tests); Deployment/DR universal
moat (2026-10-05); Real Integrations + Provisioning (Slack, GitHub, Google Workspace);
Universal Acceptance Matrix; Release Candidate slices 2A–2E; Private Alpha readiness;
Billing stages 5.1 (usage metering) and 5.2 (payment reconciliation); Gate 19 feature flags.

### 1.3 Commercial & enterprise code inventory (exists; evidence depth varies)

| Capability | Where | Evidence status |
|---|---|---|
| Subscriptions, plans, quotas | `app/developers/billing_service.py`, `app/models/finance.py` | ratified (5.1/5.2) |
| Usage metering, pricing, reconciliation | `app/api/usage_metering.py`, `usage_aggregation_service.py` | ratified (5.1/5.2) |
| Stripe provider (customers, intents, invoices, refunds, subscriptions) | `app/services/payment_provider.py` (`StripeProvider`) | code complete; **no live test-mode E2E evidence found** |
| Stripe webhooks (signature verify, dedup) | `app/services/payment_webhook_service.py`, `app/api/v1/commercial.py` | code complete; **not proven against Stripe test mode** |
| Enterprise SSO (saml/oidc/oauth2/ldap), SCIM, MFA (TOTP), passkeys, device trust, auth policies | `app/enterprise/identity_service.py`, `sso_service.py`, `scim_service.py`, `app/api/v1/enterprise.py` | code complete; **assertion parsing is a pluggable seam — not proven against a real IdP** |
| Licensing/entitlements (seats, feature gates) | `app/enterprise/licensing_service.py` | code complete |
| Compliance control catalogs (SOC 2, ISO 27001, GDPR, HIPAA, PCI) + posture/reporting | `app/enterprise/compliance_service.py` | code complete — this is a **customer-facing feature**, not VCOS's own certification |
| API gateway (keys, rotation, rate limits) | `app/enterprise/api_gateway.py` | code complete |
| Marketplace + plugins | `app/enterprise/marketplace_service.py` | code complete |
| Feature flags, security events, observability | `app/enterprise/*` | Gate 19 ratified; others code complete |

---

## 2. Honest gap analysis

**G1 — No database-level tenant isolation (RLS). Severity: HIGH (enterprise-blocking).**
Isolation today is application-level `organization_id` scoping. One forgotten filter in one of
~688 tables' query paths is a cross-tenant leak. `grep` confirms: no `ENABLE ROW LEVEL SECURITY`,
no `CREATE POLICY` anywhere in the backend. Enterprise buyers and any serious security review
will ask for this.

**G2 — No hosted production environment. Severity: HIGH.**
Everything is verified on one Windows dev host with a local PostgreSQL. There is no cloud
target, no infrastructure-as-code, no blue/green or rollback proof in a hosted environment,
no hosted restore drill. "Private Alpha readiness" is ratified *as a process*; the missing
artifact is a hosted environment with evidence.

**G3 — Third-party bindings are unproven end-to-end. Severity: MEDIUM-HIGH.**
Stripe: code complete, but no evidence of a live test-mode E2E (checkout → webhook → invoice →
reconciliation). SSO: seams exist, no real-IdP proof (Okta/Entra test tenant). SCIM: same.
Notion of "billing ratified" covers metering/reconciliation internals, not the external round trip.

**G4 — Operational guardrails absent. Severity: HIGH (proven today).**
The DR failures were environment failures: disk hit 0 bytes with no preflight check and no
retention policy for the (growing) restore scratch dirs. There is no formal disk/monitoring
alerting story, no sanctioned cleanup task for `%TEMP%\vcos_dr3_restore_*`, and two unresolved
operational anomalies from today (see §6).

**G5 — VCOS's own compliance posture is a company process, not a product feature. Severity: MEDIUM.**
`compliance_service` gives customers SOC 2 control tracking. It does not make VCOS SOC 2 certified.
An SOC 2 **Type II** requires a 3–6+ month observation window by an auditor; an 8-week plan can
only deliver readiness/gap assessment and policy work. Plan accordingly (see §5).

**G6 — Integration breadth. Severity: MEDIUM (opportunity, not wall).**
Three real adapters ratified (Slack, GitHub, Google Workspace). The canonical integration model
already anticipates oauth2/api_key/basic/saml/oidc auth types. A connector runtime is a
differentiator opportunity — not a defendable moat by itself.

**G7 — Scheduled/background automation hygiene. Severity: MEDIUM.**
Worker registry exists with intervals, but there is no operational schedule for
backup-retention enforcement, scratch-dir reaping, or archive-growth monitoring. Today's
"mystery deletions" of old scratch dirs (observed via FileSystemWatcher) are consistent with
ad-hoc cleanup by non-sanctioned actors; the fix is to make retention an official, logged task.

**G8 — Docs/status drift risk. Severity: LOW.**
`VCOS_IMPLEMENTATION_STATUS.md` §2.2 cites the morning DR.3 evidence only; tonight's re-verified
run (`ev-36db013230fe`) and the hardening changes are not yet reflected there.

---

## 3. Phased roadmap

### Phase 0 — Operational hardening & evidence hygiene (days, no new features)
**Goal:** make tonight's class of failure impossible to repeat silently.
- Add disk-space preflight to the DR.3 harness (fail fast with an honest BLOCKED if free < 5 GB).
- Formalize retention: scheduled task or worker that removes `%TEMP%\vcos_dr3_restore_*` older
  than N days, always logging what it deletes; environment scratch (`TEMP` for DR runs) stays
  configured to a non-system drive.
- Add DR_RUNBOOK entries: disk-full diagnosis, orphan instance stop (the `pg_ctl stop` verb bug),
  unique per-instance pg_ctl logs.
- Update `VCOS_IMPLEMENTATION_STATUS.md` §2.2 with tonight's run + hardening.
- Close or document the two open anomalies (§6).
**Exit criteria:** DR.3 harness preflight present; retention task runs once with a log artifact;
status doc updated; evidence note appended to `backend/POST_DR_REGRESSION_SWEEP_EVIDENCE.md` or
a new small evidence file.

### Phase 1 — Hosted deployment with rollback proof (2–4 weeks)
**Goal:** the ratified deployment contracts become real in a hosted environment.
- Choose one cloud target (single-region is fine for alpha) with managed PostgreSQL.
- Infrastructure as code; secrets via the target's secret manager (not `.env`).
- Blue/green or rolling deploy + **rollback drill with evidence**; hosted restore drill
  (restore the hosted DB into an isolated instance, run the same canonical validators).
- Wire `WAL_ARCHIVE_DIR`/vault to durable object storage.
**Exit criteria:** `HOSTED_DEPLOYMENT_EVIDENCE.md` — deploy, rollback, and restore all executed
against the hosted environment with raw outputs; RPO/RTO numbers for the hosted setup.

### Phase 2 — RLS rollout: database-enforced tenant isolation (6–10 weeks, can run during Phase 1)
**Goal:** every tenant-scoped table carries real RLS policies; app-level scoping stays as
defense in depth.
- Generate a per-table matrix: tenant-scoped vs global tables (688 total; expect most scoped).
- Policy generation: `ENABLE ROW LEVEL SECURITY` + `USING (organization_id = current_setting('app.org_id'))`
  per table, via migration, reviewed table-by-table for edge cases (audit, system, reference tables).
- **Shadow phase:** policies created but not enforced (`ALTER TABLE ... FORCE` off, role
  separation) — run the full regression + acceptance suites and compare results.
- Enforce for internal orgs; then canary real orgs; then all. Session GUC set by a single
  connection-level hook (`SET LOCAL app.org_id`), never per-query.
- Regression gate: cross-tenant probe suite that attempts reads/writes across orgs for a sample
  of every table class and must fail closed.
**Exit criteria:** `RLS_ROLLOUT_EVIDENCE.md` — enforcement on, cross-tenant probe suite green,
full regression green, rollback migration tested.

### Phase 3 — Commercial round trip (2–4 weeks, parallel with Phase 2)
**Goal:** money can be taken and reconciled for real.
- Stripe test-mode E2E: checkout → payment → webhook → invoice → usage reconciliation →
  entitlement change; dunning basics (failed payment → grace → suspend) and tax handling plan.
- Seat/plan management surfaced in the product UI; entitlement gates enforced via
  `licensing_service` on the real plan matrix.
- Backfill one full month of metered usage → invoice in test mode; verify reconciliation report.
**Exit criteria:** `BILLING_E2E_STRIPE_EVIDENCE.md` — the full round trip with Stripe test keys
(keys never echoed; references only).

### Phase 4 — Enterprise identity round trip (2–3 weeks, parallel)
**Goal:** SSO works against a real IdP, not a seam.
- Stand up a test tenant in one IdP (Entra ID or Okta); implement the `parse_assertion` seam for
  at least one protocol end-to-end (OIDC first, then SAML).
- SCIM provisioning E2E against the same IdP; MFA/passkey policy enforcement on real flows.
**Exit criteria:** `SSO_SCIM_E2E_EVIDENCE.md` — real IdP login + deprovision with raw outputs.

### Phase 5 — Trust program + integration moat (3–6 months, ongoing)
**Goal:** credible enterprise trust posture and compounding integration value.
- SOC 2 readiness now (control mapping already exists in `compliance_service` catalogs),
  external auditor engaged; Type II window started when hosting/ops are stable (post Phase 1–4).
- Universal connector runtime on top of the canonical integration model; grow ratified adapters
  from 3 to ~10 (each with an evidence file, same pattern as Slack/GitHub/Google).
- Instrument the compounding loop: verified outcomes → lessons → measurable decision-quality
  deltas per org (this is the moat metric; publish it in the product).
**Exit criteria:** per-quarter evidence files; connector count and lesson-loop metrics tracked.

---

## 4. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cross-tenant leak pre-RLS | Medium | Critical | Phase 2 expedited; cross-tenant probe gate in interim |
| Disk/ops failure repeated in hosted env | Medium | High | Phase 0 preflight + retention + monitoring before any customer |
| Stripe/SSO claims outrun evidence in sales | Medium | High | Never claim what Phase 3/4 evidence files don't show |
| SOC 2 expectation mismatch (8 weeks) | High | Medium | Reframe to readiness; Type II on a 3–6 month clock |
| Windows-dev-only verification traps | Low | Medium | Phase 1 hosted environment; Linux CI already ratified |
| Reopening ratified work without defect evidence | Low | High | Doctrine §3.5; regression-test-first rule |

---

## 5. Direct answers (the requested opinion, honestly)

- **Is DR done?** Yes — verified twice, and now hardened. The evening failures were a full disk,
  not DR logic. Remaining DR risk is operational (Phase 0), not architectural.
- **RLS over ~688 tables — is it the right call?** Yes, eventually mandatory for enterprise,
  but staged as in Phase 2. Budget 6–10 weeks with automation; do **not** rip out app-level
  scoping (defense in depth). Do it before SERIOUS enterprise sales, after hosted deployment
  exists so policies are proven in the real target.
- **B2B/Stripe readiness?** Code is essentially complete. The remaining 2–4 weeks is proof and
  polish (test-mode E2E, dunning, tax, UI), not architecture.
- **SOC 2 in 8 weeks?** Not for Type II. 8 weeks can deliver readiness: policies, control
  mapping, evidence automation. Type II needs a 3–6+ month observation window under an auditor.
  Start readiness now; time the window to when hosting and ops stop changing weekly.
- **Universal integration moat?** Three ratified adapters is a strong start, not a moat.
  The connector runtime plus the outcome loop is where defensibility compounds.
- **What is the moat, actually?** The canonical one-truth substrate and the compounding
  evidence discipline. Features (billing, SSO, DR) are table stakes competitors will match.
  The doctrine's loop — verified outcomes feeding lessons feeding better decisions — is the
  thing that takes years to copy. Protect it; measure it; sell the measurements.

---

## 6. Open operational anomalies (documented, not blockers)

1. **Intermittent deletions of old `%TEMP%\vcos_dr3_restore_*` dirs** observed 11:05–15:46
   (last pass ~15:45:43–15:46:10), then dormant; canary directories untouched since planting
   (16:26/16:53). No repo code matches. Consistent with ad-hoc cleanup by a non-sanctioned
   actor; formalized retention (Phase 0) makes the sanctioned actor the only one.
2. **60-second connections to a stopped orphan instance's port** (FATAL series in the shared
   pg_ctl log) continued until the orphan was stopped at 17:14 by the fixed cleanup; stopped
   with it. Watcher scripts and canaries remain in place
   (`C:\Users\SKEERT~1\AppData\Local\Temp\opencode\fsw_watch.ps1`, `fsw_sweep_log.txt`,
   `prober_watch_log.txt`) — if either pattern reappears, the logs now capture process snapshots.

---

## 7. Immediate next actions (ordered)

1. Phase 0 preflight + retention task (small, prevents tonight from recurring).
2. Update `VCOS_IMPLEMENTATION_STATUS.md` §2.2 to cite tonight's DR.3 run and hardening.
3. Decide the hosted target for Phase 1 (one decision unblocks weeks of work).
4. Phase 2 RLS: produce the tenant-scoped-vs-global table matrix (read-only analysis; no code).
5. Phase 3: request Stripe test-mode keys when ready (currently BLOCKED on credentials).
6. Phase 4: create one IdP test tenant (Entra ID or Okta).
7. Keep the doctrine rules: one canonical reality, no parallel engines, evidence before claims.

---

## Appendix A — Evening incident summary (2026-10-17)

- Runs 3–5 of DR.3 failed across the afternoon. Last pass of an external deletion sweep over
  scratch dirs: ~15:45:43–15:46:10. Canaries planted (16:26, 16:53) were never touched.
- Run-4 (16:55): integrity check PASSED (41725 files) but `pg_ctl start exit code: 1` — the
  shared `%TEMP%\pg_ctl_start.log` was held open by an orphaned instance's wrapper and polluted
  by its FATAL flood; root cause of the start failure was the system drive at 0 bytes free.
- Run-5 (17:14): orphan cleanup now actually stopped the orphan (missing `stop` verb fixed;
  `pg_ctl stop exit code: 0`), then failed with `[Errno 28] No space left on device`.
- Remediation: deleted 21 stale scratch dirs (8.4 GB freed; canaries preserved); redirected
  DR scratch `TEMP`/`TMP` to `D:\vcos-temp`; three code fixes (unique pg_ctl log path,
  orphan-stop verb, extraction integrity verify+retry).
- Run-6 (17:40–17:43): 10/10 PASS, `overall_success: true`, integrity scan 0 findings,
  RPO 0.1s; evidence `ev-36db013230fe`, final verdict VERIFIED; artifacts regenerated.
