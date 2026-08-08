from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0079_model_artifact_registry_governance"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="modelregistryentry",
            name="risk_modelreg_active_requires_approval",
        ),
        migrations.AddConstraint(
            model_name="modelregistryentry",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("lifecycle_state", "ACTIVE"), _negated=True),
                    models.Q(
                        ("approval_state", "APPROVED"),
                        ("promotion_state", "ACTIVE_PROMOTED"),
                        ("promotion_event__isnull", False),
                        ("active_from__isnull", False),
                        ("active_until__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="risk_modelreg_active_requires_approval",
            ),
        ),
    ]
