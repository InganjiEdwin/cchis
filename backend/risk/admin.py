from django.contrib import admin
from .models import Alert, CHV, RiskScore, Ward


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = (
        "name",
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


@admin.register(RiskScore)
class RiskScoreAdmin(admin.ModelAdmin):
    list_display = (
        "ward",
        "risk_level",
        "score",
        "rainfall_mm",
        "flood_indicator",
        "predicted_cases",
        "generated_at",
    )
    search_fields = ("ward__name", "model_version")
    list_filter = ("risk_level", "source", "generated_at")


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = (
        "ward",
        "channel",
        "recipient",
        "status",
        "sent_at",
        "created_at",
    )
    search_fields = ("ward__name", "recipient", "external_id")
    list_filter = ("channel", "status", "created_at")
