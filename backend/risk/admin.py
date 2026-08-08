from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils import timezone

from .services import (
    approve_chv_coverage_request,
    assign_chv_to_coverage_request,
    cancel_chv_assignment,
    cancel_chv_coverage_request,
    complete_chv_assignment,
    create_chv_coverage_request,
    reject_chv_coverage_request,
    resolve_chv_coverage_request,
)
from .models import (
    Alert,
    AlertWorkflowEvent,
    AlertWorkflowState,
    CatchmentPopulationRecord,
    CHV,
    CHVAssignment,
    CHVCoverageRequest,
    CHVCoverageRequestAlertLink,
    CHVCoverageRequestEmailDelivery,
    CHVCoverageRequestEvent,
    CHVDeviceRegistration,
    CHVOfflineRejectedSubmissionAudit,
    ContactPreference,
    ContactPreferenceAuditEvent,
    ClimateRecord,
    DashboardNotification,
    DashboardNotificationEvent,
    ETLHeartbeat,
    ExposureFeatureRecord,
    ExternalDataElementMapping,
    ExternalOrgUnitMapping,
    ExternalSystem,
    ExternalValueSetMapping,
    FacilityCatchment,
    FacilityContact,
    FacilityForecast,
    FacilityForecastRun,
    FacilityReadinessEscalation,
    FacilityReadinessIngestionRun,
    FacilityReadinessReview,
    FacilityReadinessReviewEvent,
    FacilityReadinessSnapshot,
    FacilityReadinessSource,
    FacilityReadinessUpdateRequest,
    FeatureDataset,
    FeatureDatasetRow,
    FeedbackAdjudication,
    FeedbackLabelCandidate,
    HealthFacility,
    IngestionRun,
    InteroperabilityMappingVersion,
    InteroperabilityRun,
    InteroperabilityRunError,
    InteroperabilityRunItem,
    MessageTemplate,
    ModelChampionChallengerComparison,
    ModelGovernanceEvent,
    ModelMonitoringSnapshot,
    ModelMonitoringThreshold,
    ModelPromotionEvent,
    ModelRegistryEntry,
    ModelRollbackEvent,
    ModelRetrainingRecommendation,
    ModelRun,
    OperationalBaselinePeriod,
    OperationalMetricDefinition,
    OperationalMetricDimension,
    OperationalMetricSnapshot,
    OperationalSLAThreshold,
    OperationalThresholdBreach,
    PopulationBaselineRecord,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PredictionFeedback,
    PredictionFeedbackEvent,
    PrivacyRetentionAuditEvent,
    PrivacyRetentionHold,
    RiskScore,
    SensitiveExportDownloadAudit,
    SensitiveExportRequest,
    SourceDataConnectorRun,
    SourceDataFeedModeOverride,
    SourceDataUploadArtifact,
    SourceDataUploadBatch,
    SourceDataUploadEvent,
    SourceDataValidationIssue,
    SurveillanceIngestionRun,
    SurveillanceLabelWindow,
    SurveillanceRecord,
    SurveillanceSource,
    SyncQueue,
    SystemControlState,
    TriageSession,
    UssdMenuVersion,
    UssdSessionLog,
    Ward,
    WardSpatialRelationship,
)


class CHVCoverageRequestAlertLinkInline(admin.TabularInline):
    model = CHVCoverageRequestAlertLink
    extra = 0
    autocomplete_fields = ("alert", "linked_by")
    readonly_fields = ("alert", "linked_by", "created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "ward_code",
        "county",
        "sub_county",
        "current_risk_level",
        "current_risk_score",
        "is_active",
        "updated_at",
    )
    search_fields = ("name", "county", "sub_county")
    list_filter = ("county", "current_risk_level", "is_active")


@admin.register(CHV)
class CHVAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_number", "ward", "language", "is_active")
    search_fields = ("name", "phone_number", "ward__name")
    list_filter = ("language", "is_active", "ward")


@admin.register(HealthFacility)
class HealthFacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "facility_code", "ward", "facility_type", "ownership", "level", "is_active")
    search_fields = ("name", "facility_code", "ward__name", "public_id")
    list_filter = ("facility_type", "ownership", "level", "is_active", "ward")


@admin.register(FacilityContact)
class FacilityContactAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "facility",
        "role",
        "preferred_channel",
        "is_verified",
        "is_active",
        "source",
        "verified_at",
    )
    search_fields = ("name", "role", "phone", "email", "facility__name", "source", "source_reference")
    list_filter = ("preferred_channel", "is_verified", "is_active", "source")
    autocomplete_fields = ("facility",)
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(ContactPreference)
class ContactPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "audience_type",
        "channel",
        "contact_reference",
        "phone_number",
        "consent_status",
        "opt_out_status",
        "source",
        "recorded_by",
        "recorded_at",
        "expires_at",
    )
    search_fields = ("phone_number", "contact_reference", "source", "source_reference", "public_id")
    list_filter = ("audience_type", "channel", "consent_status", "opt_out_status", "source")
    autocomplete_fields = ("recorded_by",)
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(ContactPreferenceAuditEvent)
class ContactPreferenceAuditEventAdmin(admin.ModelAdmin):
    list_display = ("action", "audience_type", "channel", "contact_reference", "phone_number", "actor", "created_at")
    search_fields = ("phone_number", "contact_reference", "reason", "public_id", "preference__public_id")
    list_filter = ("action", "audience_type", "channel", "created_at")
    autocomplete_fields = ("preference", "actor")
    readonly_fields = ("public_id", "created_at")


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "template_key",
        "version",
        "language",
        "audience_type",
        "channel",
        "approval_status",
        "translation_status",
        "owner",
        "risk_level",
        "approved_at",
        "retired_at",
    )
    search_fields = ("template_key", "title", "body", "owner", "public_id")
    list_filter = (
        "audience_type",
        "channel",
        "language",
        "approval_status",
        "translation_status",
        "risk_level",
        "owner",
    )
    autocomplete_fields = ("approved_by", "created_by", "source_template", "translation_reviewed_by")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(PrivacyRetentionHold)
class PrivacyRetentionHoldAdmin(admin.ModelAdmin):
    list_display = ("content_type", "object_id", "case_reference", "is_active", "expires_at", "created_by", "created_at")
    search_fields = ("object_id", "reason", "case_reference", "public_id")
    list_filter = ("is_active", "content_type", "created_at", "expires_at")
    raw_id_fields = ("content_type", "created_by")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(PrivacyRetentionAuditEvent)
class PrivacyRetentionAuditEventAdmin(admin.ModelAdmin):
    list_display = ("record_family", "action", "model_label", "object_id", "dry_run", "created_at")
    search_fields = ("run_id", "record_family", "model_label", "object_id", "decision_reason", "public_id")
    list_filter = ("action", "record_family", "dry_run", "created_at")
    raw_id_fields = ("hold", "actor")
    readonly_fields = (
        "public_id",
        "run_id",
        "action",
        "record_family",
        "model_label",
        "object_id",
        "cutoff_at",
        "window_days",
        "dry_run",
        "decision_reason",
        "before_state",
        "after_state",
        "aggregate_metrics",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SensitiveExportDownloadAuditInline(admin.TabularInline):
    model = SensitiveExportDownloadAudit
    extra = 0
    raw_id_fields = ("downloader",)
    readonly_fields = ("public_id", "downloader", "outcome", "reason", "request_metadata", "downloaded_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SensitiveExportRequest)
class SensitiveExportRequestAdmin(admin.ModelAdmin):
    list_display = ("export_type", "requester", "approval_state", "requires_approval", "generated_at", "expires_at", "download_count")
    search_fields = ("public_id", "purpose", "requester__username", "generated_filename", "payload_sha256")
    list_filter = ("export_type", "approval_state", "requires_approval", "created_at", "expires_at")
    raw_id_fields = ("requester", "approved_by", "rejected_by")
    readonly_fields = (
        "public_id",
        "export_type",
        "requester",
        "purpose",
        "filters",
        "sensitive_fields_included",
        "approval_state",
        "requires_approval",
        "generated_at",
        "expires_at",
        "approved_by",
        "approved_at",
        "rejected_by",
        "rejected_at",
        "rejection_reason",
        "generated_filename",
        "generated_content_type",
        "payload_sha256",
        "row_count",
        "download_count",
        "last_downloaded_at",
        "metadata",
        "created_at",
        "updated_at",
    )
    exclude = ("generated_payload",)
    inlines = (SensitiveExportDownloadAuditInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SensitiveExportDownloadAudit)
class SensitiveExportDownloadAuditAdmin(admin.ModelAdmin):
    list_display = ("export_request", "downloader", "outcome", "downloaded_at")
    search_fields = ("export_request__public_id", "downloader__username", "reason", "public_id")
    list_filter = ("outcome", "downloaded_at")
    raw_id_fields = ("export_request", "downloader")
    readonly_fields = ("public_id", "export_request", "downloader", "outcome", "reason", "request_metadata", "downloaded_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class InteroperabilityRunItemInline(admin.TabularInline):
    model = InteroperabilityRunItem
    extra = 0
    readonly_fields = (
        "row_number",
        "external_identifier",
        "internal_object_type",
        "internal_object_public_id",
        "internal_object_code",
        "status",
        "action",
        "safe_context",
        "source_record_ref",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class InteroperabilityRunErrorInline(admin.TabularInline):
    model = InteroperabilityRunError
    extra = 0
    readonly_fields = (
        "public_id",
        "item",
        "severity",
        "error_code",
        "field_path",
        "safe_message",
        "remediation_hint",
        "raw_value_digest",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExternalSystem)
class ExternalSystemAdmin(admin.ModelAdmin):
    list_display = ("system_key", "display_name", "system_type", "owner", "status", "updated_at")
    search_fields = ("system_key", "display_name", "owner")
    list_filter = ("system_type", "status", "created_at")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(InteroperabilityMappingVersion)
class InteroperabilityMappingVersionAdmin(admin.ModelAdmin):
    list_display = ("system", "version_label", "status", "effective_date", "retired_at", "reviewed_by")
    search_fields = ("system__system_key", "version_label", "reviewed_by__username")
    list_filter = ("status", "effective_date", "created_at")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("system", "reviewed_by")


@admin.register(ExternalOrgUnitMapping)
class ExternalOrgUnitMappingAdmin(admin.ModelAdmin):
    list_display = (
        "system",
        "mapping_version",
        "external_identifier",
        "internal_object_type",
        "internal_object_code",
        "mapping_confidence",
        "status",
    )
    search_fields = (
        "external_identifier",
        "external_display_name",
        "internal_object_public_id",
        "internal_object_code",
        "ward__name",
        "facility__name",
    )
    list_filter = ("internal_object_type", "status", "system", "effective_date")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("system", "mapping_version", "ward", "facility", "reviewed_by")


@admin.register(ExternalDataElementMapping)
class ExternalDataElementMappingAdmin(admin.ModelAdmin):
    list_display = (
        "system",
        "mapping_version",
        "exchange_type",
        "internal_field",
        "external_identifier",
        "required_for_exchange",
        "status",
    )
    search_fields = ("exchange_type", "internal_field", "external_identifier", "external_display_name")
    list_filter = ("exchange_type", "required_for_exchange", "status", "system")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("system", "mapping_version", "reviewed_by")


@admin.register(ExternalValueSetMapping)
class ExternalValueSetMappingAdmin(admin.ModelAdmin):
    list_display = ("system", "mapping_version", "value_set_key", "internal_value", "external_value", "status")
    search_fields = ("value_set_key", "internal_value", "external_value", "external_label")
    list_filter = ("value_set_key", "status", "system")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("system", "mapping_version", "reviewed_by")


@admin.register(InteroperabilityRun)
class InteroperabilityRunAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "direction",
        "exchange_type",
        "system",
        "status",
        "dry_run",
        "records_seen",
        "records_accepted",
        "records_rejected",
        "mapping_coverage",
        "started_at",
    )
    search_fields = ("public_id", "source_file_name", "endpoint_url", "operator__username", "error_summary")
    list_filter = ("direction", "exchange_type", "status", "dry_run", "system", "started_at")
    readonly_fields = (
        "public_id",
        "records_seen",
        "records_accepted",
        "records_rejected",
        "mapping_coverage",
        "error_summary",
        "dry_run_preview",
        "export_payload",
        "connector_config",
        "lineage_metadata",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("system", "mapping_version", "retry_of", "operator")
    inlines = (InteroperabilityRunItemInline, InteroperabilityRunErrorInline)


@admin.register(InteroperabilityRunItem)
class InteroperabilityRunItemAdmin(admin.ModelAdmin):
    list_display = ("run", "row_number", "external_identifier", "status", "action", "source_record_ref")
    search_fields = ("run__public_id", "external_identifier", "internal_object_public_id", "source_record_ref")
    list_filter = ("status", "action", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("run",)


@admin.register(InteroperabilityRunError)
class InteroperabilityRunErrorAdmin(admin.ModelAdmin):
    list_display = ("run", "item", "severity", "error_code", "field_path", "created_at")
    search_fields = ("run__public_id", "error_code", "field_path", "safe_message")
    list_filter = ("severity", "error_code", "created_at")
    readonly_fields = ("public_id", "created_at")
    autocomplete_fields = ("run", "item")


class SourceDataUploadArtifactInline(admin.TabularInline):
    model = SourceDataUploadArtifact
    extra = 0
    readonly_fields = (
        "original_filename",
        "content_type",
        "size_bytes",
        "sha256",
        "storage_backend",
        "storage_path",
        "retention_expires_at",
        "redaction_state",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SourceDataValidationIssueInline(admin.TabularInline):
    model = SourceDataValidationIssue
    extra = 0
    readonly_fields = ("row_number", "severity", "code", "column_name", "message", "safe_context", "created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SourceDataUploadEventInline(admin.TabularInline):
    model = SourceDataUploadEvent
    extra = 0
    readonly_fields = ("actor", "event_type", "event_at", "ip_address_hash", "user_agent_hash", "metadata")
    autocomplete_fields = ("actor",)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SourceDataUploadBatch)
class SourceDataUploadBatchAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "feed_key",
        "source_name",
        "status",
        "validation_status",
        "import_status",
        "approval_status",
        "created_by",
        "created_at",
    )
    search_fields = ("public_id", "feed_key", "source_name", "source_ref", "domain_ingestion_run_type")
    list_filter = (
        "feed_key",
        "domain",
        "source_type",
        "status",
        "validation_status",
        "import_status",
        "approval_status",
        "created_at",
    )
    autocomplete_fields = (
        "duplicate_of",
        "replaces_upload",
        "approval_requested_by",
        "approved_by",
        "created_by",
        "confirmed_by",
        "surveillance_ingestion_run",
        "population_exposure_ingestion_run",
    )
    readonly_fields = ("public_id", "created_at", "updated_at")
    inlines = (SourceDataUploadArtifactInline, SourceDataValidationIssueInline, SourceDataUploadEventInline)


@admin.register(SourceDataUploadArtifact)
class SourceDataUploadArtifactAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "upload_batch", "size_bytes", "storage_backend", "redaction_state", "created_at")
    search_fields = ("original_filename", "sha256", "storage_path", "upload_batch__public_id")
    list_filter = ("storage_backend", "redaction_state", "created_at", "retention_expires_at")
    autocomplete_fields = ("upload_batch",)
    readonly_fields = ("created_at",)


@admin.register(SourceDataValidationIssue)
class SourceDataValidationIssueAdmin(admin.ModelAdmin):
    list_display = ("upload_batch", "severity", "code", "row_number", "column_name", "created_at")
    search_fields = ("upload_batch__public_id", "code", "column_name", "message")
    list_filter = ("severity", "code", "created_at")
    autocomplete_fields = ("upload_batch",)
    readonly_fields = ("created_at",)


@admin.register(SourceDataUploadEvent)
class SourceDataUploadEventAdmin(admin.ModelAdmin):
    list_display = ("upload_batch", "event_type", "actor", "event_at")
    search_fields = ("upload_batch__public_id", "event_type", "actor__username")
    list_filter = ("event_type", "event_at")
    autocomplete_fields = ("upload_batch", "actor")
    readonly_fields = ("event_at", "ip_address_hash", "user_agent_hash")


@admin.register(SourceDataConnectorRun)
class SourceDataConnectorRunAdmin(admin.ModelAdmin):
    list_display = ("connector_key", "target_feed_key", "status", "fetched_record_count", "requested_by", "started_at")
    search_fields = ("connector_key", "target_feed_key", "source_name", "source_ref", "upload_batch__public_id")
    list_filter = ("connector_key", "target_feed_key", "status", "feed_mode", "started_at")
    autocomplete_fields = ("upload_batch", "requested_by")
    readonly_fields = ("started_at", "completed_at")


@admin.register(SourceDataFeedModeOverride)
class SourceDataFeedModeOverrideAdmin(admin.ModelAdmin):
    list_display = ("feed_key", "feed_mode", "csv_upload_enabled", "authoritative_connector_key", "updated_by", "updated_at")
    search_fields = ("feed_key", "authoritative_connector_key", "reason")
    list_filter = ("feed_mode", "csv_upload_enabled", "created_at", "updated_at")
    autocomplete_fields = ("updated_by",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(FacilityReadinessSource)
class FacilityReadinessSourceAdmin(admin.ModelAdmin):
    list_display = ("source_name", "source_type", "source_timestamp", "reporting_period_start", "reporting_period_end", "is_active")
    search_fields = ("source_name", "source_ref", "operator_note")
    list_filter = ("source_type", "is_active", "reporting_period_start", "created_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(FacilityReadinessIngestionRun)
class FacilityReadinessIngestionRunAdmin(admin.ModelAdmin):
    list_display = ("source_name", "status", "source_type", "records_seen", "records_loaded", "records_rejected", "started_at")
    search_fields = ("source_name", "source_ref", "input_ref", "error_summary")
    list_filter = ("status", "source_type", "execution_mode", "started_at")
    autocomplete_fields = ("source",)
    readonly_fields = ("started_at", "completed_at")


@admin.register(FacilityReadinessSnapshot)
class FacilityReadinessSnapshotAdmin(admin.ModelAdmin):
    list_display = ("facility", "ward", "reported_at", "readiness_state", "freshness_state", "source_kind")
    search_fields = ("facility__name", "facility__facility_code", "ward__name", "ward__ward_code", "source_name", "source_ref")
    list_filter = ("readiness_state", "freshness_state", "source_kind", "reported_at")
    autocomplete_fields = ("facility", "ward", "ingestion_run", "source")
    readonly_fields = ("created_at",)


class FacilityReadinessReviewEventInline(admin.TabularInline):
    model = FacilityReadinessReviewEvent
    extra = 0
    autocomplete_fields = ("actor",)
    readonly_fields = (
        "public_id",
        "actor",
        "action",
        "old_status",
        "new_status",
        "detail",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FacilityReadinessReview)
class FacilityReadinessReviewAdmin(admin.ModelAdmin):
    list_display = ("facility", "ward", "status", "severity", "created_by", "assigned_to", "created_at")
    search_fields = ("facility__name", "ward__name", "public_id", "notes")
    list_filter = ("status", "severity", "ward", "created_at")
    autocomplete_fields = ("facility", "ward", "created_by", "assigned_to")
    readonly_fields = (
        "public_id",
        "decision_summary_snapshot",
        "reason_codes",
        "acknowledged_at",
        "resolved_at",
        "dismissed_at",
        "created_at",
        "updated_at",
    )
    inlines = [FacilityReadinessReviewEventInline]


@admin.register(FacilityReadinessReviewEvent)
class FacilityReadinessReviewEventAdmin(admin.ModelAdmin):
    list_display = ("review", "action", "actor", "old_status", "new_status", "created_at")
    search_fields = ("review__facility__name", "review__public_id", "detail")
    list_filter = ("action", "created_at")
    autocomplete_fields = ("review", "actor")
    readonly_fields = ("public_id", "created_at")


@admin.register(FacilityReadinessUpdateRequest)
class FacilityReadinessUpdateRequestAdmin(admin.ModelAdmin):
    list_display = ("facility", "review", "contact", "channel", "status", "requested_by", "requested_at")
    search_fields = ("facility__name", "review__public_id", "contact__name", "message_body", "public_id")
    list_filter = ("channel", "status", "requested_at")
    autocomplete_fields = ("review", "facility", "contact", "requested_by")
    readonly_fields = (
        "public_id",
        "provider_reference",
        "failure_reason",
        "requested_at",
        "sent_at",
        "acknowledged_at",
        "created_at",
        "updated_at",
    )


@admin.register(FacilityReadinessEscalation)
class FacilityReadinessEscalationAdmin(admin.ModelAdmin):
    list_display = ("facility", "ward", "status", "severity", "assigned_to", "created_by", "acknowledged_by", "created_at")
    search_fields = ("facility__name", "ward__name", "review__public_id", "reason", "notes", "public_id")
    list_filter = ("status", "severity", "ward", "created_at")
    autocomplete_fields = ("review", "facility", "ward", "created_by", "acknowledged_by", "assigned_to")
    readonly_fields = (
        "public_id",
        "created_at",
        "updated_at",
        "acknowledged_at",
        "resolved_at",
        "dismissed_at",
    )


@admin.register(RiskScore)
class RiskScoreAdmin(admin.ModelAdmin):
    list_display = (
        "ward",
        "model_run",
        "risk_level",
        "score",
        "rainfall_mm",
        "flood_indicator",
        "predicted_cases",
        "generated_at",
    )
    search_fields = ("ward__name", "model_version", "model_run__model_version")
    list_filter = ("risk_level", "source", "generated_at")


@admin.register(IngestionRun)
class IngestionRunAdmin(admin.ModelAdmin):
    list_display = (
        "run_type",
        "status",
        "source_mode",
        "source_kind",
        "source_name",
        "freshness_state",
        "fallback_used",
        "started_at",
        "completed_at",
    )
    search_fields = ("run_type", "status", "source_mode", "source_name", "operator_note", "error_message")
    list_filter = ("run_type", "status", "source_mode", "source_kind", "freshness_state", "started_at")


@admin.register(ClimateRecord)
class ClimateRecordAdmin(admin.ModelAdmin):
    list_display = (
        "ward",
        "record_type",
        "source_provider",
        "lead_day",
        "forecast_horizon_days",
        "valid_date",
        "issue_time",
        "observed_timestamp",
        "rainfall_mm",
        "quality_flag",
        "fallback_flag",
    )
    search_fields = ("ward__name", "source_provider", "source_ref", "source_run")
    list_filter = ("record_type", "source_provider", "quality_flag", "fallback_flag", "valid_date")
    autocomplete_fields = ("ward", "ingestion_run")
    readonly_fields = ("lineage_metadata", "raw_payload", "created_at")


@admin.register(ETLHeartbeat)
class ETLHeartbeatAdmin(admin.ModelAdmin):
    list_display = ("component", "task_name", "status", "recorded_at")
    search_fields = ("component", "task_name", "status")
    list_filter = ("component", "status", "recorded_at")


@admin.register(SurveillanceSource)
class SurveillanceSourceAdmin(admin.ModelAdmin):
    list_display = (
        "source_name",
        "source_type",
        "reporting_period_start",
        "reporting_period_end",
        "source_timestamp",
        "submitted_at",
        "is_active",
    )
    search_fields = ("source_name", "source_ref", "operator_note")
    list_filter = ("source_type", "is_active", "submitted_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SurveillanceIngestionRun)
class SurveillanceIngestionRunAdmin(admin.ModelAdmin):
    list_display = (
        "source_name",
        "source_type",
        "status",
        "correction_mode",
        "execution_mode",
        "reporting_period_start",
        "reporting_period_end",
        "records_loaded",
        "records_seen",
        "records_rejected",
        "started_at",
        "completed_at",
    )
    search_fields = ("source_name", "source_ref", "input_ref", "operator_note", "correction_reason", "error_summary")
    list_filter = ("source_type", "status", "correction_mode", "execution_mode", "started_at")
    autocomplete_fields = ("source", "replay_of")
    readonly_fields = (
        "source_metadata",
        "results",
        "rejected_rows",
        "records_seen",
        "records_loaded",
        "records_rejected",
        "started_at",
        "completed_at",
    )


@admin.register(SurveillanceRecord)
class SurveillanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "ward",
        "facility",
        "disease_category",
        "case_class",
        "outbreak_label",
        "count_value",
        "truth_level",
        "freshness_state",
        "reporting_period_start",
        "reporting_period_end",
        "source_name",
    )
    search_fields = ("ward__name", "facility__name", "source_name", "source_ref")
    list_filter = (
        "disease_category",
        "case_class",
        "outbreak_label",
        "truth_level",
        "source_kind",
        "freshness_state",
        "reporting_granularity",
    )
    autocomplete_fields = ("ward", "facility", "ingestion_run", "source")
    readonly_fields = ("raw_payload", "created_at")


@admin.register(SurveillanceLabelWindow)
class SurveillanceLabelWindowAdmin(admin.ModelAdmin):
    list_display = (
        "ward",
        "dataset_ref",
        "schema_version",
        "label_window_start",
        "label_window_end",
        "outbreak_label",
        "label_truth_level",
        "suspected_case_count",
        "confirmed_case_count",
        "proxy_case_count",
        "source_record_count",
        "generation_mode",
    )
    search_fields = ("ward__name", "dataset_ref", "schema_version", "generation_mode")
    list_filter = ("outbreak_label", "label_truth_level", "schema_version", "generation_mode")
    autocomplete_fields = ("ward", "feature_dataset")
    readonly_fields = ("source_coverage_summary", "generated_from_record_refs", "created_at")


@admin.register(PopulationExposureSource)
class PopulationExposureSourceAdmin(admin.ModelAdmin):
    list_display = (
        "source_name",
        "source_type",
        "release_version",
        "source_timestamp",
        "submitted_at",
        "is_active",
    )
    search_fields = ("source_name", "source_ref", "release_version", "operator_note")
    list_filter = ("source_type", "is_active", "submitted_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PopulationExposureIngestionRun)
class PopulationExposureIngestionRunAdmin(admin.ModelAdmin):
    list_display = (
        "source_name",
        "source_type",
        "release_version",
        "status",
        "correction_mode",
        "execution_mode",
        "records_loaded",
        "records_seen",
        "records_rejected",
        "started_at",
        "completed_at",
    )
    search_fields = (
        "source_name",
        "source_ref",
        "release_version",
        "input_ref",
        "operator_note",
        "replacement_reason",
        "error_summary",
    )
    list_filter = ("source_type", "status", "correction_mode", "execution_mode", "started_at")
    autocomplete_fields = ("source", "replay_of", "replaces_run")
    readonly_fields = (
        "source_metadata",
        "results",
        "rejected_rows",
        "records_seen",
        "records_loaded",
        "records_rejected",
        "started_at",
        "completed_at",
    )


@admin.register(PopulationBaselineRecord)
class PopulationBaselineRecordAdmin(admin.ModelAdmin):
    list_display = (
        "ward",
        "population_total",
        "population_under_five",
        "truth_class",
        "source_kind",
        "release_version",
        "recorded_at",
    )
    search_fields = ("ward__name", "source_name", "source_ref", "release_version", "supersedes_record_ref")
    list_filter = ("truth_class", "source_kind", "freshness_state", "recorded_at")
    autocomplete_fields = ("ward", "ingestion_run", "source")
    readonly_fields = ("raw_payload", "created_at")


@admin.register(ExposureFeatureRecord)
class ExposureFeatureRecordAdmin(admin.ModelAdmin):
    list_display = (
        "ward",
        "exposure_type",
        "exposure_value",
        "unit",
        "truth_class",
        "source_kind",
        "release_version",
        "recorded_at",
    )
    search_fields = ("ward__name", "source_name", "source_ref", "release_version", "notes")
    list_filter = ("exposure_type", "truth_class", "source_kind", "freshness_state", "recorded_at")
    autocomplete_fields = ("ward", "ingestion_run", "source")
    readonly_fields = ("raw_payload", "created_at")


@admin.register(CatchmentPopulationRecord)
class CatchmentPopulationRecordAdmin(admin.ModelAdmin):
    list_display = (
        "facility",
        "catchment_population_estimate",
        "catchment_under_five_estimate",
        "truth_class",
        "source_kind",
        "release_version",
        "recorded_at",
    )
    search_fields = ("facility__name", "facility__facility_code", "source_name", "source_ref", "release_version")
    list_filter = ("truth_class", "source_kind", "freshness_state", "recorded_at")
    autocomplete_fields = ("facility", "ingestion_run", "source")
    readonly_fields = ("assigned_ward_ids", "raw_payload", "created_at")


@admin.register(WardSpatialRelationship)
class WardSpatialRelationshipAdmin(admin.ModelAdmin):
    list_display = (
        "source_ward",
        "target_ward",
        "relationship_type",
        "generation_method",
        "confidence",
        "geometry_dataset_version",
        "generated_at",
    )
    search_fields = (
        "source_ward__name",
        "target_ward__name",
        "geometry_dataset_version__version_label",
        "geometry_dataset_version__dataset__slug",
    )
    list_filter = ("relationship_type", "generation_method", "generated_at")
    autocomplete_fields = ("source_ward", "target_ward")
    raw_id_fields = ("geometry_dataset_version",)
    readonly_fields = ("lineage_metadata", "created_at", "updated_at")


@admin.register(FacilityCatchment)
class FacilityCatchmentAdmin(admin.ModelAdmin):
    list_display = (
        "facility",
        "primary_ward",
        "catchment_method",
        "source_kind",
        "population_estimate",
        "confidence",
        "is_approximate",
        "generated_at",
    )
    search_fields = (
        "facility__name",
        "facility__facility_code",
        "primary_ward__name",
        "geometry_dataset_version__version_label",
        "geometry_dataset_version__dataset__slug",
    )
    list_filter = ("catchment_method", "source_kind", "is_approximate", "generated_at")
    autocomplete_fields = ("facility", "primary_ward")
    raw_id_fields = ("geometry_dataset_version",)
    filter_horizontal = ("covered_wards",)
    readonly_fields = ("lineage_metadata", "created_at", "updated_at")


@admin.register(ModelRun)
class ModelRunAdmin(admin.ModelAdmin):
    list_display = (
        "model_version",
        "algorithm_name",
        "run_purpose",
        "execution_context",
        "promotion_target",
        "status",
        "month",
        "feature_schema_version",
        "training_row_count",
        "inference_row_count",
        "started_at",
    )
    search_fields = ("model_version", "algorithm_name", "status", "feature_schema_version", "training_dataset_ref", "inference_dataset_ref")
    list_filter = ("status", "algorithm_name", "month", "started_at")

    @admin.display(description="Run Purpose")
    def run_purpose(self, obj):
        return obj.metadata.get("run_purpose", "unknown")

    @admin.display(description="Execution Context")
    def execution_context(self, obj):
        return obj.metadata.get("execution_context", "unknown")

    @admin.display(description="Promotion Target")
    def promotion_target(self, obj):
        return obj.metadata.get("promotion_target", "unknown")


class ModelGovernanceEventInline(admin.TabularInline):
    model = ModelGovernanceEvent
    extra = 0
    can_delete = False
    readonly_fields = (
        "event_type",
        "actor",
        "reason",
        "previous_approval_state",
        "resulting_approval_state",
        "previous_lifecycle_state",
        "resulting_lifecycle_state",
        "request_id",
        "occurred_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ModelRegistryEntry)
class ModelRegistryEntryAdmin(admin.ModelAdmin):
    list_display = (
        "model_version",
        "algorithm",
        "registry_version",
        "approval_state",
        "lifecycle_state",
        "deployment_target",
        "promotion_state",
        "monitoring_state",
        "active_from",
        "active_until",
        "review_due_date",
        "owner",
    )
    search_fields = ("model_version", "algorithm", "owner", "model_run__model_version", "artifact_sha256")
    list_filter = (
        "approval_state",
        "lifecycle_state",
        "deployment_target",
        "promotion_state",
        "monitoring_state",
        "algorithm",
        "review_due_date",
    )
    raw_id_fields = ("model_run", "promotion_event", "rollback_target", "challenger_of")
    inlines = [ModelGovernanceEventInline]
    readonly_fields = (
        "public_id",
        "registry_version",
        "artifact_sha256",
        "artifact_size_bytes",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ModelPromotionEvent)
class ModelPromotionEventAdmin(admin.ModelAdmin):
    list_display = ("model_run", "source", "promoted_by", "active_from", "review_due_date", "occurred_at")
    search_fields = ("model_run__model_version", "registry_entry__model_version", "source", "promoted_by")
    list_filter = ("source", "occurred_at", "review_due_date")
    raw_id_fields = ("registry_entry", "model_run", "previous_registry_entry")
    readonly_fields = ("public_id", "occurred_at")


@admin.register(ModelRollbackEvent)
class ModelRollbackEventAdmin(admin.ModelAdmin):
    list_display = ("rolled_back_from", "rollback_target", "rolled_back_by", "occurred_at")
    search_fields = (
        "rolled_back_from__model_version",
        "rollback_target__model_version",
        "rolled_back_by",
        "reason",
    )
    list_filter = ("occurred_at",)
    raw_id_fields = ("rolled_back_from", "rollback_target")
    readonly_fields = ("public_id", "occurred_at")


@admin.register(ModelGovernanceEvent)
class ModelGovernanceEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "registry_entry",
        "actor",
        "previous_approval_state",
        "resulting_approval_state",
        "previous_lifecycle_state",
        "resulting_lifecycle_state",
        "occurred_at",
    )
    search_fields = ("registry_entry__model_version", "actor", "reason", "request_id")
    list_filter = ("event_type", "resulting_approval_state", "resulting_lifecycle_state", "occurred_at")
    raw_id_fields = ("registry_entry",)
    readonly_fields = (
        "public_id",
        "registry_entry",
        "event_type",
        "actor",
        "reason",
        "previous_approval_state",
        "resulting_approval_state",
        "previous_lifecycle_state",
        "resulting_lifecycle_state",
        "evidence_snapshot",
        "request_id",
        "occurred_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ModelMonitoringThreshold)
class ModelMonitoringThresholdAdmin(admin.ModelAdmin):
    list_display = (
        "metric_name",
        "version",
        "warning_threshold",
        "breach_threshold",
        "direction",
        "is_active",
    )
    search_fields = ("metric_name", "version", "baseline_window")
    list_filter = ("is_active", "direction", "version")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(ModelMonitoringSnapshot)
class ModelMonitoringSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "model_run",
        "metric_name",
        "value",
        "baseline_value",
        "threshold_value",
        "state",
        "threshold_version",
        "generated_at",
    )
    search_fields = ("model_run__model_version", "registry_entry__model_version", "metric_name", "threshold_version")
    list_filter = ("metric_name", "metric_family", "state", "threshold_version", "generated_at")
    raw_id_fields = ("registry_entry", "model_run", "threshold")
    readonly_fields = ("public_id", "monitoring_run_id", "created_at")


@admin.register(ModelRetrainingRecommendation)
class ModelRetrainingRecommendationAdmin(admin.ModelAdmin):
    list_display = (
        "model_run",
        "recommendation_state",
        "recommended_action",
        "new_label_count",
        "false_alert_count",
        "miss_count",
        "generated_at",
    )
    search_fields = ("model_run__model_version", "registry_entry__model_version", "recommended_action")
    list_filter = ("recommendation_state", "recommended_action", "generated_at")
    raw_id_fields = ("registry_entry", "model_run")
    readonly_fields = ("public_id", "created_at")


@admin.register(ModelChampionChallengerComparison)
class ModelChampionChallengerComparisonAdmin(admin.ModelAdmin):
    list_display = (
        "champion_model_run",
        "challenger_model_run",
        "benchmark_status",
        "comparison_validity",
        "recommended_action",
        "generated_at",
    )
    search_fields = (
        "champion_model_run__model_version",
        "challenger_model_run__model_version",
        "challenger_algorithm",
        "challenger_model_version",
    )
    list_filter = ("benchmark_status", "comparison_validity", "recommended_action", "generated_at")
    raw_id_fields = ("champion_registry_entry", "champion_model_run", "challenger_model_run")
    readonly_fields = ("public_id", "created_at")


@admin.register(FeatureDataset)
class FeatureDatasetAdmin(admin.ModelAdmin):
    list_display = ("dataset_ref", "dataset_kind", "schema_version", "source_kind", "month", "row_count", "created_at")
    search_fields = ("dataset_ref", "schema_version")
    list_filter = ("dataset_kind", "schema_version", "source_kind", "created_at")


@admin.register(FeatureDatasetRow)
class FeatureDatasetRowAdmin(admin.ModelAdmin):
    list_display = ("dataset", "ward_name_snapshot", "month", "label", "created_at")
    search_fields = ("dataset__dataset_ref", "ward_name_snapshot")
    list_filter = ("dataset__dataset_kind", "month", "created_at")


@admin.register(OperationalMetricDefinition)
class OperationalMetricDefinitionAdmin(admin.ModelAdmin):
    list_display = ("metric_key", "version", "metric_group", "metric_family", "value_type", "owner", "is_active")
    search_fields = ("metric_key", "display_name", "owner", "source_model")
    list_filter = ("metric_group", "metric_family", "value_type", "is_active")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(OperationalMetricDimension)
class OperationalMetricDimensionAdmin(admin.ModelAdmin):
    list_display = ("dimension_key", "display_name", "value_type", "source_model", "is_active")
    search_fields = ("dimension_key", "display_name", "source_model")
    list_filter = ("value_type", "is_active")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(OperationalMetricSnapshot)
class OperationalMetricSnapshotAdmin(admin.ModelAdmin):
    list_display = ("metric_definition", "date", "grain", "value", "status", "ward", "facility", "source_channel")
    search_fields = ("snapshot_key", "metric_definition__metric_key", "county", "sub_county", "model_version")
    list_filter = ("grain", "status", "date", "source_channel", "action_type", "alert_severity")
    raw_id_fields = ("metric_definition", "ward", "facility", "chv")
    readonly_fields = ("public_id", "snapshot_key", "created_at", "updated_at")


@admin.register(OperationalBaselinePeriod)
class OperationalBaselinePeriodAdmin(admin.ModelAdmin):
    list_display = ("metric_definition", "name", "status", "period_start", "period_end", "baseline_value")
    search_fields = ("baseline_key", "name", "metric_definition__metric_key", "owner")
    list_filter = ("status", "grain", "period_start", "period_end")
    raw_id_fields = ("metric_definition",)
    readonly_fields = ("public_id", "baseline_key", "created_at", "updated_at")


@admin.register(OperationalSLAThreshold)
class OperationalSLAThresholdAdmin(admin.ModelAdmin):
    list_display = ("threshold_key", "version", "metric_definition", "comparator", "target_value", "is_active")
    search_fields = ("threshold_key", "display_name", "metric_definition__metric_key", "owner", "rationale")
    list_filter = ("comparator", "is_active", "effective_from")
    raw_id_fields = ("metric_definition",)
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(OperationalThresholdBreach)
class OperationalThresholdBreachAdmin(admin.ModelAdmin):
    list_display = ("metric_definition", "breach_type", "severity", "status", "date", "threshold", "ward")
    search_fields = ("breach_key", "metric_key_snapshot", "threshold_key_snapshot", "warning_code", "title")
    list_filter = ("breach_type", "severity", "status", "date")
    raw_id_fields = ("metric_definition", "threshold", "snapshot", "ward")
    readonly_fields = (
        "public_id",
        "breach_key",
        "metric_key_snapshot",
        "metric_version_snapshot",
        "threshold_key_snapshot",
        "threshold_version_snapshot",
        "created_at",
        "updated_at",
    )


@admin.register(FacilityForecastRun)
class FacilityForecastRunAdmin(admin.ModelAdmin):
    list_display = (
        "model_version",
        "algorithm_name",
        "status",
        "horizon_days",
        "feature_schema_version",
        "training_row_count",
        "inference_row_count",
        "started_at",
        "completed_at",
    )
    search_fields = ("model_version", "algorithm_name", "target_definition")
    list_filter = ("status", "algorithm_name", "horizon_days", "started_at")


@admin.register(FacilityForecast)
class FacilityForecastAdmin(admin.ModelAdmin):
    list_display = (
        "facility",
        "forecast_run",
        "projected_case_burden",
        "projected_pressure_score",
        "projected_readiness_state",
        "forecast_mode",
        "generated_at",
    )
    search_fields = ("facility__name", "forecast_run__model_version", "model_version")
    list_filter = ("projected_readiness_state", "forecast_mode", "generated_at")


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = (
        "ward",
        "channel",
        "recipient",
        "status",
        "resolved_language",
        "fallback_used",
        "attempt_count",
        "max_attempts",
        "next_retry_at",
        "sent_at",
        "created_at",
    )
    search_fields = ("ward__name", "recipient", "external_id", "delivery_backend")
    list_filter = ("channel", "status", "resolved_language", "fallback_used", "created_at")


@admin.register(CHVCoverageRequest)
class CHVCoverageRequestAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "ward",
        "status",
        "priority",
        "trigger_source",
        "requested_chv_count",
        "requested_by",
        "assigned_to_user",
        "reviewed_by",
        "created_at",
    )
    search_fields = (
        "public_id",
        "ward__name",
        "requested_by__username",
        "assigned_to_user__username",
        "reviewed_by__username",
        "assigned_to_team",
        "reason",
        "linked_alert_links__alert__public_id",
    )
    list_filter = ("status", "priority", "trigger_source", "created_at", "reviewed_at")
    readonly_fields = ("public_id", "trigger_source", "created_at", "updated_at")
    inlines = (CHVCoverageRequestAlertLinkInline,)

    def save_model(self, request, obj, form, change):
        if not change:
            if obj.requested_by is None:
                raise ValidationError("A requesting user is required when creating a CHV coverage request.")
            if obj.trigger_source == CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN:
                raise ValidationError("Create alert-driven coverage requests through the linked alert workflow, not directly in admin.")
            created = create_chv_coverage_request(
                ward=obj.ward,
                requested_by=obj.requested_by,
                priority=obj.priority,
                reason=obj.reason,
                requested_chv_count=obj.requested_chv_count,
                notes=obj.notes,
                trigger_source=obj.trigger_source,
            )
            updates = []
            for field in ("assigned_to_user", "assigned_to_team", "expected_response_by"):
                value = getattr(obj, field, None)
                if value != getattr(created, field):
                    setattr(created, field, value)
                    updates.append(field)
            if updates:
                created.save(update_fields=updates + ["updated_at"])
            obj.pk = created.pk
            obj.public_id = created.public_id
            return

        previous = CHVCoverageRequest.objects.get(pk=obj.pk)
        status_changed = "status" in form.changed_data and obj.status != previous.status
        request_record = previous

        if "trigger_source" in form.changed_data and obj.trigger_source != previous.trigger_source:
            raise ValidationError("Trigger source is immutable after request creation.")

        if obj.trigger_source == CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN and not previous.linked_alert_links.exists():
            raise ValidationError("Alert-driven coverage requests must have stored linked alerts.")

        if status_changed:
            if obj.status == CHVCoverageRequest.STATUS_APPROVED:
                request_record = approve_chv_coverage_request(previous, actor=request.user, reason=obj.review_decision_reason)
            elif obj.status == CHVCoverageRequest.STATUS_REJECTED:
                request_record = reject_chv_coverage_request(previous, actor=request.user, reason=obj.review_decision_reason)
            elif obj.status == CHVCoverageRequest.STATUS_CANCELLED:
                request_record = cancel_chv_coverage_request(previous, actor=request.user, reason=obj.review_decision_reason)
            elif obj.status == CHVCoverageRequest.STATUS_RESOLVED:
                request_record = resolve_chv_coverage_request(previous, actor=request.user, reason=obj.review_decision_reason)
            else:
                raise ValidationError("Use a supported CHV coverage workflow transition.")

        direct_fields = [
            "priority",
            "reason",
            "requested_chv_count",
            "notes",
            "assigned_to_user",
            "assigned_to_team",
            "expected_response_by",
        ]
        updates = []
        for field in direct_fields:
            value = getattr(obj, field)
            if value != getattr(request_record, field):
                setattr(request_record, field, value)
                updates.append(field)
        if updates:
            request_record.save(update_fields=updates + ["updated_at"])

        obj.public_id = request_record.public_id


@admin.register(CHVCoverageRequestAlertLink)
class CHVCoverageRequestAlertLinkAdmin(admin.ModelAdmin):
    list_display = ("coverage_request", "alert", "linked_by", "created_at")
    search_fields = (
        "coverage_request__public_id",
        "alert__public_id",
        "alert__external_key",
        "alert__ward__name",
        "linked_by__username",
    )
    list_select_related = ("coverage_request", "alert", "linked_by", "alert__ward")
    readonly_fields = ("coverage_request", "alert", "linked_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CHVAssignment)
class CHVAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "coverage_request",
        "ward",
        "chv",
        "status",
        "assigned_by",
        "start_at",
        "end_at",
        "created_at",
    )
    search_fields = (
        "public_id",
        "coverage_request__public_id",
        "ward__name",
        "chv__name",
        "assigned_by__username",
    )
    list_filter = ("status", "ward", "created_at", "start_at", "end_at")
    readonly_fields = ("public_id", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not change:
            assignment = assign_chv_to_coverage_request(
                obj.coverage_request,
                chv=obj.chv,
                actor=request.user,
                notes=obj.notes,
                start_at=obj.start_at,
            )
            obj.pk = assignment.pk
            obj.public_id = assignment.public_id
            return

        previous = CHVAssignment.objects.get(pk=obj.pk)
        status_changed = "status" in form.changed_data and obj.status != previous.status
        assignment_record = previous

        if status_changed:
            if obj.status == CHVAssignment.STATUS_COMPLETED:
                assignment_record = complete_chv_assignment(previous, actor=request.user, notes=obj.notes)
            elif obj.status == CHVAssignment.STATUS_CANCELLED:
                assignment_record = cancel_chv_assignment(previous, actor=request.user, notes=obj.notes)
            else:
                raise ValidationError("Use a supported CHV assignment workflow transition.")
        else:
            updates = []
            for field in ("notes", "start_at", "end_at"):
                value = getattr(obj, field)
                if value != getattr(previous, field):
                    setattr(previous, field, value)
                    updates.append(field)
            if updates:
                previous.save(update_fields=updates + ["updated_at"])
                assignment_record = previous

        obj.public_id = assignment_record.public_id


@admin.register(CHVCoverageRequestEvent)
class CHVCoverageRequestEventAdmin(admin.ModelAdmin):
    list_display = (
        "coverage_request",
        "assignment",
        "action",
        "actor",
        "old_status",
        "new_status",
        "created_at",
    )
    search_fields = (
        "coverage_request__public_id",
        "assignment__public_id",
        "actor__username",
        "detail",
    )
    list_filter = ("action", "created_at")
    readonly_fields = (
        "public_id",
        "coverage_request",
        "assignment",
        "actor",
        "action",
        "old_status",
        "new_status",
        "detail",
        "metadata",
        "created_at",
    )


@admin.register(CHVCoverageRequestEmailDelivery)
class CHVCoverageRequestEmailDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "coverage_request",
        "event",
        "recipient_user",
        "recipient_email",
        "status",
        "delivery_backend",
        "created_at",
    )
    search_fields = (
        "coverage_request__public_id",
        "event__public_id",
        "recipient_user__username",
        "recipient_email",
        "external_id",
        "error_message",
    )
    list_filter = ("status", "delivery_backend", "created_at")
    readonly_fields = (
        "coverage_request",
        "event",
        "recipient_user",
        "recipient_email",
        "status",
        "delivery_backend",
        "external_id",
        "error_message",
        "metadata",
        "created_at",
    )


@admin.register(AlertWorkflowState)
class AlertWorkflowStateAdmin(admin.ModelAdmin):
    list_display = ("ward", "status", "trigger_severity", "active_alert_count", "updated_at")
    search_fields = ("ward__name", "trigger_reason", "recommended_action")
    list_filter = ("status", "trigger_severity", "updated_at")


@admin.register(AlertWorkflowEvent)
class AlertWorkflowEventAdmin(admin.ModelAdmin):
    list_display = ("workflow", "action", "actor", "old_status", "new_status", "created_at")
    search_fields = ("workflow__ward__name", "actor__username")
    list_filter = ("action", "created_at")


@admin.register(DashboardNotification)
class DashboardNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "type",
        "severity",
        "state",
        "recipient_role",
        "ward",
        "created_at",
    )
    search_fields = ("title", "body", "external_key", "source_object_id")
    list_filter = ("type", "severity", "state", "recipient_role", "created_at")


@admin.register(DashboardNotificationEvent)
class DashboardNotificationEventAdmin(admin.ModelAdmin):
    list_display = ("notification", "action", "actor", "old_state", "new_state", "created_at")
    search_fields = ("notification__title", "action", "actor__username")
    list_filter = ("action", "created_at")


@admin.register(TriageSession)
class TriageSessionAdmin(admin.ModelAdmin):
    list_display = (
        "channel",
        "phone_number",
        "ward",
        "referral_facility",
        "diarrhea",
        "vomiting",
        "dehydration",
        "fever",
        "referral_needed",
        "created_at",
    )
    search_fields = ("phone_number", "ward__name", "referral_facility__name")
    list_filter = ("channel", "referral_needed", "created_at")


@admin.register(UssdSessionLog)
class UssdSessionLogAdmin(admin.ModelAdmin):
    list_display = (
        "session_id",
        "phone_number",
        "service_code",
        "menu_version_label",
        "language",
        "menu_level",
        "session_outcome",
        "invalid_option",
        "is_terminal",
        "created_at",
    )
    search_fields = ("session_id", "phone_number", "service_code", "menu_version_label")
    list_filter = ("language", "session_outcome", "invalid_option", "is_terminal", "menu_level", "created_at")
    readonly_fields = ("created_at",)


@admin.register(UssdMenuVersion)
class UssdMenuVersionAdmin(admin.ModelAdmin):
    list_display = (
        "menu_key",
        "version_label",
        "language",
        "approval_status",
        "translation_status",
        "is_active",
        "approved_at",
        "retired_at",
        "updated_at",
    )
    search_fields = ("menu_key", "version_label", "language", "title")
    list_filter = ("language", "approval_status", "translation_status", "is_active", "created_at", "updated_at")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("approved_by", "created_by", "source_menu_version", "translation_reviewed_by")

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        if obj.approval_status == UssdMenuVersion.STATUS_APPROVED and obj.approved_at is None:
            obj.approved_at = timezone.now()
        if obj.approval_status == UssdMenuVersion.STATUS_APPROVED and obj.approved_by_id is None:
            obj.approved_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SyncQueue)
class SyncQueueAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_device_id",
        "device_registration",
        "contract_version",
        "upload_type",
        "client_submission_id",
        "idempotency_key",
        "phone_number",
        "ward",
        "status",
        "conflict_state",
        "processed_at",
        "created_at",
    )
    search_fields = ("source_device_id", "client_submission_id", "idempotency_key", "phone_number", "ward__name")
    list_filter = ("status", "upload_type", "conflict_state", "contract_version", "created_at")


@admin.register(CHVDeviceRegistration)
class CHVDeviceRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "device_id",
        "user",
        "chv",
        "ward",
        "contract_version",
        "platform",
        "is_active",
        "last_seen_at",
        "last_sync_at",
    )
    search_fields = ("device_id", "user__username", "chv__name", "ward__name")
    list_filter = ("contract_version", "platform", "is_active", "registered_at", "last_seen_at")
    readonly_fields = ("public_id", "registered_at", "updated_at")
    autocomplete_fields = ("user", "chv", "ward")


@admin.register(CHVOfflineRejectedSubmissionAudit)
class CHVOfflineRejectedSubmissionAuditAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "ward",
        "source_device_id",
        "upload_type",
        "rejection_stage",
        "error_code",
        "status_code",
        "created_at",
    )
    search_fields = (
        "public_id",
        "source_device_id",
        "client_submission_id",
        "idempotency_key",
        "error_code",
        "ward__name",
        "user__username",
    )
    list_filter = ("rejection_stage", "status_code", "created_at")
    readonly_fields = (
        "public_id",
        "user",
        "ward",
        "device_registration",
        "source_device_id",
        "client_submission_id",
        "idempotency_key",
        "upload_type",
        "contract_version",
        "rejection_stage",
        "error_code",
        "safe_error_summary",
        "field_paths",
        "status_code",
        "request_body_hmac",
        "request_metadata",
        "created_at",
    )
    autocomplete_fields = ("user", "ward", "device_registration")

    def has_add_permission(self, request):
        return False


@admin.register(SystemControlState)
class SystemControlStateAdmin(admin.ModelAdmin):
    list_display = (
        "control_key",
        "is_active",
        "active_until",
        "updated_by",
        "updated_at",
    )
    search_fields = ("control_key", "reason", "updated_by__username")
    list_filter = ("control_key", "is_active", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PredictionFeedback)
class PredictionFeedbackAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "ward",
        "feedback_type",
        "source_confidence",
        "training_usage_state",
        "submitted_at",
    )
    search_fields = ("public_id", "ward__name", "note", "risk_score__id", "model_run__model_version")
    list_filter = ("feedback_type", "source_confidence", "training_usage_state", "privacy_classification", "submitted_at")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("ward", "risk_score", "model_run", "label_window", "submitted_by")


@admin.register(PredictionFeedbackEvent)
class PredictionFeedbackEventAdmin(admin.ModelAdmin):
    list_display = ("feedback", "event_type", "old_training_usage_state", "new_training_usage_state", "created_at")
    search_fields = ("feedback__public_id", "detail", "actor__username")
    list_filter = ("event_type", "created_at")
    readonly_fields = ("public_id", "created_at")
    autocomplete_fields = ("feedback", "actor")


@admin.register(FeedbackAdjudication)
class FeedbackAdjudicationAdmin(admin.ModelAdmin):
    list_display = ("public_id", "feedback", "adjudication_state", "reviewer", "reviewed_at")
    search_fields = ("public_id", "feedback__public_id", "reason", "reviewer__username")
    list_filter = ("adjudication_state", "reviewed_at")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("feedback", "reviewer", "superseded_by_surveillance_label")


@admin.register(FeedbackLabelCandidate)
class FeedbackLabelCandidateAdmin(admin.ModelAdmin):
    list_display = (
        "candidate_ref",
        "ward",
        "outbreak_label",
        "label_truth_level",
        "training_usage_state",
        "created_at",
    )
    search_fields = ("candidate_ref", "feedback__public_id", "ward__name")
    list_filter = ("outbreak_label", "label_truth_level", "training_usage_state", "created_at")
    readonly_fields = ("public_id", "candidate_ref", "created_at", "updated_at")
    autocomplete_fields = ("feedback", "adjudication", "ward", "risk_score", "model_run", "superseded_by_surveillance_label")
