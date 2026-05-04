# Generated for cholera early warning privacy plan phase 4 on 2026-05-03

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("risk", "0042_contact_preference"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PrivacyRetentionHold",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("object_id", models.CharField(max_length=80)),
                ("reason", models.TextField()),
                ("case_reference", models.CharField(blank=True, max_length=160)),
                ("is_active", models.BooleanField(default=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="privacy_retention_holds",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="privacy_retention_holds_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PrivacyRetentionAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("run_id", models.UUIDField(db_index=True)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("DRY_RUN", "Dry run"),
                            ("ANONYMIZED", "Anonymized"),
                            ("DELETED", "Deleted"),
                            ("HELD", "Held"),
                            ("SKIPPED", "Skipped"),
                            ("SUMMARY", "Summary"),
                        ],
                        max_length=24,
                    ),
                ),
                ("record_family", models.CharField(max_length=80)),
                ("model_label", models.CharField(blank=True, max_length=120)),
                ("object_id", models.CharField(blank=True, max_length=80)),
                ("cutoff_at", models.DateTimeField(blank=True, null=True)),
                ("window_days", models.PositiveIntegerField(blank=True, null=True)),
                ("dry_run", models.BooleanField(default=True)),
                ("decision_reason", models.TextField(blank=True)),
                ("before_state", models.JSONField(blank=True, default=dict)),
                ("after_state", models.JSONField(blank=True, default=dict)),
                ("aggregate_metrics", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="privacy_retention_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "hold",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events",
                        to="risk.privacyretentionhold",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="privacyretentionhold",
            index=models.Index(fields=["content_type", "object_id"], name="risk_privhold_target_idx"),
        ),
        migrations.AddIndex(
            model_name="privacyretentionhold",
            index=models.Index(fields=["is_active", "expires_at"], name="risk_privhold_active_idx"),
        ),
        migrations.AddIndex(
            model_name="privacyretentionhold",
            index=models.Index(fields=["case_reference", "created_at"], name="risk_privhold_case_idx"),
        ),
        migrations.AddConstraint(
            model_name="privacyretentionhold",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=("content_type", "object_id"),
                name="risk_privhold_active_target_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="privacyretentionauditevent",
            index=models.Index(fields=["record_family", "created_at"], name="risk_privaudit_family_idx"),
        ),
        migrations.AddIndex(
            model_name="privacyretentionauditevent",
            index=models.Index(fields=["model_label", "object_id"], name="risk_privaudit_target_idx"),
        ),
        migrations.AddIndex(
            model_name="privacyretentionauditevent",
            index=models.Index(fields=["action", "created_at"], name="risk_privaudit_action_idx"),
        ),
    ]
