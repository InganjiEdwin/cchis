# Generated manually for child plan 3 phase 2 on 2026-05-04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0050_message_template_registry"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="governance_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="chvmessage",
            name="governance_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="facilityreadinessupdaterequest",
            name="governance_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
