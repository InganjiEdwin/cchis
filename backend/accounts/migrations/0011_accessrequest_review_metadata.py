from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_accessrequest_decision_message"),
    ]

    operations = [
        migrations.AddField(
            model_name="accessrequest",
            name="challenge_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="accessrequest",
            name="submitted_from_ip",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="accessrequest",
            index=models.Index(fields=["submitted_from_ip", "submitted_at"], name="accounts_ac_ip_sub_idx"),
        ),
    ]
