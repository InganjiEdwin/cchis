from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from risk.migori_worldpop_population_csv import DEFAULT_SUMMARY_PATH
from risk.migori_worldpop_population_import import (
    DEFAULT_COUNTY,
    DEFAULT_EXPECTED_WARD_COUNT,
    DEFAULT_IMPORT_SUMMARY_PATH,
    build_migori_worldpop_phase3_import_summary,
    write_import_summary,
)
from risk.migori_worldpop_population_validation import DEFAULT_VALIDATION_SUMMARY_PATH


class Command(BaseCommand):
    help = "Verify the Phase 3 Migori WorldPop population import and persist an import summary."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, default=None)
        parser.add_argument("--phase1-summary", default=str(DEFAULT_SUMMARY_PATH))
        parser.add_argument("--validation-summary", default=str(DEFAULT_VALIDATION_SUMMARY_PATH))
        parser.add_argument("--output", default=str(DEFAULT_IMPORT_SUMMARY_PATH))
        parser.add_argument("--expected-ward-count", type=int, default=DEFAULT_EXPECTED_WARD_COUNT)
        parser.add_argument("--county", default=DEFAULT_COUNTY)
        parser.add_argument("--strict", action="store_true", help="Fail if any Phase 3 gate is false.")

    def handle(self, *args, **options):
        try:
            summary = build_migori_worldpop_phase3_import_summary(
                run_id=options["run_id"],
                phase1_summary_path=Path(options["phase1_summary"]).expanduser().resolve(),
                validation_summary_path=Path(options["validation_summary"]).expanduser().resolve(),
                expected_ward_count=int(options["expected_ward_count"]),
                county=str(options["county"]),
            )
            output_path = Path(options["output"]).expanduser().resolve()
            write_import_summary(output_path, summary)
        except Exception as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Migori WorldPop population import verification complete. "
                f"passed={summary['passed']} "
                f"run_id={summary['run']['id']} "
                f"population_records={summary['records']['population_baseline_records']} "
                f"density_records={summary['records']['density_exposure_records']} "
                f"output={output_path}"
            )
        )
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))

        if options["strict"] and not summary["passed"]:
            failed_gates = [name for name, passed in summary["phase3_gates"].items() if not passed]
            raise CommandError(f"Phase 3 import verification failed strict gates: {', '.join(failed_gates)}")
