from django.core.management.base import BaseCommand
from django.utils import timezone

from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.tasks import run_random_forest_benchmark_task


class Command(BaseCommand):
    help = "Run or queue the explicit Random Forest benchmark path without changing model-promotion state."

    def add_arguments(self, parser):
        parser.add_argument("--month", type=int, default=timezone.now().month)
        parser.add_argument("--model-version", type=str, default="rf-v1")
        parser.add_argument("--async", action="store_true", dest="run_async")

    def handle(self, *args, **options):
        month = options["month"]
        model_version = options["model_version"]
        run_async = options["run_async"]

        if not model_version.startswith("rf-"):
            self.stderr.write(self.style.WARNING("Expected Random Forest benchmark versions to start with 'rf-'"))

        if run_async:
            task = run_random_forest_benchmark_task.delay(month=month, model_version=model_version)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued Random Forest benchmark task with id={task.id} model_version={model_version}"
                )
            )
            return

        created_scores = run_mock_prediction_pipeline(
            month=month,
            model_version=model_version,
            algorithm="random_forest",
            trigger_alerts=False,
            send_sms=False,
            dual_model=False,
            execution_context="manual_command",
            run_purpose="benchmark_scoring",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Random Forest benchmark complete. Created {len(created_scores)} risk scores "
                f"with model_version={model_version}."
            )
        )
