import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.ml.model_ops_audit import build_model_operations_audit
from risk.ml.registry import DEFAULT_MODEL_REVIEW_INTERVAL_DAYS


class Command(BaseCommand):
    help = "Audit post-promotion ward-risk model operations governance controls."

    def add_arguments(self, parser):
        parser.add_argument(
            "--stale-review-days",
            type=int,
            default=DEFAULT_MODEL_REVIEW_INTERVAL_DAYS,
            help="Maximum active-model age before review evidence is required.",
        )
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
        try:
            audit = build_model_operations_audit(
                stale_review_days=options["stale_review_days"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Model operations audit: {audit['overall_status']}")
            self.stdout.write(f"Review cadence: {audit['governance']['review_cadence_days']} days")
            self.stdout.write(f"Checks: {audit['summary']}")
            for check in audit["checks"]:
                self.stdout.write(f"- {check['id']}: {check['status']}")
                self.stdout.write(f"  {check['answer']}")
                if check["gaps"]:
                    self.stdout.write(f"  gaps={check['gaps']}")

        if options["strict"] and audit["overall_status"] == "fail":
            raise CommandError("Model operations audit finished with fail status.")
