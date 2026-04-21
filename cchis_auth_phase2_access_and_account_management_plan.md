# CCHIS Auth Phase 2: Access Control and Account Management Plan

## Purpose

This document defines the next auth and security implementation slice after the completed custom-user-model and JWT foundation work.

The first auth slice established:

- a custom `accounts.User` model
- JWT login, refresh, logout, and current-user endpoints
- role-based endpoint protection
- seeded demo users
- Docker-verified auth flows and tests

This next slice focuses on what still remains thin:

- object-level access scoping by role and ward
- user account lifecycle management
- stronger auth event auditing beyond request logs

## Why This Plan Exists

The current backend now has authentication and coarse endpoint permissions, but it still needs more precise data access controls and admin-operable account flows.

Two concrete gaps remain:

1. authenticated users can still access some data too broadly because permissions are currently endpoint-level, not object-level
2. the system does not yet have a complete account-management flow for password changes, deactivation/reactivation, or meaningful auth event auditing

This plan turns those gaps into an implementation roadmap.

## Scope

This phase should cover all of the following:

- define object-level read/write rules per role
- enforce queryset scoping and record-level protection
- add password change flow for authenticated users
- add admin user management actions for activate/deactivate
- define behavior for deactivated users and token usage
- add auth event logging for critical account actions
- add tests for role scoping and account lifecycle behavior

## Non-Goals

This phase should not expand into unrelated platform work.

Out of scope for now:

- public self-service signup
- email-based password reset unless the project already has a reliable email channel
- MFA/2FA
- SSO or OAuth integrations
- full RBAC policy engine
- frontend UX implementation beyond documenting the backend contracts

## Success Criteria

This phase is successful when:

- CHV users can only access data they are supposed to access
- supervisor access is scoped intentionally rather than implicitly broad
- analyst access is clarified and enforced
- admin users can deactivate and reactivate accounts safely
- authenticated users can change their password
- deactivated users cannot continue operating with valid-looking sessions indefinitely
- important auth events are recorded in a useful way
- automated tests cover the new behaviors

## Proposed Roles and Access Baseline

These rules should be made explicit in code, not just assumed.

### ADMIN

- full access to all wards, users, logs, alerts, risk data, and account management actions

### SUPERVISOR

- access to operational data for supervised wards only
- can view CHV and triage/sync activity in assigned scope
- can trigger operational actions in assigned scope
- should not have unrestricted access to every ward by default unless the project intentionally wants that

### CHV

- access only to their own ward-scoped operational data
- should be limited to submitting triage/sync and viewing only the ward context needed for their work
- should not browse cross-ward alert or risk data broadly

### ANALYST

- read-only access to allowed reporting and risk views
- no operational write actions
- scope needs an explicit decision:
  - either cross-ward read access is allowed
  - or analyst access is limited by assigned ward or assigned geography

## Phase 1: Object-Level Scoping

### Objective

Introduce clear record-level access rules so the same endpoint does not expose overly broad data to all authenticated users.

### Status

Completed

### Outcome Notes

- CHV and supervisor users are now scoped to their assigned ward for ward, risk, alert, CHV-list, and USSD-log visibility
- analyst users remain read-only and retain broad reporting visibility
- analyst users are now blocked from operational write endpoints such as triage and sync
- supervisor alert triggering is restricted to the supervisor's assigned ward
- CHV and supervisor cross-ward operational writes now return out-of-scope `404` responses
- automated tests were expanded to cover cross-ward denial and scoped visibility behavior

### Key Decisions to Make

- should supervisors be assigned to one ward, multiple wards, a sub-county, or all wards?
- should analysts be global read-only users or scoped users?
- should CHVs be able to view only their own ward’s risk snapshot, or only the latest risk relevant to their ward?

### Implementation Tasks

- review all list and detail endpoints that currently rely only on role checks
- define scoped queryset helpers per role
- apply ward-based filtering where appropriate
- enforce read/write separation for analyst users
- prevent CHV users from reading cross-ward operational data
- decide whether some endpoints should return:
  - `403 Forbidden`
  - filtered result sets
  - `404 Not Found` for out-of-scope objects

### Likely Code Areas

- `backend/accounts/permissions.py`
- `backend/risk/views.py`
- serializers or service-layer helpers if scoping is better enforced there
- possibly user-to-ward or supervisor-to-ward relationship modeling if the current single `ward` field is insufficient

### Deliverables

- explicit scoped access rules in code
- no broad accidental cross-ward reads for CHV users
- documented analyst and supervisor visibility rules

### Exit Criteria

- automated tests prove users cannot access out-of-scope objects or data sets

## Phase 2: Account Management Flows

### Objective

Add core account lifecycle operations so auth is manageable after users exist.

### Status

Completed

### Outcome Notes

- authenticated users can now change their password through a dedicated backend endpoint
- password change requires current-password verification and applies Django password validators
- refresh tokens are blacklisted on password change so old refresh sessions cannot continue
- admin users can now deactivate and reactivate accounts through dedicated backend endpoints
- deactivated users cannot log in, cannot refresh tokens, and cannot continue using access tokens against authenticated endpoints
- automated tests now cover password change, inactive-user behavior, and admin-only activation/deactivation controls

### Implementation Tasks

- add authenticated password change endpoint
- require current password verification for password change
- invalidate or rotate sessions appropriately after password change
- add admin endpoints or admin actions for:
  - deactivate user
  - reactivate user
  - optionally reset password administratively
- define behavior for deactivated users:
  - login should fail
  - refresh should fail
  - existing tokens should be considered in the security model
- document the backend contract for future frontend/admin UX

### Recommended Endpoints

- `POST /api/auth/change-password/`
- `POST /api/auth/users/<id>/deactivate/`
- `POST /api/auth/users/<id>/reactivate/`

Optional later:

- `POST /api/auth/users/<id>/set-password/` for admin-only reset if operationally necessary

### Validation Rules

- current password must be correct before change
- new password must pass Django password validators
- deactivated users cannot authenticate
- admin-only account actions must be strongly permissioned

### Deliverables

- user password change flow
- admin activation/deactivation flow
- tested behavior for inactive users

### Exit Criteria

- account lifecycle actions work consistently and safely in tests

## Phase 3: Auth Event Audit Trail

### Objective

Record meaningful auth and account events beyond generic request logs.

### Status

Completed

### Outcome Notes

- a DB-backed `AuthAuditEvent` model was added under `accounts`
- key auth and account events are now persisted for:
  - login success
  - login failure
  - logout
  - refresh success
  - refresh failure
  - password change
  - user creation
  - user deactivation
  - user reactivation
- auth audit events are also logged through a dedicated `accounts.audit` logger
- Django admin now exposes the audit events for review
- automated tests now verify audit-event creation for the critical auth and account flows

### Events to Capture

- login success
- login failure
- logout
- refresh token rejection
- password change
- user creation
- user deactivation
- user reactivation
- admin-performed account changes

### Design Options

#### Option A: Logger-only audit events

- fastest to implement
- good for container logs
- weaker for in-app review and admin visibility

#### Option B: Database-backed audit model

- stronger traceability
- easier to query in admin or API
- more implementation work

#### Recommendation

Use both if possible:

- structured logger events for operational observability
- lightweight DB-backed `AuthAuditEvent` model for important account actions

### Suggested Data Fields

- actor user
- target user
- event type
- status
- IP address if available
- user agent if available
- ward or scope context where relevant
- created timestamp
- optional metadata JSON field

### Likely Code Areas

- new model in `accounts` or a dedicated audit app
- auth views
- admin-triggered account-management paths
- logging configuration for structured events

### Deliverables

- auditable auth/account activity trail
- at least admin-visible access to audit data

### Exit Criteria

- critical account actions are traceable from logs and/or database records

## Phase 4: Test Matrix and Verification

### Objective

Prove the new access-control and account-management behavior under realistic role combinations.

### Status

Completed

### Outcome Notes

- the test suite now covers object-level scoping for CHV and supervisor users
- analyst write denials are tested
- password change success and failure paths are tested
- inactive-user login and refresh denial behavior is tested
- admin-only deactivate/reactivate controls are tested
- auth audit event creation is tested for key login, refresh, logout, registration, password-change, and activation/deactivation flows
- Docker-based verification was run after the Phase 2 and Phase 3 changes
- the backend test suite is currently passing with the expanded auth/security matrix

### Tests to Add

- CHV cannot read another ward’s data
- supervisor cannot act outside assigned scope
- analyst write attempts are denied
- password change succeeds with correct current password
- password change fails with wrong current password
- inactive user cannot log in
- inactive user cannot refresh token
- admin deactivate/reactivate actions are permission-protected
- auth audit events are created for key flows

### Verification in Docker

```bash
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py test
```

### Deliverables

- passing automated tests for access control and account lifecycle behavior

### Exit Criteria

- the new rules are enforced and regression-resistant

## Implementation Order

The safest order is:

1. define and lock role-scope decisions
2. implement object-level scoping
3. implement password change and deactivate/reactivate flows
4. add auth audit event capture
5. expand tests
6. run Docker verification

## Decisions Needed Before Coding

These need explicit product/operational choices before implementation:

1. Are supervisors single-ward, multi-ward, or county-wide users?
2. Are analysts globally read-only, or scoped to a ward or region?
3. Should CHVs be allowed to read any alert/risk data beyond their own ward?
4. Do we want deactivation to block only new login/refresh, or do we also want stronger active-token invalidation semantics?
5. Do we want auth auditing only in logs, or also persisted in the database?

## Recommended Starting Point

If we want the most practical next patch set, start with:

- object-level ward scoping for CHV and supervisor users
- password change endpoint
- admin deactivate/reactivate actions
- DB-backed auth audit events for key account changes

That gives the highest security and operational value without expanding too far at once.
