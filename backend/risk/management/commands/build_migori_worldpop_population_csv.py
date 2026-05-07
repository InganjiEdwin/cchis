from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from risk.map_data import MIGORI_WARD_GEOMETRY_PATH
from risk.migori_worldpop_population_csv import (
    DEFAULT_OUTPUT_CSV_PATH,
    DEFAULT_PHASE0_INVENTORY_PATH,
    DEFAULT_SUMMARY_PATH,
    build_migori_worldpop_population_csv,
)


class Command(BaseCommand):
    help = "Build a canonical Migori ward population CSV from the WorldPop 2026 raster."

    def add_arguments(self, parser):
        parser.add_argument("--inventory", default=str(DEFAULT_PHASE0_INVENTORY_PATH))
        parser.add_argument("--geojson", default=str(MIGORI_WARD_GEOMETRY_PATH))
        parser.add_argument("--raster-path", default="")
        parser.add_argument("--output", default=str(DEFAULT_OUTPUT_CSV_PATH))
        parser.add_argument("--summary-output", default=str(DEFAULT_SUMMARY_PATH))
        parser.add_argument(
            "--no-download",
            action="store_true",
            help="Require --raster-path or the default cache file to already exist.",
        )
        parser.add_argument("--strict", action="store_true", help="Fail if any Phase 1 gate is false.")

    def handle(self, *args, **options):
        try:
            summary = build_migori_worldpop_population_csv(
                inventory_path=Path(options["inventory"]).expanduser().resolve(),
                geojson_path=Path(options["geojson"]).expanduser().resolve(),
                raster_path=Path(options["raster_path"]).expanduser().resolve()
                if options["raster_path"]
                else None,
                output_csv_path=Path(options["output"]).expanduser().resolve(),
                summary_path=Path(options["summary_output"]).expanduser().resolve(),
                download_raster=not options["no_download"],
            )
        except Exception as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Migori WorldPop population CSV built. "
                f"rows={summary['row_count']} "
                f"population_total={summary['population_total_rounded']} "
                f"output={summary['output_csv_path']}"
            )
        )
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))

        if options["strict"] and not summary["passed"]:
            failed_gates = [name for name, passed in summary["phase1_gates"].items() if not passed]
            raise CommandError(f"Phase 1 CSV build failed strict gates: {', '.join(failed_gates)}")
