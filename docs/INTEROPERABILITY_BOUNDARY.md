# Interoperability Boundary

## Purpose

This document defines where import and export mapping work should live in CCHIS v1 so future DHIS2 and partner integrations do not distort the internal model.

## Core Rule

External payloads are not canonical internal models.

CCHIS should keep a stable internal shape and map to or from partner-specific payloads at an explicit boundary.

## Canonical Internal Target

The current canonical mapping home is `risk/canonical.py`.

It provides internal reference and record shapes for:

- wards
- health facilities
- risk scores
- alerts

These shapes are deliberately CCHIS-native:

- they use immutable `public_id` values where available
- they carry operational codes such as `ward_code` and `facility_code`
- they avoid using mutable display names as identifiers
- they do not expose partner-specific field names

## Boundary Direction

### Outbound exports

1. Read CCHIS domain models.
2. Convert them into canonical internal records.
3. Build a partner-specific payload from the canonical record.
4. Send or persist the partner payload in the integrations layer.

### Inbound imports

1. Receive a partner-specific payload.
2. Validate and normalize it inside the integrations layer.
3. Resolve local entities by stable local identifiers or explicit mapping records.
4. Translate the payload into canonical internal intent.
5. Apply that intent to domain models.

## What Must Not Happen

- do not let DHIS2 or partner field names spread into core domain models
- do not use display names as the import or export join key
- do not let serializers become the long-term integration contract by accident
- do not store external mappings directly on labels or ad hoc JSON blobs without a named source system

## Stable Join Strategy

Use this direction by default:

- CCHIS-native references:
  - `Ward.public_id`
  - `HealthFacility.public_id`
- operational or administrative reference codes:
  - `ward_code`
  - `facility_code`
- future partner mapping records:
  - namespaced by source system
  - linked to immutable CCHIS identifiers

## Architectural Home

- canonical record definitions belong in a stable internal mapping layer
- partner-specific translation belongs in the future `integrations` boundary
- raw provider or partner payload logs belong outside domain models

## v1 Practical Consequence

Before any DHIS2 or partner connector is added:

- new export work should map domain models into canonical records first
- new import work should normalize partner payloads before touching domain models
- any future interoperability tests should assert both:
  - canonical mapping correctness
  - partner translation correctness
