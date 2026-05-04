# Generated for cholera early warning privacy plan phase 5 on 2026-05-03

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0043_privacy_retention_ledger"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SensitiveExportRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "export_type",
                    models.CharField(
                        choices=[
                            ("ALERT_LIST_CSV", "Alert list CSV"),
                            ("ALERT_DETAIL_REPORT", "Alert detail report"),
                        ],
                        max_length=40,
                    ),
                ),
                ("purpose", models.TextField()),
                ("filters", models.JSONField(blank=True, default=dict)),
                ("sensitive_fields_included", models.JSONField(blank=True, default=list)),
                (
                    "approval_state",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                            ("EXPIRED", "Expired"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("requires_approval", models.BooleanField(default=True)),
                ("generated_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.TextField(blank=True)),
                ("generated_filename", models.CharField(blank=True, max_length=180)),
                ("generated_content_type", models.CharField(default="text/csv", max_length=80)),
                ("generated_payload", models.TextField(blank=True)),
                ("payload_sha256", models.CharField(blank=True, max_length=64)),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("download_count", models.PositiveIntegerField(default=0)),
                ("last_downloaded_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sensitive_exports_approved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "rejected_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sensitive_exports_rejected",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "requester",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sensitive_export_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SensitiveExportDownloadAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("DOWNLOADED", "Downloaded"),
                            ("BLOCKED_NOT_APPROVED", "Blocked because export is not approved"),
                            ("BLOCKED_EXPIRED", "Blocked because export expired"),
                            ("BLOCKED_PERMISSION", "Blocked by permission"),
                        ],
                        max_length=40,
                    ),
                ),
                ("reason", models.TextField(blank=True)),
                ("request_metadata", models.JSONField(blank=True, default=dict)),
                ("downloaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "downloader",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sensitive_export_download_audits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "export_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="download_audits",
                        to="risk.sensitiveexportrequest",
                    ),
                ),
            ],
            options={
                "ordering": ["-downloaded_at"],
            },
        ),
        migrations.AddIndex(
            model_name="sensitiveexportrequest",
            index=models.Index(fields=["requester", "created_at"], name="risk_sensexp_requester_idx"),
        ),
        migrations.AddIndex(
            model_name="sensitiveexportrequest",
            index=models.Index(fields=["export_type", "approval_state"], name="risk_sensexp_type_state_idx"),
        ),
        migrations.AddIndex(
            model_name="sensitiveexportrequest",
            index=models.Index(fields=["expires_at", "approval_state"], name="risk_sensexp_expiry_idx"),
        ),
        migrations.AddIndex(
            model_name="sensitiveexportdownloadaudit",
            index=models.Index(fields=["export_request", "downloaded_at"], name="risk_sensdown_export_idx"),
        ),
        migrations.AddIndex(
            model_name="sensitiveexportdownloadaudit",
            index=models.Index(fields=["downloader", "downloaded_at"], name="risk_sensdown_user_idx"),
        ),
        migrations.AddIndex(
            model_name="sensitiveexportdownloadaudit",
            index=models.Index(fields=["outcome", "downloaded_at"], name="risk_sensdown_outcome_idx"),
        ),
    ]
