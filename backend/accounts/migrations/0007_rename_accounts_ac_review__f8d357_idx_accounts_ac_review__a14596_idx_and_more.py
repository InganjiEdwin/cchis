from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_user_totp_fields_and_preauthtoken"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="accessrequest",
            new_name="accounts_ac_review__a14596_idx",
            old_name="accounts_ac_review__f8d357_idx",
        ),
        migrations.RenameIndex(
            model_name="accessrequest",
            new_name="accounts_ac_contact_8d951e_idx",
            old_name="accounts_ac_contact_c29f00_idx",
        ),
        migrations.RenameIndex(
            model_name="passwordresettoken",
            new_name="accounts_pa_token_affdf2_idx",
            old_name="accounts_pa_token_6e41d8_idx",
        ),
        migrations.RenameIndex(
            model_name="passwordresettoken",
            new_name="accounts_pa_expires_4f8a3c_idx",
            old_name="accounts_pa_expires_86f225_idx",
        ),
        migrations.RenameIndex(
            model_name="preauthtoken",
            new_name="accounts_pr_token_feef16_idx",
            old_name="accounts_pr_token_0226d3_idx",
        ),
        migrations.RenameIndex(
            model_name="preauthtoken",
            new_name="accounts_pr_expires_1faa15_idx",
            old_name="accounts_pr_expires_575df2_idx",
        ),
        migrations.AlterField(
            model_name="authauditevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("LOGIN_SUCCESS", "Login Success"),
                    ("LOGIN_FAILED", "Login Failed"),
                    ("LOGOUT", "Logout"),
                    ("REFRESH_SUCCESS", "Refresh Success"),
                    ("REFRESH_FAILED", "Refresh Failed"),
                    ("PASSWORD_CHANGED", "Password Changed"),
                    ("PASSWORD_RESET_COMPLETED", "Password Reset Completed"),
                    ("TWO_FACTOR_ENROLLMENT_REQUIRED", "Two-Factor Enrollment Required"),
                    ("TWO_FACTOR_ENROLLMENT_STARTED", "Two-Factor Enrollment Started"),
                    ("TWO_FACTOR_ENROLLMENT_COMPLETED", "Two-Factor Enrollment Completed"),
                    ("TWO_FACTOR_REQUIRED", "Two-Factor Required"),
                    ("TWO_FACTOR_VERIFIED", "Two-Factor Verified"),
                    ("TWO_FACTOR_FAILED", "Two-Factor Failed"),
                    ("USER_CREATED", "User Created"),
                    ("USER_DEACTIVATED", "User Deactivated"),
                    ("USER_REACTIVATED", "User Reactivated"),
                ],
                max_length=40,
            ),
        ),
    ]
