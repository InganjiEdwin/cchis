from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_rename_accounts_ac_review__f8d357_idx_accounts_ac_review__a14596_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="theme_preference",
            field=models.CharField(
                choices=[("SYSTEM", "System"), ("LIGHT", "Light"), ("DARK", "Dark")],
                default="SYSTEM",
                max_length=10,
            ),
        ),
    ]
