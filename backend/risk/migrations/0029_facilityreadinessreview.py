import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0028_facilitycontact"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FacilityReadinessReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("OPEN", "Open"),
                            ("ACKNOWLEDGED", "Acknowledged"),
                            ("RESOLVED", "Resolved"),
                            ("DISMISSED", "Dismissed"),
                        ],
                        default="OPEN",
                        max_length=20,
                    ),
                ),
                (
                    "severity",
                    models.CharField(
                        choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High")],
                        default="LOW",
                        max_length=10,
                    ),
                ),
                ("reason_codes", models.JSONField(blank=True, default=list)),
                ("decision_summary_snapshot", models.JSONField(blank=True, default=dict)),
                ("notes", models.TextField(blank=True)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("dismissed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="facility_readiness_reviews_assigned",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="facility_readiness_reviews_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "facility",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="readiness_reviews",
                        to="risk.healthfacility",
                    ),
                ),
                (
                    "ward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="facility_readiness_reviews",
                        to="risk.ward",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="FacilityReadinessReviewEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("CREATED", "Created"),
                            ("ACKNOWLEDGED", "Acknowledged"),
                            ("RESOLVED", "Resolved"),
                            ("DISMISSED", "Dismissed"),
                        ],
                        max_length=30,
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
                        related_name="facility_readiness_review_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "review",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="events",
                        to="risk.facilityreadinessreview",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="facilityreadinessreview",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ["OPEN", "ACKNOWLEDGED"])),
                fields=("facility",),
                name="unique_active_facility_readiness_review",
            ),
        ),
        migrations.AddIndex(
            model_name="facilityreadinessreview",
            index=models.Index(fields=["status", "created_at"], name="risk_facrev_status_idx"),
        ),
        migrations.AddIndex(
            model_name="facilityreadinessreview",
            index=models.Index(fields=["facility", "status"], name="risk_facrev_facility_idx"),
        ),
        migrations.AddIndex(
            model_name="facilityreadinessreview",
            index=models.Index(fields=["ward", "status"], name="risk_facrev_ward_idx"),
        ),
        migrations.AddIndex(
            model_name="facilityreadinessreviewevent",
            index=models.Index(fields=["review", "created_at"], name="risk_facreve_review_idx"),
        ),
        migrations.AddIndex(
            model_name="facilityreadinessreviewevent",
            index=models.Index(fields=["action", "created_at"], name="risk_facreve_action_idx"),
        ),
    ]
