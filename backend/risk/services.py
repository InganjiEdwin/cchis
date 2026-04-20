from django.utils import timezone
from .models import Alert, CHV, RiskScore, Ward
from django.utils import timezone
from .models import Alert, CHV, RiskScore, TriageSession, Ward


def build_alert_message(ward: Ward, risk_score: RiskScore) -> str:
    return (
        f"Cholera early warning for {ward.name}. "
        f"Risk level: {risk_score.risk_level}. "
        f"Predicted cases: {risk_score.predicted_cases}. "
        f"Advise households on safe water, hygiene, and early referral."
    )


def send_sms_stub(phone_number: str, message: str) -> dict:
    return {
        "success": True,
        "external_id": f"stub-{phone_number}-{timezone.now().timestamp()}",
        "error": "",
    }


def trigger_alerts_for_riskscore(risk_score: RiskScore, send_sms: bool = False) -> list[Alert]:
    ward = risk_score.ward
    alerts_created = []

    dashboard_alert = Alert.objects.create(
        ward=ward,
        risk_score=risk_score,
        channel=Alert.CHANNEL_DASHBOARD,
        recipient="dashboard",
        message=build_alert_message(ward, risk_score),
        status=Alert.STATUS_SENT,
        sent_at=timezone.now(),
    )
    alerts_created.append(dashboard_alert)

    if send_sms:
        chvs = CHV.objects.filter(ward=ward, is_active=True)
        for chv in chvs:
            message = build_alert_message(ward, risk_score)
            result = send_sms_stub(chv.phone_number, message)

            alert = Alert.objects.create(
                ward=ward,
                risk_score=risk_score,
                channel=Alert.CHANNEL_SMS,
                recipient=chv.phone_number,
                message=message,
                status=Alert.STATUS_SENT if result["success"] else Alert.STATUS_FAILED,
                external_id=result["external_id"],
                sent_at=timezone.now() if result["success"] else None,
                error_message=result["error"],
            )
            alerts_created.append(alert)

    return alerts_created


def latest_riskscore_for_ward(ward: Ward) -> RiskScore | None:
    return ward.risk_scores.order_by("-generated_at").first()


def generate_triage_recommendation(
    ward: Ward,
    diarrhea: bool,
    vomiting: bool,
    dehydration: bool,
    fever: bool,
) -> tuple[str, bool]:
    ward_risk = ward.current_risk_level

    if diarrhea and vomiting and dehydration:
        if ward_risk == Ward.RISK_HIGH:
            return (
                "High cholera suspicion. Start ORS immediately, assess dehydration urgently, "
                "refer to nearest health facility now, and alert supervisor.",
                True,
            )
        return (
            "Severe diarrhea case. Start ORS immediately, assess dehydration, and refer to a health facility urgently.",
            True,
        )

    if diarrhea and dehydration:
        return (
            "Possible acute watery diarrhea with dehydration. Start ORS, monitor closely, and refer if symptoms worsen.",
            True,
        )

    if diarrhea and vomiting:
        return (
            "Possible diarrheal illness. Give ORS, reinforce safe water and hygiene guidance, and monitor closely.",
            False,
        )

    if fever and ward_risk == Ward.RISK_HIGH:
        return (
            "Fever reported in high-risk ward. Assess for malaria and diarrheal symptoms, advise prompt testing and follow-up.",
            False,
        )

    if diarrhea:
        return (
            "Provide ORS, advise safe water use, handwashing, and monitor for worsening symptoms or dehydration signs.",
            False,
        )

    return (
        "No immediate cholera danger signs identified. Continue observation, reinforce prevention messaging, and follow routine guidance.",
        False,
    )


def create_triage_session(
    ward: Ward,
    phone_number: str,
    diarrhea: bool,
    vomiting: bool,
    dehydration: bool,
    fever: bool,
    text_input: str = "",
    channel: str = "USSD",
) -> TriageSession:
    recommendation, referral_needed = generate_triage_recommendation(
        ward=ward,
        diarrhea=diarrhea,
        vomiting=vomiting,
        dehydration=dehydration,
        fever=fever,
    )

    return TriageSession.objects.create(
        channel=channel,
        phone_number=phone_number,
        ward=ward,
        text_input=text_input,
        diarrhea=diarrhea,
        vomiting=vomiting,
        dehydration=dehydration,
        fever=fever,
        recommendation=recommendation,
        referral_needed=referral_needed,
    )


def build_alert_message(ward: Ward, risk_score: RiskScore) -> str:
    return (
        f"Cholera early warning for {ward.name}. "
        f"Risk level: {risk_score.risk_level}. "
        f"Predicted cases: {risk_score.predicted_cases}. "
        f"Advise households on safe water, hygiene, and early referral."
    )


def send_sms_stub(phone_number: str, message: str) -> dict:
    return {
        "success": True,
        "external_id": f"stub-{phone_number}-{timezone.now().timestamp()}",
        "error": "",
    }


def trigger_alerts_for_riskscore(risk_score: RiskScore, send_sms: bool = False) -> list[Alert]:
    ward = risk_score.ward
    alerts_created = []

    dashboard_alert = Alert.objects.create(
        ward=ward,
        risk_score=risk_score,
        channel=Alert.CHANNEL_DASHBOARD,
        recipient="dashboard",
        message=build_alert_message(ward, risk_score),
        status=Alert.STATUS_SENT,
        sent_at=timezone.now(),
    )
    alerts_created.append(dashboard_alert)

    if send_sms:
        chvs = CHV.objects.filter(ward=ward, is_active=True)
        for chv in chvs:
            message = build_alert_message(ward, risk_score)
            result = send_sms_stub(chv.phone_number, message)

            alert = Alert.objects.create(
                ward=ward,
                risk_score=risk_score,
                channel=Alert.CHANNEL_SMS,
                recipient=chv.phone_number,
                message=message,
                status=Alert.STATUS_SENT if result["success"] else Alert.STATUS_FAILED,
                external_id=result["external_id"],
                sent_at=timezone.now() if result["success"] else None,
                error_message=result["error"],
            )
            alerts_created.append(alert)

    return alerts_created


def latest_riskscore_for_ward(ward: Ward) -> RiskScore | None:
    return ward.risk_scores.order_by("-generated_at").first()
