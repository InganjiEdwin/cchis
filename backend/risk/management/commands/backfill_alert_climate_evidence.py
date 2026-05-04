import json

from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder

from risk.climate_horizon_audit import backfill_alert_climate_evidence


class Command(BaseCommand):
    help = "Backfill climate evidence into existing alert metadata for Phase 5 frontend/audit consistency."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Persist updates. Defaults to dry-run.")
        parser.add_argument("--force", action="store_true", help="Replace existing climate evidence even when valid.")
        parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of linked alerts to scan.")
        parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")

    def handle(self, *args, **options):
        result = backfill_alert_climate_evidence(
            dry_run=not options["apply"],
            force=options["force"],
            limit=options["limit"],
        )
        if options["format"] == "json":
            self.stdout.write(json.dumps(result, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
            return

        mode = "dry-run" if result["dry_run"] else "applied"
        self.stdout.write(f"Alert climate evidence backfill {mode}.")
        self.stdout.write(
            f"Scanned={result['scanned_count']} updated={result['updated_count']} skipped={result['skipped_count']}"
        )
        for example in result["examples"]:
            self.stdout.write(
                f"- alert:{example['alert_id']} {example['status']} "
                f"{example.get('record_type', '')} {example.get('climate_coverage_status', '')}"
            )
