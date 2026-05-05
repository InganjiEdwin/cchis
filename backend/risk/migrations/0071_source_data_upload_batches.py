# Generated manually for source-data ops phase 2 on 2026-05-05

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0070_backfill_legacy_delivery_governance_metadata"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SourceDataUploadBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("feed_key", models.CharField(max_length=80)),
                ("domain", models.CharField(max_length=80)),
                ("source_type", models.CharField(max_length=80)),
                ("source_name", models.CharField(max_length=160)),
                ("source_ref", models.CharField(blank=True, max_length=255)),
                ("source_timestamp", models.DateTimeField(blank=True, null=True)),
                ("release_version", models.CharField(blank=True, max_length=120)),
                ("reporting_period_start", models.DateField(blank=True, null=True)),
                ("reporting_period_end", models.DateField(blank=True, null=True)),
                ("correction_mode", models.CharField(blank=True, max_length=40)),
                ("replacement_reason", models.TextField(blank=True)),
                ("operator_note", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("uploaded", "Uploaded"),
                            ("validating", "Validating"),
                            ("validation_failed", "Validation failed"),
                            ("ready_for_confirmation", "Ready for confirmation"),
                            ("confirming", "Confirming"),
                            ("imported", "Imported"),
                            ("import_failed", "Import failed"),
                            ("cancelled", "Cancelled"),
                            ("superseded", "Superseded"),
                        ],
                        default="uploaded",
                        max_length=40,
                    ),
                ),
                (
                    "validation_status",
                    models.CharField(
                        choices=[
                            ("not_started", "Not started"),
                            ("running", "Running"),
                            ("passed", "Passed"),
                            ("failed", "Failed"),
                        ],
                        default="not_started",
                        max_length=40,
                    ),
                ),
                (
                    "import_status",
                    models.CharField(
                        choices=[
                            ("not_started", "Not started"),
                            ("running", "Running"),
                            ("imported", "Imported"),
                            ("failed", "Failed"),
                        ],
                        default="not_started",
                        max_length=40,
                    ),
                ),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("accepted_count", models.PositiveIntegerField(default=0)),
                ("rejected_count", models.PositiveIntegerField(default=0)),
                ("warning_count", models.PositiveIntegerField(default=0)),
                (
                    "approval_status",
                    models.CharField(
                        choices=[
                            ("not_required", "Not required"),
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("expired", "Expired"),
                        ],
                        default="not_required",
                        max_length=40,
                    ),
                ),
                ("approval_risk_category", models.CharField(blank=True, max_length=80)),
                ("approval_requested_at", models.DateTimeField(blank=True, null=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("approval_reason", models.TextField(blank=True)),
                ("approval_expires_at", models.DateTimeField(blank=True, null=True)),
                ("validation_celery_task_id", models.CharField(blank=True, max_length=255)),
                ("import_celery_task_id", models.CharField(blank=True, max_length=255)),
                ("downstream_celery_task_id", models.CharField(blank=True, max_length=255)),
                ("domain_ingestion_run_type", models.CharField(blank=True, max_length=80)),
                ("domain_ingestion_run_id", models.PositiveIntegerField(blank=True, null=True)),
                ("facility_readiness_ingestion_run_id", models.PositiveIntegerField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approval_requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_data_approval_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_data_approvals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "confirmed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_data_confirmed_upload_batches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_data_upload_batches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "duplicate_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="duplicate_uploads",
                        to="risk.sourcedatauploadbatch",
                    ),
                ),
                (
                    "population_exposure_ingestion_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_data_upload_batches",
                        to="risk.populationexposureingestionrun",
                    ),
                ),
                (
                    "replaces_upload",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="replacement_uploads",
                        to="risk.sourcedatauploadbatch",
                    ),
                ),
                (
                    "surveillance_ingestion_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_data_upload_batches",
                        to="risk.surveillanceingestionrun",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SourceDataUploadArtifact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("original_filename", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, max_length=120)),
                ("size_bytes", models.PositiveBigIntegerField(default=0)),
                ("sha256", models.CharField(max_length=64)),
                ("storage_backend", models.CharField(default="shared_filesystem", max_length=40)),
                ("storage_path", models.CharField(max_length=500)),
                ("retention_expires_at", models.DateTimeField(blank=True, null=True)),
                ("redaction_state", models.CharField(default="raw", max_length=40)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "upload_batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="artifacts",
                        to="risk.sourcedatauploadbatch",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SourceDataValidationIssue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("row_number", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "severity",
                    models.CharField(
                        choices=[("error", "Error"), ("warning", "Warning"), ("info", "Info")],
                        max_length=20,
                    ),
                ),
                ("code", models.CharField(max_length=120)),
                ("column_name", models.CharField(blank=True, max_length=120)),
                ("message", models.TextField()),
                ("safe_context", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "upload_batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="validation_issues",
                        to="risk.sourcedatauploadbatch",
                    ),
                ),
            ],
            options={
                "ordering": ["severity", "row_number", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="SourceDataUploadEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("template_downloaded", "Template downloaded"),
                            ("upload_created", "Upload created"),
                            ("validation_started", "Validation started"),
                            ("validation_completed", "Validation completed"),
                            ("confirmation_requested", "Confirmation requested"),
                            ("import_started", "Import started"),
                            ("import_completed", "Import completed"),
                            ("import_failed", "Import failed"),
                            ("errors_downloaded", "Errors downloaded"),
                            ("downstream_action_requested", "Downstream action requested"),
                            ("replacement_requested", "Replacement requested"),
                            ("upload_cancelled", "Upload cancelled"),
                        ],
                        max_length=80,
                    ),
                ),
                ("event_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("ip_address_hash", models.CharField(blank=True, max_length=64)),
                ("user_agent_hash", models.CharField(blank=True, max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_data_upload_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "upload_batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="risk.sourcedatauploadbatch",
                    ),
                ),
            ],
            options={
                "ordering": ["-event_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="sourcedatauploadbatch",
            index=models.Index(fields=["feed_key", "created_at"], name="risk_srcbatch_feed_created_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcedatauploadbatch",
            index=models.Index(fields=["status", "created_at"], name="risk_srcbatch_status_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcedatauploadbatch",
            index=models.Index(fields=["validation_status", "created_at"], name="risk_srcbatch_val_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcedatauploadbatch",
            index=models.Index(fields=["source_type", "source_timestamp"], name="risk_srcbatch_source_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcedatauploadartifact",
            index=models.Index(fields=["sha256", "created_at"], name="risk_srcart_sha_created_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcedatauploadartifact",
            index=models.Index(fields=["retention_expires_at"], name="risk_srcart_retention_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcedatavalidationissue",
            index=models.Index(fields=["upload_batch", "severity"], name="risk_srcissue_batch_sev_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcedatavalidationissue",
            index=models.Index(fields=["code"], name="risk_srcissue_code_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcedatauploadevent",
            index=models.Index(fields=["upload_batch", "event_at"], name="risk_srcevent_batch_time_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcedatauploadevent",
            index=models.Index(fields=["event_type", "event_at"], name="risk_srcevent_type_time_idx"),
        ),
    ]
