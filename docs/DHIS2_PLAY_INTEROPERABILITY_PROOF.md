# DHIS2 Play Interoperability Proof

This proof is intentionally limited to one official DHIS2 Play instance and
aggregate demonstration data. It does not represent access to Kenya's
production DHIS2 or operational Migori surveillance data.

## Scope

- Transport: authenticated, read-only DHIS2 HTTP API.
- Discovery: `/api/me`, selected organisation-unit metadata, selected
  data-element/indicator metadata, and `/api/system/info`.
- Aggregate read: one explicitly configured `analytics` or `dataValueSets`
  query with bounded pagination.
- Query scope: exactly one explicit period, mapped organisation-unit and
  element/indicator UIDs only, no relative/open-ended periods or wildcards,
  and a small page/result limit.
- Crosswalk: a versioned UID-only mapping such as
  `DHIS2_PLAY_DEMO_CROSSWALK_V1`; display-name matching is not allowed.
- CCHIS path: canonical CSV envelope, source-data validation, confirmed
  source-data import, surveillance ingestion, provenance, and truth gates.

## Runtime configuration

Keep the following values in an ignored local environment file or secret
manager. Never commit or print the credentials:

```text
SOURCE_DATA_DHIS2_BASE_URL=https://play.im.dhis2.org/stable-2-43-1
SOURCE_DATA_DHIS2_USERNAME=admin
SOURCE_DATA_DHIS2_PASSWORD=<published-demo-password>
SOURCE_DATA_DHIS2_API_TOKEN=
SOURCE_DATA_DHIS2_MAPPING_JSON=<versioned-UID-crosswalk-json>
SOURCE_DATA_DHIS2_QUERY_JSON=<small-explicit-query-json>
```

Prefer `SOURCE_DATA_DHIS2_API_TOKEN` when a private development instance
provides one. The public Play demo may use the credentials currently
published by DHIS2 over HTTPS.

## Run

After the explicit mapping includes an existing CCHIS demonstration ward
(never a silently matched Migori ward), run:

```text
docker compose exec -T backend python manage.py run_dhis2_play_proof \
  --operator-username <local-admin> \
  --output /app/risk/data/source_feeds/dhis2_play_proof_evidence.json
```

The command performs two controlled DHIS2 GET-only runs. It writes a
sanitized evidence note with the first and second connector/interoperability
run IDs, actual HTTP receipts, query identity hash, response payload hashes,
canonical counts before and after the second run, previous-ingestion
reference, and duplicate-record delta. Credential values and authorization
headers are not persisted.

## Truth classification

Every record from this proof is labelled `DEMO` and `NON_OPERATIONAL`, with
`seeded_demo` truth and a non-operational DHIS2 Play provenance envelope. The
mapping version is persisted as `DRAFT` and individual mappings as
`NEEDS_REVIEW`; it is never an approved operational crosswalk. These records
are not eligible for production model training, confirmed outbreak truth, or
production alerting.

The command claims exact replay idempotency only when both live response
payload hashes match and the second run reports zero duplicate records. If
DHIS2 returns changed values for the same query identity, the evidence must
report the correction path and the import must preserve supersession
provenance instead of claiming a replay.

If the selected Play instance prevents the required API read, stop and record
the external restriction. Do not replace the API call with the legacy
canonical-CSV fallback and describe it as DHIS2 API interoperability.

The checked-in evidence note records the two controlled live reads, including
actual GET receipts, matching response hashes, zero duplicate growth, and the
resulting exact-replay conclusion. Regenerate it whenever the proof instance
or bounded query changes.
