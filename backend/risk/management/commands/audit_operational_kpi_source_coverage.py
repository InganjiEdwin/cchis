import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.operational_metric_builders import build_operational_kpi_source_coverage_audit, parse_snapshot_date


class Command(BaseCommand):
    help = "Audit operational KPI snapshot source coverage and stale windows."

    def add_arguments(self, parser):
        parser.add_argument("--as-of-date", default="", help="Audit date in YYYY-MM-DD format. Defaults to today.")
        parser.add_argument(
            "--stale-after-days",
            type=int,
            default=1,
            help="Treat latest snapshots older than this many days as stale.",
        )
        parser.add_argument("--ward-id", default="", help="Optional ward id filter.")
        parser.add_argument("--sub-county", default="", help="Optional sub-county filter.")
        parser.add_argument("--source-channel", default="", help="Optional source channel filter.")
        parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when the audit reports warning or fail status.",
        )

    def handle(self, *args, **options):
        try:
            audit = build_operational_kpi_source_coverage_audit(
                as_of_date=parse_snapshot_date(options["as_of_date"] or None),
                stale_after_days=options["stale_after_days"],
                filters={
                    "ward_id": options["ward_id"] or None,
                    "sub_county": options["sub_county"],
                    "source_channel": options["source_channel"],
                },
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Operational KPI source coverage audit: {audit['overall_status']}")
            self.stdout.write(f"Records: {audit['record_totals']}")
            for warning in audit["warnings"]:
                detail = f"- {warning['metric_key']}: {warning['warning']}"
                if warning.get("latest_date"):
                    detail += f" latest_date={warning['latest_date']}"
                self.stdout.write(detail)

        if options["strict"] and audit["overall_status"] in {"fail", "warning"}:
            raise CommandError(f"Operational KPI source coverage audit finished with {audit['overall_status']} status.")
