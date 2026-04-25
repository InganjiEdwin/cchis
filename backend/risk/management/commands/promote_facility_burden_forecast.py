from django.core.management.base import BaseCommand, CommandError

from risk.facility_forecasting import promote_facility_forecast_run
from risk.models import FacilityForecastRun


class Command(BaseCommand):
    help = "Promote a successful facility burden forecast run for dashboard readiness truth after explicit review."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, default=None)
        parser.add_argument("--model-version", type=str, default=None)
        parser.add_argument("--promoted-by", type=str, default="manual_operator")
        parser.add_argument("--note", type=str, default="")

    def handle(self, *args, **options):
        run_id = options["run_id"]
        model_version = options["model_version"]
        promoted_by = options["promoted_by"]
        note = options["note"]

        if not run_id and not model_version:
            raise CommandError("Provide --run-id or --model-version.")

        queryset = FacilityForecastRun.objects.filter(status=FacilityForecastRun.STATUS_SUCCESS).order_by("-started_at")
        run = queryset.filter(id=run_id).first() if run_id else queryset.filter(model_version=model_version).first()
        if run is None:
            raise CommandError("No successful facility forecast run found for the requested selector.")

        run = promote_facility_forecast_run(run, promoted_by=promoted_by, note=note)
        self.stdout.write(
            self.style.SUCCESS(
                f"Promoted facility burden forecast run id={run.id} model_version={run.model_version}"
            )
        )
