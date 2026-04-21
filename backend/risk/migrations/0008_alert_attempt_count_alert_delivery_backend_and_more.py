from django.db import migrations, models


def normalize_alert_delivery_state(apps, schema_editor):
    Alert = apps.get_model("risk", "Alert")

    for alert in Alert.objects.all().iterator():
        if alert.channel == "DASHBOARD":
            alert.delivery_backend = "internal-dashboard"
            alert.max_attempts = 1
        elif alert.channel == "SMS":
            alert.delivery_backend = "africastalking"
        else:
            alert.delivery_backend = "unknown"

        if alert.status == "SENT":
            alert.status = "DELIVERED"
            alert.attempt_count = max(alert.attempt_count, 1)
            alert.last_attempted_at = alert.sent_at or alert.created_at
        elif alert.status == "PENDING":
            alert.status = "QUEUED"
        elif alert.status == "FAILED":
            alert.attempt_count = max(alert.attempt_count, 1)
            alert.last_attempted_at = alert.last_attempted_at or alert.created_at

        alert.save(
            update_fields=[
                "status",
                "delivery_backend",
                "max_attempts",
                "attempt_count",
                "last_attempted_at",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ('risk', '0007_syncqueue_idempotency'),
    ]

    operations = [
        migrations.AddField(
            model_name='alert',
            name='attempt_count',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='alert',
            name='delivery_backend',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='alert',
            name='last_attempted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='alert',
            name='max_attempts',
            field=models.PositiveSmallIntegerField(default=3),
        ),
        migrations.AddField(
            model_name='alert',
            name='next_retry_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='alert',
            name='status',
            field=models.CharField(choices=[('QUEUED', 'Queued'), ('RETRY_PENDING', 'Retry Pending'), ('DELIVERED', 'Delivered'), ('FAILED', 'Failed')], default='QUEUED', max_length=20),
        ),
        migrations.RunPython(
            normalize_alert_delivery_state,
            migrations.RunPython.noop,
        ),
    ]
