# Implementation Status

This document is the short current-state source of truth for active CCHIS implementation work.

Use it to answer:

- what is already implemented
- what is partially implemented
- what is deferred
- what the next two sprints should prioritize

For deeper rationale, use the linked planning documents.

## Implemented Backend Endpoints

Auth and recovery:

- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/verify-2fa/`
- `POST /api/v1/auth/refresh/`
- `POST /api/v1/auth/logout/`
- `POST /api/v1/auth/change-password/`
- `GET /api/v1/auth/me/`
- `POST /api/v1/auth/password-reset/request/`
- `POST /api/v1/auth/password-reset/confirm/`
- `POST /api/v1/auth/access/request/`
- `GET /api/v1/auth/access/requests/`
- `POST /api/v1/auth/access/requests/<id>/approve/`
- `POST /api/v1/auth/access/requests/<id>/reject/`

Dashboard and operational data:

- `GET /api/v1/wards/`
- `GET /api/v1/risk-scores/`
- `GET /api/v1/risk-score/latest/`
- `GET /api/v1/alerts/`
- `POST /api/v1/alerts/trigger/`
- `GET /api/v1/chvs/`
- `POST /api/v1/chv/triage/`
- `POST /api/v1/chv/sync/`
- `GET /api/v1/ussd/logs/`
- `POST /api/v1/ussd/menu/`
- `GET /api/v1/schema/`

## Implemented Frontend Routes

Public and auth routes present in `frontend/app/`:

- `/login`
- `/forgot-password`
- `/request-access`
- `/privacy`
- `/terms`
- `/verify-2fa`
- `/unauthorized`

Protected dashboard routes present in `frontend/app/(dashboard)/`:

- `/overview`
- `/wards`
- `/alerts`
- `/chvs`
- `/system`
- `/profile`

Not yet present as dedicated routes:

- `/reset-password`
- `/wards/[id]`
- `/alerts/[id]`
- `/chvs/[id]`

## Implemented Auth Flows

- Username and password login is implemented.
- Login can branch to `requires_2fa` with a short-lived pre-auth token.
- `/verify-2fa` is implemented in the frontend and calls `POST /api/v1/auth/verify-2fa/`.
- Password reset request and confirm endpoints are implemented in the backend.
- Access request submission and admin review endpoints are implemented in the backend.
- Password-reset and request-access pages exist in the frontend, but they are still lightweight first-pass screens rather than a fully polished auth suite.

## Implemented RBAC Behavior

- Backend RBAC is the source of truth.
- `ADMIN`, `SUPERVISOR`, `ANALYST`, and `CHV` are the active v1 roles.
- `/api/v1/auth/me/` returns role and scope metadata used by the frontend.
- Role-aware navigation and route-level gating exist in the Next.js dashboard shell.
- `CHV` is not treated as a first-class dashboard user in v1.
- `ADMIN` and `SUPERVISOR` are the privileged roles for current 2FA enforcement.

## Partially Implemented

- The dashboard shell, navigation, and route gating exist, but most dashboard pages are still placeholder-first rather than fully data-wired.
- Overview, wards, alerts, CHVs, system, and profile pages exist, but they still need live backend integration and richer empty, error, and stale-data handling.
- System status is currently a freshness-oriented placeholder, not a true infrastructure health surface.
- Profile exists and is real enough to anchor account context, but broader account-management features are still deferred.
- TOTP enrollment and setup UX are not implemented as self-service flows.

## Deferred

- Self-service TOTP enrollment, QR setup, backup codes, and device trust
- CHV as a first-class dashboard navigation role
- Dedicated detail endpoints and screens for wards, alerts, and CHVs
- `GET /api/v1/system/status/`
- Facility readiness views
- Rich geospatial dashboard experiences pending usable geometry data

## Current Rules

- `docs/NEXTJS_DASHBOARD_V1_PLAN.md` is the canonical dashboard planning doc.
- `docs/DASHBOARD_DATA_AND_ROLE_AWARE_UX_PLAN.md` is a supporting implementation doc.
- If a frontend screen exists before its backend support is complete, it must show an honest unavailable or placeholder state.
- Do not fake success for auth, alerting, or other critical workflows.

## Next Two Sprints

Sprint 1:

- finish syncing stale docs to the current backend and frontend reality
- wire forgot-password, request-access, and verify-2fa flows cleanly to the implemented auth contract where needed
- connect profile, overview, wards, alerts, CHVs, and system pages to live backend data
- add visible stale-data indicators and last-updated surfaces

Sprint 2:

- add ward and alert detail routes using current list-data composition where necessary
- improve loading, empty, unauthorized, and partial-data states across dashboard pages
- create backend follow-up tickets for `GET /api/v1/wards/<id>/`, `GET /api/v1/alerts/<id>/`, `GET /api/v1/chvs/<id>/`, and `GET /api/v1/system/status/`
- decide whether any limited CHV web fallback flow is needed for pilot or demo support
