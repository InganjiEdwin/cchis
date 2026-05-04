# Generated for cholera early warning privacy plan phase 2 on 2026-05-03

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0041_preparedness_action_ledger"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ContactPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "audience_type",
                    models.CharField(
                        choices=[
                            ("HOUSEHOLD", "Household"),
                            ("CHV", "CHV"),
                            ("FACILITY_CONTACT", "Facility contact"),
                            ("OPERATOR", "Operator"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("SMS", "SMS"),
                            ("EMAIL", "Email"),
                            ("USSD", "USSD"),
                            ("SYSTEM", "System"),
                        ],
                        default="SMS",
                        max_length=20,
                    ),
                ),
                ("phone_number", models.CharField(blank=True, max_length=20)),
                ("contact_reference", models.CharField(blank=True, max_length=180)),
                (
                    "consent_status",
                    models.CharField(
                        choices=[
                            ("UNKNOWN", "Unknown"),
                            ("GRANTED", "Granted"),
                            ("DENIED", "Denied"),
                            ("EXPIRED", "Expired"),
                        ],
                        default="UNKNOWN",
                        max_length=20,
                    ),
                ),
                (
                    "opt_out_status",
                    models.CharField(
                        choices=[
                            ("NOT_OPTED_OUT", "Not opted out"),
                            ("OPTED_OUT", "Opted out"),
                        ],
                        default="NOT_OPTED_OUT",
                        max_length=20,
                    ),
                ),
                ("source", models.CharField(max_length=120)),
                ("source_reference", models.CharField(blank=True, max_length=180)),
                ("recorded_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contact_preferences_recorded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-recorded_at", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ContactPreferenceAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("RECORDED", "Recorded"),
                            ("ALLOWED", "Allowed"),
                            ("BLOCKED_OPT_OUT", "Blocked by opt-out"),
                            ("BLOCKED_CONSENT_REQUIRED", "Blocked because consent is required"),
                            ("BLOCKED_CONSENT_DENIED", "Blocked because consent was denied"),
                            ("BLOCKED_CONSENT_EXPIRED", "Blocked because consent expired"),
                            ("EMERGENCY_OVERRIDE_USED", "Emergency override used"),
                        ],
                        max_length=40,
                    ),
                ),
                (
                    "audience_type",
                    models.CharField(
                        choices=[
                            ("HOUSEHOLD", "Household"),
                            ("CHV", "CHV"),
                            ("FACILITY_CONTACT", "Facility contact"),
                            ("OPERATOR", "Operator"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("SMS", "SMS"),
                            ("EMAIL", "Email"),
                            ("USSD", "USSD"),
                            ("SYSTEM", "System"),
                        ],
                        default="SMS",
                        max_length=20,
                    ),
                ),
                ("phone_number", models.CharField(blank=True, max_length=20)),
                ("contact_reference", models.CharField(blank=True, max_length=180)),
                ("reason", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contact_preference_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "preference",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events",
                        to="risk.contactpreference",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="contactpreference",
            index=models.Index(fields=["audience_type", "channel", "phone_number"], name="risk_contactpref_phone_idx"),
        ),
        migrations.AddIndex(
            model_name="contactpreference",
            index=models.Index(fields=["audience_type", "channel", "contact_reference"], name="risk_contactpref_ref_idx"),
        ),
        migrations.AddIndex(
            model_name="contactpreference",
            index=models.Index(fields=["opt_out_status", "recorded_at"], name="risk_contactpref_opt_idx"),
        ),
        migrations.AddIndex(
            model_name="contactpreference",
            index=models.Index(fields=["consent_status", "recorded_at"], name="risk_contactpref_con_idx"),
        ),
        migrations.AddIndex(
            model_name="contactpreference",
            index=models.Index(fields=["expires_at", "recorded_at"], name="risk_contactpref_exp_idx"),
        ),
        migrations.AddConstraint(
            model_name="contactpreference",
            constraint=models.CheckConstraint(
                check=models.Q(phone_number__gt="") | models.Q(contact_reference__gt=""),
                name="contact_preference_requires_phone_or_ref",
            ),
        ),
        migrations.AddIndex(
            model_name="contactpreferenceauditevent",
            index=models.Index(fields=["action", "created_at"], name="risk_contactaudit_action_idx"),
        ),
        migrations.AddIndex(
            model_name="contactpreferenceauditevent",
            index=models.Index(fields=["audience_type", "channel", "created_at"], name="risk_contactaudit_aud_idx"),
        ),
        migrations.AddIndex(
            model_name="contactpreferenceauditevent",
            index=models.Index(fields=["contact_reference", "created_at"], name="risk_contactaudit_ref_idx"),
        ),
        migrations.AddIndex(
            model_name="contactpreferenceauditevent",
            index=models.Index(fields=["phone_number", "created_at"], name="risk_contactaudit_phone_idx"),
        ),
    ]
