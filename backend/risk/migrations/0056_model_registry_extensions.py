# Generated manually on 2026-05-04

import django.db.models.deletion
import django.utils.timezone
import uuid
from datetime import timedelta

from django.db import migrations, models


def _algorithm_for_run(run):
    metadata = run.metadata or {}
    return metadata.get("algorithm") or {
        "logistic-regression-baseline": "logistic_regression",
        "random-forest-benchmark": "random_forest",
        "xgboost-candidate": "xgboost",
        "lightgbm-candidate": "lightgbm",
    }.get(run.algorithm_name, run.algorithm_name)


def backfill_promoted_model_registry_entries(apps, schema_editor):
    ModelRun = apps.get_model("risk", "ModelRun")
    ModelRegistryEntry = apps.get_model("risk", "ModelRegistryEntry")
    ModelPromotionEvent = apps.get_model("risk", "ModelPromotionEvent")

    promoted_runs = []
    for run in ModelRun.objects.filter(status="SUCCESS").order_by("started_at", "id"):
        metadata = run.metadata or {}
        if (
            metadata.get("promotion_target") == "live_baseline"
            and metadata.get("promotion_state") == "promoted"
            and metadata.get("phase_4_promotion_gates_passed") is True
            and metadata.get("alert_eligible") is True
        ):
            promoted_runs.append(run)

    previous_entry = None
    for index, run in enumerate(promoted_runs):
        metadata = run.metadata or {}
        metrics = run.evaluation_metrics or {}
        activated_at = run.completed_at or run.started_at or django.utils.timezone.now()
        next_run = promoted_runs[index + 1] if index + 1 < len(promoted_runs) else None
        active_until = (next_run.completed_at or next_run.started_at) if next_run else None
        is_active = next_run is None
        entry = ModelRegistryEntry.objects.create(
            algorithm=_algorithm_for_run(run),
            model_version=run.model_version,
            model_run=run,
            promotion_state="ACTIVE_PROMOTED" if is_active else "RETIRED",
            active_from=activated_at,
            active_until=active_until,
            retired_reason=f"Superseded by model_run:{next_run.id}" if next_run else "",
            rollback_target=previous_entry if is_active else None,
            monitoring_state="NOT_CONFIGURED",
            owner=metadata.get("model_owner", "model_operations"),
            review_due_date=(
                django.utils.timezone.localtime(activated_at).date()
                + timedelta(days=90)
            ),
            metadata={
                "schema_version": "ward-risk-model-registry-v1",
                "backfilled_from_model_run_metadata": True,
                "model_run_id": run.id,
                "algorithm_name": run.algorithm_name,
                "algorithm": _algorithm_for_run(run),
                "model_version": run.model_version,
                "training_dataset_ref": run.training_dataset_ref,
                "inference_dataset_ref": run.inference_dataset_ref,
                "training_feature_dataset_id": run.training_feature_dataset_id,
                "inference_feature_dataset_id": run.inference_feature_dataset_id,
                "feature_schema_version": run.feature_schema_version,
                "promotion_target": metadata.get("promotion_target"),
                "promotion_state": metadata.get("promotion_state"),
                "phase_4_promotion_gates_passed": metadata.get("phase_4_promotion_gates_passed"),
                "promotion_evidence_report_ref": metadata.get("promotion_evidence_report_ref"),
                "ward_risk_classification_backtest_dataset_ref": metadata.get(
                    "ward_risk_classification_backtest_dataset_ref"
                ),
                "ward_risk_classification_label_dataset_ref": metadata.get(
                    "ward_risk_classification_label_dataset_ref"
                ),
                "lead_time_recall": metrics.get("lead_time_recall"),
                "precision": metrics.get("precision"),
                "calibration_score": metrics.get("calibration_score"),
                "rollback_target_model_run_id": previous_entry.model_run_id if is_active and previous_entry else None,
            },
        )
        event = ModelPromotionEvent.objects.create(
            registry_entry=entry,
            model_run=run,
            previous_registry_entry=previous_entry,
            source=metadata.get("promotion_decision_source", "phase_4_temporal_backtest"),
            promoted_by=metadata.get("promoted_by", "migration_backfill"),
            active_from=activated_at,
            review_due_date=entry.review_due_date,
            evidence_metadata=entry.metadata,
            occurred_at=activated_at,
        )
        entry.promotion_event = event
        entry.save(update_fields=["promotion_event", "updated_at"])
        previous_entry = entry


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0055_interoperability_contracts"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelRegistryEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("algorithm", models.CharField(max_length=80)),
                ("model_version", models.CharField(max_length=80)),
                (
                    "promotion_state",
                    models.CharField(
                        choices=[
                            ("CANDIDATE", "Candidate"),
                            ("ACTIVE_PROMOTED", "Active promoted"),
                            ("RETIRED", "Retired"),
                            ("ROLLED_BACK", "Rolled back"),
                        ],
                        default="CANDIDATE",
                        max_length=32,
                    ),
                ),
                ("active_from", models.DateTimeField(blank=True, null=True)),
                ("active_until", models.DateTimeField(blank=True, null=True)),
                ("retired_reason", models.TextField(blank=True)),
                (
                    "monitoring_state",
                    models.CharField(
                        choices=[
                            ("NOT_CONFIGURED", "Not configured"),
                            ("HEALTHY", "Healthy"),
                            ("WARNING", "Warning"),
                            ("BREACHED", "Breached"),
                            ("REVIEW_REQUIRED", "Review required"),
                        ],
                        default="NOT_CONFIGURED",
                        max_length=32,
                    ),
                ),
                ("owner", models.CharField(blank=True, max_length=160)),
                ("review_due_date", models.DateField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "model_run",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="registry_entry",
                        to="risk.modelrun",
                    ),
                ),
                (
                    "rollback_target",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rollback_sources",
                        to="risk.modelregistryentry",
                    ),
                ),
            ],
            options={
                "ordering": ["-active_from", "-created_at"],
                "indexes": [
                    models.Index(fields=["promotion_state", "active_from"], name="risk_modelreg_state_active_idx"),
                    models.Index(fields=["algorithm", "model_version"], name="risk_modelreg_alg_ver_idx"),
                    models.Index(fields=["monitoring_state", "review_due_date"], name="risk_modelreg_monitor_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("promotion_state", "ACTIVE_PROMOTED")),
                        fields=("promotion_state",),
                        name="risk_modelreg_one_active_promoted",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(("active_until__isnull", True))
                            | models.Q(("active_from__isnull", True))
                            | models.Q(("active_until__gte", models.F("active_from")))
                        ),
                        name="risk_modelreg_active_window_order",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ModelPromotionEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("source", models.CharField(default="phase_4_temporal_backtest", max_length=120)),
                ("promoted_by", models.CharField(blank=True, max_length=160)),
                ("active_from", models.DateTimeField(default=django.utils.timezone.now)),
                ("review_due_date", models.DateField(blank=True, null=True)),
                ("evidence_metadata", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "model_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="promotion_events",
                        to="risk.modelrun",
                    ),
                ),
                (
                    "previous_registry_entry",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="superseding_promotion_events",
                        to="risk.modelregistryentry",
                    ),
                ),
                (
                    "registry_entry",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="promotion_events",
                        to="risk.modelregistryentry",
                    ),
                ),
            ],
            options={
                "ordering": ["-occurred_at", "-id"],
                "indexes": [
                    models.Index(fields=["model_run", "occurred_at"], name="risk_modelprom_run_time_idx"),
                    models.Index(fields=["source", "occurred_at"], name="risk_modelprom_source_idx"),
                ],
            },
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="promotion_event",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="current_registry_entries",
                to="risk.modelpromotionevent",
            ),
        ),
        migrations.CreateModel(
            name="ModelRollbackEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("rolled_back_by", models.CharField(blank=True, max_length=160)),
                ("reason", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "rollback_target",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rollback_events_as_target",
                        to="risk.modelregistryentry",
                    ),
                ),
                (
                    "rolled_back_from",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rollback_events_from",
                        to="risk.modelregistryentry",
                    ),
                ),
            ],
            options={
                "ordering": ["-occurred_at", "-id"],
                "indexes": [
                    models.Index(fields=["rollback_target", "occurred_at"], name="risk_modelroll_target_idx"),
                    models.Index(fields=["rolled_back_from", "occurred_at"], name="risk_modelroll_from_idx"),
                ],
            },
        ),
        migrations.RunPython(backfill_promoted_model_registry_entries, noop_reverse),
    ]
