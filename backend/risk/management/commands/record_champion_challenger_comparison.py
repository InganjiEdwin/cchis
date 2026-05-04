import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.comparison import (
    latest_benchmark_challenger_run,
    record_champion_challenger_comparison,
)
from risk.models import ModelRegistryEntry, ModelRun


class Command(BaseCommand):
    help = "Persist a Phase 4 champion/challenger benchmark comparison without changing live promotion state."

    def add_arguments(self, parser):
        parser.add_argument("--champion-registry-entry-id", type=int, default=None)
        parser.add_argument("--challenger-model-run-id", type=int, default=None)
        parser.add_argument("--challenger-version", type=str, default="")
        parser.add_argument("--challenger-algorithm-name", type=str, default="")

    def _champion_entry(self, registry_entry_id: int | None):
        if registry_entry_id is None:
            return None
        try:
            return ModelRegistryEntry.objects.get(id=registry_entry_id)
        except ModelRegistryEntry.DoesNotExist as error:
            raise CommandError(f"ModelRegistryEntry id={registry_entry_id} does not exist.") from error

    def _challenger_run(self, *, model_run_id: int | None, model_version: str, algorithm_name: str):
        if model_run_id is not None:
            try:
                return ModelRun.objects.get(id=model_run_id)
            except ModelRun.DoesNotExist as error:
                raise CommandError(f"ModelRun id={model_run_id} does not exist.") from error

        if model_version:
            queryset = ModelRun.objects.filter(status=ModelRun.STATUS_SUCCESS, model_version=model_version)
            if algorithm_name:
                queryset = queryset.filter(algorithm_name=algorithm_name)
            run = queryset.order_by("-started_at", "-id").first()
            if run is None:
                raise CommandError(f"No successful challenger ModelRun found for model_version={model_version}.")
            return run

        return latest_benchmark_challenger_run(algorithm_name=algorithm_name)

    def handle(self, *args, **options):
        try:
            comparison = record_champion_challenger_comparison(
                champion_entry=self._champion_entry(options["champion_registry_entry_id"]),
                challenger_run=self._challenger_run(
                    model_run_id=options["challenger_model_run_id"],
                    model_version=options["challenger_version"],
                    algorithm_name=options["challenger_algorithm_name"],
                ),
                metadata={"source": "record_champion_challenger_comparison_command"},
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        payload = {
            "comparison_id": comparison.id,
            "comparison_public_id": str(comparison.public_id),
            "champion_registry_entry_id": comparison.champion_registry_entry_id,
            "champion_model_run_id": comparison.champion_model_run_id,
            "challenger_model_run_id": comparison.challenger_model_run_id,
            "challenger_model_version": comparison.challenger_model_version,
            "benchmark_status": comparison.benchmark_status,
            "comparison_validity": comparison.comparison_validity,
            "promotion_blockers": comparison.promotion_blockers,
            "dashboard_summary": comparison.dashboard_summary,
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
