import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.spatial_relationships import (
    DEFAULT_GEOMETRY_DATASET_SLUG,
    DEFAULT_SPATIAL_COUNTY,
    rebuild_ward_spatial_relationship_graph,
)


class Command(BaseCommand):
    help = "Rebuild derived ward spatial relationship edges from the active managed geometry dataset."

    def add_arguments(self, parser):
        parser.add_argument("--dataset-slug", default=DEFAULT_GEOMETRY_DATASET_SLUG)
        parser.add_argument("--county", default=DEFAULT_SPATIAL_COUNTY)
        parser.add_argument(
            "--min-shared-boundary-length",
            type=float,
            default=0.0,
            help="Minimum GEOS boundary-intersection length required for an adjacent edge.",
        )
        parser.add_argument(
            "--nearby-centroid-threshold",
            type=float,
            default=None,
            help="Optional centroid-distance threshold, in source CRS degrees, for nearby non-adjacent edges.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute the rebuild summary without writing relationship rows.",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format for the rebuild summary.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when no adjacent edges are created or geometry pair checks are skipped.",
        )

    def handle(self, *args, **options):
        try:
            summary = rebuild_ward_spatial_relationship_graph(
                dataset_slug=options["dataset_slug"].strip(),
                county=options["county"].strip(),
                min_shared_boundary_length=options["min_shared_boundary_length"],
                nearby_centroid_threshold=options["nearby_centroid_threshold"],
                dry_run=options["dry_run"],
            )
        except Exception as error:
            raise CommandError(str(error)) from error

        if options["format"] == "json":
            self.stdout.write(json.dumps(summary, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Ward spatial relationships rebuilt: "
                    f"created={summary['created_derived_edge_count']}, "
                    f"adjacent_pairs={summary['undirected_adjacent_pair_count']}, "
                    f"nearby_pairs={summary['undirected_nearby_pair_count']}, "
                    f"deleted={summary['deleted_derived_edge_count']}, "
                    f"manual_preserved={summary['manual_edge_count_preserved']}, "
                    f"dry_run={'yes' if summary['dry_run'] else 'no'}"
                )
            )
            if summary["skipped_pair_count"]:
                self.stdout.write(self.style.WARNING(f"Skipped pair checks: {summary['skipped_pair_count']}"))

        if options["strict"] and (
            summary["undirected_adjacent_pair_count"] == 0 or summary["skipped_pair_count"] > 0
        ):
            raise CommandError("Ward spatial relationship rebuild failed strict checks.")
