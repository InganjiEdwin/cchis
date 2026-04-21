# CCHIS Domain Boundaries

## Purpose

This document defines the target bounded-context map for the CCHIS backend so v1 can mature without continuing to pour unrelated concerns into a single prototype app.

The immediate goal is not to split the entire codebase today.
The immediate goal is to make every new backend change choose the right domain home, and to make the current `risk` app's temporary composite nature explicit.

## Target Bounded Contexts

### `accounts`

Owns:

- user identity
- authentication and JWT flows
- role and permission helpers
- password lifecycle
- account activation or deactivation
- auth audit events

Does not own:

- disease operations
- ward geography
- forecasting outputs

### `geo`

Owns:

- county, sub-county, ward, and future facility geography
- geographic identifiers and mapping metadata
- spatial fields such as boundaries and centroids
- external geographic code mappings

Current likely residents:

- `Ward`
- future geographic hierarchy models
- future `HealthFacility` location metadata

### `forecasting`

Owns:

- feature generation inputs
- model runs
- model metadata
- forecast lineage
- risk score generation and storage
- forecast-oriented read APIs

Current likely residents:

- `RiskScore`
- model execution tasks now in `risk.tasks`
- forecast lineage and future feature snapshot models

### `surveillance`

Owns:

- field-observed disease signals
- triage-like records
- referrals and follow-up outcomes
- community encounter or case-like records
- offline sync ingestion records
- CHV operational roster if that roster is treated as field-operations data

Current likely residents:

- `CHV`
- `TriageSession`
- `SyncQueue`

### `operations`

Owns:

- alerts as operational actions
- response assignments
- preparedness and intervention records
- escalation workflows
- outcome tracking for actions taken after risk detection

Current likely residents:

- `Alert`

### `messaging`

Owns:

- SMS providers and delivery integrations
- USSD flows and menu definitions
- outbound message templates
- delivery events and provider callbacks
- messaging-related logs

Current likely residents:

- `UssdSessionLog`
- USSD menu handling now in `risk.views`
- SMS sending code now in `risk.services`

### `integrations`

Owns:

- DHIS2 import or export contracts
- external partner identifiers and mappings
- raw inbound or outbound payload history
- connector-specific sync jobs

### `platform`

Owns:

- cross-cutting technical concerns
- shared idempotency helpers
- shared provenance helpers
- API contract utilities
- common operational infrastructure

## Current `risk` App Responsibility Audit

The current `risk` app mixes too many concerns:

- geography: `Ward`
- field workforce: `CHV`
- forecasting: `RiskScore`
- operations: `Alert`
- surveillance workflows: `TriageSession`, `SyncQueue`
- messaging: `UssdSessionLog`, USSD menu handling, SMS sending
- platform/API glue: list filtering and orchestration views

This was acceptable for a prototype bootstrap, but it is not an acceptable long-term growth pattern.

## What Stays vs What Moves

### Should stay in `risk` for now

- `RiskScore`
- forecast-oriented services
- model-run entrypoints while forecasting remains small

### Can remain temporarily but is not the long-term home

- `Ward`

Reason:

- geography is closely used by forecasting today, but the domain should eventually live under `geo`

### Should stop growing inside `risk`

- CHV roster concerns
- triage workflows
- offline sync ingestion
- alerts as operational workflows
- SMS provider code
- USSD flow logic and session logs

## v1 Decision Rules

Use these rules immediately:

1. If a change is primarily about forecast generation or forecast retrieval, it can live in `risk` for now.
2. If a change is primarily about messaging channels, do not deepen `risk`; shape the code so it can move cleanly to `messaging`.
3. If a change is primarily about field encounters, referrals, or sync ingestion, design it toward `surveillance`.
4. If a change is primarily about alerts as actions or response workflows, design it toward `operations`.
5. If a change is primarily about geographic hierarchy or facility location, design it toward `geo`.

## Immediate Consequence For Upcoming Work

From this point forward:

- no new public or internal API should be added to an unversioned route surface
- no new non-forecast domain object should be introduced casually inside `risk`
- any future split of `risk` should prioritize:
  - `messaging`
  - `surveillance`
  - `operations`
  - `geo`

That priority order is based on how mixed the current prototype already is, not on abstract preference.
