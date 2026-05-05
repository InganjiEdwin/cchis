# Generated manually for child plan 11 phases 0 and 1 on 2026-05-04

from django.db import migrations, models


SUPPORTED_LANGUAGES = ("en", "sw", "luo")
LANGUAGE_CHOICES = [
    ("en", "English"),
    ("sw", "Kiswahili"),
    ("luo", "Dholuo"),
]
DEFAULT_LANGUAGE = "en"


def supported_language_or_default(value):
    normalized = (value or "").strip().lower()
    if normalized in SUPPORTED_LANGUAGES:
        return normalized
    return DEFAULT_LANGUAGE


def normalize_requested_language(value):
    return (value or "").strip().lower() or DEFAULT_LANGUAGE


def normalize_existing_languages(apps, schema_editor):
    MessageTemplate = apps.get_model("risk", "MessageTemplate")
    CHV = apps.get_model("risk", "CHV")
    CHVDeviceRegistration = apps.get_model("risk", "CHVDeviceRegistration")
    UssdMenuVersion = apps.get_model("risk", "UssdMenuVersion")
    UssdSessionLog = apps.get_model("risk", "UssdSessionLog")

    for template in MessageTemplate.objects.all().only("id", "language").iterator():
        normalized = supported_language_or_default(template.language)
        if template.language != normalized:
            template.language = normalized
            template.save(update_fields=["language"])

    for chv in CHV.objects.all().only("id", "language", "preferred_language").iterator():
        normalized = supported_language_or_default(chv.preferred_language or chv.language)
        if chv.language != normalized or chv.preferred_language != normalized:
            chv.language = normalized
            chv.preferred_language = normalized
            chv.save(update_fields=["language", "preferred_language"])

    chv_language_by_id = {
        chv.id: chv.preferred_language
        for chv in CHV.objects.all().only("id", "preferred_language")
    }
    for registration in CHVDeviceRegistration.objects.all().only("id", "chv_id", "preferred_language").iterator():
        normalized = supported_language_or_default(
            registration.preferred_language or chv_language_by_id.get(registration.chv_id)
        )
        if registration.preferred_language != normalized:
            registration.preferred_language = normalized
            registration.save(update_fields=["preferred_language"])

    for menu_version in UssdMenuVersion.objects.all().only("id", "language").iterator():
        normalized = supported_language_or_default(menu_version.language)
        if menu_version.language != normalized:
            menu_version.language = normalized
            menu_version.save(update_fields=["language"])

    for log in UssdSessionLog.objects.all().only("id", "language", "requested_language", "resolved_language").iterator():
        requested = normalize_requested_language(log.requested_language or log.language)
        resolved = supported_language_or_default(log.resolved_language or log.language)
        language = resolved
        if log.requested_language != requested or log.resolved_language != resolved or log.language != language:
            log.requested_language = requested
            log.resolved_language = resolved
            log.language = language
            log.fallback_used = requested != resolved
            log.save(update_fields=["requested_language", "resolved_language", "language", "fallback_used"])


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0063_feedback_governance"),
    ]

    operations = [
        migrations.AddField(
            model_name="chv",
            name="preferred_language",
            field=models.CharField(choices=LANGUAGE_CHOICES, default=DEFAULT_LANGUAGE, max_length=20),
        ),
        migrations.AddField(
            model_name="chvdeviceregistration",
            name="preferred_language",
            field=models.CharField(choices=LANGUAGE_CHOICES, default=DEFAULT_LANGUAGE, max_length=20),
        ),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="requested_language",
            field=models.CharField(default=DEFAULT_LANGUAGE, max_length=20),
        ),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="resolved_language",
            field=models.CharField(choices=LANGUAGE_CHOICES, default=DEFAULT_LANGUAGE, max_length=20),
        ),
        migrations.AddField(
            model_name="ussdsessionlog",
            name="fallback_used",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="messagetemplate",
            name="language",
            field=models.CharField(choices=LANGUAGE_CHOICES, default=DEFAULT_LANGUAGE, max_length=20),
        ),
        migrations.AlterField(
            model_name="chv",
            name="language",
            field=models.CharField(choices=LANGUAGE_CHOICES, default=DEFAULT_LANGUAGE, max_length=20),
        ),
        migrations.AlterField(
            model_name="ussdmenuversion",
            name="language",
            field=models.CharField(choices=LANGUAGE_CHOICES, default=DEFAULT_LANGUAGE, max_length=20),
        ),
        migrations.AlterField(
            model_name="ussdsessionlog",
            name="language",
            field=models.CharField(choices=LANGUAGE_CHOICES, default=DEFAULT_LANGUAGE, max_length=20),
        ),
        migrations.RunPython(normalize_existing_languages, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="messagetemplate",
            constraint=models.CheckConstraint(
                check=models.Q(language__in=SUPPORTED_LANGUAGES),
                name="risk_msgtmpl_lang_supported",
            ),
        ),
        migrations.AddConstraint(
            model_name="chv",
            constraint=models.CheckConstraint(
                check=models.Q(language__in=SUPPORTED_LANGUAGES),
                name="risk_chv_language_supported",
            ),
        ),
        migrations.AddConstraint(
            model_name="chv",
            constraint=models.CheckConstraint(
                check=models.Q(preferred_language__in=SUPPORTED_LANGUAGES),
                name="risk_chv_preflang_supported",
            ),
        ),
        migrations.AddConstraint(
            model_name="chvdeviceregistration",
            constraint=models.CheckConstraint(
                check=models.Q(preferred_language__in=SUPPORTED_LANGUAGES),
                name="risk_chvdev_preflang_supported",
            ),
        ),
        migrations.AddConstraint(
            model_name="ussdmenuversion",
            constraint=models.CheckConstraint(
                check=models.Q(language__in=SUPPORTED_LANGUAGES),
                name="risk_ussdmenu_lang_supported",
            ),
        ),
        migrations.AddConstraint(
            model_name="ussdsessionlog",
            constraint=models.CheckConstraint(
                check=models.Q(language__in=SUPPORTED_LANGUAGES),
                name="risk_ussdlog_lang_supported",
            ),
        ),
        migrations.AddConstraint(
            model_name="ussdsessionlog",
            constraint=models.CheckConstraint(
                check=models.Q(resolved_language__in=SUPPORTED_LANGUAGES),
                name="risk_ussdlog_reslang_supported",
            ),
        ),
    ]
