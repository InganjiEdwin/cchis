import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.preparedness_action_audit import build_preparedness_action_ledger_audit


class Command(BaseCommand):
    help = "Audit preparedness action ledger integrity, source linkage, evidence, and rollout readiness."

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
        audit = build_preparedness_action_ledger_audit()

        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Preparedness action ledger audit: {audit['overall_status']}")
            self.stdout.write(f"Records: {audit['record_totals']}")
            for item in audit["audit_checks"]:
                self.stdout.write(f"- {item['id']}: {item['status']}")
                self.stdout.write(f"  {item['answer']}")
                if item["gaps"]:
                    self.stdout.write(f"  gaps={item['gaps']}")

        if options["strict"] and audit["overall_status"] in {"fail", "warning"}:
            raise CommandError(f"Preparedness action ledger audit finished with {audit['overall_status']} status.")

