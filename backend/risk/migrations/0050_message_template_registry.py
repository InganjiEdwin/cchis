# Generated manually for child plan 3 phases 0 and 1 on 2026-05-04

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("risk", "0049_facility_catchments"),
    ]

    operations = [
        migrations.CreateModel(
            name="MessageTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("template_key", models.CharField(max_length=120)),
                (
                    "audience_type",
                    models.CharField(
                        choices=[
                            ("chv", "CHV"),
                            ("household", "Household"),
                            ("facility_contact", "Facility contact"),
                            ("county_operator", "County operator"),
                            ("system_operator", "System operator"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("sms", "SMS"),
                            ("ussd", "USSD"),
                            ("dashboard", "Dashboard"),
                            ("offline_chv_bundle", "Offline CHV bundle"),
                        ],
                        max_length=32,
                    ),
                ),
                ("language", models.CharField(default="en", max_length=20)),
                ("version", models.PositiveIntegerField(default=1)),
                ("title", models.CharField(max_length=160)),
                ("body", models.TextField()),
                ("placeholders", models.JSONField(blank=True, default=list)),
                (
                    "approval_status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("pending_review", "Pending review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("retired", "Retired"),
                        ],
                        default="draft",
                        max_length=32,
                    ),
                ),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("retired_at", models.DateTimeField(blank=True, null=True)),
                ("owner", models.CharField(max_length=120)),
                (
                    "risk_level",
                    models.CharField(
                        choices=[
                            ("low", "Low"),
                            ("medium", "Medium"),
                            ("high", "High"),
                            ("critical", "Critical"),
                        ],
                        default="medium",
                        max_length=20,
                    ),
                ),
                ("public_health_caveats", models.TextField(blank=True)),
                ("lineage_metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="message_templates_approved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="message_templates_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["template_key", "language", "-version"],
                "indexes": [
                    models.Index(fields=["template_key", "language", "version"], name="risk_msgtmpl_lookup_idx"),
                    models.Index(fields=["audience_type", "channel", "approval_status"], name="risk_msgtmpl_status_idx"),
                    models.Index(fields=["approval_status", "retired_at"], name="risk_msgtmpl_active_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("template_key", "language", "version"),
                        name="risk_msgtmpl_key_lang_ver_uniq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(version__gte=1),
                        name="risk_msgtmpl_version_positive",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="alert",
            name="template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="alerts",
                to="risk.messagetemplate",
            ),
        ),
        migrations.AddField(
            model_name="alert",
            name="template_key",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="alert",
            name="template_version",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="chvmessage",
            name="template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="chv_messages",
                to="risk.messagetemplate",
            ),
        ),
        migrations.AddField(
            model_name="chvmessage",
            name="template_key",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="chvmessage",
            name="template_version",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="facilityreadinessupdaterequest",
            name="template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="facility_update_requests",
                to="risk.messagetemplate",
            ),
        ),
        migrations.AddField(
            model_name="facilityreadinessupdaterequest",
            name="template_key",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="facilityreadinessupdaterequest",
            name="template_version",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["template_key", "template_version"], name="risk_alert_tpl_idx"),
        ),
        migrations.AddIndex(
            model_name="chvmessage",
            index=models.Index(fields=["template_key", "template_version"], name="risk_chvmsg_tpl_idx"),
        ),
        migrations.AddIndex(
            model_name="facilityreadinessupdaterequest",
            index=models.Index(fields=["template_key", "template_version"], name="risk_facupd_tpl_idx"),
        ),
    ]
