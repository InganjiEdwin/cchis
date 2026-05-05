# Generated manually for child plan 11 phase 4 on 2026-05-04

from copy import deepcopy

from django.db import migrations
from django.utils import timezone


USSD_MENU_KEY = "cholera_health_menu"
USSD_BUILTIN_VERSION_LABEL = "builtin-v1"
USSD_SCHEMA_VERSION = "ussd-menu-governance-phase-4-v1"
SUPPORTED_LANGUAGES = ("en", "sw", "luo")
USSD_SAFE_FALLBACK_COPY_BY_LANGUAGE = {
    "en": "END Invalid option. Please try again.",
    "sw": "END Chaguo si sahihi. Jaribu tena.",
    "luo": "END Yiero ok ber. Tem kendo.",
}
USSD_SESSION_OUTCOME_TAXONOMY = {
    "STARTED": "Session reached the root menu.",
    "IN_PROGRESS": "Session is inside a non-terminal menu branch.",
    "COMPLETED": "Session reached a terminal health guidance response.",
    "INVALID_INPUT": "Session submitted a route not present in the active menu tree.",
    "ABANDONED_INFERRED": "Prior non-terminal interaction was inferred abandoned by a restart.",
    "SAFE_FALLBACK": "Session received the configured safe fallback copy.",
}
DEFAULT_USSD_ROUTES = {
    "": "root",
    "1": "flood_safety",
    "2": "diarrhea_menu",
    "2*1": "diarrhea_urgent",
    "2*2": "diarrhea_mild",
    "3": "heat_advice",
}
DEFAULT_USSD_MENU_TREE = {
    "routes": DEFAULT_USSD_ROUTES,
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
SW_USSD_MENU_TREE = {
    "routes": DEFAULT_USSD_ROUTES,
    "nodes": {
        "root": {
            "response_type": "CON",
            "body": "Karibu CCHIS Afya\n1. Usalama wa mafuriko\n2. Msaada wa kuhara kwa mtoto\n3. Ushauri wa joto",
        },
        "flood_safety": {
            "response_type": "END",
            "body": (
                "Usalama wa mafuriko:\nTumia maji yaliyotibiwa, epuka maji ya mafuriko, "
                "na nenda kituoni mtoto akihara au kutapika."
            ),
        },
        "diarrhea_menu": {
            "response_type": "CON",
            "body": "Msaada wa kuhara kwa mtoto\n1. Kuhara na kutapika au upungufu wa maji\n2. Kuhara kidogo tu",
        },
        "diarrhea_urgent": {
            "response_type": "END",
            "body": "Mpe ORS sasa na nenda kituo cha afya mara moja. Tumia maji salama na mjulishe CHV.",
        },
        "diarrhea_mild": {
            "response_type": "END",
            "body": "Mpe ORS, endelea kumpa maji, fuatilia, na tafuta huduma akizidiwa.",
        },
        "heat_advice": {
            "response_type": "END",
            "body": (
                "Ushauri wa joto:\nMpe maji mara kwa mara, mweke kivulini, epuka jua kali, "
                "na tafuta huduma akidhoofika."
            ),
        },
    },
}
LUO_USSD_MENU_TREE = {
    "routes": DEFAULT_USSD_ROUTES,
    "nodes": {
        "root": {
            "response_type": "CON",
            "body": "Oyawore e CCHIS Afya\n1. Puonj mar piny mopong'\n2. Kony mar lweyo nyathi\n3. Puonj mar liet",
        },
        "flood_safety": {
            "response_type": "END",
            "body": (
                "Puonj mar piny mopong':\nTi gi pi mothiedhi, kik idhi e pi mopong', "
                "luok lweti, kendo dhi e thieth ka nyathi lweyo kata nindo."
            ),
        },
        "diarrhea_menu": {
            "response_type": "CON",
            "body": "Kony mar lweyo nyathi\n1. Lweyo gi nindo kata rem pi\n2. Lweyo matin kende",
        },
        "diarrhea_urgent": {
            "response_type": "END",
            "body": "Mi ORS sani kendo dhi e od thieth machiegni. Ti gi pi maber kendo nyis CHV ka nitie.",
        },
        "diarrhea_mild": {
            "response_type": "END",
            "body": "Mi ORS, med pi, rit nyathi, kendo many thieth ka wach bedo marach.",
        },
        "heat_advice": {
            "response_type": "END",
            "body": (
                "Puonj mar liet:\nMi pi kinde duto, ket nyathi e tipo, geng' chieng' mar odiechieng', "
                "many thieth ka odoko mayom."
            ),
        },
    },
}
MENU_TREE_BY_LANGUAGE = {
    "en": DEFAULT_USSD_MENU_TREE,
    "sw": SW_USSD_MENU_TREE,
    "luo": LUO_USSD_MENU_TREE,
}
TITLE_BY_LANGUAGE = {
    "en": "CCHIS Cholera Health USSD Menu",
    "sw": "Menyu ya Afya ya Kipindupindu CCHIS",
    "luo": "Menyu mar Afya mar Cholera CCHIS",
}


def _seed_menu_version(UssdMenuVersion, *, language, source_menu_id, reviewed_at):
    UssdMenuVersion.objects.filter(
        menu_key=USSD_MENU_KEY,
        language=language,
        is_active=True,
    ).exclude(version_label=USSD_BUILTIN_VERSION_LABEL).update(is_active=False)
    menu_version, _created = UssdMenuVersion.objects.update_or_create(
        menu_key=USSD_MENU_KEY,
        language=language,
        version_label=USSD_BUILTIN_VERSION_LABEL,
        defaults={
            "title": TITLE_BY_LANGUAGE[language],
            "menu_tree": deepcopy(MENU_TREE_BY_LANGUAGE[language]),
            "safe_fallback_copy": USSD_SAFE_FALLBACK_COPY_BY_LANGUAGE[language],
            "session_outcome_taxonomy": USSD_SESSION_OUTCOME_TAXONOMY,
            "approval_status": "APPROVED",
            "approved_at": reviewed_at,
            "retired_at": None,
            "translation_status": "approved",
            "source_menu_version_id": source_menu_id,
            "translation_reviewed_at": reviewed_at,
            "translation_review_notes": "Seeded approved phase 4 CHV language localization USSD menu.",
            "is_active": True,
            "lineage_metadata": {
                "seeded_by": "risk.0066_ussd_multilingual_phase_4",
                "schema_version": USSD_SCHEMA_VERSION,
                "language": language,
                "route_semantics_source": "en" if language != "en" else "",
            },
        },
    )
    return menu_version


def seed_multilingual_ussd_menu_versions(apps, schema_editor):
    UssdMenuVersion = apps.get_model("risk", "UssdMenuVersion")
    reviewed_at = timezone.now()
    english_menu = _seed_menu_version(
        UssdMenuVersion,
        language="en",
        source_menu_id=None,
        reviewed_at=reviewed_at,
    )
    for language in SUPPORTED_LANGUAGES[1:]:
        _seed_menu_version(
            UssdMenuVersion,
            language=language,
            source_menu_id=english_menu.id,
            reviewed_at=reviewed_at,
        )


def remove_multilingual_ussd_menu_versions(apps, schema_editor):
    UssdMenuVersion = apps.get_model("risk", "UssdMenuVersion")
    UssdMenuVersion.objects.filter(
        menu_key=USSD_MENU_KEY,
        language__in=SUPPORTED_LANGUAGES[1:],
        version_label=USSD_BUILTIN_VERSION_LABEL,
    ).update(is_active=False, approval_status="RETIRED", retired_at=timezone.now(), translation_status="retired")


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0065_translation_registry_phase_2"),
    ]

    operations = [
        migrations.RunPython(seed_multilingual_ussd_menu_versions, remove_multilingual_ussd_menu_versions),
    ]
