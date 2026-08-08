from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("risk", "0082_registry_dataset_reference_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelpromotionevent",
            name="promoted_by_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="model_promotions_governed",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="modelrollbackevent",
            name="rolled_back_by_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="model_rollbacks_governed",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="modelgovernanceevent",
            name="actor_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="model_governance_events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="modelgovernanceevent",
            name="previous_promotion_state",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="modelgovernanceevent",
            name="resulting_promotion_state",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
