from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0018_alertworkflowstate_alertworkflowevent_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="guided_request_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
