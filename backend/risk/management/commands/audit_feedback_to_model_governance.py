import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.feedback_governance_audit import build_feedback_to_model_governance_audit


class Command(BaseCommand):
    help = "Audit governed feedback-to-model improvement controls."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="json",
            help="Output format for the audit report.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when the audit reports fail status.",
        )

    def handle(self, *args, **options):
        audit = build_feedback_to_model_governance_audit()

        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Feedback-to-model governance audit: {audit['overall_status']}")
            self.stdout.write(f"Checks: {audit['summary']}")
            for check in audit["checks"]:
                self.stdout.write(f"- {check['id']}: {check['status']}")
                self.stdout.write(f"  {check['answer']}")
                if check["gaps"]:
                    self.stdout.write(f"  gaps={check['gaps']}")

        if options["strict"] and audit["overall_status"] == "fail":
            raise CommandError("Feedback-to-model governance audit finished with fail status.")
