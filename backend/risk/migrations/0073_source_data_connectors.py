from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("risk", "0072_facility_readiness_snapshots"),
    ]

    operations = [
        migrations.CreateModel(
            name="SourceDataConnectorRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("connector_key", models.CharField(max_length=120)),
                ("target_feed_key", models.CharField(max_length=80)),
                ("feed_mode", models.CharField(default="api", max_length=40)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Running"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                            ("skipped", "Skipped"),
                        ],
                        default="running",
                        max_length=20,
                    ),
                ),
                ("source_name", models.CharField(max_length=160)),
                ("source_ref", models.CharField(blank=True, max_length=255)),
                ("fetched_record_count", models.PositiveIntegerField(default=0)),
                ("error_summary", models.TextField(blank=True)),
                ("safe_metadata", models.JSONField(blank=True, default=dict)),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_data_connector_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "upload_batch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="connector_runs",
                        to="risk.sourcedatauploadbatch",
                    ),
                ),
            ],
            options={
                "ordering": ["-started_at"],
                "indexes": [
                    models.Index(fields=["connector_key", "started_at"], name="risk_srcconn_key_started_idx"),
                    models.Index(fields=["target_feed_key", "status"], name="risk_srcconn_feed_status_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="SourceDataFeedModeOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("feed_key", models.CharField(max_length=80, unique=True)),
                (
                    "feed_mode",
                    models.CharField(
                        choices=[
                            ("api", "API"),
                            ("csv", "CSV"),
                            ("manual", "Manual"),
                            ("fallback", "Fallback"),
                            ("demo", "Demo"),
                        ],
                        default="csv",
                        max_length=40,
                    ),
                ),
                ("authoritative_connector_key", models.CharField(blank=True, max_length=120)),
                ("csv_upload_enabled", models.BooleanField(default=True)),
                ("reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_data_feed_mode_overrides",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["feed_key"],
                "indexes": [
                    models.Index(fields=["feed_mode", "csv_upload_enabled"], name="risk_srcmode_mode_csv_idx"),
                ],
            },
        ),
    ]
