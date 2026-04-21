# CCHIS Open Source Security, Rate Limiting, and Resilience Plan

## Purpose

This document defines the next security-hardening and open-source-readiness work for CCHIS after the authentication, access-control, account-management, and auth-audit foundations are in place.

The goal is to protect the project against common operational, abuse, and maintenance risks that affect open-source software, especially software that exposes authenticated APIs and public callback endpoints.

## Why This Matters

An open-source backend is not only judged by whether it works. It is also judged by whether:

- it fails safely
- it is hard to abuse
- its defaults are not dangerous
- maintainers can understand and respond to incidents
- contributors can work on it without leaking secrets or weakening security

For CCHIS specifically, the biggest next risks are:

- no rate limiting or throttling yet
- production-security defaults are still thin
- open-source secret handling and deployment assumptions need harder boundaries
- dependency, abuse, and observability concerns are not yet addressed as a structured plan

## Scope

This plan covers:

- API rate limiting and abuse controls
- broader Django production-security hardening
- proxy and deployment trust boundaries
- secret and configuration hygiene
- dependency and supply-chain practices
- open-source documentation and contribution safety
- operational logging, auditability, and incident readiness

## Success Criteria

This phase is successful when:

- the public and auth-related endpoints have rate limits in place
- production-focused security settings are explicit and environment-driven
- the app behaves correctly behind a reverse proxy
- secrets are not expected to live in source control
- the project documents secure local and production setup clearly
- maintainers have a safer operational baseline for running an open-source backend

## Immediate Next Patch Set

This plan begins with the following concrete implementation slice:

1. add DRF throttling for login, refresh, logout, change-password, and USSD
2. harden Django production-security settings, cookies, and proxy handling
3. tighten `.env.example` and security docs around deployment assumptions

This is the highest-value near-term security sequence for the current codebase.

## Phase 1: Rate Limiting and Abuse Protection

### Objective

Prevent easy abuse of authentication and public-facing endpoints.

### Status

Completed

### Outcome Notes

- DRF scoped throttling was enabled in global REST framework settings
- separate throttle buckets were added for login, refresh, authenticated auth-write actions, and public USSD traffic
- throttling was applied to:
  - `POST /api/auth/login/`
  - `POST /api/auth/refresh/`
  - `POST /api/auth/logout/`
  - `POST /api/auth/change-password/`
  - admin auth-management write endpoints
  - `POST /api/ussd/menu/`
- `.env.example` now documents the throttle-rate environment variables
- automated tests verify throttle behavior for high-risk auth and public USSD endpoints

### Endpoints to Prioritize

- `POST /api/auth/login/`
- `POST /api/auth/refresh/`
- `POST /api/auth/logout/`
- `POST /api/auth/change-password/`
- `POST /api/ussd/menu/`
- any future password-reset or admin-management endpoints

### Recommended Approach

- enable DRF throttling defaults
- use separate throttle buckets for:
  - anonymous auth attempts
  - authenticated user actions
  - public callback endpoints such as USSD
- prefer conservative defaults first, then tune from logs

### Suggested Initial Throttle Strategy

- login: strict anonymous rate limit
- refresh: moderate authenticated rate limit
- logout/change-password: moderate authenticated rate limit
- USSD callback: public endpoint limit tuned high enough for legitimate traffic but low enough to blunt abuse
- admin-only endpoints: lower volume but still protected

### Deliverables

- working DRF throttling classes and settings
- endpoint-specific throttle configuration where needed
- tests for rate-limited behavior on high-risk endpoints

## Phase 2: Production Security Hardening

### Objective

Harden Django settings for real deployments and non-local environments.

### Status

Completed

### Outcome Notes

- environment-driven Django security settings were added for SSL redirect, secure cookies, HSTS, proxy trust, content type sniffing protection, referrer policy, frame options, and CSRF trusted origins
- `.env.example` now documents the deployment-facing security variables explicitly
- `README.md` and `SECURITY.md` now explain how local-friendly defaults differ from shared or production deployments
- the hardening remains opt-in via environment variables so local Docker development is not broken

### Settings to Address

- `SECURE_PROXY_SSL_HEADER`
- `USE_X_FORWARDED_HOST`
- `SECURE_SSL_REDIRECT`
- `SESSION_COOKIE_SECURE`
- `CSRF_COOKIE_SECURE`
- `SESSION_COOKIE_HTTPONLY`
- `CSRF_TRUSTED_ORIGINS`
- `SECURE_HSTS_SECONDS`
- `SECURE_HSTS_INCLUDE_SUBDOMAINS`
- `SECURE_HSTS_PRELOAD`
- `SECURE_CONTENT_TYPE_NOSNIFF`
- `X_FRAME_OPTIONS`
- `SECURE_REFERRER_POLICY`

### Notes

- these should remain environment-driven so local Docker development stays usable
- proxy-related settings must assume a real reverse proxy or load balancer in production

### Deliverables

- safer production defaults in `backend/core/settings.py`
- `.env.example` entries documenting the required security environment variables

## Phase 3: Reverse Proxy and Deployment Boundary Safety

### Objective

Make the application safer when deployed behind Nginx, a cloud load balancer, or another reverse proxy.

### Status

Completed

### Outcome Notes

- `TRUST_X_FORWARDED_FOR` was added as an explicit environment-driven trust boundary instead of always trusting `X-Forwarded-For`
- auth audit IP extraction now defaults to `REMOTE_ADDR` unless forwarded IP headers are explicitly trusted
- `.env.example`, `README.md`, `SECURITY.md`, and `docs/TECHNICAL_APPENDIX.md` now describe TLS termination, forwarded-header expectations, and proxy rewrite assumptions
- automated tests now cover the safe-default and trusted-proxy IP extraction paths

### Work Items

- define trusted proxy assumptions
- configure SSL/header trust correctly
- document where TLS terminates
- ensure client IP extraction is not blindly trusted in all environments
- review audit logging of IPs under proxy conditions

### Deliverables

- explicit reverse-proxy assumptions in docs
- correct proxy-related Django settings
- safer IP logging behavior

## Phase 4: Secrets, Configuration, and Seeder Hygiene

### Objective

Make secrets and seeded credentials safer for open-source use.

### Status

Completed

### Outcome Notes

- `SECRET_KEY` remains required from the environment with no silent fallback in Django settings
- the demo seeder now supports `SEED_ENABLE_SUPERUSER` and `SEED_ENABLE_DEMO_USERS` so deployers can disable seeded accounts outside local development
- seeded superuser credentials remain environment-driven, and demo user passwords stay centrally controlled through `SEED_DEFAULT_PASSWORD`
- the seeder remains idempotent by using `update_or_create` for users and risk scores
- `.env.example`, `README.md`, and `SECURITY.md` now document seeded-account controls, secret rotation expectations, and the Docker-safe bootstrap sequence

### Work Items

- ensure `SECRET_KEY` is required and never defaulted silently in production-like use
- document secret rotation expectations
- move seeded credentials to environment-driven defaults where useful
- make the demo seeder explicitly idempotent
- create a clearly documented seeded superuser for local development
- ensure the seeder can be run safely in Docker after services are up

### Deliverables

- safer `.env.example`
- clearer local-only seeded credential model
- repeatable seeding flow

## Phase 5: Dependency and Supply-Chain Hygiene

### Objective

Reduce avoidable open-source maintenance risk from dependencies and contributor workflows.

### Status

Completed

### Outcome Notes

- GitHub Actions CI was added to build the backend container and run compile plus Django test checks on pushes and pull requests
- `pip-audit` was added as a CI job to catch known vulnerable Python packages from `backend/requirements.txt`
- Dependabot configuration was added for both Python dependencies and GitHub Actions updates
- `README.md` now documents the supported Python, Docker, PostgreSQL, and PostGIS baseline plus the repository's dependency maintenance policy
- `SECURITY.md` now treats dependency and workflow changes as part of the project’s security surface

### Work Items

- review pinned versus ranged dependencies
- add dependency vulnerability scanning in CI when ready
- add lint/test checks to PR workflow
- document minimum supported Python and Docker assumptions
- consider adding Dependabot or Renovate configuration

### Deliverables

- documented dependency policy
- CI-ready dependency scanning direction

## Phase 6: Abuse, Monitoring, and Incident Readiness

### Objective

Make abuse and operational problems easier to detect and respond to.

### Status

Completed

### Outcome Notes

- an admin-only auth audit-events API was added for operational review of login, refresh, logout, password, and account-lifecycle events
- an admin-only auth audit summary endpoint was added to quickly aggregate totals, failures, and event-type distribution during investigations
- auth audit logging now emits richer structured fields including ward, IP address, request path, and request method
- `README.md` now documents the main abuse-monitoring events exposed by the platform
- `SECURITY.md` now includes a lightweight incident-response checklist for maintainers

### Work Items

- define which auth and abuse events should be monitored
- add structured logging fields useful for abuse analysis
- review admin/audit visibility for auth events
- document a simple incident response checklist for maintainers

### Deliverables

- better operational visibility
- documented maintainer response guidance

## Phase 7: Open Source Documentation and Maintainer Safety

### Objective

Reduce accidental insecure usage by contributors and deployers.

### Status

Completed

### Outcome Notes

- `CONTRIBUTING.md` was added with contributor guidance for local setup, secrets handling, seeded credentials, public endpoints, and security-sensitive changes
- `README.md` now clearly separates safe local-demo behavior from requirements for real deployment
- `README.md` now documents the intentional public-endpoint policy and explains why `POST /api/ussd/menu/` is public
- `SECURITY.md` was expanded with contributor safety notes and public-endpoint expectations for downstream deployers and maintainers
- the repository now has clearer onboarding for contributors and fewer implied insecure defaults for downstream forks

### Work Items

- expand `SECURITY.md`
- add contribution guidance for secrets, local env files, and seeded credentials
- document what is safe for demo use versus what must change for real deployment
- document public endpoints and why they are public
- document rate limiting expectations once implemented

### Deliverables

- better security onboarding for contributors
- fewer insecure assumptions in downstream forks and deployments

## Recommended Implementation Order

1. Phase 1: Rate limiting and abuse protection
2. Phase 2: Production security hardening
3. Phase 3: Reverse proxy and deployment boundary safety
4. Phase 4: Secrets, configuration, and seeder hygiene
5. Phase 6: Abuse, monitoring, and incident readiness
6. Phase 5: Dependency and supply-chain hygiene
7. Phase 7: Open source documentation and maintainer safety

## Best Next Implementation Slice

The best next coding slice after this plan is:

1. add DRF throttling for login, refresh, logout, change-password, and USSD
2. harden Django production/security settings and proxy handling
3. finish seeder hygiene with explicit local superuser and environment-driven credentials

That sequence gives the highest immediate security value for an open-source API backend.
