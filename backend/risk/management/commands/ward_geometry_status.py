import json

from django.core.management.base import BaseCommand, CommandError

from risk.ward_geometry_ops import summarize_dataset_versions


class Command(BaseCommand):
    help = "Inspect managed ward geometry dataset versions and current activation state."

    def add_arguments(self, parser):
        parser.add_argument("--dataset-slug", default="migori-ward-boundaries", help="Dataset slug to inspect.")

    def handle(self, *args, **options):
        dataset_slug = options["dataset_slug"].strip()
        if not dataset_slug:
            raise CommandError("dataset-slug is required.")

        versions = summarize_dataset_versions(dataset_slug=dataset_slug)
        if not versions:
            raise CommandError(f"No managed ward geometry dataset versions found for '{dataset_slug}'.")

        self.stdout.write(json.dumps({"dataset_slug": dataset_slug, "versions": versions}, indent=2))
