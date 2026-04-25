from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0010_wardgeometrydataset_wardgeometrydatasetversion_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="wardgeometrydatasetversion",
            name="activated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ward_geometry_activations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
