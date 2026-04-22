# Auth And Public Form Hardening Plan

This document defines the recommended hardening path for the two public-facing CCHIS attack surfaces currently exposed through the frontend:

- the dashboard login flow
- the public access-request form

It is intentionally an implementation-oriented security plan, not a generic security memo.

It is based on:

- the current auth and public-form routes in `frontend/app/login/page.tsx` and `frontend/app/request-access/page.tsx`
- the backend auth and access-request views in `backend/accounts/views.py`
- the current serializer and validation direction in `backend/accounts/serializers.py`
- the current throttle configuration in `backend/core/settings.py`
- the related security direction in `docs/TOTP_2FA_HARDENING_PLAN.md`

The goal is to reduce abuse, credential attacks, enumeration risk, bot traffic, and spam without turning the product into an unusable security obstacle course.

## Status Summary

Current implementation status:

- baseline login throttling exists via the `auth_login` throttle scope
- baseline access-request throttling exists via the `access_request` throttle scope
- login success and failure events are already audit-logged
- TOTP pre-auth exists for roles that require second-factor verification
- the access-request form now has basic client validation and matching backend validation for phone normalization and county/ward consistency
- access-request duplicate suppression now exists for matching pending requests within the configured cooling-off window
- repeated access-request acknowledgement emails are now suppressed when a duplicate pending request is detected
- backend honeypot validation and minimum submission-age checks now exist for the public form
- frontend honeypot and submission timestamp support now exist for the public form
- conditional login cooldown logic now exists after repeated failed sign-in attempts
- repeated 2FA verification failures now feed temporary cooldown logic
- repeated refresh-token abuse now feeds temporary cooldown logic
- Turnstile support now exists for the access-request form and as a conditional login challenge path
- admin review now includes duplicate-related access-request signals
- access-request review metadata now persists source IP and whether a challenge was successfully completed

What is still pending or only partially complete:

- throttle defaults have been intentionally tightened in code, but still need production tuning against real traffic and deployment behavior
- login abuse controls are stronger, but still not independently layered by username-only and IP-only counters
- repeated 2FA abuse and refresh abuse are now better backstopped, but still may need stricter thresholds after real traffic is observed
- public-form content quality filtering is still limited; junk, repetitive, or nuisance submissions are not yet screened aggressively
- observability definitions exist, but operational dashboards, emitted counters, and reviewer-facing abuse metadata are still incomplete
- Turnstile rollout still depends on final deployment configuration and enablement decisions
- the current public flows still assume JavaScript-driven UX and have not been hardened for true no-JS degradation
- username-first login remains optional future work, not current hardening scope

## No Legacy Preservation Requirement

CCHIS does not currently have production-scale public traffic patterns, established external login UX commitments, or legacy anti-bot integrations that require compatibility protection.

That means this plan should favor the cleanest credible hardening path rather than preserving draft public-flow behavior.

Explicit rules:

- do not keep weak public-form behavior for convenience if stronger defaults are available
- do not preserve prototype login UX if it encourages brute-force or enumeration abuse
- do not add frontend-only security that lacks backend enforcement
- do not treat CAPTCHA as the only answer when lower-friction server controls should exist first
- do not assume any public endpoint is low-risk simply because the app is early-stage

The practical rule is simple:

- harden both frontend and backend directly, because there is no production legacy surface worth preserving over security

## Purpose

This plan exists to make the following surfaces safer:

- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/verify-2fa/`
- `POST /api/v1/auth/access/request/`
- `GET /api/v1/auth/access/request/options/`
- the associated Next.js login and public request-access pages

It should address:

- brute-force login attempts
- username and account enumeration
- bot-driven request spam
- duplicate request flooding
- scripted abuse against public forms
- noisy operational review queues

## Recommendation Summary

The recommended hardening sequence is:

1. tighten and finish the backend controls that remain incomplete
2. finish deployment-grade challenge rollout and configuration
3. improve observability, reviewer signals, and operational response
4. revisit login UX evolution only if it still adds value after the above

This is the right order because the initial backend and frontend first slice already exists. The remaining work is now about tightening policy, closing abuse-path gaps, and making the protection operationally visible.

## Design Rules

- Every important frontend validation or anti-bot check must have a backend equivalent or backend backstop.
- Public routes should leak as little account-state information as possible.
- Rate limiting should be layered by route, IP, and abuse pattern where possible.
- The frontend should discourage abuse without punishing legitimate users by default.
- Security responses should stay generic and calm rather than revealing internal auth state.
- Logging should support investigation without storing unnecessary sensitive raw data.
- Higher-friction defenses such as CAPTCHA should be used intentionally, not as a substitute for missing server controls.

## Attack Surface Inventory

### Login Surface

Relevant user-visible surface:

- `frontend/app/login/page.tsx`

Relevant backend surface:

- `backend/accounts/views.py` login and 2FA verification endpoints

Primary risks:

- credential stuffing
- brute-force password attacks
- username enumeration
- role discovery through auth behavior
- 2FA token abuse
- refresh and retry flooding

### Access-Request Surface

Relevant user-visible surface:

- `frontend/app/request-access/page.tsx`

Relevant backend surface:

- `backend/accounts/views.py` access-request endpoints
- `backend/accounts/serializers.py` access-request validation

Primary risks:

- bot spam
- duplicate request flooding
- nuisance submissions using junk or malicious input
- admin review queue poisoning
- abuse of acknowledgement email delivery
- reconnaissance against county and ward public option data

## Login UX Question: Username First

The suggestion to present only the username field first is worth considering, but it should be treated as a UX and exposure-shaping decision, not as a primary security control.

### Recommendation

Do not rely on a username-first login flow as the main defense.

It can be useful if implemented carefully, but only after backend protections are already strong.

### Why It Can Help

- it can reduce the immediate visibility of the full credential form
- it gives the frontend a place to introduce bot checks or subtle pacing before password entry
- it can support identity-specific next steps later such as mandatory 2FA routing or tailored auth policy messaging

### Why It Is Not Enough By Itself

- attackers can still automate the first step
- it may increase username enumeration risk if the first step confirms whether an account exists
- it does not prevent brute-force attempts unless the backend treats the first step and second step as protected auth events
- it can make login feel more complex without materially improving security if the backend behavior stays unchanged

### Recommended Position

Treat username-first as an optional phase-two enhancement, not a phase-one security requirement.

If implemented, it should follow these rules:

- never confirm whether the username exists
- return the same generic response shape for valid and invalid usernames
- apply throttling to the pre-password username step
- use short-lived backend-issued login continuation tokens if the flow becomes multi-step
- keep the final password verification and account-lockout logic backend-enforced

The core judgment is:

- username-first can be a useful refinement, but only if it is paired with strong backend controls and careful anti-enumeration behavior

## Phase 1: Backend-First Baseline Hardening

This phase is partially complete and should be treated as a finish-and-tighten phase before any major login UX restructuring.

### Access-Request Backend Controls

Completed:

- deduplication windows now exist for matching `contact_email` and normalized `phone_number` on pending requests
- repeated acknowledgement emails are suppressed when duplicate pending requests are detected
- honeypot validation now exists on the backend
- minimum submission-age validation now exists on the backend
- server-side normalization exists for public-form email, phone, and ward/county consistency checks

Still needed:

- tune `access_request` throttle values for real deployment traffic and review whether the current tighter defaults are sufficient
- decide whether duplicate suppression should expand to include IP-aware fingerprinting for better spam clustering
- reject obviously malformed, excessively repetitive, or low-signal junk content more intentionally
- cap request body sizes and field lengths defensively at the request-handling layer, not only through serializer and model limits
- decide whether public option-data enumeration risk needs its own throttling or caching policy

### Login Backend Controls

Completed:

- generic login failure responses exist for invalid credential handling
- repeated login failures now feed temporary cooldown logic
- conditional login challenge escalation now exists after repeated failures when enabled
- failed login, successful login, failed 2FA, successful 2FA, and refresh outcomes are already audit-visible

Still needed:

- tune `auth_login`, `auth_2fa`, and `auth_refresh` throttle policy for real deployment traffic beyond the now-tightened code defaults
- add separate counters or lockout logic keyed by username-only and IP-only, not only the current combined pattern plus DRF identity
- decide whether repeated 2FA failures and repeated refresh abuse should escalate further into challenge requirements, not only cooldowns
- confirm the production IP extraction and proxy-awareness path used for throttling before rollout
- keep continuation-token logic optional unless a real multi-step login flow is introduced later

### Shared Backend Controls

Completed:

- abuse-focused structured logging now exists for login, duplicate suppression, honeypot rejection, suspicious timing, and challenge failures
- duplicate-request suppression events are now recorded
- honeypot hits and suspicious submission timing are now recorded
- observability inventory now defines the metrics expected for these flows

Still needed:

- emit and operationalize the defined counters, rather than only documenting them in the metric inventory
- extend reviewer-visible abuse metadata beyond the signals already exposed today, especially around throttling history, duplicate suppression history, and recent challenge failures
- confirm deployment proxy settings so throttling and challenge verification use the correct client IP data

## Phase 2: Low-Friction Frontend Defenses

This phase is mostly complete for the public form and partially complete for login.

### Access-Request Frontend Controls

Completed:

- a hidden honeypot input now exists
- client submission timing is now captured and sent to the backend
- field-level validation is already relatively calm and consistent with backend rules
- success messaging is already generic

Still needed:

- review whether the remaining validation copy is more specific than it needs to be for a public form
- decide whether public option loading needs a safer degraded fallback when JavaScript is delayed or unavailable

### Login Frontend Controls

Completed:

- login error messaging is generic for common credential failures
- the current UI does not reveal username validity before credential verification completes
- the browser session now applies a small cooldown or challenge path after repeated failures

Still needed:

- keep frontend behavior aligned with backend challenge policy so local friction does not drift from server-side enforcement
- if username-first is adopted later, ensure the first step remains visually neutral and enumeration-safe

### Shared Frontend Controls

- avoid exposing internal field names, implementation details, or auth state hints in the UI copy
- maintain accessible error handling so legitimate users can recover without support burden

Still needed:

- decide whether both public flows need true no-JavaScript fallback behavior or whether JavaScript dependency is acceptable for the deployment model

## Phase 3: Stronger Challenge Controls

This phase is largely implemented in code, but still pending final rollout and operational tuning.

Recommended direction:

- prefer Cloudflare Turnstile if infrastructure and deployment model support it cleanly
- use challenge escalation selectively rather than forcing it on every single interaction if that is operationally possible

Suggested rollout:

1. enable Turnstile for the public access-request form in deployment once hostname, secret, and site key are configured correctly
2. keep login Turnstile conditional on repeated suspicious attempts tied to backend failure counters
3. avoid a permanent login widget unless observed abuse shows the conditional policy is insufficient
4. verify that rollout includes correct proxy-aware client IP handling and hostname enforcement

Do not treat challenge widgets as the only protection.

They should supplement:

- throttling
- deduplication
- backend validation
- observability

## Phase 4: Login Flow Evolution

This phase is where the username-first idea can be considered seriously if still desirable after baseline hardening.

### Option A: Keep Current Username And Password Form

Benefits:

- simplest UX
- smallest implementation change
- lowest risk of accidental enumeration bugs introduced by a new step

Requirements:

- stronger backend rate limiting
- stronger failure handling
- optional conditional challenge after repeated failures

### Option B: Introduce Username-First Progressive Disclosure

Benefits:

- can create a cleaner staged auth flow
- provides a natural place for subtle pacing or continuation-token logic
- can align well with later security policy messaging

Risks:

- easier to introduce enumeration bugs
- more moving parts in the auth contract
- more frontend state to protect and test

Decision rule:

- choose this only if we are willing to implement it as a real backend-auth phase, not a cosmetic frontend split

Recommended preference today:

- keep the existing single-screen credential entry for now
- harden the backend first
- revisit username-first only if we want deliberate staged auth after hardening phase one

## Phase 5: Observability And Admin Review

Security hardening is incomplete without operational visibility.

Add or expand:

- dashboards for failed login volume, 2FA failure volume, throttled login attempts, and access-request rejection volume
- counts of duplicate request suppression
- counts of honeypot hits
- counts of suspected bot submissions blocked by timing rules or challenge failures
- admin review indicators for unusually frequent submissions from the same email, phone number, or IP

Admin review UX should support:

- seeing duplicate or near-duplicate access requests grouped together
- seeing when a request was rate-limited or challenge-protected
- seeing minimal but useful abuse metadata without overwhelming reviewers

Current status:

- duplicate email, duplicate phone, duplicate IP, challenge completion, and related pending-request review signals already exist
- the observability inventory already names the required auth and access-request metrics

Still needed:

- actual emitted counters and dashboards for the defined auth and access-request abuse metrics
- reviewer-visible signals for IP reuse, recent throttling, recent challenge failures, and suppressed duplicate history
- grouped or filterable review surfaces that make abuse clusters easier to inspect operationally

## Recommended Implementation Order

The practical implementation order should be:

1. tighten backend login and access-request throttling and confirm deployment IP/proxy behavior
2. deepen auth abuse controls for repeated 2FA failures and refresh abuse
3. strengthen public-form content quality screening and defensive request-size handling
4. operationalize abuse metrics and enrich admin review metadata
5. enable and validate Turnstile in deployment for access-request and conditional login challenge paths
6. revisit username-first only if we still want staged auth after the above controls exist

## Next Deliverable

The next hardening slice should implement:

- stricter reviewed throttle settings for `access_request` and `auth_login`
- explicit abuse handling for repeated 2FA failures and suspicious refresh retry patterns
- richer access-request review metadata, especially IP-related and challenge-related signals
- emitted metrics and dashboards for auth and public-form abuse patterns
- final Turnstile deployment configuration and rollout validation

This is the best next slice because the baseline hardening work is already in place, and the remaining risk now comes from untuned policy, incomplete observability, and rollout details rather than missing first-line controls.

## Out Of Scope For This Plan

- replacing JWT auth entirely
- introducing passwordless auth
- introducing third-party identity providers
- broad WAF or CDN vendor design beyond noting where challenge controls may fit
- a full incident response playbook

Those can be planned later if the project scope expands.
