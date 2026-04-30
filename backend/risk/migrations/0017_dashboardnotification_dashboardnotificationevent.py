from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("risk", "0016_ingestionrun_operator_note"),
    ]

    operations = [
        migrations.CreateModel(
            name="DashboardNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("external_key", models.CharField(max_length=180, unique=True)),
                ("type", models.CharField(choices=[("WARD_RISK_HIGH", "Ward Risk High"), ("ALERT_FAILED", "Alert Failed"), ("ALERT_RETRY_PENDING", "Alert Retry Pending"), ("FEED_STALE", "Feed Stale")], max_length=40)),
                ("severity", models.CharField(choices=[("INFO", "Info"), ("WARNING", "Warning"), ("CRITICAL", "Critical")], default="INFO", max_length=20)),
                ("title", models.CharField(max_length=255)),
                ("body", models.TextField()),
                ("source_system", models.CharField(default="risk", max_length=80)),
                ("source_object_type", models.CharField(blank=True, max_length=40)),
                ("source_object_id", models.CharField(blank=True, max_length=80)),
                ("href", models.CharField(blank=True, max_length=255)),
                ("state", models.CharField(choices=[("NEW", "New"), ("SEEN", "Seen"), ("ACKNOWLEDGED", "Acknowledged"), ("RESOLVED", "Resolved"), ("DISMISSED", "Dismissed"), ("EXPIRED", "Expired")], default="NEW", max_length=20)),
                ("recipient_scope", models.CharField(choices=[("GLOBAL", "Global"), ("WARD", "Ward")], default="GLOBAL", max_length=20)),
                ("recipient_role", models.CharField(blank=True, max_length=20)),
                ("requires_acknowledgement", models.BooleanField(default=False)),
                ("dismissible", models.BooleanField(default=True)),
                ("auto_resolve", models.BooleanField(default=False)),
                ("pinned_until_actioned", models.BooleanField(default=False)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("seen_at", models.DateTimeField(blank=True, null=True)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("dismissed_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("recipient_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dashboard_notifications", to=settings.AUTH_USER_MODEL)),
                ("ward", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dashboard_notifications", to="risk.ward")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DashboardNotificationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("CREATED", "Created"), ("SEEN", "Seen"), ("ACKNOWLEDGED", "Acknowledged"), ("RESOLVED", "Resolved"), ("DISMISSED", "Dismissed"), ("EXPIRED", "Expired"), ("UPDATED", "Updated")], max_length=20)),
                ("old_state", models.CharField(blank=True, max_length=20)),
                ("new_state", models.CharField(blank=True, max_length=20)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dashboard_notification_events", to=settings.AUTH_USER_MODEL)),
                ("notification", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="risk.dashboardnotification")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="dashboardnotification",
            index=models.Index(fields=["state", "created_at"], name="risk_dashbo_state_7b7735_idx"),
        ),
        migrations.AddIndex(
            model_name="dashboardnotification",
            index=models.Index(fields=["severity", "created_at"], name="risk_dashbo_severit_8651e9_idx"),
        ),
        migrations.AddIndex(
            model_name="dashboardnotification",
            index=models.Index(fields=["recipient_role", "created_at"], name="risk_dashbo_recipie_37d832_idx"),
        ),
        migrations.AddIndex(
            model_name="dashboardnotificationevent",
            index=models.Index(fields=["action", "created_at"], name="risk_dashbo_action_3d0109_idx"),
        ),
        migrations.AddIndex(
            model_name="dashboardnotificationevent",
            index=models.Index(fields=["notification", "created_at"], name="risk_dashbo_notific_56a5fc_idx"),
        ),
    ]
