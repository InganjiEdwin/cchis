from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from risk.migori_worldpop_connector import (
    DEFAULT_CONNECTOR_SUMMARY_PATH,
    build_migori_worldpop_phase6_connector_summary,
    write_connector_summary,
)
from risk.migori_worldpop_population_csv import DEFAULT_SUMMARY_PATH
from risk.migori_worldpop_population_import import DEFAULT_EXPECTED_WARD_COUNT, DEFAULT_RELEASE_VERSION


class Command(BaseCommand):
    help = "Verify the Phase 6 Migori WorldPop source-data connector run."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, default=None)
        parser.add_argument("--phase1-summary", default=str(DEFAULT_SUMMARY_PATH))
        parser.add_argument("--expected-ward-count", type=int, default=DEFAULT_EXPECTED_WARD_COUNT)
        parser.add_argument("--expected-release-version", default=DEFAULT_RELEASE_VERSION)
        parser.add_argument("--output", default=str(DEFAULT_CONNECTOR_SUMMARY_PATH))
        parser.add_argument("--strict", action="store_true", help="Fail if any Phase 6 gate is false.")

    def handle(self, *args, **options):
        try:
            summary = build_migori_worldpop_phase6_connector_summary(
                run_id=options["run_id"],
                phase1_summary_path=Path(options["phase1_summary"]).expanduser().resolve(),
                expected_ward_count=int(options["expected_ward_count"]),
                expected_release_version=str(options["expected_release_version"]),
            )
            output_path = Path(options["output"]).expanduser().resolve()
            write_connector_summary(output_path, summary)
        except Exception as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Migori WorldPop source-data connector verification complete. "
                f"passed={summary['passed']} "
                f"run_id={summary['connector_run']['id']} "
                f"upload={summary['upload_batch']['public_id']} "
                f"output={output_path}"
            )
        )
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))

        if options["strict"] and not summary["passed"]:
            failed_gates = [name for name, passed in summary["phase6_gates"].items() if not passed]
            raise CommandError(f"Migori WorldPop source-data connector verification failed: {', '.join(failed_gates)}")
