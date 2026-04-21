# Generated manually for safe unique identifier backfill.

import uuid

from django.db import migrations, models


def populate_public_ids(apps, schema_editor):
    Ward = apps.get_model("risk", "Ward")
    HealthFacility = apps.get_model("risk", "HealthFacility")

    for ward in Ward.objects.filter(public_id__isnull=True):
        ward.public_id = uuid.uuid4()
        ward.save(update_fields=["public_id"])

    for facility in HealthFacility.objects.filter(public_id__isnull=True):
        facility.public_id = uuid.uuid4()
        facility.save(update_fields=["public_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0002_healthfacility_triagesession_referral_facility_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ward",
            name="public_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="healthfacility",
            name="public_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(populate_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="ward",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="healthfacility",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
