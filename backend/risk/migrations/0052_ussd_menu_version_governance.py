# Generated manually for child plan 3 phase 3 on 2026-05-04

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


USSD_MENU_KEY = "cholera_health_menu"
USSD_BUILTIN_VERSION_LABEL = "builtin-v1"
USSD_DEFAULT_LANGUAGE = "en"
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


def seed_builtin_ussd_menu_version(apps, schema_editor):
    UssdMenuVersion = apps.get_model("risk", "UssdMenuVersion")
    UssdMenuVersion.objects.update_or_create(
        menu_key=USSD_MENU_KEY,
        language=USSD_DEFAULT_LANGUAGE,
        version_label=USSD_BUILTIN_VERSION_LABEL,
        defaults={
            "title": "CCHIS Cholera Health USSD Menu",
            "menu_tree": DEFAULT_USSD_MENU_TREE,
            "safe_fallback_copy": USSD_SAFE_FALLBACK_COPY,
            "session_outcome_taxonomy": USSD_SESSION_OUTCOME_TAXONOMY,
            "approval_status": "APPROVED",
            "approved_at": timezone.now(),
            "is_active": True,
            "lineage_metadata": {
                "seeded_by": "risk.0052_ussd_menu_version_governance",
                "schema_version": "ussd-menu-governance-phase-3-v1",
            },
        },
    )


def remove_seeded_builtin_ussd_menu_version(apps, schema_editor):
    UssdMenuVersion = apps.get_model("risk", "UssdMenuVersion")
    UssdMenuVersion.objects.filter(
        menu_key=USSD_MENU_KEY,
        language=USSD_DEFAULT_LANGUAGE,
        version_label=USSD_BUILTIN_VERSION_LABEL,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("risk", "0051_message_audience_governance_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="UssdMenuVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("menu_key", models.CharField(default="cholera_health_menu", max_length=120)),
                ("version_label", models.CharField(max_length=80)),
                ("language", models.CharField(default="en", max_length=20)),
                ("title", models.CharField(max_length=160)),
                ("menu_tree", models.JSONField(blank=True, default=dict)),
                ("safe_fallback_copy", models.TextField(default="END Invalid option. Please try again.")),
                ("session_outcome_taxonomy", models.JSONField(blank=True, default=dict)),
                (
                    "approval_status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("APPROVED", "Approved"),
                            ("RETIRED", "Retired"),
                        ],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("retired_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=False)),
                ("lineage_metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ussd_menu_versions_approved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ussd_menu_versions_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["menu_key", "language", "-created_at"],
                "indexes": [
                    models.Index(fields=["menu_key", "language", "is_active"], name="risk_ussdmenu_active_idx"),
                    models.Index(fields=["approval_status", "retired_at"], name="risk_ussdmenu_status_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("menu_key", "language", "version_label"),
                        name="risk_ussdmenu_langver_uniq",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("is_active", True)),
                        fields=("menu_key", "language"),
                        name="risk_ussdmenu_one_active_lang",
                    ),
                ],
            },
        ),
        migrations.RunPython(seed_builtin_ussd_menu_version, remove_seeded_builtin_ussd_menu_version),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="menu_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="session_logs",
                to="risk.ussdmenuversion",
            ),
        ),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="menu_key",
            field=models.CharField(default="cholera_health_menu", max_length=120),
        ),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="menu_version_label",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="language",
            field=models.CharField(default="en", max_length=20),
        ),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="session_outcome",
            field=models.CharField(
                choices=[
                    ("STARTED", "Started"),
                    ("IN_PROGRESS", "In progress"),
                    ("COMPLETED", "Completed"),
                    ("INVALID_INPUT", "Invalid input"),
                    ("ABANDONED_INFERRED", "Abandoned inferred"),
                    ("SAFE_FALLBACK", "Safe fallback"),
                ],
                default="IN_PROGRESS",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="invalid_option",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="abandonment_reason",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="is_terminal",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="governance_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddIndex(
            model_name="ussdsessionlog",
            index=models.Index(
                fields=["menu_key", "menu_version_label", "language"],
                name="risk_ussdlog_menu_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="ussdsessionlog",
            index=models.Index(fields=["session_outcome", "created_at"], name="risk_ussdlog_outcome_idx"),
        ),
        migrations.AddIndex(
            model_name="ussdsessionlog",
            index=models.Index(fields=["invalid_option", "created_at"], name="risk_ussdlog_invalid_idx"),
        ),
    ]
