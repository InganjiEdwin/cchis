# Generated manually on 2026-05-04

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0058_model_retraining_recommendations"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelChampionChallengerComparison",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("challenger_algorithm", models.CharField(max_length=80)),
                ("challenger_model_version", models.CharField(max_length=80)),
                (
                    "benchmark_status",
                    models.CharField(
                        choices=[
                            ("BENCHMARK_ONLY", "Benchmark only"),
                            ("NOT_COMPARABLE", "Not comparable"),
                            ("REVIEW_REQUIRED", "Review required"),
                        ],
                        default="BENCHMARK_ONLY",
                        max_length=32,
                    ),
                ),
                ("comparison_validity", models.CharField(default="comparable_inputs", max_length=80)),
                (
                    "recommended_action",
                    models.CharField(default="keep_champion_monitor_challenger", max_length=160),
                ),
                ("input_alignment", models.JSONField(blank=True, default=dict)),
                ("operational_metrics", models.JSONField(blank=True, default=dict)),
                ("temporal_metrics", models.JSONField(blank=True, default=dict)),
                ("comparison_summary", models.JSONField(blank=True, default=dict)),
                ("promotion_blockers", models.JSONField(blank=True, default=list)),
                ("dashboard_summary", models.JSONField(blank=True, default=dict)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("generated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "challenger_model_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="challenger_comparisons",
                        to="risk.modelrun",
                    ),
                ),
                (
                    "champion_model_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="champion_comparisons",
                        to="risk.modelrun",
                    ),
                ),
                (
                    "champion_registry_entry",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="champion_comparisons",
                        to="risk.modelregistryentry",
                    ),
                ),
            ],
            options={
                "ordering": ["-generated_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["champion_registry_entry", "generated_at"],
                        name="risk_modelcc_champ_time_idx",
                    ),
                    models.Index(
                        fields=["challenger_model_run", "generated_at"],
                        name="risk_modelcc_chal_time_idx",
                    ),
                    models.Index(fields=["benchmark_status", "generated_at"], name="risk_modelcc_status_idx"),
                ],
            },
        ),
    ]
