from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from risk.migori_worldpop_population_csv import DEFAULT_OUTPUT_CSV_PATH, DEFAULT_SUMMARY_PATH
from risk.migori_worldpop_population_validation import (
    DEFAULT_COUNTY,
    DEFAULT_EXPECTED_ROW_COUNT,
    DEFAULT_VALIDATION_SUMMARY_PATH,
    build_migori_worldpop_phase2_validation,
    write_validation_summary,
)


class Command(BaseCommand):
    help = "Run Phase 2 dry validation for the Migori WorldPop population CSV."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_OUTPUT_CSV_PATH))
        parser.add_argument("--phase1-summary", default=str(DEFAULT_SUMMARY_PATH))
        parser.add_argument("--output", default=str(DEFAULT_VALIDATION_SUMMARY_PATH))
        parser.add_argument("--source-type", default="gridded_population")
        parser.add_argument("--expected-row-count", type=int, default=DEFAULT_EXPECTED_ROW_COUNT)
        parser.add_argument("--county", default=DEFAULT_COUNTY)
        parser.add_argument("--strict", action="store_true", help="Fail if any Phase 2 gate is false.")

    def handle(self, *args, **options):
        try:
            summary = build_migori_worldpop_phase2_validation(
                csv_path=Path(options["file"]),
                phase1_summary_path=Path(options["phase1_summary"]) if options["phase1_summary"] else None,
                source_type=str(options["source_type"]),
                expected_row_count=int(options["expected_row_count"]),
                county=str(options["county"]),
            )
            output_path = Path(options["output"]).expanduser().resolve()
            write_validation_summary(output_path, summary)
        except Exception as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Migori WorldPop population CSV validation complete. "
                f"passed={summary['passed']} "
                f"rows={summary['inspection']['records_seen']} "
                f"accepted={summary['inspection']['records_loaded']} "
                f"rejected={summary['inspection']['records_rejected']} "
                f"output={output_path}"
            )
        )
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))

        if options["strict"] and not summary["passed"]:
            failed_gates = [name for name, passed in summary["phase2_gates"].items() if not passed]
            raise CommandError(f"Phase 2 validation failed strict gates: {', '.join(failed_gates)}")
