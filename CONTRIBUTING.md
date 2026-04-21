# Contributing to CCHIS

Thank you for contributing to CCHIS.

This repository is a prototype public health backend, so contribution safety matters as much as feature work. Please read this file together with [README.md](/Users/edwininganji/VSCodeProjects/cchis/README.md) and [SECURITY.md](/Users/edwininganji/VSCodeProjects/cchis/SECURITY.md) before opening a pull request.

## Development Baseline

- Python `3.12`
- Docker Compose v2
- PostgreSQL `16` with PostGIS `3.4`
- Redis `7`

Use the Docker-first local workflow unless you are intentionally changing the development baseline.

## Local Setup

1. Copy `.env.example` to `.env` and set local-only values.
2. Start the local stack:

```bash
docker compose up --build -d
docker compose ps
```

3. Run migrations and seed local demo data:

```bash
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo_data
```

4. Run tests before submitting changes:

```bash
docker compose exec backend python manage.py test --noinput
```

## Secrets and Local Environment Safety

- Never commit `.env`, API keys, database passwords, or provider credentials.
- Treat `.env.example` as documentation only, not as a production-ready config.
- If you add a new required environment variable, update `.env.example`, `README.md`, and any related security notes in the same patch set.
- If you suspect a secret was exposed, rotate it and document the follow-up in the PR or maintainer notes.

## Seeded Credentials

The repository includes a demo seeder for local development. Those credentials are unsafe for shared or production-like environments.

- `SEED_ENABLE_DEMO_USERS=True` is acceptable for isolated local development.
- Set `SEED_ENABLE_DEMO_USERS=False` for shared demos, staging, or deployment-like environments.
- Replace or rotate seeded credentials immediately if they were ever exposed beyond local development.

## Public Versus Protected Endpoints

Most API routes require JWT authentication. The main intentional public exception is:

- `POST /api/ussd/menu/`

Why it is public:

- USSD providers need to call it without an interactive browser login
- it serves low-connectivity and feature-phone flows
- it is protected through throttling and should stay narrowly scoped

If you add another public endpoint, document:

- why it must be public
- what abuse controls protect it
- what data it accepts and returns
- whether it should appear in `README.md` and `SECURITY.md`

## Demo Use Versus Real Deployment

Safe for demo or local development:

- seeded demo users
- relaxed local CORS settings
- local Docker networking
- non-HTTPS localhost access

Must change for real deployment:

- `DEBUG=False`
- strict `ALLOWED_HOSTS`
- explicit `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`
- secure cookie and proxy settings
- seeded demo credentials disabled or rotated
- proxy trust flags enabled only behind a trusted reverse proxy

## Pull Request Expectations

- keep changes focused and describe the user-facing or operational impact clearly
- include tests for behavioral changes when practical
- keep docs in sync with auth, security, environment, or deployment changes
- call out any new public endpoints, new secrets, or new operational assumptions explicitly

## Security-Sensitive Changes

Be extra careful with changes touching:

- authentication or permissions
- rate limiting
- proxy/header trust
- seeded credentials
- logging and audit trails
- GitHub Actions or dependency automation

When in doubt, mention the risk in the PR description so maintainers can review it with the right lens.
