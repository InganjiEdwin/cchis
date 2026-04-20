from rest_framework import serializers
from .models import Alert, CHV, RiskScore, Ward

from rest_framework import serializers
from .models import Alert, CHV, RiskScore, TriageSession, Ward


class WardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ward
        fields = [
            "id",
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


class RiskScoreSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = RiskScore
        fields = [
            "id",
            "ward",
            "ward_name",
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
            "external_id",
            "sent_at",
            "created_at",
            "error_message",
        ]


class TriggerAlertRequestSerializer(serializers.Serializer):
    ward_id = serializers.IntegerField(required=False)
    risk_level = serializers.ChoiceField(
        choices=["LOW", "MEDIUM", "HIGH"],
        required=False,
    )
    send_sms = serializers.BooleanField(default=False)


class CHVTriageRequestSerializer(serializers.Serializer):
    ward_id = serializers.IntegerField()
    phone_number = serializers.CharField(required=False, allow_blank=True)
    diarrhea = serializers.BooleanField(default=False)
    vomiting = serializers.BooleanField(default=False)
    dehydration = serializers.BooleanField(default=False)
    fever = serializers.BooleanField(default=False)


class CHVTriageResponseSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = TriageSession
        fields = [
            "id",
            "channel",
            "phone_number",
            "ward",
            "ward_name",
            "diarrhea",
            "vomiting",
            "dehydration",
            "fever",
            "recommendation",
            "referral_needed",
            "created_at",
        ]


class WardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ward
        fields = [
            "id",
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


class RiskScoreSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = RiskScore
        fields = [
            "id",
            "ward",
            "ward_name",
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
            "external_id",
            "sent_at",
            "created_at",
            "error_message",
        ]


class TriggerAlertRequestSerializer(serializers.Serializer):
    ward_id = serializers.IntegerField(required=False)
    risk_level = serializers.ChoiceField(
        choices=["LOW", "MEDIUM", "HIGH"],
        required=False,
    )
    send_sms = serializers.BooleanField(default=False)
