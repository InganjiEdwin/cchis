# Generated manually for child plan 11 phase 2 on 2026-05-04

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


TRANSLATION_DRAFT = "draft"
TRANSLATION_NEEDS_REVIEW = "needs_translation_review"
TRANSLATION_APPROVED = "approved"
TRANSLATION_RETIRED = "retired"
TRANSLATION_BLOCKED_SOURCE_RETIRED = "blocked_source_retired"
TRANSLATION_CHOICES = [
    (TRANSLATION_DRAFT, "Draft"),
    (TRANSLATION_NEEDS_REVIEW, "Needs translation review"),
    (TRANSLATION_APPROVED, "Approved"),
    (TRANSLATION_RETIRED, "Retired"),
    (TRANSLATION_BLOCKED_SOURCE_RETIRED, "Blocked because source is retired"),
]


def initialize_translation_registry(apps, schema_editor):
    MessageTemplate = apps.get_model("risk", "MessageTemplate")
    UssdMenuVersion = apps.get_model("risk", "UssdMenuVersion")

    english_templates = {
        (template.template_key, template.version): template
        for template in MessageTemplate.objects.filter(language="en")
    }
    for template in MessageTemplate.objects.all().iterator():
        update_fields = []
        if template.language == "en":
            next_status = TRANSLATION_APPROVED if template.approval_status == "approved" else TRANSLATION_DRAFT
        elif template.approval_status == "retired":
            next_status = TRANSLATION_RETIRED
        else:
            source = english_templates.get((template.template_key, template.version))
            if source is not None and template.source_template_id != source.id:
                template.source_template_id = source.id
                update_fields.append("source_template")
            source_is_active = source is not None and source.approval_status == "approved" and source.retired_at is None
            if not source_is_active and template.approval_status == "approved":
                next_status = TRANSLATION_BLOCKED_SOURCE_RETIRED
            elif template.approval_status == "approved":
                next_status = TRANSLATION_APPROVED
                template.translation_reviewed_by_id = template.approved_by_id
                template.translation_reviewed_at = template.approved_at
                update_fields.extend(["translation_reviewed_by", "translation_reviewed_at"])
            elif template.approval_status == "pending_review":
                next_status = TRANSLATION_NEEDS_REVIEW
            else:
                next_status = TRANSLATION_DRAFT
        if template.translation_status != next_status:
            template.translation_status = next_status
            update_fields.append("translation_status")
        if update_fields:
            template.save(update_fields=sorted(set(update_fields)))

    english_menus_by_key = {}
    for menu in UssdMenuVersion.objects.filter(language="en").order_by("-is_active", "-approved_at", "-created_at", "-id"):
        english_menus_by_key.setdefault(menu.menu_key, menu)

    for menu in UssdMenuVersion.objects.all().iterator():
        update_fields = []
        if menu.language == "en":
            next_status = TRANSLATION_APPROVED if menu.approval_status == "APPROVED" else TRANSLATION_DRAFT
        elif menu.approval_status == "RETIRED":
            next_status = TRANSLATION_RETIRED
        else:
            source = english_menus_by_key.get(menu.menu_key)
            if source is not None and menu.source_menu_version_id != source.id:
                menu.source_menu_version_id = source.id
                update_fields.append("source_menu_version")
            source_is_active = source is not None and source.approval_status == "APPROVED" and source.retired_at is None
            if not source_is_active and menu.approval_status == "APPROVED":
                next_status = TRANSLATION_BLOCKED_SOURCE_RETIRED
            elif menu.approval_status == "APPROVED":
                next_status = TRANSLATION_APPROVED
                menu.translation_reviewed_by_id = menu.approved_by_id
                menu.translation_reviewed_at = menu.approved_at
                update_fields.extend(["translation_reviewed_by", "translation_reviewed_at"])
            elif menu.approval_status == "DRAFT":
                next_status = TRANSLATION_DRAFT
            else:
                next_status = TRANSLATION_NEEDS_REVIEW
        if menu.translation_status != next_status:
            menu.translation_status = next_status
            update_fields.append("translation_status")
        if update_fields:
            menu.save(update_fields=sorted(set(update_fields)))


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("risk", "0064_chv_language_localization_phase_0_1"),
    ]

    operations = [
        migrations.AddField(
            model_name="messagetemplate",
            name="translation_status",
            field=models.CharField(choices=TRANSLATION_CHOICES, default=TRANSLATION_DRAFT, max_length=40),
        ),
        migrations.AddField(
            model_name="messagetemplate",
            name="source_template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="translation_variants",
                to="risk.messagetemplate",
            ),
        ),
        migrations.AddField(
            model_name="messagetemplate",
            name="translation_reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="message_template_translation_reviews",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="messagetemplate",
            name="translation_reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="messagetemplate",
            name="translation_review_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddIndex(
            model_name="messagetemplate",
            index=models.Index(fields=["source_template", "translation_status"], name="risk_msgtmpl_source_trans_idx"),
        ),
        migrations.AddField(
            model_name="ussdmenuversion",
            name="translation_status",
            field=models.CharField(choices=TRANSLATION_CHOICES, default=TRANSLATION_DRAFT, max_length=40),
        ),
        migrations.AddField(
            model_name="ussdmenuversion",
            name="source_menu_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="translation_variants",
                to="risk.ussdmenuversion",
            ),
        ),
        migrations.AddField(
            model_name="ussdmenuversion",
            name="translation_reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ussd_menu_translation_reviews",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="ussdmenuversion",
            name="translation_reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ussdmenuversion",
            name="translation_review_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddIndex(
            model_name="ussdmenuversion",
            index=models.Index(fields=["source_menu_version", "translation_status"], name="risk_ussdmenu_src_tr_idx"),
        ),
        migrations.RunPython(initialize_translation_registry, migrations.RunPython.noop),
    ]
