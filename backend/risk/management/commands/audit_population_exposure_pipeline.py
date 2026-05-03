import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.population_exposure_audit import build_population_exposure_pipeline_audit


class Command(BaseCommand):
    help = "Audit population/exposure ETL readiness, lineage, replay, and downstream honesty contracts."

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
        audit = build_population_exposure_pipeline_audit()

        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Population/exposure pipeline audit: {audit['overall_status']}")
            self.stdout.write(f"Records: {audit['record_totals']}")
            self.stdout.write(f"Sources: {audit['source_totals']}")
            for item in audit["verification_questions"]:
                self.stdout.write(f"- {item['id']}: {item['status']}")
                self.stdout.write(f"  {item['answer']}")
                if item["gaps"]:
                    self.stdout.write(f"  gaps={item['gaps']}")

        if options["strict"] and audit["overall_status"] in {"fail", "warning"}:
            raise CommandError(f"Population/exposure audit finished with {audit['overall_status']} status.")
