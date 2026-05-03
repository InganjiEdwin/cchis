from django.core.management.base import BaseCommand, CommandError

from risk.population_exposure_features import build_population_exposure_feature_dataset
from risk.population_exposure_ingestion import parse_source_timestamp


class Command(BaseCommand):
    help = "Build a reproducible population/exposure FeatureDataset snapshot from canonical records."

    def add_arguments(self, parser):
        parser.add_argument("--as-of", default="", help="ISO timestamp for the snapshot cutoff. Defaults to now.")
        parser.add_argument("--release-version", default="", help="Optional release version filter.")
        parser.add_argument("--month", type=int, default=None)

    def handle(self, *args, **options):
        try:
            as_of = parse_source_timestamp(options["as_of"]) if options["as_of"] else None
        except ValueError as error:
            raise CommandError(f"Invalid --as-of: {error}") from error

        snapshot = build_population_exposure_feature_dataset(
            as_of=as_of,
            release_version=options["release_version"] or None,
            month=options["month"],
        )
        dataset = snapshot.feature_dataset
        coverage = (dataset.lineage_metadata or {}).get("coverage", {})
        self.stdout.write(
            self.style.SUCCESS(
                f"Population/exposure dataset built. dataset_ref={dataset.dataset_ref} "
                f"rows={dataset.row_count} wards_with_population={coverage.get('wards_with_population_baseline', 0)} "
                f"wards_with_exposure={coverage.get('wards_with_any_exposure', 0)} "
                f"wards_with_catchment={coverage.get('wards_with_catchment_population', 0)}"
            )
        )
