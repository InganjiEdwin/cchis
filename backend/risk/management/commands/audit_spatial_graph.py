import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.spatial_relationships import (
    DEFAULT_GEOMETRY_DATASET_SLUG,
    DEFAULT_SPATIAL_COUNTY,
    build_spatial_graph_monitoring_audit,
)


class Command(BaseCommand):
    help = "Run Phase 5 spatial relationship, catchment, lead-time leakage, and approximation-label audit checks."

    def add_arguments(self, parser):
        parser.add_argument("--dataset-slug", default=DEFAULT_GEOMETRY_DATASET_SLUG)
        parser.add_argument("--county", default=DEFAULT_SPATIAL_COUNTY)
        parser.add_argument(
            "--feature-dataset-ref",
            default="",
            help="Optional lead-time feature dataset_ref to audit. Defaults to all lead-time feature datasets.",
        )
        parser.add_argument(
            "--row-limit",
            type=int,
            default=None,
            help="Optional maximum number of feature rows to scan.",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format for the audit report.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when the audit does not pass.",
        )

    def handle(self, *args, **options):
        row_limit = options["row_limit"]
        if row_limit is not None and row_limit <= 0:
            raise CommandError("--row-limit must be a positive integer.")

        audit = build_spatial_graph_monitoring_audit(
            dataset_slug=options["dataset_slug"].strip(),
            county=options["county"].strip(),
            feature_dataset_ref=options["feature_dataset_ref"].strip() or None,
            row_limit=row_limit,
        )

        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Spatial graph audit: {audit['overall_status']}")
            self.stdout.write(f"County: {audit['county']}")
            self.stdout.write(f"Records: {audit['record_totals']}")
            for check in audit["checks"]:
                self.stdout.write(
                    f"- {check['id']}: {check['status']} "
                    f"({check['issue_count']} issues, scanned={check['scanned_count']})"
                )
                for issue in check["issues"][:5]:
                    self.stdout.write(f"  {issue['severity']}: {issue['message']}")

        if options["strict"] and audit["overall_status"] != "pass":
            raise CommandError(f"Spatial graph audit finished with {audit['overall_status']} status.")
