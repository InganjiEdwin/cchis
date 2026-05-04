import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.operational_metric_audit import build_operational_kpi_integrity_audit


class Command(BaseCommand):
    help = "Run strict operational KPI integrity checks for M&E reporting."

    def add_arguments(self, parser):
        parser.add_argument("--date-from", default="", help="Start date in YYYY-MM-DD format.")
        parser.add_argument("--date-to", default="", help="End date in YYYY-MM-DD format.")
        parser.add_argument("--ward-id", default="", help="Optional ward id filter.")
        parser.add_argument("--sub-county", default="", help="Optional sub-county filter.")
        parser.add_argument("--source-channel", default="", help="Optional source channel filter.")
        parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
        parser.add_argument("--strict", action="store_true", help="Exit non-zero when the audit does not pass.")

    def handle(self, *args, **options):
        try:
            audit = build_operational_kpi_integrity_audit(
                date_from=options["date_from"] or None,
                date_to=options["date_to"] or None,
                ward_id=options["ward_id"] or None,
                sub_county=options["sub_county"],
                source_channel=options["source_channel"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Operational KPI integrity audit: {audit['overall_status']}")
            self.stdout.write(f"Records: {audit['record_totals']}")
            for issue in audit["issues"]:
                self.stdout.write(
                    f"- {issue['severity']} {issue['check_id']} "
                    f"{issue['record_type']}:{issue['record_id']} {issue['message']}"
                )

        if options["strict"] and audit["overall_status"] != "pass":
            raise CommandError(f"Operational KPI integrity audit finished with {audit['overall_status']} status.")
