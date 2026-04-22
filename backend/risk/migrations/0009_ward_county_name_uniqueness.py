from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0008_alert_attempt_count_alert_delivery_backend_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ward",
            name="name",
            field=models.CharField(max_length=120),
        ),
        migrations.AddConstraint(
            model_name="ward",
            constraint=models.UniqueConstraint(fields=("county", "name"), name="unique_ward_name_per_county"),
        ),
    ]
