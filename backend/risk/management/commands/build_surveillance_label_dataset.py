from django.core.management.base import BaseCommand, CommandError

from risk.surveillance_ingestion import parse_surveillance_date, parse_surveillance_source_timestamp
from risk.surveillance_labels import build_surveillance_label_dataset


class Command(BaseCommand):
    help = "Build a reproducible surveillance label FeatureDataset from canonical surveillance records."

    def add_arguments(self, parser):
        parser.add_argument("--start-date", default="", help="ISO date for the first label window start.")
        parser.add_argument("--end-date", default="", help="ISO date for the final label window end.")
        parser.add_argument("--as-of", default="", help="ISO timestamp for the snapshot cutoff. Defaults to now.")
        parser.add_argument("--window-days", type=int, default=7)
        parser.add_argument("--step-days", type=int, default=7)
        parser.add_argument("--month", type=int, default=None)
        parser.add_argument(
            "--dataset-role",
            choices=["training", "evaluation"],
            default="training",
            help="Logical dataset role stored in lineage metadata.",
        )
        parser.add_argument(
            "--exclude-seeded",
            action="store_true",
            help="Exclude seeded demo surveillance records from label windows.",
        )
        parser.add_argument(
            "--include-empty-windows",
            action="store_true",
            help="Create explicit zero-count windows for ward-periods with no source records.",
        )

    def handle(self, *args, **options):
        try:
            start_date = parse_surveillance_date(options["start_date"]) if options["start_date"] else None
            end_date = parse_surveillance_date(options["end_date"]) if options["end_date"] else None
            as_of = parse_surveillance_source_timestamp(options["as_of"]) if options["as_of"] else None
            snapshot = build_surveillance_label_dataset(
                start_date=start_date,
                end_date=end_date,
                as_of=as_of,
                window_days=options["window_days"],
                step_days=options["step_days"],
                month=options["month"],
                dataset_role=options["dataset_role"],
                include_seeded=not options["exclude_seeded"],
                include_empty_windows=options["include_empty_windows"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        dataset = snapshot.feature_dataset
        coverage = (dataset.lineage_metadata or {}).get("coverage", {})
        self.stdout.write(
            self.style.SUCCESS(
                f"Surveillance label dataset built. dataset_ref={dataset.dataset_ref} "
                f"rows={dataset.row_count} active={coverage.get('active_label_count', 0)} "
                f"watch={coverage.get('watch_label_count', 0)} none={coverage.get('none_label_count', 0)} "
                f"source_records={coverage.get('source_record_count', 0)}"
            )
        )
