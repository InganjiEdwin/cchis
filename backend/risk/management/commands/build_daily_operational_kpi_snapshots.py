import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.operational_metric_builders import build_daily_operational_kpi_snapshots, parse_snapshot_date


class Command(BaseCommand):
    help = "Build idempotent daily operational KPI snapshots."

    def add_arguments(self, parser):
        parser.add_argument("--date", default="", help="Snapshot date in YYYY-MM-DD format. Defaults to today.")
        parser.add_argument(
            "--metric-key",
            action="append",
            dest="metric_keys",
            default=None,
            help="Limit the build to a metric key. May be supplied multiple times.",
        )
        parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when source coverage warnings are emitted.",
        )

    def handle(self, *args, **options):
        try:
            snapshot_date = parse_snapshot_date(options["date"] or None)
            result = build_daily_operational_kpi_snapshots(
                snapshot_date=snapshot_date,
                metric_keys=options["metric_keys"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        if options["format"] == "json":
            self.stdout.write(json.dumps(result, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Operational KPI snapshots built. "
                    f"date={result['date']} created={result['created']} updated={result['updated']} "
                    f"snapshots={result['snapshot_count']} warnings={len(result['warnings'])}"
                )
            )
            for warning in result["warnings"]:
                self.stdout.write(f"- {warning['metric_key']}: {warning['warning']}")

        if options["strict"] and result["warnings"]:
            raise CommandError("Operational KPI snapshot build emitted source coverage warnings.")
