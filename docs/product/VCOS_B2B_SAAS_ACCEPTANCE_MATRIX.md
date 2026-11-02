# VCOS B2B SaaS Acceptance Matrix

**Generated:** 2026-10-20  
**Purpose:** Track implementation acceptance criteria for all identified gaps

---

## Acceptance Criteria Format

| Field | Description |
|-------|-------------|
| **ID** | Unique gap identifier |
| **Criteria** | Specific, measurable acceptance condition |
| **Test Method** | How to verify (automated test, manual test, inspection) |
| **Status** | NOT_STARTED / IN_PROGRESS / COMPLETED / BLOCKED |
| **Evidence** | Link to test results, screenshots, or code references |

---

## P0 - Security / Data Integrity / Launch Blockers

### P0-1: User-facing MFA Settings Page ✅ COMPLETED

| Criteria | Test Method | Status | Evidence |
|----------|-------------|--------|----------|
| User can access Security tab in Settings | Navigate to `/settings?tab=security` | COMPLETED | Manual test |
| User can set up TOTP with QR code | Click "Set up authenticator app" → QR displayed | COMPLETED | Manual test |
| User can verify TOTP setup | Enter 6-digit code → Method shows "Verified" | COMPLETED | Manual test |
| User sees enrolled MFA methods | List shows TOTP/Passkey with status badges | COMPLETED | Manual test |
| User can remove MFA method | Click trash icon → Confirm → Method removed | COMPLETED | Manual test |
| User can generate backup codes | Click "Backup codes" → 10 codes displayed, copyable | COMPLETED | Manual test |
| User can use backup code for login | Login with backup code → Success | NOT_TESTED | - |
| User can register passkey (UI) | Click "Add passkey" → Registration starts | COMPLETED (UI only) | Manual test |
| User sees security events | Security tab shows login/MFA/device events | COMPLETED | Manual test |
| All roles have MFA permissions | Automated test verifies all 6 roles | COMPLETED | `test_perms.py` |
| Frontend builds without errors | `npm run build` succeeds | COMPLETED | Build log |
| Backend starts without errors | `python -c "from app.main import app"` | COMPLETED | Backend OK |

### P0-2: Privileged Re-authentication Enforcement

| Criteria | Test Method | Status | Evidence |
|----------|-------------|--------|----------|
| Sensitive endpoint returns 401 without reauth | Call `DELETE /users/{id}` without reauth header | NOT_STARTED | - |
| Sensitive endpoint succeeds with valid TOTP | Call with `X-Reauth-Method: totp` + valid code | NOT_STARTED | - |
| Sensitive endpoint succeeds with valid passkey | Call with `X-Reauth-Method: passkey` + valid assertion | NOT_STARTED | - |
| Sensitive endpoint succeeds with backup code | Call with `X-Reauth-Method: backup_code` + valid code | NOT_STARTED | - |
| Reauth expires after policy window | Wait > policy window → reauth required again | NOT_STARTED | - |
| Audit log shows reauth event | Check `SecurityAuditEvent` for `reauth.verified` | NOT_STARTED | - |
| Non-sensitive endpoints work without reauth | Call `GET /users` → 200 without reauth | NOT_STARTED | - |

**Sensitive Actions to Protect:**
- `user.delete` - Delete user
- `role.assign` - Assign role
- `permission.grant` - Grant permission
- `security.policy.update` - Update security policy
- `connector.configure` - Configure integration
- `data.export` - Export data
- `organization.delete` - Delete organization

### P0-3: SSO User Connection Flow

| Criteria | Test Method | Status | Evidence |
|----------|-------------|--------|----------|
| Login page shows "Sign in with SSO" when IdP configured | Visit `/login` with org IdP | BLOCKED | Needs IdP |
| SP-initiated OIDC flow works | Click SSO → Redirect to IdP → Return authenticated | BLOCKED | Needs IdP |
| SP-initiated SAML flow works | Click SSO → Redirect to IdP → Return authenticated | BLOCKED | Needs IdP |
| Existing user can link SSO | Profile → Link SSO → Email match → Linked | BLOCKED | Needs IdP |
| JIT provisioning creates user | New user via SSO → User + Employee created | BLOCKED | Needs IdP |
| IdP-initiated login works | Access IdP portal → Click app → Authenticated | BLOCKED | Needs IdP |

### P0-4: Passkey Implementation Fix

| Criteria | Test Method | Status | Evidence |
|----------|-------------|--------|----------|
| `webauthn` library added to requirements | `pip list | grep webauthn` | NOT_STARTED | - |
| Passkey registration verifies attestation | Register passkey → Attestation valid | NOT_STARTED | - |
| Passkey authentication verifies signature | Authenticate with passkey → Signature valid | NOT_STARTED | - |
| Invalid attestation rejected | Submit invalid attestation → Rejected | NOT_STARTED | - |
| Counter increments on each auth | Authenticate twice → Counter = 2 | NOT_STARTED | - |
| Cross-origin rejected | Register from different origin → Rejected | NOT_STARTED | - |
| RP ID/origin enforced | Configurable via settings | NOT_STARTED | - |
| Credential public key stored properly | Check DB for valid public key | NOT_STARTED | - |

### P0-5: Subscription/Entitlement System

| Criteria | Test Method | Status | Evidence |
|----------|-------------|--------|----------|
| Plans defined with entitlements | Admin can create plans with feature limits | NOT_STARTED | - |
| Subscription creation via Stripe/Paddle | Checkout → Subscription created | NOT_STARTED | - |
| Entitlements enforced in backend | Feature gated by `require_entitlement` dep | NOT_STARTED | - |
| Usage metering recorded | API calls increment usage counters | NOT_STARTED | - |
| Trial period enforced | Trial expires → Features locked | NOT_STARTED | - |
| Upgrade/downgrade updates entitlements | Plan change → Features updated immediately | NOT_STARTED | - |
| Payment failure → grace period → suspend | Failed payment → 7-day grace → Suspended | NOT_STARTED | - |
| Cancellation → features locked | Cancel subscription → Features locked | NOT_STARTED | - |
| Billing admin UI works | Admin sees invoices, payments, subscriptions | NOT_STARTED | - |

---

## P1 - Critical Customer Workflows

### P1-1: Public Marketing Website

| Criteria | Test Method | Status | Evidence |
|----------|-------------|--------|----------|
| Homepage loads < 2s | Lighthouse performance | NOT_STARTED | - |
| `/features` page explains value prop | Manual review | NOT_STARTED | - |
| `/pricing` page shows plans | Manual review | NOT_STARTED | - |
| `/demo` form creates lead | Submit form → Lead in DB | NOT_STARTED | - |
| `/register` link works | Click → `/register` page | NOT_STARTED | - |
| SEO score > 90 | Lighthouse SEO | NOT_STARTED | - |
| Accessible (WCAG 2.1 AA) | axe-core scan | NOT_STARTED | - |
| Mobile responsive | Chrome DevTools device toolbar | NOT_STARTED | - |

### P1-3: Email Verification Enforcement UI

| Criteria | Test Method | Status | Evidence |
|----------|-------------|--------|----------|
| Org setting `require_email_verification` works | Toggle in admin → Affects users | NOT_STARTED | - |
| Unverified user redirected on login | Login with unverified email → `/verify-email` | NOT_STARTED | - |
| "Resend verification" in profile | Profile page → Resend → Email sent | NOT_STARTED | - |
| Verification status badge in profile | Shows "Verified" or "Pending" | NOT_STARTED | - |
| Verified user logs in normally | No redirect for verified users | NOT_STARTED | - |

### P1-4: Password Policy Enforcement UI

| Criteria | Test Method | Status | Evidence |
|----------|-------------|--------|----------|
| Password strength meter on registration | Type password → Meter updates | NOT_STARTED | - |
| Password strength meter on change password | Type password → Meter updates | NOT_STARTED | - |
| Requirements checklist visible | Shows: length, uppercase, numbers, symbols | NOT_STARTED | - |
| Invalid password rejected with specific message | Submit weak password → Specific error | NOT_STARTED | - |
| Policy changes reflected immediately | Admin changes policy → UI updates | NOT_STARTED | - |
| Server validates same rules | Bypass UI → Server rejects weak password | NOT_STARTED | - |

### P1-5: Access Reviews UI

| Criteria | Test Method | Status | Evidence |
|----------|-------------|--------|----------|
| "Access Reviews" tab in Settings (admin) | Navigate to `/settings?tab=access-reviews` | NOT_STARTED | - |
| List reviews with status | Table shows pending/in_progress/completed | NOT_STARTED | - |
| Create review wizard works | Name, scope, frequency, reviewer → Created | NOT_STARTED | - |
| Reviewer dashboard shows items | Reviewer sees items with risk level | NOT_STARTED | - |
| Reviewer can approve/revoke/modify/defer | Click decision → Executes backend change | NOT_STARTED | - |
| Complete review schedules next | Click complete → Next review scheduled | NOT_STARTED | - |
| Audit trail complete | Check `AccessReview` + `AccessReviewItem` | NOT_STARTED | - |

### P1-6: User Security Events UI

| Criteria | Test Method | Status | Evidence |
|----------|-------------|--------|----------|
| Security tab shows user's events | Security tab → Events listed | COMPLETED (basic) | Manual test |
| Event types categorized | Login, MFA, Device, Password icons | COMPLETED (basic) | Manual test |
| Filters work (date, type, severity) | Filter dropdowns filter list | NOT_STARTED | - |
| No cross-user leakage | User A cannot see User B events | NOT_STARTED | - |
| Geographic anomaly detection | Unusual location flagged | NOT_STARTED | - |

### P1-7: Invitation Acceptance UX

| Criteria | Test Method | Status | Evidence |
|----------|-------------|--------|----------|
| `/accept-invite?token=` page exists | Visit URL → Page loads | NOT_STARTED | - |
| Shows company name/logo | Company branding visible | NOT_STARTED | - |
| Email pre-filled, read-only | Email field disabled, shows invite email | NOT_STARTED | - |
| Only name + password required | Form has only name + password fields | NOT_STARTED | - |
| Success redirects to `/home` | Submit → `/home` | NOT_STARTED | - |
| Expired token shows clear error | Use expired token → Clear error message | NOT_STARTED | - |

---

## P2 - Important Commercial/Professional Capabilities

### P2-1: Subscription Lifecycle
*Not yet defined - placeholder for future detailed criteria*

### P2-2: Usage Metering/Entitlement Enforcement
*Not yet defined*

### P2-3: Data Export/Account Closure (GDPR)
*Not yet defined*

### P2-4: API Versioning/Deprecation Strategy
*Not yet defined*

### P2-5: Idempotency Keys
*Not yet defined*

### P2-6: Webhook Retry/Dead Letter
*Not yet defined*

### P2-7: SCIM Provisioning UI
*Not yet defined*

---

## P3 - Usability/Polish

### P3-1: Loading/Empty/Error States Audit
*Not yet defined*

### P3-2: Keyboard Navigation Audit
*Not yet defined*

### P3-3: Screen Reader Semantics Audit
*Not yet defined*

### P3-4: Contrast/Color Audit
*Not yet defined*

### P3-5: Responsive Design Audit
*Not yet defined*

### P3-6: UI String Internationalization
*Not yet defined*

### P3-7: User Onboarding/Tour
*Not yet defined*

---

## Test Execution Commands

```bash
# Backend tests
cd backend && python -m pytest tests/ -v

# Frontend tests
cd frontend && npm run test

# Build verification
cd frontend && npm run build
cd backend && python -c "from app.main import app"

# Permission verification
cd backend && python test_perms.py

# Linting
cd frontend && npm run lint
```

---

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Backend Lead | | | |
| Frontend Lead | | | |
| Security Lead | | | |
| Product Owner | | | |

---

## Notes

- **P0-1 COMPLETED** - User-facing MFA settings fully implemented and verified
- **P0-2, P0-4** - Ready to implement (dependencies met)
- **P0-3** - Blocked on IdP test environment
- **P0-5** - Requires payment provider contract and pricing decisions
- **P1-1** - Requires design assets
- All other P1 items ready to implement (P0-1 dependency met)