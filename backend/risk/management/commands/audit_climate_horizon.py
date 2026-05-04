import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.climate_horizon_audit import build_climate_horizon_monitoring_audit


class Command(BaseCommand):
    help = "Run Phase 5 climate forecast horizon, source-separation, and monitoring audit checks."

    def add_arguments(self, parser):
        parser.add_argument("--feature-dataset-ref", default="", help="Optional lead-time feature dataset ref.")
        parser.add_argument("--model-run-id", type=int, default=None, help="Optional model run id.")
        parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
        parser.add_argument("--strict", action="store_true", help="Exit non-zero when the audit does not pass.")

    def handle(self, *args, **options):
        audit = build_climate_horizon_monitoring_audit(
            feature_dataset_ref=options["feature_dataset_ref"] or None,
            model_run_id=options["model_run_id"],
        )

        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Climate horizon audit: {audit['overall_status']}")
            self.stdout.write(f"Records: {audit['record_totals']}")
            for check in audit["checks"]:
                self.stdout.write(
                    f"- {check['id']}: {check['status']} "
                    f"({check['fail_count']} fail, {check['warning_count']} warning)"
                )
                for issue in check["issues"]:
                    self.stdout.write(
                        f"  {issue['severity']} {issue['record_type']}:{issue['record_id']} "
                        f"{issue['message']}"
                    )

        if options["strict"] and audit["overall_status"] != "pass":
            raise CommandError(f"Climate horizon audit finished with {audit['overall_status']} status.")
