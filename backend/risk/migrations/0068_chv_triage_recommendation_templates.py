# Generated manually for child plan 11 hostile audit hardening on 2026-05-05

from django.db import migrations
from django.utils import timezone


SUPPORTED_LANGUAGES = ("en", "sw", "luo")
DEFAULT_LANGUAGE = "en"
MESSAGE_GOVERNANCE_SCHEMA_VERSION = "message-governance-phase-0-7-v1"

CHV_TRIAGE_RECOMMENDATION_TEMPLATE_REGISTRY = {
    "cholera.chv.triage.urgent_referral_offline": {
        "recommendation_key": "urgent_referral",
        "title": {
            "en": "Refer now",
            "sw": "Mpeleke sasa",
            "luo": "Ter sani",
        },
        "body": {
            "en": "Dehydration signs need facility review.",
            "sw": "Dalili za upungufu wa maji zinahitaji huduma ya kituo.",
            "luo": "Ranyisi remo pi dwar bedo e od thieth.",
        },
    },
    "cholera.chv.triage.facility_assessment_offline": {
        "recommendation_key": "facility_assessment",
        "title": {
            "en": "Facility check",
            "sw": "Ukaguzi wa kituo",
            "luo": "Nen e od thieth",
        },
        "body": {
            "en": "Symptoms match the escalation rule.",
            "sw": "Dalili zinaendana na kanuni ya kuongezeka kwa hatari.",
            "luo": "Ranyisi rwate kod chik mar medo wach malo.",
        },
    },
    "cholera.chv.triage.ors_and_prevention_offline": {
        "recommendation_key": "ors_and_prevention",
        "title": {
            "en": "ORS and prevention",
            "sw": "ORS na kinga",
            "luo": "ORS kod geng'o",
        },
        "body": {
            "en": "Give ORS advice and reinforce safe water.",
            "sw": "Toa ushauri wa ORS na sisitiza maji salama.",
            "luo": "Mi puonj mar ORS kendo tem pi maber.",
        },
    },
    "cholera.chv.triage.record_symptoms_offline": {
        "recommendation_key": "record_symptoms",
        "title": {
            "en": "Record symptoms",
            "sw": "Rekodi dalili",
            "luo": "Ndik ranyisi",
        },
        "body": {
            "en": "Select what is present before saving.",
            "sw": "Chagua kilichopo kabla ya kuhifadhi.",
            "luo": "Yier gima nitie kapok ikan.",
        },
    },
}


def _seed_template(MessageTemplate, *, template_key, language, source_template_id, reviewed_at):
    definition = CHV_TRIAGE_RECOMMENDATION_TEMPLATE_REGISTRY[template_key]
    MessageTemplate.objects.update_or_create(
        template_key=template_key,
        language=language,
        version=1,
        defaults={
            "audience_type": "chv",
            "channel": "offline_chv_bundle",
            "title": definition["title"][language],
            "body": definition["body"][language],
            "placeholders": [],
            "approval_status": "approved",
            "approved_at": reviewed_at,
            "retired_at": None,
            "translation_status": "approved",
            "source_template_id": source_template_id,
            "translation_reviewed_at": reviewed_at,
            "translation_review_notes": "Seeded approved CHV offline triage recommendation copy.",
            "owner": "county_health_promotion",
            "risk_level": "high",
            "public_health_caveats": (
                "Approved cholera public-health triage recommendation copy for offline CHV decision support."
            ),
            "lineage_metadata": {
                "seeded_by": "risk.0068_chv_triage_recommendation_templates",
                "schema_version": MESSAGE_GOVERNANCE_SCHEMA_VERSION,
                "language": language,
                "source_language": DEFAULT_LANGUAGE if language != DEFAULT_LANGUAGE else "",
                "recommendation_key": definition["recommendation_key"],
            },
        },
    )


def seed_chv_triage_recommendation_templates(apps, schema_editor):
    MessageTemplate = apps.get_model("risk", "MessageTemplate")
    reviewed_at = timezone.now()
    for template_key in CHV_TRIAGE_RECOMMENDATION_TEMPLATE_REGISTRY:
        _seed_template(
            MessageTemplate,
            template_key=template_key,
            language=DEFAULT_LANGUAGE,
            source_template_id=None,
            reviewed_at=reviewed_at,
        )
        source = MessageTemplate.objects.get(template_key=template_key, language=DEFAULT_LANGUAGE, version=1)
        for language in SUPPORTED_LANGUAGES[1:]:
            _seed_template(
                MessageTemplate,
                template_key=template_key,
                language=language,
                source_template_id=source.id,
                reviewed_at=reviewed_at,
            )


def retire_chv_triage_recommendation_templates(apps, schema_editor):
    MessageTemplate = apps.get_model("risk", "MessageTemplate")
    MessageTemplate.objects.filter(
        template_key__in=list(CHV_TRIAGE_RECOMMENDATION_TEMPLATE_REGISTRY),
        language__in=SUPPORTED_LANGUAGES,
        version=1,
    ).update(
        approval_status="retired",
        retired_at=timezone.now(),
        translation_status="retired",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0067_chv_sms_localization_phase_5"),
    ]

    operations = [
        migrations.RunPython(seed_chv_triage_recommendation_templates, retire_chv_triage_recommendation_templates),
    ]
