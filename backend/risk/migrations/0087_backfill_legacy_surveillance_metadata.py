from django.db import migrations


LEGACY_RUN_FILTERS = {
    "algorithm_name": "logistic-regression-baseline",
    "model_version": "lr-v1",
    "status": "SUCCESS",
    "training_dataset_ref": "mock-training-dataset:v1",
    "inference_dataset_ref": "mock-inference-dataset:month-4",
    "training_row_count": 8,
    "inference_row_count": 1449,
    "training_feature_dataset__isnull": True,
    "inference_feature_dataset__isnull": True,
}

NOT_AVAILABLE_VALIDATION = {
    "status": "not_available",
    "validation_mode": "surveillance_label_dataset_missing",
    "label_dataset_ref": None,
    "horizons": [7, 14],
    "truth_gate": {
        "proxy_only_as_confirmed_allowed": False,
        "confirmed_truth_required_for_confirmed_outbreak_claims": True,
    },
}


def backfill_legacy_surveillance_metadata(apps, schema_editor):
    ModelRun = apps.get_model("risk", "ModelRun")

    for run in ModelRun.objects.filter(**LEGACY_RUN_FILTERS).iterator():
        metadata = dict(run.metadata or {})
        metrics = dict(run.evaluation_metrics or {})

        # Do not overwrite a real lineage record if one has already been
        # attached to a matching legacy run by an operator or a later import.
        surveillance_metadata_keys = {
            "surveillance_label_dataset_ref",
            "surveillance_label_feature_dataset_id",
            "surveillance_label_usage",
            "surveillance_lead_time_validation",
        }
        if (
            surveillance_metadata_keys.intersection(metadata)
            or "surveillance_lead_time_validation" in metrics
        ):
            continue

        metadata.update(
            {
                "surveillance_label_dataset_ref": None,
                "surveillance_label_feature_dataset_id": None,
                "surveillance_label_schema_version": None,
                "surveillance_label_usage": "not_available",
                "surveillance_label_truth_gate": {
                    "proxy_only_as_confirmed_allowed": False,
                    "confirmed_truth_required_for_confirmed_outbreak_claims": True,
                },
                "surveillance_provenance_status": "unavailable_legacy_run",
                "surveillance_provenance_source": "persisted_model_run_fields",
                "surveillance_provenance_note": (
                    "No surveillance label dataset, training feature dataset, or lead-time validation evidence "
                    "was persisted for this legacy run. No surveillance training or performance claim is made."
                ),
                "surveillance_lead_time_validation": NOT_AVAILABLE_VALIDATION,
            }
        )
        metrics["surveillance_lead_time_validation"] = NOT_AVAILABLE_VALIDATION
        run.metadata = metadata
        run.evaluation_metrics = metrics
        run.save(update_fields=["metadata", "evaluation_metrics"])


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0086_feature_dataset_eligibility_state"),
    ]

    operations = [
        migrations.RunPython(
            backfill_legacy_surveillance_metadata,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
