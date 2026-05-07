# Generated manually on 2026-05-07

from copy import deepcopy

from django.db import migrations
from django.utils import timezone


USSD_MENU_KEY = "cholera_health_menu"
USSD_BUILTIN_VERSION_LABEL = "builtin-v1"
USSD_SCHEMA_VERSION = "ussd-menu-governance-phase-4-v1"
USSD_SAFE_FALLBACK_COPY = "END Invalid option. Please try again."
USSD_SESSION_OUTCOME_TAXONOMY = {
    "STARTED": "Session reached the root menu.",
    "IN_PROGRESS": "Session is inside a non-terminal menu branch.",
    "COMPLETED": "Session reached a terminal health guidance response.",
    "INVALID_INPUT": "Session submitted a route not present in the active menu tree.",
    "ABANDONED_INFERRED": "Prior non-terminal interaction was inferred abandoned by a restart.",
    "SAFE_FALLBACK": "Session received the configured safe fallback copy.",
}
DEFAULT_USSD_MENU_TREE = {
    "routes": {
        "": "root",
        "1": "flood_safety",
        "2": "diarrhea_menu",
        "2*1": "diarrhea_urgent",
        "2*2": "diarrhea_mild",
        "3": "heat_advice",
    },
    "nodes": {
        "root": {
            "response_type": "CON",
            "body": "Welcome to CCHIS Health Menu\n1. Flood safety advice\n2. Child diarrhea support\n3. Heat health advice",
        },
        "flood_safety": {
            "response_type": "END",
            "body": (
                "Flood safety:\nUse treated water, avoid flood water, wash hands often, "
                "and seek care if child has diarrhea or vomiting."
            ),
        },
        "diarrhea_menu": {
            "response_type": "CON",
            "body": "Child diarrhea support\n1. Diarrhea with vomiting or dehydration\n2. Mild diarrhea only",
        },
        "diarrhea_urgent": {
            "response_type": "END",
            "body": "Give ORS immediately and go to nearest health facility now. Use safe water and report to CHV if available.",
        },
        "diarrhea_mild": {
            "response_type": "END",
            "body": "Give ORS, continue fluids, monitor closely, and seek care if child worsens.",
        },
        "heat_advice": {
            "response_type": "END",
            "body": "Heat advice:\nGive water often, keep child in shade, avoid midday sun, and seek care for weakness or confusion.",
        },
    },
}


def ensure_active_english_ussd_menu(apps, schema_editor):
    UssdMenuVersion = apps.get_model("risk", "UssdMenuVersion")
    reviewed_at = timezone.now()

    UssdMenuVersion.objects.filter(
        menu_key=USSD_MENU_KEY,
        language="en",
        is_active=True,
    ).exclude(version_label=USSD_BUILTIN_VERSION_LABEL).update(is_active=False)

    english_menu, _created = UssdMenuVersion.objects.update_or_create(
        menu_key=USSD_MENU_KEY,
        language="en",
        version_label=USSD_BUILTIN_VERSION_LABEL,
        defaults={
            "title": "CCHIS Cholera Health USSD Menu",
            "menu_tree": deepcopy(DEFAULT_USSD_MENU_TREE),
            "safe_fallback_copy": USSD_SAFE_FALLBACK_COPY,
            "session_outcome_taxonomy": USSD_SESSION_OUTCOME_TAXONOMY,
            "approval_status": "APPROVED",
            "approved_at": reviewed_at,
            "retired_at": None,
            "translation_status": "approved",
            "source_menu_version_id": None,
            "translation_reviewed_at": reviewed_at,
            "translation_review_notes": "English source menu restored as the active phone menu baseline.",
            "is_active": True,
            "lineage_metadata": {
                "seeded_by": "risk.0074_active_english_ussd_menu_baseline",
                "schema_version": USSD_SCHEMA_VERSION,
                "language": "en",
            },
        },
    )

    UssdMenuVersion.objects.filter(
        menu_key=USSD_MENU_KEY,
        language__in=("sw", "luo"),
        version_label=USSD_BUILTIN_VERSION_LABEL,
    ).update(
        source_menu_version_id=english_menu.id,
        translation_status="approved",
        retired_at=None,
    )


def reverse_active_english_ussd_menu(apps, schema_editor):
    UssdMenuVersion = apps.get_model("risk", "UssdMenuVersion")
    UssdMenuVersion.objects.filter(
        menu_key=USSD_MENU_KEY,
        language="en",
        version_label=USSD_BUILTIN_VERSION_LABEL,
        lineage_metadata__seeded_by="risk.0074_active_english_ussd_menu_baseline",
    ).update(is_active=False, approval_status="DRAFT", translation_status="draft")


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0073_source_data_connectors"),
    ]

    operations = [
        migrations.RunPython(ensure_active_english_ussd_menu, reverse_active_english_ussd_menu),
    ]
