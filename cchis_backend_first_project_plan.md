# CCHIS UNICEF Prototype Plan

## Current direction

We are prioritizing **finishing the backend first** before building the ML layer and frontend. That means the immediate work is:

1. Clean and stabilize the Django backend
2. Add auth from day one with a custom user model, JWT, and role-based permissions
3. Finish core APIs, alerting, triage, offline sync, and logging
4. Add tests and seed/demo data
5. Add the ML prediction layer once the backend contracts are stable
6. Then connect dashboard and CHV interfaces

## When the ML layer gets added

We will add the ML layer **after the backend core is stable**, not at the very beginning.

That means:
- **Now:** finish backend models, serializers, services, views, URLs, tests, migrations, seed data, and channel integrations
- **Next:** add the prediction pipeline as the first part of the data layer
- **Then:** expose ML-generated ward risk scores through the existing APIs

In practice, the ML layer starts once these backend conditions are true:
- ward, risk score, alert, triage, sync, and USSD models are stable
- `/risk-scores/`, `/risk-score/latest/`, `/alerts/trigger/`, `/chv/triage/`, and `/chv/sync/` are working
- tests pass consistently
- demo seed data exists

## Updated roadmap

| Phase | Timeframe | Key Tasks | Output |
| --- | --- | --- | --- |
| **Phase 1: Setup & Core Backend** | Day 1–3 | - Create repo and project structure<br>- Set up backend and API app<br>- Configure PostgreSQL + PostGIS<br>- Define core data models (wards, risk, alerts, CHVs, triage)<br>- Build basic risk and alert APIs | Backend running locally with core endpoints |
| **Phase 2: Backend Completion & Field Workflows** | Day 4–6 | - Finish serializers, services, views, URLs, and migrations<br>- Add CHV triage flow<br>- Add offline sync support<br>- Add USSD session handling and logging<br>- Add tests and seed data | Stable backend ready for integrations |
| **Phase 3: Data + Prediction Layer** | Day 7–9 | - Ingest rainfall and flood data (mock first, real later)<br>- Build initial ML model (logistic regression baseline)<br>- Generate ward-level risk scores<br>- Store model outputs in DB<br>- Connect prediction outputs to `/risk-scores/` and alert logic | Functional risk prediction system |
| **Phase 4: Alerts System** | Day 10–11 | - Integrate Africa’s Talking SMS API<br>- Implement trigger logic for high-risk wards<br>- Test alert flow end-to-end<br>- Log alerts in DB | SMS alerts working with trigger engine |
| **Phase 5: Dashboard (Web UI)** | Day 12–14 | - Build React dashboard<br>- Display ward-level risk map (Leaflet)<br>- Show risk levels and alerts<br>- Add simple trend/risk charts | Visual demo dashboard |
| **Phase 6: CHV Tool (Mobile/Web)** | Day 15–17 | - Build simple CHV interface (web first)<br>- Capture symptoms and referrals<br>- Show rule-based guidance<br>- Connect offline sync flow | CHV decision support working |
| **Phase 7: Integration & Demo Prep** | Day 18–19 | - Connect backend, ML, alerts, dashboard, and CHV flows<br>- Seed demo data<br>- Improve logs and error handling<br>- Prepare demo script and screenshots/video | Fully integrated prototype |
| **Phase 8: Deployment & Polish** | Day 20–21 | - Dockerize services fully<br>- Deploy on DigitalOcean or similar<br>- Set up domain + SSL<br>- Finalize README and docs | Live deployed system + GitHub repo |

## What we are doing right now

### Backend-first checklist

- [x] Clean duplicated/corrupted backend files
- [x] Finalize models
- [x] Finalize serializers
- [x] Finalize services
- [x] Finalize views and URL routing
- [x] Add migrations for new models
- [x] Add tests for alerts, triage, USSD, and sync
- [x] Add seed/demo data
- [x] Verify local Docker flow end-to-end

### ML readiness checklist

We start the ML layer immediately after the backend-first checklist is mostly complete.

- [x] Confirm schema for ward-level input features
- [x] Define feature set: rainfall, flood indicator, historical cases, seasonality, population proxy
- [x] Create mock ingestion pipeline
- [x] Train logistic regression baseline
- [x] Write prediction results into `RiskScore`
- [x] Expose prediction run through command or scheduled job
- [x] Validate outputs with demo wards

## In-progress next steps

- [x] Expand backend tests for sync, alerts, USSD logs, and risk filters
- [x] Add ML package under `backend/risk/ml/`
- [x] Add `run_risk_model` management command
- [x] Add mock ward feature generation
- [x] Connect high-risk model outputs to alert triggering

## Backend status (post-audit)

The backend is now in a **strong prototype-complete state**:

### ✅ Completed
- Stable Django + PostGIS backend
- Clean models and migrations (including SyncQueue + USSD logs)
- Alert system (dashboard + SMS stub + integration-ready)
- CHV triage flow
- Offline sync pipeline
- USSD interaction + logging
- Seed/demo data pipeline
- Expanded automated test suite (API + edge cases)
- ML baseline (logistic regression)
- Prediction pipeline writing to `RiskScore`
- Optional alert triggering from ML outputs

### ✅ Hardening added next
- Custom `accounts` app with `AUTH_USER_MODEL`
- JWT auth via SimpleJWT
- Role-based permission helpers for admin, supervisor, CHV, and analyst access
- Protected API surface with USSD callback intentionally left public
- Demo user seeding for local Docker environments
- Safer environment-driven auth and CORS defaults

### ⚠️ Still thin / next hardening
- Logging exists, but observability is still basic
- Only one real feature input is live so far (rainfall); flood and case signals are still proxy/mock-derived
- SMS integration not yet field-tested
- Celery scheduling needs one final cleanup for dynamic month handling
- No real data ingestion yet (still mock features)
- Limited observability (logging/metrics)

## Next backend milestones

### 1. Production-hardening layer (short)
- [ ] Add structured logging (request + service level)
- [ ] Add pagination + filtering improvements
- [x] Add JWT auth with a custom user model and role-based permissions
- [ ] Add retry logic for failed alerts

### 1A. Docker-first async and ingestion rollout
- [ ] Add Redis service to Docker Compose
- [ ] Add Celery worker service
- [ ] Add Celery beat service
- [ ] Move alert sending to Celery tasks
- [ ] Move `run_risk_model` execution into Celery task
- [ ] Add one real rainfall source (static CSV first or API-backed fetcher)

### 2. Data layer upgrade (pre-ML maturity)
- [ ] Replace mock data with ingestion stubs (rainfall APIs, etc.)
- [ ] Add feature persistence (optional FeatureStore-like table)
- [ ] Version datasets used for model runs

### 3. ML layer maturity
- [ ] Persist trained model artifacts (optional)
- [ ] Add evaluation metrics (accuracy, precision, recall)
- [ ] Compare model runs over time
- [x] Add scheduled runs (cron/Celery)

### 4. System orchestration
- [x] Introduce Celery + Redis
- [x] Move model runs + alerts to async tasks
- [x] Add scheduled prediction jobs

## Working decision

**Decision:** finish backend first, then add ML as the next major layer.

This gives us a cleaner foundation, reduces rework, and makes it easier to plug the model into a stable API instead of rebuilding endpoints around the model later.

## Change log

### 2026-04-20
- Prioritized backend completion before ML
- Inserted roadmap table
- Shifted ML to start after backend stabilization
- Completed backend cleanup, migrations, tests, seed flow, USSD logging, and offline sync baseline
- Added Celery + Redis orchestration in Docker
- Added async model runs and async alert triggering
- Added initial rainfall ingestion with Open-Meteo + CSV fallback
- Added auth-first hardening plan for custom user model + JWT + role permissions
