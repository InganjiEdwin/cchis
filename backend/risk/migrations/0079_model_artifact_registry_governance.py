import django.db.models.deletion
import django.utils.timezone
import risk.models
import uuid

from django.db import migrations, models


def reset_legacy_registry_state(apps, schema_editor):
    ModelRegistryEntry = apps.get_model("risk", "ModelRegistryEntry")
    active_promoted = "ACTIVE_PROMOTED"
    for entry in ModelRegistryEntry.objects.all().iterator():
        metadata = dict(entry.metadata or {})
        if entry.promotion_state == active_promoted:
            metadata["legacy_promotion_state_before_artifact_governance"] = active_promoted
            metadata["artifact_governance_reset"] = "legacy_active_state_requires_new_review"
            entry.promotion_state = "CANDIDATE"
            entry.active_from = None
            entry.active_until = None
        if entry.promotion_state == "RETIRED":
            entry.lifecycle_state = "RETIRED"
        elif entry.promotion_state == "ROLLED_BACK":
            entry.lifecycle_state = "ROLLED_BACK"
        else:
            entry.lifecycle_state = "CANDIDATE"
        entry.approval_state = "NOT_REVIEWED"
        entry.metadata = metadata
        entry.save(
            update_fields=[
                "promotion_state",
                "lifecycle_state",
                "approval_state",
                "active_from",
                "active_until",
                "metadata",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0078_alert_callback_payload_hash_alert_delivery_kind_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelGovernanceEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("REGISTERED", "Registered"),
                            ("APPROVAL_REQUESTED", "Approval requested"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                            ("CHALLENGER_DESIGNATED", "Challenger designated"),
                            ("ACTIVATED", "Activated"),
                            ("RETIRED", "Retired"),
                            ("ROLLED_BACK", "Rolled back"),
                        ],
                        max_length=40,
                    ),
                ),
                ("actor", models.CharField(max_length=160)),
                ("reason", models.TextField()),
                ("previous_approval_state", models.CharField(blank=True, max_length=32)),
                ("resulting_approval_state", models.CharField(blank=True, max_length=32)),
                ("previous_lifecycle_state", models.CharField(blank=True, max_length=32)),
                ("resulting_lifecycle_state", models.CharField(blank=True, max_length=32)),
                ("evidence_snapshot", models.JSONField(blank=True, default=dict)),
                ("request_id", models.CharField(blank=True, max_length=160)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={"ordering": ["-occurred_at", "-id"]},
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="approval_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="approval_state",
            field=models.CharField(
                choices=[
                    ("NOT_REVIEWED", "Not reviewed"),
                    ("PENDING_REVIEW", "Pending review"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                ],
                default="NOT_REVIEWED",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="approved_by",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="artifact_format",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="artifact_location",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="artifact_sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="artifact_size_bytes",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="challenger_of",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="challengers",
                to="risk.modelregistryentry",
            ),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="code_commit",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="deployment_target",
            field=models.CharField(default="live_baseline", max_length=80),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="evaluation_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="evaluation_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="feature_contract",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="intended_use",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="lifecycle_state",
            field=models.CharField(
                choices=[
                    ("CANDIDATE", "Candidate"),
                    ("CHALLENGER", "Challenger"),
                    ("ACTIVE", "Active"),
                    ("RETIRED", "Retired"),
                    ("ROLLED_BACK", "Rolled back"),
                ],
                default="CANDIDATE",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="metrics",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="model_family",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="prohibited_uses",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="registration_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="registry_version",
            field=models.CharField(
                default=risk.models._default_model_registry_version,
                editable=False,
                max_length=180,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="training_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="training_label_dataset_ref",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="training_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="modelregistryentry",
            name="truth_source_classification",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddIndex(
            model_name="modelregistryentry",
            index=models.Index(
                fields=["lifecycle_state", "deployment_target"],
                name="risk_modelreg_life_target_idx",
            ),
        ),
        migrations.RunPython(reset_legacy_registry_state, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="modelregistryentry",
            constraint=models.UniqueConstraint(
                condition=models.Q(("lifecycle_state", "ACTIVE")),
                fields=("deployment_target", "lifecycle_state"),
                name="risk_modelreg_one_active_per_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="modelregistryentry",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("lifecycle_state", "ACTIVE"), _negated=True),
                    models.Q(
                        ("approval_state", "APPROVED"),
                        ("promotion_state", "ACTIVE_PROMOTED"),
                        ("active_from__isnull", False),
                        ("active_until__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="risk_modelreg_active_requires_approval",
            ),
        ),
        migrations.AddConstraint(
            model_name="modelregistryentry",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("approval_state", "APPROVED"), _negated=True),
                    models.Q(("approved_at__isnull", False), ("approved_by__regex", r"\S")),
                    _connector="OR",
                ),
                name="risk_modelreg_approved_requires_evidence",
            ),
        ),
        migrations.AddConstraint(
            model_name="modelregistryentry",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("lifecycle_state", "CHALLENGER"), _negated=True),
                    ("challenger_of__isnull", False),
                    _connector="OR",
                ),
                name="risk_modelreg_challenger_requires_target",
            ),
        ),
        migrations.AddField(
            model_name="modelgovernanceevent",
            name="registry_entry",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="governance_events",
                to="risk.modelregistryentry",
            ),
        ),
        migrations.AddIndex(
            model_name="modelgovernanceevent",
            index=models.Index(
                fields=["registry_entry", "occurred_at"],
                name="risk_modelgov_entry_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="modelgovernanceevent",
            index=models.Index(
                fields=["event_type", "occurred_at"],
                name="risk_modelgov_type_time_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="modelgovernanceevent",
            constraint=models.CheckConstraint(
                condition=models.Q(("actor__regex", r"\S")),
                name="risk_modelgov_actor_not_blank",
            ),
        ),
        migrations.AddConstraint(
            model_name="modelgovernanceevent",
            constraint=models.CheckConstraint(
                condition=models.Q(("reason__regex", r"\S")),
                name="risk_modelgov_reason_not_blank",
            ),
        ),
    ]
