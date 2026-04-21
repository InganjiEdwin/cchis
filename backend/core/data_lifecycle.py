from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetentionDefinition:
    record_name: str
    system_area: str
    retention_class: str
    contains_sensitive_data: bool
    deletion_expectation: str
    rationale: str


@dataclass(frozen=True)
class MinimizationDefinition:
    record_family: str
    allowed_by_default: tuple[str, ...]
    avoid_by_default: tuple[str, ...]
    required_controls: tuple[str, ...]
    rationale: str


DATA_RETENTION_INVENTORY: tuple[RetentionDefinition, ...] = (
    RetentionDefinition(
        record_name="request_trace_logs",
        system_area="platform",
        retention_class="short_lived_operations",
        contains_sensitive_data=False,
        deletion_expectation="Rotate aggressively and do not treat as the only durable source of truth.",
        rationale="Request traces are useful for debugging and incident timing, but they should not become an indefinite history store.",
    ),
    RetentionDefinition(
        record_name="auth_audit_events",
        system_area="accounts",
        retention_class="durable_security_audit",
        contains_sensitive_data=True,
        deletion_expectation="Retain longer than ordinary logs because these records support abuse review and accountability.",
        rationale="Authentication and account lifecycle actions may need investigation after application logs have rolled away.",
    ),
    RetentionDefinition(
        record_name="ussd_session_logs",
        system_area="messaging",
        retention_class="bounded_operational_history",
        contains_sensitive_data=True,
        deletion_expectation="Keep only as long as operational troubleshooting and service-quality review require, then prune.",
        rationale="USSD logs contain phone numbers and interaction text, so they should not grow indefinitely without review.",
    ),
    RetentionDefinition(
        record_name="sync_queue_payloads",
        system_area="surveillance",
        retention_class="bounded_processing_state",
        contains_sensitive_data=True,
        deletion_expectation="Processed payloads should be prunable after downstream records and required audit evidence exist.",
        rationale="Sync queue rows are an ingestion buffer, not a permanent warehouse for raw field payloads.",
    ),
    RetentionDefinition(
        record_name="triage_sessions",
        system_area="surveillance",
        retention_class="sensitive_field_record",
        contains_sensitive_data=True,
        deletion_expectation="Retain only according to a defined public-health and operational need, not by default forever.",
        rationale="Triage sessions may contain symptom and contact data that becomes more sensitive as field usage grows.",
    ),
    RetentionDefinition(
        record_name="alerts",
        system_area="operations",
        retention_class="operational_history",
        contains_sensitive_data=True,
        deletion_expectation="Retain long enough to support delivery review and operational accountability, then archive or prune by policy.",
        rationale="Alert records explain what the system attempted and to whom, but include recipient contact data.",
    ),
    RetentionDefinition(
        record_name="ingestion_runs",
        system_area="forecasting",
        retention_class="durable_provenance",
        contains_sensitive_data=False,
        deletion_expectation="Retain as provenance unless a later archival mechanism replaces the primary table.",
        rationale="Ingestion lineage is part of model explainability and should outlive transient logs.",
    ),
    RetentionDefinition(
        record_name="model_runs_and_risk_scores",
        system_area="forecasting",
        retention_class="durable_provenance",
        contains_sensitive_data=False,
        deletion_expectation="Retain as forecast lineage and analytical history unless superseded by a dedicated archive strategy.",
        rationale="Model outputs and run metadata are core decision-support history, not disposable debug artifacts.",
    ),
)


FIELD_DATA_MINIMIZATION_RULES: tuple[MinimizationDefinition, ...] = (
    MinimizationDefinition(
        record_family="triage_and_case_intake",
        allowed_by_default=(
            "ward_or_facility_reference",
            "symptom_flags",
            "created_at_timestamp",
            "referral_outcome",
            "channel",
        ),
        avoid_by_default=(
            "patient_full_name",
            "national_identifier",
            "exact_household_location",
            "caregiver_name_in_free_text",
            "unbounded_clinical_notes",
        ),
        required_controls=(
            "purpose_limited_collection",
            "role_based_access",
            "defined_retention_owner",
        ),
        rationale="Future patient-like intake should default to structured, least-identifying data rather than narrative or household-linked records.",
    ),
    MinimizationDefinition(
        record_family="sync_payloads",
        allowed_by_default=(
            "submission_identifier",
            "structured_triage_fields",
            "device_identifier",
            "ward_reference",
        ),
        avoid_by_default=(
            "duplicated_raw_payload_history",
            "embedded_credentials",
            "unnecessary_contact_lists",
        ),
        required_controls=(
            "post_processing_prune_strategy",
            "idempotency_boundary",
            "failure_path_visibility",
        ),
        rationale="Offline sync should preserve enough information for reliable processing without turning the queue into a long-term raw-data archive.",
    ),
    MinimizationDefinition(
        record_family="future_household_or_case_follow_up",
        allowed_by_default=(
            "stable_internal_reference",
            "ward_level_location",
            "status_transitions",
            "clinical_or_operational_codes",
        ),
        avoid_by_default=(
            "precise_gps_coordinates",
            "full_household_member_lists",
            "national_id_copies",
            "free_form_background_histories",
        ),
        required_controls=(
            "explicit_justification_for_direct_identifiers",
            "separate_access_review",
            "documented_export_boundary",
        ),
        rationale="If CCHIS later stores household-linked or follow-up records, direct identifiers should require explicit justification rather than appear by habit.",
    ),
)
