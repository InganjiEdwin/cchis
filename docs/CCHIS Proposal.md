**Child-Centered** **Climate** **Health** **Intelligence** **System**
**(CCHIS)**

A Proposal by Usalama Technology Limited


**Executive** **Summary**

The Child-Centered Climate Health Intelligence System (CCHIS) is an
open-source, AI-powered platform designed to reduce preventable illness
and deaths among children in climate-vulnerable communities by enabling
earlier detection of

flood-driven cholera risk and faster, more coordinated public health
response. The solution responds to a critical and growing challenge at
the intersection of climate resilience and child health: as flooding
becomes more frequent and severe, vulnerable communities face repeated
outbreaks of cholera and other diarrheal diseases, yet existing systems
remain largely reactive, fragmented, and too slow to prevent escalation.

CCHIS addresses this gap by transforming fragmented climate,
environmental, geospatial, and health data into localized, actionable
intelligence that can be used across the full response chain. The
platform combines rainfall patterns, flood indicators, historical
disease trends, and vulnerability signals to generate ward-level cholera
risk predictions up to 7 to 14 days in advance. These predictions are
not treated as stand-alone analytics. Instead, they are connected to a
decision and trigger layer that enables anticipatory action, including
targeted alerts to Community Health Volunteers and local authorities,
community hygiene and safe water messaging, and preparedness actions
such as the pre-positioning of oral rehydration salts and water
treatment supplies.

The system is designed for real-world deployment in low-resource
settings. It includes an offline-first decision support tool for
Community Health Volunteers, allowing frontline workers to access
symptom-based guidance and capture information even in areas with poor
connectivity. To ensure inclusion of users without smartphones or
internet access, the platform also supports SMS and USSD delivery
channels, enabling both CHVs and households to receive critical alerts
and guidance through basic mobile phones. This makes the platform
particularly suited to rural and underserved communities where the
burden of climate-sensitive disease is high and digital access is
uneven.

> **2**



The proposed pilot will focus on flood-prone wards in Migori County,
Kenya, including North Kamagambo, North Kadem, Macalder Kanyarwanda,
particularly the Kimai area, and Got Kachola. These communities
experience recurrent flooding associated with the Lake Victoria basin
and have faced repeated disruption, displacement, and increased health
vulnerability. The 2026 flooding events further highlighted the urgent
need for predictive, localized, and actionable systems that can support
earlier intervention before outbreaks spread widely. By grounding the
pilot in these high-risk wards, the project combines immediate relevance
with a realistic pathway to scale.

Technically, CCHIS is built as a modular and interoperable
climate-health intelligence platform. The initial predictive system will
use interpretable and data-efficient machine learning models, beginning
with logistic regression for

ward-level cholera risk estimation and Random Forest as a benchmark for
capturing non-linear relationships. As more localized and longitudinal
data becomes available, the system is designed to evolve toward
higher-performance models such as XGBoost or LightGBM, and later more
advanced spatiotemporal approaches where appropriate. This staged
approach balances immediate deployability, transparency, and scientific
rigor while creating a credible roadmap for continuous improvement.

The solution aligns directly with the four priority areas of the UNICEF
Venture Fund call. It supports **strategic** **planning** through
ward-level vulnerability mapping and climate-health risk scoring. It
advances **early** **warning** **and** **early** **action** by
generating predictive outbreak alerts and automated response triggers.
It strengthens **healthcare** **readiness** by forecasting likely surges
in disease burden and informing supply and staffing preparedness. It
improves **point-of-care** **support** through multilingual,
offline-capable decision assistance for Community Health Volunteers and
accessible low-bandwidth channels for communities. The project is
therefore not a single-point intervention, but a connected system that
links prediction, preparedness, and frontline response in a
child-centered way.

The expected impact of the pilot is both operational and health-related.
At the operational level, the system is designed to improve lead time
for outbreak detection, reduce response delays, strengthen facility
preparedness, and expand

> **3**


access to timely health guidance. At the health level, it is intended to
reduce the incidence and severity of cholera outbreaks affecting
children under five by supporting earlier prevention, faster referral,
and more coordinated response. Key indicators will include prediction
lead time, alert delivery time, CHV adoption, facility preparedness,
reduction in response time, and child health outcomes such as reductions
in severe dehydration and outbreak escalation.

The project is being led by a technically strong and execution-focused
team with expertise in software engineering, machine learning, and
mobile systems development. The founders hold degrees in Computer
Science and Informatics from Strathmore University and bring practical
experience in building digital systems for real-world environments. One
founder is currently pursuing an MSc in Artificial Intelligence and Data
Analytics at Loughborough University while working on applied AI systems
in the United Kingdom, including decision support platforms at Prorizon.
Combined with existing infrastructure, development capacity, and local
engagement in Migori County, this gives the team a strong foundation for
delivering a functional and scalable system.

The requested funding of USD 100,000 will support technical development,
pilot deployment, data integration, monitoring and evaluation,
open-source documentation, and readiness for scale. By the end of the
12-month implementation period, the project aims to deliver a validated,
open-source, and scale-ready climate-health intelligence platform that
can be adopted in other flood-prone regions of Kenya and adapted for use
across other UNICEF programme countries facing climate-sensitive health
threats.

**1.** **Problem** **Statement** **and** **Context**

Climate change is increasingly recognized as a major threat to child
health globally, with intensifying extreme weather events disrupting
access to safe water, healthcare, and basic services. Floods, droughts,
and heatwaves are not only becoming more frequent but also more severe,
disproportionately affecting vulnerable populations in low- and
middle-income countries. Children under five are

> **4**


particularly at risk, as climate-related shocks amplify exposure to
infectious diseases, malnutrition, and limited access to timely care.

In Kenya, recurrent flooding driven by changing rainfall patterns and
climate variability has become a significant public health concern,
particularly in regions surrounding Lake Victoria. Flood events
frequently lead to contamination of water sources, breakdown of
sanitation systems, and rapid transmission of waterborne diseases such
as cholera and acute diarrheal illness. These outbreaks place a
disproportionate burden on children, who are more susceptible to
dehydration and severe complications.

Migori County, located in the Lake Victoria basin, is among the regions
most affected by seasonal flooding. Flood-prone wards including North
Kamagambo, North Kadem, Macalder Kanyarwanda, particularly the Kimai
area, and Got Kachola experience repeated cycles of flooding that
disrupt livelihoods, displace communities, and increase exposure to
disease. The 2026 flooding events led to significant displacement in
areas such as Kimai, while vulnerable villages in Got Kachola, including
Konyango, Kabuto, and Modi, were among the first to require emergency
assistance. These patterns highlight the persistent vulnerability of
these communities and the recurring nature of climate-driven health
risks.

Despite the availability of climate data, satellite observations, and
health surveillance systems, there remains a critical gap in translating
this information into timely, localized, and actionable insights at the
community level. Current systems are largely reactive, with
interventions often initiated only after outbreaks are detected and
already spreading. Community Health Volunteers, who serve as the
frontline of the health system in rural Kenya, lack real-time tools to
anticipate disease risk, guide households effectively, and initiate
early preventive actions.

Existing approaches to outbreak management are therefore constrained by
delayed detection, limited predictive capacity, and weak integration
between climate intelligence and public health response. This results in
slower response times, inadequate preparedness at health facilities, and
missed opportunities to prevent disease transmission before it
escalates.

> **5**


The core problem is not the absence of data, but the absence of
integrated, predictive, and actionable systems that connect climate risk
signals to early health interventions at the last mile. Without such
systems, communities remain trapped in a cycle of reactive response,
leading to preventable illness and deaths among children during
climate-related events.

**2.** **Solution** **Overview**

To address the gap between climate risk data and timely health response,
we propose the **Child-Centered** **Climate** **Health**
**Intelligence** **System** **(CCHIS)**, an open-source, AI-powered
platform designed to predict flood-driven cholera risks and enable
early, coordinated action across community and health systems.

CCHIS transforms fragmented climate and health data into localized,
actionable intelligence that supports decision-making at multiple
levels, from national and county health authorities to frontline
Community Health Volunteers and households. The system integrates
rainfall patterns, flood indicators, geospatial data, and historical
disease trends to generate ward-level cholera risk predictions up to 7
to 14 days in advance. These predictions are continuously refined as new
data becomes available, enabling dynamic and context-specific risk
assessment.

Unlike traditional surveillance systems that respond after outbreaks
occur, CCHIS is designed to enable **anticipatory** **action**. When
predefined risk thresholds are reached, the system automatically
triggers a set of early interventions. These include sending targeted
alerts to Community Health Volunteers and local authorities via SMS and
USSD, initiating hygiene and safe water messaging for at-risk
communities, and prompting the pre-positioning of essential supplies
such as oral rehydration salts and water treatment solutions.

To strengthen healthcare readiness, CCHIS includes a forecasting module
that estimates potential case surges at facility level, allowing health
systems to prepare resources, staffing, and supplies in advance of peak
demand. This reduces strain on already limited health infrastructure and
improves the continuity of care during climate-related shocks.

> **6**

At the point of care, the system provides an offline-first decision
support tool for Community Health Volunteers. This tool enables CHVs to
input symptoms and receive context-aware guidance tailored to current
climate risk conditions, improving early detection, appropriate
referral, and household-level management of suspected cholera cases. For
broader accessibility, a USSD interface ensures that both CHVs and
community members can access critical health guidance using basic mobile
phones in low-connectivity environments.

CCHIS is designed as a modular, interoperable platform that can
integrate with existing national health systems such as DHIS2 and adapt
to different geographic contexts. By linking prediction to action across
the entire response chain, from early warning to frontline care, the
system shifts the paradigm from reactive outbreak response to proactive
prevention.

Unlike existing systems that remain reactive or operate as standalone
data dashboards, CCHIS integrates predictive modeling, decision
automation, and last-mile delivery into a single platform designed
specifically for low-resource, high-risk environments, ensuring that
risk insights translate directly into timely, actionable interventions
at community and facility level.

**3.** **System** **Design** **and** **Technical** **Approach**

The Child-Centered Climate Health Intelligence System is designed as a
multi-layer climate-health intelligence platform that combines
geospatial data engineering, supervised machine learning, rules-based
decision automation, and

low-connectivity delivery channels to support anticipatory public health
action in flood-prone settings.

**3.1** **End-to-End** **System** **Architecture**

The system is organized into six connected layers:

> **7**


**1.** **Data** **Acquisition** **Layer**

This layer ingests structured and semi-structured data from multiple
sources:

> ● rainfall observations and forecasts
>
> ● flood extent proxies or hydrometeorological indicators ● historical
> cholera and diarrheal disease data
>
> ● ward boundary shapefiles and village geographies
>
> ● health facility locations and service readiness information ●
> population and vulnerability indicators

**2.** **Data** **Processing** **and** **Feature** **Engineering**
**Layer**

Raw data is normalized, time-aligned, spatially joined, and transformed
into model-ready features. This includes:

In practical terms, this means the system converts raw ward-level
signals into structured numeric inputs that machine-learning models can
use consistently. This vectorization step turns inputs such as rainfall,
flood exposure, population density, facility readiness, and seasonal
context into a fixed feature representation for each ward and time
window, so models like logistic regression and Random Forest can learn
from comparable inputs and generate predictions reliably.

For categorical variables, the system may use one-hot encoding, which
represents categories such as month, season, facility type, or ward
class as separate binary indicators rather than forcing an artificial
numeric ordering. In later, more advanced model phases, embeddings may
also be introduced for richer representations of complex relationships,
for example between geography, time, facility catchments, or community
response patterns. In simple terms, embeddings are compact learned
numeric representations that help models capture similarity and context
more flexibly than manual category encoding alone.

> ● lagged rainfall features
>
> ● rolling rainfall accumulation windows such as 3-day, 7-day, and
> 14-day totals ● seasonality features
>
> ● flood exposure proxies
>
> ● distance-to-water and settlement proximity indicators where data is
> available ● historical outbreak density
>
> ● facility catchment vulnerability features ● ward-level temporal
> trend indicators

**3.** **Prediction** **Layer**

This layer performs outbreak risk estimation and surge forecasting using
supervised learning models and calibrated risk scoring.

**4.** **Decision** **and** **Trigger** **Layer**

Model outputs are translated into operational thresholds that trigger
alerts, preparedness actions, and frontline guidance.

**5.** **Delivery** **Layer**

> **8**


Outputs are served through:

> ● REST APIs
>
> ● web dashboards
>
> ● CHV decision-support application ● SMS alerts
>
> ● USSD menus

**6.** **Monitoring** **and** **Learning** **Layer**

This layer stores predictions, outcomes, alert logs, and user
interaction data to support evaluation, retraining, and continuous model
improvement.

**3.2** **Proposed** **Technology** **Stack**

**Backend** **and** **APIs**

> **9**


> ● **Django** for core application structure, admin, authentication,
> and business logic
>
> ● **Django** **REST** **Framework** for API endpoints
>
> ● **Celery** for asynchronous tasks such as risk scoring jobs, alert
> dispatch, and ETL scheduling
>
> ● **Redis** as task broker and cache

**Database** **and** **Geospatial**

> ● **PostgreSQL** as the primary relational database
>
> ● **PostGIS** for geospatial queries, ward-level overlays, and
> facility proximity calculations

**AI** **and** **Data** **Science**

> ● **Python**
>
> ● **pandas** for tabular data transformation ● **numpy** for numerical
> computation
>
> ● **scikit-learn** for initial classical ML models
>
> ● **xgboost** or **lightgbm** for later gradient boosting models ●
> **GeoPandas** for geospatial preprocessing
>
> ● **MLflow** optionally for experiment tracking and model versioning

**Frontend** **and** **User** **Interfaces**

> ● **React** for the planning and monitoring dashboard
>
> ● **React** **Native** or a lightweight PWA for the CHV application ●
> **USSD** **and** **SMS** **integration** **via** **Africa’s**
> **Talking**

**Deployment**

> ● **Docker** and **Docker** **Compose** ● **Nginx**
>
> ● **DigitalOcean** **droplet**
>
> ● **GitHub** **Actions** for CI/CD
>
> **10**


**3.3** **AI** **and** **Machine** **Learning** **Design**

**3.3.1** **Initial** **Modeling** **Strategy**

For the prototype and early pilot stage, the system will prioritize
**interpretable,** **robust,** **and** **data-efficient** **models**
rather than deep learning. Due to low-data public health settings, we
believe this is the correct engineering choice.

We propose three core model families:

**A.** **Logistic** **Regression** **for** **Ward-Level** **Risk**
**Classification**

**Use** **case:** binary or ordinal cholera risk classification at ward
level

**Why** **use** **we** **it** **first:**

> ● highly interpretable
>
> ● works well on smaller datasets ● easy to calibrate
>
> ● coefficients can be inspected to understand drivers of risk
>
> ● good baseline for public health settings where explainability
> matters

**Input** **examples:**

> ● 7-day cumulative rainfall ● 14-day cumulative rainfall
>
> ● rainfall anomaly relative to seasonal baseline ● recent flood proxy
> score
>
> ● prior cholera incidence in the ward
>
> ● seasonal month or epidemiological week ● neighboring ward outbreak
> presence
>
> ● WASH vulnerability proxies where available

**Output:**

> ● probability of elevated cholera risk
>
> **11**


> ● mapped to low, medium, or high categories

**Why** **this** **is** **important:**

This gives us a transparent baseline model that can be defended to
partners, and public health stakeholders.

**B.** **Random** **Forest** **Classifier** **for** **Non-Linear**
**Risk** **Interactions**

**Use** **case:** improved ward-level classification where feature
interactions are non-linear

**Why** **we** **use** **it:**

> ● captures non-linear patterns better than logistic regression ●
> robust to noisy inputs
>
> ● handles mixed feature types well ● can estimate feature importance
>
> ● useful when rainfall and flood variables interact in complex ways

**Tradeoff:**

> ● less interpretable than logistic regression
>
> ● can overfit if the dataset is small and not carefully validated

**Role** **in** **our** **stack:**

> This will be our second benchmark model after logistic regression.

**C.** **Gradient** **Boosted** **Trees** **with** **XGBoost** **or**
**LightGBM**

**Use** **case:** higher-performance outbreak risk estimation and future
production optimization

**Why** **use** **it:**

> ● often best-in-class for structured tabular prediction problems ●
> handles missing values better than many alternatives
>
> ● captures complex interactions and threshold effects
>
> **12**


> ● strong performance on small-to-medium sized real-world datasets

**Why** **we** **will** **not** **use** **it** **first** **as** **the**
**only** **model:**

> ● more tuning complexity
>
> ● less transparent than logistic regression
>
> ● may be harder to explain during early stakeholder engagement

**Recommended** **position:**

We shall use this as the **performance-oriented** **upgrade** **path**
once we have enough localized ward-level data.

**3.3.2** **Forecasting** **Facility** **Burden** **and** **Surge**
**Readiness**

Beyond classification of ward risk, the system can forecast expected
case surges for facilities.

**D.** **Negative** **Binomial** **Regression**

**Use** **case:** forecasting expected counts of diarrhea or suspected
cholera cases

**Why** **use** **it:**

> ● appropriate for count data ● interpretable
>
> ● easier to justify epidemiologically
>
> ● useful when modeling expected case volume per time period

**Why** **Negative** **Binomial** **may** **be** **better:**

> ● Cholera or diarrheal case data is often overdispersed
>
> ● Negative Binomial handles variance greater than the mean better than
> Poisson

**Outputs:**

> ● expected case counts by ward or facility
>
> ● surge thresholds for ORS, staffing, and bed readiness
>
> **13**


**3.3.3** **Spatial** **and** **Temporal** **Modeling** **Evolution**

As data volume and quality improve, we will migrate from simple tabular
models to more advanced spatiotemporal methods.

**Near-term** **upgrade** **path**

> ● **XGBoost** **/** **LightGBM** for stronger structured prediction
>
> ● **isotonic** **regression** **or** **Platt** **scaling** for
> probability calibration
>
> ● **stacked** **ensembles** combining logistic regression and boosted
> trees

These near-term additions should enter only after the early pipeline is
stable: data ingestion is reliable, ward-level features are consistent,
and the baseline classification workflow using logistic regression and
Random Forest has been evaluated on real operational data. In this
sequence, isotonic regression or Platt scaling are not primary
forecasting models; they are calibration methods introduced once the
system is already producing usable probability outputs and we need those
probabilities to become more trustworthy for alert thresholds and
decision-making.

**Medium-term** **upgrade** **path**

> ● **Temporal** **models** such as: ○ SARIMAX
>
> ○ Prophet only if useful for trend baselines, not primary disease
> intelligence
>
> ○ time-window boosted models with lag features

These temporal models should enter later, once the platform has
accumulated enough clean, time-aligned historical data to justify
sequence-aware forecasting. They are therefore not phase-one
requirements. They become useful only after the ETL layer, daily
scoring, and model-governance workflow are mature enough to support more
advanced temporal reasoning without weakening interpretability or
operational trust.

**Advanced** **future** **path**

Once we accumulate substantial ward-level historical data over multiple
seasons, we can explore:

> ● **LSTM** **or** **Temporal** **Convolutional** **Networks** for
> sequential outbreak forecasting ● **Graph** **Neural** **Networks**
> for spatial diffusion across neighboring wards or
>
> hydrological networks
>
> ● **Bayesian** **hierarchical** **spatiotemporal** **models** for
> uncertainty-aware public health forecasting
>
> ● **multitask** **models** that jointly predict outbreak probability,
> expected case count, and supply demand

These are not necessary for the MVP, but they form a credible research
and scale path.

**3.3.4** **Why** **We** **Do** **Not** **Start** **with** **Deep**
**Learning**

> **14**


For this use case, deep learning is not the best first choice because:

> ● early datasets are likely small and sparse
>
> ● structured public health and climate data often performs very well
> with tree-based models
>
> ● interpretability matters for trust and adoption
>
> ● deployment in low-resource settings benefits from lighter models

**3.4** **Feature** **Engineering** **Strategy**

Core features will include:

**Hydrometeorological** **features**

> ● cumulative rainfall over multiple windows ● rainfall anomalies from
> historical means
>
> ● flood event indicators
>
> ● days since heavy rainfall threshold exceeded

**Epidemiological** **features**

> ● prior cholera or diarrhea incidence ● rolling case counts
>
> ● seasonal outbreak history
>
> ● neighboring ward outbreak signal

**Spatial** **features**

> ● ward adjacency
>
> ● distance to major water bodies if available ● floodplain exposure
> proxy
>
> ● health facility density
>
> ● settlement concentration

**Vulnerability** **features**

> **15**


> ● population under five ● WASH risk proxies
>
> ● displacement indicators where available ● facility readiness
> indicators

**3.5** **Validation** **and** **Evaluation** **Framework**

For classification tasks:

> **●** **Accuracy:** How often is the model correct overall?. If the
> model is right 80 out of 100 times → accuracy = 80%.
>
> **Why** **it** **is** **important:** If outbreaks are rare, accuracy
> can be misleading.
>
> ● **Precision**: When the model says HIGH RISK, how often is it
> actually correct?. High precision = few false alarms
>
> **Why** **it** **is** **important:** Too many false alerts → people
> stop trusting the system
>
> **●** **Recall(Sensitivity):** Of all real high-risk situations, how
> many did we catch? High recall = fewer missed outbreaks
>
> **Why** **it** **is** **important:** Missing an outbreak is worse than
> a false alert
>
> **●** **F1** **score:** Balance between precision and recall.
>
> **Why** **it** **is** **important:** Useful because we want both:
>
> ● Not too many false alerts
>
> ● Not too many missed outbreaks
>
> **●** **ROC-AUC(Receiver** **Operating** **Characteristic** **–**
> **Area** **Under** **Curve):** Measures how well the model separates
> high-risk vs low-risk
>
> **Why** **it** **is** **important:**Can the model rank risky vs safe
> areas correctly?
>
> **16**


> ● **PR-AUC(Precision-Recall** **Area** **Under** **Curve):** Used when
> outbreaks are rare (class imbalance)
>
> **Why** **important:** In our case, most days/wards are NOT outbreaks
>
> **PR-AUC** focuses on:
>
> ● detecting rare events correctly

For operational performance:

> ● **Lead** **time** **before** **observed** **outbreaks:** How early
> did we predict risk before it actually happened?
>
> Example:
>
> ● prediction on Monday ● outbreak on Friday
>
> → lead time = 4 days
>
> Goal: 7–14 days
>
> ● **False** **alert** **rate:** How many alerts were unnecessary?
>
> Too high → system loses credibility
>
> Too low → may miss real risks
>
> ● **Proportion** **of** **high-risk** **wards** **correctly**
> **flagged:** Did we identify the right locations? This is basically
> recall but **spatially** **focused**
>
> **●** **Calibration** **quality** **of** **risk** **probabilities:**
> If the model says 80% risk, is it really 80%? This is about
> **trustworthiness** **of** **probabilities**
>
> Example:
>
> ● model predicts 0.8 risk → should correspond to real-world frequency
>
> Very important because:
>
> We use thresholds like risk \> 0.75
>
> **17**


For forecasting tasks:

> ● **MAE** **(Mean** **Absolute** **Error):** Average difference
> between predicted and actual values. Example:
>
> ○ Predicted: 100 cases ○ Actual: 90 cases
>
> → error = 10
>
> MAE = average of such errors
>
> **●** **RMSE** **(Root** **Mean** **Squared** **Error):** Like MAE,
> but penalizes large errors more. Big mistakes hurt more.
>
> Useful when:
>
> We want to avoid large mispredictions.
>
> ● **MAPE(Mean** **Absolute** **Percentage** **Error)** where
> appropriate: Error as a percentage
>
> Example:
>
> ● predicted: 100 ● actual: 80
>
> → error = 25%
>
> Note:
>
> Doesn’t work well when values are very small
>
> **●** **Outbreak** **lead-time** **usefulness:** Did the prediction
> come early enough to act? Even if accurate:
>
> ○ prediction 1 day before outbreak = not useful ○ prediction 10 days
> before = very useful

Evaluation will use **time-aware** **validation**, not random train-test
split, because this is a temporal public health prediction problem.

> **18**


**3.6** **Model** **Governance** **and** **Retraining**

The platform will maintain:

> ● model version history
>
> ● training dataset versions ● feature definitions
>
> ● calibration reports
>
> ● performance reports by ward and season

Retraining will follow:

> ● scheduled retraining every quarter
>
> ● or event-driven retraining after major rainy seasons
>
> ● with champion-challenger evaluation before promotion to production

**3.7** **Decision** **Engine** **and** **Trigger** **Logic**

The prediction layer will not directly message users without mediation.
Instead, model scores feed a rules engine.

**Example** **logic**

> ● if risk_score \>= 0.75 and flood proxy high, classify ward as HIGH ●
> if HIGH, then:
>
> ○ send CHV alert
>
> ○ send county dashboard notification ○ activate prevention messaging
>
> ○ flag facilities for ORS readiness review

This hybrid approach is best:

> ● **ML** **for** **prediction**
>
> ● **rules** **for** **accountability** **and** **operational**
> **safety**
>
> **19**


**3.8** **Offline** **and** **Low-Bandwidth** **Design**

**Smartphone** **pathway**

The CHV application supports:

> ● local data caching
>
> ● offline form completion
>
> ● local decision support logic
>
> ● deferred synchronization when connectivity returns

**Feature** **phone** **pathway**

USSD provides:

> ● ward risk lookup ● case reporting
>
> ● prevention guidance ● referral prompts

Important distinction:

> ● **offline** **capability** **comes** **from** **the** **app**
>
> ● **USSD** **provides** **low-bandwidth** **accessibility,** **not**
> **offline** **operation**

**3.9** **Interoperability**

The platform will expose structured APIs for:

> ● risk score retrieval ● alert events
>
> ● facility readiness summaries ● CHV submissions
>
> ● sync events

DHIS2 integration can initially be:

> **20**


> ● CSV export/import
>
> ● API-based sync later

**4.** **Expected** **Impact** **and** **Key** **Metrics**

The Child-Centered Climate Health Intelligence System is designed to
reduce preventable illness and deaths among children by enabling earlier
detection of climate-driven health risks and faster, coordinated
response across community and health systems. By shifting from reactive
outbreak management to anticipatory action, the system strengthens
resilience at both household and health system levels.

**4.1** **Expected** **Impact**

At the community level, the system is expected to improve early
awareness and preventive behavior by delivering timely, localized alerts
and guidance to households and Community Health Volunteers. This will
support safer water practices, improved hygiene behaviors, and earlier
care-seeking for children presenting with symptoms of diarrheal illness.

At the health system level, the platform enables improved preparedness
by forecasting potential disease surges and informing the allocation of
critical supplies such as oral rehydration salts, water treatment
solutions, and clinical staffing. This reduces the likelihood of
stockouts and improves the ability of facilities to manage increased
caseloads during flood-related events.

For frontline health workers, particularly Community Health Volunteers,
the system enhances decision-making by providing context-aware guidance
that integrates environmental risk with symptom-based assessment. This
improves early identification of suspected cholera cases, appropriate
referral, and continuity of care at the household level.

Overall, the system is expected to reduce delays in response, improve
coordination across actors, and decrease the incidence and severity of
cholera outbreaks affecting children under five in flood-prone
communities.

> **21**


**4.2** **Key** **Metrics** **and** **Indicators**

**A.** **Early** **Warning** **and** **Prediction** **Performance**

> ● **Prediction** **accuracy:** proportion of correctly identified
> high-risk periods
>
> ● **Lead** **time:** number of days between risk detection and
> observed outbreak signals (target: 7–14 days)
>
> ● **False** **alert** **rate:** proportion of alerts not followed by
> increased disease incidence

**B.** **Response** **and** **Action** **Metrics**

> ● **Alert** **delivery** **time:** time from risk threshold detection
> to alert dissemination (target: \< 5 minutes)
>
> ● **Trigger** **activation** **rate:** proportion of high-risk events
> that result in early action being initiated
>
> ● **Response** **time** **reduction:** decrease in time between risk
> detection and intervention compared to baseline (target: ≥ 30%)

**C.** **Health** **System** **Readiness** **Metrics**

> ● **Facility** **preparedness** **rate:** proportion of facilities
> that receive and act on risk alerts
>
> ● **Stockout** **reduction:** decrease in frequency of essential
> supply shortages during peak risk periods
>
> ● **Surge** **forecast** **accuracy:** alignment between predicted and
> actual increases in case volume

**D.** **Community** **and** **CHV** **Engagement** **Metrics**

> ● **CHV** **adoption** **rate:** proportion of targeted CHVs actively
> using the system (target: ≥ 70%)
>
> ● **USSD** **session** **completion** **rate:** proportion of users
> successfully completing guidance interactions
>
> **22**


> ● **Number** **of** **households** **reached:** total number of
> individuals receiving alerts and guidance

**E.** **Child** **Health** **Impact** **Metrics**

> ● **Reduction** **in** **cholera** **incidence** **among**
> **children** **under** **five** in target wards ● **Reduction** **in**
> **severe** **dehydration** **cases** presenting at health facilities
>
> ● **Reduction** **in** **outbreak** **escalation** **time**, measured
> from first case to peak transmission
>
> ● **Improved** **early** **care-seeking** **behavior**, measured
> through CHV reports and facility data

**4.3** **Monitoring** **and** **Evaluation** **Approach**

The system will incorporate built-in monitoring capabilities to track
predictions, alerts, user interactions, and outcomes. Data will be
collected through system logs, CHV reporting tools, and integration with
health information systems where available. Evaluation will focus on
both technical performance, such as model accuracy and timeliness, and
real-world impact, including behavior change and health outcomes.

Baseline data will be established during the initial deployment phase to
enable comparison over time. Continuous feedback loops will be used to
refine both the predictive models and the operational workflows,
ensuring that the system remains responsive to local conditions and user
needs.

**4.4** **Scalability** **and** **Replicability**

The system is designed for scalability across geographies and disease
contexts. While the initial pilot focuses on flood-prone wards in Migori
County, the underlying architecture is modular and adaptable to other
regions within Kenya, particularly counties in the Lake Victoria basin
with similar climate and health risk profiles. Beyond Kenya, the
platform can be extended to other UNICEF programme countries facing
climate-sensitive disease outbreaks by adapting input data sources and
retraining models on local datasets. Its open-source design,
interoperability with systems such as DHIS2, and reliance on widely
available data sources enable rapid

> **23**


replication without significant infrastructure investment, supporting
broader regional and global scale-up. The same architecture can be
extended beyond cholera to other climate-sensitive diseases such as
malaria and dengue, enabling a unified platform for predictive
surveillance and early action across multiple public health risks.

**5.** **Implementation** **Plan** **and** **Timeline**

The implementation of the Child-Centered Climate Health Intelligence
System will follow a phased, iterative approach over a 12-month period,
moving from prototype refinement to pilot deployment and scale
readiness. The plan prioritizes early validation in real-world settings,
continuous feedback, and progressive system improvement.

**5.1** **Phase** **1:** **System** **Development** **and**
**Refinement** **(Months** **1–3)**

During the initial phase, the focus will be on strengthening the core
system components and preparing the platform for field deployment.

Key activities will include:

> ● Refinement of the predictive model using localized climate and
> health datasets from Migori County
>
> ● Development and testing of the alert and trigger engine, including
> SMS and USSD integration
>
> ● Completion of the CHV decision support tool with offline
> functionality and synchronization capabilities
>
> ● Integration of core system components into a unified platform ●
> Initial testing using simulated and historical data scenarios

At the end of this phase, a fully functional prototype will be ready for
pilot deployment, with all core modules operational.

> **24**


**5.2** **Phase** **2:** **Pilot** **Deployment** **and** **Field**
**Testing** **(Months** **4–6)**

The second phase will focus on deploying the system in selected
flood-prone wards in Migori County, including North Kamagambo, North
Kadem, Macalder Kanyarwanda, and Got Kachola.

Key activities will include:

> ● Deployment of the platform in collaboration with local health
> authorities and community networks
>
> ● Onboarding and training of Community Health Volunteers and local
> stakeholders
>
> ● Activation of real-time data flows and alert systems
>
> ● Monitoring of system performance, including prediction accuracy,
> alert delivery, and user engagement
>
> ● Collection of feedback from CHVs, health facilities, and communities

This phase will validate the system under real-world conditions and
identify areas for improvement.

**5.3** **Phase** **3:** **Evaluation** **and** **System**
**Optimization** **(Months** **7–9)**

Following pilot deployment, the system will undergo detailed evaluation
and iterative refinement based on performance data and user feedback.

Key activities will include:

> ● Analysis of prediction accuracy, lead time, and operational
> effectiveness ● Refinement of machine learning models to improve
> performance and
>
> calibration
>
> ● Enhancement of user interfaces and workflows based on CHV and
> stakeholder feedback
>
> **25**


> ● Optimization of alert thresholds and trigger logic
>
> ● Strengthening of data pipelines and system reliability

This phase ensures that the system is both technically robust and
user-centered.

**5.4** **Phase** **4:** **Scale** **Preparation** **and** **Expansion**
**(Months** **10–12)**

The final phase will focus on preparing the platform for broader
deployment and long-term sustainability.

Key activities will include:

> ● Expansion of the system to additional wards or counties based on
> pilot results ● Integration with national health information systems
> such as DHIS2
>
> ● Documentation of the platform as an open-source digital public good,
> including technical documentation, deployment guides, and training
> materials
>
> ● Strengthening partnerships with government and implementing
> organizations ● Development of a scale-up strategy for deployment in
> other
>
> climate-vulnerable regions

By the end of this phase, the system will be ready for replication and
scale across Kenya and other UNICEF programme countries.

**5.5** **Implementation** **Approach**

The project will follow an iterative development model, combining agile
software development practices with continuous field validation. Early
deployment in a real-world setting will ensure that the system is
designed around user needs and operational realities, rather than purely
technical assumptions.

Close collaboration with Community Health Volunteers, local authorities,
and health system stakeholders will be central throughout the
implementation process. This

> **26**


participatory approach ensures that the system remains relevant, usable,
and aligned with existing workflows.

**5.6** **Key** **Milestones**

> ● Month 3: Functional prototype ready for deployment
>
> ● Month 6: Pilot completed with active system usage in target wards ●
> Month 9: System optimized based on evaluation data
>
> ● Month 12: Platform documented, integrated, and ready for scale

**6.** **Team** **and** **Organizational** **Capacity**

The Child-Centered Climate Health Intelligence System is being developed
by a technically skilled and execution-focused team with strong
foundations in software engineering, data science, and applied
artificial intelligence. The founding team holds degrees in Computer
Science and Informatics from Strathmore University, one of the leading
institutions for technology education in the region, with training that
emphasizes practical system development, data-driven problem solving,
and

real-world deployment.

The team brings core expertise across backend engineering, machine
learning, and mobile application development, enabling full-stack
development of the platform. This includes the design and implementation
of data pipelines, predictive models, APIs, and user-facing applications
tailored for low-resource environments. One of the founders is currently
pursuing an MSc in Artificial Intelligence and Data Analytics at
Loughborough University, while also working on applied AI systems in the
United Kingdom, including athlete performance and decision support
platforms at Prorizon. This experience strengthens the team’s capability
to design, evaluate, and operationalize machine learning systems in
real-world contexts.

From an operational perspective, the team has experience building and
deploying digital solutions and is already supported by existing
infrastructure, including a cloud-based server environment for
development and testing. This enables rapid

> **27**


prototyping, iteration, and deployment. The team is also experienced in
designing systems that operate under real-world constraints such as
intermittent connectivity, low-end devices, and limited data
availability.

At the local level, the project is supported through engagement with
community leadership in Migori County, including coordination with the
Member of County Assembly in North Kamagambo ward. This provides a
foundation for community entry, stakeholder alignment, and pilot
deployment. The team is also in the process of expanding partnerships
with county health authorities, non-governmental organizations, and
other ecosystem actors to support implementation, training, and scale.

The combination of strong technical capability, applied AI experience,
local context understanding, and existing infrastructure positions the
team to deliver a functional system within a short timeframe and to
adapt it effectively based on field feedback. The requested funding will
complement these capabilities by enabling structured pilot deployment,
model validation, and expansion to additional high-risk communities.

**7.** **Budget** **and** **Use** **of** **Funds**

The requested funding of USD 100,000 will be used to support the
development, pilot deployment, and validation of the Child-Centered
Climate Health Intelligence System in flood-prone areas of Migori
County. The budget is structured to ensure efficient use of resources
while prioritizing core system development, real-world testing, and
readiness for scale.

**7.1** **Budget** **Allocation**

**A.** **Technical** **Development** **and** **Engineering** **(40%)**

This component will support the continued development and refinement of
the platform’s core technical systems. Activities include:

> **28**


> ● Backend development and API implementation
>
> ● Machine learning model development and validation ● Development of
> the CHV decision support tool
>
> ● Integration of SMS and USSD communication channels ● System testing
> and performance optimization

This investment ensures the delivery of a stable, functional, and
scalable platform.

**B.** **Pilot** **Deployment** **and** **Field** **Implementation**
**(25%)**

This component focuses on deploying the system in selected wards in
Migori County and supporting real-world use.

Activities include:

> ● Community entry and stakeholder engagement
>
> ● Training of Community Health Volunteers and local users ● Deployment
> of the platform in target wards
>
> ● Field coordination and operational support
>
> ● Data collection and user feedback during pilot phase

This ensures that the system is tested under real conditions and adapted
to user needs.

**C.** **Data** **Acquisition** **and** **Model** **Improvement**
**(10%)**

This allocation supports access to relevant datasets and improvement of
predictive accuracy.

Activities include:

> ● Acquisition or processing of climate and environmental data ●
> Integration of local health datasets
>
> ● Data cleaning and feature engineering ● Model calibration and
> validation

This ensures that predictions are reliable and context-specific.

> **29**


**D.** **Infrastructure** **and** **Deployment** **(10%)**

This component covers the technical infrastructure required to host and
operate the system.

Activities include:

> ● Cloud hosting and server management ● Database and storage systems
>
> ● Deployment pipelines and system monitoring ● Security and backup
> systems

This ensures system availability, reliability, and scalability.

**E.** **Monitoring,** **Evaluation,** **and** **Learning** **(10%)**

This component supports measurement of system performance and impact.

Activities include:

> ● Tracking of key performance indicators
>
> ● Evaluation of prediction accuracy and response effectiveness ●
> Collection and analysis of user feedback
>
> ● Iterative system improvement based on findings

This ensures that the system continuously improves and delivers
measurable impact.

**F.** **Documentation** **and** **Open-Source** **Development**
**(5%)**

This component supports the preparation of the system as a digital
public good.

Activities include:

> ● Development of technical documentation ● Creation of deployment and
> user guides
>
> ● Codebase organization and open-source release ● Knowledge sharing
> and dissemination
>
> **30**


This ensures that the system can be reused, adapted, and scaled beyond
the initial pilot.

**7.2** **Cost** **Efficiency** **and** **Value**

The project leverages existing in-house technical capacity,
infrastructure, and prior experience in system development, reducing
overall costs and enabling efficient delivery. By focusing funding on
critical development, deployment, and validation activities, the project
maximizes impact per dollar and ensures that resources are directed
toward measurable outcomes.

**7.3** **Sustainability** **and** **Scale**

The proposed investment is designed to produce a validated, open-source
platform that can be adopted and scaled by governments, NGOs, and
development partners. By aligning with existing systems such as DHIS2
and prioritizing low-cost deployment approaches, the system is
positioned for long-term sustainability beyond the initial funding
period.

**8.** **Risks** **and** **Mitigation** **Strategy**

The implementation of the Child-Centered Climate Health Intelligence
System involves technical, operational, and contextual risks associated
with deploying predictive systems in low-resource, climate-vulnerable
environments. The project design incorporates mitigation strategies to
address these risks and ensure reliability, usability, and sustained
impact.

**8.1** **Data** **Availability** **and** **Quality** **Risks**

**Risk:**

Access to high-quality, localized, and timely climate and health data
may be limited, incomplete, or inconsistent. Historical cholera data may
be sparse or

> **31**


underreported at ward level, and real-time environmental data may not
always be available at sufficient resolution.

**Mitigation:**

The system is designed to operate with hybrid data inputs, combining
available local datasets with open-source and proxy data sources such as
rainfall estimates and flood indicators. Initial models prioritize
robustness and performance in low-data environments. Data preprocessing
pipelines include cleaning, interpolation, and feature engineering to
improve usability of imperfect datasets. As the system is deployed,
locally generated data from CHVs and health facilities will be used to
progressively improve model accuracy and localization.

**8.2** **Model** **Accuracy** **and** **Predictive** **Uncertainty**

**Risk:**

Predictive models may produce false positives or false negatives,
particularly in early stages with limited data. Overestimation of risk
may lead to alert fatigue, while underestimation may result in missed
outbreaks.

**Mitigation:**

The system uses a staged modeling approach, beginning with interpretable
models that allow for transparent validation and calibration. Model
outputs are not used in isolation but are integrated into a rules-based
decision engine with configurable thresholds. Continuous monitoring of
performance metrics such as precision, recall, and lead time will inform
ongoing model refinement. A human-in-the-loop approach, particularly
during early deployment, ensures that alerts are contextualized and
verified where necessary.

**8.3** **Connectivity** **and** **Infrastructure** **Constraints**

**Risk:**

Target communities may experience intermittent internet connectivity,
limited smartphone penetration, and unreliable access to digital
infrastructure, affecting system usability and data flow.

> **32**


**Mitigation:**

The platform is designed with an offline-first approach for frontline
users. The CHV application supports local data storage and delayed
synchronization when connectivity is restored. SMS and USSD channels
provide low-bandwidth alternatives for communication and interaction,
ensuring that critical alerts and guidance can reach users without
requiring internet access. The system architecture is lightweight and
optimized for deployment in constrained environments.

**8.4** **User** **Adoption** **and** **Behavioral** **Factors**

**Risk:**

Community Health Volunteers and other users may face challenges in
adopting new digital tools, particularly if systems are complex,
time-consuming, or not aligned with existing workflows.

**Mitigation:**

User-centered design principles are applied throughout development, with
a focus on simplicity, clarity, and relevance. The system will be
introduced through structured onboarding and training sessions, with
continuous feedback loops to refine usability. Interfaces are designed
to integrate with existing CHV workflows rather than replace them. Early
engagement with local leadership and stakeholders supports trust,
ownership, and sustained use.

**8.5** **Integration** **with** **Health** **Systems**

**Risk:**

Integration with existing systems such as DHIS2 may face technical,
administrative, or interoperability challenges, potentially limiting
data exchange and institutional adoption.

**Mitigation:**

The system is designed as modular and interoperable, with clearly
defined APIs and support for multiple integration pathways, including
CSV-based data exchange where API integration is not immediately
feasible. Engagement with county health

> **33**


authorities during the pilot phase will support alignment with existing
reporting structures and workflows. Integration will be approached
incrementally to reduce complexity and risk.

**8.6** **Operational** **and** **Deployment** **Risks**

**Risk:**

Field deployment may face logistical challenges, including coordination
across stakeholders, delays in onboarding users, or unforeseen
operational constraints in target communities.

**Mitigation:**

The implementation plan includes a phased pilot approach, allowing for
controlled deployment and iterative improvement. Local partnerships,
including engagement with community leadership and health authorities,
provide a foundation for coordination and support. The project will
maintain flexibility in timelines and deployment strategies to adapt to
on-the-ground realities.

**8.7** **Sustainability** **and** **Scale** **Risks**

**Risk:**

Sustaining the system beyond the initial pilot and scaling to additional
regions may require ongoing resources, institutional support, and
integration into broader health systems.

**Mitigation:**

The platform is designed as an open-source digital public good, reducing
barriers to adoption and reuse. Alignment with existing systems such as
DHIS2 and use of

low-cost infrastructure support long-term sustainability. The project
includes a dedicated scale preparation phase focused on documentation,
partnerships, and integration pathways to enable expansion beyond the
pilot.

> **34**

