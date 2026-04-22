from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_user_theme_preference"),
    ]

    operations = [
        migrations.AddField(
            model_name="accessrequest",
            name="administrative_ward",
            field=models.CharField(default="", max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="accessrequest",
            name="county",
            field=models.CharField(default="Migori", max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="accessrequest",
            name="phone_number",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AlterField(
            model_name="accessrequest",
            name="organization",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
