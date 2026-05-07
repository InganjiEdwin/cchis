from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from risk.migori_knbs_worldpop_reconciliation import DEFAULT_RECONCILIATION_SUMMARY_PATH
from risk.migori_worldpop_feature_dataset import (
    DEFAULT_COUNTY,
    DEFAULT_FEATURE_DATASET_SUMMARY_PATH,
    build_migori_worldpop_phase5_feature_dataset_summary,
    write_feature_dataset_summary,
)
from risk.migori_worldpop_population_csv import DEFAULT_SUMMARY_PATH
from risk.migori_worldpop_population_import import DEFAULT_EXPECTED_WARD_COUNT, DEFAULT_RELEASE_VERSION


class Command(BaseCommand):
    help = "Verify the Phase 5 Migori WorldPop population/exposure feature dataset."

    def add_arguments(self, parser):
        parser.add_argument("--dataset-ref", default="", help="FeatureDataset ref to verify. Defaults to latest WorldPop dataset.")
        parser.add_argument("--release-version", default=DEFAULT_RELEASE_VERSION)
        parser.add_argument("--expected-ward-count", type=int, default=DEFAULT_EXPECTED_WARD_COUNT)
        parser.add_argument("--county", default=DEFAULT_COUNTY)
        parser.add_argument("--phase1-summary", default=str(DEFAULT_SUMMARY_PATH))
        parser.add_argument("--reconciliation-summary", default=str(DEFAULT_RECONCILIATION_SUMMARY_PATH))
        parser.add_argument("--output", default=str(DEFAULT_FEATURE_DATASET_SUMMARY_PATH))
        parser.add_argument("--strict", action="store_true", help="Fail if any Phase 5 gate is false.")

    def handle(self, *args, **options):
        try:
            summary = build_migori_worldpop_phase5_feature_dataset_summary(
                dataset_ref=options["dataset_ref"] or None,
                release_version=str(options["release_version"]),
                phase1_summary_path=Path(options["phase1_summary"]).expanduser().resolve(),
                reconciliation_summary_path=Path(options["reconciliation_summary"]).expanduser().resolve(),
                expected_ward_count=int(options["expected_ward_count"]),
                county=str(options["county"]),
            )
            output_path = Path(options["output"]).expanduser().resolve()
            write_feature_dataset_summary(output_path, summary)
        except Exception as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Migori WorldPop feature dataset verification complete. "
                f"passed={summary['passed']} "
                f"dataset_ref={summary['dataset']['dataset_ref']} "
                f"rows={summary['dataset']['row_count']} "
                f"output={output_path}"
            )
        )
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))

        if options["strict"] and not summary["passed"]:
            failed_gates = [name for name, passed in summary["phase5_gates"].items() if not passed]
            raise CommandError(f"Migori WorldPop feature dataset verification failed: {', '.join(failed_gates)}")
