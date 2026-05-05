# Source Data Validation Error Codes

Schema version: `source-data-validation-error-catalog-v1`

This catalog is the stable operator contract for source-data diagnostics. Validation responses and rejected-row CSV files must use these codes without exposing raw direct identifiers from uploaded rows.

| Code | Severity | Operator action |
| --- | --- | --- |
| `artifact_missing` | error | Create a fresh upload so validation can read the file. |
| `artifact_hash_mismatch` | error | Create a new upload from the original CSV before validating again. |
| `unsupported_file_extension` | error | Export the workbook as `.csv` and upload the CSV file. |
| `unexpected_content_type` | error | Upload a CSV file with a CSV content type. |
| `binary_file_detected` | error | Export the source as plain UTF-8 CSV and upload that file. |
| `html_or_xml_file_detected` | error | Export the source as a plain CSV file before upload. |
| `invalid_encoding` | error | Save or export the file as UTF-8 CSV. |
| `invalid_csv` | error | Re-export the source as a valid CSV file. |
| `missing_headers` | error | Download the source-data template and keep the first row as headers. |
| `duplicate_header` | error | Keep a single copy of each template column. |
| `empty_file` | error | Export the template with headers and at least one data row. |
| `no_data_rows` | error | Keep the header row and add source-data rows before uploading. |
| `row_limit_exceeded` | error | Split the CSV into smaller source-data uploads. |
| `pii_header_detected` | error | Remove personal-information columns such as names, phone numbers, or IDs. |
| `pii_phone_value_detected` | error | Remove phone numbers from the CSV before upload. |
| `pii_email_value_detected` | error | Remove email addresses from the CSV before upload. |
| `pii_identifier_value_detected` | error | Replace direct identifiers with approved aggregate, facility, ward, or source references. |
| `unsafe_text_value_detected` | error | Remove names, contacts, identifiers, exact household locations, and clinical notes from the CSV. |
| `formula_injection_value` | error | Save plain values only; remove formulas before upload. |
| `unknown_column` | warning/error | Remove the extra column or request a contract update. |
| `missing_required_column_group` | error | Add at least one required identity/date/count column from the template. |
| `invalid_reporting_period` | error | Use `YYYY-MM-DD` dates for reporting period fields. |
| `invalid_reporting_period_bounds` | error | Set `reporting_period_end` on or after `reporting_period_start`. |
| `no_case_counts_or_outbreak_label` | error | Add suspected/confirmed/diarrheal counts or an outbreak label. |
| `ward_not_found_for_surveillance_record` | error | Correct the ward code or ward name before import. |
| `ward_not_found_for_population_record` | error | Correct the ward code or ward name before import. |
| `no_canonical_population_exposure_or_catchment_fields` | error | Add one of the accepted population, exposure, or catchment columns. |
| `facility_not_found_for_facility_proxy_record` | error | Correct the facility code or map the row to a known ward. |
| `facility_not_found_for_catchment_record` | error | Correct the facility code or register the facility before import. |
| `facility_ward_mismatch` | error | Correct either the facility code or ward code so they refer to the same facility catchment. |
| `missing_required_field` | error | Fill facility readiness required fields before validating again. |
| `unknown_facility_code` | error | Correct the facility code or register the facility before import. |
| `unknown_ward_code` | error | Correct the ward code before import. |
| `invalid_reported_at` | error | Use an ISO timestamp such as `2026-05-05T08:00:00+03:00`. |
| `future_reported_at` | error | Use the actual facility report timestamp, not a future collection date. |
| `invalid_nonnegative_integer` | error | Replace blank, negative, or decimal stock values with valid whole numbers. |
| `invalid_boolean` | error | Use `true` or `false` for readiness yes/no fields. |
| `invalid_source_kind` | error | Use an allowed `source_kind` value from the readiness template. |
| `duplicate_snapshot_in_file` | error | Remove duplicate facility snapshot rows before validating again. |
| `duplicate_snapshot` | error | Use a later `reported_at` timestamp or submit a documented replacement. |
| `facility_name_mismatch` | warning | Check the facility name against the county facility register. |
| `stale_report` | warning | Confirm the old report should still be imported, or collect a newer facility update. |
| `delayed_report` | warning | Review whether the delayed source should still be imported. |
| `stockout_detected` | warning | Review stockout flags before import; they affect readiness evidence. |
| `service_disruption_reported` | warning | Review the disruption warning before import. |
| `duplicate_file_hash` | warning | Confirm intentional replay, or upload the corrected file. |
| `duplicate_upload_metadata` | warning | Update the source timestamp or mark the import as an intentional replay. |
| `domain_row_rejected` | error | Compare the row with the source-data template and validate again after correction. |
| `domain_row_warning` | warning | Review the warning before confirming import. |
