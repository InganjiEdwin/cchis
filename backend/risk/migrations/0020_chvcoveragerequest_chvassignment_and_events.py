from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("risk", "0019_alert_guided_request_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="CHVCoverageRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("OPEN", "Open"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                            ("IN_PROGRESS", "In Progress"),
                            ("RESOLVED", "Resolved"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="OPEN",
                        max_length=20,
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High")],
                        default="MEDIUM",
                        max_length=10,
                    ),
                ),
                (
                    "trigger_source",
                    models.CharField(
                        choices=[("MANUAL", "Manual"), ("ALERT_DRIVEN", "Alert Driven")],
                        default="MANUAL",
                        max_length=20,
                    ),
                ),
                ("reason", models.TextField()),
                ("requested_chv_count", models.PositiveIntegerField(default=1)),
                ("notes", models.TextField(blank=True)),
                ("assigned_to_team", models.CharField(blank=True, max_length=120)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_decision_reason", models.TextField(blank=True)),
                ("expected_response_by", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_to_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="chv_coverage_requests_owned",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="chv_coverage_requests_requested",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="chv_coverage_requests_reviewed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="chv_coverage_requests",
                        to="risk.ward",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CHVAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Active"), ("COMPLETED", "Completed"), ("CANCELLED", "Cancelled")],
                        default="ACTIVE",
                        max_length=20,
                    ),
                ),
                ("start_at", models.DateTimeField(blank=True, null=True)),
                ("end_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="chv_assignments_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "chv",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assignments",
                        to="risk.chv",
                    ),
                ),
                (
                    "coverage_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assignments",
                        to="risk.chvcoveragerequest",
                    ),
                ),
                (
                    "ward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="chv_assignments",
                        to="risk.ward",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CHVCoverageRequestEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("CREATED", "Created"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                            ("CANCELLED", "Cancelled"),
                            ("RESOLVED", "Resolved"),
                            ("OWNERSHIP_CHANGED", "Ownership Changed"),
                            ("ASSIGNMENT_CREATED", "Assignment Created"),
                            ("ASSIGNMENT_COMPLETED", "Assignment Completed"),
                            ("ASSIGNMENT_CANCELLED", "Assignment Cancelled"),
                        ],
                        max_length=32,
                    ),
                ),
                ("old_status", models.CharField(blank=True, max_length=20)),
                ("new_status", models.CharField(blank=True, max_length=20)),
                ("detail", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="chv_coverage_request_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "assignment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="events",
                        to="risk.chvassignment",
                    ),
                ),
                (
                    "coverage_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="events",
                        to="risk.chvcoveragerequest",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="chvcoveragerequest",
            index=models.Index(fields=["status", "created_at"], name="risk_chvcov_status_3a8532_idx"),
        ),
        migrations.AddIndex(
            model_name="chvcoveragerequest",
            index=models.Index(fields=["priority", "created_at"], name="risk_chvcov_priorit_54f322_idx"),
        ),
        migrations.AddIndex(
            model_name="chvcoveragerequest",
            index=models.Index(fields=["trigger_source", "created_at"], name="risk_chvcov_trigger_04df10_idx"),
        ),
        migrations.AddIndex(
            model_name="chvcoveragerequest",
            index=models.Index(fields=["expected_response_by"], name="risk_chvcov_expecte_1ad931_idx"),
        ),
        migrations.AddConstraint(
            model_name="chvcoveragerequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(status__in=["OPEN", "APPROVED", "IN_PROGRESS"]),
                fields=("ward",),
                name="unique_live_chv_coverage_request_per_ward",
            ),
        ),
        migrations.AddIndex(
            model_name="chvassignment",
            index=models.Index(fields=["status", "created_at"], name="risk_chvass_status_bcfa68_idx"),
        ),
        migrations.AddIndex(
            model_name="chvassignment",
            index=models.Index(fields=["ward", "status"], name="risk_chvass_ward_id_9eb603_idx"),
        ),
        migrations.AddIndex(
            model_name="chvassignment",
            index=models.Index(fields=["chv", "status"], name="risk_chvass_chv_id_3f583f_idx"),
        ),
        migrations.AddConstraint(
            model_name="chvassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="ACTIVE"),
                fields=("coverage_request",),
                name="unique_active_chv_assignment_per_request",
            ),
        ),
        migrations.AddIndex(
            model_name="chvcoveragerequestevent",
            index=models.Index(fields=["action", "created_at"], name="risk_chvcov_action_567608_idx"),
        ),
        migrations.AddIndex(
            model_name="chvcoveragerequestevent",
            index=models.Index(fields=["coverage_request", "created_at"], name="risk_chvcov_coverag_2b70a4_idx"),
        ),
    ]
