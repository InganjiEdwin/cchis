from django.contrib import admin
from django.core.exceptions import ValidationError

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
from .models import Alert, AlertWorkflowEvent, AlertWorkflowState, CatchmentPopulationRecord, CHV, CHVAssignment, CHVCoverageRequest, CHVCoverageRequestAlertLink, CHVCoverageRequestEmailDelivery, CHVCoverageRequestEvent, DashboardNotification, DashboardNotificationEvent, ETLHeartbeat, ExposureFeatureRecord, FacilityContact, FacilityReadinessEscalation, FacilityReadinessReview, FacilityReadinessReviewEvent, FacilityReadinessUpdateRequest, FacilityForecast, FacilityForecastRun, FeatureDataset, FeatureDatasetRow, HealthFacility, IngestionRun, ModelRun, PopulationBaselineRecord, PopulationExposureIngestionRun, PopulationExposureSource, RiskScore, SurveillanceIngestionRun, SurveillanceLabelWindow, SurveillanceRecord, SurveillanceSource, SyncQueue, SystemControlState, TriageSession, UssdSessionLog, Ward


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
        "attempt_count",
        "max_attempts",
        "next_retry_at",
        "sent_at",
        "created_at",
    )
    search_fields = ("ward__name", "recipient", "external_id", "delivery_backend")
    list_filter = ("channel", "status", "created_at")


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
        "menu_level",
        "created_at",
    )
    search_fields = ("session_id", "phone_number", "service_code")
    list_filter = ("menu_level", "created_at")


@admin.register(SyncQueue)
class SyncQueueAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_device_id",
        "client_submission_id",
        "phone_number",
        "ward",
        "status",
        "processed_at",
        "created_at",
    )
    search_fields = ("source_device_id", "client_submission_id", "phone_number", "ward__name")
    list_filter = ("status", "created_at")


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
