from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0015_facilityforecast_facilityforecastrun_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ingestionrun",
            name="operator_note",
            field=models.TextField(blank=True),
        ),
    ]
