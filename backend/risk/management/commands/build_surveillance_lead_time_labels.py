from datetime import date

from django.core.management.base import BaseCommand, CommandError

from risk.surveillance_ingestion import parse_surveillance_source_timestamp
from risk.surveillance_labels import build_surveillance_lead_time_label_dataset


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CommandError(f"Invalid date '{value}'. Expected YYYY-MM-DD.") from error


class Command(BaseCommand):
    help = "Build Phase 3 surveillance labels for 7 to 14 day evaluation windows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prediction-date",
            action="append",
            default=[],
            help="Prediction date to evaluate from. May be supplied multiple times.",
        )
        parser.add_argument("--start-date", default="", help="First prediction date for a generated range.")
        parser.add_argument("--end-date", default="", help="Final prediction date for a generated range.")
        parser.add_argument("--step-days", type=int, default=1)
        parser.add_argument("--as-of", default="", help="ISO timestamp for the surveillance snapshot cutoff.")
        parser.add_argument("--lead-time-start-days", type=int, default=7)
        parser.add_argument("--lead-time-end-days", type=int, default=14)
        parser.add_argument(
            "--dataset-role",
            choices=["training", "evaluation"],
            default="evaluation",
            help="Logical dataset role stored in lineage metadata.",
        )
        parser.add_argument(
            "--include-seeded",
            action="store_true",
            help="Include seeded demo surveillance records. Off by default for evaluation.",
        )
        parser.add_argument(
            "--exclude-empty-windows",
            action="store_true",
            help="Do not create zero-count rows for ward-date pairs without source records.",
        )

    def handle(self, *args, **options):
        prediction_dates = [_parse_date(value) for value in options["prediction_date"]]
        start_date = _parse_date(options["start_date"]) if options["start_date"] else None
        end_date = _parse_date(options["end_date"]) if options["end_date"] else None
        as_of = parse_surveillance_source_timestamp(options["as_of"]) if options["as_of"] else None

        try:
            snapshot = build_surveillance_lead_time_label_dataset(
                prediction_dates=prediction_dates or None,
                start_date=start_date,
                end_date=end_date,
                step_days=options["step_days"],
                as_of=as_of,
                lead_time_start_days=options["lead_time_start_days"],
                lead_time_end_days=options["lead_time_end_days"],
                dataset_role=options["dataset_role"],
                include_seeded=options["include_seeded"],
                include_empty_windows=not options["exclude_empty_windows"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        dataset = snapshot.feature_dataset
        coverage = (dataset.lineage_metadata or {}).get("coverage", {})
        self.stdout.write(
            self.style.SUCCESS(
                f"Surveillance lead-time label dataset built. dataset_ref={dataset.dataset_ref} "
                f"rows={dataset.row_count} prediction_dates={coverage.get('prediction_date_count', 0)} "
                f"active={coverage.get('active_label_count', 0)} "
                f"confirmed_truth={coverage.get('confirmed_truth_label_count', 0)} "
                f"late_revisions={coverage.get('late_revision_state_counts', {})}"
            )
        )
