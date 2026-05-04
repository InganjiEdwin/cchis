from django.core.management.base import BaseCommand

from risk.operational_metric_builders import parse_snapshot_date
from risk.operational_metric_thresholds import evaluate_operational_kpi_thresholds


class Command(BaseCommand):
    help = "Evaluate operational KPI threshold warnings and breaches."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="snapshot_date", help="Evaluate thresholds as of YYYY-MM-DD. Defaults to today.")
        parser.add_argument("--stale-after-days", type=int, default=1, help="Maximum allowed KPI snapshot age in days.")
        parser.add_argument("--ward-id", type=int, default=None, help="Limit evaluation to snapshots for a ward.")
        parser.add_argument("--sub-county", default="", help="Limit evaluation to snapshots for a sub-county.")
        parser.add_argument("--source-channel", default="", help="Limit evaluation to snapshots for a source channel.")
        parser.add_argument("--persist", action="store_true", help="Persist active breaches and resolve stale ones.")
        parser.add_argument("--notify", action="store_true", help="Create or resolve dashboard notifications for persisted breaches.")

    def handle(self, *args, **options):
        filters = {
            "ward_id": options["ward_id"],
            "sub_county": options["sub_county"].strip(),
            "source_channel": options["source_channel"].strip().upper(),
        }
        filters = {key: value for key, value in filters.items() if value}
        result = evaluate_operational_kpi_thresholds(
            as_of_date=parse_snapshot_date(options["snapshot_date"]),
            filters=filters,
            stale_after_days=options["stale_after_days"],
            persist=options["persist"],
            notify=options["notify"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Operational KPI threshold evaluation complete. "
                f"active={result['active_count']} critical={result['critical_count']} "
                f"warning={result['warning_count']} created={result['created']} "
                f"updated={result['updated']} resolved={result['resolved']}"
            )
        )
        for breach in result["breaches"]:
            self.stdout.write(f"- {breach['severity']} {breach['metric_key']}: {breach['title']}")
