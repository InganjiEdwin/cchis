import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.chirps_audit import build_chirps_ingestion_audit


class Command(BaseCommand):
    help = "Run strict CHIRPS v3 historical source, spatial, provenance, and idempotency audits."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["text", "json"], default="text")
        parser.add_argument("--strict", action="store_true", help="Exit non-zero unless every audit check passes.")

    def handle(self, *args, **options):
        audit = build_chirps_ingestion_audit()
        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"CHIRPS ingestion audit: {audit['overall_status']}")
            self.stdout.write(
                f"Records scanned: {audit['records_scanned']} runs scanned: {audit['runs_scanned']}"
            )
            for check in audit["checks"]:
                self.stdout.write(
                    f"- {check['id']}: {check['status']} "
                    f"({check['fail_count']} fail, {check['warning_count']} warning)"
                )
                for issue in check["issues"]:
                    self.stdout.write(f"  {issue['severity']}: {issue['message']}")

        if options["strict"] and audit["overall_status"] != "pass":
            raise CommandError("CHIRPS ingestion audit did not pass.")
