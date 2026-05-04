import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.spatial_relationships import (
    DEFAULT_GEOMETRY_DATASET_SLUG,
    DEFAULT_SPATIAL_COUNTY,
    build_spatial_source_quality_report,
)


class Command(BaseCommand):
    help = "Audit ward geometry, facility coordinate, CRS, and proximity-source readiness for spatial features."

    def add_arguments(self, parser):
        parser.add_argument("--dataset-slug", default=DEFAULT_GEOMETRY_DATASET_SLUG)
        parser.add_argument("--county", default=DEFAULT_SPATIAL_COUNTY)
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format for the audit report.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when the audit reports fail or warning status.",
        )

    def handle(self, *args, **options):
        report = build_spatial_source_quality_report(
            dataset_slug=options["dataset_slug"].strip(),
            county=options["county"].strip(),
        )

        if options["format"] == "json":
            self.stdout.write(json.dumps(report, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Spatial source audit: {report['overall_status']}")
            self.stdout.write(f"County: {report['county']}")
            self.stdout.write(f"Geometry dataset: {report['geometry_dataset']}")
            self.stdout.write(f"Source quality: {report['source_quality']}")
            for item in report["verification_questions"]:
                self.stdout.write(f"- {item['id']}: {item['status']} - {item['answer']}")
                for gap in item["gaps"]:
                    self.stdout.write(f"  gap: {gap}")
                for assumption in item["assumptions"]:
                    self.stdout.write(f"  assumption: {assumption}")

        if options["strict"] and report["overall_status"] in {"fail", "warning"}:
            raise CommandError(f"Spatial source audit finished with {report['overall_status']} status.")
