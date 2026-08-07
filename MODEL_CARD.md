# CCHIS Model Card

## Scope and status

CCHIS contains an implemented ward-risk classification baseline and a Random Forest benchmark path. The current Logistic Regression path is an interpretable prototype for operational decision support; the Random Forest path is benchmark/shadow evidence. Neither model card entry is evidence of clinical efficacy or outbreak prediction accuracy. No model is automatically promoted to production by this repository.

The facility burden forecasting path is a proxy-derived preview contract. Its target is not a confirmed facility case count and it is not a production forecasting claim.

## Intended use

The models may help an authenticated county operator or analyst organize ward review, inspect data provenance, and prioritize human follow-up. They are not diagnostic tools, clinical decision makers, or substitutes for laboratory confirmation, surveillance leadership, or public-health judgement.

The system must not be used to deny care, allocate scarce services automatically, label a child or household as infected, publish an outbreak claim without human review, or make an enforcement or eligibility decision about a person or community.

## Inputs and labels

Inputs can include rainfall and climate records, flood and seasonality proxies, canonical surveillance aggregates, population/exposure context, facility readiness context, and operational workflow history. Population and exposure values can be baselines, spatial aggregates, or proxies; they must not be presented as exact census or exposed-person truth.

Training labels are eligible only when a surveillance label dataset has explicit lineage, temporal cutoff evidence, both classes where required, and non-seeded truth. Confirmed, suspected, field-signal, proxy diarrhoeal, and seeded-demo truth classes remain distinct. Proxy-only evidence is always `proxy_only_not_confirmed` and cannot satisfy a confirmed-outbreak gate.

Seeded demo rows, static climate fallback rows, replay diagnostics, superseded correction records, and future records beyond a source cutoff are excluded from production truth and leakage-sensitive features. Production scoring, promotion, and alert creation fail closed when those boundaries are violated.

## Evaluation

The repository contains temporal backtesting, leakage, source-cutoff, truth-gate, and correction-replay tests. These tests validate software and lineage invariants; they are not prospective public-health validation. This repository does not claim a measured 7-day or 14-day recall, precision, calibration, clinical utility, or generalization result. No such metric should be inferred from seeded fixtures, training-fit metrics, or a passing unit test.

## Human oversight and operational controls

Scores are tied to feature-dataset and model-run lineage. Promotion requires explicit review evidence and is manual. Automatic alerts are blocked when source freshness, climate horizon, production truth, or promotion gates are incomplete. Alert records cite the truth class and caveat. Operators must review the underlying records, confirm current surveillance status, and choose an appropriate response through the governed workflow.

## Known limitations

- Real confirmed outcome history, prospective deployment validation, and representative multi-county evaluation are incomplete.
- Rainfall, population, facility, and surveillance coverage can be delayed, missing, aggregated, or proxy-derived.
- The baseline can encode reporting and access bias and may not transfer outside the data-generating setting.
- A score is not a probability of infection for an individual and does not establish causality.
- Demo and proxy scenarios are useful for interface rehearsal only, not epidemiological truth.

## Change and review policy

Model code, feature schema, label definitions, source connectors, and promotion evidence must be reviewed together. Changes must preserve temporal cutoffs, truth-class separation, supersession handling, and fail-closed production checks. See [DATASET_CARD.md](DATASET_CARD.md) for source contracts and [SECURITY.md](SECURITY.md) for security reporting.
