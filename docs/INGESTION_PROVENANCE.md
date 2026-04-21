# CCHIS Ingestion Provenance

## Purpose

This document defines the v1 provenance rules for rainfall ingestion so source usage, fallback behavior, and prototype geography shortcuts are explicit and auditable.

## Current Ingestion Run Tracking

CCHIS now persists rainfall ingestion runs in `IngestionRun`.

Each run captures:

- run type
- status
- source mode
- source priority order
- requested wards
- result summaries
- completion timestamp
- error message when a run fails

This is the minimum v1 provenance layer for understanding what entered the system and how.

## Source Priority and Fallback Policy

### Source Mode: `hybrid`

Priority order:

1. ward centroid from PostGIS-backed `Ward.centroid`
2. static prototype ward-coordinate map
3. live Open-Meteo forecast using the resolved coordinates
4. static CSV rainfall seed
5. static default rainfall table
6. static fallback rainfall value

Interpretation:

- coordinate sources and rainfall sources are related but not identical
- a run may use static coordinates and still fetch live rainfall
- a run becomes `PARTIAL` when fallback behavior is used

### Source Mode: `static`

Priority order:

1. static CSV rainfall seed
2. static default rainfall table
3. static fallback rainfall value

Interpretation:

- `static` mode is deterministic and intended for local development, controlled demos, or testing
- using `static` mode is not an error, but it should not be confused with live ingestion

## Fallback Semantics

Current fallback reasons include:

- `static-mode-forced`
- `missing-coordinates`
- `live-fetch-failed`

Policy:

- fallback behavior must be visible in persisted run results
- fallback should never be a silent implementation detail
- future data consumers should be able to distinguish live input from fallback input

## Coordinate Resolution Policy

Current resolution order:

1. `Ward.centroid`
2. hardcoded prototype ward map in code
3. no coordinates available

### Why the hardcoded map still exists

The prototype currently needs a bridge for wards whose PostGIS centroid has not yet been populated.

### Migration path away from hardcoded coordinates

The hardcoded ward map is temporary.

Target direction:

- populate `Ward.centroid` from authoritative ward geometry or controlled import
- treat missing centroids as a data-quality gap to fix, not a permanent code-path
- remove the hardcoded coordinate map once centroid coverage is sufficient

Strict rule:

- no new ward should rely on the hardcoded map as its long-term coordinate source

## Practical v1 Rules

1. Live rainfall ingestion should prefer ward geometry-derived centroids whenever available.
2. Fallbacks must be persisted and reviewable.
3. New ingestion sources must declare where they sit in the priority order before they are added.
