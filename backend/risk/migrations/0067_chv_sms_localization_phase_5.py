# Generated manually for child plan 11 phase 5 on 2026-05-04

from django.db import migrations, models
from django.utils import timezone


SUPPORTED_LANGUAGES = ("en", "sw", "luo")
DEFAULT_LANGUAGE = "en"
MESSAGE_GOVERNANCE_SCHEMA_VERSION = "message-governance-phase-0-5-v1"

CHV_SMS_TEMPLATE_REGISTRY = {
    "cholera.alert.chv.high_risk_sms": {
        "title": {
            "en": "High-risk CHV alert SMS",
            "sw": "SMS ya tahadhari ya hatari kubwa kwa CHV",
            "luo": "SMS mar siem maduong' ne CHV",
        },
        "owner": "county_public_health_operations",
        "risk_level": "high",
        "placeholders": ["ward_name", "predicted_cases"],
        "body": {
            "en": (
                "CHVs: {ward_name} is high risk with {predicted_cases} predicted cases. "
                "Review field conditions and report urgent changes."
            ),
            "sw": (
                "CHVs: {ward_name} iko hatari kubwa na visa {predicted_cases} vinavyotabiriwa. "
                "Kagua hali ya eneo na uripoti mabadiliko ya dharura."
            ),
            "luo": (
                "CHVs: {ward_name} nitie e chandruok maduong' gi cases {predicted_cases} ma oket e paro. "
                "Ne ane piny kendo nyis lokruok mapoth."
            ),
        },
    },
    "cholera.chv.workflow_check_in_sms": {
        "title": {
            "en": "CHV workflow check-in SMS",
            "sw": "SMS ya ukaguzi wa mtiririko wa kazi wa CHV",
            "luo": "SMS mar penjruok mar tic ne CHV",
        },
        "owner": "ward_supervisor",
        "risk_level": "medium",
        "placeholders": ["ward_name"],
        "body": {
            "en": "Please confirm field readiness for {ward_name} and report urgent cholera concerns.",
            "sw": "Tafadhali thibitisha utayari wa eneo la {ward_name} na uripoti wasiwasi wa dharura wa kipindupindu.",
            "luo": "Kiyie mondo imok ikruok mar tic e {ward_name} kendo inyis wach cholera mapoth.",
        },
    },
}


def _seed_template(MessageTemplate, *, template_key, language, source_template_id, reviewed_at):
    definition = CHV_SMS_TEMPLATE_REGISTRY[template_key]
    MessageTemplate.objects.update_or_create(
        template_key=template_key,
        language=language,
        version=1,
        defaults={
            "audience_type": "chv",
            "channel": "sms",
            "title": definition["title"][language],
            "body": definition["body"][language],
            "placeholders": definition["placeholders"],
            "approval_status": "approved",
            "approved_at": reviewed_at,
            "retired_at": None,
            "translation_status": "approved",
            "source_template_id": source_template_id,
            "translation_reviewed_at": reviewed_at,
            "translation_review_notes": "Seeded approved phase 5 CHV SMS localization template.",
            "owner": definition["owner"],
            "risk_level": definition["risk_level"],
            "public_health_caveats": "Approved cholera public-health operational copy for CHV SMS delivery.",
            "lineage_metadata": {
                "seeded_by": "risk.0067_chv_sms_localization_phase_5",
                "schema_version": MESSAGE_GOVERNANCE_SCHEMA_VERSION,
                "language": language,
                "source_language": DEFAULT_LANGUAGE if language != DEFAULT_LANGUAGE else "",
            },
        },
    )


def seed_chv_sms_templates(apps, schema_editor):
    MessageTemplate = apps.get_model("risk", "MessageTemplate")
    reviewed_at = timezone.now()
    for template_key in CHV_SMS_TEMPLATE_REGISTRY:
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


def retire_seeded_chv_sms_templates(apps, schema_editor):
    MessageTemplate = apps.get_model("risk", "MessageTemplate")
    MessageTemplate.objects.filter(
        template_key__in=list(CHV_SMS_TEMPLATE_REGISTRY),
        language__in=SUPPORTED_LANGUAGES[1:],
        version=1,
    ).update(
        approval_status="retired",
        retired_at=timezone.now(),
        translation_status="retired",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0066_ussd_multilingual_phase_4"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="fallback_used",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="alert",
            name="requested_language",
            field=models.CharField(default=DEFAULT_LANGUAGE, max_length=20),
        ),
        migrations.AddField(
            model_name="alert",
            name="resolved_language",
            field=models.CharField(
                choices=[("en", "English"), ("sw", "Kiswahili"), ("luo", "Dholuo")],
                default=DEFAULT_LANGUAGE,
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="chvmessage",
            name="fallback_used",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="chvmessage",
            name="requested_language",
            field=models.CharField(default=DEFAULT_LANGUAGE, max_length=20),
        ),
        migrations.AddField(
            model_name="chvmessage",
            name="resolved_language",
            field=models.CharField(
                choices=[("en", "English"), ("sw", "Kiswahili"), ("luo", "Dholuo")],
                default=DEFAULT_LANGUAGE,
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["resolved_language", "created_at"], name="risk_alert_reslang_idx"),
        ),
        migrations.AddIndex(
            model_name="chvmessage",
            index=models.Index(fields=["resolved_language", "created_at"], name="risk_chvmsg_reslang_idx"),
        ),
        migrations.AddConstraint(
            model_name="alert",
            constraint=models.CheckConstraint(
                check=models.Q(resolved_language__in=SUPPORTED_LANGUAGES),
                name="risk_alert_reslang_supported",
            ),
        ),
        migrations.AddConstraint(
            model_name="chvmessage",
            constraint=models.CheckConstraint(
                check=models.Q(resolved_language__in=SUPPORTED_LANGUAGES),
                name="risk_chvmsg_reslang_supported",
            ),
        ),
        migrations.RunPython(seed_chv_sms_templates, retire_seeded_chv_sms_templates),
    ]
