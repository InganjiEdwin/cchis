import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from risk.map_data import MIGORI_WARD_GEOMETRY_PATH
from risk.ward_geometry_pipeline import build_geometry_validation_summary, feature_matches_county, load_geojson_payload


class Command(BaseCommand):
    help = (
        "Validate a GeoJSON ward boundary source, compare it against backend Ward rows, "
        "and optionally write a county-filtered output artifact."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            dest="input_path",
            default=str(MIGORI_WARD_GEOMETRY_PATH),
            help="Path to the source GeoJSON file to validate.",
        )
        parser.add_argument(
            "--county",
            default="Migori",
            help="County name to validate and optionally extract.",
        )
        parser.add_argument(
            "--write-output",
            dest="output_path",
            help="Optional path for writing a county-filtered FeatureCollection.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail when missing wards, duplicates, or placeholder geometry are detected.",
        )

    def handle(self, *args, **options):
        input_path = Path(options["input_path"]).expanduser().resolve()
        county = options["county"].strip()
        output_path = options.get("output_path")
        strict = options["strict"]

        if not input_path.exists():
            raise CommandError(f"Input GeoJSON not found: {input_path}")

        try:
            payload = load_geojson_payload(input_path)
        except json.JSONDecodeError as error:
            raise CommandError(f"Invalid JSON in {input_path}: {error}") from error

        if payload.get("type") != "FeatureCollection":
            raise CommandError("GeoJSON must be a FeatureCollection.")

        features = payload.get("features", [])
        county_features = [feature for feature in features if feature_matches_county(feature, county)]
        if not county_features:
            raise CommandError(f"No features found for county '{county}' in {input_path}.")

        extracted_payload = {
            "type": "FeatureCollection",
            "metadata": payload.get("metadata", {}),
            "features": county_features,
        }
        summary = build_geometry_validation_summary(payload, county)

        self.stdout.write(self.style.MIGRATE_HEADING("Ward geometry validation summary"))
        self.stdout.write(f"Input file: {input_path}")
        self.stdout.write(f"County filter: {county}")
        self.stdout.write(f"Source feature count: {len(features)}")
        self.stdout.write(f"Filtered county feature count: {len(county_features)}")
        self.stdout.write(f"Backend ward count for county: {summary['backend_ward_count']}")
        self.stdout.write(f"Runtime CRS: {summary['runtime_crs']}")
        self.stdout.write(f"Geometry types: {summary['geometry_type_counts']}")
        self.stdout.write(
            "Placeholder rectangle geometry detected: "
            + ("yes" if summary["placeholder_geometry_detected"] else "no")
        )
        self.stdout.write(
            "Backend ward matching: "
            + f"code={summary['backend_ward_code_match_count']}, "
            + f"name_fallback={summary['backend_ward_name_fallback_match_count']}, "
            + f"unmatched={summary['backend_ward_unmatched_feature_count']}"
        )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Ward comparison"))
        self.stdout.write(
            "Missing backend wards by normalized name: "
            + self._format_list(summary["missing_backend_ward_names"])
        )
        self.stdout.write(
            f"Missing backend ward codes: {self._format_list(summary['missing_backend_ward_codes'])}"
        )
        self.stdout.write(
            "Extra source wards not found in backend by name: "
            + self._format_list(summary["extra_source_names"])
        )
        self.stdout.write(f"Duplicate source names: {self._format_list(summary['duplicate_source_names'])}")
        self.stdout.write(f"Duplicate source codes: {self._format_list(summary['duplicate_source_codes'])}")

        if summary["invalid_geometry_features"]:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Invalid geometry types detected:"))
            for label in summary["invalid_geometry_features"]:
                self.stdout.write(f"- {label}")

        if output_path:
            output_file = Path(output_path).expanduser().resolve()
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(json.dumps(extracted_payload, indent=2))
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"Wrote filtered GeoJSON to {output_file}"))

        should_fail = any(
            [
                summary["invalid_geometry_features"],
                summary["placeholder_geometry_detected"],
                summary["duplicate_source_names"],
                summary["duplicate_source_codes"],
                summary["missing_backend_ward_names"],
                summary["backend_ward_unmatched_feature_count"],
            ]
        )
        if strict and should_fail:
            raise CommandError(
                "Ward geometry validation failed strict mode. Review missing wards, duplicates, "
                "invalid geometry types, or placeholder geometry."
            )

    def _format_list(self, values: list[str]) -> str:
        if not values:
            return "none"
        return ", ".join(values)
