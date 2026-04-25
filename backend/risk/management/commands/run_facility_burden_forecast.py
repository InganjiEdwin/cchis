from django.core.management.base import BaseCommand

from risk.facility_forecasting import run_facility_burden_forecast_pipeline
from risk.tasks import run_facility_burden_forecast_task


class Command(BaseCommand):
    help = "Run or queue the facility burden Negative Binomial baseline without promoting it to a live dashboard contract."

    def add_arguments(self, parser):
        parser.add_argument("--model-version", type=str, default="fnb-v1")
        parser.add_argument("--horizon-days", type=int, default=7)
        parser.add_argument("--async", action="store_true", dest="run_async")

    def handle(self, *args, **options):
        model_version = options["model_version"]
        horizon_days = options["horizon_days"]
        run_async = options["run_async"]

        if not model_version.startswith("fnb-"):
            self.stderr.write(
                self.style.WARNING("Expected facility burden baseline versions to start with 'fnb-'")
            )

        if run_async:
            task = run_facility_burden_forecast_task.delay(
                model_version=model_version,
                horizon_days=horizon_days,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued facility burden forecast task with id={task.id} model_version={model_version}"
                )
            )
            return

        run = run_facility_burden_forecast_pipeline(
            model_version=model_version,
            horizon_days=horizon_days,
            execution_context="manual_command",
            run_purpose="forecast_scoring",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Facility burden forecast complete. Run id={run.id} model_version={run.model_version} "
                f"status={run.status}."
            )
        )
