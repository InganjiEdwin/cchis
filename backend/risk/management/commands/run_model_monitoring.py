import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.monitoring import run_model_monitoring
from risk.models import ModelRegistryEntry


class Command(BaseCommand):
    help = "Run Phase 2 drift and calibration monitoring for the active ward-risk model registry entry."

    def add_arguments(self, parser):
        parser.add_argument("--registry-entry-id", type=int, default=None)
        parser.add_argument("--label-dataset-ref", type=str, default="")

    def _registry_entry(self, registry_entry_id: int | None):
        if registry_entry_id is None:
            return None
        try:
            return ModelRegistryEntry.objects.get(id=registry_entry_id)
        except ModelRegistryEntry.DoesNotExist as error:
            raise CommandError(f"ModelRegistryEntry id={registry_entry_id} does not exist.") from error

    def handle(self, *args, **options):
        try:
            snapshots = run_model_monitoring(
                registry_entry=self._registry_entry(options["registry_entry_id"]),
                label_dataset_ref=options["label_dataset_ref"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        payload = {
            "monitoring_run_id": str(snapshots[0].monitoring_run_id) if snapshots else None,
            "registry_entry_id": snapshots[0].registry_entry_id if snapshots else None,
            "model_run_id": snapshots[0].model_run_id if snapshots else None,
            "snapshot_count": len(snapshots),
            "snapshots": [
                {
                    "metric_name": snapshot.metric_name,
                    "value": snapshot.value,
                    "baseline_value": snapshot.baseline_value,
                    "threshold_value": snapshot.threshold_value,
                    "threshold_version": snapshot.threshold_version,
                    "state": snapshot.state,
                    "source_dataset_refs": snapshot.source_dataset_refs,
                }
                for snapshot in snapshots
            ],
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
