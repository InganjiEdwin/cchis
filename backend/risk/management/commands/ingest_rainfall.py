from django.core.management.base import BaseCommand

from risk.ml.ingestion import fetch_rainfall_for_wards
from risk.models import Ward
from risk.tasks import run_rainfall_ingestion_task


class Command(BaseCommand):
    help = "Run rainfall ingestion for active wards and persist an ingestion-run record."

    def add_arguments(self, parser):
        parser.add_argument("--async", action="store_true", dest="run_async")

    def handle(self, *args, **options):
        if options["run_async"]:
            task = run_rainfall_ingestion_task.delay()
            self.stdout.write(self.style.SUCCESS(f"Queued rainfall ingestion task with id={task.id}"))
            return

        wards = list(Ward.objects.filter(is_active=True).order_by("name"))
        _, ingestion_run = fetch_rainfall_for_wards(wards, return_ingestion_run=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"Rainfall ingestion complete. run_id={ingestion_run.id} status={ingestion_run.status} "
                f"source_kind={ingestion_run.source_kind} freshness={ingestion_run.freshness_state} "
                f"loaded={ingestion_run.records_loaded}/{ingestion_run.records_seen}"
            )
        )
