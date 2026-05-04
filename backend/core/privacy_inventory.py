from __future__ import annotations

from dataclasses import dataclass


class PrivacyDataCategory:
    PUBLIC_OPERATIONAL = "public_operational_data"
    INTERNAL_OPERATIONAL = "internal_operational_data"
    PERSONAL = "personal_data"
    SENSITIVE_HEALTH = "sensitive_health_data"
    CHILD_HEALTH = "child_health_data"
    CONTACT = "contact_data"
    DERIVED_AGGREGATE = "derived_aggregate_data"


@dataclass(frozen=True)
class PrivacyFieldDefinition:
    record_family: str
    model_label: str
    field_name: str
    data_category: str
    purpose: str
    pii_risk: str
    minimization_action: str
    retention_note: str


@dataclass(frozen=True)
class PrivacyMinimizationRule:
    record_family: str
    allowed_by_default: tuple[str, ...]
    rejected_by_default: tuple[str, ...]
    enforcement_surface: tuple[str, ...]
    rationale: str


PRIVACY_FIELD_INVENTORY: tuple[PrivacyFieldDefinition, ...] = (
    PrivacyFieldDefinition(
        "users",
        "accounts.User",
        "username",
        PrivacyDataCategory.PERSONAL,
        "Operator login and audit attribution.",
        "direct_identifier",
        "Keep only account identity fields required for authentication and role-scoped audit trails.",
        "Retain while account exists; auth audit retention is handled separately.",
    ),
    PrivacyFieldDefinition(
        "users",
        "accounts.User",
        "email",
        PrivacyDataCategory.CONTACT,
        "Password reset and account communication.",
        "direct_contact",
        "Required for user accounts; do not copy into operational exports.",
        "Retain while account exists, then remove or anonymize with account closure.",
    ),
    PrivacyFieldDefinition(
        "users",
        "accounts.User",
        "full_name",
        PrivacyDataCategory.PERSONAL,
        "Human-readable account identification.",
        "direct_identifier",
        "Optional for profile display; avoid in analytics datasets.",
        "Retain while account exists, subject to account deletion/anonymization.",
    ),
    PrivacyFieldDefinition(
        "users",
        "accounts.User",
        "phone_number",
        PrivacyDataCategory.CONTACT,
        "Optional account contact and CHV coordination.",
        "direct_contact",
        "Collect only when operationally needed; keep out of aggregate analytics.",
        "Retain while account exists or until operator removes it.",
    ),
    PrivacyFieldDefinition(
        "users",
        "accounts.User",
        "ward",
        PrivacyDataCategory.INTERNAL_OPERATIONAL,
        "Role and ward-scope enforcement.",
        "low_when_not_combined_with_direct_identifiers",
        "Prefer ward scope over exact household or GPS scope.",
        "Retain as an authorization attribute.",
    ),
    PrivacyFieldDefinition(
        "users",
        "accounts.User",
        "totp_secret",
        PrivacyDataCategory.PERSONAL,
        "Two-factor authentication.",
        "security_secret",
        "Never expose in API responses or exports.",
        "Retain only while TOTP is enrolled; rotate/remove on reset.",
    ),
    PrivacyFieldDefinition(
        "chvs",
        "risk.CHV",
        "name",
        PrivacyDataCategory.PERSONAL,
        "Identify the assigned CHV in operations workflows.",
        "direct_identifier",
        "Expose only to roles that manage CHV operations; avoid in analyst datasets.",
        "Retain while CHV record is active or needed for audit history.",
    ),
    PrivacyFieldDefinition(
        "chvs",
        "risk.CHV",
        "phone_number",
        PrivacyDataCategory.CONTACT,
        "Send operational SMS and coordinate field assignments.",
        "direct_contact",
        "Use as the delivery target only; do not duplicate into notes or metadata.",
        "Retain while CHV can receive operational messages; future phases define pruning.",
    ),
    PrivacyFieldDefinition(
        "chvs",
        "risk.CHV",
        "ward",
        PrivacyDataCategory.INTERNAL_OPERATIONAL,
        "Ward-level assignment and access scope.",
        "low_when_not_combined_with_direct_identifiers",
        "Use ward scope instead of household-level targeting by default.",
        "Retain as operational assignment history.",
    ),
    PrivacyFieldDefinition(
        "households_or_contacts",
        "future.HouseholdContact",
        "household_name",
        PrivacyDataCategory.PERSONAL,
        "Not required for current Phase 8 workflows.",
        "direct_household_identifier",
        "Do not collect by default; use ward/facility/action references unless explicitly approved later.",
        "No current retention because the system should not store it in Phase 0/1.",
    ),
    PrivacyFieldDefinition(
        "households_or_contacts",
        "risk.FacilityContact",
        "name",
        PrivacyDataCategory.PERSONAL,
        "Identify facility contact for readiness communication.",
        "direct_identifier",
        "Keep only facility role/contact details needed for verified operational updates.",
        "Retain while verified and active; future phases define contact expiry.",
    ),
    PrivacyFieldDefinition(
        "households_or_contacts",
        "risk.FacilityContact",
        "phone",
        PrivacyDataCategory.CONTACT,
        "Facility readiness SMS contact.",
        "direct_contact",
        "Do not copy into notes, evidence, or aggregate exports.",
        "Retain while contact remains active and verified.",
    ),
    PrivacyFieldDefinition(
        "households_or_contacts",
        "risk.FacilityContact",
        "email",
        PrivacyDataCategory.CONTACT,
        "Facility readiness email contact.",
        "direct_contact",
        "Do not copy into notes, evidence, or aggregate exports.",
        "Retain while contact remains active and verified.",
    ),
    PrivacyFieldDefinition(
        "triage_submissions",
        "risk.TriageSession",
        "phone_number",
        PrivacyDataCategory.CONTACT,
        "Optional callback/contact reference for field triage.",
        "direct_contact",
        "Keep in the explicit phone field only; reject phone numbers embedded in free text.",
        "Sensitive field record; future phases must define retention/anonymization.",
    ),
    PrivacyFieldDefinition(
        "triage_submissions",
        "risk.TriageSession",
        "text_input",
        PrivacyDataCategory.SENSITIVE_HEALTH,
        "Legacy free-text triage input.",
        "free_text_health_and_pii_risk",
        "Reject direct identifiers and unsafe medical-note labels; prefer structured symptom flags.",
        "Retain only under the triage retention policy; prune raw text when feasible.",
    ),
    PrivacyFieldDefinition(
        "triage_submissions",
        "risk.TriageSession",
        "diarrhea/vomiting/dehydration/fever",
        PrivacyDataCategory.CHILD_HEALTH,
        "Structured danger-sign triage flags.",
        "sensitive_health_signal",
        "Allowed as structured fields; avoid narrative clinical notes.",
        "Retain with sensitive triage records and aggregate separately for analytics.",
    ),
    PrivacyFieldDefinition(
        "sync_payloads",
        "risk.SyncQueue",
        "payload",
        PrivacyDataCategory.SENSITIVE_HEALTH,
        "Offline structured triage ingestion buffer.",
        "raw_payload_may_embed_pii",
        "Accept only documented payload keys and reject extra household/contact identifiers.",
        "Processed payloads should be prunable after downstream records and audit evidence exist.",
    ),
    PrivacyFieldDefinition(
        "sync_payloads",
        "risk.SyncQueue",
        "source_device_id",
        PrivacyDataCategory.INTERNAL_OPERATIONAL,
        "Idempotency and device troubleshooting.",
        "device_identifier",
        "Use for replay control only; do not expose in public exports.",
        "Bounded processing-state retention.",
    ),
    PrivacyFieldDefinition(
        "alerts",
        "risk.Alert",
        "recipient",
        PrivacyDataCategory.CONTACT,
        "Alert delivery target.",
        "direct_contact_or_system_endpoint",
        "Keep as explicit delivery target only; avoid copying into messages or metadata.",
        "Retain with operational alert history until export/retention phases mature.",
    ),
    PrivacyFieldDefinition(
        "alerts",
        "risk.Alert",
        "message",
        PrivacyDataCategory.INTERNAL_OPERATIONAL,
        "Operational risk/response notification.",
        "free_text_pii_risk",
        "Do not embed patient, child, household, or phone details.",
        "Retain as alert history but treat as potentially sensitive.",
    ),
    PrivacyFieldDefinition(
        "facility_contacts",
        "risk.HealthFacility",
        "contact_phone",
        PrivacyDataCategory.CONTACT,
        "Facility operations contact.",
        "direct_contact",
        "Prefer verified FacilityContact records; avoid exposing in analyst exports.",
        "Retain while facility contact remains active.",
    ),
    PrivacyFieldDefinition(
        "message_deliveries",
        "risk.CHVMessage",
        "message_body",
        PrivacyDataCategory.INTERNAL_OPERATIONAL,
        "CHV operational SMS body.",
        "free_text_pii_risk",
        "Reject direct contact details, household names, exact locations, and unsupported medical-note labels.",
        "Retain with delivery log until retention phase defines pruning.",
    ),
    PrivacyFieldDefinition(
        "message_deliveries",
        "risk.CHVMessage",
        "provider_reference",
        PrivacyDataCategory.INTERNAL_OPERATIONAL,
        "Delivery troubleshooting and provider reconciliation.",
        "external_delivery_identifier",
        "Expose only in operational/admin contexts.",
        "Retain while delivery audit is needed.",
    ),
    PrivacyFieldDefinition(
        "message_deliveries",
        "risk.FacilityReadinessUpdateRequest",
        "message_body",
        PrivacyDataCategory.INTERNAL_OPERATIONAL,
        "Facility readiness update request content.",
        "free_text_pii_risk",
        "Reject direct identifiers and unsupported clinical notes.",
        "Retain with facility readiness workflow history.",
    ),
    PrivacyFieldDefinition(
        "action_ledger",
        "risk.CHVCoverageRequest",
        "reason/notes/review_decision_reason",
        PrivacyDataCategory.INTERNAL_OPERATIONAL,
        "Explain CHV coverage workflow decisions.",
        "free_text_pii_risk",
        "Reject household names, phones, exact household locations, and clinical-note content.",
        "Retain as operational task history until retention phase matures.",
    ),
    PrivacyFieldDefinition(
        "action_ledger",
        "risk.PreparednessAction",
        "notes/completion_evidence/escalation_metadata/lineage_metadata",
        PrivacyDataCategory.INTERNAL_OPERATIONAL,
        "Task execution evidence and lineage.",
        "free_text_or_metadata_pii_risk",
        "Reject direct identifier keys and direct contact details in operator-entered metadata.",
        "Retain as task ledger evidence; future phases define export and retention controls.",
    ),
    PrivacyFieldDefinition(
        "exports",
        "canonical_export_envelope",
        "sensitive_fields",
        PrivacyDataCategory.DERIVED_AGGREGATE,
        "Future controlled data exchange/export boundary.",
        "export_reidentification_risk",
        "Default exports to ward/facility aggregates and internal references; require approval for direct identifiers.",
        "Future export governance phase must add expiry and audit events.",
    ),
)


PRIVACY_MINIMIZATION_RULES: tuple[PrivacyMinimizationRule, ...] = (
    PrivacyMinimizationRule(
        "field_text_inputs",
        (
            "ward_or_facility_reference",
            "structured_symptom_flags",
            "operational_status",
            "task_summary_without_direct_identifiers",
        ),
        (
            "household_name",
            "patient_or_child_name",
            "phone_or_email_inside_free_text",
            "national_identifier",
            "exact_household_gps_or_coordinates",
            "unsupported_free_text_medical_notes",
        ),
        (
            "risk serializer strict input fields",
            "risk serializer PII-safe text validation",
            "frontend forms only expose ward/task/message summaries",
        ),
        "Current workflows can execute using coarse ward context and structured flags; direct household or child identifiers are not needed.",
    ),
    PrivacyMinimizationRule(
        "offline_sync_payloads",
        (
            "client_submission_id",
            "structured_symptom_flags",
            "ward_id",
            "source_device_id",
            "optional_explicit_phone_number_field",
        ),
        (
            "embedded_household_contact_details",
            "extra_unknown_payload_keys",
            "free_text_identifiers",
            "precise_household_location",
        ),
        (
            "SyncPayloadSerializer strict input fields",
            "CHVSyncRequestSerializer payload validation",
        ),
        "The queue is an ingestion buffer and should not become a durable raw household data store.",
    ),
    PrivacyMinimizationRule(
        "action_evidence_and_lineage",
        (
            "summary",
            "reference",
            "captured_via",
            "captured_at",
            "internal_source_refs",
        ),
        (
            "patient_name",
            "child_name",
            "household_name",
            "phone_number",
            "email",
            "gps_coordinates",
            "clinical_notes",
            "lab_results",
        ),
        (
            "PreparednessActionCreateSerializer lineage metadata validation",
            "PreparednessActionTransitionSerializer evidence metadata validation",
        ),
        "Task evidence should prove that work happened without storing household or child-level identifiers.",
    ),
)


def inventory_record_families() -> set[str]:
    return {item.record_family for item in PRIVACY_FIELD_INVENTORY}


def sensitive_inventory_items() -> tuple[PrivacyFieldDefinition, ...]:
    sensitive_categories = {
        PrivacyDataCategory.PERSONAL,
        PrivacyDataCategory.CONTACT,
        PrivacyDataCategory.SENSITIVE_HEALTH,
        PrivacyDataCategory.CHILD_HEALTH,
    }
    return tuple(item for item in PRIVACY_FIELD_INVENTORY if item.data_category in sensitive_categories)
