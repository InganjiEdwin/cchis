# 🌍 Child-Centered Climate Health Intelligence System (CCHIS)

An open-source, AI-powered platform for predicting flood-driven cholera risk and enabling early, coordinated public health response in climate-vulnerable communities.

---

## 🚨 Why This Matters

Flood-prone regions such as Migori County in Kenya face recurring cholera outbreaks driven by climate variability and extreme weather events.

Current systems are:
- reactive
- fragmented
- slow to respond

**Children under five are the most affected.**

CCHIS addresses this by shifting from **reaction → prediction → early action**.

---

## 💡 What CCHIS Does

CCHIS transforms climate, environmental, and health data into **localized, actionable intelligence**.

### Core Capabilities

- 🔮 **Cholera Risk Prediction (7–14 days ahead)**
- 📡 **Automated Early Warning Alerts (SMS + USSD)**
- 🏥 **Healthcare Readiness Forecasting**
- 📱 **Offline-First CHV Decision Support Tool**
- 🌐 **Low-Bandwidth Access for Rural Communities**

---

## 🏗️ System Architecture

```plaintext
┌──────────────┐
│ Data Sources │
│--------------│
│ Rainfall     │
│ Flood Data   │
│ Health Data  │
│ Geo Data     │
└──────┬───────┘
       ▼
┌──────────────┐
│ ETL Pipeline │
└──────┬───────┘
       ▼
┌──────────────────────┐
│ Feature Engineering  │
└──────┬───────────────┘
       ▼
┌──────────────────────┐
│ ML Prediction Layer  │
└──────┬───────────────┘
       ▼
┌──────────────────────┐
│ Decision Engine      │
└──────┬───────────────┘
       ▼
┌────────────────────────────────────┐
│ Alerts & Interfaces                │
│------------------------------------│
│ SMS │ USSD │ Dashboard │ CHV App   │
└────────────────────────────────────┘
```

---

## 🧠 Machine Learning Approach

### Initial Models (MVP)

| Model | Purpose | Why |
|------|--------|-----|
| Logistic Regression | Risk prediction | Interpretable, robust in low-data settings |
| Random Forest | Benchmark | Captures non-linear relationships |

### Features

- Rainfall accumulation (3, 7, 14-day)
- Rainfall anomalies
- Flood indicators
- Historical cholera incidence
- Seasonal patterns
- Spatial relationships between wards

---

### 🔮 Future ML Evolution

- Gradient Boosting (XGBoost / LightGBM)
- Time-series forecasting models
- Spatiotemporal models
- Graph Neural Networks for spread modeling
- Bayesian forecasting for uncertainty

---

## 🧩 Technology Stack

### Backend

- Django
- Django REST Framework
- Celery
- Redis

### Database

- PostgreSQL
- PostGIS

### AI/ML

- Python
- pandas, numpy
- scikit-learn
- XGBoost / LightGBM (planned)

### Frontend

- React (dashboard)
- React Native / PWA (CHV tool)

### Messaging

- Africa’s Talking (SMS & USSD)

### Infrastructure

- Docker
- Nginx
- DigitalOcean

---
## ⚙️ Background Jobs and ETL

CCHIS uses Celery for asynchronous and scheduled processing.

ETL (Extract, Transform, Load) pipelines are used to:

* ingest rainfall, flood, and health data
* transform raw data into model-ready features
* load processed data into the database for prediction

Celery is used for:

* scheduled ETL jobs
* periodic risk score computation
* alert triggering and SMS dispatch

---

## 📱 Offline-First Design

### Smartphone Users (CHVs)

- Local data storage
- Offline case reporting
- Sync when connectivity returns

### Feature Phone Users

- USSD interface
- SMS alerts and guidance

---

## 🔐 Environment Variables

Create a `.env` file in the project root:

```
DEBUG=True
SECRET_KEY=your-secret-key

DB_NAME=cchis
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432

REDIS_URL=redis://localhost:6379/0

AFRICASTALKING_API_KEY=your-api-key
AFRICASTALKING_USERNAME=your-username
```

---

## 🗄️ Database Setup

Ensure PostgreSQL and PostGIS are installed:

```bash
CREATE DATABASE cchis;
\c cchis;
CREATE EXTENSION postgis;
```

---

## 📂 Project Structure

```plaintext
cchis/
│
├── backend/
│   ├── api/
│   ├── models/
│   ├── services/
│   └── tasks/
│
├── frontend-dashboard/
├── mobile-chv-app/
├── data-pipelines/
├── notebooks/
├── docs/
└── infra/
```

---

## ⚙️ Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL + PostGIS
- Redis
- Docker (optional)

---

### Installation

```bash
git clone https://github.com/your-org/cchis.git
cd cchis

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

python manage.py migrate
python manage.py runserver
```

---

### Run Background Workers

```bash
celery -A core worker -l info
celery -A core beat -l info
```

---

## 🔌 API Endpoints (Sample)

- `/api/wards/`
- `/api/risk-score/latest/`
- `/api/predict-risk/`
- `/api/alerts/`
- `/api/ussd/`

---

## 🔌 Example API Usage

```bash
curl http://localhost:8000/api/wards/
curl http://localhost:8000/api/risk-score/latest/
```

---
## 📡 USSD and SMS Integration

### USSD Endpoint

```bash
POST /api/ussd/
```

### SMS Alerts

Triggered when:

* risk score exceeds threshold
* decision engine generates alerts

---

## 🧪 Demo Data

```bash
python manage.py loaddata sample_wards.json
```

---

## 🌍 Pilot Deployment

**Location:**
Migori County, Kenya

**Target Wards:**

- North Kamagambo
- North Kadem
- Macalder Kanyarwanda (Kimai)
- Got Kachola

---

## 📊 Impact Goals

- ⏱️ 7–14 day early warning lead time
- ⚡ <5 minute alert delivery
- 📈 70%+ CHV adoption
- 🏥 Improved facility preparedness
- 👶 Reduced severe cholera cases in children under five

---

## 🚧 Current Status

* Backend API: In progress
* Risk prediction module: Functional prototype
* SMS and USSD integration: In progress
* Dashboard: Planned
* CHV mobile tool: Planned

---

## 🔒 Data Privacy and Security

CCHIS is designed with privacy, operational safety, and responsible data use in mind.

### Design principles
- Minimal personal data collection
- Aggregated and anonymized data where possible
- Role-based access control
- Secure handling of credentials and system configuration
- Support for public health workflows without unnecessary exposure of sensitive data

As the platform evolves, security and governance controls will be strengthened in line with deployment requirements.

---

## 🌐 Open Source Commitment

CCHIS will be released as a **Digital Public Good** under an open-source license (MIT or Apache 2.0).

---

## 🤝 Contributing

We welcome contributions from:

- Developers
- Data scientists
- Public health experts

---

## 📬 Contact

For partnerships and collaboration:

**Usalama Technology Limited**  
[Your Email]  
[Your Website / GitHub Org]

---

## 📄 License

MIT License (to be added)
