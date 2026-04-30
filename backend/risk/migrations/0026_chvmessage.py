import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0025_chv_public_id"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CHVMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("channel", models.CharField(choices=[("SMS", "SMS")], default="SMS", max_length=20)),
                ("message_body", models.TextField()),
                ("status", models.CharField(choices=[("QUEUED", "Queued"), ("SENT", "Sent"), ("DELIVERED", "Delivered"), ("FAILED", "Failed")], default="QUEUED", max_length=20)),
                ("provider_reference", models.CharField(blank=True, max_length=120)),
                ("failure_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("chv", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="messages", to="risk.chv")),
                ("sent_by", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="chv_messages_sent", to=settings.AUTH_USER_MODEL)),
                ("ward", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="chv_messages", to="risk.ward")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="chvmessage",
            index=models.Index(fields=["chv", "created_at"], name="risk_chvmsg_chv_6a85ae_idx"),
        ),
        migrations.AddIndex(
            model_name="chvmessage",
            index=models.Index(fields=["status", "created_at"], name="risk_chvmsg_status_8f9cc6_idx"),
        ),
    ]
