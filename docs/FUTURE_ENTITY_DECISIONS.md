# CCHIS Future Entity Decisions

## Purpose

This document records the strict entity decisions made in v1 so later versions can grow from explicit foundations rather than vague assumptions.

## 1. `HealthFacility` Decision

Decision:

- introduce `HealthFacility` in v1 now

Why:

- triage guidance already refers users to health facilities
- facility forecasting is part of the long-term system direction
- waiting longer would keep a core operational target implicit instead of modeled

Current v1 scope:

- facility identity
- facility type
- ownership
- service level
- ward relationship
- active status
- optional contact phone
- optional map point

Current intentional non-scope:

- stock snapshots
- staffing readiness
- bed capacity
- outbreak-specific facility burden
- referral outcomes

Rule:

- `HealthFacility` is a geographic and operational anchor, not yet a full readiness model

## 2. Case or Encounter Direction

Decision:

- `TriageSession` is not sufficient as the long-term surveillance or case model
- keep `TriageSession` as a decision-support encounter record in v1
- future versions should introduce a dedicated surveillance or case-oriented record instead of overloading `TriageSession`

Why:

- `TriageSession` currently captures symptom-driven guidance, not longitudinal case tracking
- it lacks diagnosis status, referral outcome, follow-up state, case classification, and reporting provenance
- using it as the canonical case record later would force semantic stretching and messy migrations

Target direction:

- keep `TriageSession` for frontline decision support
- add a future `SurveillanceCase` or `CaseEncounter` model for:
  - case classification
  - referral tracking
  - outcome tracking
  - reporting provenance
  - linkage to health facilities and external systems

Strict rule:

- do not casually add long-term surveillance fields to `TriageSession` as a shortcut

## 3. Intervention or Action Direction

Decision:

- `Alert` is not the long-term operational action model
- future versions need a dedicated intervention or response-action entity

Why:

- alerts represent notifications and delivery artifacts
- interventions represent actions taken after risk detection
- combining those concepts would blur “message sent” with “action performed”

Target direction:

- keep `Alert` as notification history
- introduce a future `ResponseAction` or `InterventionAction` model for:
  - action type
  - action owner
  - target ward or facility
  - due date
  - completion status
  - related risk score or alert
  - evidence or notes

Examples of future actions:

- ORS prepositioning
- safe-water messaging campaign
- facility readiness check
- supervisor escalation
- outbreak investigation follow-up

Strict rule:

- do not overload `Alert` with completion, assignment, or preparedness workflow fields
