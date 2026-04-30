import uuid

from django.db import migrations, models


def populate_chv_public_ids(apps, schema_editor):
    CHV = apps.get_model("risk", "CHV")

    for chv in CHV.objects.filter(public_id__isnull=True).iterator():
        chv.public_id = uuid.uuid4()
        chv.save(update_fields=["public_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0024_alert_public_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="chv",
            name="public_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(populate_chv_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="chv",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
