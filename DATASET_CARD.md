# CCHIS Dataset Card

## Coverage and ownership

CCHIS is designed around ward and facility operational context, with Migori County as the current reference geography. A row is not automatically trustworthy because it is present in the database: every downstream feature or label must retain source, time, truth, freshness, and correction lineage.

## Dataset inventory

| Category | Typical granularity | Provenance and refresh | Truth/quality contract | Production use |
| --- | --- | --- | --- | --- |
| Rainfall and climate | Ward snapshot, observed/forecast record | Provider ingestion runs such as Open-Meteo; refreshed by scheduled/manual ingestion | Source kind, issue/valid time, record type, horizon, freshness, and fallback flags are retained | Live source records only; static fallback is visible as degraded context and is not production observed truth, promotion, or alert evidence |
| Surveillance aggregates | Ward/facility reporting period | County/provider CSV, trusted push, field, backfill, and facility-proxy contracts | Confirmed, suspected, proxy, field, and seeded-demo levels remain separate; reporting lag and replay/correction lineage are retained | Source-backed records with valid mappings and cutoffs; proxy-only evidence cannot become confirmed truth |
| Surveillance labels | Ward/date window | Derived from canonical surveillance records and explicit prediction-date/source cutoffs | Label window, dataset role, source refs, truth counts, readiness, and correction replay evidence are stored | Non-seeded, leakage-safe labels only; seeded simulation labels are prohibited in production |
| Population and exposure | Ward/facility/catchment snapshot | Versioned population baselines, exposure features, and spatial aggregation inputs | Release/version, recorded-at cutoff, truth classes, and proxy caveats are stored | Context only; proxy or aggregated values must not be represented as exact census or exposed-person counts |
| Facility readiness and burden context | Facility snapshot and workflow events | Facility master data, readiness updates, reviews, alerts, and response workflow records | Freshness, reviewer/action state, and proxy-derived target limitations are retained | Decision support and preview forecasting; not confirmed facility incidence |
| Operational/auth/CHV records | User, role, contact, audit, sync, and delivery events | Application-generated records with role/scope controls | Direct identifiers and contact data are access-controlled and are not model labels by default | Operational workflows only; do not export or train on them without an approved purpose |
| Demo and rehearsal fixtures | Synthetic ward/facility scenarios and seeded source feeds | Explicit seed commands and source-kind metadata | `seeded_demo`/seeded source markers, scenario names, and non-production caveats are required | Local rehearsal and explicitly permitted staging rehearsal only; all production seeding and scoring paths fail closed |

## Geography and mapping

Ward and facility mappings are resolved through canonical identifiers where available. Production ingestion rejects unmapped, inactive, or inconsistent ward/facility mappings before canonical rows are created. Mapping failures are recorded with a stable policy code and do not create a partial operational import.

## Time and leakage controls

Historical features and labels use an explicit `as_of`/prediction reference and preserve `created_at` or source-cutoff filters. Future records, replay diagnostics, and superseded correction records are excluded from leakage-sensitive features and evaluation. Advancing the calendar beyond a reporting window must age that window out of the rolling context.

## Privacy and sensitive data

Some operational records contain phone numbers, email addresses, staff identity, CHV contacts, audit details, or free-text notes. They are access-controlled application data, not a public research dataset. Do not place direct identifiers, secrets, tokens, or raw private exports in fixtures, issue reports, model artifacts, or documentation. Use the privacy and security controls in the repository before creating any derived dataset.

## Quality and limitations

Source coverage, freshness, mapping, correction, truth, and proxy limitations are exposed in lineage metadata and dashboard caveats. Missingness is not silently converted into confirmed disease truth. Seeded scenarios can demonstrate workflows and UI states but must never be interpreted as measured incidence, prevalence, forecast skill, or impact.
