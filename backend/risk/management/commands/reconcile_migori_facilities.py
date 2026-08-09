from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from risk.migori_facility_seed import MIGORI_MAP_VERIFIED_FACILITIES
from risk.models import HealthFacility, Ward, WardGeometryDatasetVersion, WardGeometryFeature


SYNTHETIC_FACILITY_CODE_PREFIXES = ("P9-",)


class Command(BaseCommand):
    help = "Reconcile local Migori facility seed records with browser-verified Google Maps place coordinates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report changes without writing the database.",
        )

    def handle(self, *args, **options):
        if settings.CCHIS_ENVIRONMENT == "production":
            raise CommandError("Browser-derived local facility seed data is blocked in production.")

        version = (
            WardGeometryDatasetVersion.objects.select_related("dataset")
            .filter(dataset__slug="migori-ward-boundaries", is_active=True)
            .order_by("-activated_at", "-id")
            .first()
        )
        if version is None:
            raise CommandError("The active Migori ward geometry version is required before facility reconciliation.")

        rows = []
        for facility_code, record in MIGORI_MAP_VERIFIED_FACILITIES.items():
            ward = Ward.objects.filter(county__iexact="Migori", ward_code=record["ward_code"], is_active=True).first()
            if ward is None:
                raise CommandError(
                    f"Canonical Migori ward {record['ward_code']} ({record['ward_name']}) was not found."
                )
            if ward.name != record["ward_name"]:
                raise CommandError(
                    f"Ward code {record['ward_code']} resolves to {ward.name!r}, not {record['ward_name']!r}."
                )

            feature = WardGeometryFeature.objects.filter(dataset_version=version, ward=ward).first()
            point = Point(record["longitude"], record["latitude"], srid=4326)
            if feature is None or feature.geometry is None or not feature.geometry.covers(point):
                raise CommandError(
                    f"{facility_code} coordinate is not covered by the managed geometry for {ward.name}."
                )

            rows.append((facility_code, record, ward, point))

        synthetic = list(
            HealthFacility.objects.filter(ward__county__iexact="Migori")
            .filter(facility_code__startswith=SYNTHETIC_FACILITY_CODE_PREFIXES[0])
            .order_by("facility_code")
        )
        self.stdout.write(f"Validated {len(rows)} browser-verified facility records against geometry version {version.version_label}.")
        for facility_code, record, ward, point in rows:
            self.stdout.write(
                f"- {facility_code}: {record['name']} -> {ward.name} ({point.y:.7f}, {point.x:.7f})"
            )
        self.stdout.write(f"Synthetic active records to retire: {len([item for item in synthetic if item.is_active])}.")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run complete; no database changes were made."))
            return

        with transaction.atomic():
            for facility_code, record, ward, point in rows:
                HealthFacility.objects.update_or_create(
                    facility_code=facility_code,
                    defaults={
                        "name": record["name"],
                        "ward": ward,
                        "facility_type": record["facility_type"],
                        "ownership": record["ownership"],
                        "level": record["level"],
                        "is_active": True,
                        "point": point,
                        "contact_phone": "",
                    },
                )

            for facility in synthetic:
                if facility.is_active:
                    facility.is_active = False
                    facility.save(update_fields=["is_active", "updated_at"])

        self.stdout.write(self.style.SUCCESS("Migori facility reconciliation applied."))
        if synthetic:
            self.stdout.write(
                "Synthetic Phase 9 records were retired from the active directory; protected history was retained."
            )
