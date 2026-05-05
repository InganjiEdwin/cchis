# Generated manually for child plan 11 hostile audit hardening on 2026-05-05

from django.db import migrations
from django.utils import timezone


SUPPORTED_LANGUAGES = ("en", "sw", "luo")
DEFAULT_LANGUAGE = "en"
MESSAGE_GOVERNANCE_SCHEMA_VERSION = "message-governance-phase-0-7-v1"

CHV_OFFLINE_GUIDANCE_TEMPLATE_REGISTRY = {
    "cholera.household.prevention_guidance_offline_bundle": {
        "title": {
            "en": "Household prevention guidance",
            "sw": "Mwongozo wa kinga kwa kaya",
            "luo": "Puonj mar geng'o e ot",
        },
        "body": {
            "en": (
                "Use treated water, wash hands with soap, prepare ORS for diarrhea, "
                "and seek care quickly for dehydration."
            ),
            "sw": (
                "Tumia maji yaliyotibiwa, nawa mikono kwa sabuni, andaa ORS kwa kuharisha, "
                "na tafuta huduma haraka kwa upungufu wa maji."
            ),
            "luo": (
                "Ti gi pi mothiedhi, luok lweti gi sabun, ik ORS ka nitie lweyo, "
                "kendo dwar thieth mapiyo ka nitie remo pi."
            ),
        },
    },
}


def _seed_template(MessageTemplate, *, template_key, language, source_template_id, reviewed_at):
    definition = CHV_OFFLINE_GUIDANCE_TEMPLATE_REGISTRY[template_key]
    MessageTemplate.objects.update_or_create(
        template_key=template_key,
        language=language,
        version=1,
        defaults={
            "audience_type": "household",
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
            "translation_review_notes": "Seeded approved CHV offline household prevention guidance copy.",
            "owner": "county_health_promotion",
            "risk_level": "high",
            "public_health_caveats": "Approved cholera public-health guidance for offline CHV household visits.",
            "lineage_metadata": {
                "seeded_by": "risk.0069_chv_offline_guidance_templates",
                "schema_version": MESSAGE_GOVERNANCE_SCHEMA_VERSION,
                "language": language,
                "source_language": DEFAULT_LANGUAGE if language != DEFAULT_LANGUAGE else "",
            },
        },
    )


def seed_chv_offline_guidance_templates(apps, schema_editor):
    MessageTemplate = apps.get_model("risk", "MessageTemplate")
    reviewed_at = timezone.now()
    for template_key in CHV_OFFLINE_GUIDANCE_TEMPLATE_REGISTRY:
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


def retire_chv_offline_guidance_templates(apps, schema_editor):
    MessageTemplate = apps.get_model("risk", "MessageTemplate")
    MessageTemplate.objects.filter(
        template_key__in=list(CHV_OFFLINE_GUIDANCE_TEMPLATE_REGISTRY),
        language__in=SUPPORTED_LANGUAGES,
        version=1,
    ).update(
        approval_status="retired",
        retired_at=timezone.now(),
        translation_status="retired",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0068_chv_triage_recommendation_templates"),
    ]

    operations = [
        migrations.RunPython(seed_chv_offline_guidance_templates, retire_chv_offline_guidance_templates),
    ]
