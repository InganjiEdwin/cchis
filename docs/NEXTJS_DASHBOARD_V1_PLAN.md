# Next.js Dashboard V1 Plan

This document is the source of truth for the CCHIS v1 web dashboard.

It is based on:

- the product direction in `CCHIS Proposal.pdf`
- the current backend contract in `README.md`
- the existing v1 API surface in `backend/core/api_v1_urls.py`, `backend/risk/urls.py`, and `backend/accounts/urls.py`

The goal is to build a secure, operationally useful Next.js dashboard that proves the v1 value chain:

- predict risk
- monitor risk
- trigger alerts
- monitor response

Important sequencing note:

- backend-owned forgot-password, reset-password, and request-access flows now exist
- Mailgun-backed email delivery and official communication workflows are now part of the implemented backend baseline
- current implementation status is tracked in `docs/IMPLEMENTATION_STATUS.md`
- backend communication details remain documented in `docs/MAILGUN_BACKEND_IMPLEMENTATION_PLAN.md`

## No Legacy Preservation Requirement

CCHIS does not currently have production dashboard traffic, production data, or legacy frontend flows that must be preserved.

That means this plan should optimize for a clean v1 implementation rather than backward compatibility.

Explicit rules:

- do not preserve old frontend flows just because they existed in earlier prototypes
- do not add compatibility shims for legacy route shapes, auth flows, or UI states unless they are still part of the intended v1 contract
- do not spend time maintaining parallel old and new dashboard experiences
- replace incomplete or prototype-only flows directly when the new implementation is ready

The practical rule is simple:

- prefer clean replacement over migration complexity unless a real user or dataset would be harmed, and today there is no production data to protect

## V1 Product Position

The proposal describes a broader platform:

- ward-level cholera risk prediction
- alert and trigger workflows
- facility readiness forecasting
- offline-first CHV decision support
- SMS and USSD delivery
- monitoring and learning loops

For v1, the web dashboard should not try to expose the whole future platform.

The dashboard should prove:

- authenticated access works
- ward-level risk can be reviewed quickly
- alerts can be monitored and triggered safely
- operators can understand the latest system state without digging through logs

## Current Backend Reality

The current backend already supports:

- JWT login, refresh, logout, me
- TOTP verification with pre-auth login branching for privileged users
- password reset request and confirm
- access request submission plus admin review endpoints
- ward listing
- risk score listing
- latest ward risk summary
- alert listing
- alert trigger action
- CHV list
- CHV triage submission
- CHV sync submission
- public USSD callback
- versioned schema discovery

Current canonical API base:

- `/api/v1/`

Current auth model:

- username + password login
- JWT access and refresh tokens

Current backend roles:

- `ADMIN`
- `SUPERVISOR`
- `CHV`
- `ANALYST`

Important v1 constraints:

- there is no dedicated county-official role in the backend yet
- for dashboard planning, treat “County Official” as a product-facing label that maps to current read-oriented backend roles, most likely `ANALYST`
- official communication and access-request feedback should be backend-owned messaging workflows, not improvised in the frontend
- CHV is not a first-class dashboard user in v1
- future limited CHV web access can be considered only for triage or sync fallback flows

## Global Product Rules

- Every screen must support a clear operational action, not just show data.
- Every feature must map to one of:
  - predict risk
  - trigger alert
  - support CHV decision
  - monitor response
- Build MVP-first.
- Avoid speculative frontend features that have no backend support.
- One primary user goal per screen.

## Global UX Rules

- Critical status must be understandable in under 3 seconds.
- Prefer cards, badges, tables, and focused maps over dense prose.
- Use plain severity labels:
  - Low
  - Medium
  - High
- Show “last updated” anywhere risk or alert timing matters.
- Do not hide active alert state behind multiple clicks.
- Optimize for low-bandwidth and older laptops.
- Every screen must define:
  - loading state
  - empty state
  - error state
  - success state where actions exist

## Global Data Rules

- UI must tolerate missing, delayed, or partial data.
- Risk values should show:
  - label
  - numeric score
  - update timestamp
- Use at most two decimals for numeric risk scores.
- Never imply unavailable certainty.
- If data is stale or absent, the UI must say so plainly.

Initial stale-data thresholds:

- risk data should be marked stale after 6 hours without a fresher timestamp
- alert feed data should be marked stale after 15 minutes without a fresher timestamp
- the System page should surface both thresholds and the latest observed timestamps visibly

## Deferred And Placeholder Rule

If a page exists before its backend workflow is fully wired:

- show a clear `This feature is not yet active` or `Unavailable` state
- do not fake workflow completion or success
- do not add client-side-only behavior for security-sensitive or operationally sensitive flows

## Auth, Role, and Access Rules

Dashboard auth must use the existing backend JWT flow only.

Do not add frontend-only auth logic beyond session handling.

Because there is no production dashboard install base to protect, we do not need to preserve any legacy auth screens, route aliases, or session behaviors that conflict with the intended v1 flow.

V1 dashboard role behavior:

- `ADMIN`
  - full dashboard access
  - can trigger alerts
  - can see CHV and system operational surfaces
- `ANALYST`
  - county-wide read access
  - no mutation actions by default
- `SUPERVISOR`
  - operational access within scope
  - can review alerts and CHV coverage
  - can trigger alerts where backend permits
- `CHV`
  - not the primary dashboard user in v1
  - can later use selected web flows only if needed for demo or fallback

Frontend rule:

- hide actions where appropriate
- backend remains the final permission authority

Current auth contract note:

- login may return final JWTs immediately or a `requires_2fa` branch with a short-lived pre-auth token
- the frontend must route that second branch through `/verify-2fa`
- privileged-role 2FA policy remains backend-enforced

## Security and Safety Rules

- Use the canonical versioned API only:
  - `/api/v1/...`
- Store access tokens in memory where feasible and handle refresh carefully.
- If cookies are introduced later, they must align with backend deployment settings and CSRF policy.
- Do not expose raw tokens in logs, query strings, or local debug UI.
- Do not hardcode demo credentials into the frontend.
- Show safe error messages:
  - enough for the user to recover
  - not enough to leak internals
- Treat alert-trigger actions as high-sensitivity:
  - clear confirmation
  - explicit success/failure feedback
  - no repeated accidental submission
- Prefer server-side proxy routes in Next.js for backend integration if they simplify secret handling or deployment boundaries, but do not duplicate backend business rules there.

## Design Rules

- This must feel like a public-health operations system, not generic SaaS.
- Use real administrative wards, not hospital wards.
- Prefer explicit health and climate language such as:
  - cholera risk
  - flood risk
  - heavy rainfall
  - water contamination
- Avoid vague labels where operational wording is clearer.
- Every screen should answer:
  - what is happening
  - where
  - how severe
  - what action should be taken

## Recommended Frontend Stack

- Next.js with App Router
- TypeScript
- a small shared component system for:
  - status badge
  - metric card
  - data table
  - last-updated row
  - loading skeleton
  - empty state
  - inline error state
- React Query or SWR for API data fetching and cache invalidation
- Zod for request and response parsing where helpful
- Leaflet or MapLibre later for risk map work

No chart-heavy dependency set is required for the first slice.

## Information Architecture

### Must Exist In App Shell And Routing

1. Login
2. Forgot Password
3. Reset Password
4. Request Access
5. Verify 2FA
6. Privacy Policy
7. Terms of Service
8. Profile

### Must Build For Core Dashboard

9. Overview Dashboard
10. Ward Risk List
11. Ward Risk Detail
12. Alerts List
13. Alert Detail
14. Trigger Alert flow

### Build Next

15. CHV Directory
16. System Status / Data Freshness
17. Risk Map only if geometry is ready

### Later V1 Extension

18. CHV Triage Web Form
19. CHV Sync / Submission Status
20. CHV Detail
21. Facility Readiness when backend support is mature enough

MIT license note:

- MIT should exist as the repo-level `LICENSE` file
- mention it in `README.md`
- no dedicated in-app license page is required for v1
- an optional footer link later is acceptable

## V1 Navigation

Recommended primary navigation:

- Overview
- Wards
- Alerts
- CHVs
- System
- Profile

Do not add Settings as a first-class nav item in v1 unless there is real backend-supported configuration to expose.

Role-based visibility:

- `ADMIN`
  - all of the above
- `ANALYST`
  - Overview, Wards, System, Profile
- `SUPERVISOR`
  - Overview, Wards, Alerts, CHVs, Profile
- `CHV`
  - not a first-class dashboard navigation target in v1

Auth and legal pages should live outside the protected dashboard layout:

- `/login`
- `/forgot-password`
- `/reset-password`
- `/request-access`
- `/verify-2fa`
- `/privacy`
- `/terms`

Protected dashboard routes for v1 planning:

- `/overview`
- `/wards`
- `/wards/[id]`
- `/alerts`
- `/alerts/[id]`
- `/chvs`
- `/system`
- `/profile`

## Screen Specifications

### 1. Login

Goal:

- establish a secure dashboard session

Primary user:

- Admin, Analyst, Supervisor

Data needed:

- username
- password

API endpoints:

- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/refresh/`
- `GET /api/v1/auth/me/`

Components:

- branded login card
- username input
- password input
- submit button
- inline error message

States:

- loading: submitting credentials
- error: invalid credentials or network failure
- success: store session and redirect by role
- expired session: prompt re-authentication

Actions:

- sign in

Notes:

- use username, not email, because that is the current backend contract

### 2. Forgot Password

Goal:

- start a password recovery flow safely

Primary user:

- any existing account holder

API endpoint:

- `POST /api/v1/auth/password-reset/request/`

Implementation rules:

- response must stay non-enumerating
- success UI should be phrased as a neutral “If an account exists, instructions have been sent”

### 3. Reset Password

Goal:

- let a user set a new password from a verified recovery link or token

Primary user:

- existing account holder recovering access

API endpoint:

- `POST /api/v1/auth/password-reset/confirm/`

Implementation rules:

- handle invalid and expired tokens truthfully
- route back to login after successful completion

### 4. Request Access

Goal:

- give non-registered users a safe path to request dashboard access

Primary user:

- potential admin, analyst, or supervisor user

API endpoint:

- `POST /api/v1/auth/access/request/`

Supporting admin review endpoints:

- `GET /api/v1/auth/access/requests/`
- `POST /api/v1/auth/access/requests/<id>/approve/`
- `POST /api/v1/auth/access/requests/<id>/reject/`

Implementation rules:

- submission feedback should be honest and backend-confirmed
- approval or rejection messaging remains backend-owned

### 5. Verify 2FA

Goal:

- complete second-factor verification before issuing a full dashboard session

Primary user:

- privileged dashboard user whose login response returns `requires_2fa`

API endpoint:

- `POST /api/v1/auth/verify-2fa/`

Components:

- 6-digit code input
- verify action
- back-to-login action
- invalid-code state
- expired-session state

States:

- loading
- invalid code
- expired pre-auth session
- success: establish normal JWT-backed session and continue to role-appropriate route

### 6. Privacy Policy

Goal:

- provide the product privacy surface expected of a deployable app

Primary user:

- any user

Implementation note:

- static page in v1

### 7. Terms of Service

Goal:

- provide the product terms surface expected of a deployable app

Primary user:

- any user

Implementation note:

- static page in v1

### 8. Profile

Goal:

- show the authenticated user their current scope and account context

Primary user:

- Admin, Analyst, Supervisor

Data needed:

- current user info

API endpoints:

- `GET /api/v1/auth/me/`
- `POST /api/v1/auth/logout/`

Components:

- user summary card
  - username
  - full name
  - role
  - ward or scope if present
- logout action
- visible scope summary
- current 2FA status if exposed

States:

- loading
- error
- success

### 9. Overview Dashboard

Goal:

- give a fast operational snapshot

Primary user:

- Admin, Analyst, Supervisor

Data needed:

- wards list
- latest ward risk summary
- latest alerts

API endpoints:

- `GET /api/v1/wards/`
- `GET /api/v1/risk-score/latest/`
- `GET /api/v1/alerts/`

Components:

- summary metric cards
  - total wards visible
  - high-risk wards
  - medium-risk wards
  - recent alerts
- latest high-risk ward table
- latest alerts list
- immediate attention panel
- quick links

Suggested detail:

- last updated timestamp
- quick path to highest-risk wards
- alert summary by status where available

States:

- loading: dashboard skeleton
- empty: no ward or alert data yet
- error: partial card-level fallback, not full-screen collapse

Actions:

- open ward detail
- open alert detail
- jump to alerts list

### 10. Ward Risk List

Goal:

- prioritize wards by current risk

Primary user:

- Admin, Analyst, Supervisor

Data needed:

- ward metadata
- latest ward risk summary or risk score list

API endpoints:

- `GET /api/v1/risk-score/latest/`
- optional supporting fetch: `GET /api/v1/wards/`

Components:

- filter row
  - county
  - sub-county
  - risk label
  - search by ward name
- data table
  - ward name
  - county
  - sub-county
  - risk label
  - score
  - predicted cases only if returned by current backend response
  - last updated
- status badge

Rules:

- score formatting must be consistent
- do not fabricate unsupported fields
- optional trend indicator can wait until real trend support is available

States:

- loading table
- empty filters result
- empty no data
- error retry state

Actions:

- open ward detail

### 11. Ward Risk Detail

Goal:

- understand one ward’s current risk and decide next action

Primary user:

- Admin, Analyst, Supervisor

Data needed:

- ward info
- latest and recent risk scores for that ward
- related alerts for that ward

API endpoints:

- `GET /api/v1/wards/?page_size=...`
- `GET /api/v1/risk-scores/?ward_id=<id>&ordering=-generated_at`
- `GET /api/v1/alerts/?ward_id=<id>&ordering=-created_at`

Components:

- ward header
- current risk card
- latest update metadata row
- recent risk table
- related alerts panel
- suggested operational actions box
- recommended response guidance

States:

- loading
- no risk history yet
- no alerts yet
- partial data available

Actions:

- trigger alert from this ward context when authorized
- open related alert detail

### 12. Alerts List

Goal:

- monitor alert creation and delivery state

Primary user:

- Admin, Supervisor, Analyst

Data needed:

- alert list

API endpoints:

- `GET /api/v1/alerts/`

Components:

- status tabs or status-first filters
- filter row
  - ward
  - channel
  - status
- table
  - created time
  - ward
  - channel
  - status
  - recipient
  - sent time
- delivery state badges

States:

- loading
- empty
- error

Actions:

- open alert detail
- open trigger alert modal or page when authorized

Rules:

- avoid fake bulk-messaging language
- keep alert review operational and specific

### 13. Alert Detail

Goal:

- inspect one alert in enough detail to understand what happened

Primary user:

- Admin, Supervisor

Data needed:

- selected alert record
- related ward or risk context

API endpoints:

- v1 backend does not currently expose a dedicated alert-detail endpoint
- first implementation approach:
  - fetch from paginated `GET /api/v1/alerts/`
  - select client-side from cached list or filtered query

Components:

- alert summary header
- ward context
- trigger source explanation
- execution timeline or delivery timeline
- metadata section
  - ward
  - channel
  - status
  - backend
  - attempt count
  - sent time
  - error message if present
- delivery performance summary
- failure reason
- recommended action box
- related risk summary

States:

- loading
- not found
- error

Actions:

- return to alerts list
- open related ward
- retry failed deliveries later when backend supports it and role rules allow it

Recommendation:

- add a dedicated backend alert detail endpoint later if this screen becomes core to operations

### 14. Trigger Alert Action

Goal:

- safely queue an alert run against a selected ward or risk context

Primary user:

- Admin, Supervisor

API endpoint:

- `POST /api/v1/alerts/trigger/`

Request fields:

- `ward_id`
- `risk_level`
- `send_sms`

UX rules:

- make this a modal or focused action panel, not a hidden control
- include clear confirmation text
- disable repeat submits while request is in flight
- show queued success with returned `task_id`

### 15. CHV Directory

Goal:

- inspect assigned CHVs and operational coverage

Primary user:

- Admin, Supervisor

API endpoint:

- `GET /api/v1/chvs/`

Components:

- table
  - CHV name
  - phone number
  - ward
  - active status

States:

- loading
- empty
- error

### 16. CHV Detail

Goal:

- inspect one CHV’s scope and operational context

Primary user:

- Admin, Supervisor

V1 backend reality:

- no dedicated CHV detail endpoint yet
- first version would compose from `GET /api/v1/chvs/`

### 17. System Status / Data Freshness

Goal:

- provide operator confidence in data freshness and platform recency

Primary user:

- Admin, Analyst

V1 reality:

- the backend does not yet expose a dedicated pipeline-status endpoint
- first version should be derived from available timestamps:
  - API reachability
  - latest risk generation times
  - recent alert times
  - schema or API reachability

Recommendation:

- implement as a lightweight confidence panel in v1
- promote to a fuller screen later with:
  - ETL and job health
  - ingestion freshness
  - queue and task health

## Backend Integration Map

### Auth

- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/verify-2fa/`
- `POST /api/v1/auth/refresh/`
- `POST /api/v1/auth/logout/`
- `GET /api/v1/auth/me/`
- `POST /api/v1/auth/password-reset/request/`
- `POST /api/v1/auth/password-reset/confirm/`
- `POST /api/v1/auth/access/request/`

### Core dashboard data

- `GET /api/v1/wards/`
- `GET /api/v1/risk-scores/`
- `GET /api/v1/risk-score/latest/`
- `GET /api/v1/alerts/`
- `POST /api/v1/alerts/trigger/`
- `GET /api/v1/chvs/`

### Later dashboard-adjacent flows

- `POST /api/v1/chv/triage/`
- `POST /api/v1/chv/sync/`

### Auth-recovery and request-access flows

- `POST /api/v1/auth/password-reset/request/`
- `POST /api/v1/auth/password-reset/confirm/`
- `POST /api/v1/auth/access/request/`
- `GET /api/v1/auth/access/requests/`
- `POST /api/v1/auth/access/requests/<id>/approve/`
- `POST /api/v1/auth/access/requests/<id>/reject/`

### Contract discovery

- `GET /api/v1/schema/`

## API Gaps To Respect In The Frontend

- No dedicated ward detail endpoint yet
- No dedicated alert detail endpoint yet
- No dedicated CHV detail endpoint yet
- No facility-readiness endpoint yet
- No pipeline-health endpoint yet
- No dashboard-specific aggregate endpoint yet

Frontend rule:

- do not invent business logic to fill those gaps
- compose from existing list endpoints where reasonable
- where composition becomes awkward, document the backend gap rather than burying complexity in the frontend

Recommended future backend endpoints:

- `GET /api/v1/wards/<id>/`
- `GET /api/v1/alerts/<id>/`
- `GET /api/v1/chvs/<id>/`
- `GET /api/v1/system/status/`
- facility readiness endpoints later

## Shared Component Inventory

Build these first:

- `StatusBadge`
- `MetricCard`
- `DataTable`
- `LastUpdatedRow`
- `PageHeader`
- `LoadingBlock`
- `EmptyState`
- `ErrorState`
- `ConfirmActionDialog`
- `ScopePill`
- `TimelineList`

## Recommended Build Phases

### Phase A: Foundation

- scaffold Next.js app
- set up app router and route groups
- set up TypeScript and linting
- set up API client
- set up auth/session handling
- set up shared layout and component primitives
- login
- forgot password
- reset password
- request access page
- verify 2FA
- privacy page
- terms page
- profile page

Definition of done:

- user can log in
- privileged users can complete TOTP verification when required
- protected routes work
- role-aware navigation works
- auth, recovery, and legal flows are wired to the real backend where endpoints already exist

### Phase B: Core Operational Risk Screens

- Overview
- Ward Risk List
- Ward Risk Detail

Definition of done:

- operators can inspect risk from real backend data

### Phase C: Alert Operations

- Alerts List
- Alert Detail
- Trigger Alert action

Definition of done:

- dashboard covers prediction to alert review to alert action

### Phase D: Operational Expansion

- CHV Directory
- System Status / Data Freshness

Definition of done:

- dashboard feels like an operational console, not just a demo

### Phase E: Field Workflow And Optional Geography

- CHV Triage Web Form
- CHV Sync / Submission Status
- Risk Map if ward geometry is ready
- CHV Detail

Definition of done:

- selected CHV workflows can be demonstrated from the web surface
- geographic context improves decisions without blocking core v1

## Delivery Notes For V1

- Start with server-rendered layout plus client data components where it improves UX.
- Use optimistic UI sparingly; prefer truthful state over flashy interaction.
- Keep charts minimal.
- A sparkline or simple trend indicator is enough for ward history if used at all.
- The map is not a first-screen priority unless it clearly improves operational decisions.
- Only build the map once ward geometry is available in a usable form.
- Do not block core v1 on map support.

## Screen Template For Detailed Follow-Up Specs

Use this template for each implementation ticket:

- goal
- primary user
- backend role assumptions
- data needed
- API endpoints
- components
- loading state
- empty state
- error state
- success state
- user actions
- security considerations
- backend gaps

## Immediate Next Step

Continue the dashboard against the current backend in this order:

1. Login
2. Verify 2FA
3. Forgot Password
4. Request Access
5. Privacy
6. Terms
7. Profile
8. Overview
9. Ward Risk List
10. Ward Risk Detail
11. Alerts List
12. Alert Detail
13. Trigger Alert

That sequence matches both the proposal and the current backend maturity:

- prediction is already present
- alerts are already present
- auth is already present
- auth recovery, request-access, and privileged 2FA backend flows already exist
- facility readiness and richer CHV workflows can follow after the core proof works well
