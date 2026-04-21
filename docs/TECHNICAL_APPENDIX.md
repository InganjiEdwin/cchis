# CCHIS Technical Appendix

## 1. Overview

The Child-Centered Climate Health Intelligence System (CCHIS) is an AI-driven platform designed to predict flood-induced cholera risk and enable early action across public health systems.

The system integrates climate, environmental, and epidemiological data to generate predictive insights and trigger coordinated responses at community and health system levels.

---

## 2. System Architecture

CCHIS is structured as a multi-layer architecture:

1. Data Ingestion Layer  
2. Feature Engineering Layer  
3. Machine Learning Layer  
4. Decision and Trigger Engine  
5. Delivery and Interface Layer  
6. Monitoring and Feedback Layer  

---

## 3. Technology Stack

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
- XGBoost / LightGBM

### Frontend
- React (dashboard)
- React Native / PWA (CHV tool)

### Messaging
- Africa’s Talking (SMS + USSD)

### Deployment
- Docker
- Nginx
- DigitalOcean

---

## 4. Machine Learning Architecture

### 4.1 Problem Formulation

We model cholera outbreak risk as:

- Binary classification (outbreak vs no outbreak)
- Multiclass classification (low, medium, high risk)
- Regression (expected case count)

---

### 4.2 Initial Models

#### Logistic Regression
- Baseline interpretable model
- Used for initial risk classification
- Advantages:
  - transparent coefficients
  - easy calibration
  - works well with limited data

---

#### Random Forest
- Captures nonlinear relationships
- Robust to noise
- Provides feature importance

---

#### Gradient Boosting (XGBoost / LightGBM)
- Higher predictive performance
- Handles missing values
- Captures complex interactions

---

### 4.3 Feature Engineering

#### Climate Features
- 3-day, 7-day, 14-day rainfall totals
- Rainfall anomalies
- Flood proxy indicators

#### Epidemiological Features
- Previous cholera incidence
- Seasonal trends
- Neighboring ward outbreaks

#### Spatial Features
- Ward adjacency
- Facility density
- Settlement concentration

#### Vulnerability Features
- Population under five
- WASH risk proxies
- Displacement indicators

---

### 4.4 Forecasting Models

#### Poisson Regression
- Used for count prediction
- Models expected case volume

#### Negative Binomial Regression
- Handles overdispersion in disease data
- More robust than Poisson

---

### 4.5 Model Evaluation

Classification:
- Accuracy
- Precision
- Recall
- F1 Score
- ROC-AUC

Forecasting:
- MAE
- RMSE

Operational:
- Lead time before outbreaks
- False alert rate

---

### 4.6 Future AI Evolution

#### Near-Term
- XGBoost optimization
- Ensemble models

#### Medium-Term
- Time-series models (SARIMAX)
- Temporal feature pipelines

#### Advanced
- LSTM for sequential prediction
- Graph Neural Networks for spatial spread
- Bayesian models for uncertainty

---

## 5. Decision Engine

Model outputs are converted into actions using rule-based logic.

Example:
- IF risk_score > 0.75
  - Trigger SMS alerts
  - Notify CHVs
  - Recommend ORS deployment

---

## 6. Offline and Low-Connectivity Design

### Smartphone Users
- Local storage
- Offline decision support
- Background sync

### Feature Phone Users
- USSD menu system
- SMS alerts

---

## 7. Integration

- DHIS2 integration via API or CSV
- Open APIs for interoperability

---

## 8. Data Governance

- Role-based access control
- Minimal personal data storage
- Aggregation and anonymization

---

## 9. Deployment Architecture

- Dockerized services
- Hosted on DigitalOcean
- CI/CD via GitHub Actions

### 9.1 Reverse Proxy Boundary

CCHIS assumes Django will commonly sit behind Nginx or a cloud load balancer in shared environments.

Deployment expectations:

- TLS should terminate at the reverse proxy or load balancer
- Django should only trust forwarded host, proto, and client-IP headers when that proxy is controlled by the deployer
- the proxy should strip inbound client-supplied `X-Forwarded-*` headers and rewrite them before forwarding requests
- direct public access to the Django container should be avoided in production-style deployments

Operational note:

- audit-event IP logging is intentionally conservative by default and will use `REMOTE_ADDR` unless `TRUST_X_FORWARDED_FOR=True` is explicitly enabled

---

## 10. Model Lifecycle

- Versioned models
- Scheduled retraining
- Performance monitoring
- Champion-challenger deployment

---

## 11. Key Design Principles

- Offline-first
- Low-bandwidth accessibility
- Interoperability
- Open-source by design
- Child-centered impact

---
