import uuid

from django.db import migrations, models


def populate_alert_public_ids(apps, schema_editor):
    Alert = apps.get_model("risk", "Alert")

    for alert in Alert.objects.filter(public_id__isnull=True).iterator():
        alert.public_id = uuid.uuid4()
        alert.save(update_fields=["public_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0023_chvcoveragerequestalertlink_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="public_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(populate_alert_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="alert",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
