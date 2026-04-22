# TOTP 2FA Hardening Plan

This document defines the planned two-factor authentication hardening path for privileged CCHIS dashboard users.

It is intentionally a follow-on security plan, not a blocker for core v1 dashboard delivery.

It is based on:

- the current auth direction in `README.md`
- the dashboard direction in `docs/NEXTJS_DASHBOARD_V1_PLAN.md`
- the role model in `docs/RBAC_AND_ROLE_ENFORCEMENT_PLAN.md`

The goal is to add a credible second authentication factor for privileged dashboard roles without delaying the core prototype.

## Status Summary

Current implementation status:

- Phase 1: completed in planning and backend auth-contract implementation
- Phase 2: completed in backend verification foundation
- Phase 3: completed in frontend verification flow
- Phase 4: completed in pilot hardening

What is decided now:

- TOTP is the planned second factor for privileged dashboard users
- 2FA will not block core v1 delivery
- the login contract is allowed to change cleanly to support `requires_2fa`
- privileged dashboard users should move through a pre-auth step before final token issuance
- role-based 2FA policy is now exposed through auth responses for frontend consumption
- enrolled privileged users now receive a short-lived pre-auth token instead of final JWTs at login

What is not implemented yet:

- setup and enrollment UX for enabling TOTP outside admin or direct data operations
- richer setup and recovery UX such as QR enrollment, backup codes, or device trust
- optional expansion of mandatory 2FA to additional roles such as `ANALYST`

## No Legacy Preservation Requirement

CCHIS does not currently have production 2FA users, production auth-recovery traffic, or legacy verification flows that need compatibility protection.

That means this plan should define the cleanest future 2FA path rather than accommodating draft auth behavior.

Explicit rules:

- do not preserve old login response shapes if they need to evolve to support `requires_2fa`
- do not maintain parallel draft verification flows once the intended TOTP flow is implemented
- do not add migration complexity for prototype-only auth behavior that never served production users
- replace incomplete or placeholder second-factor ideas directly with the chosen TOTP design

The practical rule is simple:

- prefer a clean 2FA contract over backward compatibility, because there is no production data or live verification flow to protect

## Purpose

Add TOTP-based two-factor authentication for dashboard users who can access higher-sensitivity operational capabilities such as:

- alert triggering
- broader county-wide operational visibility
- administrative account access

This plan is for pilot hardening or the period immediately after the core dashboard v1 is working.

It should not block:

- basic dashboard delivery
- role-aware access control
- baseline auth hardening

## Recommendation Summary

The recommended security sequence is:

1. ship secure password-based auth, JWT handling, RBAC, audit logging, and login throttling first
2. add TOTP as a second factor for privileged dashboard roles next
3. make 2FA mandatory for the highest-risk roles before or during pilot hardening

This is the right balance of:

- security
- delivery speed
- operational credibility

## Why TOTP

Use TOTP as the planned first 2FA mechanism because it:

- works with common authenticator apps
- avoids SMS delivery cost and dependency
- is stronger than SMS OTP for dashboard security
- stays separate from operational SMS workflows already used elsewhere in the platform

Preferred authenticator compatibility:

- Google Authenticator
- Microsoft Authenticator
- Authy
- any TOTP-compatible app

Do not use SMS as the primary dashboard 2FA method unless deployment constraints force it later.

## Roles And Policy Direction

Recommended rollout policy:

- mandatory first for:
  - `ADMIN`
  - `SUPERVISOR`
- optional initially for:
  - `ANALYST`
- not required for:
  - `CHV`
  - USSD users
  - SMS recipients

This policy can tighten later, but v1 should stay focused on privileged dashboard users.

Phase 1 decision:

- treat `ADMIN` and `SUPERVISOR` as the default privileged roles for first implementation
- keep `ANALYST` available as an optional later enforcement target
- do not design 2FA around CHV, SMS, or USSD flows

## Design Rules

- 2FA extends the existing login flow rather than replacing it.
- Password verification still happens first.
- The user must not receive full dashboard tokens until second-factor verification succeeds when 2FA is required.
- 2FA policy must remain backend-enforced.
- The frontend should implement a simple, calm verification experience, not a sprawling security center.
- Recovery and management features should stay minimal in the first pass.
- If the current login contract needs to change to support TOTP cleanly, make the change directly rather than preserving prototype-only auth behavior.

## Auth Flow Shape

The intended flow is:

1. user submits username and password
2. backend validates primary credentials
3. if 2FA is not required:
  - return normal access token, refresh token, and user payload
4. if 2FA is required:
  - return a temporary pre-auth token and a `requires_2fa` flag
5. frontend routes the user to a TOTP verification page
6. user submits the one-time code
7. backend verifies the code
8. backend returns final access token, refresh token, and user payload

## Suggested API Contract Direction

### Login Response

Current login behavior should evolve to support a second-factor branch.

Suggested response when 2FA is required:

```json
{
  "requires_2fa": true,
  "temp_token": "temporary-pre-auth-token"
}
```

Suggested response when 2FA is not required:

```json
{
  "access": "jwt-access-token",
  "refresh": "jwt-refresh-token",
  "user": {
    "id": 1,
    "username": "admin",
    "role": "ADMIN"
  }
}
```

### Verify 2FA Endpoint

Suggested endpoint:

- `POST /api/v1/auth/verify-2fa/`

Suggested request shape:

```json
{
  "token": "temporary-pre-auth-token",
  "code": "123456"
}
```

Suggested success response:

```json
{
  "access": "jwt-access-token",
  "refresh": "jwt-refresh-token",
  "user": {
    "id": 1,
    "username": "admin",
    "role": "ADMIN"
  }
}
```

Failure response principles:

- invalid code should return a safe generic error
- expired temp token should require re-login
- repeated failures should be throttle-aware

Phase 1 contract rule:

- we should change the login response shape directly if needed instead of preserving prototype-only auth responses
- there is no production 2FA contract or production verification flow to preserve

## Backend Implementation Direction

The backend will need:

- a TOTP secret per enrolled user
- a way to mark whether 2FA is enabled or required
- a temporary pre-auth token or equivalent partial-auth state
- a `verify-2fa` endpoint
- safe failure handling and throttling

Recommended first-pass backend scope:

- store TOTP secret securely
- enroll privileged users administratively or through a minimal setup path
- verify TOTP codes server-side
- issue final JWT tokens only after successful verification

Defer unless the project explicitly chooses to add them now:

- multiple second-factor methods
- remember-this-device behavior
- broad self-service 2FA management UI
- advanced recovery tooling

## Frontend Requirements

If TOTP is implemented, the frontend needs one additional auth page:

- `/verify-2fa`

Required page behavior:

- same auth visual system as login
- 6-digit code entry
- verify action
- back-to-login action
- loading state
- invalid-code state
- expired-session state

Suggested page copy:

- title: `Two-Factor Verification`
- subtitle: `Enter the 6-digit code from your authenticator app.`

Frontend flow rules:

- do not treat the temporary token as a full session
- do not render protected dashboard content before verification completes
- clear temp state on logout, expiration, or verification failure requiring restart

Phase 1 frontend decision:

- the first frontend slice should be a single focused verification page rather than a broad 2FA settings center
- keep the UX aligned with the existing login card and auth layout

## Setup And Enrollment Direction

The first implementation does not need a large self-service setup experience.

Recommended initial options:

1. admin- or operator-assisted enrollment for privileged users
2. a minimal later setup screen that shows QR code and confirmation if needed

This means the verification screen should be planned now, while the broader setup UX can remain a later step.

## Security And Safety Rules

- 2FA must never weaken the existing login flow.
- Temporary pre-auth tokens must be short-lived.
- Final access and refresh tokens must only be issued after successful second-factor verification.
- Failed verification attempts should be rate-limited.
- Error messages should not leak enrollment or secret details.
- Audit important events such as:
  - 2FA required
  - 2FA verification success
  - repeated verification failure
  - 2FA enablement changes if tracked

## Implementation Phases

### Phase 1: Policy And Contract Definition

- define which roles require 2FA
- define login response branch for `requires_2fa`
- define temporary token semantics
- define verify endpoint contract
- explicitly allow clean auth-contract changes instead of preserving draft login behavior

Status:

- completed

Implemented now:

- auth settings can declare required and optional 2FA roles
- login responses explicitly include `requires_2fa`
- authenticated user payloads expose `two_factor_policy`
- the current implementation keeps `requires_2fa` false until real enrollment and verification infrastructure is added in Phase 2

Phase 1 decisions captured in this document:

- `ADMIN` and `SUPERVISOR` are the first mandatory-target roles
- `ANALYST` remains optional initially
- successful password verification may return either full tokens or `{ "requires_2fa": true, "temp_token": "..." }`
- `POST /api/v1/auth/verify-2fa/` is the planned verification endpoint
- the temporary token is a short-lived pre-auth artifact, not a real dashboard session
- no legacy response shape or draft second-factor flow needs to be preserved because there is no production data or live auth flow to protect

Definition of done:

- the auth flow is clearly specified without blocking current login work

### Phase 2: Backend Verification Foundation

- add enrolled-user 2FA fields
- add TOTP verification capability
- add temporary pre-auth token handling
- add `POST /api/v1/auth/verify-2fa/`
- add throttle and safe failure behavior

Status:

- completed

Implemented now:

- user records include `is_totp_enabled` and `totp_secret`
- short-lived `PreAuthToken` records back the partial-auth session
- login returns `requires_2fa` plus `temp_token` for enrolled users who must complete verification
- `POST /api/v1/auth/verify-2fa/` verifies TOTP codes and only then issues final JWTs
- invalid codes fail safely, invalid pre-auth tokens are rejected, and verification is throttle-scoped
- auth audit events now capture `TWO_FACTOR_REQUIRED`, `TWO_FACTOR_VERIFIED`, and `TWO_FACTOR_FAILED`

Definition of done:

- the backend can require and verify TOTP for an enrolled user

### Phase 3: Frontend Verification Flow

- add `/verify-2fa`
- store and pass temporary token safely
- branch login flow based on `requires_2fa`
- route verified users into the normal dashboard session

Status:

- completed

Implemented now:

- the frontend auth provider stores temporary pre-auth state separately from the real dashboard session
- the login page branches into `/verify-2fa` when backend login returns `requires_2fa`
- `/verify-2fa` verifies a 6-digit code against the backend and only then establishes the normal JWT-backed session
- protected dashboard routes still require a real authenticated session and do not treat the temporary token as access
- users can abandon the pending verification state and return cleanly to login

Definition of done:

- privileged users can complete login through password plus TOTP

### Phase 4: Pilot Hardening

- make 2FA mandatory for chosen privileged roles
- review audit and recovery expectations
- refine setup or enrollment UX if needed

Status:

- completed

Implemented now:

- `ADMIN` and `SUPERVISOR` accounts are now blocked from dashboard login until TOTP enrollment exists
- enrolled privileged users still follow the pre-auth plus verification flow before final JWT issuance
- Django admin exposes TOTP enrollment fields so pilot operations can enable TOTP without preserving any legacy flow
- audit events now distinguish missing mandatory enrollment from normal invalid-login behavior

Still deferred:

- self-service QR enrollment or broader setup UX
- backup codes, device trust, or richer recovery mechanics
- expansion of mandatory enforcement beyond the initial privileged roles

Definition of done:

- pilot access for privileged dashboard users has meaningful second-factor protection

## Test Expectations

Add tests for:

- login response when 2FA is not required
- login response when 2FA is required
- valid TOTP verification issuing final tokens
- invalid TOTP verification rejection
- expired temporary token rejection
- throttling behavior on repeated failures
- frontend login branch into verification page
- frontend expired or invalid verification state handling

## Relationship To Other Plans

This plan should be sequenced after:

- `docs/RBAC_AND_ROLE_ENFORCEMENT_PLAN.md`
- `docs/NEXTJS_DASHBOARD_V1_PLAN.md`

This plan should stay coordinated with:

- `docs/DASHBOARD_DATA_AND_ROLE_AWARE_UX_PLAN.md`

Reason:

- 2FA policy depends on knowing which roles are privileged
- the frontend auth flow needs the same session and role model already defined elsewhere

## Immediate Next Step

Do not implement this before the baseline dashboard auth flow is stable.

Instead:

1. finish password-based dashboard auth
2. finish backend RBAC enforcement
3. confirm which roles are privileged for pilot hardening
4. then implement the TOTP login extension and verification page

After that, 2FA becomes a focused hardening step instead of a distraction during core v1 build-out.
