# Security Policy

## Supported Use

This repository is a prototype public health decision-support system. Demo credentials and development defaults are provided for local testing only and must not be reused in real deployments.

## Reporting a Vulnerability

Please report suspected vulnerabilities privately to the maintainers before any public disclosure.

## Incident Readiness

When investigating suspected abuse or credential misuse:

- review auth audit events first for repeated failures, refresh-token abuse, account deactivation, and unexpected admin actions
- preserve relevant container logs, audit-event records, and timestamps before rotating services
- rotate credentials and seeded accounts if compromise is suspected
- narrow exposed hosts, origins, and proxy trust settings if the boundary is unclear
- document the affected time window, impacted accounts, and containment actions taken

## Security Notes

- Store secrets in environment variables only.
- Disable debug mode outside local development.
- Restrict allowed hosts and CORS origins in non-local environments.
- Rotate Django secrets, JWT signing secrets, and provider credentials for real deployments.
- Replace the example `SECRET_KEY` immediately and rotate it as part of any compromise response or environment rebuild.
- Use HTTPS everywhere outside local development.
- Replace demo credentials immediately in any shared or deployed environment.
- Enable secure cookie and proxy settings only when the deployment proxy is configured correctly.
- Do not trust `X-Forwarded-*` headers unless they come from your own reverse proxy or load balancer.
- Keep `TRUST_X_FORWARDED_FOR=False` unless your proxy strips client-supplied forwarded headers and rewrites them itself.
- Review throttle settings for auth and public callback endpoints before exposing the API publicly.
- Treat dependency update PRs and GitHub Actions workflow changes as security-sensitive maintenance work.

## Contributor Safety Notes

- Do not commit `.env`, provider keys, database dumps, or copied production configuration.
- Keep demo credentials local-only and disable seeded demo users in shared or deployment-like environments.
- Document any new public endpoint, auth flow, proxy assumption, or abuse-control change in the repo docs.
- Treat changes to CI, auth, permissions, throttling, and audit logging as security-relevant by default.
- Treat new patient-like, household-linked, or contact-rich field records as data-minimization work by default and document their retention direction before expanding them.
- Treat backup and restore workflows as security-sensitive operational paths and require traceable artifact, target-environment, and post-restore validation evidence.

## Public Endpoint Expectations

Current intentional public endpoint:

- `POST /api/v1/ussd/menu/`

This endpoint is public because USSD providers need callback access without an end-user login flow. It should remain tightly scoped, rate-limited, and limited to the minimum required request and response surface.

Any future public endpoint should be reviewed with the same questions:

- why must it be public
- what throttling or abuse protections exist
- what data exposure risk it creates
- what deployment assumptions it depends on

## Deployment Checklist

- Set `CCHIS_ENVIRONMENT` explicitly to `staging` or `production` outside isolated local development.
- In Compose-backed deployments, set `CCHIS_DJANGO_DEBUG=False`; Compose maps it to Django's container `DEBUG` setting.
- Set strict `ALLOWED_HOSTS`.
- Set explicit `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`.
- Enable `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, and `CSRF_COOKIE_SECURE` for HTTPS deployments.
- Enable `USE_X_FORWARDED_HOST`, `TRUST_X_FORWARDED_PROTO`, and `TRUST_X_FORWARDED_FOR` only behind a trusted reverse proxy.
- Confirm the proxy is the only public entry point and that it rewrites forwarded headers before they reach Django.
- Use non-zero HSTS values only after HTTPS is fully working.
- Rotate or replace all seeded credentials before any shared deployment.
- Prefer `SEED_ENABLE_DEMO_USERS=False` anywhere outside isolated local development.
- Do not run `seed_demo_data` in shared environments unless `SEED_ALLOW_NON_LOCAL=True` is set for an intentional, temporary demo use case.
- Review dependency audit output before releases and after any significant dependency refresh.
