from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_accessrequest_intake_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="accessrequest",
            name="decision_message",
            field=models.TextField(blank=True),
        ),
    ]
