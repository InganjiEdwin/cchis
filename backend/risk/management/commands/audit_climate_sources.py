import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.climate_source_audit import build_climate_source_separation_audit


class Command(BaseCommand):
    help = "Audit climate source separation, forecast horizons, and fallback rainfall classification."

    def add_arguments(self, parser):
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
        audit = build_climate_source_separation_audit()
        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Climate source separation audit: {audit['overall_status']}")
            self.stdout.write(f"Records: {audit['record_totals']}")
            self.stdout.write(f"Inventory: {audit['source_inventory']}")
            for item in audit["verification_questions"]:
                self.stdout.write(f"- {item['id']}: {item['status']} - {item['answer']}")
                for gap in item["gaps"]:
                    self.stdout.write(f"  gap: {gap}")

        if options["strict"] and audit["overall_status"] in {"fail", "warning"}:
            raise CommandError(f"Climate source separation audit finished with {audit['overall_status']} status.")
