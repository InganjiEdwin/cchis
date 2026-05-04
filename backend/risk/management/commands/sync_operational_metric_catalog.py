import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.operational_metrics import sync_operational_metric_catalog, validate_operational_metric_dictionary


class Command(BaseCommand):
    help = "Validate and sync the versioned operational KPI dictionary into the data mart definition tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format for the sync report.",
        )
        parser.add_argument(
            "--validate-only",
            action="store_true",
            help="Only validate the in-code KPI dictionary; do not write database rows.",
        )

    def handle(self, *args, **options):
        issues = validate_operational_metric_dictionary()
        if options["validate_only"]:
            payload = {
                "schema": "operational-kpi-dictionary-v1",
                "status": "pass" if not issues else "fail",
                "issues": issues,
            }
        elif issues:
            payload = {"schema": "operational-kpi-dictionary-v1", "status": "fail", "issues": issues}
        else:
            result = sync_operational_metric_catalog()
            payload = {"schema": "operational-kpi-dictionary-v1", "status": "synced", **result}

        if options["format"] == "json":
            self.stdout.write(json.dumps(payload, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Operational KPI dictionary: {payload['status']}")
            if "dimensions" in payload:
                self.stdout.write(f"Dimensions: {payload['dimensions']}")
            if "definitions" in payload:
                self.stdout.write(f"Definitions: {payload['definitions']}")
            if payload.get("issues"):
                for issue in payload["issues"]:
                    self.stdout.write(f"- {issue['metric_key']}: {issue['issue']}")

        if not options["validate_only"] and issues:
            raise CommandError("Operational KPI dictionary is invalid; no data mart definitions were synced.")
