from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0080_active_registry_requires_event"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="modelregistryentry",
            name="risk_modelreg_one_active_promoted",
        ),
    ]
