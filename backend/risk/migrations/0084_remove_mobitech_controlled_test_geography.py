from django.db import migrations


MOBITECH_CONTROLLED_TEST_WARD_PUBLIC_ID = "11b83323-4a36-4f66-af6f-f6d6e4a5373c"


def remove_mobitech_controlled_test_geography(apps, schema_editor):
    Ward = apps.get_model("risk", "Ward")
    Alert = apps.get_model("risk", "Alert")
    AlertDeliveryEvent = apps.get_model("risk", "AlertDeliveryEvent")
    DashboardNotification = apps.get_model("risk", "DashboardNotification")

    ward = Ward.objects.filter(public_id=MOBITECH_CONTROLLED_TEST_WARD_PUBLIC_ID).first()
    if ward is None:
        return

    # These rows were confirmed to be exclusively linked to this controlled
    # test ward before cleanup. Delete SET_NULL dependants explicitly so no
    # orphaned delivery or notification records survive the ward removal.
    alert_ids = list(Alert.objects.filter(ward_id=ward.pk).values_list("pk", flat=True))
    AlertDeliveryEvent.objects.filter(alert_id__in=alert_ids).delete()
    DashboardNotification.objects.filter(ward_id=ward.pk).delete()
    ward.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0083_governance_actor_identity_and_event_sequence"),
    ]

    operations = [
        migrations.RunPython(
            remove_mobitech_controlled_test_geography,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
