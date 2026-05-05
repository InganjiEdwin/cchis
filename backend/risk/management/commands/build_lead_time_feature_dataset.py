from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError

from risk.lead_time_features import build_lead_time_feature_dataset


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CommandError(f"Invalid date '{value}'. Expected YYYY-MM-DD.") from error


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CommandError(f"Invalid datetime '{value}'. Expected ISO-8601 timestamp.") from error


class Command(BaseCommand):
    help = "Build Phase 2 ward-time lead-time feature windows with source cutoff and leakage proof."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prediction-date",
            action="append",
            default=[],
            help="Prediction date to generate. May be supplied multiple times.",
        )
        parser.add_argument("--start-date", default="", help="First prediction date for a generated date range.")
        parser.add_argument("--end-date", default="", help="Final prediction date for a generated date range.")
        parser.add_argument("--step-days", type=int, default=1)
        parser.add_argument(
            "--source-cutoff-as-of",
            default="",
            help="Maximum source cutoff timestamp to apply in addition to each prediction date cutoff.",
        )
        parser.add_argument(
            "--include-seeded-surveillance",
            action="store_true",
            help="Include seeded demo surveillance records in trend features. Off by default.",
        )
        parser.add_argument("--heavy-rain-threshold-mm", type=float, default=50.0)
        parser.add_argument(
            "--claimed-forecast-horizon-days",
            type=int,
            default=14,
            help="Forecast lead-day coverage claim to verify on every feature row. Must be between 1 and 14.",
        )

    def handle(self, *args, **options):
        prediction_dates = [_parse_date(value) for value in options["prediction_date"]]
        start_date = _parse_date(options["start_date"]) if options["start_date"] else None
        end_date = _parse_date(options["end_date"]) if options["end_date"] else None
        source_cutoff_as_of = _parse_datetime(options["source_cutoff_as_of"]) if options["source_cutoff_as_of"] else None

        try:
            snapshot = build_lead_time_feature_dataset(
                prediction_dates=prediction_dates or None,
                start_date=start_date,
                end_date=end_date,
                step_days=options["step_days"],
                source_cutoff_as_of=source_cutoff_as_of,
                include_seeded_surveillance=options["include_seeded_surveillance"],
                heavy_rain_threshold_mm=options["heavy_rain_threshold_mm"],
                claimed_forecast_horizon_days=options["claimed_forecast_horizon_days"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        dataset = snapshot.feature_dataset
        coverage = (dataset.lineage_metadata or {}).get("coverage", {})
        self.stdout.write(
            self.style.SUCCESS(
                f"Lead-time feature dataset built. dataset_ref={dataset.dataset_ref} "
                f"rows={dataset.row_count} prediction_dates={coverage.get('prediction_date_count', 0)} "
                f"rainfall_rows={coverage.get('rows_with_rainfall_source_records', 0)} "
                f"forecast_rows={coverage.get('rows_with_forecast_rainfall_records', 0)} "
                f"climate_coverage_ok={coverage.get('rows_with_sufficient_claimed_climate_coverage', 0)} "
                f"surveillance_rows={coverage.get('rows_with_surveillance_records', 0)} "
                f"leakage_checked={coverage.get('rows_passing_leakage_check', 0)}"
            )
        )
