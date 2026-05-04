# Generated manually on 2026-05-04

from django.db import migrations, models


def backfill_rollback_event_operator_and_reason(apps, schema_editor):
    ModelRollbackEvent = apps.get_model("risk", "ModelRollbackEvent")
    for event in ModelRollbackEvent.objects.all().iterator():
        updates = {}
        if not (event.reason or "").strip():
            updates["reason"] = "legacy_missing_rollback_reason_before_governance_constraint"
        if not (event.rolled_back_by or "").strip():
            updates["rolled_back_by"] = "legacy_unknown_operator_before_governance_constraint"
        if updates:
            ModelRollbackEvent.objects.filter(id=event.id).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0059_model_champion_challenger_comparisons"),
    ]

    operations = [
        migrations.RunPython(
            backfill_rollback_event_operator_and_reason,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="modelrollbackevent",
            constraint=models.CheckConstraint(
                check=models.Q(("reason__regex", "\\S")),
                name="risk_modelroll_reason_not_blank",
            ),
        ),
        migrations.AddConstraint(
            model_name="modelrollbackevent",
            constraint=models.CheckConstraint(
                check=models.Q(("rolled_back_by__regex", "\\S")),
                name="risk_modelroll_operator_not_blank",
            ),
        ),
        migrations.AddConstraint(
            model_name="modelrollbackevent",
            constraint=models.CheckConstraint(
                check=models.Q(("rolled_back_from", models.F("rollback_target")), _negated=True),
                name="risk_modelroll_target_diff",
            ),
        ),
    ]
