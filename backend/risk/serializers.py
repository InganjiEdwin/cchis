from rest_framework import serializers
from django.utils import timezone

from .ml.alignment import latest_promoted_riskscore_for_ward
from .models import Alert, AlertWorkflowEvent, AlertWorkflowState, CHV, CHVAssignment, CHVCoverageRequest, CHVCoverageRequestEvent, CHVMessage, DashboardNotification, DashboardNotificationEvent, ETLHeartbeat, FacilityContact, FacilityReadinessEscalation, FacilityReadinessReview, FacilityReadinessReviewEvent, FacilityReadinessUpdateRequest, FeatureDataset, FeatureDatasetRow, HealthFacility, IngestionRun, ModelRun, RiskScore, ScenarioSimulationRun, SyncQueue, TriageSession, UssdSessionLog, Ward


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


class WardDetailSerializer(serializers.ModelSerializer):
    predicted_cases = serializers.SerializerMethodField()
    latest_generated_at = serializers.SerializerMethodField()
    latest_source = serializers.SerializerMethodField()
    latest_model_version = serializers.SerializerMethodField()

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
            "predicted_cases",
            "latest_generated_at",
            "latest_source",
            "latest_model_version",
            "is_active",
            "updated_at",
        ]

    def _get_latest_risk(self, obj: Ward):
        return latest_promoted_riskscore_for_ward(obj)

    def get_predicted_cases(self, obj: Ward):
        latest = self._get_latest_risk(obj)
        return latest.predicted_cases if latest else 0

    def get_latest_generated_at(self, obj: Ward):
        latest = self._get_latest_risk(obj)
        return latest.generated_at if latest else None

    def get_latest_source(self, obj: Ward):
        latest = self._get_latest_risk(obj)
        return latest.source if latest else None

    def get_latest_model_version(self, obj: Ward):
        latest = self._get_latest_risk(obj)
        return latest.model_version if latest else None


class WardIntelligenceCurrentRiskSerializer(serializers.Serializer):
    risk_level = serializers.CharField(allow_null=True)
    risk_score = serializers.FloatField(allow_null=True)
    predicted_cases = serializers.IntegerField()
    decision_policy = serializers.DictField(required=False)
    generated_at = serializers.DateTimeField(allow_null=True)
    source = serializers.CharField(allow_null=True)
    model_version = serializers.CharField(allow_null=True)
    model_run_status = serializers.CharField(allow_null=True)


class WardIntelligenceTrendSerializer(serializers.Serializer):
    label = serializers.CharField()
    direction = serializers.ChoiceField(choices=["up", "down", "flat"])
    delta_points = serializers.IntegerField(allow_null=True)
    mode = serializers.CharField()


class WardIntelligenceDriverItemSerializer(serializers.Serializer):
    text = serializers.CharField()
    tone = serializers.ChoiceField(choices=["critical", "warning", "info"])
    source_field = serializers.CharField(allow_null=True)


class WardIntelligenceDriverSummarySerializer(serializers.Serializer):
    mode = serializers.CharField()
    items = WardIntelligenceDriverItemSerializer(many=True)


class WardIntelligenceGuidanceItemSerializer(serializers.Serializer):
    text = serializers.CharField()
    urgency = serializers.ChoiceField(choices=["primary", "review_only"])


class WardIntelligenceGuidanceSummarySerializer(serializers.Serializer):
    mode = serializers.CharField()
    items = WardIntelligenceGuidanceItemSerializer(many=True)


class WardIntelligenceFreshnessSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField(allow_null=True)
    is_stale = serializers.BooleanField()
    stale_threshold_minutes = serializers.IntegerField()
    history_count = serializers.IntegerField()
    alert_count = serializers.IntegerField()
    mode = serializers.CharField()


class WardIntelligenceWorkflowSerializer(serializers.Serializer):
    public_id = serializers.CharField()
    status = serializers.ChoiceField(
        choices=["NONE", "TRIGGER_ACTIVE", "REVIEW_PENDING", "ACTION_IN_PROGRESS", "RESOLVED"]
    )
    status_label = serializers.CharField()
    recommended_action = serializers.CharField()
    expected_operational_effect = serializers.CharField()
    eligible_actions = serializers.ListField(
        child=serializers.ChoiceField(choices=["REVIEW_TRIGGER", "OPEN_TRIGGER_FLOW", "VIEW_ALERT_HISTORY"])
    )
    active_alert_count = serializers.IntegerField()
    retry_pending_alert_count = serializers.IntegerField()
    failed_alert_count = serializers.IntegerField()
    queued_alert_count = serializers.IntegerField()
    latest_risk_update_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField()


class WardIntelligenceDecisionSummarySerializer(serializers.Serializer):
    action_required = serializers.BooleanField()
    headline = serializers.CharField()
    why = serializers.CharField()
    next_steps = serializers.ListField(child=serializers.CharField())
    primary_cta_kind = serializers.ChoiceField(
        choices=["REVIEW_TRIGGER", "OPEN_TRIGGER_FLOW", "VIEW_ALERT_HISTORY"]
    )


class WardIntelligenceHeaderContextSerializer(serializers.Serializer):
    last_alert_at = serializers.DateTimeField(allow_null=True)
    latest_record_at = serializers.DateTimeField(allow_null=True)
    freshness_state = serializers.ChoiceField(choices=["FRESH", "STALE"])
    trigger_state = serializers.ChoiceField(
        choices=["NONE", "TRIGGER_ACTIVE", "REVIEW_PENDING", "ACTION_IN_PROGRESS", "RESOLVED"]
    )
    expected_cases_7d = serializers.IntegerField()
    risk_score = serializers.FloatField(allow_null=True)


class CHVSerializer(serializers.ModelSerializer):
    public_id = serializers.UUIDField(read_only=True)
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = CHV
        fields = [
            "id",
            "public_id",
            "name",
            "phone_number",
            "language",
            "is_active",
            "ward",
            "ward_name",
            "created_at",
        ]


class CHVOperationsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    public_id = serializers.UUIDField()
    name = serializers.CharField()
    phone_number = serializers.CharField()
    language = serializers.CharField()
    is_active = serializers.BooleanField()
    ward = serializers.IntegerField()
    ward_name = serializers.CharField()
    created_at = serializers.DateTimeField()
    last_sync_at = serializers.DateTimeField(allow_null=True)
    last_activity_at = serializers.DateTimeField(allow_null=True)
    operational_status = serializers.ChoiceField(choices=["ACTIVE", "IDLE", "OFFLINE"])
    sync_health = serializers.ChoiceField(choices=["ONLINE", "DELAYED", "OFFLINE"])
    triage_sessions_24h = serializers.IntegerField()
    referrals_24h = serializers.IntegerField()
    sync_payloads_24h = serializers.IntegerField()
    ussd_sessions_24h = serializers.IntegerField()
    ward_alerts_total = serializers.IntegerField()
    ward_alerts_delivered = serializers.IntegerField()
    can_message = serializers.BooleanField()
    message_mode = serializers.ChoiceField(choices=["SEND", "QUEUE_ONLY", "UNAVAILABLE"])
    message_delivery_kind = serializers.ChoiceField(choices=["LIVE", "SIMULATED", "QUEUE_ONLY", "UNAVAILABLE"])
    can_view_activity = serializers.BooleanField()


class CHVActivityEventSerializer(serializers.Serializer):
    public_id = serializers.CharField()
    event_type = serializers.CharField()
    category = serializers.ChoiceField(choices=["MESSAGE", "ASSIGNMENT", "ALERT", "SYNC", "TRIAGE", "STATUS"])
    title = serializers.CharField()
    description = serializers.CharField()
    source = serializers.CharField()
    metadata = serializers.JSONField()
    created_by = serializers.IntegerField(allow_null=True)
    created_by_username = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()


class CHVMessageSerializer(serializers.ModelSerializer):
    sent_by_username = serializers.CharField(source="sent_by.username", allow_null=True, read_only=True)

    class Meta:
        model = CHVMessage
        fields = [
            "public_id",
            "channel",
            "message_body",
            "status",
            "delivery_kind",
            "delivery_backend",
            "provider_reference",
            "failure_reason",
            "sent_by",
            "sent_by_username",
            "created_at",
            "updated_at",
        ]


class CHVMessageCreateSerializer(serializers.Serializer):
    message_body = serializers.CharField(max_length=1000)
    channel = serializers.ChoiceField(choices=[CHVMessage.CHANNEL_SMS], default=CHVMessage.CHANNEL_SMS)


class CHVCoverageRequestEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", allow_null=True, read_only=True)
    assignment_public_id = serializers.UUIDField(source="assignment.public_id", allow_null=True, read_only=True)

    class Meta:
        model = CHVCoverageRequestEvent
        fields = [
            "public_id",
            "action",
            "actor",
            "actor_username",
            "assignment",
            "assignment_public_id",
            "old_status",
            "new_status",
            "detail",
            "metadata",
            "created_at",
        ]


class CHVAssignmentSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    ward_public_id = serializers.UUIDField(source="ward.public_id", read_only=True)
    chv_name = serializers.CharField(source="chv.name", read_only=True)
    chv_phone_number = serializers.CharField(source="chv.phone_number", read_only=True)
    assigned_by_username = serializers.CharField(source="assigned_by.username", allow_null=True, read_only=True)

    class Meta:
        model = CHVAssignment
        fields = [
            "public_id",
            "coverage_request",
            "ward",
            "ward_name",
            "ward_public_id",
            "chv",
            "chv_name",
            "chv_phone_number",
            "assigned_by",
            "assigned_by_username",
            "status",
            "start_at",
            "end_at",
            "notes",
            "created_at",
            "updated_at",
        ]


class CHVCoverageLinkedAlertSerializer(serializers.ModelSerializer):
    alert_id = serializers.IntegerField(source="id", read_only=True)
    alert_public_id = serializers.UUIDField(source="public_id", read_only=True)
    ward_id = serializers.IntegerField(allow_null=True, read_only=True)
    ward_name = serializers.CharField(source="ward.name", allow_null=True, read_only=True)

    class Meta:
        model = Alert
        fields = [
            "alert_id",
            "alert_public_id",
            "ward_id",
            "ward_name",
            "status",
            "channel",
            "created_at",
            "sent_at",
            "risk_score",
        ]


class CHVCoverageRequestSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    ward_public_id = serializers.UUIDField(source="ward.public_id", read_only=True)
    requested_by_username = serializers.CharField(source="requested_by.username", allow_null=True, read_only=True)
    assigned_to_username = serializers.CharField(source="assigned_to_user.username", allow_null=True, read_only=True)
    reviewed_by_username = serializers.CharField(source="reviewed_by.username", allow_null=True, read_only=True)
    assignments = CHVAssignmentSerializer(many=True, read_only=True)
    events = CHVCoverageRequestEventSerializer(many=True, read_only=True)
    linked_alert_public_ids = serializers.SerializerMethodField()
    linked_alerts_summary = serializers.SerializerMethodField()
    request_age = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    sla_status = serializers.SerializerMethodField()

    class Meta:
        model = CHVCoverageRequest
        fields = [
            "public_id",
            "ward",
            "ward_name",
            "ward_public_id",
            "requested_by",
            "requested_by_username",
            "status",
            "priority",
            "trigger_source",
            "linked_alert_public_ids",
            "linked_alerts_summary",
            "reason",
            "requested_chv_count",
            "notes",
            "assigned_to_user",
            "assigned_to_username",
            "assigned_to_team",
            "reviewed_by",
            "reviewed_by_username",
            "reviewed_at",
            "review_decision_reason",
            "expected_response_by",
            "resolved_at",
            "request_age",
            "is_overdue",
            "sla_status",
            "created_at",
            "updated_at",
            "assignments",
            "events",
        ]

    def get_linked_alert_public_ids(self, obj: CHVCoverageRequest):
        return [str(link.alert.public_id) for link in obj.linked_alert_links.all() if link.alert_id]

    def get_linked_alerts_summary(self, obj: CHVCoverageRequest):
        alerts = [link.alert for link in obj.linked_alert_links.all() if link.alert_id]
        return CHVCoverageLinkedAlertSerializer(alerts, many=True).data

    def get_request_age(self, obj: CHVCoverageRequest):
        return int((timezone.now() - obj.created_at).total_seconds())

    def get_is_overdue(self, obj: CHVCoverageRequest):
        if not obj.expected_response_by:
            return False
        if obj.status not in {
            CHVCoverageRequest.STATUS_OPEN,
            CHVCoverageRequest.STATUS_APPROVED,
            CHVCoverageRequest.STATUS_IN_PROGRESS,
        }:
            return False
        return obj.expected_response_by < timezone.now()

    def get_sla_status(self, obj: CHVCoverageRequest):
        if obj.status not in {
            CHVCoverageRequest.STATUS_OPEN,
            CHVCoverageRequest.STATUS_APPROVED,
            CHVCoverageRequest.STATUS_IN_PROGRESS,
        }:
            return "NOT_APPLICABLE"
        return "OVERDUE" if self.get_is_overdue(obj) else "ON_TRACK"


class CHVCoverageRequestCreateSerializer(serializers.Serializer):
    ward_id = serializers.IntegerField()
    priority = serializers.ChoiceField(
        choices=[
            CHVCoverageRequest.PRIORITY_LOW,
            CHVCoverageRequest.PRIORITY_MEDIUM,
            CHVCoverageRequest.PRIORITY_HIGH,
        ]
    )
    reason = serializers.CharField()
    requested_chv_count = serializers.IntegerField(min_value=1, max_value=10)
    notes = serializers.CharField(required=False, allow_blank=True)
    linked_alert_public_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )
    trigger_source = serializers.ChoiceField(
        choices=[
            CHVCoverageRequest.TRIGGER_SOURCE_MANUAL,
            CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
        ],
        required=False,
        default=CHVCoverageRequest.TRIGGER_SOURCE_MANUAL,
    )

    def validate(self, attrs):
        linked_alert_public_ids = attrs.get("linked_alert_public_ids", [])
        normalized_linked_alert_public_ids = list(dict.fromkeys(linked_alert_public_ids))
        attrs["linked_alert_public_ids"] = normalized_linked_alert_public_ids

        if attrs["trigger_source"] == CHVCoverageRequest.TRIGGER_SOURCE_MANUAL:
            if normalized_linked_alert_public_ids:
                raise serializers.ValidationError(
                    {"linked_alert_public_ids": "Manual coverage requests cannot store linked alerts."}
                )
            return attrs

        if not normalized_linked_alert_public_ids:
            raise serializers.ValidationError(
                {"linked_alert_public_ids": "Alert-driven coverage requests require at least one linked alert."}
            )

        return attrs


class CHVCoverageRequestFromAlertPrefillSerializer(serializers.Serializer):
    alert_public_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )

    def validate(self, attrs):
        attrs["alert_public_ids"] = list(dict.fromkeys(attrs["alert_public_ids"]))
        return attrs


class CHVCoverageRequestCreateDefaultsSerializer(serializers.Serializer):
    ward_id = serializers.IntegerField()
    ward_public_id = serializers.UUIDField()
    ward_name = serializers.CharField()
    trigger_source = serializers.ChoiceField(
        choices=[
            CHVCoverageRequest.TRIGGER_SOURCE_MANUAL,
            CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
        ]
    )
    linked_alert_public_ids = serializers.ListField(child=serializers.UUIDField())
    linked_alerts_summary = CHVCoverageLinkedAlertSerializer(many=True)
    priority = serializers.ChoiceField(
        choices=[
            CHVCoverageRequest.PRIORITY_LOW,
            CHVCoverageRequest.PRIORITY_MEDIUM,
            CHVCoverageRequest.PRIORITY_HIGH,
        ]
    )
    requested_chv_count = serializers.IntegerField()
    reason = serializers.CharField()
    notes = serializers.CharField()


class CHVCoverageRequestFromAlertPrefillResponseSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["CREATE_READY", "EXISTING_LIVE_REQUEST"])
    detail = serializers.CharField()
    create_defaults = CHVCoverageRequestCreateDefaultsSerializer(allow_null=True)
    existing_request = CHVCoverageRequestSerializer(allow_null=True)


class CHVCoverageRequestDecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)


class CHVCoverageRequestAssignSerializer(serializers.Serializer):
    chv_id = serializers.IntegerField()
    start_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class CHVAssignmentDecisionSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True)


class HealthFacilitySerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    sub_county = serializers.CharField(source="ward.sub_county", read_only=True)
    ward_risk_level = serializers.CharField(source="ward.current_risk_level", read_only=True)
    ward_risk_score = serializers.FloatField(source="ward.current_risk_score", read_only=True)
    point = serializers.SerializerMethodField()

    class Meta:
        model = HealthFacility
        fields = [
            "id",
            "public_id",
            "name",
            "facility_code",
            "ward",
            "ward_name",
            "sub_county",
            "facility_type",
            "ownership",
            "level",
            "ward_risk_level",
            "ward_risk_score",
            "is_active",
            "point",
            "contact_phone",
            "updated_at",
        ]

    def get_point(self, obj: HealthFacility):
        if not obj.point:
            return None
        return [obj.point.x, obj.point.y]


class FacilityContactAvailabilitySerializer(serializers.ModelSerializer):
    display_label = serializers.SerializerMethodField()
    phone_last4 = serializers.SerializerMethodField()
    has_phone = serializers.SerializerMethodField()
    has_email = serializers.SerializerMethodField()

    class Meta:
        model = FacilityContact
        fields = [
            "public_id",
            "display_label",
            "role",
            "preferred_channel",
            "is_verified",
            "is_active",
            "source",
            "verified_at",
            "phone_last4",
            "has_phone",
            "has_email",
        ]

    def get_display_label(self, obj: FacilityContact) -> str:
        return obj.name or obj.role or "Facility contact"

    def get_phone_last4(self, obj: FacilityContact) -> str:
        return obj.phone[-4:] if obj.phone else ""

    def get_has_phone(self, obj: FacilityContact) -> bool:
        return bool(obj.phone)

    def get_has_email(self, obj: FacilityContact) -> bool:
        return bool(obj.email)


class RiskScoreSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    model_run_status = serializers.CharField(source="model_run.status", read_only=True)
    model_run_version = serializers.CharField(source="model_run.model_version", read_only=True)
    model_run_promotion_target = serializers.SerializerMethodField()
    model_run_promotion_state = serializers.SerializerMethodField()
    model_run_alert_eligible = serializers.SerializerMethodField()
    model_run_phase_4_promotion_evidence_persisted = serializers.SerializerMethodField()
    model_run_phase_4_promotion_gates_passed = serializers.SerializerMethodField()

    def _model_run_metadata_value(self, obj: RiskScore, key: str, default=None):
        if not obj.model_run:
            return default
        return (obj.model_run.metadata or {}).get(key, default)

    def get_model_run_promotion_target(self, obj: RiskScore):
        return self._model_run_metadata_value(obj, "promotion_target")

    def get_model_run_promotion_state(self, obj: RiskScore):
        return self._model_run_metadata_value(obj, "promotion_state")

    def get_model_run_alert_eligible(self, obj: RiskScore):
        return self._model_run_metadata_value(obj, "alert_eligible")

    def get_model_run_phase_4_promotion_evidence_persisted(self, obj: RiskScore):
        return self._model_run_metadata_value(obj, "phase_4_promotion_evidence_persisted", False)

    def get_model_run_phase_4_promotion_gates_passed(self, obj: RiskScore):
        return self._model_run_metadata_value(obj, "phase_4_promotion_gates_passed", False)

    class Meta:
        model = RiskScore
        fields = [
            "id",
            "ward",
            "ward_name",
            "model_run",
            "model_run_status",
            "model_run_version",
            "model_run_promotion_target",
            "model_run_promotion_state",
            "model_run_alert_eligible",
            "model_run_phase_4_promotion_evidence_persisted",
            "model_run_phase_4_promotion_gates_passed",
            "score",
            "risk_level",
            "rainfall_mm",
            "flood_indicator",
            "predicted_cases",
            "decision_policy",
            "source",
            "model_version",
            "notes",
            "generated_at",
        ]


class IngestionRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionRun
        fields = [
            "id",
            "run_type",
            "status",
            "source_mode",
            "source_kind",
            "source_name",
            "source_priority",
            "requested_wards",
            "source_timestamp",
            "freshness_state",
            "fallback_used",
            "records_seen",
            "records_loaded",
            "records_rejected",
            "operator_note",
            "results",
            "error_message",
            "started_at",
            "completed_at",
        ]


class ETLHeartbeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = ETLHeartbeat
        fields = [
            "id",
            "component",
            "task_name",
            "status",
            "details",
            "recorded_at",
        ]


class FeatureDatasetRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureDatasetRow
        fields = [
            "id",
            "dataset",
            "ward",
            "ward_name_snapshot",
            "month",
            "feature_values",
            "label",
            "created_at",
        ]


class FeatureDatasetSerializer(serializers.ModelSerializer):
    rows = FeatureDatasetRowSerializer(many=True, read_only=True)

    class Meta:
        model = FeatureDataset
        fields = [
            "id",
            "dataset_ref",
            "dataset_kind",
            "schema_version",
            "source_kind",
            "month",
            "feature_keys",
            "row_count",
            "lineage_metadata",
            "created_at",
            "rows",
        ]


class ModelRunSerializer(serializers.ModelSerializer):
    rainfall_ingestion_run_status = serializers.CharField(source="rainfall_ingestion_run.status", read_only=True)
    training_feature_dataset_ref = serializers.CharField(source="training_feature_dataset.dataset_ref", read_only=True)
    inference_feature_dataset_ref = serializers.CharField(source="inference_feature_dataset.dataset_ref", read_only=True)
    execution_context = serializers.SerializerMethodField()
    run_purpose = serializers.SerializerMethodField()
    promotion_target = serializers.SerializerMethodField()
    retraining_policy = serializers.SerializerMethodField()
    alert_eligible = serializers.SerializerMethodField()

    def _metadata_value(self, obj: ModelRun, key: str, default=None):
        return (obj.metadata or {}).get(key, default)

    def get_execution_context(self, obj: ModelRun):
        return self._metadata_value(obj, "execution_context")

    def get_run_purpose(self, obj: ModelRun):
        return self._metadata_value(obj, "run_purpose")

    def get_promotion_target(self, obj: ModelRun):
        return self._metadata_value(obj, "promotion_target")

    def get_retraining_policy(self, obj: ModelRun):
        return self._metadata_value(obj, "retraining_policy")

    def get_alert_eligible(self, obj: ModelRun):
        return self._metadata_value(obj, "alert_eligible")

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
            "execution_context",
            "run_purpose",
            "promotion_target",
            "retraining_policy",
            "alert_eligible",
            "training_feature_dataset",
            "training_feature_dataset_ref",
            "inference_feature_dataset",
            "inference_feature_dataset_ref",
            "rainfall_ingestion_run",
            "rainfall_ingestion_run_status",
            "started_at",
            "completed_at",
        ]


class ModelAlignmentSerializer(serializers.Serializer):
    current_live_baseline = serializers.DictField()
    current_benchmark_model = serializers.DictField()
    future_candidate_models = serializers.ListField(child=serializers.CharField())
    dashboard_policy = serializers.DictField()


class AlertSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    risk_score = serializers.FloatField(source="risk_score.score", allow_null=True, read_only=True)

    class Meta:
        model = Alert
        fields = [
            "id",
            "public_id",
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


class DashboardNotificationSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    category = serializers.SerializerMethodField()
    group_key = serializers.SerializerMethodField()

    def get_category(self, obj):
        if obj.type == DashboardNotification.TYPE_FEED_STALE:
            return "system_health"
        if obj.type in {DashboardNotification.TYPE_ALERT_FAILED, DashboardNotification.TYPE_ALERT_RETRY_PENDING}:
            return "alert_delivery"
        if obj.type == DashboardNotification.TYPE_WARD_RISK_HIGH:
            return "trigger_review"
        if obj.type == DashboardNotification.TYPE_CHV_COVERAGE_REQUEST_STATUS:
            return "chv_coverage_workflow"
        return "general"

    def get_group_key(self, obj):
        if obj.type == DashboardNotification.TYPE_FEED_STALE:
            return "data_freshness"
        if obj.type == DashboardNotification.TYPE_ALERT_FAILED:
            return "alert_delivery_failures"
        if obj.type == DashboardNotification.TYPE_ALERT_RETRY_PENDING:
            return "alert_delivery_retries"
        if obj.type == DashboardNotification.TYPE_CHV_COVERAGE_REQUEST_STATUS:
            return "chv_coverage_requests"
        return None

    class Meta:
        model = DashboardNotification
        fields = [
            "id",
            "public_id",
            "external_key",
            "type",
            "category",
            "group_key",
            "severity",
            "title",
            "body",
            "source_system",
            "source_object_type",
            "source_object_id",
            "href",
            "state",
            "recipient_scope",
            "recipient_role",
            "recipient_user",
            "ward",
            "ward_name",
            "requires_acknowledgement",
            "dismissible",
            "auto_resolve",
            "pinned_until_actioned",
            "metadata",
            "created_at",
            "seen_at",
            "acknowledged_at",
            "resolved_at",
            "dismissed_at",
            "expires_at",
            "updated_at",
        ]


class DashboardNotificationEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", allow_null=True, read_only=True)

    class Meta:
        model = DashboardNotificationEvent
        fields = [
            "id",
            "notification",
            "actor",
            "actor_username",
            "action",
            "old_state",
            "new_state",
            "metadata",
            "created_at",
        ]


class AlertIntelligenceClassificationSerializer(serializers.Serializer):
    label = serializers.CharField()
    tone = serializers.ChoiceField(choices=["red", "amber", "orange", "blue", "slate"])
    icon_key = serializers.CharField()
    trigger_source = serializers.CharField()
    mode = serializers.CharField()


class AlertIntelligenceRiskContextSerializer(serializers.Serializer):
    level_label = serializers.CharField()
    trend_label = serializers.CharField()
    summary = serializers.CharField()
    recorded_risk_score = serializers.FloatField(allow_null=True)
    threshold = serializers.FloatField(allow_null=True)
    policy_version = serializers.CharField(required=False, allow_null=True)
    alert_decision = serializers.CharField(required=False, allow_null=True)
    reason_codes = serializers.ListField(child=serializers.CharField(), required=False)
    mode = serializers.CharField()


class AlertIntelligenceDeliverySerializer(serializers.Serializer):
    channel_label = serializers.CharField()
    audience_label = serializers.CharField()
    status_label = serializers.CharField()
    status_tone = serializers.ChoiceField(choices=["default", "success", "warning", "danger"])
    recipient_count = serializers.IntegerField()
    attempt_count = serializers.IntegerField(required=False)
    max_attempts = serializers.IntegerField(required=False)
    delivery_backend = serializers.CharField(required=False, allow_blank=True)
    last_attempted_at = serializers.DateTimeField(required=False, allow_null=True)
    next_retry_at = serializers.DateTimeField(required=False, allow_null=True)
    sent_at = serializers.DateTimeField(required=False, allow_null=True)
    mode = serializers.CharField()


class AlertIntelligenceStateItemSerializer(serializers.Serializer):
    label = serializers.CharField()
    tone = serializers.ChoiceField(choices=["success", "warning", "neutral"])


class AlertIntelligenceFreshnessSerializer(serializers.Serializer):
    updated_at = serializers.DateTimeField(allow_null=True)
    is_stale = serializers.BooleanField()
    stale_threshold_minutes = serializers.IntegerField()
    mode = serializers.CharField()


class AlertIntelligenceTimelineEntrySerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    timestamp = serializers.DateTimeField(allow_null=True)
    tone = serializers.ChoiceField(choices=["primary", "progress", "success", "danger", "warning", "neutral"])
    category = serializers.ChoiceField(choices=["all", "system", "communication", "field_activity", "escalation", "resolution"])
    meta = serializers.CharField(allow_null=True, allow_blank=True)
    actor = serializers.CharField(required=False, allow_blank=True)
    event_type = serializers.CharField(required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)
    details = serializers.ListField(child=serializers.CharField(), required=False)


class AlertIntelligenceCapabilitiesSerializer(serializers.Serializer):
    can_resend = serializers.BooleanField()
    can_recall = serializers.BooleanField()
    can_notify_facilities = serializers.BooleanField()
    can_send_follow_up = serializers.BooleanField()
    can_dispatch_additional_chvs = serializers.BooleanField(required=False)
    can_close_alert = serializers.BooleanField(required=False)
    mode = serializers.CharField()


class AlertIntelligenceLifecycleSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["active", "monitoring", "escalated", "resolved"])
    status_label = serializers.CharField()
    summary = serializers.CharField()
    last_updated_at = serializers.DateTimeField(allow_null=True)
    mode = serializers.CharField()


class AlertIntelligenceResponseSummarySerializer(serializers.Serializer):
    status_label = serializers.CharField()
    coverage_label = serializers.CharField()
    summary = serializers.CharField()
    response_count = serializers.IntegerField()
    mode = serializers.CharField()


class AlertIntelligenceRecommendedActionSerializer(serializers.Serializer):
    label = serializers.CharField()
    detail = serializers.CharField()
    blocked = serializers.BooleanField()
    blocked_reason = serializers.CharField(allow_blank=True)
    mode = serializers.CharField()


class AlertIntelligenceMessageSourceSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["backend_generated", "operator_edited", "unavailable"])
    label = serializers.CharField()
    summary = serializers.CharField()
    trigger_type = serializers.CharField(allow_blank=True)
    preview_text = serializers.CharField(allow_blank=True)


class AlertIntelligenceSerializer(serializers.Serializer):
    alert = AlertSerializer()
    ward_detail = WardDetailSerializer(allow_null=True)
    classification = AlertIntelligenceClassificationSerializer()
    risk_context = AlertIntelligenceRiskContextSerializer()
    lifecycle = AlertIntelligenceLifecycleSerializer()
    delivery = AlertIntelligenceDeliverySerializer()
    delivery_summary = AlertIntelligenceDeliverySerializer()
    message_source = AlertIntelligenceMessageSourceSerializer()
    chv_response_summary = AlertIntelligenceResponseSummarySerializer()
    facility_response_summary = AlertIntelligenceResponseSummarySerializer()
    recommended_next_action = AlertIntelligenceRecommendedActionSerializer()
    last_updated_at = serializers.DateTimeField(allow_null=True)
    current_state = AlertIntelligenceStateItemSerializer(many=True)
    freshness = AlertIntelligenceFreshnessSerializer()
    timeline = AlertIntelligenceTimelineEntrySerializer(many=True)
    capabilities = AlertIntelligenceCapabilitiesSerializer()


class FacilityIntelligenceReadinessSerializer(serializers.Serializer):
    facility_type_label = serializers.CharField()
    surge_risk = serializers.ChoiceField(choices=["EXTREME", "MODERATE", "LOW"])
    surge_risk_label = serializers.CharField()
    status_banner_label = serializers.CharField()
    projected_cases = serializers.IntegerField()
    predicted_cases_per_day = serializers.IntegerField()
    ors_estimate_percent = serializers.IntegerField()
    ors_state = serializers.ChoiceField(choices=["CRITICAL", "STABLE", "READY"])
    staffing_filled = serializers.IntegerField()
    staffing_required = serializers.IntegerField()
    staffing_percent = serializers.IntegerField()
    staffing_state = serializers.ChoiceField(choices=["LIMITED", "OPTIMAL"])
    last_reported_at = serializers.DateTimeField(allow_null=True)
    freshness_state = serializers.ChoiceField(choices=["FRESH", "WARNING", "STALE"])
    mode = serializers.CharField()
    backing_source = serializers.CharField()
    dashboard_truth_state = serializers.CharField()


class FacilityIntelligenceContextSerializer(serializers.Serializer):
    summary = serializers.CharField()
    ward_risk_score = serializers.FloatField(allow_null=True)
    ward_alert_count = serializers.IntegerField()
    map_mode = serializers.CharField()
    driving_ward_ids = serializers.ListField(child=serializers.IntegerField())
    action_reasoning = serializers.ListField(child=serializers.CharField())


class FacilityIntelligenceFreshnessSerializer(serializers.Serializer):
    updated_at = serializers.DateTimeField(allow_null=True)
    is_stale = serializers.BooleanField()
    stale_threshold_minutes = serializers.IntegerField()
    mode = serializers.CharField()


class FacilityIntelligenceTimelineEntrySerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    timestamp = serializers.DateTimeField(allow_null=True)
    tone = serializers.ChoiceField(choices=["success", "warning", "danger", "info"])
    category = serializers.ChoiceField(choices=["system", "alert"])
    meta = serializers.CharField(allow_null=True, allow_blank=True)
    details = serializers.ListField(child=serializers.CharField(), required=False)


class FacilityLinkedAlertNavigationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    public_id = serializers.UUIDField()
    ward_id = serializers.IntegerField()
    ward_name = serializers.CharField()
    status = serializers.CharField()
    channel = serializers.CharField()
    recipient = serializers.CharField()
    risk_score = serializers.FloatField(allow_null=True)
    created_at = serializers.DateTimeField()
    sent_at = serializers.DateTimeField(allow_null=True)
    api_url = serializers.CharField()
    intelligence_api_url = serializers.CharField()
    dashboard_url = serializers.CharField()
    filtered_alerts_url = serializers.CharField()


class FacilityChvOperationsNavigationSerializer(serializers.Serializer):
    available = serializers.BooleanField()
    ward_id = serializers.IntegerField()
    ward_name = serializers.CharField()
    active_chv_count = serializers.IntegerField()
    total_chv_count = serializers.IntegerField()
    api_url = serializers.CharField()
    dashboard_url = serializers.CharField()
    mode = serializers.CharField()
    message = serializers.CharField()


class FacilityReadinessReviewEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = FacilityReadinessReviewEvent
        fields = [
            "public_id",
            "action",
            "old_status",
            "new_status",
            "detail",
            "metadata",
            "actor",
            "actor_username",
            "created_at",
        ]
        read_only_fields = fields


class FacilityReadinessReviewSummarySerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = FacilityReadinessReview
        fields = [
            "public_id",
            "facility",
            "facility_name",
            "ward",
            "ward_name",
            "status",
            "severity",
            "reason_codes",
            "notes",
            "created_at",
            "updated_at",
            "acknowledged_at",
            "resolved_at",
            "dismissed_at",
        ]
        read_only_fields = fields


class FacilityReadinessUpdateRequestSummarySerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    contact_display_label = serializers.SerializerMethodField()
    requested_by_username = serializers.CharField(source="requested_by.username", read_only=True)

    class Meta:
        model = FacilityReadinessUpdateRequest
        fields = [
            "public_id",
            "review",
            "facility",
            "facility_name",
            "contact",
            "contact_display_label",
            "requested_by",
            "requested_by_username",
            "channel",
            "status",
            "requested_at",
            "sent_at",
            "acknowledged_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_contact_display_label(self, obj: FacilityReadinessUpdateRequest) -> str:
        return obj.contact.name or obj.contact.role or "Facility contact"


class FacilityReadinessUpdateRequestSerializer(FacilityReadinessUpdateRequestSummarySerializer):
    class Meta(FacilityReadinessUpdateRequestSummarySerializer.Meta):
        fields = FacilityReadinessUpdateRequestSummarySerializer.Meta.fields + [
            "message_body",
            "provider_reference",
            "failure_reason",
        ]
        read_only_fields = fields


class FacilityReadinessEscalationSummarySerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    acknowledged_by_username = serializers.CharField(source="acknowledged_by.username", read_only=True)
    assigned_to_username = serializers.CharField(source="assigned_to.username", read_only=True)

    class Meta:
        model = FacilityReadinessEscalation
        fields = [
            "public_id",
            "review",
            "facility",
            "facility_name",
            "ward",
            "ward_name",
            "status",
            "severity",
            "reason",
            "created_by",
            "created_by_username",
            "acknowledged_by",
            "acknowledged_by_username",
            "assigned_to",
            "assigned_to_username",
            "notes",
            "created_at",
            "updated_at",
            "acknowledged_at",
            "resolved_at",
            "dismissed_at",
        ]
        read_only_fields = fields


class FacilityReadinessEscalationSerializer(FacilityReadinessEscalationSummarySerializer):
    class Meta(FacilityReadinessEscalationSummarySerializer.Meta):
        fields = FacilityReadinessEscalationSummarySerializer.Meta.fields
        read_only_fields = fields


class FacilityReadinessReviewSerializer(FacilityReadinessReviewSummarySerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    assigned_to_username = serializers.CharField(source="assigned_to.username", read_only=True)
    events = FacilityReadinessReviewEventSerializer(many=True, read_only=True)
    update_requests = FacilityReadinessUpdateRequestSummarySerializer(many=True, read_only=True)
    escalations = FacilityReadinessEscalationSummarySerializer(many=True, read_only=True)

    class Meta(FacilityReadinessReviewSummarySerializer.Meta):
        fields = FacilityReadinessReviewSummarySerializer.Meta.fields + [
            "decision_summary_snapshot",
            "created_by",
            "created_by_username",
            "assigned_to",
            "assigned_to_username",
            "events",
            "update_requests",
            "escalations",
        ]
        read_only_fields = fields


class FacilityReadinessReviewCreateSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class FacilityReadinessReviewStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            FacilityReadinessReview.STATUS_ACKNOWLEDGED,
            FacilityReadinessReview.STATUS_RESOLVED,
            FacilityReadinessReview.STATUS_DISMISSED,
        ]
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class FacilityReadinessReviewAcknowledgeSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class FacilityReadinessUpdateRequestCreateSerializer(serializers.Serializer):
    message_body = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    channel = serializers.ChoiceField(
        choices=[
            FacilityReadinessUpdateRequest.CHANNEL_SMS,
            FacilityReadinessUpdateRequest.CHANNEL_EMAIL,
            FacilityReadinessUpdateRequest.CHANNEL_SYSTEM,
        ],
        required=False,
    )


class FacilityReadinessEscalationCreateSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    severity = serializers.ChoiceField(
        choices=[
            FacilityReadinessEscalation.SEVERITY_LOW,
            FacilityReadinessEscalation.SEVERITY_MEDIUM,
            FacilityReadinessEscalation.SEVERITY_HIGH,
        ],
        required=False,
    )
    assigned_to = serializers.IntegerField(required=False, allow_null=True)


class FacilityReadinessEscalationStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            FacilityReadinessEscalation.STATUS_ACKNOWLEDGED,
            FacilityReadinessEscalation.STATUS_RESOLVED,
            FacilityReadinessEscalation.STATUS_DISMISSED,
        ]
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    assigned_to = serializers.IntegerField(required=False, allow_null=True)


class FacilityIntelligenceCapabilitiesSerializer(serializers.Serializer):
    can_view_contacts = serializers.BooleanField()
    can_open_readiness_review = serializers.BooleanField()
    can_request_facility_update = serializers.BooleanField()
    can_escalate_county_review = serializers.BooleanField()
    can_open_linked_alert = serializers.BooleanField()
    can_open_chv_operations = serializers.BooleanField()
    can_acknowledge_review = serializers.BooleanField()
    has_verified_contact = serializers.BooleanField()
    has_active_review = serializers.BooleanField()
    has_active_update_request = serializers.BooleanField()
    has_active_escalation = serializers.BooleanField()
    has_county_review_queue = serializers.BooleanField()
    mode = serializers.CharField()


class FacilityIntelligenceForecastingSerializer(serializers.Serializer):
    source_kind = serializers.CharField()
    governance_mode = serializers.CharField()
    model_version = serializers.CharField(allow_null=True)
    forecast_mode = serializers.CharField()
    projected_pressure_score = serializers.IntegerField()
    projected_readiness_state = serializers.CharField()
    driving_ward_ids = serializers.ListField(child=serializers.IntegerField())
    dashboard_truth_state = serializers.CharField()
    population_exposure = serializers.DictField(required=False)


class FacilityReadinessDecisionSummaryPrioritySerializer(serializers.Serializer):
    facility_id = serializers.IntegerField()
    facility_name = serializers.CharField()
    ward_id = serializers.IntegerField()
    ward_name = serializers.CharField()
    priority_rank = serializers.IntegerField()
    priority_label = serializers.CharField()
    reason_codes = serializers.ListField(
        child=serializers.ChoiceField(
            choices=[
                "HIGH_READINESS_DIFFERENCE",
                "MODERATE_READINESS_DIFFERENCE",
                "ELEVATED_WARD_RISK",
                "STALE_INPUTS",
                "MULTIPLE_ALERTS_IN_WARD",
                "FORECAST_PRESSURE_ELEVATED",
                "CALM_VISIBLE_SCOPE",
                "WEAK_PROXY_INPUTS",
            ]
        )
    )
    reason_text = serializers.CharField()
    review_href = serializers.CharField(allow_null=True, allow_blank=True)


class FacilityReadinessDecisionSummaryRelatedSurfacesSerializer(serializers.Serializer):
    has_linked_alerts = serializers.BooleanField()
    linked_alert_count = serializers.IntegerField()


class FacilityReadinessDecisionSummarySerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=["CALM", "REVIEW", "DEGRADED_CONFIDENCE"])
    headline = serializers.CharField()
    body = serializers.CharField()
    confidence = serializers.ChoiceField(choices=["NORMAL", "DEGRADED"])
    confidence_reason = serializers.ChoiceField(
        choices=["stale_inputs", "weak_proxy_inputs", "stale_and_weak_proxy_inputs"],
        allow_null=True,
        required=False,
    )
    total_review_facility_count = serializers.IntegerField()
    top_priorities = FacilityReadinessDecisionSummaryPrioritySerializer(many=True)
    related_surfaces = FacilityReadinessDecisionSummaryRelatedSurfacesSerializer()


class FacilityIntelligenceSerializer(serializers.Serializer):
    facility = HealthFacilitySerializer()
    contact = FacilityContactAvailabilitySerializer(allow_null=True)
    active_review = FacilityReadinessReviewSummarySerializer(allow_null=True)
    active_update_request = FacilityReadinessUpdateRequestSummarySerializer(allow_null=True)
    active_escalation = FacilityReadinessEscalationSummarySerializer(allow_null=True)
    linked_alerts = FacilityLinkedAlertNavigationSerializer(many=True)
    chv_operations = FacilityChvOperationsNavigationSerializer()
    readiness = FacilityIntelligenceReadinessSerializer()
    context = FacilityIntelligenceContextSerializer()
    forecasting = FacilityIntelligenceForecastingSerializer()
    population_exposure = serializers.DictField(required=False)
    freshness = FacilityIntelligenceFreshnessSerializer()
    decision_summary = FacilityReadinessDecisionSummarySerializer()
    timeline = FacilityIntelligenceTimelineEntrySerializer(many=True)
    capabilities = FacilityIntelligenceCapabilitiesSerializer()


class AlertWorkflowStateSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = AlertWorkflowState
        fields = [
            "id",
            "public_id",
            "ward",
            "ward_name",
            "status",
            "decision_mode",
            "confidence",
            "trigger_severity",
            "alert_delivery_state",
            "alert_delivery_label",
            "risk_level",
            "risk_score",
            "predicted_cases",
            "reason_flagged",
            "trigger_reason",
            "recommended_action",
            "recommended_response",
            "expected_operational_effect",
            "rules_basis",
            "trigger_reason_items",
            "eligible_actions",
            "active_alert_count",
            "delivered_alert_count",
            "retry_pending_alert_count",
            "failed_alert_count",
            "queued_alert_count",
            "triggered_at",
            "latest_risk_update_at",
            "last_manual_request_at",
            "metadata",
            "last_evaluated_at",
            "updated_at",
        ]


class AlertWorkflowEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", allow_null=True, read_only=True)

    class Meta:
        model = AlertWorkflowEvent
        fields = [
            "id",
            "workflow",
            "actor",
            "actor_username",
            "action",
            "old_status",
            "new_status",
            "metadata",
            "created_at",
        ]


class ScenarioSimulationRunSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", allow_null=True, read_only=True)

    class Meta:
        model = ScenarioSimulationRun
        fields = [
            "id",
            "public_id",
            "scenario_id",
            "created_by",
            "created_by_username",
            "input_parameters",
            "summary",
            "ward_results",
            "facility_results",
            "expires_at",
            "created_at",
        ]


class ScenarioSimulationRequestSerializer(serializers.Serializer):
    scenario_id = serializers.ChoiceField(
        choices=[
            ScenarioSimulationRun.SCENARIO_RAINFALL_INCREASE,
            ScenarioSimulationRun.SCENARIO_RESPONSE_DELAY,
        ]
    )
    rainfall_uplift_percent = serializers.IntegerField(required=False, min_value=5, max_value=100)
    response_delay_hours = serializers.IntegerField(required=False, min_value=1, max_value=72)


class FacilityForecastFactorSerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.JSONField()
    source = serializers.CharField()
    mode = serializers.CharField()
    truth_class_counts = serializers.DictField(required=False)
    caveat = serializers.CharField(required=False, allow_blank=True)


class FacilityForecastPreviewSerializer(serializers.Serializer):
    facility_id = serializers.IntegerField()
    generated_at = serializers.DateTimeField()
    horizon_days = serializers.IntegerField()
    projected_case_burden = serializers.IntegerField()
    projected_pressure_score = serializers.IntegerField()
    projected_readiness_state = serializers.ChoiceField(choices=["low", "watch", "capacity_concern"])
    surge_threshold_state = serializers.DictField()
    driving_ward_ids = serializers.ListField(child=serializers.IntegerField())
    forecast_factors = FacilityForecastFactorSerializer(many=True)
    model_version = serializers.CharField(allow_null=True)
    freshness_state = serializers.ChoiceField(choices=["FRESH", "WARNING", "STALE"])
    forecast_mode = serializers.CharField()
    baseline_model_status = serializers.CharField()


class FacilityForecastingStatusSerializer(serializers.Serializer):
    forecasting_state = serializers.CharField()
    current_baseline_model = serializers.CharField(allow_null=True)
    current_baseline_state = serializers.CharField(required=False)
    planned_baseline_model = serializers.CharField()
    truth_sources = serializers.DictField()
    honesty_rules = serializers.DictField()
    contract_definition = serializers.DictField(required=False)
    promotion_summary = serializers.DictField(required=False)


class FacilityForecastPromotionSummarySerializer(serializers.Serializer):
    current_run = serializers.DictField(allow_null=True)
    evaluation = serializers.DictField()
    decision = serializers.DictField()


class WardIntelligenceSerializer(serializers.Serializer):
    ward = WardDetailSerializer()
    current_risk = WardIntelligenceCurrentRiskSerializer()
    trend = WardIntelligenceTrendSerializer()
    driver_summary = WardIntelligenceDriverSummarySerializer()
    guidance_summary = WardIntelligenceGuidanceSummarySerializer()
    freshness = WardIntelligenceFreshnessSerializer()
    workflow = WardIntelligenceWorkflowSerializer()
    decision_summary = WardIntelligenceDecisionSummarySerializer()
    header_context = WardIntelligenceHeaderContextSerializer()
    population_exposure = serializers.DictField(required=False)
    surveillance = serializers.DictField(required=False)
    operational_evidence = serializers.DictField(required=False)
    risk_history = RiskScoreSerializer(many=True)
    related_alerts = AlertSerializer(many=True)


class TriggerContextRequestSerializer(serializers.Serializer):
    ward_id = serializers.IntegerField(required=False)
    risk_level = serializers.ChoiceField(
        choices=[Ward.RISK_LOW, Ward.RISK_MEDIUM, Ward.RISK_HIGH],
        required=False,
    )

    def validate(self, attrs):
        if not attrs.get("ward_id") and not attrs.get("risk_level"):
            raise serializers.ValidationError("Provide at least one of ward_id or risk_level.")
        return attrs


class TriggerContextWardSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    county = serializers.CharField()
    sub_county = serializers.CharField()


class TriggerContextRiskSerializer(serializers.Serializer):
    level = serializers.CharField(allow_null=True)
    score = serializers.FloatField(allow_null=True)
    predicted_cases = serializers.IntegerField()
    last_risk_update_at = serializers.DateTimeField(allow_null=True)


class TriggerContextWorkflowSerializer(serializers.Serializer):
    status = serializers.CharField()
    decision_mode = serializers.CharField()
    trigger_reason = serializers.CharField()
    recommended_action = serializers.CharField()
    active_alert_count = serializers.IntegerField()
    alert_delivery_state = serializers.CharField()
    alert_delivery_label = serializers.CharField()


class TriggerContextSystemSerializer(serializers.Serializer):
    why_this_might_need_an_alert = serializers.ListField(child=serializers.CharField())
    what_happens_if_no_action = serializers.CharField()
    trigger_status_label = serializers.CharField()
    recommended_trigger_type = serializers.CharField()
    confidence_label = serializers.CharField()


class TriggerRecipientPreviewSerializer(serializers.Serializer):
    chv_count = serializers.IntegerField()


class TriggerContextResponseSerializer(serializers.Serializer):
    ward = TriggerContextWardSerializer()
    risk = TriggerContextRiskSerializer()
    workflow = TriggerContextWorkflowSerializer()
    system_context = TriggerContextSystemSerializer()
    recipient_preview = TriggerRecipientPreviewSerializer()
    supported_delivery_channels = serializers.ListField(child=serializers.CharField())
    supported_trigger_types = serializers.ListField(child=serializers.CharField())


class TriggerPreviewRequestSerializer(serializers.Serializer):
    ward_id = serializers.IntegerField()
    trigger_type = serializers.ChoiceField(
        choices=[
            "HIGH_RISK_ESCALATION",
            "FOLLOW_UP_REVIEW",
            "DELIVERY_RETRY",
            "CUSTOM",
        ]
    )
    risk_level = serializers.ChoiceField(
        choices=[Ward.RISK_LOW, Ward.RISK_MEDIUM, Ward.RISK_HIGH],
        required=False,
    )
    message_override = serializers.CharField(required=False, allow_blank=True, max_length=320)


class TriggerPreviewResponseSerializer(serializers.Serializer):
    message_preview = serializers.CharField()
    message_mode = serializers.CharField()
    supports_editing = serializers.BooleanField()
    channel_defaults = serializers.ListField(child=serializers.CharField())
    recipient_preview = TriggerRecipientPreviewSerializer()
    recommended_action = serializers.CharField()


class TriggerAlertRequestSerializer(serializers.Serializer):
    ward_id = serializers.IntegerField()
    send_sms = serializers.BooleanField(default=False)
    trigger_type = serializers.ChoiceField(
        choices=[
            "HIGH_RISK_ESCALATION",
            "FOLLOW_UP_REVIEW",
            "DELIVERY_RETRY",
            "CUSTOM",
        ],
        required=False,
    )
    message_override = serializers.CharField(required=False, allow_blank=True, max_length=320)

 
class SystemControlStatusSerializer(serializers.Serializer):
    mode = serializers.CharField()
    can_retry_background_jobs = serializers.BooleanField()
    can_run_manual_risk_scoring = serializers.BooleanField()
    can_pause_alert_delivery = serializers.BooleanField()
    alert_delivery_paused = serializers.BooleanField()
    alert_delivery_paused_until = serializers.DateTimeField(allow_null=True)
    alert_delivery_pause_reason = serializers.CharField(allow_blank=True)
    alert_delivery_pause_updated_at = serializers.DateTimeField(allow_null=True)
    alert_delivery_pause_updated_by = serializers.CharField(allow_null=True)
    ward_risk_decision_policy = serializers.DictField()


class SystemRetryControlsRequestSerializer(serializers.Serializer):
    limit = serializers.IntegerField(required=False, default=25, min_value=1, max_value=100)
    retry_alert_delivery = serializers.BooleanField(default=True)
    retry_failed_sync_payloads = serializers.BooleanField(default=False)


class ManualRiskScoringRequestSerializer(serializers.Serializer):
    month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    model_version = serializers.CharField(required=False, default="lr-v1", max_length=40)
    algorithm = serializers.ChoiceField(
        required=False,
        default="logistic_regression",
        choices=["logistic_regression", "random_forest"],
    )
    trigger_alerts = serializers.BooleanField(default=False)
    send_sms = serializers.BooleanField(default=False)
    dual_model = serializers.BooleanField(default=False)


class AlertDeliveryPauseRequestSerializer(serializers.Serializer):
    paused = serializers.BooleanField()
    duration_minutes = serializers.IntegerField(required=False, default=60, min_value=1, max_value=1440)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class TriggerAlertRequestStatusResponseSerializer(serializers.Serializer):
    request_id = serializers.CharField()
    status = serializers.ChoiceField(choices=["PENDING_CREATION", "MATERIALIZED"])
    alert_id = serializers.IntegerField(allow_null=True)
    ward_id = serializers.IntegerField()
    ward_name = serializers.CharField()
    created_alert_count = serializers.IntegerField()
    sms_alert_count = serializers.IntegerField()
    dashboard_alert_id = serializers.IntegerField(allow_null=True)
    last_materialized_at = serializers.DateTimeField(allow_null=True)


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
