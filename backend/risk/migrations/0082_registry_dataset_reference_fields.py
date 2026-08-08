from django.db import migrations, models


def backfill_registry_dataset_references(apps, schema_editor):
    ModelRegistryEntry = apps.get_model("risk", "ModelRegistryEntry")
    for entry in ModelRegistryEntry.objects.select_related("model_run").all().iterator():
        model_run = entry.model_run
        entry.feature_schema_version = model_run.feature_schema_version or ""
        entry.training_feature_dataset_ref = model_run.training_dataset_ref or ""
        entry.inference_feature_dataset_ref = model_run.inference_dataset_ref or ""
        entry.save(
            update_fields=[
                "feature_schema_version",
                "training_feature_dataset_ref",
                "inference_feature_dataset_ref",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0081_allow_one_active_per_deployment_target"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelregistryentry",
            name="feature_schema_version",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="inference_feature_dataset_ref",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="training_feature_dataset_ref",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.RunPython(backfill_registry_dataset_references, migrations.RunPython.noop),
    ]
