from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from risk.migori_knbs_worldpop_reconciliation import (
    DEFAULT_COUNTY,
    DEFAULT_COUNTY_BASELINE_PATH,
    DEFAULT_EXPECTED_WARD_COUNT,
    DEFAULT_PROJECTION_PATH,
    DEFAULT_RECONCILIATION_SUMMARY_PATH,
    DEFAULT_SUB_COUNTY_BASELINE_PATH,
    DEFAULT_TARGET_YEAR,
    DEFAULT_WARNING_THRESHOLD,
    build_migori_knbs_worldpop_reconciliation,
    ensure_knbs_source_files,
    write_reconciliation_summary,
)
from risk.migori_worldpop_population_csv import DEFAULT_SUMMARY_PATH as DEFAULT_PHASE1_SUMMARY_PATH
from risk.migori_worldpop_population_import import DEFAULT_IMPORT_SUMMARY_PATH


class Command(BaseCommand):
    help = "Reconcile the imported Migori WorldPop total against KNBS baseline and projection references."

    def add_arguments(self, parser):
        parser.add_argument("--county", default=DEFAULT_COUNTY)
        parser.add_argument("--target-year", type=int, default=DEFAULT_TARGET_YEAR)
        parser.add_argument("--warning-threshold", type=float, default=DEFAULT_WARNING_THRESHOLD)
        parser.add_argument("--expected-ward-count", type=int, default=DEFAULT_EXPECTED_WARD_COUNT)
        parser.add_argument("--worldpop-import-summary", default=str(DEFAULT_IMPORT_SUMMARY_PATH))
        parser.add_argument("--phase1-summary", default=str(DEFAULT_PHASE1_SUMMARY_PATH))
        parser.add_argument("--county-baseline", default=str(DEFAULT_COUNTY_BASELINE_PATH))
        parser.add_argument("--sub-county-baseline", default=str(DEFAULT_SUB_COUNTY_BASELINE_PATH))
        parser.add_argument("--projection", default=str(DEFAULT_PROJECTION_PATH))
        parser.add_argument("--output", default=str(DEFAULT_RECONCILIATION_SUMMARY_PATH))
        parser.add_argument(
            "--download-if-missing",
            action="store_true",
            help="Download KNBS source workbooks into the ignored source cache if they are missing.",
        )
        parser.add_argument(
            "--verify-tls",
            action="store_true",
            help="Deprecated compatibility flag; KNBS TLS is verified by default.",
        )
        parser.add_argument(
            "--allow-insecure-download",
            action="store_true",
            help="Disable KNBS TLS verification only for documented recovery when the KNBS host certificate is broken.",
        )
        parser.add_argument("--strict", action="store_true", help="Fail if any reconciliation gate is false.")

    def handle(self, *args, **options):
        try:
            download_results = ensure_knbs_source_files(
                download_if_missing=bool(options["download_if_missing"]),
                verify_tls=not bool(options["allow_insecure_download"]),
            )
            summary = build_migori_knbs_worldpop_reconciliation(
                county=str(options["county"]),
                target_year=int(options["target_year"]),
                warning_threshold=float(options["warning_threshold"]),
                expected_ward_count=int(options["expected_ward_count"]),
                worldpop_import_summary_path=Path(options["worldpop_import_summary"]).expanduser().resolve(),
                phase1_summary_path=Path(options["phase1_summary"]).expanduser().resolve(),
                county_baseline_path=Path(options["county_baseline"]).expanduser().resolve(),
                sub_county_baseline_path=Path(options["sub_county_baseline"]).expanduser().resolve(),
                projection_path=Path(options["projection"]).expanduser().resolve(),
            )
            summary["knbs"]["download_results"] = download_results
            output_path = Path(options["output"]).expanduser().resolve()
            write_reconciliation_summary(output_path, summary)
        except Exception as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Migori KNBS/WorldPop reconciliation complete. "
                f"passed={summary['passed']} "
                f"worldpop={summary['worldpop']['population_total']} "
                f"knbs_projection={summary['knbs']['projection']['target_projection']} "
                f"output={output_path}"
            )
        )
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))

        if options["strict"] and not summary["passed"]:
            failed_gates = [name for name, passed in summary["gates"].items() if not passed]
            raise CommandError(f"Migori KNBS/WorldPop reconciliation failed strict gates: {', '.join(failed_gates)}")
