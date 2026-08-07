from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0076_session_security_notification_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="ingestionrun",
            name="lineage_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="climaterecord",
            name="identity_key",
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
    ]
