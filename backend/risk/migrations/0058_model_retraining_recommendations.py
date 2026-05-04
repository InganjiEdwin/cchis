# Generated manually on 2026-05-04

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0057_model_monitoring_snapshots"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelRetrainingRecommendation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "recommendation_state",
                    models.CharField(
                        choices=[
                            ("REVIEW_NOT_REQUIRED", "Review not required"),
                            ("REVIEW_REQUIRED", "Review required"),
                            ("RETRAINING_RECOMMENDED", "Retraining recommended"),
                        ],
                        default="REVIEW_NOT_REQUIRED",
                        max_length=40,
                    ),
                ),
                ("recommended_action", models.CharField(default="continue_monitoring", max_length=160)),
                ("reason_codes", models.JSONField(blank=True, default=list)),
                ("trigger_summary", models.JSONField(blank=True, default=dict)),
                ("source_snapshot_refs", models.JSONField(blank=True, default=list)),
                ("new_label_count", models.PositiveIntegerField(default=0)),
                ("false_alert_count", models.PositiveIntegerField(default=0)),
                ("miss_count", models.PositiveIntegerField(default=0)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("generated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "model_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="retraining_recommendations",
                        to="risk.modelrun",
                    ),
                ),
                (
                    "registry_entry",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="retraining_recommendations",
                        to="risk.modelregistryentry",
                    ),
                ),
            ],
            options={
                "ordering": ["-generated_at", "-id"],
                "indexes": [
                    models.Index(fields=["registry_entry", "generated_at"], name="risk_modelrec_reg_time_idx"),
                    models.Index(fields=["model_run", "generated_at"], name="risk_modelrec_run_time_idx"),
                    models.Index(fields=["recommendation_state", "generated_at"], name="risk_modelrec_state_idx"),
                ],
            },
        ),
    ]
