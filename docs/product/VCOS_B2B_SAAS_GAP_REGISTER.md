# VCOS B2B SaaS Gap Register

**Generated:** 2026-10-20  
**Based on:** VCOS_B2B_SAAS_CURRENT_STATE.md  
**Methodology:** Evidence-backed from source code inspection

---

## Gap Register

### P0 - Security / Data Integrity / Launch Blockers

| ID | Product Area | Exact Issue | Evidence | Source Files | Current Behavior | Expected Behavior | Customer Impact | Security Impact | Canonical Integrity Impact | Priority | Dependencies | Implementation Plan | Tests Required | Acceptance Criteria | Effort Range | Status | Blocker | External Dependency |
|----|--------------|-------------|----------|--------------|------------------|-------------------|-----------------|-----------------|---------------------------|----------|--------------|---------------------|----------------|---------------------|--------------|--------|---------|---------------------|
| P0-1 | Authentication / MFA | **No user-facing MFA management** - Users cannot enroll TOTP, passkeys, generate backup codes, manage trusted devices | Backend MFA service complete (`mfa_service.py`), API endpoints exist (`security.py`), but **no frontend page** for users to manage their own MFA. Only enterprise admin has MFA UI. | `app/services/mfa_service.py:98-272`, `app/api/v1/security.py:219-292`, `frontend/app/(app)/profile/page.tsx` (no MFA), `frontend/app/(app)/enterprise/page.tsx` (admin only) | Users see profile, password, sessions but **no MFA section**. MFA endpoints require `security:mfa:manage` permission which regular users don't have. | Users can: enroll TOTP (QR code), verify setup, list methods, remove methods, generate/verify backup codes, enroll passkeys, manage trusted devices, view security events | **Critical** - Users cannot secure accounts; enterprise prospects will reject product | **Critical** - Accounts vulnerable to credential theft | Low - doesn't affect canonical reality | P0 | User needs `security:mfa:read` and `security:mfa:manage` permissions (currently admin-only) | 1. Add `security:mfa:read` and `security:mfa:manage` to default user role or create self-service permission. 2. Create `/app/(app)/settings/security/page.tsx` or `/app/(app)/profile/security/page.tsx`. 3. Implement TOTP setup (QR code via `qrcode.react`), verification, method listing, removal. 4. Implement backup codes generation/verification. 5. Implement passkey enrollment (WebAuthn API). 6. Implement device trust list with revoke. 7. Add security events list for user. 8. Add MFA status to profile header. | 1. Unit tests for MFA API permissions. 2. E2E: Register → Profile → Security → Enroll TOTP → Verify → Login with TOTP. 3. E2E: Generate backup codes → Use one → Verify consumed. 4. E2E: Enroll passkey → Authenticate. 5. E2E: Trust device → Revoke device. 6. Permission test: Regular user CAN access, non-member CANNOT. | 1. User can enroll TOTP via QR code. 2. User can verify TOTP setup. 3. User sees enrolled methods. 4. User can remove method. 5. User can generate backup codes. 6. User can use backup code once. 7. User can enroll passkey. 8. User can view trusted devices and revoke. 9. User sees their security events. 10. All actions audit logged. | M (2-4 weeks) | OPEN | Permission model may need adjustment | None |
| P0-2 | Authentication / Authorization | **No privileged re-authentication enforcement** - `check_reauth_required` exists in `mfa_service.py:885-907` but not enforced on sensitive API routes | Service method exists, sensitive actions defined in policy (`user.delete`, `role.assign`, `permission.grant`, `security.policy.update`, `connector.configure`, `data.export`, `organization.delete`), but **no middleware or dependency** checks this before sensitive mutations. | `app/services/mfa_service.py:885-907`, `app/api/v1/security.py` (policy), various mutation endpoints | Sensitive actions (delete user, assign role, change security policy) proceed with only access token - no step-up MFA required | Admin actions can be performed without fresh MFA if session is valid | **High** - Compromised session allows privilege escalation | Medium - Audit trail exists but prevention missing | P0 | P0-1 (user MFA must exist first) | 1. Create `require_reauth` dependency that checks `mfa_service.check_reauth_required` for sensitive actions. 2. Apply to sensitive endpoints: user deletion, role assignment, security policy update, data export, org deletion. 3. Return 401 with `reauth_required: true` and list of valid MFA methods. 4. Frontend: Intercept 401, show MFA challenge modal, retry with `X-Reauth-Method` header. | 1. Test: Delete user without reauth → 401. 2. Test: Delete user with valid TOTP → 200. 3. Test: Reauth expires after policy window. 4. Test: Backup code works for reauth. | 1. Sensitive actions require fresh MFA. 2. Reauth valid for policy-defined window (default 5-15 min). 3. All methods (TOTP, passkey, backup) work. 4. Audit log shows reauth event. | S (1-2 weeks) | OPEN | P0-1 | None |
| P0-3 | Enterprise Identity / SSO | **No SSO user connection flow** - Enterprise has IdP config but no "Connect your SSO account" for users | `app/enterprise/identity_service.py` has provider config, but no user-facing "Link SSO" flow. SCIM provisioning exists but only API. | `app/enterprise/identity_service.py`, `app/(app)/enterprise/page.tsx` (admin only) | Admins configure IdP, but users cannot initiate SSO login or link existing account | Enterprise customers cannot use their identity provider; manual account creation required | Medium - Workaround exists but poor UX | Low | P0 | P0-1, SSO provider test env | 1. Add "Sign in with SSO" button to login page when org has IdP configured. 2. Implement SP-initiated SAML/OIDC flow. 3. Add "Link SSO Account" in user security settings (match by email). 4. Handle JIT provisioning for new users. 5. Add IdP-initiated login support. | 1. Test: Org with OIDC → User clicks SSO → Redirected to IdP → Returns authenticated. 2. Test: Existing user links SSO → Next login uses SSO. 3. Test: JIT provisioning creates user + employee. | 1. User can sign in via configured IdP. 2. Existing user can link SSO. 3. New user provisioned via JIT. 4. IdP-initiated login works. | M-L (3-6 weeks) | OPEN | Requires real IdP test environment (Okta, Entra ID, Google) | Yes - IdP sandbox needed |
| P0-4 | Authentication / Passkeys | **Passkey implementation incomplete** - Simplified crypto, no proper attestation verification | `mfa_service.py:343-414` uses manual CBOR parsing, no `webauthn` library, attestation verification is placeholder | `app/services/mfa_service.py:343-414`, `app/api/v1/security.py:312-347` | Passkey registration stores credential ID but doesn't properly verify attestation object or extract public key | **Security vulnerability** - Invalid passkeys could be registered | **Critical** - Bypasses WebAuthn security model | High - Could allow unauthorized authenticators | P0 | `webauthn` Python library | 1. Add `webauthn` library dependency. 2. Rewrite `complete_passkey_registration` using `webauthn.verify_registration_response`. 3. Rewrite `verify_passkey_authentication` using `webauthn.verify_authentication_response`. 4. Properly store credential public key, counter. 4. Add RP ID/origin configuration via settings. | 1. Test: Register passkey on authenticator → Verified. 2. Test: Authenticate with passkey → Verified. 3. Test: Rejected invalid attestation. 4. Test: Counter increments. 5. Test: Cross-origin rejected. | 1. Passkey registration verifies attestation. 2. Authentication verifies signature + counter. 3. Invalid credentials rejected. 4. RP ID/origin enforced. | S-M (1-3 weeks) | OPEN | None | `webauthn` library (PyPI) |
| P0-5 | Commercial / Subscription | **No subscription/entitlement system** - Cannot sell, meter, or enforce limits | No subscription models, no payment integration, no entitlement enforcement in codebase | N/A (missing entirely) | All features free/unlimited | **Cannot operate as commercial SaaS** | Medium - No revenue enforcement | Low | P0 | Payment provider (Stripe/Paddle), pricing decisions | 1. Design subscription models (Plan, Subscription, Entitlement, UsageMeter). 2. Integrate Stripe/Paddle for payments. 3. Create entitlement middleware for feature gating. 4. Build admin billing UI. 5. Implement usage metering for seat-based and usage-based features. 6. Handle trials, upgrades, downgrades, cancellations, payment failures. | 1. Test: Create subscription → Features unlocked. 2. Test: Cancel → Features locked. 3. Test: Upgrade/downgrade → Entitlements updated. 4. Test: Payment failure → Grace period → Suspend. 5. Test: Usage metering recorded. | 1. Customer can purchase plan. 2. Entitlements enforced in backend. 3. Usage recorded and limited. 4. Billing admin works. | L-XL (6-12 weeks) | OPEN | Pricing, packaging, payment provider contract | Yes - Stripe/Paddle account |

---

### P1 - Critical Customer Workflows

| ID | Product Area | Exact Issue | Evidence | Source Files | Current Behavior | Expected Behavior | Customer Impact | Security Impact | Priority | Dependencies | Implementation Plan | Tests Required | Acceptance Criteria | Effort Range | Status | Blocker |
|----|--------------|-------------|----------|--------------|------------------|-------------------|-----------------|-----------------|----------|--------------|---------------------|----------------|---------------------|--------------|--------|---------|
| P1-1 | Public Website | **No public website** - No marketing, pricing, demo request, signup entry point | No `/` marketing page, no `/pricing`, `/features`, `/demo`, `/security`, `/privacy`, `/terms` | `frontend/app/page.tsx` redirects to `/home` (auth required) | Unauthenticated users see login page immediately | Professional marketing site with clear value prop, pricing, demo request, signup | **Cannot acquire customers** | None | P1 | Design, copy, assets | 1. Create Next.js App Router marketing pages: `/`, `/features`, `/pricing`, `/demo`, `/security`, `/privacy`, `/terms`. 2. Add demo request form (creates lead in backend). 3. Add "Start Free Trial" → `/register`. 4. SEO metadata, OG tags. 5. Responsive design, accessibility. | 1. Test: `/` loads < 2s. 2. Test: Demo form submits → Lead created. 3. Test: Register link works. 4. Test: Mobile responsive. 5. Test: Accessibility (axe-core). | 1. All marketing pages load. 2. Demo request creates lead. 3. Signup flow works. 4. SEO score > 90. 5. Accessible (WCAG 2.1 AA). | M (2-4 weeks) | OPEN | Design assets |
| P1-2 | Authentication / MFA | **No user-facing MFA settings** - Profile page has sessions/password but no MFA | `frontend/app/(app)/profile/page.tsx` - 220 lines, no MFA section | Profile shows personal info, password change, sessions only | Users can manage MFA methods, backup codes, passkeys, trusted devices, view security events | Users cannot secure accounts; security-conscious users will leave | High | P1 | P0-1 (same implementation) | See P0-1 implementation plan | See P0-1 | See P0-1 | M | OPEN | P0-1 |
| P1-3 | Authentication / Email Verification | **No email verification enforcement UI** - Org setting exists (`require_email_verification`) but no user-facing verification flow | `OrganizationSettings.require_email_verification`, `auth_service.verify_email` exists | Setting togglable in admin, but unverified users can still login | Unverified users blocked until verification; resend verification email; clear status in profile | Security policy incomplete; users confused | Low | P1 | P0-1 | 1. Add `email_verified_at` check in login flow. 2. If required and not verified → redirect to verification page. 3. Add "Resend verification" in profile. 4. Show verification status badge. | 1. Test: Org requires verification → Unverified user redirected. 2. Test: Resend works. 3. Test: Verified user logs in normally. | 1. Unverified users blocked when policy enabled. 2. Verification email sent. 3. Status visible in profile. | S (1 week) | OPEN | None |
| P1-4 | Authentication / Password Policy | **No password policy enforcement UI** - Org policy exists but no frontend validation/feedback | `OrganizationSecurityPolicy` has `password_min_length`, `require_uppercase`, etc. | Policies set in admin, but registration/change password forms don't show requirements or validate | Real-time password strength meter; inline validation; clear requirements | Users frustrated by rejections; weak passwords accepted | Low | P1 | P1-3 | 1. Create `usePasswordPolicy` hook fetching org policy. 2. Add strength meter to registration/change password. 3. Show requirements checklist. 4. Validate on submit. | 1. Test: Policy requires 12 chars + symbols → Meter shows. 2. Test: Invalid password rejected with specific message. 3. Test: Policy change reflected immediately. | 1. Password requirements visible. 2. Real-time feedback. 3. Server validates same rules. | S (1-2 weeks) | OPEN | None |
| P1-5 | Governance / Access Reviews | **No access review UI** - Backend complete (`mfa_service.py:1147-1354`), no frontend | `app/services/mfa_service.py:1147-1354`, `app/api/v1/security.py` has endpoints | Admins can create/start/complete reviews via API only | Admin UI: create review, assign reviewers, view items, decide (approve/revoke/modify/defer), complete | Compliance requirement unmet for enterprise | Medium | P1 | P0-1 | 1. Add "Access Reviews" tab in Settings (admin only). 2. List reviews with status. 3. Create review wizard (name, scope, frequency, reviewer). 4. Reviewer dashboard: list items, show risk, decide. 5. Complete review workflow. | 1. Test: Create review → Items populated. 2. Test: Reviewer approves/revokes → Role revoked. 3. Test: Complete review → Next scheduled. | 1. Admin can create review. 2. Reviewer sees items with risk. 3. Decisions execute backend changes. 4. Audit trail complete. | M (2-3 weeks) | OPEN | None |
| P1-6 | Security / User Security Events | **No security events UI for users** - Only in enterprise admin | `app/(app)/enterprise/page.tsx` has security events tab (admin only) | Users cannot see their own login history, failed attempts, device changes | User security dashboard: recent logins, failed attempts, MFA events, device changes, geographic anomalies | Users can't detect account compromise | Low | P1 | P0-1 | 1. Add "Security Events" section in user security settings. 2. Query `mfa_service.get_security_events` with `user_id=current_user`. 3. Display: login success/failed, MFA enroll/verify, device trust/revoke, password change. 4. Filter by date, type. | 1. Test: Login → Event appears. 2. Test: Failed login → Warning event. 3. Test: MFA enroll → Info event. 4. Test: Filter works. | 1. User sees their security timeline. 2. Event types categorized. 3. Filters work. 3. No cross-user leakage. | S (1-2 weeks) | OPEN | None |
| P1-7 | Onboarding / Invitations | **No dedicated invitation acceptance UX** - Register page works but no dedicated "accept invitation" flow | `app/register/page.tsx` handles invite token but shows same form as org registration | Invited users see "Start your company" form with org fields (confusing) | Dedicated "Join [Company]" page: shows company name/logo, pre-fills email, only asks for name/password | Invitees confused; may create duplicate org | Low | P1 | None | 1. Create `/accept-invite?token=` page. 2. Fetch invitation details (company name, inviter, role). 3. Show company branding, "You're invited to join [Company]". 4. Pre-fill email, only ask name + password. 5. On success, redirect to `/home`. | 1. Test: Invite link → Shows company name. 2. Test: Email pre-filled, read-only. 3. Test: Success → Home page. 4. Test: Expired token → Clear error. | 1. Invite page shows company context. 2. Only name/password required. 3. Clear success flow. | S (1 week) | OPEN | None |

---

### P2 - Important Commercial/Professional Capabilities

| ID | Product Area | Exact Issue | Evidence | Priority | Effort Range | Status |
|----|--------------|-------------|----------|----------|--------------|--------|
| P2-1 | Commercial | No subscription lifecycle | No models, payment, entitlements | P2 | XL (8-16 weeks) | OPEN |
| P2-2 | Commercial | No usage metering/entitlement enforcement | Features not gated | P2 | L (4-8 weeks) | OPEN |
| P2-3 | Privacy/Compliance | No data export/account closure | GDPR requirement | P2 | M (2-4 weeks) | OPEN |
| P2-4 | API | No API versioning/deprecation strategy | Breaking change risk | P2 | S (1-2 weeks) | OPEN |
| P2-5 | API | No idempotency keys | Duplicate submission risk | P2 | S (1-2 weeks) | OPEN |
| P2-6 | Integrations | No webhook retry/dead letter | Integration reliability | P2 | M (2-3 weeks) | OPEN |
| P2-7 | Enterprise | No SCIM provisioning UI | Only API exists | P2 | M (2-3 weeks) | OPEN |

---

### P3 - Usability/Polish

| ID | Product Area | Exact Issue | Evidence | Priority | Effort Range | Status |
|----|--------------|-------------|----------|----------|--------------|--------|
| P3-1 | UX | No loading/empty/error states audit | Some screens lack proper states | P3 | S (1-2 weeks) | OPEN |
| P3-2 | Accessibility | No keyboard navigation audit | Not systematically assessed | P3 | M (2-3 weeks) | OPEN |
| P3-3 | Accessibility | No screen reader semantics audit | Not systematically assessed | P3 | M (2-3 weeks) | OPEN |
| P3-4 | Accessibility | No contrast/color audit | Not systematically assessed | P3 | S (1 week) | OPEN |
| P3-5 | Responsive Design | No responsive design audit | Tables may break on mobile | P3 | S (1-2 weeks) | OPEN |
| P3-5 | i18n | No UI string internationalization | Only org-level locale | P3 | M (2-4 weeks) | OPEN |
| P3-7 | Onboarding | No user onboarding/tour | First-time users dropped into dashboard | P3 | M (2-3 weeks) | OPEN |

---

## Implementation Order (Recommended)

1. **P0-1** User-facing MFA settings page (enables P0-2, P1-2, P1-6)
2. **P0-4** Passkey implementation fix (security)
3. **P0-2** Privileged re-auth enforcement (depends on P0-1)
4. **P1-1** Public marketing website (customer acquisition)
5. **P1-3** Email verification enforcement UI
6. **P1-4** Password policy UI
7. **P1-7** Invitation acceptance UX
8. **P1-5** Access reviews UI
9. **P1-6** User security events UI
10. **P0-3** SSO user connection flow (requires IdP test env)
11. **P0-5** Subscription system (parallel track, long)
12. **P2-3** Data export/account closure
13. **P2-4** API versioning
14. **P2-5** Idempotency keys
14. **P3-4** Contrast/color audit (quick win)
15. **P3-1** Loading/empty/error states audit
...

---

## External Dependencies Blocking Progress

| Dependency | Blocks | Required For | Status |
|------------|--------|--------------|--------|
| `webauthn` Python library | P0-4 | Passkey fix | Available on PyPI |
| Real IdP test environment (Okta/Entra ID/Google) | P0-3 | SSO testing | Not configured |
| Stripe/Paddle account + pricing approval | P0-5 | Subscription system | Not configured |
| Design assets for marketing site | P1-1 | Public website | Not created |
| Accessibility testing tools (axe-core, screen readers) | P3-2, P3-3 | Accessibility audit | Available |

---

## Notes

- **Do not implement P0-5 (subscription) before P0-1/P0-2/P1-1** - Subscription is a long parallel track; core security and customer acquisition come first.
- **P0-3 (SSO) requires external IdP** - Mark as BLOCKED until test environment available; implement OIDC first (simpler than SAML).
- **Passkey fix (P0-4) should use `webauthn` library** - Don't roll your own crypto.
- **Permission model change needed for P0-1** - Regular users need `security:mfa:read` and `security:mfa:manage` for self-service. Either add to default role or create self-service permission boundary.
- **All new UI must follow existing design system** - Use `Button`, `Input`, `Card`, `Modal`, `Dropdown`, `Badge`, `Spinner` from `@/components/ui`.