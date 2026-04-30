from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0017_dashboardnotification_dashboardnotificationevent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AlertWorkflowState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("status", models.CharField(choices=[("REVIEW_PENDING", "Review Pending"), ("QUEUED", "Queued"), ("DELIVERED", "Delivered"), ("RETRY_PENDING", "Retry Pending"), ("FAILED", "Failed"), ("RESOLVED", "Resolved")], default="REVIEW_PENDING", max_length=24)),
                ("decision_mode", models.CharField(default="risk_only", max_length=40)),
                ("confidence", models.CharField(default="review", max_length=20)),
                ("trigger_severity", models.CharField(choices=[("HIGH", "High"), ("MEDIUM", "Medium"), ("REVIEW", "Review")], default="REVIEW", max_length=20)),
                ("alert_delivery_state", models.CharField(default="awaiting_review", max_length=40)),
                ("alert_delivery_label", models.CharField(blank=True, max_length=120)),
                ("risk_level", models.CharField(blank=True, choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High")], max_length=10, null=True)),
                ("risk_score", models.FloatField(blank=True, null=True)),
                ("predicted_cases", models.PositiveIntegerField(default=0)),
                ("reason_flagged", models.TextField(blank=True)),
                ("trigger_reason", models.TextField(blank=True)),
                ("recommended_action", models.TextField(blank=True)),
                ("recommended_response", models.TextField(blank=True)),
                ("expected_operational_effect", models.TextField(blank=True)),
                ("rules_basis", models.JSONField(blank=True, default=dict)),
                ("trigger_reason_items", models.JSONField(blank=True, default=list)),
                ("eligible_actions", models.JSONField(blank=True, default=list)),
                ("active_alert_count", models.PositiveIntegerField(default=0)),
                ("delivered_alert_count", models.PositiveIntegerField(default=0)),
                ("retry_pending_alert_count", models.PositiveIntegerField(default=0)),
                ("failed_alert_count", models.PositiveIntegerField(default=0)),
                ("queued_alert_count", models.PositiveIntegerField(default=0)),
                ("triggered_at", models.DateTimeField(blank=True, null=True)),
                ("latest_risk_update_at", models.DateTimeField(blank=True, null=True)),
                ("last_manual_request_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("last_evaluated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("alert", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="workflow_states", to="risk.alert")),
                ("latest_risk_score", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="workflow_states", to="risk.riskscore")),
                ("ward", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="alert_workflow_state", to="risk.ward")),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="ScenarioSimulationRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("scenario_id", models.CharField(choices=[("RAINFALL_INCREASE", "Rainfall Increase"), ("RESPONSE_DELAY", "Response Delay")], max_length=40)),
                ("input_parameters", models.JSONField(blank=True, default=dict)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("ward_results", models.JSONField(blank=True, default=list)),
                ("facility_results", models.JSONField(blank=True, default=list)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="scenario_simulation_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AlertWorkflowEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("MATERIALIZED", "Materialized"), ("MANUAL_REQUEST_QUEUED", "Manual Request Queued"), ("STATUS_CHANGED", "Status Changed")], default="MATERIALIZED", max_length=32)),
                ("old_status", models.CharField(blank=True, max_length=24)),
                ("new_status", models.CharField(blank=True, max_length=24)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="alert_workflow_events", to=settings.AUTH_USER_MODEL)),
                ("workflow", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="risk.alertworkflowstate")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="alertworkflowstate",
            index=models.Index(fields=["status", "updated_at"], name="risk_alertw_status_4caea4_idx"),
        ),
        migrations.AddIndex(
            model_name="alertworkflowstate",
            index=models.Index(fields=["trigger_severity", "updated_at"], name="risk_alertw_trigger__3af095_idx"),
        ),
        migrations.AddIndex(
            model_name="alertworkflowstate",
            index=models.Index(fields=["last_evaluated_at"], name="risk_alertw_last_ev_f193f9_idx"),
        ),
        migrations.AddIndex(
            model_name="scenariosimulationrun",
            index=models.Index(fields=["scenario_id", "created_at"], name="risk_scenar_scenari_b31731_idx"),
        ),
        migrations.AddIndex(
            model_name="alertworkflowevent",
            index=models.Index(fields=["action", "created_at"], name="risk_alertw_action_2f5b2c_idx"),
        ),
        migrations.AddIndex(
            model_name="alertworkflowevent",
            index=models.Index(fields=["workflow", "created_at"], name="risk_alertw_workflo_20d4bc_idx"),
        ),
    ]
