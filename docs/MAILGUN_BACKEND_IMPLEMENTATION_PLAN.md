# Mailgun Backend Implementation Plan

This document defines the backend work needed before frontend auth-recovery and official communication flows are fully implemented.

It is intentionally separate from the Next.js dashboard plan.

The reason is simple:

- forgot-password
- reset-password
- request-access feedback
- future official outbound communication

all depend on a trustworthy backend email capability and should not be improvised in the frontend.

## Status Summary

Current implementation status:

- Phase 1: completed
- Phase 2: completed
- Phase 3: completed
- Phase 4: completed
- Phase 5: optional follow-on refinements, deferred

What is implemented now:

- backend email provider abstraction via `backend/communications/`
- `StubEmailProvider` and `MailgunEmailProvider`
- environment-based Mailgun configuration in `backend/core/settings.py`
- backend-owned password reset request and confirm endpoints
- password reset token model and refresh-token invalidation after reset
- backend-owned access request submission endpoint
- admin review endpoints for listing, approving, and rejecting access requests
- acknowledgement and decision emails routed through the communications provider boundary
- richer email delivery logging for provider resolution and delivery summaries

Current implemented endpoints:

- `POST /api/v1/auth/password-reset/request/`
- `POST /api/v1/auth/password-reset/confirm/`
- `POST /api/v1/auth/access/request/`
- `GET /api/v1/auth/access/requests/`
- `POST /api/v1/auth/access/requests/<id>/approve/`
- `POST /api/v1/auth/access/requests/<id>/reject/`

Remaining follow-on work is now optional hardening rather than a missing core flow.

These items are intentionally deferred because they are not blockers for the current backend-owned email implementation.

## No Legacy Preservation Requirement

CCHIS does not currently have production email workflows, production password-recovery traffic, or legacy communication flows that need compatibility protection.

That means this plan should prefer the cleanest backend-owned implementation rather than preserving draft or prototype behavior.

Explicit rules:

- do not preserve placeholder frontend recovery flows that were never backed by production-safe backend behavior
- do not build compatibility layers for old email request shapes, draft endpoints, or temporary manual processes unless they remain part of the intended v1 contract
- do not maintain parallel password-reset or request-access workflows once the real backend flow exists
- replace prototype communication assumptions directly with the new Mailgun-backed provider boundary

The practical rule is simple:

- choose the cleanest secure implementation, because there is no production data or live user workflow that would be harmed by replacing draft behavior

## Purpose

Add a secure, explicit backend email delivery capability using Mailgun so CCHIS can support:

- password recovery
- request-access acknowledgements and review outcomes
- future official system communications

## Scope For First Implementation

The first Mailgun backend slice should support:

1. email provider abstraction
2. Mailgun transport implementation
3. environment-based configuration
4. safe local fallback behavior
5. password-reset workflow support
6. request-access workflow support
7. audit and operational logging around outbound official communication

## Design Rules

- Backend owns all official communication logic.
- Frontend must never call Mailgun directly.
- Mailgun secrets must stay in backend environment configuration only.
- Email transport must follow the same provider-boundary principle already used for SMS.
- Official communication templates and transport should be separable.
- Failure states must be observable and safe.
- We do not need to preserve legacy recovery or request-access flows if they conflict with the cleaner backend-owned design.

## Proposed Architecture

### 1. Provider Boundary

Create an email provider abstraction similar in spirit to the SMS provider boundary.

Suggested module shape:

- `backend/communications/` or a similar future-safe module
- `providers.py`
- `services.py`
- `templates.py` or template helpers

Suggested interfaces:

- `EmailProvider`
- `DeliveryResult` or email-specific equivalent
- `get_email_provider(...)`

Suggested providers:

- `StubEmailProvider`
- `MailgunEmailProvider`

Why:

- keeps Mailgun from becoming the architecture
- allows local development without real email delivery
- allows future provider changes without rewriting auth flows

### 2. Environment Configuration

Add explicit backend configuration for:

- `EMAIL_PROVIDER`
- `MAILGUN_API_KEY`
- `MAILGUN_DOMAIN`
- `MAILGUN_BASE_URL`
- `MAILGUN_FROM_EMAIL`
- optional:
  - `MAILGUN_FROM_NAME`
  - `MAILGUN_REPLY_TO`

Defaults:

- local default should be stubbed or disabled safely
- staging and production must require explicit configuration

### 3. Password Reset Backend Flow

Add a backend-owned password-reset workflow.

Required endpoints:

- `POST /api/v1/auth/password-reset/request/`
- `POST /api/v1/auth/password-reset/confirm/`

Request flow:

- user submits username or email
- backend creates a short-lived reset token
- backend sends reset email through Mailgun provider
- response must not leak whether the account exists

Confirm flow:

- user submits token plus new password
- backend validates token
- backend sets new password
- backend invalidates existing refresh sessions if required
- backend records auth audit event

Security rules:

- no account enumeration
- signed or random time-bound tokens only
- single-use tokens preferred
- expired and invalid token states handled safely

### 4. Request Access Backend Flow

Add a backend-owned access request workflow.

Suggested endpoint:

- `POST /api/v1/auth/access/request/`

Suggested stored fields:

- full name
- organization
- desired role
- contact email
- optional message
- submission time
- review status

Suggested statuses:

- `PENDING`
- `APPROVED`
- `REJECTED`

Suggested communication events:

- acknowledgement email on submission
- approval email
- rejection or follow-up email

Operational rule:

- request access is an official communication surface and should use the same backend email provider boundary

### 5. Templates And Official Communication Types

Define the first communication templates explicitly:

- password reset request
- password reset success or confirmation
- request access acknowledgement
- request access approved
- request access rejected or needs follow-up

Template rules:

- plain language
- minimal sensitive detail
- no secrets in email body except reset link or tokenized URL
- branding should be light and operationally credible

## Security And Safety Rules

- Never reveal whether a username or email exists during password reset request.
- Never expose Mailgun credentials in frontend code or browser calls.
- Log provider success or failure safely without leaking tokens or email content.
- Treat password reset as a security-sensitive flow:
  - audit completion
  - invalidate existing sessions after reset
- Rate-limit password reset requests.
- Rate-limit request-access submissions.

## Observability Rules

Add visibility for:

- email delivery attempts
- delivery success or failure
- password reset request volume
- password reset confirmation outcomes
- request-access submission volume

Add logs for:

- provider resolution
- provider failure
- delivery response summary

Add audit where appropriate for:

- password reset completion
- access approval or rejection if a review workflow is added

## Phase 5: Optional Follow-On Refinements

Status:

- optional
- deferred until there is a concrete operational need
- not a blocker for the current Mailgun-backed backend flow

This phase exists to capture improvements worth revisiting later without treating them as missing delivery work now.

Planned follow-on items:

- polish email copy and branding further if we want a more polished operational voice
- decide later whether access-request approvals and rejections need dedicated operational audit records beyond the current review workflow
- add Mailgun webhook ingestion only if delivery-event tracking, bounce visibility, or provider-event analytics become necessary

Implementation rule:

- do not add webhook ingestion, review complexity, or branding churn just to preserve hypothetical future flexibility
- prefer the cleanest current-state implementation because there is no production legacy email flow or production data to protect

## Recommended Implementation Phases

### Phase 1: Email Provider Foundation

- define email provider interface
- add stub provider
- add Mailgun provider
- add environment configuration
- add basic delivery result typing

Definition of done:

- backend can send a safe test email through stub and Mailgun paths

Status:

- completed

### Phase 2: Password Reset

- add password-reset request endpoint
- add password-reset confirm endpoint
- add token generation and validation
- add Mailgun-backed reset email
- add audit and session invalidation behavior

Definition of done:

- frontend can safely wire forgot-password and reset-password flows

Status:

- completed

### Phase 3: Request Access

- add access-request data model if needed
- add submission endpoint
- add acknowledgement email
- define review status lifecycle

Definition of done:

- frontend can wire request-access form to a real backend flow

Status:

- completed

### Phase 4: Official Communication Hardening

- add template organization
- add better delivery logging
- add admin or ops review path if needed
- add rate limits and abuse review

Definition of done:

- official communication is operationally credible, not just technically possible

Status:

- completed

Current note:

- template logic is now centralized and reusable
- email delivery emits provider-resolution and delivery-summary logs
- admin review workflow exists for access requests via list, approve, and reject endpoints

## Suggested Backend Endpoints

Auth-recovery:

- `POST /api/v1/auth/password-reset/request/`
- `POST /api/v1/auth/password-reset/confirm/`

Request access:

- `POST /api/v1/auth/access/request/`

Possible later admin review endpoints:

- `GET /api/v1/auth/access/requests/`
- `POST /api/v1/auth/access/requests/<id>/approve/`
- `POST /api/v1/auth/access/requests/<id>/reject/`

## Test Expectations

Add tests for:

- stub provider resolution
- Mailgun provider resolution
- missing Mailgun credentials failure path
- password reset request does not leak user existence
- valid reset token changes password
- invalid or expired token is rejected safely
- existing sessions are invalidated after successful reset if that policy is chosen
- request-access submission succeeds
- request-access acknowledgement dispatch path

## Relationship To Frontend Work

Frontend can now wire these pages to the real backend:

- Forgot Password
- Reset Password
- Request Access

Frontend should still ensure:

- truthful success and failure messaging
- non-enumerating password-reset UX
- no frontend-owned communication logic
- clear unavailable states only where a route is still intentionally deferred

The real submit flows no longer need to wait for backend email capability to land first.

## Immediate Next Step

Do this next:

1. wire the Next.js auth-recovery and request-access pages to the real backend endpoints
2. verify end-to-end Mailgun-backed delivery behavior in the intended environment
3. confirm rate limits, logging, and safe failure behavior under realistic traffic
4. keep optional template and observability refinements as follow-on hardening
