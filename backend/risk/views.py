import logging

from rest_framework import generics, permissions, status
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsAdminOrSupervisor, IsAdminSupervisorOrAnalyst, IsFieldOperator

from .tasks import trigger_alerts_task

from .models import Alert, CHV, HealthFacility, RiskScore, UssdSessionLog, Ward
from .map_data import build_migori_ward_map_summary
from .serializers import (
    AlertIntelligenceSerializer,
    AlertSerializer,
    CHVSerializer,
    CHVOperationsSerializer,
    CHVSyncRequestSerializer,
    CHVTriageRequestSerializer,
    CHVTriageResponseSerializer,
    HealthFacilitySerializer,
    RiskScoreSerializer,
    TriggerAlertRequestSerializer,
    UssdSessionLogSerializer,
    WardDetailSerializer,
    WardIntelligenceSerializer,
    WardSerializer,
)
from .services import (
    build_alert_intelligence_snapshot,
    build_chv_operations_snapshot,
    build_ward_intelligence_snapshot,
    create_triage_session,
    latest_riskscore_for_ward,
    process_sync_payload,
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


def user_has_broad_dashboard_scope(user: User) -> bool:
    return user.role in [User.ROLE_ADMIN, User.ROLE_ANALYST]


def apply_ward_scope_or_none(queryset, user: User, field_name: str = "ward_id"):
    if user_has_broad_dashboard_scope(user):
        return queryset

    if not user.ward_id:
        return queryset.none()

    return queryset.filter(**{field_name: user.ward_id})


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
        payload = build_chv_operations_snapshot(scoped_queryset)
        serializer = CHVOperationsSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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


class HealthFacilityDetailAPIView(generics.RetrieveAPIView):
    serializer_class = HealthFacilitySerializer
    permission_classes = [IsAdminSupervisorOrAnalyst]

    def get_queryset(self):
        queryset = HealthFacility.objects.filter(is_active=True).select_related("ward")
        return apply_ward_scope_or_none(queryset, self.request.user)


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
        user = self.request.user
        queryset = apply_ward_scope_or_none(queryset, user)

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if risk_level:
            queryset = queryset.filter(risk_level=risk_level.upper())
        if source:
            queryset = queryset.filter(source=source.upper())

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
        queryset = apply_ward_scope_or_none(queryset, user)

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if channel:
            queryset = queryset.filter(channel=channel.upper())
        if status_value:
            queryset = queryset.filter(status=status_value.upper())
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


class TriggerAlertsAPIView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request):
        serializer = TriggerAlertRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ward_id = serializer.validated_data.get("ward_id")
        requested_risk_level = serializer.validated_data.get("risk_level")
        send_sms = serializer.validated_data.get("send_sms", False)

        queryset = RiskScore.objects.select_related("ward").all()
        user = request.user
        if user.role != User.ROLE_ADMIN:
            queryset = apply_ward_scope_or_none(queryset, user)

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if requested_risk_level:
            queryset = queryset.filter(risk_level=requested_risk_level)

        risk_score = queryset.order_by("-generated_at").first()
        if not risk_score:
            alerts_logger.warning(
                "alert_trigger_request_rejected",
                extra={
                    "actor_user_id": user.id,
                    "actor_role": user.role,
                    "requested_ward_id": ward_id,
                    "requested_risk_level": requested_risk_level,
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

        task = trigger_alerts_task.delay(risk_score.id, send_sms=send_sms)
        alerts_logger.info(
            "alert_trigger_request_queued",
            extra={
                "actor_user_id": user.id,
                "actor_role": user.role,
                "effective_ward_id": risk_score.ward_id,
                "risk_score_id": risk_score.id,
                "requested_ward_id": ward_id,
                "requested_risk_level": requested_risk_level,
                "send_sms": send_sms,
                "task_id": task.id,
                "request_path": request.path,
                "request_method": request.method,
            },
        )

        return Response(
            {
                "message": "Alert task queued successfully.",
                "risk_score_id": risk_score.id,
                "task_id": task.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


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
