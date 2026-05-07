from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from risk.map_data import MIGORI_WARD_GEOMETRY_PATH
from risk.migori_population_source_inventory import (
    DEFAULT_COUNTY,
    DEFAULT_EXPECTED_WARD_COUNT,
    DEFAULT_WORLDPOP_DATASET_KEY,
    DEFAULT_WORLDPOP_ISO3,
    DEFAULT_WORLDPOP_YEAR,
    build_migori_population_phase0_inventory,
    fetch_worldpop_population_record,
    inventory_to_json,
    select_worldpop_population_record,
)


class Command(BaseCommand):
    help = "Build the Phase 0 Migori KNBS/WorldPop source inventory."

    def add_arguments(self, parser):
        parser.add_argument("--county", default=DEFAULT_COUNTY)
        parser.add_argument("--expected-ward-count", type=int, default=DEFAULT_EXPECTED_WARD_COUNT)
        parser.add_argument("--geojson", default=str(MIGORI_WARD_GEOMETRY_PATH))
        parser.add_argument("--output", help="Optional JSON artifact path to write.")
        parser.add_argument("--worldpop-dataset-key", default=DEFAULT_WORLDPOP_DATASET_KEY)
        parser.add_argument("--worldpop-iso3", default=DEFAULT_WORLDPOP_ISO3)
        parser.add_argument("--worldpop-year", default=DEFAULT_WORLDPOP_YEAR)
        parser.add_argument(
            "--worldpop-metadata-file",
            help="Optional cached WorldPop metadata JSON payload. Useful for offline/reproducible runs.",
        )
        parser.add_argument(
            "--skip-worldpop-fetch",
            action="store_true",
            help="Do not call the WorldPop metadata API. The inventory records WorldPop as unavailable unless a metadata file is supplied.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail if any Phase 0 gate is false.",
        )

    def handle(self, *args, **options):
        geojson_path = Path(options["geojson"]).expanduser().resolve()
        if not geojson_path.exists():
            raise CommandError(f"GeoJSON file not found: {geojson_path}")

        worldpop_record = None
        worldpop_error = ""
        try:
            if options["worldpop_metadata_file"]:
                metadata_path = Path(options["worldpop_metadata_file"]).expanduser().resolve()
                if not metadata_path.exists():
                    raise CommandError(f"WorldPop metadata file not found: {metadata_path}")
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                worldpop_record = select_worldpop_population_record(payload, popyear=str(options["worldpop_year"]))
            elif not options["skip_worldpop_fetch"]:
                worldpop_record = fetch_worldpop_population_record(
                    dataset_key=str(options["worldpop_dataset_key"]),
                    iso3=str(options["worldpop_iso3"]),
                    popyear=str(options["worldpop_year"]),
                )
        except CommandError:
            raise
        except Exception as error:
            worldpop_error = str(error)

        inventory = build_migori_population_phase0_inventory(
            county=str(options["county"]),
            geojson_path=geojson_path,
            expected_ward_count=int(options["expected_ward_count"]),
            worldpop_dataset_key=str(options["worldpop_dataset_key"]),
            worldpop_iso3=str(options["worldpop_iso3"]),
            worldpop_popyear=str(options["worldpop_year"]),
            worldpop_record=worldpop_record,
            worldpop_fetch_error=worldpop_error,
        )
        rendered = inventory_to_json(inventory)

        output_path = options.get("output")
        if output_path:
            path = Path(output_path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote Migori source inventory to {path}"))

        self.stdout.write(rendered)

        if options["strict"]:
            failed_gates = [name for name, passed in inventory["phase0_gates"].items() if not passed]
            if failed_gates:
                raise CommandError(f"Phase 0 inventory failed strict gates: {', '.join(failed_gates)}")
