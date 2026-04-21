# CCHIS Identifier Policy

## Purpose

This document defines the stable identifier direction for CCHIS v1 so future APIs, partner integrations, and data pipelines do not depend on mutable display names.

## Core Rule

Display names are never canonical identifiers.

Names can change for operational, administrative, or spelling reasons.
Integrations and machine-to-machine workflows must use stable identifiers instead.

## Ward Identifier Policy

`Ward` now has two identifier layers:

- `id`
  - internal database primary key
  - acceptable for local relational joins inside the backend
  - should not be treated as the long-term external interoperability key
- `public_id`
  - immutable UUID
  - canonical CCHIS-level external identifier for ward records
  - safe for future APIs, exports, and partner references

Supporting field:

- `ward_code`
  - human-managed reference code
  - intended for administrative mapping, seed consistency, and future crosswalks
  - useful for ops and imports, but not a replacement for the immutable `public_id`

Policy:

- do not key integrations off `Ward.name`
- future public API evolution should prefer `public_id` when exposing stable references
- `ward_code` may change under controlled mapping processes, but `public_id` must not

## Health Facility Identifier Policy

`HealthFacility` now has two stable identifier layers:

- `public_id`
  - immutable UUID
  - canonical CCHIS-level external identifier
- `facility_code`
  - human-readable or imported reference code
  - required and unique in the current model
  - appropriate for operational imports and mapping tables

Policy:

- do not treat `HealthFacility.name` as stable
- use `public_id` for CCHIS-native contracts
- use `facility_code` for administrative and external-code crosswalk scenarios

## Partner and External Mapping Direction

Future interoperability work should not attach arbitrary partner identifiers directly to names.

Direction:

- partner mappings should eventually live in a dedicated interoperability layer
- each external system should have an explicit mapping record
- mapping records should reference CCHIS entities by immutable `public_id`
- external identifiers should be namespaced by source system

Target future examples:

- DHIS2 org-unit mapping for wards or facilities
- county master-facility-list mapping
- partner-specific export identifiers

## Practical v1 Rules

Use these rules immediately:

1. Do not write code that looks up wards or facilities by display name as the long-term contract.
2. Seed and demo data should always populate stable reference codes where the model supports them.
3. New interoperability features should be designed around immutable local identifiers plus explicit external mappings.
