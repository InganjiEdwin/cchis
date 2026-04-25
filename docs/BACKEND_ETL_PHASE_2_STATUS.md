# Backend ETL Phase 2 Status

## Scope

This note records the current execution state for:

- `Phase 2: Canonical Source Normalization`

from [BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md).

---

## What Was Implemented

Phase 2 is now completed for the source domains that currently exist in the backend through explicit canonical ETL record definitions in:

- [etl_records.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/etl_records.py)

The backend now has canonical internal record shapes for:

- climate records
- surveillance records
- facility-readiness records
- CHV response records

The current backend source domains are now covered as follows:

- rainfall ingestion
  - normalized into canonical climate records
- triage sessions
  - normalized into canonical surveillance records
  - normalized into canonical CHV response records
- sync payload processing
  - normalized into canonical surveillance records
  - normalized into canonical CHV response records
- facility intelligence snapshots
  - normalized into canonical facility-readiness records

---

## Canonicalization Now In Place

Rainfall ingestion results now emit a canonical climate record containing:

- schema version
- ward identity
- county
- source name
- source kind
- source mode
- source timestamp
- freshness state
- rainfall value
- coordinates / coordinate source
- fallback reason

This means the ETL contract is no longer just:

- provider payload fields

It is now:

- provider payload -> normalized observation -> canonical climate record

Triage and sync sources now also normalize into explicit internal records rather than leaving operational meaning trapped inside ad hoc model fields or API payloads.

Facility-readiness output is now normalizable from the current backend snapshot contract into a canonical readiness record, which is important because the readiness layer is currently proxy-based and still needs a stable internal shape.

---

## What This Solves

This phase materially improves ETL discipline by making it possible to:

- compare seeded and live rainfall inputs through the same canonical structure
- change providers later without making downstream code depend on provider payload shape
- carry schema versioning into ETL normalization
- keep the internal climate contract clearer than the external provider contract

---

## Remaining Limitations

Phase 2 is complete for the source domains that currently exist in this codebase, but some limitations remain:

- these canonical records are not yet persisted as their own first-class warehouse tables
- downstream feature generation still relies on prototype logic rather than a fully materialized canonical dataset layer
- facility-readiness canonicalization still depends on the current calculated snapshot logic, which is partly proxy-based
- future external surveillance or facility feeds will still need adapter-level wiring into these canonical record shapes

So the correct status is:

- canonical ETL structure established
- all currently available ETL-relevant source domains normalized through it
- later sources can plug into the same canonical layer rather than inventing new downstream contracts

---

## Verdict

Phase 2 is now complete in a real backend way for the currently available source domains and is no longer only described in the plan.

The backend now has:

- explicit canonical ETL record types
- live usage on rainfall ingestion
- live normalization coverage for triage and sync-originating surveillance / CHV response data
- live normalization coverage for current facility-readiness snapshots
- test coverage proving canonical climate records are emitted
- test coverage proving canonical surveillance, CHV response, and facility-readiness records can be produced from real backend objects

The next clean move after this is Phase 3:

- feature pipeline and dataset versioning
