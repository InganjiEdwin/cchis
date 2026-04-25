from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0011_wardgeometrydatasetversion_activated_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="ingestionrun",
            name="fallback_used",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="ingestionrun",
            name="freshness_state",
            field=models.CharField(
                choices=[
                    ("FRESH", "Fresh"),
                    ("DELAYED", "Delayed"),
                    ("STALE", "Stale"),
                    ("UNKNOWN", "Unknown"),
                ],
                default="UNKNOWN",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="ingestionrun",
            name="records_loaded",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="ingestionrun",
            name="records_rejected",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="ingestionrun",
            name="records_seen",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="ingestionrun",
            name="source_kind",
            field=models.CharField(
                choices=[
                    ("LIVE", "Live"),
                    ("SEEDED", "Seeded"),
                    ("HYBRID", "Hybrid"),
                    ("UNKNOWN", "Unknown"),
                ],
                default="UNKNOWN",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="ingestionrun",
            name="source_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="ingestionrun",
            name="source_timestamp",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
