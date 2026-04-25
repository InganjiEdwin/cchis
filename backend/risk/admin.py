from django.contrib import admin
from .models import Alert, CHV, FeatureDataset, FeatureDatasetRow, HealthFacility, IngestionRun, ModelRun, RiskScore, SyncQueue, TriageSession, UssdSessionLog, Ward


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
    search_fields = ("run_type", "status", "source_mode", "source_name", "error_message")
    list_filter = ("run_type", "status", "source_mode", "source_kind", "freshness_state", "started_at")


@admin.register(ModelRun)
class ModelRunAdmin(admin.ModelAdmin):
    list_display = ("model_version", "algorithm_name", "status", "month", "feature_schema_version", "training_row_count", "inference_row_count", "started_at")
    search_fields = ("model_version", "algorithm_name", "status", "feature_schema_version", "training_dataset_ref", "inference_dataset_ref")
    list_filter = ("status", "algorithm_name", "month", "started_at")


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
