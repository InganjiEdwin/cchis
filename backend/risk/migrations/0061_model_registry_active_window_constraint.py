# Generated manually on 2026-05-04

import django.utils.timezone
from django.db import migrations, models


def backfill_active_registry_windows(apps, schema_editor):
    ModelRegistryEntry = apps.get_model("risk", "ModelRegistryEntry")
    now = django.utils.timezone.now()
    queryset = ModelRegistryEntry.objects.filter(promotion_state="ACTIVE_PROMOTED").filter(
        models.Q(active_from__isnull=True) | models.Q(active_until__isnull=False)
    )
    for entry in queryset.only("id", "active_from", "active_until", "created_at", "updated_at").iterator():
        updates = {}
        if entry.active_from is None:
            updates["active_from"] = entry.updated_at or entry.created_at or now
        if entry.active_until is not None:
            updates["active_until"] = None
        if updates:
            ModelRegistryEntry.objects.filter(id=entry.id).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0060_model_rollback_event_constraints"),
    ]

    operations = [
        migrations.RunPython(
            backfill_active_registry_windows,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="modelregistryentry",
            constraint=models.CheckConstraint(
                check=(
                    ~models.Q(("promotion_state", "ACTIVE_PROMOTED"))
                    | (
                        models.Q(("active_from__isnull", False))
                        & models.Q(("active_until__isnull", True))
                    )
                ),
                name="risk_modelreg_active_window_required",
            ),
        ),
    ]
