from django.db import migrations


SUPERSEDED_CHIRPS_RUN_IDS = (36, 37)
CHIRPS_SOURCE_NAME = "chirps-v3.0"


def mark_superseded_chirps_runs_non_eligible(apps, schema_editor):
    IngestionRun = apps.get_model("risk", "IngestionRun")
    runs = IngestionRun.objects.filter(
        id__in=SUPERSEDED_CHIRPS_RUN_IDS,
        run_type="RAINFALL",
        source_name=CHIRPS_SOURCE_NAME,
        status="SUCCESS",
    )
    for run in runs:
        lineage = dict(run.lineage_metadata or {})
        lineage["eligibility_status"] = "non_eligible"
        lineage["non_eligibility_reason"] = (
            "Persisted observations were superseded by a later force-reconciled CHIRPS run; "
            "this historical run is retained for audit history but is not an accepted observation set."
        )
        run.status = "PARTIAL"
        run.error_message = "non_eligible: superseded observation set"
        run.lineage_metadata = lineage
        run.save(update_fields=["status", "error_message", "lineage_metadata"])


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0084_remove_mobitech_controlled_test_geography"),
    ]

    operations = [
        migrations.RunPython(
            mark_superseded_chirps_runs_non_eligible,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
