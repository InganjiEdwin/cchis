from datetime import date

from django.core.management.base import BaseCommand, CommandError

from risk.chirps_ingestion import ingest_chirps_rainfall
from risk.climate.connectors.chirps import CHIRPS_PRODUCT_STATUS_FINAL


class Command(BaseCommand):
    help = "Ingest bounded historical CHIRPS v3 final daily rainfall for active Migori wards."

    def add_arguments(self, parser):
        parser.add_argument("--start-date", required=True, help="Inclusive YYYY-MM-DD source date.")
        parser.add_argument("--end-date", required=True, help="Inclusive YYYY-MM-DD source date.")
        parser.add_argument("--variant", choices=["sat", "rnl"], default="sat")
        parser.add_argument(
            "--product-status",
            choices=[CHIRPS_PRODUCT_STATUS_FINAL],
            default=CHIRPS_PRODUCT_STATUS_FINAL,
        )
        parser.add_argument("--dry-run", action="store_true", help="Fetch and aggregate without writing records.")
        parser.add_argument("--resume", action="store_true", help="Skip complete dates already ingested.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Explicitly reprocess and update existing stable CHIRPS identities.",
        )

    def handle(self, *args, **options):
        try:
            start_date = date.fromisoformat(options["start_date"])
            end_date = date.fromisoformat(options["end_date"])
        except ValueError as exc:
            raise CommandError("CHIRPS dates must use YYYY-MM-DD.") from exc

        try:
            summary = ingest_chirps_rainfall(
                start_date=start_date,
                end_date=end_date,
                variant=options["variant"],
                product_status=options["product_status"],
                dry_run=options["dry_run"],
                resume=options["resume"],
                force=options["force"],
            )
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            "CHIRPS ingestion "
            f"status={summary['status']} run_id={summary['run_id'] or 'dry-run'} "
            f"provider={summary['provider']} version={summary['version']} "
            f"variant={summary['variant']} product_status={summary['product_status']}"
        )
        self.stdout.write(
            "Dates: "
            f"requested={summary['dates_requested']} assets_found={summary['assets_found']} "
            f"processed={summary['processed_dates']} "
            f"unavailable={len(summary['unavailable_dates'])} rejected={len(summary['rejected_dates'])}"
        )
        self.stdout.write(
            "Records: "
            f"created={summary['records_created']} updated={summary['records_updated']} "
            f"skipped={summary['records_skipped']} rejected={summary['records_rejected']}"
        )
        if summary["unavailable_dates"]:
            self.stdout.write("Unavailable dates: " + ", ".join(summary["unavailable_dates"]))
        if summary["rejected_dates"]:
            self.stdout.write("Rejected dates: " + ", ".join(summary["rejected_dates"]))

        if summary["status"] == "FAILED":
            raise CommandError("No requested CHIRPS dates were successfully processed.")
