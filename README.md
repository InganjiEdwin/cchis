# 🛠️ CCHIS Technical Project Plan

## 1. Project Overview

**Project Name:**  
Child-Centered Climate Health Intelligence System (CCHIS)

**Objective:**  
To build an open-source, AI-powered platform that predicts flood-driven cholera risk and enables early warning, anticipatory action, healthcare readiness, and point-of-care decision support to reduce child morbidity and mortality.

**Deployment Context:**  
Pilot in flood-prone wards in Migori County, Kenya:
- North Kamagambo
- North Kadem
- Macalder Kanyarwanda (Kimai area)
- Got Kachola

---

## 2. System Objectives

### Core Capabilities
1. Generate ward-level cholera risk predictions (7–14 days ahead)
2. Trigger automated alerts and early action workflows
3. Support CHVs with decision guidance at point-of-care
4. Provide dashboards for government and planners
5. Support low-connectivity access through offline-first mobile workflows, USSD, and SMS

---

## 3. System Architecture

### High-Level Layers

#### 1. Data Layer
- Rainfall data (historical + real-time)
- Flood indicators (satellite or proxy)
- Health data (cholera trends)
- Geospatial data (wards, facilities)

#### 2. AI Prediction Layer
- Flood risk estimation
- Cholera risk classification model
- Risk scoring engine

#### 3. Action Layer
- Alert engine (SMS, API, USSD-triggered workflows)
- Trigger rules (threshold-based)
- Forecast outputs (cases, supplies)

#### 4. User Layer
- CHV mobile app with offline data capture and delayed sync
- USSD interface for low-end phone access
- Government dashboard
- Community SMS alerts

---

## 4. Technical Stack

### Backend
- Django
- Django REST Framework
- PostgreSQL + PostGIS

### Data Science
- Python (pandas, scikit-learn)
- Jupyter notebooks

### Frontend
- React (dashboard)
- React Native or web app (CHV tool)

### Messaging and Access Channels
- Africa’s Talking SMS API
- Africa’s Talking USSD API

### Background Jobs
- Celery + Redis

### Offline Storage
- SQLite or local device storage for CHV mobile app
- Background sync when connectivity returns

### Deployment
- Docker + Docker Compose
- DigitalOcean droplet
- Nginx

---

## 5. Core Modules

### 5.1 Risk Prediction Module
**Inputs:**
- Rainfall levels
- Flood proxy signals
- Historical cholera data

**Outputs:**
- Risk classification (LOW, MEDIUM, HIGH)
- Risk score (0–1)

---

### 5.2 Alert and Trigger Engine
**Logic:**
- IF risk_score > threshold → trigger alert

**Actions:**
- Send SMS to CHVs and stakeholders
- Expose alerts through USSD menus
- Log alert events
- Recommend interventions

---

### 5.3 CHV Decision Support Tool
**Primary channel:**
- Offline-first mobile app for smartphone-based CHVs

**Secondary channels:**
- USSD for guided menu access on feature phones
- SMS for notifications and simple prompts

**Input:**
- Symptoms (diarrhea, vomiting, dehydration)

**Context-aware logic:**
- Flood + symptoms = higher cholera likelihood

**Output:**
- Guidance (ORS, referral, hygiene advice)

**Offline design:**
- Mobile app stores submissions locally when offline
- Syncs automatically when connectivity returns
- USSD provides low-bandwidth access but requires mobile network availability

---

### 5.4 Dashboard Module
- Ward-level risk visualization
- Alert logs
- Trends and forecasts
- Facility readiness indicators

---

## 6. Data Model (Core Entities)

- Ward
- RiskScore
- Alert
- HealthFacility
- CHVUser
- CaseReport
- SyncQueue
- UssdSessionLog

---

## 7. API Design (Sample Endpoints)

- `GET /api/wards/`
- `GET /api/risk-score/latest/`
- `POST /api/predict-risk/`
- `POST /api/trigger-alerts/`
- `GET /api/alerts/`
- `POST /api/chv/case-report/`
- `POST /api/chv/sync/`
- `POST /api/ussd/`

---

## 8. Development Phases

### Phase 1: Core Backend (Days 1–3)
- Project setup
- Database schema
- Basic API endpoints

---

### Phase 2: Prediction Engine (Days 4–6)
- Data ingestion
- Initial ML model
- Risk scoring

---

### Phase 3: Alerts and USSD System (Days 7–10)
- SMS integration
- USSD integration
- Trigger logic
- Alert logging

---

### Phase 4: Dashboard (Days 11–13)
- Risk map visualization
- Charts and alerts

---

### Phase 5: CHV Tool with Offline Sync (Days 14–17)
- Symptom input interface
- Decision logic
- Local storage for offline capture
- Background sync flow

---

### Phase 6: Integration (Days 18–20)
- Connect all modules
- Test full flow across app, SMS, and USSD

---

### Phase 7: Deployment (Days 21–23)
- Dockerize services
- Deploy on DigitalOcean
- Configure domain and SSL

---

## 9. Key Metrics (for Evaluation)

- Prediction accuracy > 75%
- Alert delivery time < 5 minutes
- CHV usage rate > 70%
- Successful offline sync completion rate > 90%
- USSD session completion rate > 60%
- Reduction in response time > 30%
- Number of households reached

---

## 10. Open Source Strategy

- License: MIT or Apache 2.0
- Public GitHub repository
- Documentation includes:
  - Setup guide
  - API documentation
  - Architecture overview
  - USSD flow documentation
  - Offline sync design notes

---

## 11. Risks and Mitigation

| Risk | Mitigation |
|------|-----------|
| Limited real data | Use simulated and open datasets |
| Model accuracy | Start simple and iterate |
| Connectivity issues | Offline-first CHV app with delayed sync; SMS and USSD as low-bandwidth channels |
| USSD is not fully offline | Use USSD for accessibility and fallback, not as the offline mechanism |
| Scope creep | Focus on core features only |

---

## 12. Definition of Working Prototype

The system is considered complete when:
- Risk prediction is functional
- SMS alerts are triggered automatically
- USSD menu is working for basic CHV access
- Dashboard displays real-time risk
- CHV mobile tool supports offline capture and later sync
- System is deployed and accessible online

---

## 13. USSD Scope for MVP

### CHV USSD Menu
- 1. View latest ward risk level
- 2. Report suspected diarrhea case
- 3. Get cholera prevention guidance
- 4. Find nearest linked facility
- 5. Request callback or follow-up

### Community USSD Menu
- 1. Flood safety advice
- 2. Safe water guidance
- 3. Child diarrhea guidance
- 4. When to seek urgent care

---

## 🚀 Next Steps

- Initialize GitHub repository
- Set up Django backend and database
- Build `/risk-score` endpoint
- Build `/ussd/` endpoint
- Develop offline-first CHV case reporting flow
- Integrate SMS and USSD
- Deploy first working version