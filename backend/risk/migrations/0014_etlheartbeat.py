from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0013_featuredataset_featuredatasetrow_modelrun_datasets"),
    ]

    operations = [
        migrations.CreateModel(
            name="ETLHeartbeat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("component", models.CharField(choices=[("SCHEDULER", "Scheduler"), ("WORKER", "Worker")], max_length=20)),
                ("task_name", models.CharField(max_length=160)),
                ("status", models.CharField(choices=[("OK", "OK"), ("WARN", "Warn"), ("FAILED", "Failed")], default="OK", max_length=20)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("recorded_at", models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                "ordering": ["-recorded_at"],
            },
        ),
        migrations.AddIndex(
            model_name="etlheartbeat",
            index=models.Index(fields=["component", "recorded_at"], name="risk_etlhea_compone_63f67b_idx"),
        ),
        migrations.AddIndex(
            model_name="etlheartbeat",
            index=models.Index(fields=["status", "recorded_at"], name="risk_etlhea_status_0b2913_idx"),
        ),
    ]
