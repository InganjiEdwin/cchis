from django.core.management.base import BaseCommand, CommandError
from risk.ward_geometry_ops import sync_canonical_ward_geometry_fields


class Command(BaseCommand):
    help = (
        "Sync canonical Ward.boundary and Ward.centroid fields from the active managed ward geometry version."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dataset-slug", default="migori-ward-boundaries", help="Dataset slug to sync from.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Inspect the sync result without updating Ward rows.",
        )

    def handle(self, *args, **options):
        dataset_slug = options["dataset_slug"].strip()
        dry_run = options["dry_run"]

        if not dataset_slug:
            raise CommandError("dataset-slug is required.")

        try:
            summary = sync_canonical_ward_geometry_fields(dataset_slug=dataset_slug, dry_run=dry_run)
        except Exception as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                f"Synced ward geometry fields from dataset='{dataset_slug}' version='{summary['version_label']}': "
                f"updated={summary['updated']}, unchanged={summary['unchanged']}, "
                f"missing_centroids={summary['missing_centroids']}, dry_run={'yes' if summary['dry_run'] else 'no'}"
            )
        )
