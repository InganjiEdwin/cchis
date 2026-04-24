from django.urls import path
from .views import (
    AlertDetailAPIView,
    AlertListAPIView,
    CHVListAPIView,
    CHVSyncAPIView,
    CHVTriageAPIView,
    LatestWardRiskAPIView,
    RiskScoreListAPIView,
    TriggerAlertsAPIView,
    USSDMenuAPIView,
    UssdSessionLogListAPIView,
    WardDetailAPIView,
    WardListAPIView,
)

urlpatterns = [
    path("wards/", WardListAPIView.as_view(), name="ward-list"),
    path("wards/<int:pk>/", WardDetailAPIView.as_view(), name="ward-detail"),
    path("chvs/", CHVListAPIView.as_view(), name="chv-list"),
    path("risk-scores/", RiskScoreListAPIView.as_view(), name="risk-score-list"),
    path("risk-score/latest/", LatestWardRiskAPIView.as_view(), name="latest-ward-risk"),
    path("alerts/", AlertListAPIView.as_view(), name="alert-list"),
    path("alerts/<int:pk>/", AlertDetailAPIView.as_view(), name="alert-detail"),
    path("alerts/trigger/", TriggerAlertsAPIView.as_view(), name="trigger-alerts"),
    path("chv/triage/", CHVTriageAPIView.as_view(), name="chv-triage"),
    path("chv/sync/", CHVSyncAPIView.as_view(), name="chv-sync"),
    path("ussd/menu/", USSDMenuAPIView.as_view(), name="ussd-menu"),
    path("ussd/logs/", UssdSessionLogListAPIView.as_view(), name="ussd-log-list"),
]
