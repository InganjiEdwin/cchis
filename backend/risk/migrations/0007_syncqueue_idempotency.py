from django.db import migrations, models


def populate_legacy_client_submission_ids(apps, schema_editor):
    SyncQueue = apps.get_model("risk", "SyncQueue")

    for sync_item in SyncQueue.objects.filter(client_submission_id="").iterator():
        sync_item.client_submission_id = f"legacy-sync-{sync_item.pk}"
        sync_item.save(update_fields=["client_submission_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0006_modelrun_feature_schema_version_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="syncqueue",
            name="client_submission_id",
            field=models.CharField(default="", max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="syncqueue",
            name="triage_session",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="sync_queue_items",
                to="risk.triagesession",
            ),
        ),
        migrations.RunPython(
            populate_legacy_client_submission_ids,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="syncqueue",
            constraint=models.UniqueConstraint(
                fields=("source_device_id", "client_submission_id"),
                name="unique_sync_submission_per_device",
            ),
        ),
    ]
