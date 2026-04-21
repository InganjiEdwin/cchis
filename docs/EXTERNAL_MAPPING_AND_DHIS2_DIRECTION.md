# External Mapping And DHIS2 Direction

## Purpose

This document defines the v1-ready direction for external location mappings and future DHIS2 exports so interoperability can mature without tearing up the internal model.

## Location Mapping Strategy

### Core rule

External mapping must never depend on mutable labels such as `Ward.name` or `HealthFacility.name`.

### Stable local anchors

Use this hierarchy of local anchors:

1. immutable CCHIS identifier
   - `Ward.public_id`
   - `HealthFacility.public_id`
2. operational reference code
   - `ward_code`
   - `facility_code`
3. display name
   - allowed for human review only
   - never a durable machine join key

### Mapping record direction

Future mapping records should contain at least:

- `source_system`
- `entity_type`
- immutable CCHIS identifier
- local reference code
- external identifier
- mapping status or lifecycle metadata

This keeps cross-system matching explicit, reviewable, and repairable.

## Ward Mapping Direction

- DHIS2 org-unit mapping should point to a ward by `Ward.public_id`
- `ward_code` should be carried as an operational cross-check
- a ward rename must not break the mapping record

## Facility Mapping Direction

- facility mapping should point to `HealthFacility.public_id`
- `facility_code` should be preserved for county lists, MFL-style references, and reconciliation
- future external facility mappings should not rely on facility names being unique across systems

## DHIS2-Ready Export Direction

### Export pipeline shape

1. domain model
2. canonical CCHIS record
3. external mapping resolution
4. DHIS2-specific payload build
5. transport by a future integrations layer

### v1 expectation

The backend should be able to produce a DHIS2-ready payload stub from canonical records without embedding DHIS2 field names inside domain models.

Current implementation direction in code:

- canonical records are defined in `backend/risk/canonical.py`
- location crosswalk and DHIS2 payload stub helpers are defined in `backend/risk/interoperability.py`

## What Must Not Happen

- do not add DHIS2 ids directly to `Ward.name` or `HealthFacility.name`
- do not make serializers the accidental source of truth for partner exports
- do not couple model fields to one external system's vocabulary
- do not use free-text location matching as the primary join strategy

## Practical v1 Rule

Any future DHIS2 or partner export work must prove two separate steps:

1. correct canonical mapping
2. correct partner payload translation

If those two steps cannot be tested independently, the integration seam is not clean enough.
