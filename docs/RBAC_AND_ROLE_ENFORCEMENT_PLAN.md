# RBAC And Role Enforcement Plan

This document defines the minimum role-based access control plan required for a credible CCHIS v1 release.

It is intentionally focused on practical authorization, not enterprise identity management.

It is based on:

- the current backend roles described in `README.md`
- the current dashboard direction in `docs/NEXTJS_DASHBOARD_V1_PLAN.md`
- the existing backend contract under `/api/v1/`

The goal is to ensure sensitive operational actions are backend-enforced, easy to reason about, and reflected consistently in the dashboard UI.

## Status Summary

Current implementation status:

- Phase 1: completed
- Phase 2: completed
- Phase 3: substantially completed
- Phase 4: completed

What is implemented now:

- backend permission classes are explicit for dashboard and field roles
- sensitive routes are backend-enforced against the v1 role model
- `/api/v1/auth/me/` now returns role plus scope metadata usable by the frontend
- backend ward scoping is centralized instead of being repeated inconsistently
- alert-trigger requests now emit clearer operational logs for queued and rejected attempts
- a frontend App Router shell exists in `frontend/` with session bootstrap, role-aware navigation, and route-level role gating for restricted pages

Remaining non-blocking follow-on work:

- connect the frontend placeholder pages to live backend data
- add frontend build and runtime verification once dependencies are installed
- decide whether analyst read access should later extend to CHV or USSD-log review surfaces

## No Legacy Preservation Requirement

CCHIS does not currently have production role-dependent dashboard flows or production authorization behavior that must be preserved.

That means this plan should optimize for a clear, enforceable v1 permission model rather than compatibility with older prototype behavior.

Explicit rules:

- do not preserve old endpoint access patterns if they are too permissive
- do not keep weak prototype role assumptions just to avoid changing frontend behavior
- do not maintain parallel authorization models while introducing the real RBAC rules
- replace ambiguous legacy access behavior directly with explicit backend-enforced permissions

The practical rule is simple:

- tighten and simplify authorization now, because there is no production data or live dashboard usage that requires backward-compatible access behavior

## Purpose

Implement minimal, backend-first RBAC so CCHIS can safely support:

- authenticated dashboard access
- read access to ward, risk, and alert information
- restricted access to alert-triggering operations
- role-aware CHV and operational workflows

This plan is a v1 requirement.

Without it, the dashboard would not be operationally credible.

## Scope For First Implementation

The first RBAC slice should support:

1. explicit role definitions
2. endpoint-level permission enforcement
3. role-aware frontend navigation and action visibility
4. a stable `/api/v1/auth/me/` contract for session and role awareness
5. simple rules that can evolve later without rewriting the entire auth model

Phase 1 outcome requirement:

- produce one explicit v1 permission baseline from the real codebase and use it as the source of truth for follow-on implementation

## Design Rules

- Backend is the source of truth for authorization.
- Frontend may hide, disable, or redirect, but never decides real permission.
- Roles should remain explicit and human-readable.
- v1 should use fixed roles, not dynamic policy builders.
- Django admin remains the place for role assignment in v1.
- Ward or scope assignment may exist, but broad scoping complexity should not block v1 endpoint protection.
- If a legacy prototype flow conflicts with the intended RBAC model, replace it rather than preserving it.

## Current Roles

The current backend roles are:

- `ADMIN`
- `SUPERVISOR`
- `ANALYST`
- `CHV`

Operational intent for v1:

- `ADMIN`
  - full administrative and operational access
- `SUPERVISOR`
  - operational access for alerting and field coordination within permitted scope
- `ANALYST`
  - read-oriented access for county-wide monitoring and analysis
- `CHV`
  - field workflow access, not broad dashboard administration

Current source files:

- `backend/accounts/models.py`
- `backend/accounts/permissions.py`
- `backend/accounts/views.py`
- `backend/risk/views.py`

## Phase 1 Audit Baseline

Phase 1 is now grounded in the current implementation rather than assumption.

Audited route files:

- `backend/core/api_v1_urls.py`
- `backend/accounts/urls.py`
- `backend/risk/urls.py`

Audited enforcement files:

- `backend/accounts/permissions.py`
- `backend/accounts/views.py`
- `backend/risk/views.py`

### Confirmed Current Role Model

The backend role model is currently:

- `ADMIN`
- `SUPERVISOR`
- `CHV`
- `ANALYST`

There is no separate county-official role.

There is also no dynamic permission system.

### Confirmed `/auth/me/` Baseline

`GET /api/v1/auth/me/` is authenticated and currently returns a user payload that already includes:

- `id`
- `username`
- `email`
- `full_name`
- `phone_number`
- `role`
- `ward`
- `ward_name`
- `scope_type`
- `scope_ward_id`
- `is_active`

This is sufficient for a first-pass role-aware frontend shell and cleaner scope-aware UI behavior.

### Confirmed Current Endpoint Behavior

The current code-backed access behavior is:

- `POST /api/v1/auth/login/`
  - public
- `POST /api/v1/auth/refresh/`
  - public
- `POST /api/v1/auth/logout/`
  - authenticated
- `GET /api/v1/auth/me/`
  - authenticated
- `POST /api/v1/auth/change-password/`
  - authenticated
- `POST /api/v1/auth/register/`
  - `ADMIN` only
- `POST /api/v1/auth/users/<id>/deactivate/`
  - `ADMIN` only
- `POST /api/v1/auth/users/<id>/reactivate/`
  - `ADMIN` only
- `GET /api/v1/auth/audit-events/`
  - `ADMIN` only
- `GET /api/v1/auth/audit-events/summary/`
  - `ADMIN` only
- `GET /api/v1/wards/`
  - `ADMIN`
  - `SUPERVISOR`
  - `ANALYST`
  - `ADMIN` and `ANALYST` can see broad data
  - `SUPERVISOR` is ward-scoped if `user.ward` exists
- `GET /api/v1/risk-scores/`
  - `ADMIN`
  - `SUPERVISOR`
  - `ANALYST`
  - `ADMIN` and `ANALYST` can see broad data
  - `SUPERVISOR` is ward-scoped if `user.ward` exists
- `GET /api/v1/risk-score/latest/`
  - `ADMIN`
  - `SUPERVISOR`
  - `ANALYST`
  - `ADMIN` and `ANALYST` can see broad data
  - `SUPERVISOR` is ward-scoped if `user.ward` exists
- `GET /api/v1/chvs/`
  - `ADMIN` and `SUPERVISOR`
  - supervisors are ward-scoped if `user.ward` exists
- `GET /api/v1/alerts/`
  - `ADMIN`, `SUPERVISOR`, and `ANALYST`
  - `ADMIN` and `ANALYST` can see broad data
  - supervisors are ward-scoped if `user.ward` exists
- `POST /api/v1/alerts/trigger/`
  - `ADMIN` and `SUPERVISOR`
  - supervisors are ward-scoped if `user.ward` exists
- `POST /api/v1/chv/triage/`
  - `SUPERVISOR`
  - `CHV`
  - ward check is enforced for `SUPERVISOR` and `CHV`
- `POST /api/v1/chv/sync/`
  - `SUPERVISOR`
  - `CHV`
  - ward check is enforced for `SUPERVISOR` and `CHV`
- `POST /api/v1/ussd/menu/`
  - public
- `GET /api/v1/ussd/logs/`
  - `ADMIN` and `SUPERVISOR`
  - supervisors are ward-scoped if `user.ward` exists

### Phase 1 Audit Gaps Closed

The originally identified Phase 1 mismatches have now been closed:

1. `GET /api/v1/alerts/` now allows `ANALYST` read access.
2. ward and risk read endpoints now use explicit dashboard-role permission classes rather than allowing every authenticated role.
3. `POST /api/v1/chv/triage/` and `POST /api/v1/chv/sync/` no longer allow `ADMIN`.
4. ward-scoping logic is now centralized in reusable helpers rather than being repeated inconsistently across views.

This means the documented target matrix is now much closer to the live backend behavior.

## Phase 1 Decision Summary

Phase 1 resolves the v1 direction as follows.

### Roles Stay Fixed

Use these roles directly:

- `ADMIN`
- `SUPERVISOR`
- `ANALYST`
- `CHV`

Do not introduce new product-facing role labels into backend enforcement.

If the product needs a county-official label, map it in presentation only.

### Backend Remains The Source Of Truth

The dashboard may:

- hide pages
- hide buttons
- redirect unauthorized users

But only the backend decides whether a request is permitted.

### Explicit V1 Target Matrix

This is the Phase 1 decision baseline for follow-on implementation.

- `GET /api/v1/wards/`
  - `ADMIN`
  - `SUPERVISOR`
  - `ANALYST`
- `GET /api/v1/risk-scores/`
  - `ADMIN`
  - `SUPERVISOR`
  - `ANALYST`
- `GET /api/v1/risk-score/latest/`
  - `ADMIN`
  - `SUPERVISOR`
  - `ANALYST`
- `GET /api/v1/alerts/`
  - `ADMIN`
  - `SUPERVISOR`
  - `ANALYST`
- `POST /api/v1/alerts/trigger/`
  - `ADMIN`
  - `SUPERVISOR`
- `GET /api/v1/chvs/`
  - `ADMIN`
  - `SUPERVISOR`
  - optional later `ANALYST` read-only only if explicitly needed
- `POST /api/v1/chv/triage/`
  - `CHV`
  - `SUPERVISOR` if operationally needed
- `POST /api/v1/chv/sync/`
  - `CHV`
  - `SUPERVISOR` only if explicitly justified
- `GET /api/v1/ussd/logs/`
  - `ADMIN`
  - `SUPERVISOR`
  - optional later `ANALYST` read-only only if explicitly needed

### Scope Rule For V1

Role is the first gate.

Ward or geography is the second gate where the backend already supports scoped behavior.

For v1:

- `ADMIN` is broad-access
- `ANALYST` is broad read-only
- `SUPERVISOR` may be ward-scoped
- `CHV` is field-scoped and should not be treated as a broad dashboard role

This gives the frontend a stable mental model while leaving room for richer scope rules later.

## Authorization Model For V1

Use a simple RBAC model built from:

1. authenticated user
2. user role
3. optional future scope such as assigned ward or assigned geography

For v1, the enforcement priority is:

1. mutation actions must be role-restricted
2. operational reads must be protected by authentication
3. frontend must reflect permissions cleanly

Do not add:

- dynamic permission editing
- per-screen custom permission builders
- multi-tenant hierarchy logic
- organization tree management

## Endpoint Permission Matrix

This matrix should be treated as the first-pass source of truth for backend enforcement.

### Auth And Session Endpoints

- `POST /api/v1/auth/login/`
  - public
- `POST /api/v1/auth/refresh/`
  - public
- `POST /api/v1/auth/logout/`
  - authenticated
- `GET /api/v1/auth/me/`
  - authenticated

### Ward And Risk Endpoints

- `GET /api/v1/wards/`
  - `ADMIN`
  - `SUPERVISOR`
  - `ANALYST`
- `GET /api/v1/risk-scores/`
  - `ADMIN`
  - `SUPERVISOR`
  - `ANALYST`
- `GET /api/v1/risk-score/latest/`
  - `ADMIN`
  - `SUPERVISOR`
  - `ANALYST`

### Alert Endpoints

- `GET /api/v1/alerts/`
  - `ADMIN`
  - `SUPERVISOR`
  - `ANALYST`
- `POST /api/v1/alerts/trigger/`
  - `ADMIN`
  - `SUPERVISOR`
  - not `ANALYST`
  - not `CHV`

### CHV And Field Endpoints

- `GET /api/v1/chvs/` if exposed in the current contract
  - `ADMIN`
  - `SUPERVISOR`
  - optional `ANALYST` read-only if the backend wants county-level visibility
- `POST /api/v1/chv/triage/`
  - `CHV`
  - `SUPERVISOR` if operational review needs it
- `POST /api/v1/chv/sync/`
  - `CHV`
  - `SUPERVISOR` only if explicitly justified

### Messaging And Public Workflow Endpoints

- `POST /api/v1/ussd/menu/`
  - public by design
- `GET /api/v1/ussd/logs/`
  - authenticated and operationally restricted
  - recommended `ADMIN`
  - recommended `SUPERVISOR`
  - optional `ANALYST` if read-only monitoring is needed

## Backend Implementation Direction

The backend should enforce RBAC through DRF permission classes and explicit view-level rules.

Recommended implementation approach:

- keep role definitions on the user model
- add small reusable permission classes such as:
  - authenticated operational user
  - admin or supervisor
  - admin only
  - analyst or above only if needed
- avoid scattering inline role checks across every view when a permission class can express the rule more clearly

Recommended v1 permission style:

- coarse route-level permission classes
- optional object or scope filtering only where it already exists cleanly

## `/auth/me/` Contract Requirements

The frontend needs a stable current-user contract so role-aware behavior is simple and consistent.

At minimum, `/api/v1/auth/me/` should return:

- `id`
- `username`
- `full_name` or equivalent display field if available
- `role`
- optional scope fields when present
- `scope_type`
- `scope_ward_id`

If future scope fields exist, examples include:

- assigned ward
- county
- sub-county
- facility association

The response should not require the frontend to reconstruct authorization logic from multiple unrelated fields.

## Frontend Responsibilities

The frontend must reflect backend RBAC without pretending to replace it.

Required frontend behavior:

- fetch current user after login
- store role in session state
- show only relevant navigation items
- hide restricted action buttons
- guard protected routes
- show clear unauthorized or insufficient-permission states where appropriate

Examples:

- hide `Trigger Alert` for `ANALYST`
- hide CHV-only operational forms for non-CHV users
- redirect away from restricted routes if the session role is not allowed

Current frontend status in `frontend/`:

- session bootstrap exists
- role-aware navigation exists
- route-level role gating exists for restricted placeholder pages such as CHVs and System
- live backend data wiring is still pending

## Role-Aware Navigation Rules

Recommended v1 navigation visibility:

- `ADMIN`
  - Overview
  - Wards
  - Alerts
  - CHVs
  - System
  - Profile
- `SUPERVISOR`
  - Overview
  - Wards
  - Alerts
  - CHVs
  - Profile
- `ANALYST`
  - Overview
  - Wards
  - System
  - Profile
- `CHV`
  - not a first-class dashboard navigation target in the main v1 web dashboard

## Audit And Safety Rules

RBAC decisions are especially important for mutation actions.

At minimum, the backend should ensure:

- alert triggering remains restricted and auditable
- login and logout remain auditable
- unauthorized access attempts return safe errors
- public endpoints stay intentionally documented rather than accidentally exposed

Recommended audit and logging direction:

- log denied mutation attempts in operational logs where useful
- preserve existing auth audit behavior
- add future domain audit entries for alert-trigger and override workflows as those features mature

## Implementation Phases

### Phase 1: Permission Baseline

- confirm role names and intended product meaning
- define endpoint-to-role matrix
- review current views and serializers for role assumptions
- align dashboard plan terminology with actual backend roles

Definition of done:

- the repo has a documented RBAC source of truth for v1
- the current code-backed baseline and the intended target matrix are both explicit

### Phase 2: Backend Enforcement

- add or refine DRF permission classes
- attach permission rules to sensitive endpoints
- ensure authenticated read routes stay protected
- verify public routes are explicitly public

Definition of done:

- sensitive endpoints reject disallowed roles correctly

Status:

- completed

### Phase 3: Frontend Role Awareness

- read role from `/api/v1/auth/me/`
- add role-aware navigation
- add role-aware action visibility
- add route guards or unauthorized states

Definition of done:

- users only see UI paths that match their role and backend permissions

Status:

- substantially completed

Current note:

- the frontend shell and route gating scaffolding exist in `frontend/`
- live data pages and build verification still need to be completed as part of the broader dashboard work

### Phase 4: Scope And Hardening

- add cleaner scope fields if needed
- refine read scoping by ward or geography where backend support exists
- review auditability for high-sensitivity operations

Definition of done:

- RBAC is not only role-aware but ready for future geography-aware scope controls

Status:

- completed for the current backend scope

Current note:

- `/api/v1/auth/me/` now exposes `scope_type` and `scope_ward_id`
- backend read scoping now uses shared helper functions
- alert-trigger requests now emit clearer queue and rejection logs

## Test Expectations

Add tests for:

- each sensitive endpoint accepting allowed roles
- each sensitive endpoint rejecting disallowed roles
- `/api/v1/auth/me/` returning the role field reliably
- frontend role-aware navigation config if frontend tests exist
- unauthorized route or action handling for restricted users

## Relationship To Other Plans

This plan is upstream of:

- `docs/NEXTJS_DASHBOARD_V1_PLAN.md`
- `docs/DASHBOARD_DATA_AND_ROLE_AWARE_UX_PLAN.md`
- `docs/TOTP_2FA_HARDENING_PLAN.md`

Reason:

- dashboard behavior depends on a stable role model
- 2FA policy depends on identifying privileged roles clearly

## Immediate Next Step

Do this before deeper dashboard implementation:

1. confirm the endpoint permission matrix
2. align backend permission classes with that matrix
3. ensure `/api/v1/auth/me/` exposes role cleanly
4. wire role-aware frontend navigation and action gating

After that, the dashboard and later 2FA work can build on a stable authorization base.
