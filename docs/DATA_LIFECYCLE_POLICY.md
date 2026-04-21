# Data Lifecycle Policy

This document defines the v1 direction for retention and sensitive data handling so CCHIS does not drift into indefinite storage of field data by accident.

## Why This Exists

The backend already stores operational and field-adjacent records such as:

- auth audit events
- USSD session logs
- sync queue payloads
- triage sessions
- alert delivery history
- ingestion and model provenance

These records do not all deserve the same retention behavior. Some are durable accountability records, some are short-lived operational traces, and some contain contact or symptom information that should stay bounded.

## Retention Direction

The code-level retention inventory lives in [backend/core/data_lifecycle.py](/Users/edwininganji/VSCodeProjects/cchis/backend/core/data_lifecycle.py).

Current direction by record family:

- request trace logs:
  - short-lived operational traces
  - rotate aggressively
  - do not treat as the only durable record of anything important
- auth audit events:
  - durable security and accountability records
  - retain longer than ordinary logs
  - review retention with security and abuse-investigation needs in mind
- USSD session logs:
  - bounded operational history
  - useful for troubleshooting and menu review
  - should not accumulate indefinitely because they include phone numbers and interaction text
- sync queue payloads:
  - bounded processing state, not a permanent raw-payload archive
  - processed rows should be prunable once downstream records and required audit evidence exist
- triage sessions:
  - sensitive field records
  - retain only according to defined operational or public-health need
  - avoid default forever-retention just because the table exists
- alerts:
  - operational history with recipient contact data
  - keep long enough for delivery review and accountability, then archive or prune by policy
- ingestion runs, model runs, and risk scores:
  - durable provenance and analytical history
  - these should outlive transient logs because they explain how forecasts were produced

## Minimization Direction

Future patient-like, household-linked, or case-follow-up records should default to structured, least-identifying data.

Baseline rules:

- collect the minimum data needed for the operational workflow
- prefer ward, facility, and internal references over direct personal identifiers
- prefer coded or structured symptom fields over free-text narrative
- require explicit justification before storing exact household location or direct identifiers
- keep contact routing data separate from clinical or case-like content when possible

## Guardrails For Future Field Records

By default, future field-intake or case-like records should avoid:

- patient full names
- national identifiers
- household member lists
- exact GPS coordinates
- open-ended background narratives

If a later workflow truly requires direct identifiers, the change should also define:

- the operational purpose
- the access boundary
- the retention owner
- the export boundary
- the prune or archive expectation

## What This Phase Does Not Claim Yet

This phase does not implement:

- automated TTL deletion jobs
- archival tables
- legal retention schedules by jurisdiction
- a full patient-record subsystem

It does establish the rule that those future choices must be deliberate, record-specific, and visible in the repo.
