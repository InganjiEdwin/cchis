import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.comparison import build_model_comparison_summary
from risk.models import ModelRun


class Command(BaseCommand):
    help = "Compare the latest successful Logistic Regression and Random Forest runs and emit a promotion-decision summary."

    def add_arguments(self, parser):
        parser.add_argument("--lr-version", type=str, default="")
        parser.add_argument("--rf-version", type=str, default="")

    def _resolve_run(self, *, algorithm_name: str, model_version: str | None):
        queryset = ModelRun.objects.filter(status=ModelRun.STATUS_SUCCESS, algorithm_name=algorithm_name).order_by("-started_at")
        if model_version:
            queryset = queryset.filter(model_version=model_version)
        run = queryset.first()
        if run is None:
            raise CommandError(f"No successful run found for algorithm_name={algorithm_name} model_version={model_version or 'latest'}")
        return run

    def handle(self, *args, **options):
        logistic_run = self._resolve_run(
            algorithm_name="logistic-regression-baseline",
            model_version=options["lr_version"] or None,
        )
        random_forest_run = self._resolve_run(
            algorithm_name="random-forest-benchmark",
            model_version=options["rf_version"] or None,
        )
        comparison = build_model_comparison_summary(
            logistic_run=logistic_run,
            random_forest_run=random_forest_run,
        )
        self.stdout.write(json.dumps(comparison, indent=2, sort_keys=True, default=str))
