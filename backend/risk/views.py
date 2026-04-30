import logging
from datetime import datetime
import uuid

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsAdminOnly, IsAdminOrSupervisor, IsAdminSupervisorOrAnalyst, IsFieldOperator

from .tasks import trigger_alerts_task

from .facility_forecasting import (
    build_facility_forecast_promotion_summary,
    build_facility_forecasting_truth_audit,
    build_initial_facility_forecast_contract_definition,
    build_initial_facility_forecast_preview,
)
from .ml.alignment import get_live_model_alignment_summary
from .models import Alert, AlertWorkflowEvent, AlertWorkflowState, CHV, CHVMessage, DashboardNotification, FacilityReadinessEscalation, FacilityReadinessReview, FacilityReadinessUpdateRequest, HealthFacility, IngestionRun, ModelRun, RiskScore, UssdSessionLog, Ward
from .models import CHVAssignment, CHVCoverageRequest, CHVCoverageRequestAlertLink, CHVCoverageRequestEvent
from .map_data import build_migori_ward_map_summary
from datetime import timedelta

from rest_framework_simplejwt.tokens import AccessToken

from .notifications import notification_summary_for_user, notifications_for_user, transition_notification
from .serializers import (
    AlertIntelligenceSerializer,
    AlertWorkflowStateSerializer,
    AlertSerializer,
    CHVAssignmentDecisionSerializer,
    CHVCoverageRequestFromAlertPrefillResponseSerializer,
    CHVCoverageRequestFromAlertPrefillSerializer,
    CHVCoverageRequestAssignSerializer,
    CHVCoverageRequestCreateSerializer,
    CHVCoverageRequestDecisionSerializer,
    CHVCoverageRequestSerializer,
    CHVActivityEventSerializer,
    CHVMessageCreateSerializer,
    CHVMessageSerializer,
    CHVSerializer,
    CHVOperationsSerializer,
    CHVSyncRequestSerializer,
    CHVTriageRequestSerializer,
    CHVTriageResponseSerializer,
    FacilityIntelligenceSerializer,
    FacilityReadinessEscalationCreateSerializer,
    FacilityReadinessEscalationSerializer,
    FacilityReadinessEscalationStatusSerializer,
    FacilityReadinessReviewAcknowledgeSerializer,
    FacilityReadinessReviewCreateSerializer,
    FacilityReadinessReviewSerializer,
    FacilityReadinessReviewStatusSerializer,
    FacilityReadinessUpdateRequestCreateSerializer,
    FacilityReadinessUpdateRequestSerializer,
    FacilityForecastPreviewSerializer,
    FacilityForecastPromotionSummarySerializer,
    FacilityForecastingStatusSerializer,
    HealthFacilitySerializer,
    IngestionRunSerializer,
    DashboardNotificationSerializer,
    ModelAlignmentSerializer,
    ModelRunSerializer,
    RiskScoreSerializer,
    ScenarioSimulationRequestSerializer,
    ScenarioSimulationRunSerializer,
    TriggerContextRequestSerializer,
    TriggerContextResponseSerializer,
    TriggerAlertRequestSerializer,
    TriggerAlertRequestStatusResponseSerializer,
    TriggerPreviewRequestSerializer,
    TriggerPreviewResponseSerializer,
    UssdSessionLogSerializer,
    WardDetailSerializer,
    WardIntelligenceSerializer,
    WardSerializer,
)
from .services import (
    build_alert_intelligence_snapshot,
    build_guided_trigger_context,
    build_guided_trigger_preview,
    build_chv_activity_timeline,
    build_chv_coverage_request_from_alert_defaults,
    build_chv_operations_snapshot,
    build_facility_intelligence_snapshot,
    build_facility_readiness_decision_summary,
    acknowledge_facility_readiness_review,
    build_alert_workflow_records,
    build_ward_intelligence_snapshot,
    cancel_chv_assignment,
    cancel_chv_coverage_request,
    complete_chv_assignment,
    create_facility_readiness_escalation,
    create_facility_readiness_review,
    create_facility_readiness_update_request,
    create_chv_message,
    create_chv_coverage_request,
    create_triage_session,
    approve_chv_coverage_request,
    assign_chv_to_coverage_request,
    latest_riskscore_for_ward,
    process_sync_payload,
    record_chv_coverage_request_event,
    reject_chv_coverage_request,
    resolve_chv_coverage_request,
    transition_facility_readiness_escalation,
    transition_facility_readiness_review,
    run_dashboard_scenario_simulation,
    sync_alert_workflow_for_ward,
    sync_alert_workflows_for_wards,
)


alerts_logger = logging.getLogger("risk.alerts")


def parse_bool_query_param(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None


def parse_datetime_query_param(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def user_has_broad_dashboard_scope(user: User) -> bool:
    return user.role in [User.ROLE_ADMIN, User.ROLE_ANALYST]


def apply_ward_scope_or_none(queryset, user: User, field_name: str = "ward_id"):
    if user_has_broad_dashboard_scope(user):
        return queryset

    if not user.ward_id:
        return queryset.none()

    return queryset.filter(**{field_name: user.ward_id})


def facility_workflow_states_for_facilities(facilities):
    facility_ids = [facility.id for facility in facilities]
    if not facility_ids:
        return []

    active_reviews = {
        review.facility_id: review
        for review in FacilityReadinessReview.objects.filter(
            facility_id__in=facility_ids,
            status__in=FacilityReadinessReview.ACTIVE_STATUSES,
        ).order_by("facility_id", "-created_at")
    }
    active_update_requests = {
        update_request.facility_id: update_request
        for update_request in FacilityReadinessUpdateRequest.objects.filter(
            facility_id__in=facility_ids,
            status__in=FacilityReadinessUpdateRequest.ACTIVE_STATUSES,
        ).order_by("facility_id", "-requested_at", "-created_at")
    }
    active_escalations = {
        escalation.facility_id: escalation
        for escalation in FacilityReadinessEscalation.objects.filter(
            facility_id__in=facility_ids,
            status__in=FacilityReadinessEscalation.ACTIVE_STATUSES,
        ).order_by("facility_id", "-created_at")
    }

    workflow_states = []
    for facility in facilities:
        review = active_reviews.get(facility.id)
        update_request = active_update_requests.get(facility.id)
        escalation = active_escalations.get(facility.id)

        if escalation is not None:
            label = "Escalated"
            tone = "warning"
        elif update_request is not None:
            label = "Update pending"
            tone = "warning"
        elif review is not None:
            label = "Review open" if review.status == FacilityReadinessReview.STATUS_OPEN else "Review acknowledged"
            tone = "warning" if review.status == FacilityReadinessReview.STATUS_OPEN else "default"
        else:
            label = "No review signals"
            tone = "success"

        workflow_states.append(
            {
                "facility_id": facility.id,
                "has_active_review": review is not None,
                "review_public_id": str(review.public_id) if review else None,
                "review_status": review.status if review else None,
                "has_active_update_request": update_request is not None,
                "update_request_public_id": str(update_request.public_id) if update_request else None,
                "update_request_status": update_request.status if update_request else None,
                "has_active_escalation": escalation is not None,
                "escalation_public_id": str(escalation.public_id) if escalation else None,
                "escalation_status": escalation.status if escalation else None,
                "label": label,
                "tone": tone,
            }
        )

    return workflow_states


def chv_coverage_request_queryset_for_user(user: User):
    queryset = (
        CHVCoverageRequest.objects.select_related(
            "ward",
            "requested_by",
            "assigned_to_user",
            "reviewed_by",
        )
        .prefetch_related(
            "assignments__chv",
            "assignments__assigned_by",
            "events__actor",
            "events__assignment",
            "linked_alert_links__alert__ward",
            "linked_alert_links__alert__risk_score",
        )
        .order_by("-created_at")
    )
    return apply_ward_scope_or_none(queryset, user, field_name="ward_id")


def facility_readiness_review_queryset_for_user(user: User):
    queryset = (
        FacilityReadinessReview.objects.select_related(
            "facility",
            "ward",
            "created_by",
            "assigned_to",
        )
        .prefetch_related("events__actor")
        .order_by("-created_at")
    )
    return apply_ward_scope_or_none(queryset, user, field_name="ward_id")


def facility_readiness_escalation_queryset_for_user(user: User):
    queryset = (
        FacilityReadinessEscalation.objects.select_related(
            "review",
            "facility",
            "ward",
            "created_by",
            "acknowledged_by",
            "assigned_to",
        )
        .order_by("-created_at")
    )
    return apply_ward_scope_or_none(queryset, user, field_name="ward_id")


def user_can_mutate_facility_readiness_review(user: User) -> bool:
    return user.role in [User.ROLE_ADMIN, User.ROLE_SUPERVISOR]


def chv_assignment_queryset_for_user(user: User):
    queryset = CHVAssignment.objects.select_related(
        "coverage_request",
        "ward",
        "chv",
        "assigned_by",
    ).order_by("-created_at")
    return apply_ward_scope_or_none(queryset, user, field_name="coverage_request__ward_id")


def reload_chv_coverage_request_for_user(user: User, public_id):
    return get_object_or_404(chv_coverage_request_queryset_for_user(user), public_id=public_id)


def attach_alerts_to_existing_coverage_request(*, request_record: CHVCoverageRequest, alerts: list[Alert], actor: User):
    existing_linked_alert_public_ids = set(
        str(public_id)
        for public_id in request_record.linked_alert_links.values_list("alert__public_id", flat=True)
    )
    CHVCoverageRequestAlertLink.objects.bulk_create(
        [
            CHVCoverageRequestAlertLink(
                coverage_request=request_record,
                alert=alert,
                linked_by=actor,
            )
            for alert in alerts
        ],
        ignore_conflicts=True,
    )
    attached_alert_public_ids = [
        str(alert.public_id)
        for alert in alerts
        if str(alert.public_id) not in existing_linked_alert_public_ids
    ]
    request_record = reload_chv_coverage_request_for_user(actor, request_record.public_id)
    if attached_alert_public_ids:
        record_chv_coverage_request_event(
            request_record,
            action=CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_ATTACHED,
            actor=actor,
            old_status=request_record.status,
            new_status=request_record.status,
            detail="Linked alert context attached to the existing coverage request.",
            metadata={
                "trigger_source": CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
                "linked_alert_public_ids": attached_alert_public_ids,
                "attachment_mode": "EXISTING_REQUEST",
            },
        )
    return request_record, attached_alert_public_ids


class WardListAPIView(generics.ListAPIView):
    serializer_class = WardSerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]
    filter_backends = [OrderingFilter]
    ordering_fields = ["name", "county", "sub_county", "updated_at", "current_risk_score"]
    ordering = ["name"]

    def get_queryset(self):
        queryset = Ward.objects.filter(is_active=True).order_by("name")
        user = self.request.user
        q = self.request.query_params.get("q")
        county = self.request.query_params.get("county")
        sub_county = self.request.query_params.get("sub_county")
        risk_level = self.request.query_params.get("risk")
        is_active = parse_bool_query_param(self.request.query_params.get("is_active"))
        queryset = apply_ward_scope_or_none(queryset, user, field_name="id")

        if q:
            queryset = queryset.filter(name__icontains=q.strip())
        if county:
            queryset = queryset.filter(county__iexact=county.strip())
        if sub_county:
            queryset = queryset.filter(sub_county__iexact=sub_county.strip())
        if risk_level:
            queryset = queryset.filter(current_risk_level=risk_level.strip().upper())
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset


class WardDetailAPIView(generics.RetrieveAPIView):
    serializer_class = WardDetailSerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get_queryset(self):
        queryset = Ward.objects.filter(is_active=True).prefetch_related("risk_scores")
        return apply_ward_scope_or_none(queryset, self.request.user, field_name="id")


class WardIntelligenceAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request, pk: int):
        queryset = Ward.objects.filter(is_active=True).prefetch_related("risk_scores", "alerts")
        ward = apply_ward_scope_or_none(queryset, request.user, field_name="id").filter(pk=pk).first()

        if ward is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = build_ward_intelligence_snapshot(ward)
        serializer = WardIntelligenceSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CHVListAPIView(generics.ListAPIView):
    serializer_class = CHVSerializer
    permission_classes = [IsAdminOrSupervisor]
    filter_backends = [OrderingFilter]
    ordering_fields = ["name", "created_at", "ward__name"]
    ordering = ["name"]

    def get_queryset(self):
        queryset = CHV.objects.filter(is_active=True).select_related("ward").order_by("name")
        user = self.request.user
        ward_id = self.request.query_params.get("ward_id")
        is_active = parse_bool_query_param(self.request.query_params.get("is_active"))
        queryset = apply_ward_scope_or_none(queryset, user)

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset


class CHVOperationsAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def get(self, request):
        queryset = CHV.objects.select_related("ward").order_by("name")
        scoped_queryset = apply_ward_scope_or_none(queryset, request.user)
        ward_id = request.query_params.get("ward_id")

        if ward_id:
            scoped_queryset = scoped_queryset.filter(ward_id=ward_id)

        payload = build_chv_operations_snapshot(scoped_queryset)
        serializer = CHVOperationsSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CHVActivityAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def get(self, request, public_id):
        queryset = CHV.objects.select_related("ward").order_by("name")
        scoped_queryset = apply_ward_scope_or_none(queryset, request.user)
        chv = get_object_or_404(scoped_queryset, public_id=public_id)
        payload = build_chv_activity_timeline(chv)
        serializer = CHVActivityEventSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CHVMessageListCreateAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def get_chv(self, request, public_id):
        queryset = CHV.objects.select_related("ward").order_by("name")
        scoped_queryset = apply_ward_scope_or_none(queryset, request.user)
        return get_object_or_404(scoped_queryset, public_id=public_id)

    def get(self, request, public_id):
        chv = self.get_chv(request, public_id)
        messages = CHVMessage.objects.filter(chv=chv).select_related("sent_by").order_by("-created_at")
        serializer = CHVMessageSerializer(messages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, public_id):
        chv = self.get_chv(request, public_id)
        serializer = CHVMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            message_record = create_chv_message(
                chv,
                message_body=serializer.validated_data["message_body"],
                sent_by=request.user,
                channel=serializer.validated_data["channel"],
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        response_serializer = CHVMessageSerializer(message_record)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CHVCoverageRequestListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = CHVCoverageRequestSerializer
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "updated_at", "expected_response_by", "priority", "status"]
    ordering = ["-created_at"]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminOrSupervisor()]
        return [IsAdminSupervisorOrAnalyst()]

    def get_queryset(self):
        queryset = chv_coverage_request_queryset_for_user(self.request.user)
        ward_id = self.request.query_params.get("ward_id")
        status_value = self.request.query_params.get("status")
        priority = self.request.query_params.get("priority")
        trigger_source = self.request.query_params.get("trigger_source")
        overdue = parse_bool_query_param(self.request.query_params.get("overdue"))
        has_linked_alerts = parse_bool_query_param(self.request.query_params.get("has_linked_alerts"))

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if status_value:
            queryset = queryset.filter(status=status_value.upper())
        if priority:
            queryset = queryset.filter(priority=priority.upper())
        if trigger_source:
            queryset = queryset.filter(trigger_source=trigger_source.upper())
        if has_linked_alerts is True:
            queryset = queryset.filter(linked_alert_links__isnull=False).distinct()
        if has_linked_alerts is False:
            queryset = queryset.filter(linked_alert_links__isnull=True)
        if overdue is True:
            queryset = queryset.filter(
                status__in=[
                    CHVCoverageRequest.STATUS_OPEN,
                    CHVCoverageRequest.STATUS_APPROVED,
                    CHVCoverageRequest.STATUS_IN_PROGRESS,
                ],
                expected_response_by__lt=timezone.now(),
            )
        if overdue is False:
            queryset = queryset.exclude(
                status__in=[
                    CHVCoverageRequest.STATUS_OPEN,
                    CHVCoverageRequest.STATUS_APPROVED,
                    CHVCoverageRequest.STATUS_IN_PROGRESS,
                ],
                expected_response_by__lt=timezone.now(),
            )
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = CHVCoverageRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ward = (
            apply_ward_scope_or_none(Ward.objects.filter(is_active=True), request.user, field_name="id")
            .filter(id=serializer.validated_data["ward_id"])
            .first()
        )
        if ward is None:
            return Response({"detail": "Ward not found."}, status=status.HTTP_404_NOT_FOUND)

        linked_alerts = []
        if serializer.validated_data["trigger_source"] == CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN:
            linked_alert_public_ids = serializer.validated_data["linked_alert_public_ids"]
            alert_queryset = apply_ward_scope_or_none(
                Alert.objects.select_related("ward", "risk_score").all(),
                request.user,
            )
            linked_alerts = list(alert_queryset.filter(public_id__in=linked_alert_public_ids))
            if len(linked_alerts) != len(linked_alert_public_ids):
                return Response(
                    {"detail": "One or more linked alerts could not be found in your permitted scope."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if any(alert.ward_id != ward.id for alert in linked_alerts):
                return Response(
                    {"detail": "Linked alerts must belong to the same ward as the coverage request."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        existing_request = (
            CHVCoverageRequest.objects.filter(
                ward=ward,
                status__in=[
                    CHVCoverageRequest.STATUS_OPEN,
                    CHVCoverageRequest.STATUS_APPROVED,
                    CHVCoverageRequest.STATUS_IN_PROGRESS,
                ],
            )
            .order_by("-created_at")
            .first()
        )
        if existing_request is not None:
            if (
                serializer.validated_data["trigger_source"] == CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN
                and linked_alerts
            ):
                existing_request, attached_alert_public_ids = attach_alerts_to_existing_coverage_request(
                    request_record=existing_request,
                    alerts=linked_alerts,
                    actor=request.user,
                )
                record_chv_coverage_request_event(
                    existing_request,
                    action=CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_REDIRECTED,
                    actor=request.user,
                    old_status=existing_request.status,
                    new_status=existing_request.status,
                    detail="Alert-linked request attempt resolved to the existing live coverage request.",
                    metadata={
                        "trigger_source": CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
                        "linked_alert_public_ids": [str(alert.public_id) for alert in linked_alerts],
                        "attached_alert_public_ids": attached_alert_public_ids,
                        "resolution": "EXISTING_LIVE_REQUEST",
                        "source_api": "DIRECT_CREATE",
                    },
                )
            return Response(
                {
                    "detail": "A live CHV coverage request already exists for this ward.",
                    "existing_request_public_id": str(existing_request.public_id),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            request_record = create_chv_coverage_request(
                ward=ward,
                requested_by=request.user,
                priority=serializer.validated_data["priority"],
                reason=serializer.validated_data["reason"].strip(),
                requested_chv_count=serializer.validated_data["requested_chv_count"],
                notes=serializer.validated_data.get("notes", "").strip(),
                trigger_source=serializer.validated_data["trigger_source"],
                linked_alerts=linked_alerts,
            )
        except IntegrityError:
            existing_request = (
                CHVCoverageRequest.objects.filter(
                    ward=ward,
                    status__in=[
                        CHVCoverageRequest.STATUS_OPEN,
                        CHVCoverageRequest.STATUS_APPROVED,
                        CHVCoverageRequest.STATUS_IN_PROGRESS,
                    ],
                )
                .order_by("-created_at")
                .first()
            )
            if (
                existing_request is not None
                and serializer.validated_data["trigger_source"] == CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN
                and linked_alerts
            ):
                existing_request, attached_alert_public_ids = attach_alerts_to_existing_coverage_request(
                    request_record=existing_request,
                    alerts=linked_alerts,
                    actor=request.user,
                )
                record_chv_coverage_request_event(
                    existing_request,
                    action=CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_REDIRECTED,
                    actor=request.user,
                    old_status=existing_request.status,
                    new_status=existing_request.status,
                    detail="Alert-linked request attempt resolved to the existing live coverage request.",
                    metadata={
                        "trigger_source": CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
                        "linked_alert_public_ids": [str(alert.public_id) for alert in linked_alerts],
                        "attached_alert_public_ids": attached_alert_public_ids,
                        "resolution": "EXISTING_LIVE_REQUEST",
                        "source_api": "DIRECT_CREATE_RACE",
                    },
                )
            return Response(
                {
                    "detail": "A live CHV coverage request already exists for this ward.",
                    "existing_request_public_id": str(existing_request.public_id) if existing_request else None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        request_record = reload_chv_coverage_request_for_user(request.user, request_record.public_id)
        return Response(CHVCoverageRequestSerializer(request_record).data, status=status.HTTP_201_CREATED)


class CHVCoverageRequestFromAlertPrefillAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request):
        serializer = CHVCoverageRequestFromAlertPrefillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        alert_public_ids = serializer.validated_data["alert_public_ids"]
        alert_queryset = apply_ward_scope_or_none(
            Alert.objects.select_related("ward", "risk_score").all(),
            request.user,
        )
        alerts = list(alert_queryset.filter(public_id__in=alert_public_ids))

        if len(alerts) != len(alert_public_ids):
            return Response(
                {"detail": "One or more linked alerts could not be found in your permitted scope."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ward_ids = {alert.ward_id for alert in alerts}
        if len(ward_ids) != 1:
            return Response(
                {"detail": "Linked alerts must all belong to the same ward."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ward = alerts[0].ward
        existing_request = (
            CHVCoverageRequest.objects.filter(
                ward=ward,
                status__in=[
                    CHVCoverageRequest.STATUS_OPEN,
                    CHVCoverageRequest.STATUS_APPROVED,
                    CHVCoverageRequest.STATUS_IN_PROGRESS,
                ],
            )
            .order_by("-created_at")
            .first()
        )

        if existing_request is not None:
            existing_request, attached_alert_public_ids = attach_alerts_to_existing_coverage_request(
                request_record=existing_request,
                alerts=alerts,
                actor=request.user,
            )
            record_chv_coverage_request_event(
                existing_request,
                action=CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_REDIRECTED,
                actor=request.user,
                old_status=existing_request.status,
                new_status=existing_request.status,
                detail="Alert-linked request attempt resolved to the existing live coverage request.",
                metadata={
                    "trigger_source": CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
                    "linked_alert_public_ids": [str(alert.public_id) for alert in alerts],
                    "attached_alert_public_ids": attached_alert_public_ids,
                    "resolution": "EXISTING_LIVE_REQUEST",
                },
            )
            payload = {
                "mode": "EXISTING_LIVE_REQUEST",
                "detail": "A live CHV coverage request already exists for this ward.",
                "create_defaults": None,
                "existing_request": existing_request,
            }
            return Response(
                CHVCoverageRequestFromAlertPrefillResponseSerializer(payload).data,
                status=status.HTTP_200_OK,
            )

        payload = {
            "mode": "CREATE_READY",
            "detail": "Alert-linked CHV coverage request defaults are ready.",
            "create_defaults": build_chv_coverage_request_from_alert_defaults(ward=ward, alerts=alerts),
            "existing_request": None,
        }
        return Response(
            CHVCoverageRequestFromAlertPrefillResponseSerializer(payload).data,
            status=status.HTTP_200_OK,
        )


class CHVCoverageRequestDetailAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request, public_id):
        request_record = get_object_or_404(chv_coverage_request_queryset_for_user(request.user), public_id=public_id)
        return Response(CHVCoverageRequestSerializer(request_record).data, status=status.HTTP_200_OK)


class CHVCoverageRequestApproveAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request, public_id):
        request_record = get_object_or_404(chv_coverage_request_queryset_for_user(request.user), public_id=public_id)
        serializer = CHVCoverageRequestDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            approve_chv_coverage_request(
                request_record,
                actor=request.user,
                reason=serializer.validated_data.get("reason", "").strip(),
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        request_record = reload_chv_coverage_request_for_user(request.user, request_record.public_id)
        return Response(CHVCoverageRequestSerializer(request_record).data, status=status.HTTP_200_OK)


class CHVCoverageRequestRejectAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request, public_id):
        request_record = get_object_or_404(chv_coverage_request_queryset_for_user(request.user), public_id=public_id)
        serializer = CHVCoverageRequestDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reject_chv_coverage_request(
                request_record,
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        request_record = reload_chv_coverage_request_for_user(request.user, request_record.public_id)
        return Response(CHVCoverageRequestSerializer(request_record).data, status=status.HTTP_200_OK)


class CHVCoverageRequestCancelAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request, public_id):
        request_record = get_object_or_404(chv_coverage_request_queryset_for_user(request.user), public_id=public_id)
        serializer = CHVCoverageRequestDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cancel_chv_coverage_request(
                request_record,
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        request_record = reload_chv_coverage_request_for_user(request.user, request_record.public_id)
        return Response(CHVCoverageRequestSerializer(request_record).data, status=status.HTTP_200_OK)


class CHVCoverageRequestResolveAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request, public_id):
        request_record = get_object_or_404(chv_coverage_request_queryset_for_user(request.user), public_id=public_id)
        serializer = CHVCoverageRequestDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            resolve_chv_coverage_request(
                request_record,
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        request_record = reload_chv_coverage_request_for_user(request.user, request_record.public_id)
        return Response(CHVCoverageRequestSerializer(request_record).data, status=status.HTTP_200_OK)


class CHVCoverageRequestAssignAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request, public_id):
        request_record = get_object_or_404(chv_coverage_request_queryset_for_user(request.user), public_id=public_id)
        serializer = CHVCoverageRequestAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chv = (
            apply_ward_scope_or_none(CHV.objects.select_related("ward"), request.user)
            .filter(id=serializer.validated_data["chv_id"])
            .first()
        )
        if chv is None:
            return Response({"detail": "CHV not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            assignment = assign_chv_to_coverage_request(
                request_record,
                chv=chv,
                actor=request.user,
                notes=serializer.validated_data.get("notes", "").strip(),
                start_at=serializer.validated_data.get("start_at"),
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        request_record = reload_chv_coverage_request_for_user(request.user, request_record.public_id)
        return Response(CHVCoverageRequestSerializer(request_record).data, status=status.HTTP_200_OK)


class CHVAssignmentCompleteAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request, public_id):
        assignment = get_object_or_404(chv_assignment_queryset_for_user(request.user), public_id=public_id)
        serializer = CHVAssignmentDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            complete_chv_assignment(
                assignment,
                actor=request.user,
                notes=serializer.validated_data.get("notes", "").strip(),
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        request_record = reload_chv_coverage_request_for_user(request.user, assignment.coverage_request.public_id)
        return Response(CHVCoverageRequestSerializer(request_record).data, status=status.HTTP_200_OK)


class CHVAssignmentCancelAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request, public_id):
        assignment = get_object_or_404(chv_assignment_queryset_for_user(request.user), public_id=public_id)
        serializer = CHVAssignmentDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cancel_chv_assignment(
                assignment,
                actor=request.user,
                notes=serializer.validated_data.get("notes", "").strip(),
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        request_record = reload_chv_coverage_request_for_user(request.user, assignment.coverage_request.public_id)
        return Response(CHVCoverageRequestSerializer(request_record).data, status=status.HTTP_200_OK)


class IngestionRunListAPIView(generics.ListAPIView):
    serializer_class = IngestionRunSerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]
    filter_backends = [OrderingFilter]
    ordering_fields = ["started_at", "completed_at", "run_type", "status"]
    ordering = ["-started_at"]

    def get_queryset(self):
        queryset = IngestionRun.objects.all().order_by("-started_at")
        run_type = self.request.query_params.get("run_type")
        status_value = self.request.query_params.get("status")

        if run_type:
            queryset = queryset.filter(run_type=run_type)
        if status_value:
            queryset = queryset.filter(status=status_value.upper())
        return queryset


class ModelRunListAPIView(generics.ListAPIView):
    serializer_class = ModelRunSerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]
    filter_backends = [OrderingFilter]
    ordering_fields = ["started_at", "completed_at", "status", "algorithm_name", "model_version"]
    ordering = ["-completed_at", "-started_at"]

    def get_queryset(self):
        queryset = ModelRun.objects.all().order_by("-completed_at", "-started_at")
        algorithm_name = self.request.query_params.get("algorithm_name")
        status_value = self.request.query_params.get("status")

        if algorithm_name:
            queryset = queryset.filter(algorithm_name=algorithm_name)
        if status_value:
            queryset = queryset.filter(status=status_value.upper())
        return queryset


class HealthFacilityListAPIView(generics.ListAPIView):
    serializer_class = HealthFacilitySerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]
    filter_backends = [OrderingFilter]
    ordering_fields = ["name", "updated_at", "ward__name", "facility_type", "level"]
    ordering = ["ward__name", "name"]

    def get_queryset(self):
        queryset = HealthFacility.objects.filter(is_active=True).select_related("ward").order_by("ward__name", "name")
        user = self.request.user
        ward_id = self.request.query_params.get("ward_id")
        facility_type = self.request.query_params.get("facility_type")
        queryset = apply_ward_scope_or_none(queryset, user)

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if facility_type:
            queryset = queryset.filter(facility_type=facility_type.upper())
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        facilities_for_summary = list(queryset)
        facilities_for_page = list(page) if page is not None else facilities_for_summary
        serializer = self.get_serializer(facilities_for_page, many=True)
        decision_summary = build_facility_readiness_decision_summary(facilities_for_summary)
        workflow_states = facility_workflow_states_for_facilities(facilities_for_page)

        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.data["decision_summary"] = decision_summary
            response.data["workflow_states"] = workflow_states
            return response

        return Response(
            {
                "count": len(serializer.data),
                "next": None,
                "previous": None,
                "results": serializer.data,
                "decision_summary": decision_summary,
                "workflow_states": workflow_states,
            },
            status=status.HTTP_200_OK,
        )


class HealthFacilityDetailAPIView(generics.RetrieveAPIView):
    serializer_class = HealthFacilitySerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get_queryset(self):
        queryset = HealthFacility.objects.filter(is_active=True).select_related("ward")
        return apply_ward_scope_or_none(queryset, self.request.user)


class HealthFacilityIntelligenceAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request, pk: int):
        queryset = HealthFacility.objects.filter(is_active=True).select_related("ward")
        facility = apply_ward_scope_or_none(queryset, request.user).filter(pk=pk).first()

        if facility is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = build_facility_intelligence_snapshot(facility, user=request.user)
        serializer = FacilityIntelligenceSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class FacilityReadinessReviewListAPIView(generics.ListAPIView):
    serializer_class = FacilityReadinessReviewSerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get_queryset(self):
        return facility_readiness_review_queryset_for_user(self.request.user)


class FacilityReadinessReviewCreateAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request, pk: int):
        queryset = HealthFacility.objects.filter(is_active=True).select_related("ward")
        facility = apply_ward_scope_or_none(queryset, request.user).filter(pk=pk).first()

        if facility is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = FacilityReadinessReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            review = create_facility_readiness_review(
                facility=facility,
                actor=request.user,
                notes=serializer.validated_data.get("notes", ""),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})

        response_serializer = FacilityReadinessReviewSerializer(review)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class FacilityReadinessReviewDetailAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get_review(self, request, public_id):
        return get_object_or_404(facility_readiness_review_queryset_for_user(request.user), public_id=public_id)

    def get(self, request, public_id):
        review = self.get_review(request, public_id)
        serializer = FacilityReadinessReviewSerializer(review)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, public_id):
        if not user_can_mutate_facility_readiness_review(request.user):
            return Response({"detail": "You do not have permission to update this review."}, status=status.HTTP_403_FORBIDDEN)

        review = self.get_review(request, public_id)
        serializer = FacilityReadinessReviewStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            review = transition_facility_readiness_review(
                review,
                actor=request.user,
                status=serializer.validated_data["status"],
                notes=serializer.validated_data.get("notes", ""),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})

        response_serializer = FacilityReadinessReviewSerializer(review)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class FacilityReadinessReviewAcknowledgeAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request, public_id):
        review = get_object_or_404(facility_readiness_review_queryset_for_user(request.user), public_id=public_id)
        serializer = FacilityReadinessReviewAcknowledgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            review = acknowledge_facility_readiness_review(
                review,
                actor=request.user,
                notes=serializer.validated_data.get("notes", ""),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})

        response_serializer = FacilityReadinessReviewSerializer(review)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class FacilityReadinessUpdateRequestCreateAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request, public_id):
        review = get_object_or_404(facility_readiness_review_queryset_for_user(request.user), public_id=public_id)
        serializer = FacilityReadinessUpdateRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            update_request = create_facility_readiness_update_request(
                review,
                actor=request.user,
                message_body=serializer.validated_data.get("message_body", ""),
                channel=serializer.validated_data.get("channel"),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})

        response_serializer = FacilityReadinessUpdateRequestSerializer(update_request)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


def _resolve_county_review_assignee(assigned_to_id):
    if assigned_to_id is None:
        return None
    return get_object_or_404(
        User.objects.filter(is_active=True, role=User.ROLE_ADMIN),
        id=assigned_to_id,
    )


class FacilityReadinessEscalationListAPIView(generics.ListAPIView):
    serializer_class = FacilityReadinessEscalationSerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get_queryset(self):
        queryset = facility_readiness_escalation_queryset_for_user(self.request.user)
        status_param = self.request.query_params.get("status")
        assignment = self.request.query_params.get("assignment")

        if status_param:
            queryset = queryset.filter(status=status_param)
        if assignment == "unassigned":
            queryset = queryset.filter(assigned_to__isnull=True)
        elif assignment == "mine":
            queryset = queryset.filter(assigned_to=self.request.user)

        return queryset


class FacilityReadinessEscalationCreateAPIView(APIView):
    permission_classes = [IsAdminOnly]

    def post(self, request, public_id):
        review = get_object_or_404(facility_readiness_review_queryset_for_user(request.user), public_id=public_id)
        serializer = FacilityReadinessEscalationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assigned_to = _resolve_county_review_assignee(serializer.validated_data.get("assigned_to"))

        try:
            escalation = create_facility_readiness_escalation(
                review,
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
                severity=serializer.validated_data.get("severity"),
                assigned_to=assigned_to,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})

        response_serializer = FacilityReadinessEscalationSerializer(escalation)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class FacilityReadinessEscalationDetailAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get_escalation(self, request, public_id):
        return get_object_or_404(facility_readiness_escalation_queryset_for_user(request.user), public_id=public_id)

    def get(self, request, public_id):
        escalation = self.get_escalation(request, public_id)
        serializer = FacilityReadinessEscalationSerializer(escalation)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, public_id):
        if not (request.user.is_superuser or request.user.role == User.ROLE_ADMIN):
            return Response({"detail": "You do not have permission to update county review escalations."}, status=status.HTTP_403_FORBIDDEN)

        escalation = self.get_escalation(request, public_id)
        serializer = FacilityReadinessEscalationStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assigned_to = _resolve_county_review_assignee(serializer.validated_data.get("assigned_to"))

        try:
            escalation = transition_facility_readiness_escalation(
                escalation,
                actor=request.user,
                status=serializer.validated_data["status"],
                notes=serializer.validated_data.get("notes", ""),
                assigned_to=assigned_to,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})

        response_serializer = FacilityReadinessEscalationSerializer(escalation)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class FacilityForecastingStatusAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request):
        payload = build_facility_forecasting_truth_audit()
        payload["contract_definition"] = build_initial_facility_forecast_contract_definition()
        payload["promotion_summary"] = build_facility_forecast_promotion_summary()
        serializer = FacilityForecastingStatusSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class HealthFacilityForecastPreviewAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request, pk: int):
        queryset = HealthFacility.objects.filter(is_active=True).select_related("ward")
        facility = apply_ward_scope_or_none(queryset, request.user).filter(pk=pk).first()

        if facility is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = build_initial_facility_forecast_preview(facility)
        serializer = FacilityForecastPreviewSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class FacilityForecastingEvaluationAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request):
        payload = build_facility_forecast_promotion_summary()
        serializer = FacilityForecastPromotionSummarySerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RiskScoreListAPIView(generics.ListAPIView):
    serializer_class = RiskScoreSerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]
    filter_backends = [OrderingFilter]
    ordering_fields = ["generated_at", "score", "risk_level", "predicted_cases", "ward__name"]
    ordering = ["-generated_at"]

    def get_queryset(self):
        queryset = RiskScore.objects.select_related("ward").all()
        ward_id = self.request.query_params.get("ward_id")
        risk_level = self.request.query_params.get("risk_level")
        source = self.request.query_params.get("source")
        generated_after = parse_datetime_query_param(self.request.query_params.get("generated_after"))
        generated_before = parse_datetime_query_param(self.request.query_params.get("generated_before"))
        user = self.request.user
        queryset = apply_ward_scope_or_none(queryset, user)

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if risk_level:
            queryset = queryset.filter(risk_level=risk_level.upper())
        if source:
            queryset = queryset.filter(source=source.upper())
        if generated_after:
            queryset = queryset.filter(generated_at__gte=generated_after)
        if generated_before:
            queryset = queryset.filter(generated_at__lte=generated_before)

        return queryset.order_by("-generated_at")


class LatestWardRiskAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request):
        results = []
        wards = Ward.objects.filter(is_active=True).order_by("name")
        user = request.user
        q = request.query_params.get("q")
        county = request.query_params.get("county")
        sub_county = request.query_params.get("sub_county")
        risk_level = request.query_params.get("risk")
        wards = apply_ward_scope_or_none(wards, user, field_name="id")

        if q:
            wards = wards.filter(name__icontains=q.strip())
        if county:
            wards = wards.filter(county__iexact=county.strip())
        if sub_county:
            wards = wards.filter(sub_county__iexact=sub_county.strip())
        if risk_level:
            wards = wards.filter(current_risk_level=risk_level.strip().upper())

        for ward in wards:
            latest = latest_riskscore_for_ward(ward)
            results.append(
                {
                    "ward_id": ward.id,
                    "ward_name": ward.name,
                    "risk_level": latest.risk_level if latest else ward.current_risk_level,
                    "risk_score": latest.score if latest else ward.current_risk_score,
                    "predicted_cases": latest.predicted_cases if latest else 0,
                    "generated_at": latest.generated_at if latest else None,
                }
            )

        return Response(results, status=status.HTTP_200_OK)


class AlertListAPIView(generics.ListAPIView):
    serializer_class = AlertSerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "sent_at", "channel", "status", "ward__name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Alert.objects.select_related("ward", "risk_score").all().order_by("-created_at")
        user = self.request.user
        ward_id = self.request.query_params.get("ward_id")
        channel = self.request.query_params.get("channel")
        status_value = self.request.query_params.get("status")
        created_after = parse_datetime_query_param(self.request.query_params.get("created_after"))
        created_before = parse_datetime_query_param(self.request.query_params.get("created_before"))
        queryset = apply_ward_scope_or_none(queryset, user)

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if channel:
            queryset = queryset.filter(channel=channel.upper())
        if status_value:
            queryset = queryset.filter(status=status_value.upper())
        if created_after:
            queryset = queryset.filter(created_at__gte=created_after)
        if created_before:
            queryset = queryset.filter(created_at__lte=created_before)
        return queryset


class AlertDetailAPIView(generics.RetrieveAPIView):
    serializer_class = AlertSerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get_queryset(self):
        queryset = Alert.objects.select_related("ward", "risk_score").all()
        return apply_ward_scope_or_none(queryset, self.request.user)


class AlertIntelligenceAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request, pk: int):
        queryset = Alert.objects.select_related("ward", "risk_score").all()
        alert = apply_ward_scope_or_none(queryset, request.user).filter(pk=pk).first()

        if alert is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        ward_queryset = Ward.objects.filter(is_active=True).prefetch_related("risk_scores")
        ward_detail = apply_ward_scope_or_none(ward_queryset, request.user, field_name="id").filter(pk=alert.ward_id).first()

        payload = build_alert_intelligence_snapshot(alert, ward_detail=ward_detail)
        serializer = AlertIntelligenceSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AlertWorkflowListAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request):
        wards = Ward.objects.filter(is_active=True).order_by("name")
        scoped_wards = list(apply_ward_scope_or_none(wards, request.user, field_name="id"))
        workflows = sync_alert_workflows_for_wards(scoped_wards)
        records = build_alert_workflow_records(workflows)
        return Response(
            {
                "count": len(records),
                "results": records,
            },
            status=status.HTTP_200_OK,
        )


class DashboardNotificationListAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request):
        queryset = notifications_for_user(request.user)
        try:
            requested_page_size = int(request.query_params.get("page_size", 100))
        except (TypeError, ValueError):
            requested_page_size = 100
        page_size = min(max(requested_page_size, 1), 100)
        serializer = DashboardNotificationSerializer(queryset[:page_size], many=True)
        summary = notification_summary_for_user(request.user)
        return Response(
            {
                "count": queryset.count(),
                **summary,
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class DashboardNotificationDetailAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request, public_id):
        queryset = notifications_for_user(request.user)
        notification = get_object_or_404(queryset, public_id=public_id)
        serializer = DashboardNotificationSerializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DashboardNotificationStreamTokenAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request):
        token = AccessToken.for_user(request.user)
        token["purpose"] = "dashboard_notifications_stream"
        token["role"] = request.user.role
        token["ward_id"] = request.user.ward_id
        token.set_exp(lifetime=timedelta(minutes=5))
        return Response(
            {
                "token": str(token),
                "websocket_path": "/ws/notifications/stream/",
                "expires_in_seconds": 300,
            },
            status=status.HTTP_200_OK,
        )


class DashboardNotificationSeenAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def post(self, request, public_id):
        queryset = notifications_for_user(request.user)
        notification = get_object_or_404(queryset, public_id=public_id)
        notification = transition_notification(notification, "SEEN", actor=request.user)
        return Response(DashboardNotificationSerializer(notification).data, status=status.HTTP_200_OK)


class DashboardNotificationAcknowledgeAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def post(self, request, public_id):
        queryset = notifications_for_user(request.user)
        notification = get_object_or_404(queryset, public_id=public_id)
        if not notification.requires_acknowledgement:
            return Response({"detail": "This notification does not require acknowledgement."}, status=status.HTTP_400_BAD_REQUEST)
        notification = transition_notification(notification, "ACKNOWLEDGED", actor=request.user)
        return Response(DashboardNotificationSerializer(notification).data, status=status.HTTP_200_OK)


class DashboardNotificationDismissAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def post(self, request, public_id):
        queryset = notifications_for_user(request.user)
        notification = get_object_or_404(queryset, public_id=public_id)
        if not notification.dismissible:
            return Response({"detail": "This notification cannot be dismissed."}, status=status.HTTP_400_BAD_REQUEST)
        notification = transition_notification(notification, "DISMISSED", actor=request.user)
        return Response(DashboardNotificationSerializer(notification).data, status=status.HTTP_200_OK)


class DashboardNotificationMarkAllSeenAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def post(self, request):
        queryset = notifications_for_user(request.user).filter(state=DashboardNotification.STATE_NEW)
        for notification in queryset:
            transition_notification(notification, "SEEN", actor=request.user)
        refreshed = notifications_for_user(request.user)
        serializer = DashboardNotificationSerializer(refreshed[:100], many=True)
        summary = notification_summary_for_user(request.user)
        return Response(
            {
                "count": refreshed.count(),
                **summary,
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class MigoriWardMapAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request):
        wards = Ward.objects.filter(is_active=True, county__iexact="Migori").order_by("name")
        scoped_wards = apply_ward_scope_or_none(wards, request.user, field_name="id")
        payload = build_migori_ward_map_summary(
            scoped_wards,
            limit_to_backend_wards=not user_has_broad_dashboard_scope(request.user),
        )
        return Response(payload, status=status.HTTP_200_OK)


class ModelAlignmentAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get(self, request):
        payload = get_live_model_alignment_summary()
        serializer = ModelAlignmentSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TriggerAlertContextAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def get(self, request):
        serializer = TriggerContextRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        queryset = Ward.objects.filter(is_active=True).order_by("name")
        user = request.user
        if user.role != User.ROLE_ADMIN:
            queryset = apply_ward_scope_or_none(queryset, user, field_name="id")

        ward_id = serializer.validated_data.get("ward_id")
        requested_risk_level = serializer.validated_data.get("risk_level")
        if ward_id:
            ward = queryset.filter(id=ward_id).first()
        else:
            ward = queryset.filter(current_risk_level=requested_risk_level).first()

        if ward is None:
            return Response({"detail": "No matching ward context found."}, status=status.HTTP_404_NOT_FOUND)

        payload = build_guided_trigger_context(ward)
        return Response(TriggerContextResponseSerializer(payload).data, status=status.HTTP_200_OK)


class TriggerAlertPreviewAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request):
        serializer = TriggerPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        queryset = Ward.objects.filter(is_active=True).order_by("name")
        user = request.user
        if user.role != User.ROLE_ADMIN:
            queryset = apply_ward_scope_or_none(queryset, user, field_name="id")

        ward = queryset.filter(id=serializer.validated_data["ward_id"]).first()
        if ward is None:
            return Response({"detail": "No matching ward context found."}, status=status.HTTP_404_NOT_FOUND)

        payload = build_guided_trigger_preview(
            ward,
            serializer.validated_data["trigger_type"],
            serializer.validated_data.get("message_override"),
        )
        return Response(TriggerPreviewResponseSerializer(payload).data, status=status.HTTP_200_OK)


class TriggerAlertsAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request):
        serializer = TriggerAlertRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ward_id = serializer.validated_data["ward_id"]
        send_sms = serializer.validated_data.get("send_sms", False)
        trigger_type = serializer.validated_data.get("trigger_type")
        message_override = serializer.validated_data.get("message_override")

        queryset = RiskScore.objects.select_related("ward").all()
        user = request.user
        if user.role != User.ROLE_ADMIN:
            queryset = apply_ward_scope_or_none(queryset, user)

        queryset = queryset.filter(ward_id=ward_id)

        risk_score = queryset.order_by("-generated_at").first()
        if not risk_score:
            alerts_logger.warning(
                "alert_trigger_request_rejected",
                extra={
                    "actor_user_id": user.id,
                    "actor_role": user.role,
                    "requested_ward_id": ward_id,
                    "send_sms": send_sms,
                    "reason": "no_matching_risk_score_in_scope",
                    "request_path": request.path,
                    "request_method": request.method,
                },
            )
            return Response(
                {"detail": "No matching risk score found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        estimated_chv_recipient_count = CHV.objects.filter(ward_id=risk_score.ward_id, is_active=True).count()
        queued_at = timezone.now()
        request_id = str(uuid.uuid4())
        trigger_context = build_guided_trigger_context(risk_score.ward)
        preview_payload = build_guided_trigger_preview(risk_score.ward, trigger_type, message_override)
        guided_request_metadata = {
            "request_id": request_id,
            "selected_trigger_type": trigger_type,
            "system_recommendation_at_confirmation": trigger_context["system_context"]["recommended_trigger_type"],
            "send_sms": send_sms,
            "message_mode": preview_payload["message_mode"],
            "message_override_applied": bool(message_override),
            "message_preview_used": preview_payload["message_preview"],
            "confirmed_by_user_id": user.id,
            "confirmed_at": queued_at.isoformat(),
        }
        workflow = sync_alert_workflow_for_ward(
            risk_score.ward,
            actor=user,
            manual_request_queued_at=queued_at,
            event_metadata=guided_request_metadata,
        )
        task = trigger_alerts_task.delay(
            risk_score.id,
            send_sms=send_sms,
            trigger_type=trigger_type,
            message_override=message_override,
            guided_request_metadata=guided_request_metadata,
        )
        alerts_logger.info(
            "alert_trigger_request_queued",
            extra={
                "actor_user_id": user.id,
                "actor_role": user.role,
                "effective_ward_id": risk_score.ward_id,
                "risk_score_id": risk_score.id,
                "requested_ward_id": ward_id,
                "send_sms": send_sms,
                "task_id": task.id,
                "request_id": request_id,
                "request_path": request.path,
                "request_method": request.method,
                "trigger_type": trigger_type,
                "message_mode": preview_payload["message_mode"],
            },
        )

        return Response(
            {
                "message": "Alert request queued successfully.",
                "request_id": request_id,
                "alert_id": None,
                "ward_id": risk_score.ward_id,
                "ward_name": risk_score.ward.name,
                "risk_level": risk_score.risk_level,
                "risk_score": risk_score.score,
                "predicted_cases": risk_score.predicted_cases,
                "risk_score_id": risk_score.id,
                "task_id": task.id,
                "send_sms": send_sms,
                "trigger_type": trigger_type,
                "message_mode": preview_payload["message_mode"],
                "queued_at": queued_at,
                "last_risk_update_at": risk_score.generated_at,
                "estimated_chv_recipient_count": estimated_chv_recipient_count,
                "trigger_linkage_state": "linked_existing_workflow" if workflow else None,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class TriggerAlertRequestStatusAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def get(self, request, request_id: str):
        request_id = str(request_id)
        alerts = (
            apply_ward_scope_or_none(
                Alert.objects.select_related("ward").order_by("created_at"),
                request.user,
            )
            .filter(guided_request_metadata__request_id=request_id)
        )

        if alerts.exists():
            dashboard_alert = alerts.filter(channel=Alert.CHANNEL_DASHBOARD).order_by("created_at").first()
            primary_alert = dashboard_alert or alerts.first()
            payload = {
                "request_id": request_id,
                "status": "MATERIALIZED",
                "alert_id": primary_alert.id if primary_alert else None,
                "ward_id": primary_alert.ward_id if primary_alert else dashboard_alert.ward_id,
                "ward_name": primary_alert.ward.name if primary_alert else dashboard_alert.ward.name,
                "created_alert_count": alerts.count(),
                "sms_alert_count": alerts.filter(channel=Alert.CHANNEL_SMS).count(),
                "dashboard_alert_id": dashboard_alert.id if dashboard_alert else None,
                "last_materialized_at": primary_alert.created_at if primary_alert else None,
            }
            return Response(TriggerAlertRequestStatusResponseSerializer(payload).data, status=status.HTTP_200_OK)

        event = (
            apply_ward_scope_or_none(
                AlertWorkflowEvent.objects.select_related("workflow__ward").order_by("-created_at"),
                request.user,
                field_name="workflow__ward_id",
            )
            .filter(
                action=AlertWorkflowEvent.ACTION_MANUAL_REQUEST_QUEUED,
                metadata__request_id=request_id,
            )
            .first()
        )

        if event is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = {
            "request_id": request_id,
            "status": "PENDING_CREATION",
            "alert_id": None,
            "ward_id": event.workflow.ward_id,
            "ward_name": event.workflow.ward.name,
            "created_alert_count": 0,
            "sms_alert_count": 0,
            "dashboard_alert_id": None,
            "last_materialized_at": None,
        }
        return Response(TriggerAlertRequestStatusResponseSerializer(payload).data, status=status.HTTP_200_OK)


class ScenarioSimulationRunAPIView(APIView):
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def post(self, request):
        serializer = ScenarioSimulationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        scenario_run = run_dashboard_scenario_simulation(
            scenario_id=serializer.validated_data["scenario_id"],
            created_by=request.user,
            rainfall_uplift_percent=serializer.validated_data.get("rainfall_uplift_percent", 20),
            response_delay_hours=serializer.validated_data.get("response_delay_hours", 12),
        )
        return Response(ScenarioSimulationRunSerializer(scenario_run).data, status=status.HTTP_201_CREATED)


class CHVTriageAPIView(APIView):
    permission_classes = [IsFieldOperator]

    def post(self, request):
        serializer = CHVTriageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ward_id = serializer.validated_data["ward_id"]
        user = request.user

        if user.role in [User.ROLE_CHV, User.ROLE_SUPERVISOR] and user.ward_id != ward_id:
            return Response(
                {"detail": "Ward not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            ward = Ward.objects.get(id=ward_id, is_active=True)
        except Ward.DoesNotExist:
            return Response(
                {"detail": "Ward not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        session = create_triage_session(
            ward=ward,
            phone_number=serializer.validated_data.get("phone_number", ""),
            diarrhea=serializer.validated_data.get("diarrhea", False),
            vomiting=serializer.validated_data.get("vomiting", False),
            dehydration=serializer.validated_data.get("dehydration", False),
            fever=serializer.validated_data.get("fever", False),
            text_input=serializer.validated_data.get("text_input", ""),
            channel=serializer.validated_data.get("channel", "API") or "API",
        )

        return Response(
            CHVTriageResponseSerializer(session).data,
            status=status.HTTP_201_CREATED,
        )


class CHVSyncAPIView(APIView):
    permission_classes = [IsFieldOperator]

    def post(self, request):
        serializer = CHVSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ward_id = serializer.validated_data["ward_id"]
        user = request.user
        phone_number = serializer.validated_data.get("phone_number", "")
        source_device_id = serializer.validated_data.get("source_device_id", "")
        payloads = serializer.validated_data["payloads"]

        if user.role in [User.ROLE_CHV, User.ROLE_SUPERVISOR] and user.ward_id != ward_id:
            return Response(
                {"detail": "Ward not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            ward = Ward.objects.get(id=ward_id, is_active=True)
        except Ward.DoesNotExist:
            return Response(
                {"detail": "Ward not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        processed = []
        for payload in payloads:
            sync_item, triage_session, replayed = process_sync_payload(
                ward=ward,
                phone_number=phone_number,
                source_device_id=source_device_id,
                payload=payload,
            )
            processed.append(
                {
                    "sync_queue_id": sync_item.id,
                    "client_submission_id": sync_item.client_submission_id,
                    "sync_status": sync_item.status,
                    "replayed": replayed,
                    "triage_session": CHVTriageResponseSerializer(triage_session).data,
                }
            )

        return Response(
            {
                "message": "Offline payloads synced successfully.",
                "processed_count": len(processed),
                "results": processed,
            },
            status=status.HTTP_201_CREATED,
        )


class USSDMenuAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "public_ussd"

    def post(self, request):
        session_id = (request.data.get("sessionId") or request.data.get("session_id") or "").strip()
        service_code = (request.data.get("serviceCode") or request.data.get("service_code") or "").strip()
        phone_number = (request.data.get("phoneNumber") or request.data.get("phone_number") or "").strip()
        text = (request.data.get("text") or "").strip()

        response_text = "END Invalid option. Please try again."
        menu_level = "invalid"
        ward = None

        if text == "":
            response_text = (
                "CON Welcome to CCHIS Health Menu\n"
                "1. Flood safety advice\n"
                "2. Child diarrhea support\n"
                "3. Heat health advice"
            )
            menu_level = "root"
        elif text == "1":
            response_text = (
                "END Flood safety:\n"
                "Use treated water, avoid flood water, wash hands often, "
                "and seek care if child has diarrhea or vomiting."
            )
            menu_level = "flood_safety"
        elif text == "2":
            response_text = (
                "CON Child diarrhea support\n"
                "1. Diarrhea with vomiting or dehydration\n"
                "2. Mild diarrhea only"
            )
            menu_level = "diarrhea_menu"
        elif text == "2*1":
            response_text = (
                "END Give ORS immediately and go to nearest health facility now. "
                "Use safe water and report to CHV if available."
            )
            menu_level = "diarrhea_urgent"
        elif text == "2*2":
            response_text = (
                "END Give ORS, continue fluids, monitor closely, "
                "and seek care if child worsens."
            )
            menu_level = "diarrhea_mild"
        elif text == "3":
            response_text = (
                "END Heat advice:\n"
                "Give water often, keep child in shade, avoid midday sun, "
                "and seek care for weakness or confusion."
            )
            menu_level = "heat_advice"

        UssdSessionLog.objects.create(
            session_id=session_id or "unknown-session",
            phone_number=phone_number,
            service_code=service_code,
            text=text,
            response_text=response_text,
            ward=ward,
            menu_level=menu_level,
        )

        return Response(
            {"response": response_text},
            status=status.HTTP_200_OK,
        )


class UssdSessionLogListAPIView(generics.ListAPIView):
    serializer_class = UssdSessionLogSerializer
    permission_classes = [IsAdminOrSupervisor]
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "session_id", "phone_number"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = UssdSessionLog.objects.select_related("ward").all().order_by("-created_at")
        user = self.request.user
        ward_id = self.request.query_params.get("ward_id")
        session_id = self.request.query_params.get("session_id")
        phone_number = self.request.query_params.get("phone_number")
        queryset = apply_ward_scope_or_none(queryset, user)

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if phone_number:
            queryset = queryset.filter(phone_number=phone_number)
        return queryset
