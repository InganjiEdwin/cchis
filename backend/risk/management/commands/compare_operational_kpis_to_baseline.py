import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.operational_metric_builders import compare_operational_kpis_to_baseline, parse_snapshot_date


class Command(BaseCommand):
    help = "Compare latest operational KPI snapshots to active baseline periods."

    def add_arguments(self, parser):
        parser.add_argument("--as-of-date", default="", help="Comparison date in YYYY-MM-DD format. Defaults to today.")
        parser.add_argument(
            "--metric-key",
            action="append",
            dest="metric_keys",
            default=None,
            help="Limit the comparison to a metric key. May be supplied multiple times.",
        )
        parser.add_argument("--ward-id", default="", help="Optional ward id filter.")
        parser.add_argument("--sub-county", default="", help="Optional sub-county filter.")
        parser.add_argument("--source-channel", default="", help="Optional source channel filter.")
        parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when current snapshots or baselines are missing.",
        )

    def handle(self, *args, **options):
        try:
            comparison = compare_operational_kpis_to_baseline(
                as_of_date=parse_snapshot_date(options["as_of_date"] or None),
                metric_keys=options["metric_keys"],
                filters={
                    "ward_id": options["ward_id"] or None,
                    "sub_county": options["sub_county"],
                    "source_channel": options["source_channel"],
                },
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        if options["format"] == "json":
            self.stdout.write(json.dumps(comparison, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Operational KPI baseline comparison: {comparison['overall_status']}")
            for item in comparison["comparisons"]:
                if item["status"] == "compared":
                    self.stdout.write(
                        f"- {item['metric_key']}: current={item['current_value']} "
                        f"baseline={item['baseline_value']} delta={item['delta']}"
                    )
                else:
                    self.stdout.write(f"- {item['metric_key']}: {item['status']}")

        if options["strict"] and comparison["overall_status"] in {"fail", "warning"}:
            raise CommandError(f"Operational KPI baseline comparison finished with {comparison['overall_status']} status.")
