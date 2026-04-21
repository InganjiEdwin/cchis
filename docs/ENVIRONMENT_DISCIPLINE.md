# Environment Discipline

This document defines the minimum environment policy for CCHIS v1 so deployer expectations are explicit instead of implied.

## Environment Classes

The backend recognizes three deployer-owned environment labels through `CCHIS_ENVIRONMENT`:

- `local`
- `staging`
- `production`

If `CCHIS_ENVIRONMENT` is unset, the backend defaults to `local` to preserve local developer ergonomics. Shared environments should always set it explicitly.

## Promotion Expectations

### Local

Use `local` for isolated developer machines and disposable Docker environments.

Expected characteristics:

- developer-friendly ports and localhost traffic are acceptable
- demo data and seeded accounts may be used
- secrets may still be local-only, but they must remain out of version control
- proxy-trust settings should normally remain disabled unless intentionally testing behind a controlled proxy

### Staging

Use `staging` for shared QA, rehearsal, UAT, or deployment-like verification.

Expected characteristics:

- configuration should be production-like for hosts, origins, cookies, and proxy trust
- staging exists to validate deployability, not to preserve local shortcuts
- demo data should not appear by habit
- seeding must be a deliberate exception, not part of normal startup or release flow

### Production

Use `production` for real operational deployments.

Expected characteristics:

- no demo credentials or sample datasets
- no seeding-by-default behavior
- explicit deployer-owned secrets, host restrictions, and TLS assumptions
- schema changes and recovery steps must be executed intentionally and recorded operationally

## Migration Policy By Environment

- Local:
  - migrations may be run ad hoc during development
  - destructive local resets are acceptable when the developer intends them
- Staging:
  - migrations should run as a deliberate deployment step before validation begins
  - migration order and rollback assumptions should be tested here before production
- Production:
  - migrations should run only through approved deployment workflows
  - schema changes should be coordinated with backup, rollback, and post-deploy validation steps

Environment-wide rules:

- no environment should depend on `makemigrations` at runtime
- committed migrations are the deployable contract
- seed or fixture loading must not be silently coupled to migration execution

## Seed And Demo Data Policy

`python manage.py seed_demo_data` is a local-development command by default.

Current backend rule:

- when `CCHIS_ENVIRONMENT=local`, the command may run normally
- when `CCHIS_ENVIRONMENT` is `staging` or `production`, the command is blocked unless `SEED_ALLOW_NON_LOCAL=True` is set explicitly

This guard exists to keep demo seeding from leaking into shared environments by habit.

Additional expectations:

- keep `SEED_ENABLE_DEMO_USERS=False` in staging and production-style environments unless a controlled demo requires otherwise
- treat `SEED_ALLOW_NON_LOCAL=True` as a temporary exception for a specific need, not a standing default
- never rely on demo seeding as part of normal environment bootstrap

## Operational Notes

- `DEBUG` should remain `False` outside local development
- `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS` should be explicit in shared environments
- forwarded-header trust should only be enabled behind a deployer-controlled reverse proxy or load balancer
- environment labels should match deployment reality; a shared environment marked `local` defeats the discipline this policy is intended to create
