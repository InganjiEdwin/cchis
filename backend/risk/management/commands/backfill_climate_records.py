import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.climate_records import backfill_climate_records_from_ingestion_runs


class Command(BaseCommand):
    help = "Backfill ClimateRecord ledger rows from rainfall ingestion results."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Persist enriched ingestion JSON and ClimateRecord rows.")
        parser.add_argument("--run-id", type=int, default=None, help="Optional rainfall ingestion run id.")
        parser.add_argument(
            "--infer-legacy-open-meteo-horizon-days",
            type=int,
            default=None,
            help=(
                "Optional fallback horizon for legacy Open-Meteo aggregate rows that predate "
                "the forecast issue/valid/lead-day contract."
            ),
        )
        parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")

    def handle(self, *args, **options):
        try:
            result = backfill_climate_records_from_ingestion_runs(
                dry_run=not options["apply"],
                infer_legacy_open_meteo_horizon_days=options["infer_legacy_open_meteo_horizon_days"],
                run_id=options["run_id"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        if options["format"] == "json":
            self.stdout.write(json.dumps(result, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
            return

        mode = "dry-run" if result["dry_run"] else "applied"
        self.stdout.write(f"ClimateRecord backfill {mode}.")
        self.stdout.write(
            f"table_available={result['climate_record_table_available']} "
            f"runs={result['runs_scanned']} rows={result['rows_seen']} "
            f"ready={result['ready_rows']} skipped={result['skipped_rows']} "
            f"saved={result['saved_records']}"
        )
        for reason, count in sorted((result.get("skip_reasons") or {}).items()):
            self.stdout.write(f"- skip {reason}: {count}")
