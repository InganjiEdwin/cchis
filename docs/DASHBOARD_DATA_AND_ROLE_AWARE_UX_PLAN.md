# Dashboard Data And Role-Aware UX Plan

This document defines the additional data and UX planning needed to make the CCHIS Next.js dashboard operationally useful and role-aware.

It is intentionally narrower than the main dashboard plan.

It is a supporting implementation document, not the canonical dashboard source of truth.

It is based on:

- `docs/NEXTJS_DASHBOARD_V1_PLAN.md`
- `docs/IMPLEMENTATION_STATUS.md`
- the backend contract in `README.md`
- the role model described in `docs/RBAC_AND_ROLE_ENFORCEMENT_PLAN.md`

The goal is to clarify what the frontend must fetch, how role-aware rendering should work, and what backend data dependencies still need to be respected.

## No Legacy Preservation Requirement

CCHIS does not currently have production dashboard users, production UI flows, or live frontend data dependencies that require legacy preservation.

That means this plan should favor a clean role-aware dashboard implementation rather than compatibility with older prototype screens or draft route behavior.

Explicit rules:

- do not preserve legacy sidebar structures, route layouts, or page states that do not match the intended v1 dashboard
- do not maintain old data-fetch assumptions once the clearer v1 data model is defined
- do not keep parallel prototype and v1 UX paths unless a real rollout constraint appears
- replace draft or placeholder UI patterns directly when the role-aware implementation is ready

The practical rule is simple:

- build the cleanest v1 dashboard data and UX model, because there is no production data or live user traffic to protect

## Purpose

Turn the broad dashboard plan into a data-aware implementation path that supports:

- correct page-level data requirements
- role-aware navigation and actions
- clearer empty, stale, and unauthorized states
- realistic frontend sequencing against the current backend

This is a v1 support plan.

It makes the main dashboard plan easier to implement without guesswork.

## Scope For First Implementation

The first dashboard data slice should support:

1. authenticated session bootstrap via `/api/v1/auth/me/`
2. role-aware app shell and navigation
3. overview, wards, alerts, CHVs, and system pages using current backend data
4. explicit handling for unavailable or not-yet-supported frontend features
5. clear rules for data freshness, loading, and stale states

## Design Rules

- The frontend must not invent data the backend does not provide.
- Every dashboard page should state what operational question it answers.
- Role-aware UX should simplify use, not fragment the application into separate apps.
- Unauthorized states should be clear and calm, not error-looking when the user is simply out of scope.
- The dashboard should behave well under partial or delayed backend data.
- Legacy prototype flows do not need to be preserved if they conflict with the intended role-aware v1 design.

## Session And Current User Data

The dashboard needs a stable session bootstrap flow.

Required current-user data:

- `id`
- `username`
- display name if available
- `role`
- optional scope metadata if present

Frontend session store should hold:

- access token
- refresh token handling state
- current user object
- derived role helpers

Recommended role helper examples:

- can view alerts
- can trigger alerts
- can view CHVs
- can view system page

## Global Dashboard Data Rules

- Use the versioned backend contract only:
  - `/api/v1/...`
- Prefer server-safe fetch boundaries if Next.js proxy routes simplify deployment separation.
- Every page should define:
  - loading state
  - empty state
  - error state
  - stale-data state where timing matters
  - unauthorized state if role restrictions apply
- Use backend timestamps directly where possible.
- Display “last updated” for risk, alert, and system freshness surfaces.

## Role-Aware UX Rules

The frontend should reflect role permissions at three levels:

1. navigation visibility
2. page access
3. action availability

### Navigation Visibility

Recommended v1 navigation:

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
  - no full dashboard navigation by default

### Page Access

Recommended route behavior:

- authenticated but unauthorized users should be redirected to a safe allowed page or shown a simple not-authorized state
- protected routes should not flash restricted content before redirect
- role checks should be based on current session user data, not guessed from route names

### Action Availability

Examples:

- show `Trigger Alert` only for `ADMIN` and `SUPERVISOR`
- hide resend or retry alert actions from `ANALYST`
- hide CHV-only data-entry flows from users who are not operational field actors

## Page-Level Data Requirements

### Overview Dashboard

Primary question:

- what needs attention right now

Likely data sources:

- `GET /api/v1/wards/`
- `GET /api/v1/risk-score/latest/`
- `GET /api/v1/alerts/`

Recommended visible data:

- total visible wards
- high-risk wards count
- medium-risk wards count
- recent alerts count
- latest high-risk wards table
- latest alerts summary
- last-updated timestamps

Role notes:

- available to `ADMIN`, `SUPERVISOR`, `ANALYST`
- mutation actions remain role-restricted even if read data is visible

### Wards List

Primary question:

- which wards are highest risk right now

Likely data sources:

- `GET /api/v1/risk-score/latest/`
- optional `GET /api/v1/wards/`

Recommended visible data:

- ward name
- county
- sub-county
- risk label
- risk score
- updated timestamp

Recommended controls:

- search by ward name
- filter by county
- filter by sub-county
- filter by risk level
- ordering by severity or recency where supported

### Ward Detail

Primary question:

- what is happening in this ward and how recent is the forecast

Likely data sources:

- ward metadata endpoint or ward list item expansion
- risk score history if available
- latest risk entry
- related recent alerts if available

Recommended visible data:

- ward identity and location context
- current risk status
- recent alert state
- latest generated timestamp
- any forecast metadata the backend already exposes safely

### Alerts List

Primary question:

- what alerts exist and what is their current status

Likely data source:

- `GET /api/v1/alerts/`

Recommended visible data:

- ward
- channel
- status
- created time
- latest delivery or processing signal if available

Recommended controls:

- filter by status
- filter by channel
- filter by ward

Role notes:

- list visibility should follow backend RBAC
- action controls such as trigger or retry must be role-gated

### Alert Trigger Flow

Primary question:

- can an authorized operator trigger an alert safely

Likely data source:

- `POST /api/v1/alerts/trigger/`

Required UX behavior:

- confirmation step
- loading and duplicate-submit protection
- explicit success state
- explicit failure state
- no availability for disallowed roles

### CHV Directory

Primary question:

- which CHVs are available or in scope

Likely data source:

- CHV listing endpoint if exposed by current backend

Recommended visible data:

- CHV identity fields already exposed by backend
- assigned ward if present
- status if present

Role notes:

- primary users are `ADMIN` and `SUPERVISOR`
- `ANALYST` read access only if backend policy supports it

### System Page

Primary question:

- how fresh and healthy is the current operational data

Possible data inputs:

- last risk generation timestamps
- recent ingestion timestamps if exposed
- alert processing recency
- simple API health or schema visibility checks if a dedicated system endpoint does not yet exist

Important note:

- if the backend does not yet provide a dedicated system status endpoint, the first system page should be framed as a data freshness and operational summary page rather than pretending to be full infrastructure observability

## Unsupported Or Deferred Areas

The dashboard plan should be honest about backend dependencies.

Treat these as deferred or placeholder-only until backend support exists:

- rich facility readiness views
- true geospatial map experience if geometry data is not ready
- deep CHV workflow editing if web support is not yet mature

## Unauthorized And Out-Of-Scope States

Not every restricted path should feel like a failure.

Recommended patterns:

- `Not authorized` when the role is wrong
- `No data available yet` when backend data has not been generated
- `Data may be outdated` when timestamps are old or missing
- `This feature is not yet active` when the screen shell exists ahead of backend delivery

## Implementation Phases

### Phase 1: Session And Role Foundations

- fetch `/api/v1/auth/me/` after login
- establish session store and role helpers
- configure role-aware navigation
- add route guard primitives

Definition of done:

- the frontend knows who the user is and what role-aware surfaces to show

### Phase 2: Core Read Views

- implement Overview
- implement Wards list
- implement Alerts list
- implement Profile
- add robust loading, empty, and error states

Definition of done:

- the main operational read surfaces work against current backend data

### Phase 3: Sensitive Actions And Operational Pages

- implement Trigger Alert flow
- implement CHV directory if the backend route is ready
- implement a first-pass System page focused on freshness and status summaries

Definition of done:

- the dashboard supports safe operational actions and status monitoring

### Phase 4: Polish And Follow-On Data Work

- improve unauthorized states
- add stale-data indicators
- refine query filters and pagination handling
- prepare for future richer scope-aware experiences

Definition of done:

- the dashboard is role-aware, stable under partial data, and ready for pilot hardening

## Test Expectations

Add tests for:

- current-user fetch and session bootstrap
- role-aware navigation rendering
- protected-route behavior
- restricted action visibility
- graceful handling of empty and stale data
- alert trigger UX success and failure handling

## Relationship To Other Plans

This plan refines:

- `docs/NEXTJS_DASHBOARD_V1_PLAN.md`

This plan should not redefine route inventory, auth endpoint inventory, or current implementation status independently when the canonical dashboard plan or implementation-status doc already covers them.

This plan depends on:

- `docs/RBAC_AND_ROLE_ENFORCEMENT_PLAN.md`

This plan should stay coordinated with:

- `docs/MAILGUN_BACKEND_IMPLEMENTATION_PLAN.md`
- `docs/TOTP_2FA_HARDENING_PLAN.md`
- `docs/IMPLEMENTATION_STATUS.md`

## Immediate Next Step

Do this before building deeper page detail:

1. confirm `/api/v1/auth/me/` response shape
2. define frontend session store and role helpers
3. map current backend endpoints to each dashboard screen
4. mark unsupported backend-dependent screens as deferred or placeholder-only

After that, the Next.js implementation can proceed with much less ambiguity.
