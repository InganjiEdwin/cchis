from django.db import migrations, models


def populate_delivery_provenance(apps, schema_editor):
    CHVMessage = apps.get_model("risk", "CHVMessage")

    for message in CHVMessage.objects.all().iterator():
        if message.status == "QUEUED":
            message.delivery_kind = "QUEUE_ONLY"
        else:
            message.delivery_kind = "SIMULATED"

        if not message.delivery_backend:
            message.delivery_backend = "stub" if message.delivery_kind == "SIMULATED" else ""

        message.save(update_fields=["delivery_kind", "delivery_backend"])


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0026_chvmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="chvmessage",
            name="delivery_backend",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="chvmessage",
            name="delivery_kind",
            field=models.CharField(
                choices=[
                    ("LIVE", "Live"),
                    ("SIMULATED", "Simulated"),
                    ("QUEUE_ONLY", "Queue Only"),
                    ("UNAVAILABLE", "Unavailable"),
                ],
                default="UNAVAILABLE",
                max_length=20,
            ),
        ),
        migrations.RunPython(populate_delivery_provenance, migrations.RunPython.noop),
    ]
