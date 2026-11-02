# VCOS B2B SaaS Remaining Roadmap

**Generated:** 2026-10-20  
**Based on:** VCOS_B2B_SAAS_GAP_REGISTER.md  
**Status:** Post-P0-1 implementation (User-facing MFA settings)

---

## Implemented (Completed in This Session)

### P0-1: User-facing MFA Settings Page ✅
**Status:** COMPLETED  
**Files Modified:**
- `backend/app/services/permission_service.py` - Added `security:mfa:read` and `security:mfa:manage` permissions to catalog and all default roles
- `frontend/lib/api.ts` - Added user-facing MFA API functions (`/security/mfa/...` endpoints)
- `frontend/types/company-experience.ts` - Added MFA type definitions
- `frontend/app/(app)/settings/page.tsx` - Added "Security" tab with:
  - TOTP setup with QR code (using qrserver.com API)
  - TOTP verification
  - MFA method listing (TOTP and Passkeys)
  - MFA method removal
  - Backup codes generation and display
  - Passkey registration (UI scaffold)
  - Security events display

**Verification:** All roles now have `security:mfa:read` and `security:mfa:manage` permissions. Frontend and backend compile successfully.

---

## Remaining Implementation Priority Order

### P0 - Security / Data Integrity / Launch Blockers

| ID | Gap | Priority | Effort | Dependencies | Status |
|----|-----|----------|--------|--------------|--------|
| P0-2 | **Privileged re-authentication enforcement** | P0 | S (1-2 weeks) | P0-1 ✅ | READY |
| P0-3 | **SSO user connection flow** | P0 | M (3-6 weeks) | P0-1, IdP test env | BLOCKED (needs IdP) |
| P0-4 | **Passkey implementation fix** | P0 | S-M (1-3 weeks) | `webauthn` library | READY |
| P0-5 | **Subscription/entitlement system** | P0 | L-XL (6-12 weeks) | Payment provider | PLANNING |

#### P0-2: Privileged Re-authentication Enforcement
**Implementation Plan:**
1. Create `require_reauth` dependency in `app/api/deps.py` that checks `mfa_service.check_reauth_required`
2. Apply to sensitive endpoints: user deletion, role assignment, security policy update, data export, org deletion
3. Return 401 with `reauth_required: true` and valid MFA methods
4. Frontend: Intercept 401, show MFA challenge modal, retry with `X-Reauth-Method` header
**Acceptance:** Sensitive actions require fresh MFA; reauth valid for policy window (5-15 min); all methods work; audit logged.

#### P0-4: Passkey Implementation Fix
**Implementation Plan:**
1. Add `webauthn` library to `requirements.txt`
2. Rewrite `complete_passkey_registration` using `webauthn.verify_registration_response`
3. Rewrite `verify_passkey_authentication` using `webauthn.verify_authentication_response`
4. Properly store credential public key, counter, transports
5. Add RP ID/origin configuration via settings
**Acceptance:** Passkey registration verifies attestation; authentication verifies signature + counter; invalid credentials rejected; RP ID/origin enforced.

---

### P1 - Critical Customer Workflows

| ID | Gap | Priority | Effort | Dependencies | Status |
|----|-----|----------|--------|--------------|--------|
| P1-1 | **Public marketing website** | P1 | M (2-4 weeks) | Design assets | PLANNING |
| P1-3 | **Email verification enforcement UI** | P1 | S (1 week) | P0-1 ✅ | READY |
| P1-4 | **Password policy enforcement UI** | P1 | S (1-2 weeks) | P1-3 | READY |
| P1-5 | **Access reviews UI** | P1 | M (2-3 weeks) | P0-1 ✅ | READY |
| P1-6 | **User security events UI** | P1 | S (1-2 weeks) | P0-1 ✅ | READY |
| P1-7 | **Invitation acceptance UX** | P1 | S (1 week) | None | READY |

#### P1-1: Public Marketing Website
**Implementation Plan:**
1. Create Next.js App Router pages: `/`, `/features`, `/pricing`, `/demo`, `/security`, `/privacy`, `/terms`
2. Add demo request form (creates lead in backend)
3. "Start Free Trial" → `/register`
4. SEO metadata, OG tags
5. Responsive design, accessibility
**Acceptance:** All pages load < 2s; demo form creates lead; signup flow works; SEO > 90; WCAG 2.1 AA.

#### P1-3: Email Verification Enforcement UI
**Implementation Plan:**
1. Add `email_verified_at` check in login flow
2. If required and not verified → redirect to verification page
3. Add "Resend verification" in profile/security settings
4. Show verification status badge in profile
**Acceptance:** Unverified users blocked when policy enabled; resend works; status visible.

#### P1-4: Password Policy Enforcement UI
**Implementation Plan:**
1. Create `usePasswordPolicy` hook fetching org policy
2. Add strength meter to registration/change password forms
3. Show requirements checklist (length, uppercase, numbers, symbols)
4. Validate on submit with clear error messages
**Acceptance:** Real-time feedback; server validates same rules; policy changes reflected immediately.

#### P1-5: Access Reviews UI
**Implementation Plan:**
1. Add "Access Reviews" tab in Settings (admin only)
2. List reviews with status (pending/in_progress/completed)
3. Create review wizard (name, scope, frequency, reviewer)
4. Reviewer dashboard: list items with risk level, decide (approve/revoke/modify/defer)
5. Complete review workflow with next review scheduling
**Acceptance:** Admin creates review; items populated with risk; decisions execute backend changes; audit trail complete.

#### P1-6: User Security Events UI
**Implementation Plan:**
1. Already partially implemented in SecurityTab - enhance with:
2. Query `listSecurityEvents` with `user_id=current_user`
3. Display: login success/failed, MFA enroll/verify, device trust/revoke, password change
4. Filter by date, type, severity
5. Add geographic anomaly detection
**Acceptance:** User sees security timeline; event types categorized; filters work; no cross-user leakage.

#### P1-7: Invitation Acceptance UX
**Implementation Plan:**
1. Create `/accept-invite?token=` page
2. Fetch invitation details (company name, inviter, role)
3. Show company branding: "You're invited to join [Company]"
4. Pre-fill email (read-only), only ask name + password
5. On success, redirect to `/home`
**Acceptance:** Invite page shows company context; only name/password required; clear success flow.

---

### P2 - Important Commercial/Professional Capabilities

| ID | Gap | Priority | Effort | Status |
|----|-----|----------|--------|--------|
| P2-1 | Subscription lifecycle | P2 | XL (8-16 weeks) | PLANNING |
| P2-2 | Usage metering/entitlement enforcement | P2 | L (4-8 weeks) | PLANNING |
| P2-3 | Data export/account closure (GDPR) | P2 | M (2-4 weeks) | PLANNING |
| P2-4 | API versioning/deprecation strategy | P2 | S (1-2 weeks) | PLANNING |
| P2-5 | Idempotency keys for mutations | P2 | S (1-2 weeks) | PLANNING |
| P2-6 | Webhook retry/dead letter handling | P2 | M (2-3 weeks) | PLANNING |
| P2-7 | SCIM provisioning UI | P2 | M (2-3 weeks) | PLANNING |

---

### P3 - Usability/Polish

| ID | Gap | Priority | Effort | Status |
|----|-----|----------|--------|--------|
| P3-1 | Loading/empty/error states audit | P3 | S (1-2 weeks) | PLANNING |
| P3-2 | Keyboard navigation audit | P3 | M (2-3 weeks) | PLANNING |
| P3-3 | Screen reader semantics audit | P3 | M (2-3 weeks) | PLANNING |
| P3-4 | Contrast/color audit | P3 | S (1 week) | PLANNING |
| P3-5 | Responsive design audit | P3 | S (1-2 weeks) | PLANNING |
| P3-6 | UI string internationalization | P3 | M (2-4 weeks) | PLANNING |
| P3-7 | User onboarding/tour | P3 | M (2-3 weeks) | PLANNING |

---

## External Dependencies Blocking Progress

| Dependency | Blocks | Required For | Status |
|------------|--------|--------------|--------|
| `webauthn` Python library | P0-4 | Passkey fix | Available on PyPI |
| Real IdP test environment (Okta/Entra ID/Google) | P0-3 | SSO testing | **Not configured** |
| Stripe/Paddle account + pricing approval | P0-5 | Subscription system | **Not configured** |
| Design assets for marketing site | P1-1 | Public website | **Not created** |
| Accessibility testing tools (axe-core, NVDA/JAWS) | P3-2, P3-3 | Accessibility audit | Available |

---

## Implementation Order (Recommended)

1. **P0-2** Privileged re-auth enforcement (depends on P0-1 ✅)
2. **P0-4** Passkey implementation fix (security)
3. **P1-3** Email verification enforcement UI
4. **P1-4** Password policy UI
5. **P1-7** Invitation acceptance UX
6. **P1-5** Access reviews UI
7. **P1-6** User security events UI (enhance existing)
8. **P0-3** SSO user connection flow (when IdP available)
9. **P1-1** Public marketing website (parallel track)
10. **P0-5** Subscription system (parallel track, long)
11. **P2-3** Data export/account closure
12. **P2-4** API versioning
13. **P2-5** Idempotency keys
14. **P3-4** Contrast/color audit (quick win)
15. **P3-1** Loading/empty/error states audit
...

---

## File Ownership Map

| Workstream | Files Owned |
|------------|-------------|
| **Deployment + Backup/Restore + DR** | Deployment configs, backup scripts, DR runbooks |
| **Real Integrations + Company Provisioning E2E** | `auth_service.py`, provisioning flows, integration connectors |
| **Universal Acceptance Matrix** | Accessibility fixes, i18n, responsive fixes |
| **Release Candidate Hardening** | Security fixes, performance, regression tests |
| **Private-Alpha Readiness** | Documentation, support processes, monitoring |

---

## Next Immediate Actions

1. **Implement P0-2** (Privileged re-auth) - Highest impact security fix
2. **Implement P0-4** (Passkey fix) - Requires `pip install webauthn`
3. **Implement P1-3, P1-4, P1-7** - Quick wins for user experience
4. **Design P1-1** - Start marketing site design in parallel
5. **Configure IdP test environment** - Unblock P0-3
6. **Evaluate payment providers** - Unblock P0-5

---

## Acceptance Criteria for Next Milestone (Private Alpha Ready)

- [ ] P0-2: Privileged actions require fresh MFA
- [ ] P0-4: Passkeys work with proper attestation verification
- [ ] P1-3: Email verification enforced when policy enabled
- [ ] P1-4: Password policy visible and enforced in UI
- [ ] P1-5: Access reviews creatable and completable by admins
- [ ] P1-6: Users see their security timeline
- [ ] P1-7: Invitation acceptance shows company context
- [ ] P3-4: Color contrast meets WCAG 2.1 AA
- [ ] All P0/P1 gaps have implementation evidence recorded
- [ ] Frontend + backend regression tests pass
- [ ] No canonical architecture regressions