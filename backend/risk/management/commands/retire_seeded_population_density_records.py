from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from risk.migori_seeded_population_retirement import (
    DEFAULT_COUNTY,
    DEFAULT_EXPECTED_WARD_COUNT,
    DEFAULT_RETIREMENT_SUMMARY_PATH,
    retire_seeded_population_density_records,
    write_retirement_summary,
)


class Command(BaseCommand):
    help = "Retire seeded demo population and population-density records replaced by a source-backed import."

    def add_arguments(self, parser):
        parser.add_argument(
            "--replacement-run-id",
            type=int,
            default=None,
            help="Replacement PopulationExposureIngestionRun id. Defaults to the latest successful gridded_population run.",
        )
        parser.add_argument("--output", default=str(DEFAULT_RETIREMENT_SUMMARY_PATH))
        parser.add_argument("--expected-ward-count", type=int, default=DEFAULT_EXPECTED_WARD_COUNT)
        parser.add_argument("--county", default=DEFAULT_COUNTY)
        parser.add_argument("--reason", default="")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the retirement. Without this flag the command performs a dry run.",
        )
        parser.add_argument("--strict", action="store_true", help="Fail if any retirement gate is false.")

    def handle(self, *args, **options):
        try:
            summary = retire_seeded_population_density_records(
                replacement_run_id=options["replacement_run_id"],
                apply=bool(options["apply"]),
                reason=options["reason"].strip()
                or "WorldPop 2026 Migori gridded population import replaced seeded population and density demo records.",
                expected_ward_count=int(options["expected_ward_count"]),
                county=str(options["county"]),
            )
            output_path = Path(options["output"]).expanduser().resolve()
            write_retirement_summary(output_path, summary)
        except Exception as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded population/density retirement complete. "
                f"applied={summary['applied']} "
                f"passed={summary['passed']} "
                f"population_marked={summary['records_marked']['population_baseline_records']} "
                f"density_marked={summary['records_marked']['density_exposure_records']} "
                f"output={output_path}"
            )
        )
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))

        if options["strict"] and not summary["passed"]:
            failed_gates = [name for name, passed in summary["gates"].items() if not passed]
            raise CommandError(f"Seeded population/density retirement failed strict gates: {', '.join(failed_gates)}")
