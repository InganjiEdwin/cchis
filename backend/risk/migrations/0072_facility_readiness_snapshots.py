from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0071_source_data_upload_batches"),
    ]

    operations = [
        migrations.CreateModel(
            name="FacilityReadinessSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_name", models.CharField(max_length=120)),
                (
                    "source_type",
                    models.CharField(
                        choices=[("readiness_snapshot", "Readiness snapshot")],
                        default="readiness_snapshot",
                        max_length=40,
                    ),
                ),
                ("source_timestamp", models.DateTimeField(blank=True, null=True)),
                ("submitted_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("reporting_period_start", models.DateField(blank=True, null=True)),
                ("reporting_period_end", models.DateField(blank=True, null=True)),
                ("source_ref", models.CharField(blank=True, max_length=255)),
                ("operator_note", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-submitted_at", "source_name"],
                "indexes": [
                    models.Index(fields=["source_type", "reporting_period_start"], name="risk_facsrc_type_period_idx"),
                    models.Index(fields=["source_name", "submitted_at"], name="risk_facsrc_name_sub_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        check=(
                            models.Q(("reporting_period_start__isnull", True))
                            | models.Q(("reporting_period_end__isnull", True))
                            | models.Q(("reporting_period_start__lte", models.F("reporting_period_end")))
                        ),
                        name="risk_facsrc_period_order",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="FacilityReadinessIngestionRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("RUNNING", "Running"),
                            ("SUCCESS", "Success"),
                            ("PARTIAL", "Partial"),
                            ("FAILED", "Failed"),
                        ],
                        default="RUNNING",
                        max_length=20,
                    ),
                ),
                ("source_name", models.CharField(max_length=120)),
                (
                    "source_type",
                    models.CharField(choices=[("readiness_snapshot", "Readiness snapshot")], max_length=40),
                ),
                ("source_timestamp", models.DateTimeField(blank=True, null=True)),
                ("reporting_period_start", models.DateField(blank=True, null=True)),
                ("reporting_period_end", models.DateField(blank=True, null=True)),
                ("source_ref", models.CharField(blank=True, max_length=255)),
                ("adapter_key", models.CharField(default="facility_readiness_snapshot_csv", max_length=80)),
                ("input_ref", models.CharField(blank=True, max_length=255)),
                (
                    "execution_mode",
                    models.CharField(
                        choices=[("manual", "Manual"), ("scheduled", "Scheduled"), ("replay", "Replay")],
                        default="manual",
                        max_length=20,
                    ),
                ),
                ("fallback_used", models.BooleanField(default=False)),
                ("records_seen", models.PositiveIntegerField(default=0)),
                ("records_loaded", models.PositiveIntegerField(default=0)),
                ("records_rejected", models.PositiveIntegerField(default=0)),
                ("operator_note", models.TextField(blank=True)),
                ("source_metadata", models.JSONField(blank=True, default=dict)),
                ("results", models.JSONField(blank=True, default=dict)),
                ("rejected_rows", models.JSONField(blank=True, default=list)),
                ("error_summary", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ingestion_runs",
                        to="risk.facilityreadinesssource",
                    ),
                ),
            ],
            options={
                "ordering": ["-started_at"],
                "indexes": [
                    models.Index(fields=["source_type", "started_at"], name="risk_facrun_type_started_idx"),
                    models.Index(fields=["status", "started_at"], name="risk_facrun_status_idx"),
                    models.Index(fields=["reporting_period_start"], name="risk_facrun_period_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        check=(
                            models.Q(("reporting_period_start__isnull", True))
                            | models.Q(("reporting_period_end__isnull", True))
                            | models.Q(("reporting_period_start__lte", models.F("reporting_period_end")))
                        ),
                        name="risk_facrun_period_order",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="FacilityReadinessSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reported_at", models.DateTimeField()),
                ("ors_sachets_available", models.PositiveIntegerField(default=0)),
                ("iv_fluids_available", models.PositiveIntegerField(default=0)),
                ("zinc_available", models.PositiveIntegerField(default=0)),
                ("chlorine_available", models.PositiveIntegerField(default=0)),
                ("beds_available", models.PositiveIntegerField(default=0)),
                ("staff_on_duty", models.PositiveIntegerField(default=0)),
                ("referral_available", models.BooleanField(default=False)),
                ("service_disruption", models.BooleanField(default=False)),
                ("stockout_notes", models.TextField(blank=True)),
                (
                    "source_kind",
                    models.CharField(
                        choices=[
                            ("facility_report", "Facility report"),
                            ("logistics_system", "Logistics system"),
                            ("county_operations", "County operations"),
                            ("seeded_demo", "Seeded demo"),
                        ],
                        default="facility_report",
                        max_length=40,
                    ),
                ),
                (
                    "freshness_state",
                    models.CharField(
                        choices=[
                            ("fresh", "Fresh"),
                            ("delayed", "Delayed"),
                            ("stale", "Stale"),
                            ("replay_diagnostic", "Replay diagnostic"),
                            ("unknown", "Unknown"),
                        ],
                        default="unknown",
                        max_length=40,
                    ),
                ),
                (
                    "readiness_state",
                    models.CharField(
                        choices=[
                            ("ready", "Ready"),
                            ("watch", "Watch"),
                            ("capacity_concern", "Capacity concern"),
                        ],
                        default="ready",
                        max_length=40,
                    ),
                ),
                ("readiness_score", models.FloatField(default=100.0)),
                ("source_name", models.CharField(max_length=120)),
                ("source_ref", models.CharField(blank=True, max_length=255)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "facility",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="readiness_snapshots",
                        to="risk.healthfacility",
                    ),
                ),
                (
                    "ingestion_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="readiness_snapshots",
                        to="risk.facilityreadinessingestionrun",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="readiness_snapshots",
                        to="risk.facilityreadinesssource",
                    ),
                ),
                (
                    "ward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="facility_readiness_snapshots",
                        to="risk.ward",
                    ),
                ),
            ],
            options={
                "ordering": ["-reported_at", "facility__name"],
                "indexes": [
                    models.Index(fields=["facility", "reported_at"], name="risk_facready_fac_rep_idx"),
                    models.Index(fields=["ward", "reported_at"], name="risk_facready_ward_rep_idx"),
                    models.Index(fields=["freshness_state", "reported_at"], name="risk_facready_fresh_idx"),
                    models.Index(fields=["readiness_state", "reported_at"], name="risk_facready_state_idx"),
                    models.Index(fields=["source_kind", "reported_at"], name="risk_facready_source_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("facility", "reported_at"), name="risk_facready_fac_report_uniq")
                ],
            },
        ),
    ]
