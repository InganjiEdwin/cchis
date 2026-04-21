# CCHIS Auth Reset and Hardening Execution Plan

## Purpose

This document is the phase-by-phase execution plan for resetting the local development database and implementing the full next backend foundation patch set for CCHIS.

The goal is to complete all of the following in one clean backend slice:

- reset the local database and migration baseline
- add an `accounts` app
- introduce a custom Django user model
- add JWT authentication with SimpleJWT
- add role-based permissions
- protect existing API endpoints
- update seed data to include demo users
- harden Django auth/security defaults for non-dev use
- add open-source readiness docs (`LICENSE`, `SECURITY.md`)
- update project documentation to reflect the new auth-first foundation

This plan assumes:

- Docker Compose is the primary local workflow
- backend source is mounted into `/app`
- Python dependencies are installed from `backend/requirements.txt`
- the main services are `backend`, `db`, `redis`, `celery_worker`, and `celery_beat`
- wiping the local database is acceptable

## Success Criteria

This patch set is complete when all of the following are true:

- the local database has been recreated from a clean migration baseline
- `accounts.User` is the active `AUTH_USER_MODEL`
- JWT login, refresh, and current-user endpoints work in Docker
- all protected `risk` endpoints require authentication and appropriate roles
- seed data creates wards, CHVs, risk scores, and demo auth users
- automated tests pass after the reset and auth changes
- the repo includes `LICENSE`, `SECURITY.md`, and updated planning documentation

## Guiding Decision

We are doing the custom user model now, before the project grows further.

That is the right move because:

- Django custom user changes become much more painful after the schema and data footprint grow
- the current repo already has working APIs that should not remain unauthenticated for long
- JWT and role-aware permissions are foundational for the dashboard, CHV users, supervisors, and future deployment work

## Status Tracker

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 0 | Completed | Scope confirmed and local DB wipe approved. |
| Phase 1 | Completed | Local Docker DB volume was removed and generated migrations were reset. |
| Phase 2 | Completed | SimpleJWT, auth settings, env defaults, and auth-related Django settings were added. |
| Phase 3 | Completed | `accounts` app, custom `User` model, admin wiring, serializers, views, URLs, and permission helpers are in place. |
| Phase 4 | Completed | JWT login, refresh, me, and admin-controlled register endpoints are wired and verified. |
| Phase 5 | Completed | Existing `risk` endpoints are now protected with explicit role-aware permissions. |
| Phase 6 | Completed | Seed flow now creates demo users alongside wards, CHVs, and risk scores. |
| Phase 7 | Completed | Tests were updated for JWT and permissions, and the suite passes in Docker. |
| Phase 8 | Completed | `LICENSE`, `SECURITY.md`, `README.md`, and planning docs were updated. |
| Phase 9 | Completed | Docker rebuild, fresh migrations, migrate, and seed were run successfully. |
| Phase 10 | Completed | JWT login, `/api/auth/me/`, and public USSD smoke checks passed. |

## Phase 0: Pre-Flight Audit and Backup Awareness

### Objective

Confirm what will be destroyed locally and freeze the implementation scope before resetting the database.

### Status

Completed

### Outcome Notes

- local reset was explicitly approved
- implementation scope was fixed around custom user model, JWT, permissions, seed updates, and docs

### Tasks

- confirm there is no local-only data worth preserving in Postgres
- confirm the reset is only for local development, not any shared or remote environment
- confirm the current implementation scope for this patch set:
  - custom user model
  - JWT auth
  - role-based permissions
  - protected endpoints
  - demo user seeding
  - safer settings defaults
  - documentation hardening
- note the current migration situation:
  - `risk` already has migrations
  - no custom auth model exists yet
  - no JWT package is installed yet

### Deliverables

- explicit go-ahead to wipe local DB
- one agreed scope for the patch set

### Exit Criteria

- there is no uncertainty about whether local Postgres data can be removed

## Phase 1: Local Reset Preparation

### Objective

Prepare the repo for a clean schema reset before introducing the custom user model.

### Status

Completed

### Outcome Notes

- `docker compose down -v` was run
- the local Postgres volume was removed
- generated migrations were deleted while preserving `__init__.py`

### Tasks

- stop the running Docker services
- remove the local Postgres volume
- delete generated migration files while preserving each app's `migrations/__init__.py`
- verify the repo still contains only the intended migration package structure
- confirm `.env` still points to the correct local Docker services

### Commands to run

```bash
docker compose down -v
find backend -path "*/migrations/*.py" ! -name "__init__.py" -delete
find backend -path "*/migrations/*.pyc" -delete
```

### Risks

- accidental loss of non-committed local database state
- stale containers or images masking reset issues

### Deliverables

- clean local DB state
- migration folders preserved but emptied of generated migrations

### Exit Criteria

- the codebase is ready for a fresh `makemigrations` run

## Phase 2: Dependency and Settings Foundation

### Objective

Add the packages and settings required for JWT-based authentication and safer defaults.

### Status

Completed

### Outcome Notes

- `djangorestframework-simplejwt` was added to `backend/requirements.txt`
- `AUTH_USER_MODEL`, DRF auth defaults, JWT settings, and env-driven CORS/host defaults were added in `backend/core/settings.py`
- `.env.example` was updated with auth-ready local defaults

### Tasks

- update `backend/requirements.txt` to include `djangorestframework-simplejwt`
- update `backend/core/settings.py` to:
  - add `rest_framework_simplejwt`
  - add the new `accounts` app
  - set `AUTH_USER_MODEL = "accounts.User"`
  - configure DRF default authentication classes
  - configure DRF default permission classes
  - add `SIMPLE_JWT` settings
  - move CORS and host behavior to environment-driven defaults
  - keep local development workable in Docker
- update `.env.example` with auth/security-friendly defaults

### Recommended settings direction

- `DEBUG=False` by default outside explicit local development
- `ALLOWED_HOSTS` controlled via environment variable
- `CORS_ALLOW_ALL_ORIGINS=False` by default
- `CORS_ALLOWED_ORIGINS` explicitly listed
- DRF default auth uses JWT
- DRF default permission uses authenticated access

### Deliverables

- auth-ready Python dependencies
- auth-ready Django settings

### Exit Criteria

- the project can boot with the new auth settings once code is added

## Phase 3: Accounts App and Custom User Model

### Objective

Introduce a first-class user model that supports CCHIS roles from day one.

### Status

Completed

### Outcome Notes

- the `backend/accounts` app was created
- `accounts.User` now extends `AbstractUser`
- CCHIS profile fields were added: `full_name`, `phone_number`, `role`, and optional `ward`
- Django admin support and reusable permission helpers were added

### Tasks

- create `backend/accounts/apps.py`
- create `backend/accounts/models.py`
- create `backend/accounts/admin.py`
- create `backend/accounts/serializers.py`
- create `backend/accounts/views.py`
- create `backend/accounts/urls.py`
- create `backend/accounts/permissions.py`
- ensure the custom `User` model extends `AbstractUser`
- add CCHIS-specific fields:
  - `full_name`
  - `phone_number`
  - `role`
  - optional `ward`
- register the user model in Django admin with the extra profile fields

### Recommended roles

- `ADMIN`
- `SUPERVISOR`
- `CHV`
- `ANALYST`

### Deliverables

- new `accounts` app
- custom `User` model active in the project
- reusable permission helpers for role-aware API protection

### Exit Criteria

- `accounts.User` is the single user model used by Django

## Phase 4: JWT Authentication Endpoints

### Objective

Expose a minimal but production-sensible auth API for login, refresh, and current-user access.

### Status

Completed

### Outcome Notes

- a custom JWT token serializer was added in `backend/accounts/serializers.py`
- JWT claims now include `username`, `role`, and `ward_id`
- auth routes were added under `/api/auth/`
- the following endpoints are live:
  - `POST /api/auth/login/`
  - `POST /api/auth/refresh/`
  - `GET /api/auth/me/`
  - `POST /api/auth/register/`
- registration is restricted to admin-only use rather than public self-signup
- Docker smoke checks confirmed seeded users can log in and successfully call `/api/auth/me/`

### Tasks

- implement a custom token serializer that adds role-aware claims
- add auth endpoints:
  - `POST /api/auth/login/`
  - `POST /api/auth/refresh/`
  - `GET /api/auth/me/`
  - `POST /api/auth/register/` if we choose to keep admin-controlled registration in the API
- decide whether open registration should remain enabled

### Recommendation

Keep registration restricted for now. Since this is an early backend for controlled users such as admins, supervisors, and CHVs, registration should not be public by default.

### JWT claims to include

- `username`
- `role`
- `ward_id`

### Deliverables

- working JWT auth endpoints
- tokens that carry role and ward context

### Exit Criteria

- a seeded user can log in and retrieve `/api/auth/me/`

## Phase 5: Role-Based Permissions Across Existing APIs

### Objective

Protect the current backend endpoints according to operational role and channel sensitivity.

### Status

Completed

### Outcome Notes

- explicit DRF permission classes were added to `backend/risk/views.py`
- reusable role helpers from `backend/accounts/permissions.py` are now used across protected endpoints
- the authenticated and restricted API surface is now:
  - `GET /api/wards/` requires authentication
  - `GET /api/chvs/` requires admin or supervisor access
  - `GET /api/risk-scores/` requires authentication
  - `GET /api/risk-score/latest/` requires authentication
  - `GET /api/alerts/` requires admin or supervisor access
  - `POST /api/alerts/trigger/` requires admin or supervisor access
  - `POST /api/chv/triage/` requires CHV-or-higher access
  - `POST /api/chv/sync/` requires CHV-or-higher access
  - `GET /api/ussd/logs/` requires admin or supervisor access
- `POST /api/ussd/menu/` was intentionally kept public for callback-style access
- the updated test suite verifies unauthenticated and wrong-role denial behavior for the protected routes

### Tasks

- update `backend/risk/views.py` to add explicit permission classes
- use DRF permissions consistently rather than leaving views open
- keep only the deliberate public surface area open

### Recommended permission matrix

| Endpoint | Recommendation |
| --- | --- |
| `GET /api/wards/` | Authenticated |
| `GET /api/chvs/` | Admin or Supervisor |
| `GET /api/risk-scores/` | Authenticated |
| `GET /api/risk-score/latest/` | Authenticated |
| `GET /api/alerts/` | Admin or Supervisor |
| `POST /api/alerts/trigger/` | Admin or Supervisor |
| `POST /api/chv/triage/` | CHV or higher |
| `POST /api/chv/sync/` | CHV or higher |
| `POST /api/ussd/menu/` | Public |
| `GET /api/ussd/logs/` | Admin or Supervisor |

### Notes

- `USSD` should remain public only if it is intended to receive unauthenticated telco callbacks
- admin and supervisor flows should be protected more tightly than CHV operational endpoints
- staff or superuser status can remain a compatibility override where useful

### Deliverables

- no sensitive operational API remains unintentionally public

### Exit Criteria

- unauthorized requests to protected endpoints fail as expected

## Phase 6: Seed Data and Demo User Bootstrapping

### Objective

Make fresh local environments usable immediately after migration by seeding realistic demo users and domain data.

### Status

Completed

### Outcome Notes

- `backend/risk/management/commands/seed_demo_data.py` was updated to create demo auth users alongside wards, CHVs, and risk scores
- the seeded local users are:
  - `admin`
  - `supervisor`
  - `chv_demo`
  - `analyst_demo`
- seeded users include role assignments and ward links where appropriate
- the demo password was set to `ChangeMe123!`
- the README now documents that these credentials are for local development only
- after seeding, JWT login works without manual superuser creation

### Tasks

- update `backend/risk/management/commands/seed_demo_data.py`
- keep the current ward, CHV, and risk-score seeding
- add seeded auth users such as:
  - `admin`
  - `supervisor`
  - `chv_demo`
  - optional `analyst_demo`
- assign at least one seeded ward-linked user
- set demo passwords deliberately and document them
- make seed behavior idempotent where practical

### Demo credential policy

- use clearly demo-only credentials
- document that they must never be reused in a real deployment
- call this out in the README or security notes

### Deliverables

- seeded auth accounts for local testing
- one-command local demo bootstrap

### Exit Criteria

- after `seed_demo_data`, JWT login works without manual admin creation

## Phase 7: Tests and Verification Hardening

### Objective

Bring the automated test suite in line with the new auth model and current async behavior.

### Status

Completed

### Outcome Notes

- `backend/risk/tests.py` was rewritten to authenticate protected requests with JWT
- auth tests now cover login success, login failure, `/api/auth/me/`, admin-only registration, and permission denial cases
- permission tests now cover unauthenticated access denial and wrong-role access denial on protected `risk` endpoints
- the async alert-trigger contract was aligned with the current Celery-backed behavior
- public USSD behavior remains covered by tests
- the Docker test run passed with the updated suite

### Tasks

- update `backend/risk/tests.py` to authenticate protected requests
- add auth-focused tests for:
  - login success
  - login failure
  - `/api/auth/me/`
  - permission denial for unauthenticated users
  - permission denial for wrong roles
- verify public `USSD` behavior still works without auth
- fix any outdated expectations in current tests

### Important existing issue to address

The current tests and implementation appear out of sync around alert triggering behavior. The view now queues a Celery task and returns an async-style response, so tests should reflect the current contract.

### Deliverables

- reliable auth-aware test suite
- test coverage for the most important permission rules

### Exit Criteria

- `python manage.py test` passes after the reset

## Phase 8: Documentation and Open-Source Readiness

### Objective

Bring the repo documentation in line with the new architecture and public-readiness baseline.

### Status

Completed

### Outcome Notes

- `LICENSE` was added with MIT text
- `SECURITY.md` was added with basic security guidance for local and deployed use
- `README.md` was updated to document JWT auth, demo credentials, Docker reset/bootstrap flow, and public versus protected endpoints
- `cchis_backend_first_project_plan.md` was updated to reflect the auth-first foundation and next hardening direction
- `cchis_auth_reset_execution_plan.md` is being kept as the live execution tracker for this patch set

### Tasks

- add `LICENSE` with MIT text
- add `SECURITY.md`
- update `README.md` to mention:
  - JWT auth
  - demo credentials
  - Docker reset/bootstrap flow
  - public vs protected endpoints
- update `cchis_backend_first_project_plan.md` to reflect:
  - auth is now a first-class backend foundation
  - JWT is included from day one
  - next hardening priorities move to observability, deployment, and real ingestion

### Deliverables

- MIT license file
- security guidance
- updated planning and onboarding docs

### Exit Criteria

- a new contributor can understand how auth works and how to run the project locally

## Phase 9: Docker Rebuild and Migration Regeneration

### Objective

Recreate the application stack from scratch using the new auth-aware schema.

### Status

Completed

### Outcome Notes

- Docker images were rebuilt successfully after the auth changes
- the local database was recreated from a clean baseline
- fresh migrations were generated for `accounts` and `risk`
- `python manage.py migrate` completed successfully in Docker
- `python manage.py seed_demo_data` completed successfully in Docker
- the backend, database, Redis, Celery worker, and Celery beat services were brought back up successfully
- an existing circular import in the ML/task path was surfaced during rebuild and fixed as part of the reset

### Tasks

- rebuild the Docker images
- start services
- generate fresh migrations
- apply migrations
- seed demo data
- optionally create a manual superuser only if still needed beyond seeded demo users

### Commands to run

```bash
docker compose up --build -d
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo_data
docker compose exec backend python manage.py test
```

### Deliverables

- running Docker stack with clean schema
- fresh migration history aligned with the new user model

### Exit Criteria

- all services start successfully and migrations apply cleanly

## Phase 10: Smoke Testing and Acceptance Checks

### Objective

Verify the new foundation works end to end in the actual local Docker environment.

### Status

Completed

### Outcome Notes

- seeded-user login was verified through `POST /api/auth/login/`
- the returned access token was used successfully against `GET /api/auth/me/`
- protected-route denial behavior was verified by the automated tests for unauthenticated and wrong-role cases
- the public USSD endpoint was smoke-tested successfully
- the full Docker-based Django test suite passed after the reset and rebuild
- the custom user model is now active in the running environment and available to Django admin

### Tasks

- log in with a seeded demo user
- call `/api/auth/me/` with the returned access token
- verify a protected endpoint fails without a token
- verify a protected endpoint succeeds with the right role
- verify a restricted endpoint fails with the wrong role
- verify the public USSD endpoint still works
- verify Django admin can load with the custom user model

### Example smoke test flow

```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"ChangeMe123!"}'
```

```bash
curl http://localhost:8000/api/auth/me/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

```bash
curl http://localhost:8000/api/wards/
```

```bash
curl -X POST http://localhost:8000/api/ussd/menu/ \
  -H "Content-Type: application/json" \
  -d '{"sessionId":"demo-1","serviceCode":"*123#","phoneNumber":"+254700000001","text":"2*1"}'
```

### Deliverables

- verified login flow
- verified role protection
- verified public callback path

### Exit Criteria

- the backend is ready for authenticated frontend integration and safer sharing

## Recommended Execution Order

Execute the work in this order without skipping ahead:

1. Phase 0: Pre-Flight Audit and Backup Awareness
2. Phase 1: Local Reset Preparation
3. Phase 2: Dependency and Settings Foundation
4. Phase 3: Accounts App and Custom User Model
5. Phase 4: JWT Authentication Endpoints
6. Phase 5: Role-Based Permissions Across Existing APIs
7. Phase 6: Seed Data and Demo User Bootstrapping
8. Phase 7: Tests and Verification Hardening
9. Phase 8: Documentation and Open-Source Readiness
10. Phase 9: Docker Rebuild and Migration Regeneration
11. Phase 10: Smoke Testing and Acceptance Checks

## Out of Scope for This Patch Set

These items are important, but they should not block this auth foundation slice:

- full production deployment configuration
- HTTPS termination and Nginx reverse proxy setup
- advanced structured observability stack
- real SMS field validation
- real rainfall and flood ingestion maturity
- frontend integration work
- mobile app auth and token-refresh UX

## Immediate Next Step After This Plan

Once this plan is approved, implementation should begin with the database reset and the `accounts` app introduction in the same working branch.
