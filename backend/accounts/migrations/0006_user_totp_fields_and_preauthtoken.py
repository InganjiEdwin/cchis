from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_accessrequest"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_totp_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="totp_secret",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.CreateModel(
            name="PreAuthToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=128, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="pre_auth_tokens",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="preauthtoken",
            index=models.Index(fields=["token"], name="accounts_pr_token_0226d3_idx"),
        ),
        migrations.AddIndex(
            model_name="preauthtoken",
            index=models.Index(fields=["expires_at", "used_at"], name="accounts_pr_expires_575df2_idx"),
        ),
    ]
