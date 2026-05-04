import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.spatial_relationships import (
    DEFAULT_GEOMETRY_DATASET_SLUG,
    DEFAULT_SPATIAL_COUNTY,
    rebuild_facility_catchment_approximations,
)


class Command(BaseCommand):
    help = "Build approximate facility catchments from source catchment records, ward adjacency, or distance thresholds."

    def add_arguments(self, parser):
        parser.add_argument("--dataset-slug", default=DEFAULT_GEOMETRY_DATASET_SLUG)
        parser.add_argument("--county", default=DEFAULT_SPATIAL_COUNTY)
        parser.add_argument(
            "--distance-threshold",
            type=float,
            default=None,
            help="Optional source-CRS degree threshold from facility point to ward geometry.",
        )
        parser.add_argument(
            "--skip-adjacent-wards",
            action="store_true",
            help="Do not expand primary ward catchments through phase 1 adjacent-ward edges.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute catchment output without writing rows.",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format for the catchment build summary.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when any active facility cannot receive a catchment.",
        )

    def handle(self, *args, **options):
        try:
            summary = rebuild_facility_catchment_approximations(
                dataset_slug=options["dataset_slug"].strip(),
                county=options["county"].strip(),
                include_adjacent_wards=not options["skip_adjacent_wards"],
                distance_threshold=options["distance_threshold"],
                dry_run=options["dry_run"],
            )
        except Exception as error:
            raise CommandError(str(error)) from error

        if options["format"] == "json":
            self.stdout.write(json.dumps(summary, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Facility catchments built: "
                    f"created={summary['created_catchment_count']}, "
                    f"active_facilities={summary['active_facility_count']}, "
                    f"same_facility_edges={summary['created_same_facility_relationship_count']}, "
                    f"skipped={summary['skipped_facility_count']}, "
                    f"dry_run={'yes' if summary['dry_run'] else 'no'}"
                )
            )
            for catchment in summary["catchments"]:
                approximate = "approximate" if catchment["is_approximate"] else "verified"
                self.stdout.write(
                    "- "
                    f"{catchment['facility_name']}: {catchment['catchment_method']} "
                    f"wards={catchment['covered_ward_names']} "
                    f"population={catchment['population_estimate']} "
                    f"confidence={catchment['confidence']} "
                    f"label={approximate}"
                )

        if options["strict"] and summary["skipped_facility_count"]:
            raise CommandError("Facility catchment build failed strict checks.")
