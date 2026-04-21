from rest_framework import generics, permissions, status
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsAdminOrSupervisor, IsOperationalUser

from .tasks import trigger_alerts_task

from .models import Alert, CHV, RiskScore, UssdSessionLog, Ward
from .serializers import (
    AlertSerializer,
    CHVSerializer,
    CHVSyncRequestSerializer,
    CHVTriageRequestSerializer,
    CHVTriageResponseSerializer,
    RiskScoreSerializer,
    TriggerAlertRequestSerializer,
    UssdSessionLogSerializer,
    WardSerializer,
)
from .services import (
    create_triage_session,
    latest_riskscore_for_ward,
    process_sync_payload,
)


def parse_bool_query_param(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None


class WardListAPIView(generics.ListAPIView):
    serializer_class = WardSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [OrderingFilter]
    ordering_fields = ["name", "county", "sub_county", "updated_at", "current_risk_score"]
    ordering = ["name"]

    def get_queryset(self):
        queryset = Ward.objects.filter(is_active=True).order_by("name")
        user = self.request.user
        county = self.request.query_params.get("county")
        sub_county = self.request.query_params.get("sub_county")
        is_active = parse_bool_query_param(self.request.query_params.get("is_active"))

        if user.role in [User.ROLE_ADMIN, User.ROLE_ANALYST]:
            pass
        elif user.ward_id:
            queryset = queryset.filter(id=user.ward_id)
        else:
            return queryset.none()

        if county:
            queryset = queryset.filter(county__iexact=county.strip())
        if sub_county:
            queryset = queryset.filter(sub_county__iexact=sub_county.strip())
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset


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

        if user.role == User.ROLE_ADMIN:
            pass
        elif user.ward_id:
            queryset = queryset.filter(ward_id=user.ward_id)
        else:
            return queryset.none()

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset


class RiskScoreListAPIView(generics.ListAPIView):
    serializer_class = RiskScoreSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [OrderingFilter]
    ordering_fields = ["generated_at", "score", "risk_level", "predicted_cases", "ward__name"]
    ordering = ["-generated_at"]

    def get_queryset(self):
        queryset = RiskScore.objects.select_related("ward").all()
        ward_id = self.request.query_params.get("ward_id")
        risk_level = self.request.query_params.get("risk_level")
        source = self.request.query_params.get("source")
        user = self.request.user

        if user.role not in [User.ROLE_ADMIN, User.ROLE_ANALYST]:
            if not user.ward_id:
                return queryset.none()
            queryset = queryset.filter(ward_id=user.ward_id)

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if risk_level:
            queryset = queryset.filter(risk_level=risk_level.upper())
        if source:
            queryset = queryset.filter(source=source.upper())

        return queryset.order_by("-generated_at")


class LatestWardRiskAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        results = []
        wards = Ward.objects.filter(is_active=True).order_by("name")
        user = request.user

        if user.role not in [User.ROLE_ADMIN, User.ROLE_ANALYST]:
            if not user.ward_id:
                wards = Ward.objects.none()
            else:
                wards = wards.filter(id=user.ward_id)

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
    permission_classes = [IsAdminOrSupervisor]
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "sent_at", "channel", "status", "ward__name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Alert.objects.select_related("ward", "risk_score").all().order_by("-created_at")
        user = self.request.user
        ward_id = self.request.query_params.get("ward_id")
        channel = self.request.query_params.get("channel")
        status_value = self.request.query_params.get("status")

        if user.role == User.ROLE_ADMIN:
            pass
        elif user.ward_id:
            queryset = queryset.filter(ward_id=user.ward_id)
        else:
            return queryset.none()

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if channel:
            queryset = queryset.filter(channel=channel.upper())
        if status_value:
            queryset = queryset.filter(status=status_value.upper())
        return queryset


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
            if not user.ward_id:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(ward_id=user.ward_id)

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if requested_risk_level:
            queryset = queryset.filter(risk_level=requested_risk_level)

        risk_score = queryset.order_by("-generated_at").first()
        if not risk_score:
            return Response(
                {"detail": "No matching risk score found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        task = trigger_alerts_task.delay(risk_score.id, send_sms=send_sms)

        return Response(
            {
                "message": "Alert task queued successfully.",
                "risk_score_id": risk_score.id,
                "task_id": task.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class CHVTriageAPIView(APIView):
    permission_classes = [IsOperationalUser]

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
    permission_classes = [IsOperationalUser]

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

        if user.role == User.ROLE_ADMIN:
            pass
        elif user.ward_id:
            queryset = queryset.filter(ward_id=user.ward_id)
        else:
            return queryset.none()

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if phone_number:
            queryset = queryset.filter(phone_number=phone_number)
        return queryset
