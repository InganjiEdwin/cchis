from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Alert, CHV, RiskScore, Ward
from .serializers import (
    AlertSerializer,
    CHVSerializer,
    RiskScoreSerializer,
    TriggerAlertRequestSerializer,
    WardSerializer,
)
from .services import latest_riskscore_for_ward, trigger_alerts_for_riskscore
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Alert, CHV, RiskScore, Ward
from .serializers import (
    AlertSerializer,
    CHVSerializer,
    RiskScoreSerializer,
    TriggerAlertRequestSerializer,
    WardSerializer,
)
from .services import latest_riskscore_for_ward, trigger_alerts_for_riskscore


class WardListAPIView(generics.ListAPIView):
    queryset = Ward.objects.filter(is_active=True).order_by("name")
    serializer_class = WardSerializer


class CHVListAPIView(generics.ListAPIView):
    queryset = CHV.objects.filter(is_active=True).select_related("ward").order_by("name")
    serializer_class = CHVSerializer


class RiskScoreListAPIView(generics.ListAPIView):
    serializer_class = RiskScoreSerializer

    def get_queryset(self):
        queryset = RiskScore.objects.select_related("ward").all()
        ward_id = self.request.query_params.get("ward_id")
        risk_level = self.request.query_params.get("risk_level")

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if risk_level:
            queryset = queryset.filter(risk_level=risk_level.upper())

        return queryset.order_by("-generated_at")


class LatestWardRiskAPIView(APIView):
    def get(self, request):
        results = []
        wards = Ward.objects.filter(is_active=True).order_by("name")

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
    queryset = Alert.objects.select_related("ward", "risk_score").all().order_by("-created_at")
    serializer_class = AlertSerializer


class TriggerAlertsAPIView(APIView):
    def post(self, request):
        serializer = TriggerAlertRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ward_id = serializer.validated_data.get("ward_id")
        requested_risk_level = serializer.validated_data.get("risk_level")
        send_sms = serializer.validated_data.get("send_sms", False)

        queryset = RiskScore.objects.select_related("ward").all()

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

        alerts = trigger_alerts_for_riskscore(risk_score, send_sms=send_sms)

        return Response(
            {
                "message": "Alerts triggered successfully.",
                "risk_score_id": risk_score.id,
                "alerts_created": len(alerts),
                "alerts": AlertSerializer(alerts, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class CHVTriageAPIView(APIView):
    def post(self, request):
        ward_id = request.data.get("ward_id")
        symptoms = {
            "diarrhea": bool(request.data.get("diarrhea", False)),
            "vomiting": bool(request.data.get("vomiting", False)),
            "dehydration": bool(request.data.get("dehydration", False)),
            "fever": bool(request.data.get("fever", False)),
            "blood_in_stool": bool(request.data.get("blood_in_stool", False)),
        }

        if not ward_id:
            return Response(
                {"detail": "ward_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ward = Ward.objects.get(id=ward_id, is_active=True)
        except Ward.DoesNotExist:
            return Response(
                {"detail": "Ward not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        latest_risk = latest_riskscore_for_ward(ward)
        ward_risk_level = latest_risk.risk_level if latest_risk else ward.current_risk_level

        suspected_condition = "General diarrheal illness"
        urgency = "MEDIUM"
        actions = [
            "Advise caregiver on safe water and handwashing",
            "Monitor child closely",
        ]
        refer = False

        cholera_pattern = (
            symptoms["diarrhea"] and symptoms["vomiting"]
        ) or (
            symptoms["diarrhea"] and symptoms["dehydration"]
        )

        if cholera_pattern and ward_risk_level == Ward.RISK_HIGH:
            suspected_condition = "Suspected cholera"
            urgency = "HIGH"
            actions = [
                "Begin oral rehydration immediately",
                "Refer child to nearest health facility urgently",
                "Advise caregiver to use safe or treated water",
                "Report suspected case to supervisor",
            ]
            refer = True
        elif symptoms["diarrhea"] and symptoms["dehydration"]:
            suspected_condition = "Acute watery diarrhea with dehydration"
            urgency = "HIGH"
            actions = [
                "Begin oral rehydration immediately",
                "Refer child to nearest health facility",
                "Monitor for worsening dehydration",
            ]
            refer = True
        elif symptoms["fever"] and ward_risk_level in [Ward.RISK_MEDIUM, Ward.RISK_HIGH]:
            suspected_condition = "Fever in climate-sensitive risk area"
            urgency = "MEDIUM"
            actions = [
                "Check for danger signs",
                "Refer for malaria or other febrile illness assessment if symptoms persist",
                "Continue household prevention advice",
            ]

        if symptoms["blood_in_stool"]:
            suspected_condition = "Diarrheal illness with danger sign"
            urgency = "HIGH"
            actions = [
                "Refer immediately to health facility",
                "Begin supportive care if available",
                "Report case urgently",
            ]
            refer = True

        response = {
            "ward_id": ward.id,
            "ward_name": ward.name,
            "ward_risk_level": ward_risk_level,
            "suspected_condition": suspected_condition,
            "urgency": urgency,
            "refer_to_facility": refer,
            "actions": actions,
        }

        return Response(response, status=status.HTTP_200_OK)


class USSDMenuAPIView(APIView):
    """
    Simple USSD-compatible flow.
    Accepts:
    - session_id
    - phone_number
    - text

    Returns:
    - CON ... to continue session
    - END ... to end session

    Example flow:
    "" -> main menu
    "1" -> flood advice
    "2" -> child diarrhea advice
    "2*1" -> severe diarrhea/dehydration
    """

    def post(self, request):
        text = (request.data.get("text") or "").strip()

        if text == "":
            return Response(
                {
                    "response": (
                        "CON Welcome to CCHIS Health Menu\n"
                        "1. Flood safety advice\n"
                        "2. Child diarrhea support\n"
                        "3. Heat health advice"
                    )
                }
            )

        if text == "1":
            return Response(
                {
                    "response": (
                        "END Flood safety:\n"
                        "Use treated water, avoid flood water, wash hands often, "
                        "and seek care if child has diarrhea or vomiting."
                    )
                }
            )

        if text == "2":
            return Response(
                {
                    "response": (
                        "CON Child diarrhea support\n"
                        "1. Diarrhea with vomiting or dehydration\n"
                        "2. Mild diarrhea only"
                    )
                }
            )

        if text == "2*1":
            return Response(
                {
                    "response": (
                        "END Give ORS immediately and go to nearest health facility now. "
                        "Use safe water and report to CHV if available."
                    )
                }
            )

        if text == "2*2":
            return Response(
                {
                    "response": (
                        "END Give ORS, continue fluids, monitor closely, and seek care if child worsens."
                    )
                }
            )

        if text == "3":
            return Response(
                {
                    "response": (
                        "END Heat advice:\n"
                        "Give water often, keep child in shade, avoid midday sun, "
                        "and seek care for weakness or confusion."
                    )
                }
            )

        return Response(
            {
                "response": (
                    "END Invalid option. Please try again."
                )
            }
        )


class WardListAPIView(generics.ListAPIView):
    queryset = Ward.objects.filter(is_active=True).order_by("name")
    serializer_class = WardSerializer


class CHVListAPIView(generics.ListAPIView):
    queryset = CHV.objects.filter(is_active=True).select_related("ward").order_by("name")
    serializer_class = CHVSerializer


class RiskScoreListAPIView(generics.ListAPIView):
    serializer_class = RiskScoreSerializer

    def get_queryset(self):
        queryset = RiskScore.objects.select_related("ward").all()
        ward_id = self.request.query_params.get("ward_id")
        risk_level = self.request.query_params.get("risk_level")

        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)
        if risk_level:
            queryset = queryset.filter(risk_level=risk_level.upper())

        return queryset.order_by("-generated_at")


class LatestWardRiskAPIView(APIView):
    def get(self, request):
        results = []
        wards = Ward.objects.filter(is_active=True).order_by("name")

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
    queryset = Alert.objects.select_related("ward", "risk_score").all().order_by("-created_at")
    serializer_class = AlertSerializer


class TriggerAlertsAPIView(APIView):
    def post(self, request):
        serializer = TriggerAlertRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ward_id = serializer.validated_data.get("ward_id")
        requested_risk_level = serializer.validated_data.get("risk_level")
        send_sms = serializer.validated_data.get("send_sms", False)

        queryset = RiskScore.objects.select_related("ward").all()

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

        alerts = trigger_alerts_for_riskscore(risk_score, send_sms=send_sms)

        return Response(
            {
                "message": "Alerts triggered successfully.",
                "risk_score_id": risk_score.id,
                "alerts_created": len(alerts),
                "alerts": AlertSerializer(alerts, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )
