# Generated manually on 2026-05-04

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0056_model_registry_extensions"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelMonitoringThreshold",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("metric_name", models.CharField(max_length=120)),
                ("version", models.CharField(default="phase-2-default-v1", max_length=40)),
                ("warning_threshold", models.FloatField(blank=True, null=True)),
                ("breach_threshold", models.FloatField(blank=True, null=True)),
                (
                    "direction",
                    models.CharField(
                        choices=[
                            ("HIGHER_IS_WORSE", "Higher is worse"),
                            ("LOWER_IS_WORSE", "Lower is worse"),
                        ],
                        default="HIGHER_IS_WORSE",
                        max_length=32,
                    ),
                ),
                ("baseline_window", models.CharField(blank=True, max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["metric_name", "-version"],
                "indexes": [
                    models.Index(fields=["metric_name", "is_active"], name="risk_modelmon_thr_active_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("metric_name", "version"),
                        name="risk_modelmon_thr_metric_ver_uniq",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("is_active", True)),
                        fields=("metric_name",),
                        name="risk_modelmon_thr_one_active",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ModelMonitoringSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("monitoring_run_id", models.UUIDField(default=uuid.uuid4)),
                ("metric_name", models.CharField(max_length=120)),
                ("metric_family", models.CharField(blank=True, max_length=80)),
                ("value", models.FloatField(blank=True, null=True)),
                ("baseline_value", models.FloatField(blank=True, null=True)),
                ("threshold_value", models.FloatField(blank=True, null=True)),
                ("threshold_version", models.CharField(blank=True, max_length=40)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("HEALTHY", "Healthy"),
                            ("WARNING", "Warning"),
                            ("BREACHED", "Breached"),
                            ("NOT_READY", "Not ready"),
                        ],
                        default="NOT_READY",
                        max_length=20,
                    ),
                ),
                ("generated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("source_dataset_refs", models.JSONField(blank=True, default=list)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "model_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="monitoring_snapshots",
                        to="risk.modelrun",
                    ),
                ),
                (
                    "registry_entry",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="monitoring_snapshots",
                        to="risk.modelregistryentry",
                    ),
                ),
                (
                    "threshold",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="snapshots",
                        to="risk.modelmonitoringthreshold",
                    ),
                ),
            ],
            options={
                "ordering": ["-generated_at", "metric_name"],
                "indexes": [
                    models.Index(fields=["registry_entry", "generated_at"], name="risk_modelmon_reg_time_idx"),
                    models.Index(fields=["model_run", "metric_name"], name="risk_modelmon_run_metric_idx"),
                    models.Index(fields=["metric_name", "state"], name="risk_modelmon_metric_state_idx"),
                    models.Index(fields=["monitoring_run_id"], name="risk_modelmon_runid_idx"),
                ],
            },
        ),
    ]
