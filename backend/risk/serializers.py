from collections.abc import Mapping

from rest_framework import serializers
from rest_framework.fields import empty
from django.utils import timezone

from .ml.alignment import latest_promoted_riskscore_for_ward
from .chv_offline import (
    OFFLINE_CHV_CONTRACT_VERSION,
    OFFLINE_CHV_UPLOAD_PAYLOAD_VERSION,
    SUPPORTED_PHASE_4_UPLOAD_TYPES,
)
from .models import Alert, AlertWorkflowEvent, AlertWorkflowState, CHV, CHVAssignment, CHVCoverageRequest, CHVCoverageRequestEvent, CHVDeviceRegistration, CHVMessage, ContactPreference, DashboardNotification, DashboardNotificationEvent, ETLHeartbeat, ExternalDataElementMapping, ExternalOrgUnitMapping, ExternalSystem, ExternalValueSetMapping, FacilityContact, FacilityReadinessEscalation, FacilityReadinessReview, FacilityReadinessReviewEvent, FacilityReadinessUpdateRequest, FeatureDataset, FeatureDatasetRow, HealthFacility, IngestionRun, InteroperabilityMappingVersion, InteroperabilityRun, InteroperabilityRunError, InteroperabilityRunItem, MessageTemplate, ModelRun, PreparednessAction, PreparednessActionEvent, RiskScore, ScenarioSimulationRun, SensitiveExportDownloadAudit, SensitiveExportRequest, SyncQueue, TriageSession, UssdMenuVersion, UssdSessionLog, Ward
from .privacy_minimization import (
    PrivacyMinimizationViolation,
    ensure_pii_safe_mapping,
    ensure_pii_safe_text,
)
from .privacy_access import (
    mask_contact_value,
    privacy_context,
    redact_direct_identifiers_in_text,
    redact_field_health_text,
    redact_provider_identifier,
    serializer_user,
    user_can_view_direct_identifiers,
)


class PiiSafeInputSerializerMixin:
    pii_safe_text_fields: tuple[str, ...] = ()
    pii_safe_mapping_fields: tuple[str, ...] = ()

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unsupported_fields = sorted(set(data) - set(self.fields))
            if unsupported_fields:
                raise serializers.ValidationError(
                    {
                        field: [
                            "Unsupported field. This endpoint only accepts the documented minimum data fields."
                        ]
                        for field in unsupported_fields
                    }
                )
        return super().to_internal_value(data)

    def run_validation(self, data=empty):
        value = super().run_validation(data)
        if isinstance(value, dict):
            self._validate_pii_safe_fields(value)
        return value

    def _validate_pii_safe_fields(self, attrs: dict) -> None:
        errors: dict[str, list[str]] = {}
        for field_name in self.pii_safe_text_fields:
            if field_name not in attrs:
                continue
            try:
                ensure_pii_safe_text(attrs.get(field_name, ""), location=field_name)
            except PrivacyMinimizationViolation as exc:
                errors[field_name] = [str(exc)]

        for field_name in self.pii_safe_mapping_fields:
            if field_name not in attrs:
                continue
            try:
                ensure_pii_safe_mapping(attrs.get(field_name) or {}, location=field_name)
            except PrivacyMinimizationViolation as exc:
                errors[field_name] = [str(exc)]

        if errors:
            raise serializers.ValidationError(errors)


def validate_pii_safe_serializer_text(value: str, *, field_name: str) -> str:
    try:
        ensure_pii_safe_text(value, location=field_name)
    except PrivacyMinimizationViolation as exc:
        raise serializers.ValidationError(str(exc)) from exc
    return value


class ContactPreferenceSerializer(serializers.ModelSerializer):
    recorded_by_username = serializers.CharField(source="recorded_by.username", allow_null=True, read_only=True)

    class Meta:
        model = ContactPreference
        fields = [
            "public_id",
            "audience_type",
            "channel",
            "phone_number",
            "contact_reference",
            "consent_status",
            "opt_out_status",
            "source",
            "source_reference",
            "recorded_by",
            "recorded_by_username",
            "recorded_at",
            "expires_at",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "recorded_by", "recorded_by_username", "created_at", "updated_at"]


class ContactPreferenceCreateSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("contact_reference", "source", "source_reference")
    pii_safe_mapping_fields = ("metadata",)

    audience_type = serializers.ChoiceField(choices=ContactPreference.AUDIENCE_CHOICES)
    channel = serializers.ChoiceField(choices=ContactPreference.CHANNEL_CHOICES, default=ContactPreference.CHANNEL_SMS)
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=20)
    contact_reference = serializers.CharField(required=False, allow_blank=True, max_length=180)
    consent_status = serializers.ChoiceField(
        choices=ContactPreference.CONSENT_CHOICES,
        default=ContactPreference.CONSENT_UNKNOWN,
    )
    opt_out_status = serializers.ChoiceField(
        choices=ContactPreference.OPT_OUT_CHOICES,
        default=ContactPreference.OPT_OUT_NOT_OPTED_OUT,
    )
    source = serializers.CharField(max_length=120)
    source_reference = serializers.CharField(required=False, allow_blank=True, max_length=180)
    recorded_at = serializers.DateTimeField(required=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        phone_number = ContactPreference.normalize_phone_number(attrs.get("phone_number", ""))
        contact_reference = attrs.get("contact_reference", "").strip()
        if phone_number and not ContactPreference.is_valid_phone_number(phone_number):
            raise serializers.ValidationError(
                {"phone_number": "Enter a valid Kenyan mobile phone number for SMS contact preferences."}
            )
        if not phone_number and not contact_reference:
            raise serializers.ValidationError(
                {"detail": "A phone number or contact reference is required for a contact preference."}
            )
        recorded_at = attrs.get("recorded_at") or timezone.now()
        expires_at = attrs.get("expires_at")
        if expires_at is not None and expires_at <= recorded_at:
            raise serializers.ValidationError({"expires_at": "Preference expiry must be after the recorded time."})
        attrs["phone_number"] = phone_number
        attrs["contact_reference"] = contact_reference
        attrs["source"] = attrs["source"].strip()
        attrs["source_reference"] = attrs.get("source_reference", "").strip()
        attrs["recorded_at"] = recorded_at
        return attrs


class MessageTemplateSerializer(serializers.ModelSerializer):
    approved_by_username = serializers.CharField(source="approved_by.username", allow_null=True, read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", allow_null=True, read_only=True)

    class Meta:
        model = MessageTemplate
        fields = [
            "public_id",
            "template_key",
            "audience_type",
            "channel",
            "language",
            "version",
            "title",
            "body",
            "placeholders",
            "approval_status",
            "approved_by",
            "approved_by_username",
            "approved_at",
            "retired_at",
            "translation_status",
            "source_template",
            "translation_reviewed_by",
            "translation_reviewed_at",
            "translation_review_notes",
            "owner",
            "risk_level",
            "public_health_caveats",
            "lineage_metadata",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "approved_by_username",
            "created_by_username",
            "created_at",
            "updated_at",
        ]


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
            "preferred_language",
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
    preferred_language = serializers.CharField()
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


class CHVDeviceRegistrationCreateSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_mapping_fields = ("metadata",)

    device_id = serializers.CharField(max_length=120)
    contract_version = serializers.CharField(required=False, allow_blank=True, default=OFFLINE_CHV_CONTRACT_VERSION)
    app_version = serializers.CharField(required=False, allow_blank=True, max_length=64)
    preferred_language = serializers.CharField(required=False, allow_blank=True, max_length=20)
    platform = serializers.ChoiceField(
        choices=[choice[0] for choice in CHVDeviceRegistration.PLATFORM_CHOICES],
        required=False,
        default=CHVDeviceRegistration.PLATFORM_UNKNOWN,
    )
    metadata = serializers.DictField(required=False, default=dict)

    def validate_device_id(self, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("A device_id is required.")
        return normalized


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
            "template",
            "template_key",
            "template_version",
            "requested_language",
            "resolved_language",
            "fallback_used",
            "message_body",
            "governance_metadata",
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


class CHVMessageCreateSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("message_body", "override_reason")
    pii_safe_mapping_fields = ("template_context",)

    message_body = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    channel = serializers.ChoiceField(choices=[CHVMessage.CHANNEL_SMS], default=CHVMessage.CHANNEL_SMS)
    template_key = serializers.CharField(required=False, allow_blank=True, max_length=120)
    template_version = serializers.IntegerField(required=False, min_value=1, allow_null=True)
    template_language = serializers.CharField(required=False, allow_blank=True, max_length=20)
    template_context = serializers.JSONField(required=False, default=dict)
    emergency_override = serializers.BooleanField(required=False, default=False)
    override_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate(self, attrs):
        message_body = attrs.get("message_body", "").strip()
        template_key = attrs.get("template_key", "").strip()
        if not message_body and not template_key:
            raise serializers.ValidationError({"message_body": "A message body or template key is required."})
        attrs["message_body"] = message_body
        attrs["template_key"] = template_key
        attrs["template_language"] = attrs.get("template_language", "").strip().lower()
        if attrs.get("emergency_override") and not attrs.get("override_reason", "").strip():
            raise serializers.ValidationError({"override_reason": "Emergency override requires a reason."})
        return attrs


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
    chv_phone_number = serializers.SerializerMethodField()
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

    def get_chv_phone_number(self, obj: CHVAssignment) -> str:
        user = serializer_user(self)
        if user_can_view_direct_identifiers(user):
            return obj.chv.phone_number
        return mask_contact_value(obj.chv.phone_number)


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
    assignments = serializers.SerializerMethodField()
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

    def get_assignments(self, obj: CHVCoverageRequest):
        return CHVAssignmentSerializer(obj.assignments.all(), many=True, context=self.context).data

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


class CHVCoverageRequestCreateSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("reason", "notes")

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


class CHVCoverageRequestDecisionSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("reason",)

    reason = serializers.CharField(required=False, allow_blank=True)


class CHVCoverageRequestAssignSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("notes",)

    chv_id = serializers.IntegerField()
    start_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class CHVAssignmentDecisionSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("notes",)

    notes = serializers.CharField(required=False, allow_blank=True)


class HealthFacilitySerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    sub_county = serializers.CharField(source="ward.sub_county", read_only=True)
    ward_risk_level = serializers.CharField(source="ward.current_risk_level", read_only=True)
    ward_risk_score = serializers.FloatField(source="ward.current_risk_score", read_only=True)
    point = serializers.SerializerMethodField()
    contact_phone = serializers.SerializerMethodField()

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

    def get_contact_phone(self, obj: HealthFacility) -> str:
        user = serializer_user(self)
        if user_can_view_direct_identifiers(user):
            return obj.contact_phone
        return mask_contact_value(obj.contact_phone)


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


class ModelOperationsHealthSerializer(serializers.Serializer):
    schema_version = serializers.CharField()
    generated_at = serializers.DateTimeField()
    summary = serializers.DictField()
    active_model = serializers.DictField(allow_null=True)
    monitoring = serializers.DictField()
    challenger_comparison = serializers.DictField()
    rollback_history = serializers.ListField(child=serializers.DictField())
    model_states = serializers.ListField(child=serializers.DictField())
    dashboard_policy = serializers.DictField()


class AlertSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    risk_score = serializers.FloatField(source="risk_score.score", allow_null=True, read_only=True)
    recipient = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()
    external_id = serializers.SerializerMethodField()
    error_message = serializers.SerializerMethodField()
    privacy_context = serializers.SerializerMethodField()

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
            "template",
            "template_key",
            "template_version",
            "requested_language",
            "resolved_language",
            "fallback_used",
            "message",
            "governance_metadata",
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
            "privacy_context",
        ]

    def _can_view_direct_identifiers(self) -> bool:
        user = serializer_user(self)
        return user_can_view_direct_identifiers(user)

    def get_recipient(self, obj: Alert) -> str:
        if self._can_view_direct_identifiers():
            return obj.recipient
        return mask_contact_value(obj.recipient)

    def get_message(self, obj: Alert) -> str:
        return redact_direct_identifiers_in_text(
            obj.message,
            can_view=self._can_view_direct_identifiers(),
        )

    def get_external_id(self, obj: Alert) -> str:
        return redact_provider_identifier(
            obj.external_id,
            can_view=self._can_view_direct_identifiers(),
        )

    def get_error_message(self, obj: Alert) -> str:
        return redact_direct_identifiers_in_text(
            obj.error_message,
            can_view=self._can_view_direct_identifiers(),
        )

    def get_privacy_context(self, obj: Alert) -> dict:
        redacted = not self._can_view_direct_identifiers()
        return privacy_context(
            classification="sensitive_contact_data",
            redacted=redacted,
            reason="Alert delivery recipients, provider identifiers, and embedded contact values are masked for analyst views.",
        )


class SensitiveExportRequestCreateSerializer(serializers.Serializer):
    export_type = serializers.ChoiceField(choices=SensitiveExportRequest.EXPORT_TYPE_CHOICES)
    purpose = serializers.CharField(min_length=12, max_length=1000)
    filters = serializers.DictField(required=False)

    def validate_purpose(self, value: str) -> str:
        return validate_pii_safe_serializer_text(value.strip(), field_name="purpose")


class SensitiveExportDecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate_reason(self, value: str) -> str:
        if not value:
            return value
        return validate_pii_safe_serializer_text(value.strip(), field_name="reason")


class SensitiveExportRequestSerializer(serializers.ModelSerializer):
    requester_username = serializers.CharField(source="requester.username", read_only=True)
    approved_by_username = serializers.CharField(source="approved_by.username", read_only=True, allow_null=True)
    rejected_by_username = serializers.CharField(source="rejected_by.username", read_only=True, allow_null=True)
    download_audit_count = serializers.SerializerMethodField()
    has_payload = serializers.SerializerMethodField()

    class Meta:
        model = SensitiveExportRequest
        fields = [
            "public_id",
            "export_type",
            "requester",
            "requester_username",
            "purpose",
            "filters",
            "sensitive_fields_included",
            "approval_state",
            "requires_approval",
            "generated_at",
            "expires_at",
            "approved_by",
            "approved_by_username",
            "approved_at",
            "rejected_by",
            "rejected_by_username",
            "rejected_at",
            "rejection_reason",
            "generated_filename",
            "generated_content_type",
            "payload_sha256",
            "row_count",
            "download_count",
            "download_audit_count",
            "last_downloaded_at",
            "has_payload",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_has_payload(self, obj: SensitiveExportRequest) -> bool:
        return bool(obj.generated_payload)

    def get_download_audit_count(self, obj: SensitiveExportRequest) -> int:
        return obj.download_audits.count()


class SensitiveExportDownloadAuditSerializer(serializers.ModelSerializer):
    downloader_username = serializers.CharField(source="downloader.username", read_only=True, allow_null=True)

    class Meta:
        model = SensitiveExportDownloadAudit
        fields = [
            "public_id",
            "export_request",
            "downloader",
            "downloader_username",
            "outcome",
            "reason",
            "request_metadata",
            "downloaded_at",
        ]
        read_only_fields = fields


class ExternalSystemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalSystem
        fields = [
            "public_id",
            "system_key",
            "display_name",
            "system_type",
            "owner",
            "default_exchange_format",
            "auth_config_reference",
            "api_base_url",
            "status",
            "lineage_metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class InteroperabilityMappingVersionSerializer(serializers.ModelSerializer):
    system_key = serializers.CharField(source="system.system_key", read_only=True)
    reviewed_by_username = serializers.CharField(source="reviewed_by.username", read_only=True, allow_null=True)

    class Meta:
        model = InteroperabilityMappingVersion
        fields = [
            "public_id",
            "system",
            "system_key",
            "version_label",
            "status",
            "effective_date",
            "retired_at",
            "reviewed_by",
            "reviewed_by_username",
            "lineage_metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ExternalOrgUnitMappingSerializer(serializers.ModelSerializer):
    system_key = serializers.CharField(source="system.system_key", read_only=True)
    mapping_version_label = serializers.CharField(source="mapping_version.version_label", read_only=True)
    ward_name = serializers.CharField(source="ward.name", read_only=True, allow_null=True)
    facility_name = serializers.CharField(source="facility.name", read_only=True, allow_null=True)
    reviewed_by_username = serializers.CharField(source="reviewed_by.username", read_only=True, allow_null=True)

    class Meta:
        model = ExternalOrgUnitMapping
        fields = [
            "public_id",
            "system",
            "system_key",
            "mapping_version",
            "mapping_version_label",
            "external_identifier",
            "external_display_name",
            "internal_object_type",
            "internal_object_public_id",
            "internal_object_code",
            "ward",
            "ward_name",
            "facility",
            "facility_name",
            "mapping_confidence",
            "status",
            "effective_date",
            "retired_date",
            "reviewed_by",
            "reviewed_by_username",
            "lineage_metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ExternalDataElementMappingSerializer(serializers.ModelSerializer):
    system_key = serializers.CharField(source="system.system_key", read_only=True)
    mapping_version_label = serializers.CharField(source="mapping_version.version_label", read_only=True)
    reviewed_by_username = serializers.CharField(source="reviewed_by.username", read_only=True, allow_null=True)

    class Meta:
        model = ExternalDataElementMapping
        fields = [
            "public_id",
            "system",
            "system_key",
            "mapping_version",
            "mapping_version_label",
            "exchange_type",
            "external_identifier",
            "external_display_name",
            "internal_field",
            "value_type",
            "required_for_exchange",
            "mapping_confidence",
            "status",
            "effective_date",
            "retired_date",
            "reviewed_by",
            "reviewed_by_username",
            "lineage_metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ExternalValueSetMappingSerializer(serializers.ModelSerializer):
    system_key = serializers.CharField(source="system.system_key", read_only=True)
    mapping_version_label = serializers.CharField(source="mapping_version.version_label", read_only=True)
    reviewed_by_username = serializers.CharField(source="reviewed_by.username", read_only=True, allow_null=True)

    class Meta:
        model = ExternalValueSetMapping
        fields = [
            "public_id",
            "system",
            "system_key",
            "mapping_version",
            "mapping_version_label",
            "value_set_key",
            "external_value",
            "external_label",
            "internal_value",
            "internal_label",
            "mapping_confidence",
            "status",
            "effective_date",
            "retired_date",
            "reviewed_by",
            "reviewed_by_username",
            "lineage_metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class InteroperabilityRunItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteroperabilityRunItem
        fields = [
            "id",
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
        ]
        read_only_fields = fields


class InteroperabilityRunErrorSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(read_only=True, allow_null=True)
    item_row_number = serializers.IntegerField(source="item.row_number", read_only=True, allow_null=True)
    item_external_identifier = serializers.CharField(source="item.external_identifier", read_only=True, allow_null=True)

    class Meta:
        model = InteroperabilityRunError
        fields = [
            "public_id",
            "item",
            "item_id",
            "item_row_number",
            "item_external_identifier",
            "severity",
            "error_code",
            "field_path",
            "safe_message",
            "remediation_hint",
            "created_at",
        ]
        read_only_fields = fields


class InteroperabilityRunSerializer(serializers.ModelSerializer):
    system_key = serializers.CharField(source="system.system_key", read_only=True)
    system_name = serializers.CharField(source="system.display_name", read_only=True)
    mapping_version = serializers.CharField(source="mapping_version.version_label", read_only=True, allow_null=True)
    mapping_version_label = serializers.CharField(source="mapping_version.version_label", read_only=True, allow_null=True)
    retry_of = serializers.UUIDField(source="retry_of.public_id", read_only=True, allow_null=True)
    retry_of_public_id = serializers.UUIDField(source="retry_of.public_id", read_only=True, allow_null=True)
    operator_username = serializers.CharField(source="operator.username", read_only=True, allow_null=True)
    source_reference = serializers.SerializerMethodField()
    contract_errors = serializers.SerializerMethodField()
    items = InteroperabilityRunItemSerializer(many=True, read_only=True)
    errors = InteroperabilityRunErrorSerializer(many=True, read_only=True)

    def get_source_reference(self, obj):
        from .interoperability import interoperability_run_source_reference

        return interoperability_run_source_reference(obj)

    def get_contract_errors(self, obj):
        from .interoperability import validate_interoperability_run_record_contract

        return validate_interoperability_run_record_contract(obj)

    class Meta:
        model = InteroperabilityRun
        fields = [
            "public_id",
            "direction",
            "exchange_type",
            "system",
            "system_key",
            "system_name",
            "mapping_version",
            "mapping_version_label",
            "retry_of",
            "retry_of_public_id",
            "status",
            "dry_run",
            "source_file_name",
            "endpoint_url",
            "source_reference",
            "records_seen",
            "records_accepted",
            "records_rejected",
            "mapping_coverage",
            "operator",
            "operator_username",
            "error_summary",
            "dry_run_preview",
            "export_payload",
            "connector_config",
            "lineage_metadata",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
            "contract_errors",
            "items",
            "errors",
        ]
        read_only_fields = fields


class InteroperabilityOrgUnitMappingImportSerializer(serializers.Serializer):
    system_key = serializers.CharField(required=False, allow_blank=True, default="dhis2", max_length=80)
    mapping_version_label = serializers.CharField(required=False, allow_blank=True, max_length=120)
    source_file_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    csv_text = serializers.CharField()
    confirm = serializers.BooleanField(required=False, default=False)
    retry_of_public_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs.get("csv_text", "").strip():
            raise serializers.ValidationError({"csv_text": "CSV content is required for an interoperability dry-run."})
        attrs["system_key"] = attrs.get("system_key", "").strip() or "dhis2"
        attrs["mapping_version_label"] = attrs.get("mapping_version_label", "").strip()
        attrs["source_file_name"] = attrs.get("source_file_name", "").strip() or "org-unit-mapping.csv"
        return attrs


class InteroperabilityExportPreviewSerializer(serializers.Serializer):
    system_key = serializers.CharField(required=False, allow_blank=True, default="dhis2", max_length=80)
    mapping_version_label = serializers.CharField(required=False, allow_blank=True, max_length=120)

    def validate(self, attrs):
        attrs["system_key"] = attrs.get("system_key", "").strip() or "dhis2"
        attrs["mapping_version_label"] = attrs.get("mapping_version_label", "").strip()
        return attrs


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
        if obj.type == DashboardNotification.TYPE_OPERATIONAL_KPI_THRESHOLD:
            return "operational_kpi_threshold"
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
        if obj.type == DashboardNotification.TYPE_OPERATIONAL_KPI_THRESHOLD:
            return "operational_kpi_thresholds"
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
    climate_evidence = serializers.DictField(required=False)
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
            "template",
            "template_key",
            "template_version",
            "status",
            "governance_metadata",
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


class FacilityReadinessReviewCreateSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("notes",)

    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class FacilityReadinessReviewStatusSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("notes",)

    status = serializers.ChoiceField(
        choices=[
            FacilityReadinessReview.STATUS_ACKNOWLEDGED,
            FacilityReadinessReview.STATUS_RESOLVED,
            FacilityReadinessReview.STATUS_DISMISSED,
        ]
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class FacilityReadinessReviewAcknowledgeSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("notes",)

    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class FacilityReadinessUpdateRequestCreateSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("message_body", "override_reason")
    pii_safe_mapping_fields = ("template_context",)

    message_body = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    channel = serializers.ChoiceField(
        choices=[
            FacilityReadinessUpdateRequest.CHANNEL_SMS,
            FacilityReadinessUpdateRequest.CHANNEL_EMAIL,
            FacilityReadinessUpdateRequest.CHANNEL_SYSTEM,
        ],
        required=False,
    )
    template_key = serializers.CharField(required=False, allow_blank=True, max_length=120)
    template_version = serializers.IntegerField(required=False, min_value=1, allow_null=True)
    template_language = serializers.CharField(required=False, allow_blank=True, max_length=20)
    template_context = serializers.JSONField(required=False, default=dict)
    emergency_override = serializers.BooleanField(required=False, default=False)
    override_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate(self, attrs):
        attrs["message_body"] = attrs.get("message_body", "").strip()
        attrs["template_key"] = attrs.get("template_key", "").strip()
        attrs["template_language"] = attrs.get("template_language", "").strip().lower() or "en"
        if attrs.get("emergency_override") and not attrs.get("override_reason", "").strip():
            raise serializers.ValidationError({"override_reason": "Emergency override requires a reason."})
        return attrs


class FacilityReadinessEscalationCreateSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("reason",)

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


class FacilityReadinessEscalationStatusSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("notes",)

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


class PreparednessActionEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", allow_null=True, read_only=True)

    class Meta:
        model = PreparednessActionEvent
        fields = [
            "public_id",
            "event_type",
            "actor",
            "actor_username",
            "old_status",
            "new_status",
            "detail",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


class PreparednessActionSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    ward_public_id = serializers.UUIDField(source="ward.public_id", read_only=True)
    facility_name = serializers.CharField(source="facility.name", allow_null=True, read_only=True)
    chv_name = serializers.CharField(source="chv.name", allow_null=True, read_only=True)
    alert_public_id = serializers.UUIDField(source="alert.public_id", allow_null=True, read_only=True)
    alert_workflow_public_id = serializers.UUIDField(source="alert_workflow.public_id", allow_null=True, read_only=True)
    model_run_version = serializers.CharField(source="model_run.model_version", allow_null=True, read_only=True)
    facility_readiness_review_public_id = serializers.UUIDField(
        source="facility_readiness_review.public_id",
        allow_null=True,
        read_only=True,
    )
    facility_update_request_public_id = serializers.UUIDField(
        source="facility_update_request.public_id",
        allow_null=True,
        read_only=True,
    )
    facility_escalation_public_id = serializers.UUIDField(
        source="facility_escalation.public_id",
        allow_null=True,
        read_only=True,
    )
    chv_coverage_request_public_id = serializers.UUIDField(
        source="chv_coverage_request.public_id",
        allow_null=True,
        read_only=True,
    )
    created_by_username = serializers.CharField(source="created_by.username", allow_null=True, read_only=True)
    assigned_to_username = serializers.CharField(source="assigned_to.username", allow_null=True, read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    sla_status = serializers.SerializerMethodField()
    events = PreparednessActionEventSerializer(many=True, read_only=True)

    class Meta:
        model = PreparednessAction
        fields = [
            "id",
            "public_id",
            "action_type",
            "source_trigger_type",
            "source_trigger_ref",
            "ward",
            "ward_name",
            "ward_public_id",
            "facility",
            "facility_name",
            "chv",
            "chv_name",
            "alert",
            "alert_public_id",
            "alert_workflow",
            "alert_workflow_public_id",
            "risk_score",
            "model_run",
            "model_run_version",
            "facility_readiness_review",
            "facility_readiness_review_public_id",
            "facility_update_request",
            "facility_update_request_public_id",
            "facility_escalation",
            "facility_escalation_public_id",
            "chv_coverage_request",
            "chv_coverage_request_public_id",
            "status",
            "priority",
            "created_by",
            "created_by_username",
            "assigned_to",
            "assigned_to_username",
            "assigned_to_team",
            "decision_policy_version",
            "due_at",
            "sla_target_at",
            "acknowledged_at",
            "completed_at",
            "cancelled_at",
            "escalated_at",
            "completion_evidence",
            "cancellation_reason",
            "escalation_metadata",
            "lineage_metadata",
            "notes",
            "is_overdue",
            "sla_status",
            "created_at",
            "updated_at",
            "events",
        ]
        read_only_fields = fields

    def get_sla_status(self, obj: PreparednessAction) -> str:
        if not obj.is_active:
            return "NOT_APPLICABLE"
        return "OVERDUE" if obj.is_overdue else "ON_TRACK"


class PreparednessActionCreateSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("notes",)
    pii_safe_mapping_fields = ("lineage_metadata",)

    ward_id = serializers.IntegerField()
    action_type = serializers.ChoiceField(choices=[choice[0] for choice in PreparednessAction.ACTION_TYPE_CHOICES])
    source_trigger_type = serializers.ChoiceField(
        choices=[choice[0] for choice in PreparednessAction.SOURCE_TRIGGER_CHOICES],
        required=False,
        default=PreparednessAction.SOURCE_MANUAL,
    )
    priority = serializers.ChoiceField(
        choices=[choice[0] for choice in PreparednessAction.PRIORITY_CHOICES],
        required=False,
        default=PreparednessAction.PRIORITY_MEDIUM,
    )
    status = serializers.ChoiceField(
        choices=[
            PreparednessAction.STATUS_DRAFT,
            PreparednessAction.STATUS_QUEUED,
            PreparednessAction.STATUS_ASSIGNED,
        ],
        required=False,
        default=PreparednessAction.STATUS_QUEUED,
    )
    facility_id = serializers.IntegerField(required=False, allow_null=True)
    chv_id = serializers.IntegerField(required=False, allow_null=True)
    alert_public_id = serializers.UUIDField(required=False, allow_null=True)
    alert_workflow_public_id = serializers.UUIDField(required=False, allow_null=True)
    risk_score_id = serializers.IntegerField(required=False, allow_null=True)
    model_run_id = serializers.IntegerField(required=False, allow_null=True)
    facility_readiness_review_public_id = serializers.UUIDField(required=False, allow_null=True)
    facility_update_request_public_id = serializers.UUIDField(required=False, allow_null=True)
    facility_escalation_public_id = serializers.UUIDField(required=False, allow_null=True)
    chv_coverage_request_public_id = serializers.UUIDField(required=False, allow_null=True)
    assigned_to_id = serializers.IntegerField(required=False, allow_null=True)
    assigned_to_team = serializers.CharField(required=False, allow_blank=True, max_length=120)
    decision_policy_version = serializers.CharField(required=False, allow_blank=True, max_length=80)
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    sla_target_at = serializers.DateTimeField(required=False, allow_null=True)
    source_trigger_ref = serializers.CharField(required=False, allow_blank=True, max_length=160)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    lineage_metadata = serializers.DictField(required=False)


class PreparednessActionTransitionSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("detail", "cancellation_reason")
    pii_safe_mapping_fields = ("completion_evidence", "escalation_metadata")

    status = serializers.ChoiceField(choices=[choice[0] for choice in PreparednessAction.STATUS_CHOICES])
    detail = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    assigned_to_id = serializers.IntegerField(required=False, allow_null=True)
    assigned_to_team = serializers.CharField(required=False, allow_blank=True, max_length=120)
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    sla_target_at = serializers.DateTimeField(required=False, allow_null=True)
    completion_evidence = serializers.DictField(required=False)
    cancellation_reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    escalation_metadata = serializers.DictField(required=False)


class PreparednessActionSourceTriggerSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("notes",)
    pii_safe_mapping_fields = ("lineage_metadata",)

    action_type = serializers.ChoiceField(choices=[choice[0] for choice in PreparednessAction.ACTION_TYPE_CHOICES])
    priority = serializers.ChoiceField(
        choices=[choice[0] for choice in PreparednessAction.PRIORITY_CHOICES],
        required=False,
        allow_null=True,
    )
    status = serializers.ChoiceField(
        choices=[
            PreparednessAction.STATUS_DRAFT,
            PreparednessAction.STATUS_QUEUED,
            PreparednessAction.STATUS_ASSIGNED,
        ],
        required=False,
        default=PreparednessAction.STATUS_QUEUED,
    )
    assigned_to_id = serializers.IntegerField(required=False, allow_null=True)
    assigned_to_team = serializers.CharField(required=False, allow_blank=True, max_length=120)
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    sla_target_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    lineage_metadata = serializers.DictField(required=False)


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
    spatial_evidence = serializers.DictField(required=False)
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


class TriggerPreviewRequestSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("message_override",)
    pii_safe_mapping_fields = ("template_context",)

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
    template_key = serializers.CharField(required=False, allow_blank=True, max_length=120)
    template_version = serializers.IntegerField(required=False, min_value=1, allow_null=True)
    template_language = serializers.CharField(required=False, allow_blank=True, max_length=20)
    template_context = serializers.JSONField(required=False, default=dict)

    def validate_message_override(self, value):
        return validate_pii_safe_serializer_text(value, field_name="message_override")

    def validate(self, attrs):
        attrs["template_key"] = attrs.get("template_key", "").strip()
        attrs["template_language"] = attrs.get("template_language", "").strip().lower()
        return attrs


class TriggerPreviewResponseSerializer(serializers.Serializer):
    message_preview = serializers.CharField()
    message_mode = serializers.CharField()
    supports_editing = serializers.BooleanField()
    channel_defaults = serializers.ListField(child=serializers.CharField())
    recipient_preview = TriggerRecipientPreviewSerializer()
    recommended_action = serializers.CharField()
    message_template = serializers.JSONField(required=False)


class TriggerAlertRequestSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("message_override",)
    pii_safe_mapping_fields = ("template_context",)

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
    template_key = serializers.CharField(required=False, allow_blank=True, max_length=120)
    template_version = serializers.IntegerField(required=False, min_value=1, allow_null=True)
    template_language = serializers.CharField(required=False, allow_blank=True, max_length=20)
    template_context = serializers.JSONField(required=False, default=dict)

    def validate_message_override(self, value):
        return validate_pii_safe_serializer_text(value, field_name="message_override")

    def validate(self, attrs):
        attrs["template_key"] = attrs.get("template_key", "").strip()
        attrs["template_language"] = attrs.get("template_language", "").strip().lower()
        return attrs


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

    def validate_reason(self, value):
        return validate_pii_safe_serializer_text(value, field_name="reason")


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


class CHVTriageRequestSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("text_input",)

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
    phone_number = serializers.SerializerMethodField()
    text_input = serializers.SerializerMethodField()
    privacy_context = serializers.SerializerMethodField()

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
            "privacy_context",
        ]

    def _can_view_sensitive_field_health_echo(self) -> bool:
        user = serializer_user(self)
        return user_can_view_direct_identifiers(user)

    def get_phone_number(self, obj: TriageSession) -> str:
        if self._can_view_sensitive_field_health_echo():
            return obj.phone_number
        return mask_contact_value(obj.phone_number)

    def get_text_input(self, obj: TriageSession) -> str:
        return redact_field_health_text(
            obj.text_input,
            can_view=self._can_view_sensitive_field_health_echo(),
        )

    def get_privacy_context(self, obj: TriageSession) -> dict:
        return privacy_context(
            classification="sensitive_field_health_data",
            redacted=not self._can_view_sensitive_field_health_echo(),
            reason="Field triage response echoes are masked for CHV field sessions and labelled as sensitive health data.",
        )


class UssdSessionLogSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    menu_version_public_id = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()
    text = serializers.SerializerMethodField()
    response_text = serializers.SerializerMethodField()

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
            "menu_version",
            "menu_version_public_id",
            "menu_key",
            "menu_version_label",
            "language",
            "requested_language",
            "resolved_language",
            "fallback_used",
            "menu_level",
            "session_outcome",
            "invalid_option",
            "abandonment_reason",
            "is_terminal",
            "governance_metadata",
            "created_at",
        ]

    def _can_view_raw_ussd_log(self) -> bool:
        user = serializer_user(self)
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and (getattr(user, "is_superuser", False) or getattr(user, "role", None) == "ADMIN")
        )

    def get_phone_number(self, obj: UssdSessionLog) -> str:
        if self._can_view_raw_ussd_log():
            return obj.phone_number
        return mask_contact_value(obj.phone_number)

    def get_text(self, obj: UssdSessionLog) -> str:
        return redact_direct_identifiers_in_text(
            obj.text,
            can_view=self._can_view_raw_ussd_log(),
        )

    def get_response_text(self, obj: UssdSessionLog) -> str:
        return redact_direct_identifiers_in_text(
            obj.response_text,
            can_view=self._can_view_raw_ussd_log(),
        )

    def get_menu_version_public_id(self, obj: UssdSessionLog) -> str:
        return str(obj.menu_version.public_id) if obj.menu_version else ""


class UssdMenuVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UssdMenuVersion
        fields = [
            "id",
            "public_id",
            "menu_key",
            "version_label",
            "language",
            "title",
            "menu_tree",
            "safe_fallback_copy",
            "session_outcome_taxonomy",
            "approval_status",
            "approved_by",
            "approved_at",
            "retired_at",
            "translation_status",
            "source_menu_version",
            "translation_reviewed_by",
            "translation_reviewed_at",
            "translation_review_notes",
            "is_active",
            "lineage_metadata",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "public_id", "created_at", "updated_at"]


class SyncPayloadSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    pii_safe_text_fields = ("text_input",)
    pii_safe_mapping_fields = ("payload",)

    SUPPORTED_PAYLOAD_KEYS = {
        SyncQueue.UPLOAD_SYMPTOM_TRIAGE: {
            "ward_id",
            "task_public_id",
            "action_public_id",
            "diarrhea",
            "vomiting",
            "dehydration",
            "fever",
            "text_input",
        },
        SyncQueue.UPLOAD_SUSPECTED_CASE_SIGNAL: {
            "ward_id",
            "task_public_id",
            "action_public_id",
            "diarrhea",
            "vomiting",
            "dehydration",
            "fever",
            "text_input",
        },
        SyncQueue.UPLOAD_PREVENTION_VISIT: {
            "ward_id",
            "task_public_id",
            "action_public_id",
            "visit_completed",
            "households_reached_count",
            "messages_delivered_count",
            "water_treatment_demo",
            "soap_or_handwashing_discussed",
        },
        SyncQueue.UPLOAD_TASK_ACK: {
            "ward_id",
            "task_public_id",
            "action_public_id",
            "assignment_public_id",
            "acknowledgment_status",
            "coded_reason",
        },
        SyncQueue.UPLOAD_ALERT_ACK: {
            "ward_id",
            "alert_public_id",
            "task_public_id",
            "action_public_id",
            "acknowledgment_status",
            "coded_reason",
        },
    }

    client_submission_id = serializers.CharField(max_length=120)
    idempotency_key = serializers.CharField(required=False, allow_blank=True, max_length=160)
    payload_version = serializers.CharField(
        required=False,
        allow_blank=True,
        default=OFFLINE_CHV_UPLOAD_PAYLOAD_VERSION,
        max_length=64,
    )
    upload_type = serializers.ChoiceField(
        choices=[choice[0] for choice in SyncQueue.UPLOAD_CHOICES],
        required=False,
        default=SyncQueue.UPLOAD_SYMPTOM_TRIAGE,
    )
    download_bundle_version = serializers.CharField(required=False, allow_blank=True, max_length=96)
    recorded_at = serializers.DateTimeField(required=False, allow_null=True)
    payload = serializers.DictField(required=False)
    diarrhea = serializers.BooleanField(required=False, default=False)
    vomiting = serializers.BooleanField(required=False, default=False)
    dehydration = serializers.BooleanField(required=False, default=False)
    fever = serializers.BooleanField(required=False, default=False)
    text_input = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        upload_type = attrs.get("upload_type") or SyncQueue.UPLOAD_SYMPTOM_TRIAGE
        if upload_type not in SUPPORTED_PHASE_4_UPLOAD_TYPES:
            raise serializers.ValidationError(
                {
                    "upload_type": "This upload type is not accepted by CHV offline sync processing."
                }
            )
        payload_version = (attrs.get("payload_version") or OFFLINE_CHV_UPLOAD_PAYLOAD_VERSION).strip()
        if payload_version != OFFLINE_CHV_UPLOAD_PAYLOAD_VERSION:
            raise serializers.ValidationError(
                {
                    "payload_version": f"Unsupported CHV offline payload version: {payload_version}."
                }
            )

        nested_payload = dict(attrs.get("payload") or {})
        legacy_keys = {"diarrhea", "vomiting", "dehydration", "fever", "text_input"}
        legacy_payload = (
            {key: attrs.get(key) for key in legacy_keys if key in attrs}
            if upload_type in {SyncQueue.UPLOAD_SYMPTOM_TRIAGE, SyncQueue.UPLOAD_SUSPECTED_CASE_SIGNAL}
            else {}
        )
        payload = {**legacy_payload, **nested_payload}
        supported_keys = self.SUPPORTED_PAYLOAD_KEYS.get(upload_type, set())
        unsupported_keys = sorted(set(payload) - supported_keys)
        if unsupported_keys:
            raise serializers.ValidationError(
                {
                    "payload": [
                        "Unsupported field. This endpoint only accepts the documented minimum data fields.",
                        *unsupported_keys,
                    ]
                }
            )

        attrs["client_submission_id"] = attrs["client_submission_id"].strip()
        attrs["idempotency_key"] = (attrs.get("idempotency_key") or attrs["client_submission_id"]).strip()
        attrs["payload_version"] = payload_version
        attrs["upload_type"] = upload_type
        attrs["payload"] = payload
        return attrs


class CHVSyncRequestSerializer(PiiSafeInputSerializerMixin, serializers.Serializer):
    contract_version = serializers.CharField(required=False, allow_blank=True, default=OFFLINE_CHV_CONTRACT_VERSION)
    device_registration_id = serializers.UUIDField(required=False, allow_null=True)
    session_scope = serializers.DictField(required=False, default=dict)
    download_bundle_version = serializers.CharField(required=False, allow_blank=True, max_length=96)
    ward_id = serializers.IntegerField(required=False)
    phone_number = serializers.CharField(required=False, allow_blank=True, default="")
    source_device_id = serializers.CharField(required=False, allow_blank=True, default="")
    language = serializers.CharField(required=False, allow_blank=True, max_length=20)
    requested_language = serializers.CharField(required=False, allow_blank=True, max_length=20)
    resolved_language = serializers.CharField(required=False, allow_blank=True, max_length=20)
    fallback_used = serializers.BooleanField(required=False, default=False)
    payloads = SyncPayloadSerializer(many=True, required=False)
    uploads = SyncPayloadSerializer(many=True, required=False)

    def _validate_payload_identities(self, value):
        submission_ids = [
            item["client_submission_id"].strip()
            for item in value
            if item.get("client_submission_id", "").strip()
        ]
        if len(submission_ids) != len(value):
            raise serializers.ValidationError("Each payload must include client_submission_id.")
        if len(set(submission_ids)) != len(submission_ids):
            raise serializers.ValidationError("client_submission_id values must be unique within a request.")
        idempotency_keys = [
            (item.get("idempotency_key") or item["client_submission_id"]).strip()
            for item in value
            if (item.get("idempotency_key") or item.get("client_submission_id", "")).strip()
        ]
        if len(set(idempotency_keys)) != len(idempotency_keys):
            raise serializers.ValidationError("idempotency_key values must be unique within a request.")

    def validate(self, attrs):
        payloads = attrs.get("payloads")
        uploads = attrs.get("uploads")
        if payloads is not None and uploads is not None:
            raise serializers.ValidationError({"uploads": "Use either uploads or payloads, not both."})
        normalized_payloads = payloads if payloads is not None else uploads
        if not normalized_payloads:
            raise serializers.ValidationError({"payloads": "At least one payload is required."})
        self._validate_payload_identities(normalized_payloads)

        source_device_id = (attrs.get("source_device_id") or "").strip()
        if not source_device_id and not attrs.get("device_registration_id"):
            raise serializers.ValidationError(
                {
                    "source_device_id": (
                        "A source_device_id or device_registration_id is required "
                        "for idempotent offline sync."
                    )
                }
            )

        ward_id = attrs.get("ward_id")
        session_scope = attrs.get("session_scope") or {}
        if ward_id is None and session_scope.get("ward_id") is not None:
            ward_id = session_scope["ward_id"]
        if ward_id is None:
            raise serializers.ValidationError({"ward_id": "A ward_id or session_scope.ward_id is required."})
        try:
            ward_id = int(ward_id)
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({"ward_id": "A valid ward_id is required."}) from exc

        attrs["ward_id"] = ward_id
        attrs["source_device_id"] = source_device_id
        attrs["payloads"] = normalized_payloads
        attrs["contract_version"] = (attrs.get("contract_version") or OFFLINE_CHV_CONTRACT_VERSION).strip()
        attrs["language"] = (attrs.get("language") or "").strip().lower()
        attrs["requested_language"] = (attrs.get("requested_language") or attrs["language"]).strip().lower()
        attrs["resolved_language"] = (attrs.get("resolved_language") or "").strip().lower()
        return attrs

    def validate_payloads(self, value):
        self._validate_payload_identities(value)
        return value


class SyncQueueSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = SyncQueue
        fields = [
            "id",
            "source_device_id",
            "device_registration",
            "contract_version",
            "upload_type",
            "client_submission_id",
            "idempotency_key",
            "download_bundle_version",
            "recorded_at",
            "phone_number",
            "ward",
            "ward_name",
            "triage_session",
            "payload",
            "status",
            "conflict_state",
            "server_receipt",
            "processed_at",
            "error_message",
            "created_at",
        ]
