import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.operational_metric_builders import backfill_daily_operational_kpi_snapshots, parse_snapshot_date


class Command(BaseCommand):
    help = "Backfill idempotent daily operational KPI snapshots over a date range."

    def add_arguments(self, parser):
        parser.add_argument("--start-date", required=True, help="First snapshot date in YYYY-MM-DD format.")
        parser.add_argument("--end-date", required=True, help="Final snapshot date in YYYY-MM-DD format.")
        parser.add_argument(
            "--metric-key",
            action="append",
            dest="metric_keys",
            default=None,
            help="Limit the backfill to a metric key. May be supplied multiple times.",
        )
        parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when source coverage warnings are emitted.",
        )

    def handle(self, *args, **options):
        try:
            result = backfill_daily_operational_kpi_snapshots(
                start_date=parse_snapshot_date(options["start_date"]),
                end_date=parse_snapshot_date(options["end_date"]),
                metric_keys=options["metric_keys"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        if options["format"] == "json":
            self.stdout.write(json.dumps(result, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Operational KPI snapshot backfill complete. "
                    f"start={result['start_date']} end={result['end_date']} days={result['days']} "
                    f"created={result['created']} updated={result['updated']} warnings={len(result['warnings'])}"
                )
            )
            for warning in result["warnings"]:
                self.stdout.write(f"- {warning['metric_key']}: {warning['warning']}")

        if options["strict"] and result["warnings"]:
            raise CommandError("Operational KPI backfill emitted source coverage warnings.")
