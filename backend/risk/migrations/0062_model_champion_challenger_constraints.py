# Generated manually on 2026-05-04

from django.db import migrations, models


def remove_invalid_self_comparisons(apps, schema_editor):
    ModelChampionChallengerComparison = apps.get_model("risk", "ModelChampionChallengerComparison")
    ModelChampionChallengerComparison.objects.filter(
        champion_model_run_id=models.F("challenger_model_run_id")
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0061_model_registry_active_window_constraint"),
    ]

    operations = [
        migrations.RunPython(
            remove_invalid_self_comparisons,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="modelchampionchallengercomparison",
            constraint=models.CheckConstraint(
                check=models.Q(("champion_model_run", models.F("challenger_model_run")), _negated=True),
                name="risk_modelcc_champion_diff_challenger",
            ),
        ),
    ]
