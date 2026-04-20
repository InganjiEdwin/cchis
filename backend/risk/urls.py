from django.urls import path
from .views import (
    AlertListAPIView,
    CHVListAPIView,
    CHVTriageAPIView,
    LatestWardRiskAPIView,
    RiskScoreListAPIView,
    TriggerAlertsAPIView,
    USSDMenuAPIView,
    WardListAPIView,
)

urlpatterns = [
    path("wards/", WardListAPIView.as_view(), name="ward-list"),
    path("chvs/", CHVListAPIView.as_view(), name="chv-list"),
    path("risk-scores/", RiskScoreListAPIView.as_view(), name="risk-score-list"),
    path("risk-score/latest/", LatestWardRiskAPIView.as_view(), name="latest-ward-risk"),
    path("alerts/", AlertListAPIView.as_view(), name="alert-list"),
    path("alerts/trigger/", TriggerAlertsAPIView.as_view(), name="trigger-alerts"),
    path("chv/triage/", CHVTriageAPIView.as_view(), name="chv-triage"),
    path("ussd/menu/", USSDMenuAPIView.as_view(), name="ussd-menu"),
]