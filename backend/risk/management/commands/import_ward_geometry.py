import json
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from risk.map_data import MIGORI_WARD_GEOMETRY_PATH, normalize_ward_name
from risk.models import Ward, WardGeometryDataset, WardGeometryDatasetVersion, WardGeometryFeature
from risk.prepare_migori_ward_geometry import DEFAULT_REFERENCE_CSV, prepare_geometry_payload
from risk.ward_geometry_ops import activate_geometry_version, resolve_operator
from risk.ward_geometry_pipeline import build_geometry_validation_summary, compute_file_sha256


class Command(BaseCommand):
    help = (
        "Import ward geometry into the managed dataset/version/feature tables using "
        "the canonical preparation and validation pipeline."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            dest="input_path",
            default=str(MIGORI_WARD_GEOMETRY_PATH),
            help="Path to the source GeoJSON file to import.",
        )
        parser.add_argument(
            "--reference-csv",
            default=str(DEFAULT_REFERENCE_CSV),
            help="Path to the canonical Kenya wards CSV used during preparation.",
        )
        parser.add_argument("--county", default="Migori", help="County name to import.")
        parser.add_argument(
            "--dataset-slug",
            default="migori-ward-boundaries",
            help="Logical dataset slug for the managed geometry dataset.",
        )
        parser.add_argument(
            "--dataset-name",
            default="Migori Ward Boundaries",
            help="Logical dataset display name.",
        )
        parser.add_argument(
            "--version-label",
            required=True,
            help="Version label for the imported dataset version.",
        )
        parser.add_argument(
            "--source-url",
            default="",
            help=(
                "Source URL to record on the managed dataset version. Required unless the input "
                "GeoJSON metadata already provides source or source_url."
            ),
        )
        parser.add_argument(
            "--source-name",
            default="",
            help="Optional source name override for the managed dataset version.",
        )
        parser.add_argument(
            "--source-license",
            default="",
            help="Optional source license override.",
        )
        parser.add_argument(
            "--source-crs",
            default="",
            help="Optional source CRS override.",
        )
        parser.add_argument(
            "--notes",
            default="",
            help="Optional operator notes for the imported version.",
        )
        parser.add_argument(
            "--operator-username",
            default="",
            help="Optional username to record as the import and activation operator.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run preparation and validation without writing any database rows.",
        )
        parser.add_argument(
            "--activate",
            action="store_true",
            help="Mark the imported version active after successful import.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail when validation finds missing wards, duplicates, placeholder geometry, or unmatched features.",
        )

    def handle(self, *args, **options):
        input_path = Path(options["input_path"]).expanduser().resolve()
        reference_csv = Path(options["reference_csv"]).expanduser().resolve()
        county = options["county"].strip().title()
        dataset_slug = options["dataset_slug"].strip()
        dataset_name = options["dataset_name"].strip()
        version_label = options["version_label"].strip()
        source_url_override = options["source_url"].strip()
        source_name_override = options["source_name"].strip()
        source_license_override = options["source_license"].strip()
        source_crs_override = options["source_crs"].strip()
        notes = options["notes"].strip()
        operator_username = options["operator_username"].strip() or None
        dry_run = options["dry_run"]
        activate = options["activate"]
        strict = options["strict"]

        if not input_path.exists():
            raise CommandError(f"Input GeoJSON not found: {input_path}")
        if not reference_csv.exists():
            raise CommandError(f"Reference CSV not found: {reference_csv}")
        if not dataset_slug:
            raise CommandError("dataset-slug is required.")
        if not version_label:
            raise CommandError("version-label is required.")

        try:
            input_payload = json.loads(input_path.read_text())
        except json.JSONDecodeError as error:
            raise CommandError(f"Invalid JSON in {input_path}: {error}") from error
        input_metadata = input_payload.get("metadata", {}) if isinstance(input_payload, dict) else {}
        metadata_source_url = str(input_metadata.get("source", "")).strip() or str(
            input_metadata.get("source_url", "")
        ).strip()
        default_source_url = source_url_override or metadata_source_url
        if not default_source_url:
            raise CommandError(
                "source-url is required unless the input GeoJSON metadata provides source or source_url."
            )

        prepared_payload = prepare_geometry_payload(
            input_path=input_path,
            reference_csv=reference_csv,
            county=county,
            source_url=default_source_url,
        )
        validation_summary = build_geometry_validation_summary(prepared_payload, county)
        metadata = prepared_payload.get("metadata", {})

        self.stdout.write(self.style.MIGRATE_HEADING("Ward geometry managed import"))
        self.stdout.write(f"Input file: {input_path}")
        self.stdout.write(f"Dataset slug: {dataset_slug}")
        self.stdout.write(f"Version label: {version_label}")
        self.stdout.write(f"County: {county}")
        self.stdout.write(f"Prepared feature count: {validation_summary['filtered_feature_count']}")
        self.stdout.write(f"Backend ward count: {validation_summary['backend_ward_count']}")
        self.stdout.write(
            "Backend matching: "
            + f"code={validation_summary['backend_ward_code_match_count']}, "
            + f"name_fallback={validation_summary['backend_ward_name_fallback_match_count']}, "
            + f"unmatched={validation_summary['backend_ward_unmatched_feature_count']}"
        )
        self.stdout.write(
            "Placeholder geometry detected: "
            + ("yes" if validation_summary["placeholder_geometry_detected"] else "no")
        )

        should_fail = any(
            [
                validation_summary["invalid_geometry_features"],
                validation_summary["placeholder_geometry_detected"],
                validation_summary["duplicate_source_names"],
                validation_summary["duplicate_source_codes"],
                validation_summary["missing_backend_ward_names"],
                validation_summary["backend_ward_unmatched_feature_count"],
            ]
        )
        if strict and should_fail:
            raise CommandError(
                "Ward geometry import failed strict validation. Review missing wards, duplicates, "
                "invalid geometry types, placeholder geometry, or unmatched features."
            )

        if dry_run:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Dry run complete. No managed geometry rows were written."))
            return

        if WardGeometryDatasetVersion.objects.filter(
            dataset__slug=dataset_slug,
            version_label=version_label,
        ).exists():
            raise CommandError(
                f"Managed geometry version already exists for dataset '{dataset_slug}' and version '{version_label}'."
            )

        try:
            operator = resolve_operator(operator_username)
        except ValueError as error:
            raise CommandError(str(error)) from error

        with transaction.atomic():
            dataset, _ = WardGeometryDataset.objects.get_or_create(
                slug=dataset_slug,
                defaults={
                    "name": dataset_name,
                    "coverage_scope": WardGeometryDataset.SCOPE_COUNTY,
                    "geometry_kind": WardGeometryDataset.KIND_WARD_BOUNDARIES,
                    "is_active": True,
                },
            )
            dataset_updates = []
            if dataset.name != dataset_name:
                dataset.name = dataset_name
                dataset_updates.append("name")
            if not dataset.is_active:
                dataset.is_active = True
                dataset_updates.append("is_active")
            if dataset_updates:
                dataset.save(update_fields=dataset_updates)

            version = WardGeometryDatasetVersion.objects.create(
                dataset=dataset,
                version_label=version_label,
                source_name=source_name_override or metadata.get("source_dataset") or input_path.name,
                source_url=default_source_url or metadata.get("source") or "",
                source_license=source_license_override or metadata.get("source_license") or "",
                source_crs=source_crs_override or metadata.get("source_crs") or "EPSG:4326",
                source_checksum=compute_file_sha256(input_path),
                imported_at=timezone.now(),
                imported_by=operator,
                validation_summary=validation_summary,
                feature_count=validation_summary["filtered_feature_count"],
                expected_feature_count=metadata.get("expected_ward_count") or validation_summary["backend_ward_count"],
                missing_source_wards=metadata.get("missing_source_wards", []),
                is_active=False,
                activated_at=None,
                notes=notes,
            )

            wards = list(Ward.objects.filter(county__iexact=county))
            ward_by_code = {
                ward.ward_code.strip(): ward
                for ward in wards
                if isinstance(ward.ward_code, str) and ward.ward_code.strip()
            }
            ward_by_name = {normalize_ward_name(ward.name): ward for ward in wards}

            feature_rows = []
            unmatched_labels = []
            for feature in prepared_payload.get("features", []):
                properties = feature.get("properties", {})
                ward_code = str(properties.get("ward_code", "")).strip()
                ward_name = str(properties.get("name", "")).strip()
                ward = ward_by_code.get(ward_code) if ward_code else None
                matching_source = "ward_code" if ward else None
                if ward is None and ward_name:
                    ward = ward_by_name.get(normalize_ward_name(ward_name))
                    if ward is not None:
                        matching_source = "name"
                if ward is None:
                    unmatched_labels.append(ward_name or ward_code or "Unnamed feature")
                    continue

                centroid = properties.get("centroid")
                centroid_point = None
                if isinstance(centroid, list) and len(centroid) >= 2:
                    centroid_point = Point(float(centroid[0]), float(centroid[1]), srid=4326)

                feature_rows.append(
                    WardGeometryFeature(
                        dataset_version=version,
                        ward=ward,
                        backend_public_id_snapshot=ward.public_id,
                        ward_code_snapshot=ward.ward_code,
                        display_name_snapshot=ward.name,
                        source_name=str(properties.get("source_name", "")).strip(),
                        source_ward_code=str(properties.get("source_ward_code", "")).strip(),
                        matching_source=matching_source or "",
                        geometry=GEOSGeometry(json.dumps(feature["geometry"]), srid=4326),
                        centroid=centroid_point,
                        properties=properties,
                    )
                )

            if unmatched_labels:
                raise CommandError(
                    "Managed geometry import found unmatched features after preparation: "
                    + ", ".join(unmatched_labels)
                )

            WardGeometryFeature.objects.bulk_create(feature_rows, batch_size=200)

        if activate:
            version, _sync_summary = activate_geometry_version(
                dataset_slug=dataset_slug,
                version_label=version_label,
                operator_username=operator_username,
                notes=notes,
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported managed ward geometry dataset='{dataset_slug}' version='{version_label}' "
                f"features={len(feature_rows)} active={'yes' if version.is_active else 'no'}"
            )
        )
