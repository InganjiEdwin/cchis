from rest_framework import serializers

from .models import Alert, CHV, HealthFacility, ModelRun, RiskScore, SyncQueue, TriageSession, UssdSessionLog, Ward


class WardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ward
        fields = [
            "id",
            "public_id",
            "name",
            "county",
            "sub_county",
            "ward_code",
            "current_risk_level",
            "current_risk_score",
            "is_active",
            "updated_at",
        ]


class CHVSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = CHV
        fields = [
            "id",
            "name",
            "phone_number",
            "language",
            "is_active",
            "ward",
            "ward_name",
            "created_at",
        ]


class HealthFacilitySerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = HealthFacility
        fields = [
            "id",
            "public_id",
            "name",
            "facility_code",
            "ward",
            "ward_name",
            "facility_type",
            "ownership",
            "level",
            "is_active",
            "contact_phone",
            "updated_at",
        ]


class RiskScoreSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    model_run_status = serializers.CharField(source="model_run.status", read_only=True)
    model_run_version = serializers.CharField(source="model_run.model_version", read_only=True)

    class Meta:
        model = RiskScore
        fields = [
            "id",
            "ward",
            "ward_name",
            "model_run",
            "model_run_status",
            "model_run_version",
            "score",
            "risk_level",
            "rainfall_mm",
            "flood_indicator",
            "predicted_cases",
            "source",
            "model_version",
            "notes",
            "generated_at",
        ]


class ModelRunSerializer(serializers.ModelSerializer):
    rainfall_ingestion_run_status = serializers.CharField(source="rainfall_ingestion_run.status", read_only=True)

    class Meta:
        model = ModelRun
        fields = [
            "id",
            "algorithm_name",
            "model_version",
            "status",
            "month",
            "feature_schema_version",
            "feature_keys",
            "training_dataset_ref",
            "inference_dataset_ref",
            "training_row_count",
            "inference_row_count",
            "evaluation_metrics",
            "metadata",
            "rainfall_ingestion_run",
            "rainfall_ingestion_run_status",
            "started_at",
            "completed_at",
        ]


class AlertSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = Alert
        fields = [
            "id",
            "ward",
            "ward_name",
            "risk_score",
            "channel",
            "recipient",
            "message",
            "status",
            "delivery_backend",
            "attempt_count",
            "max_attempts",
            "last_attempted_at",
            "next_retry_at",
            "external_id",
            "sent_at",
            "created_at",
            "error_message",
        ]


class TriggerAlertRequestSerializer(serializers.Serializer):
    ward_id = serializers.IntegerField(required=False)
    risk_level = serializers.ChoiceField(
        choices=[Ward.RISK_LOW, Ward.RISK_MEDIUM, Ward.RISK_HIGH],
        required=False,
    )
    send_sms = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if not attrs.get("ward_id") and not attrs.get("risk_level"):
            raise serializers.ValidationError(
                "Provide at least one of ward_id or risk_level."
            )
        return attrs


class CHVTriageRequestSerializer(serializers.Serializer):
    ward_id = serializers.IntegerField()
    phone_number = serializers.CharField(required=False, allow_blank=True)
    text_input = serializers.CharField(required=False, allow_blank=True, default="")
    channel = serializers.CharField(required=False, allow_blank=True, default="API")
    diarrhea = serializers.BooleanField(default=False)
    vomiting = serializers.BooleanField(default=False)
    dehydration = serializers.BooleanField(default=False)
    fever = serializers.BooleanField(default=False)


class CHVTriageResponseSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    referral_facility_name = serializers.CharField(source="referral_facility.name", read_only=True)

    class Meta:
        model = TriageSession
        fields = [
            "id",
            "channel",
            "phone_number",
            "ward",
            "ward_name",
            "referral_facility",
            "referral_facility_name",
            "text_input",
            "diarrhea",
            "vomiting",
            "dehydration",
            "fever",
            "recommendation",
            "referral_needed",
            "created_at",
        ]


class UssdSessionLogSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = UssdSessionLog
        fields = [
            "id",
            "session_id",
            "phone_number",
            "service_code",
            "text",
            "response_text",
            "ward",
            "ward_name",
            "menu_level",
            "created_at",
        ]


class SyncPayloadSerializer(serializers.Serializer):
    client_submission_id = serializers.CharField()
    diarrhea = serializers.BooleanField(default=False)
    vomiting = serializers.BooleanField(default=False)
    dehydration = serializers.BooleanField(default=False)
    fever = serializers.BooleanField(default=False)
    text_input = serializers.CharField(required=False, allow_blank=True, default="")


class CHVSyncRequestSerializer(serializers.Serializer):
    ward_id = serializers.IntegerField()
    phone_number = serializers.CharField(required=False, allow_blank=True, default="")
    source_device_id = serializers.CharField(required=False, allow_blank=True, default="")
    payloads = SyncPayloadSerializer(many=True)

    def validate_payloads(self, value):
        if not value:
            raise serializers.ValidationError("At least one payload is required.")
        submission_ids = [item["client_submission_id"].strip() for item in value if item.get("client_submission_id", "").strip()]
        if len(submission_ids) != len(value):
            raise serializers.ValidationError("Each payload must include client_submission_id.")
        if len(set(submission_ids)) != len(submission_ids):
            raise serializers.ValidationError("client_submission_id values must be unique within a request.")
        return value


class SyncQueueSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = SyncQueue
        fields = [
            "id",
            "source_device_id",
            "client_submission_id",
            "phone_number",
            "ward",
            "ward_name",
            "triage_session",
            "payload",
            "status",
            "processed_at",
            "error_message",
            "created_at",
        ]
